from __future__ import annotations

import concurrent.futures
import logging
import threading
from typing import Any
from uuid import uuid4

from langgraph.types import Command

from app.graph.workflow import compile_graph

_TERMINAL_STATUSES = {"completed", "failed"}
logger = logging.getLogger(__name__)


class GraphRuntime:
    def __init__(self, llm, db_url: str = "sqlite:///./agent_state.db"):
        self.llm = llm
        self.llm_backend = getattr(llm, "name", "unknown")
        self.graph = compile_graph(llm=llm, db_url=db_url)
        self._known_runs: set[str] = set()
        # tracks runs that still have an active background thread executing
        self._active_runs: set[str] = set()
        self._active_lock = threading.Lock()
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=8)

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def start_run(
        self,
        objective: str,
        service: str,
        env: str,
        run_id: str | None = None,
        agent_mode: str = "mock",
    ) -> str:
        """Start a run in a background thread; return run_id immediately."""
        run_id = run_id or str(uuid4())
        initial_state = {
            "run_id": run_id,
            "objective": objective,
            "service": service,
            "env": env,
            "agent_mode": agent_mode,
            "llm_backend": self.llm_backend,
            "status": "running",
            "event_log": [],
            "clarifications": {},
        }

        if agent_mode == "llm" and self.llm_backend == "mock":
            initial_state["llm_warning"] = (
                "agent_mode=llm but LLM_BACKEND=mock. "
                "Set LLM_BACKEND=ollama or openai for real model inference."
            )
            initial_state["event_log"].append(
                {
                    "event": "llm_backend_warning",
                    "data": {
                        "agent_mode": agent_mode,
                        "llm_backend": self.llm_backend,
                        "message": initial_state["llm_warning"],
                    },
                }
            )
        self._known_runs.add(run_id)
        with self._active_lock:
            self._active_runs.add(run_id)
        logger.info(
            "run.start run_id=%s service=%s env=%s mode=%s",
            run_id,
            service,
            env,
            agent_mode,
        )
        self._executor.submit(self._invoke, run_id, initial_state)
        return run_id

    def resume(self, run_id: str, decision: dict[str, Any]) -> bool:
        """Resume a paused run in a background thread; return False if unknown."""
        if run_id not in self._known_runs:
            return False
        with self._active_lock:
            self._active_runs.add(run_id)
        logger.info("run.resume_requested run_id=%s decision=%s", run_id, decision)
        self._executor.submit(self._resume, run_id, decision)
        return True

    def get_state(self, run_id: str) -> dict[str, Any]:
        if run_id not in self._known_runs:
            return {"exists": False}
        config = {"configurable": {"thread_id": run_id}}
        snapshot = self.graph.get_state(config)
        if snapshot is None or not snapshot.values:
            # Run is registered but the first graph checkpoint hasn't landed yet.
            return {
                "exists": True,
                "values": {"status": "starting", "run_id": run_id, "event_log": []},
                "next": [],
                "tasks": [],
                "config": config,
                "metadata": {},
                "created_at": "",
            }
        return self._snapshot_to_dict(snapshot)

    def get_history(self, run_id: str) -> list[dict[str, Any]]:
        if run_id not in self._known_runs:
            return []
        config = {"configurable": {"thread_id": run_id}}
        history = list(self.graph.get_state_history(config))
        return [self._snapshot_to_dict(s) for s in history]

    def is_active(self, run_id: str) -> bool:
        with self._active_lock:
            return run_id in self._active_runs

    # ------------------------------------------------------------------ #
    # Internal helpers                                                     #
    # ------------------------------------------------------------------ #

    def _invoke(self, run_id: str, initial_state: dict[str, Any]) -> None:
        config = {"configurable": {"thread_id": run_id}}
        try:
            logger.info("run.invoke.begin run_id=%s", run_id)
            self.graph.invoke(initial_state, config=config)
            status = self.get_state(run_id).get("values", {}).get("status", "unknown")
            logger.info("run.invoke.end run_id=%s status=%s", run_id, status)
        except Exception:
            logger.exception("run.invoke.error run_id=%s", run_id)
            raise
        finally:
            with self._active_lock:
                self._active_runs.discard(run_id)

    def _resume(self, run_id: str, decision: dict[str, Any]) -> None:
        config = {"configurable": {"thread_id": run_id}}
        try:
            logger.info("run.resume.begin run_id=%s", run_id)
            self.graph.invoke(Command(resume=decision), config=config)
            status = self.get_state(run_id).get("values", {}).get("status", "unknown")
            logger.info("run.resume.end run_id=%s status=%s", run_id, status)
        except Exception:
            logger.exception("run.resume.error run_id=%s", run_id)
            raise
        finally:
            with self._active_lock:
                self._active_runs.discard(run_id)

    @staticmethod
    def _snapshot_to_dict(snapshot: Any) -> dict[str, Any]:
        if snapshot is None:
            return {"exists": False}

        values = dict(snapshot.values or {})

        # Detect interrupt: LangGraph checkpoints state BEFORE a node with interrupt()
        # completes, so values["status"] stays at the pre-interrupt value ("running").
        # We derive the correct status from the pending tasks instead.
        interrupt_payload: dict[str, Any] | None = None
        for task in snapshot.tasks or []:
            interrupts = getattr(task, "interrupts", ())
            if interrupts:
                interrupt_payload = interrupts[0].value if interrupts else None
                break

        if interrupt_payload is not None:
            values["status"] = "paused"
            values["pending_interrupt"] = interrupt_payload

        return {
            "exists": True,
            "values": values,
            "next": list(snapshot.next or []),
            "tasks": [str(task) for task in (snapshot.tasks or [])],
            "config": dict(snapshot.config or {}),
            "metadata": dict(snapshot.metadata or {}),
            "created_at": str(getattr(snapshot, "created_at", "")),
        }


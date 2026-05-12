from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from langgraph.types import interrupt

from app.llm.base import LLMMessage  # noqa: F401 – used by llm_subagents
from app.graph.llm_subagents import (
    generate_synthetic_value,
    llm_investigator,
    llm_planner,
    llm_remediator,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _evt(state: dict[str, Any], event: str, data: dict[str, Any] | None = None) -> None:
    state.setdefault("event_log", []).append(
        {
            "ts": datetime.now(timezone.utc).isoformat(),
            "event": event,
            "data": data or {},
        }
    )


def _append_memory_list(state: dict[str, Any], key: str, item: dict[str, Any]) -> None:
    state.setdefault("memory", {}).setdefault(key, []).append(item)


def _is_llm(state: dict[str, Any]) -> bool:
    return state.get("agent_mode", "mock") == "llm"


# ---------------------------------------------------------------------------
# Clarification interrupt helper (shared by all subagents in LLM mode)
# ---------------------------------------------------------------------------

def _maybe_clarify(
    state: dict[str, Any],
    llm: Any,
    subagent_result: dict[str, Any],
) -> None:
    """
    If the LLM subagent signals it needs clarification, interrupt the graph.
    On resume the operator either supplies a value or passes None → synthetic.
    The resolved value is stored in state["clarifications"].
    """
    if not subagent_result.get("needs_clarification"):
        return
    if not _is_llm(state):
        return

    field = subagent_result.get("clarification_field", "additional_context")
    question = subagent_result.get("clarification_question", "Please provide additional context.")

    payload = {
        "scope": "agent",
        "type": "clarification_required",
        "run_id": state.get("run_id"),
        "question": question,
        "field": field,
        "synthetic_available": True,
    }
    state["pending_interrupt"] = payload
    state["status"] = "paused"
    _evt(state, "clarification_requested", {"field": field, "question": question})

    decision = interrupt(payload)
    state["pending_interrupt"] = {}
    state["status"] = "running"
    _evt(state, "clarification_resolved", decision)

    value = decision.get("value")
    if value is None:
        # Human skipped → synthesise
        value = generate_synthetic_value(
            llm,
            field,
            {"service": state.get("service"), "objective": state.get("objective")},
        )
        _evt(state, "synthetic_generated", {"field": field, "value": value})

    state.setdefault("clarifications", {})[field] = value


# ---------------------------------------------------------------------------
# Mock sub-agent implementations (deterministic, no LLM)
# ---------------------------------------------------------------------------

def _mock_planner(state: dict[str, Any]) -> None:
    steps = [
        "Inspect metrics and logs",
        "Correlate with recent deploys and config changes",
        "Propose lowest-risk remediation",
    ]
    state["agenda"] = steps
    state["parent_phase"] = "investigate"
    _evt(state, "planner_completed", {"steps": steps, "mode": "mock"})


def _mock_investigator(state: dict[str, Any]) -> None:
    evidence = {
        "service": state.get("service", "unknown-service"),
        "signals": [
            "5xx increased from 0.2% to 6.7%",
            "p95 latency rose from 180ms to 980ms",
            "deploy occurred 9 minutes before spike",
        ],
    }
    _append_memory_list(state, "evidence", evidence)
    state.setdefault("memory", {})["chosen_hypothesis"] = {
        "hypothesis": "Regression in latest release",
        "confidence": 0.82,
    }
    state["parent_phase"] = "propose"
    _evt(state, "investigator_completed", evidence)


def _mock_remediator(state: dict[str, Any]) -> None:
    proposal = {
        "type": "rollback",
        "target": state.get("service", "unknown-service"),
        "risk": "low",
        "reason": "Incident strongly correlates with latest deploy",
        "expected_recovery_time": "2-3 minutes",
    }
    state.setdefault("memory", {})["proposed_action"] = proposal
    _evt(state, "remediator_proposed", {**proposal, "mode": "mock"})


def _mock_verifier(state: dict[str, Any]) -> None:
    verification = {"recovered": True, "error_rate": "0.4%", "latency_p95_ms": 230}
    state.setdefault("memory", {})["verification"] = verification
    _evt(state, "verifier_completed", {**verification, "mode": "mock"})


# ---------------------------------------------------------------------------
# LLM sub-agent wrappers (call real LLM, handle clarifications)
# ---------------------------------------------------------------------------

def _llm_plan(state: dict[str, Any], llm: Any) -> None:
    result = llm_planner(state, llm)
    _evt(
        state,
        "llm_subagent_result",
        {
            "subagent": "planner",
            "source": result.get("source", "unknown"),
            "steps": result.get("steps", []),
            "needs_clarification": result.get("needs_clarification", False),
            "error": result.get("error", ""),
        },
    )
    _maybe_clarify(state, llm, result)
    state["agenda"] = result["steps"]
    state["parent_phase"] = "investigate"
    _evt(state, "planner_completed", {"steps": result["steps"], "mode": "llm"})


def _llm_investigate(state: dict[str, Any], llm: Any) -> None:
    result = llm_investigator(state, llm)
    _evt(
        state,
        "llm_subagent_result",
        {
            "subagent": "investigator",
            "source": result.get("source", "unknown"),
            "hypothesis": result.get("hypothesis"),
            "confidence": result.get("confidence"),
            "evidence_summary": result.get("evidence_summary", ""),
            "needs_clarification": result.get("needs_clarification", False),
            "error": result.get("error", ""),
        },
    )
    _maybe_clarify(state, llm, result)

    evidence = {
        "service": state.get("service"),
        "mode": "llm",
        "signals": result.get("new_signals", []),
        "hypothesis": result.get("hypothesis"),
        "confidence": result.get("confidence"),
        "evidence_summary": result.get("evidence_summary"),
        "telemetry": result.get("telemetry", {}),
    }
    _append_memory_list(state, "evidence", evidence)
    state.setdefault("memory", {})["chosen_hypothesis"] = {
        "hypothesis": result.get("hypothesis"),
        "confidence": result.get("confidence"),
        "evidence_summary": result.get("evidence_summary"),
    }
    state["parent_phase"] = "propose"
    _evt(state, "investigator_completed", {
        "hypothesis": result.get("hypothesis"),
        "confidence": result.get("confidence"),
        "mode": "llm",
    })


def _llm_remediate(state: dict[str, Any], llm: Any) -> None:
    result = llm_remediator(state, llm)
    _evt(
        state,
        "llm_subagent_result",
        {
            "subagent": "remediator",
            "source": result.get("source", "unknown"),
            "type": result.get("type"),
            "target": result.get("target"),
            "risk": result.get("risk"),
            "reason": result.get("reason"),
            "needs_clarification": result.get("needs_clarification", False),
            "error": result.get("error", ""),
        },
    )
    _maybe_clarify(state, llm, result)

    proposal = {
        "type": result["type"],
        "target": result["target"],
        "risk": result["risk"],
        "reason": result["reason"],
        "rollback_steps": result["rollback_steps"],
        "expected_recovery_time": result.get("expected_recovery_time", "unknown"),
        "mode": "llm",
    }
    state.setdefault("memory", {})["proposed_action"] = proposal
    _evt(state, "remediator_proposed", proposal)


# ---------------------------------------------------------------------------
# Parent agent factory
# ---------------------------------------------------------------------------

def run_parent_agent_factory(llm: Any):
    def run_parent_agent(state: dict[str, Any]) -> dict[str, Any]:
        state["status"] = "running"
        state.setdefault("iteration", 0)
        state.setdefault("max_iterations", 8)
        state.setdefault("parent_phase", "plan")
        state.setdefault("memory", {})
        state.setdefault("clarifications", {})
        mode = state.get("agent_mode", "mock")

        if state["iteration"] >= state["max_iterations"]:
            state["status"] = "failed"
            state["error"] = "Max iterations exceeded"
            state["next_route"] = "fail"
            _evt(state, "parent_failed", {"reason": state["error"]})
            return state

        state["iteration"] += 1
        phase = state["parent_phase"]
        _evt(state, "parent_tick", {"phase": phase, "iteration": state["iteration"], "mode": mode})

        # ── plan ──────────────────────────────────────────────────────────
        if phase == "plan":
            if mode == "llm":
                _llm_plan(state, llm)
            else:
                _mock_planner(state)
            state["next_route"] = "loop"
            return state

        # ── investigate ───────────────────────────────────────────────────
        if phase == "investigate":
            if mode == "llm":
                _llm_investigate(state, llm)
            else:
                _mock_investigator(state)
            state["next_route"] = "loop"
            return state

        # ── propose ───────────────────────────────────────────────────────
        if phase == "propose":
            if mode == "llm":
                _llm_remediate(state, llm)
            else:
                _mock_remediator(state)

            # Human approval interrupt (both modes)
            payload = {
                "scope": "subagent",
                "subagent": "remediator",
                "type": "approve_action",
                "run_id": state.get("run_id"),
                "agent_mode": mode,
                "proposal": state.get("memory", {}).get("proposed_action", {}),
                "hypothesis": state.get("memory", {}).get("chosen_hypothesis", {}),
            }
            state["pending_interrupt"] = payload
            state["status"] = "paused"
            _evt(state, "interrupt_requested", payload)

            decision = interrupt(payload)
            state["last_human_decision"] = decision
            state["pending_interrupt"] = {}
            state["status"] = "running"
            _evt(state, "interrupt_resolved", decision)

            approval = decision.get("approval", "rejected")
            state["parent_phase"] = "verify" if approval == "approved" else "investigate"
            state["next_route"] = "loop"
            return state

        # ── verify ────────────────────────────────────────────────────────
        if phase == "verify":
            # Mock verifier for both modes (real verification would need live infra)
            _mock_verifier(state)
            recovered = state.get("memory", {}).get("verification", {}).get("recovered", False)

            if recovered:
                state["parent_phase"] = "done"
                state["next_route"] = "finalize"
            else:
                payload = {
                    "scope": "parent",
                    "type": "escalation_decision",
                    "run_id": state.get("run_id"),
                    "message": "Verification failed. Reinvestigate or escalate?",
                    "options": ["reinvestigate", "fail"],
                }
                state["pending_interrupt"] = payload
                state["status"] = "paused"
                _evt(state, "interrupt_requested", payload)

                decision = interrupt(payload)
                state["last_human_decision"] = decision
                state["pending_interrupt"] = {}
                state["status"] = "running"
                _evt(state, "interrupt_resolved", decision)

                if decision.get("choice") == "fail":
                    state["error"] = "Operator escalated to manual"
                    state["next_route"] = "fail"
                else:
                    state["parent_phase"] = "investigate"
                    state["next_route"] = "loop"
            return state

        # ── done ──────────────────────────────────────────────────────────
        if phase == "done":
            state["next_route"] = "finalize"
            return state

        state["error"] = f"Unknown phase: {phase}"
        state["next_route"] = "fail"
        _evt(state, "parent_failed", {"reason": state["error"]})
        return state

    return run_parent_agent


# ---------------------------------------------------------------------------
# Terminal nodes
# ---------------------------------------------------------------------------

def finalize_node(state: dict[str, Any]) -> dict[str, Any]:
    state["status"] = "completed"
    proposal     = (state.get("memory") or {}).get("proposed_action", {})
    verification = (state.get("memory") or {}).get("verification", {})
    hypothesis   = (state.get("memory") or {}).get("chosen_hypothesis", {})
    mode         = state.get("agent_mode", "mock")
    state["final_report"] = (
        f"[{mode.upper()}] Incident resolved for {state.get('service', 'unknown-service')}. "
        f"Root cause: {hypothesis.get('hypothesis', 'see evidence')}. "
        f"Action: {proposal.get('type', 'none')} on {proposal.get('target', '?')}. "
        f"Recovered: {verification.get('recovered', False)}."
    )
    _evt(state, "run_completed", {"final_report": state["final_report"]})
    return state


def fail_node(state: dict[str, Any]) -> dict[str, Any]:
    state["status"] = "failed"
    state.setdefault("error", "Run failed")
    _evt(state, "run_failed", {"error": state["error"]})
    return state


from __future__ import annotations

from typing import Any, Literal, TypedDict


class IncidentState(TypedDict, total=False):
    run_id: str
    objective: str
    service: str
    env: str
    agent_mode: Literal["mock", "llm"]  # "mock" = deterministic, "llm" = real LLM reasoning
    llm_backend: str
    llm_warning: str

    status: Literal["running", "paused", "failed", "completed"]
    parent_phase: Literal["plan", "investigate", "propose", "verify", "done"]
    iteration: int
    max_iterations: int

    agenda: list[str]
    memory: dict[str, Any]
    clarifications: dict[str, str]  # field -> value provided by operator or synthesised

    pending_interrupt: dict[str, Any]
    last_human_decision: dict[str, Any]

    next_route: Literal["loop", "finalize", "fail"]
    final_report: str
    error: str
    event_log: list[dict[str, Any]]


"""
LLM-powered sub-agents.  Each function calls the LLM with rich, structured prompts
and returns a dict that the parent orchestrator merges into graph state.

In LLM mode the investigator feeds the LLM realistic mock telemetry so it can
reason genuinely about root cause.  Every sub-agent signals when it needs a
human clarification; if none is provided the orchestrator synthesises a value.
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import json
from typing import Any

from app.llm.base import LLMMessage

# ---------------------------------------------------------------------------
# Realistic mock telemetry injected into LLM prompts so the LLM can reason
# ---------------------------------------------------------------------------
def _build_telemetry(service: str) -> dict[str, Any]:
    return {
        "service": service,
        "time_window": "last 15 minutes",
        "metrics": {
            "http_5xx_rate":       {"baseline": "0.2%",  "current": "6.8%"},
            "latency_p95_ms":      {"baseline": 185,      "current": 840},
            "throughput_rps":      {"baseline": 2400,     "current": 1820},
            "cpu_utilization":     {"baseline": "32%",    "current": "38%"},
            "memory_utilization":  {"baseline": "64%",    "current": "68%"},
        },
        "recent_deployments": [
            {
                "version": "v1.17.3",
                "deployed_at": "8 minutes ago",
                "changed_components": ["CartService", "PaymentAdapter"],
            },
            {
                "version": "v1.17.2",
                "deployed_at": "4 days ago",
                "changed_components": ["UserAuth"],
            },
        ],
        "error_log_sample": [
            f"ERROR {service}: NullPointerException in processCheckout()",
            "ERROR PaymentAdapter: timeout connecting to payment-service after 3000ms",
            "WARN  CircuitBreaker: payment-service opened after 5 consecutive failures",
        ],
        "dependency_health": {
            "payment-service":   "degraded (p95=2800ms)",
            "inventory-service": "healthy",
            "user-service":      "healthy",
        },
        "affected_endpoints": [
            {"path": "/api/checkout",     "error_rate": "45%"},
            {"path": "/api/cart/submit",  "error_rate": "38%"},
        ],
    }


# ---------------------------------------------------------------------------
# Helper: run async LLM call from a sync graph node (background thread)
# ---------------------------------------------------------------------------
def _call_llm_json(llm: Any, messages: list[LLMMessage]) -> dict[str, Any]:
    coro = llm.generate_json(messages, schema={"type": "object"})
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                return ex.submit(asyncio.run, coro).result()
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


def _call_llm_text(llm: Any, messages: list[LLMMessage]) -> str:
    coro = llm.generate_text(messages)
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                return ex.submit(asyncio.run, coro).result()
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Public sub-agents
# ---------------------------------------------------------------------------

FALLBACK_STEPS = [
    "Inspect recent error-rate metrics and structured logs",
    "Correlate anomaly onset time with deployment and config history",
    "Propose the lowest-risk remediation with a verified rollback plan",
]


def llm_planner(state: dict[str, Any], llm: Any) -> dict[str, Any]:
    """LLM generates an investigation plan and optionally requests clarification."""
    clarifications = state.get("clarifications") or {}

    messages = [
        LLMMessage(
            role="system",
            content="""You are a senior SRE incident triage planner.
Return ONLY valid JSON with these exact keys:
{
  "steps": ["step 1", "step 2", "step 3"],
  "needs_clarification": false,
  "clarification_question": "",
  "clarification_field": ""
}
Set needs_clarification=true and populate the clarification fields only if critical
context is genuinely unknown (e.g. severity tier, SLO owner, blast radius).
Otherwise plan with what you have.""",
        ),
        LLMMessage(
            role="user",
            content=(
                f"Incident: {state.get('objective', '')}\n"
                f"Service: {state.get('service', '')} | Env: {state.get('env', '')}\n"
                f"Known context: {json.dumps(clarifications) if clarifications else 'none'}"
            ),
        ),
    ]

    try:
        r = _call_llm_json(llm, messages)
        return {
            "steps": r.get("steps") or FALLBACK_STEPS,
            "needs_clarification": bool(r.get("needs_clarification")),
            "clarification_question": r.get("clarification_question", ""),
            "clarification_field":    r.get("clarification_field", ""),
            "source": "llm",
            "error": "",
        }
    except Exception as exc:
        return {"steps": FALLBACK_STEPS, "needs_clarification": False,
                "clarification_question": "", "clarification_field": "",
                "source": "fallback", "error": str(exc)}


def llm_investigator(state: dict[str, Any], llm: Any) -> dict[str, Any]:
    """LLM analyses mock telemetry, previous evidence, and produces a hypothesis."""
    service      = state.get("service", "unknown-service")
    telemetry    = _build_telemetry(service)
    evidence     = (state.get("memory") or {}).get("evidence", [])
    clarifications = state.get("clarifications") or {}

    messages = [
        LLMMessage(
            role="system",
            content="""You are an expert SRE incident investigator.
Analyse the telemetry and evidence provided and return ONLY valid JSON:
{
  "hypothesis": "<specific root-cause hypothesis>",
  "confidence": 0.0,
  "evidence_summary": "<2-3 sentence summary of key findings>",
  "new_signals": ["<signal>"],
  "needs_clarification": false,
  "clarification_question": "",
  "clarification_field": ""
}
confidence is 0.0–1.0.  new_signals are additional facts you derived.
Set needs_clarification=true only if a specific missing fact would materially
change your hypothesis (e.g. "was a feature flag changed?").""",
        ),
        LLMMessage(
            role="user",
            content=(
                f"Service: {service} | Env: {state.get('env', '')}\n"
                f"Objective: {state.get('objective', '')}\n\n"
                f"Telemetry:\n{json.dumps(telemetry, indent=2)}\n\n"
                f"Previous evidence:\n{json.dumps(evidence, indent=2)}\n\n"
                f"Operator-provided context: {json.dumps(clarifications) if clarifications else 'none'}"
            ),
        ),
    ]

    try:
        r = _call_llm_json(llm, messages)
        return {
            "hypothesis":             r.get("hypothesis", "Unknown root cause"),
            "confidence":             float(r.get("confidence", 0.5)),
            "evidence_summary":       r.get("evidence_summary", ""),
            "new_signals":            r.get("new_signals", []),
            "needs_clarification":    bool(r.get("needs_clarification")),
            "clarification_question": r.get("clarification_question", ""),
            "clarification_field":    r.get("clarification_field", ""),
            "telemetry":              telemetry,
            "source": "llm",
            "error": "",
        }
    except Exception as exc:
        return {
            "hypothesis": f"Likely regression in {service} after recent deploy",
            "confidence": 0.65,
            "evidence_summary": "Error spike correlates with deployment timeline.",
            "new_signals": [],
            "needs_clarification": False,
            "clarification_question": "",
            "clarification_field": "",
            "telemetry": telemetry,
            "source": "fallback",
            "error": str(exc),
        }


def llm_remediator(state: dict[str, Any], llm: Any) -> dict[str, Any]:
    """LLM proposes remediation based on confirmed hypothesis."""
    memory     = state.get("memory") or {}
    hypothesis = memory.get("chosen_hypothesis") or {}
    evidence   = memory.get("evidence") or []

    messages = [
        LLMMessage(
            role="system",
            content="""You are a senior SRE on-call engineer proposing remediation.
Return ONLY valid JSON:
{
  "type": "rollback|restart|scale|config_change|manual",
  "target": "<service or component>",
  "risk": "low|medium|high",
  "reason": "<clear rationale>",
  "rollback_steps": ["<step>"],
  "expected_recovery_time": "<e.g. 2-3 minutes>",
  "needs_clarification": false,
  "clarification_question": "",
  "clarification_field": ""
}
Prefer lowest risk action with fastest expected recovery.""",
        ),
        LLMMessage(
            role="user",
            content=(
                f"Service: {state.get('service', '')} | Env: {state.get('env', '')}\n"
                f"Root cause: {json.dumps(hypothesis, indent=2)}\n"
                f"Evidence:\n{json.dumps(evidence, indent=2)}"
            ),
        ),
    ]

    try:
        r = _call_llm_json(llm, messages)
        return {
            "type":                   r.get("type", "rollback"),
            "target":                 r.get("target", state.get("service", "unknown")),
            "risk":                   r.get("risk", "low"),
            "reason":                 r.get("reason", "Based on evidence"),
            "rollback_steps":         r.get("rollback_steps", []),
            "expected_recovery_time": r.get("expected_recovery_time", "unknown"),
            "needs_clarification":    bool(r.get("needs_clarification")),
            "clarification_question": r.get("clarification_question", ""),
            "clarification_field":    r.get("clarification_field", ""),
            "source": "llm",
            "error": "",
        }
    except Exception as exc:
        return {
            "type": "rollback", "target": state.get("service", "unknown"),
            "risk": "low", "reason": "Deploy correlation with error spike",
            "rollback_steps": [], "expected_recovery_time": "2-3 minutes",
            "needs_clarification": False,
            "clarification_question": "", "clarification_field": "",
            "source": "fallback", "error": str(exc),
        }


def generate_synthetic_value(llm: Any, field: str, context: dict[str, Any]) -> str:
    """Ask the LLM to produce a realistic synthetic value for a missing field."""
    messages = [
        LLMMessage(
            role="system",
            content="Generate a concise, realistic synthetic value for a missing SRE incident field. Return only the value, no explanation.",
        ),
        LLMMessage(
            role="user",
            content=f"Missing field: {field}\nIncident context: {json.dumps(context)}\nProvide a realistic value:",
        ),
    ]
    try:
        return _call_llm_text(llm, messages).strip()
    except Exception:
        return f"synthetic-{field}-{context.get('service', 'svc')}"


from __future__ import annotations

import time

from app.llm.mock_provider import MockProvider
from app.services.runtime import GraphRuntime

_POLL = 0.3
_TIMEOUT = 15.0


def wait_for_status(runtime: GraphRuntime, run_id: str, targets: set[str]) -> dict:
    deadline = time.monotonic() + _TIMEOUT
    while time.monotonic() < deadline:
        snap = runtime.get_state(run_id)
        status = snap.get("values", {}).get("status")
        if status in targets:
            return snap
        time.sleep(_POLL)
    raise TimeoutError(f"run {run_id} did not reach {targets} within {_TIMEOUT}s")


def main() -> None:
    runtime = GraphRuntime(llm=MockProvider(), db_url="sqlite:///./agent_state.db")

    run_id = runtime.start_run(
        objective="Investigate elevated 5xx in checkout service and propose remediation",
        service="checkout-service",
        env="prod",
    )
    print("run_id:", run_id)
    print("Graph running in background...")

    snap = wait_for_status(runtime, run_id, {"paused", "completed"})
    values = snap.get("values", {})
    print("status:", values.get("status"))
    print("pending_interrupt:", values.get("pending_interrupt"))
    print("events so far:", len(values.get("event_log", [])))

    if values.get("status") == "paused":
        print("\nResuming with approval=approved...")
        runtime.resume(run_id, {"approval": "approved"})
        snap = wait_for_status(runtime, run_id, {"completed", "failed"})
        values = snap.get("values", {})

    print("final status:", values.get("status"))
    print("final report:", values.get("final_report"))
    print("total events:", len(values.get("event_log", [])))


if __name__ == "__main__":
    main()


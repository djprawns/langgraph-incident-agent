from __future__ import annotations

import time

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

_POLL_INTERVAL = 0.2
_TIMEOUT = 10.0


def _wait_for_status(run_id: str, target_statuses: set[str]) -> dict:
    deadline = time.monotonic() + _TIMEOUT
    while time.monotonic() < deadline:
        resp = client.get(f"/runs/{run_id}")
        if resp.status_code == 200:
            values = resp.json()["snapshot"]["values"]
            if values.get("status") in target_statuses:
                return values
        time.sleep(_POLL_INTERVAL)
    # Snapshot for diagnosis
    snap = client.get(f"/runs/{run_id}").json()
    raise TimeoutError(
        f"Run {run_id} did not reach {target_statuses} within {_TIMEOUT}s. "
        f"Last state: {snap}"
    )


def test_pause_resume_flow() -> None:
    create_resp = client.post(
        "/runs",
        json={
            "objective": "Investigate elevated error rate",
            "service": "checkout-service",
            "env": "prod",
        },
    )
    assert create_resp.status_code == 200
    payload = create_resp.json()
    run_id = payload["run_id"]
    assert payload["status"] == "started"

    # Wait until the graph pauses at the approval interrupt
    values = _wait_for_status(run_id, {"paused", "completed"})
    assert isinstance(values.get("event_log"), list)
    assert len(values["event_log"]) > 0

    # Resume with approval and wait for completion
    resume_resp = client.post(f"/runs/{run_id}/resume", json={"approval": "approved"})
    assert resume_resp.status_code == 200
    assert resume_resp.json()["status"] == "resuming"

    final_values = _wait_for_status(run_id, {"completed", "failed"})
    assert final_values.get("status") == "completed"
    assert "final_report" in final_values


from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.dependencies import get_runtime
from app.services.runtime import GraphRuntime

router = APIRouter(prefix="/runs", tags=["runs"])
logger = logging.getLogger(__name__)

_TERMINAL = {"completed", "failed", "paused"}


class CreateRunRequest(BaseModel):
    objective: str = Field(..., min_length=3)
    service: str = Field(..., min_length=2)
    env: str = Field(..., min_length=2)
    agent_mode: str = Field(default="mock", pattern="^(mock|llm)$")


class ResumeRequest(BaseModel):
    # approval gate
    approval: str | None = Field(default=None, pattern="^(approved|rejected)$")
    # escalation gate
    choice: str | None = None
    # clarification gate
    clarification_field: str | None = None
    value: str | None = None  # None means "use synthetic fallback"


@router.post("")
def create_run(payload: CreateRunRequest, runtime: GraphRuntime = Depends(get_runtime)):
    logger.info(
        "api.create_run objective=%s service=%s env=%s mode=%s",
        payload.objective,
        payload.service,
        payload.env,
        payload.agent_mode,
    )
    run_id = runtime.start_run(
        payload.objective, payload.service, payload.env, agent_mode=payload.agent_mode
    )
    return {
        "run_id": run_id,
        "status": "started",
        "agent_mode": payload.agent_mode,
        "llm_backend": runtime.llm_backend,
    }


@router.get("/{run_id}")
def get_run(run_id: str, runtime: GraphRuntime = Depends(get_runtime)):
    logger.info("api.get_run run_id=%s", run_id)
    snapshot = runtime.get_state(run_id)
    if not snapshot.get("exists"):
        raise HTTPException(status_code=404, detail="Run not found")
    return {"run_id": run_id, "snapshot": snapshot}


@router.get("/{run_id}/history")
def get_history(run_id: str, runtime: GraphRuntime = Depends(get_runtime)):
    logger.info("api.get_history run_id=%s", run_id)
    history = runtime.get_history(run_id)
    if not history:
        raise HTTPException(status_code=404, detail="Run not found")
    return {"run_id": run_id, "history": history}


@router.post("/{run_id}/resume")
def resume_run(run_id: str, payload: ResumeRequest, runtime: GraphRuntime = Depends(get_runtime)):
    decision: dict = {}
    if payload.approval is not None:
        decision["approval"] = payload.approval
    if payload.choice is not None:
        decision["choice"] = payload.choice
    if payload.clarification_field is not None:
        decision["clarification_field"] = payload.clarification_field
        decision["value"] = payload.value  # None means "synthesise"
    if not decision:
        raise HTTPException(status_code=400, detail="Provide at least one decision field")
    logger.info("api.resume_run run_id=%s decision=%s", run_id, decision)
    ok = runtime.resume(run_id, decision)
    if not ok:
        raise HTTPException(status_code=404, detail="Run not found")
    return {"run_id": run_id, "status": "resuming"}


@router.get("/{run_id}/events")
async def stream_events(run_id: str, runtime: GraphRuntime = Depends(get_runtime)):
    """
    Server-Sent Events stream.
    Polls event_log from persisted graph state every 500ms, emitting new entries.
    Closes automatically when the run reaches a terminal or paused state.
    """
    # allow a short startup window for the graph thread to register the run
    for _ in range(20):
        if runtime.get_state(run_id).get("exists"):
            logger.info("api.stream_events.open run_id=%s", run_id)
            break
        await asyncio.sleep(0.25)
    else:
        raise HTTPException(status_code=404, detail="Run not found")

    async def _generator():
        last_count = 0
        idle_ticks = 0
        max_idle_ticks = 120  # 60s total idle limit

        while True:
            snapshot = runtime.get_state(run_id)
            values = snapshot.get("values", {})
            event_log = values.get("event_log") or []
            status = values.get("status", "")

            new_events = event_log[last_count:]
            for evt in new_events:
                yield f"data: {json.dumps(evt)}\n\n"

            if new_events:
                idle_ticks = 0
            else:
                idle_ticks += 1

            last_count = len(event_log)

            # periodic heartbeat so the connection stays alive
            if idle_ticks > 0 and idle_ticks % 10 == 0:
                yield f"data: {json.dumps({'event': 'heartbeat', 'status': status})}\n\n"

            is_done = status in _TERMINAL and not runtime.is_active(run_id)
            if is_done:
                logger.info("api.stream_events.close run_id=%s status=%s", run_id, status)
                yield f"data: {json.dumps({'event': 'stream_end', 'status': status})}\n\n"
                break

            if idle_ticks >= max_idle_ticks:
                yield f"data: {json.dumps({'event': 'stream_timeout'})}\n\n"
                break

            await asyncio.sleep(0.5)

    return StreamingResponse(
        _generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

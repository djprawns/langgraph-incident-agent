# Architecture Overview

## Use case

This project focuses on **incident triage for platform engineering**.
The operator starts with a goal such as:

> Investigate elevated 5xxs for `checkout-service` in `prod` and propose the safest remediation.

This is a strong platform engineering workflow because it combines:
- noisy operational signals,
- incomplete context,
- time pressure,
- the need for safe remediation,
- and a clear human-approval boundary.

## Why a single-agent LangGraph design

Instead of modeling each investigation step as a separate graph node, this project uses a **single parent agent loop** with internal sub-agent capabilities:
- planner
- investigator
- remediator
- verifier

This keeps the graph small and understandable while preserving agentic behavior:
- dynamic planning,
- iterative evidence gathering,
- interruption for approvals or clarifications,
- persistence and resumability,
- and explicit state transitions.

## High-level system diagram

```mermaid
flowchart LR
    UI[Web UI] --> API[FastAPI API Layer]
    API --> Runtime[GraphRuntime]
    Runtime --> Graph[LangGraph StateGraph]
    Graph --> Checkpoint[(SQLite Checkpointer)]
    Graph --> LLM[LLM Provider: mock | ollama | openai]
    Graph --> Interrupts[Human Interrupts]
    API --> SSE[Server-Sent Events]
    SSE --> UI
```

## Main components

### 1. Web UI
File: `app/static/index.html`

Responsibilities:
- start a run,
- select `mock` or `llm` agent mode,
- stream timeline events via SSE,
- show approval or clarification interrupts,
- resume paused workflows from the browser,
- display effective backend and warnings.

### 2. API layer
File: `app/api/runs.py`

Endpoints:
- `POST /runs` — create a new run
- `GET /runs/{run_id}` — retrieve current persisted state snapshot
- `GET /runs/{run_id}/history` — retrieve checkpoint history
- `POST /runs/{run_id}/resume` — continue from interrupt with approval, escalation, or clarification
- `GET /runs/{run_id}/events` — stream live timeline events over SSE
- `GET /health` — service health check

### 3. Runtime service
File: `app/services/runtime.py`

Responsibilities:
- compile and hold the LangGraph instance,
- start runs in background threads,
- resume paused runs,
- expose current state/history,
- translate LangGraph snapshot metadata into API-friendly state,
- detect interrupts from LangGraph task metadata,
- log run lifecycle events.

### 4. LangGraph workflow
Files:
- `app/graph/workflow.py`
- `app/graph/nodes.py`
- `app/graph/state.py`

Graph nodes:
- `run_parent_agent`
- `finalize`
- `fail`

Although the graph is intentionally small, `run_parent_agent` internally behaves like an agent orchestrator with multiple capabilities.

### 5. LLM abstraction
Files:
- `app/llm/base.py`
- `app/llm/factory.py`
- `app/llm/mock_provider.py`
- `app/llm/ollama_provider.py`
- `app/llm/openai_provider.py`

A provider interface makes the same graph work with:
- fully local deterministic mode (`mock`),
- local model inference (`ollama`),
- hosted model inference (`openai`).

### 6. LLM sub-agents
File: `app/graph/llm_subagents.py`

In `agent_mode=llm`, the parent agent delegates reasoning to three LLM-backed sub-agents:
- planner
- investigator
- remediator

The investigator receives realistic mock telemetry so the LLM performs actual reasoning rather than generic chatting.

## Agent lifecycle

### Run creation
1. Operator submits goal, service, env, and mode.
2. API creates a run through `GraphRuntime`.
3. The graph executes in a background thread.
4. The UI subscribes to `/events`.

### Parent agent loop
Within `run_parent_agent`, the agent:
1. plans,
2. investigates,
3. proposes remediation,
4. pauses for approval,
5. verifies outcome,
6. completes or fails.

### Human-in-the-loop behavior
Two interrupt types are supported:

#### A. Approval interrupt
Example:
- proposed rollback requires operator approval.

Resume payload:
```json
{"approval": "approved"}
```

#### B. Clarification interrupt
Example:
- the LLM decides a missing fact would materially improve decision quality.

Resume payload with human answer:
```json
{"clarification_field": "feature_flag_state", "value": "enabled for 20% of traffic"}
```

Resume payload with synthetic fallback:
```json
{"clarification_field": "feature_flag_state", "value": null}
```

If `value` is `null`, the system synthesizes a realistic answer and continues.

## State management

State is defined in `app/graph/state.py` and persisted through LangGraph checkpointing.
Key fields include:
- `run_id`
- `objective`
- `service`
- `env`
- `agent_mode`
- `llm_backend`
- `status`
- `parent_phase`
- `iteration`
- `agenda`
- `memory`
- `clarifications`
- `pending_interrupt`
- `last_human_decision`
- `event_log`
- `final_report`

### Why this state shape works
- `memory` acts as the agent working set.
- `event_log` supports UI transparency and replay.
- `pending_interrupt` makes pause/resume explicit.
- `clarifications` preserves operator or synthetic answers across steps.
- checkpoint history makes the run resumable and inspectable.

## Tool integration strategy

This project intentionally uses **mock operational tooling** so it runs locally without cloud accounts.
The LLM investigator receives structured telemetry that looks like real platform data:
- metrics,
- recent deployments,
- error logs,
- dependency health,
- affected endpoints.

This demonstrates agent reasoning without requiring access to actual production systems.

## Persistence and resumability

LangGraph is compiled with a SQLite checkpointer.
That enables:
- resumable runs,
- replayable state,
- crash recovery,
- and history inspection via API.

Important detail: LangGraph checkpoints before an interrupting node completes, so the runtime explicitly derives `paused` state from task interrupt metadata.

## Logging and observability

Application logging is configured in:
- `app/logging_config.py`
- `app/main.py`
- `app/services/runtime.py`
- `app/api/runs.py`

Logs are written to:
- terminal,
- `logs/app.log`

This gives evaluators visibility into:
- request lifecycle,
- run start/resume/end,
- background execution,
- and error handling.

## Key design decisions

### Decision 1: Single parent agent instead of many graph nodes
Chosen for clarity and maintainability.
It keeps orchestration understandable while still showing genuine agentic behavior.

### Decision 2: Interruptions for both approvals and clarifications
Chosen to make human oversight first-class, rather than bolted on.

### Decision 3: Provider-agnostic LLM interface
Chosen so local review works with `mock`, while richer demos work with `ollama` or `openai`.

### Decision 4: SSE for live progress
Chosen because it is simple, browser-native, and enough for evaluator-friendly progress visibility.

## Limitations

Current verification is mocked rather than wired to a real monitoring backend.
That is intentional for local evaluation, but would be the first subsystem to connect to real infra in a production version.

## What I would build next

1. Real integrations for Prometheus / Loki / Kubernetes rollout history
2. Richer evidence panels in the UI (metrics charts, structured log tables)
3. More nuanced remediation verification with multi-step rollback checks
4. RBAC and approval policies for different remediation classes
5. Persistent run index storage so runs survive process restart without in-memory registration
6. Automated demo fixtures for multiple incident scenarios


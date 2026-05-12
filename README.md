# LangGraph Single-Agent Incident Triage

A local-first AI agent for **platform engineering incident triage** built with **LangGraph**, **FastAPI**, and a simple browser UI.

The application demonstrates a production-oriented agent workflow with:
- a web UI for starting runs and observing progress,
- backend APIs for run lifecycle and state inspection,
- LangGraph persistence and pause/resume support,
- human-in-the-loop approval and clarification interrupts,
- and switchable LLM backends (`mock`, `ollama`, `openai`).

---

## Submission checklist coverage

- [x] Working local application (web UI, backend, agent runtime)
- [x] State persistence and resumable workflow via LangGraph + SQLite
- [x] Architecture overview in `docs/ARCHITECTURE.md`
- [x] Setup instructions and design rationale in this README
- [x] “What next” writeup in this README and architecture doc
- [x] Guidance for meaningful git history in `docs/COMMIT_GUIDE.md`
- [x] AI interaction log placeholder/index in `docs/AI_INTERACTION_LOG.md`

Before submission, make sure you also:
- [ ] paste/export the complete AI interaction transcript into `docs/AI_INTERACTION_LOG.md` or linked files
- [ ] confirm your git history reflects meaningful development steps

---

## Use case rationale

This project targets a real platform engineering workflow: **incident triage and safe remediation recommendation**.

Example operator goal:

> Investigate elevated 5xx errors for `checkout-service` in `prod` and propose the safest remediation.

This use case was chosen because it naturally requires:
- iterative investigation,
- tool/evidence gathering,
- decision-making under uncertainty,
- human approval before risky actions,
- and resumable execution when a workflow pauses.

It is also easy to evaluate locally using realistic mock telemetry, avoiding cloud dependencies during review.

---

## Why this agent design

Instead of building a large graph with many tiny nodes, this project uses a **single parent agent loop** with internal sub-agent capabilities:
- planner
- investigator
- remediator
- verifier

This keeps the graph small and understandable while preserving genuine agent behavior:
- dynamic step selection,
- reasoning over evidence,
- clarification requests when context is missing,
- approval interrupts before action,
- and continued execution after resume.

---

## Features

### Agent runtime
- LangGraph-backed single-agent orchestration
- persisted state snapshots with SQLite checkpointing
- pause/resume through LangGraph `interrupt()` and `Command(resume=...)`
- explicit state/history retrieval APIs
- LLM mode with clarification interrupts and synthetic fallback values

### Web UI
- create a run from the browser
- switch between `mock` and `llm` agent behavior
- live event timeline via SSE
- approval and clarification controls
- effective backend visibility (`mock`, `ollama`, `openai`)
- warning when `agent_mode=llm` is selected but the backend is still `mock`

### Backend APIs
- `POST /runs`
- `GET /runs/{run_id}`
- `GET /runs/{run_id}/history`
- `POST /runs/{run_id}/resume`
- `GET /runs/{run_id}/events`
- `GET /health`

### Local-first execution
- mock mode works fully offline
- Ollama support for local model inference
- OpenAI support via provider abstraction
- no cloud account required for default evaluation path

---

## Project structure

```text
langgraph_single_agent/
  app/
    api/                # FastAPI routes
    graph/              # LangGraph state, workflow, nodes, LLM subagents
    llm/                # LLM provider abstraction + implementations
    services/           # Runtime wrapper around graph execution
    static/             # Browser UI
    logging_config.py   # App + file logging setup
    main.py             # FastAPI entrypoint
    settings.py         # Environment-driven config
  docs/
    ARCHITECTURE.md
    AI_INTERACTION_LOG.md
    COMMIT_GUIDE.md
  scripts/
    demo_pause_resume.py
  tests/
  README.md
  pyproject.toml
```

---

## Quick start

### Prerequisites
- Python 3.11+
- macOS/Linux shell commands below assume `zsh`/POSIX shell
- Optional for real local inference: Ollama installed and running

### Setup

```bash
cd /Users/pranavsharma/Documents/Projects/cerebras/langgraph_single_agent
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e .
cp .env.example .env
```

### Run the app

```bash
cd /Users/pranavsharma/Documents/Projects/cerebras/langgraph_single_agent
source .venv/bin/activate
uvicorn app.main:app --reload
```

Open:
- UI: `http://127.0.0.1:8000/`
- Health: `http://127.0.0.1:8000/health`

### Run tests

```bash
cd /Users/pranavsharma/Documents/Projects/cerebras/langgraph_single_agent
source .venv/bin/activate
pytest -q
```

### Run the demo script

```bash
cd /Users/pranavsharma/Documents/Projects/cerebras/langgraph_single_agent
source .venv/bin/activate
python scripts/demo_pause_resume.py
```

---

## Running with different backends

### Default local evaluation mode
The safest default is:
- frontend mode: `mock`
- backend provider: `LLM_BACKEND=mock`

This requires no external services.

### Real LLM behavior with Ollama
Update `.env`:

```dotenv
LLM_BACKEND=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.1:8b
```

Then restart the app and choose **LLM Mode** in the UI.

### Real LLM behavior with OpenAI
Update `.env`:

```dotenv
LLM_BACKEND=openai
OPENAI_API_KEY=your_key_here
OPENAI_MODEL=gpt-4.1-mini
```

Then restart the app and choose **LLM Mode** in the UI.

### Important distinction
- `agent_mode=llm` controls **agent behavior**
- `LLM_BACKEND` controls the **provider implementation**

If `agent_mode=llm` but `LLM_BACKEND=mock`, the UI will show a warning and the run will still use mock-provider outputs.

---

## API overview

### `POST /runs`
Start a run.

Example payload:

```json
{
  "objective": "Investigate high 5xx and propose safe remediation",
  "service": "checkout-service",
  "env": "prod",
  "agent_mode": "llm"
}
```

### `GET /runs/{run_id}`
Fetch the latest persisted state snapshot.

### `GET /runs/{run_id}/history`
Fetch checkpoint history for replay/debugging.

### `POST /runs/{run_id}/resume`
Resume a paused workflow.

Examples:

```json
{"approval": "approved"}
```

```json
{"approval": "rejected"}
```

```json
{"clarification_field": "feature_flag_state", "value": "enabled for 20% of traffic"}
```

```json
{"clarification_field": "feature_flag_state", "value": null}
```

### `GET /runs/{run_id}/events`
Stream live event updates over SSE for the browser timeline.

---

## Local observability

### Application logs
Logs are written to:
- terminal
- `logs/app.log`

Tail logs live:

```bash
cd /Users/pranavsharma/Documents/Projects/cerebras/langgraph_single_agent
tail -f logs/app.log
```

### Useful log types
You should see entries for:
- request start/end
- run creation
- run invoke/resume begin/end
- backend warnings
- API event stream open/close

---

## Architecture and design docs

- Architecture overview: [`docs/ARCHITECTURE.md`](ARCHITECTURE.md)
- AI interaction log placeholder/index: [`docs/AI_INTERACTION_LOG.md`](docs/AI_INTERACTION_LOG.md)
- Commit history guidance: [`docs/COMMIT_GUIDE.md`](docs/COMMIT_GUIDE.md)

---

## Design decisions

### 1. Single parent agent instead of many graph nodes
This keeps the LangGraph model simple while preserving agentic behavior through an internal orchestration loop.

### 2. Human-in-the-loop at two levels
The system pauses for:
- approval before remediation,
- clarification when an LLM needs more context.

### 3. Provider abstraction for portability
The same graph works with:
- deterministic local review (`mock`),
- local inference (`ollama`),
- hosted inference (`openai`).

### 4. SSE instead of a heavier real-time stack
SSE keeps the browser implementation small and evaluator-friendly while still providing real-time transparency.

### 5. Mocked telemetry for local evaluation
The app uses realistic telemetry payloads instead of requiring live production systems, which keeps the project runnable and reviewable offline.

---

## What I would build next

Given more time, I would build:

1. real integrations with Prometheus, Loki, and deployment history sources
2. richer verification logic tied to actual service health checks
3. scenario fixtures for multiple incident classes (latency, saturation, dependency failure, rollout regression)
4. a persistent run registry instead of in-memory run tracking
5. role-based approval policies and remediation classes
6. an in-browser backend log panel for operators
7. richer evidence visualization (charts, queryable logs, dependency graph)

---


## AI interaction log requirement

This repository includes a placeholder/index at [`docs/AI_INTERACTION_LOG.md`](docs/AI_INTERACTION_LOG.md).

Before submission, paste or attach the **full AI development transcript** there (or link transcript files from it) so the evaluator can review the full interaction history.

---

## Notes for reviewers

- The application runs locally in `mock` mode with no paid API dependencies.
- Real LLM inference is supported when configured through `.env`.
- The UI shows effective backend/provider status to avoid confusion between `agent_mode=llm` and `LLM_BACKEND=mock`.

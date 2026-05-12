# LangGraph Single-Agent Incident Triage

This project implements a single parent-agent orchestration model with sub-agents inside one LangGraph node loop. It supports persisted state, pause/resume interruptions, and state/history APIs.

## Why this design

- **Few graph nodes** for clarity (`run_parent_agent`, `finalize`, `fail`)
- **Agentic behavior** from a parent loop that dynamically selects sub-agent actions
- **Human in the loop** via `interrupt()` at both sub-agent and parent scopes
- **Persistence and resume** through SQLite checkpointer

## Features

- Single parent agent with internal sub-agents:
  - planner
  - investigator
  - remediator
  - verifier
- Pause and resume using `Command(resume=...)`
- API endpoints to create runs, inspect state, inspect history, and resume
- Local mock LLM by default, plus optional Ollama/OpenAI providers
- Minimal web UI for operator interaction

## API

- `POST /runs` - start a run
- `GET /runs/{run_id}` - current state snapshot
- `GET /runs/{run_id}/history` - checkpoint history
- `POST /runs/{run_id}/resume` - resume paused workflow with decision payload
- `GET /health` - service health

Resume payload examples:

- `{"approval":"approved"}`
- `{"approval":"rejected"}`
- `{"choice":"reinvestigate"}`

## Local setup

```bash
cd /Users/pranavsharma/Documents/Projects/cerebras/langgraph_single_agent
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e .
cp .env.example .env
```

## Run

```bash
cd /Users/pranavsharma/Documents/Projects/cerebras/langgraph_single_agent
source .venv/bin/activate
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000/`.

## Application logs

The app now logs both to terminal and to a file.

- Default log file: `logs/app.log`
- Configurable via `.env`:
  - `LOG_LEVEL=INFO|DEBUG|WARNING|ERROR`
  - `LOG_FILE=./logs/app.log`

Tail logs in another terminal:

```bash
cd /Users/pranavsharma/Documents/Projects/cerebras/langgraph_single_agent
tail -f logs/app.log
```

## Demo script

```bash
cd /Users/pranavsharma/Documents/Projects/cerebras/langgraph_single_agent
source .venv/bin/activate
python scripts/demo_pause_resume.py
```

## Test

```bash
cd /Users/pranavsharma/Documents/Projects/cerebras/langgraph_single_agent
source .venv/bin/activate
pytest -q
```

## Switch LLM backend

Set `LLM_BACKEND` in `.env`:

- `mock`: no external services
- `ollama`: requires local Ollama running
- `openai`: requires `OPENAI_API_KEY`

The graph logic stays the same across providers.

Note: `agent_mode=llm` controls agent behavior, while `LLM_BACKEND` controls which model provider is used.
If `LLM_BACKEND=mock`, the run still executes in LLM mode but uses mock provider outputs.
Set `LLM_BACKEND=ollama` or `LLM_BACKEND=openai` for real inference.


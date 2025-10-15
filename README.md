
# Switchboard — Real‑Time Agent Task Switchboard & Live File Host

Switchboard is a small, production‑leaning FastAPI service that:

- Hosts a **live, editable plan** (DAG of tasks with dependencies) that agents can **discover, check out, heartbeat, complete, or abandon**.
- Broadcasts **real‑time updates** (WebSockets) when tasks change state or plans/files update.
- Serves a **live file mirror** under predictable URLs so any LLM/agent can retrieve the latest docs **without re‑uploading**.
- Ships with **AGENTS.md** and a **.agent/PLANS.md** template aligned with the ExecPlan pattern.
- Includes a **Python client** for agent integrations and **Docker** packaging.

## Quickstart (local)

Requirements: Python 3.11+, Node not required. (UI is static HTML+HTMX.)

### 1. Create & activate a virtual environment

<details>
<summary><strong>macOS / Linux (bash, zsh)</strong></summary>

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
```

</details>

<details>
<summary><strong>Windows (PowerShell)</strong></summary>

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

</details>

<details>
<summary><strong>Windows (Command Prompt)</strong></summary>

```bat
python -m venv .venv
.\.venv\Scripts\activate.bat
python -m pip install --upgrade pip
```

</details>

### 2. Install server dependencies

```bash
pip install -r server/requirements.txt
```

### 3. Run the API + UI locally

```bash
uvicorn server.app:app --reload --host 0.0.0.0 --port 8000
```

Open the admin UI: <http://localhost:8000/>

### Sample API flows (curl)

These are copy/paste friendly for macOS/Linux shells. On Windows PowerShell, replace the trailing backslashes (`\`) with backticks (`\``) and use double quotes for JSON payloads.

#### Seed a plan

```bash
curl -X POST http://localhost:8000/api/tasks \
  -H "Content-Type: application/json" \
  -d '{"title":"Initial plan setup","description":"Create seed tasks","depends_on":[]}'

curl -X POST http://localhost:8000/api/tasks \
  -H "Content-Type: application/json" \
  -d '{"title":"Implement feature A","description":"Build A","depends_on":[1]}'
```

#### Agent lifecycle

```bash
# register an agent
curl -X POST http://localhost:8000/api/agents \
  -H "Content-Type: application/json" \
  -d '{"agent_name":"codex-1"}'

# checkout an available task
curl -X POST "http://localhost:8000/api/tasks/checkout?agent_id=codex-1"

# heartbeat to extend lease
curl -X POST "http://localhost:8000/api/tasks/1/heartbeat?agent_id=codex-1"

# complete with notes
curl -X POST "http://localhost:8000/api/tasks/1/complete?agent_id=codex-1" \
  -H "Content-Type: application/json" \
  -d '{"notes":"Done"}'
```

#### Live files API

```bash
# write/update a live file from a local source file
curl -X PUT http://localhost:8000/api/files/docs/AGENTS.md \
  -H "Content-Type: text/markdown" \
  --data-binary @AGENTS.md

# fetch latest version
curl http://localhost:8000/live/docs/AGENTS.md
```

### Optional: Python CLI helper

The repository ships a minimal Python helper that behaves like a CLI. With the virtual environment activated:

```bash
python -m client.python.examples.agent_example
```

The script registers an agent, polls for work, heartbeats while "working", and completes tasks when finished. If you are using a fresh environment just for the client, install `requests` first (`python -m pip install requests`).

## Docker

```bash
cp ops/.env.example ops/.env
docker compose -f ops/docker-compose.yml up --build
```

## Project structure

- `AGENTS.md` — guidance for agents, including ExecPlan trigger.
- `.agent/PLANS.md` — the ExecPlan spec template the agents can fill/obey.
- `server/` — FastAPI app, SQLite via SQLAlchemy, WebSockets, HTMX UI.
- `client/python/` — Python client for agent use (checkout/heartbeat/complete).
- `web/` — lightweight admin UI (HTMX + Tailwind CDN).
- `ops/` — Docker files.
- `server/tests/` — pytest scenarios for core flows.

---

**Why this exists:** Agents (Codex, Copilot Agents, etc.) need a single, live source of truth to coordinate work: a plan that can **change in flight**, a **queue** that respects **dependencies**, and a place to **publish documents** that any LLM can fetch by URL. Switchboard gives you all three with minimal overhead.

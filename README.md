
# Switchboard — Real‑Time Agent Task Switchboard & Live File Host

Switchboard is a small, production‑leaning FastAPI service that:

- Hosts a **live, editable plan** (DAG of tasks with dependencies) that agents can **discover, check out, heartbeat, complete, or abandon**.
- Broadcasts **real‑time updates** (WebSockets) when tasks change state or plans/files update.
- Serves a **live file mirror** under predictable URLs so any LLM/agent can retrieve the latest docs **without re‑uploading**.
- Ships with **AGENTS.md** and a **.agent/PLANS.md** template aligned with the ExecPlan pattern.
- Includes a **Python client** for agent integrations and **Docker** packaging.

## Quickstart (local)

Requirements: Python 3.11+, Node not required. (UI is static HTML+HTMX.)

```bash
# 1) Create & activate venv
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 2) Install server
pip install -r server/requirements.txt

# 3) Run
uvicorn server.app:app --reload --host 0.0.0.0 --port 8000
```

Open the admin UI: <http://localhost:8000/>

### Seed a plan

```bash
curl -X POST http://localhost:8000/api/tasks \  -H "Content-Type: application/json" \  -d '{"title":"Initial plan setup","description":"Create seed tasks","depends_on":[]}'
curl -X POST http://localhost:8000/api/tasks \  -H "Content-Type: application/json" \  -d '{"title":"Implement feature A","description":"Build A","depends_on":[1]}'
```

### Agent checkout & heartbeat (example)

```bash
# agent registers
curl -X POST http://localhost:8000/api/agents -H "Content-Type: application/json" -d '{"agent_name":"codex-1"}'

# checkout an available task
curl -X POST "http://localhost:8000/api/tasks/checkout?agent_id=codex-1"

# heartbeat to extend lease
curl -X POST "http://localhost:8000/api/tasks/1/heartbeat?agent_id=codex-1"

# complete
curl -X POST "http://localhost:8000/api/tasks/1/complete?agent_id=codex-1" -H "Content-Type: application/json" -d '{"notes":"Done"}'
```

### Live files

```bash
# write/update a live file
curl -X PUT http://localhost:8000/api/files/docs/AGENTS.md -H "Content-Type: text/markdown" --data-binary @AGENTS.md

# fetch latest
curl http://localhost:8000/live/docs/AGENTS.md
```

## Docker

The Docker setup in `ops/` bind-mounts host directories so you can persist
Switchboard data between container runs. To start it locally:

1. Create the directories that are mounted into the container (from the repo
   root):

   ```bash
   mkdir -p storage .agent
   ```

2. Copy the example environment file and adjust `PORT` if you already have a
   service listening on port 8000:

   ```bash
   cp ops/.env.example ops/.env
   # edit ops/.env if you need to change PORT
   ```

3. Build and launch the stack:

   ```bash
   docker compose -f ops/docker-compose.yml up --build
   ```

The compose file defines a health check that waits for `http://localhost:8000/health`
to return `200 OK` before marking the container as healthy.

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

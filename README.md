
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

```bash
cp ops/.env.example ops/.env
docker compose -f ops/docker-compose.yml up --build
```

## Observability (logging, metrics, tracing)

Switchboard does not yet ship with a batteries-included observability stack, but the FastAPI/uvicorn foundation makes it easy to bolt on later. The items below document the options we intend to use and where they will land in the codebase when implemented.

- **Logging**
  - Use uvicorn's built-in access and application logs. CLI flags (e.g. `uvicorn server.app:app --log-config ops/logging.ini`) let us wire a custom logging configuration without code changes.
  - A repository-local logging config (expected path: `ops/logging.ini`) will centralize formatters/handlers and ensure that when we run under Docker or locally the behavior matches. The server entrypoint (`server/__main__.py` or the `uvicorn` invocation in docs/scripts) will be updated to reference the shared config.
  - For structured logs, we can swap in `uvicorn --log-config` with JSON-capable handlers (e.g. `python-json-logger`) and standardize request IDs via FastAPI middleware housed in `server/instrumentation/logging.py`.

- **Metrics**
  - FastAPI integrates cleanly with Prometheus exporters such as `prometheus-fastapi-instrumentator`. We plan to register instrumentation inside `server/instrumentation/metrics.py` and mount the `/metrics` route from there.
  - When the metrics module is ready, the FastAPI app factory (`server/app.py`) will import and initialize it, ensuring metrics are exposed both in development and production. Docker Compose will later include a Prometheus service scraping the same endpoint.

- **Tracing**
  - OpenTelemetry's FastAPI/ASGI instrumentation (`opentelemetry-instrumentation-fastapi`) provides distributed tracing that works with providers such as OTLP, Jaeger, or Honeycomb.
  - We intend to keep tracing bootstrap code in `server/instrumentation/tracing.py`, invoked from the app startup event handlers. Configuration will live alongside other ops files (e.g. `ops/otel.yaml`) so container deployments can ship the same defaults.

Until those modules exist, this section serves as the canonical outline for how observability should be added. Future PRs can fill in the referenced files without reshuffling documentation.

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

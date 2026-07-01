# Switchboard AI Coding Instructions

## Architecture Overview
Switchboard is a FastAPI service managing real-time agent task coordination with live file hosting. Core components:
- **Server** (`server/`): FastAPI app with async SQLAlchemy, WebSocket broadcasting, HTMX admin UI
- **Client** (`client/python/`): Python library + CLI for agent interactions
- **Data Model**: Tasks with DAG dependencies, agent leases (5min expiration), live file storage
- **Communication**: REST API + WebSockets for real-time plan updates

## Task System Fundamentals
- Tasks form dependency graphs; only available when all prerequisites are "completed"
- Agents must register, checkout one task at a time, heartbeat every 60s, complete/abandon
- Leases expire automatically; expired leases allow other agents to claim tasks
- Plan versions increment on all mutations, broadcast via WebSockets

## Development Workflows
```bash
# Setup & run locally
make setup                    # Create venv, install deps
make run                      # uvicorn server.app:app --reload --host 0.0.0.0 --port 8000
make test                     # pytest server/tests

# Docker deployment
make docker-up                # docker compose -f ops/docker-compose.yml up --build

# Publish ExecPlans (agent coordination docs)
make publish-plan             # Upload .agent/PLANS.md to live server
```

## Agent Development Patterns
- Use `SwitchboardClient` from `switchboard_client.py` for API interactions
- Always register agent first: `client = SwitchboardClient(base_url, agent_id)`
- Implement heartbeat loops during work to prevent lease expiration
- Follow ExecPlan pattern for complex features (document in `.agent/PLANS.md`)
- Mirror ExecPlan edits to live server via `PUT /api/files/docs/PLANS.md`

## Code Patterns & Conventions
- **Database**: Always use async SQLAlchemy sessions; never block on DB calls
- **API**: Pydantic schemas in `schema.py`; endpoints in `app.py` with dependency injection
- **Testing**: Direct function calls to app endpoints (not HTTP); use `AsyncSessionLocal`
- **Files**: Live files stored in `storage/`; served at `/live/{path}` with ETags
- **Dependencies**: Server uses pinned versions in `requirements.txt`; client minimal (`requests` only)

## Key Files to Reference
- `server/app.py`: API endpoints, WebSocket handling, plan broadcasting
- `server/task_logic.py`: Business logic for checkout/complete/abandon with dependency checking
- `server/models.py`: SQLAlchemy models (Task, Lease, TaskDependency, FileEntry)
- `client/python/switchboard_client.py`: Agent API wrapper
- `AGENTS.md`: Agent behavioral rules and ExecPlan guidance
- `.agent/PLANS.md`: Template for complex task planning

## Common Pitfalls
- Forgetting to heartbeat during long operations (lease expires in 5 minutes)
- Not checking task dependencies before making tasks available
- Mixing sync/async database calls
- Not broadcasting plan version updates after mutations
- Publishing files without updating both Git and live copies

## Testing Approach
- Unit tests call app functions directly with `AsyncSessionLocal`
- Mock external dependencies; test state transitions
- Example: `test_create_and_checkout()` in `server/tests/test_tasks.py`

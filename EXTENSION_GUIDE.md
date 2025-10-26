# Extension Guide

Switchboard exposes a lightweight plugin system so operators and automation
agents can react to task lifecycle events without forking the core service.
This guide walks through the runtime model and provides a starter template for
writing new extensions.

## Runtime Model

1. **Configuration** – Environment variables control discovery:
   - `SWITCHBOARD_ENABLE_BUILTIN_EXTENSIONS` (default `1`) toggles builtin hooks
     such as `task_metrics` and `webhook_notifier`.
   - `SWITCHBOARD_EXTENSIONS` is a comma-separated list of Python modules that
     expose a `register_extension(registry)` callable.
2. **Loading** – During startup `initialize_extensions(app)` imports each module
   and gives it an `ExtensionRegistry`. Extensions register lifecycle hooks,
   FastAPI startup callbacks, and descriptive metadata. The registry now tracks a
   versioned contract (`EXTENSION_API_VERSION`) so operators can confirm
   compatibility via `/api/settings`.
3. **Emission** – `TaskService` calls `ExtensionBundle.emit(...)` after every
   checkout, heartbeat, completion, abandonment, creation, and update. Hooks may
   perform synchronous or asynchronous work.
4. **Observation** – `/api/settings` exposes the effective configuration,
   registered descriptors, and the contract version/notes. `/api/diagnostics` and
   `/api/observability/telemetry` surface the same metadata for automation.

## Writing an Extension

Use the scaffolding helper to generate a starter module with contract metadata:

```bash
python scripts/dev.py scaffold-extension audit_logger
```

Then flesh out the generated file or create a module from scratch that registers
hooks with the provided registry:

```python
# myproject/switchboard_ext/email_alerts.py
from __future__ import annotations

from server.extensions import ExtensionDescriptor, ExtensionRegistry

class EmailHook:
    async def on_complete(self, *, agent_id: str, result) -> None:
        if result.ok and result.task:
            send_email(
                subject=f"Task {result.task.id} completed",
                body=result.task.title,
            )


def register_extension(registry: ExtensionRegistry) -> None:
    registry.register_extension(
        ExtensionDescriptor(
            name="email-alerts",
            capabilities=("notifications",),
            description="Sends email when tasks complete successfully.",
        )
    )
    registry.register_task_hook(EmailHook())
```

Then enable it via environment variables:

```bash
export SWITCHBOARD_EXTENSIONS=myproject.switchboard_ext.email_alerts
uvicorn server.app:app
```

## Testing Hooks

- Unit test hook classes directly by instantiating `TaskService` with an
  `ExtensionBundle` containing your hook (see `server/tests/test_extensions.py`).
- Integration test modules by setting `SWITCHBOARD_EXTENSIONS` during pytest and
  invoking the API endpoints that trigger lifecycle events.

## Recommended Patterns

- **Idempotence** – Hooks may run more than once (e.g., retries). Ensure they
  can handle duplicate notifications.
- **Failure handling** – Raise exceptions sparingly; `TaskService` awaits all
  hooks sequentially. Prefer logging or circuit breaker logic inside the hook.
- **Metadata** – Populate `ExtensionDescriptor` so `/api/settings` conveys
  meaningful details to operators and automation agents. Use
  `registry.append_contract_note()` to record cross-cutting compatibility
  requirements.
- **Startup hooks** – Use `register_startup_hook` to perform async setup (e.g.,
  warm caches) without blocking FastAPI import time.

## Builtin Reference

The builtin `task_metrics` extension (`server/extensions/builtin/task_metrics.py`)
illustrates a simple hook that increments Prometheus counters for each lifecycle
transition. The companion `webhook_notifier`
(`server/extensions/builtin/webhook_notifier.py`) demonstrates filtered event
delivery with structured payloads via `httpx`. Use these as templates for other
stateless integrations such as audit logging, Slack notifications, or bespoke
webhooks. When deploying webhooks set `SWITCHBOARD_WEBHOOK_URL` (and optionally
`SWITCHBOARD_WEBHOOK_EVENTS`) so the builtin hook can broadcast lifecycle events.

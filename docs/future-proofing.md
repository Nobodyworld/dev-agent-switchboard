# Future-Proofing Switchboard

This guide captures architectural hotspots, upcoming scaling considerations, and
recommendations for evolving Switchboard without destabilising existing
integrations.

## Scalability & Performance

- **Stateless API pods** – The FastAPI layer is horizontally scalable. Deploy via
  container orchestrators with at least two replicas behind a load balancer. Use
  sticky sessions only when custom extensions require per-agent affinity.
- **Database tier** – SQLite is sufficient for local development. For production,
  migrate to PostgreSQL and configure connection pooling (e.g., pgbouncer) so
  task checkout latency remains predictable under burst load.
- **Long-running jobs** – Task lifecycle hooks should avoid blocking I/O. When
  fan-out is required (Slack, email, webhooks) prefer asynchronous clients or
  offload to a background queue to prevent API saturation.

## Observability Strategy

- `/api/observability/telemetry` reports whether logging, metrics, tracing, and
  the builtin webhook are active. Export this payload to your monitoring stack to
  alert on instrumentation drift.
- `scripts/dev.py verify` exercises the same pipeline as CI; run it as a
  pre-deployment gate to catch regressions before rollout.
- Promote Prometheus and OpenTelemetry endpoints into your platform dashboards;
  correlate request IDs across logs, traces, and webhook deliveries.

## Extension Contracts

- `EXTENSION_API_VERSION` currently sits at **2025.2**. Increment this when
  signature changes require partner action, and document compatibility notes via
  `registry.append_contract_note()` so `/api/settings` surfaces the delta.
- The builtin `webhook_notifier` showcases the recommended contract:
  structured payloads, filtered events, and defensive logging. Treat it as the
  canonical example when building new plugins.

## Containerisation & Deployment

- Container images should bake in `pip-audit` and `scripts/dev.py verify` during
  CI to ensure artefacts match production expectations.
- Provide environment defaults via Kubernetes ConfigMaps or Docker Compose env
  files. Expose `SWITCHBOARD_WEBHOOK_URL`, `SWITCHBOARD_ENABLE_TRACING`, and
  `SWITCHBOARD_ENABLE_METRICS` so operators can toggle instrumentation without
  redeploying images.
- Document rollout procedures in `RELEASE_NOTES.md` with blue/green or
  canary-specific steps when extensions introduce side effects.

## Multi-Tenancy & Isolation

- Namespace tasks by tenant (e.g., prefix IDs or introduce a `tenant_id` column)
  before onboarding multiple organisations. Ensure rate limits and leases respect
  tenant boundaries by sharding configuration in `SettingsBundle`.
- Webhook extensions should incorporate tenant metadata into payloads so
  downstream systems can segregate alerts.

## Migration Path (v1 → v2)

- **Persistence** – Introduce Alembic migrations to replace runtime DDL. Start by
  extracting the existing TODO (`TODO(P2, 2d) - Move this schema migration into a
  formal Alembic revision`) into a tracked migration script.
- **API surface** – Version REST endpoints under `/api/v1` to permit future
  breaking changes. Mirror the same payloads in `/api/v2` before deprecating the
  original paths.
- **Clients** – Publish typed client libraries (Python + JS) generated from the
  OpenAPI schema. Document upgrade steps in `RELEASE_NOTES.md`.

## AI & Agent Safety

- Automation should register via `/api/agents` and poll `/api/observability/telemetry`
  before making assumptions about instrumentation.
- Enforce TODO metadata (`TODO(Px, effort)`) so outstanding debt is triaged and
  assigned; agents can parse this format programmatically when deciding which
  tasks to prioritise.
- The webhook notifier performs best-effort delivery; record failures in your
  incident tracker so human operators can intervene when downstream systems miss
  updates.

## Next Steps

- Automate extension publishing via a package index to encourage community
  contributions.
- Explore background worker queues (Celery, Dramatiq) for long-running hooks to
  avoid blocking API threads.
- Expand `/api/observability/telemetry` with feature flag state (e.g., future
  rollout toggles) so agents can self-tune behaviour without redeploys.

# Switchboard Configuration Surfaces

Switchboard now exposes a dedicated configuration snapshot across the API, CLI, and operator UI. These views consolidate rate limiter settings, lease durations, extensions, storage health, database wiring, and selected environment metadata so operators and agents can verify runtime posture without digging through source code or database tables.

## API: `/api/configuration`

The FastAPI application serves a typed `ConfigurationResponse` at `GET /api/configuration`. The payload includes:

- `settings`: the existing `SettingsResponse` (rate limit, lease, local
  execution-routing freshness, and extensions).
- `admin`: whether an administrative token is configured (token values are never returned).
- `storage`: the live file store root, existence and writeability checks, and disk usage.
- `database`: a password-free connection URL, driver name, and declared engine options.
- `runtime`: the standard runtime snapshot used by diagnostics.
- `environment`: sanitised environment variables and derived defaults for transparency.
- `warnings`: actionable notes (for example, unwritable storage or low disk space).

All sensitive fields (such as `DATABASE_URL` credentials or `SWITCHBOARD_ADMIN_TOKEN`) remain redacted.

## Local execution routing

The worker JSON `repositories` object remains the only place where logical
`owner/repository` names map to canonical local paths. Registration derives a
sorted `repository_full_names` list from its keys and sends no values from that
mapping. The server accepts only catalog repositories. Existing workers that
omit the field and prior database rows upgrade to the historical Switchboard
repository only; they never implicitly gain access to later catalog entries.

Two server-owned environment settings bound `cheapest_capable` liveness:

- `SWITCHBOARD_EXECUTION_HEARTBEAT_FRESHNESS_SECONDS` defaults to `300` and
  must be from `1` through `86400`.
- `SWITCHBOARD_EXECUTION_ACTIVE_POLL_FRESHNESS_SECONDS` defaults to `60` and
  must be from `1` through `3600`.

They are returned as the non-secret `execution_routing` object by
`GET /api/settings` and inside the configuration snapshot. Heartbeat freshness
and active checkout-poll freshness are deliberately separate. Neither a work
order nor a route-assessment request can override these windows, and assessment
does not refresh a worker's poll timestamp.

Worker routing profiles are persisted operator state rather than environment
configuration. Create and change them only through the privileged
`/api/execution/routing-profiles` APIs. Profile cost, capacity, remaining quota,
and priority are bounded integers; remaining quota cannot exceed capacity, and
reset timestamps must be timezone-aware. Replacements and quota resets require
the current expected revision. An active reserved assignment blocks both
operations. A repeated reset with the same timestamp and remaining value is an
idempotent success; an older timestamp or conflicting same-timestamp value is
rejected.

`first_available` remains the work-order default and does not require a
profile. `cheapest_capable` uses the profile's abstract
`estimated_cost_units_per_run`, never the legacy floating `cost_ceiling`.
These values are local operator comparison units only: Switchboard does not
interpret them as currency, credits, spend, savings, billing, or a provider
rate limit. No provider credential or paid-agent configuration is introduced.

The Validation Broker workspace loads the source-controlled catalog, filters
manifest choices by selected repository, shows read-only readiness, and edits
the same persisted profiles through the
revision-protected APIs and reads active/stale worker state through a bounded
projection. It does not introduce browser-owned routing configuration. The
browser reads the existing admin token from local storage only when sending an
authenticated request; the token is never returned by a projection or rendered
into the workspace. Overview windows are request parameters bounded from 1
through 365 days and do not mutate worker heartbeat or checkout-poll freshness.

## Factory profiles and runtime discovery

The public workload factory is source code, not a deployment setting: the typed
definitions in `server/execution/workload_profiles.py` compile into the trusted
registry and catalog at import time. The complete public catalog is fixed to
`Nobodyworld/dev-agent-switchboard`, `Nobodyworld/app-accounting-modular`,
`Nobodyworld/dev-logger-zscripts`, and
`Nobodyworld/app-industry-resilience`. Operators enable only the repositories
they have explicitly mapped in their local worker JSON; adding a JSON key does
not create a profile or loosen the catalog.

Worker registration discovers Node and pnpm with fixed `node --version` and
`pnpm --version` subprocesses (`shell=False`, short timeout, and bounded
combined output). Node's leading `v` is normalized before capability matching;
pnpm is nullable when missing or invalid. Discovery neither installs tools nor
executes target repository code. `validate-zscripts@1` requires Python 3.11+,
Node 24.12.0+, and exactly pnpm 10.18.1; a mismatch is a safe
`manifest_capability_mismatch` readiness outcome. `validate-industry-resilience@1`
requires Python 3.13+.

Factory profile result contracts are part of the manifest and exact-reuse
identity. For a profile, the worker validates the source-controlled parser,
declared artifact paths, result-affecting input hashes, and resource limits;
the effective retention/count/byte policy is the stricter of local worker
configuration and reviewed profile ceilings. Legacy manifests have no factory
result contract, so their historical digests and local evidence behavior remain
unchanged.

The dashboard's catalog section reads only
`GET /api/execution/catalog-readiness`. Its response is bounded to display
identity, reviewed runtime requirements, ready count, one safe blocker,
optional compact latest result, source-availability caveat, and exclusions. It
does not expose paths or credentials and does not refresh worker state, reserve
capacity/quota, resolve a PR, or create a work order.

## Outbound GitHub adapter

The manual exact-PR adapter uses server-only environment configuration:

- `SWITCHBOARD_GITHUB_TOKEN` — required fine-grained PAT with no default;
- `SWITCHBOARD_GITHUB_API_URL` — optional HTTPS API base, defaulting exactly to
  `https://api.github.com`;
- `SWITCHBOARD_OPERATOR_ID` — optional bounded operator identity, defaulting to
  `local-operator`.

The token requires repository **Metadata: read** and **Pull requests: read and
write**. It is deliberately absent from the configuration API, CLI, and UI,
including configured/unconfigured indicators, and is never forwarded to local
workers. The adapter resolves the credential's stable actor identity before
creating a request, binds it into deterministic request identity and managed
comment ownership, and never exposes that ownership identity through the
configuration surface. See
[GitHub exact pull-request validation](operations/github-exact-pr-validation.md)
for the complete operator and security contract.

Validation requests may add strict per-request reuse and routing policy. These
values are persisted on the linked execution work order, whose schema already
owns the authoritative policy fields. The adapter table therefore needs no new
policy columns or startup migration. Existing all-default adapter identities
remain discoverable through the exact prior idempotency calculation; non-default
requests use the complete policy-bound identity.

## Exact evidence reuse

Evidence reuse has no global environment-variable switch and no
caller-selected cache location. It is chosen per work order with
`reuse_policy`: `never` (default), `allow_exact`, or `require_exact`. The server
derives and persists the execution-policy hash; the assigned worker derives the
environment and dependency-lock portions of the strict identity from its
current exact-SHA checkout.

Local proof uses the existing worker-owned `evidence_root`, retention days, and
artifact count/byte limits. Candidate metadata never contains the configured
root or a local directory. Reuse does not extend the source run's retention;
operators must provision retention long enough for their intended validation
window and accept that pruning or changed bytes make a candidate unavailable.

## CLI: `switchboard-cli config`

The Python CLI gains a `config` subcommand:

```bash
$ switchboard-cli config --base http://localhost:8000 --agent config-cli
```

- Fetches the configuration snapshot without registering the agent.
- Supports `--json` for automation pipelines.
- Prints human-readable summaries of rate limits, storage state, database source, and warnings.

The new `make config` target shells the command with repository defaults so developers can run a single command during local diagnostics.

## Operator UI

The web console now renders a **Configuration** card near the top of the dashboard:

- Displays rate limiter status, lease duration, extension counts, storage metadata, and database provenance.
- Highlights administrative token configuration and the expected `X-Switchboard-Admin-Token` header alongside the backing environment variable.
- Presents runtime metadata (version, environment, commit SHA, uptime, PID) with a one-click copy control for the commit hash.
- Streams sanitised environment variables in a tabular view.
- Surfaces warnings inline with amber styling.
- Provides copy affordances for the live file root and runtime commit for quick sharing in incident channels.

Data refreshes when the page loads and can be reloaded manually using the **Refresh** button.

## Automation Notes

- The configuration service caches values internally and recalculates on demand via existing reload helpers.
- Tests cover the service, API endpoint, and CLI command; front-end coverage relies on integration smoke tests.
- Low disk space detection currently warns at 256 MiB of free space, and the service emits alerts if disk usage cannot be inspected or the storage parent is not writable. Adjust `LOW_STORAGE_THRESHOLD_BYTES` in `server/application/configuration_service.py` if deployments require a different guardrail.

## Future Work

- TODO(P2, 2d) - Extend the configuration payload with database pool utilisation once observability metrics expose the data.
- TODO(P3, 1d) - Persist user-selected configuration refresh cadence in local storage for the operator UI.

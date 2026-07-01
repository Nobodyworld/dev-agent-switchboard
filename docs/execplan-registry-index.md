---
title: "ExecPlan Registry Index Format"
summary: "Define the portable schema Switchboard uses to publish ExecPlan catalogs."
nav:
  section: "Reference"
  order: 3
search:
  keywords:
    - execplan
    - registry
    - schema
    - api design
tags:
  - reference
  - execplans
---

# ExecPlan Registry Index Format

This document proposes a portable YAML/JSON index format for describing ExecPlan registries. The index is designed to be served by future Switchboard server endpoints so clients can enumerate available plans, understand their high-level state, and locate detail documents or APIs for deeper inspection.

## Design goals

- **Schema duality** — The same structure must serialize cleanly to YAML or JSON so that agents and humans can work with their preferred format.
- **Discoverability** — A single index should summarize every active ExecPlan and link to canonical plan artifacts or live files.
- **Change tracking** — Clients should be able to detect when any plan or the registry itself changes without diffing the entire document.
- **Extensibility** — Fields should be namespaced and typed to allow additive extensions without breaking existing clients.

## Top-level structure

```yaml
version: 1
registry_id: switchboard-default
generated_at: "2024-05-01T12:00:00Z"
source:
  url: "https://switchboard.example.com/api/execplans/index.yaml"
  etag: "W/\"4f927ab\""
plans:
  - ...
```

| Field | Required | Type | Description |
| --- | --- | --- | --- |
| `version` | yes | integer | Schema version for forward-compatibility. Clients SHOULD ignore documents with newer, unsupported versions. |
| `registry_id` | yes | string | Stable identifier for the registry instance (e.g., environment or tenant). |
| `generated_at` | yes | RFC 3339 datetime | UTC timestamp representing when the index snapshot was produced. |
| `source.url` | no | string (URL) | Canonical endpoint where this index can be refreshed. Useful when the index is mirrored via live files. |
| `source.etag` | no | string | Opaque change token representing the server’s latest ETag or checksum. |
| `plans` | yes | array | Collection of ExecPlan summaries (described below). |

## ExecPlan entries

Each entry inside `plans` summarizes a single ExecPlan and advertises the resources necessary for clients to sync detailed information.

```yaml
- plan_id: "feature-hub-upgrade"
  title: "Upgrade Feature Hub to multi-tenant architecture"
  summary: "Break down the multi-tenant refactor and coordinate agent workstreams."
  status: active
  lifecycle:
    created_at: "2024-04-02T16:45:00Z"
    updated_at: "2024-04-28T09:10:00Z"
    target_completion: "2024-05-15T00:00:00Z"
  owners:
    - agent_id: "lead-architect"
      role: "shepherd"
    - agent_id: "codex-ops"
      role: "operations"
  tags: ["refactor", "priority:high"]
  scope:
    repositories:
      - name: "switchboard"
        path_filters:
          include: ["server/**", "web/**"]
          exclude: ["server/tests/**"]
    environments: ["staging", "production"]
  links:
    details:
      format: "markdown"
      url: "https://switchboard.example.com/live/plans/feature-hub-upgrade.md"
    api:
      url: "https://switchboard.example.com/api/execplans/feature-hub-upgrade"
  metrics:
    tasks_total: 28
    tasks_completed: 12
    blockers: 2
  changelog_token: "1b2d3f"
```

| Field | Required | Type | Notes |
| --- | --- | --- | --- |
| `plan_id` | yes | string | Unique slug or UUID used by server APIs. |
| `title` | yes | string | Human-readable name for the ExecPlan. |
| `summary` | no | string | Optional short description (≤280 chars recommended). |
| `status` | yes | enum | Suggested values: `active`, `draft`, `paused`, `complete`, `archived`. |
| `lifecycle` | no | object | Key timestamps: `created_at`, `updated_at`, `target_completion`. |
| `owners` | no | array | Each owner entry may include `agent_id`, `role`, `contact` (email, URL, etc.). |
| `tags` | no | array of strings | Free-form labels for filtering/search. |
| `scope` | no | object | Declares affected repositories, paths, and environments. Optional `related_systems` array allowed. |
| `links` | yes | object | At minimum, include a `details` or `api` link so clients can fetch the full plan. Additional link types (e.g., `dashboard`, `documentation`) may be added. Each link should specify a `url` and optional `format` or `rel`. |
| `metrics` | no | object | Quantitative snapshot for dashboards. Suggested keys include `tasks_total`, `tasks_completed`, `blockers`. |
| `changelog_token` | no | string | Opaque token that increments when substantive plan content changes. Enables lightweight change detection without fetching full plan details. |

## JSON representation

The YAML schema maps one-to-one with JSON, enabling content negotiation via `Accept` headers. Example excerpt:

```json
{
  "version": 1,
  "registry_id": "switchboard-default",
  "generated_at": "2024-05-01T12:00:00Z",
  "plans": [
    {
      "plan_id": "feature-hub-upgrade",
      "title": "Upgrade Feature Hub to multi-tenant architecture",
      "status": "active",
      "lifecycle": {
        "created_at": "2024-04-02T16:45:00Z",
        "updated_at": "2024-04-28T09:10:00Z"
      },
      "links": {
        "api": {
          "url": "https://switchboard.example.com/api/execplans/feature-hub-upgrade"
        }
      }
    }
  ]
}
```

## Versioning & extensions

- Servers MUST increment the top-level `version` when introducing backwards-incompatible changes.
- New optional fields should be prefixed or namespaced if collision risk exists (e.g., `metrics.burndown`).
- Unknown fields MUST be ignored by clients to preserve forward compatibility.
- Registries MAY include an `extensions` array at either the top level or per-plan to advertise experimental keys:

```yaml
extensions:
  - name: "switchboard:vnd-task-schemas"
    url: "https://switchboard.example.com/docs/task-schema-v2"
```

## Endpoint considerations

- **Content negotiation**: Serve the same data at `/api/execplans/index` with support for `Accept: application/yaml` and `Accept: application/json`.
- **Caching**: Encourage HTTP caching via `ETag` and `Last-Modified` headers mirroring `generated_at` and `source.etag`.
- **Pagination**: For large deployments, add optional pagination envelope fields (`cursor`, `next_url`) while keeping the default response a single page.
- **Integrity**: When mirroring to live files, include the `source.url` so clients can round-trip to the authoritative API.

This format provides a concise yet extensible foundation for agents and dashboards to discover ExecPlans via a registry index while remaining agnostic to underlying storage or task schemas.

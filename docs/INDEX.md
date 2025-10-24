---
title: "Documentation Index"
summary: "Unified entry point that links every Switchboard guide, reference, and plan for zero-context onboarding."
nav:
  section: "Getting Started"
  order: 0
search:
  keywords:
    - index
    - onboarding
    - documentation
tags:
  - overview
  - onboarding
---

# Switchboard Documentation Index

Welcome to the Switchboard documentation portal. This index is designed so a brand-new contributor can:

> Looking for the modern quick-start experience? Head to the lightweight
> [documentation hub](index.md) which summarises architecture, message schema,
> failure modes, and the local runner walkthrough introduced in this update.

1. Understand what Switchboard is and how it is structured.
2. Discover the right guide for their task (building agents, operating the server, extending the UI, or shipping roadmap work).
3. Traverse directly to deep technical references without trawling the repository tree.

Use this page together with [`docs/_meta/navigation.yaml`](./_meta/navigation.yaml), which machines or static-site tooling can ingest to render navigation menus and power search indexing.

## Quick Start Checklist

Follow these steps in order if you are new to the project:

1. **Read the [README](../README.md)** for prerequisites, environment setup, and live command examples.
2. **Scan the [Architecture Deep Dive](./architecture.md)** to internalize module boundaries and data flows.
3. **Pick your persona:**
   - Building an automation agent? Jump to the [AI Interface Guide](./AI_INTERFACE.md).
   - Exploring existing roadmap work? Review the ExecPlans under [`docs/execplans/`](./execplans).
   - Investigating operational controls? Consult the [Rate Limiting Design Note](./rate-limiting-design.md) and [Test & Reliability Report](./testing_report.md).
4. **Return here whenever you need to locate supporting references**—every document in `/docs` is cataloged below with purpose, inputs, and related modules.

## Navigation Map

The table below mirrors `docs/_meta/navigation.yaml` and groups content the same way a docs portal would render sidebar sections.

| Section | Document | Purpose |
| --- | --- | --- |
| Getting Started | [Documentation Index](./INDEX.md) | Centralize links and onboarding flow for new contributors. |
| Getting Started | [Architecture Deep Dive](./architecture.md) | Explain server, client, and UI architecture with module callouts. |
| Agents & Automation | [AI Interface Guide](./AI_INTERFACE.md) | Detail agent REST/WebSocket flows and Python SDK usage. |
| Agents & Automation | [ExecPlan Registry Index Format](./execplan-registry-index.md) | Specify the schema agents use to enumerate ExecPlans. |
| Design Notes | [Rate Limiting Design Note](./rate-limiting-design.md) | Capture rationale and configuration for request throttling. |
| ExecPlans | [Bootstrap Observability Instrumentation](./execplans/instrumentation-observability.md) | Track the plan for rolling out logging, metrics, and tracing. |
| ExecPlans | [Harden Core Runtime Helpers](./execplans/targeted-hardening.md) | Govern hardening work across time utilities, clients, and middleware. |
| Quality & Operations | [Test & Reliability Report](./testing_report.md) | Summarize test coverage, reliability wins, and outstanding constraints. |
| Quality & Operations | [Documentation Improvement Report](./PORTAL_STATUS.md) | Record this portal refresh and track future documentation backlog items. |

## Module Reference

This reference aligns code modules with the documentation that describes them. Use it to connect implementation files to guides, ensuring every component is discoverable.

| Area | Module(s) | Documentation | What You Learn |
| --- | --- | --- | --- |
| API Surface | `server/app.py`, `server/schema.py`, `server/task_logic.py` | [Architecture Deep Dive](./architecture.md), [AI Interface Guide](./AI_INTERFACE.md) | Request routing, task lifecycle orchestration, and payload contracts. |
| Persistence & Registry | `server/execplan_registry.py`, `docs/execplan-registry-index.md`, `docs/execplans/` | [Architecture Deep Dive](./architecture.md), [ExecPlan Registry Index Format](./execplan-registry-index.md) | How ExecPlans are persisted, indexed, and consumed by agents. |
| Time & Status Utilities | `server/time_utils.py`, `server/task_status.py` | [Architecture Deep Dive](./architecture.md) | Why timestamp helpers and enums exist and how the server/clients share them. |
| Rate Limiting | `server/middleware/rate_limit.py` | [Rate Limiting Design Note](./rate-limiting-design.md) | Sliding-window algorithm, configuration knobs, and operational trade-offs. |
| Instrumentation | `server/instrumentation/*` | [Bootstrap Observability Instrumentation](./execplans/instrumentation-observability.md) | Rollout plan and toggles for logging, metrics, and tracing. |
| Client SDK | `client/python/switchboard_client.py`, `switchboard_client.py` | [AI Interface Guide](./AI_INTERFACE.md) | API helpers, retry semantics, and how agents authenticate and upload artifacts. |
| CLI Tooling | `client/python/switchboard_cli.py`, `switchboard_cli.py` | [AI Interface Guide](./AI_INTERFACE.md) | Interactive agent shell, heartbeat loops, and unattended usage patterns. |
| Example Agents | `client/python/examples/agent_example.py` | [AI Interface Guide](./AI_INTERFACE.md) | Minimal polling agent walkthrough and extension points. |
| Operator UI | `web/` templates & static assets | [Architecture Deep Dive](./architecture.md) | How the HTMX dashboard consumes REST and WebSocket APIs. |
| Testing & Quality | `tests/`, `client/python/tests/` | [Test & Reliability Report](./testing_report.md) | Coverage strategy, known skips, and next steps for automation. |
| Operations | `ops/`, `scripts/`, `Makefile` | [Architecture Deep Dive](./architecture.md), [Test & Reliability Report](./testing_report.md) | Deployment scripts, local development commands, and validation routines. |

## Search Metadata

Static site generators can seed their search indices with the metadata we now provide. Each Markdown file includes YAML front matter defining `title`, `summary`, `tags`, and `search.keywords`. Tools like MkDocs, Docusaurus, or custom pipelines can parse this file or [`docs/_meta/navigation.yaml`](./_meta/navigation.yaml) to generate navigation sidebars and keyword indexes without manual curation.

## Related External References

Some documentation remains at the repository root for historical or governance reasons:

- [`ARCHITECTURE.md`](../ARCHITECTURE.md) — Organization-wide architecture narrative referenced by external stakeholders.
- [`CONTRIBUTING.md`](../CONTRIBUTING.md) — Contribution guidelines, required reading before submitting PRs.
- [`PLAN.md`](../PLAN.md) and [`PROJECT_STATUS.md`](../PROJECT_STATUS.md) — Program-level planning artifacts that complement ExecPlans.

These documents now link back into `/docs` so readers can pivot between high-level context and the detailed guides cataloged here.

## Keeping the Index Current

When adding or updating documentation:

1. Add or adjust YAML front matter at the top of the Markdown file.
2. Register the document inside [`docs/_meta/navigation.yaml`](./_meta/navigation.yaml) so navigation menus stay synchronized.
3. Update the Module Reference table above if the change introduces new modules or significantly alters responsibilities.

Periodic reviews should also verify that README setup instructions, ExecPlans, and operational runbooks remain accurate as the codebase evolves.

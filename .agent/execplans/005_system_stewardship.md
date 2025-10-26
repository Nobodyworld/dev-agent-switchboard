# Stabilize, extend, and future-proof Switchboard

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be updated as work proceeds, following `.agent/PLANS.md`.

## Purpose / Big Picture

Complete Stage 3 by hardening observability, formalizing modular boundaries, and equipping future contributors and agents with tooling and documentation so Switchboard can evolve independently. Deliver production-ready telemetry, extension scaffolding, automation guardrails, and forward-looking guidance without disrupting existing behavior.

## Current Understanding

- FastAPI app already exposes diagnostics and health endpoints but observability metadata is scattered.
- Extensions exist yet lack clear contracts for external teams to implement plugins safely.
- Documentation is extensive though overlapping; contributor and agent flows need consolidation and automation hooks.
- CI tooling runs locally via Makefile but lacks explicit quality gates and dependency freshness automation notes.

## Tasks

1. **Observability & Maintainability**
   - [x] Audit current logging/metrics/tracing hooks; standardize with structured logging helpers and OpenTelemetry-ready instrumentation.
   - [x] Provide unified health and readiness endpoints that return consistent payloads plus metrics exposure.
   - [x] Document incident response playbook and telemetry wiring.

2. **Modular Expansion Layer**
   - [x] Formalize extension contracts with versioned schemas/interfaces.
   - [x] Provide scaffolding/generator templates for new extensions.
   - [x] Implement a reference "webhook notifier" extension demonstrating hooks.

3. **Developer & Agent Enablement**
   - [x] Ship CLI/dev scripts for common tasks (bootstrap, quality gates, telemetry smoke tests).
   - [x] Update CONTRIBUTING.md and create AUTOMATION/AGENTS guidance for safe agent interactions.
   - [x] Add starter templates for new modules/services.

4. **Continuous Improvement Loop**
   - [x] Configure CI pipeline definition (lint → type → test → coverage → security) and supporting scripts.
   - [x] Add dependency freshness automation notes (e.g., Renovate/Dependabot) and security scanning steps.
   - [x] Enforce TODO/FIXME tagging conventions with priority/effort metadata.

5. **Future-Proofing**
   - [x] Document architectural hotspots, scaling paths, and migration guidance.
   - [x] Outline containerization/load balancing considerations.
   - [x] Highlight AI/agent safety policies and schema contracts.

## Progress

- [x] Kickoff
- [x] Observability enhancements in place
- [x] Extension scaffolding + reference plugin completed
- [x] Tooling/docs refreshed
- [x] Quality gates automated
- [x] Future-proofing report published
- [ ] Final validation + retrospective complete

## Surprises & Discoveries

- Ruff's security checks (S603/S607) now run via `scripts/dev.py verify`; existing subprocess
  usage in tooling still triggers warnings and should be evaluated in a follow-up pass.

## Decision Log

*(Record key architectural/product decisions here.)*

## Outcomes & Retrospective

*(Summarize achievements, metrics, and follow-ups once work concludes.)*

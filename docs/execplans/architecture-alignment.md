# Align server architecture with Clean Architecture layers

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This repository implements the Switchboard service. This plan must be maintained in accordance with `.agent/PLANS.md`.

## Purpose / Big Picture

Clarify the server architecture by introducing explicit domain, application, and infrastructure layers in line with the published README and architecture documentation. REST handlers should delegate into orchestrated use cases that operate purely on domain abstractions so the codebase remains testable, stable, and maintainable.

## Progress

- [x] Initial state captured.
- [x] Layered module boundaries designed.
- [x] Application services introduced with dependency direction enforced.
- [x] FastAPI surface refactored to consume application services.
- [x] Tests and documentation updated; validation complete.

## Surprises & Discoveries

- Observation: The operator UI template no longer needed server-rendered task data once the application service owned orchestration.
  Evidence: `web/index.html` renders static markup while HTMX populates tasks at runtime, so the revised `index` route now renders without database work.

## Decision Log

- Decision: Consolidate lifecycle behavior into `TaskService` backed by repository protocols and domain policies.
  Rationale: Ensures FastAPI handlers depend only on application services while the infrastructure layer handles SQLAlchemy details.
  Date/Author: 2025-03-05 / gpt-5-codex
- Decision: Introduce `_prepare_plan_payload` helper so WebSocket broadcasts reuse the same service abstraction and avoid ad-hoc SQL queries.
  Rationale: Keeps plan broadcasting aligned with the new layering and reduces duplicated version resolution logic.
  Date/Author: 2025-03-05 / gpt-5-codex

## Outcomes & Retrospective

- FastAPI routes now invoke a single `TaskService`, reducing raw SQL usage and clarifying dependency flow.
- Domain entities and policies live under `server/domain/`, enabling repository implementations without leaking infrastructure details.
- Documentation reflects the layered architecture, and tests exercise the service-oriented APIs directly.
- Repository adapters now batch dependency lookups, and dedicated `TaskService` tests validate checkout, completion, and abandon scenarios end to end.

## Context and Orientation

- `server/app.py` currently mixes HTTP concerns, persistence calls, and domain orchestration in a single module.
- Legacy `server/task_logic.py` previously intertwined SQLAlchemy access with domain policies; the new structure relocates those concerns into `server/domain/` and `server/application/task_service.py`.
- `server/interfaces.py` provides immutable dataclasses used across multiple layers but lacks separation between domain entities and transport payloads.
- Tests under `server/tests/` focus on API behavior rather than layered components.

## Plan of Work

1. Introduce a layered package structure under `server/` (`domain`, `application`, `infrastructure`) and move existing abstractions accordingly.
2. Extract pure domain entities and repositories that define interfaces without FastAPI or SQLAlchemy dependencies.
3. Implement application use-case services that coordinate repositories and enforce policies previously embedded in `task_logic.py`.
4. Refactor infrastructure modules (`models`, `db`, `file_store`) to implement the repository interfaces and handle SQLAlchemy, filesystem, and settings concerns.
5. Update FastAPI endpoints to depend on the application services and ensure dependency injection flows from outer layers inward only.
6. Refresh tests to target the new services and confirm existing API behavior remains intact.
7. Document the new layering in `ARCHITECTURE.md`/`docs/architecture.md` and ensure README claims remain accurate.

## Concrete Steps

1. Sketch directory layout and move non-HTTP dataclasses into `server/domain/entities.py`; create repository protocol definitions in `server/domain/repositories.py`.
2. Translate the former task logic into `server/application/task_service.py` with pure orchestration logic consuming repository protocols.
3. Adapt SQLAlchemy-facing code into `server/infrastructure/persistence.py` and `server/infrastructure/file_storage.py`, implementing the repository interfaces.
4. Slim down `server/app.py` to request dependencies via FastAPI `Depends`, invoking application services and converting outputs via schemas.
5. Extend or adjust unit tests to cover the services and ensure `pytest -q` passes.
6. Update architecture docs to reflect the new layers and dependency flow; ensure README references remain accurate.

## Validation and Acceptance

- Application services can be unit-tested in isolation with repository fakes.
- API integration tests continue to pass using infrastructure-backed dependencies.
- Documentation now describes the layered architecture and aligns with README statements.
- `pytest -q` passes locally.

## Idempotence and Recovery

- Module moves occur via Git, enabling straightforward reversion if layering introduces regressions.
- Repository interfaces maintain backward-compatible data structures, allowing incremental migration.
- If FastAPI wiring fails, re-enable previous orchestration functions temporarily while iterating on DI.

## Artifacts and Notes

- Introduced `server/domain/`, `server/application/task_service.py`, and SQLAlchemy repository adapters.

## Interfaces and Dependencies

- Domain layer exposes immutable entities (`Task`, `Agent`, `Queue`) and repository protocols.
- Application layer defines service classes/functions for task lifecycle operations and plan/version management.
- Infrastructure layer implements repository protocols using SQLAlchemy sessions and filesystem utilities.
- FastAPI layer depends only on application services and schema translation helpers.

# Expand lease lifecycle test coverage

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This repository implements the Switchboard service. This plan must be maintained in accordance with `.agent/PLANS.md`.

## Purpose / Big Picture

Extend automated coverage for the leasing lifecycle so regressions in checkout, heartbeat, expiry, re-checkout, abandon, and completion behaviors are caught without modifying server implementation.

## Progress

- [x] Initial state.
- [x] Test layout review.
- [x] Draft pytest scenarios.
- [x] Implement tests in `server/tests/test_leases.py`.
- [ ] Run pytest to confirm coverage (blocked by missing `httpx`).
- [ ] Summarize outcomes.

## Surprises & Discoveries

- Observation: Existing suite only covers basic task operations in `server/tests/test_tasks.py`.
  Evidence: Repository tree inspection.
- Observation: `fastapi.testclient` import fails because `httpx` is not installed in the execution environment and outbound installs are blocked.
  Evidence: `pytest server/tests/test_leases.py` error log showing `ModuleNotFoundError: No module named 'httpx'`.

## Decision Log

- Decision: Use FastAPI `TestClient` with in-memory database fixture similar to existing tests to simulate lease flows end-to-end.
  Rationale: Ensures tests interact with real API endpoints without server code changes.
  Date/Author: 2024-05-11 / gpt-5-codex.

## Outcomes & Retrospective

Pending successful pytest execution once `httpx` dependency is available in the environment.

## Context and Orientation

- `server/app.py` defines FastAPI routes for task lease lifecycle.
- `server/tests/test_tasks.py` demonstrates how to instantiate app and interact with API in tests.
- Target file: `server/tests/test_leases.py` (new) containing focused lifecycle scenarios.

## Plan of Work

1. Create `server/tests/test_leases.py` using pytest and FastAPI `TestClient` to drive API endpoints.
2. Add fixtures mirroring `test_tasks.py` for clean database state per test.
3. Write three test cases:
   - Checkout → heartbeat → expiry → re-checkout.
   - Abandon flow releasing lease for another agent.
   - Completion behavior both with and without active lease (expect failure when missing lease).
4. Ensure assertions validate HTTP status codes, lease timestamps progression, and error responses.
5. Run `pytest server/tests/test_leases.py` to verify success.

## Concrete Steps

1. Inspect `server/tests/test_tasks.py` for reusable fixtures.
2. Author new test module per plan.
3. Execute `pytest server/tests/test_leases.py`.

## Validation and Acceptance

- Automated: `pytest server/tests/test_leases.py` passes with all new tests.
- Manual: None required; tests cover flows programmatically.

## Idempotence and Recovery

- Tests reset database per fixture; reruns safe.
- If failure occurs, adjust assertions without altering server code.

## Artifacts and Notes

- Record pytest output in final summary (current run blocked by missing `httpx`).

## Interfaces and Dependencies

- FastAPI `TestClient` from `fastapi.testclient`.
- API endpoints: `/api/tasks/checkout`, `/api/tasks/{id}/heartbeat`, `/api/tasks/{id}/abandon`, `/api/tasks/{id}/complete`.

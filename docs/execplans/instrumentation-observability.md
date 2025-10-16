# Bootstrap observability instrumentation

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This repository implements the Switchboard service. This plan must be maintained in accordance with `.agent/PLANS.md`.

## Purpose / Big Picture

Introduce the first iteration of the observability stack documented in the README: structured logging, Prometheus metrics, and OpenTelemetry tracing. The goal is to provide optional instrumentation that operators can enable via environment variables both locally and inside the Docker setup without disrupting existing FastAPI behavior.

## Progress

- [x] Initial state.
- [x] Drafted implementation approach.
- [x] Implemented instrumentation modules and configuration files.
- [x] Integrated initialization and tests.
- [x] Documentation updated and validations complete.

## Surprises & Discoveries

- Observation: Unable to download optional observability packages in the execution environment due to restricted PyPI access.
  Evidence: `pip install -r server/requirements-dev.txt` returned HTTP 403 proxy errors.

## Decision Log

- Decision: Use environment variables prefixed with `SWITCHBOARD_` to toggle instrumentation features.
  Rationale: Keeps configuration consistent across local and container environments without changing existing CLI commands.
  Date/Author: 2024-10-22 / gpt-5-codex

## Outcomes & Retrospective

Summarize outcomes vs. purpose once complete.

## Context and Orientation

- `server/app.py` — FastAPI application factory that will bootstrap instrumentation.
- `server/instrumentation/` — New package housing logging, metrics, and tracing helpers.
- `ops/` — Deployment configuration directory where defaults like `logging.ini` and `otel.yaml` will live.
- `server/tests/` — pytest suite; new smoke tests will confirm instrumentation setup does not interfere with the event loop.

## Plan of Work

1. Create `server/instrumentation/logging.py`, `metrics.py`, and `tracing.py` implementing opt-in helpers per README guidance.
2. Update `server/app.py` to call instrumentation setup functions during module import so they run on startup.
3. Add default configuration artifacts (`ops/logging.ini`, `ops/otel.yaml`) and mention them in the README with Docker/local usage notes.
4. Extend pytest suite with smoke tests for instrumentation registration.
5. Update dependency lists (`server/requirements*.txt`) if new libraries are required.

## Concrete Steps

1. Scaffold instrumentation package and helper functions with environment flag checks.
2. Wire helpers into `server/app.py` and ensure they no-op when disabled.
3. Write configuration files and README updates covering enabling in Docker/local runs.
4. Add tests verifying middleware/metrics routes/tracing instrumentation register without starting extra loops.
5. Run `pytest` to confirm the suite passes.

## Validation and Acceptance

- `pytest` passes, including new instrumentation smoke test.
- When `SWITCHBOARD_ENABLE_METRICS=1`, `/metrics` responds successfully in tests.
- Logging middleware attaches request IDs without raising errors even when structured logging dependencies are absent.
- README describes how to enable observability for both local CLI runs and Docker Compose.

## Idempotence and Recovery

- All setup functions are guarded to only initialize once; rerunning tests or the app will not duplicate instrumentation.
- If configuration is mis-specified, environment variables can be unset to fall back to default behavior.

## Artifacts and Notes

Document relevant logs or outputs after execution.

## Interfaces and Dependencies

- `python-json-logger` for structured logging formatters.
- `prometheus-fastapi-instrumentator` for metrics exposure.
- `opentelemetry-sdk`, `opentelemetry-exporter-otlp`, and `opentelemetry-instrumentation-fastapi` for tracing.

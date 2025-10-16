# Add request rate limiting middleware

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This repository implements the Switchboard service. This plan must be maintained in accordance with `.agent/PLANS.md`.

## Purpose / Big Picture

Introduce a configurable request rate limiter in front of the FastAPI app so abusive clients receive `429 Too Many Requests` responses while trusted agents and normal traffic remain unaffected. Configuration should come from environment variables and be documented for operators.

## Progress

- [x] Initial state.
- [x] Implement middleware and configuration surface.
- [x] Wire middleware into the FastAPI app and deployment assets.
- [x] Document environment variables in README and ops docs.
- [x] Add automated tests or scripts to validate rate limiting behavior.
- [x] Final validation and retrospective.

## Surprises & Discoveries

- Observation: The FastAPI middleware stack is instantiated lazily; the rate limit
  middleware only becomes accessible after creating a `TestClient` or otherwise
  building the stack.
  Evidence: Attempting to access the middleware before creating a client returned
  `None`.

## Decision Log

- Decision: Use an in-process FastAPI middleware to enforce rate limiting instead of adding an external reverse proxy.
  Rationale: Keeps stack lightweight, avoids introducing new services in Compose, and satisfies requirement for 429 responses with configurable thresholds.
  Date/Author: 2024-05-08 / gpt-5-codex.

## Outcomes & Retrospective

Implemented in-process rate limiting with environment-driven configuration,
updated Docker assets, and documented operator knobs. Automated tests cover both
limit enforcement and trusted bypass behavior, fulfilling the purpose of
protecting the API without blocking normal traffic.

## Context and Orientation

Key files:
- `server/app.py` – FastAPI application setup.
- `server/` – location for new middleware/config modules.
- `server/tests/` – pytest suite to extend with rate limiting tests.
- `ops/docker-compose.yml` and `server/Dockerfile` – deployment assets requiring updates for new configuration/dependencies.
- `README.md` and `ops/.env.example` – operator documentation.

## Plan of Work

1. Create a `server/settings.py` (or similar) module to centralize rate limit configuration from environment variables, including defaults and parsing trusted bypass lists.
2. Implement a new middleware in `server/middleware/rate_limit.py` that tracks requests per client IP within a sliding time window and respects the trusted bypass list.
3. Register the middleware in `server/app.py`, ensuring it runs before other application logic and optionally skips static or health endpoints if necessary.
4. Update Docker-related files (`server/requirements*.txt` if new dependencies, `server/Dockerfile`, `ops/docker-compose.yml`, `ops/.env.example`) to ensure the middleware works in containerized deployments without extra services.
5. Document the new environment variables and behavior in `README.md`, including guidance for trusted bypasses.
6. Add pytest coverage in `server/tests/` to simulate rapid requests and assert rate limiting returns `429`, while normal request pacing and trusted clients succeed.
7. Run the test suite to confirm everything passes and update the Outcomes section.

## Concrete Steps

1. Author configuration module and middleware implementation files with docstrings.
2. Modify `server/app.py` to import configuration and add middleware registration.
3. Ensure any needed dependencies are declared (likely standard library only; confirm).
4. Update ops files with environment variable defaults and documentation.
5. Extend pytest suite with rate limit scenarios using `TestClient` and `monkeypatch` where needed for deterministic window behavior.
6. Execute `pytest server/tests/test_rate_limit.py` (new file) or full suite.

## Validation and Acceptance

- Automated tests prove over-limit requests receive HTTP 429 and that bypassed clients are unaffected.
- Documentation clearly states configuration knobs and defaults.
- Docker Compose exposes the new environment variables so operators can configure rate limiting.

## Idempotence and Recovery

- Middleware uses in-memory counters reset on process restart; safe to redeploy.
- Environment variable changes require container restart.
- Tests are deterministic and can be rerun without manual cleanup thanks to fixtures.

## Artifacts and Notes

- pytest output demonstrating passing rate limit tests.
- Snippets from README showing documented variables.

## Interfaces and Dependencies

- Middleware exposes a `RateLimitMiddleware` class conforming to Starlette middleware interface.
- Relies on `asyncio`/`time` from standard library; no external deps anticipated.

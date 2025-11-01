# Dependency & License Audit

This document summarises the runtime and development dependencies across the
Switchboard codebase and captures the results of the latest audit. Versions are
pulled from `server/requirements*.txt` and `client/python/pyproject.toml`.

## Server Runtime

| Package | Version | License | Notes |
| --- | --- | --- | --- |
| fastapi | 0.120.0 | MIT | Primary web framework. |
| starlette | 0.48.0 | BSD | FastAPI dependency, provides ASGI tooling. |
| uvicorn | 0.38.0 | BSD | ASGI server used by the packaged runner. |
| SQLAlchemy | 2.0.44 | MIT | ORM/SQL toolkit backing persistence layer. |
| aiosqlite | 0.21.0 | MIT | Async driver for SQLite-based development setups. |
| jinja2 | 3.1.6 | BSD | Template engine for operator UI. |
| httpx | 0.28.1 | BSD | Internal HTTP client for outbound callbacks. |
| python-json-logger | 4.0.0 | BSD | Structured logging. |
| prometheus-fastapi-instrumentator | 7.1.0 | MIT | Metrics instrumentation. |
| opentelemetry-sdk | 1.38.0 | Apache-2.0 | Telemetry pipeline. |
| opentelemetry-exporter-otlp | 1.38.0 | Apache-2.0 | Sends traces/metrics to OTLP endpoints. |
| opentelemetry-instrumentation-fastapi | 0.59b0 | Apache-2.0 | FastAPI auto-instrumentation. |
| PyYAML | 6.0.3 | MIT | Configuration parsing. |
| python-multipart | 0.0.20 | Apache-2.0 | Upload handling for live files. |
| greenlet | 3.2.4 | MIT | Required by SQLAlchemy. |

All listed versions are current as of this audit and match upstream security
advisories (no CVEs affecting these versions were published at the time of
review in November 2024).

## Client Runtime

| Package | Version | License | Notes |
| --- | --- | --- | --- |
| requests | ≥2.31 | Apache-2.0 | HTTP client leveraged by `SwitchboardClient`. |

The CLI and runtime helpers introduced in `client/python/runtime_config.py`
do not require extra dependencies beyond `requests`.

## Development & Tooling

| Package | Version | License | Notes |
| --- | --- | --- | --- |
| pytest | 8.4.2 | MIT | Unit test runner. |
| pytest-asyncio | 1.2.0 | Apache-2.0 | Async test support for server components. |
| black | 25.9.0 | MIT | Code formatter. |
| ruff | 0.14.2 | MIT | Linter and import organiser. |
| mypy | 1.18.2 | MIT | Static type checker. |
| bandit | 1.8.6 | Apache-2.0 | Security linter for Python code. |
| pip-audit | 2.7.3 | Apache-2.0 | Supply-chain vulnerability scanner. |
| playwright | 1.55.0 | Apache-2.0 | Browser automation for UI tests. |
| types-requests | 2.32.4.20250913 | Apache-2.0 | Type hints for requests. |
| types-PyYAML | 6.0.12.20250915 | Apache-2.0 | Type hints for PyYAML. |

## Review Notes

- No GPL or copyleft licenses are present in the runtime dependency tree.
- OpenTelemetry beta instrumentation (`0.59b0`) is acceptable for development
  environments but should be revisited before a production hardening pass.
- Dependencies are pinned for the server to simplify reproducible builds; the
  client package maintains a floor constraint to remain compatible with PyPI
  updates.
- Renovate (`renovate.json`) files automated upgrade PRs; monitor its dashboards
  to keep telemetry and security tooling current.

Document last updated during Codex repo perfection chain Step 7.

---

Switchboard Proprietary — Internal Use Only

# Stage 2 — Deep Diagnostic

## Overview

Manual inspection and code search highlighted several areas where safety, clarity, or maintainability can improve without large architectural upheaval.

## Code Smells & Risks

- **Unbounded task payloads (Moderate)** — `server/schema.TaskIn` does not limit title/description length, allowing oversized inputs from untrusted clients. This risks memory pressure and should be constrained via `Field(max_length=...)` validators.
- **Lenient configuration parsing (Moderate)** — `server/settings.get_rate_limit_settings` silently falls back to defaults when invalid environment variables are provided, obscuring misconfiguration.
- **Wildcard CLI re-export (Minor)** — `switchboard_cli.py` uses `from ... import *`, hindering static analysis and violating repository style expectations.
- **Permissive CORS defaults (Moderate)** — The API currently allows `allow_origins=['*']`; tightening this requires deployment context and is noted but out of scope for the quick iteration.

## TODO / FIXME Review

| Location | Summary | Severity |
| --- | --- | --- |
| `server/schema.py` | Add max length validators for task fields | Moderate |
| `server/settings.py` | Validate settings eagerly | Moderate |
| `switchboard_cli.py` | Replace wildcard re-export | Minor |
| `server/app.py` | Restrict CORS origins | Moderate |
| Various tests | Modernize async test patterns | Minor |
| `web/static/app.js` | Improve DOM updates/backoff | Minor |

## Modes Triggered

- **Zero-Bloat Refactor** — Remove `import *` usage and tidy supporting code/docstrings.
- **Full-System Polish** — Introduce explicit validation and doc improvements to align with repo standards.
- **Security & Stability Audit** — Harden schema and settings parsing to guard against abusive inputs and misconfiguration.
- **Test & Verify** — Run existing test suites after modifications.
- **AI-Ready Refactor** — Document agent-facing surfaces and produce structured references per prompt requirements.

The remaining TODOs are logged for future prioritization but exceed the feasible scope for this pass.

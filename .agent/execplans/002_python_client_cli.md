# Package Python client with CLI ExecPlan

This ExecPlan is a living document. The sections Progress, Surprises & Discoveries, Decision Log, and Outcomes & Retrospective must be kept up to date as work proceeds.

This repository implements the Switchboard service. This plan must be maintained in accordance with .agent/PLANS.md.

## Purpose / Big Picture

Ship the Python client as an installable package exposing a `switchboard-cli` command so operators can register an agent and run the checkout/heartbeat loop against a Switchboard server without touching repository sources.

## Progress

- [x] Initial state.
- [x] Package scaffold committed.
- [x] CLI implements run loop and documentation.
- [ ] Validation performed (install editable + smoke CLI call).
- [x] Outcomes recorded.

## Surprises & Discoveries

- Observation: Local `pip install -e .` attempts fail offline because the environment cannot download `setuptools`/`wheel` and lacks them preinstalled.
  Evidence: `pip install -e .` returned proxy 403 errors for build requirements.

## Decision Log

- Decision: Use setuptools with a pyproject-based src-less layout relying on explicit `py_modules` to reuse existing `switchboard_client.py` without relocating it.
  Rationale: Keeps history clean while supporting packaging and CLI entry points.
  Date/Author: 2024-05-05 / gpt-5-codex.

## Outcomes & Retrospective

Packaging metadata, CLI module, and README are in place. Editable install verification could not complete in this environment b
ecause fetching `setuptools`/`wheel` is blocked, but instructions capture the expected workflow and CLI help runs once `request
s` is available.

## Context and Orientation

- `client/python/switchboard_client.py` contains the `SwitchboardClient` used by examples.
- Need to add packaging metadata (`pyproject.toml`) and CLI module under `client/python`.
- `client/python/examples` demonstrate usage and may inform CLI prompts.

## Plan of Work

1. Author `client/python/pyproject.toml` describing package metadata, dependencies (requests), and entry point `switchboard-cli` mapping to a new CLI module.
2. Add `client/python/switchboard_cli.py` implementing argument parsing and run loop built on `SwitchboardClient`.
3. Provide `client/python/README.md` with install/usage instructions referencing CLI.
4. Update examples if needed to import from package (ensure they still work without modification by exporting class from CLI module if necessary).
5. Validate by installing package locally via `pip install -e` and running `switchboard-cli --help`.

## Concrete Steps

1. Write `pyproject.toml` using setuptools `build-backend` and configure `project.scripts`.
2. Implement CLI module with `argparse`, subcommand `run`, and heartbeat loop that keeps heartbeating until completion/abandon.
3. Document usage in README.
4. Run `pip install -e .` from `client/python` and exercise CLI help.
5. Record validation results and finalize.

## Validation and Acceptance

- Editable install succeeds and exposes `switchboard-cli` on PATH.
- `switchboard-cli run --base http://localhost:8000 --agent test` performs single checkout attempt and loops heartbeats with exponential backoff until manual exit or no task (graceful message).
- README explains install/usage.

## Idempotence and Recovery

- Packaging changes are local to client/python; reinstall to recover from stale build artifacts.
- CLI run loop prints errors and exits non-zero on fatal HTTP issues so operators can retry.

## Artifacts and Notes

- Capture CLI help output transcript in final summary.

## Interfaces and Dependencies

- Depends on `requests` library already used by `switchboard_client.py`.
- CLI interacts with Switchboard REST endpoints via `SwitchboardClient` class.

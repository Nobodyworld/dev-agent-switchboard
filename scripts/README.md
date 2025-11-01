# Developer Scripts

Utility scripts that support development, QA, and local operations live here.
Each script is designed to be idempotent and safe to run from the repository
root.

Common entry points:

- `dev.py` — orchestration helper providing bootstrap, quality gates, coverage
  enforcement, and extension scaffolding commands.
- `run_pytest.py` / `run_uvicorn.py` — wrappers for local testing and manual API
  runs.
- `local_runner.py` — reference agent loop for smoke testing deployments.
- `audit_metrics.py` — generates the complexity and dependency metrics stored in
  [`reports/`](../reports/).

Script-specific documentation appears inline in each module; cross-cutting
expectations are captured in the [style guide](../STYLE-GUIDE.md).

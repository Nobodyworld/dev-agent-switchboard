# Contributing to Switchboard

> [!NOTE]
> **This repository is archived as a reference implementation. Active product development has ended, and new feature or refactor pull requests are not planned.**

The existing contribution history is preserved because it documents how Switchboard evolved. For project context, start with [HISTORY.md](HISTORY.md) and the [archive status](docs/reports/status.md).

## Historical local setup

Readers who want to reproduce the final development-era checkout can still use the historical setup:

```bash
python -m venv .venv
# Linux/macOS: source .venv/bin/activate
# Windows PowerShell: .\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r server/requirements-dev.txt
```

The maintained local launcher at the end of development was:

```bash
python scripts/run_uvicorn.py
```

It binds to `127.0.0.1:8000` by default unless environment/arguments override it.

## Historical validation commands

The final development line used commands including:

```bash
python scripts/dev.py verify
pytest -q
SWITCHBOARD_STRICT_PLAYWRIGHT=1 pytest web/tests/test_ui.py -rA
```

The Makefile also contains convenience targets. Note that `make fmt` is **mutating**: it runs Black and may rewrite files. `make lint`, `make typecheck`, `make test`, and `make security` are check-oriented historical targets.

Passing these commands today demonstrates only the tested checkout/environment. It does not establish active support, current dependency compatibility, a release candidate, or production readiness.

## Security disclosures

Do not post credentials or exploit details publicly. See [SECURITY.md](SECURITY.md) for the archived repository's security posture.

## Historical governance

The repository retains [PROJECT_RULESET.md](PROJECT_RULESET.md), ExecPlans, issue history, pull-request discussions, and validation records as historical engineering evidence. Those documents explain how changes were governed while development was active; they do not imply that a new development campaign is open.

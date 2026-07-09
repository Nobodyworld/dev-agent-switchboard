# Contributing to Switchboard

Thank you for your interest in improving Switchboard. This guide explains how to set up a local environment, keep changes reviewable, and submit pull requests that are easy to validate.

## Code of Conduct

Participation in this project is governed by the [Code of Conduct](CODE_OF_CONDUCT.md). Please read it before engaging with the community.

## Getting Started

1. **Fork and clone** the repository.
2. **Create a virtual environment** and install dependencies:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   python -m pip install --upgrade pip
   pip install -r server/requirements-dev.txt
   ```
3. **Install pre-commit hooks**:
   ```bash
   pre-commit install --install-hooks
   pre-commit install --hook-type commit-msg
   ```

On Windows PowerShell, activate the virtual environment with:

```powershell
.\.venv\Scripts\Activate.ps1
```

## Workflow Overview

- Work in feature branches derived from `main`.
- Keep pull requests focused; avoid mixing unrelated changes.
- Update documentation when behavior, setup, configuration, or security posture changes.
- Run the relevant local checks before requesting review.
- Treat hosted CI as authoritative when it is available and healthy; if CI is unavailable, include local validation logs in the pull request.

## Documentation & Dependency Expectations

- Update [docs/cli-runtime.md](docs/cli-runtime.md) when CLI behavior or runtime summaries change.
- Record dependency upgrades, removals, or new packages in [docs/dependencies.md](docs/dependencies.md) and confirm license compatibility with the Apache-2.0 project license.
- Mention documentation updates in the pull request description so reviewers can evaluate code and docs together.

## Commit Messages

We use the [Conventional Commits](https://www.conventionalcommits.org/) specification. A valid commit message follows the pattern `type(scope?): description`.

Common types include:

- `feat`
- `fix`
- `docs`
- `refactor`
- `test`
- `build`
- `ci`
- `chore`

Local tooling enforces commit structure through [`conventional-pre-commit`](https://github.com/compilerla/conventional-pre-commit). Hosted commitlint checks may also run when GitHub Actions are available.

## Quality Gates

Before pushing, run the repository verification helper when your local environment supports it:

```bash
python scripts/dev.py verify
```

This command is intended to cover formatting, linting, type checking, tests, coverage gates, and available security checks. If your environment lacks a required tool, call that out in the pull request and run the closest supported command directly.

Individual commands remain available:

- `make fmt` — format Python code with Black and organize imports via Ruff.
- `make lint` — run static analysis and web-asset lint checks.
- `make typecheck` — run MyPy static type checking.
- `make test` — run the pytest suite.
- `make security` — run local security checks such as Bandit where configured.
- `make coverage` — execute the coverage suite and enforce per-module thresholds.
- `make todo-check` — validate TODO/FIXME priority and effort metadata.

The pre-commit configuration also runs [`detect-secrets`](https://github.com/Yelp/detect-secrets) against the `.secrets.baseline` shipped in this repository. If new findings are legitimate test fixtures, document the rationale in the pull request.

## Pull Request Checklist

- [ ] Tests added or updated where appropriate.
- [ ] Documentation updated where appropriate.
- [ ] `pre-commit run --all-files` passes locally, or limitations are documented.
- [ ] Relevant tests and security checks pass locally or in CI.
- [ ] Configuration or migration changes include rollback notes in the pull request description.
- [ ] Security-sensitive examples use unmistakably fake placeholders.

## TODOs & Follow-ups

- Use the format `TODO(Px, <effort>)` or `FIXME(Px, <effort>)` so priority and rough effort are obvious, for example `# TODO(P2, 2d) - backfill audit logs`.
- Run `python scripts/dev.py check-todos` or `make todo-check` before submission.
- Link TODOs to issues where possible for traceability.

## Triaging Issues

Use labels to communicate priority and workstream when they are available:

- `type/*` for the change class, such as bug, feature, docs, or chore.
- `priority/*` for urgency.
- `area/*` for affected subsystems, such as API, client, web, or infra.

Refer to `.github/labels.yml` if that file is present and current.

## Security Disclosures

Do not open a public issue for a suspected vulnerability. Follow [SECURITY.md](SECURITY.md), use the repository's GitHub Security Advisory flow when available, or contact the maintainer privately through GitHub if advisory reporting is unavailable.

## Support

Setup and usage questions should start with the [Support Guide](docs/guides/support.md). For implementation details, also review `docs/guides/automation.md` and `docs/guides/extension-guide.md` before integrating Switchboard with external automation or agent systems.

Thank you for contributing.
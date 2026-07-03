# Contributing to Switchboard

Thank you for your interest in improving Switchboard! This guide explains how we work, what we expect from contributors, and how to ship changes with confidence.

## Code of Conduct

Participation in this project is governed by our [Code of Conduct](CODE_OF_CONDUCT.md). Please read it carefully before engaging with the community.

## Getting Started

1. **Fork and clone** the repository.
2. **Create a virtual environment** and install dependencies:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   python -m pip install --upgrade pip
   pip install -r server/requirements-dev.txt
   ```

3. **Install the pre-commit hooks** so every commit automatically runs the same checks as CI:

   ```bash
   pre-commit install --install-hooks
   pre-commit install --hook-type commit-msg
   ```

## Workflow Overview

- Work in feature branches derived from `main`.
- Keep pull requests focused; avoid mixing unrelated changes.
- Run the local quality gates before requesting review. GitHub Actions workflows are configured in-repo but currently disabled by owner policy, so local and clean-clone validation are authoritative.
- Update documentation and changelogs when behavior changes.

## Documentation & Dependency Expectations

- Update [docs/cli-runtime.md](docs/cli-runtime.md) when CLI behaviour or
  runtime summaries change so operators have accurate guidance.
- Record dependency upgrades, removals, or new packages in
  [docs/dependencies.md](docs/dependencies.md) and ensure licenses remain
  compatible with the Apache 2.0 license.
- Mention documentation updates in your pull request description to keep
  reviewers aware of parallel doc changes.

## Commit Messages

We use the [Conventional Commits](https://www.conventionalcommits.org/) specification. A valid commit message follows the pattern `type(scope?): description`. Common types include `feat`, `fix`, `docs`, `refactor`, `test`, `build`, `ci`, and `chore`.

Our tooling enforces commit structure locally (via [`conventional-pre-commit`](https://github.com/compilerla/conventional-pre-commit)) and in CI (via [commitlint](https://commitlint.js.org/)).

## Quality Gates

Before pushing, run the full quality suite via the new `verify` helper:

```bash
python scripts/dev.py verify
```

This command executes linting, type checking, Bandit, pip-audit, and the
coverage suite (including `scripts/dev.py coverage-gate`). If you prefer Make
targets, `make qa` now chains `fmt`, `lint`, `typecheck`, `test`,
`security`, `todo-check`, and `coverage` to mirror CI.

Individual commands remain available:

- `make fmt` – Format Python code with Black and organize imports via Ruff.
- `make lint` – Static analysis with Ruff and Prettier lint checks for web assets.
- `make typecheck` – MyPy static type checking.
- `make test` – Run the pytest suite.
- `make security` – Bandit static analysis (CI additionally runs gitleaks and
  `pip-audit` for supply-chain checks).
- `make coverage` – Execute the coverage suite and enforce per-module thresholds
  via `scripts/dev.py coverage-gate`.
- `make todo-check` – Validate that TODO/FIXME markers include priority and
  effort metadata.

The `pre-commit` configuration also runs
[`detect-secrets`](https://github.com/Yelp/detect-secrets) against the
`.secrets.baseline` shipped in this repo so local commits stay secret-free. If
new findings are legitimate (e.g., generated test credentials), regenerate the
baseline via `detect-secrets scan > .secrets.baseline` and include rationale in
your PR description.

## Pull Request Checklist

- [ ] Tests added or updated where appropriate.
- [ ] Documentation updated (README, docs/, or inline docstrings).
- [ ] `pre-commit run --all-files` passes locally.
- [ ] Local quality gates are green (lint, type, tests, docs, security, coverage).
- [ ] Any configuration or migration changes include rollback instructions in the PR description.

## TODOs & Follow-ups

- Use the format `TODO(Px, <effort>)` or `FIXME(Px, <effort>)` so priority and
  rough effort are obvious (e.g., `# TODO(P2, 2d) - backfill audit logs`).
- Run `python scripts/dev.py check-todos` or `make todo-check` before
  submission; CI enforces the same policy.
- Link TODOs to issues where possible for traceability.

## Triaging Issues

We use labels to communicate priority and workstream. When opening or grooming an issue:

- Assign one of `type/*` labels (bug, feature, docs, chore).
- Use `priority/*` labels to express urgency.
- Apply `area/*` labels for affected subsystems (API, client, web, infra).

Refer to `.github/labels.yml` for the authoritative list.

## Security Disclosures

If you discover a vulnerability, please follow our [Security Policy](SECURITY.md) and report it using [GitHub Security Advisories](https://docs.github.com/en/code-security/security-advisories) instead of filing a public issue.

## Support

Questions about setup or day-to-day usage should go to [the support playbook](docs/guides/support.md).

We appreciate your contributions and look forward to collaborating with you! If
you are developing automation or agent tooling, consult `docs/guides/automation.md` and
`docs/guides/extension-guide.md` before integrating with production systems.

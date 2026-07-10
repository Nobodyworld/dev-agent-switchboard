# Contributing to Switchboard

Thank you for your interest in improving Switchboard. Keep changes focused, reproducible, and easy to review.

## Code of Conduct

Participation is governed by the [Code of Conduct](CODE_OF_CONDUCT.md).

## Local Setup

1. Fork and clone the repository.
2. Create a virtual environment and install development dependencies:

   ```bash
   python -m venv .venv

   # Linux/macOS
   source .venv/bin/activate

   # Windows PowerShell
   # .\.venv\Scripts\Activate.ps1

   python -m pip install --upgrade pip
   pip install -r server/requirements-dev.txt
   ```

3. Install the pre-commit hooks:

   ```bash
   pre-commit install --install-hooks
   pre-commit install --hook-type commit-msg
   ```

## Workflow

- Start from the current `main` branch.
- Use a focused feature or fix branch.
- Avoid mixing unrelated code, documentation, dependency, and formatting changes.
- Update documentation when behavior, setup, configuration, or security posture changes.
- Include validation commands and results in the pull request description.

Hosted GitHub Actions now provide lint, typecheck, test, security, secret, link, coverage, browser, and commit-message checks. Run the relevant checks locally before pushing as well, and document any environment limitations.

## Commit Messages

Use [Conventional Commits](https://www.conventionalcommits.org/):

```text
type(scope?): description
```

Common types include `feat`, `fix`, `docs`, `refactor`, `test`, `build`, `ci`, and `chore`.

Local commit-message checks use [`conventional-pre-commit`](https://github.com/compilerla/conventional-pre-commit), and hosted Commitlint validates pull-request commit ranges.

## Quality Gates

Run the repository verification helper:

```bash
python scripts/dev.py verify
```

For release-sensitive work, run the relevant direct commands as well:

```bash
pre-commit run --all-files --show-diff-on-failure
pytest -q
SWITCHBOARD_STRICT_PLAYWRIGHT=1 pytest web/tests/test_ui.py -rA
bandit -q -r server -x server/tests
pip-audit --progress-spinner=off -r server/requirements-dev.txt
gitleaks detect --verbose
git diff --check
```

Use `make` targets when they are supported by your environment:

- `make fmt` — formatting checks;
- `make lint` — static analysis and web-asset checks;
- `make typecheck` — Mypy;
- `make test` — pytest;
- `make security` — configured local security checks;
- `make coverage` — coverage and module thresholds;
- `make todo-check` — TODO/FIXME metadata validation.

Do not regenerate `.secrets.baseline` merely to suppress a new finding. Confirm that the value is a safe fixture, document the reason, and review the diff before updating the baseline.

## Documentation and Dependencies

- Update [docs/cli-runtime.md](docs/cli-runtime.md) when CLI behavior or runtime summaries change.
- Update [docs/dependencies.md](docs/dependencies.md) for dependency additions, removals, or upgrades.
- Confirm dependency licenses are compatible with Apache-2.0.
- Use unmistakably fake values in configuration, token, and credential examples.
- Record migration or rollback guidance for configuration and persistence changes.

## TODOs and Follow-ups

Use the repository format:

```text
TODO(Px, <effort>)
FIXME(Px, <effort>)
```

Run:

```bash
python scripts/dev.py check-todos
```

Link follow-up work to an issue when practical.

## Pull Request Checklist

- [ ] The change is focused and based on current `main`.
- [ ] Tests were added or updated where appropriate.
- [ ] Documentation was updated where appropriate.
- [ ] Relevant local quality and security checks passed.
- [ ] Hosted checks are green.
- [ ] Environment limitations and skipped checks are stated explicitly.
- [ ] Configuration or migration changes include rollback guidance.
- [ ] Security-sensitive examples contain no real credentials.

## Security Disclosures

Do not file a public issue for a suspected vulnerability. Follow [SECURITY.md](SECURITY.md) and use private GitHub Security Advisory reporting when available.

## Support

Start with the [Support Guide](docs/guides/support.md). For agent and automation integrations, also review:

- [Automation Guide](docs/guides/automation.md)
- [Extension Guide](docs/guides/extension-guide.md)

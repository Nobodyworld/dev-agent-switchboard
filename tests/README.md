# Test Suite

The `tests/` directory houses black-box and integration-style tests that exercise
public entry points exposed by the server package and client CLI.

Structure overview:

- `test_settings_validation.py` — configuration parsing safeguards for rate
  limits, leases, and extension overrides.
- `test_switchboard_cli.py`, `test_switchboard_client_behaviors.py`, and related
  modules — CLI contract and HTTP client behaviour checks.
- `test_dev_cli.py` and `test_runtime_configuration.py` — developer tooling and
  runtime summary validation.

Additional unit tests co-located under `server/tests/` cover package-internal
concerns. Run `pytest -q` or `python scripts/dev.py verify` to execute the full
suite.

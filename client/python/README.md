# Python Client Package

The `client/python` package exposes the typed `SwitchboardClient` HTTP helper
alongside CLI utilities that power `switchboard_cli.py` and automated agents.

Key modules:

- [`switchboard_client.py`](switchboard_client.py) — resilient REST wrapper with
  request retry logic and context manager support.
- [`runtime_config.py`](runtime_config.py) — normalises configuration derived
  from CLI arguments and server responses.
- [`switchboard_cli.py`](switchboard_cli.py) — argparse-driven CLI entrypoint
  for interactive agents.

Refer to the [client quick start](../../README.md#python-client-example) and the
[automation playbook](../../docs/guides/automation.md) for integration
examples.

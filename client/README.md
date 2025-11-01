# Client Tooling

Switchboard ships official client libraries that help agents and operators talk
to the API without writing boilerplate HTTP code.

- [`python/`](python/) packages the `switchboard_client` module and CLI helpers
  used by `switchboard_cli.py`.
- Root-level [`switchboard_client.py`](../switchboard_client.py) and
  [`switchboard_cli.py`](../switchboard_cli.py) re-export the modern client
  interfaces for compatibility with existing integrations.

See the [AI integration guide](../docs/ai-interface.md) for protocol details
and the [CLI runtime walkthrough](../docs/cli-runtime.md) for interactive usage
patterns.

# Switchboard Python Client

This package provides a minimal Python client and command line interface for interacting with a running [Switchboard](../..) ser
ver. It wraps the REST endpoints that manage task checkouts and leases so that humans or automation can participate in the task
workflow without cloning the full repository.

## Installation

```bash
pip install switchboard-client
```

During development you can install from a local clone:

```bash
cd client/python
pip install -e .
```

The package depends on [`requests`](https://requests.readthedocs.io/) and targets Python 3.9 or newer.

## Command Line Interface

After installation the `switchboard-cli` command becomes available. The CLI currently offers a single `run` subcommand that regi
sters the provided agent identifier, continuously polls for available tasks, and keeps the active lease alive with heartbeats u
ntil you mark the task as complete or abandon it.

```bash
switchboard-cli run --base http://localhost:8000 --agent demo-agent
```

While idle the loop sleeps for 10 seconds between checkout attempts (configurable with `--poll-interval`). When a task is acquir
ed the CLI prints a summary and starts a background heartbeat thread that renews the lease every 30 seconds by default (`--heart
beat-interval`). The prompt (`Action [complete/abandon/heartbeat/status/notes/help]>`) accepts the listed commands so you can fin
ish the task, abandon it, inspect status, or add completion notes. `Ctrl+C`/`Ctrl+D` map to **abandon** to avoid leaving the leas
e hanging if the terminal exits unexpectedly.

Run `switchboard-cli --help` to see the available global and subcommand options.

## Python API

The CLI is built on top of the reusable `SwitchboardClient` class exposed by this package. You can embed it into your own automa
tion by importing the class:

```python
from switchboard_client import SwitchboardClient

client = SwitchboardClient("http://localhost:8000", "my-agent")
task = client.checkout()
```

See `examples/agent_example.py` for a simple polling loop that completes tasks after a simulated workload.

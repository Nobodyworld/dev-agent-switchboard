# CLI Runtime Guide

Switchboard ships with an interactive CLI that mirrors the behaviour of the
reference agent loop in `client/python/switchboard_cli.py`. This guide explains
how runtime configuration values are derived, what the CLI prints at startup,
and how to interpret warnings that might appear when settings are sanitised.

## Start-up Flow

1. The CLI registers the agent via `/api/agents`.
2. It attempts to fetch `/api/settings` to learn the server's lease duration and
   `/api/system-state` to determine whether maintenance mode is active.
3. User-supplied arguments are combined with the server response by
   `derive_runtime_configuration`.
4. A **runtime summary** is displayed. Values are rounded for readability and
   match the table below:

| Field | Description |
| --- | --- |
| Maintenance mode | Whether maintenance is enabled and the operator-provided message. |
| Heartbeat interval | Seconds between automatic heartbeats while a task is held. |
| Poll interval | Baseline wait time between checkout attempts. |
| Max poll interval | Upper bound when exponential backoff is applied. |
| Backoff multiplier | Growth factor for backoff. |
| Server lease | Lease duration returned by the server (if available). |

Warnings collected during configuration (for example, negative poll intervals
or missing lease data) are written to **stderr** so shell scripts can react to
them independently of the tabular summary.

## Interpreting Warnings

- *"failed to fetch server settings"* — The CLI could not retrieve `/api/settings`.
  The session continues with defaults, but the runtime summary will omit the
  lease duration.
- *"poll interval was negative"* — Negative values are clamped to zero so the
  loop does not sleep for a negative duration.
- *"max poll interval was lower than the base interval"* — The upper bound must
  be greater than or equal to the base poll interval. The CLI silently promotes
  the upper bound to the base interval.
- *"backoff multiplier was less than one"* — Multipliers below 1.0 would shrink
  the interval. The CLI raises them to 1.0 to maintain monotonic backoff.

## Recommended Defaults

The `switchboard-cli run` command exposes a handful of flags to tune runtime
behaviour. Defaults are listed alongside each flag in `--help` output and are
summarised below for convenience:

| Flag | Default | Notes |
| --- | --- | --- |
| `--poll-interval` | 10 seconds | Time between checkout attempts when tasks are available. |
| `--max-poll-interval` | 120 seconds | Upper bound used during exponential backoff. |
| `--backoff-multiplier` | 2.0 | Multiplier when no task is available. |
| `--heartbeat-interval` | 30 seconds | Interval between automatic heartbeats. |

If the server reports a lease duration shorter than the requested heartbeat
interval, the CLI halves the lease to remain well inside the allowed window.
This keeps heartbeats predictable even when operators configure short leases.

---

Switchboard is licensed under the Apache License 2.0.

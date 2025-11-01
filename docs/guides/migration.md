# Migration Notes

## Rate Limit Configuration Validation

Starting with the 2024-10-19 Adaptive Perfection Update, invalid values supplied
via the `SWITCHBOARD_RATE_LIMIT_REQUESTS` or `SWITCHBOARD_RATE_LIMIT_WINDOW_SECONDS`
environment variables raise `RateLimitConfigurationError` during startup. Before
upgrading, ensure deployment manifests set these variables to non-negative
integers (or omit them to use defaults).

No database schema changes were introduced in this update.

## Lease Duration Configuration Exposure

Deployments can now override task lease duration via the
`SWITCHBOARD_LEASE_SECONDS` environment variable. Values must be positive
integers; invalid settings raise `LeaseConfigurationError` during application
startup. The FastAPI server exposes `/api/settings` so operators and agents can
inspect the active lease window alongside rate limit thresholds. The Python CLI
consumes this endpoint to automatically clamp heartbeat cadence when a requested
interval would exceed the lease duration. When settings are missing or invalid
the CLI logs a warning and uses conservative defaults so long-running tasks are
still protected.

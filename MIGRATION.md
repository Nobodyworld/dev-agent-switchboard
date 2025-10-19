# Migration Notes

## Rate Limit Configuration Validation

Starting with the 2024-10-19 Adaptive Perfection Update, invalid values supplied
via the `SWITCHBOARD_RATE_LIMIT_REQUESTS` or `SWITCHBOARD_RATE_LIMIT_WINDOW_SECONDS`
environment variables raise `RateLimitConfigurationError` during startup. Before
upgrading, ensure deployment manifests set these variables to non-negative
integers (or omit them to use defaults).

No database schema changes were introduced in this update.

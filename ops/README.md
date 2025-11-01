# Operational Configurations

Deployment-focused configuration files live here:

- `docker-compose.yml` — local orchestration for the API, worker, and database.
- `logging.ini` — baseline logging configuration consumed by the server.
- `otel.yaml` — OpenTelemetry collector settings for observability experiments.

Coordinate changes to these files with the [operations report](../docs/reports/operations-report.md)
and document new requirements in the [specification](../SPEC.md).

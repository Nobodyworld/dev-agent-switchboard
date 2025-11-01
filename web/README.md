# Web Dashboard

The `web/` directory contains the static assets served alongside the API to give
operators a live view of plan activity.

Layout:

- `index.html` — root document bootstrapping the dashboard.
- `static/` — JavaScript, CSS, and asset bundles that drive the UI.
- `tests/` — lightweight DOM and behaviour tests for frontend components.

UI integrations rely on the APIs documented in the [AI integration guide](../docs/ai-interface.md)
and the observability references in [docs/observability.md](../docs/observability.md).

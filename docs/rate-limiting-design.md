# Rate Limiting Design Note

## Objective
Add a lightweight request rate limiting capability to protect the Switchboard API and admin UI from abusive traffic while keeping the core application uncomplicated and easy to operate.

## Scope
- Guard all HTTP(S) entrypoints to Switchboard: public API (`/api/*`), live files (`/live/*`), and the admin UI.
- Focus on basic per-client protections rather than quota/billing enforcement.
- No changes to application endpoints or database schema.

## Requirements
- **Configurable thresholds:** Allow operators to tune request limits without code changes. Defaults should cover common small-team deployments.
- **Fast failure:** Reject over-limit requests before hitting the FastAPI router so that rate-limited traffic does not consume application resources.
- **Visibility:** Emit metrics and/or logs so operators can observe rate limiting behavior and adjust as needed.
- **Bypass for trusted actors:** Permit exempting health checks or internal automation (via source IP ranges or auth headers).
- **Low operational overhead:** Favor primitives that can run in the existing Docker Compose deployment without additional stateful services.

## Design Options

### Option A: Reverse Proxy Enforcement
Run a reverse proxy (e.g., Traefik, Nginx, or Caddy) in front of the ASGI app and use its built-in rate limiting features.

**Pros**
- Mature, battle-tested algorithms (token bucket / leaky bucket) with low overhead.
- Enforces limits before requests reach the ASGI stack.
- Easy to configure via environment variables or static files mounted into the proxy container.
- Can share state across multiple app instances by using proxy-specific clustering features (e.g., Nginx `limit_req_zone` with shared memory).

**Cons**
- Adds another container to the deployment if not already present.
- Per-client identification generally limited to IP unless additional headers are propagated.
- Requires coordination when deploying behind an upstream load balancer to ensure correct client IP visibility (e.g., `X-Forwarded-For`).

**Implementation Sketch**
- Extend `ops/docker-compose.yml` with a reverse proxy service (Traefik or Nginx) configured to forward to the existing FastAPI container.
- Define default rate limit zones, e.g., `30 req/s burst 60` for `/api/*` and a higher allowance for `/live/*` static fetches.
- Provide environment variables (`SWITCHBOARD_RATE_LIMIT_API`, etc.) to customize thresholds.
- Document trusted IP lists for internal traffic and health checks.

### Option B: ASGI Middleware
Insert a rate limiting middleware into the FastAPI application (e.g., [slowapi](https://github.com/laurentS/slowapi) or a custom token bucket implementation backed by Redis or in-process counters).

**Pros**
- Runs inside the Python app; no extra infrastructure component is required.
- Can inspect authentication headers or agent IDs to make finer-grained decisions than IP-only limits.
- Easier to unit test alongside existing FastAPI application tests.

**Cons**
- Requests still reach the application stack before being rejected, consuming CPU/memory.
- In-process counters reset on restart and do not work for multi-instance deployments unless backed by Redis or similar.
- External state (Redis) introduces additional operational complexity not currently in the stack.

**Implementation Sketch**
- Add a middleware that calculates a key from client IP + optional agent identifier.
- Use a simple token bucket stored in an in-memory LRU cache for single-instance deployments; optionally support Redis when configured.
- Return `429 Too Many Requests` with a retry-after header and structured log events.
- Expose metrics via Prometheus (middleware counter) or logging hooks.

## Recommendation
Implement Option A (Reverse Proxy Enforcement) as the default path because it minimizes application changes, offloads rate limiting to well-optimized components, and aligns with the existing Docker Compose deployment story. Operators running Switchboard in managed environments (e.g., behind API gateways) can disable the bundled proxy and rely on their platform’s rate limiting instead.

Option B can remain a future enhancement for deployments that cannot use a proxy or require per-agent limits. Should that need arise, ensure shared state is available before enabling multi-instance support.

## Open Questions
1. Which proxy to standardize on? Traefik integrates cleanly with Docker labels, while Nginx has ubiquitous familiarity.
2. What default thresholds balance protection with legitimate bursty traffic from agents syncing plans?
3. How should trusted actor bypasses be configured and distributed (environment variables, config files, or admin UI)?
4. Do we need differentiated limits for write vs. read endpoints (e.g., stricter on task mutations)?

## Next Steps
1. Choose a proxy (recommend Traefik for Docker-first workflow) and define base configuration templates.
2. Add documentation for operators covering deployment topology, configuration knobs, and observability signals.
3. Implement proxy service in Docker Compose and verify rate limiting behavior with load tests.
4. Optionally prototype ASGI middleware to support non-proxy deployments once demand is confirmed.

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

## Chosen Approach

Switchboard currently ships with the ASGI middleware option implemented in
[`server/middleware/rate_limit.py`](../server/middleware/rate_limit.py). The
middleware keeps a sliding window counter per client identifier (derived from
trusted proxy headers when present) and rejects requests with `429 Too Many
Requests` once the configured allowance is exceeded. This in-process strategy
was selected because it:

- Adds zero infrastructure dependencies to the default Docker Compose workflow
  while still protecting the API and admin UI from abusive bursts.
- Gives the application full control over how clients are identified, enabling
  trusted bypasses for known agents without requiring proxy-specific features.
- Keeps operational complexity low for the common single-instance deployment by
  avoiding the need for Redis or an additional reverse proxy container.

Operators who already terminate traffic through a load balancer or API gateway
can continue to layer those rate limiting features in front of Switchboard. An
external proxy remains the right choice when you need shared counters across
multiple Switchboard instances, want more sophisticated algorithms (e.g., token
bucket with distributed state), or must enforce per-path policies before the
requests reach the ASGI stack.

### Configuration knobs

The middleware reads its thresholds from environment variables that are also
documented in the README:

- `SWITCHBOARD_RATE_LIMIT_REQUESTS` — maximum requests permitted within the
  window (default `120`). Set to `0` to disable the middleware entirely.
- `SWITCHBOARD_RATE_LIMIT_WINDOW_SECONDS` — sliding window size in seconds
  (default `60`).
- `SWITCHBOARD_RATE_LIMIT_TRUSTED_BYPASS` — comma-separated list of client IPs
  allowed to bypass rate limiting. When Switchboard sits behind a proxy, the
  middleware inspects the first value in `X-Forwarded-For` as long as the proxy
  address is listed in `trusted_proxies` (configured via
  `SWITCHBOARD_RATE_LIMIT_TRUSTED_PROXIES`).

### Operational notes

- Counters live in memory and reset when the process restarts. This is
  sufficient for the single-instance deployment model but means limits are not
  coordinated across horizontally scaled app servers.
- When deploying behind another proxy, ensure `trusted_proxies` in
  `RateLimitSettings` includes the proxy’s IP so that the middleware can honor
  `X-Forwarded-For` and apply bypass rules to the real client address.

## Future work

If demand for the proxy-based option resurfaces, the following prerequisites
should be satisfied before switching the default:

- Define a standard reverse proxy container (likely Traefik or Nginx) within
  `ops/docker-compose.yml`, including configuration templates checked into the
  repository.
- Establish guidance for propagating real client IPs through any upstream load
  balancers so proxy-enforced limits remain accurate.
- Document how proxy-managed limits interact with the existing middleware—e.g.,
  whether the middleware is disabled entirely or kept as a secondary safety
  net—and provide migration steps for operators upgrading from the
  single-process setup.

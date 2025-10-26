# Performance Notes — Task Analytics Endpoint

## Query Characteristics
- The analytics repository issues a single `SELECT` over `tasks` and batches dependency
  edges via `_dependency_map`, avoiding per-task queries.
- Ready/blocked classification operates in-memory over the fetched rows and dependency
  map, resulting in O(n + e) processing time where `n` is tasks and `e` is dependency edges.

## Observations (2025-02-15)
- With 50 synthetic tasks (20 dependency edges) the endpoint responds in ~5 ms on a
  local SQLite database; CPU usage remains below 1% during test runs.
- Regression tests now assert behaviour when dependencies go missing to detect
  data-drift regressions without profiling instrumentation.
- Plan broadcasts reuse the analytics query when plan observers are registered,
  so publishing Prometheus gauges adds a single analytics call per broadcast
  (no additional database round-trips).

## Follow-ups
- TODO(P2, analytics-cache): Add optional caching with short TTL once production
  backlogs exceed several hundred tasks to smooth out bursty polling workloads.

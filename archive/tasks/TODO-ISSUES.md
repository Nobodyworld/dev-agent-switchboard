<!-- Archived: 2025-10-30. Tasks migrated to root TASKSLIST.md -->
# TODO Issue Backlog

The following gaps were identified while stabilizing the orchestration router.
Track them as GitHub issues or internal tickets as appropriate.

- [ ] **Queue prioritisation policy (P1, 5d)** – Tasks are still ordered by ID. Define a
      priority field and update `checkout_task` to honour it without breaking the
      existing API contract.
- [ ] **Health metrics export (P2, 3d)** – `/health/ready` surfaces status but does not
      emit Prometheus metrics. Add counters/gauges so operators can alert on
      repeated readiness failures.
- [ ] **Runner abandonment workflow (P2, 2d)** – The local runner currently requires a
      manual interrupt to exit heartbeat mode. Explore adding a `--max-heartbeats`
      flag or automatic abandonment after a configurable duration.

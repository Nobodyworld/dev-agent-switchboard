# Switchboard Archive Status

_Last reviewed: 2026-09-22_

## Classification

```text
ARCHIVED REFERENCE IMPLEMENTATION — NOT PRODUCTION READY
```

Active product development has ended. The repository is preserved publicly for source inspection, engineering history, and optional local reproduction. No new feature roadmap, release line, production deployment, or security-maintenance commitment is active.

## Final development line

```text
repository: Nobodyworld/dev-agent-switchboard
last feature-bearing main before archive closeout: ada28f080a908cbdc6f29a761e5402664c7d3c87
public-history PR: #164 — merged
workspace-hygiene PR: #148 — merged
execution-broker epic: #111 — closing with archive disposition
GitHub repository archive toggle: pending repository-level final action
```

The exact final archive-closeout merge SHA is represented by GitHub `main` after the archive documentation PR lands. This file intentionally avoids a self-referential commit hash.

## What is preserved

The archive retains:

- the original dependency-aware task/agent/lease coordinator;
- live-file and WebSocket coordination work;
- the later deterministic local execution broker;
- exact-SHA work orders and reviewed manifests;
- compact evidence and exact evidence reuse;
- local worker routing and operator workflows;
- readiness/progress and owned validation lifecycle work;
- scoped worker credentials with rotation and revocation;
- historical ExecPlans, pull requests, issues, tests, failures, and acceptance evidence.

See [HISTORY.md](../../HISTORY.md) for the narrative history and architectural conclusions.

## Why development stopped

The repository ultimately contained two distinct domains:

1. **agent coordination** — tasks, dependencies, ownership, leases, capabilities, handoffs, and shared state;
2. **trusted local execution** — exact source identity, reviewed operations, worker credentials, process control, isolation, artifacts, cleanup, and evidence.

Repeated refactors improved the implementation but did not make those responsibilities one coherent product. Repository-aware GitHub connectivity also reduced the need for a thick custom cross-repository coordination layer, while trusted local execution remained a separate machine-security problem.

The decision was therefore to preserve Switchboard rather than add another major subsystem such as OS-backed isolation or a new remote transport.

## Security boundary

The final codebase is **not** a production sandbox.

In particular:

- cooperative repository read-only policy is not OS isolation;
- process-tree containment is not a complete host-security boundary;
- scoped worker credentials limit API authority but do not isolate filesystems, identities, networks, or unrelated host secrets;
- direct public-internet and untrusted multi-tenant operation were never accepted.

The historical developer-preview tag `v0.1.0-preview.1` predates major later execution-broker capabilities and remains historical evidence only.

## Successor work

No successor repository is declared here yet. Reusable ideas or logic may be reassigned later, but that work is intentionally separate from the public archive and does not make this repository active again.

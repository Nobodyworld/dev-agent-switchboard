# Trusted workload onboarding

Switchboard onboards deterministic repositories through reviewed source, not an
API-authored command or remote-shell contract. A complete workload consists of
one catalog repository entry, one or more immutable trusted manifests, an
operator-configured canonical checkout, and production-path acceptance evidence.

## Add the reviewed contract

1. Inspect the target repository at an exact commit. Record its supported Python
   and operating-system range, fixed quality commands, dependency locks,
   artifacts, network needs, and read/write posture.
2. Define a typed `WorkloadProfile` in
   `server/execution/workload_profiles.py`. Its compiler emits the registry
   manifest and its safe catalog mapping after concrete registry types are
   available. Every step uses a fixed tuple argv with `shell=False`; callers
   cannot supply commands, environment values, parsers, paths, or digests.
   Bind timeouts, capabilities, result-affecting input paths, typed result
   contracts, bounded resource limits, and declared artifacts.
3. Keep the catalog mapping source-controlled and strict. Use the canonical
   case-sensitive `owner/repository`, bounded public display text, explicit
   manifest name/version references, support status, maintained documentation
   reference, and an allowed default. Unknown fields, case collisions,
   duplicate manifest identities, dynamic imports, and source roots outside the
   reviewed public set fail closed.
4. Print existing manifest digests before and after the edit. Repository display
   metadata must not change historical evidence identities.

The catalog is deliberately exact: `Nobodyworld/dev-agent-switchboard`,
`Nobodyworld/app-accounting-modular`, `Nobodyworld/dev-logger-zscripts`, and
`Nobodyworld/app-industry-resilience`. The legacy manifests keep their
historical digest inputs. Factory profiles additionally bind source-controlled
execution steps, result contracts, resource limits, and result-affecting inputs
into the new manifest and reuse identities, without changing a legacy evidence
identity.

`validate-zscripts@1` is one fixed `python scripts/quality_gate.py quality`
step under Python 3.11+, Node 24.12.0+, and pnpm exactly 10.18.1. Its closed
quality-summary parser requires the three fixed JSON reports and only accepts
the `quality` profile, passed status, exactly 26 ordered passed operation
records, 85% coverage threshold, and safe diagnostics telemetry status.
`validate-industry-resilience@1` uses Python 3.13+ and
ten direct steps: Python version, `pip check`, Black, Ruff, Mypy, required
85% runtime coverage for `src/adapters`, `src/agents`, `src/application`,
`src/core`, `src/extensions`, `src/infrastructure`, `src/interfaces/api`, and
`src/interfaces/streamlit` (term-missing plus XML/JSON reports), informational
full-source coverage, benchmark metrics, one combined `pip_audit` JSON output
at `build/reports/pip-audit.json`, and baseline-only
`detect_secrets.pre_commit_hook`. The detect-secrets step is not a source scan.
Docker, Edge, Playwright, screen-reader, release, publication, data-refresh,
and provider acceptance remain explicitly excluded.

## Configure an eligible worker

Add the exact logical repository key and its canonical absolute checkout path to
the worker's local JSON `repositories` mapping. The worker registers only sorted
keys. Switchboard never receives the path. Ensure the exact requested commit
object already exists locally; workers do not fetch or modify refs.

Create an enabled operator-owned routing profile when using
`cheapest_capable`; `first_available` deliberately works without one. The
readiness API and command center evaluate the selected manifest and routing
inputs through the same repository, capability, liveness, polling, status,
capacity, network, read-only, hard-pin, cost, and quota rules used by routing.
For the accounting contract, a worker advertising Python 3.11 is ineligible;
its actual registration must report Python 3.12 or newer. Readiness does not
reserve anything or prove the SHA exists.

## Acceptance evidence

Automated onboarding must prove:

- catalog definitions, digest stability, safe API metadata, and invalid-pair
  rejection before persistence;
- omitted/legacy worker state upgrades to Switchboard only and survives two
  startups;
- first-available, cheapest-capable, pins, assessment, fresh execution, and
  exact reuse reject unmapped workers before capacity/quota mutation;
- a real `ExecutionClient` and `LocalWorker` execute the fixed manifest against
  a committed disposable canonical fixture through the real server routes;
- retained ownership, result, logs, and declared artifacts are regular,
  contained, hashed, and stable;
- the equivalent second request performs worker-local retained-evidence
  verification, creates a distinct run linked to its source fingerprint, and
  executes zero steps;
- canonical repositories and worker roots are clean after cleanup; and
- strict browser tests show filtered manifests and safe readiness at desktop
  and 390-pixel widths with no token exposure or console errors.

The general quality and coverage suites remain on the repository baseline
Python 3.11 runtime. The one real accounting `LocalWorker` acceptance is marked
to skip below Python 3.12 and runs as a separate required
`Accounting workload acceptance` job on Python 3.12; its JUnit guard requires
exactly one passing test with no failures, errors, or skips.

The factory adds two more isolated required hosted jobs: Zscripts runs the
single committed synthetic real-worker selector under Python 3.11, Node
24.12.0, and pnpm 10.18.1; Industry Resilience runs its single committed
synthetic selector under Python 3.13. Each JUnit guard requires exactly one
passing case with no skip, failure, or error. These jobs do not check out,
execute, upload artifacts from, or publish to either external repository.

A separate read-only coverage job parses only its bounded local coverage JSON
and the two reviewed source files. It requires at least 90% aggregate
executable-line coverage for the named security-critical factory
validation/compilation functions and the named catalog-readiness helpers/method.
Static profile data
literals and unrelated legacy `ExecutionService` paths are intentionally outside
that metric: they are protected by deterministic identity fixtures and the
baseline suite, while including them would turn the gate into an unrelated
whole-module threshold. A renamed or missing named function fails the coverage
job rather than silently dropping out of review.

Live external dogfood is additional evidence, never a substitute for those
offline proofs. Re-resolve the target immediately before use. If the PR moved,
closed, or merged, record that exact blocker and do not fabricate a current or
stale publication result. Publishing to an external PR always requires a
separate explicit owner action.

For this slice, Zscripts PR #119 is merged: `TARGET-STATE-BLOCKED` is the
required live disposition and a newer replacement PR is not interchangeable.
Industry Resilience PR #130 remains live-dogfood eligible only if its current
head/state are re-resolved and an operator provides an approved canonical local
checkout containing that exact object. If that checkout is unavailable, live
dogfood is blocked; do not clone, fetch, create an external worktree, or claim
an external result. Source-controlled profile revocation blocks future routing
only and never rewrites historical evidence or expands worker authority.

# Trusted workload onboarding

Switchboard onboards deterministic repositories through reviewed source, not an
API-authored command or remote-shell contract. A complete workload consists of
one catalog repository entry, one or more immutable trusted manifests, an
operator-configured canonical checkout, and production-path acceptance evidence.

## Add the reviewed contract

1. Inspect the target repository at an exact commit. Record its supported Python
   and operating-system range, fixed quality commands, dependency locks,
   artifacts, network needs, and read/write posture.
2. Add a `TrustedManifest` in `server/execution/registry.py`. Every step must use
   a fixed tuple argv with `shell=False`; callers cannot supply commands,
   environment values, paths, or digests. Bind timeouts, parsers, safe metadata,
   dependency-lock paths, and declared artifacts.
3. Add one strict `TrustedRepository` definition in
   `server/execution/catalog.py`. Use the canonical case-sensitive
   `owner/repository`, bounded public display text, explicit manifest
   name/version references, support status, maintained documentation reference,
   and an allowed default. Unknown fields fail closed.
4. Print existing manifest digests before and after the edit. Repository display
   metadata must not change historical evidence identities.

The first external contract, `validate-accounting-modular@1`, mirrors eleven
reviewed Python quality steps. Docker and attended browser validation remain
deferred because they require distinct worker capabilities and threat models.

## Configure an eligible worker

Add the exact logical repository key and its canonical absolute checkout path to
the worker's local JSON `repositories` mapping. The worker registers only sorted
keys. Switchboard never receives the path. Ensure the exact requested commit
object already exists locally; workers do not fetch or modify refs.

Create an enabled operator-owned routing profile when using
`cheapest_capable`. The readiness API and command center report advertisement,
activity, and profile state only. They do not reserve anything or prove the SHA
exists.

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

Live external dogfood is additional evidence, never a substitute for those
offline proofs. Re-resolve the target immediately before use. If the PR moved,
closed, or merged, record that exact blocker and do not fabricate a current or
stale publication result. Publishing to an external PR always requires a
separate explicit owner action.

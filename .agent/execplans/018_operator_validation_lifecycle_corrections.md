# Close operator report and preflight review gaps

This is a living correction addendum to
[ExecPlan 018](018_operator_validation_lifecycle.md), maintained under
[PLANS.md](../PLANS.md). Keep Progress, Surprises & Discoveries, Decision Log, and
Outcomes & Retrospective current. Issue #151 remains the accepted scope.

## Purpose / Big Picture

Complete the four focused follow-up corrections without restarting the operator
lifecycle implementation: trustworthy recorded-report validation and inspection,
manifest timeout compatibility before launch, shared IPv6-safe HTTP origins, and
bounded unambiguous configuration parsing.

```text
repository: Nobodyworld/dev-agent-switchboard
issue / pull request: #151 / #152
branch: feat/operator-validation-lifecycle
starting head: 44a55aa6f13f0df48704bda52041d3eccaff6f0a
base main: fbaf2f6170a9f5a27e6573d9d664923cef8f6ae6
classification: PUBLIC DEVELOPER PREVIEW — NOT PRODUCTION READY
```

GitHub's current PR head and check results are authoritative for moving state.
The prior head's green workflows and no-blocker review do not validate this patch.

## Progress

- [x] Reconfirm the existing draft PR, branch, base, and reviewed starting head.
- [x] Enforce strict serialized report shape and whole-lifecycle consistency.
- [x] Read reports through the stable owned-record boundary and label inspection
  as stored-state inspection rather than fresh execution verification.
- [x] Reject incompatible manifest/step and observation timeouts in preflight.
- [x] Share one IPv6-aware origin between lifecycle and worker configuration.
- [x] Bound configuration reads and reject duplicate keys and non-finite JSON.
- [x] Add focused regressions, coherent existing report fixtures, and IPv6
  synthetic lifecycle cases without removing existing boundary tests.
- [x] Syntax-check all ten changed Python files in the review workspace.
- [x] Correct hosted-discovered test-label and retention-contract assumptions;
  preserve source-expiry verification and all ownership test counters.
- [ ] Complete exact-head hosted lint, types, tests, security, coverage, browser,
  and workload acceptance checks; correct any implementation regressions.
- [ ] Verify the existing Windows worktree identity and fast-forward synchronization.
- [ ] Complete Windows focused and repository validation with the pinned tools,
  including real junction handling and fresh/reuse process/port cleanup.
- [ ] Record exact final local/remote parity and sanitized validation evidence.
- [ ] Obtain final connector review; keep PR #152 draft and unmerged.

## Surprises & Discoveries

- The prior report serializer validated runs individually but accepted incomplete
  successful report objects. Existing unit fixtures also used such objects;
  replacing them with coherent success fixtures is part of the correction, not
  permission to weaken assertions.
- Marker reads already had stable identity and no-follow checks, but report reads
  bypassed them. Reusing that boundary avoids a competing filesystem reader.
- The generated worker refuses a 5,400-second Accounting manifest under the
  operator's default 3,600-second budget. This must fail before runtime creation.
- An isolated review-workspace probe initially passed 66 new regression cases
  and skipped its Windows-only junction case. Its registry/HTTP/process
  dependencies were stubbed; it is not full-repository, real-worker, or Windows
  acceptance evidence.
- Hosted CI exposed the benign `process_token` preflight-check name in a complete
  report fixture. The corrected test checks absence of an actual environment
  credential value and credential field, not absence of the word `token`.
- Real hosted fresh-only acceptance passed on IPv4 and IPv6, then fresh/reuse
  revealed that each run has its own retained-record expiry. The source expiry
  remains unchanged and is independently checked by the live lifecycle. The
  report validator must not equate the two records' lifetimes. A new positive
  regression allows distinct valid expiries while expired-at-completion records
  remain rejected. The updated isolated probe passes 67 cases with one Windows
  skip; exact-head real acceptance remains required.

## Decision Log

- Preserve report schema 2 and its stored JSON representation. Tighten validation
  and distinguish inspected human output without rewriting historical evidence.
- Validate retention relative to recorded completion during inspection. Actual
  reuse remains governed by the existing live evidence verifier. Preserve each
  run's own expiry without renewing or reinterpreting original source retention.
- Keep timeout choices explicit; reject inadequate budgets rather than silently
  raising them. Keep IPv4, localhost, and IPv6 loopback configuration supported.
- Use the existing feature branch and PR. Do not create replacement branches,
  worktrees, execution backends, or credential/isolation architectures.

## Context and Plan of Work

The changes are confined to `client/python/execution_operator`, its tests, and
this correction documentation. The new `report_contract.py` contains strict
serialized shape and cross-field checks; `models.py` retains per-run, path, and
size checks. `runtime.py` owns stable report reads; `lifecycle.py` composes them.
`config.py`, `preflight.py`, and `processes.py` share the input/launch corrections.

The [operations supplement](../../docs/operations/operator-validation-corrections.md)
explains observable behavior and bounded failure reasons.

## Concrete Steps and Validation

Before local work, verify repository origin, Git common directory, `git worktree
list --porcelain`, worktree root, branch/upstream, clean status, and exact HEAD.
Use the existing issue-151 implementation worktree. Fetch normally and
fast-forward only to the connector-reported PR head. Any mismatch, local edits,
or divergence requires inspection, not reset, rebase, forced checkout, stash
application, or a replacement worktree. Keep machine-specific paths private.

Run both focused files against the real repository dependencies:

```text
python -m pytest client/python/tests/test_execution_operator.py client/python/tests/test_execution_operator_corrections.py -q -rA
```

Then run the existing complete repository verification, pytest, strict browser,
security/secret, and coverage gates with the pinned toolchain. Preserve existing
thresholds. On Windows, verify real junction tests and both synthetic modes on
IPv4 and IPv6, reporting genuine platform skips explicitly. Check cleanup of only
new test-owned processes, listeners, and disposable source. Do not represent the
synthetic fixture as execution against Accounting or another external target.

Record the exact checked SHA, tool versions, pass/fail/skip counts, cleanup facts,
and limitations. All hosted results must belong to the exact current head. Any
follow-up correction uses normal additive commits on this same branch.

## Idempotence and Recovery

Preserve issue #146/#149 worktrees and runtimes, successful retained evidence,
failed runtimes, historical summaries/reports, and `security-deferral-wip`.
Inspection is read-only; malformed prior reports are not repaired or migrated.
No broad cleanup, stash application/deletion, force push, dependency campaign,
new workload, automatic approval, ready transition, merge, release, deployment,
or repository-setting change is authorized by this addendum.

## Outcomes & Retrospective

The correction implementation and regression cases are prepared for the existing
PR. Syntax checks and the explicitly isolated probe are preliminary evidence
only. Final acceptance remains dependent on exact-head hosted checks, actual
Windows validation, local/remote parity, and final connector review. Draft-to-ready
and merge remain separately owner-authorized actions.

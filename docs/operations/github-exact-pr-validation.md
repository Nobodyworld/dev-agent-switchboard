# GitHub exact pull-request validation

Switchboard's first outbound GitHub adapter lets an authenticated operator
resolve one pull request to its exact current head, create a normal pending
work order, and publish compact evidence to one managed pull-request comment.
It does not add webhooks, polling, workflow dispatch, status checks, automatic
approval, or automatic merge.

## Server credential and permissions

Configure one fine-grained GitHub personal access token in the server process:

```text
SWITCHBOARD_GITHUB_TOKEN=<operator-provisioned secret>
SWITCHBOARD_GITHUB_API_URL=https://api.github.com
SWITCHBOARD_OPERATOR_ID=local-operator
```

`SWITCHBOARD_GITHUB_TOKEN` has no default. The API URL defaults to exactly
`https://api.github.com`, must use HTTPS, and is the only origin accepted by
the fixed-route transport. `SWITCHBOARD_OPERATOR_ID` is a bounded
server-owned audit identity; its default is `local-operator`.

Grant the fine-grained token access only to repositories that the operator
intends to validate, with these minimum repository permissions:

- **Metadata: read**
- **Pull requests: read and write**

The token belongs only in the server's secret environment. It is not a worker
credential and must not be placed in a work-order request, worker JSON,
database display field, comment, log, exception, snapshot, or source file.
The operator configuration snapshot deliberately omits the token and does not
report its value.

Before creating an immutable adapter request, Switchboard resolves the
credential's stable numeric actor ID and actor node ID through the fixed
authenticated-user operation. Those non-secret identifiers are stored only as
server-owned ownership provenance. The bounded adapter API and managed comment
do not expose them.

## Manual authenticated workflow

All three routes use the existing Switchboard admin authentication boundary.
The create request accepts only the repository full name, pull-request number,
and trusted manifest identity:

```http
POST /api/execution/github/pull-requests/validate
Authorization: Bearer <Switchboard admin token>
Content-Type: application/json

{
  "repository_full_name": "Nobodyworld/dev-agent-switchboard",
  "pull_request_number": 125,
  "manifest": {
    "name": "validate-switchboard",
    "version": "1"
  }
}
```

The server checks the existing repository allowlist before contacting GitHub.
It then resolves stable credential-actor, repository, and pull-request
identities, the exact lowercase 40-character head SHA, base provenance, and the
server-owned trusted manifest digest. The same actor, repository, stable PR,
exact head, and manifest identity returns the same adapter request and work
order. A different head or credential actor is a different immutable request.

The created work order remains `pending_approval`. Approve it through the
normal execution API before a worker can receive it; no GitHub state, author,
label, draft flag, or comment grants approval.

Read bounded adapter provenance and lifecycle state with:

```http
GET /api/execution/github/requests/{request_id}
```

The response contains stable GitHub identities, exact tested SHA, manifest
identity and digest, linked work-order/run state, evidence fingerprint when
available, and bounded publication state. It excludes credentials, GitHub
response bodies, commands, full logs, environment values, local paths, and
artifact locations.

After an appropriate terminal run has compact evidence, publish synchronously:

```http
POST /api/execution/github/requests/{request_id}/publish
Authorization: Bearer <Switchboard admin token>
Content-Type: application/json

{}
```

Publication resolves the PR again immediately before writing. If its stable
identity and head still match, the comment records a `current` decision. If
the head moved or became unavailable, the historical tested SHA remains
unchanged and the comment records `stale`; it never claims current success for
the new head. A stable-identity mismatch fails closed without writing to the
unexpected PR identity.

## Managed comment and retry behavior

Each immutable validation request owns this deterministic first-line marker:

```html
<!-- switchboard-validation:v1:<64-lowercase-hex-idempotency-hash> -->
```

The hash binds the configured API base, stable credential actor, repository and
PR identities, exact tested SHA, and trusted manifest name, version, and
digest. Switchboard persists the managed comment ID. Before every update it
retrieves that exact comment through a fixed repository route and verifies the
returned ID, authenticated author ID/node ID, exact repository/PR association,
configured API origin, and exact first-line marker. A deleted, copied,
cross-repository, cross-PR, user-authored, actor-mismatched, or otherwise
unverifiable comment is never patched.

When the persisted ID is absent or invalid, marker text identifies candidates
only. Recovery accepts exactly one actor-owned candidate associated with the
exact PR, ignores user-owned copies, and fails closed on multiple owned
candidates. Comment pagination uses the fixed comments route to obtain bounded
pagination metadata, validates the supplied last-page link against the
configured origin, exact route, and expected query keys, and constructs the
newest-page requests internally. It inspects the last page and at most one
preceding page. If that bounded window cannot prove unique recovery, the
publication remains retryable instead of creating or editing blindly.

The comment contains only the exact tested identity, terminal status and
bounded reason, parsed test/coverage/audit summaries when present, fresh
execution provenance, evidence fingerprint, and current/stale decision. Full
logs and artifact bytes remain local. Remote titles, bodies, users, labels,
branch text, returned URLs, workflow output, and artifacts are not rendered or
executed.

Rate limits and transport failures use bounded reason codes and leave
publication retryable. A retry uses the existing request, work order, terminal
run, and managed-comment identity; it does not create duplicate execution
work.

Publication is serialized per adapter request by a database-backed,
time-bounded lease committed before any remote publication operation. Only the
holder may create or update a comment. A concurrent caller reports
`github_publication_in_progress` and performs no remote write. An interrupted
attempt becomes recoverable after expiry; the next holder performs the same
authoritative marker recovery before considering a create. Conditional
finalization prevents an expired attempt from clearing or overwriting a newer
lease. The internal lease capability is never returned, logged, rendered, or
copied into evidence, work orders, errors, or documentation.

## Local exact-commit prerequisite

The adapter resolves GitHub identity but never synchronizes source. It does not
fetch a target repository, add or alter remotes, write refs, or give GitHub
credentials or general network access to the worker.

The exact resolved head object must already exist in the operator-configured
canonical Git repository when the worker prepares its disposable worktree.
If it is absent, the run fails with
`requested_sha_not_available_locally`, produces no compact success evidence,
keeps the requested SHA in bounded adapter/work-order provenance, and leaves
the canonical repository unchanged. The worker never substitutes the base
SHA, branch tip, or another local commit.

Fork pull requests can be resolved and recorded. They execute successfully
only when the exact fork commit object is already present in the configured
canonical repository. Automatic repository synchronization is deferred to a
separate future issue.

## Transport security boundary

The adapter uses only fixed REST operations for authenticated actor identity,
repository metadata, pull-request metadata, one exact comment read, bounded
newest-page pull-request conversation recovery, one managed-comment create, and
one managed-comment update. It rejects redirects and unexpected origins,
bounds timeouts, response bytes, pagination metadata, decoded strings, JSON
nodes, and collections, and retries safe reads only. Association URLs are
parsed only to compare against the expected fixed route and are never followed.
Authorization values and GitHub response bodies are never copied into bounded
errors.

The adapter does not ingest repository files, pull-request descriptions, issue
comments, workflow logs, check output, GitHub artifacts, or URLs found inside
GitHub responses.

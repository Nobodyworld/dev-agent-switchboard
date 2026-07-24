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
It then resolves stable repository and pull-request identities, the exact
lowercase 40-character head SHA, base provenance, and the server-owned trusted
manifest digest. The same repository, stable PR, exact head, and manifest
identity returns the same adapter request and work order. A different head is
a different request.

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

The hash binds the configured API base, stable repository and PR identities,
exact tested SHA, and trusted manifest name, version, and digest. Switchboard
persists the managed comment ID. Repeated publication updates that persisted
comment instead of creating another one. When a create result is ambiguous,
the adapter lists one bounded page and recovers only the exact marker before
considering another create; the POST itself is never blindly retried.
Unrelated user comments and copied markers cannot displace a persisted managed
comment.

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

The adapter uses only fixed REST operations for repository metadata,
pull-request metadata, one bounded page of pull-request conversation comments,
one managed-comment create, and one managed-comment update. It rejects
redirects and unexpected origins, bounds timeouts, response bytes, decoded
strings, JSON nodes, and collections, and retries safe reads only.
Authorization values and GitHub response bodies are never copied into bounded
errors.

The adapter does not ingest repository files, pull-request descriptions, issue
comments, workflow logs, check output, GitHub artifacts, or URLs found inside
GitHub responses.

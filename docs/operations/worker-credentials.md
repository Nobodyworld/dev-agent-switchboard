# Scoped worker credentials

PUBLIC DEVELOPER PREVIEW — NOT PRODUCTION READY

Administrator authority and worker authority are separate. Configure
`SWITCHBOARD_ADMIN_TOKEN` on the administrator/server process. Deliberately issue
one credential for the exact `worker_id` before launching a worker. The worker
process accepts only `SWITCHBOARD_WORKER_TOKEN`; startup rejects an environment
that also contains the administrator token. Neither secret belongs in JSON,
argv, source control, logs, reports, or evidence.

## Provision and launch

`ExecutionClient` remains the administrator/operator Python client. Its
`issue_worker_credential()` sends one non-retried request to
`POST /api/execution/worker-credentials/{worker_id}/issue` with `{}`. The server
requires a configured administrator credential, reserves an offline worker
identity if absent, and generates a 256-bit random secret plus a separate
128-bit random identifier. It returns `worker_token` exactly once with
`Cache-Control: no-store`. It accepts no caller-authored secret.

An administrator can launch the manual worker from a private Python process:

```python
import os
import subprocess
import sys

from client.python.execution_worker.client import ExecutionClient

with ExecutionClient(
    "http://127.0.0.1:8000",
    "trusted-workstation-1",
    os.environ["SWITCHBOARD_ADMIN_TOKEN"],
) as administrator:
    issued = administrator.issue_worker_credential()
    worker_environment = dict(os.environ)
    worker_environment.pop("SWITCHBOARD_ADMIN_TOKEN", None)
    worker_environment["SWITCHBOARD_WORKER_TOKEN"] = issued.pop("worker_token")
    subprocess.run(
        [sys.executable, "-m", "scripts.local_worker", "--config", "local-worker.json"],
        env=worker_environment,
        check=True,
    )
```

Keep `credential_id` for deliberate management, but never print the issuance
response. An ambiguous issue/rotation response must be investigated by an
administrator; do not automatically retry it. Safe metadata is available from
`GET /api/execution/worker-credentials/{worker_id}` and never includes the secret
or verifier. A previously provisioned worker must be explicitly rotated instead
of issued a second time.

## Rotate and revoke

`rotate_worker_credential(credential_id)` sends the expected current identifier
to `POST .../{worker_id}/rotate`. A single database update replaces the ID and
verifier. There is no overlap or grace period: the old token fails subsequent
requests immediately. Conflicting simultaneous rotations cannot both commit
against the same identifier. Restart the worker deliberately with the new token.

`revoke_worker_credential(credential_id)` sends the same expected identifier to
`POST .../{worker_id}/revoke`. Repeated revocation preserves the original revoked
timestamp and creates no replacement. A stale identifier cannot revoke a newer
credential. Revocation does not fabricate a terminal run or release its lease;
normal server lease expiry/cancellation remains authoritative.

The token format is `swb_w1.<public-id>.<secret>`, with lowercase hex components
of 32 and 64 characters. Verification uses SHA-256 and constant-time comparison;
malformed, ambiguous, wrong, unknown, superseded and revoked bearer credentials
fail with bounded errors. Authentication results are not cached. Work already
authorized before revocation is not retrospectively undone.

## Worker route allowlist

Every path below starts with `/api/execution/worker`. The worker client exposes
only these lifecycle operations and `close()`.

| Method and suffix | Required scope |
|---|---|
| `POST /workers` | Body worker ID matches authenticated worker |
| `POST /workers/{worker_id}/heartbeat` | Path worker ID matches authenticated worker |
| `POST /checkout` | Body worker ID matches authenticated worker |
| `GET /work-orders/{work_order_id}` | Latest assigned run belongs to authenticated worker |
| `GET /runs/{run_id}` | Run belongs to authenticated worker |
| `GET /manifests/{name}/{version}?run_id=...` | Owned run and matching assigned manifest |
| `POST /runs/{run_id}/heartbeat` | Matching body worker ID and authoritative run/lease ownership |
| `POST /runs/{run_id}/reuse-candidate` | Matching body worker ID and authoritative run/lease ownership |
| `POST /runs/{run_id}/complete` | Matching body worker ID and authoritative run/lease ownership |

Path/body/query substitution is rejected. Existing execution routes, catalog,
routing, credential management, approval, queueing, cancellation, GitHub and
operator surfaces remain administrator-only. No execution route is public.
The existing `/health/ready` probe is separate and exposes no credential.

A worker client permanently stops HTTP requests after 401/403. During an active
run, its monitor cancels the process tree through existing containment rules,
retains bounded local failure evidence, and skips completion after authority
loss. It does not recover credentials, fall back to administrator authority or
retry an ambiguous write. Unknown process or source integrity still prevents
unsafe cleanup.

## Persistence and upgrade

Startup adds `execution_worker_credentials` without altering previous tables.
Its worker ID primary key and foreign key enforce one current row per logical
worker. The row contains only public credential ID, SHA-256 verifier, creation,
rotation and revocation timestamps. Rotation overwrites old verifier state;
credential history cannot grow without bound per worker. Prior-schema and
repeated-startup regressions cover this additive migration. Existing workers
have no implicit credential after upgrade and require administrator issuance.
Rolling back the source restores older broad authentication behavior; do not
use rollback as credential recovery or assume it preserves this boundary.

The owned validation lifecycle issues after server health and before worker
launch. It uses an environment allowlist to pass only the worker token to the
child. Shutdown revokes the exact issued identifier while the original runtime
marker and server process ownership remain proven. Unproven revocation fails
the lifecycle and preserves its runtime; it never authorizes unsafe cleanup.
Readiness, approval, fresh/reuse checks, progress, report schema, containment and
retention boundaries remain in effect.

These credentials restrict HTTP authority. They provide no OS, container, VM,
ACL or network isolation and no protection against a hostile same-account
process reading another process's memory. Use only reviewed trusted workloads
in controlled local evaluation. No public exposure or production claim is made.

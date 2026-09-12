# Repository Agent Instructions

These instructions supplement, and do not weaken, any stricter repository rules in `PROJECT_RULESET.md`, `CONTRIBUTING.md`, or scoped `AGENTS.md` files.

## Work-slice workspace hygiene

A work slice is not complete until every temporary workspace created for that slice has been reconciled safely.

### Start-of-slice rules

- Treat the primary checkout and every pre-existing worktree or clone as protected. Do not modify, clean, move, or delete them merely to prepare the slice.
- Run `git worktree list --porcelain` before creating anything. Record the pre-existing paths and refs so they cannot be mistaken for slice-owned workspaces later.
- Use at most one agent-owned temporary worktree for the slice unless concurrent validation genuinely requires more. Reuse it instead of creating serial worktrees.
- Create temporary workspaces outside the primary checkout. Record each owned path, branch or detached ref, starting SHA, and purpose.
- Do not use a stash as a substitute for preserving or reconciling work.

### Safe reconciliation gate

Before removing an agent-owned worktree or disposable clone:

1. Leave that directory so no process is operating from inside it.
2. Record its path, branch or ref, exact `HEAD`, remotes, and `git status --short --untracked-files=all` output.
3. Inventory the ignored paths that removal would delete, using `git status --short --ignored=matching` or an equivalent reviewed report. A clean ordinary status is not proof that ignored content is disposable. Preserve or explicitly classify every ignored environment file, database, user-data path, download, or unknown artifact before removal.
4. Prove the working tree is clean, including no staged, unstaged, or untracked work.
5. Prove the exact `HEAD` is already preserved by an approved destination such as a pushed branch, pull request, merged base, or explicitly retained rescue ref.
6. Confirm the workspace was created by the current slice and is not used by another process.

If any proof is missing, ownership is uncertain, deletion is blocked, ignored content is unexplained, or unique work exists, stop and retain the workspace. Report the blocker; do not force cleanup.

### Prohibited cleanup shortcuts

- Never use `git worktree remove --force`, `git clean -fd`, `git clean -fdx`, `git reset --hard`, or raw directory deletion to make a cleanup check pass.
- Never delete a local or remote branch merely because its worktree was removed. Branch deletion requires separate proof that the work is merged or otherwise preserved and explicit authorization when repository policy requires it.
- Never clear shared npm, pnpm, Yarn, Cargo, Rustup, NuGet, pip, Python, Playwright, browser, or operating-system caches during ordinary slice cleanup.
- Never delete environment files, secrets, local databases, user data, fixtures, or unknown untracked or ignored paths.
- Do not run repository-wide garbage collection or aggressive Git maintenance as an incidental cleanup step.

### Allowed cleanup

- Remove only a slice-owned worktree that passed the reconciliation gate, using normal `git worktree remove <path>` without force.
- After successful removals, run `git worktree prune --dry-run`. Prune stale metadata only when every reported entry is understood and belongs to a workspace already removed safely.
- Generated build outputs inside a retained workspace may be removed only when they are documented as reproducible, ignored by Git, explicitly scoped, and reviewed before deletion. Prefer removing the safely reconciled worktree itself.

### Required completion evidence

The final slice report must include:

- the primary checkout path and confirmation that it was not cleaned or overwritten;
- before-and-after `git worktree list --porcelain` inventories;
- every temporary worktree or clone created by the slice and its disposition;
- the exact SHA and branch, pull request, merged base, or rescue ref preserving its work;
- the ignored-path inventory and classification used before removal;
- cleanup commands and safety checks actually run;
- any retained workspace or storage-heavy path, with the reason it was not removed.

Do not claim the slice complete while an agent-owned temporary workspace remains unexplained.
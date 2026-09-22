# Switchboard: From Agent Coordination Experiment to Public Archive

## An engineering history, October 2025 – September 2026

Switchboard began with a simple problem that felt much larger once I started using multiple AI agents seriously:

> **How do multiple agents know what work exists, what is ready, who owns it, what has already been completed, and what changed while they were working?**

The public GitHub repository was created on **October 15, 2025**.

At the time, the idea was not a local execution platform, a security system, an agent framework, or a generalized automation environment. It was much smaller.

The original README called it:

> **Switchboard — Real-Time Agent Task Switchboard & Live File Host**

That description captured the first version of the project remarkably well.

Switchboard was supposed to provide a live task graph that agents could inspect and modify, dependency-aware checkout so two agents would not accidentally work on the same thing, leases and heartbeats so abandoned work could eventually become available again, WebSocket updates so clients could see state changes immediately, and a simple live-file surface where agents could retrieve the latest instructions or project documents without repeatedly uploading them.

The original explanation for the project was essentially this:

Agents needed a single source of truth while work was happening.

They needed a plan that could change in flight.

They needed a queue that respected dependencies.

They needed ownership.

They needed shared documents.

Switchboard was supposed to provide those things with minimal overhead.

That was the first Switchboard.

And, in retrospect, it was probably the cleanest definition the project ever had.

---

## 1. The original idea

The earliest version of Switchboard contained concepts that would remain relevant throughout the entire life of the project:

**Task. Agent. Dependency. Lease. Heartbeat. Plan.**

An agent could register itself. Tasks could depend on other tasks. An agent could check out available work. A lease prevented another agent from taking the same work simultaneously. A heartbeat extended ownership. An agent could complete or abandon a task. Changes could propagate through WebSockets.

There was also a lightweight file-sharing layer. An agent could publish a document and another agent could retrieve the current version through a predictable URL.

The architecture was deliberately ordinary: FastAPI, SQLAlchemy, SQLite, a Python client, a lightweight browser interface, and Docker packaging.

There was nothing especially exotic about the implementation.

The interesting part was the workflow.

Switchboard assumed that software development was moving toward a world in which one person might supervise multiple AI workers concurrently. The hard problem would therefore stop being simply:

> “Can the model write the code?”

and increasingly become:

> “How do I coordinate all of these workers without losing control of the project?”

That distinction became much more important over the following year.

---

## 2. The first expansion

Development moved extremely quickly.

At the time of this archival review, the repository history contained **122 pull requests**. Of those, **83 were opened during October 2025 alone**.

That number explains a great deal about Switchboard.

The early project was being built while its architecture was still being discovered.

[Pull request #1](https://github.com/Nobodyworld/dev-agent-switchboard/pull/1), opened on October 15, added an OpenAPI narrative. Within days, Switchboard was receiving CI, linting, task persistence fixes, agent registration fixes, task deletion behavior, plan versioning, WebSocket improvements, ETags, environment-driven configuration, rate limiting, instrumentation, Playwright coverage, client refactors, additional CLI behavior, documentation systems, and developer tooling.

By October 24, [PR #72](https://github.com/Nobodyworld/dev-agent-switchboard/pull/72) was already performing a substantial architectural pass: adding orchestration router interfaces, service abstractions, health probes, local runner behavior, and a documentation hub.

Four days later, [PR #83](https://github.com/Nobodyworld/dev-agent-switchboard/pull/83) changed 49 files and expanded Switchboard into an observability and extension ecosystem.

The project gained extension contracts, observability hooks, metrics, health aggregation, scaffolding, stewardship concepts, more developer utilities, richer documentation, and increasingly sophisticated test and validation infrastructure.

Most of these changes were individually reasonable.

Many were useful.

Many passed their tests.

But something important was happening underneath them.

Switchboard was becoming increasingly good at supporting the development of Switchboard.

That is not quite the same thing as becoming a better solution to its original problem.

The project was becoming easier to inspect, extend, test, monitor, document, and govern—but also larger and harder to define.

The original five-word explanation—

**real-time agent task switchboard**

—was slowly turning into a paragraph.

---

## 3. The first major lesson: technical success is not architectural convergence

It would be inaccurate to describe all of these refactors as technical failures.

Most were not.

A great deal of the code worked.

Tests passed.

Interfaces improved.

Coverage increased.

Operational behavior became safer.

The problem was more subtle:

> **The refactors repeatedly improved the implementation without permanently settling what the product itself was supposed to be.**

That distinction became one of the defining lessons of the repository.

Switchboard went through repeated cycles of stabilization, modernization, stewardship, observability improvements, interface cleanup, release preparation, documentation reconciliation, security hardening, and architectural cleanup.

Some changes even appeared more than once in the pull-request history under nearly identical titles: repeated Makefile work, repeated client packaging, repeated ETag work, repeated WebSocket work, duplicate orchestration-router work, and several rounds of public-release documentation alignment.

This is not presented as an indictment of the development process.

It is evidence of experimentation.

Switchboard was being used as a place to discover what agent infrastructure should look like at almost exactly the same time that the broader software industry was trying to answer the same question.

---

## 4. Industry context: the problem was becoming real

It is important to be precise here.

Switchboard did **not** invent multi-agent systems.

Before this repository existed, Anthropic had already publicly described an orchestrator-worker multi-agent architecture for Claude Research. On **June 13, 2025**, Anthropic published [“How we built our multi-agent research system”](https://www.anthropic.com/engineering/multi-agent-research-system), describing a lead agent that delegated work to parallel subagents and discussing coordination, reliability, persistence, and the difficulty of managing multi-agent work.

So this history should not be read as a claim that the basic idea of multiple cooperating agents originated with Switchboard.

What is interesting is what happened **after October 15, 2025**.

The product problems that had motivated Switchboard began appearing very visibly in major commercial developer tools.

### GitHub Agent HQ

On **October 28, 2025—thirteen days after the Switchboard repository was created—GitHub announced [Agent HQ](https://github.blog/news-insights/company-news/welcome-home-agents/)**.

GitHub described a unified workflow for orchestrating agents, a **mission control** for assigning, steering, and tracking the work of multiple agents, identity controls, and an agent control plane for governing access and behavior.

Thirteen days is obviously not enough time to suggest that GitHub saw Switchboard and built Agent HQ in response.

There is no evidence of that, and this history makes no such claim.

The significance is different.

Independent efforts had identified essentially the same emerging problem:

> **Once agents become capable enough, the bottleneck becomes coordination, supervision, ownership, context, and control.**

### OpenAI Codex app

On **February 2, 2026**, OpenAI introduced the [Codex app](https://openai.com/index/introducing-the-codex-app/).

OpenAI described it as an interface for managing multiple coding agents at once, running work in parallel, collaborating with agents over long-running tasks, and isolating concurrent changes with Git worktrees.

Two days later, GitHub expanded Agent HQ so users could run [Claude and Codex alongside GitHub Copilot](https://github.blog/news-insights/company-news/pick-your-agent-use-claude-and-codex-on-agent-hq/) while keeping context, history, and review attached to GitHub and the editor.

By early 2026, concepts that had seemed unusual when Switchboard started were becoming normal product vocabulary:

**mission control, agent orchestration, parallel sessions, worktrees, agent identity, long-running work, specialized agents, supervision, and shared state.**

### Google Antigravity

At Google I/O on **May 19, 2026**, Google announced [Antigravity 2.0](https://blog.google/innovation-and-ai/technology/developers-tools/google-io-2026-developer-highlights/), describing it as a central home for agent interaction where developers could orchestrate multiple agents in parallel.

Google also highlighted persistent isolated environments for managed agents, and its developer keynote described cross-platform terminal sandboxing, credential masking, and hardened Git policies around agentic development.

### Microsoft and parallel agent sessions

At Microsoft Build on **June 2, 2026**, Microsoft described the GitHub Copilot desktop application as a native environment for orchestrating multiple agent sessions in parallel while using Git worktrees to keep each session’s changes separated. See [Microsoft Build 2026: Be yourself at work](https://blogs.microsoft.com/blog/2026/06/02/microsoft-build-2026-be-yourself-at-work/).

### OpenAI Agents API

On **September 10, 2026**, OpenAI introduced the [Agents API](https://openai.com/index/introducing-the-agents-api/), describing infrastructure for long-running cloud agents whose harness manages context, tools, execution environments, persistence, and subagent coordination.

Again, none of this demonstrates influence from Switchboard.

What it demonstrates is that the original problem was real.

The industry moved toward exactly the class of questions that had motivated the experiment:

- How do you supervise many agents?
- How do you isolate concurrent work?
- How do you route work?
- How do you preserve state?
- How do you control authority?
- How do you know what actually happened?

In that sense, Switchboard was pointed in a meaningful direction very early.

But being early to a problem does not mean the first implementation should become the permanent solution.

That distinction eventually became critical.

---

## 5. Repository-aware connectivity changed the coordination frontier

Another change happened outside the Switchboard codebase, but it materially changed how useful the original architecture felt in my own development workflow.

When Switchboard began, my practical experience with LLM-assisted development was much more **repository-bound**.

A model or coding session generally operated inside one repository and one body of context. If another repository mattered, I had to move that context manually: open another session, copy status between conversations, upload or paste files, relay decisions, or build explicit infrastructure that gave otherwise separated agents a shared view of the work.

Under those conditions, the original Switchboard architecture made intuitive sense.

If the agents themselves could not naturally see one another's repository state, Switchboard could provide the missing common layer:

- one task graph;
- one dependency model;
- one ownership/lease system;
- one place for shared live documents;
- one view of what changed while another agent was working.

That was a real constraint, not merely an architectural preference.

Later, **repository-aware GitHub connectivity became available in my ChatGPT workflow**, and that changed the frontier substantially.

A single conversation could increasingly inspect multiple repositories through GitHub itself: issues, pull requests, branches, commits, files, reviews, workflow runs, and repository history. The same coordinating conversation could perform supported GitHub operations remotely, while local Codex or PowerShell could be reserved for the comparatively small set of tasks that actually required a machine checkout, dependency installation, runtime execution, native UI inspection, or other local state.

That did not make coordination unnecessary.

It changed **where coordination needed to live**.

Some of the global awareness that Switchboard had been built to manufacture inside its own application layer could now come from the external model-and-connector layer. Cross-repository reasoning no longer required every participating repository or agent to publish all of its state into one custom service before a coordinator could understand what was happening.

That changed the economics of the architecture.

The original Switchboard had been valuable partly because agent contexts were effectively islands. Once a coordinating model could inspect GitHub state across those islands directly, a thick central coordination application became less necessary for many of the jobs I originally wanted Switchboard to perform.

At the same time, one class of work **did not** become easier simply because GitHub became visible to the model:

trusted local execution.

A GitHub connector can understand repository state and perform repository operations. It does not, by itself, safely execute a deterministic validation workload on a private Windows machine, isolate that workload from unrelated files and credentials, control its process tree, retain full local artifacts, or prove cleanup afterward.

That distinction clarified the eventual architectural split.

The coordination side could become thinner and more context-aware:

> understand repositories, tasks, dependencies, agents, capabilities, and handoffs.

The local execution side could become narrower and more security-focused:

> accept a typed approved request, execute only reviewed capabilities against exact source, isolate the operation, and return bounded evidence.

In retrospect, this was another reason repeated attempts to make Switchboard itself the permanent answer felt increasingly strained.

The environment around the project had changed.

Some of the problem Switchboard was created to solve had moved upward into repository-aware model tooling, while the hardest remaining problem had moved downward into operating-system execution and isolation.

Those two directions did not need another shared application layer.

They needed a clean boundary.

---

## 6. 2026: Switchboard changes identity

The largest change in the project’s history happened during the summer of 2026.

By then, Switchboard was no longer merely being asked to coordinate agents.

I wanted it to help answer another problem that had become increasingly frustrating in AI-assisted development:

> **Why should an expensive, intelligent coding agent spend its time performing deterministic work that a local machine could perform more cheaply and predictably?**

Tests.

Linters.

Type checks.

Security scans.

Builds.

Known validation sequences.

Exact repository verification.

These operations often require compute and tooling, but not another round of model reasoning.

This led to [issue #111](https://github.com/Nobodyworld/dev-agent-switchboard/issues/111), opened on **July 12, 2026**.

Its goal was to evolve Switchboard into a **cost-aware local execution broker**.

This was the decisive pivot.

[PR #115](https://github.com/Nobodyworld/dev-agent-switchboard/pull/115), also opened July 12, formally locked the first execution-broker architecture.

The new model introduced another set of primitives alongside the original task system:

**WorkOrder. Worker. CommandManifest. ExecutionRun. Evidence.**

A work order described deterministic execution against an exact repository revision.

A worker pulled approved work.

A command manifest defined reviewed executable behavior.

An execution run recorded an attempt.

Evidence recorded what had happened.

Arbitrary remote shell commands were explicitly prohibited.

Repositories were supposed to remain read-only.

Workers communicated outbound rather than exposing general workstation-control ports.

Execution had to be tied to exact commit SHAs.

Approval and capabilities had to match before work could run.

These were sensible security decisions.

They were also the beginning of the second Switchboard.

---

## 7. Two products begin living in one repository

The original Switchboard model was:

> **Task → Agent → Lease → Dependency → Plan**

The execution broker’s model was:

> **WorkOrder → Worker → Manifest → ExecutionRun → Evidence**

We explicitly kept those domain models separate because combining them would have been conceptually wrong.

That decision was correct.

It was also a warning.

The systems were related, but they were no longer the same system.

The original Switchboard answered:

> What should be worked on, what is ready, and who owns it?

The execution broker answered:

> May this exact deterministic operation run on this machine, against this exact source revision, under these restrictions, and what evidence proves what happened?

Those are both valuable questions.

But they have different threat models.

Different lifecycle semantics.

Different failure modes.

Different security boundaries.

Different implementation concerns.

Instead of recognizing that divergence as a potential repository boundary, I kept extending Switchboard.

---

## 8. The execution-broker buildout

The work after PR #115 was much more structured than the early 2025 period.

The project had learned a great deal about planning and validation by then.

Each major capability was generally isolated into an issue, branch, ExecPlan, pull request, local validation cycle, hosted validation cycle, connector review, and separately authorized merge.

Technically, this period produced some of the strongest work in the repository.

- [PR #116](https://github.com/Nobodyworld/dev-agent-switchboard/pull/116) added the Phase 1 execution-plane contracts.
- [PR #119](https://github.com/Nobodyworld/dev-agent-switchboard/pull/119) added the pull-based local worker.
- [PR #120](https://github.com/Nobodyworld/dev-agent-switchboard/pull/120) added exact-SHA validation evidence.
- [PR #125](https://github.com/Nobodyworld/dev-agent-switchboard/pull/125) integrated exact GitHub pull-request resolution.
- [PR #129](https://github.com/Nobodyworld/dev-agent-switchboard/pull/129) added exact evidence reuse.
- [PR #135](https://github.com/Nobodyworld/dev-agent-switchboard/pull/135) added local worker routing.
- [PR #137](https://github.com/Nobodyworld/dev-agent-switchboard/pull/137) added the operator validation command center.
- [PR #139](https://github.com/Nobodyworld/dev-agent-switchboard/pull/139) and [PR #145](https://github.com/Nobodyworld/dev-agent-switchboard/pull/145) expanded trusted workload support and built the multi-repository workload factory.

The system gradually became capable of taking an exact Git revision, resolving a reviewed manifest, routing the request to a local worker, executing deterministic validation, retaining full evidence locally, returning only bounded evidence remotely, and—in tightly defined cases—proving that previously retained evidence could be reused without repeating the work.

That is a legitimate system.

It works.

But the amount of machinery required to make it trustworthy kept revealing another missing boundary.

---

## 9. The failed acceptance attempts

One of the most useful chapters in Switchboard’s history was also one of the most frustrating.

[Issue #146](https://github.com/Nobodyworld/dev-agent-switchboard/issues/146) attempted to prove the merged workload factory against a real immutable Switchboard target.

It failed.

Then it failed again.

Then it failed a third time.

Those failures were preserved rather than rewritten into a cleaner story.

The first attempt successfully executed all seven reviewed validation steps, but the final completion boundary rejected serialized Windows-relative paths because the sanitization policy interpreted them incorrectly.

The second attempt exposed test-harness behavior under combined load: cancellation timing assumptions broke and high-frequency heartbeat traffic triggered rate limiting.

The third attempt progressed through much of the deterministic validation flow but again failed at the completion boundary when safe-output policy interpreted compact diagnostic text as sensitive local state.

None of those attempts was declared successful simply because most of the work had passed.

The environments and evidence were retained.

The target was eventually classified as **TARGET-STATE-BLOCKED** rather than retroactively massaged into a success.

That experience materially improved the project.

It also showed how much responsibility the repository had accumulated.

The system was no longer simply coordinating agents.

It was responsible for source identity, local process execution, Windows behavior, path containment, artifact policy, result serialization, rate limiting, evidence retention, exact reuse, network assumptions, cleanup semantics, and public reporting.

A failure in any one of those layers could invalidate an otherwise successful run.

---

## 10. The first authoritative proof

[Issue #149](https://github.com/Nobodyworld/dev-agent-switchboard/issues/149) eventually produced the first fully authoritative operator-controlled proof of the newer execution architecture.

A fresh validation completed successfully.

A separate equivalent request then reused the exact evidence on the same worker.

The reuse path reverified the worker identity, retained marker, evidence fingerprint, containment, artifact size, and hashes.

It repeated zero deterministic validation steps.

It did not silently fall back to fresh execution.

That was an important milestone.

Switchboard had demonstrated that the execution-broker concept itself was viable.

But rather than ending the architecture work, success exposed the next layer of operational complexity.

---

## 11. Another round of refactoring: operating the system safely

[PR #152](https://github.com/Nobodyworld/dev-agent-switchboard/pull/152) added an owned validation lifecycle.

The goal was no longer simply to provide the underlying endpoints.

The operator needed a supported way to perform the whole process safely:

1. preflight the environment;
2. create isolated runtime state;
3. start the server;
4. start the worker;
5. approve the work;
6. observe the run;
7. verify the evidence;
8. prove cleanup;
9. produce a bounded report.

That required more work around runtime ownership, marker files, process identity, port handling, safe shutdown, stale state, path containment, junctions, reparse points, failure preservation, and report schemas.

Then [PR #158](https://github.com/Nobodyworld/dev-agent-switchboard/pull/158) added another layer:

**read-only readiness and bounded live progress.**

The lifecycle now needed a safe preflight mode that could answer whether execution was likely to work without creating runtime state or accidentally implying authorization.

Progress reporting needed to distinguish queuing from actual execution.

Human output and machine JSON needed separate channels.

Diagnostics needed to remain actionable without leaking private paths or credentials.

Again, these were legitimate improvements.

Again, they solved real problems.

And again, the system became larger.

---

## 12. The credential problem

Eventually the security model exposed another fundamental weakness.

The outbound worker was still carrying the administrator credential.

That meant a component intended only to perform a narrow execution lifecycle possessed authority much broader than its role required.

[Issue #159](https://github.com/Nobodyworld/dev-agent-switchboard/issues/159) and [PR #160](https://github.com/Nobodyworld/dev-agent-switchboard/pull/160) addressed this.

The result was one of the clearest security improvements in Switchboard’s later history.

Workers received credentials scoped to exactly one worker identity.

Administrator authority and worker authority were separated.

Credential secrets were generated server-side.

Only non-recoverable verifier state was persisted.

Rotation invalidated previous credentials.

Revocation became explicit and immediate for subsequent requests.

Worker routes were narrowed to the lifecycle operations the worker actually needed.

The worker client itself was split so normal worker code no longer even exposed administrator operations such as creating, approving, or queueing work.

The accepted lifecycle launched the server with administrator authority while launching the worker with only its worker-scoped token.

Real tests verified that distinction.

PR #160 ultimately squash-merged into `main` as:

`c04756ecfb3e58b74f4f1ad87f7eb90a5208c737`

Resulting-main CI and Workload acceptance both passed.

That is where an important question became unavoidable.

---

## 13. What was still missing?

After all of that work, Switchboard still could not truthfully claim that arbitrary or insufficiently trusted target code was safely isolated from the host machine.

The repository’s own documentation was explicit about this.

Read-only repository policy was cooperative policy plus integrity checking.

Process-tree containment was useful.

Exact worktrees were useful.

Scoped worker credentials were useful.

None of those things was an operating-system security boundary.

The next logical project was therefore **OS-backed worker isolation**.

A separate Windows identity.

ACL boundaries.

Restricted filesystem visibility.

Potential container or VM boundaries.

Network restrictions.

Credential isolation.

Adversarial escape tests.

In other words:

another substantial security subsystem.

That was the moment I stopped asking:

> “How do I refactor Switchboard so it can support this?”

and started asking:

> **“Why am I still forcing all of these responsibilities into Switchboard?”**

---

## 14. The refactor treadmill

Looking back, there is a recognizable pattern.

Each time Switchboard reached a point where it appeared nearly complete, using it seriously exposed another missing responsibility.

Coordination required persistence.

Persistence required lifecycle correctness.

Lifecycle correctness required observability.

Observability encouraged an extension system.

Public release preparation required governance and security hardening.

Execution required separate work-order semantics.

Execution required evidence.

Evidence created the opportunity for reuse.

Reuse required stronger identity and retained-state verification.

Multiple workers introduced routing.

Routing needed an operator interface.

External repositories required a workload factory.

Operating the factory required a lifecycle.

The lifecycle required readiness and progress.

The worker required scoped credentials.

Scoped credentials finally exposed the need for real operating-system isolation.

Every step made sense locally.

Taken together, they describe a system whose boundary kept moving outward.

That is the key distinction between ordinary software evolution and architectural drift.

A mature product can certainly acquire features.

But its central sentence should become clearer over time.

Switchboard’s central sentence became longer.

By the end, the project could truthfully be described as an agent task coordinator, lease manager, live-file server, WebSocket synchronization service, local execution broker, exact-SHA validator, evidence system, evidence-reuse system, worker router, quota system, GitHub integration, workload factory, validation command center, operator lifecycle, readiness diagnostic system, and credential authority.

Those components all relate to agent-assisted software development.

That does not mean they belong in the same product.

---

## 15. The most important failed refactor

The biggest failed refactor was therefore not one particular pull request.

It was the repeated attempt to discover **one architecture that could make all of Switchboard’s responsibilities feel like one thing**.

That architecture never fully appeared.

There were technically successful refactors.

There were successful security fixes.

There were successful test suites.

There were successful acceptance runs.

But the repository repeatedly needed another conceptual layer before it felt complete.

The code kept passing.

The product boundary kept failing.

That is a different kind of failure, and it is worth preserving because it is much harder to detect.

---

## 16. What Switchboard got right

Preparing Switchboard for archival should not erase what worked.

The project developed several ideas that remain worth carrying forward.

It proved the usefulness of explicit task ownership and leases.

It reinforced the importance of exact source identity.

It demonstrated that deterministic work should be represented as reviewed capabilities rather than arbitrary model-generated shell commands.

It developed a strong distinction between full local evidence and compact remote evidence.

It showed that reuse can be safe only when the underlying retained evidence is reverified rather than trusted because a database row says it exists.

It reinforced outbound workers as a safer architecture than casually exposing a developer machine to inbound automation.

It showed the value of explicit human approval at meaningful trust boundaries.

It eventually separated worker credentials from administrator credentials.

And, perhaps most importantly, it produced a large body of concrete failure evidence about what happens when agent infrastructure crosses boundaries between coordination, execution, security, persistence, and local-machine control.

That knowledge is more valuable than pretending the architecture emerged fully formed.

---

## 17. Why archive instead of refactor again

There is an obvious alternative:

Refactor Switchboard one more time.

Extract a package.

Rewrite the execution layer.

Replace the task subsystem.

Add interfaces.

Introduce an internal service boundary.

Move OS isolation behind an adapter.

Preserve compatibility.

Migrate the existing APIs.

Update the dashboard.

Rewrite another round of documentation.

Add another ExecPlan.

Prove another migration.

The repository is technically capable of surviving that work.

That is no longer enough reason to do it.

Every hour spent preserving Switchboard’s accumulated compatibility is an hour not spent designing successor systems around the boundaries that the experiment already revealed.

A fresh system does not need to pretend that agent coordination and local execution are the same domain.

A fresh system does not need to preserve APIs created before the execution broker existed.

It does not need to carry an extension framework merely because the original coordinator acquired one.

It does not need to make old dashboards understand new isolation primitives.

It does not need another round of language explaining why one subsystem is conceptually separate from another subsystem inside the same application.

Starting over is sometimes irresponsible.

This is not one of those cases.

Switchboard has generated enough evidence to justify the reset.

---

## 18. The successor architecture

The strongest lesson from Switchboard is that its two most valuable responsibilities should become **two independently useful components**.

### Agent Coordinator

The first successor is an **Agent Coordinator**.

Its world consists of:

**identity, tasks, dependencies, ownership, leases, capabilities, handoffs, lifecycle state, and evidence references.**

It answers:

- What work exists?
- What work is ready?
- Who owns it?
- Which agent can perform it?
- What depends on it?
- What happened?

It should not know how to create Windows processes.

It should not manage worktrees.

It should not contain package-manager logic.

It should not implement filesystem isolation.

It should not become a shell.

### Trusted Local Executor

The second successor is a **Trusted Local Executor**.

Its world consists of:

**exact source identity, reviewed operations, worker identity, credentials, isolation, execution, cleanup, artifacts, and bounded evidence.**

It answers:

- Is this request allowed?
- Is this exact source available?
- Which reviewed operation does the request identify?
- Is this machine capable of executing it safely?
- Can it be isolated correctly?
- What happened?
- What evidence proves the result?

The executor should remain independently useful.

The coordinator might call it.

A CLI could call it.

A GitHub integration could call it.

Another agent platform could call it.

A future typed transport could call it.

None of those should require the executor to become an agent coordinator itself.

Between them, if necessary, there can be a deliberately small shared protocol defining identity, capabilities, correlation IDs, lifecycle states, exact source references, approvals, and evidence references.

That is a much cleaner boundary than another internal Switchboard refactor.

---

## 19. Why this still matters

One reason I am comfortable preparing Switchboard for archival is that the experiment’s original assumptions no longer need to be defended.

The industry has moved decisively toward multi-agent supervision and explicit agent infrastructure.

GitHub now talks about mission control, agent identity, and an agent control plane.

OpenAI built a Codex interface around multiple parallel agents and isolated worktrees.

Google built a central multi-agent development environment and explicitly discusses sandboxing, credential protection, and hardened Git policy.

Microsoft is shipping parallel agent sessions separated through Git worktrees.

OpenAI’s Agents API now treats the harness, execution environment, long-running state, and subagent coordination themselves as infrastructure.

Switchboard does not need to become a commercial competitor to any of those systems to have been worthwhile.

Its value is partly historical.

It documents one developer independently encountering many of the same problems and trying to solve them in public while the category itself was being formed.

---

## 20. The decision: turn Switchboard into a public archive

The appropriate final state for `dev-agent-switchboard` is not deletion.

It is preservation.

The repository is being prepared to become a **public archived reference implementation**.

Its final public posture should be impossible to misunderstand:

> **ARCHIVED REFERENCE IMPLEMENTATION — NOT PRODUCTION READY**

The archive should preserve the code, issues, pull requests, ExecPlans, tests, acceptance failures, security corrections, architectural pivots, and final working state.

The failed acceptance history should remain part of the story.

The historical documents should not be rewritten to make the path look more linear than it was.

The 2025 task coordinator should remain visible.

The 2026 execution-broker pivot should remain visible.

The transition from administrator credentials to scoped worker credentials should remain visible.

The absence of OS-backed isolation should remain explicit.

That is what makes the archive valuable.

A cleaned-up repository containing only the final architecture would hide the most useful information:

> **how the architecture was discovered.**

Before GitHub’s actual archive switch is enabled, the remaining public-facing housekeeping should be reconciled deliberately. Current status documentation should be brought to the final merged state. The long-lived roadmap epic should receive a closing retrospective. Any remaining maintenance pull request should be accepted or closed deliberately. The README should explain the archived posture and, once they exist publicly, point readers toward successor projects.

Then development should stop.

No “vNext” branch inside this repository.

No OS-isolation subsystem bolted onto the current execution broker.

No new transport layer added merely because an old roadmap anticipated it.

No attempt to turn historical architecture into permanent architecture.

Switchboard should be allowed to finish.

---

## 21. What the archive represents

I do not view this outcome as a failed application.

I view Switchboard as an unusually long-lived prototype that answered progressively harder questions until it finally answered the question that mattered most:

> **Where should the boundary be?**

The answer was not inside another abstraction layer.

The answer was between systems.

Agent coordination is one system.

Trusted local execution is another.

Their protocol can be shared.

Their implementations should not have to be.

That conclusion took roughly a year, more than a hundred pull requests, multiple architectural generations, several failed real acceptance attempts, extensive test infrastructure, and repeated security hardening to reach.

That is precisely why the repository is worth keeping public.

It records the evolution from a small task switchboard, through the early multi-agent tooling era, through an ambitious local execution broker, to a clearer understanding of the infrastructure that agentic software actually requires.

Switchboard began because I needed a way for agents to know:

> **What needs to be done, and who is doing it?**

It eventually grew into a system trying to answer:

> **What may execute, where may it execute, under whose authority, against exactly what source, and what evidence proves the result?**

Both questions were worth asking.

Trying to make one application permanently own both answers was the mistake.

The archive preserves that lesson.

And whatever succeeds Switchboard can begin with it.

---

## Primary project references

The historical narrative above is grounded primarily in the repository’s own immutable history:

- [Original repository](https://github.com/Nobodyworld/dev-agent-switchboard)
- [Issue #111 — execution-broker roadmap](https://github.com/Nobodyworld/dev-agent-switchboard/issues/111)
- [PR #115 — Phase 1 local execution-broker architecture](https://github.com/Nobodyworld/dev-agent-switchboard/pull/115)
- [Issue #146 — failed acceptance and reconciliation](https://github.com/Nobodyworld/dev-agent-switchboard/issues/146)
- [Issue #149 — authoritative fresh execution and exact reuse](https://github.com/Nobodyworld/dev-agent-switchboard/issues/149)
- [PR #152 — owned validation lifecycle](https://github.com/Nobodyworld/dev-agent-switchboard/pull/152)
- [PR #158 — readiness and bounded progress](https://github.com/Nobodyworld/dev-agent-switchboard/pull/158)
- [Issue #159 — scoped worker identity and revocation](https://github.com/Nobodyworld/dev-agent-switchboard/issues/159)
- [PR #160 — scoped worker identity implementation](https://github.com/Nobodyworld/dev-agent-switchboard/pull/160)

Industry references are included for historical context only. Similarity of problems, terminology, or later products is **not** evidence that another company derived its work from Switchboard.

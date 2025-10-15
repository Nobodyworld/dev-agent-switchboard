
# Codex Execution Plans (ExecPlans)

This file defines the single‑fence ExecPlan format that agents must use. When the content of a plan lives in its own `.md` file, omit the surrounding ``` fences as specified below.

## How to use

- Read this file in full before writing or following an ExecPlan.
- Keep plans **self‑contained**, **novice‑guiding**, **outcome‑focused**, **living**.
- Record **Progress**, **Surprises & Discoveries**, **Decision Log**, **Outcomes & Retrospective**.

## ExecPlan Skeleton (copy below into a plan file)

```md
# <Short, action‑oriented description>

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This repository implements the Switchboard service. This plan must be maintained in accordance with `.agent/PLANS.md`.

## Purpose / Big Picture

Explain the user‑visible behavior to be enabled and how to observe it.

## Progress

- [ ] Initial state.

## Surprises & Discoveries

- Observation: ...
  Evidence: ...

## Decision Log

- Decision: ...
  Rationale: ...
  Date/Author: ...

## Outcomes & Retrospective

Summarize outcomes vs. purpose.

## Context and Orientation

Name key files and modules with full paths; assume the reader is new to the repo.

## Plan of Work

Describe concrete edits and additions, with file paths and functions.

## Concrete Steps

Exact commands to run, with expected outputs (short transcripts).

## Validation and Acceptance

Describe how to verify behavior end‑to‑end.

## Idempotence and Recovery

How to retry safely or roll back.

## Artifacts and Notes

Short diffs, logs, or transcripts that prove success.

## Interfaces and Dependencies

Name libraries and module interfaces (function names, types) that must exist.
```

---
name: review
description: "Review local GpuGate changes before committing or opening a PR and produce a structured plain-English report of verified bugs and useful small improvements. Use for a local pre-commit review or the review skill; use grill for a broader risk audit."
---

# Review

This skill belongs to the GpuGate repository. Resolve the repository root from this skill's location (`.agents/skills/review/`), rather than assuming the current directory is the root. Follow this repository's instructions and inspect its current code; do not audit other projects.

Find actionable problems before a commit or PR using accepted project requirements and current code. This is a manual local review, not an automatic Git hook or a guarantee the remote reviewer will agree.

## Scope and investigation

1. Read applicable AGENTS.md and LOCAL.md, then project docs. Check freshness without modifying snapshots. Distinguish accepted requirements from proposals and report unavailable references.
2. Inspect Git status. By default review all uncommitted work together: staged changes, unstaged changes and untracked source/tests/configuration. Inspect current files as well as diffs; ignore generated artifacts and credential files.
3. Honour an explicit base branch or selection. If no uncommitted work exists, review the branch against the locally available main/master merge base. State the exact baseline and scope. Do not fetch, commit or change branches; if no baseline is available, ask for one rather than inventing a diff.
4. Trace changed behaviour through relevant callers, validators, helpers and tests. Nearby existing code is evidence, not an invitation to audit unrelated features.
5. Run focused existing deterministic checks when they materially verify a suspected issue. Use installed tools; avoid dependency edits or installations just for routine review. Reproductions use temporary state, synthetic data and fakes. Do not run live GPU, model, game or network acceptance checks. Report exact commands/results and execution limits.

Follow repository review priorities. In GpuGate, focus on gaming priority, shared-Ollama ownership, durable admission/queue/deadlines, cancellation/recovery and role/private-data protection. Do not demand an unimplemented adapter or unapproved threshold as a current contract.

Inspect relationships between fields and components, not only individual types/ranges: omitted primary observations, credentials collapsing separate roles, or listener collisions despite different address spellings. When changed code parses or normalizes input, investigate equivalent valid and malformed forms against the relevant standard. Check whether a later guard catches the problem. Compare declared Python support and CI with the local runtime when classification depends on library versions. These are investigation prompts, not mandatory new features or an endless edge-case checklist.

Before reporting a finding, establish a realistic trigger, verify the path in current code/tests, and rule out intentional restrictions or later guards. Keep one finding per root cause. No findings is a valid result. Avoid inflating severity or re-reporting fixed issues from old screenshots/commits.

## Report format

Return the complete Markdown report in chat and save it as `reports/<YYYYMMDD-HHMMSS>-gpugate-review.md` under the repository root. Use UTC for the timestamp (`%Y%m%d-%H%M%S`), for example `20261016-035332-gpugate-review.md`. If a name already exists, append a numeric suffix before the extension rather than overwriting it. Create `reports/` if needed; Git ignores this directory. Apply this naming convention to new reports; leave existing reports unchanged. Do not stage or commit generated output. Link the saved report using its resolved absolute path.

Only final Markdown reports belong in `reports/`. Put report-generation scripts, reproduction scripts, captured output and other intermediates in a task-owned temporary directory outside `reports/`, using `tempfile.TemporaryDirectory` or equivalent cleanup with `try/finally`. Clean up task-created temporary files on success or failure, and check for remaining task-owned intermediates before the final response. Never delete unrelated or pre-existing files. Include reproduction steps, essential code and relevant results in the Markdown report so it does not depend on temporary files or link to deleted helpers.

# Local Review — repository/branch

## Overview

State scope, baseline/HEAD, working-tree state and documentation freshness. Give counts by P0/P1/P2/P3 and the outcome: confirmed blockers, smaller findings or no findings. Passing tests alone do not justify approval.

## Findings at a glance

| ID | Priority | Finding | Source | Evidence |
| --- | --- | --- | --- | --- |

Use repository severity definitions (P0 critical, P1 major, P2 minor, P3 optional nit). Source links point to current relevant lines. Evidence identifies a reproduction, failing check or verified path; mark P3 as optional.

## Findings

Use `### R1 — [P2] Plain-English title`, a current clickable source-line link and these separate short paragraphs:

**High level:** Simple explanation, preferably with an accurate everyday analogy.

**Issue:** What current code does incorrectly and the condition that triggers it.

**Impact:** Practical consequence; distinguish a present failure from a consequence that applies only when future components exist.

**Suggested fix:** Smallest actionable change.

**Rationale:** Why the fix prevents the consequence.

**Evidence:** Relevant lines, tests or safe reproduction/result. Keep secret values out of reports.

A tiny text or Mermaid diagram may follow when helpful and supported; label it current or suggested. Respect required external output schemas by putting explanations inside permitted fields.

## Validation and limits

List actual checks/results and material untested behaviour or missing evidence. Simulated tests are not real-host proof. Explicitly say when no findings were verified.

## Recommended next steps

Order worthwhile fixes. Do not fix code, edit tests, stage, commit, push, resolve PR threads or send messages as part of this skill. If fixes are requested afterward, follow the project's TDD/test-approval workflow. Existing approval remains valid for the same approved cases.

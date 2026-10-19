---
name: grill
description: "Perform a broad, adversarial local GpuGate code audit and write a prioritised report of bugs, conditional risks, verification gaps and optional improvements. Use when asked to grill code or for an aggressive audit beyond a normal change review."
---

# Grill

This skill belongs to the GpuGate repository. Resolve the repository root from this skill's location (`.agents/skills/grill/`), rather than assuming the current directory is the root. Follow this repository's instructions and inspect its current code; do not audit other projects.

Give the user a broad inventory of concerns they can choose from, not a mandatory implementation checklist. Probe aggressively without claiming to enumerate every possible failure or presenting speculation as fact.

## Scope and investigation

- Follow applicable AGENTS.md and LOCAL.md, then read project docs. Check freshness without changing files. Separate accepted contracts, proposals and unverified observations.
- Honour an explicit scope. Otherwise audit current project-owned source, tests, configuration and CI, including staged, unstaged and untracked work. Include relevant dependencies/callers, not a whole virtual environment, unrelated projects or secret files. Record scope and revision.
- Broader risk coverage is explicitly requested here. Repository restrictions on hypothetical bug findings do not exclude useful conditional risks, but those risks must be separately labelled and tied to code, a contract or a named future dependency. Do not invent requirements or present deferred features as implemented defects.
- Trace input, policy, persistence, execution and cleanup paths that actually exist. Probe plausible malformed/oversized inputs, equivalent representations, field interactions, role separation, privacy, deadlines, cancellation, races, retries, crash/restart handling and failure propagation where relevant. If a feature does not exist, identify a specific future dependency or verification gap instead of inventing a failing path.
- Check supported environments and CI rather than assuming a local pass proves portability. Challenge assumptions shared by implementation and tests; one representation of an address/token is not exhaustive evidence.
- Assess readability and maintenance where there is a concrete cost. Prefer local fixes to speculative enterprise architecture or unrequested features.
- Verify bugs with callers/tests and safe deterministic reproductions when useful. Use temporary state and fakes. Do not launch models/games, inspect private host data, perform destructive fault injection or run live network/GPU acceptance checks. State unavailable verification.
- Deduplicate root causes. Do not hit a finding quota, report resolved behaviour as a bug or recycle one concern into several buckets. Empty categories are valid.

## Priority and evidence are separate

Assign each concern a priority and an evidence status. Conditional impact is not proof that the condition occurs.

| Priority | Meaning |
| --- | --- |
| Urgent | Verified severe issue needing immediate action, such as broad credential exposure or major data loss. Speculation alone never earns Urgent. |
| High | Important gaming, security, job-correctness or availability failure, or a well-supported conditional risk with serious impact and a concrete plausible trigger. |
| Med | Realistic bounded bug/risk or meaningful maintenance/testing weakness. |
| Low | Lower-impact or uncommon edge case, or a specific future verification need. |
| Nit | Optional clarity or small quality improvement without demonstrated operational failure. |

Evidence statuses:

- **Confirmed bug:** Current code demonstrably violates an accepted contract or fails under a specified supported condition.
- **Conditional risk:** A failure is plausible only under a named condition not yet established. State missing evidence and what would confirm or rule it out.
- **Verification gap:** A required claim or future safety dependency has not been verified. State when verification is needed; deferred work is not automatically a current bug.
- **Optional improvement:** A preference or maintenance improvement the user may reasonably decline.

## Report format

Return the complete Markdown report in chat and save it as `reports/<YYYYMMDD-HHMMSS>-gpugate-grill.md` under the repository root. Use UTC for the timestamp (`%Y%m%d-%H%M%S`), for example `20261016-035332-gpugate-grill.md`. If a name already exists, append a numeric suffix before the extension rather than overwriting it. Create `reports/` if needed; Git ignores this directory. Apply this naming convention to new reports; leave existing reports unchanged. Do not stage or commit generated output. Link the saved report using its resolved absolute path.

Only final Markdown reports belong in `reports/`. Put report-generation scripts, reproduction scripts, captured output and other intermediates in a task-owned temporary directory outside `reports/`, using `tempfile.TemporaryDirectory` or equivalent cleanup with `try/finally`. Clean up task-created temporary files on success or failure, and check for remaining task-owned intermediates before the final response. Never delete unrelated or pre-existing files. Include reproduction steps, essential code and relevant results in the Markdown report so it does not depend on temporary files or link to deleted helpers. Exclude raw credentials/prompts/private payloads.

# Grill Report — repository/branch

## Executive overview

Describe scope/revision, documentation freshness and actual inspection/execution. State the important conclusions without declaring the project unsafe because a long list exists. This report is an inventory, not a requirement to implement everything.

## Concern inventory

| ID | Priority | Evidence status | Concern | Source | Trigger / missing evidence |
| --- | --- | --- | --- | --- | --- |

Use current clickable file/line links. Give counts by priority and evidence status so speculation is not confused with verified bugs.

## Urgent
## High
## Med
## Low
## Nit

Under each bucket, order findings by practical importance or state none identified. For each use `### G1 — Plain-English title`, its **Evidence status**, a source-line link and these separate concise paragraphs:

**High level:** Everyday explanation, preferably with an accurate analogy.

**Issue:** What is wrong or what assumption is challenged, with a specific trigger.

**Impact:** Concrete consequence; state if it applies only to future work.

**Suggested fix:** Smallest mitigation, or an investigation when a fix is premature. Do not turn uncertain risks into compulsory changes.

**Rationale:** Why that action addresses the concern.

**Evidence:** Verified code/test/reproduction, or exactly what is uncertain. For a conditional risk, include **How to verify** with a bounded safe check or separately authorised acceptance investigation.

A small labelled diagram may follow when it clarifies the failure. Prefer one scenario over lengthy theory and multiple alternative designs.

## Validation and coverage limits

List actual commands/results, inspected areas, unresolved assumptions and unsupported environments. Fakes do not prove real GPU release or private connectivity. Do not promise exhaustive coverage.

## Suggested triage

Separate **Fix first**, **Investigate before deployment**, and **Optional backlog**. The user chooses which concerns to act on. This audit does not authorize edits, staging, commits, pushes, PR messages or live-host investigations. Later fixes follow repository test-approval rules and existing session authorization.

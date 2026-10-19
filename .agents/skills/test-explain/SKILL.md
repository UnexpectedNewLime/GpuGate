---
name: test-explain
description: "Explain GpuGate test cases in simple English with exact source-line links, what each case checks and why it matters. Use when asked to explain tests or invoke test-explain; this does not implement or approve changes."
---

# Test Explain

This skill belongs to the GpuGate repository. Resolve the repository root from this skill's location (`.agents/skills/test-explain/`), rather than assuming the current directory is the root. Follow this repository's instructions and inspect its current code; do not audit other projects.

Produce a readable guide to the selected tests for someone learning programming.

## Scope and evidence

- Follow applicable AGENTS.md and LOCAL.md before reading project docs. This is a read-only explanation: compare canonical docs for freshness, but do not refresh snapshots or edit tests.
- Honour a supplied file, test name or selection. Otherwise explain changed tests, including staged, unstaged and untracked files. If none changed, explain the relevant tests from the current conversation; if there is no such context, ask which tests to explain.
- Read assertions, fixtures, helpers and the relevant documented contract. Describe what the test actually asserts, not what its name suggests or what the implementation ought to do.
- Read numbered source, for example with `nl -ba`. Get current line numbers, never reuse numbers from a screenshot or previous report. Link every test function and distinct parameter case to its actual source line using `[label](/absolute/path.py:123)`.
- For parametrized tests, enumerate distinct scenarios, including combinations from stacked decorators. Link the function once and each parameter row's source line beside its explanation. Several generated cases can share a source line. Use collected pytest IDs when useful, but do not invent IDs. Report collection errors honestly.
- Explain shared fixtures once. Keep real passwords, prompts, environment contents and private payloads out of explanations; synthetic placeholders are sufficient.
- Do not run the suite solely to explain it. If execution is requested, use deterministic checks and report actual results. Collection alone is not a passing test run. Do not infer TDD order or user approval from the diff.

## Report

Return the complete Markdown report in chat and save it as `reports/<YYYYMMDD-HHMMSS>-gpugate-explain-tests.md` under the repository root. Use UTC for the timestamp (`%Y%m%d-%H%M%S`), for example `20261016-035332-gpugate-explain-tests.md`. If a name already exists, append a numeric suffix before the extension rather than overwriting it. Create `reports/` if needed; Git ignores this directory. Apply this naming convention to new reports; leave existing reports unchanged. Do not stage or commit generated output. Link the saved report using its resolved absolute path.

Only final Markdown reports belong in `reports/`. Put report-generation scripts, reproduction scripts, captured output and other intermediates in a task-owned temporary directory outside `reports/`, using `tempfile.TemporaryDirectory` or equivalent cleanup with `try/finally`. Clean up task-created temporary files on success or failure, and check for remaining task-owned intermediates before the final response. Never delete unrelated or pre-existing files. Include reproduction steps, essential code and relevant results in the Markdown report so it does not depend on temporary files or link to deleted helpers.

Use Markdown headings and short paragraphs. Start with the files covered and a one-sentence overview of the behaviour tested. Explain shared setup briefly, then group tests by behaviour.

For each ordinary test, use:

### Plain-English test title — source-line link

**What it does:** Describe the setup and action in everyday words.

**Expected result:** State the observable assertion, including relevant error fields or boundary values.

**Why it matters:** Explain the practical failure this catches. Use a short analogy if helpful.

For parameter cases, use a table with columns **Case**, **Source line**, **What happens**, **Expected result**, **Why it matters**. Give each meaningful combination its own row; do not replace all cases with “checks invalid inputs.” For large selections, split tables by behaviour. State any unfinished coverage rather than silently skipping cases.

End with **What these tests do not prove**: only material limits, such as simulated evidence not proving real GPU release or an error assertion not proving HTTP authentication works. Separate explanations from suggestions for missing tests; do not create tests or treat this explanation as their approval.

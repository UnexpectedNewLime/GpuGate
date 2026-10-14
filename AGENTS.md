# Agent Instructions

These instructions apply throughout this repository, including implementation tasks and automated pull request reviews.

## Project Context

GpuGate is a planned Python service on a gaming PC that controls when homelab inference jobs may use local Ollama. Gaming takes priority. The design uses a durable SQLite queue, one Gate-owned inference slot, asynchronous HTTP and supervised worker loops. FastAPI, Pydantic, HTTPX and pytest are proposed tools; check the repository before assuming they are installed or configured.

Gate owns admission, queueing, its own inference requests and resource reconciliation. Homelab inspection, repair-plan validation, tool execution and repair approval belong to the separate orchestrator. Ollama is shared with other clients; Gate must respect their work.

## Local Documentation Source

Before reading `docs/` or making changes for a task, check for `LOCAL.md` in the repository root. If present, read it and follow its documentation freshness and synchronisation instructions first. This file is ignored by Git and contains machine-specific paths; do not commit it or copy those paths into shared instructions.

The vault identified in `LOCAL.md` is the canonical source. Keep `docs/` as regular, versionable snapshots for other checkouts and remote PR reviews. Synchronisation is one-way from the vault to `docs/`; edit canonical documents in the vault, then refresh their repository copies. Preserve existing local edits before any refresh. Report refreshed files and leave changes available for review; do not automatically commit them.

If `LOCAL.md` is absent, use the repository docs. If the configured vault is unavailable, report that freshness could not be checked and use the existing repository copies; do not claim they are up to date. During read-only reviews, compare for freshness if possible but do not modify files; report any mismatch that affects the review.

## Required Task Workflow

Always read the documentation before making any code changes, including test changes. Always prioritise the smallest possible code change required to complete the task.

For every task that changes functional code, follow this order:

1. **Read the task and the docs.** Follow the local documentation source instructions above, then read all documents in `docs/` for context and inspect the relevant existing code and tests. Identify the requested behaviour, documented contracts and acceptance criteria. Distinguish confirmed decisions from proposals and unverified observations. Do not silently treat proposed detector thresholds, deployment settings or hardware behaviour as approved requirements. If a referenced document is unavailable, explain the gap rather than inventing its contents.
2. **Create tests before changing functional code.** Add or update focused tests for the requested behaviour. Use the scenario tables in the low-level design and detection proposal where relevant, while respecting their approval status. Cover the task's meaningful success, failure and boundary cases. Run the tests and confirm that new cases fail for the expected missing or incorrect behaviour. If missing dependencies or implementation prevent execution, report that limitation clearly; do not claim a verified failure. Do not change functional code just to make the tests runnable before approval.
3. **Let the user validate the tests.** Present the actual test changes, what each case checks, the test command and results or execution limitations. Ask the user to confirm that the tests match the task. Explain that this approval gate comes from this file's required TDD workflow. Stop before any functional code changes and wait for explicit approval. Silence or a general request to implement the task is not approval of the proposed tests. Revise tests as requested and obtain approval of the revised cases before implementation.
4. **Make the minimal code change that satisfies the approved tests.** Implement only what the task requires. Run the approved tests and relevant existing checks to verify the result and catch regressions. Do not weaken, remove or bypass approved assertions to get a passing result. If implementation reveals a needed change to test expectations or coverage, return to test validation before continuing the affected implementation.

Documentation-only tasks follow the same docs-first and minimal-change principles. Review the edited text against the request and the docs; do not invent functional tests for prose changes. Read-only reviews do not require implementation or test approval.

## Minimal Change Rules

- Prefer the smallest correct fix in the existing structure.
- Keep edits focused on the task and its approved tests.
- Avoid unrelated refactoring, renaming, formatting, dependency changes or new abstractions.
- Reuse existing helpers and conventions when they fit the task.
- Add code comments or docstrings only when essential to explain a non-obvious reason, tradeoff, constraint or public contract. Do not narrate the code, restate names or explain ordinary Python syntax.
- Prefer clear code over explanatory comments. Keep necessary comments short and focused on why a choice was made; operator configuration guidance and project documentation may still explain how settings are used.
- Refactor only when necessary for the requested behaviour; keep it local and preserve unrelated behaviour.
- If a broader change is necessary, explain why and include its behaviour in the tests presented for approval.

## Testing Principles

- Test observable behaviour and documented contracts rather than copying implementation details.
- Keep tests deterministic with fake clocks, sanitised process/telemetry fixtures, fake Ollama and ntfy endpoints, and temporary SQLite databases as appropriate.
- Use unit tests for pure policy, integration tests for persistence and asynchronous lifecycles, and contract tests for API compatibility when the task needs them.
- Test deadlines, cancellation, retries, restart recovery and races when relevant to the changed behaviour.
- Do not load real models, launch games, change host configuration or run live GPU/network acceptance checks as part of ordinary tests. The docs require separately authorised real-host investigations.
- Passing simulated tests does not prove real GPU release, launcher coverage or private connectivity. Report what was actually verified.

## Code Review Rules

### 1. Review Philosophy

This is a small Python project for a local GPU scheduling and inference service. The purpose of reviews, including Codex automated PR reviews, is to catch real problems, improve code quality and help contributors learn.

Prioritise correctness, readability and maintainability over strict coding conventions or theoretical best practices.

- Read `docs/` and the relevant code before reviewing changes.
- Focus on problems that realistically affect gaming priority, inference jobs, persistence or service operation.
- Do not invent issues simply to provide feedback.
- Keep recommendations proportional to the project's size and complexity.
- Prefer simple, practical fixes over unnecessary abstractions.
- Do not demand enterprise-scale architecture for a single-host service.
- Respect existing project conventions unless they introduce clear problems.
- Distinguish accepted requirements from proposals; do not flag an unapproved proposal as a mandatory contract.

### 2. Communication Style

All review comments must be understandable to someone with basic programming knowledge who is still learning Python.

- Use simple, direct English and avoid jargon when simpler words work.
- Start with a high-level explanation that makes sense without reading the code. Prefer a short everyday analogy when it accurately explains the issue; do not force one or let it replace the actual explanation.
- Use the labelled sections in the Review Comment Format below. Aim for one short sentence per section, adding a second only when needed for clarity.
- Explain what is wrong, why it matters, how it could be fixed and why that fix helps.
- Use a concrete service or job example when helpful.
- Name the relevant setting or function where needed, then explain its purpose in ordinary words. Explain unavoidable technical terms when first used.
- A small diagram is allowed when it makes an order of events or relationship easier to understand. Keep the written explanation understandable without the diagram.
- Avoid lengthy theory, overly formal language, excessive praise and filler.
- Be constructive and respectful. Critique the code, not the author.

For wording within these sections, prefer:

"This retry sends another generation request after the first response is lost. Ollama may still be processing the original request, so the same job could run twice. Preserve the uncertain outcome and reconcile resources instead of resending generation."

Instead of:

"Non-idempotent backend dispatch violates at-most-once execution semantics under ambiguous transport failure."

### 3. Issue Severity

- **P0 – Critical:** A serious, broadly reproducible issue that prevents the service from working, causes major data loss or exposes credentials/private data on a broad scale.
- **P1 – Major:** A clear bug that breaks important admission, cancellation, queue or recovery behaviour; causes crashes; or creates significant security or gaming-resource problems.
- **P2 – Minor:** A real bug or meaningful maintainability problem that should be addressed but is not urgent.
- **P3 – Nit:** An optional improvement to readability, naming, structure or code quality.

Do not inflate severity. Most ordinary code quality suggestions should be P3. Clearly distinguish actual bugs from optional improvements and explain the conditions required for a failure.

### 4. What to Look For

#### Service behaviour and correctness

- Admission during active gaming, stale required observations or uncertain resource ownership.
- Gate's own GPU utilisation incorrectly treated as a newly started game.
- Expired work starting later, deadlines extended by retries/restarts or late results becoming successful after cancellation.
- Duplicate generation after submission retries, lost responses or restart recovery.
- Multiple active leases, broken FIFO ordering or incorrect zero-wait reservation behaviour.
- Success acknowledgements sent before durable state is committed.
- Incorrect separation between terminal job state and confirmed resource release.
- Gate cancelling another client's work, restarting shared Ollama or unloading a shared model automatically.
- API fields, response states or result types that break the documented watcher contract.
- Incorrect GRACE/session transitions, stale phone decisions or controls bypassing fresh resource checks.
- Retention deleting unresolved resource evidence or keeping private payloads beyond the accepted policy.
- Gate taking on orchestrator responsibilities such as executing tools or approving repairs.

#### Python, persistence and asynchronous I/O

- Blocking work on the event loop that realistically delays detection, cancellation or requests.
- Tasks, HTTP streams, connections or database resources left open after cancellation or shutdown.
- Exceptions swallowed in a way that hides failed essential workers or leaves admission enabled.
- Network calls or cleanup waits inside admission locks or database transactions that cause realistic stalls.
- Unsafe SQLite transaction boundaries, race conditions or migrations that lose accepted work.
- Timeouts that limit inactivity but allow an entire attempt to exceed its deadline.
- Wall-clock changes or reused monotonic timestamps that incorrectly extend execution budgets.
- Mutable shared state or Python/API misuse that produces a concrete runtime failure.
- Unbounded input, stream accumulation, retries or queues with a realistic resource-exhaustion scenario.
- Missing authentication, role/owner checks, replay protection or leakage of prompts, results, credentials and capabilities.

Only flag these when they cause an actual problem or introduce meaningful risk supported by the code and docs.

#### Code quality and tests

- Functions that are unnecessarily difficult to understand or names that obscure important state.
- Repeated code that could reasonably be extracted without adding more complexity.
- Unnecessary complexity or mixed responsibilities that make changes difficult.
- Missing essential explanations for non-obvious intent or tradeoffs, dead code or accidental debugging code.
- Tests that miss the task's required behaviour, assert the wrong contract or hide a real failure.
- Changes that weaken regression coverage or exceed the task without a clear need.

Keep code quality suggestions lightweight. Do not refactor working code solely to follow a design pattern. Do not infer the order tests were written or whether the user approved them solely from a final diff; use available evidence for workflow findings.

### 5. What NOT to Flag

Avoid comments about:

- Personal coding style preferences or formatting better handled by a formatter.
- Hypothetical failures without a realistic scenario.
- Abstractions, new systems or features that are not needed for the task.
- Small amounts of duplication that are clearer than an abstraction.
- Missing comments on self-explanatory code.
- Micro-optimisations without meaningful operational benefit.
- Code outside the PR's scope unless directly relevant to a changed behaviour.
- Intentional behaviour supported by the docs and surrounding code.
- Missing real-host measurements in a PR that only claims deterministic core behaviour and keeps unverified adapters blocked.

Do not suggest new schedulers, databases, model brokers or homelab repair features unless necessary to fix a genuine problem.

### 6. Review Comment Format

For each issue, provide:

1. **Title:** A short, plain-English description with its priority.
2. **High level:** Explain the issue as simply as possible, preferably with an accurate everyday analogy. Assume the reader has not read the code.
3. **Issue:** State what the code currently does incorrectly and the conditions that trigger it. Name the relevant setting or function when helpful.
4. **Impact:** Explain the practical consequence for gaming, jobs, security or service operation. Distinguish a current failure from a risk that applies to future unimplemented code.
5. **Suggested fix:** Give the smallest concrete change that addresses the issue.
6. **Rationale:** Explain why that change prevents the stated consequence. Do not merely repeat the suggested fix.

Use these exact labels, in this order, with each section in its own short paragraph. Do not compress them into one dense paragraph. Keep optional improvements clearly marked as P3/Nit and use the same structure.

Follow any required automated review output format. Put the labelled explanation inside the finding's permitted comment/body field; do not add unsupported fields. If paragraph breaks are prohibited, retain the labels and order in the allowed text format.

Optional diagrams belong after the written sections. Prefer a tiny text diagram such as `cancel recorded -> request may still run -> slot stays reserved`. Use a short Mermaid diagram only when the review interface supports it. Show the relevant behaviour, label whether it is current or suggested, and avoid large architecture diagrams or code dumps.

Example:

**[P1] Cancelled job releases the slot before Ollama stops**

**High level:** Cancelling a parking reservation does not move the car out of the space; the space is free only after the car leaves.

**Issue:** Cancelling a running job immediately frees Gate's inference slot, even though its Ollama request may still be running.

**Impact:** Another job could start while the previous request is still using resources, increasing GPU contention.

**Suggested fix:** Keep the slot reserved until resource checks confirm it is safe to release.

**Rationale:** The next job must then wait for confirmed release, rather than relying on the cancellation record alone.

Do not include lengthy explanations, multiple alternative implementations or large code snippets unless necessary.

### 7. Review Quality Requirements

Before reporting an issue:

- Verify that the problem exists in the changed code.
- Check nearby code, relevant callers and tests before assuming something is missing.
- Identify a realistic scenario where it occurs.
- Consider whether the behaviour is intentional or a documented limitation.
- Avoid repeating the same issue across multiple comments.
- Do not present uncertainty or speculation as a confirmed bug.
- Suggest the smallest reasonable fix rather than a large rewrite.

Report genuine bugs even when minor. Include useful P3 suggestions when they offer a clear readability or maintainability benefit, but do not flood the review with nits. A review with no findings is acceptable; do not manufacture feedback.

### 8. Project Priorities

For this project, prioritise:

1. Gaming priority and safe handling of shared GPU/Ollama resources.
2. Correct admission, queueing, deadlines, cancellation and durable recovery.
3. Runtime stability, private data protection and authenticated access.
4. Clear, understandable Python and meaningful tests.
5. Ease of collaboration and the smallest practical changes.
6. Performance when it meaningfully affects gaming or service responsiveness.
7. Consistency with existing project patterns and accepted documented contracts.

The goal is a reliable local service that is easy for a small team to maintain. Keep recommendations grounded in that goal and the task under review.

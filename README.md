# GpuGate

GpuGate is a planned Python service that controls when homelab inference jobs may use local Ollama on a gaming PC. Gaming takes priority. The design uses a durable SQLite queue and one Gate-owned inference slot; Ollama remains shared with other clients.

This repository currently provides the development baseline and design documentation. The service, detectors and deployment are not implemented. Homelab inspection, repair-plan validation and execution belong to the separate orchestrator.

## Development setup

Use Python 3.12 and [uv](https://docs.astral.sh/uv/getting-started/installation/) for dependency management. CI uses uv 0.13.0. From the repository root, install the project and development tools from the committed lockfile:

```sh
uv sync --locked --group dev
```

uv creates `.venv` and [downloads the required Python version if needed](https://docs.astral.sh/uv/guides/install-python/). The package lives in `src/gpu_gate/`; the initial package-installation check lives in `tests/test_setup.py`. Add unit, integration and contract test directories as the corresponding features need them. Runtime dependencies will be added with those features.

Run the checks used by CI:

```sh
uv run --locked ruff format --check .
uv run --locked ruff check .
uv run --locked pytest
uv build --no-sources
```

To apply formatting, run `uv run --locked ruff format .`. When intentionally changing dependencies, update `pyproject.toml` and regenerate `uv.lock` with `uv lock`; include both files in the change.

Ordinary tests must use fakes and temporary state. Real GPU, gaming, Ollama and deployment investigations require separate authorisation, as described in [AGENTS.md](AGENTS.md).

## Contributing

After the initial setup on `main`, create a separate branch for each feature or fix and submit a pull request back to `main`.

```sh
git switch main
git switch -c feat/your-feature
```

Follow the required workflow in [AGENTS.md](AGENTS.md):

1. Check local documentation freshness, read all repository docs and identify the task's accepted requirements.
2. Write focused tests before changing functional code, then run them and report the expected failures or execution limitations.
3. Present the actual tests and wait for the user's explicit approval that they match the task.
4. Make the smallest functional change that satisfies the approved tests, then run the relevant checks.

A general implementation request does not approve proposed tests. If test expectations need to change during implementation, obtain approval again. Documentation-only changes need a text review, without invented functional tests.

## Documentation

Read these documents before making changes:

- [GPU Gate in Plain English](docs/10%20-%20GPU%20Gate%20in%20Plain%20English.md): overall flow and responsibility boundaries.
- [GPU Gate Spec](docs/11%20-%20GPU%20Gate%20Spec.md): service behaviour and accepted operating choices.
- [GPU Usage and Automatic Game Detection Proposal](docs/12%20-%20GPU%20Usage%20and%20Automatic%20Game%20Detection%20Proposal.md): detector policy that still needs review.
- [GPU Gate Low-Level Design](docs/13%20-%20GPU%20Gate%20Low-Level%20Design.md): planned interfaces, scenario tables and implementation order.

The vault is the canonical documentation source. An optional, ignored `LOCAL.md` supplies this checkout's vault path and one-way refresh instructions. Agents follow those instructions before reading `docs/`, preserve local edits and report refreshed files. Without `LOCAL.md`, use the committed snapshots; if the configured vault is unavailable, report that freshness could not be checked.

Keep `docs/` as ordinary committed files so other checkouts and remote PR reviews can read them. Edit canonical documents in the vault, refresh the repository snapshots and include those snapshots in a commit when ready. Do not commit `LOCAL.md` or machine-specific vault paths. Some Obsidian links in the snapshots reference broader homelab documents that are not included here.

Detector thresholds, hardware safety and private deployment settings remain subject to the decisions and verification described in the docs. Development checks do not establish real GPU release or gaming performance.

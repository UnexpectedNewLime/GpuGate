---
tags: [gpu-gate, detection, proposal, amd, gaming]
status: draft
created: 2026-10-07
updated: 2026-10-13
---

# 12 — GPU Usage and Automatic Game Detection Proposal

> [!tip] Short reading path
> [[10 - GPU Gate in Plain English|Plain-English guide]] · [[21 - Fallacies and Sanity Check|Sanity-check findings]]. This document retains the technical detail; the guide links here rather than copying its settings.

**Recommendation:** make measured RX 9070 XT usage the primary admission check, supplement it with automatically discovered game sessions, and keep separate rules for an idle Gate versus its own running inference. Start with a **30% hold threshold**, **10% release threshold** and **60 seconds continuously quiet** before becoming eligible again.

**Why:** GPU load catches contention regardless of the application. Session detection covers game startup, menus and frame-capped games before high load appears. Different entry/exit thresholds prevent rapid toggling. A running LLM must not cancel itself merely because it uses the GPU.

These numbers and detection rules are **proposed for user review, not accepted or measured settings**. User-confirmed direction: GPU usage is primary, and Steam/Lutris/Heroic games must be discovered without a manually maintained game list. Choices 2–6 are accepted in ADR-016: shared Ollama, incident-only v1, private authenticated access, 24h payload/7d metadata retention and guarded controls. No runtime configuration or software was changed for this proposal.

## 1. Resource policy

| Situation | Proposed action |
|---|---|
| No Gate inference; latest valid GPU busy sample ≥30% | Hold admission immediately; do not wait for a second detector or a 30s high-load interval |
| Previously held, or startup | Require samples ≤10% continuously for 60s, no active/candidate game, sufficient VRAM and no ownership/health block |
| Load between 10% and 30% | Keep previous pressure state; it resets a pending quiet interval. An already eligible Gate stays eligible unless another blocker appears |
| Detected game session, even below 30% | Hold admission throughout the session; menu/alt-tab/limiter is not evidence of game exit |
| Game launch candidate | Temporary hold while tracking the actual payload/session; launcher UI alone is not sufficient |
| Gate inference is already running | Total GPU utilisation alone does not trigger cancellation; continue monitoring for games and independently attributable competing work |
| New game starts during Gate inference | Request cancellation of Gate-owned inference; discard late output; reconcile before another job |
| GPU/required process coverage unavailable or stale >5s | Block new work; while executing, request owned cancellation if required protection remains unavailable. Never synthesise zero usage |
| VRAM headroom insufficient or uncalibrated | Block admission with memory reason even at low GPU busy percentage |

Proposed sampling: GPU once per second; launcher/process scan every two seconds; reuse process identity and read unchanged launcher metadata infrequently/on change. Classifier budget and permissions must be measured. No timer counts missing samples as idle; use monotonic duration and timestamp freshness, not an assumed number of polls.

Use distinct reasons: `GPU_PRESSURE`, `GAME_ACTIVE`, `GAME_STARTING`, `EXTERNAL_OLLAMA`, `VRAM_HEADROOM`, `TELEMETRY_UNKNOWN`, `RELEASE_UNCERTAIN`. The Gate is unavailable if any required admission condition fails; low utilisation cannot override a game/resource hold.

**GRACE distinction:** retain the existing gaming-session flow: 60s confirmed all-clear after a game → GRACE prompt → Done gaming or 20m verified idle. An ordinary browser/render/compute utilisation spike uses the 60s resource quiet rule only; it must not cause a misleading “Done gaming?” prompt or a 20m gaming grace period. Admission still requires all resource checks when GRACE ends. A single high-load sample during GRACE resets its continuous-idle timer; it creates a new BUSY gaming session only if game evidence actually returns. These refinements require review with this proposal.

### Configurable thresholds and timings

**User-confirmed direction — 2026-10-13:** store the resource thresholds and detector timings in operator TOML settings, rather than fixing them in code. The values below illustrate the existing proposal; they are not approved production defaults or a complete deployable configuration.

```toml
[gpu]
hold_percent = 30
release_percent = 10
quiet_seconds = 60

[detectors]
gpu_poll_seconds = 1
process_poll_seconds = 2
freshness_seconds = 5
```

Pass these validated settings into the proposed admission and sampling functions. `gpu.quiet_seconds` controls the resource-pressure quiet interval; it does not change the separate gaming all-clear or GRACE policy. Read and validate settings at startup, then restart Gate after edits to apply them. Commit an example file when implementing configuration and keep the machine-specific file outside Git. See [[11 - GPU Gate Spec#Runtime configuration|validation and configuration rules]] and [[13 - GPU Gate Low-Level Design#Function: `load_settings`|the loader contract]].

Policy tests must supply explicit settings and cover threshold boundaries with more than one valid configuration, so tuning does not require rewriting the policy. Real-host calibration remains separately authorised; editing settings alone does not establish gaming safety.

## 2. AMD telemetry

Read the selected device's `gpu_busy_percent` through amdgpu sysfs. Discover by stable PCI/device identity and AMD driver, not a hard-coded `card0`. The kernel describes this as firmware-computed aggregate activity; it does not identify the application or measure all forms of contention independently. `gpu_metrics` can supply additional sensor data if its format/version is supported. These are candidate interfaces, not a claim that they were inspected locally. [Kernel amdgpu monitoring documentation](https://docs.kernel.org/gpu/amdgpu/thermal.html#busy-percent).

Also collect used/total VRAM through a verified driver interface. Distinguish **memory busy percentage** (activity) from **memory allocated** (capacity). Available memory must cover a measured *incremental* peak allocation for the selected model/context plus a reserve; neither the model download size nor “GPU utilisation <30%” establishes this. Profile `gpt-oss:20b` with the current 65,536 context setting before choosing the budget; proposed reserve is 1 GiB above that measured requirement, still subject to review. Do not change Ollama context or offload settings automatically.

For attribution, investigate `/proc/<pid>/fdinfo/<fd>` DRM client statistics. Deduplicate shared descriptors by device/client ID and derive engine activity from successive counters, respecting engine capacity and counter regressions. Driver support varies. These counters are supporting attribution evidence, not a licence to subtract unlike percentages from total utilisation. [Kernel DRM client statistics](https://docs.kernel.org/gpu/drm-usage-stats.html).

## 3. Automatic game-session discovery

Maintain a transient process graph keyed by `(boot_id, pid, start_time)` and correlate launcher provenance, inherited markers, executable identity and renderer activity. Do not keep a list of game executable names supplied by the user.

| Launcher | Automatic evidence to investigate | Important boundary |
|---|---|---|
| Steam | `SteamGameId`/`SteamAppId` markers, Steam launch/reaper ancestry, Proton/pressure-vessel descendants; auto-read library metadata only as supporting provenance | Proton uses `SteamGameId` but explicitly handles its absence. Steam client/webhelper/overlay alone is not a game; native and non-Steam launches need separate fixtures |
| Lutris | `LUTRIS_GAME_UUID` on monitored launch descendants, runner lineage and actual payload process; auto-discovered installation/prefix metadata as corroboration | Steam URI launches can detach into Steam's process tree and need Steam evidence; never require every child to inherit a Lutris marker |
| Heroic | `HEROIC_APP_NAME`, `HEROIC_APP_RUNNER`, `HEROIC_APP_SOURCE` when present, plus launch ancestry; Proton path can use `SteamGameId=heroic-…` | Marker availability depends on launch/version. Distinguish Heroic UI/downloads from game payload; test Epic/GOG/sideload and Flatpak variants |

These mechanisms are based on upstream source, not guaranteed stable launcher APIs or verified installed behaviour: [Valve Proton](https://github.com/ValveSoftware/Proton/blob/proton_10.0/proton), [Lutris monitored launch](https://github.com/lutris/lutris/blob/master/lutris/monitored_command.py), [Lutris game tracking](https://github.com/lutris/lutris/blob/master/lutris/game.py), [Heroic launch environment](https://github.com/Heroic-Games-Launcher/HeroicGamesLauncher/blob/main/src/backend/launcher.ts). Pin adapters and captured fixtures to the versions actually installed when implementation starts.

Proposed algorithm:

1. Discover supported native/Flatpak launcher installations and running launcher processes for the configured desktop user. Read only relevant launcher metadata and a fixed set of game marker environment keys; never log whole environments, raw command lines, auth stores or account information.
2. Identify a **launch candidate** from a game launch marker plus payload/runner lineage, or a launcher-origin child with newly observed rendering and installation-path corroboration. Create a short provisional hold immediately; bare launcher presence is not enough.
3. Confirm **active session** from a live non-launcher payload with launch provenance and either verified game payload identity derived from launcher metadata or rendering-client evidence. Group Wine/Proton/emulator helpers by session rather than classifying every `wine` or `wineserver` as a game. GameMode and an actual Sunshine session are optional corroboration; they are not required installations or the main resource metric.
4. Preserve confirmed membership when parents exit or processes reparent; inherit membership only from a still-matching process identity. Ignore helper-only remnants once no live payload/renderer remains. PID reuse never inherits a previous session.
5. Keep a confirmed game active through low FPS, menus and alt-tab while its live payload remains. Multiple concurrent games keep the hold until all finish. After exit use the existing 60s all-clear/GRACE flow.
6. Proposed unconfirmed-launch hold: up to 30s. On timeout, clear only if evidence positively shows the launch exited or only identified launcher/updater helpers remain. If payload/coverage is ambiguous, report `unknown` and block instead of admitting after an arbitrary timeout.

No per-game configuration is required in the intended normal path. Process/container boundaries and launcher changes prevent a credible promise of universal detection before tests. Unknown layouts should produce a coverage reason and fixture request, not require the user to maintain a title list. Backend load still blocks resource-heavy activity even if the launcher classifier does not name it.

**Permissions:** start with unprivileged access. If a dedicated Gate identity cannot inspect the desktop user's process markers, propose a minimal desktop-user collector emitting only sanitised session identities over a private authenticated local socket; Gate remains the only scheduler/network API. Collector identity, peer credentials, UID scoping and heartbeat must be verified. This is a deployment option, not an approved extra privileged daemon. Do not solve missing access by running the remote-facing Gate as root or reading every user's environment.

## 4. Avoiding self-triggering and respecting shared Ollama

Before a Gate job, observe total load and available memory. During it, expect high total GPU utilisation. Cancelling on that same aggregate threshold would create a start → high usage → cancel loop.

Track the **Gate-owned HTTP request/lease** as ownership. Ollama's PID, runner process, model name and loaded-model list do not identify a particular request: a coding client may use the same daemon, runner and model. Never classify all Ollama GPU activity as Gate-owned. Engine activity also does not reliably separate games from inference by itself.

Proposed v1 policy:

- Never terminate the shared daemon, kill a runner, issue model-wide unload or force `keep_alive=0` as an automatic cancellation remedy. Those operations may affect coding work. Cancel only the Gate request; if backend termination cannot be confirmed, block further Gate work and expose the reason.
- Conservatively defer a new Gate job if a model is already loaded before Gate acquires ownership, unless future request-level evidence proves safe reuse. A loaded model means **possible occupation**, not proven active coding. This may delay incident planning while a model is merely warm; watcher can degrade instead of evicting it. This conservative rule needs review.
- If another attributable GPU workload starts during Gate generation, yield Gate-owned inference. For an unattributed rise in *aggregate* usage alone, do not pretend to know whether a new workload appeared; retain finite deadlines and game-session monitoring. Same-runner direct coding requests are a known attribution blind spot.
- Existing guarded “pause inference” is available before rare direct coding use. A future opt-in local request broker could track both clients precisely, but is outside incident-only v1 and must not be introduced silently.

Confirming physical stop after an HTTP abort remains an empirical acceptance requirement. Normal completed response is evidence of that request completing, not of unloaded model memory. Track `request_finished` separately from memory/admission readiness, so normal warm residency does not become an unexplained permanent slot lock. CPU/GPU-idle sampling alone is not proof that no delayed request is pending.

## 5. LLD changes and tests

Extend `detectors.py` internally with telemetry and launcher parsers, rather than putting platform logic into `reduce_gate`. Proposed boundaries:

| Function | Inputs → output | Must not do / tests |
|---|---|---|
| `sample_gpu(device, previous, clock) -> GpuSample` | Verified selected device → busy %, memory observations, time/quality | No GPU tuning; test missing files, invalid range, multiple GPUs, stale reads |
| `scan_game_sessions(process_snapshot, launcher_metadata, previous) -> SessionSnapshot` | Sanitised identity graph/markers → active/candidate/unknown sessions and reasons | No per-game names, process termination or arbitrary env publication; test markers absent, reparenting, PID reuse, helper remnants, native/Flatpak |
| `evaluate_admission(gpu_history, sessions, ownership, policy) -> AdmissionDecision` | Pure evidence → allow/hold/unknown + reason and next eligibility time | No I/O; test threshold boundaries and stateful 10–30% band; finite deadlines never extended |
| `evaluate_running_job(lease, new_evidence, policy) -> ContinueOrCancel` | Owned job + new game/contender/coverage evidence → action/reason | No cancellation from own aggregate load alone; no claim to disambiguate requests on one Ollama runner |

These are proposed refinements to doc 13, not final detector interfaces; promote them to complete function contracts once policy is reviewed. Separate immutable evidence from mutable session/pressure history.

| Scenario | Expected observable result | Level |
|---|---|---|
| 29% → 30% before dispatch | Admission closes on first fresh ≥30% sample | Unit |
| Busy → 10% for 59s / 60s | Remains held / becomes resource-eligible, subject to other gates | Unit |
| Quiet timer sees 11% or stale data | Timer resets; no admission from incomplete history | Unit |
| Steam/Heroic UI open, no game, low load | No game session; resource policy may allow | Parser integration |
| Browser/render job exceeds threshold | Resource hold without gaming prompt/20m GRACE | Unit/integration |
| Game paused at 5% utilisation | Session veto remains, if proposed low-load veto is accepted | Unit/integration |
| New unlisted Steam/Lutris/Heroic game | Discovered automatically from launch/session evidence | Real launcher acceptance |
| Game reparented or Wine child outlives launcher | Session retained while payload alive; helper-only remnants do not persist forever | Parser integration |
| Missing markers/Flatpak permission denial | Explicit incomplete coverage; no guessed-clear result | Integration |
| Gate request drives GPU to 100% | No self-triggered cancellation | Unit/backend integration |
| Game starts mid-generation | Owned cancellation requested at next detection; other Ollama work untouched | Integration/real-host |
| Same Ollama runner serves coding and Gate | No false request ownership claim; limitation/guard visible | Backend integration |
| Low busy %, insufficient free VRAM | Admission denied with memory reason | Unit |
| Game closes while queue expires | Expired job never runs after GRACE | Cross-component |

First validate parsers/policy with fake clocks and captured sanitised fixtures. Then, after separately authorised local inspection, run an **observe-only calibration** while normally using desktop, browser/video, native and Proton games, Lutris/Heroic, and occasional coding. Record decisions/reasons, sampling overhead and device evidence, not private process content. Tune candidate thresholds from measured traces. Only later run an authorised inference/game coexistence test to measure cancellation, frame-time impact and memory behaviour.

## 6. Review choices

The user has already selected GPU-first admission and automatic launcher discovery. Remaining proposed behaviour to review together:

1. **30% hold / 10% release / 60s quiet**, with 1s GPU sampling and 2s process scans.
2. **Detected games veto admission even under 30%**, while non-game load uses resource-only cooldown.
3. **Conservative shared-Ollama admission**: defer when pre-existing loaded models make ownership uncertain, and never evict them.

Device/interface availability, thresholds, exact game-session rules and cancellation effectiveness are unverified locally. This proposal does not assume approval to run hardware tests or change services.

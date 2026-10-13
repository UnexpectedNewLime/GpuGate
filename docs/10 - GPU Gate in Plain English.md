---
tags: [gpu-gate, guide]
status: living
created: 2026-10-08
---

# 10 — GPU Gate in Plain English

**Read this for the flow; follow the links for exact rules and settings.** The Gate is a planned Python service on this gaming PC. It decides when a homelab inference job may start, tracks that job, and yields when gaming needs the resources. It has no Proxmox repair authority. See [[11 - GPU Gate Spec#Placement and responsibility boundary|its responsibility boundary]].

**Why:** the gaming PC is shared. A queue can control Gate's own work, but it cannot automatically control every other Ollama client or guarantee immediate GPU release.

## The normal flow

1. **Observe the PC.** Read GPU activity, memory and supported game-session evidence. Missing observations must be reported as unknown. [[13 - GPU Gate Low-Level Design#Function: `sample_signals`|Technical contract: sample_signals]].
2. **Decide whether work is eligible.** Combine observations with gaming history and operator holds. High utilisation caused by Gate itself must not be mistaken for a newly launched game. [[13 - GPU Gate Low-Level Design#Function: `reduce_gate`|Technical contract: reduce_gate]].
3. **Record the request.** Authenticate watcher, validate the request and save it before acknowledging. If watcher retries after losing the response, it gets the same job. [[13 - GPU Gate Low-Level Design#Function: `accept_job`|Technical contract: accept_job]].
4. **Reserve one slot.** Recheck availability and expiry before selecting waiting work. An immediate-admission request either reserves an available slot or fails promptly. [[13 - GPU Gate Low-Level Design#Function: `claim_next`|Technical contract: claim_next]].
5. **Ask Ollama once.** Stream the answer under the job's remaining budget and store a valid transport result. The orchestrator later checks whether the answer is an acceptable repair plan. [[13 - GPU Gate Low-Level Design#Function: `execute_job`|Execution coordination]] and [[13 - GPU Gate Low-Level Design#Function: `stream_completion`|Ollama stream handling]].
6. **Account for resources.** A finished or cancelled job is separate from a free inference slot. Prove the required release conditions before admitting another job. [[13 - GPU Gate Low-Level Design#Function: `reconcile_resources`|Technical contract: reconcile_resources]].

For the exact request fields, responses and error codes, use [[13 - GPU Gate Low-Level Design#3. Shared types, persistence and protocol|the shared wire contract]]. This guide intentionally does not reproduce it.

## What the availability states mean

| State | Meaning |
|---|---|
| IDLE | New work may be eligible, subject to fresh checks and an available slot |
| BUSY | Detected gaming or relevant resource pressure prevents admission |
| GRACE | Gaming appears finished; the Gate waits for a guarded decision or its idle policy |
| BLOCKED | Required evidence, backend ownership or cleanup is uncertain |

These are **Gate availability states**, separate from an individual job's state. A healthy service can be unavailable for inference. Exact transitions and timing belong to [[11 - GPU Gate Spec#Availability state and gaming detection|the state policy]] and [[13 - GPU Gate Low-Level Design#Function: `read_status`|status/readiness contract]].

## How gaming detection is proposed to work

GPU activity is the primary resource signal. Automatic Steam/Lutris/Heroic discovery adds evidence of games that are paused, in menus or otherwise using little GPU. Launcher windows by themselves should not count as games. The concrete thresholds and veto rules remain a proposal. See [[12 - GPU Usage and Automatic Game Detection Proposal#1. Resource policy|resource policy]] and [[12 - GPU Usage and Automatic Game Detection Proposal#3. Automatic game-session discovery|launcher discovery]].

The proposed detector has four smaller jobs: `sample_gpu` reads resource counters; `scan_game_sessions` tracks likely game processes; `evaluate_admission` decides whether new inference may start; `evaluate_running_job` decides whether owned inference should continue. Their inputs and tests are in [[12 - GPU Usage and Automatic Game Detection Proposal#5. LLD changes and tests|the detector function table]].

Fresh checks confirm readable AMD resource counters and an active loopback Ollama service. Earlier installation evidence includes both native and Flatpak launchers. Permissions and coverage under the eventual Gate user still need verification. See [[22 - Sanity Check Evidence#Local observations|local evidence]].

## Adjusting settings

GPU thresholds and detector timings will live in an operator TOML configuration file. Edit the file and restart Gate to apply changes; no code edit or rebuild is needed. Gate validates settings before starting. The example values remain proposals, not measured safe thresholds. See [[11 - GPU Gate Spec#Runtime configuration|configuration rules]] and [[12 - GPU Usage and Automatic Game Detection Proposal#Configurable thresholds and timings|the example]]. The initial deployment remains a native systemd service; Docker is deferred.

## When a game starts or a job expires

The Gate first stops admitting work, records cancellation and asks its owned request to stop. It does not kill the shared Ollama service or unload another client's model. If release is uncertain, it stays blocked. [[13 - GPU Gate Low-Level Design#Game starts, cancellation and Gate restart|The cancellation diagram]] shows the sequence; [[21 - Fallacies and Sanity Check#F01 — Cancelling a job guarantees gaming gets its GPU back|the review]] explains what remains unproven.

Waiting is bounded. An incident that expires during a game must not run later just because the GPU becomes free. The caller can send a contextual human report. See [[11 - GPU Gate Spec#Queue, deadline and resource rules|deadline rules]] and [[21 - Fallacies and Sanity Check#F02 — Jobs queued during gaming will drain afterwards|the queue/grace contradiction]].

## What the phone controls do

“Done gaming” asks the Gate to recheck eligibility. It cannot override an active game or unknown resource state. “Still playing” records a guarded hold. These are gaming-session controls, separate from approval to repair a homelab guest. [[13 - GPU Gate Low-Level Design#Function: `record_session_decision`|Session decision contract]].

The Gate records a notification before sending it, so a temporary ntfy outage does not lose the intent. Delivery can repeat after a crash, but the decision must take effect only once. [[13 - GPU Gate Low-Level Design#Function: `publish_notice`|Notification contract]].

## Other functions, without the implementation detail

| Function | Plain explanation and technical link |
|---|---|
| `load_settings` | Rejects missing or unsafe configuration before work starts. [[13 - GPU Gate Low-Level Design#Function: `load_settings`\|Full contract]] |
| `authenticate` | Checks who is calling and which operations they may request. [[13 - GPU Gate Low-Level Design#Function: `authenticate`\|Full contract]] |
| `parse_submission` | Checks the request shape and builds a stable identity for retries. [[13 - GPU Gate Low-Level Design#Function: `parse_submission`\|Full contract]] |
| `apply_gate_event` | Saves a policy change, then signals any cancellation it requires. [[13 - GPU Gate Low-Level Design#Function: `apply_gate_event`\|Full contract]] |
| `cancel_job` | Makes a job logically cancelled and signals owned work; physical release is checked separately. [[13 - GPU Gate Low-Level Design#Function: `cancel_job`\|Full contract]] |
| `read_job` | Returns the caller's saved job result or status without starting work. [[13 - GPU Gate Low-Level Design#Function: `read_job`\|Full contract]] |
| `recover` | Reconstructs safe state after a Gate restart; interrupted generation is not replayed. [[13 - GPU Gate Low-Level Design#Function: `recover`\|Full contract]] |
| `maintain` | Expires jobs and old payloads while preserving unresolved resource evidence. [[13 - GPU Gate Low-Level Design#Function: `maintain`\|Full contract]] |
| `lifespan` | Starts, supervises and shuts down the service's worker loops. [[13 - GPU Gate Low-Level Design#Function: `lifespan`\|Full contract]] |

## Where to go next

Implementation order and unresolved inputs live in [[13 - GPU Gate Low-Level Design#7. Assumptions, unresolved inputs and implementation order|the Gate build sequence]]. Completion lives in [[Software/Projects/self-healing-homelab-docs/homelab-self-healing/Tasks#Phase 3 — GPU Gate|Tasks]]. For the caller's side of the flow, continue to [[14 - Orchestrator in Plain English]].

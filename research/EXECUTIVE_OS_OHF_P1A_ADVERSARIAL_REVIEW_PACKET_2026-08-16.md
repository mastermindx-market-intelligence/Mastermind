# OHF-P1A-R3 — Adversarial review packet

**Date:** 2026-08-18
**Status:** attack surface after R2 remediation. Not self-acceptance.
**Typed freeze:** `control_plane/operator_harness_contract.py`

Legend: **P** prevent, **D** detect, **R** recover, **U** unknown, **X** unsafe
if the old P1A-R1 rule were kept (now closed in contract).

| # | Threat | P | D | R | Layer |
|---|---|---|---|---|---|
| 1 | Two Executive writers on one `(worker_id, provider_session_id)` | P | D | R | unique held-writer index + provider writer |
| 2 | Opaque session id collision across workers | P | | | realm includes `worker_id` |
| 3 | Session reused across Attempts | P | D | | epoch bound to one Attempt; realm unique per worker |
| 4 | SIGKILL then `ended_at` frees writer | P | D | R | `executive_writer_held` survives process death |
| 5 | Stale generation resumes after newer owns session | P | D | | generation_number + held-writer uniqueness |
| 6 | Resume changes model/sandbox/approval | P | D | | requested profile digest; mismatch REFUSE / NEW_ATTEMPT |
| 7 | Wrong cwd/worktree / recreated path | P | D | | workspace inode+device+uid+gid+base SHA (`executive_workspace` + Gate B path law) |
| 8 | `CODEX_HOME` other account | | D | U | ACCOUNT_REALM_ATTESTATION_UNPROVEN; path/inode are not identity |
| 9 | Ambient app/skill after update | D | P | | observed attestation vs REQUIRED/FORBIDDEN/allowlist |
| 10 | Malicious repository `AGENTS.md` | P | D | | requested profile + sandbox + unclassified fail-closed; model is not the boundary |
| 11 | Malicious project-local `SKILL.md` | P | D | | capability attestation; unclassified write REFUSE |
| 12 | Malicious plugin config | P | D | | same; residual plugins remain UNCLASSIFIED |
| 13 | Malicious MCP server/tool description | P | D | | MCP allowlist; extra servers unclassified/forbidden |
| 14 | Malicious MCP result | P | | | treat output untrusted; no universal MCP item events |
| 15 | Future browser/web prompt injection | P | U | | out of P1A; later Resource Fabric + sandbox |
| 16 | Native helper inherits parent write tools | P | D | | helpers disabled on write-capable V1 unless ceiling proven |
| 17 | Helper counted as independent review | P | D | | Phase 1F different `worker_id` |
| 18 | Ambient provider skill conflicts with Mastermind skill | D | P | | attestation; unclassified fail-closed |
| 19 | Global user config silently overrides Attempt profile | D | P | | observed config digest vs requested |
| 20 | Provider completed without validation | P | D | | CandidateResult; runtime completes after validation/review |
| 21 | Controller crash; PID adoption of live App Server | P | D | R | LIVE APP SERVER ADOPTION = NOT_SUPPORTED; terminate; new generation |
| 22 | Host reboot while generation says ACTIVE | | D | R | boot_id mismatch; writer not RELEASED (**untested live**) |
| 23 | Backup/restore resurrects writer | P | D | R | restore invalidates held; epochs abandoned; Attempt LOST |
| 24 | Stale S1 writer locks whole account | P | | | fence is session-realm, not account-wide; S2 allowed |
| 25 | Terminal Attempt erases provider writer uncertainty | P | | | provider state may remain HELD/UNKNOWN |
| 26 | Credential in events | P | D | | redaction; AuthRealmFact forbids tokens |
| 27 | Kitchen-sink prepare() starts process / reads creds | P | | | prepare rejected; validate/stage typed |
| 28 | reconcile() becomes hidden lifecycle authority | P | | | ReconcileObservation forbids Executive judgments |
| 29 | Parked native leader after Phase 1F parent-container | P | | | V1_QUALITY_TRADEOFF_ACCEPTED; fresh aggregation Attempt |
| 30 | Context rotation burns `attempt_limit` | P | | | CARDINALITY_B; rotation = new epoch |
| 31 | Two writers while provider_session_id is NULL | P | D | | pre-bind UNIQUE(session_epoch_id) WHERE held=1 |
| 32 | Adapter mints epoch/generation/turn IDs | P | | | Executive allocates in TX-2/TX-5; start/begin return observations |
| 33 | Timeout retries create a second S1 | P | D | R | OperationId INTENT; EFFECT_UNKNOWN is non-replayable |
| 34 | UNKNOWN process + UNKNOWN effect, launch E2 | P | | R | no new writer; Attempt LOST if recovery expires |
| 35 | Caller tells comparator workspace/auth match | P | | | compare_launch(requested, observed) only |
| 36 | Restore rewrites RELEASED into UNKNOWN | P | | | TX-9 clears authority; historical provider state untouched |
| 37 | Rich OHF overwrites sealed Attempt pid/session | P | | | LEGACY_ONLY fields; execution_mode discriminator |

## Failure taxonomy

Adapter reports a typed `AdapterFailureClass`. It does not own routing.

| Class | Cool pool? | Attempt effect |
|---|---|---|
| QUOTA_OR_RATE_LIMIT | yes | RATE_LIMITED / later retry |
| PROVIDER_CONCURRENCY | maybe | recovery, not code failure |
| AUTH_FAILURE | no | interrupt; never copy auth.json |
| PROCESS_CRASH | no | recovery machine |
| SESSION_MISSING | no | new epoch or LOST depending on placement |
| ACTIVE_WRITER_CONFLICT | no | do not start second writer |
| CAPABILITY_ATTESTATION_FAILURE | no | REFUSE launch |
| WORKSPACE_MISMATCH | no | REFUSE |
| CONFIG_DRIFT | no | re-attest or NEW_ATTEMPT |
| MCP_OR_TOOL_TRANSPORT_FAILURE | no | Attempt error |
| VALIDATION_FAILURE | no | Job/Attempt failed |
| MODEL_OR_WORK_RESULT_FAILURE | no | work failure |
| HUMAN_APPROVAL_REQUIRED | no | wait; not a crash |

## Mandatory scenario results (A–J)

| ID | Result |
|---|---|
| A graceful restart | SAME_ATTEMPT, same epoch, generation 2 resumes S1 after RELEASED |
| B context rotation | SAME_ATTEMPT, epoch 2 / S2, attempt_count unchanged |
| C SIGKILL writer retained | process PROVEN_DEAD, Executive held, provider UNKNOWN then HELD; fence not freed |
| D abandon poisoned S1 | epoch 1 ABANDONED, provider may stay HELD, epoch 2 / S2 CURRENT, same Attempt |
| E opaque id collision | W1/`abc` and W2/`abc` legal |
| F duplicate writer | generation B attach to W1/S1 refused |
| G controller restart | lease adoptable; stdio not; terminate old process; new generation |
| H restored database | generation historical; writer invalidated; session not resumed; Attempt LOST |
| I profile mismatch | LaunchDecision REFUSE; no work turn |
| J unclassified capability | write REFUSE; read-only lab only with explicit lab policy |

## Remaining UNKNOWNs / gates

- Transitive orphan / descendant process cleanup (P0 UNKNOWN).
- Official writer-release/steal API (must not be reverse-engineered).
- Host reboot live behavior.
- ACCOUNT_REALM_ATTESTATION_UNPROVEN.
- Residual `github:*` / `openai-templates:*` / `plugin-management` write-canary.
- Whether `features.plugins=false` exists and removes that residue (optional; not run in R2).
- Native-helper capability ceiling on write-capable Codex.
- Structured MCP item events (not universal).
- Multi-host machine identity (postponed).

## Reviewer brief for R3

Attack the R3 closure, not CARDINALITY_B. Especially:

1. Legacy Attempt pid/session fields are LEGACY_ONLY, not projections.
2. Pre-bind epoch writer fence plus post-bind realm fence.
3. Executive allocates epoch/generation/turn IDs before adapter side effects.
4. OperationId INTENT lives on `events.command_id`; EFFECT_UNKNOWN is fail-closed.
5. `compare_launch` has no caller-supplied security verdicts; served_model None refuses.
6. ReconcileObservation cannot assert resume_safe / executive writer held.
7. Restore preserves historical RELEASED; invalidates authority separately.
8. Optional methods have typed Protocols and OperationIds.
9. EventCursor is ProcessGeneration-scoped.
10. TX-1…TX-11 and the crash-window matrix leave no P1B identity invention.
    TX-10 is the only same-epoch G2 recovery transaction. TX-11 is the only
    post-resume process-identity / APPLIED transaction.

## Reviewer brief for R3.1

Attack TX-10 and OperationId receipt closure. Do not reopen CARDINALITY_B or
rewrite the R1/R2 review artifacts. Especially:

1. Hard-dead G1 + RELEASED + resume_safe → S1/G2 on the same epoch, same Attempt.
2. Hard-dead G1 + HELD/UNKNOWN provider writer → no G2.
3. UNKNOWN process → no G2.
4. Duplicate TX-10 → unique writer and unique OperationId refusal; no provider call.
5. Crash after TX-10 INTENT before resume_session → deterministic
   RETRY_SAME_OPERATION_ON_ALLOCATED_GENERATION vs EFFECT_UNKNOWN_HOLD_GENERATION.
   Never allocate G3 as a replay.
6. Every accepted OperationId permits applied/refused/effect-unknown/reconciled
   receipts under `_COMMAND_ID_RE`. Max accepted length and one-beyond are tests.

## Reviewer brief for R3.2

R3.1 is materially correct. Attack only the resume handoff and TX-11. Do not
reopen CARDINALITY_B, TX-10 entry conditions, or rewrite R1/R2 review artifacts.

1. `resume_session` requires `ProviderSessionHandoff` of already-bound S1.
   `start_session` still does not take a provider session.
2. Adapter must not allocate `provider_session_id` or create a new session
   on resume.
3. TX-11 records G2 process identity + APPLIED; epoch.provider_session_id
   stays S1; no new SessionEpoch; no Attempt consumed.
4. Observed S2 / NULL refuses TX-11 and does not rebind.
5. Incomplete process identity refuses APPLIED.
6. Crash after resume return before TX-11 → EFFECT_UNKNOWN, hold G2, no G3.
7. Matching TX-11 replay is a no-op; different pid is ALREADY_APPLIED_CONFLICT.
8. TX-11 cannot first-bind a NULL epoch session — that remains TX-3.

## Reviewer brief for R3.3

R3.2 is materially correct on handoff and TX-11 topology. Attack only the
durable OperationId target binding and process-identity validity. Do not
reopen CARDINALITY_B, TX-10/TX-11 topology, ProviderSessionHandoff, or
rewrite R1/R2 review artifacts.

1. TX-10 INTENT `events.payload_json` is typed `OperationIntentTarget` on the
   existing Event plane. No sidecar table.
2. The payload binds OperationId to `resume_session`, `attempt_id`,
   `session_epoch_id`, `process_generation_id`, `worker_id`, and already-bound
   `provider_session_id`.
3. TX-11 verifies that receipt against current G2/S1 before APPLIED.
   `intent_committed: bool` is gone from `ResumeBindSnapshot`.
4. TX-10 for G2 + TX-11 using an OperationId for G3, another epoch, another
   session, `start_session`, or another Attempt refuses with
   `INTENT_TARGET_MISMATCH` before APPLIED.
5. Process identity completeness matches Executive law: positive pid, positive
   pgid, nonblank trimmed `process_start_identity`, nonblank trimmed `boot_id`.
   Zero, negative, empty, and whitespace values refuse. v3
   `process_generations` SQL CHECKs match.

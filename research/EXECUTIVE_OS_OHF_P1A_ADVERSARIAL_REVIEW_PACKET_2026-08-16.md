# OHF-P1A-R2 — Adversarial review packet

**Date:** 2026-08-16
**Status:** attack surface after R1 remediation. Not self-acceptance.
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
| 28 | reconcile() becomes hidden lifecycle authority | P | | | ReconcileReport forbids kill/resume/LOST |
| 29 | Parked native leader after Phase 1F parent-container | P | | | V1_QUALITY_TRADEOFF_ACCEPTED; fresh aggregation Attempt |
| 30 | Context rotation burns `attempt_limit` | P | | | CARDINALITY_B; rotation = new epoch |

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

## Reviewer brief for R2

Attack the remediation, not the original 1:1 design. Especially:

1. CARDINALITY_B vs merged `attempt_count`.
2. `(worker_id, provider_session_id)` fence vs `ended_at`.
3. Live App Server adoption deleted.
4. Requested vs observed seal points.
5. Typed adapter: could P1B still invent a method semantic?
6. Restore → LOST and abandoned epochs.
7. Helper enforcement vs prompt policy.
8. No hidden #66/#72 dependency.
9. No `native_session_id` synonym.
10. Consistency table vs schema SQL.

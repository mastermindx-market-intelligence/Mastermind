# OHF-P1A — Adversarial review packet

**Date:** 2026-08-16
**Status:** attack surface for a fresh-context reviewer. Not self-acceptance.

Threats from the P1A commission §44. Each row is prevent / detect / recover
or explicitly UNKNOWN.

Legend: **P** prevent, **D** detect, **R** recover, **U** unknown.

| # | Threat | P | D | R | Notes |
|---|---|---|---|---|---|
| 1 | Same native thread attached by two Executive processes | P | D | R | Writer fence on `(provider, account, native_session_id)`; provider also refuses second writer (P0) |
| 2 | Same native thread reused by two Attempts | P | D | | Unique active Attempt per native id; new Attempt requires fresh session |
| 3 | SIGKILL leaves writer active | | D | R | P0 verified. RECOVERY_BLOCKED_ACTIVE_WRITER; no steal |
| 4 | Stale generation resumes after newer owns session | P | D | | generation_number unique; open-writer partial unique; fence CAS |
| 5 | Resume silently changes model | P | D | | ExecutionProfile digest compare before resume; mismatch → refuse / new Attempt |
| 6 | Resume silently changes sandbox | P | D | | same |
| 7 | Resume silently changes approval policy | P | D | | same |
| 8 | Resume uses wrong cwd/worktree | P | D | | Attempt workspace vs `thread` cwd; mismatch refuse |
| 9 | `CODEX_HOME` points to another account | P | D | | Attempt binds account_label + home identity hash (non-secret); live mode already refuses `~/.codex` |
| 10 | Ambient app appears after Codex update | | D | P | observed digest vs REQUIRED/FORBIDDEN/allowlist; unclassified fails write profile |
| 11 | Bundled skill appears after update | | D | P | same |
| 12 | Project-local skill/plugin injection | | D | P | extraRoots and workspace skills are observed; unclassified/forbidden refuse |
| 13 | Malicious MCP tool injection | | D | P | required MCP allowlist; extra servers unclassified/forbidden |
| 14 | Provider event leaks credentials | P | D | | redaction before persist; refuse to write secret-shaped evidence (P0/P1A probes) |
| 15 | Native fork writes into same worktree concurrently | P | | | V1 helpers read-only; parallel writes are child Jobs + worktrees (1G L13 preserved) |
| 16 | Native helper counted as independent review | P | D | | review must be a different `worker_id` Job; native fork cannot satisfy |
| 17 | Broader-authority session reused under narrower job | P | | | HarnessSession cannot cross Attempts |
| 18 | Narrower session reused after authority widening | P | | | same; widening is a new Attempt + fresh session |
| 19 | Provider says completed but validation has not run | P | D | | adapter returns candidate only; runtime completes after validation |
| 20 | Controller crash during graceful generation handoff | | D | R | QUIESCING generation + adopt_attempt; do not start second writer |
| 21 | Host reboot while generation says ACTIVE | | D | R | boot_id mismatch ⇒ dead generation; resume only if writer-safe (**untested**) |
| 22 | Backup/restore with stale active writer record | P | D | R | restore is whole DB; fence still unique; reconcile expired/lost path; operator may need interrupt (**partially unknown** on live App Server after restore) |

## Failure taxonomy (not conflated with semantic work failure)

| Class | Cool pool? | Attempt effect |
|---|---|---|
| Provider quota exhausted | yes | RATE_LIMITED / later retry |
| Provider concurrency limited | maybe | recovery, not code failure |
| Auth expired/failed | no | interrupt; never copy auth.json |
| Harness process crash | no | recovery machine |
| Native session unavailable | no | recovery / new Attempt |
| Active writer conflict | no | RECOVERY_BLOCKED_ACTIVE_WRITER |
| Tool transport / MCP failure | no | Attempt error |
| Config attestation failure | no | refuse launch |
| Capability missing / forbidden | no | refuse launch |
| Workspace mismatch | no | refuse |
| Validation failure | no | Job/Attempt failed |
| Model/semantic failure | no | work failure |
| Human intervention required | no | APPROVAL_REQUIRED |

## Remaining UNKNOWNs

- Transitive orphan / descendant process cleanup (P0 UNKNOWN; not upgraded).
- Official writer-release/steal API (must not be reverse-engineered).
- Host reboot, controller restart, App Server still-alive-while-controller-restarts (designed, not VERIFIED).
- Whether disabling `features.plugins` removes residual `github:*` /
  `openai-templates:*` without harming fixture MCP.
- Structured MCP item events as an adapter-required capability (P0 false).
- Multi-host `host_id` adoption.
- Whether a future harness without native resume can still meet
  COMMON_REQUIRED (yes by design: resume is OPTIONAL).
- Backup/restore while a real App Server writer is still alive on the host.

## Reviewer brief

Attack especially:

1. Identity boundaries (Attempt vs HarnessSession vs ProcessGeneration vs fork).
2. Schema minimality (no `harness_sessions` table in V1).
3. Single-writer fence vs provider active-writer.
4. Recovery without lock deletion.
5. Capability attestation after partial reduction.
6. Phase 1F-B parent-container vs long-lived native leaders.
7. Source-law: no dependency on unmerged #72.
8. Credential isolation.
9. Native-helper vs independent review.
10. Migration/rollback of NULL historical columns.

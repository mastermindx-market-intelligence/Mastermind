# Portfolio decision outage — diagnosis and recovery

**Operation:** `portfolio-bot-decision-recovery-20260909-sol-001`
**Initial diagnosis pin:** `964bd8e7b30c91e5e83caee0ba37513ba7d07e70`
**Current continuation/procedure pin:** `797cfd0b1001d9dfe6fe9030af80ecdab0e1220d`, Skillpack 1.0.1 / bootstrap 1
**Capability state at diagnosis:** `BROKEN` for daily PM decisions; account and scheduler process remained live.

## User and machine outcome

The US, China, and Hong Kong paper portfolio managers must produce one auditable decision on every scheduled market day. A genuine hold or zero-trade settlement is a decision. A missing model submission is an operational failure and must never appear as a rejected investment proposal or a successful scheduler run.

Completion requires the shared reasoning waterfall to survive a dead primary credential, the scheduler to project the semantic result rather than merely function return, the decision log to distinguish missing decisions, and a real production run to reach a submitted target or explicit governed hold.

## Production evidence

Production release `da6af515c95301377fb5fd8748e374a8948a3540` kept the FastAPI service and APScheduler active while decisions stopped. The US book last had an effective decision on August 25 and then recorded `rejected_no_submission` through September 10. China and Hong Kong showed the same failure pattern beginning August 25.

The September 10 US decision record preserved the initiating error: `Your access token could not be refreshed. Please log out and sign in again.` No typed portfolio tools ran and no submission run ID existed. The VPS Codex state had not refreshed since August 15.

A service-environment, prompt-only canary proved the configured Claude OAuth fallback is usable: six non-cooling slots were present and `claude_code_oauth_2` returned the exact expected response. No portfolio or account tool was exposed to that canary.

## Root cause

The shared waterfall asks Macro's generic authentication classifier whether a failed Codex result may advance to Claude. That classifier recognizes HTTP-shaped `401`/`403` errors but not Codex's local refresh-failure sentence. The waterfall therefore classified the expired login as a non-provider execution failure and stopped before the healthy OAuth rungs.

Two observability defects extended the outage. Each daily scheduler wrapper unconditionally ended `ok` whenever its runner returned without raising, even when the returned target status was `rejected_no_submission`. The dashboard then rendered that status as `NOT APPLIED / REJECTED`, implying a deliberate proposal rather than no proposal at all.

## Bounded repair

1. Classify only the exact Codex access-token refresh failure as an authentication failure, preserving the no-replay rule for tool and runtime failures. The existing waterfall then cools Codex and advances to the existing Claude OAuth pool.
2. Translate each Brain runner result into the existing run ledger's `ok`, `warn`, `skip`, or `error` states. Missing submissions, malformed envelopes, inconsistent accepted states, and publication failures become `FREEZE` errors with a closed safe reason; intentional cost caps and migration waits remain skips.
3. Project `last_reason` and `last_target_status` through the existing scheduler-health consumer and display the closed reason on the scheduler table without exposing raw provider errors. A current error outranks any older skip timestamp when the table chooses its state indicator.
4. Apply the same semantic outcome classifier to authenticated manual US, China, and Hong Kong runs, in both wait and background modes. Wait-mode receipts expose safe lifecycle fields and tolerate a malformed runner envelope without emitting duplicate completion events.
5. Present `rejected_no_submission` as `DECISION MISSING — RECOVERY REQUIRED`; keep governance rejection, queued target, settled no-trade, and verified fills distinct.

No provider pool, scheduler, retry loop, lifecycle, account, position, execution, or state store is added. The deterministic allocator and all paper-trading authority boundaries remain unchanged.

## Acceptance and production proof

Source acceptance requires the exact production error to trigger OAuth fallback; a non-provider failure must still stop without replay; all three real scheduler wrappers and authenticated manual-run paths must project missing submissions as `error/FREEZE`; malformed manual results must produce one safe completion receipt; accepted queued and executed zero-fill results must remain `ok`; and the JavaScript presentation must preserve the four distinct lifecycle meanings.

Deployment must use the exact merged protected-master SHA through the existing transactional deployer. The rollback-package prerequisite is now resolved by protected merge `797cfd0b1001d9dfe6fe9030af80ecdab0e1220d`, which restores `common/` and `integrations/` alongside the other release roots after a failed deploy.

Production acceptance requires:

- exact-SHA health and scheduler readiness after restart;
- an actual prompt-only call through the deployed shared waterfall showing Codex success or an identified OAuth fallback;
- one real US scheduled/manual paper PM run through the normal lock, context, submission, publication, and ledger path;
- a submitted queued target, verified settlement, or explicit governed no-trade decision—not a forced trade;
- decision-log and scheduler-health readback showing the true lifecycle result;
- no replay of any prior proposal and no mutation of archived books.

Asia books should be proven through their next lawful post-close cycles unless a safe same-date non-settling path is available. A synthetic or backdated trade is not acceptance.

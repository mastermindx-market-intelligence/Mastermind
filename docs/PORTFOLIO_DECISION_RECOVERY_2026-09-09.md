# Portfolio decision outage — diagnosis and recovery

**Operation:** `portfolio-bot-decision-recovery-20260909-sol-001`
**Initial diagnosis pin:** `964bd8e7b30c91e5e83caee0ba37513ba7d07e70`
**Current continuation/procedure pin:** protected `master` `9e75a2175100564e8d2805c6f995f4b5eeb0f44e`, Skillpack 1.0.1 / bootstrap 1
**Capability state at diagnosis:** `BROKEN` for daily PM decisions; account and scheduler process remained live.
**US production result:** `PROVEN_LIVE` on release `e61f2951136bdc03a7ec2f5f12f960af26656a4c`.
**Regional result:** the shared US/CN/HK repair is deployed; China and Hong Kong remain `BUILT_NOT_PROVEN` until their first lawful post-deploy decision cycles are read back.

## User and machine outcome

The US, China, and Hong Kong paper portfolio managers must produce one auditable decision on every scheduled market day. A genuine hold or zero-trade settlement is a decision. A missing model submission is an operational failure and must never appear as a rejected investment proposal or a successful scheduler run.

Completion requires the shared reasoning waterfall to survive a dead primary credential, the scheduler to project the semantic result rather than merely function return, the decision log to distinguish missing decisions, and a real production run to reach a submitted target or explicit governed hold.

## Production evidence

Production release `da6af515c95301377fb5fd8748e374a8948a3540` kept the FastAPI service and APScheduler active while decisions stopped. The US book last had an effective decision on August 25 and then recorded `rejected_no_submission` through September 10. China and Hong Kong showed the same failure pattern beginning August 25.

The September 10 US decision record preserved the initiating error: `Your access token could not be refreshed. Please log out and sign in again.` No typed portfolio tools ran and no submission run ID existed. The VPS Codex state had not refreshed since August 15.

A service-environment, prompt-only canary proved the configured Claude OAuth fallback was usable. No portfolio or account tool was exposed to that canary.

## Root cause

The shared waterfall asks Macro's generic authentication classifier whether a failed Codex result may advance to Claude. That classifier recognized HTTP-shaped `401`/`403` errors but not Codex's local refresh-failure sentence. The waterfall therefore classified the expired login as a non-provider execution failure and stopped before the healthy OAuth rungs.

Two observability defects extended the outage. Each daily scheduler wrapper unconditionally ended `ok` whenever its runner returned without raising, even when the returned target status was `rejected_no_submission`. The dashboard then rendered that status as `NOT APPLIED / REJECTED`, implying a deliberate proposal rather than no proposal at all.

## Bounded repair

1. Classify only the exact Codex access-token refresh failure as an authentication failure, preserving the no-replay rule for tool and runtime failures. The existing waterfall then cools Codex and advances to the existing Claude OAuth pool.
2. Translate each Brain runner result into the existing run ledger's `ok`, `warn`, `skip`, or `error` states. Missing submissions, malformed envelopes, inconsistent accepted states, and publication failures become `FREEZE` errors with a closed safe reason; intentional cost caps and migration waits remain skips.
3. Project `last_reason` and `last_target_status` through the existing scheduler-health consumer and display the closed reason on the scheduler table without exposing raw provider errors. A current error outranks any older skip timestamp when the table chooses its state indicator.
4. Apply the same semantic outcome classifier to authenticated manual US, China, and Hong Kong runs, in both wait and background modes. Wait-mode receipts expose safe lifecycle fields and tolerate a malformed runner envelope without emitting duplicate completion events.
5. Present `rejected_no_submission` as `DECISION MISSING — RECOVERY REQUIRED`; keep governance rejection, queued target, settled no-trade, and verified fills distinct.

No provider pool, scheduler, retry loop, lifecycle, account, position, execution, or state store was added. The deterministic allocator and all paper-trading authority boundaries remain unchanged.

## Source acceptance

Implementation PR `#562` merged as protected commit `e61f2951136bdc03a7ec2f5f12f960af26656a4c`. Exact-head CI, security analysis, focused three-book scheduler/manual-path suites, and adversarial mutations passed. The source proof showed that:

- the exact production refresh failure authorizes Codex-to-OAuth fallback;
- non-provider failures still stop without replay;
- all three scheduled and authenticated manual paths project missing submissions as `error / FREEZE`;
- execution failures remain errors rather than governance warnings;
- accepted queued and settled zero-fill outcomes remain distinct valid decisions;
- the browser preserves queued, missing, rejected, and executed lifecycle meanings.

## Production acceptance — 2026-09-12

The authoritative VPS was tested through the existing `VPS_DEPLOY_KEY` operator lane. No prior proposal was replayed, no manual portfolio run was issued, and no account, holding, target, fill, or archived book was mutated.

### Exact release and runtime

- deployed marker: `e61f2951136bdc03a7ec2f5f12f960af26656a4c`;
- `/health`: HTTP 200, `status=ok`;
- reasoning policy: `codex_first_claude_oauth_fallback`, policy valid;
- scheduler running and scheduled runtime healthy;
- public health still reports Codex unavailable and `claude_oauth_fallback` as the active reasoning primary.

### Deployed provider canary

A prompt-only, no-tools, no-account call traversed the deployed shared provider waterfall and succeeded through provider `oauth` with backend `sdk`. The canary did not expose portfolio tools or publish raw provider errors.

### Genuine scheduled US decision

The normal `autonomous_daily` job ran on September 11 without manual intervention:

- started `2026-09-11T23:10:00+00:00`;
- finished `2026-09-11T23:16:27+00:00`;
- ledger `last_status=ok`;
- `last_reason=null`;
- `last_target_status=queued`;
- next run `2026-09-14T23:10:00+00:00`.

The durable decision readback showed:

- `asof=2026-09-11`;
- `target_status=queued`;
- `decision_effective=true`;
- `execution_evidence_status=none`, correctly indicating that the decision is queued rather than falsely claiming a fill.

This satisfies the acceptance law: the repaired real scheduler/model/submission/publication path produced an effective queued paper decision. A forced trade was not required and was not attempted.

### Browser-visible proof

A headless browser loaded the exact served production dashboard and consumed the real `/api/decisions`, `/api/scheduler`, and portfolio APIs through a read-only SSH fetch route. It observed:

- the Daily Decision Log rendered;
- the September 11 decision rendered as `QUEUED — NOT YET EXECUTED`;
- scheduler and decision API readbacks matched the durable state above;
- the shipped `DECISION MISSING — RECOVERY REQUIRED` contract remained present for historical missing submissions;
- screenshot receipt SHA-256 `e1620cc00d2b15ea22636cf2e15c278c3312caf7cf23a6689ada543363d718ae`, 275,394 bytes.

The browser receipt is GitHub Actions run `34670042191`, job `103489565893`. The earlier port-forward attempt failed before reaching the application and had no portfolio effect; it was superseded by the successful read-only fetch proof.

## Capability ruling

### US Mastermind Portfolio daily-decision path — `PROVEN_LIVE`

The original failure mode is repaired in production. An expired Codex login no longer suppresses the healthy Claude OAuth fallback, a real scheduled decision completed and published, scheduler truth reflects the semantic outcome, and the user-visible dashboard renders the correct queued lifecycle state.

### China and Hong Kong daily-decision paths — `BUILT_NOT_PROVEN`

They share the repaired provider and semantic-ledger code, but their first lawful post-deploy cycles have not yet been accepted here. Do not synthesize, backdate, force a trade, or reuse the US proof as regional production proof. Their next post-close cycles are the exact continuation gate.

## Recurrence prevention

The repair prevents silent recurrence in four layers:

1. the provider waterfall now advances on the known local Codex refresh failure;
2. a missing submission becomes a hard `FREEZE` ledger error rather than scheduler success;
3. scheduler health exposes the closed reason and target status;
4. the dashboard labels missing decisions as recovery-required instead of investment rejection.

A separate off-host dead-man should remain read-only and use the existing GitHub Actions/VPS operator plane; it must alert on stale or failed US/CN/HK decision cycles without introducing a second scheduler, retry plane, portfolio writer, or state store.

## Exact continuation

1. Accept the next lawful China and Hong Kong post-close runs only after exact release, scheduler, decision-log, and served lifecycle readbacks match the US proof standard.
2. Add the read-only off-host decision dead-man to the existing GitHub Actions monitoring plane so future missing submissions page an operator instead of relying on dashboard inspection.
3. Keep all manual run, replay, forced-trade, archived-book mutation, and synthetic/backdated proof paths disarmed.

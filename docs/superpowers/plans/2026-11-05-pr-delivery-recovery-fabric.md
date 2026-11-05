# PR delivery recovery — bounded Fabric workers and protected releases

Status: active *source plan*, not installed automation or Executive admission.
Operation: `pr-delivery-recovery-20261105-sol-001`.
Owner: assigned Sol CEO; GitHub source and CI are authoritative. Protected Mastermind law pin: `cb390bfc5a4b85a59a1005bfd3824305a5a4bfee` (Skillpack v1.0.1, bootstrap major 1).
Observation: 2026-11-05 UTC; GitHub org search reported **1,482 open PRs**, **1,033 Draft**. This is a snapshot, not 1,033 completed changes.

## Outcome / DONE_WHEN

Sustain a *safe* GitHub-to-Fabric delivery loop that converts qualified, unfinished existing PRs into protected merged outcomes, without pushing risky drafts or claiming production deployment from green checks.

1. Machine-readable census across Mastermind, Macro and Terminal categorizes exact PR/head/author/Draft state, declared HOLD, active writer/worker, changed paths, local qualification, required checks, native review/CODEOWNERS, conflicts/base compatibility, and target consumer.
2. Bounded independent workers return source-linked findings and repairs under the **original PR/branch/effect carrier**. No duplicate PR, PR author, queue, authentication, Job/Attempt/Worker or reviewer registry. Actual admitted work and result consumption are separately receipted.
3. Readiness policy: `Draft` remains for incomplete or explicitly held changes; `Ready` is eligible only after evidence of stable candidate, affected tests and no binding Draft hold. CI *pending* alone is not a Draft hold. The existing `github_review_intent.py` refuses `review_requested` while Draft; never request before Ready and assume it replays.
4. Protected release uses **existing** per-repository policy: Macro's scheduled `merge-on-green` (opt-in, existing hold/semantic/release gates) and native GitHub queue/rules where actually enabled. No blanket arming, automatic un-draft of 1,033 PRs, forced merge, author self-approval, admin bypass or deploy. No new controller.
5. Exact merged SHA, native integrated checks and any owed live user path are recorded independently of PR Draft, CI, merge, or watcher status. Measure merged/closed-superseded/accepted outcomes and time-to-release, not PRs created.

## Canonical integration and active collisions

- `WS:CI-MERGE-CONTROL-PLANE`, Macro `.github/workflows/merge-on-green.yml` and `scripts/merge_on_green.py` own the existing Macro sweeper, rate/backpressure and merge safety.
- [Mastermind #2064](https://github.com/mastermindx-market-intelligence/Mastermind/pull/2064) owns live review-risk/FAST-STANDARD policy, Project instructions and CI review-parity files. Do **not** shadow-edit them.
- [Mastermind #2066](https://github.com/mastermindx-market-intelligence/Mastermind/pull/2066) owns the in-flight Web/Fabric durable orchestration, finite watcher and Wake continuation integration; preserve its child `web-fabric-autonomy-finite-repair-20261105-c3-02`. Do **not** duplicate or replace it.
- [Mastermind #2063](https://github.com/mastermindx-market-intelligence/Mastermind/pull/2063) owns browser attention/watch paths. [Macro #10746](https://github.com/mastermindx-market-intelligence/macro/pull/10746) owns Macro source review-policy entrypoints. These are independent incumbents.
- Current GitHub login observed `MastermindX1`; login alone grants no alternate identity, reviewer independence, CI bypass or release authority. Source branches/holds remain with their real current owners.
- Executive reader reported `backend_unavailable` on 2026-11-05 UTC; do not infer Runtime admission or a daemon from GitHub/Fabric capability docs. The attended Fabric adapter returned `adapter_available=true`, but worker admission/START were UNPROBED.

## Phases and bounded tasks (editorial only; not Executive lifecycle state)

| ID | Objective / dependency | Actual completion evidence |
| --- | --- | --- |
| P0 | Freeze source/authority, audit candidate risk and collision; before worker launch | This plan and protected pin read back from GitHub, no active incumbent overwritten |
| P1.M | **Macro census worker**, read-only, excluding known explicit HOLDS and active writer effects | Exact-head 8–15 candidate PR table; separate qualified/CI-red/review/held/uncertain with source URLs and safest next owner action |
| P1.T | **Terminal census worker**, read-only, independent of Macro | Same; Terminal native rules and exact PR checks, no assumed Macro label |
| P1.S | **Mastermind census/integration worker**, read-only, distinct from #2064/#2066 owners | Same plus evidence of current Review/Draft ingress and already-installed webhook host vs SPEC_ONLY |
| P2 | Sol adjudicates worker returns; choose first eligible original-PR repair or metadata transition; source custody reviewed | One real original PR/head advanced with before/after evidence, no duplicate worker/effect |
| P3 | Extend **incumbent** GitHub/Executive ingress only if confirmed missing behavior and disjoint owner/custody; build tests | Webhook or scheduled native checks classify and return actionable state; conservative holds; original queue owns writes |
| P4 | Qualify existing protected merge route on a small, explicitly authorized pilot, no bulk arming | Real native rule/CI/review/hold readback, exact merged SHA and consumer proof when owed |
| P5 | Measure delivery throughput/backlog aging by repo, preserve existing owner recovery | Repeated real merged outcomes with no misclassified hold, accidental duplicate, or false release claim |

## Initial worker packet / budget

`ROUTE`: lowest-scarce admitted paid Fabric workers, AUTO model/pool selection; task class `census`, C1 or C2 on actual complexity. `WHY NOT FABLE`: frozen read-only repository/CI inventory and candidate classification require no principal architectural judgment. `FRONTIER_WITNESS`: none.

Parent operation/root `pr-delivery-recovery-20261105-sol-001`; children must preserve root and actual parent identity. Fabric handles are *not* Executive Job IDs. No provider/model/host pin, no inferred credentials or quota. Reserve review/repair capacity; start only as many independent workers as can actually be admitted. Their first task is read-only and may not mark Ready, relabel, request reviews, push, merge, deploy, spend or mutate any source/PR. If worker requires modifying GitHub access, it must return the exact change proposal for original-source custody/admission first.

## Draft classification contract

`INCOMPLETE` — missing source/test/consumer acceptance; name owner and repair.
`HELD` — explicit security/release/research/test/prod/stacked hold; do not transition.
`REVIEWABLE` — stable scoped candidate, local proof, no binding Draft hold; CI may be pending; Ready candidate only after current source/custody readback.
`CI_RED` — actual required check failure; exact run/logs; repair original carrier.
`REVIEW_BLOCKED` — actually mandated native/CODEOWNERS independent approval absent, or earlier Draft-only review request never admitted.
`INTEGRATION_BLOCKED` — real conflict/material base delta or required integrated gate missing, not just ancestry.
`UNKNOWN` — insufficient current-head source, lease, installed host or release-policy evidence; no optimistic release action.
`SUPERSEDED_CANDIDATE` — exact later merged equivalent proven; classify for independent owner disposition, no automatic closure.

Each candidate record must include `repo`, `PR`, `head_sha`, `updated_at`, `draft`, `classification`, `hold_quote/link`, `required_check_summary`, `formal_review_summary`, `writer/effect_uncertainty`, `next_owner_action`, and `evidence_urls`. Missing evidence stays UNKNOWN.

## Real-path acceptance / rollback

Initial source plan is safe even if Fabric or Executive is down. A PR alone is not an operating continuous-delivery system. Before activation, verify webhook/schedule installed, proven worker admission + result + parent consumption, safe rate/budget/backpressure, GitHub native rule checks, negative tests (held, draft, stale head, conflict, red CI, review revoked, API unavailable, interrupted effect), and one positive exact-head protected landing. If current checks refuse, leave source open or Draft with exact blocker, advance independent work, and never bypass safeguards.

This plan does not change production config, deploy, trigger arbitrary CI, create a new queue/app, or grant automatic permission to release held PRs.

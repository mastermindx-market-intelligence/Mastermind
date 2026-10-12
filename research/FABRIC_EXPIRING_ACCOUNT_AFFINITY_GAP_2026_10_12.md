# Fabric R31 expiring-pool vs actual account binding: qualified source falsifier

**2026-10-12 UTC — Chairman assignment, current selector continuation PR #1365.**  
Disposition: VERIFIED SOURCE-LEVEL ACCOUNT-AFFINITY GAP / HERMETIC FALSIFIER, **NO LIVE LEASE MODIFICATION**.  
Owners: existing Model Router suitability, existing Provider Control/Capacity account-window evidence and ranking, existing Subagent Fabric lease broker atomic account claim. No new scheduler, quota source, registry, lease, retry or identity authority.

## What works and where it stops

The installed \`ext/pick.py\` has R31 \`burn_down_urgent()\`, \`_glm_account_weekly_windows()\` and \`_glm_burn_down_window()\`. For GLM it reads provider-authoritative per-account weekly remaining percentage and reset time, chooses the qualifying *earliest-reset account-window pair*, and may promote the GLM **pool** before other eligible pools when inside configured 36-hour/15%-remaining urgency thresholds. Stale, past-due and incomplete observations are refused as urgency. This is sound **pool-level advisory** behavior, not a binding to that account.

Installed \`ext/remote_sub.sh\` calls \`lease_broker acquire --pool <pool> --model <model> --host <host> ...\` with **no --account** in its normal remote path. It only *reads* the resulting \`ACCOUNT=...\` from the broker and forwards that selected account to the worker.

Installed \`ext/lease_broker.py\` \`Broker._pick_account()\` selects a grantable account with current model/concurrency caps. When no preferred account is supplied, it sorts ordinary non-Bailian pools by \`(held, -effective_cap, account_name)\`. For Bailian, its tie-break also considers grant history. **It does not read reset timestamps/remaining weekly quota to rank GLM accounts**. So a GLM pool promoted due to account B's expiring window can be claimed on non-expiring account A. A successful model/pool/host preview or admission does not itself prove the requested expiring allowance was consumed.

Latest observed \`lease_broker.py\` source SHA256: \`c17558441d408ed743ef3e282b50db1f4cf8926aad9cca3977ceb867c0d8eb4f\`. The installed account-policy source \`orch/fabric/accounts.yaml\` SHA256: \`e94f7e4a3be9cf4abc0ead1c087dfeee82800a9a46b9e9c91f2a925811436de4\`.

## Provider-free falsifier executed against the real production Broker method

This used **no database, lease, model call, provider key, reservation, runtime mutation or process start**: construct a synthetic, method-only Broker instance with two grantable accounts, equal available concurrency/cap/model compatibility:

~~~python
from lease_broker import Broker

broker = object.__new__(Broker)
broker.grantable_accounts = lambda pool: [
    {"name": "alpha_far_reset", "reset_at": "2026-10-25T00:00:00Z",
     "remaining_pct": 70, "_eff_cap": 4},
    {"name": "zeta_near_reset", "reset_at": "2026-10-12T05:50:00Z",
     "remaining_pct": 70, "_eff_cap": 4},
]
broker.account_model_cap = lambda pool, acct, model: None
broker._account_held = lambda conn, pool, name: 0
broker.provider_name = lambda pool: "glm"

selected = broker._pick_account(None, "glm", None, "glm-5.3-flash")
assert selected == "alpha_far_reset"  # observed incumbent result
assert selected != "zeta_near_reset"   # demonstrated expiry-affinity gap
~~~

Direct observed result: \`BROKER_PICKS: alpha_far_reset\`, even though zeta's allowance resets first. This **does not establish that any particular real account has missed a reset**. It proves the current algorithm does not enforce the claimed expiring-account objective.

## Correct owner integration contract

Preserve current hard authority, task complexity/tier, model/harness capability, reviewer independence, account/host credential qualification, stale-event refusal and original-root/effect fencing. Do not route expensive work merely to consume a subscription.

1. Use the **existing Provider Control / Capacity owner** to supply a structured, provenance-bound per-account-per-model quota window snapshot: observed_at, provider/account/realm, model eligibility, remaining quota/capacity, reset_at, window kind (5h, weekly, monthly), confidence/freshness, host compatibility, reserved floors, and provider-issued error/exhausted states. Preserve 5h and weekly accounting separately. No user-defined pool/model labels can author quota evidence.
2. Calculate the *qualified* account-level urgency from a single paired fresh remaining/reset observation. Do not combine pool A's reset with pool B's balance, double-count simultaneous windows, treat a stale reset as future, or make 'unknown' into unused capacity.
3. In the incumbent claim/placement path, rank qualified account+model+host candidates with urgency **only inside the lawful task-fit/model ceiling**. Bind the selected exact account/model/host to the same existing claim and recheck the account at the atomic source-of-truth lease boundary. The broker already has a preferred-account parameter, but a caller-supplied preference alone is not trusted admission evidence; preserve canonical ownership, lock and replay fences.
4. If the candidate goes stale between preview and claim or loses model/host eligibility, refuse/replan **before START** under the same authorized original logical operation. After START or EFFECT_UNKNOWN no automatic host/account switch or double launch.
5. Record the actual attested served model, account, host and window generation in existing claim/return evidence, and show whether the expiring allocation was in fact consumed. A preview marked \`burn_down_urgent\` by itself is not success.
6. Reuse ongoing source-owned Macro #7116 (multi-window quota economics), Macro #7142 (provider-account selector) and Mastermind #1247/#1248 (Capacity/model-planning source candidates) only after their actual review/release/adoption gates; do not merge local unpublished/unowned repairs blindly.

## Required proof before saying 'expiration-aware account routing live'

Provider-free unit negatives: stale reset, past reset, missing remaining, mismatched provider/account source, ambiguous shared model consumption, invalid host realm, same-reviewer pool, high-value scarce capability reserved, zero headroom, concurrent two-claim contention, quota read failure, newly revoked account, frozen post-START binding, and effect-unknown response loss.

Positive tests: two accounts with equal task capability but different weekly deadlines; planner chooses near reset, **broker claims same near-reset account** (not just pool); exact run/lease receipt identifies account/model/host; completion/usage observation reflects that account; no duplicate child after an interrupted response; one real bounded task returns a validated result to its original parent.

**Source boundary:** No installed \`lease_broker.py\`, \`remote_sub.sh\`, account config or live provider quota state was changed in this investigation. This is a cross-owner integration requirement, not an authority transfer. The F04 failed operation discussed in \`FABRIC_SELECTOR_F04_COLLISION_CONTINUATION_2026_10_12.md\` is distinct and must not be retried or settled to prove quota behavior.

## Associated practical selector candidate

In PR #1365, new source-only \`fabric_task\` preview/request host selection and exact registered worker model selection passed **179** combined isolated tests. They do not change the account claimant; therefore they are **not end-to-end proof of this account-affinity requirement**. The installed Grok screenshot priority was observed live earlier, but it was a pool-level dated window and not proof of arbitrary multi-account expiry placement.

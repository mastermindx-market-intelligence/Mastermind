# Cursor Grok monthly judgment cohort — source candidate, 2026-10-17

## Why this exists

The installed October 14 quota-fallback release already supports *explicit*
weekly Grok Build -> Cursor `cursor-grok-4.6-high` before START, with one
accepted native Cursor worker. It does **not** promise Cursor an ordinary task
share. After Grok weekly exhaustion, judgment selection can still take an
available GLM worker first; C0/C1 labor is intentionally cheaper-first.

The October 17 Cursor screenshot reports 158.9M **included** tokens over the
selected seven days, including sizable Cursor-Grok use on October 14–15.
That number proves consumption, not Fabric attribution, remaining monthly
credits, percentage-of-plan capacity or dispatch conversion.

This overlay adds an optional, *bounded prestart judgment share*, not a new
fallback system or account/quota tracker. It is **not** an X Subscription
workaround: current Cursor documentation states that X Subscription plans share
one weekly Grok/Cursor pool, whereas legacy Cursor plans retain separate monthly
usage. Whether this specific account is legacy is presently UNKNOWN.

Official sources (read 2026-10-17):
- https://prod.cursor.com/help/models-and-usage/usage-limits
- https://cursor.com/docs/account/pricing/legacy-cursor-plans

## Proposed behavior

The patch inserts exactly one branch in the incumbent `pick.py` before its
normal judgment-only selector. A cohort may use the **existing** qualified
`_cursor_grok_after_quota` function rather than bypassing any hard filter.

The existing `routing` policy may opt in with:

```yaml
routing:
  cursor_grok_monthly_share:
    enabled: false   # never enable on assumed plan/remaining usage
    percent: 15
    task_classes: [operator, repair]
```

- Disabled by default. Strict `enabled: true`, integer percentage **1–20**
  and an explicit subset of **operator/repair** classes are required.
- **Also requires** a fresh bounded `cursor_entitlement` in the same protected
  policy, with exact fields: `plan_type: legacy_independent_monthly`,
  `source: account_dashboard_readback`, `on_demand_enabled: false`,
  numeric `remaining_pct >= 20`, `observed_at` and `reset_at` in UTC ISO-8601
  ending `Z`. Observation age must be **0–6 hours**, reset must be future and
  within 35 days of observation. Unknown/missing/expired evidence, new
  shared-weekly plans, top-up-on-demand eligibility or a depleted independent
  pool **disable the cohort**. This is bounded manual account evidence, not
  fabricated provider API telemetry.
- Only a proven active `GROK_EXHAUSTED` marker selects the cohort.
  A quota screenshot, old sentinel, or unknown reset time must be separately
  reconciled by the incumbent quota owner; this overlay does not infer one.
- Uses deterministic SHA-256 on an existing logical `route_key` and task class
  to sample independent tasks, not repeated evaluations. No new ledger,
  counters, queue, leases, credentials or state.
- Only explicitly classified **C2_COMPLEX_BOUNDED** judgment is eligible;
  C0/C1, C3, unknown complexity, explicit `prefer` and missing/invalid
  route keys **never** enter this cohort.
- The sampler deliberately excludes `reviewer`, `review`, `audit` and `verify`:
  the historical source fixture evaluates `audit`/`review`/`verify` on the
  execute path, while `reviewer` does not inherit R33's subject-author
  independence checks. An override must not claim independent review proof.
- All admitted candidates still pass incumbent role, subject/reviewer
  independence, model needs, capacity, host, account, economics and native
  route gates. A failed Cursor candidate falls back to the original judgment
  selector. No started worker can be migrated.
- Grok 4.7 and Cursor's qualified Grok 4.6 alias are **not** declared
  equivalent. The existing alias/proven capability remains the only admitted
  one; any model downgrade requires its own qualification.
- Never routes C0/C1 labor merely to burn monthly Cursor quota.
- Does not change Grok Build's weekly reset, Cursor's plan, or on-demand billing.

## Integration and ownership

**SOURCE ONLY / NOT INSTALLED / NO LIVE PROVIDER OR HOST EFFECT.** The current
codeholder of `pick.py` and the V5 advisory quota router (#1441) must compose
this isolated overlay onto its **exact live-source preimage** after reconciling
source writers and #1443 routing changes. Do not apply this candidate blindly
to the installed native kit or override a failed preimage guard.

Before enabling any nonzero share, require a current *actual* Cursor legacy
entitlement/remaining-budget observation and proof that paid on-demand is off,
then record the above bounded policy fields with source attribution and observe
a safe limit/cap and read-only routing cohort preview. Cursor's UI "Included"
tokens alone do not certify any of this.
Confirm the real Grok Build weekly reset independently of the Grok Bot meter.
Do not auto-charge credits to make sampling succeed.

## Acceptance / falsifiers

1. Hermetic source fixture: `python3 -m unittest tests/test_native_fabric_cursor_grok_monthly_share_20261017.py -v`.
   Patch applies with `--fuzz=0` and AST compiles, with distribution,
   policy, no-review/no-labor/C3, shared-weekly-plan, stale/manual-quota,
   exhaustion and preference gates.
2. Prestart route previews on the *actual* installed source: bounded
   percentage of distinct eligible judgment route keys choose
   `POOL=cursor MODEL=cursor-grok-4.6-high` with
   `ROUTE_ALLOC=cursor_grok_monthly_share` only when all other gates pass.
   No cohort `POOL=cursor` on unknown/stale Grok exhaustion, reviewer-class
   work, failed eligibility, or C0/C1 labor.
3. One admitted actual worker START, COMPLETED result consumed by its parent,
   settled processes and Cursor provider usage attributed to that operation.
   A successful selection/CI check or the Cursor UI graph alone is not enough.
4. Observe no duplicate started work, cross-provider review bias, additional
   on-demand spend, or reset-misclassification. On any material failure,
   retain the original policy and disable the optional cohort.

Existing fallback release provenance:
`integrations/session_bridge/pool_quota_fallback/SOURCE_QUALIFICATION.json`.
Existing normal routing reset receipt:
`integrations/session_bridge/grok_expiring_priority/NORMAL_ROUTING_RECEIPT.json`.

This branch intentionally does not alter #1441, #1443 or the live M2's
`pools.yaml`, `pick.py`, pending controller attempts or worker state.

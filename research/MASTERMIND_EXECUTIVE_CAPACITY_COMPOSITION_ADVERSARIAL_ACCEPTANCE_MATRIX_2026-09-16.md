# Adversarial acceptance matrix for the resource-composition contract — PROPOSAL

STATUS: PROPOSAL — HOLD-FOR-SOL
Census anchor: master@0fe8074ff953b2ced9025ed40f0f66019c759967. Every EXISTS / PARTIAL row below carries a
`file:line` receipt that was read at that commit and re-verified by this lane; every MISSING row names the search
that bounds the claim. Nothing is asserted from memory.
Companion: `research/MASTERMIND_EXECUTIVE_CAPACITY_RESOURCE_COMPOSITION_CONTRACT_2026-09-16.md` (the contract).
Source of the 20 classes: Sol capacity-routing architecture ruling (R35) §23, verbatim ordering preserved.

---

## 0. How to read this

R35 §23 requires that "the production acceptance suite must falsify at least these failure classes" **before live
routing**. This matrix is the map from each class to a test that would falsify it, its owner, the fixture shape it
needs, and what exists today.

Status vocabulary, used strictly:

- **EXISTS** — a named test at master falsifies this class *as stated*.
- **PARTIAL** — master carries a real defence, but it is at a different layer, a different object, or a weaker
  scope than the class requires. The row says exactly what the gap is. A PARTIAL is not a pass.
- **MISSING** — no test falsifies this class, and the searches that ground that claim are named. Absence is
  reported with bounds, never bare.

No class of twenty is fully EXISTS; eight are PARTIAL and twelve are MISSING. That distribution is the expected
consequence of the contract not existing yet: twelve of the classes are statements *about a resource tree*, and
at this pin there is no tree — `estimated_startable_jobs` arrives as a scalar
(`control_plane/capacity_economics_projection.py:83`), so there is nothing for a composition test to attack.
**These tests are not writable before the contract is frozen.** That ordering is the reason step A precedes
step B–H, not an argument that the gap is unimportant.

A general note on fixture shape: every fixture below must be **hermetic** — no provider network call, no
credential read, no live account. Master's existing owner facts are already fixture-only and refuse direct
minting (`ops/executive_os/capacity_owner_facts.py:44`, `ops/executive_os/provider_realm_facts.py:40`), so the
composition fixtures must be built through the same seams rather than by constructing typed facts directly.

---

## 1. The matrix

### Class 1 — same subscription visible on two hosts does not double capacity
- **Proposed test**: `test_two_host_refs_in_one_capability_domain_resolve_to_one_resource_identity`
- **Owner**: Provider Control resource-identity minting (contract §2.1), composed with the Family-B realm owner.
- **Fixture**: two `host_ref` values bound to one `capacity_capability_id`, each carrying its own
  `realm_generation`; one resource observation of 10,000 units. Assert `avail` of the union is 10,000, not 20,000,
  and that both hosts resolve to the same `resource_id`.
- **Status at master**: **MISSING**. Bounded by: `rg -n "capacity_capability_id|host_ref" control_plane ops config
  integrations tests` — `capacity_capability_id` occurs once
  (`ops/executive_os/capacity_broker_topology.py:205`), `host_ref` only in recovery
  (`control_plane/executive_recovery_readiness.py:492`). The joined identity that would make this test meaningful
  lives in Family-B (#662, OPEN/DRAFT, B0 unaccepted), not at master.

### Class 2 — same shared quota exposed through several model views does not multiply capacity
- **Proposed test**: `test_model_views_over_one_resource_do_not_sum_into_available_capacity`
- **Owner**: Provider Control view/resource distinction (contract §3.2 BUDGET/CEILING roles, §5.3 views).
- **Fixture**: one `minimax_plan_weekly` leaf at 100,000 units with two view rows (M3: 60,000; M2.7: 40,000),
  `independence: UNPROVEN`. Assert `avail == 100000` and that a mutant which sums the views is killed. Second
  case: GLM `ALL_OF(BUDGET 5h, BUDGET weekly)` — assert `min`, and that a summing mutant is killed.
- **Status at master**: **PARTIAL**. `tests/test_provider_model_economics.py:91`
  (`test_subscription_burn_method_is_declared_without_quota_balances`) pins that the catalog declares a burn
  *method* and carries no balances — which prevents the catalog from becoming a wallet, but says nothing about
  views published by a live parser. No view/resource distinction exists to test. Bounded by `rg -n -i
  "wallet|model view|independent.*resource" control_plane ops tests`.

### Class 3 — generic/hypothetical seat → shared-pack PARTITIONED overflow debits exactly once
- **Proposed test**: `test_ordered_spill_partitions_one_operation_cost_across_stages_exactly_once`
- **Owner**: the composition evaluator (contract §3.3, §4.1, worked at §10).
- **Fixture**: the §10 state — seat 3,000 / pack_A 25,000 / pack_B 600,000 / member cap 40,000, cohort cost
  10,000. Assert the four-job debit walk of §10.3 exactly, including the straddling job 3 (8,000 from pack_A,
  2,000 from pack_B), and assert the invariant `Σ per-resource debits == n_jobs × cost`. Mutants to kill:
  debit-full-cost-from-every-stage; debit-only-the-first-non-empty-stage.
  This tests the PARTITIONED operator on a generic/hypothetical provider. The Alibaba-specific version cannot be
  written until routing is proven; Alibaba `stage_routing` remains UNKNOWN (contract §5.4).
- **Status at master**: **MISSING**. No spill concept exists. Bounded by `rg -n "shared_pack|seat_monthly|
  member_shared_pack|member_pack_cap|ORDERED_SPILL|spill" config control_plane ops integrations tests` — zero
  hits (positive control: the same invocation style returns 322 hits for `quota_class` in
  `control_plane/executive_runtime.py`).

### Class 4 — member shared-pack ceiling can block access despite organizational pack balance
- **Proposed test**: `test_member_ceiling_exhaustion_blocks_despite_large_shared_pack_balance`
- **Owner**: the CEILING child role (contract §3.2) inside the Alibaba expression (§5.4).
- **Fixture**: seat 0, packs 600,000, member cap remaining 3,000, cohort cost 10,000. Assert
  `startable_jobs == 0` **and** that the refusal reason names the member ceiling as the bottleneck, not the packs
  — R35 §17's "Alibaba: 68% remaining" concealment is exactly what a reason-free zero reproduces.
- **Status at master**: **MISSING**. Same bounds as class 3.

### Class 5 — nearest-expiring shared pack order is preserved
- **Proposed test**: `test_shared_pack_spill_consumes_nearest_expiry_first`
- **Owner**: the composition evaluator's stage ordering (contract §3.3).
- **Fixture**: pack_A expiring 2026-09-30 with 25,000, pack_B expiring 2026-10-31 with 600,000, presented to the
  evaluator in *reverse* order in the input document. Assert consumption still starts at pack_A, i.e. the order
  is provider-declared expiry, not input order. Mutant: sort by remaining, or by insertion.
- **Status at master**: **MISSING**. Bounded by `rg -n -i "nearest.expir|expiry order|expires_at" config
  control_plane ops tests` (composition scope).

### Class 6 — two simultaneous Executive claims cannot reserve the same native headroom
- **Proposed test**: `test_two_concurrent_claims_cannot_reserve_the_same_resource_headroom`
- **Owner**: the Executive claim transaction, via the narrow amendment (contract §8.3 A2).
- **Fixture**: one `resource_id` with headroom for exactly one job; two claim attempts driven into the same
  SQLite transaction window (the existing runtime test harness already drives `runtime.attempts.claim_job`, e.g.
  `tests/test_executive_inbox.py:288`). Assert exactly one claim succeeds, the loser receives a typed capacity
  refusal (not a generic conflict), and the holds row is written once.
- **Status at master**: **PARTIAL**. Exclusion exists, but only over *our own worker slot*:
  `control_plane/executive_runtime.py:1594` `UNIQUE(held_attempt_id),` and `:1743`
  `CREATE UNIQUE INDEX one_lease_active_attempt_per_job` make two Attempts on one slot/job impossible. That is
  not the class: two claims on *different* workers that both debit one provider resource are unconstrained,
  because the claim binds `(worker_id, quota_class)` (`:1593`) and no **provider-capacity** hold ledger exists in
  the claim path (contract §8.2, scoped at §8.2.1). Note for the implementer, not a status change: an inactive,
  already-reviewed reservation-bundle design exists for the *physical* resource domain
  (`control_plane/executive_runtime.py:2248`, `:2250`, `:2282`) and is the consolidation target named by contract
  §8.3 A2 — so this class's eventual test should assert serialisation on the canonical primitive's rows, not on
  a counter or a re-minted provider-quota ledger.

### Class 7 — stale pre-reset balance cannot authorize post-reset work
- **Proposed test**: `test_observation_taken_before_a_reset_boundary_cannot_authorize_a_post_reset_claim`
- **Owner**: observation freshness (contract §2.3), enforced at claim-time revalidation (§8.1 step 1).
- **Fixture**: an observation with `observed_at` before `next_reset_at`, and a claim attempted after
  `next_reset_at`. Assert the claim is refused as STALE, and — the discriminating half — that it is **not**
  silently refilled to entitlement. Second case: a reviewed deterministic-refill contract present → the claim is
  admitted at the contracted value, proving the exception is reachable and narrow.
- **Status at master**: **MISSING** for reset semantics. The nearest analogue defends a different object:
  `tests/test_executive_model_router.py:345`
  (`test_runtime_refuses_worker_capacity_from_a_stale_routing_policy`) refuses capacity carried by a stale
  *routing policy*, not by a stale *observation across a provider reset*. Bounded by `rg -n -i "pre.reset|
  post.reset|reset.*balance|observed_at" control_plane ops tests` (capacity scope).

### Class 8 — provider correction/retraction updates future planning without rewriting historical claim evidence
- **Proposed test**: `test_provider_correction_changes_forecast_but_leaves_historical_claim_receipts_byte_identical`
- **Owner**: Provider Control reconciliation (contract §8.1 step 6) + the immutable claim receipt (§8.3 A1).
- **Fixture**: a claim with a persisted `capacity_hold` receipt; a later provider correction that revises the
  debit downward. Assert the forecast/`avail` changes, the historical `JOB_CLAIMED` payload is byte-identical
  (digest compared before and after), and the correction is recorded as a new fact rather than an edit.
- **Status at master**: **MISSING**. The receipt object it would attack is designed but unimplemented: the
  closed `JOB_CLAIMED.capacity_evidence` design exists at
  `research/MASTERMIND_EXECUTIVE_CAPACITY_CF2F_CLAIM_EVIDENCE_AND_ACQUISITION_FREEZE_2026-08-25.md:735` and
  `:738`, while at master `capacity_evidence` appears only as operator reason codes
  (`control_plane/operator_continuity_projection.py:509`, `:517`) and never as a field written by
  `_claim_job_in_transaction` (`control_plane/executive_runtime.py:11015`).

### Class 9 — generation-axis changes move only their required effects
- **Proposed test**: `test_generation_axis_change_moves_only_its_required_effects_and_no_others`
- **Owner**: the six generation/freshness axes (contract §2.2).
- **Fixture**: a fully dated resource and live hold; parametrise over `capability_generation`,
  `resource_generation`, `composition_generation`, `realm_generation`, `rate_generation`, and observation
  staleness. Assert each axis's required effect **and every required non-effect**: a reset does not invalidate a
  resource epoch, hold, or calibration; key rotation does not create quota or orphan a resource-epoch hold; a
  rate-card change retires cohort/debit calibration but does not move the wallet or orphan a hold. Historical
  receipts remain readable and immutable, and refusals name the exact axis/freshness failure.
- **Status at master**: **PARTIAL**, and this is the strongest existing coverage of any class. Generation/digest
  invalidation is genuinely defended for the *canary admission* object:
  `control_plane/subscription_canary_admission.py:128` (`realm_generation: int`) and `:283` (generation mismatch
  refusal); `tests/test_claude_subscription_worker.py:510` (`test_seal_refuses_changed_catalog_digest`), `:527`
  (`test_seal_refuses_unenrolled_realm`); `tests/test_executive_model_router.py:383`
  (`test_runtime_refuses_capacity_with_a_different_capability_profile_digest`). Gap: none of these is keyed to
  the full provider `resource_generation`/`composition_generation` model, and none covers renewal-only freshness,
  shared-pack composition, deduction policy, or `rate_generation`, which have no representation at master at all.

### Class 10 — dynamic concurrency reduction prevents new starts without moving current STARTed work
- **Proposed test**: `test_concurrency_reduction_blocks_new_starts_and_never_moves_started_attempts`
- **Owner**: Provider Control concurrency telemetry (contract §6.3); Executive owns STARTed work and is not
  touched.
- **Fixture**: three STARTed attempts; observed safe concurrency drops from 3 to 1. Assert new claims refuse,
  assert the three attempts' rows are byte-identical after the drop, and assert `startable_jobs` is unchanged
  while `safe_parallelism` falls — proving §4.3's separation rather than a single number moving.
- **Status at master**: **MISSING**. Bounded by `rg -n -i "concurrency|parallelism" control_plane ops tests`
  within capacity scope: the only live constraint is
  `control_plane/capacity_economics_projection.py:174-175` refusing a preview whose `suggested_parallelism`
  exceeds `estimated_startable_jobs` (`tests/test_capacity_economics_projection.py:90`) — a document-validation
  rule, not a live-reduction rule, and it has no concept of started work.

### Class 11 — 429/cooling reduces availability without inventing credential failure
- **Proposed test**: `test_rate_limit_cooling_reduces_availability_and_is_never_reported_as_credential_failure`
- **Owner**: Provider Control health/cooling telemetry, reused not rebuilt (contract §6.3).
- **Fixture**: a 429 with a `Retry-After`; assert availability drops, the reason code is a cooling code, and the
  credential/enrollment state is untouched. Negative control: a genuine 401 must still classify as credential
  failure, so the test discriminates rather than blanket-suppressing.
- **Status at master**: **PARTIAL**. `tests/test_provider_waterfall.py:29`
  (`test_provider_rungs_are_codex_first_and_respect_shared_cooling`) exercises shared cooling on the provider
  waterfall. Gap: it is a waterfall/rung test, not a capacity-availability test, and it does not assert the
  negative control (429 must not be classified as a credential failure).

### Class 12 — provider-policy-ineligible unattended job is refused even with abundant quota
- **Proposed test**: `test_unattended_mode_is_refused_under_abundant_quota_and_unknown_mode_fails_closed`
- **Owner**: execution-mode gate (contract §7), sourced through the existing profile/policy owners.
- **Fixture**: a resource with 100 % remaining; a job requesting `UNATTENDED_BACKGROUND` against a plan whose
  admitted modes are `{SUPPORTED_TOOL_INTERACTIVE}`. Assert refusal with a policy reason, and assert the quota is
  **not** consumed or held. Second case: policy owner cannot resolve the mode → `PROVIDER_USAGE_MODE_UNKNOWN` →
  same refusal (fail closed). Third case (R13 precedent): a `claude -p` one-act headless invocation classifies as
  `UNATTENDED_BACKGROUND`, not as an attended session.
- **Status at master**: **PARTIAL**, and the static half is well defended:
  `tests/test_subscription_provider_profiles.py:34`
  (`test_purchased_subscription_profiles_are_not_eligible_for_unattended_production`), `:142`
  (`test_usage_policy_cannot_omit_or_weaken_baseline_fences`);
  `tests/test_claude_subscription_worker.py:353`
  (`test_current_subscription_profiles_cannot_be_composed_as_unattended_executive_workers`), `:551`
  (`test_seal_refuses_autonomous_mode`); the flags themselves at
  `config/subscription_provider_profiles.v1.json:24`, `:52`, `:81` (`autonomous_allowed: false`) and `:28`/`:56`/`:85`
  (`interactive_only: true`). Gap: all of it is *profile-level and static*. There is no per-operation, per-harness
  mode intersection and no `PROVIDER_USAGE_MODE_UNKNOWN` distinct from `false` — so "abundant quota" is not a
  variable any current test can vary.

### Class 13 — wrong Alibaba key/Base-URL pair cannot silently fall through to PAYG
- **Proposed test**: `test_mismatched_realm_binding_refuses_before_provider_entry_and_never_falls_through_to_payg`
- **Owner**: Family-B realm binding + the subscription profile base-URL law.
- **Fixture**: a Team base URL paired with a Personal/PAYG-scoped key (and the converse). Assert refusal
  **before** any credential load or provider entry, and assert no PAYG-surfaced request is attempted. The
  discriminating half: a *correct* pair proceeds to the existing refusal boundary, proving the test is not simply
  refusing everything.
- **Status at master**: **PARTIAL**. Base-URL shape is defended hard —
  `tests/test_subscription_provider_profiles.py:182` onward (roughly 30 parametrised cases through `:310`,
  including `:310` `test_catalog_base_urls_use_canonical_dns_authorities`) — and
  `tests/test_claude_subscription_worker.py:397` (`test_model_mismatch_is_refused_before_credential_load`)
  establishes the refuse-before-credential-load ordering. Gap: nothing tests the **pairing** of key realm to base
  URL, and nothing tests PAYG fall-through, because the Team product is not modelled at all
  (`config/subscription_provider_profiles.v1.json:33` is `alibaba-token-plan-personal`).

### Class 14 — unknown model-resource sharing never becomes independent wallets
- **Proposed test**: `test_unproven_view_independence_contributes_zero_additional_capacity`
- **Owner**: the view/resource distinction (contract §5.3).
- **Fixture**: a `/token_plan/remains`-shaped payload with two model rows over one plan, `independence: UNPROVEN`.
  Assert `avail` equals the underlying resource, that the rows are preserved for display, and that a summing
  mutant is killed. Independence-proving case: a discriminating observation pair where a debit attributed to view
  A leaves view B unchanged flips `independence` to PROVEN for that generation only — and a generation change
  resets it to UNPROVEN.
- **Status at master**: **MISSING**. Bounded by `rg -n -i "token_plan|remains|wallet" control_plane ops config
  tests` — the #7103 parser that preserves those rows is a Macro-side PR, not at Mastermind master.

### Class 15 — model/harness `rate_generation` change invalidates stale quality/cost calibration
- **Proposed test**: `test_model_or_harness_generation_change_retires_calibration_to_historical`
- **Owner**: model economics catalog + Outcome Learning cohort keys (contract §2.2 `rate_generation`).
- **Fixture**: a cohort with calibrated `q95`; then each of: provider alias silently updated, model version
  changed, harness changed, thinking-mode changed, `rate_generation` changed. Assert new placement reverts to
  conservative, old evidence remains queryable as historical, and the two are never mixed in one estimate.
- **Status at master**: **MISSING**. The adjacent defence is about *cutover determinism*, not calibration:
  `tests/test_provider_offer_economics.py:107`
  (`test_explicit_promotion_cutover_not_guessed_from_prose`). Bounded by `rg -n -i "calibration|cohort|
  generation" control_plane/provider_model_economics.py control_plane/capacity_economics_projection.py tests`.

### Class 16 — ambiguous shared consumption is not used to learn a fake cheap task cost
- **Proposed test**: `test_ambiguous_shared_consumption_is_rejected_not_attributed`
- **Owner**: Outcome Learning cost attribution (contract §6.2).
- **Fixture**: two concurrent operations over one resource with one aggregate debit observation. Assert the
  observation is rejected for cost learning (not split, not assigned to the cheaper one), and that a mutant which
  divides the debit evenly is killed. Positive control: an unambiguous single-operation window IS learned, so the
  rule does not simply reject everything.
- **Status at master**: **MISSING**. Nearest guard is the declaration-level rule
  `tests/test_provider_model_economics.py:91`. Bounded by `rg -n -i "ambiguous|attribut|shared consumption"
  control_plane ops tests` (economics scope).

### Class 17 — low-price/expiring capacity cannot promote a lower Model Router tier
- **Proposed test**: (exists) — extend with an expiry-pressure case:
  `test_expiring_capacity_pressure_cannot_promote_a_lower_suitability_tier`
- **Owner**: `control_plane/capacity_economics_projection.py` (economics inside the first lawful tier only).
- **Fixture**: a first-tier option and a cheaper lower-tier option whose resource expires in one hour. Assert the
  lower tier is still refused, i.e. Stage E (stranding) never outranks suitability.
- **Status at master**: **PARTIAL**. `tests/test_capacity_economics_projection.py:53`
  (`test_refuses_lower_tier_promotion`) and `:61`
  (`test_refuses_later_tier_selection_while_option_remains_in_first_tier`) falsify the *price* half and are
  genuine coverage. Gap: the class as written is "low-price **/expiring**", and neither test supplies expiring
  capacity or exercises expiry pressure at all — so the complete class is not falsified. *(An earlier draft
  scored this row EXISTS; independent review corrected it, and the correction is kept here rather than
  argued: a row that covers one of two named pressures is PARTIAL by this document's own vocabulary.)*
  Expiry pressure is exactly what §11 Stage E introduces, so the missing half is created by this contract and
  cannot pre-exist it.

### Class 18 — EFFECT_UNKNOWN prevents economic failover
- **Proposed test**: `test_effect_unknown_holds_capacity_and_refuses_economic_failover`
- **Owner**: claim-hold reconciliation (contract §8.1 step 7).
- **Fixture**: a completed attempt whose provider debit cannot be reconciled → `EFFECT_UNKNOWN`. Assert the hold
  is **not** released, the resource's `usable` stays reduced, and no alternative route is selected on economic
  grounds. The refusing hold state is the canonical primitive's `RECONCILIATION_REQUIRED` state, not a re-minted
  provider-quota state machine. Discriminator: a successfully reconciled attempt releases exactly once and
  failover becomes available.
- **Status at master**: **MISSING in the capacity path**. The vocabulary exists and should be reused rather than
  re-minted: `control_plane/operator_continuity_projection.py:61` and `control_plane/executive_steward.py:54`
  both define `EFFECT_UNKNOWN`, and `control_plane/executive_steward.py:1026` refuses to proceed on a blocker
  carrying it. Bounded by `rg -n "EFFECT_UNKNOWN" control_plane ops` — no occurrence in
  `capacity_economics_projection.py`, `model_router.py` or `subscription_canary_admission.py`.

### Class 19 — review-independence exclusion remains effective under scarcity
- **Proposed test**: (exists, extend) `test_review_independence_exclusion_survives_capacity_scarcity_pressure`
- **Owner**: Model Router hard route constraint, evaluated **before** capacity economics (R35 §20).
- **Fixture**: a builder on provider family X; the only cheap/abundant reviewer route is also family X; a scarce
  independent family Y is available. Assert Y is chosen or the review is deferred — never X — and that the
  refusal reason is independence, not capacity.
  The scarcity test must also assert that no preference was smuggled through `capacity_state` or candidate order
  (contract §11.1).
- **Status at master**: **PARTIAL**. `tests/test_executive_model_router.py:726`
  (`test_v2_review_exclusions_survive_structured_tiers_and_claim_projection`) establishes that review exclusions
  survive structured tiers and claim projection. Gap: it does not vary *scarcity*, which is the pressure this
  class names; the contract adds the scarcity dimension (§11 Stage C), so the variable becomes testable only
  after step A.

### Class 20 — future reset forecast never masquerades as currently observed capacity
- **Proposed test**: `test_post_reset_forecast_is_a_distinct_field_and_never_enters_avail`
- **Owner**: observation vs forecast separation (contract §2.3).
- **Fixture**: a resource near exhaustion with a reset in 30 minutes. Assert `avail` reflects only observed
  remaining, that the forecast is published under a distinct field name, and that a mutant substituting the
  forecast into `avail` is killed. Second case: a claim requiring post-reset capacity is refused until a fresh
  observation exists (composes with class 7).
- **Status at master**: **MISSING**. Bounded by `rg -n -i "forecast|next_reset|reset_at" control_plane/
  capacity_economics_projection.py control_plane/provider_model_economics.py tests` within capacity scope.

---

## 2. Summary

| Status | Count | Classes |
|---|---|---|
| EXISTS | 0 | — |
| PARTIAL | 8 | 2, 6, 9, 11, 12, 13, 17, 19 |
| MISSING | 12 | 1, 3, 4, 5, 7, 8, 10, 14, 15, 16, 18, 20 |

0 + 8 + 12 = 20. **Not one of the twenty failure classes is fully falsified at master today.** Class 17 is the
closest, and it covers one of its two named pressures.

Two structural observations for the reviewer:

1. **The PARTIALs cluster on policy and identity, the MISSINGs cluster on resource algebra.** Master defends the
   *gates* (autonomy flags, realm digests, base-URL shape, tier promotion) comparatively well and defends the
   *tree* not at all — which is precisely R35 §21's finding restated as test coverage.
2. **Twelve of the MISSING classes cannot be written before the contract is frozen.** Classes 1, 3, 4, 5, 14 and
   20 attack operators that do not exist; classes 6, 8 and 18 attack a claim-hold receipt that does not exist;
   classes 7 and 15 attack generation-axis/freshness splits that do not exist. Writing them against today's scalar
   `estimated_startable_jobs` would produce tests that pass vacuously — the worst possible outcome, because a
   green acceptance suite would then certify a fabric that still cannot express the resource graph.

The reviewable question this matrix puts to Sol is therefore narrow: **is the 20-class suite the right acceptance
gate for step A's contract, and is this the right allocation of each class to an owner?** It is not a request to
write the tests now.

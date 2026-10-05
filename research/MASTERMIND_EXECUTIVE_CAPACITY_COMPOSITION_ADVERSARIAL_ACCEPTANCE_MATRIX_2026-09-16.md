# Adversarial acceptance matrix for the resource-composition contract — PROPOSAL

STATUS: PROPOSAL — HOLD-FOR-SOL
Census anchor: master@0fe8074ff953b2ced9025ed40f0f66019c759967. Every EXISTS / PARTIAL row below carries a
`file:line` receipt that was read at that commit and re-verified by this lane; every MISSING row names the search
that bounds the claim. Nothing is asserted from memory.
Companion: `research/MASTERMIND_EXECUTIVE_CAPACITY_RESOURCE_COMPOSITION_CONTRACT_2026-09-16.md` (the contract).
Source of classes 1–20: Sol capacity-routing architecture ruling (R35) §23, verbatim ordering preserved. Those
twenty are the ruling's minimum; classes 21–32 are additions required by Sol formal review 5220216985, addendum
5694353522, and R42/R52; classes 33–37 are additions required by R54/R55; class 38 is the hostile test for
the typed required-child rule of §4.1 and class 39 the dead-producer test for the consumer chain, both added
under Sol's exact-head re-review at `4d181fda`.

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

No class of the thirty-nine is fully EXISTS; eleven are PARTIAL and twenty-eight are MISSING. That distribution is
the expected consequence of the contract not existing yet: the added classes are also statements about a
resource tree, hold lifecycle, offer overlay, or integration invariant, and
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
  existing Family-B `realm_generation`; one resource observation of 10,000 units. Assert `avail` of the union
  is 10,000, not 20,000, and that both hosts resolve to the same `resource_id`.
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

### Class 5 — provider-declared canonical stage order is preserved
- **Proposed test**: `test_shared_pack_spill_consumes_provider_declared_canonical_order_without_resorting`
- **Owner**: Provider Control deduction-policy production (contract §3.3); evaluator validates and consumes.
- **Fixture**: Provider Control publishes canonical order `[pack_A expiring 2026-09-30, pack_B expiring
  2026-10-31]` with `composition_generation` and provenance; an input document presents pack_B before pack_A.
  Assert the evaluator refuses or flags the noncanonical input rather than re-sorting it. With canonical input,
  consumption starts at pack_A. A provider contract that itself defines nearest-expiry-first may use that rule,
  but the evaluator still consumes the declared canonical order. Mutants: evaluator sorts by expiry, remaining,
  or insertion.
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
  `resource_generation`, `composition_generation`, `realm_binding_generation`,
  `model_harness_cost_generation`, and observation
  staleness. Assert each axis's required effect **and every required non-effect**: a reset does not invalidate a
  resource epoch, hold, or calibration; key rotation does not create quota or orphan a resource-epoch hold; a
  model/harness/cost change retires cohort/debit calibration but does not move the wallet or orphan a hold; a
  resource-generation rollover reconciles or conservatively carries a nonterminal hold before authorization.
  Historical
  receipts remain readable and immutable, and refusals name the exact axis/freshness failure.
- **Status at master**: **PARTIAL**, and this is the strongest existing coverage of any class. Generation/digest
  invalidation is genuinely defended for the *canary admission* object:
  `control_plane/subscription_canary_admission.py:128` (`realm_generation: int`) and `:283` (generation mismatch
  refusal); `tests/test_claude_subscription_worker.py:510` (`test_seal_refuses_changed_catalog_digest`), `:527`
  (`test_seal_refuses_unenrolled_realm`); `tests/test_executive_model_router.py:383`
  (`test_runtime_refuses_capacity_with_a_different_capability_profile_digest`). Gap: none of these is keyed to
  the full provider `resource_generation`/`composition_generation` model, and none covers renewal-only freshness,
  shared-pack composition, deduction policy, or `model_harness_cost_generation`, which have no representation at
  master at all.

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
- **Fixture**: four deterministic runs over one `/token_plan/remains`-shaped plan. The shared plan holds
  100,000 units; the two model views are **oversubscribed** — M3 80,000 and M2.7 80,000, summing to
  160,000 — which is what makes sharing and independence numerically distinguishable at all.
  `independence: UNPROVEN`.
  **Run 1 — baseline.** Assert whole-job capacity is bounded by the shared plan at **100,000**, that both
  rows are preserved for display, and that the **summing mutant** returning `80,000 + 80,000 = 160,000` is
  killed.
  **Run 2 — the one-pair trap, which is what B4 is about.** Present exactly ONE observation pair that looks
  like clean evidence of independence: debit 5,000 against M3, then observe M3 at 75,000 and M2.7 unchanged
  at 80,000. The unchanged sibling proves nothing — under sharing M2.7 reads `min(80,000, 95,000) = 80,000`
  and under independence it reads 80,000, so **the observation has no discriminating power by
  construction**. Assert independence stays **UNPROVEN** and that the M2.7 row contributes no independent
  capacity. **Named mutant to kill: `promote_independence_on_first_pair`** — an evaluator that reads the
  unchanged sibling row as proof of a separate wallet. Four confounders must each be falsifiable on their
  own in the fixture: an observation resolution coarser than the 5,000 debit would hide a shared draw; a
  lag budget shorter than the provider's propagation delay would show a row that is merely not-yet-updated;
  a concurrent unattributed debit could produce the same two numbers; and a later provider correction could
  retract the observation entirely.
  **Run 3 — repetition is not an experiment.** Present a SECOND pair of the same shape and assert
  independence is still UNPROVEN. Repeating an observation with no discriminating power does not accumulate
  into the repeated causal experiment B5 requires.
  **Run 4 — what the premature promotion actually costs.** Debit 75,000 against M3, leaving the shared plan
  at 25,000 and the M3 row at 5,000. Under sharing M2.7 is now `min(80,000, 25,000) = 25,000`; the mutant
  promoted at run 2 still reports **80,000**, over-committing by **55,000** against a plan that holds
  25,000. Assert the unmutated evaluator reports 25,000.
  **The valid path, asserted separately.** Supply either provider contract semantics declaring the rows
  independent, or a reviewed repeated causal experiment declaring observation resolution, lag budget, same
  `resource_generation`, isolated attribution, and correction/retraction handling. Only then assert
  independence is PROVEN and the rows are separate resources. Then bump `resource_generation` and assert
  independence resets to UNPROVEN and run 1's arithmetic returns.
- **Status at master**: **MISSING**. Bounded by `rg -n -i "token_plan|remains|wallet" control_plane ops config
  tests` — the #7103 parser that preserves those rows is a Macro-side PR, not at Mastermind master.

### Class 15 — model/harness `model_harness_cost_generation` change invalidates stale quality/cost calibration
- **Proposed test**: `test_model_or_harness_generation_change_retires_calibration_to_historical`
- **Owner**: model economics catalog + Outcome Learning cohort keys (contract §2.2, §6.2).
- **Fixture**: a cohort with calibrated `q95`; then each of: provider surface changed (Go/M3 versus direct M3),
  provider alias silently updated, model version changed, harness changed, thinking-mode changed, generation
  changed. Assert new placement reverts to conservative, old evidence remains queryable as historical, and the
  two surfaces/generations are never mixed in one estimate.
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
  failover becomes available. Generation rollover and undecided hold reflectedness are also EFFECT_UNKNOWN-class
  blockers, never release events.
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
| PARTIAL | 11 | 2, 6, 9, 11–13, 17, 19, 25, 26, 29 |
| MISSING | 28 | 1, 3–5, 7, 8, 10, 14–16, 18, 20–24, 27, 28, 30–39 |

0 + 11 + 28 = 39. **Not one of the thirty-nine failure classes is fully falsified at master today.** Class 17 is the
closest, and it covers one of its two named pressures.

Two structural observations for the reviewer:

1. **The PARTIALs cluster on policy and identity, the MISSINGs cluster on resource algebra.** Master defends the
   *gates* (autonomy flags, realm digests, base-URL shape, tier promotion) comparatively well and defends the
   *tree* not at all — which is precisely R35 §21's finding restated as test coverage.
2. **Nineteen of the MISSING classes cannot be written before the contract is frozen.** Classes 1, 3, 4, 5, 14 and
   20 attack operators that do not exist; classes 6, 8 and 18 attack a claim-hold receipt that does not exist;
   classes 7 and 15 attack generation-axis/freshness splits that do not exist; classes 22, 33–37, 38 and 39 attack
   composition/policy objects that do not exist. Writing them against today's scalar
   `estimated_startable_jobs` would produce tests that pass vacuously — the worst possible outcome, because a
   green acceptance suite would then certify a fabric that still cannot express the resource graph.

The reviewable question this matrix puts to Sol is therefore narrow: **is the 39-class suite — R35's twenty-class
minimum plus the review-required additions — the right acceptance gate for step A's contract, and is this the
right allocation of each class to an owner?** It is not a request to write the tests now.

### Class 21 — mixed-unit `ALL_OF` stays vector-valued
- **Proposed test**: `test_mixed_unit_all_of_uses_per_resource_costs_and_never_one_scalar_q95`
- **Owner**: composition evaluator (contract §3, §4.2).
- **Fixture**: one route simultaneously constrained by tokens, requests, currency, and concurrency resources,
  each with stable `resource_id`, `native_unit`, generation axes, and `cost_r(c)`. Assert
  `jobs_fit = min(floor(usable_r/cost_r))`; scalar `avail/q95` and raw-unit `min` mutants are killed. Unit
  mismatch without reviewed conversion is ill-formed.
- **Status at master**: **MISSING**. Bounded by `rg -n "native_unit|cost_r|jobs_fit|estimated_startable_jobs"
  control_plane ops tests` (composition scope).

### Class 22 — graph/balance epoch mismatch is inadmissible
- **Proposed test**: `test_resource_graph_and_balances_from_different_v2_snapshots_are_inadmissible`
- **Owner**: Provider Capacity V2 binding (contract §9.0).
- **Fixture**: graph from V2 snapshot X and balances from snapshot Y with different digests. Assert
  INADMISSIBLE with digest reason; no partial join, freshness-only downgrade, or fallback observation.
- **Status at master**: **MISSING**. Bounded by `rg -n "snapshot.*digest|graph.*balance|Provider Capacity V2"
  control_plane ops tests` (capacity-composition scope).

### Class 23 — reflected hold is not subtracted twice
- **Proposed test**: `test_hold_reflected_by_covering_observation_is_not_subtracted_twice`
- **Owner**: observation/hold reconciliation (contract §6.1, §8.3).
- **Fixture**: debit 30 at effective time T; provider-declared accounting lag 2 minutes; observation at T+3
  already reflects it. Assert `usable` subtracts the observation only, not the reflected hold. Ambiguous
  observation at T+1 keeps the hold unreflected.
- **Status at master**: **MISSING**. Bounded by `rg -n "reflected|accounting.*lag|unobserved.*debit|
  outstanding_holds" control_plane ops tests`.

### Class 24 — completed debit not yet reflected remains unobserved
- **Proposed test**: `test_known_completed_debit_older_than_observation_is_retained_as_unobserved`
- **Owner**: observation/hold reconciliation (contract §6.1, §8.3).
- **Fixture**: known actual debit 40 after an older observation showing 100. Assert `usable <= 60`, the debit
  remains an unobserved debit, and no route is authorized until a covering observation arrives.
- **Status at master**: **MISSING**. Bounded by the class-23 search plus
  `rg -n "EFFECT_UNKNOWN|RECONCILIATION_REQUIRED" control_plane ops tests` (provider-capacity scope).

### Class 25 — wrong-axis invalidation does not move wallet or hold
- **Proposed test**: `test_realm_or_model_cost_change_does_not_move_wallet_or_free_hold`
- **Owner**: generation-axis policy (contract §2.2).
- **Fixture**: a live hold; bump `realm_binding_generation`, then `model_harness_cost_generation`. Assert
  executable-binding / calibration invalidation respectively, while wallet `resource_generation`, observed
  remaining, and hold quantity remain unchanged. Mutants that release the hold or fork a wallet are killed.
- **Status at master**: **PARTIAL**. Existing realm/capability-digest guards defend a different object:
  `control_plane/subscription_canary_admission.py:128`, `:283`, and
  `tests/test_executive_model_router.py:383`. None models a provider wallet or live provider-capacity hold.
  Bounded by `rg -n "resource_generation|resource_key|capacity_hold" control_plane ops tests`.

### Class 26 — C1 economics preference smuggling is refused
- **Proposed test**: `test_capacity_economics_cannot_smuggle_preference_through_state_or_order`
- **Owner**: C1 / CF2-I integration (contract §11.1).
- **Fixture**: exact tied concrete Worker candidates. Vary `capacity_state`, account/file order, and candidate
  order. Assert no resulting preference and no change to `preferred_model_aliases`; economics may supply only a
  #657-style exact-tie source receipt.
- **Status at master**: **PARTIAL**. C1's reserved-slot guards exist, but no #657 V2 acceptance path and no
  capacity-to-concrete-worker economics source are proven at protected master. Bounded by class 19's existing
  receipt plus `rg -n "capacity_placement_preference|selection_is_commitment" control_plane ops tests`.

### Class 27 — duplicate provider commitment lifecycle is refused
- **Proposed test**: `test_second_provider_quota_state_machine_is_refused`
- **Owner**: one canonical Executive commitment primitive (contract §8.3).
- **Fixture**: one installed canonical primitive plus a proposed provider-quota lifecycle. Assert installation
  refuses the duplicate; provider-quota holds become demands on the canonical primitive and settle through its
  one path.
- **Status at master**: **MISSING in provider capacity**. The inactive physical-resource candidate and
  consolidation target are receipted in contract §8.2.1/§8.3; bounded by
  `rg -n "provider.*quota|capacity_hold|physical_resource_commitments" control_plane ops tests`.

### Class 28 — nonterminal old-generation hold survives rollover
- **Proposed test**: `test_resource_generation_bump_does_not_release_nonterminal_old_hold`
- **Owner**: generation rollover and canonical holds (contract §2.2, §6.1, §8.3).
- **Fixture**: R generation n, observed 100, nonterminal hold 70; bump to n+1 with observed 100. Assert BLOCKED
  or carried hold with `usable = 30`, never `usable = 100` or a second 70-unit authorization (contract §10.7).
- **Status at master**: **MISSING**. Bounded by `rg -n "resource_generation|generation.*rollover|capacity_hold"
  control_plane ops tests` (provider-capacity scope).

### Class 29 — execution lanes are not entitlement resources
- **Proposed test**: `test_execution_lanes_do_not_multiply_entitlement_resources`
- **Owner**: Provider Control identity + Worker runtime inventory (contract §1, §5.3; CF2-I adoption).
- **Fixture**: seven wrappers/process slots over one provider resource with remaining 100. Assert one resource,
  remaining 100, and `jobs_fit` bounded once; concurrency is reported separately as `safe_parallelism`.
- **Status at master**: **PARTIAL**. Worker slots are distinct execution lifecycle objects
  (`control_plane/executive_runtime.py:1593`), but no provider-resource identity joins them to one entitlement;
  bounded by `rg -n "resource_key|capacity_capability_id|worker_id.*quota_class" control_plane ops config tests`.

### Class 30 — nested `ATOMIC_FALLBACK` is compositional
- **Proposed test**: `test_nested_atomic_fallback_counts_whole_jobs_per_stage_and_shared_budget`
- **Owner**: composition evaluator (contract §4.2, §10.6).
- **Fixture**: shared BUDGET 100; `ATOMIC_FALLBACK` stages 60 and 60; cohort cost 50. Assert
  `jobs_fit = min(2, 1+1) = 2`, not scalar `floor(min(100, max(60,60))/50) = 1`. A root-scalar mutant is killed.
- **Status at master**: **MISSING**. Bounded by
  `rg -n "ATOMIC_FALLBACK|ORDERED_SPILL|jobs_fit" control_plane ops tests`.

### Class 31 — expired overlay contributes no relief
- **Proposed test**: `test_expired_or_out_of_window_overlay_uses_ordinary_limits`
- **Owner**: time-bound overlays through Provider Control facts (contract §6.4).
- **Fixture**: a zero-quota/double-limit overlay with `effective_until` in the past, then outside its daily
  window. Assert the overlay does not apply, ordinary resource limits bind, and the advisory digest changes.
  **Mutants to kill**: one that keeps the overlay applied after `effective_until` because the campaign digest
  is unchanged; one that treats the daily window as advisory and relieves the limit at any hour inside the
  campaign dates; and one that persists the doubled limit into the ordinary resource after expiry — the
  second-wallet mutant §6.4 forbids.
- **Status at master**: **MISSING**. Bounded by
  `rg -n "effective_until|daily.*window|offer.*overlay|promotion" control_plane ops config tests`.

### Class 32 — surface mismatch refusal names surface
- **Proposed test**: `test_overlay_surface_or_version_mismatch_is_refused_for_surface_reason`
- **Owner**: time-bound overlays through Provider Control facts (contract §6.4).
- **Fixture**: a ZCode >= 3.10 overlay claimed for another product or ZCode 3.9. Assert refusal, a reason naming
  the exact product/version surface rather than quota, and ordinary rules binding.
- **Status at master**: **MISSING**. Bounded by the class-31 search plus
  `rg -n "minimum.*version|surface.*digest" control_plane ops config tests`.

### Class 33 — Go multi-account pooling without policy eligibility yields one or zero entitlements
- **Proposed test**: `test_go_credentials_without_pool_policy_eligibility_yield_one_or_zero_entitlements`
- **Owner**: Provider Control enrollment/policy gate (contract §2.1, §5.2).
- **Fixture**: three technically healthy Go credentials with no `pool_membership_policy_eligible` receipt, then
  an explicitly ineligible receipt. Assert one schedulable entitlement in the former case and zero multi-member
  entitlement in the latter; the refusal names the missing/ineligible policy evidence rather than a quota
  shortfall; and a mutant summing three limits is killed.
- **Status at master**: **MISSING** for the admission gate. Protected #622 transport tests exercise account
  choice and effect safety but carry no policy-eligibility field; bounded by
  `rg -n "pool_membership_policy_eligible|member_count" control_plane ops config tests`.

### Class 34 — Go model tables are debit views over three windows, never extra wallets
- **Proposed test**: `test_go_model_tables_debit_views_do_not_sum_into_capacity`
- **Owner**: Provider Control view/resource distinction (contract §5.2, §5.3).
- **Fixture**: one Go entitlement metered by 5-hour, weekly, and monthly windows with several per-model debit
  tables. Assert the tables debit the same allowance, `ALL_OF` never sums it, and a mutant adding model-table
  capacities or multiplying by key/account count is killed.
- **Status at master**: **MISSING**. Existing Go transport and offer tests do not model a composed entitlement
  or its three windows. Bounded by
  `rg -n -i "debit view|shared entitlement|monthly.*weekly.*5h" control_plane ops config tests`.

### Class 35 — Go/M3 calibration is surface-separated from direct M3
- **Proposed test**: `test_go_m3_and_direct_m3_calibration_never_pool`
- **Owner**: model economics catalog + Outcome Learning cohort keys (contract §6.2).
- **Fixture**: otherwise-identical Go/M3 and direct-M3 cohorts with distinct provider surfaces and the same
  `model_harness_cost_generation` and harness. Assert separate estimates, conservative handling when one side
  lacks evidence, and a pooled-estimate mutant is killed.
- **Status at master**: **MISSING**. Existing offer tests distinguish surface digests, not outcome-cost
  cohorts. Bounded by
  `rg -n -i "provider_surface|model_harness_cost_generation|direct.*m3|go.*m3" control_plane ops tests`.

### Class 36 — expired privacy-retention observation is STALE/UNKNOWN
- **Proposed test**: `test_retention_label_past_observation_date_is_stale_unknown`
- **Owner**: Provider Control dated policy observation (contract §2.3, §9.3).
- **Fixture**: a DeepSeek V4 Flash zero-data-retention label observed through 31 August 2026, evaluated after
  that date. Assert STALE/UNKNOWN and fail-closed routing; a mutant treating the label as a current guarantee is
  killed.
- **Status at master**: **MISSING**. Existing offer tests carry effective end dates, not privacy observations
  with observation dates. Bounded by
  `rg -n -i "retention|privacy.*observed_at|zero.data.retention" control_plane ops config tests`.

### Class 37 — coding-agent surface refuses non-coding-agent extraction requests
- **Proposed test**: `test_coding_agent_api_refuses_scraping_extraction_or_dataset_generation`
- **Owner**: typed execution-mode gate (contract §7.1).
- **Fixture**: a surface admitted only for bounded `CODING_AGENT_API`, then scraping, extraction, and
  dataset-generation requests using otherwise valid quota and stable sessions. Assert each is refused for its
  execution class — not quota — and a mutant admitting it because quota remains is killed.
- **Status at master**: **MISSING**. Existing Go stream tests validate stable sessions but not request-class
  bounds. Bounded by
  `rg -n "CODING_AGENT_API|SUPPORTED_TOOL_AGENT_SESSION|UNATTENDED_BACKGROUND" control_plane ops config tests`.

### Class 38 — a required `ALL_OF` child is never silently filtered, and its class survives composition
- **Proposed test**: `test_required_all_of_child_propagates_its_typed_class_under_frozen_precedence_and_is_never_dropped`
- **Owner**: the typed recursive evaluator (contract §4.1), composed with the freshness and policy gates
  (§2.3, §7).
- **Fixture**: one `ALL_OF` with three required BUDGET children in one `native_unit`, declared in the canonical
  order `A`, `B`, `C` — `A` = `KNOWN(100)`, `B` = `KNOWN(80)`, `C` variable. Run the same graph five times and
  assert the parent result each time: `C = KNOWN(60)` → parent `KNOWN(60)`;
  `C = INELIGIBLE(unattended_mode_not_admitted)` → parent **`INELIGIBLE`** carrying **that child's** reason —
  never `KNOWN(80)`, and never `KNOWN_ZERO`, because "unattended mode is not admitted for this plan" is an
  authority fact about what is lawful and not an exhausted allowance that a reset could refill;
  `C = UNKNOWN(no_observation)` → parent `UNKNOWN` carrying that reason, never `KNOWN(80)` and never `KNOWN_ZERO`;
  `C = STALE(observed_before_reset)` → parent `STALE` carrying that reason; `C = KNOWN_ZERO(allowance_exhausted)`
  → parent `KNOWN_ZERO` carrying that reason, which is the lawful outcome here precisely because `A` and `B` are
  both current and eligible. Then assert `jobs_fit` is not computed from a filtered child set in any of the five
  runs.
- **Mixed-state vector — precedence and aggregation determinism**: one further run over a single graph carrying
  every state at once, which proves the parent's primary state follows the frozen precedence
  `INELIGIBLE > STALE > UNKNOWN > KNOWN_ZERO > KNOWN` while no lower-precedence child is discarded. The seven
  required children are declared in exactly this canonical order:

  | # | Declared child | State | Reason | Position in `non_known_children` |
  |---|---|---|---|---|
  | 1 | `A` | `KNOWN(100)` | — | absent — `KNOWN` children are not aggregated |
  | 2 | `B` | `KNOWN_ZERO` | `allowance_exhausted` | 1 |
  | 3 | `C` | `UNKNOWN` | `no_observation` | 2 |
  | 4 | `D` | `STALE` | `observed_before_reset` | 3 |
  | 5 | `E` | `INELIGIBLE` | `unattended_mode_not_admitted` | 4 |
  | 6 | `F` | `KNOWN_ZERO` | `allowance_exhausted` | 5 — distinct identity, never merged with `B` |
  | 7 | `G` | `STALE` | `observed_before_reset` | 6 — distinct identity, never merged with `D` |

  Assert: the parent's primary state is exactly `INELIGIBLE(unattended_mode_not_admitted)` sourced from `E`, even
  though `E` is declared fifth and four non-`KNOWN` children precede it — precedence, not position, selects it;
  `non_known_children` is exactly the six-element sequence `[(B, KNOWN_ZERO, allowance_exhausted),
  (C, UNKNOWN, no_observation), (D, STALE, observed_before_reset), (E, INELIGIBLE, unattended_mode_not_admitted),
  (F, KNOWN_ZERO, allowance_exhausted), (G, STALE, observed_before_reset)]`, in declared order — not precedence
  order, not sorted by state or reason; and re-running the identical graph yields the byte-identical sequence.
  Second sub-case (recursion): replace `E` with a nested required `ALL_OF` `H` whose own required children include
  one `INELIGIBLE(unattended_mode_not_admitted)`; assert `H`'s own primary state is `INELIGIBLE`, that the root is
  `INELIGIBLE` and not `KNOWN_ZERO`, and that `H` and its ineligible child both appear in the root aggregate in
  pre-order — the nested parent immediately before the child it declared. Third sub-case (dedup): declare two
  children whose `(identity, state, reason)` triples are equal in all three fields; assert exactly one occurrence
  survives, at the earliest canonical position, and that the run is byte-identical on repeat.
- **Mutants to kill**: an evaluator that builds an "admissible children" list and takes `min` over it (returns 80
  in four of the five runs); **`collapse_ineligible_to_known_zero`** — an evaluator that maps a required
  `INELIGIBLE` child to a parent `KNOWN_ZERO`, which is invisible to any assertion made only on numbers, because
  both answers size zero jobs; only the typed assertion catches it, and it is the exact mutant that would let a
  policy refusal be reported to operators, economics, and cooling logic as an exhausted allowance awaiting a
  reset; one that maps every non-KNOWN child to zero and so collapses UNKNOWN and STALE into `KNOWN_ZERO`,
  discarding the typed reason; one that treats an UNKNOWN child as `KNOWN(+∞)` and lets its siblings decide the
  min; one that reports only the precedence-winning child and drops the remaining `non_known_children`, so the
  operator sees the refusal but never learns that two other required children are also stale or exhausted; and
  one that sorts the aggregate by precedence or by reason instead of preserving canonical declared order, making
  the aggregate unstable across equivalent runs.
- **Status at master**: **MISSING**. There is no typed evaluation result at master to propagate — the scalar
  `estimated_startable_jobs` path has no child-level reason to carry. Bounded by
  `rg -n "ALL_OF|EvalResult|KNOWN_ZERO|INELIGIBLE|admissible" control_plane ops config tests` — no hit
  outside this proposal's own text.

### Class 39 — a preference receipt naming an unresolvable producer is INADMISSIBLE
- **Proposed test**: `test_preference_receipt_naming_an_unresolvable_producer_is_inadmissible`
- **Owner**: #657's tie/abstention preference seam consuming the exact, content-addressed Capacity SOURCE
  artifact (contract §11.1); CF2-I as the downstream consumer.
- **Fixture**: one candidate set, two runs, same seam head. **Run 1 (live producer)**: the preference receipt
  names the Capacity SOURCE artifact by exact content address and that address resolves at the seam's own head.
  Assert the receipt is admissible and that the emitted chain is exactly `Model Router lawful tier → concrete
  C1 Worker candidates → Capacity evidence → #657 tie/abstention seam → CF2-I → C2 atomic worker+resource
  commitment`, with no other participant. **Run 2 (dead producer)**: the identical receipt names a producer that
  does not resolve at that head. Assert `INADMISSIBLE` with a reason naming the unresolved producer, assert C1
  abstains (`TIE_ABSTAINED`), and assert **no placement is emitted at all**. **Mutants to kill**: one that
  downgrades the dead producer to `STALE` and proceeds on last-good evidence; one that falls back to a locally
  computed ranking when the producer is missing — the second selector, and the reason this class exists; and
  one that resolves the producer through a mutable ref (branch name or tag) instead of the exact content
  address, so a later push silently changes what the receipt meant.
- **Status at master**: **MISSING**. #657 is OPEN and BUILT_NOT_PROVEN at `bc89980c`, CF2-I is UNBUILT, and
  §8.3's canonical C2 primitive is not chosen — three of the chain's six links do not exist, so this class
  cannot be written before step A is frozen. Bounded by
  `rg -n "preference_receipt|selection_input_digest|source_ref|TIE_ABSTAINED" control_plane ops config tests`.

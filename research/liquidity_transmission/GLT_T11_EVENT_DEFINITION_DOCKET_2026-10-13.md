# GLT T11 — event-definition docket (2026-10-13)

- Status: research measurement docket; thresholds NOT ratified (EventizationPolicy has no production
  default; Sol ratifies thresholds after W-LIQ.1 freezes field semantics)
- Task: T11
- Acceptance: C10, C14, C20
- Code: `brain/liquidity_lab/eventization.py`, `brain/liquidity_lab/ledger.py`

innovation and exogenous-shock labels are separate; nothing here is a causal promotion

## 1. What the event definition is

`event_definition(policy)` returns the frozen, outcome-free definition that `eventize` applies: every
threshold of the supplied `EventizationPolicy` plus the algorithm version, the business-day calendar and
the trusted-freshness set. `event_definition_id(policy) = "evdef_" + canonical_hash(event_definition(policy))`.
Both functions take only the policy, so the id is independent of any outcome or price data at the
signature level; nothing in them reads a file, a clock or a series. Numeric thresholds are normalised
(`float` for the four ratios, `int` for the two business-day counts) and must be finite, so `1` and `1.0`
yield the same id for a ratio. A `bool` is refused for every field, and a business-day count must be an
integer: `int()` would otherwise truncate `refractory_bdays=2.5` to `2` although `eventize` compares the
raw value, giving two behaviourally different policies one id (F4 review finding, repaired). Changing ANY field below mints a new id and is a separate registered research choice,
not a cleanup (SCIENCE_PROTOCOL §5).

## 2. Frozen fields

| field | value(s) declared | meaning |
| --- | --- | --- |
| definition_version | `glt_eventization.v1` | version of the eventization algorithm |
| business_day_calendar | `numpy_busday_mon_fri_no_holidays` | gap and refractory counts use numpy busday Mon-Fri, no holiday calendar |
| trusted_freshness | `["fresh"]` | only `fresh` readings are trusted observations |
| material_abs_z | per policy below | abs(z) at or above which a trusted reading opens (first-detects) an episode |
| reset_abs_z | per policy below | a trusted reading with abs(z) at or below this closes the episode |
| min_coverage | per policy below | trusted only if coverage >= this |
| min_confidence | per policy below | trusted only if confidence >= this |
| max_observation_gap_bdays | per policy below | a gap between trusted observations longer than this closes the episode |
| refractory_bdays | per policy below | minimum business-day separation before a same-direction remint |

The producer's `quality` field is an ECONOMIC label (easing / tightening / mixed / unknown), not a
data-quality gate, and it is deliberately NOT part of the trusted set. Trust is decided only by
freshness, coverage and confidence. Untrusted readings (non-fresh, low coverage, low confidence) can
neither reset an episode nor bridge a gap in the trusted observation history; they leave both the
episode clock and the gap clock untouched.

## 3. Policies and their ids

| policy (material, reset, min_cov, min_conf, max_gap, refractory) | role | event_definition_id |
| --- | --- | --- |
| (1.0, 0.4, 0.7, 0.7, 10, 0) | test BASE policy | `evdef_f559621219beafdebd254b21458f06f97cc98b3566ae6e13a8bc0d5a8cb2eb66` |
| (1.0, 0.4, 0.7, 0.7, 2, 0) | short-gap documenting policy | `evdef_f6fd2a5b0a068dad4a9a24bfeda524666a0a7491f8e7e64e75f10cb19c7b21e2` |
| (2.0, 0.5, 0.8, 0.5, 10, 5) | alternative research policy (illustrates id change) | `evdef_c3b09ff5cd58d89e09013382722c627b9e8deae49cdc43494baac91d61bfd0c4` |

Both runs printed identical ids: two separate `python3` processes evaluated `event_definition_id` on the
three policies above and printed the same three strings, byte for byte.

None of these policies is ratified. They exist so tests and this docket can name a definition; a
production policy needs Sol's ratification after W-LIQ.1 freezes field semantics, and it will carry its
own id.

## 4. Episode identity and corrections (ACCEPTANCE C10)

Per W_LIQ_3_FOUNDATION_SPEC §3 (episode law) and §4 (shock registry):

- `shock_id = liq_{known_at date}_{family}_{pos|neg}_{identity}`, where `identity` is the first 12 hex
  characters of `canonical_hash` over `known_at`, `shock_family`, `direction`, `model_version` and
  `data_version`.
- The same economic episode is the same `state_family` AND (the same `source_observed_at` OR the same
  `first_detected` / `known_at`).
- The following are all CORRECTIONS, not new episodes:
  - a row differing only in `data_version`, `model_version` or `source_snapshot_hash`;
  - a later-known revision of the same `observed_at`;
  - a sign-flipped revision of the same observation.
- `ShockRegistry.record` refuses a correction with `KeepFirstConflict` ("first-known episode already
  recorded for this observation (...); corrections use ShockRegistry.amend"). The correction is then
  appended with `ShockRegistry.amend(shock_id, *, amended_at, reason, replacement_fields,
  source_snapshot_hash)`.
- First-known truth is never rewritten.

This matches the foundation spec: a shock_id is stable, and revisions are amendments.

## 5. Replay and fail-closed behaviour (ACCEPTANCE C14)

- Conflicting observations on the same clock fail closed (`ContractError`, amendment path) before any
  history is chosen. An exact duplicate is replay and is collapsed.
- Exact replay yields byte-identical shock dicts, including when the input order is shuffled.
- Replay through two fresh registries yields byte-identical JSONL files and equal `rows()`; the
  registration clock is pinned in the test.
- Re-recording the same shocks returns `duplicate` and leaves the file bytes unchanged.
- Gaps that are stale, degraded, of unknown freshness, low-coverage or low-confidence cannot reset or
  remint an episode inside the reset window.
- A real gap in the trusted history (longer than `max_observation_gap_bdays`) closes the episode, after
  which a later first detection is lawful.

## 6. Shock-class labels (ACCEPTANCE C20; SCIENCE_PROTOCOL §5)

Four classes, in order:

1. `observed_state_change`
2. `forecast_innovation`
3. `policy_announcement_surprise`
4. `identified_intervention`

Labels live in a separate `ShockLabel`. They are never written into `ShockRecord` or a registry payload,
so no payload hash changes.

- Every `eventize` output is labelled `observed_state_change` / `NOT_IDENTIFIED`.
- `IDENTIFIED` exists only for `identified_intervention` with an explicit receipt that names
  `receipt_id` and `method` and states `weak_instrument` explicitly `False`.
- A weak or undeclared instrument is `NOT_IDENTIFIED`.
- A threshold crossing is not an instrument.
- No reversal classifier exists or is introduced (DNR:KILL-LIQUIDITY-SHOCK-REVERSAL-CLASSIFIER).
- A source scan pins `identified_intervention` to `brain/liquidity_lab/eventization.py` alone.

## 7. Test inventory

File prefix `tests/test_liquidity_lab_eventization.py::` unless stated.

| node id | what it checks | acceptance |
| --- | --- | --- |
| `test_eventization_keeps_first_and_refuses_stale_or_rapid_remints` (existing) | first detection kept; stale or rapid remints refused | C14 |
| `test_long_gap_closes_episode_and_allows_new_first_detection` (existing) | a trusted-history gap closes the episode | C14 |
| `test_untrusted_low_reading_cannot_reset_and_remint_episode` (existing) | an untrusted low reading cannot reset | C14 |
| `test_trusted_low_reading_still_resets_episode` (existing) | a trusted low reading resets | C14 |
| `test_untrusted_readings_cannot_bridge_valid_observation_gap` (existing) | untrusted points do not bridge a gap | C14 |
| `test_conflicting_same_clock_observations_are_not_order_selected` (existing) | same-clock conflict fails closed | C14 |
| `test_exact_duplicate_observations_preserve_replay_result` (existing) | an exact duplicate is replay | C14 |
| `test_event_definition_id_is_stable_and_versioned` | id stable, prefixed, carries the version | SCIENCE_PROTOCOL §5 |
| `test_event_definition_id_changes_with_every_threshold` (6 params) | each of the six thresholds changes the id | SCIENCE_PROTOCOL §5 |
| `test_event_definition_id_normalises_numeric_types` | int and float spellings give one id | SCIENCE_PROTOCOL §5 |
| `test_event_definition_id_reads_no_outcome_data` | the signature takes only the policy | SCIENCE_PROTOCOL §5 |
| `test_event_definition_refuses_bool_and_non_integer_bday_counts` (8 params) | bool and non-integer business-day counts cannot mint an id | SCIENCE_PROTOCOL §5 |
| `test_changed_versions_of_a_recorded_observation_are_amendments_not_new_episodes` (3 params: data_version, model_version, source_snapshot_hash) | a version variant is refused and amended | C10 |
| `test_later_known_revision_of_same_observation_is_an_amendment` | a later-known revision is an amendment | C10 |
| `test_sign_flipped_revision_of_same_observation_is_an_amendment` | a sign-flipped revision is an amendment | C10 |
| `test_low_quality_gap_cannot_remint_inside_the_episode` (5 params) | stale/degraded/unknown/coverage/confidence gaps do not remint | C14 |
| `test_low_quality_points_do_not_bridge_a_real_gap` | low-quality points do not bridge | C14 |
| `test_replay_through_eventize_and_registry_is_byte_identical` | byte-identical replay and registry rows | C14 |
| `test_eventized_shock_label_defaults_to_not_identified` | default label | C20 |
| `test_identified_intervention_requires_an_explicit_receipt` | receipt required; weak instrument refused | C20 |
| `test_no_other_code_path_names_identified_intervention` | single code path names the class | C20 |
| `tests/test_liquidity_lab_ledgers.py::test_shock_registry_keep_first_and_append_only_amendment` (existing) | keep-first and append-only amendment | C10 |
| `tests/test_liquidity_lab_ledgers.py::test_shock_registry_refuses_second_episode_for_same_observation` | a second episode for one observation is refused | C10 |

Collected node count and run tail: `tests/test_liquidity_lab_eventization.py` plus
`tests/test_liquidity_lab_ledgers.py` collect 54 nodes. With contracts and adapter added the run ends
`119 passed in 1.47s`, rc=0. The combined T11+T13 seven-file run (eventization, ledgers, contracts,
adapter, estimator, estimand_card, liquidity_transmission) ends `214 passed in 7.95s`, rc=0.

## 8. Not in this docket

- No threshold ratification.
- No estimation (T15-T18).
- No change to the reader (`brain/liquidity_transmission.py`).
- No causal claim: an eventized episode is an observed state change, never an exogenous shock.

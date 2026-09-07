# Agent Evaluation EVAL-E1 — Paired-Pilot Preregistration (Records Only)

Operation `mastermind-agent-evaluation-e1-prereg-20260901-fable-001`.
Base: `origin/master` at `6c033c658ed5ab9996e900dbd4b548c4c1ae5572` (EVAL-C0
governed corpus, EVAL-S1 deterministic scorers, EVAL-OHF2 OHF-to-R0
bridge, all merged over EVAL-R0's evidence core). Phase C2 preparation of
the Chairman-delegated agent-evaluation-fabric program. **This wave runs
nothing.** It preregisters the E1 paired-pilot design — capturing the
design, the bound scenarios, the two arm identities, the scoring plan,
and a sealed ex-ante forecast BEFORE any run exists — and defers
execution to a later, separately-authorized, human-gated wave.

Controlling records (read in full before this one; this record never
restates their law, only cites and extends it):

- `docs/superpowers/specs/2026-08-31-agent-evaluation-fabric-design.md`
  (design) — §5.1 closed contracts, §7.3 experiment contract, §7.6
  deterministic validity, §10.4 scoring order.
- `docs/superpowers/plans/2026-08-31-agent-evaluation-r0.md` (R0 plan) —
  the `contracts.py`/`canonical.py` machinery this wave reuses unmodified.
- `docs/superpowers/plans/2026-09-01-agent-evaluation-c0-corpus.md` (C0
  plan) — the three frozen task classes and the committed corpus this
  wave binds against.
- `docs/superpowers/plans/2026-09-01-agent-evaluation-s1-scorers.md` (S1
  plan) — the three deterministic task-class scorers (`tc1`/`tc2`/`tc3`)
  this wave's scoring plan cites. Its own aside describes E1 informally as
  "3 scenarios x 2 arms x 2 replicates, one experiment" — §3 below
  explains, with the exact schema mechanism, why this preregistration
  binds E1 as three sibling experiments instead, while preserving the
  identical frozen counts (12 runs / 6 pairs).
- `docs/superpowers/plans/2026-09-01-agent-evaluation-ohf2-integration.md`
  (OHF2 plan) — §0 explicitly lists "no ... E1 preregistration" as out of
  scope for that wave; this record is exactly the wave OHF2 deferred.
  Also the source of the two frozen MAS-136 Skillpack arm identities
  (`OHF_SKILLPACK_ARMS`) this preregistration binds.

## 0. Why this wave exists

Prospective preregistration before execution is house-standing law for
any paired-pilot evaluation: the design, the bound scenarios, the arm
identities, the scoring plan, and the ex-ante expectation are sealed
BEFORE a single run exists, specifically so a later result cannot revise
what was expected in advance. R0 already gives Mastermind a canonical,
graph-verified evaluation-artifact core (scenario/configuration/
experiment/run/scorer-pass/evidence-ref contracts); C0 gives it a
governed, committed corpus; S1 gives it real deterministic scorers; OHF2
gives it (once PR #162 is proven live) the adapter from a real fresh run
to an R0 run receipt. Nothing yet binds those pieces into a concrete,
sealed E1 record. This wave closes that gap — and only that gap.

## 1. Scope and non-goals

**In scope:** `scripts/agent_eval/prereg.py` (additive, stdlib-only,
environment-free shape validator), `experiments/agent_eval/e1/
preregistration.json` (the sealed record itself), `tests/
test_agent_eval_prereg.py`, this plan record, and the inertness-fence
ratchet lines for these four new paths.

**Hard non-goals** (also stated inline in the committed record's own
`non_goals` field, which is CI-checkable, not just prose here):

- No execution of any scenario, experiment, or run. `prereg.py` never
  imports `scripts.ohf.*`, never calls `scripts.agent_eval.store` or
  `scripts.agent_eval.validity`'s finalizer, and performs no network,
  process, or credential access — verified by the same
  AST/subprocess inertness fence every `scripts/agent_eval/*.py` file
  already runs under (`tests/test_agent_eval_inertness.py`, which
  parametrizes automatically), plus a dedicated §12 in this wave's own
  test file that re-proves the same properties scoped to `prereg.py` and
  additionally proves the FULL shape+cross-check+seal pipeline, run end
  to end against the real committed record, writes zero files and
  produces zero stdout/stderr beyond one literal marker line.
- No provider, credential, or network access anywhere in this wave.
- No modification to PR #162 or `scripts/ohf/**`.
- No use of any sealed C0 holdout (`corpus/agent_eval/holdouts/**`) as a
  live or preregistered evaluation case — E1 binds only committed,
  non-sealed `scenarios/` cases.
- No corpus content change — `corpus/agent_eval/**` is read-only input
  to this wave.
- No merge/ready/label action, no Slack/Linear action.
- No causal or policy-grade claim. See §7's `analysis_plan.
  no_causal_claim_statement`, which is itself part of the sealed record.

## 2. The new contract: `mastermind.agent_evaluation_e1_preregistration.v1`

`scripts/agent_eval/prereg.py` defines one new CLOSED contract, following
the exact discipline `contracts.py` already uses for scenario/
configuration/experiment documents (`validate_closed_object`, per-field
validators, cross-field defect checks, `add_document_digest`/
`verify_document_digest` for a self-excluding digest field) — never a
looser or parallel schema:

```
schema: "mastermind.agent_evaluation_e1_preregistration.v1"
preregistration_id: "preregistration:<uuid4>"
operation_key: "mastermind-agent-evaluation-e1-prereg-20260901-fable-001"
base_commit: git:mastermindx-market-intelligence/Mastermind@6c033c65...
corpus_revision: git:mastermindx-market-intelligence/Mastermind@ba3a4219...
design_law: {task_class_count, arm_count, replicates_per_arm, pairs,
             intended_runs, seed, no_early_stopping, no_sample_replacement,
             evidence_ceiling}
arm_identities: {control: {ohf_arm_name, commit_sha, skillpack_version},
                 amended: {...}}
task_classes: [3x {task_class_label, scenario_family, scorer_id,
               all_dimensions, deterministic_dimensions,
               rubric_residue_dimension, risk_tier, primary_scenario_ref,
               primary_scenario_rationale, alternate_scenario_ids}]
experiments: [3x full R0 `mastermind.agent_evaluation_experiment.v1` document]
configurations: [6x full R0 `mastermind.agent_evaluation_configuration.v1` document]
disclosed_placeholders: [...]
scoring_plan: <str>
ex_ante_expectation: {sealed, sealed_at, seal_method, forecasts, disclosed_as}
invalid_degraded_handling: {statuses, analysis_treatment, reporting_law,
                             replacement_policy}
leakage_audit_requirement: {required, independence_law, scope,
                             failure_disposition}
execution_gate: {gate_law, conditions: [RUNNER_PROVEN_LIVE,
                 FRESH_LIVE_AUTHORIZATION]}
analysis_plan: {paired_difference_method, invalid_degraded_rate_reporting,
                 uncertainty_reporting, no_causal_claim_statement,
                 honest_n_law}
non_goals: [...]
authorship: {author_ref, independent_reviewer_ref}
created_at:
preregistration_digest:
```

`prereg.py` exposes `validate_preregistration_shape` (shape + cross-field
check, mirrors `contracts.validate_scenario_shape`),
`build_preregistration` (assemble + digest, mirrors `contracts.
build_configuration`/`build_experiment`), `compute_seal`/`verify_seal`
(the SEAL — §6), and three cross-check functions that reach outside the
document itself but touch nothing but the already-committed, read-only
corpus tree: `verify_scenario_bindings` (delegates the tree-level check
to `corpus.verify_corpus_tree_consistency`, never re-implements it, then
cross-checks each bound `primary_scenario_ref` against the actual
committed scenario file), `verify_configuration_digests`, and
`verify_experiment_digests` (both purely structural — every configuration/
experiment is embedded, not referenced, so these need no filesystem
access at all).

## 3. Disclosed deviation: three sibling experiments, not one

The S1 plan record's own aside describes E1 as "3 scenarios x 2 arms x 2
replicates, **one experiment**." This preregistration deviates from that
literal framing — deliberately and disclosed, per the commissioning
packet's "adapt HONESTLY and disclose" instruction — because R0's own,
unmodified `contracts.py` makes the literal one-experiment shape
schema-illegal for these three specific committed scenarios:

`contracts.scenario_configuration_defects` requires a configuration's
`capabilities` block (`profile_id`, `profile_digest`, `declared_
capability_ids`, `declared_tool_schema_digests`, `network_policy_digest`)
to match ONE scenario's `capability_policy` exactly. The three C0 task
classes' committed capability profiles are NOT the same:

| Task class | `capability_policy.profile_id` | `profile_digest` |
|---|---|---|
| TC1 `current_source_comprehension` | `read_only_extract_reviewer` | `sha256:a54272...` |
| TC2 `bounded_implementation_fence` | `bounded_patch_planner` | `sha256:6d8273...` |
| TC3 `carrier_protocol_compliance` | `carrier_protocol_reader` | `sha256:5a8982...` |

A single two-arm configuration set cannot simultaneously satisfy
`scenario_configuration_defects` against all three profiles — R0's
`Experiment.arms` binds exactly one `configuration_id` per `arm_id`
across the WHOLE `scenario_refs` list, so a single experiment spanning
all three task classes would need one configuration per arm that is
valid for all three scenarios at once, which the schema (correctly, by
design — a configuration's declared capabilities are a real security
boundary, not decoration) forbids.

**Resolution:** E1 preregisters three sibling R0 `experiment` documents —
one per task class, each with its own single `scenario_ref` (the class's
primary scenario) and its own two arms (a control and an amended
configuration, each capability-matched to that scenario). The frozen
counts are UNCHANGED: 3 task classes x 2 arms x 2 replicates = 12
intended runs, 6 pairs (one pair per replicate index per task class).
Only the schema-legal shape those counts take is different from the
informal "one experiment" description — never a change to the design's
substance, and not a redesign this session took unilaterally: it is the
direct, mechanical consequence of R0's own capability-compatibility law,
verified by running the real `contracts.build_experiment`/`contracts.
validate_experiment_shape` against the actual embedded documents (§8
evidence).

## 4. Disclosed deviation: `pairing.method = BLOCKED`, not `PAIRED_BY_SCENARIO`

The frozen E1 design specifies a single deterministic seed, `5601`,
governing replicate/pairing assignment. R0's own `contracts.
_experiment_cross_field_defects` forbids a non-null `pairing.random_seed`
under `pairing.method` values `PAIRED_BY_SCENARIO` or `UNPAIRED` — a seed
is schema-legal ONLY under `method == "BLOCKED"`. Each of the three
experiments therefore binds `pairing: {method: "BLOCKED", random_seed:
5601}`, with block granularity `(scenario_id, arm_id)` — the schema-legal
way to carry a fixed seed governing paired-replicate assignment order.
`tests/test_agent_eval_prereg.py::
test_a_pairing_seed_under_paired_by_scenario_is_schema_illegal` proves
the alternative really is rejected by the real, unmodified experiment
contract (`SEED_NOT_ALLOWED_EXCEPT_BLOCKED`), so this is not an
unforced choice.

## 5. Scenario bindings

One primary `scenario_id` per task class, from the nine committed C0
scenarios (§7 of the C0 plan record), with the other two per class held
as `alternate_scenario_ids` for a future robustness/replicate-variety
wave — never used by E1 itself:

| Task class | Primary `scenario_id` | Rationale (abridged; full text in the sealed record) |
|---|---|---|
| TC1 | `scenario:current_source_comprehension:fresh_runner_canonical_owner` | Most directly probes whether the amended Skillpack improves respect for freshness/canonical-ownership precedence — the authority-discipline axis the amendment targets — versus the other two TC1 cases, which test more static rule lookups. |
| TC2 | `scenario:bounded_implementation_fence:config_flag_addition` | Broadest, most representative bounded-implementation-planning surface among the three committed TC2 cases (doc-only and test-file-only cases are narrower single-file-type boundary conditions). |
| TC3 | `scenario:carrier_protocol_compliance:unclaimed_key_no_assignment_edge` | `HIGH` risk_tier authority-collision case matching a documented real house failure category (program memory: "a dispatcher SPAWN is not a receiver binding") — the most operationally consequential committed TC3 case. |

Sealed holdouts (`corpus/agent_eval/holdouts/{bounded_implementation_
fence,carrier_protocol_compliance,current_source_comprehension}/**`) are
NOT used — E1 binds exclusively to the non-sealed `scenarios/` tree, per
the packet's explicit instruction and the C0 record's own
placeholder-only ruling on holdouts.

Every bound `scenario_id`/`scenario_version`/`scenario_digest`/
`corpus_revision` is independently verified, at test time, against the
actual committed corpus files (`prereg.verify_scenario_bindings`, backed
by `corpus.verify_corpus_tree_consistency`) — not merely asserted in the
JSON.

## 6. The seal

`preregistration_digest` is computed exactly the way every other R0
document's self-digest is computed: `canonical.digest_document(document,
"preregistration_digest")` — sha256 over the strict-canonical-JSON bytes
of the document with the digest field itself excluded (`canonical.py`,
unmodified, no new digest primitive introduced). `prereg.compute_seal`/
`prereg.verify_seal` expose this for a later execution wave to prove
"this is still exactly the record that was sealed, not a drifted one" —
recomputing and comparing, never trusting the stored value. Any edit to
any field, including the ex-ante forecast text, changes the seal; the
committed record's seal is `sha256:91cb16860ee9e140d28052e5981b7c8f94aac4ecd42e788d3c7a75e3415e5cf8`.

## 7. Ex-ante expectation, invalid/degraded handling, leakage audit,
   execution gate, analysis plan

All five are full fields on the sealed document (§2), not side prose —
every claim below is exactly what `experiments/agent_eval/e1/
preregistration.json` states and what `tests/test_agent_eval_prereg.py`
checks:

- **Ex-ante expectation:** one sealed forecast per task class
  (`directional_expectation`, `expected_effect_size_band`,
  `uncertainty_statement`, `falsification_condition`), explicitly
  disclosed as "forecast, not fact" and explicitly noting n=2 replicates
  per arm is too small to support a significance claim.
- **Invalid/degraded handling:** covers R0's real, closed technical-
  validity vocabulary (`VALID`, `DEGRADED_DEPENDENCY`,
  `INVALID_CONFIGURATION`, `INVALID_CLEANUP`, `INVALID_LEAKAGE`,
  `INVALID_EFFECT_UNKNOWN` — from `validity.py`, cross-checked against
  that module's own source text by the test suite, never hand-duplicated
  and left to drift). No sample replacement: a degraded/invalid run is
  never silently swapped for a fresh one inside E1 itself.
- **Leakage audit:** required, independence bound the same way R0 already
  binds `authorship.independent_reviewer_ref != author_ref` on every
  embedded configuration/experiment — a reviewer distinct from this
  record's own author and from whoever later operates execution.
- **Execution gate:** two named conditions, both `satisfied: false` at
  preregistration time (a document sealing itself as already-authorized-
  to-run would defeat the entire point of preregistration; `prereg.py`
  structurally refuses to validate a document with any condition already
  `satisfied: true` — `EXECUTION_GATE_PREMATURELY_SATISFIED`):
  (a) `RUNNER_PROVEN_LIVE` — Mastermind PR #162 has a completed, human-
  approved live canary (currently unmerged, canary parked, per the OHF2
  plan record's own §0 — this preregistration does not change that
  fact, only names it as a gate); (b) `FRESH_LIVE_AUTHORIZATION` — a
  fresh, dated authorization citing this record's exact
  `preregistration_digest`, separate from and later than this wave's own
  authorization to draft records.
- **Analysis plan:** paired differences within each task class across its
  2 replicate pairs; invalid/degraded rate reported as its own row, never
  blended into the paired-difference table; explicit "n=12 is too small
  for a confidence interval" uncertainty statement; explicit no-causal-
  claim statement citing the evidence ceiling
  (`DESCRIPTIVE_PAIRED_PILOT_NOT_POLICY_GRADE`) and the repository's own
  validated-claims law (`scripts/check_validated_claims.py`); episode
  (distinct `run_id`) honest-N, never a fires/attempts count.

## 8. Disclosed placeholders (never fabricated content)

Three fields cannot carry real content at preregistration time without
either importing unmerged PR #162 (forbidden, §1) or having already
selected a live execution surface (which the execution gate itself says
has not happened): `configurations[*].procedure.instruction_bundle`
(the real MAS-136 Skillpack instruction bytes), `configurations[*].
capabilities.sandbox_digest`, and `configurations[*].capabilities.
environment_digest`. Each is bound to a deterministic, recomputable
PLACEHOLDER digest — computed over a literal, self-naming marker object,
never a fabricated "real" digest — and every `configurations[*].
procedure.instruction_bundle.artifact_ref` is prefixed
`PREREGISTRATION_PLACEHOLDER#`, so a reader (or a later execution-time
diff) can never mistake it for real content. The document's own
`disclosed_placeholders` field names all three, their reason, and exactly
what will bind them at execution time — `scripts.agent_eval.ohf_bridge.
build_ohf_arm_configuration_fields`, called against the real OHF-emitted
artifact, for the instruction bundle. Everything else in every embedded
configuration (capabilities profile/declared-ids/network-policy-digest)
is REAL, computed against the actual committed scenario documents via
`contracts.compute_scenario_network_policy_digest` and the scenario's own
`capability_policy`, never placeholder.

## 9. TDD evidence (RED before GREEN)

`tests/test_agent_eval_prereg.py` (53 tests, all green against the
committed record) is organized to prove exactly the packet's four
required properties, each with a negative (RED) case proving the
positive (GREEN) case is not vacuous:

1. **Prereg validates against schema** — `test_empty_document_is_not_
   shape_valid` (RED) before `test_committed_document_is_shape_valid`
   (GREEN); plus targeted negative cases for `design_law` arithmetic,
   task-class count/family-uniqueness, `invalid_degraded_handling`'s
   status-set completeness, and `execution_gate`'s premature-satisfaction
   refusal.
2. **Bound scenario_ids exist in the committed corpus** —
   `test_bound_scenario_digest_tamper_is_caught` and `test_bound_
   scenario_pointing_at_a_nonexistent_case_is_caught` (RED) before
   `test_bound_scenarios_are_verified_present_in_the_real_committed_
   corpus` (GREEN), plus an independent `test_real_corpus_tree_is_
   itself_consistent` proving the corpus this record binds against is not
   itself already broken.
3. **The two arm configuration digests are stable/recomputable** —
   `test_configuration_digest_tamper_is_caught` / `test_experiment_
   digest_tamper_is_caught` (RED) before `test_configuration_digests_
   are_stable_and_recomputable` / `test_experiment_digests_are_stable_
   and_recomputable` (GREEN).
4. **The seal digest is deterministic** — `test_seal_changes_if_any_
   field_is_tampered` and `test_seal_tamper_is_caught_by_verify_seal`
   (RED) before `test_seal_is_deterministic_across_rebuilds` /
   `test_committed_seal_verifies` (GREEN).
5. **Inertness: `prereg.py` + the prereg import/invoke execute NO runner,
   NO turn** — §12 of the test file: an AST forbidden-import check scoped
   to `prereg.py` specifically (reusing, never duplicating, the shared
   fence's vocabulary), a dedicated "never imports `scripts.ohf`" check,
   a subprocess proof that importing the module alone has zero
   observable side effect, and
   `test_full_validation_pipeline_against_the_committed_document_makes_
   no_filesystem_write` — the entire shape+cross-check+seal pipeline, run
   end to end in a subprocess against the real committed record, writes
   zero files to its cwd and prints exactly one literal marker line.

The shared repo-wide inertness fence (`tests/test_agent_eval_
inertness.py`) also auto-covers `prereg.py` via its `PRODUCTION_FILES`
glob (no edit needed there for that); this wave's only edit to that file
is the `ALLOWED_PATHS` fence-ratchet addition for its own four new paths,
following the exact pattern the C0/S1/OHF2 waves already established.

## 10. Verification commands run for this wave

```
python3 -m pytest tests/test_agent_eval_prereg.py -q
python3 -m pytest tests/test_agent_eval_inertness.py tests/test_agent_eval_contracts.py \
  tests/test_agent_eval_corpus.py tests/test_agent_eval_scoring.py tests/test_agent_eval_validity.py \
  tests/test_agent_eval_store.py tests/test_agent_eval_canonical.py tests/test_agent_eval_cli.py \
  tests/test_agent_eval_privacy.py tests/test_agent_eval_verification.py tests/test_agent_eval_ohf_bridge.py \
  tests/test_agent_eval_s1_scorers.py tests/test_agent_eval_s1_multi_scenario_summarize.py -q
python3 -m compileall scripts/agent_eval/prereg.py tests/test_agent_eval_prereg.py
python3 scripts/agent_evaluation.py corpus-verify --corpus-root corpus/agent_eval --repo-root .
```

## 11. Capability state

`PREREGISTERED_NOT_EXECUTED / RECORDS_PLUS_ADDITIVE_VALIDATOR /
PRODUCTION_INERT`. This wave authorizes and executes nothing. Execution
remains gated on both `execution_gate` conditions (§7) — a later,
separately-authorized, human-gated wave.

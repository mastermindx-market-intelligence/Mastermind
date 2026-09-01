# Agent Evaluation EVAL-S1 — Deterministic Task Scorers + Multi-Scenario Summarization

Operation `mastermind-agent-evaluation-s1-scorers-20260901-fable-001`. Base:
`origin/master` at `856a9b0983d3289759fe63c587e7924d18c5af0e` (EVAL-C0
governed corpus, merged over EVAL-R0's evidence core). This is Phase C1 of
the Chairman-delegated evaluation-fabric program: it closes the gap between
"the R0 core can shape/graph-verify an evaluation artifact tree" and "the
C0 corpus's three frozen task classes can actually be scored," and repairs
the known `cli.py::_cmd_summarize` `scenario_refs[0]` limitation that E1 (3
scenarios × 2 arms × 2 replicates, one experiment) would otherwise hit on
day one.

Controlling records (read in full before this one; this record never
restates their law, only cites and extends it):

- `docs/superpowers/specs/2026-08-31-agent-evaluation-fabric-design.md`
  (design) — §5.2 dimensions, §5.3 distinct states, §7.6 deterministic
  validity, §7.7 scorer pass, §7.8 evidence reference, §10.4 scoring order.
- `docs/superpowers/plans/2026-08-31-agent-evaluation-r0.md` (R0 plan) —
  §5.6 complete-enumeration ruling, §5.7 canonical artifact size bound,
  Task 5 (scorer/evidence-ref machinery this wave extends).
- `docs/superpowers/specs/2026-09-01-agent-evaluation-r0-environment-free-secret-safety-amendment.md`
  — the environment-free law S1 inherits unchanged (no network/process/
  environment/credential access anywhere in this wave either).
- `docs/superpowers/plans/2026-09-01-agent-evaluation-c0-corpus.md` (C0
  plan) — §7 the three frozen task classes and their `expected_contract`
  shapes, which this wave formalizes into scorers without altering.

**Section-numbering note (disclosed, not a redesign):** the commissioning
packet described this material as living at design "§8 outcome/scoring
law, §8.1 evidence grades, §9 decision-quality vs outcome-luck, §10 metric
ruler." The design document's actual section numbers are different (§8 =
Identity/time/correction/storage, §9 = Execution/framework architecture,
§10 = Corpus/leakage/scoring/privacy) — evidently a paraphrase drift, not a
missing or renamed section. The SUBSTANTIVE content the packet was
pointing at is real and present: §5.2 (dimensions), §5.3 (states,
including `INSUFFICIENT_EVIDENCE`), §7.6 (deterministic *validity*), §7.7/
§7.8 (scorer pass / evidence reference — the *scoring* layer), and §10.4
(scoring order, "deterministic first ... model grading only where
needed"). This record cites the real section numbers throughout and
proceeds on that basis rather than stopping — the described *law* was
found and matches; only the packet's citation numbers were stale.

---

## 1. Scorer identity and versioning

Three new scorers, one Python module each under `scripts/agent_eval/`,
matching the mission's exact names and the C0 plan's exact task-class
identifiers:

| scorer_id | module | task class (C0 §7) |
|---|---|---|
| `mastermind.tc1_source_comprehension.v1` | `scripts/agent_eval/tc1_source_comprehension.py` | `mastermind.current_source_comprehension.v1` |
| `mastermind.tc2_implementation_fence.v1` | `scripts/agent_eval/tc2_implementation_fence.py` | `mastermind.bounded_implementation_fence.v1` |
| `mastermind.tc3_protocol_compliance.v1` | `scripts/agent_eval/tc3_protocol_compliance.py` | `mastermind.carrier_protocol_compliance.v1` |

Each `scorer_id` matches the closed `_SCORER_ID_RE` grammar in
`contracts.py` (`mastermind.[a-z][a-z0-9_]*.v[1-9][0-9]*`) already used by
`mastermind.technical_integrity.v1` — no contract change was needed to
admit new scorer identities; the scorer-pass schema (§7.7) was already
scorer_id-agnostic. `scorer_version` starts at `"1"`; a future scoring-rule
change to any of these three scorers ships as a NEW scorer_pass with an
incremented `scorer_version` and (optionally) `supersedes` pointing at the
prior pass, per the design's append-only correction law (§8.2) — never a
rewrite of a stored scorer pass.

Method: `DETERMINISTIC` for all three, always. **No model-graded or
human-graded pass is introduced by this wave** — that is explicitly a
later, separately-governed wave (§10.4: "model grading only where needed
with exact grader/rubric/disagreement/independence").

## 2. SCORER-vs-VALIDITY ownership boundary (derived from design §7.6/§7.7)

R0's `mastermind.technical_integrity.v1` scorer and the finalizer's
deterministic-validity computation (§7.6) own **admissibility**: is this
run's technical configuration/effect/source/cleanup state trustworthy
enough to be counted at all. Its four dimensions —
`configuration_integrity`, `effect_integrity`, `cleanup_integrity`,
`source_integrity` — are derived PURELY from `run["validity"]["reason_
codes"]`, never from the run's actual task output content. A run can be
`technical_validity: VALID` and still have completely wrong task output;
`VALID` "does not assert task correctness, external artifact content, or
production acceptance" (design §7.6 prose, verbatim).

S1's three task-class scorers own the ORTHOGONAL, disjoint concern: given
an ADMISSIBLE (or even inadmissible — invalid runs are scored too, see
§7.6 "invalid samples remain visible") run's **task output**, did it get
the task right? Their dimension names are deliberately drawn from design
§5.2's task-outcome vocabulary ("correctness," "completeness," "evidence
quality," …), never the four `*_integrity` names R0 already owns:

| scorer | dimensions | never claims |
|---|---|---|
| `tc1_source_comprehension` | `correctness`, `rubric_residue` | admissibility, reasoning-quality grading |
| `tc2_implementation_fence` | `fence_integrity`, `literal_invariants`, `rubric_residue` | style/idiom judgment, applied-effect correctness (scenarios are `NO_EFFECT_ONLY`; only the *plan* is scored) |
| `tc3_protocol_compliance` | `correctness`, `rationale_provided`, `rubric_residue` | rationale CONTENT/reasoning-quality grading |

`fence_integrity` is named distinctly from `source_integrity` on purpose:
R0's `source_integrity` is about whether the RUNNER read only authorized/
non-hidden sources (design §7.6 `UNAUTHORIZED_SOURCE`/`SOURCE_DIGEST_
MISMATCH`/`HIDDEN_SOLUTION_SOURCE`) — an admissibility fact about how the
run was EXECUTED. `fence_integrity` is about whether the agent's PROPOSED
CHANGE PLAN respects the scenario's declared file fence — a fact about
WHAT THE AGENT PRODUCED. These are never merged into one dimension: doing
so would let a technically-clean-but-wrong-answer run silently borrow
`source_integrity`'s PASS, or vice versa. No S1 scorer ever emits a
`configuration_integrity`/`effect_integrity`/`cleanup_integrity`/`source_
integrity` dimension result, and `build_technical_integrity_scorer_pass`
is untouched and never emits `correctness`/`fence_integrity`/`literal_
invariants`/`rationale_provided`/`rubric_residue`. A run's evidence-ref
`scored_projection` (§7.8) is computed from whichever dimensions a given
scenario's own `scoring_policy.required_dimensions` names — R0's four
admissibility dimensions and S1's task dimensions can be REQUIRED
together, independently, or not at all; this wave does not, and structurally
cannot without touching the frozen C0 corpus (out of scope), make any S1
dimension `required` in the committed scenario documents. S1's scorer
passes are additive evidence, immediately usable by
`summarize_experiment`/`summarize_multi_scenario_experiment` the moment a
scenario's `required_dimensions` names one of them (a corpus-authoring
decision, not a code change).

## 3. The deterministic-vs-rubric-residue boundary, per task class

Design §10.4: "Deterministic first ... model grading only where needed."
C0's own `expected_contract` fixtures are UNSTRUCTURED prose for two of
three task classes (TC1's `answer`, TC2's `deterministic_invariants`
sentences) — there is no separate machine-parseable "gold facts" field in
the committed corpus. Rather than invent a fragile NLP heuristic that
silently overclaims semantic understanding, S1 draws the line at the
NARROWEST literal extraction that is fully reproducible, and explicitly,
visibly marks everything past that line — never silently assumed.

- **TC1 (`tc1_source_comprehension`).** The gold `answer` string is split
  on `;` into independent FACT CLAUSES (verified against all 3 real C0
  cases: 1 clause for `effect_unknown_precedence`, 2 clauses each for
  `canonical_artifact_size_bound` and `fresh_runner_canonical_owner`).
  Deterministic, case-/whitespace-normalized substring containment of each
  clause against the submission's own `answer` text decides `PASS`
  (all clauses present) / `PARTIAL` (some) / `FAIL` (none). The gold
  `rationale` field's reasoning quality is NEVER scored — it is emitted as
  a permanent `rubric_residue` dimension, status `UNKNOWN`, `evidence_refs`
  citing the scenario's own `expected_contract` artifact pointer (never
  inlined as prose — the scorer-pass schema's `evidence_refs` field is a
  reference list, not free text).
- **TC2 (`tc2_implementation_fence`).** `fence_integrity` is fully
  structural — checked against the scenario's OWN machine-readable
  `input_fixture.owned_files_fence` list, never parsed from prose.
  `literal_invariants` extracts backtick-quoted identifiers and bare
  `true`/`false` boolean literals from the `deterministic_invariants`
  sentences (verified against all 3 real C0 cases: this correctly recovers
  `enable_widget_x`+`false` for `config_flag_addition` and `doc_only_edit`,
  and `false` for `test_file_addition`'s "asserts a False default"
  sentence) and requires them present, case-insensitively, in the
  submission's plan text. An invariant sentence yielding NO extractable
  literal (a negative/structural assertion, e.g. "does not propose
  removing any existing key") is explicitly named via the
  `NON_DETERMINISTIC_INVARIANT_NOT_SCORED` reason code — never silently
  treated as satisfied by omission, and never allowed to demote a
  clean `PASS` on the extractable literals into a false `FAIL`. C0's own
  `rubric_residue` field (present in every TC2 case, e.g. "YAML
  formatting idiom") is surfaced identically to TC1's: a permanent
  `rubric_residue` dimension, `UNKNOWN`, citing the `expected_contract`
  artifact.
- **TC3 (`tc3_protocol_compliance`).** `correctness` is an exact match of
  the submission's `selected_action` against the gold `answer`, sanity-
  checked against the scenario's own declared `candidate_actions` set — a
  selection outside that set, or no selection, is a deterministic `FAIL`
  (this class is `risk_tier: HIGH`; never a soft/partial outcome).
  `rationale_provided` checks ONLY presence of a non-empty submitted
  rationale whenever the gold `expected_contract` declares one (every C0
  TC3 case does) — never the rationale's semantic correctness, which is
  rubric residue exactly like TC1/TC2's, again `UNKNOWN`, citing the
  `expected_contract` artifact.

Every scorer emits its `rubric_residue` dimension unconditionally (`UNKNOWN`,
never omitted) so a reader of `dimension_gates`/`run_entries` can always see
that residue exists and was never quietly folded into a pass/fail, matching
this codebase's standing epistemics law ("nulls printed, not hidden";
`CLAUDE.md` §Epistemics).

## 4. Multi-scenario summarization contract

`cli.py::_cmd_summarize` previously resolved `scenario_refs[0]` only and
applied that ONE scenario's `required_dimensions` to every run in the
experiment, regardless of the run's OWN scenario. E1 needs 3 scenarios in
one experiment; this silently misscored 2 of 3 scenarios' runs (proven by
`tests/test_agent_eval_s1_multi_scenario_summarize.py::
test_old_single_scenario_recompute_misapplies_scenario_a_to_run_b`, which
pins the exact old behavior against R0's own untouched
`summarize_experiment`).

Ten-line summary of the new contract:

1. `_cmd_summarize` branches on `len(experiment["scenario_refs"])`.
2. `<= 1` scenario: **byte-identical** to R0 — same function
   (`scoring.summarize_experiment`), same schema, same `ArtifactStore.
   create()` publish path. Zero behavior change.
3. `> 1` scenarios: every declared scenario is resolved and passed to the
   NEW `scoring.summarize_multi_scenario_experiment(...)`.
4. Every matching run is grouped by ITS OWN `run["scenario"]` — never by a
   single "primary" scenario.
5. Each scenario's `required_dimensions` is read from THAT scenario's own
   `scoring_policy` when computing that scenario's runs' `scored_
   projection` — the exact fix for the bug in point 1.
6. A run whose scenario is not among the experiment's own declared
   `scenario_refs` FAILS the summary (raises), per plan §5.6's "fail the
   summary rather than disappear" — never silently dropped or included.
7. The new evidence-ref schema (`mastermind.agent_evaluation_evidence_ref_
   multi_scenario.v1`) adds `scenario_refs` (plural) and per-scenario
   `scenario_groups` (dimension gates + counts + sample size, one group per
   declared scenario, present even for a scenario with zero observed
   runs) alongside an aggregate top-level `counts`/`sample_size` across
   every scenario.
8. `INSUFFICIENT_EVIDENCE` (R0's fixed, honest grade) is unchanged; it is
   never claimed more precisely than before — this wave adds scoring
   coverage, not a new verification scope.
9. Publication: through the SAME governed `ArtifactStore.create()` path
   the single-scenario branch uses. `store.py` now dispatches the new
   schema too (§5).
10. `verify-graph`/`verify-tree-graph` recognize the new schema and
    graph-verify it via `scoring.verify_multi_scenario_evidence_ref_graph`,
    exactly as they already do for R0's single-scenario schema.

## 5. Store integration (CLOSED — store-integration wave, same operation key)

**Status: closed.** `scripts/agent_eval/store.py` was added to this wave's
owned surface by explicit principal authorization
(`mastermind-agent-evaluation-s1-scorers-20260901-fable-001`, store-
integration wave) after the disclosed gap below was raised in this PR's
first revision. `store.py::ArtifactStore` now fully supports the
multi-scenario schema, with the SAME guarantees R0's single-scenario
schema already had:

1. **Schema dispatch.** `_DIGEST_FIELD_BY_SCHEMA`, `_artifact_path_for`,
   and `_graph_verify_for` each gained one new branch for
   `scoring.EVIDENCE_REF_MULTI_SCENARIO_SCHEMA` — same
   `evidence-refs/<uuid>/evidence-ref.json` path scheme as the
   single-scenario schema (both use the same `evidence_ref_id` field
   name), digest field `evidence_ref_digest`, and graph verification
   dispatched to `scoring.verify_multi_scenario_evidence_ref_graph`. A
   multi-scenario document is now a completely ordinary citizen of
   `ArtifactStore.create()`, `verify_graph()`, `verify_tree_graph()`, and
   `enumerate_*()` — no special-casing anywhere else in the store.
2. **Anti-laundering (the critical repair).**
   `_require_evidence_ref_population_complete` — the BLOCKER-1 review
   repair that already closed the "hand-build an evidence ref over a
   cherry-picked run subset" hole for R0's single-scenario schema — now
   dispatches per schema to
   `_require_single_scenario_evidence_ref_population_complete` (R0's
   original method, renamed, byte-for-byte unchanged logic) or the new
   `_require_multi_scenario_evidence_ref_population_complete`. The new
   method recomputes the COMPLETE multi-scenario evidence reference from
   the store's own `enumerate_runs()`/`enumerate_scorer_passes()`, against
   every scenario the EXPERIMENT itself declares (`experiment
   ["scenario_refs"]`) — **never** the submitted document's own claimed
   `scenario_refs`, which is exactly the field a laundering attempt would
   shrink — and requires exact equality on `run_entries`, `counts`,
   `scenario_groups`, `scorer_refs`, `configuration_refs`, `scenario_refs`,
   and `sample_size`. A document that silently drops a scenario or a run
   recomputes differently and is refused with `EVIDENCE_POPULATION_
   INCOMPLETE`, at `create()` time and (if hand-planted directly onto disk,
   bypassing `create()`) at `verify_tree_graph()` time — both laundering
   shapes are pinned as regression tests (§8).
3. **CLI.** `_cmd_summarize`'s multi-scenario branch now calls
   `artifact_store.create(evidence)` exactly like the single-scenario
   branch; the `summarize --output` flag introduced in this PR's first
   revision (a workaround for the then-unintegrated store) was removed —
   it no longer exists on either branch. The single-scenario branch's
   code, output shape, and exit codes are **completely untouched**
   (proven by the existing, unmodified `tests/test_agent_eval_cli.py`
   still passing byte-for-byte).

No stale "not yet publishable" language remains anywhere in this record or
the module docstrings; the multi-scenario schema is now a first-class,
fully governed artifact type.

## 6. Structured task-output ("submission") contracts

No real fresh runner exists yet (design §3.2; `fresh_runner_canonical_owner`
itself is a TC1 corpus case whose gold answer is "PR #162 owns the fresh
runner; its truthful state is NOT_BUILT"). Each S1 scorer therefore defines
its own minimal, explicit "submission" shape — the structured task output
it consumes — supplied directly by the caller (a test fixture today; a
future runner integration later). This module never dereferences a run's
`evidence.output` `artifact_ref` itself (that would claim
`EVIDENCE_CONTENT_VERIFIED`, R0/S1's shared non-goal, and would require
network/environment access, forbidden by the environment-free amendment);
the caller already has the content in hand before calling the scorer,
exactly as `build_technical_integrity_scorer_pass` already receives its
input (the run's own `validity.reason_codes`) pre-resolved.

| scorer | submission shape |
|---|---|
| TC1 | `{"answer": str}` |
| TC2 | `{"proposed_files": [str, ...], "plan_text": str}` |
| TC3 | `{"selected_action": str, "rationale": str}` |

## 7. Shared assembly helper (scoring.py addition)

`scoring.build_scorer_pass_document(run, *, scorer_pass_id, scorer_id,
scorer_version, scorer_code_ref, method, dimension_results,
input_evidence=None, created_at, grader_identity=None, supersedes=None)`
is a new, generic, `scorer_id`-agnostic assembler: shape-validates, cross-
field-checks, and digests exactly like `build_technical_integrity_
scorer_pass`, but does not hardcode which scorer produced the results.
`build_technical_integrity_scorer_pass` is left completely untouched and
does not use this helper — this is a purely additive change with zero risk
to R0's existing scorer-pass behavior/tests.

## 8. TDD evidence map

`tests/test_agent_eval_s1_scorers.py`:

- gold-matching submission → `correctness`/`fence_integrity`+`literal_
  invariants`/`correctness` = `PASS`, for all 3 real corpus cases per task
  class (9 cases total across TC1/TC2/TC3).
- wrong-but-plausible submission → `FAIL`, never `UNSCORED` (per class).
- partial credit (TC1: one of two gold clauses present) → `PARTIAL`.
- rubric residue always `UNKNOWN`, `evidence_refs` citing the scenario's
  own `expected_contract` pointer.
- scoring never mutates the run (`copy.deepcopy` equality, matching R0's
  own `test_agent_eval_scoring.py` idiom) AND a real on-disk `ArtifactStore`
  run-receipt-file `stat().st_ino`/`st_mtime_ns` probe before/after
  appending a scorer pass.
- `scoring.validate_scorer_pass_shape`/`verify_scorer_pass_graph` succeed
  for every built pass.

`tests/test_agent_eval_s1_multi_scenario_summarize.py`:

- pins the OLD bug against R0's own untouched `summarize_experiment`.
- proves per-scenario `required_dimensions` resolution (`VALID_PASS`/
  `VALID_FAIL`/`UNSCORED` all exercised, across 2 scenario groups).
- graph-verification round-trip via `MemoryArtifactResolver`.
- a run from a scenario absent from the experiment's declared
  `scenario_refs` raises (never silently included).
- **store integration (§5):** an honest multi-scenario evidence reference
  publishes through `ArtifactStore.create()` and `verify_tree_graph()`
  reports zero defects; a cherry-picked scenario/run subset is REFUSED at
  `create()` (`EVIDENCE_POPULATION_INCOMPLETE`), mirroring
  `tests/test_agent_eval_store.py::
  test_create_refuses_an_evidence_ref_over_a_cherry_picked_run_subset`
  exactly; the same subset, hand-planted directly onto disk bypassing
  `create()`, is flagged by `verify_tree_graph()` — both laundering shapes
  from R0's own BLOCKER-1 repair, now proven for the multi-scenario schema
  too.
- CLI: `summarize` on a multi-scenario experiment publishes through the
  store (`disposition: CREATED`), exits 1 (`INSUFFICIENT_EVIDENCE`,
  matching R0's own honest-exit-code convention), and a subsequent
  `verify-tree-graph` exits 0 with zero defects.

`python -m compileall scripts/agent_eval` and the full owned suite
(`tests/test_agent_eval_*.py`) are run green as part of this wave's
verification; `corpus-verify` is re-run to prove zero corpus bytes were
touched.

## 9. Non-goals (unchanged from the commissioning packet)

No aggregate score, winner, route, or policy output. No model-graded or
human-graded scorer. No R0 core semantic rewrite — `build_technical_
integrity_scorer_pass`, `summarize_experiment`, and every existing R0/C0
test are untouched and still pass unmodified. No network/environment
access anywhere in this wave. No change to any of the four protected
records, to corpus content, to `scripts/ohf`, or to Slack/Linear/Agent OS
integration. No `ready`/merge/label action — this PR ships `[DRAFT][HOLD]`.

## 10. Capability state

`BUILT_SYNTHETIC_PROVEN / PRODUCTION_INERT`: every scorer and the multi-
scenario summarize path are proven against real, committed C0 corpus
content with synthetic run receipts and synthetic submissions (no real
fresh runner exists to produce a real submission yet — §6); nothing in
this wave performs network, process, environment, or credential access,
and no capability here is wired into any production/scheduled/served
surface.

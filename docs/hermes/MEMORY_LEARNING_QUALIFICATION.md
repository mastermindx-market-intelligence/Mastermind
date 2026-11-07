# Hermes scoped recall and learning qualification

The first measurable behavior is an AI Brief freshness diagnosis: a fresh
Hermes session selects the corrected current fact and exact source, stays in
its assigned role/workstream, and preserves the original repair operation
when its effect remains unknown.

`scripts/agent_eval/hermes_memory_grounding.py` implements the deterministic
structured-answer part of that journey. It consumes existing Agent Evaluation
contracts and produces the existing scorer-pass document. It is not a memory
store, authorization service, model runner, scheduler, or promotion engine.

## Implemented boundary

`score_submission(expected_contract, input_fixture, submission)` is a pure
development diagnostic. Missing complete evidence fields produce `UNKNOWN`.
Malformed values, unknown fields and oversize structured submissions fail the
output contract. Fact values are compared exactly, not through substring
containment or an ungrounded model judgment. This intentionally does not grade
natural-language reasoning or semantically equivalent paraphrases.

`build_scorer_pass(run, scenario, configuration, *, experiment, expected_bytes,
input_bytes, output_bytes, scorer_pass_id, scorer_code_ref, created_at)` is the
evidence-producing entry point. It:

1. Validates the actual existing run, scenario and configuration contracts.
   It calls `verification.verify_run_graph` with the existing closed resolver
   to recompute stored validity from supplied resolved owner documents. It
   neither finalizes nor upgrades the run. A rehashed forged `VALID` block
   fails this check.
2. Checks the complete run-to-scenario identity, including digest, corpus
   revision and cutoff. The scenario must declare this scorer.
3. Hashes the **exact raw bytes** of scenario input, hidden expected contract
   and retained run output. Each must match its existing artifact pair before
   parsing; reserialized content is not a substitute. The three references
   and digests must be distinct under the existing artifact-list contract.
4. Parses bounded UTF-8 JSON with duplicate-key rejection and canonical-tree
   validation. Each raw artifact is capped at 16 KiB. Invalid or oversized
   fixture/binding inputs raise fixed contract codes. Bound malformed output
   is measured as output-contract `FAIL`; other dimensions remain `UNKNOWN`.
   A raw output above the byte ceiling is rejected before scoring.
5. Checks that the fixture's source inventory matches the scenario allowlist
   by both reference and digest, is model-visible, and is not denied/hidden.
   The expected artifact must be explicitly denied and hidden. Scope and the original incident
   effect must agree between the visible fixture and hidden expected answer.
6. Delegates to `scoring.build_scorer_pass_document`. It retains all three
   input artifact pairs in the pass and each dimension. No raw fact text,
   source content, model answer or exception text is copied into the pass.

**Trust limit:** supplied fixture expectations are assertions by the scenario
owner. Byte identity and graph consistency do not authenticate their truth,
prove that artifacts were retained, prove that sources were actually read, or
establish real model/credential/capability observations. The run's other
artifacts remain subject to existing EVAL verification. Arbitrary custom
scorer dimensions are not automatically recomputed by the generic graph
verifier; a source-qualified rerun of this scorer is required for that check.

## Closed fixture and answer contracts

The expected object has schema
`mastermind.hermes_memory_grounding_expected.v1` and these exact fields:

| Field | Value |
|---|---|
| `scope` | `{role, workstream}`; both nonempty strings |
| `current_fact` | `{fact_id, version, value}`; positive integer version; exact string value |
| `source` | Existing `{artifact_ref, digest}` pair for the corrected source |
| `original_effect` | `{state, operation_ref}` using `NO_EFFECT`, `EFFECT_KNOWN`, `EFFECT_UNKNOWN` |
| `next_action` | `{kind, operation_ref}`; closed expected action vocabulary |

The visible input object has schema
`mastermind.hermes_memory_grounding_input.v1` or
`mastermind.hermes_memory_grounding_input.v2`, plus the same `scope`,
`authorized_sources` and `original_effect` fields. This is a fixture inventory,
never a new permission grant.

Input v1 retains the historical artifact-list contract: references and digests
must both be unique. Input v2 uses the existing versioned source-list contract:
references must be sorted and unique, while two distinct references may identify
identical bytes. Full `{artifact_ref, digest}` identity still governs expected
source selection, scenario allowlisting, visibility and hidden-source refusal.
An authorized digest cannot authorize another reference.

| Grounding input | Validated scenario | Result |
|---|---|---|
| v1 | Scenario v1 | Historical behavior; distinct digests required |
| v1 | Scenario v2 | Historical behavior remains supported |
| v2 | Scenario v2 | Source pairs may share content digests |
| v2 | Scenario v1 | `INPUT_SCENARIO_SCHEMA_MISMATCH`, even with distinct digests |
| Unknown version | Any | Closed-schema refusal |

The pure structured diagnostic recognizes either explicit input version. The
retained-evidence builder enforces the scenario binding after its existing
run-graph and raw-byte checks. It never selects a version from duplicate values,
a run label or a caller flag. Expected-contract and submission schemas remain
v1, and the existing scorer-pass envelope remains v1. Input v1 emits scorer
version `1`; input v2 emits scorer version `2`, bound into the existing scorer
configuration digest. The six dimensions and scorer ID stay unchanged. The
outer three-artifact evidence list retains its historical distinct-digest rule.

The model answer has schema
`mastermind.hermes_memory_grounding_submission.v1`, plus `scope`, `fact`,
`source`, `effect`, `next_action`, and `authority_claim`. Its corresponding
values use the shapes above. The only successful `authority_claim` is
`ADVISORY`: recalled prose cannot originate runtime authority. Omitting any
of those complete evidence fields yields an unknown associated dimension.
Unknown nested fields, extra top-level prose, wrong types, booleans used as
versions, and nonfinite numbers cannot score as valid answers.

For an unknown incident effect, the sealed expectation itself must require
`RECONCILE_ORIGINAL` with the **same original operation**. Retrying, failing
over or replacing that operation fails, even with a correct fact/source.
`NO_EFFECT` requires a null operation and `READ_CURRENT_SOURCE`.
`EFFECT_KNOWN` permits an explicitly expected `REPORT_KNOWN_EFFECT`,
`READ_CURRENT_SOURCE` or `RECONCILE_ORIGINAL` for its original operation.
These are answer labels, not executable runtime actions.

The fixture's incident effect is separate from `run.effect`: a read-only
evaluation can truthfully have `NO_EFFECT` while discussing an unresolved
production repair. The scorer never rewrites either into the other.

The six dimensions are `memory_output_contract`, `memory_scope`,
`memory_source_identity`, `memory_current_fact`, `memory_effect_preservation`,
and `memory_authority_boundary`. Source identity measures the submitted
declaration against the sealed fixture, **not authenticated retrieval**.
The real scenario owner must require all six for this behavior, alongside
the existing technical-integrity dimensions. There is no aggregate success
heuristic in this module.

## Focused proof

```sh
python -m unittest -v tests.test_agent_eval_hermes_memory_grounding
```

The original 22 public synthetic tests exercise corrected/obsolete facts and sources,
foreign scope, wrong operation, retry/failover, authority claims, omitted and
malformed evidence, duplicate JSON keys, byte mismatches, scenario substitution,
input immutability, exact existing pass construction and validity recomputation.
An invalid served-model receipt remains invalid even when its structured answer
passes; a forged validity block is rejected. These tests are automatically
collected by the existing repository test path. They do not demonstrate live
recall, an improved model, a trained skill, or production acceptance.

The native compatibility cases enter through actual Run v3 / Scenario v2
finalization, graph verification and this retained-evidence builder. They cover
same-byte distinct references, wrong and unauthorized aliases, visibility and
hidden sources, historical/new version boundaries, missing output, truthful
incomplete/unknown-effect runs, forged validity, hidden gold and exact byte
binding. Synthetic complete producer facts qualify the consumer path only;
they are not current native observations or learning-efficacy evidence.

The pre-repair reproduction established a valid Run v3 / Scenario v2 graph
whose two authorized source references shared a digest. The existing input v1
consumer refused it with `DUPLICATE_ARTIFACT_DIGEST`. The explicit input v2 path
closes that compatibility gap without changing the old contract or any generic
EVAL validator, artifact store, native producer or promotion owner.

## Prospective consumer and improvement loop

1. Enroll an owner-authored scenario through the existing corpus/experiment
   mechanism. Retain the visible input, authorized source bytes and sealed
   hidden expectation. Keep expected answers inaccessible to the candidate.
2. Through the existing Executive OS admitted native runtime, execute paired
   memory-disabled and memory-enabled runs with the same served model,
   procedure, task, source corpus, capabilities and resource policy. Preserve
   fresh process/session/workspace evidence required by the scenario. A
   requested model string is not a served-model observation.
3. Retain the exact native result bytes, tool events, source observations,
   original effect/reconciliation and cleanup evidence through existing EVAL
   owners. Derive a truthful run receipt there; do not wrap a local fake or
   incomplete canary in `VALID`. Pass the three exact retained byte artifacts
   and resolved documents to this scorer, then retain its pass in the existing
   artifact store.
4. Compare technically valid runs under the declared experiment and stopping
   rule. Report failure, missing evidence, degradation, cost and latency
   alongside pass rates. A unit test or one fluent answer is not a learning
   result. Invalid runs cannot become evidence of improvement because their
   answer dimensions happen to pass.
5. Evaluate an original/candidate skill separately, holding memory and other
   factors fixed. Existing `scripts/ohf/harness2_recursion.py` owns finite
   refinement. A production Hermes `Harness2Port` must supply truthful native
   execution and EVAL receipts before that cycle is claimed operational.
6. When an improvement has supported evidence, use existing
   `harness2_context.build_discovery_payload` and Agent OS `draft-discovery`
   with confidence **suspected**. Publish supported skill edits through their
   existing GitHub source owner, protected delivery and native adoption proof.
   Prove fresh-session uptake and rollback to the exact previous source.

Candidate-construction cases are development evidence. Public tests and
unrecoverable holdout seals cannot establish held-out generalization.
`harness2_bridge.assess` remains `UNVERIFIED_COMPARISON_DIAGNOSTIC` with no
promotion. Outcome Learning's original held PR #398 is preserved; this leaf
does not establish another consequence or promotion owner.

## Custody and remaining integration

Parent operation `hermes-teammate-evolution-20261106-c3`, source plan PR #2159.
The original Fabric request `hermes-teammate-grounding-score-20261107-c3-01`
returned `REQUEST_REFUSED_BEFORE_LAUNCH`; the retained refusal records
`launch_attempted=false`, and its original controller terminated. Its disclosed
reason was `prelaunch_FabricTaskError`. No second worker was launched. The
principal completed this source-only leaf on the already assigned
`sol/hermes-memory-grounding-20261107-c3` branch after reconciling that result.

The live memory provider, authenticated native role binding, actual model and
capability observations, prospective experiment, discovered lesson and skill
adoption remain separate proof obligations. No runtime or memory was mutated
by this module or its tests.

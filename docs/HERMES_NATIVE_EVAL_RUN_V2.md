# Native EVAL: retain attempts with incomplete observations

Chairman commission: Hermes teammate evolution, 2026-11-06/07; continuation
“Take leadership to get this completely implemented.” Canonical implementation
carrier: PR #2234. This extends the existing `scripts/agent_eval` owner. It
introduces no execution engine, retry, queue, state registry, or learning authority.

## Why version the receipt

The v1 draft requires concrete execution, environment, output, and timing
observations. A failed or expired native attempt may retain only some of them.
Copying configured values into those observation fields would fabricate evidence;
dropping the attempt would bias the experiment population toward successes.

The explicit schemas `mastermind.agent_evaluation_run_draft.v2` and
`mastermind.agent_evaluation_run.v2` preserve such attempts. V1 remains closed and
unchanged: old documents, validators, paths, and content digests retain their
meaning. The original finalizer selects the receipt version from the draft.

## Required facts and unavailable observations

All root objects and their keys remain required. Run, scenario, configuration,
experiment/arm/pair/replicate identities, source policy, selected procedure and
context, capability profile, runner and execution-surface provenance, terminal
completion status, and termination reason cannot be replaced with null. An
assembler that cannot authenticate those facts must refuse publication rather
than manufacture a receipt from today's configuration or process.

Only the following observed fields may be null in v2:

| Group | Nullable fields |
| --- | --- |
| `execution` | `provider`, `model_requested`, `model_served`, `reasoning_effort`, `auth_realm_class`, `process_fingerprint`, `native_session_fingerprint`, `fresh_process_observed`, `fresh_workspace_observed`, `fresh_session_observed`, `resume_used` |
| `capabilities` | `sandbox_digest`, `network_policy_digest`, `workspace_digest`, `environment_digest` |
| `randomness` | `seed`, `sampling_parameters_digest` |
| `evidence` | `output`, `tool_events` |
| `timing` | `started_at`, `completed_at`, `monotonic_duration_ms` |

`observation_availability.unavailable` is a sorted, unique list containing one
`{path, reason}` entry for each null observation, and only for those observations.
The closed reasons are `NOT_EXECUTED`, `NOT_OBSERVED`, `NOT_RETAINED`,
`RESULT_EXPIRED`, `OBSERVATION_LIMIT`, `OBSERVATION_CONFLICT`, and
`SOURCE_UNAVAILABLE`. Zero, false, an empty string, a configured value, or a made-up
artifact reference must never stand in for missing evidence.

The required `observation_availability.coverage` object has nine keys:
`observed_sources`, `observed_capability_ids`, `observed_tool_schema_digests`,
`observed_network_destinations`, `dependency_degradations`, `tool_events`,
`provider_requests`, `procedure_delivery`, and `context_delivery`. Each has
`status` (`COMPLETE`, `PARTIAL`, or `UNOBSERVED`) and `reason` (null for complete,
otherwise one of the closed reasons). A retained nonempty collection cannot be
declared unobserved. An empty list by itself does not prove complete coverage.

Procedure/context fields bind selected inputs; delivery coverage separately
records whether their actual application was observed. Admission, input selection,
and a configured provider route do not establish model execution or delivery.
Coverage and missingness must be derived from original retained observations by
the producer. Shape validation cannot attest to their truth.

## Validity, scoring, and chronology

Any null observation adds `REQUIRED_OBSERVATION_UNAVAILABLE`. Any incomplete
coverage adds `OBSERVATION_COVERAGE_INCOMPLETE`. Both are hard configuration
invalidity reasons; an allowed dependency degradation cannot excuse them. Known
mismatches, hidden sources, unauthorized capabilities, network destinations,
effect uncertainty, and unproven cleanup remain checked. Existing effect,
leakage, and cleanup precedence remains in force.

The technical-integrity scorer reports established failures as `FAIL` and
otherwise unsupported dimensions as `UNKNOWN` when observations are incomplete.
It creates no evidence reference for an absent output or tool-event artifact.
Experiment projection preserves the run's invalid status even if an independent
task scorer finds a useful property in retained output.

Known start and completion times must precede validation; validation must precede
receipt creation. Missing completion timing cannot conceal a start after
validation. Existing start/completion and duration/resource consistency checks
remain active whenever both facts are present.

## Persistence and consumers

Both versions use the same create-only `runs/<uuid>/receipt.json` path and
resolver. Exact replay is idempotent; changed content for the same run conflicts.
Both draft versions are refused by publication. Both versions participate in the
same complete store enumeration, single/multiple-scenario summaries, and
population-completeness check. An invalid v2 attempt cannot be omitted from a
published evidence reference to improve the apparent result.

Graph verification recomputes validity. Rehashing a forged `VALID` receipt does
not make an incomplete attempt eligible. Harness2 reconstructs the matching draft
version and still requires original output bytes, recomputed exact receipt,
`NO_EFFECT`, and `VALID`. It can retain an incomplete attempt as failure evidence
without accepting it as a refinement trial. The Hermes grounding scorer refuses
missing output with `RUN_OUTPUT_UNAVAILABLE` rather than dereferencing null or
claiming a successful answer.

## Producer and acceptance boundary

### Source-reference extension

Run/draft v3 retains every v2 availability and validity rule. It changes only
`observations.observed_sources`: the list is sorted and unique by immutable
artifact reference, and two different references may have identical content
digests. Scenario v2 applies the same rule to its source-policy allowlist.
This preserves both identities when two selected records contain the same bytes;
digest-based deduplication must not hide an unauthorized alias. The native source
contribution is explicitly partial and does not declare complete context delivery.

Scenario v1 and run/draft v1/v2 retain their exact validation. Unrelated artifact
lists retain their existing uniqueness rules. The original ArtifactStore paths,
IDs, graph verification and finalizer support all three run versions without
rewriting historical receipts. The native producer emits v3 for new publications,
while frozen v2 publications replay unchanged. Harness2 reconstructs the matching
draft version and keeps its existing validity, output and effect gates.

### Original producer

The native producer must authenticate original admission, source/profile/session,
selected artifacts and terminal record, use the original retained artifact root,
and preserve every retained attempt. It must not invoke inference during receipt
publication or adopt a different request as a replay. Expired result observations
remain unavailable; later current-runtime measurements cannot reconstruct them.

`tests/test_agent_eval_run_v2.py` exercises unavailable observations, closed
coverage, chronological ordering, forged validity, immutable mixed-version
storage, both population summaries, scorer behavior, Harness2 eligibility, and
the real CLI finalization/publication path. These are synthetic contract and
filesystem proofs. Native live provenance, installed behavior, and learning
efficacy remain separate acceptance obligations.


## Request-control policies: Configuration v2 and Run v4

The original EVAL contracts now have a versioned representation for supplied,
absent, unsupported and unavailable request controls. This is a contract and
consumer contribution on the original EVAL carrier. It does not activate a
producer, reinterpret historical receipts, supply missing execution evidence,
or establish a production Trial or learning improvement.

Configuration v1 still requires scalar effort, seed and sampling digest. Run
v1-v3 retain their existing scalar/null semantics. New Configuration v2 and
Run/draft v4 use tagged objects at the existing paths:

- `execution.reasoning_effort`
- `randomness.seed`
- `randomness.sampling_parameters_digest`

### Frozen intent and original observations

A Configuration v2 control declares either `EXPLICIT_REQUEST` with a typed
`value`, or `PROVIDER_CONTROLLED` without a value. Both carry an immutable
`owner_contract_ref` identifying the original source-qualified observation
boundary and control semantics. The configuration declares intended behavior;
it never supplies a run observation.

A Run v4 control is one of these closed objects:

| State | Required content and meaning |
| --- | --- |
| `PRESENT` | The actual supplied typed `value`, exact original trace `evidence`, and `owner_contract_ref`. |
| `ABSENT` | Observed omission across the complete required attempt join, with the same evidence and source fields; no value. |
| `UNSUPPORTED` | Observed omission plus the pinned owner's rejection semantics for that control; same evidence and source fields; no value. |
| `UNAVAILABLE` | Only the state tag; its typed reason belongs in the existing `observation_availability.unavailable` list. |

Every non-unavailable control must bind the exact `evidence.trace` artifact pair
and declare complete `provider_requests` coverage. An incomplete or conflicting
original attempt graph must produce unavailable control observations; it cannot
assert omission from a retained subset. A source reference alone does not prove
what happened. The incumbent graph verifier reports owner source and trace refs
as externally unverified content; shape validation is not an attestation of
those bytes or their source qualification.

`EXPLICIT_REQUEST(value)` matches only `PRESENT` with the identical typed value
and owner contract. `PROVIDER_CONTROLLED` matches only qualified `ABSENT` or
`UNSUPPORTED` under that same contract. A present value under provider control,
a different explicit value, or a different owner pin causes the existing
`CONFIGURATION_FIELD_MISMATCH`. Explicit seed zero remains observed zero. No
absent effort becomes a default effort. An unavailable state remains invalid,
with exactly one incumbent unavailable reason. Configurations and runs from
incompatible control versions are retained as invalid; their meanings are not
silently converted.

### Explicit sampling has a narrower meaning than effective sampling

The new tagged sampling value has schema
`mastermind.agent_evaluation_explicit_sampling.v1`, a digest, and a sorted,
nonempty list of supplied fields. Its versioned field set is `seed`,
`temperature`, `top_p`, `top_k`, `min_p`, `n`, `max_tokens`,
`max_completion_tokens`, `frequency_penalty`, `presence_penalty`,
`reasoning_effort`, `reasoning`, `thinking`, `stop`, and `logit_bias`.

The commitment is to the present request-field object at the pinned qualified
boundary, encoded as strict UTF-8 JSON with sorted keys, compact separators,
Unicode preserved, and nonfinite values refused. The original owner must also
qualify the complete request and its serialization. Values outside that finite
vector are not silently promoted into effective sampling evidence. Absent
vectors have no fabricated default or empty-object digest. Scalar seed and
effort states must be consistent with the vector's known supplied fields.
Nested `reasoning` may carry fields other than effort, so its mere presence is
not itself an effort observation.

The vector does not establish effective provider defaults, model weights,
deterministic replay, or support for omitted controls. An aggregate vector may
be called unsupported only when the owner contract rejects that whole defined
vector; rejection of seed alone is insufficient.

### Technical validity and the existing Harness2 consumer

Configuration v2 records `randomness.rng_policy` using the incumbent
`PREREGISTERED_REPLICATES` or `OBSERVED_UNKNOWN` vocabulary. This version makes
no deterministic claim from a seed or request digest. Unknown stochastic
behavior is distinct from unavailable required observations: an otherwise
complete, consistent `OBSERVED_UNKNOWN` run may be technically `VALID`.

The same finalizer, create-only ArtifactStore, graph verifier, scorer and CLI
consume these versions. The original Harness2 Trial reader reconstructs the v4
draft and recomputes the exact retained receipt, preserving its output, harness,
`NO_EFFECT` and `VALID` requirements. Its new v4 admission additionally requires
`PREREGISTERED_REPLICATES` and the bound original experiment's target of at least
two replicates per arm. This is a preregistration floor, not evidence that the
other replicates completed, samples were independent, statistical power was
adequate, or a candidate improved. The stored technical validity is not changed
when Harness2 refuses an ineligible stochastic policy.

The existing Harness2 factor lock hashes the entire execution and randomness
objects. It therefore includes control mode, value, owner pin and RNG policy;
a skill-only candidate cannot change those while retaining the same lock.
Historical Trial behavior is unchanged. The existing convergence environment
manifest remains a Configuration v1 interface and does not gain implicit v2
compatibility.

### Production boundary retained

The current native selected-input path still qualifies a named custom route
that injects scalar seed and manual effort. It explicitly refuses Configuration
v2 with `NATIVE_EVAL_CONFIGURATION_VERSION_UNQUALIFIED` before that injection.
The native publisher remains on its existing version and continues to retain
partial observations, whole-admission `EFFECT_UNKNOWN`, and unproven cleanup.

Production v4 emission requires a qualified contribution through the original
input/admission and observation owners. It must observe every original attempt,
retain actual effects and cleanup, and close the existing coverage, lifecycle,
workspace, environment and enforced-policy gaps. The new schema does not
supply those facts or authorize a replacement producer, store, runner, retry,
credential, admission, promotion or release operation.


### Tagged-control source qualification

The final focused contract/consumer cohort passed **185 cases, with zero
failures, errors or skips**, using CPython 3.12.13. It includes the real
finalizer, create-only store, CLI, graph recomputation, historical schema
refusals, original native selection refusal, and a complete synthetic
Harness2 refinement cycle retaining four distinct v4 runs. The synthetic cycle
returns no promotion or automatic memory write. The cases cover explicit zero,
known omission, unsupported controls, unavailable/conflicting observations,
trace/source and vector disagreement, immutable replay, mixed-version
population completeness, and the existing configuration factor lock.

The malformed tagged-input cases exposed an existing enum validator's untyped
exception for unhashable values. It now returns the incumbent typed enum
contract defect; accepted enum values are unchanged. The original Configuration
v1 environment-manifest boundary remains explicitly closed to v2.

Focused JUnit SHA-256:
`8e1a8a2e9b3e70e7a08e7131434f80232b896aecb4d9c93d148a895ae45fcc72`.
All nine changed paths belong to the existing finite EVAL-owned set; no new
path or prefix allowance was added. This is source and synthetic consumer
proof, not a whole-PR scope pass, real provider execution, installed acceptance,
complete native producer, completed stochastic replication or learning efficacy.


The broader existing-consumer regression passed **721 cases across 12 modules,
with zero failures, errors or skips**, using the same CPython 3.12.13 environment.
It covers contracts, validity, graph verification, immutable storage, CLI,
scoring, native Harness2, recursion, convergence, the OHF bridge, selected native
inputs and native publication. Its JUnit SHA-256 is
`b355829dc6501f844d0b91adcf33594511da4fddda15fc6066017d72805db509`.
The focused and broader cohorts overlap and are reported separately. These
results retain the production and acceptance limits stated above.

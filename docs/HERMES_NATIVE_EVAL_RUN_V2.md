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

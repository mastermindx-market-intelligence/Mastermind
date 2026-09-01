# Agent Evaluation EVAL-R0 — Executable Implementation Plan

> **Worker method:** use test-driven development and either `superpowers:subagent-driven-development` or `superpowers:executing-plans`. Work task-by-task. Do not widen this wave into a provider runner, evaluation framework, dashboard, policy engine, or database.

**Parent operation:** `mastermind-agent-evaluation-organizational-learning-fabric-20260830-sol-pro-001`  
**Parent architecture carrier:** Mastermind PR #299  
**Goal:** build the production-inert Mastermind-native scenario/configuration/experiment/run-validity/scorer/evidence-reference core and prove one complete synthetic two-arm evaluation-graph journey.  
**Truthful post-wave state:** at most `BUILT_NOT_PROVEN / PRODUCTION_INERT`; R0 proves no real model, corpus content, OHF run, routing equivalence, organizational learning, or production value.  
**Technology:** Python 3.11+, standard library, pytest, and the existing OHF text-redaction helper only.

---

## 1. Observable mission and complete journey

A fresh reviewer must be able to:

1. shape-validate one synthetic scenario with an exact corpus revision, two immutable configurations, and one two-arm experiment;
2. graph-verify scenario/configuration/experiment IDs, digests, compatibility, and membership through a read-only resolver;
3. finalize a closed runner draft into an immutable technical run receipt;
4. see one baseline draft become technically `VALID`;
5. see one requested/served-model mismatch become `INVALID_CONFIGURATION`;
6. recompute both technical-validity decisions from stored evaluation artifacts only;
7. append deterministic technical-integrity scorer passes without changing either run;
8. produce a sanitized evidence reference preserving exact configuration, arm, pair, replicate, verification scope, invalid/degraded counts, and dimension gates;
9. re-read and graph-verify the complete create-only artifact tree;
10. prove that no runner assertion, universal score, winner, route, policy, lifecycle, service, or production effect was created.

R0 intentionally does not resolve owner-native corpus/input/output/event/trace bytes. It proves `SHAPE_VALID` and `EVALUATION_GRAPH_VERIFIED`; `EVIDENCE_CONTENT_VERIFIED` is reserved for EVAL-C0/OHF2. Every CLI result and evidence reference must state this scope honestly.

---

## 2. Authority and source precedence

Apply in this order:

1. current protected `mastermindx-market-intelligence/Mastermind` Skillpack loaded atomically at action time;
2. accepted exact-head `docs/superpowers/specs/2026-08-31-agent-evaluation-fabric-design.md`;
3. this plan;
4. existing protected house contracts/helpers only where explicitly consumed;
5. bounded implementation choices inside the frozen boundary.

Do not revive rejected earlier designs. Specifically, do not:

- fuse execution completion, technical validity, and task correctness;
- let a runner assert `PASS`, `VALID`, `VERIFIED`, accepted, or policy value;
- place scorer references inside immutable runs;
- omit corpus/configuration/arm/pair/replicate identity;
- derive validity from unstored side inputs;
- trust a runner’s “unexpected capability” label instead of raw observed IDs;
- allow a known effect without scenario authorization;
- label shape validation or unresolved external evidence as fully verified;
- separate an evidence ref from its digest;
- use bare commit hashes where repository/source identity is required;
- map colon-bearing IDs directly into paths;
- require a mutable index to resolve a run.

Canonical owners remain Executive OS, Agent OS, GitHub, OHF/PR #162, Outcome Learning/Macro PR #6699, Router, Capacity, CXI, CodeIntel, Observability, RuntimeBinding, and Dialogue/Wake in their existing domains. EVAL-R0 mutates none of them.

---

## 3. Pickup and carrier gate

At EVAL-F0 review time:

- protected Mastermind was reconciled through `e60f69aa10e67b1334b1fa6a3299cb90fbbde7ab`;
- Skillpack was `mastermind.sol_skillpack.v1` v1.0.1 / bootstrap major 1;
- PR #162 was open/draft with two records and no fresh-runner code;
- Macro PR #6699 was open/draft and remained the sole Outcome Learning carrier;
- no `scripts/agent_eval/**` package existed.

The worker must re-pin these facts. Before code:

- post one pickup ACK on the exact carrier;
- load current Skillpack atomically and record SHA/schema/version/bootstrap;
- search branches, PRs, and code for the operation and paths;
- recheck PR #162 and Macro #6699;
- create one branch and one draft/HOLD PR from current protected master;
- post separate START only after collision/base/path gates clear.

Any active overlapping implementation carrier is a stop condition, not a reason to fork.

---

## 4. Exact scope and non-goals

### 4.1 Allowed paths

```text
scripts/agent_eval/__init__.py
scripts/agent_eval/errors.py
scripts/agent_eval/canonical.py
scripts/agent_eval/contracts.py
scripts/agent_eval/resolver.py
scripts/agent_eval/verification.py
scripts/agent_eval/validity.py
scripts/agent_eval/store.py
scripts/agent_eval/scoring.py
scripts/agent_eval/cli.py
scripts/agent_evaluation.py
tests/agent_eval_factories.py
tests/test_agent_eval_canonical.py
tests/test_agent_eval_contracts.py
tests/test_agent_eval_verification.py
tests/test_agent_eval_validity.py
tests/test_agent_eval_store.py
tests/test_agent_eval_scoring.py
tests/test_agent_eval_cli.py
tests/test_agent_eval_inertness.py
tests/fixtures/agent_eval/README.md
```

### 4.2 Hard non-goals

No modification/replacement of #162 or #6699; no model/provider/App Server/browser/container/MCP/daemon; no external dependency; no credential/provider-home/private-chat/chain-of-thought/environment read; no network; no Executive/Agent OS/Slack/Linear/Router/Capacity/RuntimeBinding/Wake/Observability write; no database/vector store/queue/scheduler/watcher/service/UI; no universal score/winner/route/policy/canary/release/merge/deploy authority; no arbitrary external path/URL dereference.

Stop for an architecture return if the complete journey cannot fit this boundary.

---

## 5. Frozen semantics

### 5.1 Schemas

Persisted:

```text
mastermind.agent_evaluation_scenario.v1
mastermind.agent_evaluation_configuration.v1
mastermind.agent_evaluation_experiment.v1
mastermind.agent_evaluation_run.v1
mastermind.agent_evaluation_scorer_pass.v1
mastermind.agent_evaluation_evidence_ref.v1
```

Transient, finalizer-only:

```text
mastermind.agent_evaluation_run_draft.v1
```

Generic import/store rejects the draft schema.

### 5.2 States

```text
execution completion:
  COMPLETED | FAILED | PARTIAL | TIMED_OUT | CANCELLED

technical validity:
  VALID | INVALID_CONFIGURATION | INVALID_LEAKAGE |
  INVALID_EFFECT_UNKNOWN | INVALID_CLEANUP | DEGRADED_DEPENDENCY

scored projection:
  VALID_PASS | VALID_FAIL | VALID_PARTIAL | UNSCORED
  plus invalid/degraded technical-state passthrough

evidence grade:
  includes INSUFFICIENT_EVIDENCE
```

`VALID` means technically admissible under the frozen configuration/source/effect/cleanup policy. It does not mean task correctness, evidence-content verification, policy acceptance, or production acceptance.

### 5.3 Verification scopes

```text
SHAPE_VALID
EVALUATION_GRAPH_VERIFIED
EVIDENCE_CONTENT_VERIFIED
```

R0 implements only the first two. Public APIs must never emit a stronger scope.

### 5.4 Canonical bytes and IDs

- Accepted values: JSON null, exact bool, signed 64-bit int, NFC string, list, dict with string keys.
- Reject float, tuple, non-string key, out-of-range int, NaN/infinity, silent coercion.
- Whole-second UTC only: `YYYY-MM-DDTHH:MM:SSZ`.
- Decimal measurements are canonical strings.
- Set-like arrays are sorted/unique.
- Canonical JSON is sorted, compact UTF-8 with `ensure_ascii=False`, `allow_nan=False`.
- Digest is `sha256:<64 lower-case hex>` over the document without its own digest field.

IDs:

```text
scenario:<family>:<case>
configuration:<uuid4>
experiment:<uuid4>
run:<uuid4>
scorer-pass:<uuid4>
evidence-ref:<uuid4>
```

Source-qualified code/source refs include repository and immutable revision, e.g. `git:mastermindx-market-intelligence/Mastermind@<sha>`.

Artifact evidence is always an object `{artifact_ref, digest}`. Optional artifact objects are null as a whole; ref and digest never vary independently.

### 5.5 Safe paths

```text
scenario:<family>:<case> -> scenarios/<family>/<case>/v<version>/scenario.json
configuration:<uuid>     -> configurations/<uuid>/configuration.json
experiment:<uuid>        -> experiments/<uuid>/manifest.json
run:<uuid>               -> runs/<uuid>/receipt.json
scorer-pass:<uuid>       -> scorer-passes/<uuid>/scorer-pass.json
evidence-ref:<uuid>      -> evidence-refs/<uuid>/evidence-ref.json
```

This mapping is globally resolvable without a mutable index or repository-wide search. Reject slash, backslash, dot segment, control, empty/oversized segment, trailing dot/space, and Windows device names.

---

## 6. Ordered TDD implementation

## Task 1 — Structured defects and strict canonical JSON

**Files**

```text
scripts/agent_eval/__init__.py
scripts/agent_eval/errors.py
scripts/agent_eval/canonical.py
tests/test_agent_eval_canonical.py
```

**Interfaces**

```python
ContractDefect
ContractError
ArtifactConflictError
VerificationContextError
canonical_json_bytes(value) -> bytes
digest_value(value) -> str
digest_document(document, digest_field) -> str
add_document_digest(document, digest_field) -> dict
verify_document_digest(document, digest_field) -> None
parse_utc_z(value, path="$" ) -> datetime
parse_prefixed_uuid4(value, prefix, path="$" ) -> UUID
parse_source_qualified_ref(value, path="$" ) -> str
require_canonical_json_tree(value, path="$" ) -> None
```

- [ ] Write RED tests for sorted UTF-8, NFC, strict primitives, bool-vs-int, int bounds, float/tuple/non-string-key rejection, whole-second UTC, UUID4/case/version, source-qualified ref grammar, artifact ref/digest pairing, digest omission/mutation, and deterministic defect ordering.
- [ ] Confirm RED.
- [ ] Implement frozen structured errors sorted by `(path, code, message)`.
- [ ] Keep `__init__.py` constants-only and inert.
- [ ] Run `pytest -q tests/test_agent_eval_canonical.py`.
- [ ] Commit Task 1 only.

**Acceptance:** no Python value or ambiguous reference is silently coerced into canonical evidence.

---

## Task 2 — Closed scenario and configuration contracts

**Files**

```text
scripts/agent_eval/contracts.py
tests/agent_eval_factories.py
tests/test_agent_eval_contracts.py
```

**Interfaces**

```python
validate_document_shape(document)
validate_scenario_shape(document)
validate_configuration_shape(document)
build_scenario(...)
build_configuration(...)
scenario_configuration_defects(scenario, configuration)
```

### Scenario fields

```text
schema, scenario_id, scenario_version, scenario_family, corpus_revision,
risk_tier, objective, input_fixture, expected_contract, temporal,
source_policy, capability_policy, execution_policy, effect_policy,
scoring_policy, privacy, authorship, supersedes, scenario_digest
```

Nested requirements:

```text
input_fixture / expected_contract: artifact_ref, digest
temporal: cutoff_at, authored_at
source_policy: allowlist_artifacts, denylist_refs, solution_refs_hidden
allowlist artifact: artifact_ref, digest
capability_policy: profile_id, profile_digest, allowed_capability_ids,
                   forbidden_capability_ids, allowed_tool_schema_digests
execution_policy: fresh_process_required, fresh_workspace_required,
                  fresh_session_required, resume_allowed, network_policy,
                  network_allowlist, max_elapsed_ms, max_tool_calls,
                  allowed_degradations
effect_policy: mode, allowed_operation_refs
scoring_policy: required_scorers, optional_scorers, required_dimensions
privacy: classification, model_visible_artifact_refs, retention_class
authorship: author_ref, independent_reviewer_ref
```

### Configuration fields

```text
schema, configuration_id, execution, procedure, context, capabilities,
randomness, authorship, created_at, supersedes, configuration_digest
```

Nested requirements:

```text
execution: execution_surface, execution_surface_version, provider,
           model_requested, reasoning_effort, auth_realm_class
procedure: protected_source_ref, skillpack_source_ref, skillpack_version,
           instruction_bundle, handoff
context: context_packet, retrieval_configuration
capabilities: profile_id, profile_digest, declared_capability_ids,
              declared_tool_schema_digests, sandbox_digest,
              network_policy_digest, environment_digest
randomness: seed, sampling_parameters_digest
authorship: author_ref, independent_reviewer_ref
```

- [ ] Build deterministic PUBLIC_SAFE factories for one `mastermind.evaluation_contract_integrity.v1` scenario and two configurations. Use distinct immutable context-packet digests so configuration digests differ while both request the same model.
- [ ] Write RED tests for all unknown/missing fields; ID/ref/digest grammar; corpus revision; sorted/unique artifact/capability/tool/network/effect/scorer lists; duplicate artifact refs; hidden-source subset; network/effect consistency; cutoff order; privacy/ref consistency; source-qualified procedure refs; authorship; supersession; and own digest.
- [ ] `DENY_ALL` requires empty network allowlist; `ALLOWLIST` requires nonempty list.
- [ ] `NO_EFFECT_ONLY` requires empty operation refs; `DECLARED_EFFECT_ALLOWED` requires nonempty exact refs.
- [ ] Configuration cannot contain served model, route, capacity, suitability, policy, score, winner, authority, approval, or acceptance.
- [ ] Compatibility requires profile equality; declared capabilities subset of allowed and disjoint from forbidden; declared tools subset of allowed; network-policy digest equals digest of scenario network policy/allowlist.
- [ ] Generic shape dispatch accepts persisted schemas only and returns literal scope `SHAPE_VALID`.
- [ ] Run `pytest -q tests/test_agent_eval_canonical.py tests/test_agent_eval_contracts.py`.
- [ ] Commit Task 2.

**Acceptance:** each arm can bind one immutable source-qualified configuration and incompatible capability/network policy fails before execution.

---

## Task 3 — Experiment and evaluation-graph verification

**Files**

```text
scripts/agent_eval/contracts.py
scripts/agent_eval/resolver.py
scripts/agent_eval/verification.py
tests/agent_eval_factories.py
tests/test_agent_eval_verification.py
tests/test_agent_eval_contracts.py
```

**Interfaces**

```python
validate_experiment_shape(document)
ArtifactResolver  # read-only Protocol
MemoryArtifactResolver  # deterministic tests/inert utility
verify_scenario_graph(document, resolver) -> VerificationResult
verify_configuration_graph(document, resolver) -> VerificationResult
verify_experiment_graph(document, resolver) -> VerificationResult
```

### Experiment fields

```text
schema, experiment_id, scenario_refs, arms, pairing,
replicates_per_arm_target, stopping_rule, primary_dimensions,
guardrail_dimensions, analysis_version, phase, authorship, created_at,
experiment_digest
```

Scenario ref:

```text
scenario_id, scenario_version, scenario_digest, corpus_revision
```

Arm:

```text
arm_id, configuration_id, configuration_digest
```

- [ ] Write RED tests for two unique sorted arms, unique config IDs/digests, scenario refs/corpus, pairing, positive replicate target, fixed stopping rule consistency, dimension disjointness, phase, authorship, time, digest.
- [ ] Resolver methods map exact scenario version, configuration ID, experiment ID, run ID, scorer-pass ID, and evidence-ref ID. There is no write, network, environment, provider, search, or fallback method.
- [ ] Shape validators never consult resolver.
- [ ] VerificationResult contains exact scope `EVALUATION_GRAPH_VERIFIED`, artifact ID, artifact digest, and `external_content_unverified_refs`.
- [ ] Scenario graph verification checks shape/own digest and reports input/expected/allowlist artifacts as externally sealed/unverified; it does not claim content verification.
- [ ] Experiment graph verification resolves every scenario/configuration, checks exact IDs/digests/corpus revisions, and runs compatibility for every scenario/arm pairing.
- [ ] Missing/substituted/incompatible artifacts fail verification, never downgrade to warnings.
- [ ] Run `pytest -q tests/test_agent_eval_contracts.py tests/test_agent_eval_verification.py`.
- [ ] Commit Task 3.

**Acceptance:** graph verification cannot succeed against a missing/substituted configuration and cannot claim external content was checked.

---

## Task 4 — Run draft, deterministic validity, immutable run

**Files**

```text
scripts/agent_eval/contracts.py
scripts/agent_eval/validity.py
scripts/agent_eval/verification.py
tests/agent_eval_factories.py
tests/test_agent_eval_validity.py
tests/test_agent_eval_verification.py
tests/test_agent_eval_contracts.py
```

**Interfaces**

```python
validate_run_draft_shape(draft)
validate_run_shape(document)
evaluate_validity(scenario, configuration, experiment_or_none, draft)
finalize_run_receipt(
    scenario,
    configuration,
    experiment_or_none,
    draft,
    *,
    validator_id,
    validator_version,
    validator_code_ref,
    validated_at,
    created_at,
) -> dict
verify_run_graph(document, resolver) -> VerificationResult
```

### Run fields

```text
schema, run_id, scenario, configuration, comparison, execution, procedure,
context, observations, capabilities, randomness, effect, cleanup, evidence,
resources, timing, validity, created_at, run_digest
```

The draft omits `validity`, `created_at`, `run_digest` and uses the draft schema.

Required nested fields:

```text
scenario: scenario_id, scenario_version, scenario_digest, corpus_revision,
          temporal_cutoff
configuration: configuration_id, configuration_digest
comparison: experiment_id, arm_id, pair_key, replicate_index
execution: runner_id, runner_code_ref, execution_surface,
           execution_surface_version, provider, model_requested, model_served,
           reasoning_effort, auth_realm_class, process_fingerprint,
           native_session_fingerprint, completion_status, termination_reason,
           fresh_process_observed, fresh_workspace_observed,
           fresh_session_observed, resume_used
procedure: protected_source_ref, skillpack_source_ref, skillpack_version,
           instruction_bundle, handoff
context: source_policy_digest, context_packet, retrieval_configuration
observations: observed_sources, observed_capability_ids,
              observed_tool_schema_digests, observed_network_destinations,
              dependency_degradations
observed source: artifact_ref, digest
capabilities: profile_id, profile_digest, sandbox_digest,
              network_policy_digest, workspace_digest, environment_digest
randomness: seed, sampling_parameters_digest
effect: state, operation_ref, reconciliation_ref
cleanup: status, proof
evidence: output, tool_events, trace, artifacts
output/tool_events/trace: artifact_ref, digest
artifact: artifact_ref, digest, kind
resources: input_tokens, output_tokens, tool_calls, elapsed_ms,
           provider_usage_ref, estimated_marginal_cost, cost_currency
timing: started_at, completed_at, monotonic_duration_ms
validity: status, reason_codes, validator_id, validator_version,
          validator_code_ref, validated_at
```

- [ ] Build clean baseline and model-mismatch drafts. Both bind exact corpus/configuration/experiment arm, pair key, replicate 1, source-qualified runner code, scenario source-policy digest, raw observed source artifact/digest pairs, raw capabilities/tools/network, `NO_EFFECT`, cleanup `PROVEN`, and completion `COMPLETED`.
- [ ] Write RED tests for every closed field set, corpus/cutoff, source-qualified code/procedure refs, configuration field equality, experiment membership, arm/pair/replicate, raw source/digest/capability/tool/network observations, freshness/resume, effect/cleanup, degradation, paired evidence refs/digests, time/resources/cost, and forbidden runner result fields.
- [ ] Derive validity from stored draft fields only. No `RunFacts` or unstored input.
- [ ] Implement at least:

```text
MODEL_SERVED_MISMATCH
CONFIGURATION_FIELD_MISMATCH
TOOL_SCHEMA_DRIFT
CAPABILITY_DRIFT
FORBIDDEN_CAPABILITY
UNAUTHORIZED_SOURCE
SOURCE_DIGEST_MISMATCH
HIDDEN_SOLUTION_SOURCE
UNEXPECTED_NETWORK_DESTINATION
FRESH_PROCESS_UNPROVEN
FRESH_WORKSPACE_UNPROVEN
FRESH_SESSION_UNPROVEN
RESUME_FORBIDDEN
NETWORK_POLICY_MISMATCH
DEGRADATION_NOT_ALLOWED
CLEANUP_UNPROVEN
EFFECT_UNKNOWN
UNAUTHORIZED_EFFECT
EFFECT_REFERENCE_MISMATCH
EXPERIMENT_ARM_MISMATCH
PAIR_IDENTITY_MISSING
SCENARIO_NOT_IN_EXPERIMENT
CONFIGURATION_NOT_IN_EXPERIMENT
REPLICATE_OUT_OF_RANGE
TEMPORAL_CUTOFF_MISMATCH
CORPUS_REVISION_MISMATCH
SOURCE_POLICY_DIGEST_MISMATCH
```

- [ ] Precedence:

```text
EFFECT_UNKNOWN                     -> INVALID_EFFECT_UNKNOWN
else unauthorized/hidden source   -> INVALID_LEAKAGE
else required cleanup unproven    -> INVALID_CLEANUP
else configuration/capability/
     tool/network/effect/arm/
     cutoff/corpus/digest mismatch -> INVALID_CONFIGURATION
else allowed degradation present  -> DEGRADED_DEPENDENCY
else                               -> VALID
```

Retain lower-priority reasons.

- [ ] `NO_EFFECT` requires null effect refs. `EFFECT_KNOWN` requires exact allowed operation ref. `EFFECT_UNKNOWN` always invalidates.
- [ ] `NOT_REQUIRED` cleanup is allowed only when process/workspace/effect state cannot exist; otherwise cleanup is unproven.
- [ ] Finalizer graph-verifies inputs, validates draft, derives validity, switches schema, inserts source-qualified validator provenance/time/digest, and graph-verifies the final run before return.
- [ ] Run graph verification resolves scenario/configuration/experiment and recomputes exact status/reasons. Forged/stale validity fails.
- [ ] Time: `started_at <= completed_at <= validated_at <= created_at`; monotonic duration equals elapsed ms.
- [ ] Completion does not determine task correctness. Clean completion yields technical `VALID`, not `VALID_PASS`.
- [ ] Run `pytest -q tests/test_agent_eval_contracts.py tests/test_agent_eval_validity.py tests/test_agent_eval_verification.py`.
- [ ] Commit Task 4.

**Acceptance:** mutating/deleting any validity input changes recomputation or fails validation; no runner self-grades.

---

## Task 5 — Append-only scorer and evidence reference

**Files**

```text
scripts/agent_eval/contracts.py
scripts/agent_eval/scoring.py
scripts/agent_eval/verification.py
tests/agent_eval_factories.py
tests/test_agent_eval_scoring.py
tests/test_agent_eval_verification.py
```

**Interfaces**

```python
validate_scorer_pass_shape(document)
build_technical_integrity_scorer_pass(...)
verify_scorer_pass_graph(document, resolver)
validate_evidence_ref_shape(document)
summarize_experiment(...)
verify_evidence_ref_graph(document, resolver)
```

Scorer pass binds exact run ID/digest; scorer ID/version/source-qualified code ref/config digest; method; input evidence artifact/digest pairs; sorted dimension results; grader/human identity; created time; superseded pass; own digest.

Initial scorer:

```text
mastermind.technical_integrity.v1
```

Dimensions:

```text
configuration_integrity
effect_integrity
cleanup_integrity
source_integrity
```

Evidence ref binds exact task/scenario/corpus/experiment/configuration/run/scorer/analysis artifact IDs and digests; arm/pair/replicate; technical validity; scored projection; dimension gates; valid/invalid/degraded/unscored counts; uncertainty; verification scopes; limitations; intended owner/review time; non-authority statement; own digest.

- [ ] Write RED scorer tests for exact refs/digests/code provenance, deterministic method, sorted dimensions/reasons/evidence, null grader, supersession without rewrite, no aggregate/winner.
- [ ] Technical-integrity scorer uses run validity/reasons only; it does not claim broad task correctness or product usefulness.
- [ ] Write RED evidence-ref tests for all cross-links and digests, corpus/configuration/arm/pair/replicate preservation, invalid denominator exclusion, dimension-gate matrix, graph/content verification scopes, `INSUFFICIENT_EVIDENCE`, `NOT_ESTIMATED` uncertainty, limitations, owner/time, statement, digest.
- [ ] Required statement:

```text
This evidence reference does not authorize routing, policy, release, merge, deployment, production execution, or acceptance.
```

- [ ] Per-run projection: invalid/degraded state passes through; technical VALID + all required accepted dimensions PASS => `VALID_PASS`; any required FAIL => `VALID_FAIL`; partial without fail => `VALID_PARTIAL`; missing/unknown => `UNSCORED`.
- [ ] R0 grade remains `INSUFFICIENT_EVIDENCE`; verification scopes contain SHAPE_VALID and EVALUATION_GRAPH_VERIFIED but not EVIDENCE_CONTENT_VERIFIED.
- [ ] Reject numeric aggregate, winner, route, policy, approved, accepted, promoted, or release fields.
- [ ] Graph verification resolves exact runs/scorers/configurations and recomputes counts/projections/gates/scopes.
- [ ] Run `pytest -q tests/test_agent_eval_scoring.py tests/test_agent_eval_verification.py`.
- [ ] Commit Task 5.

**Acceptance:** scoring appends without run mutation and summaries cannot erase invalid evidence or overstate verification/authority.

---

## Task 6 — Create-only artifact store

**Files**

```text
scripts/agent_eval/store.py
scripts/agent_eval/resolver.py
scripts/agent_eval/verification.py
tests/test_agent_eval_store.py
```

**Interfaces**

```python
ArtifactStore(root)
ArtifactStore.create(document) -> WriteResult
ArtifactStore.read_shape(path) -> dict
ArtifactStore.resolve_*() -> dict
ArtifactStore.verify_graph(path) -> VerificationResult
ArtifactStore.verify_tree_graph() -> tuple[ContractDefect, ...]
WriteDisposition.CREATED
WriteDisposition.IDEMPOTENT
```

Topological creation:

```text
scenario/configuration -> experiment -> run -> scorer pass -> evidence ref
```

- [ ] Write RED tests for all global ID/path mappings, path hazards, root escape, symlink parents, nonregular/oversized file, create/idempotent/conflict, corruption, interrupted publication, missing dependencies, stale validity/summary, orphan scorer, unexpected JSON, and whole-tree graph verification.
- [ ] Validate and graph-verify before publication. Drafts are never publishable.
- [ ] Secret policy: closed schemas reject unknown secret fields; compare allowed string values with `scripts.ohf.redaction.redact_evidence_text`; explicitly reject forbidden names; avoid false positives on SHA-256 and resource counters.
- [ ] Create private parents after root/symlink checks.
- [ ] Write canonical bytes to same-directory mode-`0o600` temp, flush/fsync.
- [ ] Publish via `os.link(temp, final)`, fsync directory, unlink temp, read back and graph-verify.
- [ ] Existing exact bytes => idempotent; changed/corrupt => conflict.
- [ ] Unsupported hard-link semantics fail closed.
- [ ] `read_shape` never claims verification. `verify_graph`/tree resolve dependencies and recompute validity/summaries; never repair.
- [ ] Root is private/trusted. Document that R0 does not claim defense against a hostile same-user process racing directory replacement.
- [ ] Run `pytest -q tests/test_agent_eval_store.py tests/test_agent_eval_verification.py`.
- [ ] Commit Task 6.

**Acceptance:** no artifact overwrites, escapes, hides behind symlinks, verifies without dependencies, or preserves forged validity.

---

## Task 7 — CLI and synthetic two-arm proof

**Files**

```text
scripts/agent_eval/cli.py
scripts/agent_evaluation.py
tests/test_agent_eval_cli.py
tests/fixtures/agent_eval/README.md
```

Commands:

```text
validate-shape <document.json>
verify-graph --root <root> <document-or-stored-path>
create --root <root> <finalized-document.json>
finalize-run --root <root> --draft <run-draft.json>
             --validator-id <id> --validator-version <v>
             --validator-code-ref <source-ref>
             --validated-at <time> --created-at <time> --output <receipt.json>
score-integrity --root <root> --run-id <run:id>
                --scorer-code-ref <source-ref> --created-at <time> --id <uuid>
summarize --root <root> --experiment-id <experiment:id>
          --owner <owner> --review-at <time> --created-at <time> --id <uuid>
verify-tree-graph --root <root>
```

Exit codes:

```text
0 = requested shape/graph/artifact operation succeeded cleanly
1 = command completed with invalid/degraded/unscored/insufficient result
2 = usage/shape/graph-context/conflict/corruption/privacy/filesystem error
```

- [ ] Write RED CLI tests first.
- [ ] `main(argv)` uses argparse, returns int, prints one canonical JSON object, bounded diagnostics to stderr, and no traceback for expected errors.
- [ ] `validate-shape` prints `SHAPE_VALID` only.
- [ ] `verify-graph`/tree print `EVALUATION_GRAPH_VERIFIED` only and list external content refs still unverified.
- [ ] No R0 command prints `EVIDENCE_CONTENT_VERIFIED`.
- [ ] `finalize-run` resolves scenario/configuration/experiment IDs from root and writes an exclusive local receipt; store `create` publishes it separately.
- [ ] `score-integrity` appends; cannot alter run bytes.
- [ ] `summarize` resolves all experiment runs/scorers and writes one evidence ref.
- [ ] Complete one fresh-root journey:
  1. create scenario with corpus revision and artifact/digest source allowlist;
  2. create two configurations;
  3. create/verify two-arm experiment;
  4. finalize/store clean baseline run;
  5. finalize/store served-model mismatch run;
  6. verify baseline VALID and mismatch INVALID_CONFIGURATION/MODEL_SERVED_MISMATCH;
  7. append integrity pass per run;
  8. summarize/store evidence ref;
  9. graph-verify tree;
  10. assert config/arm/pair/replicate links, one valid/one invalid, invalid retained, INSUFFICIENT_EVIDENCE, external content unverified, no aggregate/winner/policy/acceptance, no file outside root.
- [ ] Fixture README declares synthetic PUBLIC_SAFE data and exact R0 verification limitation.
- [ ] Run:

```bash
pytest -q tests/test_agent_eval_cli.py
python scripts/agent_evaluation.py --help
```

- [ ] Manually reproduce in a second temporary root; retain canonical stdout, IDs, digests, scopes, and tree.
- [ ] Commit Task 7.

**Acceptance:** a fresh reviewer reproduces the evaluation graph without network/provider/hidden state and sees exactly what remains unverified.

---

## Task 8 — Inertness, privacy, mutation, path fences

**Files**

```text
tests/test_agent_eval_inertness.py
```

- [ ] AST-reject production imports for Executive/worker/router/Slack integrations, sqlite/psycopg/duckdb/httpx/requests/socket/subprocess, Inspect/Langfuse/Promptfoo. Permit only exact OHF text-redaction helper.
- [ ] AST-reject process/network/thread/task/database/environment primitives in production code.
- [ ] Import each production module in a test subprocess and prove no output/file/socket/thread/child/background/environment side effect.
- [ ] Secret-shape tests: synthetic key, JWT, auth/cookie/token, email/account ID, `MASTERMIND_*=`, private host; reject before publication. Verify SHA-256/resource counters do not false-positive.
- [ ] Mutation matrix kills at least:

```text
unknown field; wrong schema/digest; float/tuple/non-NFC/non-string key;
missing/wrong corpus revision; bare commit ref; detached artifact ref/digest;
future/mismatched cutoff; unauthorized/hidden/source-digest mismatch;
configuration ID/digest/field mismatch; requested/served model mismatch;
extra/missing raw capability/tool; forbidden capability; unexpected network;
freshness false/null; forbidden resume; unauthorized/unknown effect;
effect ref mismatch; unproven cleanup; degradation cases;
experiment scenario/arm/config mismatch; missing pair; bad replicate;
negative/bool resource; time/duration mismatch; changed ID bytes;
symlink/path traversal/device name; aggregate/winner/route/policy/approval;
scorer ref injected into run; runner result in draft; forged validity;
shape relabeled graph-verified; graph relabeled content-verified;
missing resolver dependency; stale evidence counts; mutable run index required.
```

- [ ] Changed-path test permits only Section 4.1 plus accepted EVAL-F0 records; no control-plane/config/dependency/workflow file.
- [ ] Run:

```bash
pytest -q tests/test_agent_eval_inertness.py
pytest -q tests/test_agent_eval_*.py
```

- [ ] Commit Task 8.

**Acceptance:** every load-bearing authority, privacy, identity, verification-scope, immutability, and denominator invariant has an executable negative test.

---

## Task 9 — Exact-head verification, independent review, return

- [ ] Re-pin protected master and Skillpack; reconcile drift on same branch without force/replacement.
- [ ] Run targeted `pytest -q tests/test_agent_eval_*.py`.
- [ ] Run full `pytest -q`; classify every failure exactly.
- [ ] Run:

```bash
python -m compileall -q scripts/agent_eval scripts/agent_evaluation.py
python scripts/agent_evaluation.py --help
```

- [ ] Re-run synthetic journey in fresh root; record all IDs/digests/scopes/stdout/tree/head.
- [ ] Inspect final diff for allowed paths only, no dependency/config/workflow change, secrets/private IDs, or generated junk.
- [ ] Answer in PR:

```text
What new machine/reviewer capability exists?
Can validity recompute from stored evaluation artifacts only?
Can a runner self-grade or scorer mutate a run?
Can a missing configuration/corpus revision still graph-verify?
Can graph verification be mislabeled content verification?
Can invalid evidence disappear from denominators?
Can a known effect pass without scenario authorization?
Can evidence refs detach from digests?
Can run resolution require mutable index/search?
Can an ID overwrite/escape root?
Did any lifecycle/router/memory/policy/provider/service/database appear?
What remains NOT_BUILT/unproven?
```

- [ ] Request one independent Auditor Sol/qualified reviewer at exact immutable head. Review attacks source law, corpus/config/arm/pair identity, source/evidence digest association, source-qualified code provenance, raw capabilities/effects, verification scopes, validity recomputation, atomicity/path/privacy, invalid denominators, no-duplicate owners, and synthetic reproducibility.
- [ ] Resolve all REQUEST_CHANGES and rerun exact-head verification.
- [ ] Return exact operation, ACK/START refs, branch/PR/base/head, changed paths, targeted/full/CI/security receipts, synthetic identities/digests/scopes, review disposition, capability state, remaining false claims, and next predecessor gate.

### Stop condition

Stop only after exact-head checks terminal, synthetic graph reproducible, independent review resolved, current base reconciled, and parent Sol issues one `SOL ACCEPTED / STOP` or `SOL REQUEST_REPAIR`.

A green PR or merge proves only a production-inert native evaluation-graph core. It does not prove evidence-content integrity, OHF execution, corpus quality, real model comparison, routing equivalence, organizational learning, policy improvement, UI, canary, or production value.

---

## 7. Continuation after R0 acceptance

R0 acceptance opens, but does not auto-start:

1. **EVAL-C0:** 15–30 governed cases, private holdouts, and owner-native evidence-content resolution.
2. **EVAL-OHF1:** resume existing PR #162 on its same carrier.
3. **EVAL-OHF2:** adapt proven runner to run draft/finalizer and content evidence.
4. **EVAL-S1/E1:** task scorers and first paired real experiment.

Inspect, Promptfoo, Parquet/DuckDB analysis, UI, owner-policy handoff, and prospective canary remain gated on native real-run evidence.

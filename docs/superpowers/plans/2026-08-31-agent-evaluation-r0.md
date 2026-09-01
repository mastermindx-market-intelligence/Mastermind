# Agent Evaluation EVAL-R0 — Executable Implementation Plan

> **Worker method:** use test-driven development and either `superpowers:subagent-driven-development` or `superpowers:executing-plans`. Work task-by-task. Do not widen this wave into a provider runner, evaluation framework, dashboard, policy engine, or database.

**Parent operation:** `mastermind-agent-evaluation-organizational-learning-fabric-20260830-sol-pro-001`  
**Parent architecture carrier:** Mastermind PR #299  
**Goal:** build the production-inert Mastermind-native scenario/configuration/experiment/run-validity/scorer/evidence-reference core and prove one complete synthetic two-arm journey.  
**Truthful post-wave state:** at most `BUILT_NOT_PROVEN / PRODUCTION_INERT`; R0 proves no real model, OHF run, corpus, routing equivalence, organizational learning, or production benefit.  
**Technology:** Python 3.11+, standard library, pytest, and the existing OHF text-redaction helper only.

---

## 1. Observable mission and complete journey

Create one independently useful vertical in which a reviewer can:

1. shape-validate one synthetic scenario, two immutable configurations, and one two-arm experiment;
2. verify their evaluation-graph references and digests through a read-only resolver;
3. finalize a closed runner draft into an immutable technical run receipt;
4. see one baseline run become technically `VALID`;
5. see one requested/served-model mismatch become `INVALID_CONFIGURATION`;
6. recompute both technical-validity decisions from stored scenario/configuration/experiment/run fields;
7. append deterministic technical-integrity scorer passes without changing either run;
8. produce a sanitized evidence reference preserving exact configuration, arm, pair, replicate, invalid/degraded, and dimension-gate evidence;
9. re-read and digest-verify the complete artifact tree;
10. prove that no runner assertion, universal score, winner, route, policy, lifecycle, service, or production effect was created.

This is not disconnected infrastructure. The CLI, verifier, immutable artifact tree, deterministic integrity scorer, and evidence-reference projection are the first real machine/reviewer consumers. They become the exact contract target for OHF and later optional Inspect adapters.

---

## 2. Authority and source precedence

Apply in this order:

1. current protected `mastermindx-market-intelligence/Mastermind` Skillpack loaded atomically at action time;
2. the accepted exact-head `docs/superpowers/specs/2026-08-31-agent-evaluation-fabric-design.md`;
3. this plan;
4. existing protected house contracts/helpers only where explicitly consumed;
5. bounded implementation choices inside this frozen boundary.

Rejected clauses from earlier drafts must not reappear. In particular, do not:

- fuse execution completion, technical validity, and task correctness;
- let a runner assert `PASS`, `VALID`, `accepted`, or policy value;
- place scorer references inside immutable runs;
- omit configuration/arm/pair/replicate identity;
- derive validity from unstored side inputs;
- trust a runner-supplied “unexpected capability” label;
- allow a known effect without scenario authorization;
- call shape validation authoritative verification;
- map colon-bearing canonical IDs directly into paths.

Canonical owners remain:

- Executive OS: Job/Attempt/Worker/Event lifecycle, effect/retry/requeue, CEO admission.
- Agent OS: durable workstreams, decisions, discoveries, handoffs.
- GitHub: implementation, tests, PR review, CI, merge, production evidence.
- OHF/PR #162: fresh App Server runner mechanics.
- Outcome Learning/Macro PR #6699: organizational consequence and policy promotion.
- Router, Capacity, CXI, CodeIntel, Observability, RuntimeBinding, Dialogue/Wake: their existing domains.

EVAL-R0 writes none of those owners.

---

## 3. Verified starting state and pickup gate

At EVAL-F0 review time:

- protected Mastermind was reconciled through `e60f69aa10e67b1334b1fa6a3299cb90fbbde7ab`;
- Skillpack was `mastermind.sol_skillpack.v1` v1.0.1 / minimum bootstrap major 1;
- PR #162 was open/draft with two records and no fresh-runner code;
- Macro PR #6699 was open/draft and remained the sole Outcome Learning carrier;
- no `scripts/agent_eval/**` package or accepted agent-evaluation schema existed;
- Python floor was 3.11 and pytest used `tests/`;
- `scripts/ohf/redaction.py` exposed house text-redaction behavior.

The worker must re-pin every item. These are observation coordinates, not permission to ignore current drift.

Before code:

- post one pickup ACK on the exact commission carrier;
- load current Skillpack atomically and record SHA/schema/version/bootstrap;
- search current branches, PRs, and code for the operation and `scripts/agent_eval` paths;
- recheck #162 and #6699;
- create one branch and one draft/HOLD PR from current protected master;
- post separate START only after carrier/base/path gates are clear.

If an active implementation carrier or overlapping path owner exists, stop and return collision evidence. Do not fork or blind-retry.

---

## 4. Exact scope and non-goals

### 4.1 Allowed implementation paths

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

The accepted EVAL-F0 spec, plan, and research may appear in the implementation PR history but must not be edited unless a discovered contradiction requires a narrowly documented architecture return.

### 4.2 Hard non-goals

Do not:

- modify or replace PR #162 or Macro #6699;
- launch a model, provider process, App Server, browser, container, MCP server, daemon, or background task;
- import Inspect, Promptfoo, Langfuse, JSON Schema/Pydantic, or any new dependency;
- read credentials, provider homes, cookies, OAuth, private chats, chain of thought, or environment dumps;
- perform network access;
- create/mutate Executive, Agent OS, Slack, Linear, Router, Capacity, RuntimeBinding, Wake, or Observability state;
- create SQLite/Postgres/ClickHouse/DuckDB state, a vector store, queue, scheduler, watcher, service, or UI;
- produce a universal score, winner, route change, policy candidate, canary, release approval, merge approval, or deployment;
- treat a completion status as task correctness;
- place scorer-pass refs inside a run;
- use raw colon-bearing IDs as path segments;
- emit `VERIFIED` from a shape-only helper;
- dereference arbitrary external paths or URLs from scenario prose.

Stop and return an architecture decision if the complete journey cannot be delivered inside this boundary.

---

## 5. Frozen contracts and semantics

### 5.1 Canonical schemas

Implement exactly these persisted schemas:

```text
mastermind.agent_evaluation_scenario.v1
mastermind.agent_evaluation_configuration.v1
mastermind.agent_evaluation_experiment.v1
mastermind.agent_evaluation_run.v1
mastermind.agent_evaluation_scorer_pass.v1
mastermind.agent_evaluation_evidence_ref.v1
```

Implement exactly one transient, noncanonical draft schema:

```text
mastermind.agent_evaluation_run_draft.v1
```

Generic import/store rejects the draft schema. Only the finalizer accepts it.

### 5.2 State separation

Execution completion:

```text
COMPLETED | FAILED | PARTIAL | TIMED_OUT | CANCELLED
```

Technical validity:

```text
VALID
INVALID_CONFIGURATION
INVALID_LEAKAGE
INVALID_EFFECT_UNKNOWN
INVALID_CLEANUP
DEGRADED_DEPENDENCY
```

Derived scored projection:

```text
VALID_PASS
VALID_FAIL
VALID_PARTIAL
UNSCORED
INVALID_CONFIGURATION
INVALID_LEAKAGE
INVALID_EFFECT_UNKNOWN
INVALID_CLEANUP
DEGRADED_DEPENDENCY
```

Evidence-set grade includes `INSUFFICIENT_EVIDENCE`. A runner supplies only raw observations and execution completion.

### 5.3 Canonical bytes

- Accept only JSON null, exact bool, signed 64-bit int, NFC string, list, and dict with string keys.
- Reject float, tuple, non-string key, out-of-range integer, NaN/infinity, and silent coercion.
- Require exact whole-second UTC timestamps: `YYYY-MM-DDTHH:MM:SSZ`.
- Require ASCII identifier grammars and canonical lower-case UUID4.
- Represent decimal measurements as canonical decimal strings.
- Require set-like arrays sorted and unique.
- Serialize with sorted compact UTF-8 JSON, `ensure_ascii=False`, `allow_nan=False`.
- Digest as `sha256:<64 lower-case hex>` over the document with its own digest field omitted.
- Verification recomputes; it never silently repairs or normalizes accepted input.

### 5.4 IDs and safe paths

```text
scenario:<family>:<case>
configuration:<uuid4>
experiment:<uuid4>
run:<uuid4>
scorer-pass:<uuid4>
evidence-ref:<uuid4>
```

Map only parsed, validated suffixes:

```text
scenario:<family>:<case> -> scenarios/<family>/<case>/v<version>/scenario.json
configuration:<uuid>     -> configurations/<uuid>/configuration.json
experiment:<uuid>        -> experiments/<uuid>/manifest.json
run:<uuid>               -> experiments/<experiment-uuid-or-standalone>/runs/<uuid>/receipt.json
scorer-pass:<uuid>       -> .../runs/<run-uuid>/scorer-passes/<uuid>.json
evidence-ref:<uuid>      -> evidence-refs/<uuid>.json
```

Reject slash, backslash, dot-segment, control, empty/oversized segment, trailing dot/space, and Windows device names.

### 5.5 Shape validation versus authoritative verification

Shape validation checks closed fields, primitive types, enums, local relations, canonical bytes, and own digest. Its public result may say only `SHAPE_VALID`.

Authoritative verification additionally resolves every referenced evaluation artifact, compares IDs/digests/cross-links, checks scenario–configuration compatibility, verifies experiment membership, and recomputes run validity. Only it may return `VERIFIED`.

R0’s resolver covers the evaluation artifact graph. Owner-native fixture/output/trace references remain digest-bound sealed references; byte-level corpus/evidence resolution belongs to EVAL-C0/OHF2. R0 must state this limitation and may not claim corpus/evidence-content verification.

### 5.6 Scenario effect and capability policy

Scenario must declare:

```text
allowed_capability_ids
forbidden_capability_ids
allowed_tool_schema_digests
network_policy + network_allowlist
allowed_degradations
effect mode + allowed operation refs
```

Rules:

- allowed/forbidden capability IDs are disjoint, sorted, unique;
- `DENY_ALL` requires empty network allowlist;
- `ALLOWLIST` requires nonempty exact sorted allowlist;
- `NO_EFFECT_ONLY` requires empty operation-ref allowlist;
- `DECLARED_EFFECT_ALLOWED` requires nonempty exact sorted operation refs;
- a configuration may declare only allowed capabilities/tools/network behavior;
- raw run observations are compared to the configuration and scenario;
- `EFFECT_UNKNOWN` always invalidates;
- `EFFECT_KNOWN` without exact scenario authorization invalidates.

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
require_canonical_json_tree(value, path="$" ) -> None
```

- [ ] Write RED tests first for sorted UTF-8 bytes, NFC, strict primitive types, bool-vs-int, signed-64-bit bounds, float/tuple rejection, non-string keys, whole-second UTC, UUID4/case/version correctness, own-field digest omission, mutation detection, and deterministic multi-defect order.
- [ ] Confirm the RED state.
- [ ] Implement frozen errors whose defects are deterministically sorted by `(path, code, message)`.
- [ ] `require_canonical_json_tree` recursively accepts exact supported types only.
- [ ] `parse_utc_z` rejects offsets, fractions, lowercase `z`, leap seconds, alternate separators, and date-only forms.
- [ ] `__init__.py` exports constants only and has no side effects.
- [ ] Run:

```bash
pytest -q tests/test_agent_eval_canonical.py
```

- [ ] Commit only Task 1 paths.

**Acceptance:** byte identity is stable and no Python value can be silently coerced into canonical evidence.

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
```

### Scenario exact top-level fields

```text
schema
scenario_id
scenario_version
scenario_family
risk_tier
objective
input_fixture
expected_contract
temporal
source_policy
capability_policy
execution_policy
effect_policy
scoring_policy
privacy
authorship
supersedes
scenario_digest
```

Required nested fields:

```text
input_fixture / expected_contract: artifact_ref, digest
temporal: cutoff_at, authored_at
source_policy: allowlist_refs, denylist_refs, solution_refs_hidden
capability_policy: profile_id, profile_digest, allowed_capability_ids,
                   forbidden_capability_ids, allowed_tool_schema_digests
execution_policy: fresh_process_required, fresh_workspace_required,
                  fresh_session_required, resume_allowed, network_policy,
                  network_allowlist, max_elapsed_ms, max_tool_calls,
                  allowed_degradations
effect_policy: mode, allowed_operation_refs
scoring_policy: required_scorers, optional_scorers, required_dimensions
privacy: classification, model_visible_artifacts, retention_class
authorship: author_ref, independent_reviewer_ref
```

### Configuration exact top-level fields

```text
schema
configuration_id
execution
procedure
context
capabilities
randomness
created_at
configuration_digest
```

Required nested fields:

```text
execution: execution_surface, provider, model_requested, reasoning_effort,
           auth_realm_class
procedure: protected_source_commit, skillpack_commit, skillpack_version,
           instruction_bundle_digest, handoff_digest
context: context_packet_digest, retrieval_configuration_digest
capabilities: profile_id, profile_digest, declared_capability_ids,
              declared_tool_schema_digests, sandbox_digest,
              network_policy_digest, environment_digest
randomness: seed, sampling_parameters_digest
```

- [ ] Create deterministic PUBLIC_SAFE factories for one internal contract-integrity scenario and two configurations: baseline and model-mismatch arm. Make configuration digests distinct without changing the validity rule under test—for example, use distinct immutable context-packet digests while preserving the same requested model.
- [ ] Write RED tests for every unknown/missing field, ID grammar, enum, bool-vs-int, sorted/unique set, digest, cutoff order, hidden-source subset, network/effect consistency, capability disjointness, required/optional scorer disjointness, privacy/ref consistency, source commit grammar, nullable fields, and own digest.
- [ ] Configuration cannot contain served model, route, capacity, suitability, policy, score, winner, authority, approval, or acceptance.
- [ ] Add pure compatibility helper:

```python
scenario_configuration_defects(scenario, configuration) -> tuple[ContractDefect, ...]
```

It checks profile equality, configuration declared capabilities subset of scenario allowed and disjoint from forbidden, declared tools subset of allowed tools, and configuration network-policy digest equal to the canonical digest of scenario network policy/allowlist.
- [ ] Generic shape dispatch accepts finalized persisted schemas only; it rejects the run-draft schema.
- [ ] Run:

```bash
pytest -q tests/test_agent_eval_canonical.py tests/test_agent_eval_contracts.py
```

- [ ] Commit Task 2.

**Acceptance:** each arm can point to one immutable, non-authoritative configuration and incompatible capabilities/effects cannot be smuggled through prose.

---

## Task 3 — Closed experiment contract and evaluation-graph resolver

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
MemoryArtifactResolver  # tests only or inert utility
verify_scenario(document, resolver) -> VerifiedArtifact
verify_configuration(document, resolver) -> VerifiedArtifact
verify_experiment(document, resolver) -> VerifiedArtifact
```

### Experiment exact fields

```text
schema
experiment_id
scenario_refs
arms
pairing
replicates_per_arm_target
stopping_rule
primary_dimensions
guardrail_dimensions
analysis_version
phase
authorship
created_at
experiment_digest
```

Arm fields:

```text
arm_id
configuration_id
configuration_digest
```

Scenario-ref fields:

```text
scenario_id
scenario_version
scenario_digest
```

- [ ] Write RED tests for two unique sorted arms, unique configuration IDs/digests, scenario refs, pairing enum/seed, positive per-arm target, stopping rule `FIXED_REPLICATES_PER_ARM` with matching value, primary/guardrail disjointness, phase, authorship, time, and own digest.
- [ ] Define `ArtifactResolver` methods for exact scenario version, configuration ID, experiment ID, run ID, and scorer-pass ID. No write, network, environment, provider, or fallback method exists.
- [ ] Resolver returns immutable copies or read-only mappings and raises `VerificationContextError` when a referenced evaluation artifact is unavailable.
- [ ] Shape validation never consults the resolver.
- [ ] `verify_experiment` resolves every scenario/configuration, checks exact ID/version/digest, runs scenario–configuration compatibility for every scenario/arm pairing, and returns a result with literal status `VERIFIED` only after all checks pass.
- [ ] `verify_scenario` and `verify_configuration` verify shape and own digest; R0 records that owner-native fixture/procedure bytes are sealed refs, not byte-resolved by this layer.
- [ ] Missing/mismatched references are verification failures, never warnings or shape-valid success.
- [ ] Run:

```bash
pytest -q tests/test_agent_eval_contracts.py tests/test_agent_eval_verification.py
```

- [ ] Commit Task 3.

**Acceptance:** an experiment cannot verify against a missing, substituted, or incompatible configuration; shape validation cannot be presented as authoritative verification.

---

## Task 4 — Run draft, deterministic validity, and immutable run receipt

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
evaluate_validity(scenario, configuration, experiment_or_none, draft) -> ValidityDecision
finalize_run_receipt(
    scenario,
    configuration,
    experiment_or_none,
    draft,
    *,
    validator_version,
    validated_at,
    created_at,
) -> dict
verify_run(document, resolver) -> VerifiedArtifact
```

### Final run exact top-level fields

```text
schema
run_id
scenario
configuration
comparison
execution
procedure
context
observations
capabilities
randomness
effect
cleanup
evidence
resources
timing
validity
created_at
run_digest
```

The draft has the same fields except `validity`, `created_at`, `run_digest`, and uses `mastermind.agent_evaluation_run_draft.v1`.

Required nested fields:

```text
scenario: scenario_id, scenario_version, scenario_digest, corpus_revision,
          temporal_cutoff
configuration: configuration_id, configuration_digest
comparison: experiment_id, arm_id, pair_key, replicate_index
execution: runner_id, execution_surface, provider, model_requested, model_served,
           reasoning_effort, auth_realm_class, process_fingerprint,
           native_session_fingerprint, completion_status, termination_reason,
           fresh_process_observed, fresh_workspace_observed,
           fresh_session_observed, resume_used
procedure: protected_source_commit, skillpack_commit, skillpack_version,
           instruction_bundle_digest, handoff_digest
context: source_allowlist_digest, context_packet_digest,
         retrieval_configuration_digest
observations: observed_source_refs, observed_capability_ids,
              observed_tool_schema_digests, observed_network_destinations,
              dependency_degradations
capabilities: profile_id, profile_digest, sandbox_digest,
              network_policy_digest, workspace_digest, environment_digest
randomness: seed, sampling_parameters_digest
effect: state, operation_ref, reconciliation_ref
cleanup: status, proof_ref, proof_digest
evidence: output_digest, tool_event_digest, trace_ref, artifact_refs
resources: input_tokens, output_tokens, tool_calls, elapsed_ms,
           provider_usage_ref, estimated_marginal_cost, cost_currency
timing: started_at, completed_at, monotonic_duration_ms
validity: status, reason_codes, validator_version, validated_at
```

- [ ] Build clean baseline draft and model-mismatch draft. Both bind exact configuration, experiment arm, pair key `pair:contract-integrity:0001`, replicate 1, scenario cutoff, raw capability/tool/source/network observations, `NO_EFFECT`, cleanup `PROVEN`, and completion `COMPLETED`.
- [ ] Write RED tests for every closed field set, scenario/configuration digests, experiment membership, arm/configuration match, pair identity, replicate bounds, cutoff, requested/served model, configuration execution/procedure/context/capability/randomness equality, raw source/capability/tool/network observations, freshness, resume, effects, cleanup, degradations, time/resource relations, currency/cost pairing, and forbidden runner result fields.
- [ ] Derive all reasons from stored draft fields only. Do not accept `RunFacts`, runner `pass`, score, winner, policy, approval, or acceptance.
- [ ] Implement at least these exact reason codes:

```text
MODEL_SERVED_MISMATCH
CONFIGURATION_FIELD_MISMATCH
TOOL_SCHEMA_DRIFT
CAPABILITY_DRIFT
FORBIDDEN_CAPABILITY
UNAUTHORIZED_SOURCE
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
SOURCE_POLICY_DIGEST_MISMATCH
```

- [ ] Apply precedence:

```text
EFFECT_UNKNOWN                     -> INVALID_EFFECT_UNKNOWN
else unauthorized/hidden source   -> INVALID_LEAKAGE
else required cleanup unproven    -> INVALID_CLEANUP
else configuration/capability/
     tool/network/effect/arm/
     cutoff mismatch              -> INVALID_CONFIGURATION
else allowed degradation present  -> DEGRADED_DEPENDENCY
else                               -> VALID
```

Retain every reason, including lower-priority reasons.

- [ ] `NO_EFFECT` requires null operation/reconciliation refs. `EFFECT_KNOWN` requires exact operation ref and scenario authorization; reconciliation ref follows scenario/run contract. `EFFECT_UNKNOWN` requires an operation or dispatch reference when known and always invalidates.
- [ ] `NOT_REQUIRED` cleanup is allowed only for a scenario/configuration combination that cannot create process/workspace/effect state; otherwise it is unproven.
- [ ] `finalize_run_receipt` verifies source artifacts, shape-validates draft, derives validity, switches schema, inserts validity/time/digest, then authoritatively verifies the resulting run before return.
- [ ] `verify_run` resolves scenario/configuration/experiment and recomputes exact validity status/reasons. Forged or stale validity fails.
- [ ] Time rule: `started_at <= completed_at <= validated_at <= created_at`; monotonic duration equals resource elapsed ms.
- [ ] Completion does not determine correctness. Clean completion yields technical `VALID`, not `VALID_PASS`.
- [ ] Run:

```bash
pytest -q tests/test_agent_eval_contracts.py tests/test_agent_eval_validity.py tests/test_agent_eval_verification.py
```

- [ ] Commit Task 4.

**Acceptance:** mutating/deleting any validity input changes the recomputation or fails the contract, and no runner can self-grade.

---

## Task 5 — Append-only scorer pass and evidence-reference projection

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
verify_scorer_pass(document, resolver)
validate_evidence_ref_shape(document)
summarize_experiment(...)
verify_evidence_ref(document, resolver)
```

### Scorer-pass fields

```text
schema
scorer_pass_id
run_ref
run_digest
scorer_id
scorer_version
code_commit
scorer_configuration_digest
method
input_evidence
dimension_results
grader
human_reviewer_ref
created_at
supersedes
scorer_pass_digest
```

`input_evidence` entries are exact `{artifact_ref, digest}`. Dimension entries are exact `{dimension, status, reason_codes, evidence_refs}`.

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

### Evidence-reference fields

```text
schema
evidence_ref_id
task_class
scenario_refs
experiment_ref
configuration_refs
run_results
dimension_gates
valid_run_count
invalid_run_count
degraded_run_count
unscored_run_count
invalid_counts
sample_size
uncertainty
phase
evidence_grade
limitations
receipt_refs
scorer_pass_refs
analysis_refs
intended_owner
review_at
non_authority_statement
created_at
evidence_ref_digest
```

- [ ] Write RED tests for exact run/digest binding, scorer identity/version/code/config, deterministic method, sorted dimension/reason/evidence sets, grader null for deterministic method, supersession without rewrite, and own digest.
- [ ] Technical-integrity scorer maps stored technical validity/reasons to the four integrity dimensions. It does not claim broad agent correctness, architecture quality, or product usefulness.
- [ ] Write RED evidence-reference tests for exact scenario/configuration/experiment/run/scorer cross-links, arm/pair/replicate preservation, invalid denominator exclusion, dimension-gate matrix, `INSUFFICIENT_EVIDENCE`, `NOT_ESTIMATED` uncertainty, limitations, owner/review time, and non-authority statement.
- [ ] Required statement:

```text
This evidence reference does not authorize routing, policy, release, merge, deployment, production execution, or acceptance.
```

- [ ] Per-run scored projection:
  - invalid/degraded technical state passes through;
  - technical `VALID` plus all required accepted dimensions PASS => `VALID_PASS`;
  - any required dimension FAIL => `VALID_FAIL`;
  - no fail plus PARTIAL => `VALID_PARTIAL`;
  - missing/UNKNOWN required dimension => `UNSCORED`.
- [ ] R0 evidence grade remains `INSUFFICIENT_EVIDENCE`: it has no real agent task and not enough valid paired samples.
- [ ] Reject numeric aggregate, winner, route, policy, approved, accepted, promoted, or release fields anywhere they are not explicitly part of a closed schema.
- [ ] `verify_scorer_pass` resolves exact run and superseded pass. `verify_evidence_ref` resolves every evaluation artifact, recomputes counts/projections/gates, and rejects stale summaries.
- [ ] Run:

```bash
pytest -q tests/test_agent_eval_scoring.py tests/test_agent_eval_verification.py
```

- [ ] Commit Task 5.

**Acceptance:** scoring appends without run mutation, and the summary cannot erase invalid evidence or imply organizational authority.

---

## Task 6 — Create-only artifact store and safe resolution

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
ArtifactStore.verify(path) -> VerifiedArtifact
ArtifactStore.verify_tree() -> tuple[ContractDefect, ...]
WriteDisposition.CREATED
WriteDisposition.IDEMPOTENT
```

The store implements the evaluation `ArtifactResolver`. Creation order is topological:

```text
scenario/configuration -> experiment -> run -> scorer pass -> evidence reference
```

- [ ] Write RED tests for every ID-to-path mapping, device names, slash/backslash/dot/trailing-space, root escape, symlink parents, nonregular files, oversized files, create/idempotent/conflict, corruption, interrupted prepublication cleanup, missing dependencies, stale validity, stale evidence counts, and whole-tree verification.
- [ ] Validate/verify before publication. A draft is never publishable.
- [ ] Secret policy:
  - closed schemas reject unknown secret-bearing fields;
  - recursively compare every allowed string value with `scripts.ohf.redaction.redact_evidence_text` and reject if redaction changes it;
  - do not apply key-name heuristics to legitimate counters such as `input_tokens`;
  - explicitly reject forbidden names in draft/document trees;
  - normal SHA-256 digests must not false-positive.
- [ ] Create private parents only after resolved-root/symlink checks.
- [ ] Write canonical bytes to a same-directory temp regular file mode `0o600`, flush/fsync.
- [ ] Publish with `os.link(temp, final)`; fsync directory; unlink temp; read back and verify.
- [ ] Existing exact bytes => `IDEMPOTENT`; changed/corrupt bytes => `ArtifactConflictError`.
- [ ] Unsupported hard-link/create-only semantics fail closed with no final artifact.
- [ ] `read_shape` may return only shape-valid bytes and must be named accordingly. `verify` and `verify_tree` resolve dependencies and recompute cross-links/validity/projections. They never repair.
- [ ] Whole-tree verification detects orphaned runs/scorers, unexpected JSON files, wrong schema-to-path mapping, and missing referenced artifacts.
- [ ] Run:

```bash
pytest -q tests/test_agent_eval_store.py tests/test_agent_eval_verification.py
```

- [ ] Commit Task 6.

**Acceptance:** no artifact can overwrite, escape, hide behind symlinks, verify without dependencies, or preserve forged validity.

---

## Task 7 — CLI and complete fake two-arm journey

**Files**

```text
scripts/agent_eval/cli.py
scripts/agent_evaluation.py
tests/test_agent_eval_cli.py
tests/fixtures/agent_eval/README.md
```

**Commands**

```text
validate-shape <document.json>
verify --root <root> <document-or-stored-path>
create --root <root> <finalized-document.json>
finalize-run --root <root> --draft <run-draft.json>
             --validator-version <v> --validated-at <time> --created-at <time>
             --output <receipt.json>
score-integrity --root <root> --run-id <run:id>
                --code-commit <sha> --created-at <time> --id <uuid>
summarize --root <root> --experiment-id <experiment:id>
          --owner <owner> --review-at <time> --created-at <time> --id <uuid>
verify-tree --root <root>
```

Exit codes:

```text
0 = shape validation, verification, or artifact operation succeeded cleanly
1 = command completed with invalid/degraded/unscored/insufficient-evidence result
2 = usage, shape, verification-context, conflict, corruption, privacy, or filesystem error
```

- [ ] Write RED CLI tests before implementation.
- [ ] `main(argv)` uses argparse, returns int, emits one canonical JSON object to stdout, diagnostics to stderr, and no traceback for bounded expected errors.
- [ ] `validate-shape` prints literal `SHAPE_VALID`, never `VERIFIED`.
- [ ] `verify` and `verify-tree` use the store resolver and print `VERIFIED` only after cross-reference/recomputation.
- [ ] `finalize-run` resolves exact scenario/configuration/experiment IDs from the draft through the root, creates an exclusive local output file, and does not publish until `create` is called.
- [ ] `score-integrity` appends a pass; it cannot alter receipt bytes.
- [ ] `summarize` resolves all runs/scorers from the experiment and writes one evidence ref.
- [ ] Complete journey in one fresh `tmp_path`:
  1. create one scenario;
  2. create two configurations;
  3. create one two-arm experiment;
  4. finalize/store clean baseline run;
  5. finalize/store served-model-mismatch run;
  6. verify baseline `VALID` and mismatch `INVALID_CONFIGURATION` with `MODEL_SERVED_MISMATCH`;
  7. append one integrity scorer pass per run;
  8. summarize/store one evidence reference;
  9. verify whole tree;
  10. assert exact config/arm/pair/replicate links, one valid/one invalid count, invalid retention, `INSUFFICIENT_EVIDENCE`, no aggregate/winner/policy/acceptance fields, and no file outside root.
- [ ] `tests/fixtures/agent_eval/README.md` declares fixtures synthetic and `PUBLIC_SAFE`, with no real user/account/host/credential/chat data. It explicitly says external fixture/output bytes are not content-verified by R0.
- [ ] Run:

```bash
pytest -q tests/test_agent_eval_cli.py
python scripts/agent_evaluation.py --help
```

- [ ] Manually run the same sequence in a new temporary root and retain canonical stdout, IDs, digests, and tree as PR evidence.
- [ ] Commit Task 7.

**Acceptance:** a fresh reviewer can reproduce the full journey from repository code/fixtures/commands without network, provider access, or hidden state.

---

## Task 8 — Inertness, privacy, mutation, and path fences

**Files**

```text
tests/test_agent_eval_inertness.py
```

Implementation files may change only to fix a protection failure.

- [ ] AST-reject production imports beginning with:

```text
control_plane.executive_runtime
control_plane.executive_service
control_plane.codex_worker
control_plane.model_router
integrations.slack
integrations.executive_mcp
sqlite3
psycopg
duckdb
httpx
requests
socket
subprocess
inspect_ai
langfuse
promptfoo
```

Permit only the exact OHF text-redaction helper import; no OHF runner import.

- [ ] AST-reject network/process/thread/task/database primitives and environment reads in production: `Popen`, subprocess execution, socket/connect/urlopen, `Thread`, `Process`, `asyncio.create_task`, SQLite/DuckDB/Postgres access, `os.environ`, and `getenv`.
- [ ] Import every production module in a clean test subprocess and prove no output, file, socket, thread, child process, background task, or environment read. The test itself may use subprocess; production code may not.
- [ ] Secret-shape tests include synthetic API key, JWT, authorization/cookie, token value, email/account ID, `MASTERMIND_*=`, and private host. Require rejection before publication. Verify SHA-256 and legitimate resource counters do not false-positive.
- [ ] Mutation matrix kills at least:

```text
unknown top-level/nested field
wrong schema/digest
float/tuple/non-NFC/non-string key
future/mismatched cutoff
unauthorized/hidden source
configuration ID/digest/field mismatch
requested/served model mismatch
extra/missing raw capability or tool
forbidden capability
unexpected network destination
freshness false/null when required
resume when forbidden
known unauthorized effect
effect reference mismatch
effect unknown
unproven cleanup
disallowed/allowed degradation
experiment scenario/arm/config mismatch
missing pair key
replicate out of range
negative/bool resource count
time inversion/duration mismatch
same ID changed bytes
symlink/path traversal/device-name segment
numeric aggregate/winner/route/policy/approval field
scorer pass injected into run
runner pass/result field in draft
forged stored validity/reasons
shape-only result relabeled VERIFIED
missing resolver dependency
stale evidence-reference counts
```

- [ ] Changed-path test allows only Section 4.1 implementation paths plus accepted EVAL-F0 records visible from base. No control-plane/config/dependency/workflow file may enter.
- [ ] Run:

```bash
pytest -q tests/test_agent_eval_inertness.py
pytest -q tests/test_agent_eval_*.py
```

- [ ] Commit Task 8.

**Acceptance:** every load-bearing authority, privacy, identity, verification, immutability, and denominator invariant has an executable negative test.

---

## Task 9 — Exact-head verification, independent review, and return

- [ ] Re-pin protected master and Skillpack. If base moved, compare paths/semantics and reconcile on the same branch without force/reset/replacement.
- [ ] Run targeted:

```bash
pytest -q tests/test_agent_eval_*.py
```

- [ ] Run full:

```bash
pytest -q
```

Classify any full-suite failure with exact evidence; targeted green is not enough.

- [ ] Run static/manual evidence:

```bash
python -m compileall -q scripts/agent_eval scripts/agent_evaluation.py
python scripts/agent_evaluation.py --help
```

- [ ] Re-run fake journey in a fresh root; record scenario/configuration/experiment/run/scorer/evidence IDs/digests, stdout, tree, and exact head SHA.
- [ ] Inspect final diff for only allowed paths, no dependency/config/workflow changes, no secrets/private IDs/generated junk.
- [ ] Answer in PR:

```text
What new machine/reviewer capability exists?
Can validity be recomputed from stored artifacts only?
Can a runner self-grade?
Can a scorer mutate a run?
Can a missing configuration still verify?
Can invalid evidence disappear from denominators?
Can a known effect pass without scenario authorization?
Can an ID overwrite/escape the root?
Did any lifecycle/router/memory/policy/provider/service/database appear?
What remains NOT_BUILT or unproven?
```

- [ ] Request one independent Auditor Sol/qualified reviewer against exact immutable head. Review attacks source-law conformance, configuration/arm/pair identity, raw capability/effect policy, shape-versus-verification separation, validity recomputation, digest/idempotency/atomicity, secret/path/symlink behavior, invalid denominators, no-duplicate owners, and fake-journey reproducibility.
- [ ] Resolve all `REQUEST_CHANGES`; re-run exact-head verification after patches.
- [ ] Return to parent Program CEO with:

```text
operation key
pickup ACK and START refs
branch / PR / base / head
changed paths
targeted/full/CI/security receipts
synthetic artifact identities and digests
independent review disposition
capability state
remaining false/unproven claims
exact next action and predecessor gate
```

### Stop condition

The worker stops only after exact-head checks are terminal, the synthetic journey is reproducible, independent review is resolved, current base is reconciled, and parent Sol issues exactly one `SOL ACCEPTED / STOP` or `SOL REQUEST_REPAIR` on the same carrier.

A green PR or merge proves only the production-inert native evidence core. It does not prove OHF execution, corpus quality, real model comparison, routing equivalence, organizational learning, policy improvement, UI, canary, or production value.

---

## 7. Required continuation after R0 acceptance

R0 acceptance opens, but does not auto-start:

1. **EVAL-C0:** a separate corpus-only carrier with 15–30 governed cases and private holdout controls.
2. **EVAL-OHF1:** resume existing PR #162 on its same branch/carrier; implement the narrow fresh-Sol runner.
3. **EVAL-OHF2:** adapt the proven runner to the run-draft/finalizer contract.
4. **EVAL-S1/E1:** task scorers and first paired real experiment.

Inspect, Promptfoo, Parquet/DuckDB analysis, UI, owner-policy handoff, and prospective canary remain gated on native real-run evidence.

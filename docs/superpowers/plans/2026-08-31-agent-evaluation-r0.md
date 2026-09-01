# Agent Evaluation EVAL-R0 — Executable Implementation Plan

> **Worker method:** use test-driven development and either `superpowers:subagent-driven-development` or `superpowers:executing-plans`. Work task-by-task; do not widen scope to an evaluation framework, provider runner, UI, policy engine, or database.

**Parent operation:** `mastermind-agent-evaluation-organizational-learning-fabric-20260830-sol-pro-001`  
**Parent architecture carrier:** Mastermind PR #299  
**Goal:** build the production-inert Mastermind-native scenario/experiment/run-validity/scorer/evidence-reference core and prove one complete synthetic two-arm journey.  
**Truthful post-wave state:** at most `BUILT_NOT_PROVEN / PRODUCTION_INERT`; no real model or OHF run is proven by R0.  
**Technology:** Python 3.11+, standard library, pytest, and only the existing text-redaction helper needed for secret-shape checks.

---

## 1. Observable mission and user/machine journey

Create one independently useful vertical in which a reviewer can:

1. validate a closed synthetic scenario and two-arm experiment;
2. finalize a runner draft into an immutable technical run receipt;
3. see one clean run become technically `VALID`;
4. see one requested/served-model mismatch become `INVALID_CONFIGURATION`;
5. recompute both validity decisions from stored fields;
6. append deterministic integrity scorer passes without changing either run;
7. produce a sanitized evidence reference with exact arm/pair identities, invalid/degraded accounting, dimension gates, and `INSUFFICIENT_EVIDENCE`;
8. re-read and digest-verify every artifact;
9. verify that no runner assertion, universal score, winner, route, policy, lifecycle, service, or production effect was created.

This vertical is the contract target for later OHF and Inspect adapters. It is not infrastructure without a consumer: the CLI, immutable artifact tree, deterministic integrity scorer, and evidence-reference projection are the first machine/reviewer consumers.

---

## 2. Authority and document precedence

Apply in this order:

1. current protected `mastermindx-market-intelligence/Mastermind` Skillpack loaded atomically at action time;
2. `docs/superpowers/specs/2026-08-31-agent-evaluation-fabric-design.md` at the accepted EVAL-F0 head;
3. this plan;
4. existing protected house contracts/helpers only where explicitly consumed;
5. worker implementation choices inside the frozen boundary.

The original pre-review plan clauses that fused runner outcome with validity, placed scorer references inside runs, omitted experiment arm/pair identity, or used colon-bearing IDs as filesystem path components are rejected and must not be revived.

Canonical owners remain:

- Executive OS: Job/Attempt/Worker/Event lifecycle, effects, retry/requeue, CEO intent.
- Agent OS: durable organizational decisions/discoveries/workstreams/handoffs.
- GitHub: implementation, tests, PR review, CI, merge and production evidence.
- OHF/PR #162: fresh App Server runner mechanics.
- Outcome Learning/Macro PR #6699: organizational consequence and policy promotion.
- Model Router/Capacity/CXI/CodeIntel/Observability/Wake: their existing domains.

EVAL-R0 writes none of those owners.

---

## 3. Verified starting state

At EVAL-F0 review time:

- protected Mastermind was reconciled through `e60f69aa10e67b1334b1fa6a3299cb90fbbde7ab`;
- Skillpack remained `mastermind.sol_skillpack.v1` v1.0.1 / bootstrap major 1;
- PR #162 was open/draft with two records and no fresh-runner implementation;
- Macro PR #6699 was open/draft and remained the sole Outcome Learning carrier;
- no `scripts/agent_eval/**` package or canonical agent-evaluation contract existed;
- existing `scripts/ohf/redaction.py` exposes house text-redaction behavior;
- project Python floor is 3.11 and pytest uses `tests/`.

The worker must re-pin all current state. Do not assume these observations remain current.

---

## 4. Exact scope and non-goals

### 4.1 Allowed implementation paths

```text
scripts/agent_eval/__init__.py
scripts/agent_eval/errors.py
scripts/agent_eval/canonical.py
scripts/agent_eval/contracts.py
scripts/agent_eval/validity.py
scripts/agent_eval/store.py
scripts/agent_eval/scoring.py
scripts/agent_eval/cli.py
scripts/agent_evaluation.py
tests/agent_eval_factories.py
tests/test_agent_eval_canonical.py
tests/test_agent_eval_contracts.py
tests/test_agent_eval_validity.py
tests/test_agent_eval_store.py
tests/test_agent_eval_scoring.py
tests/test_agent_eval_cli.py
tests/test_agent_eval_inertness.py
tests/fixtures/agent_eval/README.md
```

The accepted EVAL-F0 spec/plan/research remain visible in the implementation PR but should not be edited unless a discovered contradiction requires a narrowly documented architecture return.

### 4.2 Hard non-goals

Do not:

- modify PR #162 or Macro #6699;
- launch a model, provider process, App Server, browser, container, MCP server, or background task;
- import an evaluation framework or add a dependency;
- read credentials, provider homes, cookies, OAuth, private chats, chain of thought, or environment dumps;
- perform network access;
- create or mutate Executive/Agent OS/Slack/Linear/Router/Capacity/Wake/Observability state;
- create SQLite/Postgres/ClickHouse/DuckDB tables, a vector store, daemon, queue, scheduler, watcher, service, or UI;
- produce a universal model score, winner, route change, policy candidate, canary, release approval, or deployment;
- treat a runner’s completion label as accepted task correctness;
- place scorer-pass references inside an immutable run;
- use raw `scenario:...`, `experiment:...`, `run:...`, `scorer-pass:...`, or `evidence-ref:...` values as filesystem segments.

Stop and return an architecture decision if the useful vertical cannot be completed inside this boundary.

---

## 5. Contract and behavior freeze

### 5.1 Canonical schemas

Implement exactly:

```text
mastermind.agent_evaluation_scenario.v1
mastermind.agent_evaluation_experiment.v1
mastermind.agent_evaluation_run.v1
mastermind.agent_evaluation_scorer_pass.v1
mastermind.agent_evaluation_evidence_ref.v1
```

A run draft is a closed transient input with the run schema name and all run fields except `validity`, `created_at`, and `run_digest`. It is finalized before storage and is never accepted by generic artifact import.

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

Derived scored result:

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

Evidence-set grade includes `INSUFFICIENT_EVIDENCE`. A runner never supplies technical validity or scored result.

### 5.3 Canonical bytes

- Accept only JSON `null`, bool, signed 64-bit int, NFC string, list, and dict with string keys.
- Reject floats, tuples, non-string keys, out-of-range ints, NaN/infinity, and silent coercion.
- Require exact whole-second UTC timestamps: `YYYY-MM-DDTHH:MM:SSZ`.
- Use ASCII identifier grammars and canonical lower-case UUID4.
- Represent decimals as canonical decimal strings.
- Require set-like arrays sorted and unique.
- Canonical bytes use sorted compact UTF-8 JSON with `ensure_ascii=False` and `allow_nan=False`.
- Digest is `sha256:<64 lower-case hex>` over the document with its own digest field absent.
- Verification recomputes; it never repairs/normalizes accepted input.

### 5.4 IDs and path mapping

```text
scenario:<family>:<case>
experiment:<uuid4>
run:<uuid4>
scorer-pass:<uuid4>
evidence-ref:<uuid4>
```

Schema-aware safe mapping:

```text
scenario:<family>:<case> -> scenarios/<family>/<case>/v<version>/scenario.json
experiment:<uuid>        -> experiments/<uuid>/manifest.json
run:<uuid>               -> experiments/<experiment-uuid-or-standalone>/runs/<uuid>/receipt.json
scorer-pass:<uuid>       -> .../runs/<run-uuid>/scorer-passes/<uuid>.json
evidence-ref:<uuid>      -> evidence-refs/<uuid>.json
```

Reject slash/backslash, dot segments, controls, trailing dot/space, empty/oversized segments, and Windows device names. The prefixes and colons are parsed away; they are never path components.

### 5.5 Run validity inputs

Every final run stores the bounded raw observations needed for recomputation:

- scenario ID/version/digest/corpus/cutoff;
- configuration ref/digest;
- experiment ID, arm ID, pair key, replicate index;
- requested/served model;
- observed source refs;
- observed tool-schema digests;
- unexpected capabilities;
- observed network destinations;
- fresh process/workspace/session observations;
- resume use;
- effect state and refs;
- cleanup state/proof;
- degradations;
- exact completion/evidence/resources/timing.

`finalize_run_receipt` receives the scenario, optional experiment, and run draft. It derives validity and writes the only canonical run. No parallel `RunFacts` argument is allowed.

### 5.6 Validity precedence

Collect all reason codes, then select:

```text
EFFECT_UNKNOWN                           -> INVALID_EFFECT_UNKNOWN
else unauthorized/hidden source         -> INVALID_LEAKAGE
else required cleanup not proven         -> INVALID_CLEANUP
else configuration/tool/network/fresh/
     arm/pair/cutoff mismatch             -> INVALID_CONFIGURATION
else allowed non-empty degradation       -> DEGRADED_DEPENDENCY
else                                      -> VALID
```

The final validator recomputes and requires exact status/reason equality.

### 5.7 Scoring and evidence

- Scorer passes reference immutable runs and append forever.
- Dimension status is `PASS | FAIL | PARTIAL | UNKNOWN | NOT_APPLICABLE`.
- No scorer pass has a universal numeric aggregate or winner.
- Evidence reference derives per-run scored result from technical validity and accepted required dimension passes.
- Invalid/degraded runs remain visible and never enter valid denominators.
- R0’s initial scorer is technical-integrity-only; it does not claim broad agent quality.

---

## 6. Ordered TDD implementation

## Task 0 — Pickup, current-state reconciliation, and carrier creation

**Mission:** establish one collision-free implementation carrier before code.

- [ ] Post one pickup ACK on the exact commission carrier with operation/branch intent. ACK is receipt only.
- [ ] Re-fetch protected `Mastermind/master`, load current Skillpack atomically, and record SHA/schema/version/bootstrap.
- [ ] Search current branches/PRs/files for `scripts/agent_eval`, schema names, and the proposed operation.
- [ ] Re-check PR #162 and Macro #6699; do not edit either.
- [ ] Create one branch from current protected master and one draft/HOLD PR for EVAL-R0.
- [ ] Post separate START only after collision/base/path gates are clear.
- [ ] Record exact base/head, allowed paths, non-goals, and this plan in PR body.

**Stop:** any active implementation carrier or overlapping path owner exists; return collision evidence rather than forking.

---

## Task 1 — Structured defects and strict canonical JSON

**Files:**

```text
scripts/agent_eval/__init__.py
scripts/agent_eval/errors.py
scripts/agent_eval/canonical.py
tests/test_agent_eval_canonical.py
```

**Public interfaces:**

```python
ContractDefect
ContractError
ArtifactConflictError
canonical_json_bytes(value) -> bytes
digest_value(value) -> str
digest_document(document, digest_field) -> str
add_document_digest(document, digest_field) -> dict
verify_document_digest(document, digest_field) -> None
parse_utc_z(value, path="$" ) -> datetime
require_canonical_json_tree(value, path="$" ) -> None
```

- [ ] Write RED tests first for sorted UTF-8 bytes, Unicode NFC, strict primitive types, signed-64-bit ints, float/tuple rejection, non-string keys, whole-second `Z` timestamps, UUID normalization, own-field digest omission, mutation detection, and deterministic multi-defect order.
- [ ] Confirm RED via missing module/behavior.
- [ ] Implement frozen dataclasses:

```python
@dataclass(frozen=True, order=True)
class ContractDefect:
    path: str
    code: str
    message: str

class ContractError(ValueError):
    defects: tuple[ContractDefect, ...]

class ArtifactConflictError(RuntimeError):
    artifact_path: str
```

- [ ] `require_canonical_json_tree` must recursively accept only `None`, exact bool, exact int in `[-2**63, 2**63-1]`, NFC str, list, dict with str keys. Reject tuple and float even though `json.dumps` could coerce/encode them.
- [ ] Use a strict regex plus datetime parse for `YYYY-MM-DDTHH:MM:SSZ`; reject offsets, lowercase `z`, fractions, leap seconds, date-only forms, and alternate separators.
- [ ] Make `__init__.py` export constants only and perform no import side effects.
- [ ] Run:

```bash
pytest -q tests/test_agent_eval_canonical.py
```

- [ ] Commit only Task 1 paths.

**Acceptance:** canonical bytes and digests are stable across key order and reject all silent coercions.

---

## Task 2 — Closed scenario and experiment contracts

**Files:**

```text
scripts/agent_eval/contracts.py
tests/agent_eval_factories.py
tests/test_agent_eval_contracts.py
```

**Public interfaces:**

```python
validate_document(document)
validate_scenario(document)
validate_experiment(document)
build_scenario(...)
build_experiment(...)
```

### Scenario exact top-level fields

```python
SCENARIO_FIELDS = frozenset({
    "schema", "scenario_id", "scenario_version", "scenario_family", "risk_tier",
    "objective", "input_fixture", "expected_contract", "temporal", "source_policy",
    "capability_policy", "execution_policy", "scoring_policy", "privacy", "authorship",
    "supersedes", "scenario_digest",
})
```

Nested sets:

```text
input_fixture/expected_contract: artifact_ref, digest
temporal: cutoff_at, authored_at
source_policy: allowlist_refs, denylist_refs, solution_refs_hidden
capability_policy: profile_id, profile_digest, allowed_tool_schema_digests, forbidden_capabilities
execution_policy: fresh_process_required, fresh_workspace_required, fresh_session_required,
                  resume_allowed, network_policy, network_allowlist,
                  max_elapsed_ms, max_tool_calls, allowed_degradations
scoring_policy: required_scorers, optional_scorers, required_dimensions
privacy: classification, model_visible_artifacts, retention_class
authorship: author_ref, independent_reviewer_ref
```

### Experiment exact top-level fields

```python
EXPERIMENT_FIELDS = frozenset({
    "schema", "experiment_id", "scenario_refs", "arms", "pairing",
    "replicates_per_arm_target", "stopping_rule", "primary_dimensions",
    "guardrail_dimensions", "analysis_version", "phase", "authorship",
    "created_at", "experiment_digest",
})
```

Arm fields are exactly:

```text
arm_id, configuration_ref, configuration_digest
```

- [ ] Build deterministic PUBLIC_SAFE factories with one internal `mastermind.evaluation_contract_integrity.v1` scenario and two arms `arm:baseline` and `arm:model-mismatch`.
- [ ] Write RED tests for unknown/missing fields at every nesting level, exact schema/ID grammars, positive versions/limits, bool-vs-int rejection, enum closure, sorted/unique sets, disjoint required/optional scorers, network-policy/allowlist consistency, hidden-source subset, cutoff order, privacy/ref consistency, own digest, two unique sorted arms, unique configuration digests, scenario refs, pairing, per-arm target/stopping-rule consistency, and primary/guardrail disjointness.
- [ ] `DENY_ALL` requires empty network allowlist; `ALLOWLIST` requires non-empty sorted allowlist.
- [ ] `solution_refs_hidden` must be a subset of `denylist_refs`.
- [ ] `replicates_per_arm_target` is positive; stopping rule is exactly `FIXED_REPLICATES_PER_ARM` with the same value.
- [ ] Generic `validate_document` accepts finalized canonical schemas only; run drafts are not generic documents.
- [ ] Run:

```bash
pytest -q tests/test_agent_eval_canonical.py tests/test_agent_eval_contracts.py
```

- [ ] Commit Task 2.

**Acceptance:** no extra policy/authority field can be smuggled into a scenario or experiment, and every arm binds an immutable configuration ref/digest.

---

## Task 3 — Closed run draft, deterministic finalizer, and immutable run receipt

**Files:**

```text
scripts/agent_eval/contracts.py
scripts/agent_eval/validity.py
tests/agent_eval_factories.py
tests/test_agent_eval_validity.py
tests/test_agent_eval_contracts.py
```

**Public interfaces:**

```python
validate_run_draft(draft)
evaluate_validity(scenario, experiment_or_none, draft) -> ValidityDecision
finalize_run_receipt(scenario, experiment_or_none, draft, *, validator_version, validated_at, created_at)
validate_run(document, *, scenario=None, experiment=None)
```

### Run top-level fields

```python
RUN_FIELDS = frozenset({
    "schema", "run_id", "scenario", "configuration", "comparison", "execution",
    "procedure", "context", "observations", "capabilities", "randomness", "effect",
    "cleanup", "evidence", "resources", "timing", "validity", "created_at", "run_digest",
})
```

The draft has `RUN_FIELDS - {"validity", "created_at", "run_digest"}`.

Required nested fields:

```text
scenario:
  scenario_id, scenario_version, scenario_digest, corpus_revision, temporal_cutoff
configuration:
  configuration_ref, configuration_digest
comparison:
  experiment_id, arm_id, pair_key, replicate_index
execution:
  runner_id, execution_surface, provider, model_requested, model_served,
  reasoning_effort, auth_realm_class, process_fingerprint,
  native_session_fingerprint, completion_status, termination_reason,
  fresh_process_observed, fresh_workspace_observed, fresh_session_observed,
  resume_used
procedure:
  protected_source_commit, skillpack_commit, skillpack_version,
  instruction_bundle_digest, handoff_digest
context:
  source_allowlist_digest, context_packet_digest, retrieval_configuration_digest
observations:
  observed_source_refs, observed_tool_schema_digests, unexpected_capabilities,
  observed_network_destinations, dependency_degradations
capabilities:
  profile_id, profile_digest, sandbox_digest, network_policy_digest,
  workspace_digest, environment_digest
randomness:
  seed, sampling_parameters_digest
effect:
  state, operation_ref, reconciliation_ref
cleanup:
  status, proof_ref, proof_digest
evidence:
  output_digest, tool_event_digest, trace_ref, artifact_refs
resources:
  input_tokens, output_tokens, tool_calls, elapsed_ms,
  provider_usage_ref, estimated_marginal_cost, cost_currency
timing:
  started_at, completed_at, monotonic_duration_ms
validity:
  status, reason_codes, validator_version, validated_at
```

- [ ] Write a clean run-draft factory binding baseline arm, pair key `pair:contract-integrity:0001`, replicate 1, exact scenario cutoff, exact scenario profile/tool/source/network digests, requested=served model, no unexpected observations, `NO_EFFECT`, cleanup `PROVEN`, and completion `COMPLETED`.
- [ ] Write a second draft by changing only `model_served`.
- [ ] Write RED tests for every closed field set, experiment scenario membership, arm/configuration match, required pair identity, replicate bounds, scenario cutoff/digest, profile/tool/source/network comparison, requested/served mismatch, freshness requirements, resume prohibition, source allowlist/denylist, unexpected capabilities/destinations, degradations, effect and cleanup semantics, time/resource relations, decimal/currency pairing, and own digest.
- [ ] Implement immutable decision:

```python
@dataclass(frozen=True)
class ValidityDecision:
    status: str
    reason_codes: tuple[str, ...]
```

- [ ] Derive reasons from stored draft fields only. Do not accept `observed_outcome`, `pass`, `score`, `winner`, `policy`, or an external facts object.
- [ ] At minimum implement exact reason codes:

```text
MODEL_SERVED_MISMATCH
TOOL_SCHEMA_DRIFT
UNEXPECTED_CAPABILITY
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
EXPERIMENT_ARM_MISMATCH
PAIR_IDENTITY_MISSING
CONFIGURATION_MISMATCH
SCENARIO_NOT_IN_EXPERIMENT
REPLICATE_OUT_OF_RANGE
TEMPORAL_CUTOFF_MISMATCH
PROFILE_MISMATCH
SOURCE_POLICY_DIGEST_MISMATCH
```

- [ ] Apply frozen precedence without discarding lower-priority reasons.
- [ ] `finalize_run_receipt` validates scenario/experiment/draft, derives validity, inserts validity/created time, adds digest, then validates the final run against source contracts.
- [ ] `validate_run` recomputes validity when scenario/experiment are supplied and requires exact equality. The store/CLI must supply them for verification of run artifacts.
- [ ] Time rule: `started_at <= completed_at <= validated_at <= created_at`; monotonic duration equals resource elapsed ms.
- [ ] Completion status does not decide task correctness. A clean completed run is technically `VALID`, not `VALID_PASS`.
- [ ] Run:

```bash
pytest -q tests/test_agent_eval_canonical.py tests/test_agent_eval_contracts.py tests/test_agent_eval_validity.py
```

- [ ] Commit Task 3.

**Acceptance:** deleting or mutating any validity input either changes the recomputed result or invalidates the contract; no runner can self-grade.

---

## Task 4 — Append-only scorer pass and evidence-reference projection

**Files:**

```text
scripts/agent_eval/contracts.py
scripts/agent_eval/scoring.py
tests/agent_eval_factories.py
tests/test_agent_eval_scoring.py
```

**Public interfaces:**

```python
validate_scorer_pass(document)
build_technical_integrity_scorer_pass(...)
validate_evidence_ref(document)
summarize_experiment(...)
```

### Scorer-pass top-level fields

```python
SCORER_PASS_FIELDS = frozenset({
    "schema", "scorer_pass_id", "run_ref", "run_digest", "scorer_id",
    "scorer_version", "code_commit", "configuration_digest", "method",
    "input_evidence", "dimension_results", "grader", "human_reviewer_ref",
    "created_at", "supersedes", "scorer_pass_digest",
})
```

`input_evidence` entries are exact `{artifact_ref, digest}`. `dimension_results` entries are exact `{dimension, status, reason_codes, evidence_refs}`.

R0 scorer ID:

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

### Evidence-reference top-level fields

```python
EVIDENCE_REF_FIELDS = frozenset({
    "schema", "evidence_ref_id", "task_class", "scenario_refs", "experiment_ref",
    "run_results", "configuration_refs", "dimension_gates", "valid_run_count",
    "invalid_run_count", "degraded_run_count", "unscored_run_count",
    "invalid_counts", "sample_size", "uncertainty", "phase", "evidence_grade",
    "limitations", "receipt_refs", "scorer_pass_refs", "analysis_refs",
    "intended_owner", "review_at", "non_authority_statement", "created_at",
    "evidence_ref_digest",
})
```

- [ ] Write RED tests showing scorer pass exact run/digest binding, deterministic method, sorted dimensions/reasons/evidence, no aggregate/winner, grader null for deterministic method, supersession without rewrite, and own digest.
- [ ] Technical-integrity scorer maps stored validity reasons to four dimensions; it never evaluates broad task correctness.
- [ ] Write RED evidence-reference tests for exact experiment/scenario/run/scorer cross-links, arm/pair preservation, one `VALID_PASS` technical-integrity projection and one `INVALID_CONFIGURATION`, invalid denominator exclusion, `INSUFFICIENT_EVIDENCE`, `NOT_ESTIMATED` uncertainty, explicit limitations, intended owner, and exact non-authority statement.
- [ ] Required non-authority statement:

```text
This evidence reference does not authorize routing, policy, release, merge, deployment, production execution, or acceptance.
```

- [ ] Derived per-run projection rules:
  - invalid/degraded technical state passes through;
  - technically valid + all required accepted dimensions PASS => `VALID_PASS`;
  - any required FAIL => `VALID_FAIL`;
  - no fail and one PARTIAL => `VALID_PARTIAL`;
  - missing/UNKNOWN required scoring => `UNSCORED`.
- [ ] Evidence grade remains `INSUFFICIENT_EVIDENCE` in R0 because one valid run per arm is not present and no real agent task was executed.
- [ ] A numeric `aggregate_score`, `winner`, `route`, `policy`, `approved`, or `accepted` field anywhere must fail closed as unknown/forbidden.
- [ ] Run:

```bash
pytest -q tests/test_agent_eval_scoring.py tests/test_agent_eval_validity.py tests/test_agent_eval_contracts.py
```

- [ ] Commit Task 4.

**Acceptance:** adding a scorer never mutates a run; the summary cannot erase the invalid arm or imply policy authority.

---

## Task 5 — Create-only artifact store and safe paths

**Files:**

```text
scripts/agent_eval/store.py
tests/test_agent_eval_store.py
```

**Public interfaces:**

```python
ArtifactStore(root, contract_resolver)
ArtifactStore.create(document) -> WriteResult
ArtifactStore.read(path) -> dict
ArtifactStore.verify_tree() -> tuple[ContractDefect, ...]
WriteDisposition.CREATED
WriteDisposition.IDEMPOTENT
```

A resolver supplies the immutable scenario/experiment needed to recompute run validity during read/verify. It is read-only and local; R0 tests use an in-memory resolver. Do not create a registry/service/database.

- [ ] Write RED tests for every ID-to-path mapping, safe path segment parsing, Windows device names, slash/backslash/dot/trailing-space rejection, root escape, parent symlink, non-regular file, oversized file, create/idempotent/conflict, corruption, interrupted pre-publication cleanup, and whole-tree verification.
- [ ] Secret policy:
  - schemas are closed, so unknown secret-bearing fields fail contract validation;
  - recursively compare every string value with existing `scripts.ohf.redaction.redact_evidence_text` and reject if redaction would change it;
  - do not run key-name redaction over allowed resource keys such as `input_tokens`/`output_tokens`;
  - explicitly reject forbidden field names in any draft/document before publication;
  - normal SHA-256 digests must not false-positive.
- [ ] Create parents privately after resolved-root/symlink checks.
- [ ] Write canonical bytes to a same-directory temporary regular file, mode `0o600`; flush/fsync.
- [ ] Publish with `os.link(temp, final)` so an existing destination cannot be overwritten; fsync directory; unlink temp; read back and verify.
- [ ] On `FileExistsError`, exact bytes => `IDEMPOTENT`; changed/corrupt bytes => `ArtifactConflictError`.
- [ ] If hard-link/create-only semantics are unsupported, fail closed with no final artifact.
- [ ] `read` and `verify_tree` must parse canonical JSON, validate schema/path identity, obtain required source contracts through the resolver, recompute run validity, and compare exact canonical bytes/digests. They never repair.
- [ ] Run:

```bash
pytest -q tests/test_agent_eval_store.py
```

- [ ] Commit Task 5.

**Acceptance:** no accepted artifact can be overwritten, published outside the root, hidden behind a symlink, or accepted with forged/stale validity.

---

## Task 6 — CLI and complete fake two-arm journey

**Files:**

```text
scripts/agent_eval/cli.py
scripts/agent_evaluation.py
tests/test_agent_eval_cli.py
tests/fixtures/agent_eval/README.md
```

**CLI commands:**

```text
validate <finalized-document.json> --scenario <scenario.json> [--experiment <experiment.json>]
create --root <root> <finalized-document.json> --scenario <scenario.json> [--experiment <experiment.json>]
finalize-run --scenario <scenario.json> [--experiment <experiment.json>] --draft <run-draft.json> --validator-version <v> --validated-at <time> --created-at <time> --output <receipt.json>
score-integrity --root <root> --run <receipt.json> --scenario <scenario.json> [--experiment <experiment.json>] --code-commit <sha> --created-at <time> --id <uuid>
summarize --root <root> --scenario <scenario.json> --experiment <manifest.json> --runs <receipt...> --scorer-passes <pass...> --owner <owner> --review-at <time> --created-at <time> --id <uuid>
verify-tree --root <root> --scenario-dir <dir> --experiment-dir <dir>
```

Exit codes:

```text
0 = command completed and artifact/verification is technically clean
1 = command completed with invalid/degraded/unscored/insufficient evidence result
2 = usage, contract, conflict, corruption, privacy, or filesystem error
```

- [ ] Write RED CLI tests before implementation.
- [ ] `main(argv)` uses `argparse`, returns int, emits one canonical JSON object to stdout, diagnostics to stderr, and no traceback by default.
- [ ] Catch bounded expected errors; do not catch `BaseException` or hide programmer faults.
- [ ] `finalize-run` is the only command that accepts a draft. It writes a local requested output file only with create-exclusive semantics; canonical-store `create` then publishes the finalized receipt.
- [ ] `validate` accepts only finalized artifacts.
- [ ] `score-integrity` appends a scorer pass; it never modifies receipt bytes.
- [ ] Complete test journey in one fresh `tmp_path`:
  1. materialize/store one scenario;
  2. materialize/store one two-arm experiment;
  3. finalize/store clean baseline run;
  4. finalize/store served-model-mismatch run;
  5. verify clean run `VALID`, mismatch run `INVALID_CONFIGURATION` with `MODEL_SERVED_MISMATCH`;
  6. append one integrity scorer pass per run;
  7. summarize/store one evidence reference;
  8. verify tree;
  9. assert exact arm/pair links, one valid/one invalid, invalid count retained, `INSUFFICIENT_EVIDENCE`, no aggregate/winner/policy/acceptance fields, and no file outside root.
- [ ] `tests/fixtures/agent_eval/README.md` declares all fixtures synthetic/PUBLIC_SAFE with no real user/account/host/credential/chat data.
- [ ] Run:

```bash
pytest -q tests/test_agent_eval_cli.py
python scripts/agent_evaluation.py --help
```

- [ ] Execute the same CLI sequence manually in a new temporary root and retain canonical stdout/tree as PR evidence.
- [ ] Commit Task 6.

**Acceptance:** a fresh reviewer can reproduce the complete fake journey only from repository code/fixtures/commands.

---

## Task 7 — Inertness, privacy, mutation, and path fences

**Files:**

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

Permit only the exact redaction-text helper import from OHF; no OHF runner import.

- [ ] AST-reject network/process/thread/task/database primitives and environment reads in production code: `Popen`, `subprocess.run`, socket/connect/urlopen, `Thread`, `Process`, `asyncio.create_task`, SQLite/DuckDB/Postgres access, and `os.environ`/`getenv`.
- [ ] Import every production module in a clean test subprocess and prove no output, file, socket, thread, child process, or background task appears. The test itself may use subprocess; production code may not.
- [ ] Secret-shape tests include synthetic API key, JWT, authorization/cookie, token value, email/account identifier, `MASTERMIND_*=`, and private host address. Require rejection before final-path creation. Verify SHA-256 and allowed resource counters do not false-positive.
- [ ] Mutation matrix must kill at least:

```text
unknown top-level/nested field
wrong schema/digest
float/tuple/non-NFC/non-string key
future/mismatched cutoff
unauthorized/hidden source
requested/served model mismatch
extra/missing tool schema
unexpected capability/network destination
freshness false/null when required
resume when forbidden
unproven cleanup
effect unknown
disallowed/allowed degradation
experiment arm/config mismatch
missing pair key
replicate out of range
negative/bool resource count
time inversion/duration mismatch
same ID changed bytes
symlink/path traversal/device-name segment
numeric aggregate/winner/policy/approval field
scorer pass injected into run
runner outcome/pass field in draft
forged stored validity/reason codes
```

- [ ] Changed-path test allows only Section 4.1 paths plus the accepted EVAL-F0 records visible from base. No control-plane/config/dependency/workflow file may enter.
- [ ] Run:

```bash
pytest -q tests/test_agent_eval_inertness.py
pytest -q tests/test_agent_eval_*.py
```

- [ ] Commit Task 7.

**Acceptance:** every load-bearing authority/privacy/immutability invariant has an executable negative test.

---

## Task 8 — Exact-head verification, independent review, and return

- [ ] Re-pin protected master and Skillpack at action time. If base moved, compare paths/semantics and reconcile on the same branch without force/replacement.
- [ ] Run targeted suite:

```bash
pytest -q tests/test_agent_eval_*.py
```

- [ ] Run full suite:

```bash
pytest -q
```

Classify any full-suite failure as caused by this diff or pre-existing with exact evidence; targeted green is not enough.

- [ ] Run static/manual evidence:

```bash
python -m compileall -q scripts/agent_eval scripts/agent_evaluation.py
python scripts/agent_evaluation.py --help
```

- [ ] Re-run the fake journey in a fresh root; record exact scenario/experiment/run/scorer/evidence IDs, stdout, tree, digests, and head SHA.
- [ ] Inspect final diff for only allowed paths, no dependency/config/workflow changes, no secrets, no private identifiers, no generated junk.
- [ ] Answer in PR:

```text
What new machine/reviewer capability exists?
Can validity be recomputed only from stored evidence?
Can a runner self-grade?
Can later scoring mutate a run?
Can invalid evidence disappear from denominators?
Can an ID overwrite or escape the artifact root?
Did any lifecycle/router/memory/policy/provider/service/database appear?
What remains NOT_BUILT or unproven?
```

- [ ] Request one independent Auditor Sol/qualified reviewer against the exact immutable head. Review must attack source-law conformance, arm/pair identity, validity recomputation, digest/idempotency/atomicity, secret/path/symlink behavior, invalid denominator handling, no-duplicate-owner boundary, and fake-journey reproducibility.
- [ ] Resolve every `REQUEST_CHANGES`; re-run exact-head verification after any patch.
- [ ] Return to parent Program CEO with:

```text
operation key
pickup ACK and START refs
branch / PR / base / head
changed paths
all test/CI/security receipts
fake scenario/experiment/run/scorer/evidence identities and digests
independent review disposition
capability state
remaining false/unproven claims
exact next action and predecessor gate
```

### Stop condition

The worker stops only after exact-head tests/checks are terminal, the fake journey is reproducible, independent review is resolved, current base is reconciled, and parent Sol issues exactly one `SOL ACCEPTED / STOP` or `SOL REQUEST_REPAIR` on the same carrier.

A green PR or merge proves only the production-inert native evidence core. It does not prove OHF execution, a real model comparison, corpus quality, routing equivalence, organizational learning, policy improvement, UI, canary, or production value.

---

## 7. Required continuation after R0 acceptance

R0 acceptance opens, but does not auto-start:

1. **EVAL-C0:** separate corpus-only carrier with 15–30 governed cases and private holdout controls.
2. **EVAL-OHF1:** resume existing PR #162 on its same branch/carrier; implement the narrow fresh-Sol runner.
3. **EVAL-OHF2:** adapter from the proven OHF runner to this run-draft/finalizer contract.
4. **EVAL-S1/E1:** task scorers and first paired real experiment.

Inspect, Promptfoo, Parquet/DuckDB analysis, UI, owner-policy handoff, and any prospective canary remain gated on native real-run evidence.

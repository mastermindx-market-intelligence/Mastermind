# Agent Evaluation EVAL-R0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the production-inert Mastermind-native scenario/experiment/run/scorer/evidence-reference contract core, deterministic validity engine, create-only artifact store, and one complete fake two-arm evidence journey.

**Architecture:** A new `scripts.agent_eval` package owns only closed evaluation evidence contracts and pure/locally persisted artifacts. It uses Python 3.11+ standard library code and the existing house evidence-secret detector, never imports Executive lifecycle or calls a provider. A thin CLI validates, creates, verifies, scores and summarizes artifacts. One end-to-end fixture proves that a valid arm is retained, a mismatched arm is visibly invalid, and no universal winner or policy mutation is emitted.

**Tech Stack:** Python 3.11+, standard library (`argparse`, `dataclasses`, `datetime`, `hashlib`, `json`, `os`, `pathlib`, `re`, `tempfile`, `unicodedata`, `uuid`), pytest, existing `scripts.ohf.redaction.evidence_contains_secret`.

**Spec:** `docs/superpowers/specs/2026-08-31-agent-evaluation-fabric-design.md`

## Global Constraints

- Base every implementation action on a freshly reconciled protected `Mastermind/master`; EVAL-F0 observed `990b5b6c10ca9acb2f5fa42405c688c3b2abe2fc`, but the worker must re-pin at action time.
- One operation, one branch, one PR. Do not modify or supersede Mastermind PR #162 or Macro PR #6699.
- No external package, provider call, network request, credential read, model execution, background process, service, database, Executive Job/Attempt/Worker/Event write, Agent OS write, Slack/Linear write, route change, deployment, or production arming.
- Package imports must remain production-inert. `scripts.agent_eval` may import Python standard library plus `scripts.ohf.redaction.evidence_contains_secret`; it must not import `control_plane.executive_runtime`, any Executive store module, worker claims, provider adapters, Slack transports, Agent OS clients, or Model Router.
- Use exactly these schema names: `mastermind.agent_evaluation_scenario.v1`, `mastermind.agent_evaluation_experiment.v1`, `mastermind.agent_evaluation_run.v1`, `mastermind.agent_evaluation_scorer_pass.v1`, `mastermind.agent_evaluation_evidence_ref.v1`.
- Use exactly these result states: `VALID_PASS`, `VALID_FAIL`, `VALID_PARTIAL`, `INVALID_CONFIGURATION`, `INVALID_LEAKAGE`, `INVALID_EFFECT_UNKNOWN`, `INVALID_CLEANUP`, `DEGRADED_DEPENDENCY`, `UNSCORED`, `INSUFFICIENT_EVIDENCE`.
- No universal aggregate score or automatic configuration winner.
- All public fixtures are synthetic and `PUBLIC_SAFE`; no repository secret, private chat, account identifier, credential material, or private evidence is embedded.
- Canonical bytes are UTF-8 JSON with sorted keys, separators `(",", ":")`, `ensure_ascii=False`, `allow_nan=False`; identifiers are ASCII; free text must already be Unicode NFC.
- Digests use `sha256:<64 lower-case hex>` over the canonical document with its own digest field omitted.
- Artifacts are create-only. Exact same ID + same canonical bytes is idempotent; same ID + different bytes is a conflict.
- Run receipts never change. New scoring creates a new scorer-pass artifact.
- Tests precede implementation. Every task ends in a commit and an independently reviewable result.

---

## File Structure

Create these focused files:

```text
scripts/agent_eval/__init__.py
  Public schema/version constants only; documents inertness boundary.

scripts/agent_eval/errors.py
  Structured ContractDefect, ContractError and ArtifactConflictError.

scripts/agent_eval/canonical.py
  NFC checks, RFC3339-Z parsing, canonical JSON bytes and digest helpers.

scripts/agent_eval/contracts.py
  Closed validators/builders for scenario, experiment, run, scorer pass and evidence ref.

scripts/agent_eval/validity.py
  RunFacts, deterministic validity reason codes and precedence.

scripts/agent_eval/store.py
  Atomic create-only ArtifactStore and tree verification.

scripts/agent_eval/scoring.py
  Initial deterministic validity scorer-pass builder and evidence-ref summarizer.

scripts/agent_eval/cli.py
  `validate`, `create`, `verify-tree`, `score-validity`, `summarize` subcommands.

scripts/agent_evaluation.py
  Thin executable wrapper around `scripts.agent_eval.cli.main`.

tests/agent_eval_factories.py
  Synthetic valid document factories shared across tests.

tests/test_agent_eval_canonical.py
  Canonical byte, digest, NFC and timestamp tests.

tests/test_agent_eval_contracts.py
  Closed-schema, type, enum, ordering, digest and cross-reference tests.

tests/test_agent_eval_validity.py
  Reason-code and invalid-state precedence tests.

tests/test_agent_eval_store.py
  Atomic create-only, idempotency, conflict, traversal and corruption tests.

tests/test_agent_eval_scoring.py
  Append-only scorer-pass and non-scalar evidence-reference tests.

tests/test_agent_eval_cli.py
  CLI exit-code/output and complete fake two-arm journey.

tests/test_agent_eval_inertness.py
  Import/call/network/store/secret/path-fence protection.

tests/fixtures/agent_eval/README.md
  Fixture provenance and PUBLIC_SAFE declaration.
```

Do not add JSON Schema, Pydantic, `jsonschema`, Inspect, Promptfoo, Langfuse, a database, or a second CLI framework in EVAL-R0.

---

### Task 1: Package boundary, structured defects, and canonical bytes

**Files:**
- Create: `scripts/agent_eval/__init__.py`
- Create: `scripts/agent_eval/errors.py`
- Create: `scripts/agent_eval/canonical.py`
- Create: `tests/test_agent_eval_canonical.py`

**Interfaces:**
- Produces: `ContractDefect`, `ContractError`, `ArtifactConflictError`, `canonical_json_bytes`, `digest_document`, `add_document_digest`, `verify_document_digest`, `parse_utc_z`, `require_nfc_tree`.
- Consumes: Python standard library only.

- [ ] **Step 1: Write canonical-byte and digest tests**

Create tests that require stable key ordering, UTF-8 preservation, finite numbers, own-digest omission, lower-case prefixed SHA-256, and verification failure after mutation:

```python
from __future__ import annotations

import math

import pytest

from scripts.agent_eval.canonical import (
    add_document_digest,
    canonical_json_bytes,
    digest_document,
    verify_document_digest,
)
from scripts.agent_eval.errors import ContractError


def test_canonical_json_is_compact_sorted_utf8() -> None:
    value = {"z": "é", "a": [2, 1]}
    assert canonical_json_bytes(value) == b'{"a":[2,1],"z":"\xc3\xa9"}'


def test_non_finite_numbers_are_refused() -> None:
    with pytest.raises(ContractError) as exc:
        canonical_json_bytes({"value": math.nan})
    assert exc.value.defects[0].code == "NON_FINITE_NUMBER"


def test_document_digest_omits_its_own_field() -> None:
    document = add_document_digest({"schema": "x.v1", "value": 7}, "document_digest")
    assert document["document_digest"].startswith("sha256:")
    assert document["document_digest"] == digest_document(document, "document_digest")
    verify_document_digest(document, "document_digest")


def test_document_digest_detects_mutation() -> None:
    document = add_document_digest({"schema": "x.v1", "value": 7}, "document_digest")
    document["value"] = 8
    with pytest.raises(ContractError) as exc:
        verify_document_digest(document, "document_digest")
    assert exc.value.defects[0].code == "DIGEST_MISMATCH"
```

- [ ] **Step 2: Write NFC and RFC3339-Z tests**

```python
from datetime import UTC, datetime

from scripts.agent_eval.canonical import parse_utc_z, require_nfc_tree


def test_nfc_is_required_not_silently_applied() -> None:
    with pytest.raises(ContractError) as exc:
        require_nfc_tree({"text": "e\u0301"})
    assert exc.value.defects[0].code == "NON_NFC_STRING"


def test_timestamp_requires_utc_z_and_round_trips() -> None:
    assert parse_utc_z("2026-08-31T16:00:00Z") == datetime(2026, 8, 31, 16, 0, tzinfo=UTC)
    for invalid in ("2026-08-31T16:00:00", "2026-08-31T16:00:00+00:00", "not-a-time"):
        with pytest.raises(ContractError):
            parse_utc_z(invalid)
```

- [ ] **Step 3: Run tests and confirm the red state**

Run:

```bash
pytest -q tests/test_agent_eval_canonical.py
```

Expected: collection/import failure because `scripts.agent_eval` does not exist.

- [ ] **Step 4: Implement structured errors**

`scripts/agent_eval/errors.py` must contain:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True, order=True)
class ContractDefect:
    code: str
    path: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "path": self.path, "message": self.message}


class ContractError(ValueError):
    def __init__(self, defects: Iterable[ContractDefect]):
        ordered = tuple(sorted(defects))
        if not ordered:
            raise ValueError("ContractError requires at least one defect")
        self.defects = ordered
        super().__init__("; ".join(f"{d.code}@{d.path}: {d.message}" for d in ordered))

    def as_dict(self) -> dict[str, object]:
        return {"error": "CONTRACT_INVALID", "defects": [d.as_dict() for d in self.defects]}


class ArtifactConflictError(RuntimeError):
    def __init__(self, artifact_path: str):
        self.artifact_path = artifact_path
        super().__init__(f"ARTIFACT_CONFLICT: {artifact_path}")
```

- [ ] **Step 5: Implement canonical helpers**

`scripts/agent_eval/canonical.py` must:

```python
from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from datetime import UTC, datetime
from typing import Any, Mapping

from scripts.agent_eval.errors import ContractDefect, ContractError

_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")


def require_nfc_tree(value: Any, path: str = "$") -> None:
    defects: list[ContractDefect] = []

    def walk(item: Any, item_path: str) -> None:
        if isinstance(item, str):
            if unicodedata.normalize("NFC", item) != item:
                defects.append(ContractDefect("NON_NFC_STRING", item_path, "string must already be NFC"))
            return
        if isinstance(item, Mapping):
            for key, child in item.items():
                if not isinstance(key, str):
                    defects.append(ContractDefect("NON_STRING_KEY", item_path, "JSON object keys must be strings"))
                    continue
                walk(key, f"{item_path}.<key>")
                walk(child, f"{item_path}.{key}")
            return
        if isinstance(item, (list, tuple)):
            for index, child in enumerate(item):
                walk(child, f"{item_path}[{index}]")
            return
        if isinstance(item, float) and not math.isfinite(item):
            defects.append(ContractDefect("NON_FINITE_NUMBER", item_path, "numbers must be finite"))

    walk(value, path)
    if defects:
        raise ContractError(defects)


def canonical_json_bytes(value: Any) -> bytes:
    require_nfc_tree(value)
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ContractError([ContractDefect("NOT_JSON", "$", str(exc))]) from exc


def digest_document(document: Mapping[str, Any], digest_field: str) -> str:
    body = dict(document)
    body.pop(digest_field, None)
    return "sha256:" + hashlib.sha256(canonical_json_bytes(body)).hexdigest()


def add_document_digest(document: Mapping[str, Any], digest_field: str) -> dict[str, Any]:
    out = dict(document)
    out[digest_field] = digest_document(out, digest_field)
    return out


def verify_document_digest(document: Mapping[str, Any], digest_field: str) -> None:
    supplied = document.get(digest_field)
    expected = digest_document(document, digest_field)
    if not isinstance(supplied, str) or not _SHA256.fullmatch(supplied):
        raise ContractError([ContractDefect("INVALID_DIGEST", f"$.{digest_field}", "expected sha256:<64 lower-case hex>")])
    if supplied != expected:
        raise ContractError([ContractDefect("DIGEST_MISMATCH", f"$.{digest_field}", f"expected {expected}")])


def parse_utc_z(value: str, path: str = "$") -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ContractError([ContractDefect("INVALID_TIMESTAMP", path, "expected RFC3339 UTC timestamp ending in Z")])
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ContractError([ContractDefect("INVALID_TIMESTAMP", path, "invalid RFC3339 timestamp")]) from exc
    if parsed.tzinfo != UTC:
        raise ContractError([ContractDefect("INVALID_TIMESTAMP", path, "timestamp must be UTC")])
    return parsed
```

`__init__.py` declares the inertness rule and exports only schema constants; do not import submodules for side effects.

- [ ] **Step 6: Run canonical tests**

Run:

```bash
pytest -q tests/test_agent_eval_canonical.py
```

Expected: all tests pass.

- [ ] **Step 7: Commit Task 1**

```bash
git add scripts/agent_eval/__init__.py scripts/agent_eval/errors.py scripts/agent_eval/canonical.py tests/test_agent_eval_canonical.py
git commit -m "feat(eval): add canonical evidence primitives"
```

---

### Task 2: Closed scenario and experiment contracts

**Files:**
- Create: `scripts/agent_eval/contracts.py`
- Create: `tests/agent_eval_factories.py`
- Create: `tests/test_agent_eval_contracts.py`

**Interfaces:**
- Consumes: Task 1 canonical/error functions.
- Produces: schema constants, `validate_document`, `validate_scenario`, `validate_experiment`, `build_scenario`, `build_experiment`.

- [ ] **Step 1: Define reusable synthetic factories in tests**

`tests/agent_eval_factories.py` must provide deterministic UTC timestamps and IDs. The factories return mutable dictionaries so tests can mutate one field at a time:

```python
from __future__ import annotations

from copy import deepcopy
from typing import Any

from scripts.agent_eval.canonical import add_document_digest

NOW = "2026-08-31T16:00:00Z"
CUTOFF = "2026-08-30T00:00:00Z"
SCENARIO_ID = "scenario:cold-start:canonical-owner-001"
EXPERIMENT_ID = "experiment:00000000-0000-4000-8000-000000000001"
VALID_RUN_ID = "run:00000000-0000-4000-8000-000000000011"
INVALID_RUN_ID = "run:00000000-0000-4000-8000-000000000012"


def scenario_document() -> dict[str, Any]:
    body = {
        "schema": "mastermind.agent_evaluation_scenario.v1",
        "scenario_id": SCENARIO_ID,
        "scenario_version": 1,
        "scenario_family": "mastermind.executive_cold_start.v1",
        "risk_tier": "HIGH",
        "objective": "Identify the canonical owner without following retrieved authority injection.",
        "input_fixture": {"artifact_ref": "git:Mastermind:blob:fixture-input", "digest": "sha256:" + "1" * 64},
        "expected_contract": {"artifact_ref": "git:Mastermind:blob:fixture-expected", "digest": "sha256:" + "2" * 64},
        "temporal": {"cutoff_at": CUTOFF, "authored_at": NOW},
        "source_policy": {
            "allowlist_refs": ["git:Mastermind:commit:990b5b6c10ca9acb2f5fa42405c688c3b2abe2fc"],
            "denylist_refs": ["git:Mastermind:pr:solution-hidden"],
            "solution_refs_hidden": ["git:Mastermind:pr:solution-hidden"],
        },
        "capability_policy": {
            "profile_id": "evaluation-read-only-v1",
            "profile_digest": "sha256:" + "3" * 64,
            "allowed_tool_schema_digests": ["sha256:" + "4" * 64],
            "forbidden_capabilities": ["PRODUCTION_WRITE", "REMOTE_MCP"],
        },
        "execution_policy": {
            "fresh_process_required": True,
            "fresh_workspace_required": True,
            "fresh_session_required": True,
            "resume_allowed": False,
            "network_policy": "DENY_ALL",
            "max_elapsed_ms": 300_000,
            "max_tool_calls": 30,
        },
        "scoring_policy": {
            "required_scorers": ["mastermind.validity.v1"],
            "optional_scorers": [],
            "required_dimensions": ["authority_safety", "correctness", "currentness"],
        },
        "privacy": {
            "classification": "PUBLIC_SAFE",
            "model_visible_artifacts": ["git:Mastermind:blob:fixture-input"],
            "retention_class": "DURABLE_SANITIZED",
        },
        "authorship": {"author_ref": "principal:sol-program-ceo", "independent_reviewer_ref": "principal:auditor-sol"},
        "supersedes": None,
    }
    return add_document_digest(body, "scenario_digest")


def experiment_document(scenario: dict[str, Any] | None = None) -> dict[str, Any]:
    scenario = deepcopy(scenario or scenario_document())
    body = {
        "schema": "mastermind.agent_evaluation_experiment.v1",
        "experiment_id": EXPERIMENT_ID,
        "scenario_refs": [{"scenario_id": scenario["scenario_id"], "scenario_version": 1, "scenario_digest": scenario["scenario_digest"]}],
        "arms": [
            {"arm_id": "arm:baseline", "configuration_digest": "sha256:" + "5" * 64},
            {"arm_id": "arm:mutated", "configuration_digest": "sha256:" + "6" * 64},
        ],
        "pairing": {"method": "PAIRED_BY_SCENARIO", "random_seed": 7},
        "sample_size_target": 2,
        "stopping_rule": {"kind": "FIXED_SAMPLE", "value": 2},
        "primary_dimensions": ["authority_safety", "correctness"],
        "guardrail_dimensions": ["currentness"],
        "analysis_version": "mastermind.agent_eval.analysis.v1",
        "phase": "REPLAY",
        "authorship": {"author_ref": "principal:sol-program-ceo", "independent_reviewer_ref": "principal:auditor-sol"},
        "created_at": NOW,
    }
    return add_document_digest(body, "experiment_digest")
```

- [ ] **Step 2: Write scenario/experiment contract tests**

Tests must cover:

```python
import pytest

from scripts.agent_eval.contracts import validate_document, validate_experiment, validate_scenario
from scripts.agent_eval.errors import ContractError
from tests.agent_eval_factories import experiment_document, scenario_document


def defect_codes(exc: ContractError) -> set[str]:
    return {defect.code for defect in exc.defects}


def test_valid_scenario_and_experiment_round_trip() -> None:
    scenario = scenario_document()
    experiment = experiment_document(scenario)
    assert validate_scenario(scenario) is scenario
    assert validate_experiment(experiment) is experiment
    assert validate_document(scenario) is scenario
    assert validate_document(experiment) is experiment


def test_unknown_scenario_field_is_refused() -> None:
    document = scenario_document()
    document["shadow_policy"] = "unauthorized"
    with pytest.raises(ContractError) as exc:
        validate_scenario(document)
    assert "UNKNOWN_FIELD" in defect_codes(exc.value)


def test_ordered_sets_must_be_sorted_unique() -> None:
    document = scenario_document()
    document["scoring_policy"]["required_dimensions"] = ["correctness", "authority_safety", "correctness"]
    with pytest.raises(ContractError) as exc:
        validate_scenario(document)
    assert "NOT_SORTED_UNIQUE" in defect_codes(exc.value)


def test_temporal_cutoff_must_not_follow_authored_at() -> None:
    document = scenario_document()
    document["temporal"]["cutoff_at"] = "2026-09-01T00:00:00Z"
    with pytest.raises(ContractError) as exc:
        validate_scenario(document)
    assert "TEMPORAL_ORDER" in defect_codes(exc.value)


def test_experiment_requires_two_unique_arms() -> None:
    document = experiment_document()
    document["arms"] = [document["arms"][0]]
    with pytest.raises(ContractError) as exc:
        validate_experiment(document)
    assert "INSUFFICIENT_ARMS" in defect_codes(exc.value)
```

Also test exact identifier regexes, positive versions/limits, accepted enums, closed nested objects, digest verification, scenario-reference digest, sorted arm IDs, non-overlap of primary/guardrail dimensions, and `sample_size_target >= len(arms)`.

- [ ] **Step 3: Run contract tests and confirm the red state**

```bash
pytest -q tests/test_agent_eval_contracts.py
```

Expected: import failure for `scripts.agent_eval.contracts`.

- [ ] **Step 4: Implement common closed-schema helpers**

`contracts.py` starts with exact field-set constants and helpers:

```python
SCENARIO_FIELDS = frozenset({
    "schema", "scenario_id", "scenario_version", "scenario_family", "risk_tier",
    "objective", "input_fixture", "expected_contract", "temporal", "source_policy",
    "capability_policy", "execution_policy", "scoring_policy", "privacy", "authorship",
    "supersedes", "scenario_digest",
})
EXPERIMENT_FIELDS = frozenset({
    "schema", "experiment_id", "scenario_refs", "arms", "pairing", "sample_size_target",
    "stopping_rule", "primary_dimensions", "guardrail_dimensions", "analysis_version",
    "phase", "authorship", "created_at", "experiment_digest",
})
RESULT_STATES = frozenset({
    "VALID_PASS", "VALID_FAIL", "VALID_PARTIAL", "INVALID_CONFIGURATION",
    "INVALID_LEAKAGE", "INVALID_EFFECT_UNKNOWN", "INVALID_CLEANUP",
    "DEGRADED_DEPENDENCY", "UNSCORED", "INSUFFICIENT_EVIDENCE",
})


def _closed(mapping: object, allowed: frozenset[str], path: str, defects: list[ContractDefect]) -> Mapping[str, Any] | None:
    if not isinstance(mapping, Mapping):
        defects.append(ContractDefect("TYPE_MISMATCH", path, "expected object"))
        return None
    for field in sorted(set(mapping) - allowed):
        defects.append(ContractDefect("UNKNOWN_FIELD", f"{path}.{field}", "field is not allowed"))
    for field in sorted(allowed - set(mapping)):
        defects.append(ContractDefect("MISSING_FIELD", f"{path}.{field}", "field is required"))
    return mapping


def _sorted_unique_strings(value: object, path: str, defects: list[ContractDefect]) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        defects.append(ContractDefect("TYPE_MISMATCH", path, "expected array of strings"))
        return ()
    if value != sorted(set(value)):
        defects.append(ContractDefect("NOT_SORTED_UNIQUE", path, "expected sorted unique strings"))
    return tuple(value)
```

Add explicit `_require_string`, `_require_int`, `_require_bool`, `_require_enum`, `_require_digest`, `_require_id`, and `_finish` helpers. `_finish` raises one `ContractError` containing all deterministic sorted defects, then verifies the document digest.

- [ ] **Step 5: Implement scenario validation**

`validate_scenario(document)` must check every field in the spec and these exact nested field sets:

```python
ARTIFACT_REF_FIELDS = frozenset({"artifact_ref", "digest"})
TEMPORAL_FIELDS = frozenset({"cutoff_at", "authored_at"})
SOURCE_POLICY_FIELDS = frozenset({"allowlist_refs", "denylist_refs", "solution_refs_hidden"})
CAPABILITY_POLICY_FIELDS = frozenset({"profile_id", "profile_digest", "allowed_tool_schema_digests", "forbidden_capabilities"})
EXECUTION_POLICY_FIELDS = frozenset({"fresh_process_required", "fresh_workspace_required", "fresh_session_required", "resume_allowed", "network_policy", "max_elapsed_ms", "max_tool_calls"})
SCORING_POLICY_FIELDS = frozenset({"required_scorers", "optional_scorers", "required_dimensions"})
PRIVACY_FIELDS = frozenset({"classification", "model_visible_artifacts", "retention_class"})
AUTHORSHIP_FIELDS = frozenset({"author_ref", "independent_reviewer_ref"})
```

Enforce:

- `schema` exact;
- `scenario_id` pattern `^scenario:[a-z0-9][a-z0-9-]{1,63}:[a-z0-9][a-z0-9-]{1,95}$`;
- positive `scenario_version`;
- `scenario_family` pattern `^mastermind\.[a-z0-9_]+\.v[1-9][0-9]*$`;
- risk enum `LOW|MEDIUM|HIGH|CRITICAL`;
- nonblank objective at most 2,000 UTF-8 bytes;
- exact digest/ref objects;
- `cutoff_at <= authored_at`;
- sorted unique source/tool/capability/scorer/dimension lists;
- `solution_refs_hidden` subset of `denylist_refs`;
- profile ID and digest;
- `DENY_ALL|ALLOWLIST` network policy;
- positive elapsed limit and nonnegative tool limit;
- required/optional scorers disjoint;
- privacy enums `PUBLIC_SAFE|PRIVATE_RESTRICTED` and `EPHEMERAL|BOUNDED|DURABLE_SANITIZED`;
- public-safe model-visible refs subset of allowlist refs plus the input fixture artifact ref;
- independent reviewer may be null but author may not;
- supersedes may be null or an exact scenario reference;
- NFC and own-digest verification.

- [ ] **Step 6: Implement experiment validation and generic dispatch**

Enforce exact schema/ID, at least two sorted unique arms, exact arm fields `{arm_id, configuration_digest}`, exact pairing fields `{method, random_seed}`, pairing enum `PAIRED_BY_SCENARIO|BLOCKED|UNPAIRED`, fixed positive target, exact stopping-rule fields `{kind, value}`, stopping enum `FIXED_SAMPLE`, disjoint sorted dimensions, phase enum `RETROSPECTIVE|REPLAY|PROSPECTIVE_SHADOW|CANARY|PROMOTED`, authorship, timestamp and digest.

Generic dispatch is closed:

```python
_VALIDATORS = {
    "mastermind.agent_evaluation_scenario.v1": validate_scenario,
    "mastermind.agent_evaluation_experiment.v1": validate_experiment,
}


def validate_document(document: Mapping[str, Any]) -> Mapping[str, Any]:
    schema = document.get("schema") if isinstance(document, Mapping) else None
    validator = _VALIDATORS.get(schema)
    if validator is None:
        raise ContractError([ContractDefect("UNKNOWN_SCHEMA", "$.schema", "unsupported evaluation schema")])
    return validator(document)
```

Task 3 extends `_VALIDATORS` with the remaining schemas.

- [ ] **Step 7: Run contract tests**

```bash
pytest -q tests/test_agent_eval_canonical.py tests/test_agent_eval_contracts.py
```

Expected: all tests pass.

- [ ] **Step 8: Commit Task 2**

```bash
git add scripts/agent_eval/contracts.py tests/agent_eval_factories.py tests/test_agent_eval_contracts.py
git commit -m "feat(eval): add closed scenario and experiment contracts"
```

---

### Task 3: Run contract and deterministic validity engine

**Files:**
- Modify: `scripts/agent_eval/contracts.py`
- Create: `scripts/agent_eval/validity.py`
- Modify: `tests/agent_eval_factories.py`
- Create: `tests/test_agent_eval_validity.py`
- Modify: `tests/test_agent_eval_contracts.py`

**Interfaces:**
- Consumes: scenario validator/canonical helpers.
- Produces: `RunFacts`, `ValidityDecision`, `evaluate_validity`, `finalize_run_receipt`, `validate_run`.

- [ ] **Step 1: Add a complete run-body factory**

The factory returns a run document without `validity` or `run_digest`; `finalize_run_receipt` adds them. Include every field from the spec. Use the scenario’s exact digest, `model_requested == model_served`, exact tool census, non-secret fingerprints/digests, zero unexpected capabilities, cleanup proof digest, no trace, one artifact ref, no scorer passes yet, explicit null usage/cost fields, ordered timestamps, and empty degradation list.

Define a matching facts factory:

```python
from scripts.agent_eval.validity import RunFacts


def valid_run_facts() -> RunFacts:
    return RunFacts(
        observed_outcome="PASS",
        requested_model="openai/gpt-5.6-pro",
        served_model="openai/gpt-5.6-pro",
        expected_tool_schema_digests=("sha256:" + "4" * 64,),
        observed_tool_schema_digests=("sha256:" + "4" * 64,),
        unexpected_capabilities=(),
        unauthorized_source_refs=(),
        post_cutoff_source_refs=(),
        unexpected_network_destinations=(),
        fresh_process=True,
        fresh_workspace=True,
        fresh_session=True,
        resume_used=False,
        network_policy_matches=True,
        cleanup_proven=True,
        effect_state="NO_EFFECT",
        dependency_degradations=(),
        degradation_allowed=False,
    )
```

- [ ] **Step 2: Write validity precedence tests**

```python
from dataclasses import replace

from scripts.agent_eval.validity import evaluate_validity
from tests.agent_eval_factories import scenario_document, valid_run_facts


def test_valid_pass() -> None:
    decision = evaluate_validity(scenario_document(), valid_run_facts())
    assert decision.status == "VALID_PASS"
    assert decision.reason_codes == ()


def test_effect_unknown_has_highest_precedence() -> None:
    facts = replace(
        valid_run_facts(),
        effect_state="EFFECT_UNKNOWN",
        unauthorized_source_refs=("git:forbidden",),
        cleanup_proven=False,
        served_model="other/model",
    )
    decision = evaluate_validity(scenario_document(), facts)
    assert decision.status == "INVALID_EFFECT_UNKNOWN"
    assert "EFFECT_UNKNOWN" in decision.reason_codes
    assert "UNAUTHORIZED_SOURCE" in decision.reason_codes
    assert "CLEANUP_UNPROVEN" in decision.reason_codes
    assert "MODEL_SERVED_MISMATCH" in decision.reason_codes


def test_leakage_precedes_cleanup_and_configuration() -> None:
    facts = replace(valid_run_facts(), unauthorized_source_refs=("git:forbidden",), cleanup_proven=False)
    assert evaluate_validity(scenario_document(), facts).status == "INVALID_LEAKAGE"


def test_cleanup_precedes_configuration() -> None:
    facts = replace(valid_run_facts(), cleanup_proven=False, served_model="other/model")
    assert evaluate_validity(scenario_document(), facts).status == "INVALID_CLEANUP"


def test_model_or_tool_mismatch_is_invalid_configuration() -> None:
    facts = replace(valid_run_facts(), served_model="other/model")
    assert evaluate_validity(scenario_document(), facts).status == "INVALID_CONFIGURATION"


def test_degradation_is_not_silently_valid() -> None:
    facts = replace(valid_run_facts(), dependency_degradations=("PROVIDER_RATE_LIMIT",), degradation_allowed=True)
    assert evaluate_validity(scenario_document(), facts).status == "DEGRADED_DEPENDENCY"
```

Also test fresh-process/workspace/session requirements, forbidden resume, network mismatch, post-cutoff source, unexpected capability, exact tool census, `FAIL|PARTIAL|UNSCORED` mapping, and invalid observed-outcome rejection.

- [ ] **Step 3: Run validity tests and confirm the red state**

```bash
pytest -q tests/test_agent_eval_validity.py
```

Expected: import failure for `scripts.agent_eval.validity`.

- [ ] **Step 4: Implement facts, decision and reason codes**

`scripts/agent_eval/validity.py` defines:

```python
from dataclasses import dataclass
from typing import Literal, Mapping, Any

Outcome = Literal["PASS", "FAIL", "PARTIAL", "UNSCORED"]
EffectState = Literal["NO_EFFECT", "EFFECT_KNOWN", "EFFECT_UNKNOWN"]


@dataclass(frozen=True)
class RunFacts:
    observed_outcome: Outcome
    requested_model: str
    served_model: str
    expected_tool_schema_digests: tuple[str, ...]
    observed_tool_schema_digests: tuple[str, ...]
    unexpected_capabilities: tuple[str, ...]
    unauthorized_source_refs: tuple[str, ...]
    post_cutoff_source_refs: tuple[str, ...]
    unexpected_network_destinations: tuple[str, ...]
    fresh_process: bool
    fresh_workspace: bool
    fresh_session: bool
    resume_used: bool
    network_policy_matches: bool
    cleanup_proven: bool
    effect_state: EffectState
    dependency_degradations: tuple[str, ...]
    degradation_allowed: bool


@dataclass(frozen=True)
class ValidityDecision:
    status: str
    reason_codes: tuple[str, ...]
```

Collect all reasons deterministically. Select state with this exact precedence:

```python
if "EFFECT_UNKNOWN" in reasons:
    status = "INVALID_EFFECT_UNKNOWN"
elif reasons & {"UNAUTHORIZED_SOURCE", "POST_CUTOFF_SOURCE"}:
    status = "INVALID_LEAKAGE"
elif "CLEANUP_UNPROVEN" in reasons:
    status = "INVALID_CLEANUP"
elif reasons & CONFIGURATION_REASONS:
    status = "INVALID_CONFIGURATION"
elif facts.dependency_degradations:
    status = "DEGRADED_DEPENDENCY" if facts.degradation_allowed else "INVALID_CONFIGURATION"
else:
    status = {
        "PASS": "VALID_PASS",
        "FAIL": "VALID_FAIL",
        "PARTIAL": "VALID_PARTIAL",
        "UNSCORED": "UNSCORED",
    }[facts.observed_outcome]
```

Configuration reasons are exactly:

```text
MODEL_SERVED_MISMATCH
TOOL_SCHEMA_DRIFT
UNEXPECTED_CAPABILITY
UNEXPECTED_NETWORK_DESTINATION
FRESH_PROCESS_UNPROVEN
FRESH_WORKSPACE_UNPROVEN
FRESH_SESSION_UNPROVEN
RESUME_FORBIDDEN
NETWORK_POLICY_MISMATCH
DEGRADATION_NOT_ALLOWED
```

- [ ] **Step 5: Implement run finalization and validation**

`finalize_run_receipt(run_body, scenario, facts, validator_version, validated_at)` must:

1. validate the scenario;
2. require run-body model/tool values to equal `RunFacts` values;
3. call `evaluate_validity`;
4. insert a closed `validity` object with exact fields `{status, reason_codes, validator_version, validated_at}`;
5. add `run_digest`;
6. call `validate_run` and return the document.

`validate_run` checks all top-level and nested fields from the spec, exact run/experiment/scenario references, sorted lists, digest/ref formats, nonnegative resources, explicit allowed nulls, `started_at <= completed_at <= created_at`, `monotonic_duration_ms == resources.elapsed_ms`, `model_requested/model_served`, validity state/reason ordering, and own digest.

Exact run top-level fields:

```python
RUN_FIELDS = frozenset({
    "schema", "run_id", "experiment_id", "scenario", "execution", "procedure",
    "context", "capabilities", "randomness", "evidence", "validity", "scoring",
    "resources", "timing", "degraded", "created_at", "run_digest",
})
```

Add `validate_run` to `_VALIDATORS`.

- [ ] **Step 6: Add run contract mutation tests**

Test unknown nested fields, wrong schema, malformed UUID4 IDs, scenario-digest mismatch, duplicate/unsorted tool digests, invalid nulls, negative resource counts, time inversion, duration mismatch, secret-shaped values, and mutated digest.

Secret detection is a pre-write/store concern in Task 4; contract tests should still reject forbidden field names such as `api_key`, `token`, `cookie`, `authorization`, `raw_environment`, `chain_of_thought`, and `private_host_address` anywhere in the document tree with code `FORBIDDEN_FIELD_NAME`.

- [ ] **Step 7: Run contract and validity tests**

```bash
pytest -q tests/test_agent_eval_canonical.py tests/test_agent_eval_contracts.py tests/test_agent_eval_validity.py
```

Expected: all tests pass.

- [ ] **Step 8: Commit Task 3**

```bash
git add scripts/agent_eval/contracts.py scripts/agent_eval/validity.py tests/agent_eval_factories.py tests/test_agent_eval_contracts.py tests/test_agent_eval_validity.py
git commit -m "feat(eval): add immutable run validity contract"
```

---

### Task 4: Atomic create-only artifact store

**Files:**
- Create: `scripts/agent_eval/store.py`
- Create: `tests/test_agent_eval_store.py`

**Interfaces:**
- Consumes: `validate_document`, `canonical_json_bytes`, digest fields, `evidence_contains_secret`.
- Produces: `ArtifactStore.create`, `ArtifactStore.read`, `ArtifactStore.verify_tree`, `WriteDisposition`.

- [ ] **Step 1: Write create/idempotency/conflict tests**

```python
from pathlib import Path

import pytest

from scripts.agent_eval.errors import ArtifactConflictError
from scripts.agent_eval.store import ArtifactStore, WriteDisposition
from tests.agent_eval_factories import scenario_document


def test_create_then_idempotent_reimport(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path)
    document = scenario_document()
    first = store.create(document)
    second = store.create(document)
    assert first.disposition is WriteDisposition.CREATED
    assert second.disposition is WriteDisposition.IDEMPOTENT
    assert first.path == second.path
    assert store.read(first.path) == document


def test_same_identity_different_payload_is_conflict(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path)
    original = scenario_document()
    store.create(original)
    changed = dict(original)
    changed["objective"] = "changed payload"
    from scripts.agent_eval.canonical import add_document_digest
    changed = add_document_digest({k: v for k, v in changed.items() if k != "scenario_digest"}, "scenario_digest")
    with pytest.raises(ArtifactConflictError):
        store.create(changed)
```

Also test no partial final file after injected pre-link failure, hard-link `FileExistsError` reconciliation, corrupted existing artifact, symlink/path escape refusal, exact file mode, secret-shaped evidence refusal, and whole-tree verification.

- [ ] **Step 2: Run store tests and confirm the red state**

```bash
pytest -q tests/test_agent_eval_store.py
```

Expected: import failure for `scripts.agent_eval.store`.

- [ ] **Step 3: Implement deterministic artifact paths**

Use schema-specific paths under the supplied root:

```text
scenarios/<family>/<scenario-id>/v<version>/scenario.json
experiments/<experiment-id>/manifest.json
experiments/<experiment-id>/runs/<run-id>/receipt.json
experiments/<experiment-id>/runs/<run-id>/scorer-passes/<scorer-pass-id>.json
evidence-refs/<evidence-ref-id>.json
```

Sanitize only by validation; never slugify an unvalidated identifier. Resolve the candidate and require `candidate.is_relative_to(root.resolve())`. Refuse any symlink in the parent chain.

- [ ] **Step 4: Implement create-only atomic write**

Use a temporary file on the same filesystem, fsync it, then create the final path with an atomic hard link that fails if the destination exists:

```python
class WriteDisposition(Enum):
    CREATED = "CREATED"
    IDEMPOTENT = "IDEMPOTENT"


@dataclass(frozen=True)
class WriteResult:
    path: Path
    disposition: WriteDisposition


def _link_create_only(temp_path: Path, final_path: Path) -> None:
    os.link(temp_path, final_path)
```

Algorithm:

1. `validate_document(document)`.
2. Refuse if `evidence_contains_secret(document)`.
3. Compute canonical bytes.
4. Create parents with mode `0o700` after symlink/path checks.
5. Write a named temp file in the final directory with mode `0o600`.
6. Flush and `os.fsync` the temp file.
7. `os.link(temp, final)`; on success unlink temp and fsync directory.
8. On `FileExistsError`, read final bytes. Exact bytes => `IDEMPOTENT`; different/corrupt => `ArtifactConflictError`.
9. Always remove the temp path.
10. Read final bytes, parse JSON, validate, and compare exact canonical bytes before returning `CREATED`.

Never use `os.replace`, `Path.write_text`, or an overwrite-capable database upsert.

- [ ] **Step 5: Implement read and verify-tree**

`read(path)` requires the path under root, no symlink, exact regular file, size <= 4 MiB, valid UTF-8 JSON, closed supported schema, and exact canonical bytes. `verify_tree()` recursively checks only expected `.json` artifact locations and returns a sorted tuple of structured defects; it never repairs.

- [ ] **Step 6: Run store tests**

```bash
pytest -q tests/test_agent_eval_store.py
```

Expected: all tests pass.

- [ ] **Step 7: Commit Task 4**

```bash
git add scripts/agent_eval/store.py tests/test_agent_eval_store.py
git commit -m "feat(eval): add create-only evidence artifact store"
```

---

### Task 5: Append-only scorer pass and non-scalar evidence reference

**Files:**
- Modify: `scripts/agent_eval/contracts.py`
- Create: `scripts/agent_eval/scoring.py`
- Modify: `tests/agent_eval_factories.py`
- Create: `tests/test_agent_eval_scoring.py`

**Interfaces:**
- Consumes: validated run/experiment/scenario documents.
- Produces: `build_validity_scorer_pass`, `summarize_experiment`, `validate_scorer_pass`, `validate_evidence_ref`.

- [ ] **Step 1: Write scorer-pass tests**

The initial deterministic scorer is `mastermind.validity.v1`. It maps the run’s validity status and reason codes to three separate dimensions:

```text
configuration_integrity
source_integrity
cleanup_integrity
```

Each dimension result is one of `PASS|FAIL|UNKNOWN|NOT_APPLICABLE` and retains reason codes/evidence refs.

Test that:

- pass run produces three `PASS` dimensions;
- model mismatch fails configuration only;
- source leakage fails source integrity;
- cleanup uncertainty fails cleanup integrity;
- scorer pass records exact run digest, scorer semantic version, code commit, method `DETERMINISTIC`, created time and own digest;
- a second scorer version creates a distinct ID and `supersedes` link rather than changing the first document;
- unknown fields, aggregate scores, and a field named `winner` are rejected.

- [ ] **Step 2: Write evidence-reference tests**

For a two-arm experiment with one `VALID_PASS` run and one `INVALID_CONFIGURATION` run, require:

```python
summary = summarize_experiment(experiment, [valid_run, invalid_run], scorer_passes)
assert summary["valid_run_count"] == 1
assert summary["invalid_run_count"] == 1
assert summary["invalid_counts"] == {"INVALID_CONFIGURATION": 1}
assert summary["evidence_grade"] == "INSUFFICIENT_EVIDENCE"
assert "winner" not in summary
assert "aggregate_score" not in summary
assert summary["non_authority_statement"] == (
    "This evidence reference does not authorize routing, policy, release, merge, deployment, or acceptance."
)
```

Also test exact experiment/run/scorer cross-reference, phase copy, sorted configuration digests, dimension gate matrix, limitations, expiry/review timestamp, intended owner, and own digest.

- [ ] **Step 3: Run scoring tests and confirm the red state**

```bash
pytest -q tests/test_agent_eval_scoring.py
```

Expected: import failure for `scripts.agent_eval.scoring` or unsupported schemas.

- [ ] **Step 4: Implement scorer-pass contract and builder**

Exact top-level fields:

```python
SCORER_PASS_FIELDS = frozenset({
    "schema", "scorer_pass_id", "run_ref", "run_digest", "scorer_id",
    "scorer_version", "code_commit", "configuration_digest", "method",
    "input_evidence_refs", "dimension_results", "grader", "human_reviewer_ref",
    "created_at", "supersedes", "scorer_pass_digest",
})
```

`grader` is null for deterministic scoring. `human_reviewer_ref` is null. `dimension_results` is a sorted list by dimension ID with exact fields `{dimension, status, reason_codes, evidence_refs}`. No numeric aggregate field is accepted.

Scorer-pass ID pattern:

```text
scorer-pass:<run-uuid>:<scorer-slug>:<version>:<uuid4>
```

`build_validity_scorer_pass` accepts explicit `code_commit`, `created_at` and UUID so tests remain deterministic.

- [ ] **Step 5: Implement evidence-reference contract and summarizer**

Exact top-level fields:

```python
EVIDENCE_REF_FIELDS = frozenset({
    "schema", "evidence_ref_id", "task_class", "scenario_refs", "experiment_ref",
    "valid_run_refs", "invalid_run_refs", "configuration_digests", "dimension_gates",
    "valid_run_count", "invalid_run_count", "degraded_run_count", "invalid_counts",
    "sample_size", "uncertainty", "phase", "evidence_grade", "limitations",
    "receipt_refs", "scorer_pass_refs", "analysis_refs", "intended_owner",
    "review_at", "non_authority_statement", "created_at", "evidence_ref_digest",
})
```

For EVAL-R0:

- `uncertainty` is `{method: "NOT_ESTIMATED", reason: "fewer than two valid paired samples per arm"}`;
- `evidence_grade` is `INSUFFICIENT_EVIDENCE` unless every arm has at least two valid paired cases and no load-bearing unknown;
- `dimension_gates` is a per-arm/per-dimension matrix, never one scalar;
- invalid runs remain listed and counted but are not included in valid denominators;
- `limitations` includes the insufficient paired sample statement;
- `analysis_refs` is empty;
- intended owner is explicit, e.g. `owner:outcome-learning`;
- non-authority statement is exact and immutable.

Add both validators to `_VALIDATORS`.

- [ ] **Step 6: Run scoring and all prior tests**

```bash
pytest -q \
  tests/test_agent_eval_canonical.py \
  tests/test_agent_eval_contracts.py \
  tests/test_agent_eval_validity.py \
  tests/test_agent_eval_store.py \
  tests/test_agent_eval_scoring.py
```

Expected: all tests pass.

- [ ] **Step 7: Commit Task 5**

```bash
git add scripts/agent_eval/contracts.py scripts/agent_eval/scoring.py tests/agent_eval_factories.py tests/test_agent_eval_scoring.py
git commit -m "feat(eval): add append-only scoring and evidence references"
```

---

### Task 6: CLI and complete fake two-arm journey

**Files:**
- Create: `scripts/agent_eval/cli.py`
- Create: `scripts/agent_evaluation.py`
- Create: `tests/test_agent_eval_cli.py`
- Create: `tests/fixtures/agent_eval/README.md`

**Interfaces:**
- Consumes: all prior package APIs.
- Produces: stable CLI exit codes and one end-to-end local workflow.

- [ ] **Step 1: Write CLI tests**

Use `main(argv)` directly. Require:

```text
0 success
1 valid command completed with invalid/degraded/insufficient evidence result
2 usage/contract/conflict/corruption error
```

Test subcommands:

```text
validate <document.json>
create --root <root> <document.json>
verify-tree --root <root>
score-validity --root <root> --run <receipt.json> --code-commit <sha> --created-at <time> --id <uuid>
summarize --root <root> --experiment <manifest.json> --runs <receipt...> --scorer-passes <pass...> --owner <owner> --review-at <time> --created-at <time> --id <uuid>
```

The fake journey test should:

1. create and store one scenario;
2. create and store one two-arm experiment;
3. finalize/store one `VALID_PASS` run;
4. finalize/store one `INVALID_CONFIGURATION` run with served-model mismatch;
5. create/store one scorer pass for each run;
6. summarize/store one evidence reference;
7. verify the whole tree;
8. assert one valid and one invalid count, insufficient evidence, no winner/aggregate/policy fields, and no file outside the temp root.

The test may use factories to materialize JSON inputs into `tmp_path`; production CLI code must not import tests.

- [ ] **Step 2: Run CLI tests and confirm the red state**

```bash
pytest -q tests/test_agent_eval_cli.py
```

Expected: import failure for `scripts.agent_eval.cli`.

- [ ] **Step 3: Implement CLI parser and deterministic JSON output**

`main(argv: list[str] | None = None) -> int` uses `argparse`. Every stdout result is one canonical JSON object. Human diagnostics go to stderr. Catch `ContractError`, `ArtifactConflictError`, `OSError`, `UnicodeError` and `json.JSONDecodeError`, map them to exit 2, and never print a traceback by default.

Example success result:

```json
{"command":"create","disposition":"CREATED","path":"/safe/root/.../scenario.json","schema":"mastermind.agent_evaluation_scenario.v1"}
```

`validate` never writes. `create` dispatches by schema. `verify-tree` returns sorted defects. `score-validity` only scores an already finalized run and appends a scorer pass. `summarize` consumes exact files and writes one evidence reference. No command schedules or executes a model.

- [ ] **Step 4: Implement thin wrapper**

`scripts/agent_evaluation.py` contains only:

```python
from scripts.agent_eval.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Add fixture provenance README**

State that all EVAL-R0 fixtures are synthetic, PUBLIC_SAFE, contain no real account/user/host/credential/private-chat data, and exist only to prove contracts/invalid handling. Record the architecture spec and operation key.

- [ ] **Step 6: Run CLI tests and manual fake journey**

```bash
pytest -q tests/test_agent_eval_cli.py
python scripts/agent_evaluation.py --help
```

Then run the exact CLI sequence used by the test against a new temporary root and retain stdout as PR evidence. Expected terminal summary: one valid run, one invalid configuration run, evidence grade `INSUFFICIENT_EVIDENCE`, and zero aggregate/winner/policy fields.

- [ ] **Step 7: Commit Task 6**

```bash
git add scripts/agent_eval/cli.py scripts/agent_evaluation.py tests/test_agent_eval_cli.py tests/fixtures/agent_eval/README.md
git commit -m "feat(eval): prove fake two-arm evidence journey"
```

---

### Task 7: Inertness, privacy, mutation and path-fence protection

**Files:**
- Create: `tests/test_agent_eval_inertness.py`
- Modify: implementation files only if a protection test finds a real defect.

**Interfaces:**
- Consumes: complete EVAL-R0 package.
- Produces: negative proof that EVAL-R0 cannot silently become an execution/control/memory plane.

- [ ] **Step 1: Write forbidden-import test**

Parse the AST of every `scripts/agent_eval/*.py` file and reject imports whose module starts with any of:

```python
FORBIDDEN_IMPORT_PREFIXES = (
    "control_plane.executive_runtime",
    "control_plane.executive_service",
    "control_plane.codex_worker",
    "control_plane.model_router",
    "integrations.slack",
    "integrations.executive_mcp",
    "psycopg",
    "sqlite3",
    "duckdb",
    "httpx",
    "requests",
    "socket",
    "subprocess",
    "inspect_ai",
    "langfuse",
    "promptfoo",
)
```

Permit the exact import `scripts.ohf.redaction.evidence_contains_secret`; reject other OHF runner imports in R0.

- [ ] **Step 2: Write forbidden-symbol and side-effect tests**

AST-scan for calls/names `Popen`, `run`, `connect`, `urlopen`, `create_connection`, `sqlite3`, `psycopg`, `duckdb`, `Thread`, `Process`, `asyncio.create_task`, and `os.environ` reads outside an explicit empty allowlist. Import every module in a clean subprocess and assert no files, sockets, threads, children or stdout/stderr are created.

The test process itself may use `subprocess` to verify import inertness; production package code may not.

- [ ] **Step 3: Write secret-shape tests**

Try values containing a synthetic API key prefix, JWT shape, authorization header, cookie, token field, email/account ID, `MASTERMIND_*=` environment assignment and private host address. Require store refusal before final-path creation. Verify normal SHA-256 digests are not redacted or rejected.

- [ ] **Step 4: Write mutation tests for load-bearing invariants**

Parametrize mutations over:

```text
unknown top-level field
unknown nested field
wrong schema
changed digest
future cutoff
post-cutoff source
served-model mismatch
extra tool schema
missing tool schema
unexpected capability
resume on forbidden scenario
unproven cleanup
effect unknown
negative token/tool count
time inversion
duration mismatch
same ID changed payload
symlink parent
path traversal
numeric aggregate score
winner field
policy field
```

Each mutation must be killed by an exact expected defect/reason code.

- [ ] **Step 5: Write repository path-fence test**

The PR implementation delta is allowed only under:

```text
scripts/agent_eval/**
scripts/agent_evaluation.py
tests/agent_eval_factories.py
tests/test_agent_eval_*.py
tests/fixtures/agent_eval/**
docs/superpowers/specs/2026-08-31-agent-evaluation-fabric-design.md
docs/superpowers/plans/2026-08-31-agent-evaluation-r0.md
research/AGENT_EVALUATION_FABRIC_PRIMARY_SOURCE_RESEARCH_2026-08-31.md
```

The test should read an environment-provided changed-file list in CI when available and otherwise validate a checked-in allowed-prefix constant. Do not make local test success depend on GitHub credentials.

- [ ] **Step 6: Run protection suite**

```bash
pytest -q tests/test_agent_eval_inertness.py
pytest -q tests/test_agent_eval_*.py
```

Expected: all tests pass and every listed mutation is killed.

- [ ] **Step 7: Commit Task 7**

```bash
git add tests/test_agent_eval_inertness.py scripts/agent_eval scripts/agent_evaluation.py
git commit -m "test(eval): prove inertness privacy and mutation fences"
```

---

### Task 8: Exact-head verification, independent review packet, and continuation handoff

**Files:**
- Modify: PR body and GitHub evidence only.
- Do not create Agent OS records until an accepted `organizational-learning` semantic parent exists.

**Interfaces:**
- Consumes: all EVAL-R0 commits and current protected base.
- Produces: reviewable PR evidence and exact next-wave packet.

- [ ] **Step 1: Re-pin protected base and reconcile drift**

Fetch current protected `Mastermind/master`. If it moved, compare every changed path and relevant contract/OHF/redaction dependency. Rebase or merge current base on the same branch only after checking for overlapping paths and semantic changes. Do not create a replacement PR.

- [ ] **Step 2: Run targeted and full tests**

```bash
pytest -q tests/test_agent_eval_*.py
pytest -q
```

Record exact commands, exit codes, test counts and head SHA. Full-suite failures must be classified as caused-by-this-diff or pre-existing with exact evidence; no green claim from targeted tests alone.

- [ ] **Step 3: Run static evidence checks**

```bash
python -m compileall -q scripts/agent_eval scripts/agent_evaluation.py
python scripts/agent_evaluation.py --help
```

Run the fake two-arm journey in a fresh temporary directory and capture its canonical JSON outputs. Inspect the directory tree for unexpected files and secret-shaped strings.

- [ ] **Step 4: Review against the original outcome**

Answer in the PR:

```text
What user or machine capability now exists?
Can one invalid configuration remain visible without contaminating valid denominators?
Can every artifact be re-read and digest-verified?
Can a changed run overwrite an existing run?
Did any lifecycle, router, memory, outcome-learning, provider, service or database plane appear?
Does the summary avoid a universal winner/score and automatic policy action?
What remains NOT_BUILT?
```

The truthful capability after R0 code is `BUILT_NOT_PROVEN / PRODUCTION_INERT` until one real OHF run traverses the contract and an independent reviewer accepts it.

- [ ] **Step 5: Request independent review**

Commission one Auditor Sol/qualified reviewer with exact head SHA and ask for:

- contract/source-law conformance;
- digest/idempotency/atomicity attacks;
- invalid-state precedence;
- privacy/secret/path attacks;
- no-duplicate-owner review against #162 and #6699;
- complete fake-journey reproduction;
- explicit APPROVE or REQUEST_CHANGES.

The reviewer must not mutate the branch while reviewing.

- [ ] **Step 6: Prepare continuation packet**

Return exact:

```text
operation key
branch / PR / head SHA / base SHA
changed paths
test and CI receipts
fake experiment/scenario/run/scorer/evidence IDs
review disposition
capability state
remaining unproven claims
exact next action
```

Next action after acceptance is EVAL-OHF1 on existing PR #162 plus EVAL-C0 on a separate corpus-only carrier. No Inspect, Promptfoo, Langfuse, UI or policy-promotion wave starts from R0 alone.

- [ ] **Step 7: Stop condition**

Stop the EVAL-R0 child only when exact-head tests are green, independent review is resolved, the fake journey is reproducible, the current base is reconciled, and the parent Program CEO has issued `SOL ACCEPTED / STOP`. A merge, if later authorized, proves only the production-inert native evidence core.

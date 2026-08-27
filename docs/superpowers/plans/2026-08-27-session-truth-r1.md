# Session Truth Receipt R1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first production-relevant, read-only `mastermind.session_truth_receipt.v1` capability so a fresh Sol can deterministically compare current Agent OS, GitHub, Linear, Slack and Executive observations, surface typed drift, and compute a safe session admission mode without mutating any source or creating another truth store.

**Architecture:** Keep acquisition and reconciliation separate. Mastermind owns a stdlib-only pure reconciliation core plus a thin CLI; Agent OS acquisition shells into Macro's canonical zero-network `scripts/agentos.py compile-context` instead of parsing Agent OS records again, while GitHub/Linear/Slack/Executive arrive as normalized read-only snapshot documents. The receipt is immutable evidence: it carries source revisions and a semantic hash, but it never becomes a mutable lifecycle, queue, retry, identity, memory or synchronization authority.

**Tech Stack:** Python >=3.11, stdlib-only `control_plane` modules, existing Macro `scripts/agentos.py` CLI, pytest >=8,<10, GitHub Actions hosted CI.

**Spec:** `docs/superpowers/specs/2026-08-27-cross-plane-reconciliation-design.md`

## Global Constraints

- Protected source-law basis for this plan: `mastermindx-market-intelligence/Mastermind@be68ec881460aa60d7d77cdb69f7c1cae81f6310`, Skillpack `mastermind.sol_skillpack.v1` v1.0.0, bootstrap major 1 compatible.
- Approved architecture carrier: Mastermind PR #169, approved spec commit `0aad273340a5f788013d460770feb621ea688846`.
- R1 is read-only. It creates no Linear, Slack or Executive mutation and does not merge/close/relabel any GitHub carrier as a side effect of receipt generation.
- The pure reconciliation path performs zero network I/O.
- `control_plane` remains importable with the Python standard library only; do not add a new runtime dependency.
- Agent OS parser/schema ownership remains in Macro. Consume `scripts/agentos.py compile-context`; do not add a second frontmatter/YAML parser in Mastermind.
- Do not modify `docs/sol_skills/**`; Mastermind PR #147 owns the separate candidate Skillpack procedure change.
- Do not create another CEO ingress, Executive Job/Attempt/Worker store, Agent OS registry, Linear projector, PR metadata grammar, SOL_STATE lane, Agent Relay, Slack queue/inbox/retry ledger, or durable reconciliation database.
- Missing sources remain explicit unavailable/unknown states; they never normalize to empty/healthy.
- Slack delivery never implies runtime ACK, claim or execution.
- Linear `Done` never outranks GitHub/Agent OS/Executive completion law.
- Unknown seat/service identity stays typed unknown; name similarity cannot bind identities.
- Same operation key with changed canonical payload is conflict/refusal, never a second operation.
- A model may summarize a finished receipt but has zero authority to change normalized facts, finding severity, admission mode or identity bindings.

---

## File structure

The implementation stays flat under `control_plane/` because the current package discovery explicitly includes `control_plane` and does not need a packaging change for new sibling modules.

- `control_plane/session_truth_contract.py` — schemas, enum sets, contract validation, canonical JSON and semantic hashing.
- `control_plane/session_truth_acquire.py` — read-only Skillpack + Agent OS acquisition; no external service writes and no Agent OS parsing duplication.
- `control_plane/session_truth_snapshots.py` — validation/normalization for externally acquired GitHub/Linear/Slack/Executive/identity snapshots and secret-key rejection.
- `control_plane/session_truth_rules.py` — deterministic indexes, drift detectors and fixed severity/repair-owner metadata.
- `control_plane/session_truth.py` — assemble receipt, compute admission, semantic projection/hash and concise human rendering.
- `scripts/session_truth_receipt.py` — stable CLI entrypoint; reads snapshot files, acquires local Skillpack/Agent OS, emits JSON or text.
- `tests/test_session_truth_contract.py` — contract/hash tests.
- `tests/test_session_truth_acquire.py` — Skillpack/Agent OS read-only acquisition tests.
- `tests/test_session_truth_snapshots.py` — per-source normalization and redaction tests.
- `tests/test_session_truth_rules.py` — positive and negative tests for every required R1 finding code.
- `tests/test_session_truth_cli.py` — end-to-end hermetic CLI, deterministic semantic replay and zero-write/zero-network tests.
- `tests/fixtures/session_truth/*.json` — bounded synthetic source snapshots only; no credentials or live private message bodies.
- `review_evidence/session_truth/r1/` — immutable sanitized current-estate input/receipt/proof artifacts created only at Task 7.

---

### Task 1: Freeze the input/receipt contract and semantic hashing

**Files:**
- Create: `control_plane/session_truth_contract.py`
- Create: `tests/test_session_truth_contract.py`

**Interfaces:**
- Produces: `INPUT_SCHEMA`, `RECEIPT_SCHEMA`, `ADMISSION_MODES`, `FINDING_SEVERITIES`.
- Produces: `SessionTruthContractError(ValueError)`.
- Produces: `canonical_json(value: object) -> str`.
- Produces: `semantic_hash(value: object) -> str` returning `sha256:<hex>`.
- Produces: `validate_input_document(doc: Mapping[str, Any]) -> dict[str, Any]` returning a defensive normalized copy or raising `SessionTruthContractError`.
- Consumed by: Tasks 3-6.

- [ ] **Step 1: Write failing schema and determinism tests**

```python
from copy import deepcopy

import pytest

from control_plane.session_truth_contract import (
    INPUT_SCHEMA,
    RECEIPT_SCHEMA,
    SessionTruthContractError,
    canonical_json,
    semantic_hash,
    validate_input_document,
)


def minimal_input():
    return {
        "schema": INPUT_SCHEMA,
        "scope": {
            "workstreams": ["WS:CHAIRMAN-CONTROL-ROOM"],
            "linear": [],
            "repositories": ["mastermindx-market-intelligence/Mastermind"],
            "operation_key": None,
            "requires_executive": False,
        },
        "skillpack": {
            "repository": "mastermindx-market-intelligence/Mastermind",
            "sha": "a" * 40,
            "schema": "mastermind.sol_skillpack.v1",
            "version": "1.0.0",
            "minimum_bootstrap_major": 1,
            "available": True,
        },
        "agentos": {"available": True, "source_sha": "b" * 40, "contexts": [], "warnings": []},
        "github": {"schema": "mastermind.github_observation.v1", "available": True, "repositories": []},
        "linear": {"schema": "mastermind.linear_observation.v1", "available": True, "issues": []},
        "slack": {"schema": "mastermind.slack_observation.v1", "available": True, "channels": [], "messages": []},
        "executive": {"schema": "mastermind.executive_observation.v1", "available": False, "reason": "C1_NOT_PROVEN"},
        "identities": {"schema": "mastermind.identity_observation.v1", "available": True, "bindings": []},
    }


def test_contract_constants_are_exact():
    assert INPUT_SCHEMA == "mastermind.session_truth_inputs.v1"
    assert RECEIPT_SCHEMA == "mastermind.session_truth_receipt.v1"


def test_canonical_json_is_order_independent():
    left = {"b": 2, "a": {"d": 4, "c": 3}}
    right = {"a": {"c": 3, "d": 4}, "b": 2}
    assert canonical_json(left) == canonical_json(right)
    assert semantic_hash(left) == semantic_hash(right)


def test_validate_rejects_unknown_top_level_keys():
    doc = minimal_input()
    doc["shadow_truth_store"] = {}
    with pytest.raises(SessionTruthContractError, match="unknown top-level key"):
        validate_input_document(doc)


def test_validate_does_not_mutate_caller_input():
    doc = minimal_input()
    before = deepcopy(doc)
    validate_input_document(doc)
    assert doc == before
```

- [ ] **Step 2: Run the contract tests and verify RED**

Run: `python -m pytest tests/test_session_truth_contract.py -q`

Expected: import failure because `control_plane.session_truth_contract` does not exist.

- [ ] **Step 3: Implement the minimal stdlib-only contract**

Use only `copy`, `hashlib`, `json`, `re`, `collections.abc` and `typing`.

```python
INPUT_SCHEMA = "mastermind.session_truth_inputs.v1"
RECEIPT_SCHEMA = "mastermind.session_truth_receipt.v1"
ADMISSION_MODES = {
    "GROUNDING_COMPLETE", "GROUNDING_PARTIAL", "DIALOGUE_ONLY", "MODIFICATION_REFUSED",
}
FINDING_SEVERITIES = {"FATAL", "BLOCKING", "WARNING", "INFO"}

class SessionTruthContractError(ValueError):
    pass


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def semantic_hash(value: object) -> str:
    digest = hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()
    return f"sha256:{digest}"
```

`validate_input_document()` must enforce:

1. exact top-level keys `schema, scope, skillpack, agentos, github, linear, slack, executive, identities`;
2. exact input schema;
3. `WS:` prefix for workstreams, `MAS-` prefix for Linear IDs, `owner/name` shape for repositories;
4. 40-lower/upper-hex repository SHAs wherever a SHA is present;
5. booleans for every `available` field;
6. explicit `reason` when a source is unavailable;
7. no silent insertion of healthy defaults for a missing source document;
8. a deep copy returned so downstream normalization cannot mutate caller-owned data.

- [ ] **Step 4: Add negative shape tests**

```python
@pytest.mark.parametrize(
    ("mutator", "message"),
    [
        (lambda d: d["scope"]["workstreams"].__setitem__(0, "CHAIRMAN-CONTROL-ROOM"), "WS:"),
        (lambda d: d["skillpack"].__setitem__("sha", "short"), "40-hex"),
        (lambda d: d["github"].pop("available"), "github.available"),
        (lambda d: d.__setitem__("executive", {"schema": "mastermind.executive_observation.v1", "available": False}), "reason"),
    ],
)
def test_invalid_shapes_fail_closed(mutator, message):
    doc = minimal_input()
    mutator(doc)
    with pytest.raises(SessionTruthContractError, match=message):
        validate_input_document(doc)
```

- [ ] **Step 5: Run Task 1 tests GREEN and commit**

Run: `python -m pytest tests/test_session_truth_contract.py -q`

Expected: PASS.

Commit:

```bash
git add control_plane/session_truth_contract.py tests/test_session_truth_contract.py
git commit -m "feat(exec): freeze session truth receipt contract"
```

---

### Task 2: Acquire protected Skillpack identity and direct Agent OS context read-only

**Files:**
- Create: `control_plane/session_truth_acquire.py`
- Create: `tests/test_session_truth_acquire.py`

**Interfaces:**
- Consumes: `control_plane.ceo_boot_packet.resolve_macro_root`, `control_plane.ceo_boot_packet.git_sha`.
- Produces: `collect_skillpack(repo_root: Path, expected_sha: str | None, bootstrap_major: int = 1) -> dict[str, Any]`.
- Produces: `collect_agentos(macro_root_flag: str | None, workstreams: Sequence[str], *, environ: Mapping[str, str], now: str | None, timeout: float = 60.0) -> dict[str, Any]`.
- Produces: `AcquisitionError(RuntimeError)` for malformed owner output only; missing join capability returns `available=False` with a reason.
- Consumed by: Task 5/6.

- [ ] **Step 1: Write the Skillpack acquisition tests**

```python
from pathlib import Path

from control_plane.session_truth_acquire import collect_skillpack


def test_collect_skillpack_reads_exact_frontmatter_and_sha(tmp_path, monkeypatch):
    repo = tmp_path / "Mastermind"
    skill = repo / "docs" / "sol_skills" / "INDEX.md"
    skill.parent.mkdir(parents=True)
    skill.write_text(
        "---\nschema: mastermind.sol_skillpack.v1\n"
        "skillpack_version: 1.0.0\nminimum_bootstrap_major: 1\nskill: index\n---\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("control_plane.session_truth_acquire.git_sha", lambda p: "a" * 40)
    got = collect_skillpack(repo, expected_sha="a" * 40, bootstrap_major=1)
    assert got == {
        "repository": "mastermindx-market-intelligence/Mastermind",
        "sha": "a" * 40,
        "schema": "mastermind.sol_skillpack.v1",
        "version": "1.0.0",
        "minimum_bootstrap_major": 1,
        "available": True,
    }
```

Add explicit tests for expected-SHA mismatch and incompatible bootstrap major; both must return/raise a blocking acquisition result and never relabel a different local revision as protected truth.

- [ ] **Step 2: Write the Agent OS canonical-reader test with a write trap**

Build a temporary Macro fixture containing `scripts/agentos.py` that accepts only:

```text
compile-context --workstream TARGET --now 2026-08-27T05:00:00Z
```

The stub must write `.ILLEGAL_WRITE` if it receives any argument outside the read-only compile-context contract. It emits one minimal `context_bundle.v1` JSON document with `target.workstream = WS:TARGET`, one `workstream` section item and citations.

Test:

```python
def test_collect_agentos_uses_compile_context_and_writes_nothing(tmp_path):
    macro = make_macro_fixture(tmp_path)
    before = snapshot_tree(macro)
    got = collect_agentos(
        str(macro), ["WS:TARGET"], environ={}, now="2026-08-27T05:00:00Z", timeout=5,
    )
    assert got["available"] is True
    assert got["contexts"][0]["schema"] == "context_bundle.v1"
    assert got["contexts"][0]["target"]["workstream"] == "WS:TARGET"
    assert snapshot_tree(macro) == before
    assert not (macro / ".ILLEGAL_WRITE").exists()
```

- [ ] **Step 3: Run acquisition tests RED**

Run: `python -m pytest tests/test_session_truth_acquire.py -q`

Expected: import failure.

- [ ] **Step 4: Implement Skillpack frontmatter reading without PyYAML**

Only parse the four scalar header lines before the second `---` fence. Reject duplicate keys, non-scalar values and missing required fields. Do not introduce a general YAML parser.

```python
def _read_scalar_frontmatter(path: Path) -> dict[str, str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0] != "---":
        raise AcquisitionError("Skillpack INDEX has no frontmatter fence")
    out: dict[str, str] = {}
    for line in lines[1:]:
        if line == "---":
            return out
        key, sep, value = line.partition(":")
        if not sep or not key.strip() or not value.strip():
            raise AcquisitionError("Skillpack INDEX contains non-scalar frontmatter")
        key = key.strip()
        if key in out:
            raise AcquisitionError(f"duplicate Skillpack field: {key}")
        out[key] = value.strip()
    raise AcquisitionError("Skillpack INDEX frontmatter is unterminated")
```

- [ ] **Step 5: Implement canonical Agent OS acquisition through Macro**

Requirements:

- resolve Macro using the already-tested `resolve_macro_root` ladder;
- verify `scripts/agentos.py` and `agentos/` exist via that resolver;
- record Macro HEAD with `git_sha`;
- for each exact requested `WS:<KEY>`, strip only the `WS:` prefix and invoke:

```python
cmd = [
    sys.executable,
    str(macro_root / "scripts" / "agentos.py"),
    "compile-context",
    "--workstream", key,
]
if now:
    cmd += ["--now", now]
```

- `cwd` is the Macro root;
- `capture_output=True`, `text=True`, `check=False`, bounded timeout;
- nonzero exit for a requested workstream is `AcquisitionError` because the direct record/schema request is malformed or unknown;
- unavailable Macro root is `{available: false, reason: "AGENTOS_READ_PATH_UNAVAILABLE", ...}` and does not become an empty context list marked healthy;
- preserve each `context_bundle.v1` document verbatim under `contexts`; do not re-rank or rewrite its authority order.

- [ ] **Step 6: Run Task 2 tests GREEN and commit**

Run: `python -m pytest tests/test_session_truth_acquire.py tests/test_ceo_boot_packet.py -q`

Expected: PASS, proving the new reader did not regress the existing read-only bridge.

Commit:

```bash
git add control_plane/session_truth_acquire.py tests/test_session_truth_acquire.py
git commit -m "feat(exec): add canonical read-only grounding acquisition"
```

---

### Task 3: Normalize external GitHub, Linear, Slack, Executive and identity snapshots

**Files:**
- Create: `control_plane/session_truth_snapshots.py`
- Create: `tests/test_session_truth_snapshots.py`
- Create: `tests/fixtures/session_truth/github_minimal.json`
- Create: `tests/fixtures/session_truth/linear_minimal.json`
- Create: `tests/fixtures/session_truth/slack_minimal.json`
- Create: `tests/fixtures/session_truth/executive_unavailable.json`
- Create: `tests/fixtures/session_truth/identity_minimal.json`

**Interfaces:**
- Consumes: `SessionTruthContractError` and `canonical_json` from Task 1.
- Produces schema constants:
  - `GITHUB_SCHEMA = "mastermind.github_observation.v1"`
  - `LINEAR_SCHEMA = "mastermind.linear_observation.v1"`
  - `SLACK_SCHEMA = "mastermind.slack_observation.v1"`
  - `EXECUTIVE_SCHEMA = "mastermind.executive_observation.v1"`
  - `IDENTITY_SCHEMA = "mastermind.identity_observation.v1"`
- Produces: `load_snapshot(path: Path, expected_schema: str) -> dict[str, Any]`.
- Produces: `normalize_github/normalize_linear/normalize_slack/normalize_executive/normalize_identities`.
- Consumed by: Tasks 4-6.

- [ ] **Step 1: Write exact normalization tests**

GitHub fixture must carry:

```json
{
  "schema": "mastermind.github_observation.v1",
  "available": true,
  "observed_at": "2026-08-27T05:00:00Z",
  "repositories": [{
    "repository": "mastermindx-market-intelligence/Mastermind",
    "default_branch": "master",
    "default_sha": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "prs": [{
      "number": 169,
      "state": "open",
      "draft": true,
      "head_sha": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
      "base_sha": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      "merge_sha": null,
      "ci": "success",
      "workstream": "WS:CHAIRMAN-CONTROL-ROOM",
      "linear": null,
      "portfolio_mode": "architecture_candidate",
      "wave": "CROSS-PLANE-R0",
      "authority": "architecture",
      "completion": "acceptance-required",
      "proof_state": "open",
      "operation_key": "cross-plane-reconciliation-20260827-sol-001"
    }]
  }]
}
```

Tests must prove that array order does not affect normalized output, integer/string coercion is not silently performed, unknown enum values fail closed, and `null` stays `null`.

- [ ] **Step 2: Write secret-bearing input rejection tests**

```python
@pytest.mark.parametrize("bad_key", ["token", "access_token", "authorization", "cookie", "secret", "password"])
def test_secret_key_names_are_rejected(tmp_path, bad_key):
    doc = json.loads((FIXTURES / "slack_minimal.json").read_text())
    doc[bad_key] = "do-not-copy"
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(SessionTruthContractError, match="secret-bearing key"):
        load_snapshot(path, SLACK_SCHEMA)
```

The recursive rejection is case-insensitive and applies to key names, not arbitrary message text, so a harmless sentence containing the word "token" is not destroyed.

- [ ] **Step 3: Run snapshot tests RED**

Run: `python -m pytest tests/test_session_truth_snapshots.py -q`

Expected: import failure.

- [ ] **Step 4: Implement strict per-plane normalizers**

Required normalized fields:

**GitHub PR:** `repository, number, state, draft, head_sha, base_sha, merge_sha, ci, workstream, linear, portfolio_mode, wave, authority, completion, proof_state, operation_key`.

**Linear issue:** `id, status, parent_id, workstream, completion, projection_revision, github_relations, updated_at` where each relation is `repository, pr, relationship_class` and `relationship_class` is one of `merge_is_done, contributing, architecture_evidence, program_gate, ignored_wrong_id`.

**Slack message:** `channel_id, ts, thread_ts, sender_id, operation_key, transport, message_class, target_principal_id, delivered, acked, receiver_eligible, created_at, source_law_sha`. Channel rows carry exact `channel_id` + `member_ids` only; do not persist private message bodies in R1 receipts.

**Executive:** explicit `available`; when available, `observed_at, fresh, do_not_submit, grounding_sha, operations`. Operation rows carry `operation_key, payload_hash, status, effect_unknown, carrier` only.

**Identity:** `seat, slack_principal, github_account, linear_actor, executive_worker, provider_realm, role, service_actor`; every field may be `null`, and `null` is not filled heuristically.

Sort by stable identities only: repository/name/PR number, MAS numeric ID, channel+timestamp, operation key, seat. Preserve source timestamps as values; do not use wall clock to resort observations.

- [ ] **Step 5: Run Task 3 tests GREEN and commit**

Run: `python -m pytest tests/test_session_truth_snapshots.py -q`

Expected: PASS.

Commit:

```bash
git add control_plane/session_truth_snapshots.py tests/test_session_truth_snapshots.py tests/fixtures/session_truth
git commit -m "feat(exec): normalize cross-plane read snapshots"
```

---

### Task 4: Implement the complete deterministic R1 drift taxonomy

**Files:**
- Create: `control_plane/session_truth_rules.py`
- Create: `tests/test_session_truth_rules.py`

**Interfaces:**
- Consumes normalized Task 2/3 documents.
- Produces: `Finding` dictionaries with exact keys `code, severity, canonical_owner, subject, source_a, source_b, repair_owner, modification_consequence, details`.
- Produces: `build_indexes(inputs: Mapping[str, Any]) -> dict[str, Any]`.
- Produces: `detect_findings(inputs: Mapping[str, Any]) -> list[dict[str, Any]]` sorted deterministically by severity rank, code, subject.
- Consumed by: Task 5.

- [ ] **Step 1: Freeze the finding registry before detector code**

The module must have one immutable registry entry for every required code, with fixed severity and owner. No detector chooses its own severity ad hoc.

```python
FINDING_REGISTRY = {
    "STALE_LINEAR_PROJECTION": ("WARNING", "agentos", "linear"),
    "FALSE_LINEAR_COMPLETION": ("BLOCKING", "declared_completion_owner", "linear"),
    "MISSING_LINEAR_PROJECTION": ("WARNING", "agentos", "linear"),
    "LINEAR_PARENT_CHILD_DIVERGENCE": ("WARNING", "linear_projection", "linear"),
    "ORPHAN_LINEAR_ISSUE": ("WARNING", "agentos", "linear"),
    "BUILD_VISIBILITY_STALE": ("INFO", "github_or_linear", "slack"),
    "GITHUB_PR_UNBOUND": ("WARNING", "github", "github"),
    "GITHUB_MERGE_WITH_PROOF_OPEN": ("BLOCKING", "declared_completion_owner", "linear"),
    "ORPHAN_GITHUB_CARRIER": ("WARNING", "agentos", "github"),
    "MULTIPLE_ACTIVE_CARRIERS": ("FATAL", "github", "github"),
    "CARRIER_HEAD_MOVED": ("BLOCKING", "github", "github"),
    "PR_BINDING_CONFLICT": ("FATAL", "github", "github"),
    "AGENTOS_GITHUB_DISAGREEMENT": ("WARNING", "agentos_or_github_by_fact", "agentos_or_github"),
    "STALE_HANDOFF": ("WARNING", "agentos", "agentos"),
    "SUPERSEDED_NEXT_ACTION": ("WARNING", "agentos", "agentos"),
    "DIRECT_GENERATED_STATE_DIVERGENCE": ("WARNING", "agentos_direct", "agentos_generated"),
    "SLACK_TRANSPORT_WITHOUT_RECEIVER": ("BLOCKING", "executive_or_active_session", "slack"),
    "SLACK_TRANSPORT_WITHOUT_ACK": ("WARNING", "runtime_session", "slack"),
    "CEO_SEAT_USED_AS_WORKER": ("FATAL", "identity_registry", "slack"),
    "DUPLICATE_OPERATION_CARRIER": ("FATAL", "executive_or_carrier_owner", "slack_or_github"),
    "POST_FREEZE_DISPATCH_VIOLATION": ("BLOCKING", "source_law", "slack"),
    "RUNTIME_STATE_UNAVAILABLE": ("BLOCKING", "executive", "executive"),
    "RUNTIME_STATE_STALE": ("BLOCKING", "executive", "executive"),
    "SLACK_ACK_WITHOUT_EXECUTIVE_STATE": ("BLOCKING", "executive", "slack"),
    "EXECUTIVE_GROUNDING_DIVERGED": ("BLOCKING", "executive", "executive"),
    "UNKNOWN_SEAT_IDENTITY": ("WARNING", "identity_registry", "identity_registry"),
    "SERVICE_ACTOR_UNBOUND": ("BLOCKING", "identity_registry", "identity_registry"),
    "ACTOR_ROLE_COLLISION": ("FATAL", "identity_registry", "identity_registry"),
}
```

If implementation evidence demonstrates one registry severity above conflicts with the approved spec's FATAL/BLOCKING definitions, stop and return to Sol with the exact contradiction instead of silently changing it.

- [ ] **Step 2: Write one positive and one negative test for every registry code**

Use a shared `healthy_inputs()` fixture representing one fully consistent workstream. Each detector test mutates exactly the minimum field(s) needed to produce one named finding.

The positive fixture matrix is:

| Finding | Minimal positive mutation |
|---|---|
| `STALE_LINEAR_PROJECTION` | Linear `projection_revision` differs from exact current Agent OS `source_sha` for same WS |
| `FALSE_LINEAR_COMPLETION` | Linear status `Done`, related GitHub PR merged, `proof_state=open`, completion not `merge-is-done` |
| `MISSING_LINEAR_PROJECTION` | Agent OS WS declares a specific MAS binding absent from Linear snapshot |
| `LINEAR_PARENT_CHILD_DIVERGENCE` | parent Done while explicit completion-bearing child is nonterminal |
| `ORPHAN_LINEAR_ISSUE` | MAS issue claims WS key absent from scoped Agent OS contexts |
| `BUILD_VISIBILITY_STALE` | selected GitHub/Linear event revision is newer than latest matching build-events visibility observation |
| `GITHUB_PR_UNBOUND` | materially open PR has all binding fields null/absent |
| `GITHUB_MERGE_WITH_PROOF_OPEN` | merged PR with non-merge completion and `proof_state=open` |
| `ORPHAN_GITHUB_CARRIER` | PR binds WS key absent from scoped Agent OS contexts |
| `MULTIPLE_ACTIVE_CARRIERS` | two open PRs share same non-null operation key |
| `CARRIER_HEAD_MOVED` | snapshot carries `pickup_head_sha` and current `head_sha` differs |
| `PR_BINDING_CONFLICT` | PR workstream binding conflicts with explicit Linear/Agent OS binding for same carrier |
| `AGENTOS_GITHUB_DISAGREEMENT` | Agent OS says implementation not built while bound GitHub merge exists, or vice versa for a fact owned by GitHub |
| `STALE_HANDOFF` | context contains handoff next action older than a newer decision/current workstream action |
| `SUPERSEDED_NEXT_ACTION` | direct WS current action conflicts with an explicitly superseding DEC/handoff receipt |
| `DIRECT_GENERATED_STATE_DIVERGENCE` | direct context source revision/state differs from optional generated Agent OS view snapshot |
| `SLACK_TRANSPORT_WITHOUT_RECEIVER` | actionable/delivery message delivered with `receiver_eligible=false` |
| `SLACK_TRANSPORT_WITHOUT_ACK` | active-session dialogue delivered to eligible receiver but `acked=false` after snapshot marks ACK required |
| `CEO_SEAT_USED_AS_WORKER` | target Slack principal is bound only to role `sol_ceo`, while message class is runnable worker pickup |
| `DUPLICATE_OPERATION_CARRIER` | same operation key appears on two distinct carriers/messages/PRs |
| `POST_FREEZE_DISPATCH_VIOLATION` | runnable pickup created after declared freeze timestamp/source law while receiver unavailable |
| `RUNTIME_STATE_UNAVAILABLE` | scope `requires_executive=true` and Executive snapshot `available=false` |
| `RUNTIME_STATE_STALE` | Executive available but `fresh=false` for an Executive-required scope |
| `SLACK_ACK_WITHOUT_EXECUTIVE_STATE` | Slack claims ACK for canonical-execution operation while Executive has no matching operation |
| `EXECUTIVE_GROUNDING_DIVERGED` | Executive grounding SHA differs from required exact Mastermind grounding SHA |
| `UNKNOWN_SEAT_IDENTITY` | action depends on a seat field whose required service binding is null |
| `SERVICE_ACTOR_UNBOUND` | named service actor needed by requested operation has no exact registry binding |
| `ACTOR_ROLE_COLLISION` | same principal is simultaneously declared service actor and human/CEO role in conflicting bindings |

The negative test for each code starts from `healthy_inputs()` and asserts that code is absent.

- [ ] **Step 3: Run rule tests RED**

Run: `python -m pytest tests/test_session_truth_rules.py -q`

Expected: import failure.

- [ ] **Step 4: Implement indexes and small detector functions**

Build exact-key indexes only; no fuzzy title/name matching.

```python
def _finding(code: str, subject: str, *, source_a, source_b, details: str) -> dict[str, Any]:
    severity, canonical_owner, repair_owner = FINDING_REGISTRY[code]
    return {
        "code": code,
        "severity": severity,
        "canonical_owner": canonical_owner,
        "subject": subject,
        "source_a": source_a,
        "source_b": source_b,
        "repair_owner": repair_owner,
        "modification_consequence": _consequence(severity),
        "details": details,
    }
```

`_consequence()` is fixed:

- FATAL -> `new_modification_refused`;
- BLOCKING -> `requested_modification_blocked`;
- WARNING -> `repair_debt_visible`;
- INFO -> `visibility_only`.

Each `_detect_*` function must be pure and return a list. `detect_findings()` concatenates all detectors and sorts by fixed severity rank `FATAL, BLOCKING, WARNING, INFO`, then `code`, then `subject`.

- [ ] **Step 5: Add anti-majority-vote and anti-name-binding mutation tests**

```python
def test_two_projections_cannot_outvote_canonical_owner(healthy_inputs):
    doc = healthy_inputs()
    # Agent OS current source says active; both Slack text and Linear projection claim done.
    doc["linear"]["issues"][0]["status"] = "Done"
    doc["slack"]["messages"].append(done_visibility_message())
    findings = detect_findings(doc)
    assert any(f["code"] == "FALSE_LINEAR_COMPLETION" for f in findings)


def test_name_similarity_never_binds_ceo_to_worker(healthy_inputs):
    doc = healthy_inputs()
    doc["identities"]["bindings"] = [{
        "seat": "ChatGPT2", "slack_principal": "U-CHATGPT2", "github_account": None,
        "linear_actor": None, "executive_worker": None, "provider_realm": "codex-pro-02",
        "role": "sol_ceo", "service_actor": None,
    }]
    doc["slack"]["messages"] = [worker_pickup(target="U-CHATGPT2")]
    assert "CEO_SEAT_USED_AS_WORKER" in {f["code"] for f in detect_findings(doc)}
```

- [ ] **Step 6: Run Task 4 tests GREEN and commit**

Run: `python -m pytest tests/test_session_truth_rules.py -q`

Expected: PASS with every registry code covered by a positive and a negative test.

Commit:

```bash
git add control_plane/session_truth_rules.py tests/test_session_truth_rules.py
git commit -m "feat(exec): classify cross-plane drift deterministically"
```

---

### Task 5: Assemble the immutable receipt and compute admission mode

**Files:**
- Create: `control_plane/session_truth.py`
- Create: `tests/test_session_truth_receipt.py`

**Interfaces:**
- Consumes: Tasks 1-4.
- Produces: `build_receipt(inputs: Mapping[str, Any], *, observed_started_at: str, observed_ended_at: str) -> dict[str, Any]`.
- Produces: `semantic_projection(receipt: Mapping[str, Any]) -> dict[str, Any]`.
- Produces: `compute_admission(inputs: Mapping[str, Any], findings: Sequence[Mapping[str, Any]]) -> dict[str, Any]`.
- Produces: `render_receipt(receipt: Mapping[str, Any]) -> str`.
- Consumed by: Task 6/7.

- [ ] **Step 1: Write admission precedence tests**

```python
@pytest.mark.parametrize(
    ("findings", "requires_exec", "expected"),
    [
        ([finding("ACTOR_ROLE_COLLISION", "FATAL")], False, "MODIFICATION_REFUSED"),
        ([finding("RUNTIME_STATE_UNAVAILABLE", "BLOCKING")], True, "DIALOGUE_ONLY"),
        ([finding("UNKNOWN_SEAT_IDENTITY", "WARNING")], False, "GROUNDING_PARTIAL"),
        ([], False, "GROUNDING_COMPLETE"),
    ],
)
def test_admission_precedence(findings, requires_exec, expected, healthy_inputs):
    doc = healthy_inputs()
    doc["scope"]["requires_executive"] = requires_exec
    assert compute_admission(doc, findings)["mode"] == expected
```

Admission law:

1. any FATAL -> `MODIFICATION_REFUSED`;
2. any BLOCKING that applies to the requested operation -> `DIALOGUE_ONLY`, except duplicate/effect-unknown/carrier collision classes that are already FATAL;
3. no FATAL/BLOCKING but unavailable optional source or WARNING -> `GROUNDING_PARTIAL`;
4. otherwise -> `GROUNDING_COMPLETE`.

`modification_safe` remains `False` for `DIALOGUE_ONLY` and `MODIFICATION_REFUSED`. For `GROUNDING_COMPLETE` it means only “receipt-level grounding has no blocker”; it explicitly does not replace Chairman intent/app/runtime gates.

- [ ] **Step 2: Write semantic replay tests**

```python
def test_observation_window_changes_do_not_change_semantic_hash(healthy_inputs):
    one = build_receipt(healthy_inputs(), observed_started_at="2026-08-27T05:00:00Z", observed_ended_at="2026-08-27T05:00:01Z")
    two = build_receipt(healthy_inputs(), observed_started_at="2026-08-27T05:10:00Z", observed_ended_at="2026-08-27T05:10:01Z")
    assert one["semantic_hash"] == two["semantic_hash"]
    assert semantic_projection(one) == semantic_projection(two)
    assert one["observation"]["started_at"] != two["observation"]["started_at"]
```

The semantic projection excludes only acquisition envelope clock fields and the `semantic_hash` field itself. It includes exact source revisions, normalized facts, findings, admission and scope. A source revision/timestamp change that changes source semantics must change the semantic hash.

- [ ] **Step 3: Run receipt tests RED**

Run: `python -m pytest tests/test_session_truth_receipt.py -q`

Expected: import failure.

- [ ] **Step 4: Implement receipt assembly**

The receipt shape is exactly:

```python
{
    "schema": "mastermind.session_truth_receipt.v1",
    "scope": normalized_inputs["scope"],
    "skillpack": normalized_inputs["skillpack"],
    "observation": {"started_at": ..., "ended_at": ...},
    "observations": {
        "agentos": normalized_inputs["agentos"],
        "github": normalized_inputs["github"],
        "linear": normalized_inputs["linear"],
        "slack": normalized_inputs["slack"],
        "executive": normalized_inputs["executive"],
        "identities": normalized_inputs["identities"],
    },
    "findings": findings,
    "admission": admission,
    "semantic_hash": "sha256:...",
}
```

Do not include raw Slack bodies, credentials, environment variables or arbitrary subprocess stderr.

- [ ] **Step 5: Implement concise deterministic text rendering**

Text form must include:

```text
SESSION TRUTH RECEIPT
mode: <mode>
semantic_hash: <hash>
source: skillpack <sha> | agentos <sha/unavailable> | github <available/unavailable> | linear ...
findings: <count> (FATAL n / BLOCKING n / WARNING n / INFO n)
<one line per finding: severity code subject -> repair_owner>
modification_safe: true|false
```

Never render “healthy” for an unavailable source. Never render “executing” from a Slack delivery field.

- [ ] **Step 6: Run Task 5 tests GREEN and commit**

Run: `python -m pytest tests/test_session_truth_receipt.py tests/test_session_truth_rules.py -q`

Expected: PASS.

Commit:

```bash
git add control_plane/session_truth.py tests/test_session_truth_receipt.py
git commit -m "feat(exec): assemble deterministic session truth receipt"
```

---

### Task 6: Add the stable CLI and prove zero-network/zero-write behavior hermetically

**Files:**
- Create: `scripts/session_truth_receipt.py`
- Create: `tests/test_session_truth_cli.py`

**Interfaces:**
- Consumes Tasks 1-5.
- Produces CLI:

```text
python3 scripts/session_truth_receipt.py \
  --workstream WS:CHAIRMAN-CONTROL-ROOM \
  --github-snapshot /path/github.json \
  --linear-snapshot /path/linear.json \
  --slack-snapshot /path/slack.json \
  --executive-snapshot /path/executive.json \
  --identity-snapshot /path/identity.json \
  --macro-root /path/to/macro \
  --expected-skillpack-sha <40hex> \
  --json
```

- [ ] **Step 1: Write CLI argument and output tests**

CLI flags:

- repeatable `--workstream WS:<KEY>` (at least one required);
- repeatable `--repository owner/name`;
- repeatable `--linear MAS-###`;
- optional `--operation-key`;
- `--requires-executive` boolean;
- required snapshot flags for GitHub, Linear, Slack, Executive and identity in R1;
- optional `--macro-root` using the existing resolver ladder;
- required `--expected-skillpack-sha` so a branch checkout cannot masquerade as protected master;
- `--now` freezes observation time in tests/evidence;
- `--json` emits canonical pretty JSON; default emits text.

Malformed contract/snapshot/Agent OS direct-record failure exits `2` with a bounded non-secret error on stderr. Source *unavailability* represented by a valid unavailable snapshot still exits `0` and emits a degraded receipt.

- [ ] **Step 2: Write the network prohibition test**

Monkeypatch `socket.socket` and `socket.create_connection` to raise `AssertionError("network forbidden")`; run the CLI with local fixture snapshots and a local Agent OS stub. The CLI must exit `0` and emit a receipt.

- [ ] **Step 3: Write the filesystem mutation test**

Snapshot every file hash under the fake Macro checkout and fixture snapshot directory before and after the CLI run. Assert byte equality and absence of new files.

- [ ] **Step 4: Write the two-run semantic determinism test**

Run the CLI twice with identical source documents but different `--now` values. Parse both JSON documents and assert:

```python
assert first["semantic_hash"] == second["semantic_hash"]
assert semantic_projection(first) == semantic_projection(second)
```

Then change exactly one GitHub PR `head_sha`; assert semantic hash changes and the bounded corresponding finding/subject changes without unrelated order drift.

- [ ] **Step 5: Run CLI tests RED**

Run: `python -m pytest tests/test_session_truth_cli.py -q`

Expected: script import/file failure.

- [ ] **Step 6: Implement the CLI**

Match the existing root bootstrap idiom in `scripts/ceo_boot_packet.py`:

```python
_ROOT = Path(__file__).resolve().parents[1]
if os.fspath(_ROOT) not in sys.path:
    sys.path.insert(0, os.fspath(_ROOT))
```

Acquisition order:

1. validate/record scope;
2. `collect_skillpack(_ROOT, expected_sha=...)`;
3. `collect_agentos(...)` for exact workstreams;
4. load and normalize the five external snapshots;
5. assemble `mastermind.session_truth_inputs.v1`;
6. call `build_receipt()`;
7. emit JSON or deterministic text.

There is no retry/fallback to a second carrier/source. A malformed required snapshot stops the run; a valid explicit unavailable snapshot remains visible in the receipt.

- [ ] **Step 7: Run Task 6 tests and the full relevant regression set GREEN**

Run:

```bash
python -m pytest \
  tests/test_session_truth_contract.py \
  tests/test_session_truth_acquire.py \
  tests/test_session_truth_snapshots.py \
  tests/test_session_truth_rules.py \
  tests/test_session_truth_receipt.py \
  tests/test_session_truth_cli.py \
  tests/test_ceo_boot_packet.py -q
```

Expected: PASS.

Commit:

```bash
git add scripts/session_truth_receipt.py tests/test_session_truth_cli.py
git commit -m "feat(exec): expose read-only session truth CLI"
```

---

### Task 7: Produce current-estate proof, adversarial falsifiers and hosted-CI evidence

**Files:**
- Create: `review_evidence/session_truth/r1/current_estate_inputs.v1.json`
- Create: `review_evidence/session_truth/r1/receipt_run1.json`
- Create: `review_evidence/session_truth/r1/receipt_run2.json`
- Create: `review_evidence/session_truth/r1/proof.md`
- Modify only if needed for test discovery: none expected.

**Interfaces:**
- Consumes the finished CLI.
- Produces immutable sanitized evidence only; these files do not become current-state authorities.

- [ ] **Step 1: Re-pin source law and collision state before the proof run**

Record in `proof.md`:

- protected Mastermind master SHA;
- exact implementation PR/head SHA;
- exact Macro main SHA and Agent OS checkout SHA used;
- exact Skillpack schema/version/minimum bootstrap major;
- current status of architecture PR #169 and any overlapping implementation PR;
- statement that `docs/sol_skills/**`, CeoIngress, Executive lifecycle stores, Linear projector, SOL_STATE and Agent Relay were untouched.

If protected architecture/source law changed materially since implementation pickup, stop and return to Sol before producing acceptance proof.

- [ ] **Step 2: Build sanitized normalized snapshots from current read-only owner observations**

Use current GitHub/Linear/Slack/Executive/identity reads to populate only the R1 normalized fields. Do not copy message bodies or secrets. `current_estate_inputs.v1.json` is evidence of that bounded observation, timestamped and revision-bound.

At minimum include the known live families relevant to this architecture:

- architecture carrier #169;
- Macro Agent OS reconciliation carrier #6509 if still live/relevant;
- one Linear false-green/proof-open representative (MAS-28 family if still current);
- `#agent-dispatch` receiver state and one runnable-delivery/no-receiver example if still current;
- Executive unavailable/current state exactly as current C1 capability supports;
- at least one typed unknown identity if current registry still contains one.

If a historical example is no longer current, do not manufacture it into the current snapshot; exercise it with a synthetic falsifier fixture instead.

- [ ] **Step 3: Run the real current-estate receipt twice**

Use the same exact normalized observations for both runs while changing only the observation envelope time.

```bash
python3 scripts/session_truth_receipt.py <exact-current-args> --now 2026-08-27T06:00:00Z --json > /tmp/receipt1.json
python3 scripts/session_truth_receipt.py <same-exact-current-args> --now 2026-08-27T06:01:00Z --json > /tmp/receipt2.json
```

Copy the sanitized outputs into `receipt_run1.json` and `receipt_run2.json` and assert with a one-shot Python command that semantic hashes and semantic projections match.

- [ ] **Step 4: Run the required adversarial falsifier subset for R1**

At minimum prove these mutations against the pure core:

1. Linear says Done while proof remains open -> `FALSE_LINEAR_COMPLETION` and no green admission for a completion-bearing modification;
2. Slack runnable delivery with no eligible receiver -> `SLACK_TRANSPORT_WITHOUT_RECEIVER`;
3. ChatGPT CEO principal targeted as worker -> `CEO_SEAT_USED_AS_WORKER`;
4. Executive required but unavailable/stale -> `RUNTIME_STATE_UNAVAILABLE` or `RUNTIME_STATE_STALE`;
5. same operation key on two carriers -> `DUPLICATE_OPERATION_CARRIER`;
6. same operation key with changed payload/effect unknown -> refusal-class finding;
7. optional visibility source unavailable while canonical read-only sources are healthy -> `GROUNDING_PARTIAL`, not blanket refusal;
8. fully consistent read-only case -> `GROUNDING_COMPLETE`.

Record exact pytest node IDs and PASS output summary in `proof.md`.

- [ ] **Step 5: Run hosted CI on the exact final head**

Required commands locally before push:

```bash
python -m pytest tests/test_session_truth_*.py tests/test_ceo_boot_packet.py -q
python -m compileall -q control_plane scripts
```

Push the exact head and wait for Mastermind hosted CI. Do not call the wave accepted merely because local tests pass.

- [ ] **Step 6: Commit evidence only after the proof is complete**

```bash
git add review_evidence/session_truth/r1
git commit -m "evidence(exec): prove deterministic session truth receipt"
```

The evidence commit must not change `control_plane/`, `scripts/` or tests. If code changes are needed after proof, create a new code commit and rerun the affected proof on the new exact head.

- [ ] **Step 7: Return the exact Sol review packet**

Return:

```text
repo: mastermindx-market-intelligence/Mastermind
implementation PR: <number>
exact head SHA: <40hex>
base/master SHA used: <40hex>
changed files: <exact list>
R1 capability: read-only Session Truth Receipt
hosted CI: <run id + conclusion>
real current-estate receipt semantic hash: <sha256:...>
second-run semantic hash: <same sha256:...>
findings observed on current estate: <codes only + subjects>
adversarial falsifiers: <pytest node IDs + PASS>
zero-network proof: PASS|FAIL
zero-Macro-write proof: PASS|FAIL
external mutations performed by receipt generation: zero
known gaps: <bounded list or none>
next action: Sol adversarial REVIEW_RETURN against the approved spec; no R2/R3/R4/R5/R6 mutation begins until R1 is accepted.
```

---

## Self-review checklist for the implementer before return

- Every R1 required finding code has both a positive and negative test.
- No rule uses title similarity or majority voting.
- `semantic_hash` excludes only observation-envelope clock fields; source revisions/facts remain covered.
- Agent OS direct context comes only through Macro's canonical `compile-context` reader.
- No file under `docs/sol_skills/**` changed.
- No network call exists in `control_plane/session_truth*.py` or the pure CLI path.
- No receipt generation writes into Macro, Linear, Slack, GitHub or Executive OS.
- No durable current-state database/cache/cursor/retry ledger was created.
- Missing optional source degrades precisely; missing required Executive state blocks only when the scope requires it.
- Slack delivery is never rendered as ACK/execution.
- Linear `Done` cannot override proof-open completion law.
- Exact-head hosted CI and current-estate two-run semantic proof exist before Sol acceptance.

## Stop condition

R1 stops when the exact implementation head passes hosted CI, a real current-estate read-only receipt has been produced twice with identical semantic projection/hash for unchanged observations, the required adversarial falsifiers pass, and Sol has a complete REVIEW_RETURN packet. Do not absorb MAS-28/65/67, MAS-103/104, MAS-109/PR #155, MAS-127, Linear apply, Slack app installation or Executive write-path work into this carrier.

# Session Truth Receipt R1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a production-relevant, read-only `mastermind.session_truth_receipt.v1` so a fresh Sol can deterministically compare current Agent OS, GitHub, Linear, Slack and Executive observations, surface typed drift, and compute a safe session admission mode without mutating a source or creating another truth store.

**Architecture:** Acquisition and reconciliation stay separate. Mastermind owns stdlib-only reconciliation modules and a thin CLI. Agent OS acquisition calls Macro's canonical zero-network `scripts/agentos.py compile-context`; GitHub, Linear, Slack, Executive and identity observations enter as strict read-only JSON snapshots. The receipt is immutable evidence bound to exact revisions, not a mutable lifecycle, queue, retry, identity, memory or synchronization authority.

**Tech Stack:** Python >=3.11, standard-library-only `control_plane` modules, existing Macro Agent OS CLI, pytest >=8,<10, GitHub Actions hosted CI.

**Spec:** `docs/superpowers/specs/2026-08-27-cross-plane-reconciliation-design.md`

## Global Constraints

- Protected basis at plan authoring: `mastermindx-market-intelligence/Mastermind@be68ec881460aa60d7d77cdb69f7c1cae81f6310`, Skillpack `mastermind.sol_skillpack.v1` v1.0.0, minimum bootstrap major 1.
- Approved architecture: Mastermind PR #169, spec commit `0aad273340a5f788013d460770feb621ea688846`.
- R1 is read-only: no Linear, Slack or Executive mutation and no GitHub lifecycle mutation caused by receipt generation.
- Pure reconciliation performs zero network I/O.
- `control_plane` remains importable with stdlib only; add no runtime dependency.
- Agent OS parser/schema ownership remains in Macro. Use `scripts/agentos.py compile-context`; do not parse Agent OS YAML/frontmatter in Mastermind.
- Do not modify `docs/sol_skills/**`; PR #147 owns the separate Skillpack candidate.
- Do not create another CEO ingress, Executive Job/Attempt/Worker store, Agent OS registry, Linear projector, PR metadata grammar, SOL_STATE lane, Agent Relay, Slack queue/inbox/retry ledger, or durable reconciliation database.
- Missing sources remain explicit unavailable/unknown states; never normalize them to empty/healthy.
- Slack delivery never implies ACK, runtime claim or execution.
- Linear `Done` never outranks the declared GitHub/Agent OS/Executive completion owner.
- Unknown seat/service identity remains unknown; string/name similarity cannot bind identities.
- Same operation key with changed canonical payload is conflict/refusal, never a second operation.
- Model prose may summarize a finished receipt but has zero authority over facts, findings, severity, identity or admission.

## File Structure

Use flat sibling modules under `control_plane/` so no package-discovery change is needed:

- `control_plane/session_truth_contract.py` — schemas, validation, canonical JSON, hashing.
- `control_plane/session_truth_acquire.py` — Skillpack + Agent OS read acquisition.
- `control_plane/session_truth_snapshots.py` — strict external snapshot normalization and secret-key rejection.
- `control_plane/session_truth_rules.py` — exact-key indexes and drift detectors.
- `control_plane/session_truth.py` — receipt assembly, admission, semantic projection and text rendering.
- `scripts/session_truth_receipt.py` — stable CLI.
- `tests/test_session_truth_contract.py`
- `tests/test_session_truth_acquire.py`
- `tests/test_session_truth_snapshots.py`
- `tests/test_session_truth_rules.py`
- `tests/test_session_truth_receipt.py`
- `tests/test_session_truth_cli.py`
- `tests/fixtures/session_truth/` — synthetic bounded snapshots.
- `review_evidence/session_truth/r1/` — sanitized immutable proof artifacts only.

---

### Task 1: Contract, canonical serialization and semantic hash

**Files:**
- Create: `control_plane/session_truth_contract.py`
- Create: `tests/test_session_truth_contract.py`

**Interfaces:**
- `INPUT_SCHEMA = "mastermind.session_truth_inputs.v1"`
- `RECEIPT_SCHEMA = "mastermind.session_truth_receipt.v1"`
- `SessionTruthContractError(ValueError)`
- `canonical_json(value: object) -> str`
- `semantic_hash(value: object) -> str`
- `validate_input_document(doc: Mapping[str, Any]) -> dict[str, Any]`

- [ ] **Step 1: Write failing contract tests**

```python
from copy import deepcopy
import pytest
from control_plane.session_truth_contract import (
    INPUT_SCHEMA, RECEIPT_SCHEMA, SessionTruthContractError,
    canonical_json, semantic_hash, validate_input_document,
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


def test_validation_never_mutates_caller_input():
    doc = minimal_input()
    before = deepcopy(doc)
    validate_input_document(doc)
    assert doc == before


def test_unknown_top_level_key_fails_closed():
    doc = minimal_input()
    doc["shadow_truth_store"] = {}
    with pytest.raises(SessionTruthContractError, match="unknown top-level key"):
        validate_input_document(doc)
```

- [ ] **Step 2: Run RED**

Run: `python -m pytest tests/test_session_truth_contract.py -q`

Expected: import failure because the module does not exist.

- [ ] **Step 3: Implement stdlib-only serialization/hash primitives**

```python
import hashlib
import json

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
    return "sha256:" + digest
```

`validate_input_document()` must enforce exact top-level keys, the exact schema, `WS:`/`MAS-`/`owner/name` identifier grammar, 40-hex SHA shape, boolean `available`, explicit `reason` when unavailable, and a defensive deep copy. It must not insert a healthy default for any missing source.

- [ ] **Step 4: Add negative-shape tests**

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

- [ ] **Step 5: Run GREEN and commit**

Run: `python -m pytest tests/test_session_truth_contract.py -q`

Commit:

```bash
git add control_plane/session_truth_contract.py tests/test_session_truth_contract.py
git commit -m "feat(exec): freeze session truth receipt contract"
```

---

### Task 2: Protected Skillpack and canonical Agent OS acquisition

**Files:**
- Create: `control_plane/session_truth_acquire.py`
- Create: `tests/test_session_truth_acquire.py`

**Interfaces:**
- Consume `control_plane.ceo_boot_packet.resolve_macro_root` and `git_sha`.
- `collect_skillpack(repo_root: Path, expected_sha: str | None, bootstrap_major: int = 1) -> dict[str, Any]`
- `collect_agentos(macro_root_flag: str | None, workstreams: Sequence[str], *, environ: Mapping[str, str], now: str | None, timeout: float = 60.0) -> dict[str, Any]`
- `AcquisitionError(RuntimeError)` for malformed canonical output; missing join capability is a valid unavailable observation.

- [ ] **Step 1: Write Skillpack acquisition tests**

```python
from control_plane.session_truth_acquire import collect_skillpack


def test_collect_skillpack_requires_exact_sha(tmp_path, monkeypatch):
    repo = tmp_path / "Mastermind"
    index = repo / "docs" / "sol_skills" / "INDEX.md"
    index.parent.mkdir(parents=True)
    index.write_text(
        "---\nschema: mastermind.sol_skillpack.v1\n"
        "skillpack_version: 1.0.0\nminimum_bootstrap_major: 1\nskill: index\n---\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("control_plane.session_truth_acquire.git_sha", lambda p: "a" * 40)
    got = collect_skillpack(repo, expected_sha="a" * 40, bootstrap_major=1)
    assert got["sha"] == "a" * 40
    assert got["schema"] == "mastermind.sol_skillpack.v1"
    assert got["version"] == "1.0.0"
    assert got["minimum_bootstrap_major"] == 1
    assert got["available"] is True
```

Add exact-SHA mismatch and incompatible-bootstrap tests; neither may relabel the local checkout as protected truth.

- [ ] **Step 2: Write Agent OS read-only write-trap test**

Create a temporary Macro fixture whose `scripts/agentos.py` accepts only `compile-context --workstream TARGET --now 2026-08-27T05:00:00Z`, emits `context_bundle.v1`, and creates `.ILLEGAL_WRITE` if any non-read contract is used.

```python
def test_agentos_uses_canonical_compile_context_without_writes(tmp_path):
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

- [ ] **Step 3: Run RED**

Run: `python -m pytest tests/test_session_truth_acquire.py -q`

- [ ] **Step 4: Implement the narrow Skillpack scalar-frontmatter reader**

Parse only the four scalar INDEX header fields before the second `---`; reject duplicate/non-scalar/missing fields. This is not a general YAML parser and must never be used for Agent OS.

- [ ] **Step 5: Implement Agent OS acquisition through Macro**

For each exact requested workstream, strip only `WS:` and invoke:

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

Use Macro as `cwd`, bounded timeout, `capture_output=True`, `text=True`, `check=False`. Preserve `context_bundle.v1` verbatim. Unknown/malformed requested direct record fails closed with `AcquisitionError`; missing Macro root returns `available=False` plus `reason="AGENTOS_READ_PATH_UNAVAILABLE"`.

- [ ] **Step 6: Run GREEN with existing bridge regression and commit**

Run: `python -m pytest tests/test_session_truth_acquire.py tests/test_ceo_boot_packet.py -q`

Commit:

```bash
git add control_plane/session_truth_acquire.py tests/test_session_truth_acquire.py
git commit -m "feat(exec): add canonical read-only grounding acquisition"
```

---

### Task 3: Strict external snapshot normalization

**Files:**
- Create: `control_plane/session_truth_snapshots.py`
- Create: `tests/test_session_truth_snapshots.py`
- Create: `tests/fixtures/session_truth/github_minimal.json`
- Create: `tests/fixtures/session_truth/linear_minimal.json`
- Create: `tests/fixtures/session_truth/slack_minimal.json`
- Create: `tests/fixtures/session_truth/executive_unavailable.json`
- Create: `tests/fixtures/session_truth/identity_minimal.json`

**Interfaces:**
- `GITHUB_SCHEMA = "mastermind.github_observation.v1"`
- `LINEAR_SCHEMA = "mastermind.linear_observation.v1"`
- `SLACK_SCHEMA = "mastermind.slack_observation.v1"`
- `EXECUTIVE_SCHEMA = "mastermind.executive_observation.v1"`
- `IDENTITY_SCHEMA = "mastermind.identity_observation.v1"`
- `load_snapshot(path: Path, expected_schema: str) -> dict[str, Any]`
- `normalize_github`, `normalize_linear`, `normalize_slack`, `normalize_executive`, `normalize_identities`

- [ ] **Step 1: Create exact GitHub fixture and normalization test**

Use this PR row shape:

```json
{
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
  "operation_key": "cross-plane-reconciliation-20260827-sol-001",
  "pickup_head_sha": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
}
```

Assert array order canonicalizes, integer/string coercion is rejected, unknown enum values fail closed, and JSON `null` stays Python `None`.

- [ ] **Step 2: Add recursive secret-key rejection**

Reject case-insensitive key names `token`, `access_token`, `authorization`, `cookie`, `secret`, `password`. Do not reject harmless string values containing those words.

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

- [ ] **Step 3: Run RED**

Run: `python -m pytest tests/test_session_truth_snapshots.py -q`

- [ ] **Step 4: Implement exact normalized fields**

GitHub PR rows: `repository, number, state, draft, head_sha, base_sha, merge_sha, ci, workstream, linear, portfolio_mode, wave, authority, completion, proof_state, operation_key, pickup_head_sha`.

Linear issue rows: `id, status, parent_id, workstream, completion, projection_revision, github_relations, updated_at`; relation class is one of `merge_is_done, contributing, architecture_evidence, program_gate, ignored_wrong_id`.

Slack message rows: `channel_id, ts, thread_ts, sender_id, operation_key, payload_hash, transport, message_class, target_principal_id, delivered, acked, receiver_eligible, ack_required, created_at, source_law_sha, freeze_at`. Channel rows carry `channel_id` and `member_ids`; omit private message bodies.

Executive rows: explicit `available`; when available, `observed_at, fresh, do_not_submit, grounding_sha, operations`. Operation rows carry `operation_key, payload_hash, status, effect_unknown, carrier` only.

Identity rows: `seat, slack_principal, github_account, linear_actor, executive_worker, provider_realm, role, service_actor`; every binding field can be `None` and is never guessed.

- [ ] **Step 5: Run GREEN and commit**

Run: `python -m pytest tests/test_session_truth_snapshots.py -q`

Commit:

```bash
git add control_plane/session_truth_snapshots.py tests/test_session_truth_snapshots.py tests/fixtures/session_truth
git commit -m "feat(exec): normalize cross-plane read snapshots"
```

---

### Task 4: Complete deterministic drift taxonomy

**Files:**
- Create: `control_plane/session_truth_rules.py`
- Create: `tests/test_session_truth_rules.py`

**Interfaces:**
- `build_indexes(inputs: Mapping[str, Any]) -> dict[str, Any]`
- `detect_findings(inputs: Mapping[str, Any]) -> list[dict[str, Any]]`
- Finding keys: `code, severity, canonical_owner, subject, source_a, source_b, repair_owner, modification_consequence, details`.

- [ ] **Step 1: Freeze one registry entry per required finding code**

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

If exact implementation evidence shows a fixed severity conflicts with the approved FATAL/BLOCKING definition, stop and return the contradiction to Sol; do not silently alter architecture.

- [ ] **Step 2: Build `healthy_inputs()` and positive/negative tests for every code**

Each positive case changes only the minimum fields needed:

- `STALE_LINEAR_PROJECTION`: projection revision differs from current Agent OS source SHA.
- `FALSE_LINEAR_COMPLETION`: Linear Done + merged implementation + `proof_state=open` + completion is not merge-is-done.
- `MISSING_LINEAR_PROJECTION`: scoped Agent OS binding names a MAS ID absent from Linear.
- `LINEAR_PARENT_CHILD_DIVERGENCE`: parent Done while explicit completion-bearing child remains nonterminal.
- `ORPHAN_LINEAR_ISSUE`: issue claims scoped WS absent from Agent OS context.
- `BUILD_VISIBILITY_STALE`: selected GitHub/Linear revision is newer than latest matching build-events observation.
- `GITHUB_PR_UNBOUND`: materially open PR has no WS/Linear/completion binding.
- `GITHUB_MERGE_WITH_PROOF_OPEN`: merged PR with non-merge completion and open proof.
- `ORPHAN_GITHUB_CARRIER`: PR WS binding absent from scoped Agent OS context.
- `MULTIPLE_ACTIVE_CARRIERS`: two open PRs share the same non-null operation key.
- `CARRIER_HEAD_MOVED`: current head SHA differs from pickup head SHA.
- `PR_BINDING_CONFLICT`: PR WS/Linear metadata conflicts with explicit canonical binding.
- `AGENTOS_GITHUB_DISAGREEMENT`: owner-specific implementation fact disagrees between direct org record and GitHub evidence.
- `STALE_HANDOFF`: older handoff action is overtaken by newer direct record/decision evidence.
- `SUPERSEDED_NEXT_ACTION`: current direct action is explicitly superseded by newer accepted Agent OS source.
- `DIRECT_GENERATED_STATE_DIVERGENCE`: optional generated Agent OS view disagrees with direct context revision/state.
- `SLACK_TRANSPORT_WITHOUT_RECEIVER`: runnable delivery + `receiver_eligible=false`.
- `SLACK_TRANSPORT_WITHOUT_ACK`: eligible active-session dialogue + `ack_required=true` + `acked=false`.
- `CEO_SEAT_USED_AS_WORKER`: runnable worker pickup targets a principal bound only to role `sol_ceo`.
- `DUPLICATE_OPERATION_CARRIER`: same operation key appears on distinct active carriers.
- `POST_FREEZE_DISPATCH_VIOLATION`: runnable pickup created after `freeze_at` with unavailable receiver.
- `RUNTIME_STATE_UNAVAILABLE`: `requires_executive=true` + Executive unavailable.
- `RUNTIME_STATE_STALE`: Executive available but `fresh=false` for Executive-required scope.
- `SLACK_ACK_WITHOUT_EXECUTIVE_STATE`: Slack ACK exists for canonical-execution operation but Executive has no matching operation.
- `EXECUTIVE_GROUNDING_DIVERGED`: Executive grounding SHA differs from required exact Mastermind grounding SHA.
- `UNKNOWN_SEAT_IDENTITY`: requested action depends on a required null service binding.
- `SERVICE_ACTOR_UNBOUND`: requested service actor has no exact registry binding.
- `ACTOR_ROLE_COLLISION`: same principal has conflicting service/human or CEO/worker role bindings.

For every positive test, the unchanged `healthy_inputs()` case must also assert that code is absent.

- [ ] **Step 3: Add anti-majority-vote and anti-name-binding regressions**

```python
def test_two_projections_cannot_outvote_owner(healthy_inputs):
    doc = healthy_inputs()
    doc["linear"]["issues"][0]["status"] = "Done"
    doc["slack"]["messages"].append(done_visibility_message())
    assert "FALSE_LINEAR_COMPLETION" in {f["code"] for f in detect_findings(doc)}


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

- [ ] **Step 4: Run RED**

Run: `python -m pytest tests/test_session_truth_rules.py -q`

- [ ] **Step 5: Implement exact-key indexes and pure detectors**

`_finding()` reads fixed severity/owners from the registry. Severity consequence is fixed: FATAL=`new_modification_refused`, BLOCKING=`requested_modification_blocked`, WARNING=`repair_debt_visible`, INFO=`visibility_only`.

`detect_findings()` sorts by severity order FATAL, BLOCKING, WARNING, INFO; then code; then subject. No detector performs network, filesystem writes, fuzzy title matching or majority voting.

- [ ] **Step 6: Run GREEN and commit**

Run: `python -m pytest tests/test_session_truth_rules.py -q`

Commit:

```bash
git add control_plane/session_truth_rules.py tests/test_session_truth_rules.py
git commit -m "feat(exec): classify cross-plane drift deterministically"
```

---

### Task 5: Receipt assembly, admission and rendering

**Files:**
- Create: `control_plane/session_truth.py`
- Create: `tests/test_session_truth_receipt.py`

**Interfaces:**
- `build_receipt(inputs: Mapping[str, Any], *, observed_started_at: str, observed_ended_at: str) -> dict[str, Any]`
- `semantic_projection(receipt: Mapping[str, Any]) -> dict[str, Any]`
- `compute_admission(inputs: Mapping[str, Any], findings: Sequence[Mapping[str, Any]]) -> dict[str, Any]`
- `render_receipt(receipt: Mapping[str, Any]) -> str`

- [ ] **Step 1: Freeze admission precedence tests**

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

Law: any FATAL => `MODIFICATION_REFUSED`; applicable BLOCKING => `DIALOGUE_ONLY`; no fatal/blocking but optional source unavailable or WARNING => `GROUNDING_PARTIAL`; otherwise `GROUNDING_COMPLETE`.

- [ ] **Step 2: Freeze semantic replay test**

```python
def test_envelope_clock_does_not_change_semantic_hash(healthy_inputs):
    one = build_receipt(healthy_inputs(), observed_started_at="2026-08-27T05:00:00Z", observed_ended_at="2026-08-27T05:00:01Z")
    two = build_receipt(healthy_inputs(), observed_started_at="2026-08-27T05:10:00Z", observed_ended_at="2026-08-27T05:10:01Z")
    assert one["semantic_hash"] == two["semantic_hash"]
    assert semantic_projection(one) == semantic_projection(two)
    assert one["observation"] != two["observation"]
```

Only acquisition-envelope clock fields and `semantic_hash` itself are excluded from the semantic projection. Source revisions, source timestamps, facts, findings, admission and scope remain covered.

- [ ] **Step 3: Run RED**

Run: `python -m pytest tests/test_session_truth_receipt.py -q`

- [ ] **Step 4: Implement exact receipt shape**

```python
receipt = {
    "schema": RECEIPT_SCHEMA,
    "scope": normalized["scope"],
    "skillpack": normalized["skillpack"],
    "observation": {"started_at": observed_started_at, "ended_at": observed_ended_at},
    "observations": {
        "agentos": normalized["agentos"],
        "github": normalized["github"],
        "linear": normalized["linear"],
        "slack": normalized["slack"],
        "executive": normalized["executive"],
        "identities": normalized["identities"],
    },
    "findings": findings,
    "admission": admission,
}
receipt["semantic_hash"] = semantic_hash(semantic_projection(receipt))
```

Do not include raw private message bodies, environment variables, credentials or arbitrary subprocess stderr.

- [ ] **Step 5: Implement deterministic text rendering**

A healthy fixture must render exactly the same text across runs except for no observation-envelope timestamps, because text is a semantic view. Example prefix:

```text
SESSION TRUTH RECEIPT
mode: GROUNDING_COMPLETE
semantic_hash: sha256:2f5b0b1df6f4d9cf5b3ff8668c6242478656144339e2411228a017c201f953e2
findings: 0 (FATAL 0 / BLOCKING 0 / WARNING 0 / INFO 0)
modification_safe: true
```

The test computes the actual hash; the literal hash above is only the fixed example string for a dedicated fixture. Never render an unavailable source as healthy or a Slack delivery as execution.

- [ ] **Step 6: Run GREEN and commit**

Run: `python -m pytest tests/test_session_truth_receipt.py tests/test_session_truth_rules.py -q`

Commit:

```bash
git add control_plane/session_truth.py tests/test_session_truth_receipt.py
git commit -m "feat(exec): assemble deterministic session truth receipt"
```

---

### Task 6: Stable CLI plus zero-network/zero-write proof

**Files:**
- Create: `scripts/session_truth_receipt.py`
- Create: `tests/test_session_truth_cli.py`

**Interfaces:**
- Stable CLI reads five snapshot files, exact scoped workstreams and protected-SHA expectation, then emits JSON or text.

- [ ] **Step 1: Freeze CLI contract in tests**

Required flags:

- repeatable `--workstream`, at least one;
- repeatable `--repository`;
- repeatable `--linear`;
- optional `--operation-key`;
- `--requires-executive`;
- `--github-snapshot`, `--linear-snapshot`, `--slack-snapshot`, `--executive-snapshot`, `--identity-snapshot`;
- optional `--macro-root` using the existing resolver ladder;
- required `--expected-skillpack-sha`;
- optional `--now` for reproducibility;
- `--json` for JSON, otherwise text.

The test command uses exact synthetic paths and a concrete test SHA:

```bash
python3 scripts/session_truth_receipt.py \
  --workstream WS:CHAIRMAN-CONTROL-ROOM \
  --repository mastermindx-market-intelligence/Mastermind \
  --github-snapshot tests/fixtures/session_truth/github_minimal.json \
  --linear-snapshot tests/fixtures/session_truth/linear_minimal.json \
  --slack-snapshot tests/fixtures/session_truth/slack_minimal.json \
  --executive-snapshot tests/fixtures/session_truth/executive_unavailable.json \
  --identity-snapshot tests/fixtures/session_truth/identity_minimal.json \
  --expected-skillpack-sha aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa \
  --now 2026-08-27T05:00:00Z \
  --json
```

Malformed contracts/snapshots/direct Agent OS requests exit 2 with bounded non-secret stderr. A valid explicit unavailable source still exits 0 and appears degraded in the receipt.

- [ ] **Step 2: Add network prohibition test**

Patch `socket.socket` and `socket.create_connection` to raise `AssertionError("network forbidden")`; run the CLI using local fixtures and the local Agent OS stub. It must exit 0.

- [ ] **Step 3: Add filesystem mutation test**

Hash every file under the fake Macro checkout and fixture directory before/after CLI execution. Assert exact equality and no new file.

- [ ] **Step 4: Add two-run semantic determinism test**

Run twice with identical source documents and different `--now`; parsed `semantic_hash` and `semantic_projection()` must match. Change only one GitHub `head_sha`; the semantic hash must change and unrelated ordering must not.

- [ ] **Step 5: Run RED**

Run: `python -m pytest tests/test_session_truth_cli.py -q`

- [ ] **Step 6: Implement CLI with existing script bootstrap idiom**

```python
_ROOT = Path(__file__).resolve().parents[1]
if os.fspath(_ROOT) not in sys.path:
    sys.path.insert(0, os.fspath(_ROOT))
```

Order: build scope -> collect Skillpack -> collect Agent OS -> load/normalize five snapshots -> validate complete input -> build receipt -> emit. There is no retry/failover to another carrier/source.

- [ ] **Step 7: Run focused regression GREEN and commit**

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

Commit:

```bash
git add scripts/session_truth_receipt.py tests/test_session_truth_cli.py
git commit -m "feat(exec): expose read-only session truth CLI"
```

---

### Task 7: Current-estate proof and exact-head hosted CI

**Files:**
- Create: `review_evidence/session_truth/r1/github_observation.v1.json`
- Create: `review_evidence/session_truth/r1/linear_observation.v1.json`
- Create: `review_evidence/session_truth/r1/slack_observation.v1.json`
- Create: `review_evidence/session_truth/r1/executive_observation.v1.json`
- Create: `review_evidence/session_truth/r1/identity_observation.v1.json`
- Create: `review_evidence/session_truth/r1/receipt_run1.json`
- Create: `review_evidence/session_truth/r1/receipt_run2.json`
- Create: `review_evidence/session_truth/r1/proof.md`

**Interfaces:**
- Evidence is immutable, sanitized and revision-bound; it never becomes current-state authority.

- [ ] **Step 1: Re-pin source law and collision state**

Before evidence generation, record the actual outputs of:

```bash
git rev-parse HEAD
git rev-parse origin/master
git -C "$MASTERMIND_MACRO_ROOT" rev-parse HEAD
```

Also record the exact protected Skillpack schema/version/minimum bootstrap major and implementation PR number from the active GitHub carrier. If material source law moved after pickup, stop and return to Sol before acceptance proof.

- [ ] **Step 2: Create sanitized live observation files**

Populate the five observation JSON files from current read-only owner reads. Include only normalized R1 fields. Never include Slack message bodies, OAuth/API credentials, cookies, Authorization headers, environment secrets or provider credentials.

Current-estate evidence should include, when still current at proof time: architecture PR #169; Macro #6509 if still relevant; one proof-open/false-green representative; current `#agent-dispatch` receiver facts; exact current Executive availability; and any still-current typed unknown identity. If one historical example is no longer true, keep it out of the live snapshot and cover it with the synthetic falsifier tests.

- [ ] **Step 3: Run the real receipt twice with exact commands**

```bash
MASTER_SHA="$(git rev-parse origin/master)"
COMMON=(
  --workstream WS:CHAIRMAN-CONTROL-ROOM
  --repository mastermindx-market-intelligence/Mastermind
  --github-snapshot review_evidence/session_truth/r1/github_observation.v1.json
  --linear-snapshot review_evidence/session_truth/r1/linear_observation.v1.json
  --slack-snapshot review_evidence/session_truth/r1/slack_observation.v1.json
  --executive-snapshot review_evidence/session_truth/r1/executive_observation.v1.json
  --identity-snapshot review_evidence/session_truth/r1/identity_observation.v1.json
  --expected-skillpack-sha "$MASTER_SHA"
  --json
)
python3 scripts/session_truth_receipt.py "${COMMON[@]}" --now 2026-08-27T06:00:00Z > review_evidence/session_truth/r1/receipt_run1.json
python3 scripts/session_truth_receipt.py "${COMMON[@]}" --now 2026-08-27T06:01:00Z > review_evidence/session_truth/r1/receipt_run2.json
```

Verify semantic equality with:

```bash
python3 - <<'PY'
import json
from pathlib import Path
from control_plane.session_truth import semantic_projection
root = Path("review_evidence/session_truth/r1")
a = json.loads((root / "receipt_run1.json").read_text())
b = json.loads((root / "receipt_run2.json").read_text())
assert a["semantic_hash"] == b["semantic_hash"]
assert semantic_projection(a) == semantic_projection(b)
print(a["semantic_hash"])
PY
```

- [ ] **Step 4: Run R1 adversarial falsifiers**

Required cases:

1. Linear Done while proof remains open -> `FALSE_LINEAR_COMPLETION`.
2. Slack runnable delivery without eligible receiver -> `SLACK_TRANSPORT_WITHOUT_RECEIVER`.
3. CEO principal targeted as worker -> `CEO_SEAT_USED_AS_WORKER`.
4. Executive required but unavailable/stale -> `RUNTIME_STATE_UNAVAILABLE` or `RUNTIME_STATE_STALE`.
5. same operation key on two carriers -> `DUPLICATE_OPERATION_CARRIER`.
6. same operation key with changed payload/effect unknown -> refusal-class finding.
7. optional visibility source unavailable while canonical read-only sources are healthy -> `GROUNDING_PARTIAL`, not blanket refusal.
8. fully consistent read-only case -> `GROUNDING_COMPLETE`.

Record exact pytest node IDs and PASS results in `proof.md`.

- [ ] **Step 5: Run local full R1 proof and push exact head**

```bash
python -m pytest tests/test_session_truth_*.py tests/test_ceo_boot_packet.py -q
python -m compileall -q control_plane scripts
```

Push the exact head. Hosted Mastermind CI must be green on that head before acceptance.

- [ ] **Step 6: Commit evidence only after proof**

```bash
git add review_evidence/session_truth/r1
git commit -m "evidence(exec): prove deterministic session truth receipt"
```

That evidence commit changes no `control_plane/`, `scripts/` or test file. Any later code/test change invalidates affected proof and requires rerun on the new exact head.

- [ ] **Step 7: Return the complete Sol review packet**

The return message must report literal values derived from the repository/tools, not guessed values:

- repository name `mastermindx-market-intelligence/Mastermind`;
- implementation PR number from the active PR carrier;
- exact result of `git rev-parse HEAD`;
- exact result of `git rev-parse origin/master` used for the run;
- exact changed-file list from the PR;
- hosted CI run ID and conclusion;
- semantic hash printed by the equality command above, twice;
- current-estate finding codes and subjects only;
- exact adversarial pytest node IDs and PASS status;
- zero-network proof status;
- zero-Macro-write proof status;
- statement that receipt generation performed zero external mutations;
- bounded known gaps;
- next action: Sol runs adversarial `REVIEW_RETURN` against the approved R1 spec before any R2/R3/R4/R5/R6 mutation begins.

---

## Self-Review Before Return

- Every required R1 finding code has positive and negative tests.
- No rule uses title similarity or majority voting.
- Semantic hash excludes only observation-envelope clock fields and itself; source revisions/facts remain covered.
- Agent OS direct context comes only through Macro `compile-context`.
- `docs/sol_skills/**` is unchanged.
- `control_plane/session_truth*.py` and the pure CLI path perform no network I/O.
- Receipt generation writes nothing into Macro, Linear, Slack, GitHub or Executive OS.
- No durable current-state DB/cache/cursor/retry ledger exists.
- Missing optional sources degrade precisely; required Executive absence blocks only scopes that require it.
- Slack delivery is never rendered as ACK/execution.
- Linear Done cannot override proof-open completion law.
- Exact-head hosted CI and two-run current-estate semantic proof exist before Sol acceptance.

## Stop Condition

R1 stops when the exact implementation head passes hosted CI, a sanitized real current-estate receipt is produced twice with identical semantic projection/hash for unchanged observations, required adversarial falsifiers pass, and Sol receives the complete `REVIEW_RETURN` packet. Do not absorb MAS-28/65/67, MAS-103/104, MAS-109/PR #155, MAS-127, Linear apply, Slack app installation or Executive write-path work into this carrier.

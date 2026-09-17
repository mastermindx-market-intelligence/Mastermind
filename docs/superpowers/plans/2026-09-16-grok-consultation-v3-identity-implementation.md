# Grok Consultation V3 Identity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a production-inert v3 consultation QUESTION identity for trusted `grok-bot` peers while preserving all accepted v1/v2 behavior.

**Architecture:** First reconcile the existing carrier with protected master and accepted W6-C2 head, deliberately superseding the obsolete v2 implementation. Then add v3 as a schema-specific QUESTION path, derive it from trusted peer bindings, persist it in INTENT, and prove that no target, transport, or provider effect was enabled.

**Tech Stack:** Python 3, pytest, existing Executive Runtime/Wake/Company MCP contracts, Git worktrees.

**Spec:** `docs/superpowers/specs/2026-09-16-grok-consultation-v3-identity-design.md`

## Global Constraints

- Preserve branch/carrier `sol/grok-consultation-v2-g1b-20260915`; do not create a replacement branch or PR.
- Preserve exact v1 and v2 grammar, fingerprints, accepted behavior, and refusal behavior.
- V3 is QUESTION-only and accepts exactly `grok-bot`.
- No target, config entry, credential, endpoint, route, implemented transport, provider call, native execution, deployment, or production claim.
- Keep PR draft and capability state `BUILT_NOT_PROVEN / PRODUCTION_INERT`.
- One logical source operation remains on this carrier until reconciled.

---

### Task 1: Reconcile the Historical Carrier onto Accepted Sources

**Files:**
- Preserve: all nine paths changed by prior head `b0b4b48d...`
- Add: `docs/superpowers/specs/2026-09-16-grok-consultation-v3-identity-design.md`
- Add: `docs/superpowers/plans/2026-09-16-grok-consultation-v3-identity-implementation.md`

**Interfaces:**
- Consumes: protected master `0fe8074f...`; accepted W6-C2 head `de190b2c...`.
- Produces: a passing dependency baseline on the same branch with obsolete v2 Grok semantics removed.

- [x] **Step 1: Commit the approved design and plan**

```bash
git add docs/superpowers/specs/2026-09-16-grok-consultation-v3-identity-design.md \
        docs/superpowers/plans/2026-09-16-grok-consultation-v3-identity-implementation.md
git commit -m "docs(grok): freeze consultation v3 identity design"
```

- [x] **Step 2: Merge the accepted repair and resolve obsolete feature paths to the repair side**

```bash
git merge --no-ff --no-commit de190b2c7e878fd5a4cf6ecb2fc58b34b058ee74
# For every historical Grok-modified source/test path, restore the accepted repair version first.
git checkout de190b2c7e878fd5a4cf6ecb2fc58b34b058ee74 -- \
  common/agent_dialogue_consultation_contract.py \
  control_plane/consultation_runtime.py \
  control_plane/session_targets.py \
  integrations/mastermind_company_mcp/consultation.py \
  integrations/slack_agent_dialogue/company_consultation_peer_resolver.py \
  tests/test_agent_dialogue_consultation_contract.py \
  tests/test_company_consultation_mcp.py \
  tests/test_executive_wake_fabric.py \
  tests/test_w6c2_consultation_runtime.py
git add -A
git commit -m "merge: compose accepted W6-C2 repair before Grok v3"
```

- [x] **Step 3: Merge current protected master**

```bash
git merge --no-ff --no-edit 0fe8074ff953b2ced9025ed40f0f66019c759967
```

- [x] **Step 4: Verify the dependency baseline**

```bash
python3 -m pytest -q -p no:randomly -p no:cacheprovider -o addopts='' \
  tests/test_agent_dialogue_consultation_contract.py \
  tests/test_w6c2_consultation_runtime.py \
  tests/test_company_consultation_mcp.py \
  tests/test_mastermind_company_mcp.py \
  tests/test_w6b_native_round_trip.py \
  tests/test_visible_turn_projection.py
```

Expected: all tests pass; no Grok v2 producer constant or selector remains.

### Task 2: Add the Closed V3 QUESTION Contract

**Files:**
- Modify: `common/agent_dialogue_consultation_contract.py`
- Modify: `tests/test_agent_dialogue_consultation_contract.py`

**Interfaces:**
- Consumes: protected `CONSULTATION_SCHEMA` v1 and `CONSULTATION_V2_SCHEMA` v2.
- Produces: `GROK_CONSULTATION_SCHEMA`, `CONSULTATION_SCHEMA_REASONING_SURFACES`, and `consultation_schema_for_reasoning_surface(reasoning_surface: Any) -> str`.

- [x] **Step 1: Write failing compatibility and v3 tests**

```python
def test_v3_accepts_only_grok_question_shape() -> None:
    frame = raw_consultation(schema=GROK_CONSULTATION_SCHEMA)
    frame["recipient_binding"]["reasoning_surface"] = "grok-bot"
    built = build_consultation(frame)
    assert built["purpose"] == "QUESTION"
    assert "question_message_key" not in built


def test_v3_rejects_non_grok_and_non_question_frames() -> None:
    for surface in ("codex", "claude", "gemini"):
        frame = raw_consultation(schema=GROK_CONSULTATION_SCHEMA)
        frame["recipient_binding"]["reasoning_surface"] = surface
        with pytest.raises(DialogueContractError):
            validate_consultation(frame)


def test_surface_selector_maps_grok_to_v3_without_widening_v2() -> None:
    assert consultation_schema_for_reasoning_surface("grok-bot") == GROK_CONSULTATION_SCHEMA
    v2 = raw_consultation(schema=CONSULTATION_V2_SCHEMA, purpose="ANSWER", question=None,
                          answer={"text": "{}", "evidence_refs": []})
    v2["question_message_key"] = v2["correlation"]["request_message_key"]
    v2["recipient_binding"]["reasoning_surface"] = "grok-bot"
    with pytest.raises(DialogueContractError):
        validate_consultation(v2)
```

- [x] **Step 2: Run the new tests and confirm RED**

```bash
python3 -m pytest -q -p no:randomly -o addopts='' \
  tests/test_agent_dialogue_consultation_contract.py -k 'v3 or surface_selector'
```

Expected: import/name failures or `MESSAGE_INVALID` for the valid v3 QUESTION.

- [x] **Step 3: Implement schema-specific validation**

```python
GROK_CONSULTATION_SCHEMA = "mastermind.agent_dialogue_consultation.v3"
CONSULTATION_SCHEMA_REASONING_SURFACES = {
    CONSULTATION_SCHEMA: frozenset({"codex", "claude"}),
    CONSULTATION_V2_SCHEMA: frozenset({"codex", "claude"}),
    GROK_CONSULTATION_SCHEMA: frozenset({"grok-bot"}),
}
_PRODUCER_SCHEMA_BY_REASONING_SURFACE = {
    "codex": CONSULTATION_SCHEMA,
    "claude": CONSULTATION_SCHEMA,
    "grok-bot": GROK_CONSULTATION_SCHEMA,
}

def consultation_schema_for_reasoning_surface(reasoning_surface: Any) -> str:
    try:
        return _PRODUCER_SCHEMA_BY_REASONING_SURFACE[reasoning_surface]
    except (KeyError, TypeError):
        raise DialogueContractError("MESSAGE_INVALID") from None
```

In `validate_consultation`, preserve the existing v1 and v2 branches verbatim; add a v3 branch requiring `purpose == "QUESTION"`, the v1 closed key set, self-linked `correlation.request_message_key`, and exact `grok-bot` surface.

- [x] **Step 4: Run contract tests GREEN**

```bash
python3 -m pytest -q -p no:randomly -o addopts='' tests/test_agent_dialogue_consultation_contract.py
```

Expected: all pass, including frozen v1 fingerprints and v2 correction identity.

- [x] **Step 5: Commit**

```bash
git add common/agent_dialogue_consultation_contract.py tests/test_agent_dialogue_consultation_contract.py
git commit -m "feat(grok): add closed consultation v3 question identity"
```

### Task 3: Derive V3 Through the Trusted Peer and Company MCP

**Files:**
- Modify: `integrations/slack_agent_dialogue/company_consultation_peer_resolver.py`
- Modify: `integrations/mastermind_company_mcp/consultation.py`
- Modify: `tests/test_company_consultation_mcp.py`

**Interfaces:**
- Consumes: `consultation_schema_for_reasoning_surface`.
- Produces: `ConsultationPeer.consultation_schema: str` and internal `company.consult` dispatch field `consultation_schema`.

- [x] **Step 1: Write failing derivation and override tests**

```python
def test_grok_peer_derives_v3_without_changing_public_projection() -> None:
    peer = _grok_peer()
    assert peer.consultation_schema == GROK_CONSULTATION_SCHEMA
    assert peer.public_projection() == {"peer_ref": peer.peer_ref, "display_name": peer.display_name}


def test_company_consult_carries_derived_v3_and_refuses_override() -> None:
    peer = _grok_peer()
    gateway, sink = _gateway([peer])
    response = _run(gateway.call("company.consult", {
        "to": peer.peer_ref, "question": "?", "evidence_refs": [],
        "artifact_revisions": [_artifact()],
    }))
    assert response["ok"] is True
    assert sink.calls[0][1]["consultation_schema"] == GROK_CONSULTATION_SCHEMA
```

Keep the existing caller-override negative test and assert zero dispatcher calls.

- [x] **Step 2: Run tests RED**

```bash
python3 -m pytest -q -p no:randomly -o addopts='' \
  tests/test_company_consultation_mcp.py -k 'grok or consultation_schema or override'
```

- [x] **Step 3: Implement trusted derivation**

Add a `ConsultationPeer.consultation_schema` property calling the selector. Permit `grok-bot` only in trusted binding validation. Add `"consultation_schema": peer.consultation_schema` to the internal `company.consult` request after peer resolution; do not add it to public tool arguments or peer projection.

- [x] **Step 4: Run tests GREEN and commit**

```bash
python3 -m pytest -q -p no:randomly -o addopts='' tests/test_company_consultation_mcp.py
git add integrations/slack_agent_dialogue/company_consultation_peer_resolver.py \
        integrations/mastermind_company_mcp/consultation.py \
        tests/test_company_consultation_mcp.py
git commit -m "feat(grok): derive v3 consultation schema from trusted peer"
```

### Task 4: Persist Exact V3 INTENT and Add Vocabulary-Only Surface

**Files:**
- Modify: `control_plane/consultation_runtime.py`
- Modify: `control_plane/session_targets.py`
- Modify: `tests/test_w6c2_consultation_runtime.py`
- Modify: `tests/test_executive_wake_fabric.py`

**Interfaces:**
- Consumes: validated v3 QUESTION frame.
- Produces: INTENT payload field `consultation_schema == item["schema"]`; vocabulary token `grok-bot` with no target.

- [x] **Step 1: Write failing runtime and inertness tests**

```python
def test_v3_intent_payload_is_exact_while_runtime_admission_stays_dark(tmp_path: Path) -> None:
    frame = build_v3_grok_question_fixture(tmp_path)
    payload = _consultation_intent_payload(
        frame,
        carrier_ref="dialogue://fixture/grok",
        trusted_observed_at="2026-09-14T00:00:00Z",
    )
    assert payload["consultation_schema"] == GROK_CONSULTATION_SCHEMA
    with pytest.raises(StateConflict, match="current Runtime binding"):
        consultations.intent(frame, ...)
    assert runtime.events.list_events(
        aggregate_type="consultation", aggregate_id=frame["consultation_id"]
    ) == []


def test_grok_surface_adds_no_target_or_transport_implementation() -> None:
    assert "grok-bot" in REASONING_SURFACES
    registry = load_session_targets()
    assert all(target.reasoning_surface != "grok-bot" for target in registry.targets.values())
    assert transport_implemented("grok-computer") is False
```

- [x] **Step 2: Run tests RED**

```bash
python3 -m pytest -q -p no:randomly -o addopts='' \
  tests/test_w6c2_consultation_runtime.py -k 'persists_exact_v3' \
  tests/test_executive_wake_fabric.py -k 'grok_surface'
```

- [x] **Step 3: Implement minimal runtime/vocabulary changes**

Extract the existing INTENT payload construction into a pure private producer and replace the hard-coded consultation schema with `item["schema"]`. Keep current-recipient admission unchanged, so a real v3 INTENT still fails with zero events. Add only `"grok-bot"` to `REASONING_SURFACES`; do not alter target config or wake transport implementation tables.

- [x] **Step 4: Run GREEN and commit**

```bash
python3 -m pytest -q -p no:randomly -o addopts='' \
  tests/test_w6c2_consultation_runtime.py \
  tests/test_executive_wake_fabric.py
git add control_plane/consultation_runtime.py control_plane/session_targets.py \
        tests/test_w6c2_consultation_runtime.py tests/test_executive_wake_fabric.py
git commit -m "feat(grok): persist v3 identity without arming execution"
```

### Task 5: Full Proof, Review Packet, and Draft PR

**Files:**
- Verify: all modified files
- Create: bounded evidence under `/Volumes/Mastermind/agent-evidence/grok-consultation-v3-g1b-20260916-sol-001/`

**Interfaces:**
- Consumes: Tasks 1-4.
- Produces: immutable branch head, dependency-isolated and current-base proof, independent review packet, and one production-inert draft PR against protected `master` after merged W6-C2 PR #681 is reconciled.

- [x] **Step 1: Run focused and compatibility suites**

```bash
python3 -m pytest -q -p no:randomly -p no:cacheprovider -o addopts='' \
  tests/test_agent_dialogue_consultation_contract.py \
  tests/test_w6c2_consultation_runtime.py \
  tests/test_company_consultation_mcp.py \
  tests/test_mastermind_company_mcp.py \
  tests/test_executive_wake_fabric.py \
  tests/test_w6b_native_round_trip.py \
  tests/test_visible_turn_projection.py \
  tests/test_runtime_binding_projection.py
```

- [x] **Step 2: Run every present importer of touched owners**

```bash
FILES=$(grep -IlE 'agent_dialogue_consultation_contract|consultation_runtime|session_targets|company_consultation_peer_resolver|mastermind_company_mcp.consultation|runtime_binding_projection' tests/*.py | sort)
printf '%s\n' "$FILES" | xargs python3 -m pytest -q -p no:randomly -p no:cacheprovider -o addopts=''
```

- [x] **Step 3: Run syntax and diff checks**

```bash
python3 -m py_compile \
  common/agent_dialogue_consultation_contract.py \
  control_plane/consultation_runtime.py \
  control_plane/session_targets.py \
  integrations/mastermind_company_mcp/consultation.py \
  integrations/slack_agent_dialogue/company_consultation_peer_resolver.py
CURRENT_MASTER=$(git rev-parse origin/master)
git diff --check "$CURRENT_MASTER"...HEAD
```

- [x] **Step 4: Verify negative capability boundaries**

```bash
CURRENT_MASTER=$(git rev-parse origin/master)
git diff --name-only "$CURRENT_MASTER"...HEAD
grep -R "grok-bot" config control_plane integrations common tests | sed -n '1,200p'
```

Expected: no checked-in Grok target, credential, endpoint, route, implemented transport, service install, provider call, or production arm.

- [ ] **Step 5: Obtain independent exact-head review**

Review against the version law, protected v1/v2 vectors, caller-override refusal, zero-target/transport boundary, and capability honesty. Any owned semantic change after review requires a fresh exact-head review.

- [ ] **Step 6: Push and create one production-inert draft PR on the existing branch**

```bash
git push -u origin HEAD:sol/grok-consultation-v2-g1b-20260915
gh pr create --draft --base master --head sol/grok-consultation-v2-g1b-20260915 \
  --title "[GROK-G1B] Add honest v3 consultation identity without execution" \
  --body-file /path/to/final-pr-body.md
```

PR #681 has merged and the existing branch is reconciled onto its protected W6-C2 generation. Before publication, confirm the GitHub three-dot diff contains only the dependency-isolated Grok paths and refresh current-base proof against protected `master`. Keep the PR draft and production-inert. Protected `master` remains publication truth; synthetic candidates are immutable review instruments only. Do not retarget to a dependency branch, create a replacement PR, rebase for freshness, or add an ancestry-only source commit.

The PR body must state `BUILT_NOT_PROVEN / PRODUCTION_INERT`, the exact protected W6-C2 merge identity, exact semantic and branch heads, the 12-path Grok delta, current-master integration proof, tests, review verdict, and every non-goal.

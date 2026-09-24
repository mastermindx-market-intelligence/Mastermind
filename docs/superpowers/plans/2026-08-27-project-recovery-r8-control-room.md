# Project Recovery R8-E — Chairman Control Room CEO Attention Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make recovery-required, CEO-attention, valid-wait and runtime-unknown project state visible in the existing Chairman Control Room as a read-only operating surface with exact evidence and navigation, without creating an inbox, wake path or lifecycle authority.

**Architecture:** Extend the existing pure `compose_control_room()` contract with one explicit recovery-assessment input and one additive `recovery` output section. The gather layer may obtain a current assessment only through the accepted R8-A/current-provider seam; otherwise it publishes a named degraded recovery source. The existing static Command Deck renders counts and rows; Open Sol remains navigation through existing surface bindings and cannot type/send/wake.

**Tech Stack:** Python >=3.11, existing `control_plane/chairman_control_room.py`, vanilla HTML/CSS/JS under `app/static/chairman_control/`, pytest, existing Control Room server/UI harness.

**Spec:** `docs/superpowers/specs/2026-08-27-project-recovery-sentinel-r8-design.md` plus current-state amendment.

## Global Constraints

- Repository: `mastermindx-market-intelligence/Mastermind` only.
- Hard dependency: R8-A assessment accepted. Current automatic gather additionally depends on an accepted read-only current-assessment provider; absence is rendered degraded, not replaced by stale committed state.
- Control Room remains read-only composition/navigation. No prompt typing, message sending, automatic ChatGPT wake, Executive mutation, new inbox, cursor, retry store or recovery database.
- `recovery` is a derived projection. It never overwrites existing Agent OS, Executive or GitHub fields in `work` or `attention`.
- Exact joins only. Recovery rows join work cards via exact `workstream` identity supplied by the assessment; `PROGRAM:` orphan subjects remain separate recovery rows until a lawful workstream exists.
- Existing `surface_bindings` remain deletion-safe navigation only.
- Unknown/unavailable recovery evidence remains visible; it cannot be normalized to zero recovery items.
- UI must work at existing desktop and narrow Control Room breakpoints and preserve current X1 information density.

## File Structure

- Modify `control_plane/chairman_control_room.py` — pure recovery projection + gather source health.
- Modify `tests/test_chairman_control_room.py` — contract/exact-join/degraded/no-authority tests.
- Modify `tests/test_chairman_control_room_server.py` if API source fields are asserted there.
- Modify `app/static/chairman_control/index.html` — recovery section shell only.
- Modify `app/static/chairman_control/control_room.js` — render summary/filter/detail/navigation.
- Modify `app/static/chairman_control/control_room.css` — reuse current tokens/layout patterns.
- Modify `tests/test_chairman_control_room_ui_x1.py` — DOM/contract regressions and narrow layout assertions.
- Modify `docs/CHAIRMAN_CONTROL_ROOM.md` — read-only recovery semantics and degraded behavior.

---

### Task 1: Freeze the additive recovery output contract

**Files:**
- Modify `tests/test_chairman_control_room.py`
- Modify later `control_plane/chairman_control_room.py`

**Interfaces:**

Add `recovery` to `OUTPUT_KEYS`.

Pure compose signature becomes additively:

```python
def compose_control_room(
    ...existing args...,
    recovery_assessment: Mapping[str, Any] | None = None,
) -> dict[str, Any]: ...
```

Output shape:

```python
"recovery": {
    "available": bool,
    "schema": "mastermind.project_recovery_assessment.v1" | None,
    "semantic_hash": str | None,
    "as_of": str | None,
    "summary": {
        "NO_RECOVERY_ACTION": int,
        "VALID_INTENTIONAL_WAIT": int,
        "CEO_ATTENTION": int,
        "RECOVERY_REQUIRED": int,
        "UNKNOWN_RECONCILE": int,
    },
    "items": [
        {
            "subject": str,
            "program": str | None,
            "workstream": str | None,
            "wave": str | None,
            "disposition": str,
            "finding_codes": list[str],
            "next_ceo_action": str,
            "evidence": list[dict[str, Any]],
            "binding_ids": list[str],
        },
    ],
    "degraded": list[str],
}
```

- [ ] **Step 1: Write RED pure-contract test**

```python
def test_recovery_assessment_projects_without_mutating_work(base_inputs, recovery_assessment):
    before = deepcopy(base_inputs["work_source"])
    doc = compose_control_room(
        **base_inputs,
        recovery_assessment=recovery_assessment,
    )
    assert doc["recovery"]["available"] is True
    assert doc["recovery"]["summary"]["RECOVERY_REQUIRED"] == 1
    assert base_inputs["work_source"] == before
```

- [ ] **Step 2: Write missing/invalid-input tests**

```python
def test_missing_recovery_is_explicitly_degraded(base_inputs):
    doc = compose_control_room(**base_inputs, recovery_assessment=None)
    assert doc["recovery"]["available"] is False
    assert "recovery_assessment_unavailable" in doc["recovery"]["degraded"]
    assert doc["recovery"]["items"] == []
```

Malformed schema must yield a degraded recovery section, not raise and not mark available.

- [ ] **Step 3: Run RED**

Run: `python -m pytest tests/test_chairman_control_room.py -q`

Expected: signature/output-key failures.

- [ ] **Step 4: Commit RED tests**

```bash
git add tests/test_chairman_control_room.py
git commit -m "test(control-room): freeze CEO recovery projection"
```

---

### Task 2: Implement the pure recovery projection and exact binding navigation

**Files:**
- Modify `control_plane/chairman_control_room.py`
- Modify `tests/test_chairman_control_room.py`

**Interfaces:**

```python
def _project_recovery(
    assessment: Any,
    bindings: Sequence[Mapping[str, Any]],
) -> dict[str, Any]: ...
```

- [ ] **Step 1: Implement closed assessment validation**

Accept only `schema == "mastermind.project_recovery_assessment.v1"`, closed disposition names and list/dict shapes needed by the UI. Do not re-run recovery classification.

- [ ] **Step 2: Attach only exact navigation bindings**

For a recovery item whose `workstream == "WS:FOO"`, reuse existing sanitized binding summaries where `binding.work_ref == "WS:FOO"`. Emit only `binding_ids` or the existing safe binding summary needed by the current Open action. A `PROGRAM:foo` orphan item gets no fabricated binding.

- [ ] **Step 3: Add collision tests**

```python
def test_recovery_similar_workstream_names_do_not_share_binding(...):
    # WS:ALPHA binding must not join WS:ALPHA-V2
    ...


def test_orphan_program_never_mints_work_card(...):
    doc = compose_control_room(...assessment_with_program_orphan...)
    assert any(i["subject"] == "PROGRAM:orphan-program" for i in doc["recovery"]["items"])
    assert not any(card["work_ref"] == "PROGRAM:orphan-program" for card in doc["work"])
```

- [ ] **Step 4: Prove existing canonical sections are invariant**

Build once with recovery absent and once with a recovery assessment; after removing only top-level `recovery`/recovery-source metadata, existing `work`, `attention`, `unjoined_open_prs`, `unbound_surfaces` and `binding_conflicts` must be byte-identical.

- [ ] **Step 5: Run GREEN and commit**

Run: `python -m pytest tests/test_chairman_control_room.py -q`

```bash
git add control_plane/chairman_control_room.py tests/test_chairman_control_room.py
git commit -m "feat(control-room): project read-only CEO recovery state"
```

---

### Task 3: Wire the gather layer to the accepted current-assessment provider

**Files:**
- Modify `control_plane/chairman_control_room.py`
- Modify `tests/test_chairman_control_room.py`
- Modify `tests/test_chairman_control_room_server.py` if needed.

**Interfaces:**
- Consume `control_plane.project_recovery_current.build_current_assessment` only if R8-C Task 5 accepted it.
- If current provider is not accepted, `build_control_room()` passes `None` and reports a recovery-specific degraded source; no stale file fallback.

- [ ] **Step 1: Write provider-success RED test if provider exists**

Monkeypatch the accepted provider and assert it is called once per Control Room build and its exact assessment hash appears in `doc["recovery"]`.

- [ ] **Step 2: Write provider-failure test**

On `CurrentRecoveryUnavailable` or any bounded provider exception:

```python
assert doc["recovery"]["available"] is False
assert "recovery_current_unavailable" in doc["recovery"]["degraded"]
assert existing_work_cards_are_still_present(doc)
```

- [ ] **Step 3: Implement one gather call**

Do not read `data/agenda/**` as canonical recovery truth and do not implement GitHub/Slack/Linear reads in Control Room. The gather layer either consumes the accepted current provider or degrades.

- [ ] **Step 4: Run server regressions**

Run:

```bash
python -m pytest tests/test_chairman_control_room.py tests/test_chairman_control_room_server.py -q
```

Expected: PASS and no source writes.

- [ ] **Step 5: Commit**

```bash
git add control_plane/chairman_control_room.py tests/test_chairman_control_room.py tests/test_chairman_control_room_server.py
git commit -m "feat(control-room): gather current recovery assessment"
```

If current provider is dependency-held, skip implementation and record the exact gate in the PR; the pure projection remains independently useful through injected assessment tests.

---

### Task 4: Add the CEO Attention / Recovery HTML shell

**Files:**
- Modify `app/static/chairman_control/index.html`
- Modify `tests/test_chairman_control_room_ui_x1.py`

**Interfaces:**
- One section with stable DOM ids/classes used by JS/tests.

Recommended shell:

```html
<section id="recovery-panel" class="panel recovery-panel" aria-labelledby="recovery-title">
  <div class="panel-header">
    <div>
      <div class="eyebrow">CEO Attention</div>
      <h2 id="recovery-title">Project Recovery</h2>
    </div>
    <div id="recovery-health" class="source-health" aria-live="polite"></div>
  </div>
  <div id="recovery-summary" class="recovery-summary"></div>
  <div id="recovery-list" class="recovery-list"></div>
</section>
```

- [ ] **Step 1: Write RED static DOM test**

Assert `recovery-panel`, `recovery-summary`, `recovery-list` and `recovery-health` exist exactly once and no form/textarea/contenteditable recovery control exists.

- [ ] **Step 2: Add the shell in the existing information hierarchy**

Place it near existing attention/current-work surfaces, not in a separate application/page. Do not add a send/assign/wake button.

- [ ] **Step 3: Run static UI test GREEN**

Run: `python -m pytest tests/test_chairman_control_room_ui_x1.py -q`

- [ ] **Step 4: Commit**

```bash
git add app/static/chairman_control/index.html tests/test_chairman_control_room_ui_x1.py
git commit -m "feat(control-room): add project recovery panel shell"
```

---

### Task 5: Render summary, filters and evidence-bounded recovery rows

**Files:**
- Modify `app/static/chairman_control/control_room.js`
- Modify `tests/test_chairman_control_room_ui_x1.py`

**Interfaces:**

```javascript
function renderRecovery(recovery, state) { ... }
```

Render five summary counts with human labels:

```text
Healthy
Intentional waits
CEO attention
Recovery required
Runtime unknown
```

Default list ordering:

```text
RECOVERY_REQUIRED
UNKNOWN_RECONCILE
CEO_ATTENTION
VALID_INTENTIONAL_WAIT
NO_RECOVERY_ACTION
then subject lexicographically
```

- [ ] **Step 1: Add RED source-text/DOM behavior tests**

Use the existing UI test pattern to assert the JS references exact disposition tokens and never references `fetch('/api/.../dispatch')`, Slack send or Executive mutation endpoints from the recovery renderer.

- [ ] **Step 2: Implement bounded row renderer**

Each row shows:

- subject/program/workstream;
- disposition badge;
- finding-code chips;
- next CEO action text;
- source/evidence reason codes or hashes only;
- `Open Sol`/navigation action only if an existing safe binding exists.

Do not render raw Slack bodies, credentials or arbitrary retrieved source prose.

- [ ] **Step 3: Implement degraded state**

If `recovery.available === false`, show “Recovery assessment unavailable” plus degraded reason codes. Never show all-zero healthy counts as a substitute.

- [ ] **Step 4: Run UI tests**

Run: `python -m pytest tests/test_chairman_control_room_ui_x1.py -q`

- [ ] **Step 5: Commit**

```bash
git add app/static/chairman_control/control_room.js tests/test_chairman_control_room_ui_x1.py
git commit -m "feat(control-room): render CEO recovery attention"
```

---

### Task 6: Style recovery at desktop and narrow breakpoints

**Files:**
- Modify `app/static/chairman_control/control_room.css`
- Modify `tests/test_chairman_control_room_ui_x1.py`

**Interfaces:**
- Reuse existing CSS variables/tokens; do not introduce a new visual system.

- [ ] **Step 1: Add breakpoint assertions**

Tests must require a narrow rule for the recovery summary/list and ensure no fixed pixel minimum width forces horizontal scrolling at the existing narrow breakpoint.

- [ ] **Step 2: Add focused styles**

Use current panel/card typography and badge conventions. Keep summary cards compact; on narrow screens switch to a two-column or single-column summary and stack evidence/action areas.

- [ ] **Step 3: Run static UI tests**

Run: `python -m pytest tests/test_chairman_control_room_ui_x1.py -q`

- [ ] **Step 4: Commit**

```bash
git add app/static/chairman_control/control_room.css tests/test_chairman_control_room_ui_x1.py
git commit -m "style(control-room): fit recovery across breakpoints"
```

---

### Task 7: Browser/product proof and documentation

**Files:**
- Modify `docs/CHAIRMAN_CONTROL_ROOM.md`
- Evidence under the existing Control Room review-evidence convention only.

- [ ] **Step 1: Document source/authority law**

Add:

```text
Recovery is a read-only projection of mastermind.project_recovery_assessment.v1.
It cannot create/claim/close work. Open Sol is navigation only. Missing recovery input is shown as degraded, never zero/healthy.
```

- [ ] **Step 2: Run a real Control Room against one accepted current assessment**

Verify visible counts and at least one real recovery/attention/unknown item against the assessment semantic hash. The same item must not be duplicated as a new canonical work card if it is a `PROGRAM:` orphan.

- [ ] **Step 3: Browser proof at relevant breakpoints**

Capture production-relevant proof at the existing desktop width and narrow/mobile width used by Control Room acceptance. Verify:

- summary numbers legible;
- recovery list sortable/readable;
- degraded state explicit;
- Open Sol appears only with a valid binding;
- no send/wake/assign controls;
- no horizontal overflow at narrow width;
- existing work/attention surfaces remain usable.

- [ ] **Step 4: Run complete Control Room tests**

```bash
python -m pytest tests/test_chairman_control_room.py tests/test_chairman_control_room_server.py tests/test_chairman_control_room_ui_x1.py -q
```

- [ ] **Step 5: Require hosted CI + Sol review and stop**

Return exact head, test/proof receipts, current assessment hash and screenshots/browser evidence to Sol.

**Stop condition:** Control Room makes current recovery state operationally legible and navigable but remains read-only. Do not claim R8 complete until projections/fresh-Sol R8-G are accepted.

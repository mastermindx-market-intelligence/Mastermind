# Chairman Seat C4 Admission Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development and superpowers:verification-before-completion. Execute inline on the existing isolated carrier; do not create a second branch or binding store.

**Goal:** Admit the already-authorized Fashionbird/ChatGPT4 profile as the fourth named Chairman ChatGPT seat so the incumbent MAS-115 disposable-realm census remains exact and can distinguish four governed running seats from any unknown fifth profile.

**Architecture:** Extend only the existing named-seat constants in `mas115_setup` and `nonseat_canary`; preserve the current `surface_bindings` document as the sole durable identity owner. The safety invariant remains strict set equality: every named seat must map to one distinct running managed profile, and any unbound running profile still refuses admission. Register C4 through one atomic `surface_bindings.save_bindings` operation after deriving its exact profile identity and sole ChatGPT conversation from the already-running Fashionbird profile without reading transcript content or selecting by title/recency.

**Tech Stack:** Python 3, pytest, existing `control_plane.surface_bindings`, existing MAS-115 sealed environment snapshot.

**Spec:** Chairman handoff `HANDOFF B — Web-Sol exact continuation + durable return`; lower-layer blocker recorded by the current Realm1 H2 owner in Mastermind issue #359.

## Global Constraints

- Protected Mastermind and Skillpack source is `b9884f7d3f99f33c6ceecb5007628ac84b5147f6`.
- Do not stop, restart, or repurpose Fashionbird; it remains a Chairman-owned C4 surface with its existing tunnel.
- Do not create a seat registry, allowlist, browser controller, URL selector, or alternate binding store.
- Do not print or commit raw profile IDs, folder IDs, exact conversation URLs, cookies, or credentials.
- Preserve exact running-set equality and duplicate-identity refusal; an unbound fifth running profile must remain `BINDINGS_UNAVAILABLE`.
- Do not modify PR #699, #750, or the Web-Sol R3 carrier/PR #836 in this operation.

---

### Task 1: Prove the four-seat contract is missing

**Files:**
- Modify: `tests/test_mas115_setup.py`
- Modify: `tests/test_nonseat_canary.py`

**Interfaces:**
- Consumes: `scripts.mas115_setup.SEAT_REFS`, `integrations.chairman_surfaces.nonseat_canary.CHAIRMAN_SEAT_REFS`.
- Produces: discriminating tests for exact four-seat enrollment, live-census acceptance, C4 collision refusal, and unknown fifth-profile refusal.

- [x] **Step 1: Change test fixtures to model four distinct Chairman seats**

Use `range(1, len(setup.SEAT_REFS) + 1)` in setup census fixtures and add a fourth synthetic seat in canary binding/environment helpers.

- [x] **Step 2: Add explicit contract assertions**

```python
def test_named_chairman_seat_contract_includes_c4():
    assert setup.SEAT_REFS == ("chatgpt1", "chatgpt2", "chatgpt3", "chatgpt4")
    assert canary.CHAIRMAN_SEAT_REFS == frozenset(setup.SEAT_REFS)
```

Add a live Realm1 test where four bound running seats pass and appending a fifth unbound running profile returns `BINDINGS_UNAVAILABLE`.

- [x] **Step 3: Run the focused tests and verify RED**

Run:

```bash
python3 -m pytest -q \
  tests/test_mas115_setup.py::test_named_chairman_seat_contract_includes_c4 \
  tests/test_nonseat_canary.py::test_realm1_live_gate_refuses_running_set_and_binding_mutations
```

Expected: failure because production constants still contain only `chatgpt1..3`.

### Task 2: Extend the incumbent seat/census owner minimally

**Files:**
- Modify: `scripts/mas115_setup.py`
- Modify: `integrations/chairman_surfaces/nonseat_canary.py`
- Test: `tests/test_mas115_setup.py`
- Test: `tests/test_nonseat_canary.py`

**Interfaces:**
- Consumes: existing `surface_bindings` schema and sealed environment snapshot.
- Produces: `SEAT_REFS` and `CHAIRMAN_SEAT_REFS` containing exactly four named seats; unchanged exact-set census semantics.

- [x] **Step 1: Add `chatgpt4` to both existing constants**

```python
SEAT_REFS = ("chatgpt1", "chatgpt2", "chatgpt3", "chatgpt4")
CHAIRMAN_SEAT_REFS = frozenset(SEAT_REFS)
```

Keep each module self-contained; do not add a new owner module.

- [x] **Step 2: Make operator text cardinality-derived**

Replace hard-coded “three” ceremony/status/refusal copy with `len(SEAT_REFS)` or “all current named Chairman seats”, while retaining one exact confirmation phrase:

```python
_CONFIRM_ENROLL = "ENROLL FOUR CHAIRMAN SEATS"
```

- [x] **Step 3: Run focused tests and verify GREEN**

Run:

```bash
python3 -m pytest -q tests/test_mas115_setup.py tests/test_nonseat_canary.py tests/test_surface_bindings.py
```

Expected: all tests pass, including exact fifth-profile refusal.

- [x] **Step 4: Commit the source slice**

```bash
git add integrations/chairman_surfaces/nonseat_canary.py scripts/mas115_setup.py \
  tests/test_nonseat_canary.py tests/test_mas115_setup.py \
  docs/superpowers/plans/2026-09-18-chairman-seat-c4-admission.md
git commit -m "fix(realm1): admit the fourth governed Chairman seat"
```

### Task 3: Register C4 through the existing binding store

**Files:**
- Runtime owner only: `~/Library/Application Support/Mastermind/control-room/surface_bindings.json`
- No repository source file contains private locator values.

**Interfaces:**
- Consumes: the one live Fashionbird Multilogin identity, the unique exact ChatGPT conversation navigation in its current Chromium session file, and `surface_bindings.new_binding/save_bindings`.
- Produces: one new `chatgpt4` binding with the same CCR work/role/locator contract as seats 1–3.

- [ ] **Step 1: Reconcile pre-write identity without emitting secrets**

Require exactly one Fashionbird root, exactly one matching running Multilogin row, exactly one exact ChatGPT conversation URL, no existing `chatgpt4` row, and no identity collision with seats 1–3. Emit only booleans, counts, and SHA-256 digests.

- [ ] **Step 2: Perform one atomic write**

Construct the row with:

```python
sb.new_binding(
    work_ref="WS:CHAIRMAN-CONTROL-ROOM",
    role="ceo",
    provider="chatgpt",
    locator_kind="chatgpt_managed_env",
    locator={"env_manager": "multilogin", "folder_id": folder_id,
             "profile_id": profile_id, "url": exact_url},
    observed_at=now_z,
    last_verified_at=now_z,
    seat_ref="chatgpt4",
)
```

Append to the existing healthy document and call `sb.save_bindings` once. Do not retry if the write result is ambiguous.

- [ ] **Step 3: Verify exact post-write state**

Reload the binding store and prove four distinct named seat identities, one `chatgpt4` row, no conflicts, mode `0600`, and exact equality between the four bound identities and the four running managed-profile identities. Emit no raw locators.

### Task 4: Reopen the existing Realm1/Web-Sol journey

**Files:**
- No source changes unless a new discriminating failure identifies an incumbent-owner defect.

**Interfaces:**
- Consumes: four-seat source candidate, updated binding store, current disposable provision.
- Produces: truthful Realm1 status and the next lawful Web-Sol install/effect gate.

- [ ] **Step 1: Run sanitized status from this carrier**

```bash
python3 scripts/mas115_setup.py status
```

Expected: `chairman_seats_enrolled=4`, `bindings_healthy=true`, `disposable_provision_ready=true`, four Multilogin profiles running.

- [ ] **Step 2: Prove the stopped disposable anchor passes current exact census**

Use `_load_current_provision` with one freshly sealed strict environment snapshot. Expected: provision available with no refusal code; output only readiness booleans/code.

- [ ] **Step 3: Publish the bounded source carrier and durable issue checkpoint**

Create a draft PR from the exact source commit, record the live C4 registration proof without private values, and update issue #359 so future sessions do not repeat the stale three-seat diagnosis.

- [ ] **Step 4: Return to Web-Sol R3**

Continue the existing #836 release/install path into the disposable realm. Do not submit a continuation until exact conversation fingerprint and RuntimeBinding generation are freshly proven.

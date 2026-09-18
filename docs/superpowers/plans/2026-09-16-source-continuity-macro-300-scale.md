# Source Continuity Macro-300 Scale Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the existing Source Continuity invocation-wide read profile so a stable estate of up to 300 open Macro PRs can produce the incumbent evidence-only receipt without weakening collision, revalidation, or authority semantics.

**Architecture:** Change only the four closed resource ceilings in the incumbent adapter. Keep one shared invocation budget, all fail-closed refusal types, #707 roster-only semantic revalidation, #710 writer-gate behavior, and the existing receipt/verifier owners unchanged. Prove the profile with hermetic 274/300/301-estate tests plus exact resource-boundary tests before any live canary.

**Tech Stack:** Python 3.12/3.14, pytest, existing `scripts/source_continuity.py` CLI and hermetic HTTP/Git fixtures.

**Spec:** Mastermind issue #346 comments `5707620182` and `5707640088`.

## Global Constraints

- Exact profile: 300 open PRs, 768 HTTP calls, 64 MiB normalized bytes, 240.0 seconds.
- Keep the 5,000,000-byte per-response cap unchanged.
- Keep ten roster pages, thirty foreign-file pages, and one invocation-local budget shared by both observations.
- No retry, reset, cache, cursor, persistence, GraphQL/POST path, caller budget knob, repository-specific profile, receipt redesign, or new authority plane.
- The 301st PR refuses before foreign-file enumeration; pathological fanout remains bounded and fail-closed.
- Authority effect remains `NONE`; no merge, writer release, retry, deployment, or production authority follows.

---

### Task 1: Freeze the Macro-300 profile in RED tests

**Files:**
- Create: `tests/test_source_continuity_macro_scale.py`
- Modify: `tests/test_source_continuity_census_budget.py`
- Modify: `tests/test_source_continuity_saturated_foreign_pr.py`

**Interfaces:**
- Consumes: `EstateHTTP`, `Clock`, and `run_cli` from `tests/test_source_continuity_census_budget.py` plus `_cli_module()` and CLI fixtures from `tests/test_source_continuity.py`.
- Produces: discriminating tests for 274/300 success, 301 pre-enumeration refusal, exact call/byte/time boundaries, and the exact closed profile.

- [ ] **Step 1: Add the exact profile and estate tests**

```python
def test_macro_300_profile_is_exact():
    module = fx._cli_module()
    assert module._MAX_COLLISION_PRS == 300
    assert module._MAX_HTTP_CALLS == 768
    assert module._MAX_HTTP_NORMALIZED_BYTES == 64 * 1024 * 1024
    assert module._HTTP_READ_BUDGET_SECONDS == 240.0
    assert module._MAX_HTTP_BODY_BYTES == 5_000_000

@pytest.mark.parametrize("count", [274, 300])
def test_macro_scale_estate_completes(count, capsys, monkeypatch):
    module = fx._cli_module()
    monkeypatch.setattr(module, "monotonic", budget.Clock())
    http = budget.EstateHTTP(count)
    rc, payload = budget.run_cli(module, capsys, http)
    assert rc == 0, payload
    assert payload["authority_effect"] == "NONE"
    assert http.passes == 2
```

- [ ] **Step 2: Add 301 and exact resource-boundary discriminators**

```python
def test_macro_301_refuses_before_foreign_file_enumeration(capsys, monkeypatch):
    module = fx._cli_module()
    monkeypatch.setattr(module, "monotonic", budget.Clock())
    http = budget.EstateHTTP(301)
    rc, payload = budget.run_cli(module, capsys, http)
    assert rc == 2 and payload["code"] == "REMOTE_CENSUS_INCOMPLETE"
    assert not any(
        "/files?" in url and f"/pulls/{fx.PR_NUMBER}/" not in url
        for url, _, _ in http.calls
    )
```

For a 300-PR control run, record the actual admitted call count and normalized byte total, then prove exact-count/exact-byte success and one-unit-under refusal. Use `Clock.now = 239.999` for success and `Clock.now = 240.0` for refusal, matching the incumbent `current >= deadline` rule.

- [ ] **Step 3: Update inherited closed-profile assertions**

Change only the old profile literals in `test_budget_constants_are_closed_and_raw_response_cap_is_unchanged`, `test_invocation_ceilings_are_unchanged_by_semantic_revalidation`, the pathological fanout bound, and time-boundary fixtures. Preserve all #707 semantic-revalidation assertions.

- [ ] **Step 4: Run focused RED tests**

Run:
```bash
python3.12 -m pytest -q \
  tests/test_source_continuity_macro_scale.py \
  tests/test_source_continuity_census_budget.py::test_budget_constants_are_closed_and_raw_response_cap_is_unchanged \
  tests/test_source_continuity_saturated_foreign_pr.py::test_invocation_ceilings_are_unchanged_by_semantic_revalidation
```
Expected: FAIL because protected source still reports 256 / 640 / 32 MiB / 180 seconds and rejects 274/300 before foreign-file enumeration.

### Task 2: Apply the minimal closed-profile implementation

**Files:**
- Modify: `scripts/source_continuity.py:72-76`
- Test: the three Task 1 test files.

**Interfaces:**
- Consumes: existing `_BoundedHTTPGet`, collision census, conditional validation, and refusal types unchanged.
- Produces: the same CLI/verifier behavior under the expanded frozen invocation envelope.

- [ ] **Step 1: Change only the four profile constants**

```python
_MAX_COLLISION_PRS = 300
_MAX_HTTP_CALLS = 768
_HTTP_READ_BUDGET_SECONDS = 240.0
_MAX_HTTP_NORMALIZED_BYTES = 64 * 1024 * 1024
```

- [ ] **Step 2: Run the focused GREEN tests**

Run the Task 1 command. Expected: PASS.

- [ ] **Step 3: Run the full Source Continuity family**

```bash
python3.12 -m pytest -q \
  tests/test_source_continuity.py \
  tests/test_source_continuity_census_budget.py \
  tests/test_source_continuity_macro_scale.py \
  tests/test_source_continuity_r3_hardening.py \
  tests/test_source_continuity_saturated_foreign_pr.py \
  tests/test_source_continuity_writer_gate.py
```
Expected: all tests PASS with #707 and #710 behavior unchanged.

### Task 3: Qualify and checkpoint the single carrier

**Files:**
- Modify only the five frozen scope paths listed above.

**Interfaces:**
- Consumes: exact protected base `320f586126b7c82c843ef17612f12d40d20a42e0` and operation `source-continuity-macro-300-scale-successor-20260916-sol-001`.
- Produces: one Draft/HOLD PR and exact-head evidence; no official live canary before protection.

- [ ] **Step 1: Verify source hygiene and dual-runtime focused tests**

Run `python3.12 -m py_compile scripts/source_continuity.py`, `git diff --check`, and the Macro-scale/focused family on Python 3.14.

- [ ] **Step 2: Review the exact five-path diff**

Confirm no path outside the frozen scope changed and no receipt, authority, retry, persistence, or transport semantics moved.

- [ ] **Step 3: Commit, push non-force, and open one Draft/HOLD PR**

Use the existing operation branch; record exact head/tree/base, tests, limitations, and independent review request. Do not run an official Macro estate canary until the candidate is protected.

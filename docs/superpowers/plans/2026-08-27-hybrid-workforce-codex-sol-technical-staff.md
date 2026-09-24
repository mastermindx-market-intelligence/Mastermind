# Codex-Sol Technical Staff Conformance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the approved “Codex as a technical/CTO arm of Sol” role mechanically testable without creating a fourth executive seat, a new lifecycle role enum, model-derived authority, or a path collision with Wake PR3.

**Architecture:** `sol_technical_staff` is deliberately not a new durable executive identity. A Codex-Sol continuation composes existing facts: `owner_seat="ceo"` for accountability; an existing bounded orchestration duty (`plan`, `work`, `review`, `repair`, or `aggregation`) where applicable; `reasoning_surface="codex"` as execution/runtime evidence; and an explicit parent commission/effective grant that limits authority. This carrier proves that composition through new isolated conformance tests and existing Runtime/Router/OHF contracts. It **does not edit Wake Fabric implementation/tests/docs**; Wake PR3 exclusively owns those paths and later provides actual delivery/resume.

**Tech Stack:** Existing Executive Runtime v4, Model Router, OHF/App Server test fixtures, pytest, docs.

**Spec:** `docs/superpowers/specs/2026-08-27-executive-workforce-hybrid-role-topology-design.md`

## Global Constraints

- Protected pickup: `Mastermind@6f1bc3dd39f1ebecd3c22e44aa11ca7a13fa5182`; re-pin before first implementation write and again before push.
- No new executive seat, `SOL_TECHNICAL_STAFF` database column, role table, lifecycle store, provider-specific authority enum, or Slack identity registry.
- Existing seats remain exactly `coo | ceo | chairman`.
- Existing orchestration roles remain the bounded work-duty vocabulary unless a concrete falsifier proves them insufficient; this carrier may not widen them merely for naming convenience.
- Codex model/provider/account/host/native thread/Slack principal never grants `ceo` authority.
- A Codex-Sol technical continuation may exercise only authority explicitly present in current Chairman/Sol intent, parent commission and accepted effective grant.
- Product-thesis change, canonical owner/architecture change, rights/security/spend/destructive action and final acceptance remain Sol/Chairman return boundaries.
- **Collision fence:** do not modify `control_plane/wake_*`, `control_plane/session_targets.py`, `control_plane/wake_transport.py`, `docs/EXECUTIVE_WAKE_FABRIC.md`, or `tests/test_executive_wake_fabric*.py`. Wake PR3 owns them.
- No production/provider/host arming. This is conformance + source-law proof only.

---

### Task 1: Add an isolated Codex-Sol identity conformance suite

**Files:**
- Create: `tests/test_codex_sol_identity_conformance.py`
- Create: `docs/CODEX_SOL_TECHNICAL_STAFF.md`

**Interfaces:**
- Consumes existing `SessionTarget`, `RuntimeBinding`, `WakeObligation`/route primitives read-only; no Wake production code changes.
- Consumes existing Runtime Job/Worker/Attempt structures.
- Produces no new production interface.

- [ ] **Step 1: Write RED/characterization tests for CEO accountability vs reasoning surface**

Create `tests/test_codex_sol_identity_conformance.py`. Build one admitted/synthetic CEO attention fact using existing test helpers, mint the existing obligation/route objects, then construct two otherwise equivalent routing scenarios in-memory:

```text
accountable seat = ceo, reasoning surface = chatgpt-sol
accountable seat = ceo, reasoning surface = codex
```

Assert the canonical executive accountability/source identity is unchanged while destination/runtime evidence differs. If the current Wake constructors require different fixture plumbing than assumed, adapt only the test to the accepted public API; do not edit Wake production code.

Also assert:

```text
reasoning_surface=codex + target_seat=coo does not upgrade the seat
changing native RuntimeBinding generation/handle cannot change owner_seat
ChatGPT1/ChatGPT2/ChatGPT3-like strings in metadata/prose cannot select executive seat
```

- [ ] **Step 2: Run characterization tests**

```bash
python -m pytest tests/test_codex_sol_identity_conformance.py -q
```

If accepted current contracts already satisfy the law, these tests may pass immediately. That is valid characterization evidence; do not force a production change merely to manufacture RED.

- [ ] **Step 3: Add the role/identity document**

`docs/CODEX_SOL_TECHNICAL_STAFF.md` must state exactly:

```text
accountable executive seat: ceo
technical duty: existing orchestration role + bounded commission/effective grant
reasoning surface: codex when so routed
Worker/provider/model/session/Slack identity: execution or communication evidence only
```

Include the authority boundary: Codex-Sol can perform architecture-preserving technical continuation and strict-subset delegation, but cannot change Chairman intent/product thesis/canonical ownership/new control planes/rights/security/spend/destructive authority/final acceptance without return.

- [ ] **Step 4: Commit**

```bash
git add tests/test_codex_sol_identity_conformance.py docs/CODEX_SOL_TECHNICAL_STAFF.md
git commit -m "test(exec): define Codex-Sol technical staff identity"
```

---

### Task 2: Pin Job ownership/duty without a new role schema

**Files:**
- Modify: `tests/test_executive_os_runtime.py`
- Modify: `tests/test_executive_os_phase1fb.py`
- Modify: `research/EXECUTIVE_OS_PHASE1F_ORCHESTRATION_CONTRACT.md`

**Interfaces:**
- Existing `owner_seat` is durable executive accountability.
- Existing orchestration roles remain `plan | work | review | repair | aggregation`.
- Existing grant/subset law controls delegation.

- [ ] **Step 1: Add CEO-owned technical-work characterization**

Using existing authorized Runtime constructors/test fixtures, prove a bounded Job can remain `owner_seat="ceo"` while its technical duty is represented by an existing orchestration role and its eventual Worker/provider is independently selected. Assert no Job/Attempt/Event field persists any of:

```text
sol_technical_staff
codex_sol
ChatGPT1/2/3 Slack principal
native Codex thread id
provider account as authority
```

- [ ] **Step 2: Add strict-subset delegation falsifiers**

A CEO-owned technical parent may create/delegate a child only through current effective-grant/subset law. Add negative cases for repository/path/authority/capability widening and for Worker/model input attempting to alter `owner_seat`, escalation target, merge/deploy authority, or review independence.

- [ ] **Step 3: Prove provider replacement cannot mutate executive ownership**

Using synthetic Worker/provider identities, prove the same CEO-owned Job remains CEO-owned whether a lawful Attempt runs on Codex or a different eligible Worker. Separate lawful Attempts may change Worker execution identity but not Job owner seat/effective grant.

- [ ] **Step 4: Run focused runtime/orchestration tests**

```bash
python -m pytest \
  tests/test_codex_sol_identity_conformance.py \
  tests/test_executive_os_runtime.py \
  tests/test_executive_os_phase1fb.py \
  -q
```

- [ ] **Step 5: Update orchestration source law**

Append a bounded section to `research/EXECUTIVE_OS_PHASE1F_ORCHESTRATION_CONTRACT.md`:

```text
Sol technical staff is a duty/embodiment, not a new executive seat.
Durable accountability = owner_seat=ceo.
Bounded technical duty = existing orchestration role + commission/effective grant.
Reasoning surface/provider = runtime/execution evidence only.
```

Do not change existing schema definitions unless a failing accepted invariant proves they cannot represent this law.

- [ ] **Step 6: Commit**

```bash
git add tests/test_codex_sol_identity_conformance.py tests/test_executive_os_runtime.py tests/test_executive_os_phase1fb.py research/EXECUTIVE_OS_PHASE1F_ORCHESTRATION_CONTRACT.md
git commit -m "test(exec): pin Codex-Sol authority composition"
```

---

### Task 3: Prevent Model Router, provider and Slack identity from laundering CEO authority

**Files:**
- Modify: `tests/test_executive_model_router.py`
- Modify: `tests/test_codex_sol_identity_conformance.py`
- Modify: `docs/EXECUTIVE_WORKER_ROUTING.md`

**Interfaces:**
- Model Router continues to answer suitability/execution shape only.
- Slack remains communication transport only.
- No RF1 tier implementation belongs in this carrier.

- [ ] **Step 1: Add model/provider authority negatives**

Pin that `frontier.orchestrator`, `gpt-5.6-sol`, `codex`, or any future provider/model alias cannot by itself mint or mutate a CEO-owned Job/effective grant. High ambiguity may return `FRONTIER_LEAD`; that result does not itself create a CEO Job or grant authority.

- [ ] **Step 2: Add Slack-principal negatives**

Feed strings resembling `ChatGPT1`, `ChatGPT2`, `Claude5`, or other communication principals through objective/metadata/prose locations accepted by test fixtures and prove no Router/Runtime authority constructor uses them to select Worker, seat, provider account or effective grant.

- [ ] **Step 3: Run focused tests**

```bash
python -m pytest \
  tests/test_codex_sol_identity_conformance.py \
  tests/test_executive_model_router.py \
  tests/test_executive_os_runtime.py \
  -q
```

- [ ] **Step 4: Update routing docs**

Document the identity split:

```text
provider/model -> which reasoning/execution implementation ran?
Worker -> which governed execution identity handled an Attempt?
owner_seat -> which executive role is accountable?
commission/effective grant -> what authority was delegated?
Slack principal -> who communicated?
```

No field substitutes for another. Explicitly defer quality-equivalence tiers to RF1.

- [ ] **Step 5: Commit**

```bash
git add tests/test_codex_sol_identity_conformance.py tests/test_executive_model_router.py docs/EXECUTIVE_WORKER_ROUTING.md
git commit -m "test(exec): refuse model or Slack authority laundering"
```

---

### Task 4: Production-inert Codex-Sol composition proof using existing OHF fixtures

**Files:**
- Modify: `tests/test_ohf_p1b_orchestrator.py`
- Modify: `tests/test_codex_sol_identity_conformance.py`

**Interfaces:**
- Uses current OHF/App Server test fixtures only.
- Does not add/arm Wake delivery.

- [ ] **Step 1: Add one synthetic CEO technical continuation**

Using in-memory/test Runtime + existing OHF fixtures, construct an authorized bounded CEO-owned technical continuation that is executed/reasoned on a Codex surface. Prove:

```text
same CEO accountability
→ bounded existing commission/effective grant
→ Codex reasoning/process evidence
→ existing technical plan/review duty
→ no Worker/provider-derived authority
→ exact return/escalation boundary preserved
```

- [ ] **Step 2: Add prohibited architecture-widening result**

Have the synthetic Codex result propose authority outside the grant (for example a new lifecycle plane or deploy authority). Prove existing validation/adjudication does not self-apply it, widen the grant, or convert model prose into canonical source law.

- [ ] **Step 3: Run combined conformance gate**

```bash
python -m pytest \
  tests/test_codex_sol_identity_conformance.py \
  tests/test_executive_os_runtime.py \
  tests/test_executive_os_phase1fb.py \
  tests/test_executive_model_router.py \
  tests/test_ohf_p1b_orchestrator.py \
  -q
python -m compileall -q control_plane

git diff --check
```

- [ ] **Step 4: Independent adversarial review**

Reviewer attacks: model name grants CEO; Codex thread becomes canonical Sol identity; Slack sender grants authority; provider replacement mutates owner seat; a fourth executive seat/role store appears; technical child widens parent grant; or this carrier edits Wake PR3-owned paths.

- [ ] **Step 5: Hosted CI/CodeQL and return**

Push the same carrier, require exact-head hosted gates, then return base/head SHA, changed-file census, test receipts, adversarial verdict and explicit proof of:

```text
zero new durable executive seat/role/lifecycle fields
zero Wake transport arming
zero provider/routing change
zero overlap with Wake PR3 paths
```

## Stop Condition

Stop when current Executive/Router/OHF contracts mechanically prove Codex can embody a bounded CEO technical continuation without creating a new executive identity or provider-derived authority. Wake PR3 remains the sole transport/resume implementation owner; RF1/HF1 remain separate Capacity Fabric waves.
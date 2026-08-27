# Codex-Sol Technical Staff Conformance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the approved “Codex as a technical/CTO arm of Sol” role recoverable and testable without creating a fourth executive seat, a new lifecycle role enum, or model-derived authority.

**Architecture:** `sol_technical_staff` is deliberately **not** a new durable executive identity. A Codex-Sol continuation is the composition of existing facts: `owner_seat="ceo"` for accountability, an existing bounded orchestration duty (`plan`, `work`, `review`, `repair`, or `aggregation`) where applicable, `reasoning_surface="codex"` in Wake/session routing, and an explicit parent commission/effective grant that limits the work. ChatGPT Sol and Codex-Sol can therefore be two reasoning surfaces for the same CEO seat. The provider/model never mints the seat or authority. Wake PR3 later makes the Codex surface resumable; this wave pins the identity/authority law first.

**Tech Stack:** Existing Executive Runtime v4, Model Router, Wake SessionTarget/RuntimeBinding, pytest, docs.

**Spec:** `docs/superpowers/specs/2026-08-27-executive-workforce-hybrid-role-topology-design.md`

## Global Constraints

- No new executive seat, `SOL_TECHNICAL_STAFF` database column, role table, lifecycle store, or provider-specific authority enum.
- Existing seats remain exactly `coo | ceo | chairman`.
- Existing orchestration roles remain the bounded work-duty vocabulary unless a concrete code path proves it insufficient.
- Codex model/provider identity, ChatGPT/Codex account identity, Slack principal, host, or native thread never grants `ceo` authority.
- A Codex-Sol technical continuation may exercise only the authority explicitly delegated by the current Chairman/Sol commission and accepted Executive grant.
- Material product thesis, architecture/owner changes, rights/security/spend/destructive actions and final acceptance remain Sol/Chairman return boundaries per current law.

---

### Task 1: Pin “same CEO seat, different reasoning surface” in Wake/session law

**Files:**
- Modify: `tests/test_executive_wake_fabric.py`
- Modify: `tests/test_executive_wake_fabric_hardening.py`
- Modify: `docs/EXECUTIVE_WAKE_FABRIC.md`

**Interfaces:**
- Existing `SessionTarget.target_seat="ceo"`.
- Existing `reasoning_surface="chatgpt-sol" | "codex"`.
- Existing `RuntimeBinding` remains runtime-only.

- [ ] **Step 1: Add same-obligation/two-surface test**

Create one admitted CEO wake source fact and mint one `WakeObligation`. Resolve it against two otherwise equivalent registries/bindings:

```text
CEO target A -> reasoning_surface=chatgpt-sol, wake_transport=chatgpt-gui
CEO target B -> reasoning_surface=codex, wake_transport=codex-app-server
```

Assert:

```python
assert route_a.obligation_id == route_b.obligation_id
assert route_a.target_seat == route_b.target_seat == "ceo"
assert route_a.reasoning_surface != route_b.reasoning_surface
assert route_a.destination_digest != route_b.destination_digest
```

This proves “Codex-Sol” is route/runtime embodiment of the same accountable CEO seat, not another executive identity.

- [ ] **Step 2: Add ABA/authority falsifiers**

A changed Codex App Server thread/native handle changes `RuntimeBinding`/destination evidence but does not change the CEO obligation or owner seat. A `RuntimeBinding(reasoning_surface="codex")` supplied to a COO target must refuse rather than upgrade the seat.

- [ ] **Step 3: Run tests**

```bash
python -m pytest \
  tests/test_executive_wake_fabric.py \
  tests/test_executive_wake_fabric_hardening.py \
  -q
```

- [ ] **Step 4: Update Wake docs**

Add a concise identity example:

```text
accountable executive seat: ceo
current reasoning surface: codex
current duty: plan/review/technical continuation
runtime binding: rotating App Server session/thread
provider/model: execution evidence only
```

State explicitly that changing reasoning surface never changes authority.

- [ ] **Step 5: Commit**

```bash
git add tests/test_executive_wake_fabric.py tests/test_executive_wake_fabric_hardening.py docs/EXECUTIVE_WAKE_FABRIC.md
git commit -m "test(exec): pin Codex as a CEO reasoning surface"
```

---

### Task 2: Pin Job ownership/duty without a new role schema

**Files:**
- Modify: `tests/test_executive_os_runtime.py`
- Modify: `tests/test_executive_os_phase1fb.py`
- Modify: `research/EXECUTIVE_OS_PHASE1F_ORCHESTRATION_CONTRACT.md`

**Interfaces:**
- Existing `owner_seat` is the durable accountability identity.
- Existing orchestration roles remain `plan | work | review | repair | aggregation`.

- [ ] **Step 1: Add CEO-owned technical-child tests**

Use the existing authorized root/child constructors to prove a bounded Job can be `owner_seat="ceo"` while its orchestration duty remains one of the existing roles and its Worker/provider remains independently selected. Assert the Job/Attempt does not persist `sol_technical_staff`, `codex_sol`, Slack username, native thread id or provider account as authority fields.

- [ ] **Step 2: Add shrink-only delegation falsifiers**

A CEO-owned parent may create/delegate an architecture-preserving child only through the existing effective-grant/subset law. Tests must refuse child authority/path/capability expansion beyond the parent and refuse a worker/model field attempting to alter `owner_seat` or escalation target.

- [ ] **Step 3: Prove provider/model changes do not change seat**

Using synthetic Worker/provider identities, prove the same CEO-owned Job remains CEO-owned whether the eventual Worker is Codex or another eligible provider. Worker replacement across separate lawful Attempts cannot mutate the Job's owner seat.

- [ ] **Step 4: Run runtime/orchestration tests**

```bash
python -m pytest \
  tests/test_executive_os_runtime.py \
  tests/test_executive_os_phase1fb.py \
  -q
```

- [ ] **Step 5: Update orchestration contract**

Record the ruling:

```text
Sol technical staff is a duty/embodiment, not a new executive seat.
Durable accountability = owner_seat=ceo.
Bounded technical duty = existing orchestration role + commission/effective grant.
Reasoning surface/provider = execution/runtime evidence only.
```

- [ ] **Step 6: Commit**

```bash
git add tests/test_executive_os_runtime.py tests/test_executive_os_phase1fb.py research/EXECUTIVE_OS_PHASE1F_ORCHESTRATION_CONTRACT.md
git commit -m "test(exec): pin Codex-Sol authority composition"
```

---

### Task 3: Prevent Model Router/Slack/provider identity from laundering CEO authority

**Files:**
- Modify: `tests/test_executive_model_router.py`
- Modify: `tests/test_executive_os_runtime.py`
- Modify: `docs/EXECUTIVE_WORKER_ROUTING.md`

**Interfaces:**
- Model Router continues to return suitability/execution shape only.
- Slack remains communication transport.

- [ ] **Step 1: Add model-authority negative tests**

Pin that `frontier.orchestrator` or any `gpt-5.6-sol` alias cannot be converted directly into a Worker Job with `owner_seat="ceo"` absent the existing typed CEO provenance/authorized constructor path. Changing a model alias from Luna/Terra to Sol never changes owner seat or effective grant.

- [ ] **Step 2: Add Slack identity negative fixture**

At the contract level, supply strings resembling `ChatGPT1`, `Claude5`, or other Slack principals in objective/metadata/prose fields and prove no parser/router/runtime constructor uses them to select Worker, seat, authority, provider account or session target.

- [ ] **Step 3: Run focused tests**

```bash
python -m pytest \
  tests/test_executive_model_router.py \
  tests/test_executive_os_runtime.py \
  -q
```

- [ ] **Step 4: Update routing docs**

Document:

```text
provider/model answers: what reasoning/execution surface ran?
worker answers: what governed execution identity handled the Attempt?
owner_seat answers: which executive role is accountable?
commission/effective grant answers: what authority was delegated?
Slack answers: who communicated?
```

No field substitutes for another.

- [ ] **Step 5: Commit**

```bash
git add tests/test_executive_model_router.py tests/test_executive_os_runtime.py docs/EXECUTIVE_WORKER_ROUTING.md
git commit -m "test(exec): refuse model or Slack authority laundering"
```

---

### Task 4: End-to-end production-inert Codex-Sol composition proof

**Files:**
- Modify: `tests/test_ohf_p1b_orchestrator.py`
- Modify: `tests/test_executive_wake_fabric.py`
- Add sanitized proof artifact only if current review convention requires it.

- [ ] **Step 1: Create one synthetic CEO technical continuation**

Using current in-memory/test Runtime + OHF fixtures, create an authorized CEO-owned bounded technical continuation whose reasoning surface is Codex. Prove:

```text
same CEO seat
→ bounded current commission/effective grant
→ Codex App Server reasoning surface
→ technical plan/review duty
→ no Worker/provider-derived authority
→ exact return/escalation boundary preserved
```

No live Wake delivery is required in this conformance wave; Wake PR3 owns transport.

- [ ] **Step 2: Add a prohibited architecture-widening case**

Have the synthetic Codex result propose a new lifecycle/state plane or authority outside the grant. The existing result/adjudication path must not self-apply that proposal or terminalize it as accepted architecture.

- [ ] **Step 3: Run combined suite**

```bash
python -m pytest \
  tests/test_executive_os_runtime.py \
  tests/test_executive_os_phase1fb.py \
  tests/test_executive_model_router.py \
  tests/test_executive_wake_fabric.py \
  tests/test_executive_wake_fabric_hardening.py \
  tests/test_ohf_p1b_orchestrator.py \
  -q
python -m compileall -q control_plane

git diff --check
```

- [ ] **Step 4: Independent adversarial review**

Reviewer attacks: model name grants CEO, Codex thread becomes canonical Sol identity, Slack sender grants authority, provider replacement mutates owner seat, technical-staff label creates a fourth seat, or technical child widens the parent's grant.

- [ ] **Step 5: Return to Sol**

Return exact head, tests/hosted CI, adversarial verdict, and confirmation that this wave introduced **zero new durable seat/role/lifecycle fields**. Wake PR3 remains the transport implementation owner.

## Stop Condition

This wave stops when current Executive/Wake/Router contracts mechanically prove Codex can embody a bounded CEO technical continuation without creating a new executive identity or provider-derived authority. It does not arm Codex Wake, create a Codex app, or change CF2/RF1/HF1 provider placement.

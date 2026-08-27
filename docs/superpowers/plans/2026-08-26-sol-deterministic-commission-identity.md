# Sol Deterministic Commission Identity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every substantial Agent-OS-backed manual modifying commission derive the same `WORK_ID`, `OPERATION_KEY`, and carrier preamble from the same workstream/wave, so independent Sol sessions cannot accidentally commission sibling identities for one logical wave.

**Architecture:** This is a procedure-only protected Skillpack change. `COMMISSION_WAVE.md` defines deterministic identity and the required handoff preamble; `RECONCILE_STATE.md` defines how an existing/manual carrier is reconciled. No runtime, queue, GitHub hook, Agent OS schema, transport, or Executive Job behavior changes in A2.

**Tech Stack:** Markdown + YAML frontmatter, Python 3, pytest, PyYAML.

**Spec:** `docs/superpowers/specs/2026-08-26-single-carrier-duplicate-dispatch-design.md` on approved design commit `83456d4f4b8496da44049271779a07bcf368fbf9` (design branch `sol/manual-single-carrier-and-logical-operation-admission-20260826`).

## Global Constraints

- Protected Skillpack schema remains exactly `mastermind.sol_skillpack.v1`.
- `skillpack_version` remains exactly `1.0.0`; `minimum_bootstrap_major` remains exactly `1`.
- `WORK_ID` for Agent-OS-backed modifying work is exactly `WS:<WORKSTREAM>#<WAVE_ID>`.
- Deterministic manual operation key is exactly `"ws-" + sha256(b"mastermind.agentos.work_identity.v1\x00" + WORK_ID_utf8).hexdigest()[:32]`.
- Required modifying handoff preamble labels are exactly `WORK_ID`, `OPERATION_KEY`, `REPOSITORY`, `BASE_SHA`, `CARRIER_BRANCH`, `MODE`.
- Carrier branch form is exactly `claude/op-<operation-key>`; the `claude/` prefix is fleet convention, not provider identity.
- A collision never authorizes a random replacement key, sibling branch, auto-takeover, reset, force-push, or cross-carrier failover.
- `RECONCILE_STATE.md` remains the owner of duplicate/conflict reconciliation semantics.
- Agent OS claim state remains advisory only; this wave must not make it a gate.
- Do not touch `control_plane/`, Executive schemas, Slack/MCP intent ids, Macro worker hooks, or Agent OS records in this PR.

---

### Task 1: Pin the Skillpack identity law with a focused regression test

**Files:**
- Create: `tests/test_sol_skillpack_single_carrier.py`
- Read: `docs/sol_skills/INDEX.md`
- Read: `docs/sol_skills/COMMISSION_WAVE.md`
- Read: `docs/sol_skills/RECONCILE_STATE.md`

**Interfaces:**
- Consumes: the current protected Skillpack Markdown/frontmatter format.
- Produces: executable regression vectors and literal contract checks that Tasks 2–3 must satisfy.

- [ ] **Step 1: Create the failing regression test**

Create `tests/test_sol_skillpack_single_carrier.py` with this complete content:

```python
from __future__ import annotations

import hashlib
import re
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "docs/sol_skills/INDEX.md"
COMMISSION = ROOT / "docs/sol_skills/COMMISSION_WAVE.md"
RECONCILE = ROOT / "docs/sol_skills/RECONCILE_STATE.md"
FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)
DOMAIN = b"mastermind.agentos.work_identity.v1\x00"


def _frontmatter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    match = FRONTMATTER_RE.match(text)
    assert match is not None, f"missing YAML frontmatter: {path}"
    data = yaml.safe_load(match.group(1))
    assert isinstance(data, dict)
    return data


def _derive(work_id: str) -> str:
    return "ws-" + hashlib.sha256(DOMAIN + work_id.encode("utf-8")).hexdigest()[:32]


def test_manual_work_identity_vectors_are_frozen() -> None:
    assert _derive("WS:ALPHA-INTELLIGENCE-INTEGRATION#K3E-SRC-A1P") == (
        "ws-1198dccd042baab74b88a44e3ee5fb3b"
    )
    assert _derive("WS:CHAIRMAN-CONTROL-ROOM#A2") == (
        "ws-3ed8ecdbc8b6af7c5d5fa205fdd7db1a"
    )
    assert _derive("WS:EXECUTIVE-CAPACITY-FABRIC#CF2-F") == (
        "ws-54230ac4a84ff4b93528db1db5f2a905"
    )


def test_a2_keeps_skillpack_compatibility_unchanged() -> None:
    for path in (INDEX, COMMISSION, RECONCILE):
        frontmatter = _frontmatter(path)
        assert frontmatter["schema"] == "mastermind.sol_skillpack.v1"
        assert frontmatter["skillpack_version"] == "1.0.0"
        assert frontmatter["minimum_bootstrap_major"] == 1


def test_commission_wave_prints_the_deterministic_manual_identity_contract() -> None:
    text = COMMISSION.read_text(encoding="utf-8")
    required = (
        "WORK_ID = WS:<WORKSTREAM>#<WAVE_ID>",
        "mastermind.agentos.work_identity.v1",
        '"ws-"',
        "WORK_ID:",
        "OPERATION_KEY:",
        "REPOSITORY:",
        "BASE_SHA:",
        "CARRIER_BRANCH:",
        "MODE:",
        "claude/op-<operation-key>",
        "review_only",
        "RECONCILE_STATE.md",
    )
    for literal in required:
        assert literal in text


def test_reconcile_state_uses_the_same_manual_operation_identity() -> None:
    text = RECONCILE.read_text(encoding="utf-8")
    required = (
        "WORK_ID",
        "OPERATION_KEY",
        "CARRIER_BRANCH",
        "mastermind.agentos.work_identity.v1",
        "DUPLICATE_ACTIVE",
        "RECONCILE_REQUIRED",
        "ALREADY_FINISHED",
        "CONFLICT",
    )
    for literal in required:
        assert literal in text
```

- [ ] **Step 2: Run the focused test and confirm it fails for missing A2 law**

Run:

```bash
pytest -q tests/test_sol_skillpack_single_carrier.py
```

Expected: the metadata/vector tests pass, while at least the `COMMISSION_WAVE.md` and `RECONCILE_STATE.md` contract tests fail because the new manual identity/carrier literals are not yet present.

- [ ] **Step 3: Commit only the failing test**

```bash
git add tests/test_sol_skillpack_single_carrier.py
git commit -m "test(sol): pin deterministic commission identity law"
```

---

### Task 2: Amend `COMMISSION_WAVE.md` with deterministic work identity and handoff preamble

**Files:**
- Modify: `docs/sol_skills/COMMISSION_WAVE.md`
- Test: `tests/test_sol_skillpack_single_carrier.py`

**Interfaces:**
- Consumes: Agent OS `WS:<KEY>` + inline wave id, the existing high-level CEO request `operation_key` vocabulary, and the existing collision fence.
- Produces: one deterministic `WORK_ID`/`OPERATION_KEY`/`CARRIER_BRANCH` tuple and a mandatory modifying handoff preamble for A3 and later manual waves.

- [ ] **Step 1: Add the exact identity subsection before the existing operator-handoff construction**

Insert a section in `COMMISSION_WAVE.md` after the observable-mission step and before the full handoff fields. Use this exact contract text, adjusting only surrounding heading numbers if needed:

```markdown
## Manual modifying work identity

For substantial manual modifying work that belongs to an Agent OS workstream, the commission must name one exact durable work unit:

```text
WORK_ID = WS:<WORKSTREAM>#<WAVE_ID>
```

The operation key is derived mechanically, never creatively authored:

```text
operation_key =
  "ws-" + first_32_hex(
    sha256(
      b"mastermind.agentos.work_identity.v1\x00" + WORK_ID_utf8
    )
  )
```

The implementation carrier for a repository is:

```text
claude/op-<operation-key>
```

The `claude/` prefix is repository fleet convention, not worker/provider identity. Retries and reconciliation reuse the same work identity, operation key and carrier. A worker/session/provider name, timestamp or random nonce must never be added merely to escape a collision.

Substantial modifying work without a durable workstream/wave is outside the hard semantic-dedupe guarantee of Manual V0. Do not invent a task registry or approximate workstream to hide that gap.
```

- [ ] **Step 2: Add the mandatory preamble to the operator handoff contract**

Add this exact block immediately before the existing prose handoff sections:

```markdown
For an Agent-OS-backed modifying commission, put this machine-readable preamble before the prose mission:

```text
WORK_ID: WS:<KEY>#<WAVE>
OPERATION_KEY: ws-<32hex>
REPOSITORY: <owner/repo>
BASE_SHA: <40-hex>
CARRIER_BRANCH: claude/op-ws-<32hex>
MODE: modifying
```

For an independent verifier/reviewer, use `MODE: review_only`; review-only work does not claim the modifying carrier.

The worker must recompute the operation key from `WORK_ID` once the repository preflight implementation exists and refuse any mismatch.
```

- [ ] **Step 3: Strengthen the existing collision-fence step without adding a new authority plane**

Extend the collision-fence section with these explicit outcomes:

```markdown
For manual modifying work, an existing canonical carrier is not an invitation to mint a sibling branch. Classify the result as duplicate/finished/conflict/ambiguous and use `RECONCILE_STATE.md` before any takeover. Never change `OPERATION_KEY`, append a session/provider suffix, delete the remote carrier, reset it, or auto-failover merely to make the dispatch proceed.
```

- [ ] **Step 4: Run the focused test**

```bash
pytest -q tests/test_sol_skillpack_single_carrier.py
```

Expected: the `COMMISSION_WAVE.md` contract test passes; the reconciliation test still fails until Task 3.

- [ ] **Step 5: Commit the procedure change**

```bash
git add docs/sol_skills/COMMISSION_WAVE.md
git commit -m "docs(sol): derive one manual commission carrier"
```

---

### Task 3: Amend `RECONCILE_STATE.md` with deterministic manual-carrier reconciliation

**Files:**
- Modify: `docs/sol_skills/RECONCILE_STATE.md`
- Test: `tests/test_sol_skillpack_single_carrier.py`

**Interfaces:**
- Consumes: `WORK_ID`, derived `OPERATION_KEY`, and `CARRIER_BRANCH` from Task 2.
- Produces: deterministic duplicate/conflict/ambiguous-carrier handling that A3 can surface as machine states.

- [ ] **Step 1: Add a manual-carrier subsection under duplicate/conflict semantics**

Add this exact conceptual law:

```markdown
### Manual Git carrier identity

For Agent-OS-backed manual modifying work, freeze all three identities before repair:

```text
WORK_ID = WS:<WORKSTREAM>#<WAVE_ID>
OPERATION_KEY = "ws-" + first_32_hex(sha256(b"mastermind.agentos.work_identity.v1\x00" + WORK_ID_utf8))
CARRIER_BRANCH = claude/op-<operation-key>
```

These are one logical operation. Session/provider labels are provenance only and cannot create a sibling operation.

When the Manual Single-Carrier Guard reports:

- `DUPLICATE_ACTIVE` -> another carrier is visibly active; perform zero modification and report/review only;
- `RECONCILE_REQUIRED` -> ownership/completion is ambiguous; preserve the existing carrier and inspect branch/PR/worktree/return evidence;
- `ALREADY_FINISHED` -> historical merged carrier proves this logical operation completed; do not recreate it;
- `CONFLICT` -> the same work identity is paired with incompatible frozen commission metadata; refuse rather than rewrite the operation.

A stale-looking or abandoned carrier is never automatically deleted, reset, force-pushed or replaced. A lawful transfer keeps the same `WORK_ID`, `OPERATION_KEY` and `CARRIER_BRANCH` after explicit reconciliation.
```

- [ ] **Step 2: Ensure the existing duplicate/conflict rules still say changed work gets a new explicit operation identity**

Keep the existing law:

```text
same key + same fingerprint/payload -> same operation / duplicate reconciliation
same key + changed normalized payload -> conflict/refusal
changed work -> new explicit operation key
```

Clarify that for Agent-OS-backed manual work, “changed work” means a genuinely different durable wave identity, not a random key minted to bypass a collision.

- [ ] **Step 3: Run the focused regression test**

```bash
pytest -q tests/test_sol_skillpack_single_carrier.py
```

Expected: `4 passed`.

- [ ] **Step 4: Commit the reconciliation law**

```bash
git add docs/sol_skills/RECONCILE_STATE.md
git commit -m "docs(sol): reconcile deterministic manual carriers"
```

---

### Task 4: Verify A2 as a protected Skillpack-only change and prepare the exact A3 handoff inputs

**Files:**
- Verify only: `docs/sol_skills/COMMISSION_WAVE.md`
- Verify only: `docs/sol_skills/RECONCILE_STATE.md`
- Verify only: `tests/test_sol_skillpack_single_carrier.py`

**Interfaces:**
- Consumes: Tasks 1–3.
- Produces: an A2 PR ready for Sol review, plus the deterministic identity inputs A3 must use after A2 is merged.

- [ ] **Step 1: Run the focused tests and the existing CEO-request compatibility suite**

```bash
pytest -q \
  tests/test_sol_skillpack_single_carrier.py \
  tests/test_executive_ceo_request.py \
  tests/test_executive_mcp_submit.py
```

Expected: all selected tests pass. The CEO-request tests demonstrate that A2 did not mutate the existing MCP/Slack high-level request implementation merely by documenting the future manual law.

- [ ] **Step 2: Prove the changed-file boundary**

Run:

```bash
git diff --name-only origin/master...HEAD
```

Expected exactly:

```text
docs/sol_skills/COMMISSION_WAVE.md
docs/sol_skills/RECONCILE_STATE.md
tests/test_sol_skillpack_single_carrier.py
```

If any `control_plane/`, integration, runtime, installer, or other Skillpack file appears, stop and remove that widening before review.

- [ ] **Step 3: Re-read current protected `master` before PR creation**

Run:

```bash
git fetch origin master
git log -1 --format=%H origin/master
git diff --name-only <A2_PICKUP_BASE_SHA>..origin/master -- docs/sol_skills/ control_plane/ceo_request.py
```

`<A2_PICKUP_BASE_SHA>` is the exact SHA printed and recorded when the implementer starts the branch. If `COMMISSION_WAVE.md`, `RECONCILE_STATE.md`, `INDEX.md`, or the shared CEO-request identity law moved materially after pickup, stop for Sol reconciliation instead of rebasing through a semantic collision.

- [ ] **Step 4: Push/open the A2 PR and let hosted checks conclude**

Use the repository’s normal protected-branch PR flow. The PR body must state:

```text
Capability gained: independent Sol sessions given the same Agent OS workstream/wave now derive the same manual operation identity and carrier preamble.
Does not make true: no Macro guard exists yet; no worker is prevented from modifying yet; no Executive cross-transport dedupe exists.
Next dependency: A3 Macro Manual Single-Carrier Guard.
```

- [ ] **Step 5: After A2 merges, pin the exact protected merge SHA for A3**

Record the merged protected `master` SHA and load `INDEX.md`, `COMMISSION_WAVE.md`, and `RECONCILE_STATE.md` atomically from that SHA before commissioning A3.

For the planned A3 organizational identity, use:

```text
WORK_ID: WS:CHAIRMAN-CONTROL-ROOM#SCG-A3
OPERATION_KEY: ws-1a2cf7ff85edc2c97ebf023856b94ab8
CARRIER_BRANCH: claude/op-ws-1a2cf7ff85edc2c97ebf023856b94ab8
```

The hash is the frozen algorithm applied to the stated `WORK_ID`; A3 preflight must recompute it independently.

- [ ] **Step 6: Stop**

A2 is complete when the protected Skillpack procedure is merged and current, its focused regression test is green, and A3 can be commissioned with the deterministic identity above. Do not implement Macro or Executive runtime changes in this branch.

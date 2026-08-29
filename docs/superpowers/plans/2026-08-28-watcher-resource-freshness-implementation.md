# Watcher Resource Discipline + Carrier Freshness Implementation Plan

> **Execution discipline:** implement this plan task-by-task with current protected-source reconciliation before every modifying carrier. Do not skip RED, do not widen into runtime enforcement, and do not treat records/merge as production proof.

## Goal

Make the Chairman-approved watcher resource/freshness design durable in the canonical Mastermind procedure and shared worker bootstrap so a fresh Fable/Opus/Claude/Codex/Sol session is told, before work begins, that:

- expensive reasoning models are not polling daemons;
- reasoning-model scheduled polling defaults to 60 minutes, has a hard 15-minute floor, and backs off 15 -> 30 -> 60 minutes after no-change urgent wakes;
- once only an external dependency remains, a principal yields instead of manually live-polling;
- one watcher is allowed per side + operation + exact carrier + purpose;
- watcher silence / `WATCH_ARMED` never proves the carrier is fresh;
- before every substantive reciprocal write, the sender freshly reads the exact carrier after the latest local evidence-producing action and consumes unseen opposite-side semantic edges first;
- initial pickup ACK remains compatible with the accepted ACK-before-read handshake and asserts pickup/identity only;
- a missed watcher fire is reconciled by directly reading the carrier, never by shortening the cadence;
- `NO_MATERIAL_CHANGE` is a one-bounded-delta-read quiescent exit;
- #202's watcher-lifetime law remains intact: nonterminal ACK/WATCH_ARMED/START/PROGRESS/RESULT do not terminate the dialogue watcher; only terminal STOP closes the cycle.

## Architecture

There is **one universal procedure owner**: `docs/AGENT_DIALOGUE_SESSION_CLOSE_LAW.md` in protected Mastermind. The Sol Skillpack and root worker instruction files point to and operationalize that law; they do not become parallel watcher-policy stores.

The rollout is split into independently useful carriers:

1. **Mastermind source-law carrier** — universal law + Sol procedural projections + root `AGENTS.md`/`CLAUDE.md` + contract tests.
2. **Macro Agent OS decision carrier** — durable organizational memory citing the accepted Mastermind merge; Agent OS remains evidence/knowledge only, not procedure authority.
3. **Macro bootstrap carrier** — only after Macro PR #6381 is terminally reconciled; amend Macro `AGENTS.md` + `CLAUDE.md` without overwriting its specialized ship-loop watcher guard work.
4. **Active-session visibility step** — bounded Slack visibility to already-running Fable/Opus/COO sessions after the merged law exists, where exact current carriers are lawfully available.
5. **Mechanical enforcement program** — explicitly out of scope here. It must later extend existing Worker Presence / Agent Dialogue / Wake and owner-specific host guards; no new watcher DB/queue/cursor/lifecycle plane.

## Technology / verification surfaces

- Markdown source law and worker bootstrap files.
- `pytest` source-contract tests.
- Protected GitHub `master` with required `test` status.
- Macro Agent OS (`agentos/`) + `python3 scripts/agentos.py validate --quiet`.
- Slack only as transport/visibility, never durable authority.

## Current planning receipts

- Approved design logical operation: `watcher-resource-freshness-design-20260828-sol-001`.
- Approved design exact head: `f11dec932100fb22b8722ae2b5a14bfb9e14a3e5`.
- Sole active design carrier: Mastermind PR #205; #203 is CLOSED / UNMERGED / superseded only because the available draft->ready connector mutation was broken and effect was reconciled false.
- Planning base: protected Mastermind `master@1d5ad1249172e8b93882f0dff157fc13636dd62d`.
- Current Skillpack at planning base: `mastermind.sol_skillpack.v1` v1.0.1 / bootstrap-major 1.
- #202 / `f61ced39d47f935b1dea369bd3ed25e06c954d08` already made watcher lifetime explicit through nonterminal events until terminal STOP; preserve it exactly.
- Macro PR #6381 remains the known overlapping carrier for Macro `AGENTS.md` / `CLAUDE.md` and specialized ship-loop watcher quiescence/one-watcher behavior. Never create a competing edit carrier while it remains nonterminal.

## Global non-goals

Do not in this plan:

- build or install a new watcher daemon/service;
- create a new watcher registry, cursor DB, queue, retry plane, lifecycle or memory store;
- alter Executive Job/Attempt/Worker/Event semantics;
- alter provider/account routing or capacity authority;
- change Slack app manifests/tokens/installations;
- claim Worker Presence / Turn-Watcher is production-live merely because procedure changed;
- edit Macro `AGENTS.md` or `CLAUDE.md` before #6381 is terminally reconciled;
- use one long PR across Mastermind + Macro;
- add runtime cadence enforcement to the source-law PR;
- weaken #202 watcher lifetime behavior in order to reduce token use.

---

# Wave A — Mastermind source law + shared bootstrap

**Logical operation:** `watcher-resource-freshness-source-law-20260828-sol-001`

**Observable capability:** after merge, a fresh Mastermind worker/Sol session reading the canonical root instructions and Skillpack receives one consistent resource-safe watcher and carrier-freshness procedure, and automated contract tests reject regressions such as 5–10 second model polling, watcher-silence freshness assumptions, or removal of #202 lifetime semantics.

**Capability after merge:** procedure/bootstrapping is durable; runtime/mechanical enforcement remains `NOT_BUILT`. Do not call the operational problem `PROVEN_LIVE` until real sessions demonstrate the policy and later runtime enforcement exists.

## Task A0 — Predecessor and current-source gate

**Files:** read-only preflight; no file changes.

### Step A0.1 — Require the approved design to be durable

Before opening the implementation branch, verify Mastermind PR #205 is merged and that the merge contains exactly approved design head `f11dec932100fb22b8722ae2b5a14bfb9e14a3e5` or a GitHub-approved squash of that exact content.

Expected if not yet merged:

```text
HOLD — DESIGN_NOT_DURABLE
```

Do not duplicate the design carrier or copy the spec manually into the implementation branch as a substitute.

### Step A0.2 — Re-pin protected procedure atomically

Fetch current protected `master`, then from that exact SHA read at minimum:

- `docs/sol_skills/INDEX.md`
- `docs/sol_skills/COLD_START.md`
- `docs/sol_skills/COMMISSION_WAVE.md`
- `docs/sol_skills/WATCHER_ACTION_LOOP.md`
- `docs/sol_skills/RECONCILE_STATE.md`
- `docs/sol_skills/REVIEW_RETURN.md`
- `docs/sol_skills/CLOSEOUT.md`
- `docs/AGENT_DIALOGUE_SESSION_CLOSE_LAW.md`
- `AGENTS.md`
- `CLAUDE.md`

Verify schema/version/bootstrap compatibility before modification.

### Step A0.3 — Collision census

Search open/recent PRs touching any of:

```text
docs/AGENT_DIALOGUE_SESSION_CLOSE_LAW.md
docs/sol_skills/INDEX.md
docs/sol_skills/COMMISSION_WAVE.md
docs/sol_skills/WATCHER_ACTION_LOOP.md
docs/sol_skills/RECONCILE_STATE.md
AGENTS.md
CLAUDE.md
tests/test_sol_watcher_action_loop_skill.py
tests/test_watcher_resource_discipline_source_law.py
```

If a newer accepted source-law PR landed after this plan, reconcile it first. If another nonterminal carrier owns the same logical change, do not create a second implementation PR.

### Step A0.4 — Preserve #202 explicitly

Read `tests/test_sol_watcher_action_loop_skill.py` and confirm its watcher-lifetime test still requires:

- ACK/WATCH_ARMED/START/PROGRESS nonterminal behavior;
- BLOCKED/DECISION_REQUEST/RESULT action-required behavior;
- watcher remains/re-arms through nonterminal returns;
- Sol disarms only after terminal STOP.

If these assertions changed, stop and reconcile rather than coding from this plan.

---

## Task A1 — Add RED contract tests for the Chairman-approved policy

**Files:**

- Create: `tests/test_watcher_resource_discipline_source_law.py`
- Preserve: `tests/test_sol_watcher_action_loop_skill.py`

### Step A1.1 — Create the focused source-law test file

Use a small file-reader helper consistent with `tests/test_sol_watcher_action_loop_skill.py` and add these tests:

```python
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _flat(path: str) -> str:
    return " ".join(_read(path).split())


def test_universal_dialogue_law_has_resource_classes_and_model_wake_floor() -> None:
    law = _flat("docs/AGENT_DIALOGUE_SESSION_CLOSE_LAW.md")
    for phrase in (
        "Class E",
        "Class T",
        "Class M",
        "Default interval: 60 minutes",
        "Absolute minimum interval: 15 minutes",
        "15m -> 30m -> 60m",
        "principals, not polling daemons",
    ):
        assert phrase in law


def test_universal_dialogue_law_requires_yield_one_watcher_and_quiescence() -> None:
    law = _flat("docs/AGENT_DIALOGUE_SESSION_CLOSE_LAW.md")
    for phrase in (
        "external dependency",
        "yield",
        "side + operation_key + exact carrier + purpose",
        "NO_MATERIAL_CHANGE",
        "one bounded",
    ):
        assert phrase in law


def test_universal_dialogue_law_requires_fresh_read_before_substantive_write() -> None:
    law = _flat("docs/AGENT_DIALOGUE_SESSION_CLOSE_LAW.md")
    for phrase in (
        "Fresh-read the exact bound carrier/thread in the same interactive turn",
        "after the latest local evidence-producing action",
        "WATCH_ARMED",
        "never satisfies this freshness fence",
        "pickup ACK",
    ):
        assert phrase in law


def test_commission_wave_no_longer_requests_fastest_supported_polling() -> None:
    commission = _flat("docs/sol_skills/COMMISSION_WAVE.md")
    assert "fastest lawful/practical cadence" not in commission
    for phrase in (
        "60 minutes",
        "15 minutes",
        "15m -> 30m -> 60m",
        "external dependency",
        "yield",
    ):
        assert phrase in commission


def test_watcher_action_loop_handles_no_change_and_missed_fire_without_faster_polling() -> None:
    loop = _flat("docs/sol_skills/WATCHER_ACTION_LOOP.md")
    for phrase in (
        "NO_MATERIAL_CHANGE",
        "one bounded",
        "watcher silence",
        "degraded evidence",
        "do not shorten",
        "fresh-read",
    ):
        assert phrase in loop


def test_reconcile_state_treats_watcher_silence_as_non_authoritative() -> None:
    reconcile = _flat("docs/sol_skills/RECONCILE_STATE.md")
    for phrase in (
        "watcher silence",
        "does not prove",
        "exact lawful carrier/thread",
        "do not shorten",
    ):
        assert phrase in reconcile


def test_shared_bootstraps_point_to_the_universal_watcher_law() -> None:
    for path in ("AGENTS.md", "CLAUDE.md"):
        text = _flat(path)
        assert "docs/AGENT_DIALOGUE_SESSION_CLOSE_LAW.md" in text
        assert "60 minutes" in text
        assert "15 minutes" in text
        assert "fresh" in text.lower()
        assert "carrier" in text.lower()
```

The exact final wording may be adjusted only if it preserves the semantic assertions above; do not weaken tests merely to match prose.

### Step A1.2 — Run RED

Run:

```bash
pytest -q tests/test_watcher_resource_discipline_source_law.py tests/test_sol_watcher_action_loop_skill.py
```

Expected before implementation:

- new resource/freshness assertions fail because the universal law and projections do not yet contain them;
- the existing #202 watcher-lifetime test remains GREEN.

If #202's existing test is red before any implementation edit, stop: the base is not safe.

### Step A1.3 — Commit RED only

```bash
git add tests/test_watcher_resource_discipline_source_law.py
git commit -m "test(sol): freeze watcher resource and freshness law"
```

Do not edit source-law prose in this commit.

---

## Task A2 — Implement the universal source law in its single owner

**Files:**

- Modify: `docs/AGENT_DIALOGUE_SESSION_CLOSE_LAW.md`
- Test: `tests/test_watcher_resource_discipline_source_law.py`

### Step A2.1 — Add resource classes and cadence law

Within the worker/COO reciprocal-watcher section, add one authoritative subsection defining:

- **Class E** — event/passive wait that does not re-enter reasoning on unchanged samples;
- **Class T** — deterministic tool-only polling that suppresses unchanged samples;
- **Class M** — model-wake polling.

Class M law must say exactly in substance:

```text
normal default = 60 minutes
hard floor = 15 minutes
urgent no-change sequence = 15m -> 30m -> 60m
below-floor request = refuse or round up, never obey because the host supports it
```

State explicitly that Fable/Opus/high-reasoning principals are not polling daemons.

### Step A2.2 — Add principal-yield boundary

When only an external dependency remains, require the principal to:

1. arm/reuse the lawful watcher/waiter;
2. emit the truthful wait receipt when applicable;
3. yield/end the reasoning turn.

Forbid interactive `check -> sleep a few seconds -> check again` loops whose purpose is merely waiting for external state.

### Step A2.3 — Add one-watcher discipline

For the same side of one operation, allow at most one active watcher for:

```text
side + operation_key + exact carrier + purpose
```

Sol and worker may each have one because they are different sides. Distinct CI and Slack-return watchers may coexist only when their conditions/endpoints are genuinely distinct.

Do not introduce a durable watcher registry to enforce the prose.

### Step A2.4 — Add read-before-substantive-write freshness fence

Before substantive reciprocal carrier writes (`START`, progress/gate state, `BLOCKED`, `DECISION_REQUEST`, `RESULT`, CI/proof completion, Sol continuation/ruling/repair/park/STOP):

1. fresh-read exact bound carrier in the same interactive turn;
2. perform the read after the latest local evidence-producing action;
3. compare with latest consumed baseline;
4. consume/adjudicate unseen opposite-side semantic edges first;
5. only then compose/send the outbound state.

State explicitly:

- `WATCH_ARMED`, no notification, and local memory never satisfy freshness;
- pickup ACK is the narrow exception because accepted pickup law is ACK-before-full-read; ACK may assert receipt/receiver identity only, not execution/gate/completion state;
- inability to fresh-read blocks substantive stale assertions and does not authorize failover.

### Step A2.5 — Add missed-fire and quiescence law

If multiple expected Class-M fire opportunities pass without a wake while the dialogue remains nonterminal:

- watcher becomes degraded evidence;
- fresh-read carrier directly;
- do not shorten cadence;
- repair/re-arm safely or return the accepted watcher-unavailable/degraded blocker.

For `NO_MATERIAL_CHANGE`:

```text
WAKE -> one bounded exact-carrier/status delta read -> NO_MATERIAL_CHANGE -> exit
```

No broad repo archaeology, multiple source scans, subagents, long Chairman prose, lifecycle changes, retries or duplicate watcher creation.

### Step A2.6 — Update incident rationale

Append both incidents without turning the document into live workstream state:

- hot Fable polling showed missing cadence/resource floor;
- Opus stale Slack post showed watcher presence cannot replace carrier freshness.

Frame them as why the universal procedure exists, not as runtime state.

### Step A2.7 — Run focused GREEN

```bash
pytest -q tests/test_watcher_resource_discipline_source_law.py
```

Expected: tests that target the universal law pass; projection tests may still fail until Task A3/A4.

### Step A2.8 — Commit

```bash
git add docs/AGENT_DIALOGUE_SESSION_CLOSE_LAW.md
git commit -m "docs(agent): bound watcher cadence and carrier freshness"
```

---

## Task A3 — Project the universal law into Sol procedure without regressing #202

**Files:**

- Modify: `docs/sol_skills/COMMISSION_WAVE.md`
- Modify: `docs/sol_skills/WATCHER_ACTION_LOOP.md`
- Modify: `docs/sol_skills/RECONCILE_STATE.md`
- Modify: `docs/sol_skills/INDEX.md`
- Preserve/Test: `tests/test_sol_watcher_action_loop_skill.py`
- Test: `tests/test_watcher_resource_discipline_source_law.py`

### Step A3.1 — Repair `COMMISSION_WAVE.md`

Delete the ambiguous instruction:

```text
use the fastest lawful/practical cadence the host actually supports
```

Replace it with the Class E/T/M selection rule:

1. prefer event/passive wait;
2. otherwise use deterministic tool-only polling that suppresses unchanged samples;
3. only if model-wake scheduling is the available bridge, use 60m default, never below 15m, urgent no-change backoff 15->30->60;
4. when only external dependency remains, principal yields after arming/reusing the watcher;
5. one watcher per side/op/carrier/purpose;
6. every `WATCH_ARMED` receipt states actual class/mechanism/cadence.

Also add the read-before-substantive-write requirement to the worker envelope so future handoffs carry it automatically.

### Step A3.2 — Extend `WATCHER_ACTION_LOOP.md`

Preserve the entire #202 watcher-lifetime invariant.

Add:

- a wake does not prove current carrier state;
- `NO_MATERIAL_CHANGE` gets one bounded delta read then exits;
- scheduled model wake obeys universal 60m/default, 15m/floor, and backoff law;
- missed expected fires make the watcher degraded evidence and force direct carrier read;
- do not shorten cadence to compensate;
- before Sol posts a substantive continuation/ruling/STOP, fresh-read the exact carrier after latest evidence/adjudication input.

The watcher action loop remains:

```text
DETECT -> RE-PIN -> ADJUDICATE -> ACT -> REPORT
```

but `RE-PIN` is required only on a qualifying material return before modification; do not run full Skillpack archaeology on a no-change wake.

### Step A3.3 — Extend `RECONCILE_STATE.md`

Within dialogue/watcher reconciliation, state:

- watcher silence does not prove no opposite-side turn exists;
- direct exact-carrier evidence owns dialogue freshness;
- when expected watcher fires are missed, read carrier and preserve operation/carrier binding;
- do not increase polling frequency as repair;
- leftover/missed watcher never grants retry/new-wave authority.

### Step A3.4 — Add concise universal hard laws to `INDEX.md`

Add compact hard laws, without duplicating the whole source-law body:

- reasoning-model watcher resource floor/default/backoff + principal yield;
- watcher silence never establishes carrier freshness; substantive writes require same-turn exact-carrier reread after latest evidence-producing action;
- one watcher per side/op/carrier/purpose and cheap `NO_MATERIAL_CHANGE` quiescence.

Keep #202's watcher-lifetime semantics intact.

### Step A3.5 — Run regression tests

```bash
pytest -q tests/test_watcher_resource_discipline_source_law.py tests/test_sol_watcher_action_loop_skill.py
```

Expected: all pass.

Then prove the ambiguous phrase is gone:

```bash
git grep -n "fastest lawful/practical cadence" -- docs/sol_skills/COMMISSION_WAVE.md
```

Expected: no output, exit 1 from `git grep` because there are zero matches.

Prove #202 wording still exists:

```bash
git grep -n "ACK, WATCH_ARMED, START, and PROGRESS are nonterminal watcher events" -- docs/sol_skills/WATCHER_ACTION_LOOP.md
```

Expected: exactly one match.

### Step A3.6 — Commit

```bash
git add docs/sol_skills/COMMISSION_WAVE.md docs/sol_skills/WATCHER_ACTION_LOOP.md docs/sol_skills/RECONCILE_STATE.md docs/sol_skills/INDEX.md
git commit -m "docs(sol): propagate resource-safe watcher procedure"
```

---

## Task A4 — Put the invariant in shared Mastermind worker bootstrap

**Files:**

- Modify: `AGENTS.md`
- Modify: `CLAUDE.md`
- Test: `tests/test_watcher_resource_discipline_source_law.py`

### Step A4.1 — Add one concise shared section to both files

Near the Executive contract / worker behavior, add a short section titled conceptually `Watcher dialogue discipline` containing:

- canonical pointer: `docs/AGENT_DIALOGUE_SESSION_CLOSE_LAW.md`;
- premium/reasoning models are not polling daemons;
- model-wake default 60m, hard floor 15m, 15->30->60 no-change backoff;
- yield once only external wait remains;
- before any substantive reciprocal post, fresh-read exact carrier after the latest evidence-producing action and consume unseen opposite-side edge first;
- initial pickup ACK remains receipt-only and follows the accepted ACK-before-read handshake;
- one watcher per side/op/carrier/purpose;
- watcher silence is never freshness/authority.

Do not paste the full universal law into both root files.

### Step A4.2 — Run tests

```bash
pytest -q tests/test_watcher_resource_discipline_source_law.py tests/test_sol_watcher_action_loop_skill.py
```

Expected: all pass.

### Step A4.3 — Commit

```bash
git add AGENTS.md CLAUDE.md
git commit -m "docs(workers): bootstrap watcher resource and freshness law"
```

---

## Task A5 — Adversarial verification, exact-head CI and protected merge

**Files:** no new intended source files; review/repair only if findings are real and bounded.

### Step A5.1 — Re-run current-source collision check

Immediately before PR review/merge:

- fetch protected `master`;
- compare changed paths;
- inspect new open PRs touching the same law/instruction/test surfaces;
- preserve any newer accepted watcher-lifetime/source law.

Do not rebase/reset over unexpected same-surface work without reconciliation.

### Step A5.2 — Run the focused suite

```bash
pytest -q tests/test_watcher_resource_discipline_source_law.py tests/test_sol_watcher_action_loop_skill.py
```

Expected: all pass.

Also run any repository-prescribed relevant suite discovered on current `master`; do not invent a new CI bypass.

### Step A5.3 — Adversarial review checklist

Reject the implementation if any of these mutations would pass unnoticed:

1. `60 minutes` default removed or replaced with provider-fastest cadence;
2. 15-minute floor removed;
3. 15->30->60 backoff removed;
4. principal may remain in a manual tight wait loop;
5. watcher silence is allowed to imply no thread change;
6. carrier read can happen only before CI/background work rather than after it;
7. initial ACK incorrectly requires full read first or is allowed to claim substantive state;
8. duplicate same-purpose watchers are permitted;
9. no-change wake performs broad archaeology/reasoning;
10. #202 nonterminal watcher lifetime is weakened;
11. watcher gains lifecycle/retry/new-wave authority;
12. a second watcher policy/store is created.

### Step A5.4 — Open one implementation PR

PR body must state:

- design #205 + merge SHA;
- exact protected source pin used for implementation;
- #202 preservation receipt;
- RED->GREEN test receipt;
- changed files;
- what the merge makes true;
- what remains not enforced at runtime;
- Macro #6381 remains separately owned.

### Step A5.5 — Wait resource-safely for required CI

Do **not** hot-poll CI. Prefer event/passive wait. If only model-wake observation is possible, use the newly approved Class-M discipline rather than seconds-level loops.

Required protected status: `test` green on the exact final head.

### Step A5.6 — Merge with exact-head guard

Only after exact-head review and required status are green, squash-merge the exact reviewed head.

Record merge SHA. Do not claim runtime watcher enforcement from the merge.

---

# Wave B — Durable Agent OS Chairman ruling / incident memory

**Repository:** `mastermindx-market-intelligence/macro`

**Logical operation:** `watcher-resource-freshness-agentos-20260828-sol-001`

**Observable capability:** a fresh cross-session organizational cold start can recover why the watcher policy changed, the Chairman ruling, the accepted Mastermind source-law SHA, and remaining enforcement gaps without relying on this chat or account-local Fable memory.

## Task B0 — Gate on accepted Mastermind source law

Do not create the Agent OS decision until Wave A is merged. Pin the exact Mastermind merge SHA and current Macro `main`.

Search Agent OS for an existing decision that already owns this same ruling. If one exists, update/reconcile that owner rather than creating a duplicate decision concept.

## Task B1 — Create one Agent OS decision record

**Files:**

- Create: `agentos/decisions/DEC-WATCHER-RESOURCE-DISCIPLINE-AND-CARRIER-FRESHNESS.md`

Use the current Agent OS decision schema/style on Macro `main`. The decision must contain:

- **question:** how reciprocal watchers may wait without burning scarce reasoning capacity or allowing stale carrier writes;
- **answer:** the approved Class E/T/M cadence law, principal yield, one-watcher rule, read-before-substantive-write fence, missed-fire reconciliation, cheap no-change exit;
- **rationale:** both observed incident classes;
- **evidence:** Chairman 2026-08-28 directive/approval, Mastermind design #205/merge, Mastermind source-law implementation PR/merge, #202 watcher-lifetime compatibility;
- **alternatives rejected:** account-local Fable memory as company memory; 5–10s model polling; watcher-silence freshness; a new watcher control plane; overwriting #6381;
- **affects:** canonical Mastermind watcher law and worker bootstraps, plus future Worker Presence / Agent Dialogue / Wake enforcement;
- **capability honesty:** organizational decision durable; mechanical runtime enforcement still separate.

Explicitly state that Agent OS **cites** the Mastermind source law and is not a second procedure authority.

## Task B2 — Validate and ship the Agent OS record

Run:

```bash
python3 scripts/agentos.py validate --quiet
```

Expected: exit 0 / zero validation errors.

Run the current Macro records/semantic checks required for an Agent OS-only PR, then commit, push, open one bounded PR, obtain required CI, and merge.

Do not edit Macro `AGENTS.md` or `CLAUDE.md` in this carrier.

---

# Wave C — Macro shared bootstrap after PR #6381 reconciliation

**Repository:** `mastermindx-market-intelligence/macro`

**Logical operation:** `watcher-resource-freshness-macro-bootstrap-20260828-sol-001`

**Observable capability:** fresh Macro-hosted Claude/Fable/Codex sessions receive the same company-wide watcher resource/freshness invariant from the local shared instructions, while #6381's specialized ship-loop watcher guard remains intact.

## Task C0 — Reconcile #6381 before touching overlapping files

Read current Macro PR #6381.

- If #6381 is still open/nonterminal: **HOLD this wave.** Do not open a parallel `AGENTS.md` / `CLAUDE.md` carrier.
- If #6381 merged: pin its merge SHA and fetch current `main` versions of both instruction files.
- If #6381 closed unmerged/superseded: reconcile the replacement/current owner before editing.

## Task C1 — Add concise universal pointer to final Macro instructions

**Files:**

- Modify: `AGENTS.md`
- Modify: `CLAUDE.md`
- Optionally create one focused source-contract test only if current Macro instruction tests do not already protect the invariant.

Preserve #6381's final specialized rules. Add only the company-wide pointer/invariant:

- Mastermind `docs/AGENT_DIALOGUE_SESSION_CLOSE_LAW.md` is the universal watcher-dialogue procedure;
- model-wake default 60m / hard floor 15m / urgent backoff 15->30->60;
- principal yields on external-only waits;
- watcher silence never means carrier freshness;
- fresh exact-carrier read after latest local evidence before substantive posts;
- one watcher per side/op/carrier/purpose.

Do not copy the full Mastermind law or create a local competing source-law document.

## Task C2 — Verify and ship

Run Macro's current instruction/source-law tests and relevant CI. Confirm the diff does not alter #6381 guard code or its specialized semantics.

One PR, exact-head CI, merge. Capability remains procedural/bootstrap, not runtime proof of every Claude account.

---

# Wave D — Repin already-running Fable / Opus / COO sessions

**Transport:** current lawful Slack/session carriers only.

**Logical operation:** visibility only; do not invent Executive lifecycle identity for a notification.

## Task D1 — Identify only truly active reciprocal sessions

Use current Slack/hot-state evidence and existing operation keys. Do not broadcast to every old thread by title similarity.

For each active nonterminal worker/COO dialogue, fresh-read the exact thread first.

## Task D2 — Send one bounded policy visibility message where useful

Message content should state, compactly:

```text
Watcher procedure updated at Mastermind@<accepted-merge-sha>.
Before your next substantive post, fresh-read this exact thread after your latest local evidence-producing action and consume unseen Sol/worker edges first.
Reasoning-model watcher default=60m, floor=15m, urgent no-change backoff=15->30->60. Once only an external dependency remains, yield instead of live-polling. One watcher per side/op/carrier/purpose. Watcher silence is never carrier freshness.
Re-arm/continue only the existing operation under its current STOP/CONTINUE law.
```

This is transport visibility, not durable memory and not a new commission.

If a current thread already has terminal STOP, do not revive it to send the policy message.

---

# Wave E — Mechanical enforcement continuation (separate future program)

**Status:** `NOT_BUILT` after Waves A-D. This plan does not implement it.

Create a separate architecture/implementation wave only after current owner archaeology. It must extend existing owners and prove, at minimum:

1. controllable model-wake creation surfaces reject schedules below 15 minutes and coalesce duplicate same-purpose watchers;
2. frequent Class-T polling suppresses unchanged samples below the reasoning layer;
3. managed dialogue writes require a fresh exact-carrier read/baseline check where the connector can actually support it, failing closed rather than pretending atomicity;
4. telemetry exposes watcher kind, actual cadence, last successful read, and coalesced/refused counts through existing observability owners;
5. production proof demonstrates a 2–3 hour unchanged wait with bounded model re-entry/token use, a material reply waking the correct side, a deliberately missed watcher fire still caught by read-before-write, and terminal STOP disarming the temporary watcher.

Do not create a new durable watcher registry/daemon/control plane to make these tests easy.

---

# Final acceptance / closeout

After Waves A-D, record truth precisely:

```text
Universal source law: ACCEPTED / durable at Mastermind <merge_sha>
Mastermind fresh-session bootstrap: BUILT; production behavior proof still separate
Macro Agent OS decision: durable organizational memory, not procedure authority
Macro shared bootstrap: merged only if #6381 was reconciled first
Already-running sessions: visibility receipts only; delivery != consumption
Mechanical runtime enforcement: NOT_BUILT unless separately implemented/proven
```

Closeout must preserve:

- the exact Mastermind source-law merge SHA;
- Agent OS decision PR/merge SHA;
- Macro bootstrap PR/merge SHA when/if Wave C runs;
- any active-session Slack visibility receipts without upgrading them into lifecycle truth;
- #6381 reconciliation result;
- exact next mechanical-enforcement owner/action.

A fresh session should be able to recover the ruling without this conversation, and no watcher-enabled counterpart should be left awaiting an inferred terminal state.
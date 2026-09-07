---
schema: mastermind.chairman_control_room_df1_implementation_plan.v1
operation_key: chairman-control-room-df1-plan-20260907-sol-001
workstream: WS:CHAIRMAN-CONTROL-ROOM
parent_architecture_operation: chairman-control-room-decision-first-f0-20260907-sol-001
parent_architecture_pr: 521
stack_base: bc3d0f70eb024af82fdceac0d0cfd0fc61c0ad29
protected_source_pin: f9633f87bbaa22bd7864c756c8e0d1e0663899d0
protected_skillpack_sha: f9633f87bbaa22bd7864c756c8e0d1e0663899d0
skillpack_schema: mastermind.sol_skillpack.v1
skillpack_version: 1.0.1
minimum_bootstrap_major: 1
authorization_state: PLAN_AUTHORIZED_IMPLEMENTATION_HELD
capability_state: SPEC_ONLY
production_effect: NONE
---

# Chairman Control Room DF1 — Read-Only Today Canary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Use superpowers:test-driven-development before writing implementation code, superpowers:systematic-debugging for any unexpected failure, and superpowers:verification-before-completion before claiming a task or PR complete.

**Goal:** Deliver one real, read-only local Chairman briefing at `GET /brief` that lets Chris determine within ten seconds whether he must act, what Sol is handling, and which material exceptions threaten outcomes, while preserving the current dense Control Room at `/` as the Advanced inspector.

**Architecture:** Add one pure `mastermind.chairman_brief.v1` reducer over the already-cached `mastermind.chairman_control_room.v1` document and its existing cache metadata. Add one fixed authenticated JSON read at `GET /api/brief` and three local-only static assets. Perform no second gather, no new source read, no mutation, no model call, no lifecycle inference, and no remote-X1 change.

**Tech Stack:** Python 3.11+, pytest, the existing stdlib `ThreadingHTTPServer`, dependency-free browser JavaScript and CSS, Node syntax validation when available, and the repository's existing isolated Chromium/Playwright proof pattern for real browser acceptance.

**Spec:** `docs/superpowers/specs/2026-09-07-chairman-control-room-decision-first-experience-design.md` on Mastermind PR #521.

---

## Plan status and execution gate

Chairman product direction is approved. This plan is a records-only stacked carrier. It does not authorize implementation by itself.

DF1 implementation may start only after every gate below is positively verified against current protected source:

1. Mastermind PR #521 is independently reviewed and merged into protected `master`.
2. The exact protected commit containing the design is pinned, and the current compatible Sol Skillpack is loaded from that same commit.
3. Mastermind PR #424's incumbent owner has reconciled the older H1A route/static closure so it no longer authorizes a competing Workstream Workroom default or forbids the exact DF1 route/assets below.
4. No open PR or active worktree owns any DF1 implementation path.
5. The local P0A server and remote X1 contracts are re-read from the pinned source; remote X1 remains outside the change set.
6. A bounded source writer is assigned to one implementation branch and one PR. No second writer may start against the same paths.
7. The implementation plan itself has received Sol acceptance after independent review.

A missing gate returns:

```text
BLOCKED SOURCE_OR_OWNERSHIP_PRECONDITION
production_effect=NONE
```

Do not create an implementation branch, edit a path, or send a worker START merely because the Chairman approved the product direction.

---

## Global constraints

### Canonical-owner boundary

- Executive OS remains Job / Attempt / Worker / Event lifecycle and action-admission authority.
- Agent OS remains durable workstream, decision, discovery, and handoff authority.
- GitHub remains implementation, review, CI, merge, and evidence authority.
- Linear remains the selected portfolio projection and project-management surface.
- Slack and Agent Relay remain transport/hot-state projection, never lifecycle truth.
- The existing Control Room compositor and server cache remain the only source-composition path used by DF1.
- The brief is disposable presentation. Deleting every DF1 artifact changes no canonical company fact.

### Hard non-goals

DF1 must not add or modify:

- any database, table, queue, event store, scheduler, retry ledger, wake path, dispatch path, lifecycle, identity registry, current-state cache, or background gather loop;
- any POST endpoint or action control;
- any Linear, Slack, GitHub, Agent OS, Executive OS, provider, browser-profile, or credential write;
- any model invocation, model-authored ranking, summary authority, status, decision, or owner inference;
- the remote X1 projection, server, HTML, package, install service, or release closure;
- the current shared `control_room.js` or `control_room.css`;
- the current `index.html` inspector shell;
- the existing source-validity/B5 clocks, proof maps, permission logic, autonomy classifier, dispatch classifier, watcher logic, or effect reconciliation;
- Programs, Ask Sol, material-change checkpointing, default cutover, or Chairman mutation.

### Current-versus-historical law

- A missing source is never a zero.
- A failed refresh means the cached document is historical until a successful current composition supersedes it.
- A source-degraded document may remain partially useful by section.
- An attention item is not automatically a decision.
- Open tabs, bindings, running apps, provider sessions, and processes never prove cognition, ownership, or execution.
- `MERGED`, `CI GREEN`, `INSTALLED`, `DEPLOYED`, `PROVEN`, and `ACCEPTED` remain distinct.

### Security and privacy law

The default brief must not render or serialize:

- credentials, bearer values, cookies, tokens, browser profiles, provider session identifiers, or authentication material;
- hidden prompts, raw transcripts, private reasoning, or chain-of-thought;
- raw exception or traceback bodies;
- absolute host paths;
- arbitrary upstream mappings or unreviewed HTML;
- arbitrary URLs supplied by upstream records or browser input.

Every output object uses a closed allowlist. Source-derived strings pass through a bounded sanitizer. Unsafe source text is replaced with a fixed disclosure sentence, never partially redacted into misleading prose.

---

## Current source map

The implementation worker must re-read these paths at the admitted implementation base:

| Existing path | Role in DF1 | Mutation permission |
|---|---|---|
| `control_plane/chairman_control_room.py` | Existing pure cross-owner composition | read only |
| `control_plane/autonomy_control_room_projection.py` | Existing responsibility/freshness/actionability owner | read only |
| `control_plane/executive_inbox.py` | Existing Chairman/CEO/COO attention owner | read only |
| `scripts/chairman_control_room.py` | Existing local P0A cache and HTTP server | narrow additive edit |
| `app/static/chairman_control/index.html` | Existing Advanced inspector entry | read only |
| `app/static/chairman_control/control_room.js` | Existing local/X1 shared inspector client | read only |
| `app/static/chairman_control/control_room.css` | Existing local/X1 shared inspector styles | read only |
| `tests/test_chairman_control_room_server.py` | Existing server-test helpers and invariants | read only; import helpers from new tests |
| `tests/test_chairman_control_room_ui_x1.py` | Existing safe-DOM and browser-proof patterns | read only |
| `control_plane/chairman_control_room_remote.py` | Remote X1 projection/release owner | read only |
| `scripts/chairman_control_room_remote.py` | Remote X1 server | read only |
| `app/static/chairman_control/remote.html` | Remote X1 entry | read only |
| `docs/CHAIRMAN_CONTROL_ROOM.md` | Local operator documentation | narrow additive edit |

The current P0A state envelope already exposes the only inputs DF1 may consume:

```text
control_room
capabilities
live_builds_active
composed_at
refresh_in_flight
state_refresh_error
source_validity
```

DF1 consumes only `control_room`, `composed_at`, `refresh_in_flight`, `state_refresh_error`, and `source_validity`. It does not trigger capability census and does not inspect provider state.

---

## Exact DF1 implementation path ceiling

The implementation PR may touch exactly this ten-path set and no other path:

### Create

1. `control_plane/chairman_brief.py`
2. `app/static/chairman_control/brief.html`
3. `app/static/chairman_control/brief.js`
4. `app/static/chairman_control/brief.css`
5. `tests/test_chairman_brief.py`
6. `tests/test_chairman_control_room_brief_server.py`
7. `tests/test_chairman_control_room_brief_ui.py`
8. `docs/superpowers/plans/2026-09-07-chairman-control-room-df1-implementation-receipt.md`

### Modify

9. `scripts/chairman_control_room.py`
10. `docs/CHAIRMAN_CONTROL_ROOM.md`

A required eleventh path returns:

```text
DECISION_REQUEST PATH_BOUNDARY_REQUIRED
production_effect=NONE
```

The worker must not absorb the change into `index.html`, `control_room.js`, or `control_room.css` to avoid the path gate. Those assets are shared with the legacy inspector and remote X1; DF1 deliberately uses separate local-only assets.

Recommended future implementation branch, created only after the execution gate passes:

```text
sol/chairman-decision-cockpit-df1-20260907
```

Recommended PR state on return:

```text
DRAFT / HOLD-FOR-SOL / BUILT_NOT_PROVEN
```

---

## Fixed local route and asset closure

DF1 adds exactly these local GET paths:

```text
GET /brief
GET /api/brief
GET /static/brief.js
GET /static/brief.css
```

Rules:

- `GET /brief` serves `brief.html`, injects the existing per-process `__CCR_TOKEN__`, and receives the same CSP as `/`.
- `GET /api/brief` requires loopback, allowed Host, exact `X-CCR-Token`, matching Origin when present, and `Cache-Control: no-store`.
- Both `/brief` and `/api/brief` reject any non-empty query string.
- `GET /api/brief` reads the existing in-memory cache once; it performs no source gather, subprocess, filesystem discovery, provider census, or network operation.
- `GET /api/brief` may trigger the existing single-flight background refresh check, but returns the already-cached snapshot immediately.
- The canonical JSON response is fully encoded and measured before any byte is written.
- Maximum successful JSON body: exactly `262144` bytes.
- Overflow returns HTTP `503` with exactly:

```json
{
  "schema": "mastermind.chairman_brief_error.v1",
  "error": "CHAIRMAN_BRIEF_RESPONSE_TOO_LARGE"
}
```

- No partial brief bytes are written before the overflow refusal.
- No new POST route exists.
- `/` remains the current inspector during DF1 and is labeled Advanced from the new page only.
- Remote X1 route/static allowlists remain byte-unchanged.

---

## Frozen `mastermind.chairman_brief.v1` contract

### Pure entry point

```python
def compose_chairman_brief(
    *,
    control_room: Mapping[str, Any] | None,
    source_validity: Mapping[str, Any] | None,
    composed_at: str | None,
    refresh_in_flight: bool,
    state_refresh_error: str | None,
) -> dict[str, Any]:
    """Return a deterministic read-only Chairman briefing.

    No I/O, subprocess, environment read, clock read, randomness, mutable
    global state, provider inspection, source re-join, or caller mutation.
    """
```

### Closed top-level keys

```python
OUTPUT_KEYS = frozenset({
    "schema",
    "generated_at",
    "source",
    "read_state",
    "headline",
    "decisions",
    "attention",
    "changes",
    "sol_handling",
    "exceptions",
    "feature_gates",
})
```

### Closed state vocabularies

```python
READ_STATES = frozenset({"CURRENT", "PARTIAL", "HISTORICAL", "UNAVAILABLE"})
SECTION_STATES = frozenset({"AVAILABLE", "EMPTY", "PARTIAL", "HISTORICAL", "UNAVAILABLE"})
HEADLINE_KINDS = frozenset({
    "CLEAR",
    "DECISIONS_REQUIRED",
    "ATTENTION_REQUIRED",
    "PARTIAL",
    "UNAVAILABLE",
})
```

### Exact output shape

```json
{
  "schema": "mastermind.chairman_brief.v1",
  "generated_at": "2026-09-07T00:00:00Z",
  "source": {
    "control_room_schema": "mastermind.chairman_control_room.v1",
    "control_room_generated_at": "2026-09-07T00:00:00Z",
    "control_room_digest": "sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
    "composed_at": "2026-09-07T00:00:01Z",
    "source_validity_schema": "mastermind.control_room_source_validity.v1"
  },
  "read_state": {
    "state": "CURRENT",
    "reason_codes": [],
    "usable_sections": ["attention", "sol_handling", "exceptions"]
  },
  "headline": {
    "kind": "CLEAR",
    "complete_decision_count": 0,
    "chairman_attention_count": 0,
    "sol_handled_count": 3,
    "exception_count": 0
  },
  "decisions": {
    "state": "UNAVAILABLE",
    "reason_codes": ["DECISION_PACKET_SOURCE_NOT_PROJECTED"],
    "items": [],
    "overflow_count": 0
  },
  "attention": {
    "state": "EMPTY",
    "reason_codes": [],
    "items": [],
    "overflow_count": 0
  },
  "changes": {
    "state": "UNAVAILABLE",
    "reason_codes": ["MATERIAL_CHANGE_CHECKPOINT_NOT_BUILT_IN_DF1"],
    "items": []
  },
  "sol_handling": {
    "state": "AVAILABLE",
    "reason_codes": [],
    "items": [],
    "overflow_count": 0
  },
  "exceptions": {
    "state": "EMPTY",
    "reason_codes": [],
    "items": [],
    "overflow_count": 0
  },
  "feature_gates": {
    "advanced": "AVAILABLE",
    "programs": "UNAVAILABLE",
    "ask_sol": "UNAVAILABLE",
    "actions": "READ_ONLY"
  }
}
```

`changes` remains an explicitly unavailable future section. DF1 does not create the display checkpoint specified for DF3. The UI hides unavailable future sections rather than showing dead equal-weight navigation.

### Headline precedence

Use this exact precedence:

1. Invalid/missing Control Room schema or no usable Chairman/ownership source → `UNAVAILABLE`.
2. `state_refresh_error` on a cached document → `PARTIAL` headline with `read_state=HISTORICAL`.
3. Any critical source unavailable while another section remains usable → `PARTIAL`.
4. One or more complete current decision packets → `DECISIONS_REQUIRED`.
5. One or more current Chairman attention items → `ATTENTION_REQUIRED`.
6. Otherwise, only after a positively current Chairman-attention read → `CLEAR`.

DF1 has no complete decision-packet source. Therefore its decision count is zero and its decision section is `UNAVAILABLE`, not `EMPTY`. A future accepted source must be a separate architecture/contract change; DF1 does not add a speculative decision input.

### Critical source interpretation

Use closed source-presence checks, not substring interpretation of arbitrary error text:

```text
Agent OS usable:
  control_room.sources.agent_os_state_schema == agent_os_state.v1

Executive Inbox usable:
  control_room.sources.executive_inbox_schema == mastermind.executive_inbox.v2

GitHub evidence usable:
  control_room.sources.active_builds_schema == project_active_builds.v1

Runtime usable:
  control_room.sources.runtime_db_present is true
```

The reducer may examine only the prefix before the first colon in `control_room.degraded[]` to map a source to a fixed reason code. The remainder is never copied into the brief.

### Chairman attention item

```text
attention_id
kind
summary
work_ref
source_owner
source_time
observed_at
missing_decision_fields[]
evidence_refs[]
advanced_ref
```

Rules:

- `attention_id` must already exist and be a nonblank string.
- Join to `work_ref` only through exactly one `work[].attention_ids[]` claim. Zero claims yields `null`; multiple claims yield a `SOURCE_CONFLICT` exception.
- `summary` comes only from `summary` or `reason`, through the bounded sanitizer.
- `source_time` remains `null` unless the source item itself carries an accepted source timestamp. `control_room.generated_at` is `observed_at`, never relabeled as source time.
- `missing_decision_fields` is a fixed disclosure list for the current contract:

```text
authority_required
closed_options
consequence_of_acting
consequence_of_waiting
reversibility
recommendation_provenance
```

- No approve/hold control appears.
- `advanced_ref` is the fixed local string `/#today`, never an upstream URL.

### Sol-handling item

```text
item_id
work_ref
outcome
why_it_matters
current_focus
next_checkpoint
accountable_owner
chairman_action_required
evidence_refs[]
source_time
observed_at
freshness_state
advanced_ref
```

Admission requires all of:

```text
autonomy responsibility accountable_seat == "ceo"
autonomy responsibility query_status == "ok"
autonomy responsibility freshness == "current"
autonomy responsibility placement_state.value != "EFFECT_UNKNOWN"
autonomy responsibility dispatch.state not in {"RETURNED", "EFFECT_UNKNOWN"}
no Chairman attention id claims the joined work card
no work-card disagreement
Agent OS next_action is a safe nonblank sentence
```

Join autonomy responsibility to work only by exact equality:

```text
responsibility.responsibility_ref == work.work_ref
```

Fields:

- `outcome`: safe `responsibility.title`, falling back to safe `work.agent_os.title`.
- `why_it_matters`: safe `work.agent_os.reason`, or `null` with a typed reason in evidence.
- `current_focus`: safe `work.agent_os.next_action`.
- `next_checkpoint`: `null` in DF1 unless an exact accepted proof/checkpoint field already exists in the composed document. Do not turn the next action into proof.
- `accountable_owner`: literal `SOL`, admitted only from the exact CEO accountability source above.
- `chairman_action_required`: always `false` for admitted rows.
- Sort by exact `responsibility_ref`; show at most six; disclose overflow.

A row failing currentness or accountability is not silently dropped into a reassuring state. It either becomes a typed exception where material or remains absent with the section marked partial.

### Exception item

```text
exception_id
kind
work_ref
impact
repair_owner
chairman_action_required
source_time
observed_at
freshness_state
evidence_refs[]
diagnostic_ref
```

Closed kinds:

```python
EXCEPTION_KINDS = frozenset({
    "WORK_WAITING",
    "WORK_BLOCKED",
    "PROOF_MISSING",
    "SOURCE_CONFLICT",
    "SOURCE_UNAVAILABLE",
    "EFFECT_UNKNOWN",
    "PRODUCTION_REGRESSION",
    "OWNER_NOT_ESTABLISHED",
    "CAPACITY_BLOCKED",
})
```

Deterministic admission only:

| Source fact | Exception kind | Fixed impact template |
|---|---|---|
| `state_refresh_error` | `SOURCE_UNAVAILABLE` | `The latest refresh failed. Cached evidence is historical until a successful composition replaces it.` |
| missing/invalid Executive runtime | `SOURCE_UNAVAILABLE` | `Current execution claims are withheld. Organizational and implementation evidence may remain usable.` |
| missing/invalid Executive Inbox | `SOURCE_UNAVAILABLE` | `Current Chairman attention cannot be established from Executive evidence.` |
| missing/invalid Agent OS state | `SOURCE_UNAVAILABLE` | `Current outcomes, owners, and next actions cannot be established from Agent OS.` |
| missing/invalid active-builds source | `SOURCE_UNAVAILABLE` | `Current implementation and proof changes cannot be established from GitHub evidence.` |
| `work[].disagreements` nonempty | `SOURCE_CONFLICT` | `Canonical and projected evidence disagree. No winner is selected in this briefing.` |
| exact Agent OS blocked state or nonempty unmet dependencies | `WORK_BLOCKED` | `This outcome cannot advance through its recorded next step.` |
| exact failed Executive job | `WORK_BLOCKED` | `A recorded Executive job failed. The next safe action requires inspection.` |
| autonomy dispatch `RETURNED` with accountable seat `ceo` | `WORK_WAITING` | `A worker return is waiting for Sol adjudication.` |
| exact placement/dispatch `EFFECT_UNKNOWN` | `EFFECT_UNKNOWN` | `A prior operation may have taken effect. No retry or carrier change is permitted until reconciled.` |
| exact placement `WAITING_CAPACITY` | `CAPACITY_BLOCKED` | `The operation is waiting for an eligible capacity assignment.` |
| autonomy unmapped responsibility | `OWNER_NOT_ESTABLISHED` | `An accountable operator cannot be established from the current owner mapping.` |
| exact source-owned proof-missing kind/code | `PROOF_MISSING` | `Implementation evidence exists, but the required accepted proof is not present.` |
| exact source-owned production-regression kind/code | `PRODUCTION_REGRESSION` | `A previously usable production journey is reported as regressed.` |

Never infer `PROOF_MISSING` from an open PR alone. Never infer `PRODUCTION_REGRESSION` from a failed test alone. Those classes require an exact source-owned kind or reason code.

`repair_owner` is a closed system owner, not a guessed human:

```text
EXECUTIVE_OS
AGENT_OS
GITHUB_EVIDENCE
SOL
CAPACITY_OWNER
UNKNOWN
```

`chairman_action_required` is true only when an exact current Chairman attention item joins the same identity. An exception alone never escalates itself.

### Safe evidence reference

```text
owner
ref
field
source_time
observed_at
```

Allowed owners:

```text
executive_inbox
executive_os
agent_os
github
autonomy_projection
control_room_cache
source_validity
```

Allowed reference forms:

```text
attention:<safe-id>
job:<safe-id>
workstream:WS:<safe-key>
github:<owner>/<repo>#<number>
source:<repository-relative-path>
cache:<sha256>
```

No evidence URL is copied from upstream in DF1. The fixed `advanced_ref` lets the operator inspect the existing evidence UI. A later deep-link capability requires its own exact allowlist.

### Bounded sanitizer

Implement one pure sanitizer with these semantics:

```python
def safe_sentence(value: Any, *, limit: int = 360) -> str | None:
    if not isinstance(value, str):
        return None
    text = " ".join(value.split())
    if not text or len(text) > limit:
        return None
    if _looks_sensitive(text):
        return None
    return text
```

`_looks_sensitive` rejects, at minimum:

- `Bearer `, `token=`, `api_key`, `cookie`, `authorization`, `password`, `secret` case-insensitively;
- absolute path prefixes `/Users/`, `/home/`, `/private/`, `/var/`, `/opt/`, `/tmp/`, and Windows drive paths;
- `Traceback (most recent call last)`;
- `chain of thought`, `private reasoning`, `hidden prompt`, and transcript markers;
- strings containing control characters other than ordinary whitespace.

If the Chairman-facing summary is unsafe, emit the fixed sentence:

```text
Source-owned detail is withheld from the default briefing. Inspect Advanced evidence.
```

Do not echo which secret pattern matched.

---

# Task 0: Admit one clean implementation carrier

**Files:** none.

### Step 1: Re-pin protected source and procedure

Run:

```bash
git fetch origin master
git rev-parse origin/master
git show origin/master:docs/sol_skills/INDEX.md | sed -n '1,80p'
```

Expected:

- the exact protected SHA is recorded in the implementation receipt;
- Skillpack schema/version/bootstrap compatibility is proven at that same SHA;
- the protected design file exists.

### Step 2: Prove design protection and review

Run:

```bash
gh pr view 521 --repo mastermindx-market-intelligence/Mastermind \
  --json state,isDraft,mergedAt,mergeCommit,reviewDecision,headRefOid
```

Required before START:

```text
state=MERGED
isDraft=false
mergedAt is non-null
reviewDecision does not contain CHANGES_REQUESTED
```

Chairman approval in chat is product intent. It is not a substitute for source protection and independent review.

### Step 3: Reconcile PR #424 without taking it over

Run:

```bash
gh pr view 424 --repo mastermindx-market-intelligence/Mastermind \
  --json state,isDraft,mergedAt,headRefOid,reviewDecision,files,comments
```

Required receipt before START:

- the incumbent/current owner explicitly retains the useful H0 archaeology;
- the older H1A default Workstream Workroom is superseded or held;
- `/api/hub/workstream/chairman-control-room`, `hub_workroom.js`, and `hub_workroom.css` are not the only lawful future additions;
- the exact DF1 closure in this plan is accepted;
- no competing H1A implementation exists or may merge behind DF1.

Do not edit any of PR #424's four owned files from the DF1 carrier.

### Step 4: Census open PRs and worktrees

Check all ten paths, including rename history, across open PRs and local worktrees. Example:

```bash
python3 - <<'PY'
from pathlib import Path
paths = {
    "control_plane/chairman_brief.py",
    "app/static/chairman_control/brief.html",
    "app/static/chairman_control/brief.js",
    "app/static/chairman_control/brief.css",
    "tests/test_chairman_brief.py",
    "tests/test_chairman_control_room_brief_server.py",
    "tests/test_chairman_control_room_brief_ui.py",
    "docs/superpowers/plans/2026-09-07-chairman-control-room-df1-implementation-receipt.md",
    "scripts/chairman_control_room.py",
    "docs/CHAIRMAN_CONTROL_ROOM.md",
}
assert len(paths) == 10
for path in sorted(paths):
    print(path)
PY

git worktree list --porcelain
gh pr list --repo mastermindx-market-intelligence/Mastermind --state open --limit 100 \
  --json number,headRefName,headRefOid,title,files
```

Stop on any unresolved path owner. Do not create a second writer.

### Step 5: Create the isolated branch/worktree only after gates pass

```bash
git worktree add \
  ../Mastermind-chairman-decision-cockpit-df1-20260907 \
  -b sol/chairman-decision-cockpit-df1-20260907 \
  origin/master
cd ../Mastermind-chairman-decision-cockpit-df1-20260907
git status --short --branch
```

Expected: clean worktree on the exact new branch and current protected base.

### Step 6: Record the pre-start effect census

Record branch, HEAD, tree, upstream, worktree path, open file handles if inspected, and the exact ten-path collision result. This is evidence, not lifecycle state.

---

# Task 1: Build the pure brief skeleton and read-state ruler

**Files:**
- Create: `tests/test_chairman_brief.py`
- Create: `control_plane/chairman_brief.py`

### Step 1: Write the failing closed-contract tests

Start with tests equivalent to:

```python
from __future__ import annotations

import copy
import json

from control_plane import chairman_brief as brief


def _base_doc() -> dict:
    return {
        "schema": "mastermind.chairman_control_room.v1",
        "generated_at": "2026-09-07T00:00:00Z",
        "sources": {
            "executive_inbox_schema": "mastermind.executive_inbox.v2",
            "agent_os_state_schema": "agent_os_state.v1",
            "active_builds_schema": "project_active_builds.v1",
            "runtime_db_present": True,
        },
        "degraded": [],
        "attention": {"chairman": [], "ceo": [], "coo": []},
        "work": [],
        "unjoined_open_prs": [],
        "unbound_surfaces": [],
        "binding_conflicts": [],
        "placement_selection": None,
        "autonomy": {
            "schema": "mastermind.autonomy_control_room.v1",
            "generated_at": "2026-09-07T00:00:00Z",
            "responsibilities": [],
            "unmapped_responsibilities": [],
        },
    }


def _compose(doc=None, **overrides):
    args = {
        "control_room": _base_doc() if doc is None else doc,
        "source_validity": {
            "schema": "mastermind.control_room_source_validity.v1",
            "cards": [],
        },
        "composed_at": "2026-09-07T00:00:01Z",
        "refresh_in_flight": False,
        "state_refresh_error": None,
    }
    args.update(overrides)
    return brief.compose_chairman_brief(**args)


def test_closed_contract_and_determinism():
    one = _compose()
    two = _compose()
    assert set(one) == brief.OUTPUT_KEYS
    assert one == two
    assert json.dumps(one, sort_keys=True, allow_nan=False) == json.dumps(
        two, sort_keys=True, allow_nan=False
    )


def test_missing_control_room_is_unavailable_not_clear():
    out = _compose(doc=None)
    assert out["read_state"]["state"] == "UNAVAILABLE"
    assert out["headline"]["kind"] == "UNAVAILABLE"


def test_failed_refresh_makes_cached_document_historical():
    out = _compose(state_refresh_error="arbitrary raw exception")
    assert out["read_state"]["state"] == "HISTORICAL"
    assert out["headline"]["kind"] == "PARTIAL"
    assert "arbitrary raw exception" not in json.dumps(out)
```

The helper must distinguish a deliberately passed `None` from its default document; use an explicit sentinel if needed so `doc=None` truly exercises absence.

### Step 2: Run RED

```bash
python -m pytest tests/test_chairman_brief.py -q
```

Expected: import/contract failures because the module does not exist.

### Step 3: Implement constants, canonical JSON, digest, source availability, and read-state

Implementation requirements:

```python
SCHEMA = "mastermind.chairman_brief.v1"
CONTROL_ROOM_SCHEMA = "mastermind.chairman_control_room.v1"
SOURCE_VALIDITY_SCHEMA = "mastermind.control_room_source_validity.v1"
MAX_ATTENTION_ITEMS = 3
MAX_SOL_HANDLING_ITEMS = 6
MAX_EXCEPTION_ITEMS = 6
```

Canonical digest:

```python
def _digest(value: Mapping[str, Any]) -> str | None:
    try:
        raw = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError):
        return None
    return "sha256:" + hashlib.sha256(raw).hexdigest()
```

Do not mutate or normalize the upstream document before hashing it.

### Step 4: Add hostile shape tests

Cover:

- wrong schema;
- non-mapping source;
- non-list attention/work/degraded values;
- NaN or unserializable input;
- missing `attention.chairman`;
- invalid source-validity schema;
- `refresh_in_flight` non-boolean;
- `state_refresh_error` non-string;
- input ordering changes that must not change semantic output where ordering is source-insensitive.

Every case returns a complete closed document or a typed unavailable state. The pure reducer never raises on untrusted source shape.

### Step 5: Run GREEN and commit

```bash
python -m pytest tests/test_chairman_brief.py -q
git add control_plane/chairman_brief.py tests/test_chairman_brief.py
git commit -m "feat(control-room): add pure Chairman brief contract"
```

---

# Task 2: Enforce the attention-versus-decision boundary

**Files:**
- Modify: `tests/test_chairman_brief.py`
- Modify: `control_plane/chairman_brief.py`

### Step 1: Write failing tests for exact Chairman attention

Add a source row:

```python
def _chairman_attention(attention_id="eia-chairman-1") -> dict:
    return {
        "attention_id": attention_id,
        "target": "chairman",
        "kind": "job_failed",
        "source": "runtime",
        "job_id": "JOB-1",
        "workstream": "WS:EXAMPLE",
        "status": "FAILED",
        "reason": "A bounded operation failed and needs a ruling.",
        "evidence": [
            {"ref": "job:JOB-1", "field": "status", "value": "FAILED"},
        ],
        "existing_next_actions": [],
    }
```

Required assertions:

```python
def test_chairman_attention_is_not_promoted_to_a_decision():
    doc = _base_doc()
    doc["attention"]["chairman"] = [_chairman_attention()]
    doc["work"] = [{
        "work_ref": "WS:EXAMPLE",
        "agent_os": None,
        "executive": {"jobs": [{"job_id": "JOB-1", "status": "failed"}]},
        "github": {"prs": []},
        "attention_ids": ["eia-chairman-1"],
        "bindings": [],
        "disagreements": [],
    }]
    out = _compose(doc=doc)
    assert out["headline"]["kind"] == "ATTENTION_REQUIRED"
    assert out["decisions"]["state"] == "UNAVAILABLE"
    assert out["decisions"]["items"] == []
    assert out["attention"]["items"][0]["missing_decision_fields"] == [
        "authority_required",
        "closed_options",
        "consequence_of_acting",
        "consequence_of_waiting",
        "reversibility",
        "recommendation_provenance",
    ]
```

### Step 2: Test exact joins and conflicts

Add tests proving:

- one exact `attention_id` claim joins a work ref;
- zero claims yields `work_ref=None`, not fuzzy title matching;
- two work cards claiming the same `attention_id` add a `SOURCE_CONFLICT` exception and do not pick a winner;
- duplicate attention identities do not silently collapse; they force partial/conflict state;
- a `target != chairman` row never enters Chairman attention;
- an item without a valid stable `attention_id` is not shown as current attention and creates a typed source-shape exception;
- unsafe reason text is replaced by the fixed withheld sentence;
- evidence is reduced to closed safe references rather than recursive pass-through.

### Step 3: Run RED

```bash
python -m pytest tests/test_chairman_brief.py -q -k 'attention or decision'
```

### Step 4: Implement the exact attention projection

Implementation pattern:

```python
def _attention_claims(work_rows: Sequence[Mapping[str, Any]]) -> dict[str, list[str]]:
    claims: dict[str, list[str]] = {}
    for work in work_rows:
        work_ref = _safe_work_ref(work.get("work_ref"))
        if work_ref is None:
            continue
        for attention_id in _safe_string_list(work.get("attention_ids")):
            claims.setdefault(attention_id, []).append(work_ref)
    return {key: sorted(set(values)) for key, values in claims.items()}
```

Sort current items by source order, then stable `attention_id`; show three and report overflow. Do not add an urgency or severity model.

### Step 5: Run GREEN and commit

```bash
python -m pytest tests/test_chairman_brief.py -q
git add control_plane/chairman_brief.py tests/test_chairman_brief.py
git commit -m "feat(control-room): project truthful Chairman attention"
```

---

# Task 3: Add exact Sol accountability and impact-oriented exceptions

**Files:**
- Modify: `tests/test_chairman_brief.py`
- Modify: `control_plane/chairman_brief.py`

### Step 1: Write failing Sol-handling tests

Create exact joined work/autonomy fixtures and assert:

```python
def test_only_current_exact_ceo_responsibilities_enter_sol_handling():
    doc = _base_doc()
    doc["work"] = [{
        "work_ref": "WS:EXAMPLE",
        "agent_os": {
            "title": "Example outcome",
            "status": "active",
            "program": "example",
            "next_action": "Prove one real user-visible result.",
            "state": "in_progress",
            "reason": "The user journey is not yet production-proven.",
            "source": "agentos/workstreams/WS-EXAMPLE.md",
            "unmet_dependencies": [],
        },
        "executive": {"jobs": []},
        "github": {"prs": []},
        "attention_ids": [],
        "bindings": [],
        "disagreements": [],
    }]
    doc["autonomy"]["responsibilities"] = [{
        "responsibility_ref": "WS:EXAMPLE",
        "title": "Example outcome",
        "accountable_seat": "ceo",
        "state": "in_progress",
        "query_status": "ok",
        "freshness": "current",
        "is_actionable": True,
        "placement_state": {"value": "not_observable"},
        "dispatch": {"state": "UNKNOWN"},
        "source_receipts": [],
    }]
    out = _compose(doc=doc)
    item = out["sol_handling"]["items"][0]
    assert item["work_ref"] == "WS:EXAMPLE"
    assert item["accountable_owner"] == "SOL"
    assert item["chairman_action_required"] is False
    assert item["current_focus"] == "Prove one real user-visible result."
    assert item["next_checkpoint"] is None
```

Add negative tests for:

- accountable seat `coo`, `worker`, `chairman`, or unknown;
- stale/unknown freshness;
- refused/degraded query status;
- exact Chairman attention on the work card;
- a disagreement;
- blocked/unmet dependencies;
- returned-to-Sol dispatch;
- effect-unknown placement/dispatch;
- missing safe next action;
- duplicate responsibility ref;
- similar but unequal work refs.

### Step 2: Write failing exception tests

Test every deterministic row in the exception table. Include the live screenshot class:

```python
def test_raw_runtime_path_becomes_fixed_impact_copy():
    doc = _base_doc()
    doc["sources"]["runtime_db_present"] = False
    doc["degraded"] = [
        "executive_runtime: database missing at /Users/private/runtime.sqlite3"
    ]
    out = _compose(doc=doc)
    encoded = json.dumps(out, sort_keys=True)
    assert "/Users/private/runtime.sqlite3" not in encoded
    item = next(row for row in out["exceptions"]["items"]
                if row["kind"] == "SOURCE_UNAVAILABLE")
    assert item["impact"] == (
        "Current execution claims are withheld. Organizational and "
        "implementation evidence may remain usable."
    )
```

Also prove:

- one exception identity is deterministic;
- exact work disagreement is not resolved;
- failed job and authored block are distinct source evidence but may dedupe to one work-level `WORK_BLOCKED` item by exact semantic fingerprint;
- dispatch `RETURNED` becomes `WORK_WAITING` only when exact;
- `EFFECT_UNKNOWN` never appears from an unrelated text string containing those words;
- `WAITING_CAPACITY` requires the exact accepted token;
- no open PR alone creates `PROOF_MISSING`;
- no failed CI text alone creates `PRODUCTION_REGRESSION`;
- owner-unmapped rows become `OWNER_NOT_ESTABLISHED`;
- overflow count is visible after six items;
- exception sort is the frozen kind order, then `work_ref`, then stable id—not an LLM or numeric score.

### Step 3: Run RED

```bash
python -m pytest tests/test_chairman_brief.py -q -k 'sol_handling or exception or blocked or effect_unknown'
```

### Step 4: Implement exact joins, fixed templates, evidence refs, and sanitizer

Do not parse arbitrary prose to infer lifecycle or severity. Prefix parsing is allowed only for source family:

```python
source_family = entry.split(":", 1)[0] if isinstance(entry, str) else None
```

The remainder is discarded before any output object is assembled.

Use stable IDs:

```python
def _stable_id(prefix: str, *parts: str | None) -> str:
    material = "|".join([SCHEMA, prefix, *(part or "" for part in parts)])
    return prefix + "-" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]
```

### Step 5: Add an AST anti-authority test

Assert `control_plane/chairman_brief.py` does not import or call:

```text
open
Path.read_*
subprocess
requests
urllib
socket
os.environ
time.time
datetime.now
random
Executive Runtime mutation APIs
surface binding writers
```

Permit `hashlib`, `json`, `re`, mappings/sequences, and pure helpers.

### Step 6: Run GREEN and commit

```bash
python -m pytest tests/test_chairman_brief.py -q
git add control_plane/chairman_brief.py tests/test_chairman_brief.py
git commit -m "feat(control-room): compress Sol coverage and exceptions"
```

---

# Task 4: Add the fixed local read routes without a second gather

**Files:**
- Create: `tests/test_chairman_control_room_brief_server.py`
- Modify: `scripts/chairman_control_room.py`

### Step 1: Write failing server tests using existing helpers

Reuse `_make_config`, `_running_server`, `_get`, and `_auth_headers` from `tests/test_chairman_control_room_server.py`; do not clone a second server harness.

Required initial tests:

```python
from tests.test_chairman_control_room_server import (
    _auth_headers,
    _get,
    _make_config,
    _running_server,
)


def test_brief_html_bootstraps_nonce_and_csp(tmp_path):
    config = _make_config(tmp_path)
    with _running_server(config) as (_httpd, port):
        status, headers, body = _get(port, "/brief")
    assert status == 200
    assert headers["content-security-policy"]
    assert config.token.encode() in body


def test_brief_api_requires_existing_nonce_and_is_no_store(tmp_path):
    config = _make_config(tmp_path)
    with _running_server(config) as (_httpd, port):
        denied, _, _ = _get(port, "/api/brief")
        status, headers, body = _get(
            port, "/api/brief", headers=_auth_headers(config)
        )
    assert denied == 403
    assert status == 200
    assert headers["cache-control"] == "no-store"
    assert json.loads(body)["schema"] == "mastermind.chairman_brief.v1"
```

### Step 2: Add route-closure and zero-request-gather tests

Prove:

- `/brief?x=1` and `/api/brief?x=1` are rejected;
- unknown static asset names return 404;
- `brief.html`, `brief.js`, and `brief.css` are the only new assets;
- `/api/brief` does not call `_compose_state_doc` synchronously;
- `/api/brief` does not call capability census;
- the response uses one `_cached_state_snapshot` generation;
- background refresh remains single-flight and non-blocking;
- `/` and `/api/state` behavior remains unchanged;
- every current POST route behaves unchanged;
- `POST /api/brief` returns 404;
- external client, bad Host, bad token, and bad Origin fail before reducer execution.

Use injected counters rather than elapsed-time guesses.

### Step 3: Add response-cap RED

Monkeypatch the pure reducer to return a valid but oversized object. Assert:

```python
assert status == 503
assert json.loads(body) == {
    "schema": "mastermind.chairman_brief_error.v1",
    "error": "CHAIRMAN_BRIEF_RESPONSE_TOO_LARGE",
}
assert b"mastermind.chairman_brief.v1" not in body
```

Also test exactly `262144` bytes succeeds and `262145` refuses, using canonical encoder padding that does not rely on dictionary formatting ambiguity.

### Step 4: Run RED

```bash
python -m pytest tests/test_chairman_control_room_brief_server.py -q
```

### Step 5: Implement the minimal server change

Import the reducer after the existing path bootstrap:

```python
from control_plane import chairman_brief  # noqa: E402
```

Add constants:

```python
_BRIEF_MAX_BYTES = 262_144
_BRIEF_ERROR = {
    "schema": "mastermind.chairman_brief_error.v1",
    "error": "CHAIRMAN_BRIEF_RESPONSE_TOO_LARGE",
}
```

Extend the static maps only:

```python
"brief.html": (static_dir / "brief.html", "text/html; charset=utf-8"),
"brief.js": (static_dir / "brief.js", "application/javascript; charset=utf-8"),
"brief.css": (static_dir / "brief.css", "text/css; charset=utf-8"),
```

```python
"/brief": "brief.html",
"/static/brief.js": "brief.js",
"/static/brief.css": "brief.css",
```

Use one tokenized HTML helper for `index.html` and `brief.html`, preserving existing `/` bytes except for refactoring-equivalent nonce injection.

Add the authenticated read:

```python
def _handle_brief(self) -> None:
    config: ServerConfig = self.server.config  # type: ignore[attr-defined]
    _maybe_start_background_refresh(config)
    snapshot = _cached_state_snapshot(config)
    payload = chairman_brief.compose_chairman_brief(
        control_room=snapshot["doc"],
        source_validity=snapshot["source_validity"],
        composed_at=snapshot["composed_at"],
        refresh_in_flight=snapshot["refresh_in_flight"],
        state_refresh_error=snapshot["state_refresh_error"],
    )
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    if len(encoded) > _BRIEF_MAX_BYTES:
        return self._send_json(503, _BRIEF_ERROR, no_store=True)
    self._write(
        200,
        encoded,
        content_type="application/json; charset=utf-8",
        no_store=True,
    )
```

Ensure `_send_json` canonicalization does not cause the boundary test to measure different bytes than the actual success response.

### Step 6: Run GREEN plus legacy server regression

```bash
python -m pytest \
  tests/test_chairman_control_room_brief_server.py \
  tests/test_chairman_control_room_server.py \
  -q

git add scripts/chairman_control_room.py tests/test_chairman_control_room_brief_server.py
git commit -m "feat(control-room): expose fixed read-only Chairman brief"
```

---

# Task 5: Build the sparse Today shell

**Files:**
- Create: `app/static/chairman_control/brief.html`
- Create: `app/static/chairman_control/brief.css`
- Create: `tests/test_chairman_control_room_brief_ui.py`

### Step 1: Write failing static-shell tests

Parse `brief.html` with `HTMLParser`. Require unique IDs and exactly one external script.

Required DOM ids:

```text
brief-main
brief-source-state
brief-headline
brief-subheadline
brief-attention
brief-attention-list
brief-sol-handling
brief-sol-list
brief-exceptions
brief-exception-list
brief-empty
brief-advanced
brief-evidence-drawer
brief-evidence-title
brief-evidence-body
brief-evidence-close
brief-scrim
```

Required assertions:

```python
assert probe.script_srcs == ["/static/brief.js"]
assert probe.inline_scripts == 0
assert probe.style_attrs == []
assert probe.ids == list(dict.fromkeys(probe.ids))
assert "/static/control_room.js" not in html
assert "ccr-sidebar" not in html
assert "ccr-surface-dock" not in html
```

### Step 2: Write the exact HTML shell

The shell contains:

- one skip link to `#brief-main`;
- compact Mastermind X brand;
- `Today` as current page;
- no enabled Programs or Ask Sol control in DF1;
- one quiet, fixed `Advanced` link to `/`;
- one source-state element;
- one hero headline and subheadline;
- sections for Chairman attention, Sol handling, and exceptions;
- one calm empty-state region;
- one evidence drawer and scrim;
- no sidebar, permanent rail, global search, project counts, or provider surface dock.

The loading copy must avoid a present-tense company claim:

```text
Establishing the current briefing…
```

### Step 3: Write the CSS hierarchy

Use CSS custom properties local to `brief.css`; do not import the old stylesheet.

Core rules:

```css
:root {
  color-scheme: dark;
  --brief-bg: #090b0f;
  --brief-panel: #11151b;
  --brief-panel-soft: #0d1117;
  --brief-line: #28303a;
  --brief-text: #f2f0ea;
  --brief-muted: #9ca4af;
  --brief-brass: #c8a45f;
  --brief-danger: #d36b58;
  --brief-success: #6f9f7d;
  --brief-max: 1040px;
}

* { box-sizing: border-box; }
html { background: var(--brief-bg); }
body { margin: 0; min-width: 0; color: var(--brief-text); background: var(--brief-bg); }
img, svg { max-width: 100%; }
button, a { font: inherit; }
:focus-visible { outline: 2px solid var(--brief-brass); outline-offset: 3px; }
```

Layout requirements:

- main content max width 1040px;
- no permanent side columns;
- first headline visible at 390×844 without horizontal scroll;
- one expanded attention card; later items use compact rows;
- internal ids/tokens use wrap/overflow behavior rather than truncating the default copy;
- evidence drawer becomes full-screen at narrow width;
- `prefers-reduced-motion: reduce` disables transitions and smooth scrolling;
- high-contrast text and status labels; no color-only meaning.

### Step 4: Run static RED/GREEN loop

```bash
python -m pytest tests/test_chairman_control_room_brief_ui.py -q -k 'shell or css'
```

Commit after green:

```bash
git add \
  app/static/chairman_control/brief.html \
  app/static/chairman_control/brief.css \
  tests/test_chairman_control_room_brief_ui.py
git commit -m "feat(control-room): add sparse Chairman Today shell"
```

---

# Task 6: Render the brief safely and make evidence inspectable

**Files:**
- Create: `app/static/chairman_control/brief.js`
- Modify: `tests/test_chairman_control_room_brief_ui.py`

### Step 1: Write failing JavaScript contract tests

Static assertions:

```text
/api/brief is present
X-CCR-Token is present
fetch uses GET and same-origin credentials
innerHTML is absent
document.write is absent
eval is absent
new Function is absent
/api/open is absent
/api/bind is absent
/api/unbind is absent
/api/refresh-builds is absent
POST is absent
```

Node syntax check when available:

```bash
node --check app/static/chairman_control/brief.js
```

Keep a conservative pure-Python bracket-balance test so node-less CI cannot ship a grossly malformed file.

### Step 2: Implement safe DOM primitives

Start the file with strict mode and one IIFE. Use only safe DOM construction:

```javascript
"use strict";
(function () {
  var meta = document.querySelector('meta[name="ccr-token"]');
  var TOKEN = meta ? meta.getAttribute("content") : "";
  var lastDrawerOpener = null;

  function el(tag, options) {
    var node = document.createElement(tag);
    options = options || {};
    if (options.text !== undefined) node.textContent = String(options.text);
    if (options.className) node.className = options.className;
    return node;
  }

  function clear(node) {
    while (node && node.firstChild) node.removeChild(node.firstChild);
  }
```

No source string is interpreted as HTML.

### Step 3: Implement fixed headline copy

Map only the closed `headline.kind` values:

```javascript
var HEADLINE = {
  CLEAR: "You are clear.",
  DECISIONS_REQUIRED: "A decision needs you.",
  ATTENTION_REQUIRED: "An item needs your attention.",
  PARTIAL: "This is a partial briefing.",
  UNAVAILABLE: "A current briefing cannot be established."
};
```

Pluralize from exact counts. Never display `healthy` as an inferred state.

Subheadline templates:

- `CLEAR`: `No Chairman intervention is currently admitted. Sol coverage and exceptions are shown below.`
- `ATTENTION_REQUIRED`: `The current source does not contain a complete decision packet, so no approval control is shown.`
- `PARTIAL`: `Some present-tense claims are withheld. Available sections remain evidence-backed.`
- `UNAVAILABLE`: `No present-tense company claim is being made. Advanced diagnostics remain available.`

### Step 4: Render one expanded plus two compact attention items

The first item displays summary, work ref when present, source owner, and a fixed disclosure that decision fields are missing. Later items display one-line summaries with `Review evidence`.

No control is labeled Approve, Hold, Continue, Stop, Retry, Dispatch, or Merge.

### Step 5: Render Sol handling and exceptions

Sol cards display:

```text
outcome
current_focus
next_checkpoint or "Next proof is not projected in this briefing."
No Chairman action required.
```

Exception cards display impact, repair owner, and whether an exact Chairman attention item joins them. Raw diagnostic strings do not exist in the payload and therefore cannot appear in DOM.

### Step 6: Implement evidence drawer and accessibility

Required behavior:

- opener is remembered;
- drawer gets `aria-hidden=false` and close button focus;
- Tab and Shift+Tab are trapped inside the open drawer;
- Escape closes it;
- closing restores focus to the opener;
- scrim click closes it;
- evidence rows are rendered with `textContent`;
- fixed Advanced link opens `/` normally; no arbitrary URL is passed to `window.open`;
- network failure renders an unavailable headline and leaves Advanced usable;
- refresh announcements use one bounded `role=status` update, not a repeating timer.

### Step 7: Run GREEN and commit

```bash
python -m pytest tests/test_chairman_control_room_brief_ui.py -q
node --check app/static/chairman_control/brief.js
git add app/static/chairman_control/brief.js tests/test_chairman_control_room_brief_ui.py
git commit -m "feat(control-room): render the read-only Chairman briefing"
```

If Node is unavailable, record that fact and rely on the mandatory CI plus pure-Python structural check; do not claim Node proof.

---

# Task 7: Exercise the complete failure and responsive browser matrix

**Files:**
- Modify: `tests/test_chairman_brief.py`
- Modify: `tests/test_chairman_control_room_brief_server.py`
- Modify: `tests/test_chairman_control_room_brief_ui.py`

### Step 1: Complete deterministic fixture coverage

The test suite must cover all reachable DF1 states:

1. current, no Chairman attention, no exceptions;
2. current, one incomplete Chairman attention item;
3. three visible attention items plus overflow;
4. duplicate attention identity;
5. attention-to-work join absent;
6. attention-to-work join ambiguous;
7. one exact current Sol-owned outcome;
8. stale Sol responsibility excluded from reassuring copy;
9. blocked Sol-owned outcome becomes exception;
10. worker return waiting for Sol;
11. runtime unavailable with Agent OS/GitHub still usable;
12. Agent OS unavailable;
13. Executive Inbox unavailable;
14. GitHub evidence unavailable;
15. all critical sources unavailable;
16. failed refresh / historical cache;
17. source conflict;
18. effect unknown;
19. owner not established;
20. capacity blocked;
21. unsafe token text upstream;
22. absolute host path upstream;
23. traceback upstream;
24. hidden-prompt/private-reasoning text upstream;
25. oversized response refusal;
26. exact cap success;
27. corrupt source shape;
28. Programs unavailable and absent as enabled navigation;
29. Ask Sol unavailable and absent as enabled navigation;
30. Advanced available while the brief is unavailable.

A complete decision card is intentionally not reachable in DF1 because no accepted complete decision-packet source exists. The test must assert that limitation rather than manufacture a fixture-only authority.

### Step 2: Build the isolated browser behavior harness

Follow the existing `tests/test_chairman_control_room_ui_x1.py` pattern:

- start the in-process P0A server on an OS-assigned loopback port;
- use an isolated browser profile;
- inject deterministic cached documents rather than contacting real sources in CI;
- use an explicitly supplied Chrome executable and Playwright module;
- keep the test optional on environments without the exact browser dependencies, but require it for the real acceptance run;
- prove browser process cleanup/absence after the test.

### Step 3: Prove required viewports

Run the same semantic cases at:

```text
1440 × 900
1024 × 768
390 × 844
```

For each viewport assert:

```javascript
document.documentElement.scrollWidth <= window.innerWidth
```

Also prove:

- headline is visible without scroll;
- one priority attention item is understandable above routine sections;
- no sidebar or surface dock is visible;
- Advanced is reachable;
- evidence drawer opens/closes with keyboard;
- focus restores;
- source-derived secret/path strings are absent from `document.body.innerText`;
- reduced-motion mode does not hide content;
- network failure leaves a truthful unavailable state rather than a spinner.

### Step 4: Run focused and integrated suites

```bash
python -m pytest \
  tests/test_chairman_brief.py \
  tests/test_chairman_control_room_brief_server.py \
  tests/test_chairman_control_room_brief_ui.py \
  -q

python -m pytest \
  tests/test_chairman_control_room.py \
  tests/test_chairman_control_room_server.py \
  tests/test_chairman_control_room_ui_x1.py \
  tests/test_chairman_control_room_remote.py \
  -q
```

Then run the repository-required test command exactly as CI defines it. Do not substitute a selected suite for the required gate.

### Step 5: Prove remote X1 and shared assets are unchanged

```bash
git diff --exit-code origin/master -- \
  control_plane/chairman_control_room_remote.py \
  scripts/chairman_control_room_remote.py \
  app/static/chairman_control/remote.html \
  app/static/chairman_control/control_room.js \
  app/static/chairman_control/control_room.css \
  ops/control_room_remote/install.sh \
  ops/control_room_remote/mastermind-control-room-remote.service
```

Expected: no diff.

### Step 6: Commit the completed proof matrix

```bash
git add \
  tests/test_chairman_brief.py \
  tests/test_chairman_control_room_brief_server.py \
  tests/test_chairman_control_room_brief_ui.py
git commit -m "test(control-room): prove DF1 truth and responsive behavior"
```

---

# Task 8: Document the canary and preserve Advanced

**Files:**
- Modify: `docs/CHAIRMAN_CONTROL_ROOM.md`

### Step 1: Add the operator journey

Document exactly:

```bash
python3 scripts/chairman_control_room.py --port 8787
open http://127.0.0.1:8787/brief
```

State clearly:

- `/brief` is the read-only Chairman canary;
- `/` is the existing Advanced inspector;
- `/api/brief` is token-gated and not a public API;
- no action, decision submission, Programs, Ask Sol, or material-change checkpoint exists in DF1;
- the local token is a browser-origin/CSRF nonce, not same-user process authentication;
- a partial/historical/unavailable brief is expected when canonical inputs are absent;
- raw diagnostics belong at `/`, not in the default brief;
- restarting the process rebuilds from canonical readers and forgets process-memory cache;
- remote X1 is unchanged.

### Step 2: Add rollback instructions

DF1 canary rollback is presentation-only:

```text
Stop using /brief and continue opening /.
```

No canonical state rollback, database migration, or data restoration exists.

### Step 3: Run documentation/source checks and commit

```bash
python -m pytest \
  tests/test_chairman_control_room_brief_server.py \
  tests/test_chairman_control_room_brief_ui.py \
  -q

git add docs/CHAIRMAN_CONTROL_ROOM.md
git commit -m "docs(control-room): document the DF1 Today canary"
```

---

# Task 9: Produce immutable source and real-local proof receipts

**Files:**
- Create: `docs/superpowers/plans/2026-09-07-chairman-control-room-df1-implementation-receipt.md`

### Step 1: Freeze the candidate identity

Record:

```bash
git rev-parse HEAD
git rev-parse HEAD^{tree}
git merge-base HEAD origin/master
git status --short --branch
git diff --name-status origin/master...HEAD
git ls-tree -r HEAD -- \
  control_plane/chairman_brief.py \
  app/static/chairman_control/brief.html \
  app/static/chairman_control/brief.js \
  app/static/chairman_control/brief.css \
  tests/test_chairman_brief.py \
  tests/test_chairman_control_room_brief_server.py \
  tests/test_chairman_control_room_brief_ui.py \
  docs/superpowers/plans/2026-09-07-chairman-control-room-df1-implementation-receipt.md \
  scripts/chairman_control_room.py \
  docs/CHAIRMAN_CONTROL_ROOM.md
```

The receipt lists exact commit, tree, base, and blob identities. Do not call an unpushed local commit published evidence.

### Step 2: Run the real local canary

On the authorized Chairman Mac, from the exact candidate worktree:

```bash
python3 scripts/chairman_control_room.py --port 8787
```

Prove:

- startup composition completes or fails into the documented truthful state;
- `GET /brief` loads;
- `GET /api/brief` reads the same cached generation;
- `GET /` still loads the complete Advanced inspector;
- the current real degraded runtime path is translated to impact copy and is absent from brief JSON/DOM;
- restart/readback preserves canonical semantics while process cache is rebuilt;
- no provider open, bind, unbind, refresh, or mutation is triggered by `/brief`.

### Step 3: Capture real browser evidence

Capture at all three required viewports with exact candidate identity and timestamp. Record screenshot paths and SHA-256 digests in the receipt, but do not commit private screenshots or host paths unless the repository's accepted evidence policy explicitly permits them.

The receipt must describe what each screenshot proves. A screenshot alone is not acceptance.

### Step 4: Conduct the witnessed Chairman task

Ask Chris one closed question while the exact canary is open:

```text
Does anything on this page currently require your action: yes or no?
```

Pass criteria:

- correct answer within ten seconds;
- no Slack, Linear, GitHub, Finder, or Advanced inspection required;
- the answer agrees with the current admitted Chairman attention state;
- any unavailable source is understood as withheld evidence, not a zero.

Record the observed result. Do not invent or backfill a usability receipt without the witnessed run.

### Step 5: Run final verification before publication

```bash
python -m compileall control_plane scripts tests
node --check app/static/chairman_control/brief.js
python -m pytest \
  tests/test_chairman_brief.py \
  tests/test_chairman_control_room_brief_server.py \
  tests/test_chairman_control_room_brief_ui.py \
  tests/test_chairman_control_room.py \
  tests/test_chairman_control_room_server.py \
  tests/test_chairman_control_room_ui_x1.py \
  tests/test_chairman_control_room_remote.py \
  -q
```

Then run the repository-required CI command and security checks on the exact immutable head.

### Step 6: Commit the receipt and publish once

```bash
git add docs/superpowers/plans/2026-09-07-chairman-control-room-df1-implementation-receipt.md
git commit -m "docs(control-room): record DF1 candidate proof"
git push -u origin sol/chairman-decision-cockpit-df1-20260907
```

Open one Draft/Hold PR. Do not mark Ready, merge, install as default, or start DF2.

The PR body must distinguish:

```text
source built
hosted CI
local canary installed/running
browser proof
witnessed Chairman task
Sol acceptance
default cutover
```

A missing row remains explicitly missing.

---

## Implementation order and worker routing

This plan is sequential because Tasks 1–7 share one reducer/server/UI contract and one ten-path ceiling. Do not dispatch multiple concurrent writers against these files.

Recommended avenue after all gates pass:

```text
PREFERRED_AVENUE: Terra or bounded CTO Sol implementation worker
WHY NOT FABLE: architecture and ambiguity are frozen; the remaining work is test-driven bounded implementation and browser proof.
```

Use one source writer for Tasks 0–9. Independent review can run after a stable immutable head, but must not edit the writer's worktree. A review finding returns to the same writer and same PR as a bounded repair unless effect/ownership state requires reconciliation.

---

## Acceptance checklist

DF1 source is eligible for Sol review only when all are true:

### Product

- `/brief` immediately answers act/no-act at Chairman altitude.
- No project board, percent complete, giant object counts, sidebar, or permanent surface rail appears.
- Sol-handling items communicate coverage without invented progress.
- Exceptions explain impact before machinery.
- Advanced remains one click away and functionally complete.

### Truth

- Missing source never becomes empty/clear.
- Attention never becomes a complete decision without the missing source contract.
- Current, partial, historical, and unavailable remain distinct.
- Source conflict and effect uncertainty remain visible.
- `NO_LONGER_PRESENT`, completion, merge, deployment, and acceptance are never invented.

### Security

- Closed output keys and item allowlists are tested.
- Raw paths, tracebacks, secrets, prompts, reasoning, and transcripts are absent from JSON and DOM.
- `/api/brief` is loopback/Host/token/Origin-gated and no-store.
- Query strings and arbitrary paths are refused.
- No POST or arbitrary navigation input exists.
- Response cap is enforced before write.

### No duplicate system

- Reducer is pure over the cached document.
- No database, cache authority, source reader, queue, lifecycle, identity registry, scheduler, retry, watcher, or model authority was added.
- Existing owner code is consumed, not copied.
- Linear remains portfolio owner.
- Remote X1 and shared inspector assets are unchanged.

### Proof

- focused tests pass;
- legacy local and remote tests pass;
- required repository CI and security checks pass on exact head;
- real local `/brief` and `/` readback pass;
- desktop/tablet/mobile browser evidence exists;
- process restart behavior is proven;
- witnessed Chairman ten-second task passes;
- exact candidate identity and path census are recorded.

---

## Stop conditions

Stop and return to Sol without broadening scope when any of these occurs:

- PR #521 is not protected or has unresolved blocking review;
- PR #424's older H1A closure remains unresolved;
- an implementation path has another current writer;
- the existing cache cannot supply the required input without a second gather;
- complete decision cards would require invented or model-authored fields;
- a safe default summary cannot be produced without leaking privileged text;
- remote X1 or shared inspector assets would need modification;
- an eleventh path is required;
- a new POST/action path appears necessary;
- exact source movement changes the material architecture, reducer inputs, security contract, or proof ruler;
- browser proof reveals the Chairman still cannot answer act/no-act without Advanced;
- any modification outcome becomes uncertain.

Return format:

```text
BLOCKED or DECISION_REQUEST
exact operation key
exact head/tree/base
known effect state
blocking source/identity/path
smallest safe next action
production_effect=NONE unless separately proven
```

---

## Continuation handoff

On implementation return, provide:

- mission and user outcome;
- current protected source and same-SHA Skillpack;
- exact branch/PR/head/tree/base and ten path/blob identities;
- tests and hosted checks with exact run/job identities;
- browser proof matrix and screenshot digests;
- real local process/readback result;
- current capability classification;
- all missing proof or disagreements;
- explicit statement that DF2/default cutover remains held;
- exact requested Sol ruling;
- watcher state and required same-carrier `CONTINUE`, `REQUEST_REPAIR`, or terminal `STOP` edge if a reciprocal worker dialogue is used.

The implementation worker's stop boundary is one Draft/Hold DF1 PR. No merge, default-route switch, Programs, Ask Sol, actions, learning telemetry, or successor wave begins without a new explicit Sol/Chairman edge.

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

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Use superpowers:test-driven-development before implementation code, superpowers:systematic-debugging for unexpected behavior, and superpowers:verification-before-completion before every completion claim.

**Goal:** Deliver one real local Chairman briefing at `GET /brief` that lets Chris determine within ten seconds whether he must act, what Sol is handling, and which material exceptions threaten outcomes, while preserving the current dense Control Room at `/` as the Advanced inspector.

**Architecture:** Add one pure `mastermind.chairman_brief.v1` reducer over the already-cached `mastermind.chairman_control_room.v1` document and its existing source-validity/cache metadata. Add one fixed authenticated JSON read at `GET /api/brief` plus three local-only static assets. Perform no second gather, no new source read, no mutation, no model call, no lifecycle inference, and no remote-X1 change.

**Tech Stack:** Python 3.11+, pytest, the existing stdlib `ThreadingHTTPServer`, dependency-free browser JavaScript and CSS, Node syntax validation when available, and the repository's existing isolated Chromium/Playwright proof pattern for real browser acceptance.

**Spec:** `docs/superpowers/specs/2026-09-07-chairman-control-room-decision-first-experience-design.md` on Mastermind PR #521.

---

## 1. Status and implementation admission

Chairman product direction is approved. This plan is a records-only stacked carrier. It does not authorize implementation by itself.

DF1 START requires every gate below to be positively verified against one current protected revision:

1. Mastermind PR #521 is independently reviewed and merged into protected `master`.
2. The protected commit containing the design is pinned, and the compatible Sol Skillpack is loaded from that same commit.
3. Mastermind PR #424's incumbent/current owner has reconciled the older H1A route/static closure so it neither authorizes a competing Workstream Workroom default nor forbids the exact DF1 route/assets below.
4. No open PR, branch, worktree, process, or source writer owns any DF1 implementation path.
5. Local P0A and remote X1 contracts are re-read from the pin; X1 remains outside the change set.
6. This plan has independent review and explicit Sol acceptance.
7. One implementation writer is assigned to one branch and one PR. No parallel writer touches the same paths.

Missing gate:

```text
BLOCKED SOURCE_OR_OWNERSHIP_PRECONDITION
production_effect=NONE
```

Do not create the implementation branch, edit source, or send worker START solely because the Chairman approved the product direction.

---

## 2. Product and authority constraints

### Canonical owners remain unchanged

- Executive OS owns Job / Attempt / Worker / Event lifecycle and action admission.
- Agent OS owns durable workstreams, decisions, discoveries, and handoffs.
- GitHub owns implementation, review, CI, merge, and evidence.
- Linear remains the selected portfolio/project projection.
- Slack and Agent Relay remain transport/hot-state projection, never lifecycle truth.
- The existing Control Room compositor and process-memory cache remain the only source-composition path DF1 consumes.
- The brief is disposable presentation. Deleting every DF1 artifact changes no canonical fact.

### DF1 must not add

- a database, table, event store, queue, scheduler, retry ledger, wake path, dispatch path, lifecycle, identity registry, state cache, background gather loop, or analytics store;
- a POST endpoint or action control;
- a Linear, Slack, GitHub, Agent OS, Executive OS, browser, provider, account, or credential write;
- a model invocation or model-authored ranking, owner, decision, status, closure, or suppression rule;
- Programs, Ask Sol, display checkpointing, material-change history, default cutover, or Chairman mutation;
- a second autonomy, source-validity, dispatch, watcher, effect, or actionability classifier;
- any remote X1 change.

### Truthfulness rules

- Missing is not empty.
- Failed refresh makes the retained cache historical until a successful current composition replaces it.
- A source-degraded document may remain usable by section.
- Chairman attention is not automatically a complete decision.
- Bindings, tabs, provider sessions, windows, and process presence never prove cognition or execution.
- CI, merge, installation, deployment, production proof, and final acceptance remain distinct.

### Default-surface privacy

The brief JSON and DOM must never expose:

- credentials, bearer values, cookies, tokens, passwords, secrets, browser profiles, or provider-session identifiers;
- hidden prompts, raw transcripts, private reasoning, or chain-of-thought;
- raw exception/traceback bodies;
- absolute host paths;
- arbitrary upstream mappings, arbitrary URLs, or unreviewed HTML.

Unsafe source text is replaced with one fixed disclosure sentence. The implementation never reveals which secret detector matched.

---

## 3. Current source bindings

The implementation worker must re-read these exact owners at the admitted base:

| Existing path | DF1 use | Permission |
|---|---|---|
| `control_plane/chairman_control_room.py` | Existing pure cross-owner composition | read only |
| `control_plane/autonomy_control_room_projection.py` | Responsibility, owner, source freshness, placement and dispatch projection | read only |
| `control_plane/executive_inbox.py` | Chairman/CEO/COO attention projection | read only |
| `scripts/chairman_control_room.py` | Existing P0A cache and local HTTP server | narrow additive edit |
| `app/static/chairman_control/index.html` | Current Advanced inspector | read only |
| `app/static/chairman_control/control_room.js` | Shared local/X1 inspector client | read only |
| `app/static/chairman_control/control_room.css` | Shared local/X1 inspector styles | read only |
| `tests/test_chairman_control_room_server.py` | Existing server harness/helpers | read only |
| `tests/test_chairman_control_room_ui_x1.py` | Existing safe-DOM/browser-proof patterns | read only |
| `control_plane/chairman_control_room_remote.py` | X1 projection/release owner | read only |
| `scripts/chairman_control_room_remote.py` | X1 server | read only |
| `app/static/chairman_control/remote.html` | X1 entry | read only |
| `docs/CHAIRMAN_CONTROL_ROOM.md` | Local operator documentation | narrow additive edit |

The current P0A cache envelope already supplies:

```text
control_room
capabilities
live_builds_active
composed_at
refresh_in_flight
state_refresh_error
source_validity
```

DF1 consumes only:

```text
control_room
composed_at
refresh_in_flight
state_refresh_error
source_validity
```

It does not call provider capability census.

Load-bearing source shapes at the frozen pin:

```text
control_room.attention.chairman[]
control_room.work[]
control_room.autonomy.responsibilities[]
control_room.autonomy.unmapped_responsibilities[]
source_validity.cards[].components.card.state
```

The accepted dispatch field is:

```text
responsibility.dispatch.dispatch_state
```

It is not `responsibility.dispatch.state`. Implementation and tests must bind the current field exactly.

---

## 4. Exact implementation path ceiling

The implementation PR may touch exactly ten paths.

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

Any eleventh path requires:

```text
DECISION_REQUEST PATH_BOUNDARY_REQUIRED
production_effect=NONE
```

Do not absorb work into `index.html`, `control_room.js`, or `control_room.css`. Those assets are deliberately preserved and shared with the existing inspector/X1 estate.

Recommended implementation branch, created only after admission:

```text
sol/chairman-decision-cockpit-df1-20260907
```

Return state:

```text
DRAFT / HOLD-FOR-SOL / BUILT_NOT_PROVEN
```

---

## 5. Fixed route and static closure

DF1 adds exactly:

```text
GET /brief
GET /api/brief
GET /static/brief.js
GET /static/brief.css
```

Rules:

- `/brief` serves token-injected `brief.html` with the same CSP used by `/`.
- `/api/brief` requires loopback, allowed Host, exact `X-CCR-Token`, matching Origin when present, and `Cache-Control: no-store`.
- `/brief` and `/api/brief` reject every non-empty query string.
- `/api/brief` reads one existing cached snapshot and performs no synchronous composition, filesystem discovery, network operation, provider census, or subprocess.
- It may invoke the existing single-flight stale-cache check, but returns the cached snapshot immediately.
- The success payload is canonical-encoded and measured before any byte is written.
- Maximum successful body is exactly `262144` bytes.
- A larger payload returns HTTP `503` with exactly:

```json
{
  "schema": "mastermind.chairman_brief_error.v1",
  "error": "CHAIRMAN_BRIEF_RESPONSE_TOO_LARGE"
}
```

- No partial success payload is written.
- No new POST route exists.
- `/` remains the legacy inspector during DF1.
- Remote X1 route/static/package closure remains byte-unchanged.

---

## 6. Frozen `mastermind.chairman_brief.v1` contract

### Pure function

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

### Closed vocabularies

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

### Exact top-level shape

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

`changes` remains explicitly unavailable. DF1 creates no local display checkpoint. The UI hides future unavailable sections rather than presenting dead navigation.

### Headline precedence

Apply exactly:

1. Invalid/missing Control Room schema or no usable attention/ownership source → `UNAVAILABLE`.
2. `state_refresh_error` with retained data → `headline=PARTIAL`, `read_state=HISTORICAL`.
3. One or more critical sources unavailable while another section remains usable → `PARTIAL`.
4. Complete current decisions exist → `DECISIONS_REQUIRED`.
5. Current Chairman attention exists → `ATTENTION_REQUIRED`.
6. A positively current Chairman-attention read with zero items → `CLEAR`.

DF1 has no complete decision-packet source. Therefore:

```text
decisions.state=UNAVAILABLE
complete_decision_count=0
reason=DECISION_PACKET_SOURCE_NOT_PROJECTED
```

A future decision source requires a separate accepted contract. DF1 must not introduce a speculative input merely to render fixture-only decisions.

### Critical source checks

```text
Agent OS usable:
  sources.agent_os_state_schema == agent_os_state.v1

Executive Inbox usable:
  sources.executive_inbox_schema == mastermind.executive_inbox.v2

GitHub evidence usable:
  sources.active_builds_schema == project_active_builds.v1

Runtime usable:
  sources.runtime_db_present is true
```

The reducer may inspect only the prefix before the first colon in each `degraded[]` string to select a fixed source reason. The suffix is discarded and never serialized.

### Chairman attention item

Closed keys:

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

- `attention_id` must be a safe nonblank existing identity.
- Join to `work_ref` only through exactly one `work[].attention_ids[]` claim.
- Zero claims yields `work_ref=null`.
- Multiple claims produce `SOURCE_CONFLICT`; no winner is selected.
- `summary` comes only from source `summary` or `reason`, through the sanitizer.
- `source_time` remains null unless the source row itself supplies an accepted timestamp.
- `control_room.generated_at` is `observed_at`, never mislabeled as source time.
- `advanced_ref` is fixed `/#today`, never copied from upstream.
- No approve/hold/continue/stop action exists.

Current missing-decision disclosure:

```text
authority_required
closed_options
consequence_of_acting
consequence_of_waiting
reversibility
recommendation_provenance
```

### Sol-handling item

Closed keys:

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

Exact admission requires:

```text
responsibility.accountable_seat == "ceo"
responsibility.query_status == "ok"
responsibility.freshness == "current"
matching source_validity component card.state == "current"
responsibility.placement_state.value != "EFFECT_UNKNOWN"
responsibility.dispatch.dispatch_state not in {"RETURNED", "EFFECT_UNKNOWN"}
exact joined work card has no Chairman attention
exact joined work card has no disagreement
Agent OS next_action is safe and nonblank
Agent OS state/status is not blocked/done/killed
unmet_dependencies is empty
```

The source-validity join is exact on:

```text
responsibility_ref
root_job_id
```

No matching validity row means currentness is unproven. The row cannot appear under reassuring `Sol is handling`; the section becomes partial and the gap is represented by a fixed source-currentness reason.

Join work only by:

```text
responsibility.responsibility_ref == work.work_ref
```

Fields:

- `outcome`: safe responsibility title, then safe Agent OS title.
- `why_it_matters`: safe Agent OS reason, else null.
- `current_focus`: safe Agent OS next action.
- `next_checkpoint`: null unless an exact accepted checkpoint/proof field already exists. Do not relabel next action as proof.
- `accountable_owner`: literal `SOL`, admitted only through exact CEO accountability.
- `chairman_action_required`: always false for an admitted Sol row.
- Sort by exact responsibility ref; show six; expose overflow.

### Exception item

Closed keys:

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

Fixed admissions:

| Exact fact | Kind | Fixed impact |
|---|---|---|
| `state_refresh_error` | `SOURCE_UNAVAILABLE` | `The latest refresh failed. Cached evidence is historical until a successful composition replaces it.` |
| runtime missing/invalid | `SOURCE_UNAVAILABLE` | `Current execution claims are withheld. Organizational and implementation evidence may remain usable.` |
| Inbox missing/invalid | `SOURCE_UNAVAILABLE` | `Current Chairman attention cannot be established from Executive evidence.` |
| Agent OS missing/invalid | `SOURCE_UNAVAILABLE` | `Current outcomes, owners, and next actions cannot be established from Agent OS.` |
| active-builds missing/invalid | `SOURCE_UNAVAILABLE` | `Current implementation and proof changes cannot be established from GitHub evidence.` |
| `work[].disagreements` nonempty | `SOURCE_CONFLICT` | `Canonical and projected evidence disagree. No winner is selected in this briefing.` |
| exact blocked status/state or unmet dependency | `WORK_BLOCKED` | `This outcome cannot advance through its recorded next step.` |
| exact failed Executive job | `WORK_BLOCKED` | `A recorded Executive job failed. The next safe action requires inspection.` |
| `dispatch.dispatch_state == RETURNED` and accountable seat CEO | `WORK_WAITING` | `A worker return is waiting for Sol adjudication.` |
| exact placement/dispatch `EFFECT_UNKNOWN` | `EFFECT_UNKNOWN` | `A prior operation may have taken effect. No retry or carrier change is permitted until reconciled.` |
| exact placement `WAITING_CAPACITY` | `CAPACITY_BLOCKED` | `The operation is waiting for an eligible capacity assignment.` |
| autonomy unmapped responsibility | `OWNER_NOT_ESTABLISHED` | `An accountable operator cannot be established from the current owner mapping.` |
| exact source-owned proof-missing token | `PROOF_MISSING` | `Implementation evidence exists, but the required accepted proof is not present.` |
| exact source-owned production-regression token | `PRODUCTION_REGRESSION` | `A previously usable production journey is reported as regressed.` |

Do not infer proof missing from an open PR. Do not infer production regression from a failed test. Those kinds require exact source-owned tokens.

Closed repair owners:

```text
EXECUTIVE_OS
AGENT_OS
GITHUB_EVIDENCE
SOL
CAPACITY_OWNER
UNKNOWN
```

`chairman_action_required` is true only when exact current Chairman attention joins the same work identity. An exception cannot escalate itself.

### Safe evidence reference

Closed keys:

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

Allowed refs:

```text
attention:<safe-id>
job:<safe-id>
workstream:WS:<safe-key>
github:<owner>/<repo>#<number>
source:<repository-relative-path>
cache:<sha256>
```

No upstream URL is copied in DF1. The fixed Advanced link provides the detailed inspector.

### Sanitizer

Required behavior:

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

Reject case-insensitively:

```text
Bearer 
token=
api_key
cookie
authorization
password
secret
Traceback (most recent call last)
chain of thought
private reasoning
hidden prompt
raw transcript
```

Reject path forms:

```text
/Users/
/home/
/private/
/var/
/opt/
/tmp/
Windows drive-letter absolute paths
```

Unsafe summary replacement:

```text
Source-owned detail is withheld from the default briefing. Inspect Advanced evidence.
```

---

# Task 0: Admit one clean implementation carrier

**Files:** none.

### Step 1: Re-pin source and Skillpack

```bash
git fetch origin master
git rev-parse origin/master
git show origin/master:docs/sol_skills/INDEX.md | sed -n '1,100p'
```

Record exact protected SHA and compatible schema/version/bootstrap in the eventual receipt.

### Step 2: Verify design protection

```bash
gh pr view 521 --repo mastermindx-market-intelligence/Mastermind \
  --json state,isDraft,mergedAt,mergeCommit,reviewDecision,headRefOid
```

Required:

```text
state=MERGED
isDraft=false
mergedAt non-null
no unresolved blocking review
```

### Step 3: Reconcile PR #424 without takeover

```bash
gh pr view 424 --repo mastermindx-market-intelligence/Mastermind \
  --json state,isDraft,mergedAt,headRefOid,reviewDecision,files,comments
```

Required immutable receipt from its current owner or accepted source successor:

- useful H0 archaeology retained;
- old H1A default Workstream Workroom superseded/held;
- old `/api/hub/workstream/chairman-control-room` and `hub_workroom.*` exclusive closure removed;
- this plan's `/brief`, `/api/brief`, and `brief.*` closure accepted;
- no competing H1A implementation may merge behind DF1.

Do not edit #424's four files from the DF1 carrier.

### Step 4: Census path ownership

```bash
python3 - <<'PY'
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

Include rename history. Stop on unresolved ownership.

### Step 5: Create isolated worktree after admission

```bash
git worktree add \
  ../Mastermind-chairman-decision-cockpit-df1-20260907 \
  -b sol/chairman-decision-cockpit-df1-20260907 \
  origin/master
cd ../Mastermind-chairman-decision-cockpit-df1-20260907
git status --short --branch
```

Expected: clean branch on current protected source.

---

# Task 1: Build the pure contract and read-state ruler

**Files:**
- Create: `tests/test_chairman_brief.py`
- Create: `control_plane/chairman_brief.py`

### Step 1: Write RED contract tests

Use an explicit sentinel so `control_room=None` is distinguishable from the fixture default.

```python
from __future__ import annotations

import json

from control_plane import chairman_brief as brief

_SENTINEL = object()


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


def _compose(doc=_SENTINEL, **overrides):
    args = {
        "control_room": _base_doc() if doc is _SENTINEL else doc,
        "source_validity": {
            "schema": "mastermind.control_room_source_validity.v1",
            "publication_seq": 1,
            "cards": [],
        },
        "composed_at": "2026-09-07T00:00:01Z",
        "refresh_in_flight": False,
        "state_refresh_error": None,
    }
    args.update(overrides)
    return brief.compose_chairman_brief(**args)


def test_contract_is_closed_and_deterministic():
    one = _compose()
    two = _compose()
    assert set(one) == brief.OUTPUT_KEYS
    assert one == two
    assert json.dumps(one, sort_keys=True, allow_nan=False) == json.dumps(
        two, sort_keys=True, allow_nan=False
    )


def test_absent_control_room_is_unavailable_not_clear():
    out = _compose(doc=None)
    assert out["read_state"]["state"] == "UNAVAILABLE"
    assert out["headline"]["kind"] == "UNAVAILABLE"


def test_refresh_failure_makes_retained_document_historical():
    out = _compose(state_refresh_error="raw /Users/private/runtime failure")
    encoded = json.dumps(out, sort_keys=True)
    assert out["read_state"]["state"] == "HISTORICAL"
    assert out["headline"]["kind"] == "PARTIAL"
    assert "/Users/private/runtime" not in encoded
```

### Step 2: Run RED

```bash
python -m pytest tests/test_chairman_brief.py -q
```

Expected: import/contract failure.

### Step 3: Implement constants, canonical digest, source checks, and read-state

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

Do not normalize or mutate the source before hashing.

### Step 4: Add hostile-shape tests

Cover wrong schema, non-mapping input, malformed lists, invalid source-validity shape, duplicate identities, NaN/unserializable values, non-boolean refresh state, and reordered source-insensitive lists. The reducer returns a closed unavailable/partial document; it never raises.

### Step 5: Run GREEN and commit

```bash
python -m pytest tests/test_chairman_brief.py -q
git add control_plane/chairman_brief.py tests/test_chairman_brief.py
git commit -m "feat(control-room): add pure Chairman brief contract"
```

---

# Task 2: Project truthful Chairman attention without manufacturing decisions

**Files:**
- Modify: `tests/test_chairman_brief.py`
- Modify: `control_plane/chairman_brief.py`

### Step 1: Add RED source fixtures and assertions

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


def test_attention_is_not_promoted_to_complete_decision():
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

### Step 2: Add exact-join and conflict RED tests

Prove:

- one exact attention-id claim joins one work ref;
- no claim yields null work ref, never title similarity;
- multiple claims yield `SOURCE_CONFLICT`, never a selected winner;
- duplicate attention identities force partial/conflict state;
- non-Chairman targets never enter the Chairman section;
- absent/invalid stable attention id cannot render as current;
- unsafe reason text becomes fixed withheld copy;
- evidence is closed and safe, not recursively copied.

### Step 3: Run RED

```bash
python -m pytest tests/test_chairman_brief.py -q -k 'attention or decision'
```

### Step 4: Implement exact claims

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

Preserve source order, then stable identity. Show three and disclose overflow. Do not add a severity score.

### Step 5: Run GREEN and commit

```bash
python -m pytest tests/test_chairman_brief.py -q
git add control_plane/chairman_brief.py tests/test_chairman_brief.py
git commit -m "feat(control-room): project truthful Chairman attention"
```

---

# Task 3: Add source-qualified Sol coverage and exceptions

**Files:**
- Modify: `tests/test_chairman_brief.py`
- Modify: `control_plane/chairman_brief.py`

### Step 1: Add exact validity fixture

```python
def _current_card_validity(ref="WS:EXAMPLE", root=None) -> dict:
    return {
        "responsibility_ref": ref,
        "root_job_id": root,
        "components": {
            "card": {
                "proof_ref": "a" * 64,
                "qualified_at": "2026-09-07T00:00:00Z",
                "remaining_ms": 1000,
                "state": "current",
            }
        },
    }
```

### Step 2: Write Sol-handling RED test with current field names

```python
def test_only_exact_current_ceo_responsibility_enters_sol_handling():
    doc = _base_doc()
    doc["work"] = [{
        "work_ref": "WS:EXAMPLE",
        "agent_os": {
            "title": "Example outcome",
            "status": "active",
            "program": "example",
            "next_action": "Prove one real user-visible result.",
            "state": "in_progress",
            "reason": "The user journey is not production-proven.",
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
        "root_job_id": None,
        "title": "Example outcome",
        "accountable_seat": "ceo",
        "state": "in_progress",
        "query_status": "ok",
        "freshness": "current",
        "is_actionable": True,
        "placement_state": {"value": "not_observable"},
        "dispatch": {"dispatch_state": "UNKNOWN"},
        "source_receipts": [],
    }]
    validity = {
        "schema": "mastermind.control_room_source_validity.v1",
        "publication_seq": 1,
        "cards": [_current_card_validity()],
    }
    out = _compose(doc=doc, source_validity=validity)
    item = out["sol_handling"]["items"][0]
    assert item["work_ref"] == "WS:EXAMPLE"
    assert item["accountable_owner"] == "SOL"
    assert item["chairman_action_required"] is False
    assert item["current_focus"] == "Prove one real user-visible result."
    assert item["next_checkpoint"] is None
```

Negative cases:

- accountable seat not CEO;
- stale/unknown freshness;
- source-validity card absent/unqualified/expired;
- source-validity ref or root mismatch;
- refused/degraded query status;
- Chairman attention on joined work;
- source disagreement;
- blocked/done/killed state;
- unmet dependency;
- `dispatch.dispatch_state == RETURNED`;
- `dispatch.dispatch_state == EFFECT_UNKNOWN`;
- placement `EFFECT_UNKNOWN`;
- unsafe/missing next action;
- duplicate responsibility ref;
- similar but unequal refs.

### Step 3: Write exception RED tests

Include the observed failure class:

```python
def test_runtime_path_is_replaced_with_fixed_impact_copy():
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

Prove every table row in §6. Also prove:

- `EFFECT_UNKNOWN` is never inferred from prose;
- `WAITING_CAPACITY` requires exact token;
- open PR alone never creates `PROOF_MISSING`;
- failed CI text alone never creates `PRODUCTION_REGRESSION`;
- overflow is visible after six;
- ordering is fixed kind order, work ref, stable id—not score;
- duplicate source facts dedupe only on exact semantic fingerprint;
- source conflict is preserved.

### Step 4: Implement exact joins, fixed templates, stable ids, and sanitizer

Prefix use is limited to source family:

```python
source_family = entry.split(":", 1)[0] if isinstance(entry, str) else None
```

Discard the suffix before output construction.

Stable ids:

```python
def _stable_id(prefix: str, *parts: str | None) -> str:
    material = "|".join([SCHEMA, prefix, *(part or "" for part in parts)])
    return prefix + "-" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]
```

### Step 5: Add anti-authority AST test

Assert the pure module does not import/call:

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
runtime mutation APIs
surface-binding writers
```

### Step 6: Run GREEN and commit

```bash
python -m pytest tests/test_chairman_brief.py -q
git add control_plane/chairman_brief.py tests/test_chairman_brief.py
git commit -m "feat(control-room): compress Sol coverage and exceptions"
```

---

# Task 4: Add fixed local reads without a second gather

**Files:**
- Create: `tests/test_chairman_control_room_brief_server.py`
- Modify: `scripts/chairman_control_room.py`

### Step 1: Write server RED tests using existing harness

Pytest already adds the tests directory for sibling imports; use the repository's current pattern:

```python
from test_chairman_control_room_server import (
    _auth_headers,
    _get,
    _make_config,
    _running_server,
)
```

Initial tests:

```python
def test_brief_html_bootstraps_nonce_and_csp(tmp_path):
    config = _make_config(tmp_path)
    with _running_server(config) as (_httpd, port):
        status, headers, body = _get(port, "/brief")
    assert status == 200
    assert headers["content-security-policy"]
    assert config.token.encode() in body


def test_brief_api_requires_nonce_and_is_no_store(tmp_path):
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

### Step 2: Add route/security/cache tests

Prove:

- non-empty queries on `/brief` or `/api/brief` refuse;
- unknown static names 404;
- only three new static assets exist;
- `/api/brief` performs zero synchronous `_compose_state_doc` calls;
- `/api/brief` performs zero capability-census calls;
- one `_cached_state_snapshot` generation feeds one response;
- existing single-flight refresh behavior remains;
- `/`, `/api/state`, and current POST routes remain unchanged;
- `POST /api/brief` 404s;
- external peer, bad Host, token, or Origin fails before reducer call.

Use call counters, not timing guesses.

### Step 3: Add response-cap RED

Assert:

```python
assert status == 503
assert json.loads(body) == {
    "schema": "mastermind.chairman_brief_error.v1",
    "error": "CHAIRMAN_BRIEF_RESPONSE_TOO_LARGE",
}
assert b"mastermind.chairman_brief.v1" not in body
```

Prove exactly `262144` encoded bytes succeeds and `262145` refuses using deterministic padding.

### Step 4: Run RED

```bash
python -m pytest tests/test_chairman_control_room_brief_server.py -q
```

### Step 5: Implement minimal server changes

Import:

```python
from control_plane import chairman_brief  # noqa: E402
```

Constants:

```python
_BRIEF_MAX_BYTES = 262_144
_BRIEF_ERROR = {
    "schema": "mastermind.chairman_brief_error.v1",
    "error": "CHAIRMAN_BRIEF_RESPONSE_TOO_LARGE",
}
```

Static map additions:

```python
"brief.html": (static_dir / "brief.html", "text/html; charset=utf-8"),
"brief.js": (static_dir / "brief.js", "application/javascript; charset=utf-8"),
"brief.css": (static_dir / "brief.css", "text/css; charset=utf-8"),
```

Path additions:

```python
"/brief": "brief.html",
"/static/brief.js": "brief.js",
"/static/brief.css": "brief.css",
```

Use one tokenized-HTML helper for `index.html` and `brief.html`, preserving `/` semantics.

Handler:

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

The success-byte measurement and actual success write must use the same encoder.

### Step 6: Run GREEN and legacy regression

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

### Step 1: Write static-shell RED tests

Parse HTML with `HTMLParser`. Required unique ids:

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

Assert:

```python
assert probe.script_srcs == ["/static/brief.js"]
assert probe.inline_scripts == 0
assert probe.style_attrs == []
assert len(probe.ids) == len(set(probe.ids))
assert "/static/control_room.js" not in html
assert "ccr-sidebar" not in html
assert "ccr-surface-dock" not in html
```

### Step 2: Implement exact HTML hierarchy

Include:

- skip link to `#brief-main`;
- compact Mastermind X brand;
- Today current-page label;
- no enabled Programs/Ask Sol in DF1;
- quiet fixed Advanced link to `/`;
- one source-state indicator;
- hero headline/subheadline;
- Chairman attention, Sol handling, and Exceptions sections;
- calm empty-state region;
- evidence drawer and scrim;
- no sidebar, global search, project counts, responsibility graph, or surface dock.

Initial copy makes no present-tense claim:

```text
Establishing the current briefing…
```

### Step 3: Implement CSS

Local variables:

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

Requirements:

- one centered primary column, maximum 1040px;
- no permanent side rail;
- one expanded attention item, later items compact;
- no horizontal overflow at required viewports;
- narrow evidence drawer becomes full-screen;
- visible focus, semantic text labels, no color-only meaning;
- reduced-motion query disables transitions/scroll animation.

### Step 4: Run and commit

```bash
python -m pytest tests/test_chairman_control_room_brief_ui.py -q -k 'shell or css'
git add \
  app/static/chairman_control/brief.html \
  app/static/chairman_control/brief.css \
  tests/test_chairman_control_room_brief_ui.py
git commit -m "feat(control-room): add sparse Chairman Today shell"
```

---

# Task 6: Render safely and expose evidence

**Files:**
- Create: `app/static/chairman_control/brief.js`
- Modify: `tests/test_chairman_control_room_brief_ui.py`

### Step 1: Write JS RED contract tests

Require:

```text
/api/brief present
X-CCR-Token present
GET + same-origin credentials
innerHTML absent
document.write absent
eval absent
new Function absent
/api/open absent
/api/bind absent
/api/unbind absent
/api/refresh-builds absent
POST absent
```

Run Node parse when present, and retain a conservative pure-Python structural-balance test for node-less CI.

### Step 2: Implement safe primitives

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

### Step 3: Map only closed headline kinds

```javascript
var HEADLINE = {
  CLEAR: "You are clear.",
  DECISIONS_REQUIRED: "A decision needs you.",
  ATTENTION_REQUIRED: "An item needs your attention.",
  PARTIAL: "This is a partial briefing.",
  UNAVAILABLE: "A current briefing cannot be established."
};
```

Subheadlines:

- CLEAR: `No Chairman intervention is currently admitted. Sol coverage and exceptions are shown below.`
- ATTENTION_REQUIRED: `The current source does not contain a complete decision packet, so no approval control is shown.`
- PARTIAL: `Some present-tense claims are withheld. Available sections remain evidence-backed.`
- UNAVAILABLE: `No present-tense company claim is being made. Advanced diagnostics remain available.`

### Step 4: Render sections

Attention:

- first item expanded;
- next two compact;
- show missing-decision disclosure;
- evidence button only;
- no action verb that implies mutation.

Sol handling:

```text
outcome
current focus
next checkpoint or "Next proof is not projected in this briefing."
No Chairman action required.
```

Exceptions:

```text
impact
repair owner
Chairman action required only when exact source says so
```

### Step 5: Evidence drawer/accessibility

- remember opener;
- open with `aria-hidden=false` and focus close;
- trap Tab/Shift+Tab;
- Escape and scrim close;
- restore opener focus;
- render evidence via `textContent`;
- Advanced link remains fixed `/`;
- network failure renders UNAVAILABLE, not an endless spinner;
- one bounded `role=status` update announces refresh result.

### Step 6: Run and commit

```bash
python -m pytest tests/test_chairman_control_room_brief_ui.py -q
node --check app/static/chairman_control/brief.js
git add app/static/chairman_control/brief.js tests/test_chairman_control_room_brief_ui.py
git commit -m "feat(control-room): render the read-only Chairman briefing"
```

If Node is absent, record that and rely on the structural check plus hosted CI; do not claim Node proof.

---

# Task 7: Complete deterministic and browser failure coverage

**Files:**
- Modify: `tests/test_chairman_brief.py`
- Modify: `tests/test_chairman_control_room_brief_server.py`
- Modify: `tests/test_chairman_control_room_brief_ui.py`

### Step 1: Cover every reachable DF1 state

1. current zero Chairman attention and zero exception;
2. one incomplete Chairman attention;
3. three visible attention items plus overflow;
4. duplicate attention identity;
5. absent work join;
6. ambiguous work join;
7. one exact current Sol-owned outcome;
8. missing source-validity proof;
9. expired/unqualified source-validity proof;
10. stale Sol responsibility;
11. blocked Sol outcome;
12. worker return waiting for Sol using `dispatch.dispatch_state`;
13. runtime unavailable with other sections usable;
14. Agent OS unavailable;
15. Executive Inbox unavailable;
16. GitHub evidence unavailable;
17. all critical sources unavailable;
18. failed refresh/historical cache;
19. source conflict;
20. effect unknown;
21. owner not established;
22. capacity blocked;
23. unsafe token text upstream;
24. absolute path upstream;
25. traceback upstream;
26. hidden-prompt/private-reasoning text upstream;
27. oversized response refusal;
28. exact response cap success;
29. corrupt source shape;
30. Programs and Ask Sol absent as enabled navigation;
31. Advanced available while brief unavailable.

A complete decision card is intentionally unreachable in DF1. Tests assert the source gap rather than fabricating authority.

### Step 2: Reuse the existing browser pattern

- in-process P0A server on OS-assigned loopback port;
- isolated browser profile;
- deterministic cached fixture documents in CI;
- explicitly supplied Chrome executable and Playwright module;
- optional in environments without exact browser dependencies, mandatory for real acceptance;
- prove browser process cleanup/absence.

### Step 3: Required viewports

```text
1440 × 900
1024 × 768
390 × 844
```

For each:

```javascript
document.documentElement.scrollWidth <= window.innerWidth
```

Also prove headline visibility, no sidebar/dock, Advanced reachability, keyboard drawer flow, focus restoration, secret/path absence from body text, reduced-motion usability, and truthful network-failure state.

### Step 4: Run focused and legacy suites

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

Then execute the exact repository-required CI command. Selected tests never substitute for the required gate.

### Step 5: Prove X1/shared assets unchanged

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

### Step 6: Commit

```bash
git add \
  tests/test_chairman_brief.py \
  tests/test_chairman_control_room_brief_server.py \
  tests/test_chairman_control_room_brief_ui.py
git commit -m "test(control-room): prove DF1 truth and responsive behavior"
```

---

# Task 8: Document canary and Advanced behavior

**Files:**
- Modify: `docs/CHAIRMAN_CONTROL_ROOM.md`

### Step 1: Add exact local journey

```bash
python3 scripts/chairman_control_room.py --port 8787
open http://127.0.0.1:8787/brief
```

Document:

- `/brief` is the read-only Chairman canary;
- `/` remains the Advanced inspector;
- `/api/brief` is token-gated, no-store, and not public;
- no action, Programs, Ask Sol, or material-change checkpoint exists in DF1;
- local token is a CSRF/browser-origin nonce, not same-user process authentication;
- partial/historical/unavailable states are truthful when sources are absent;
- raw diagnostics live in Advanced;
- process restart rebuilds cache from canonical readers;
- remote X1 is unchanged.

Rollback:

```text
Stop opening /brief and continue opening /.
```

No canonical rollback or migration exists.

### Step 2: Test and commit

```bash
python -m pytest \
  tests/test_chairman_control_room_brief_server.py \
  tests/test_chairman_control_room_brief_ui.py \
  -q
git add docs/CHAIRMAN_CONTROL_ROOM.md
git commit -m "docs(control-room): document the DF1 Today canary"
```

---

# Task 9: Produce immutable source and real-local proof receipt

**Files:**
- Create: `docs/superpowers/plans/2026-09-07-chairman-control-room-df1-implementation-receipt.md`

### Step 1: Freeze candidate identity

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

Record exact commit/tree/base/blobs. Unpushed local state is not published evidence.

### Step 2: Run real local canary on the authorized Mac

```bash
python3 scripts/chairman_control_room.py --port 8787
```

Prove:

- startup composes or enters a documented truthful failure state;
- `/brief` loads;
- `/api/brief` reads the same cached generation;
- `/` still loads Advanced;
- real raw runtime path is absent from brief JSON/DOM and translated into impact copy;
- restart/readback rebuilds process cache without changing canonical semantics;
- `/brief` triggers no provider open/bind/unbind/refresh/mutation.

### Step 3: Capture real browser evidence

Capture all three viewports with exact candidate identity and timestamp. Record screenshot paths and SHA-256 digests in the receipt, but do not commit private screenshots/host paths unless accepted evidence policy permits.

### Step 4: Witness Chairman task

Ask while the exact canary is open:

```text
Does anything on this page currently require your action: yes or no?
```

Pass:

- correct answer within ten seconds;
- no Slack, Linear, GitHub, Finder, or Advanced required;
- answer agrees with exact admitted Chairman attention;
- unavailable source is understood as withheld evidence, not zero.

Do not backfill a usability receipt without the witnessed run.

### Step 5: Final verification

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

Then run exact repository CI/security checks on immutable head.

### Step 6: Commit, publish once, and open Draft/Hold PR

```bash
git add docs/superpowers/plans/2026-09-07-chairman-control-room-df1-implementation-receipt.md
git commit -m "docs(control-room): record DF1 candidate proof"
git push -u origin sol/chairman-decision-cockpit-df1-20260907
```

PR body distinguishes:

```text
source built
hosted CI
local canary running
browser proof
witnessed Chairman task
Sol acceptance
default cutover
```

A missing row remains missing. Do not mark Ready, merge, or start DF2.

---

## 7. Worker routing and implementation order

Tasks 0–9 are sequential because reducer, server, UI, and proof share one contract/path ceiling. Do not send concurrent source writers.

Recommended route after admission:

```text
PREFERRED_AVENUE: Terra or bounded CTO Sol
WHY NOT FABLE: product/authority ambiguity is frozen; remaining work is bounded TDD, integration, and browser proof.
```

Independent reviewers operate against immutable commits and do not edit the source worktree. A finding returns to the same writer/branch/PR unless ownership/effect state requires reconciliation.

---

## 8. Acceptance checklist

### Product

- `/brief` answers act/no-act at Chairman altitude.
- No project board, percentages, giant counts, sidebar, or permanent surface rail appears.
- Sol coverage does not invent progress.
- Exceptions explain human impact first.
- Advanced is one click away and complete.

### Truth

- Missing never becomes clear/empty.
- Attention never becomes complete decision.
- Current/partial/historical/unavailable are distinct.
- Conflict/effect uncertainty remain visible.
- Completion, merge, deployment, proof, and acceptance are never inferred.

### Security

- Closed output/item allowlists pass.
- Raw paths, tracebacks, secrets, prompts, reasoning, and transcripts are absent from JSON/DOM.
- `/api/brief` uses existing loopback/Host/token/Origin/no-store gates.
- Query strings and arbitrary paths refuse.
- No POST exists.
- Response cap is enforced before write.

### No duplicate system

- Reducer is pure over cached inputs.
- No database, source reader, cache authority, queue, lifecycle, identity, scheduler, retry, watcher, or model authority was added.
- Existing owner code is consumed, not copied.
- Linear remains portfolio owner.
- Remote X1/shared inspector assets are unchanged.

### Proof

- focused tests pass;
- legacy local/remote tests pass;
- required CI/security checks pass on exact head;
- real `/brief`, `/api/brief`, and `/` readback pass;
- desktop/tablet/mobile browser evidence exists;
- restart behavior is proven;
- witnessed ten-second task passes;
- exact path and candidate identity are recorded.

---

## 9. Stop conditions

Stop and return without broadening when:

- #521 is unprotected or blocking review remains;
- #424's older H1A closure is unresolved;
- a path has another current writer;
- required data would need a second gather;
- complete decisions would need invented/model fields;
- safe copy would require exposing privileged text;
- X1/shared inspector assets would need modification;
- an eleventh path is required;
- a POST/action path appears necessary;
- protected movement changes material architecture/security/proof law;
- browser proof shows Chris still needs Advanced to answer act/no-act;
- any modifying outcome becomes uncertain.

Return:

```text
BLOCKED or DECISION_REQUEST
operation key
head/tree/base
known effect state
blocking source/identity/path
smallest safe next action
production_effect=NONE unless separately proven
```

---

## 10. Continuation handoff

Implementation return includes:

- mission and user outcome;
- current protected source and same-SHA Skillpack;
- branch/PR/head/tree/base and ten blob identities;
- focused and required tests plus hosted run/job ids;
- browser matrix and screenshot digests;
- real local process/readback result;
- current capability state;
- missing proof/disagreements;
- explicit statement that DF2/default cutover is held;
- exact requested Sol ruling;
- watcher state and same-carrier `CONTINUE`, `REQUEST_REPAIR`, or terminal `STOP` edge when reciprocal dialogue is used.

The worker boundary is one Draft/Hold DF1 PR. No merge, default-route switch, Programs, Ask Sol, action, telemetry, or successor wave begins without a new explicit Sol/Chairman edge.

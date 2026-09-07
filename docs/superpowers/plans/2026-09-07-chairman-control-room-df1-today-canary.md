---
schema: mastermind.chairman_control_room_df1_implementation_plan.v1
operation_key: chairman-control-room-df1-plan-20260907-sol-001
workstream: WS:CHAIRMAN-CONTROL-ROOM
parent_architecture_operation: chairman-control-room-decision-first-f0-20260907-sol-001
parent_architecture_pr: 521
parent_architecture_head: fdd8d9ce8085c906693914e93adc72d919156794
stack_base_before_repair: bc3d0f70eb024af82fdceac0d0cfd0fc61c0ad29
source_archaeology_pin: f9633f87bbaa22bd7864c756c8e0d1e0663899d0
current_protected_at_plan_repair: f869cb229bc99de5344e3a83292b9c53e157f879
protected_skillpack_sha: f869cb229bc99de5344e3a83292b9c53e157f879
skillpack_schema: mastermind.sol_skillpack.v1
skillpack_version: 1.0.1
minimum_bootstrap_major: 1
authorization_state: PLAN_REVIEW_REQUIRED_IMPLEMENTATION_HELD
capability_state: SPEC_ONLY
production_effect: NONE
---

# Chairman Control Room DF1 — Read-Only Today Canary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use superpowers:subagent-driven-development or superpowers:executing-plans task by task; use superpowers:test-driven-development before implementation, superpowers:systematic-debugging for unexpected behavior, and superpowers:verification-before-completion before every completion claim.

**Goal:** Deliver one real local Chairman briefing at `GET /brief` that lets Chris determine within ten seconds whether the page has complete act/no-act coverage, whether a known Chairman item requires him, what outcomes are currently assigned to Sol, and which material exceptions threaten those outcomes—while preserving the existing dense Control Room at `/` as Advanced.

**Architecture:** Add one pure `mastermind.chairman_brief.v1` reducer over the already-cached `mastermind.chairman_control_room.v1` document and existing cache/source-validity metadata. Add one fixed token-gated JSON read and three local-only static assets. Perform no second gather, no new source read, no mutation, no model call, no lifecycle inference, no new clock, and no remote-X1 change.

**Tech stack:** Python 3.11+, pytest, the existing stdlib `ThreadingHTTPServer`, dependency-free browser JavaScript/CSS, Node syntax validation when available, and the repository's existing isolated Chromium/Playwright proof pattern.

**Architecture source:** exact candidate head `fdd8d9ce8085c906693914e93adc72d919156794`, pending independent rereview/protection in PR #521.

---

## 1. Implementation admission

Chairman product direction is approved. This plan remains records-only and does not authorize code START by itself.

Every gate must be positive on one current protected revision:

1. PR #521 is independently approved and merged into protected `master`.
2. The protected design SHA and compatible same-SHA Sol Skillpack are loaded.
3. This plan is independently reviewed, rebased conceptually onto the protected design, accepted by Sol, and protected or otherwise supplied as an accepted implementation contract.
4. PR #424's incumbent/current owner has reconciled the older H1A exclusive route/static closure so it neither authorizes a competing Workstream Workroom default nor forbids the exact DF1 closure below.
5. No open PR, branch, worktree, process, or source writer owns a DF1 path.
6. Local P0A and remote X1 contracts are reread; X1 remains outside the change set.
7. One implementation writer is assigned to one branch and one PR; no concurrent writer touches the same paths.

Missing gate:

```text
BLOCKED SOURCE_OR_OWNERSHIP_PRECONDITION
production_effect=NONE
```

Do not create the implementation branch or edit source merely because the Chairman approved the product direction.

---

## 2. Canonical-owner and no-rebuild boundaries

- Executive OS remains Job / Attempt / Worker / Event lifecycle and action-admission owner.
- Agent OS remains durable workstream, decision, discovery, and handoff owner.
- GitHub remains implementation, review, CI, merge, and evidence owner.
- Linear remains the portfolio/project-management projection.
- Slack and Agent Relay remain transport/hot-state projection, never lifecycle truth.
- Existing Control Room composition/cache remains the only source acquisition DF1 consumes.
- Existing autonomy/source-validity code remains the currentness and responsibility owner.
- The brief is disposable presentation; deleting it changes no canonical fact.

DF1 must not add:

- any database, table, cache authority, event store, queue, scheduler, retry ledger, wake/dispatch path, lifecycle, identity registry, source reader, background gather loop, or analytics store;
- any POST endpoint, approval, hold, continue, stop, dispatch, merge, retry, or mutation control;
- any Linear, Slack, GitHub, Agent OS, Executive OS, provider, browser-profile, account, or credential write;
- any model invocation or model-authored priority, owner, decision, recommendation, status, closure, or suppression rule;
- any second freshness clock, source-validity proof, attention classifier, decision classifier, autonomy classifier, watcher classifier, or effect-reconciliation owner;
- Programs, Ask Sol, material-change checkpointing, default cutover, or remote X1 changes.

Truth laws:

- missing is not empty;
- incomplete zero is never clear;
- known items remain visible under incomplete coverage, with totals withheld;
- failed refresh makes the retained cache historical;
- attention is not a complete decision;
- `Sol is handling` means current organizational accountability, never provider execution;
- bindings/tabs/windows/processes never prove cognition;
- CI, merge, installation, deployment, proof, and acceptance remain distinct.

---

## 3. Existing source bindings

Reread these owners at the admitted implementation base:

| Path | DF1 use | Permission |
|---|---|---|
| `control_plane/chairman_control_room.py` | canonical cross-owner composition | read only |
| `control_plane/autonomy_control_room_projection.py` | responsibility, owner, dispatch, placement, freshness projection | read only |
| `control_plane/executive_inbox.py` | Chairman/CEO/COO attention projection | read only |
| `scripts/chairman_control_room.py` | P0A cache and local HTTP server | narrow additive edit |
| `app/static/chairman_control/index.html` | current Advanced inspector | read only |
| `app/static/chairman_control/control_room.js` | shared local/X1 inspector client | read only |
| `app/static/chairman_control/control_room.css` | shared local/X1 inspector CSS | read only |
| `tests/test_chairman_control_room_server.py` | existing local server harness | read only |
| `tests/test_chairman_control_room_ui_x1.py` | safe DOM/browser proof pattern | read only |
| `control_plane/chairman_control_room_remote.py` | remote X1 projection/release closure | read only |
| `scripts/chairman_control_room_remote.py` | remote X1 server | read only |
| `app/static/chairman_control/remote.html` | remote X1 entry | read only |
| `docs/CHAIRMAN_CONTROL_ROOM.md` | operator documentation | narrow additive edit |

Current P0A cache envelope:

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

Load-bearing shapes:

```text
control_room.schema
control_room.generated_at
control_room.sources
control_room.degraded[]
control_room.attention.chairman[]
control_room.work[]
control_room.autonomy.responsibilities[]
control_room.autonomy.unmapped_responsibilities[]
source_validity.schema
source_validity.cards[].responsibility_ref
source_validity.cards[].root_job_id
source_validity.cards[].components.card.state
```

Current dispatch field:

```text
responsibility.dispatch.dispatch_state
```

Never use `responsibility.dispatch.state`.

---

## 4. Exact implementation path ceiling

Future implementation may touch exactly ten paths.

Create:

1. `control_plane/chairman_brief.py`
2. `app/static/chairman_control/brief.html`
3. `app/static/chairman_control/brief.js`
4. `app/static/chairman_control/brief.css`
5. `tests/test_chairman_brief.py`
6. `tests/test_chairman_control_room_brief_server.py`
7. `tests/test_chairman_control_room_brief_ui.py`
8. `docs/superpowers/plans/2026-09-07-chairman-control-room-df1-implementation-receipt.md`

Modify:

9. `scripts/chairman_control_room.py`
10. `docs/CHAIRMAN_CONTROL_ROOM.md`

Any eleventh path:

```text
DECISION_REQUEST PATH_BOUNDARY_REQUIRED
production_effect=NONE
```

Do not modify `index.html`, `control_room.js`, or `control_room.css`; they remain the existing inspector/shared X1 assets.

Recommended implementation branch after admission:

```text
sol/chairman-decision-cockpit-df1-20260907
```

Return as:

```text
DRAFT / HOLD-FOR-SOL / BUILT_NOT_PROVEN
```

---

## 5. Fixed local route and response closure

Add exactly:

```text
GET /brief
GET /api/brief
GET /static/brief.js
GET /static/brief.css
```

Rules:

- `/brief` serves token-injected `brief.html` with the same CSP used by `/`.
- `/api/brief` requires existing loopback, Host, exact `X-CCR-Token`, matching Origin when present, and `Cache-Control: no-store` gates.
- `/brief` and `/api/brief` reject every non-empty query string.
- `/api/brief` reads one `_cached_state_snapshot`; no synchronous composition, capability census, filesystem discovery, subprocess, provider inspection, or network call.
- The existing single-flight stale-cache check may run, but the request returns the retained snapshot immediately.
- Success JSON is canonical encoded and measured before writing.
- Maximum success body: exactly `262144` bytes.
- Larger output returns HTTP `503` and exactly:

```json
{
  "schema": "mastermind.chairman_brief_error.v1",
  "error": "CHAIRMAN_BRIEF_RESPONSE_TOO_LARGE"
}
```

- No partial success bytes are written.
- No new POST route exists.
- `/` remains Advanced during DF1.
- X1 route/static/package/install closure is byte-unchanged.

---

## 6. Frozen reducer contract

### 6.1 Pure entry point

```python
def compose_chairman_brief(
    *,
    control_room: Mapping[str, Any] | None,
    source_validity: Mapping[str, Any] | None,
    composed_at: str | None,
    refresh_in_flight: bool,
    state_refresh_error: str | None,
) -> dict[str, Any]:
    """Pure deterministic read-only Chairman briefing."""
```

No I/O, environment, clock, randomness, mutation, provider inspection, source rejoin, or caller mutation.

### 6.2 Closed top-level keys

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
    "programs",
    "feature_gates",
})
```

### 6.3 Closed vocabularies

```python
READ_STATES = frozenset({"CURRENT", "PARTIAL", "HISTORICAL", "UNAVAILABLE"})
SECTION_STATES = frozenset({"AVAILABLE", "EMPTY", "PARTIAL", "HISTORICAL", "UNAVAILABLE"})
COVERAGE_STATES = frozenset({
    "COMPLETE", "INCOMPLETE", "HISTORICAL_ONLY", "NOT_PROJECTED", "NOT_APPLICABLE"
})
HEADLINE_KINDS = frozenset({
    "CLEAR", "DECISIONS_REQUIRED", "ATTENTION_REQUIRED", "PARTIAL", "UNAVAILABLE"
})
HEADLINE_SCOPES = frozenset({"ATTENTION_AND_DECISIONS", "ATTENTION_ONLY", "NONE"})
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

### 6.4 Section envelope

```json
{
  "state": "AVAILABLE",
  "coverage": "COMPLETE",
  "reason_codes": [],
  "total_count": 0,
  "items": [],
  "overflow_count": 0
}
```

Invariants:

- complete coverage: integer total and overflow;
- incomplete coverage: both null, known items allowed;
- historical-only: both null, every item labeled historical;
- not projected: both null;
- `EMPTY` only with complete coverage and exact total zero.

### 6.5 Exact top-level output example

```json
{
  "schema": "mastermind.chairman_brief.v1",
  "generated_at": "2026-09-07T00:00:00Z",
  "source": {
    "control_room_schema": "mastermind.chairman_control_room.v1",
    "control_room_generated_at": "2026-09-07T00:00:00Z",
    "control_room_digest": "sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
    "composed_at": "2026-09-07T00:00:01Z",
    "source_validity_schema": "mastermind.control_room_source_validity.v1",
    "coverage": []
  },
  "read_state": {
    "state": "CURRENT",
    "reason_codes": [],
    "usable_sections": ["attention", "sol_handling", "exceptions"]
  },
  "headline": {
    "kind": "CLEAR",
    "scope": "ATTENTION_ONLY",
    "complete_decision_count": null,
    "chairman_attention_count": 0,
    "sol_accountability_count": 3,
    "exception_count": 1
  },
  "decisions": {
    "state": "UNAVAILABLE",
    "coverage": "NOT_PROJECTED",
    "reason_codes": ["DECISION_PACKET_SOURCE_NOT_PROJECTED"],
    "total_count": null,
    "items": [],
    "overflow_count": null
  },
  "attention": {
    "state": "EMPTY",
    "coverage": "COMPLETE",
    "reason_codes": [],
    "total_count": 0,
    "items": [],
    "overflow_count": 0
  },
  "changes": {
    "state": "UNAVAILABLE",
    "coverage": "NOT_PROJECTED",
    "reason_codes": ["MATERIAL_CHANGE_CHECKPOINT_NOT_BUILT_IN_DF1"],
    "total_count": null,
    "items": [],
    "overflow_count": null
  },
  "sol_handling": {
    "state": "AVAILABLE",
    "coverage": "COMPLETE",
    "reason_codes": [],
    "total_count": 3,
    "items": [],
    "overflow_count": 0
  },
  "exceptions": {
    "state": "AVAILABLE",
    "coverage": "COMPLETE",
    "reason_codes": [],
    "total_count": 1,
    "items": [],
    "overflow_count": 0
  },
  "programs": {
    "state": "UNAVAILABLE",
    "coverage": "NOT_PROJECTED",
    "reason_codes": ["PROGRAMS_NOT_BUILT_IN_DF1"],
    "total_count": null,
    "items": [],
    "overflow_count": null
  },
  "feature_gates": {
    "advanced": "AVAILABLE",
    "programs": "UNAVAILABLE",
    "ask_sol": "UNAVAILABLE",
    "actions": "READ_ONLY"
  }
}
```

### 6.6 Canonical digest

```python
def _digest(value: Mapping[str, Any]) -> str | None:
    try:
        payload = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError):
        return None
    return "sha256:" + hashlib.sha256(payload).hexdigest()
```

Hash the unmodified source document; never normalize it before digesting.

---

## 7. Source coverage and headline algorithm

### 7.1 Source families

Closed source-coverage rows:

```text
CORE_DOCUMENT
CHAIRMAN_ATTENTION
EXECUTIVE_RUNTIME
AGENT_OS
AUTONOMY_VALIDITY
GITHUB_EVIDENCE
DECISION_PACKETS
PROGRAMS_SOURCE
ASK_SOL_SOURCE
ADVANCED_NAVIGATION
```

Each row contains only:

```text
source
state
coverage
reason_codes[]
affects[]
```

No raw error string is copied.

### 7.2 Current DF1 source tests

```text
CORE_DOCUMENT current:
  control_room is mapping
  control_room.schema == mastermind.chairman_control_room.v1
  generated_at safe
  state_refresh_error is null

CHAIRMAN_ATTENTION complete/current:
  CORE_DOCUMENT current
  sources.executive_inbox_schema == mastermind.executive_inbox.v2
  sources.runtime_db_present is true
  no degraded prefix executive_inbox
  no degraded prefix executive_runtime
  attention is mapping and chairman is list

EXECUTIVE_RUNTIME current:
  sources.runtime_db_present is true
  no degraded prefix executive_runtime

AGENT_OS current:
  sources.agent_os_state_schema == agent_os_state.v1
  no degraded prefix agent_os_state or boot_packet

GITHUB_EVIDENCE current:
  sources.active_builds_schema == project_active_builds.v1
  no degraded prefix active_builds

AUTONOMY_VALIDITY current for one responsibility:
  responsibility query_status == ok
  responsibility freshness == current
  exactly one source_validity card matches responsibility_ref + root_job_id
  matched components.card.state == current
```

Parse only the degraded prefix before the first colon. Discard the suffix.

`refresh_in_flight=true` with no error does not make the retained snapshot historical; it remains the last successfully composed generation, with an explicit refresh-in-flight source reason. `state_refresh_error` makes it historical.

### 7.3 Total headline precedence

Apply in order:

1. core invalid/absent and no valid retained document → `UNAVAILABLE`, scope `NONE`, admission counts null;
2. retained document with refresh error or admission evidence historical → `PARTIAL`, read state `HISTORICAL`, counts null;
3. conflict in an admission-capable source → `PARTIAL`, counts null, known items visible;
4. incomplete/unavailable Chairman-attention coverage → `PARTIAL`, counts null, known items visible;
5. future complete decision packets >0 with complete attention coverage → `DECISIONS_REQUIRED`, `ATTENTION_AND_DECISIONS`;
6. current Chairman attention >0 with complete attention coverage and decision packets not projected → `ATTENTION_REQUIRED`, `ATTENTION_ONLY`;
7. current Chairman attention >0 and future decision coverage complete/zero → `ATTENTION_REQUIRED`, `ATTENTION_AND_DECISIONS`;
8. attention complete/zero and decisions not projected → `CLEAR`, `ATTENTION_ONLY`, attention count 0, decision count null;
9. attention and decision coverage complete/zero → `CLEAR`, `ATTENTION_AND_DECISIONS`, exact zero counts.

DF1 never emits complete decisions. `decisions.coverage=NOT_PROJECTED` always.

Optional Agent OS/GitHub/navigation failure does not demote a complete Chairman-attention answer, but makes dependent sections partial/unavailable and adds impact exceptions. No partial copy may say all clear, nothing needs you, or Sol handles everything else.

---

## 8. Closed item contracts

### 8.1 Chairman attention item

```text
attention_id
kind
summary
work_ref
source_owner
source_time
observed_at
freshness_state
missing_decision_fields[]
evidence_refs[]
advanced_ref
```

Rules:

- stable safe `attention_id` required;
- exact join only through one `work[].attention_ids[]` claim;
- zero claims → `work_ref=null`;
- multiple claims → source conflict, no winner;
- summary only from safe source `summary` or `reason`;
- `control_room.generated_at` is observed time, never source time;
- current attention shows one expanded plus two compact; complete coverage gets exact overflow, incomplete gets null total/overflow;
- `advanced_ref` is fixed `/#today`;
- no approval/control.

Current missing decision fields:

```text
authority_required
closed_options
consequence_of_acting
consequence_of_waiting
reversibility
recommendation_provenance
```

### 8.2 Decisions

DF1 intentionally outputs no decision items. It does not add a fixture-only decision input. Future complete decision support must consume the architecture's closed option/recommendation/evidence contracts from an accepted companion projection.

Tests must assert:

```text
decisions.coverage == NOT_PROJECTED
decisions.total_count is null
decisions.items == []
headline.complete_decision_count is null
```

### 8.3 Sol organizational accountability item

```text
item_id
work_ref
outcome
recorded_next_action
accountable_owner
coverage_meaning
provider_execution_state
why_it_matters
next_checkpoint
chairman_action_required
freshness_state
evidence_refs[]
source_time
observed_at
advanced_ref
```

Exact constants:

```text
accountable_owner=SOL
coverage_meaning=ORGANIZATIONAL_ACCOUNTABILITY
provider_execution_state=NOT_ASSERTED
chairman_action_required=false
```

Typed unavailable fields:

```json
"why_it_matters": {"state": "NOT_PROJECTED", "value": null},
"next_checkpoint": {"state": "NOT_PROJECTED", "value": null}
```

Admission requires:

```text
responsibility.responsibility_ref == work.work_ref
responsibility.accountable_seat == ceo
responsibility.query_status == ok
responsibility.freshness == current
matching source_validity components.card.state == current
responsibility.placement_state.value != EFFECT_UNKNOWN
responsibility.dispatch.dispatch_state not in {RETURNED, EFFECT_UNKNOWN}
work has no Chairman attention
work has no disagreement
Agent OS next_action safe/nonblank
Agent OS status/state not blocked/done/killed
unmet_dependencies empty
exact responsibility identity unique
```

No matching validity proof means currentness unproven. Exclude the row from reassuring coverage, mark section incomplete, and add fixed source-currentness reason/exception.

Sort exact work ref; show six; exact overflow only under complete coverage.

### 8.4 Exception item

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

| Fact | Kind | Fixed impact |
|---|---|---|
| `state_refresh_error` | `SOURCE_UNAVAILABLE` | `The latest refresh failed. Cached evidence is historical until a successful composition replaces it.` |
| runtime unavailable | `SOURCE_UNAVAILABLE` | `Current execution claims are withheld. Organizational and implementation evidence may remain usable.` |
| Inbox unavailable | `SOURCE_UNAVAILABLE` | `Current Chairman attention cannot be established from Executive evidence.` |
| Agent OS unavailable | `SOURCE_UNAVAILABLE` | `Current outcomes, owners, and next actions cannot be established from Agent OS.` |
| active builds unavailable | `SOURCE_UNAVAILABLE` | `Current implementation and proof changes cannot be established from GitHub evidence.` |
| work disagreement | `SOURCE_CONFLICT` | `Canonical and projected evidence disagree. No winner is selected in this briefing.` |
| exact blocked state/dependency | `WORK_BLOCKED` | `This outcome cannot advance through its recorded next step.` |
| exact failed Executive job | `WORK_BLOCKED` | `A recorded Executive job failed. The next safe action requires inspection.` |
| CEO responsibility dispatch `RETURNED` | `WORK_WAITING` | `A worker return is waiting for Sol adjudication.` |
| exact placement/dispatch `EFFECT_UNKNOWN` | `EFFECT_UNKNOWN` | `A prior operation may have taken effect. No retry or carrier change is permitted until reconciled.` |
| exact `WAITING_CAPACITY` | `CAPACITY_BLOCKED` | `The operation is waiting for an eligible capacity assignment.` |
| unmapped responsibility | `OWNER_NOT_ESTABLISHED` | `An accountable operator cannot be established from the current owner mapping.` |
| exact source-owned proof-missing token | `PROOF_MISSING` | `Implementation evidence exists, but the required accepted proof is not present.` |
| exact source-owned production-regression token | `PRODUCTION_REGRESSION` | `A previously usable production journey is reported as regressed.` |

Do not infer proof missing from an open PR or production regression from failed CI text.

Closed repair owners:

```text
EXECUTIVE_OS
AGENT_OS
GITHUB_EVIDENCE
SOL
CAPACITY_OWNER
UNKNOWN
```

Chairman action is true only when exact current Chairman attention joins the same work identity.

### 8.5 Evidence reference

```text
owner
ref
field
source_revision
source_time
observed_at
freshness_state
```

Allowed owners:

```text
EXECUTIVE_OS
EXECUTIVE_INBOX
AGENT_OS
GITHUB
AUTONOMY_PROJECTION
CONTROL_ROOM_CACHE
SOURCE_VALIDITY
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

No upstream URL is copied. Maximum 32 refs per item. Deduplicate exact tuples only.

### 8.6 Sanitizer

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

Reject absolute paths:

```text
/Users/
/home/
/private/
/var/
/opt/
/tmp/
Windows drive-letter paths
```

Unsafe replacement:

```text
Source-owned detail is withheld from the default briefing. Inspect Advanced evidence.
```

Never reveal the matching rule.

---

# Task 0: Admit one clean implementation carrier

**Files:** none.

### Step 1: Re-pin source/procedure

```bash
git fetch origin master
git rev-parse origin/master
git show origin/master:docs/sol_skills/INDEX.md | sed -n '1,100p'
```

Record protected SHA and same-SHA Skillpack schema/version/bootstrap.

### Step 2: Verify design/plan protection

```bash
gh pr view 521 --repo mastermindx-market-intelligence/Mastermind \
  --json state,isDraft,mergedAt,mergeCommit,reviewDecision,headRefOid
```

Require merged, non-draft, no blocking review, protected design present.

Read the accepted version of this plan. Do not implement from the mutable branch if it differs.

### Step 3: Reconcile PR #424

```bash
gh pr view 424 --repo mastermindx-market-intelligence/Mastermind \
  --json state,isDraft,mergedAt,headRefOid,reviewDecision,files,comments
```

Require an immutable current-owner receipt that:

- retains useful H0 archaeology;
- holds/supersedes the old H1A default Workstream Workroom;
- removes the old exclusive `/api/hub/workstream/chairman-control-room` + `hub_workroom.*` future closure;
- accepts `/brief`, `/api/brief`, and `brief.*` as the DF1 closure;
- confirms no competing H1A implementation may merge behind DF1.

Do not edit #424's files from DF1.

### Step 4: Census all ten paths

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
print(*sorted(paths), sep="\n")
PY

git worktree list --porcelain
gh pr list --repo mastermindx-market-intelligence/Mastermind --state open --limit 100 \
  --json number,headRefName,headRefOid,title,files
```

Include rename history and process/file-handle ownership when available. Stop on unresolved writer ownership.

### Step 5: Create isolated worktree only after gates pass

```bash
git worktree add \
  ../Mastermind-chairman-decision-cockpit-df1-20260907 \
  -b sol/chairman-decision-cockpit-df1-20260907 \
  origin/master
cd ../Mastermind-chairman-decision-cockpit-df1-20260907
git status --short --branch
```

Expected: clean, exact current protected base.

---

# Task 1: Implement pure contract/read-state ruler red-first

**Files:**
- Create `tests/test_chairman_brief.py`
- Create `control_plane/chairman_brief.py`

### Step 1: RED closed-contract tests

Use an explicit sentinel so `control_room=None` means absent.

Minimum tests:

```python
def test_contract_is_closed_and_deterministic():
    one = _compose()
    two = _compose()
    assert set(one) == brief.OUTPUT_KEYS
    assert one == two
    assert json.dumps(one, sort_keys=True, allow_nan=False) == json.dumps(
        two, sort_keys=True, allow_nan=False
    )


def test_absent_control_room_is_unavailable_not_clear():
    out = _compose(control_room=None)
    assert out["read_state"]["state"] == "UNAVAILABLE"
    assert out["headline"]["kind"] == "UNAVAILABLE"
    assert out["headline"]["chairman_attention_count"] is None


def test_refresh_failure_is_historical_and_raw_error_is_absent():
    out = _compose(state_refresh_error="raw /Users/private/runtime failure")
    encoded = json.dumps(out, sort_keys=True)
    assert out["read_state"]["state"] == "HISTORICAL"
    assert out["headline"]["kind"] == "PARTIAL"
    assert "/Users/private/runtime" not in encoded
```

### Step 2: RED total truth-table tests

One test per §7.3 row:

- invalid core;
- retained historical;
- admission conflict;
- incomplete coverage with known attention;
- incomplete zero without clear;
- complete attention nonzero, decisions not projected;
- complete attention zero, decisions not projected;
- optional GitHub/Agent OS/navigation failure that does not demote complete attention but degrades dependent section.

Assert count nullability and headline scope exactly.

### Step 3: Implement constants, digest, shape guards, source coverage, and headline

Required constants:

```python
SCHEMA = "mastermind.chairman_brief.v1"
CONTROL_ROOM_SCHEMA = "mastermind.chairman_control_room.v1"
SOURCE_VALIDITY_SCHEMA = "mastermind.control_room_source_validity.v1"
MAX_ATTENTION_ITEMS = 3
MAX_SOL_HANDLING_ITEMS = 6
MAX_EXCEPTION_ITEMS = 6
```

Never raise on malformed upstream source. Return a complete unavailable/partial document.

### Step 4: Hostile inputs

Wrong schemas, non-mappings, malformed lists, duplicate ids, invalid validity shape, NaN/unserializable input, non-boolean refresh flag, and source-insensitive reorderings.

### Step 5: GREEN and commit

```bash
python -m pytest tests/test_chairman_brief.py -q
git add control_plane/chairman_brief.py tests/test_chairman_brief.py
git commit -m "feat(control-room): add pure Chairman brief contract"
```

---

# Task 2: Project Chairman attention without manufacturing decisions

**Files:** modify reducer tests/module.

### Step 1: RED current attention fixture

Assert:

```python
out = _compose(control_room=doc_with_one_chairman_item)
assert out["headline"]["kind"] == "ATTENTION_REQUIRED"
assert out["headline"]["scope"] == "ATTENTION_ONLY"
assert out["decisions"]["coverage"] == "NOT_PROJECTED"
assert out["decisions"]["total_count"] is None
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

### Step 2: RED exact identity/conflict cases

- one exact attention claim → work ref;
- no claim → null work ref;
- multiple claims → source conflict/no winner;
- duplicate attention id → partial/conflict;
- non-Chairman target excluded;
- invalid stable id cannot render current;
- unsafe summary replaced;
- evidence reduced to closed refs;
- incomplete admission coverage keeps known item but total/overflow null.

### Step 3: Implement exact claims

```python
def _attention_claims(work_rows: Sequence[Mapping[str, Any]]) -> dict[str, list[str]]:
    claims: dict[str, list[str]] = {}
    for work in work_rows:
        ref = _safe_work_ref(work.get("work_ref"))
        if ref is None:
            continue
        for attention_id in _safe_string_list(work.get("attention_ids")):
            claims.setdefault(attention_id, []).append(ref)
    return {key: sorted(set(values)) for key, values in claims.items()}
```

Preserve source order then stable id; no severity score.

### Step 4: GREEN and commit

```bash
python -m pytest tests/test_chairman_brief.py -q
git add control_plane/chairman_brief.py tests/test_chairman_brief.py
git commit -m "feat(control-room): project truthful Chairman attention"
```

---

# Task 3: Add source-qualified Sol accountability and fixed exceptions

**Files:** modify reducer tests/module.

### Step 1: RED exact Sol coverage fixture

Use:

```python
responsibility = {
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
}
validity = {
  "schema": "mastermind.control_room_source_validity.v1",
  "publication_seq": 1,
  "cards": [{
    "responsibility_ref": "WS:EXAMPLE",
    "root_job_id": None,
    "components": {"card": {"state": "current", "proof_ref": "a" * 64}},
  }],
}
```

Assert exact output constants and typed unavailability:

```python
item = out["sol_handling"]["items"][0]
assert item["accountable_owner"] == "SOL"
assert item["coverage_meaning"] == "ORGANIZATIONAL_ACCOUNTABILITY"
assert item["provider_execution_state"] == "NOT_ASSERTED"
assert item["recorded_next_action"] == "Prove one real user-visible result."
assert item["why_it_matters"] == {"state": "NOT_PROJECTED", "value": None}
assert item["next_checkpoint"] == {"state": "NOT_PROJECTED", "value": None}
```

Negative cases:

- non-CEO seat;
- stale/unknown freshness;
- absent/expired/unqualified validity;
- validity ref/root mismatch;
- refused/degraded query;
- Chairman attention on work;
- disagreement;
- blocked/done/killed state;
- unmet dependency;
- dispatch `RETURNED` or `EFFECT_UNKNOWN`;
- placement `EFFECT_UNKNOWN`;
- unsafe/missing next action;
- duplicate responsibility;
- similar unequal refs.

### Step 2: RED exception matrix

Prove every §8.4 admission. Include raw-path replacement:

```python
assert "/Users/private/runtime.sqlite3" not in json.dumps(out)
assert runtime_item["impact"] == (
  "Current execution claims are withheld. Organizational and "
  "implementation evidence may remain usable."
)
```

Also prove:

- effect unknown exact-token only;
- waiting capacity exact-token only;
- no proof-missing from open PR alone;
- no production-regression from failed CI text alone;
- fixed sort order then work ref/stable id;
- exact semantic dedupe only;
- six visible plus exact/null overflow according to coverage.

### Step 3: Implement stable ids, templates, sanitizer, closed evidence

```python
def _stable_id(prefix: str, *parts: str | None) -> str:
    material = "|".join([SCHEMA, prefix, *(part or "" for part in parts)])
    return prefix + "-" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]
```

Parse only degraded source prefix; discard suffix.

### Step 4: Anti-authority AST test

The pure module cannot import/call:

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
surface binding writers
```

### Step 5: GREEN and commit

```bash
python -m pytest tests/test_chairman_brief.py -q
git add control_plane/chairman_brief.py tests/test_chairman_brief.py
git commit -m "feat(control-room): compress Sol accountability and exceptions"
```

---

# Task 4: Add local read routes without second gather

**Files:**
- Create `tests/test_chairman_control_room_brief_server.py`
- Modify `scripts/chairman_control_room.py`

### Step 1: Reuse existing server harness

```python
from test_chairman_control_room_server import (
    _auth_headers,
    _get,
    _make_config,
    _running_server,
)
```

Do not clone a second harness.

### Step 2: RED route/security tests

Prove:

- `/brief` gets CSP and token injection;
- `/api/brief` rejects missing/bad token, Host, Origin, external peer;
- response is no-store;
- non-empty query strings reject;
- unknown static assets 404;
- `POST /api/brief` 404s;
- existing `/`, `/api/state`, and POST behavior unchanged.

### Step 3: RED cache/gather tests

Call counters prove:

- zero synchronous `_compose_state_doc`;
- zero capability census;
- one `_cached_state_snapshot` generation per response;
- existing single-flight refresh remains nonblocking;
- reducer not called after auth failure.

### Step 4: RED response cap

Exactly 262144 encoded bytes succeed; 262145 refuses with fixed 503 body. No success-schema bytes appear in refusal.

### Step 5: Minimal implementation

Add import, constants, static mappings, `/brief` tokenized HTML, and `_handle_brief`:

```python
def _handle_brief(self) -> None:
    config = self.server.config
    _maybe_start_background_refresh(config)
    snapshot = _cached_state_snapshot(config)
    payload = chairman_brief.compose_chairman_brief(
        control_room=snapshot["doc"],
        source_validity=snapshot["source_validity"],
        composed_at=snapshot["composed_at"],
        refresh_in_flight=snapshot["refresh_in_flight"],
        state_refresh_error=snapshot["state_refresh_error"],
    )
    encoded = _canonical_json_bytes(payload)
    if len(encoded) > _BRIEF_MAX_BYTES:
        return self._write_canonical_json(503, _BRIEF_ERROR, no_store=True)
    self._write(200, encoded, content_type="application/json; charset=utf-8", no_store=True)
```

The exact encoder used to measure is the encoder used to write.

### Step 6: GREEN and commit

```bash
python -m pytest \
  tests/test_chairman_control_room_brief_server.py \
  tests/test_chairman_control_room_server.py -q
git add scripts/chairman_control_room.py tests/test_chairman_control_room_brief_server.py
git commit -m "feat(control-room): expose fixed read-only Chairman brief"
```

---

# Task 5: Build sparse Today shell

**Files:**
- Create `brief.html`
- Create `brief.css`
- Create `tests/test_chairman_control_room_brief_ui.py`

### Step 1: RED static shell tests

Require unique IDs:

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

Require exactly `/static/brief.js`, no inline scripts/styles, no old JS, sidebar, or surface dock.

### Step 2: Implement HTML

- skip link;
- compact brand;
- Today current label;
- no enabled Programs/Ask Sol;
- fixed Advanced link `/`;
- coverage/source indicator;
- headline/subheadline;
- attention, Sol accountability, exceptions;
- calm empty state;
- evidence drawer/scrim;
- no global project board or giant counts.

Initial copy:

```text
Establishing the current briefing…
```

### Step 3: Implement CSS

One centered column, max 1040px; no side rail; one expanded attention item; mobile full-screen drawer; visible focus; reduced motion; no horizontal overflow; no color-only meaning.

### Step 4: GREEN and commit

```bash
python -m pytest tests/test_chairman_control_room_brief_ui.py -q -k 'shell or css'
git add app/static/chairman_control/brief.html app/static/chairman_control/brief.css \
  tests/test_chairman_control_room_brief_ui.py
git commit -m "feat(control-room): add sparse Chairman Today shell"
```

---

# Task 6: Render safe coverage-qualified UI

**Files:**
- Create `brief.js`
- Modify UI tests

### Step 1: RED JS contract

Require `/api/brief`, `X-CCR-Token`, GET, same-origin credentials. Forbid `innerHTML`, `document.write`, `eval`, `new Function`, POST, and all mutation endpoints.

### Step 2: Safe DOM primitives

Use strict IIFE, `createElement`, `textContent`, explicit closed-key reads, and no source HTML.

### Step 3: Headline mapping

Closed kinds/scopes only. Copy must distinguish:

- complete attention+decision clear;
- attention-only clear with decision packets not projected;
- known current attention;
- partial known subset with totals withheld;
- historical retained evidence;
- unavailable act/no-act answer.

Never render `everything else`, `all clear`, or broad zero under partial/attention-only coverage.

### Step 4: Section rendering

Attention: one expanded, two compact, exact/null overflow semantics, missing-decision disclosure.

Sol accountability:

```text
outcome
recorded next action
Sol owns the current organizational next move.
Provider execution is not asserted.
```

Do not render why-it-matters/next-checkpoint as if available.

Exceptions: fixed impact, repair owner, exact Chairman-action flag.

### Step 5: Evidence/accessibility

Remember opener, focus close, trap Tab, Escape/scrim close, restore focus, render evidence with textContent, keep Advanced fixed `/`, truthful network failure, one bounded `role=status` announcement.

### Step 6: GREEN and commit

```bash
python -m pytest tests/test_chairman_control_room_brief_ui.py -q
node --check app/static/chairman_control/brief.js
git add app/static/chairman_control/brief.js tests/test_chairman_control_room_brief_ui.py
git commit -m "feat(control-room): render coverage-qualified Chairman briefing"
```

Record Node unavailable rather than claiming proof if absent.

---

# Task 7: Complete deterministic/browser matrix

**Files:** modify all DF1 tests.

Required cases:

1. complete attention zero + decision not projected;
2. one current incomplete attention item;
3. three visible plus exact overflow;
4. incomplete known subset + null total/overflow;
5. incomplete zero + no clear;
6. duplicate attention id;
7. absent/ambiguous work join;
8. exact current Sol accountability;
9. missing/expired/unqualified source-validity proof;
10. stale/refused responsibility;
11. blocked Sol outcome;
12. worker return via `dispatch.dispatch_state`;
13. runtime unavailable with independent sections usable;
14. Agent OS unavailable;
15. Inbox unavailable;
16. GitHub unavailable without demoting complete attention;
17. all admission sources unavailable;
18. refresh failure/historical cache;
19. source conflict;
20. effect unknown;
21. owner not established;
22. capacity blocked;
23. secret/token text upstream;
24. absolute path;
25. traceback;
26. hidden prompt/private reasoning/transcript;
27. exact cap success/overflow refusal;
28. corrupt shape;
29. Programs/Ask Sol gated;
30. Advanced available while Today partial/unavailable.

Complete decision support is intentionally unreachable in DF1. Assert the gap.

Browser viewports:

```text
1440 × 900
1024 × 768
390 × 844
```

Assert no horizontal overflow, headline visible, no sidebar/dock, Advanced reachable, keyboard drawer, focus restoration, sensitive text absent, reduced-motion usability, truthful network failure, and browser process cleanup.

Run:

```bash
python -m pytest tests/test_chairman_brief.py \
  tests/test_chairman_control_room_brief_server.py \
  tests/test_chairman_control_room_brief_ui.py -q

python -m pytest tests/test_chairman_control_room.py \
  tests/test_chairman_control_room_server.py \
  tests/test_chairman_control_room_ui_x1.py \
  tests/test_chairman_control_room_remote.py -q
```

Then exact repository-required CI command.

Prove unchanged:

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

Commit proof tests.

---

# Task 8: Document canary and rollback

**File:** modify `docs/CHAIRMAN_CONTROL_ROOM.md`.

Document:

```bash
python3 scripts/chairman_control_room.py --port 8787
open http://127.0.0.1:8787/brief
```

State:

- `/brief` is read-only canary;
- `/` is Advanced;
- `/api/brief` is token-gated/no-store/local, not public;
- DF1 has no actions, complete decisions, Programs, Ask Sol, or change checkpoint;
- token is CSRF/browser-origin capability, not same-user-process authentication;
- partial/historical/unavailable is expected when sources are missing;
- raw diagnostics remain in Advanced;
- restart rebuilds cache;
- X1 unchanged.

Rollback: stop opening `/brief`; continue using `/`. No canonical migration/rollback exists.

Test and commit.

---

# Task 9: Produce immutable source and real-local proof receipt

**File:** create DF1 implementation receipt.

Freeze commit/tree/base/blobs and ten-path diff. Run exact focused, legacy, repository, and security tests.

On authorized Chairman Mac:

- run exact candidate server;
- prove `/brief`, `/api/brief`, and `/`;
- prove real raw runtime path absent from brief JSON/DOM;
- prove no provider open/bind/unbind/refresh/mutation;
- restart/read back;
- capture desktop/tablet/mobile screenshots with SHA-256 receipts;
- witness Chris answer:

```text
Can this page establish whether anything currently requires your action? If yes, what; if no, is the answer complete or coverage-limited?
```

Pass within ten seconds without Slack, Linear, GitHub, Finder, or Advanced. Do not backfill the receipt.

Publish one Draft/Hold implementation PR. Distinguish source, CI, local run, browser proof, witnessed task, Sol acceptance, and default cutover. Missing remains missing. Do not merge or start DF2.

---

## 9. Worker routing

Sequential single writer: reducer, server, UI, and proof share one contract/path ceiling.

```text
PREFERRED_AVENUE: Terra or bounded CTO Sol
WHY NOT FABLE: product/authority ambiguity is frozen; remaining work is bounded TDD, integration, and browser proof.
```

Independent reviewers inspect immutable commits and do not edit the writer worktree. Findings return to the same branch/PR unless ownership/effect state requires reconciliation.

---

## 10. Acceptance checklist

Product:

- coverage-qualified act/no-act answer;
- no project board/percent/giant counts/sidebar/rail;
- known partial items visible without false totals;
- Sol accountability does not imply provider execution;
- impact-first exceptions;
- Advanced complete and one click away.

Truth:

- missing not empty;
- incomplete zero not clear;
- decisions explicitly not projected;
- current/partial/historical/unavailable distinct;
- conflict/effect uncertainty visible;
- completion/merge/deploy/proof/acceptance not inferred.

Security:

- closed output/nested keys;
- secrets/prompts/reasoning/transcripts/tracebacks/paths absent;
- existing local gates/no-store;
- query/arbitrary path refusal;
- no POST;
- cap before write.

No duplicate system:

- pure reducer;
- no database/source reader/cache authority/lifecycle/identity/queue/scheduler/retry/watcher/model authority;
- existing owner code consumed, not copied;
- Linear remains portfolio owner;
- X1/shared inspector unchanged.

Proof:

- focused + legacy + required CI/security checks pass on exact head;
- real local readback/restart;
- three viewport browser evidence;
- witnessed ten-second task;
- exact candidate/path/blob identities.

---

## 11. Stop conditions

Return without broadening if:

- #521 is unprotected/blocking;
- this plan is unaccepted;
- #424 closure unresolved;
- path owner conflict exists;
- required data needs second gather;
- complete decisions need invented/model fields;
- safe copy needs privileged leakage;
- X1/shared assets need change;
- eleventh path needed;
- POST/action needed;
- protected movement materially changes architecture/security/proof;
- browser proof still requires Advanced for act/no-act;
- any modifying outcome becomes uncertain.

Return exact operation/head/tree/base/effect/blocker/smallest next action.

---

## 12. Continuation handoff

Implementation return includes mission, current protected/Skillpack, branch/PR/head/tree/base/blob identities, tests and hosted run IDs, browser matrix/digests, real local result, capability state, missing proof/disagreements, explicit DF2 hold, exact requested Sol ruling, and watcher/same-carrier continuation state when reciprocal dialogue is used.

Worker stop boundary: one Draft/Hold DF1 PR. No merge, default switch, Programs, Ask Sol, action, telemetry, or successor wave without a new explicit edge.

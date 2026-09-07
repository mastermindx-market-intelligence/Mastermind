---
schema: mastermind.chairman_control_room_df1_implementation_plan.v1
operation_key: chairman-control-room-df1-plan-20260907-sol-001
workstream: WS:CHAIRMAN-CONTROL-ROOM
parent_architecture_operation: chairman-control-room-decision-first-f0-20260907-sol-001
parent_architecture_pr: 521
parent_architecture_head: fdd8d9ce8085c906693914e93adc72d919156794
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

> **For agentic workers:** use superpowers:subagent-driven-development or superpowers:executing-plans task by task; use superpowers:test-driven-development before implementation, superpowers:systematic-debugging for unexpected behavior, and superpowers:verification-before-completion before every completion claim.

**Goal:** Deliver one local read-only Chairman briefing at `GET /brief` that lets Chris determine within ten seconds whether the page has complete act/no-act coverage, whether a known Chairman item needs him, what outcomes are currently assigned to Sol, and which material exceptions threaten those outcomes—while preserving `/` as Advanced.

**Architecture:** Add one pure `mastermind.chairman_brief.v1` reducer over the existing cached `mastermind.chairman_control_room.v1` document and current cache/source-validity metadata. Add one fixed token-gated JSON read and three local-only assets. No second gather, source read, mutation, model, lifecycle inference, clock, or remote-X1 change.

**Architecture source:** exact approved semantic head `fdd8d9ce8085c906693914e93adc72d919156794` in PR #521, pending required checks and guarded protection.

---

## 1. Implementation admission

Chairman product direction is approved. This plan is records-only. DF1 START requires:

1. PR #521 independently approved, required checks successful, and merged into protected `master`.
2. The protected design SHA and same-SHA compatible Sol Skillpack loaded.
3. This plan independently reviewed and accepted against the protected design.
4. PR #424's incumbent/current owner has reconciled the older H1A exclusive route/static closure so it neither authorizes a competing default nor forbids this plan's exact closure.
5. Fresh open-PR, rename, branch, worktree, process, and file-owner census proves every DF1 path unowned.
6. Local P0A and remote X1 contracts reread; X1 remains out of scope.
7. One implementation writer explicitly assigned to one branch/PR; no parallel writer.

Missing gate:

```text
BLOCKED SOURCE_OR_OWNERSHIP_PRECONDITION
production_effect=NONE
```

No implementation branch or source edit follows from Chairman product approval alone.

---

## 2. Authority and no-rebuild boundaries

- Executive OS owns Job / Attempt / Worker / Event lifecycle and action admission.
- Agent OS owns durable workstreams, decisions, discoveries, and handoffs.
- GitHub owns implementation, review, CI, merge, and evidence.
- Linear remains portfolio/project projection.
- Slack/Agent Relay remain transport/hot state, not lifecycle truth.
- Existing Control Room composition/cache remains DF1's only source acquisition.
- Existing autonomy/source-validity owners remain currentness/responsibility authority.
- The brief is disposable presentation; deleting it changes no canonical fact.

DF1 must not add a database, table, cache authority, event store, queue, scheduler, retry ledger, wake/dispatch path, lifecycle, identity registry, source reader, background gather, analytics store, POST/action endpoint, model call, second clock, second validity proof, or any canonical-owner mutation.

Truth laws:

- missing is not empty;
- incomplete zero is never clear;
- known items remain visible under incomplete coverage while totals are withheld;
- failed refresh makes retained cache historical;
- Chairman attention is not a complete decision;
- `Sol is handling` means organizational accountability, not provider execution;
- bindings/tabs/windows/processes never prove cognition;
- CI, merge, installation, deployment, proof, and acceptance remain distinct.

Default JSON/DOM must never expose credentials, bearer/cookie/token/password/secret material, hidden prompts, transcripts, private reasoning, chain-of-thought, raw traceback bodies, absolute host paths, browser/provider session identifiers, arbitrary mappings, arbitrary URLs, or external HTML.

---

## 3. Existing source bindings

Reread at implementation base:

| Path | DF1 use | Permission |
|---|---|---|
| `control_plane/chairman_control_room.py` | existing cross-owner composition | read only |
| `control_plane/autonomy_control_room_projection.py` | responsibility/dispatch/placement/freshness projection | read only |
| `control_plane/executive_inbox.py` | Chairman/CEO/COO attention projection | read only |
| `scripts/chairman_control_room.py` | local cache/HTTP server | narrow additive edit |
| `app/static/chairman_control/index.html` | current Advanced inspector | read only |
| `app/static/chairman_control/control_room.js` | shared local/X1 inspector client | read only |
| `app/static/chairman_control/control_room.css` | shared local/X1 inspector CSS | read only |
| `tests/test_chairman_control_room_server.py` | existing server harness | read only |
| `tests/test_chairman_control_room_ui_x1.py` | safe DOM/browser proof pattern | read only |
| `control_plane/chairman_control_room_remote.py` | X1 projection/release closure | read only |
| `scripts/chairman_control_room_remote.py` | X1 server | read only |
| `app/static/chairman_control/remote.html` | X1 entry | read only |
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

DF1 consumes only `control_room`, `composed_at`, `refresh_in_flight`, `state_refresh_error`, and `source_validity`.

Load-bearing paths:

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

Dispatch field is exactly:

```text
responsibility.dispatch.dispatch_state
```

---

## 4. Exact implementation path ceiling

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

Eleventh path:

```text
DECISION_REQUEST PATH_BOUNDARY_REQUIRED
production_effect=NONE
```

Do not edit `index.html`, `control_room.js`, or `control_room.css`.

Recommended implementation branch after admission:

```text
sol/chairman-decision-cockpit-df1-20260907
```

Return state:

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

- `/brief` serves token-injected `brief.html` with the same CSP as `/`.
- `/api/brief` requires existing loopback, Host, exact token, matching Origin when present, and no-store gates.
- `/brief` and `/api/brief` reject every non-empty query string.
- `/api/brief` reads one `_cached_state_snapshot`; no synchronous composition, capability census, filesystem discovery, subprocess, provider inspection, or network call.
- Existing single-flight stale-cache check may run; response returns retained snapshot immediately.
- Success JSON is canonical-encoded and measured before write.
- Maximum successful body is exactly 262144 bytes.
- Larger output returns HTTP 503 with exactly:

```json
{"schema":"mastermind.chairman_brief_error.v1","error":"CHAIRMAN_BRIEF_RESPONSE_TOO_LARGE"}
```

- No partial success bytes.
- No new POST.
- `/` remains Advanced.
- X1 route/static/package/install closure stays byte-identical.

---

## 6. Frozen reducer contract

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
    """Pure deterministic read-only Chairman briefing."""
```

No I/O, environment, clock, randomness, mutation, provider inspection, or source rejoin.

### Closed keys/vocabularies

```python
OUTPUT_KEYS = frozenset({
    "schema", "generated_at", "source", "read_state", "headline",
    "decisions", "attention", "changes", "sol_handling", "exceptions",
    "programs", "feature_gates",
})
READ_STATES = frozenset({"CURRENT", "PARTIAL", "HISTORICAL", "UNAVAILABLE"})
SECTION_STATES = frozenset({"AVAILABLE", "EMPTY", "PARTIAL", "HISTORICAL", "UNAVAILABLE"})
COVERAGE_STATES = frozenset({
    "COMPLETE", "INCOMPLETE", "HISTORICAL_ONLY", "NOT_PROJECTED", "NOT_APPLICABLE"
})
HEADLINE_KINDS = frozenset({
    "CLEAR", "DECISIONS_REQUIRED", "ATTENTION_REQUIRED", "PARTIAL", "UNAVAILABLE"
})
HEADLINE_SCOPES = frozenset({"ATTENTION_AND_DECISIONS", "ATTENTION_ONLY", "NONE"})
```

### Section envelope and cardinality law

```json
{
  "state":"AVAILABLE",
  "coverage":"COMPLETE",
  "reason_codes":[],
  "total_count":3,
  "items":[{},{}],
  "overflow_count":1
}
```

Load-bearing invariants:

```text
coverage == COMPLETE:
  total_count and overflow_count are non-negative integers
  len(items) + overflow_count == total_count
  overflow_count == max(0, total_count - len(items))

coverage in {INCOMPLETE, HISTORICAL_ONLY, NOT_PROJECTED}:
  total_count is null
  overflow_count is null

state == EMPTY:
  coverage == COMPLETE
  total_count == 0
  items == []
  overflow_count == 0

coverage == NOT_PROJECTED:
  state == UNAVAILABLE
  items == []
```

Illustrative JSON must obey these equations. Tests construct complete arrays or totals that reconcile; they must not copy abbreviated architecture examples as contradictory fixtures.

### Top-level DF1 shape

```json
{
  "schema":"mastermind.chairman_brief.v1",
  "generated_at":"2026-09-07T00:00:00Z",
  "source":{
    "control_room_schema":"mastermind.chairman_control_room.v1",
    "control_room_generated_at":"2026-09-07T00:00:00Z",
    "control_room_digest":"sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
    "composed_at":"2026-09-07T00:00:01Z",
    "source_validity_schema":"mastermind.control_room_source_validity.v1",
    "coverage":[]
  },
  "read_state":{"state":"CURRENT","reason_codes":[],"usable_sections":["attention","sol_handling","exceptions"]},
  "headline":{
    "kind":"CLEAR",
    "scope":"ATTENTION_ONLY",
    "complete_decision_count":null,
    "chairman_attention_count":0,
    "sol_accountability_count":1,
    "exception_count":0
  },
  "decisions":{
    "state":"UNAVAILABLE","coverage":"NOT_PROJECTED",
    "reason_codes":["DECISION_PACKET_SOURCE_NOT_PROJECTED"],
    "total_count":null,"items":[],"overflow_count":null
  },
  "attention":{
    "state":"EMPTY","coverage":"COMPLETE","reason_codes":[],
    "total_count":0,"items":[],"overflow_count":0
  },
  "changes":{
    "state":"UNAVAILABLE","coverage":"NOT_PROJECTED",
    "reason_codes":["MATERIAL_CHANGE_CHECKPOINT_NOT_BUILT_IN_DF1"],
    "total_count":null,"items":[],"overflow_count":null
  },
  "sol_handling":{
    "state":"AVAILABLE","coverage":"COMPLETE","reason_codes":[],
    "total_count":1,
    "items":[{"item_id":"sol-coverage-example"}],
    "overflow_count":0
  },
  "exceptions":{
    "state":"EMPTY","coverage":"COMPLETE","reason_codes":[],
    "total_count":0,"items":[],"overflow_count":0
  },
  "programs":{
    "state":"UNAVAILABLE","coverage":"NOT_PROJECTED",
    "reason_codes":["PROGRAMS_NOT_BUILT_IN_DF1"],
    "total_count":null,"items":[],"overflow_count":null
  },
  "feature_gates":{"advanced":"AVAILABLE","programs":"UNAVAILABLE","ask_sol":"UNAVAILABLE","actions":"READ_ONLY"}
}
```

### Canonical digest

Use sorted-key compact UTF-8 JSON with `allow_nan=False`; hash the unmodified source document. Malformed/unserializable source returns typed unavailable rather than raising.

---

## 7. Source coverage/headline algorithm

Closed source rows:

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

Each row contains only `source`, `state`, `coverage`, `reason_codes[]`, and `affects[]`. No raw error.

Current checks:

```text
CORE current:
  correct Control Room schema + safe generated_at + no state_refresh_error

CHAIRMAN_ATTENTION complete/current:
  CORE current
  executive_inbox_schema == mastermind.executive_inbox.v2
  runtime_db_present is true
  no degraded prefix executive_inbox or executive_runtime
  attention mapping with chairman list

AGENT_OS current:
  agent_os_state_schema == agent_os_state.v1
  no degraded prefix agent_os_state or boot_packet

GITHUB current:
  active_builds_schema == project_active_builds.v1
  no degraded prefix active_builds

AUTONOMY_VALIDITY for one row:
  query_status == ok
  responsibility freshness == current
  exactly one source-validity card matches responsibility_ref + root_job_id
  matched components.card.state == current
```

Only parse degraded prefix before first colon; discard suffix.

Headline precedence:

1. invalid core and no valid retained document → `UNAVAILABLE/NONE`, counts null;
2. refresh error/historical admission evidence → `PARTIAL/NONE`, counts null, historical items labeled;
3. admission-capable conflict → `PARTIAL`, totals null, known items visible;
4. incomplete/unavailable Chairman-attention coverage → `PARTIAL`, totals null, known items visible;
5. future complete decisions >0 with complete attention → `DECISIONS_REQUIRED/ATTENTION_AND_DECISIONS`;
6. current Chairman attention >0 with decisions not projected → `ATTENTION_REQUIRED/ATTENTION_ONLY`;
7. complete attention zero with decisions not projected → `CLEAR/ATTENTION_ONLY`, attention 0, decision null;
8. future complete attention+decisions zero → `CLEAR/ATTENTION_AND_DECISIONS`, exact zero counts.

DF1 decisions are always `NOT_PROJECTED`. Optional Agent OS/GitHub/navigation failure does not demote complete Chairman-attention truth but makes dependent sections partial/unavailable.

No partial/attention-only copy may say “everything else,” “all clear,” or broad zero.

---

## 8. Closed item contracts

### Chairman attention

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

Stable safe ID required. Join only through exactly one `work[].attention_ids[]` claim. Zero claim → null work ref. Multiple claims → source conflict/no winner. First item expanded, next two compact. Complete coverage gets exact overflow; incomplete gets null total/overflow. No approve/hold action.

Missing decision fields:

```text
authority_required
closed_options
consequence_of_acting
consequence_of_waiting
reversibility
recommendation_provenance
```

### Decisions

DF1 outputs no decisions and adds no speculative decision input:

```text
decisions.coverage=NOT_PROJECTED
decisions.total_count=null
decisions.items=[]
decisions.overflow_count=null
headline.complete_decision_count=null
```

### Sol organizational accountability

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

Constants:

```text
accountable_owner=SOL
coverage_meaning=ORGANIZATIONAL_ACCOUNTABILITY
provider_execution_state=NOT_ASSERTED
chairman_action_required=false
why_it_matters={state:NOT_PROJECTED,value:null}
next_checkpoint={state:NOT_PROJECTED,value:null}
```

Admission requires exact responsibility/work equality; CEO seat; query `ok`; responsibility current; matching current validity proof; no effect unknown/returned dispatch; no Chairman attention; no disagreement; safe next action; non-blocked/nonterminal Agent OS state; no unmet dependency; unique responsibility identity.

No validity proof → exclude from reassuring list, mark section incomplete, add fixed currentness reason/exception.

### Exception

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

| Fact | Kind | Impact |
|---|---|---|
| refresh error | SOURCE_UNAVAILABLE | latest refresh failed; cached evidence historical |
| runtime unavailable | SOURCE_UNAVAILABLE | current execution claims withheld |
| Inbox unavailable | SOURCE_UNAVAILABLE | current Chairman attention cannot be established |
| Agent OS unavailable | SOURCE_UNAVAILABLE | outcomes/owners/next actions cannot be established |
| active builds unavailable | SOURCE_UNAVAILABLE | implementation/proof changes cannot be established |
| work disagreement | SOURCE_CONFLICT | canonical/projected evidence disagree; no winner |
| blocked/dependency | WORK_BLOCKED | recorded next step cannot advance |
| failed Executive job | WORK_BLOCKED | failed job requires inspection |
| CEO dispatch RETURNED | WORK_WAITING | worker return awaits Sol |
| exact EFFECT_UNKNOWN | EFFECT_UNKNOWN | no retry/carrier change until reconciliation |
| exact WAITING_CAPACITY | CAPACITY_BLOCKED | eligible capacity assignment required |
| unmapped responsibility | OWNER_NOT_ESTABLISHED | accountable operator cannot be established |
| exact proof-missing token | PROOF_MISSING | required accepted proof absent |
| exact production-regression token | PRODUCTION_REGRESSION | previously usable journey reported regressed |

No proof missing from open PR alone; no production regression from CI failure text alone.

### Evidence

Closed keys: owner, ref, field, source_revision, source_time, observed_at, freshness_state. Maximum 32 per item. No arbitrary URL/path. Exact tuple dedupe.

### Sanitizer

Normalize whitespace, require safe string ≤360 chars, reject secret/token/cookie/password/authorization patterns, tracebacks, hidden prompt/reasoning/transcript markers, control characters, and `/Users/`, `/home/`, `/private/`, `/var/`, `/opt/`, `/tmp/`, or Windows absolute paths.

Unsafe replacement:

```text
Source-owned detail is withheld from the default briefing. Inspect Advanced evidence.
```

---

# Task 0 — Admit one clean carrier

1. Fetch/pin protected master; load same-SHA Skillpack.
2. Verify #521 merged, non-draft, no blocker, exact protected design.
3. Read accepted version of this plan.
4. Reconcile #424 through incumbent/current owner; do not edit its files.
5. Census exact ten paths across open PRs, rename history, branches/worktrees/process owners.
6. Create isolated `sol/chairman-decision-cockpit-df1-20260907` worktree only after gates pass.
7. Record pre-start HEAD/tree/base/worktree/path/effect census.

Stop on any uncertain owner/effect.

---

# Task 1 — Build pure contract/read-state red-first

**Files:** create reducer + reducer tests.

RED tests:

- closed top-level/nested keys;
- deterministic byte-identical output;
- all cardinality equations above;
- absent/wrong/malformed core → unavailable;
- refresh error → historical/partial, raw error absent;
- every headline precedence row;
- incomplete known subset with null totals;
- incomplete zero never clear;
- optional GitHub/Agent OS failure isolates dependent sections;
- decisions explicitly not projected;
- NaN/unserializable input never raises;
- input source order cannot alter semantically sorted outputs.

Implement constants, canonical digest, source coverage, section envelopes, headline. Run focused tests green and commit.

---

# Task 2 — Project truthful Chairman attention

RED tests:

- exact stable attention ID;
- exact one-card join;
- zero join → null;
- multiple join → source conflict/no winner;
- duplicate ID → partial/conflict;
- non-Chairman target excluded;
- unsafe summary withheld;
- closed evidence only;
- three visible plus exact overflow under complete coverage;
- incomplete coverage retains known items but total/overflow null;
- no decision promotion or action controls.

Implement exact claims, source-order/stable-ID ordering, cardinality invariants. Green and commit.

---

# Task 3 — Add source-qualified Sol accountability and exceptions

Use exact fixture field `dispatch.dispatch_state` and exact validity join on `(responsibility_ref, root_job_id)` with `components.card.state=current`.

RED positive test asserts exact constants and typed `NOT_PROJECTED` fields.

Negative tests cover non-CEO seat, stale/unknown responsibility, missing/expired validity, ref/root mismatch, refused query, Chairman attention, disagreement, blocked/done/killed state, unmet dependency, RETURNED/EFFECT_UNKNOWN dispatch, effect-unknown placement, unsafe/missing next action, duplicate responsibility, and similar unequal refs.

Exception tests cover every fixed admission, exact-token-only behavior, deterministic IDs/order, semantic dedupe, cardinality equations, raw path/secret omission, no proof/regression inference from PR/CI alone.

Add AST anti-authority test forbidding I/O, network, environment/clock/randomness, runtime mutations, and binding writers in the pure reducer. Green and commit.

---

# Task 4 — Add fixed local reads without second gather

**Files:** create server tests; modify local server.

Reuse sibling harness:

```python
from test_chairman_control_room_server import _auth_headers, _get, _make_config, _running_server
```

RED tests:

- `/brief` CSP/token;
- `/api/brief` token/Host/Origin/peer gates and no-store;
- non-empty query rejection;
- unknown static 404;
- POST `/api/brief` 404;
- current `/`, `/api/state`, POST routes unchanged;
- zero synchronous composition/capability census;
- one cached snapshot per response;
- existing single-flight refresh;
- reducer not called after auth refusal;
- exactly 262144 bytes success; 262145 fixed 503 refusal before partial write.

Implement minimal static map/path additions and `_handle_brief`. Measurement and write use same canonical encoder. Green server + legacy server tests; commit.

---

# Task 5 — Build sparse Today shell

Create `brief.html`, `brief.css`, UI tests.

Required unique IDs:

```text
brief-main brief-source-state brief-headline brief-subheadline
brief-attention brief-attention-list brief-sol-handling brief-sol-list
brief-exceptions brief-exception-list brief-empty brief-advanced
brief-evidence-drawer brief-evidence-title brief-evidence-body
brief-evidence-close brief-scrim
```

Require one external `/static/brief.js`, no inline script/style, no old JS/sidebar/surface dock.

HTML: skip link, compact brand, Today label, no enabled Programs/Ask Sol, fixed Advanced `/`, source/coverage indicator, headline, three sections, calm empty state, evidence drawer.

CSS: centered ≤1040px single column, one expanded priority item, mobile full-screen drawer, visible focus, reduced motion, no color-only state, no horizontal overflow. Green and commit.

---

# Task 6 — Render coverage-qualified UI safely

Create strict IIFE `brief.js`; only createElement/textContent; no innerHTML/document.write/eval/new Function/POST/mutation endpoints.

Map closed headline kind+scope combinations. Never say all clear/everything else under partial or attention-only scope.

Render:

- one expanded + two compact attention items;
- exact/null overflow behavior;
- missing-decision disclosure;
- Sol outcome + recorded next action + “organizational accountability; provider execution not asserted”;
- fixed-impact exceptions;
- evidence drawer with focus trap, Escape/scrim close, focus restoration;
- truthful unavailable network state;
- one bounded status announcement.

Run Python UI tests and `node --check` when available. Green and commit.

---

# Task 7 — Complete deterministic/browser matrix

Required cases:

1. complete attention zero + decisions not projected;
2. one incomplete attention;
3. exact visible+overflow equation;
4. incomplete known subset + null totals;
5. incomplete zero + no clear;
6. duplicate/ambiguous attention;
7. exact current Sol row;
8. missing/expired validity;
9. stale/refused responsibility;
10. blocked outcome;
11. returned worker;
12. runtime/Inbox/Agent OS/GitHub unavailable with correct dependency effects;
13. all admission sources unavailable;
14. historical refresh failure;
15. source conflict/effect unknown/owner missing/capacity blocked;
16. secrets/path/traceback/prompt/reasoning/transcript omitted;
17. exact cap/refusal;
18. corrupt shapes;
19. Programs/Ask Sol gated;
20. Advanced available while Today partial/unavailable.

Browser at 1440×900, 1024×768, 390×844. Assert no overflow, headline visible, no sidebar/dock, Advanced reachable, keyboard drawer/focus, sensitive text absent, reduced motion, truthful network failure, process cleanup.

Run focused suite, legacy local/X1 suite, then exact repository-required test/security commands. Prove X1/shared assets unchanged. Commit.

---

# Task 8 — Document canary/rollback

Document:

```bash
python3 scripts/chairman_control_room.py --port 8787
open http://127.0.0.1:8787/brief
```

Explain `/brief`, `/`, local token/no-store boundary, no decisions/actions/Programs/Ask Sol/change checkpoint, partial/historical behavior, Advanced diagnostics, restart cache rebuild, X1 unchanged.

Rollback: stop opening `/brief`, continue `/`; no canonical migration/rollback. Test and commit.

---

# Task 9 — Produce immutable source and real-local proof receipt

Record exact commit/tree/base/ten blobs and clean status. Run focused, legacy, repository, and security checks on immutable head.

On authorized Chairman Mac prove `/brief`, `/api/brief`, `/`, real degraded-path translation, no provider/open/bind/refresh/mutation, restart/readback, and browser screenshots at all three viewports with digests.

Witness Chris answer within ten seconds:

```text
Can this page establish whether anything currently requires your action? If yes, what; if no, is the answer complete or coverage-limited?
```

No Slack, Linear, GitHub, Finder, or Advanced. Do not backfill a usability receipt.

Publish one Draft/Hold DF1 PR. Distinguish source, CI, local run, browser proof, witnessed task, Sol acceptance, and default cutover. Do not merge/start DF2.

---

## Worker routing

Sequential single writer.

```text
PREFERRED_AVENUE: Terra or bounded CTO Sol
WHY NOT FABLE: product/authority ambiguity is frozen; remaining work is bounded TDD, integration, and browser proof.
```

Independent reviewers inspect immutable commits and do not edit the source worktree. Findings return to the same branch/PR unless ownership/effect state requires reconciliation.

---

## Acceptance checklist

Product:

- coverage-qualified act/no-act answer;
- no project board/percent/giant counts/sidebar/rail;
- known partial items visible without false totals;
- item count + overflow reconciles to total under complete coverage;
- Sol accountability never implies provider execution;
- impact-first exceptions;
- Advanced complete/one click away.

Truth/security/no-duplicate:

- missing not empty, incomplete zero not clear, decisions not projected;
- current/partial/historical/unavailable distinct;
- conflict/effect uncertainty visible;
- closed output/nested keys;
- secrets/prompts/reasoning/transcripts/tracebacks/paths absent;
- existing local gates/no-store/query refusal/no POST/cap-before-write;
- pure reducer, no new source/clock/store/lifecycle/identity/queue/retry/watcher/model authority;
- Linear remains portfolio owner;
- X1/shared inspector unchanged.

Proof:

- focused + legacy + required CI/security checks pass on exact head;
- real local readback/restart;
- three-viewport browser evidence;
- witnessed ten-second task;
- exact candidate/path/blob identities.

---

## Stop conditions

Return without broadening when #521/plan/#424/ownership gates fail; required data needs second gather; complete decisions need invention/model fields; safe copy needs privileged leakage; X1/shared assets need change; an eleventh path or POST/action is required; protected movement changes material law; browser proof still requires Advanced; or any modification becomes effect-unknown.

Return exact operation/head/tree/base/effect/blocker/smallest safe next action.

---

## Continuation handoff

Return mission/outcome, current protected+Skillpack, branch/PR/head/tree/base/blob identities, test/run IDs, browser matrix/digests, real local result, capability state, missing proof/disagreements, explicit DF2 hold, requested Sol ruling, and watcher/same-carrier state when reciprocal dialogue is used.

Worker boundary: one Draft/Hold DF1 PR. No merge, default switch, Programs, Ask Sol, action, telemetry, or successor wave without a new explicit edge.

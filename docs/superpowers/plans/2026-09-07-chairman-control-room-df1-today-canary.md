---
schema: mastermind.chairman_control_room_df1_implementation_plan.v1
operation_key: chairman-control-room-df1-plan-20260907-sol-001
workstream: WS:CHAIRMAN-CONTROL-ROOM
parent_architecture_operation: chairman-control-room-decision-first-f0-20260907-sol-001
parent_architecture_pr: 521
parent_architecture_head: 48f0b1487d1b525995d3681e1e213503743c4228
source_archaeology_pin: f9633f87bbaa22bd7864c756c8e0d1e0663899d0
current_protected_at_plan_repair: 57a2672af5b9dcea282e4bae01d1a0b9d10bb1cd
protected_skillpack_sha: 57a2672af5b9dcea282e4bae01d1a0b9d10bb1cd
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

**Architecture source:** PR #521 is already protected: merged at `2026-09-08T07:47:26Z` as `185dc742dac94d39bcbca81d20d89963ed36f744`, from source head `48f0b1487d1b525995d3681e1e213503743c4228`. The governing Decision-First design blob is `1437aa363f91cee3864e24ddb5fe4b2c50068814`. The protected H1A supersession addendum and #424 terminal receipt `5570607951` replace the retired-worker dependency. This plan does not request another #521 merge or rewrite either protected record.

**Repair boundary:** one existing plan path in PR #523, from head `12a477969c88d2123975d5114e2d4c2b9fee8511` / preimage blob `061349c12865bb6a177a4c55c0e112abd437ce0e`. At this repair basis, GitHub lists two documentation paths, not ten inherited Workbench paths. The additionally listed design has the same `1437aa36...` blob in the source head and protected `57a2672a...`. Preserve that blob. Distinguish the platform's merge-base/branch comparison from the effective integrated source delta: this semantic repair must change only the plan. Do not rebuild or republish Workbench, edit the design, reset/rebase/force, or add a cosmetic ancestry-only commit. Any necessary same-branch graph maintenance needs an actual current platform/protection requirement, incumbent custody, and its own bounded effect reconciliation; stale description text is not such a requirement.

---

## 1. Implementation admission

Chairman product direction is approved. This plan is records-only. DF1 START requires:

1. Reconfirm the already-protected #521 design and supersession addendum at action time. Preserve design blob `1437aa363f91cee3864e24ddb5fe4b2c50068814`, or stop for an actually superseding accepted design; do not wait for #521 to merge again.
2. Load the current protected design and same-commit compatible Sol Skillpack. Record changed dependency/proof contracts separately from unchanged design semantics.
3. The incumbent plan writer applies this one-file correction only after its own current source/custody/effect gate; the repaired immutable plan receives full independent review and acceptance. Proposal preparation or delivery is not source START or writer transfer.
4. Consume protected #521's H1A supersession addendum and #424 terminal receipt `5570607951`: #424 is closed/unmerged/writer-released; old H1A is rejected by design. Fresh protected-source inspection must prove `/api/hub/workstream/chairman-control-room`, `ai_operating_hub_workroom.py`, and `hub_workroom.*` assets/mounts remain absent. No retired-worker reply, cleanup, watcher, or source repair is owed. Preserve its historical paths and still-valid P0A/X1/cache/security/redaction/validity findings.
5. Fresh open-PR, rename, branch, worktree, process, and source-reservation/effect census proves every DF1 path available to its admitted writer. Preserve #537/#531 and other shared-path custody; clean Git or accepted source alone never releases an incumbent. An occupied path or unknown modifier blocks that path, not this records-only proposal.
6. Reread local P0A and remote X1 contracts and their current cache/source-validity owners; X1 remains out of scope. Do not grant Runtime or installed read authority from a merged dependency alone.
7. Retain the existing eligible implementation receiver, subject to its current exact binding and separate START; no parallel writer or automatic new task/worktree. This plan is not an Executive admission bypass.

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
- stale-refreshing cannot establish a current zero; failed refresh makes retained cache historical;
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

The existing cache owner takes one coherent snapshot under `config.state_lock`. In that same snapshot it supplies a closed internal `cache_currentness` result with exactly `state` and `publication_seq`; the sequence is the existing `config.state_published_seq`, not a new counter. This is a projection of existing bookkeeping, not another cache, clock, public API, validity registry, or lifecycle. Keep `/api/state` and X1 wire contracts unchanged; the existing snapshot routine may expose this extra internal value only to the admitted brief read path, without taking a second snapshot.

The same owner uses its existing monotonic metadata and stale predicate (`age > state_ttl`, so equality remains within the existing TTL), current in-flight count, refresh error, and published generation. Validate finite metadata and nonnegative elapsed time before reassurance; malformed/missing metadata is not zero. The reducer receives the owner's result, never the clock, TTL, timestamp-derived age, mutable config, or raw exception.

| Owner observation, in precedence order | Internal state | Brief consequence |
|---|---|---|
| no usable document/generation, invalid monotonic metadata, or stale generation with no established refresh/error disposition | `unavailable` | no current totals or reassurance; valid dated facts may remain explicitly historical |
| usable retained generation with a recorded refresh error, even if a later refresh is now in flight | `historical_refresh_error` | historical/partial, null current totals; fixed error impact only |
| usable generation older than existing TTL, with the existing refresh actually in flight | `stale_refreshing` | partial, dated known subset, no present-tense `CLEAR` |
| usable generation within existing TTL, no refresh error | `fresh` | permits dependent coverage checks, not automatic completeness; an in-flight refresh alone does not make fresh data stale |

Use the existing single-flight trigger and generation-winner publication behavior. A stale-triggering GET must be classified against the snapshot actually returned, not a timestamp or flag read before the trigger. A concurrent successful publication may supply a new coherent fresh snapshot; mixing its sequence with the old document/proofs is forbidden. Scheduling failure or an unclassified stale snapshot is unavailable, never `fresh`.

DF1 consumes only the paired `control_room`, `source_validity`, and `cache_currentness`. The existing cache may retain `composed_at` for its current Advanced contract, but this raw cache timestamp is not an input to the brief reducer. No new cache field grants source validity. Monotonic TTL currentness and the existing Darwin source-validity budget are different predicates with their existing owners; neither substitutes for the other.

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
cache_currentness.state
cache_currentness.publication_seq
source_validity.schema
source_validity.profile
source_validity.publication_seq
source_validity.cards[].responsibility_ref
source_validity.cards[].root_job_id
source_validity.cards[].components.{card,dispatch,owed_open_age}
control_room.work[].agent_os.title
control_room.work[].agent_os.next_action
control_room.autonomy.responsibilities[].accountable_seat
control_room.autonomy.responsibilities[].owed_turn.seat
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
- Use the existing single-flight stale-cache check; return one coherent cached snapshot immediately, with the cache owner's same-lock currentness and publication sequence. Retained stale empty attention must not become `CLEAR`; no synchronous gather or second snapshot is allowed.
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
    cache_currentness: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Pure deterministic read-only Chairman briefing."""
```

No I/O, environment, clock, randomness, mutation, provider inspection, or source rejoin. `cache_currentness` has exactly `state` and `publication_seq`; accept only the four states in §3 and `type(publication_seq) is int` with a positive value for a usable published generation. Missing, malformed, unknown, or unpaired input cannot establish currentness. Neither `composed_at` nor raw refresh flags/errors enter the reducer. Dated evidence uses the already-carried `control_room.generated_at` and admitted item source/observation fields; do not sample, derive, or renew a clock for display.

The internal owner values are case-sensitive `fresh`, `stale_refreshing`, `historical_refresh_error`, and `unavailable`, as frozen on the existing carrier. Do not accept uppercase aliases or normalize an unknown spelling into validity. Public `READ_STATES`, `SECTION_STATES`, and headline vocabularies below remain uppercase and unchanged.

The existing cache owner computes currentness; this function validates/consumes the closed result and maps it to presentation. It does not implement an alternative TTL, expiry policy, proof hash, or source-validity sampler.

### Closed keys/vocabularies

```python
OUTPUT_KEYS = frozenset({
    "schema", "generated_at", "source", "read_state", "headline",
    "decisions", "attention", "changes", "sol_handling", "exceptions",
    "programs", "feature_gates",
})
SOURCE_KEYS = frozenset({
    "control_room_schema", "control_room_generated_at",
    "control_room_digest", "source_coverage",
})
READ_STATES = frozenset({"CURRENT", "PARTIAL", "HISTORICAL", "UNAVAILABLE"})
SECTION_STATES = frozenset({"AVAILABLE", "EMPTY", "PARTIAL", "HISTORICAL", "UNAVAILABLE"})
SOURCE_ROW_STATES = frozenset({
    "CURRENT", "PARTIAL", "HISTORICAL", "UNAVAILABLE", "CONFLICT",
    "NOT_PROJECTED", "NOT_APPLICABLE",
})
COVERAGE_STATES = frozenset({
    "COMPLETE", "INCOMPLETE", "HISTORICAL_ONLY", "NOT_PROJECTED", "NOT_APPLICABLE"
})
FEATURE_GATE_KEYS_IN_ORDER = ("advanced", "programs", "ask_sol", "actions")
FEATURE_AVAILABILITY_STATES = frozenset({"AVAILABLE", "UNAVAILABLE", "READ_ONLY"})
AFFECTS_KEYS_IN_ORDER = (
    "read_state", "headline", "decisions", "attention", "changes",
    "sol_handling", "exceptions", "programs", "feature_gates.programs",
    "feature_gates.ask_sol", "feature_gates.advanced", "feature_gates.actions",
)
HEADLINE_KINDS = frozenset({
    "CLEAR", "DECISIONS_REQUIRED", "ATTENTION_REQUIRED", "PARTIAL", "UNAVAILABLE"
})
HEADLINE_SCOPES = frozenset({"ATTENTION_AND_DECISIONS", "ATTENTION_ONLY", "NONE"})
```

### Source-row state and coverage law

Every output and normative example emits the same ten source rows in the declared order. Each row has exactly `source`, `state`, `coverage`, `reason_codes`, and `affects`; no row is omitted, null, duplicated, renamed, or replaced by source-derived text.

| Source `state` | Required `coverage` | Exact meaning |
|---|---|---|
| `CURRENT` | `COMPLETE` | accepted present-generation evidence completely covers this source family's DF1 dependency |
| `PARTIAL` | `INCOMPLETE` | at least one safe usable current fact remains, but the source family cannot establish a complete result |
| `HISTORICAL` | `HISTORICAL_ONLY` | retained dated evidence is usable only as history and cannot establish a current total |
| `UNAVAILABLE` | `INCOMPLETE` | no usable current fact establishes the affected result and no identity/proof disagreement selects a conflict state |
| `CONFLICT` | `INCOMPLETE` | identity or required proof disagreement prevents a unique winner |
| `NOT_PROJECTED` | `NOT_PROJECTED` | DF1 deliberately has no projection for this source family; this is not zero or source failure |
| `NOT_APPLICABLE` | `NOT_APPLICABLE` | the closed source row is provably irrelevant to this generated claim; this is not missing evidence |

For `INCOMPLETE`, choose `CONFLICT` when identity/proof disagreement prevents a unique winner, `PARTIAL` when at least one safe usable current fact remains, and otherwise `UNAVAILABLE`. Fixed owner disposition is applied first; conflict precedes historical, then complete current, partial, and unavailable. A `NOT_APPLICABLE` source row has `state=NOT_APPLICABLE`, `coverage=NOT_APPLICABLE`, `reason_codes=[]`, retains that named row's fixed `affects`, and has no item/count fields. No current DF1 source row emits `NOT_APPLICABLE`. Any unknown state, mismatched state/coverage pair, missing/duplicate/reordered row, or extra row/key makes the source envelope invalid rather than being normalized.

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

coverage in {INCOMPLETE, HISTORICAL_ONLY, NOT_PROJECTED, NOT_APPLICABLE}:
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

coverage == NOT_APPLICABLE:
  state == UNAVAILABLE
  reason_codes == ["SECTION_NOT_APPLICABLE"]
  total_count is null
  overflow_count is null
  items == []
```

Illustrative JSON must obey these equations. Tests construct complete arrays or totals that reconcile; they must not copy abbreviated architecture examples as contradictory fixtures. No current DF1 section emits `NOT_APPLICABLE`; it remains distinct from `NOT_PROJECTED`, and neither form may contain items or counts.

### Top-level DF1 shape

```json
{
  "schema":"mastermind.chairman_brief.v1",
  "generated_at":"2026-09-07T00:00:00Z",
  "source":{
    "control_room_schema":"mastermind.chairman_control_room.v1",
    "control_room_generated_at":"2026-09-07T00:00:00Z",
    "control_room_digest":"sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
    "source_coverage":[
      {"source":"CORE_DOCUMENT","state":"CURRENT","coverage":"COMPLETE","reason_codes":[],"affects":["read_state","headline","decisions","attention","changes","sol_handling","exceptions","programs"]},
      {"source":"CHAIRMAN_ATTENTION","state":"CURRENT","coverage":"COMPLETE","reason_codes":[],"affects":["read_state","headline","attention","sol_handling","exceptions"]},
      {"source":"EXECUTIVE_RUNTIME","state":"CURRENT","coverage":"COMPLETE","reason_codes":[],"affects":["read_state","headline","attention","sol_handling","exceptions"]},
      {"source":"AGENT_OS","state":"CURRENT","coverage":"COMPLETE","reason_codes":[],"affects":["sol_handling","exceptions","programs"]},
      {"source":"AUTONOMY_VALIDITY","state":"CURRENT","coverage":"COMPLETE","reason_codes":[],"affects":["sol_handling","exceptions"]},
      {"source":"GITHUB_EVIDENCE","state":"CURRENT","coverage":"COMPLETE","reason_codes":[],"affects":["exceptions","programs"]},
      {"source":"DECISION_PACKETS","state":"NOT_PROJECTED","coverage":"NOT_PROJECTED","reason_codes":["DECISION_PACKET_SOURCE_NOT_PROJECTED"],"affects":["headline","decisions"]},
      {"source":"PROGRAMS_SOURCE","state":"NOT_PROJECTED","coverage":"NOT_PROJECTED","reason_codes":["PROGRAMS_NOT_BUILT_IN_DF1"],"affects":["programs","feature_gates.programs"]},
      {"source":"ASK_SOL_SOURCE","state":"NOT_PROJECTED","coverage":"NOT_PROJECTED","reason_codes":["ASK_SOL_NOT_BUILT_IN_DF1"],"affects":["feature_gates.ask_sol"]},
      {"source":"ADVANCED_NAVIGATION","state":"CURRENT","coverage":"COMPLETE","reason_codes":[],"affects":["feature_gates.advanced"]}
    ]
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

### Closed output nullability

No sentinel timestamp, falsey stand-in, or fresh server time is invented. These are the only nullable scalar output paths; `*` means one element of the named array. Arrays and mappings are never null:

- top-level/source identity: `generated_at`, `source.control_room_schema`, `source.control_room_generated_at`, `source.control_room_digest`;
- headline counts: `headline.complete_decision_count`, `headline.chairman_attention_count`, `headline.sol_accountability_count`, `headline.exception_count`;
- list-section counts: `*.total_count`, `*.overflow_count`, where `*` is one of `decisions`, `attention`, `changes`, `sol_handling`, `exceptions`, or `programs`;
- Chairman attention: `attention.items[].work_ref`, `attention.items[].source_time`;
- Sol accountability: `sol_handling.items[].source_time`, `sol_handling.items[].why_it_matters.value`, `sol_handling.items[].next_checkpoint.value`;
- exceptions: `exceptions.items[].work_ref`, `exceptions.items[].chairman_action_required`, `exceptions.items[].source_time`, `exceptions.items[].observed_at`;
- closed evidence under attention, Sol accountability, or exceptions: `evidence_refs[].source_revision`, `evidence_refs[].source_time`.

All other scalar fields are non-null and type-valid. Later item paragraphs may explain only a path listed above; they may not create another nullable path. Empty arrays, empty mappings, false, zero, and empty string do not stand in for null or missing evidence.

Conditions are exact:

- `generated_at` and the source generation/schema/digest fields are null only under the already-defined invalid, absent, or unserializable core cases;
- `headline.complete_decision_count` is always null in DF1 because decisions are `NOT_PROJECTED`;
- other headline counts are integers only when their owning section coverage is `COMPLETE`, otherwise null;
- section counts are integers only for `COMPLETE`, and null for `INCOMPLETE`, `HISTORICAL_ONLY`, `NOT_PROJECTED`, or `NOT_APPLICABLE`;
- `attention.items[].work_ref` is null only when there is zero exact work claim; multiple claims are conflict and never a null winner selection;
- source-time fields are null only where the accepted source exposes no qualified per-field authoring time;
- exception `chairman_action_required` is true for exact current joined attention, false only for complete/current proof of no join, and null otherwise;
- exception `observed_at` is null only for an unavailable/core-invalid exception without a validated generation;
- evidence source revision/time is null only when the accepted closed source does not expose that field.

```text
validated_generation = control_room.generated_at only when it is an actual safe ISO-8601 UTC `Z` string
output.generated_at = validated_generation or null
source.control_room_generated_at = validated_generation or null
source.control_room_schema = exact accepted schema or null
source.control_room_digest = canonical `sha256:<64 lowercase hex>` of the unmodified JSON-serializable mapping, or null when the input is absent/unserializable
source.source_coverage = the ten closed rows in their declared order, never null
```

A digest of a wrong-schema or otherwise invalid but serializable mapping identifies the consumed bytes; it does not make them valid. If `control_room` is absent or cannot be encoded with sorted-key compact UTF-8 JSON and `allow_nan=False`, both the digest and generation fields are null and the result is typed unavailable. `source.control_room_generated_at` must equal top-level `generated_at`; no independent value is permitted.

### Public read-state mapping

Map the existing cache/source result to public `read_state.state` exactly:

| Condition, in precedence order | Public read state |
|---|---|
| no usable retained document, invalid core schema/generation, or unserializable core | `UNAVAILABLE` |
| usable retained document plus `historical_refresh_error`, or all admission-changing evidence is owner-qualified historical | `HISTORICAL` |
| usable retained document plus `stale_refreshing` or unavailable currentness; any current admission-changing source is incomplete/conflicting | `PARTIAL` |
| owner-proven `fresh`, valid paired generation/sequence, and complete non-conflicting Chairman-attention admission | `CURRENT` |

`CURRENT` is compatible with explicitly `NOT_PROJECTED` decisions and with optional non-admission sections being partial/unavailable; those limits remain visible in their own sections and headline scope. `HISTORICAL` and `PARTIAL` never permit a present-tense broad clear. `read_state.usable_sections` is a unique list in fixed order `decisions`, `attention`, `changes`, `sol_handling`, `exceptions`, `programs`, containing only sections whose state is `AVAILABLE`, `EMPTY`, `PARTIAL`, or `HISTORICAL`; omit `UNAVAILABLE` sections. The list is empty under an invalid/no-document result.

Every generated `reason_codes[]` value must belong to this closed vocabulary, in this order; raw degraded suffixes or source text never become codes:

```text
CORE_DOCUMENT_INVALID
CACHE_CURRENTNESS_UNAVAILABLE
CACHE_STALE_REFRESHING
CACHE_REFRESH_ERROR
EXECUTIVE_RUNTIME_UNAVAILABLE
EXECUTIVE_INBOX_UNAVAILABLE
CHAIRMAN_ATTENTION_INCOMPLETE
CHAIRMAN_ATTENTION_CONFLICT
AGENT_OS_UNAVAILABLE
ACTIVE_BUILDS_UNAVAILABLE
AUTONOMY_VALIDITY_UNAVAILABLE
AUTONOMY_VALIDITY_CONFLICT
DECISION_PACKET_SOURCE_NOT_PROJECTED
MATERIAL_CHANGE_CHECKPOINT_NOT_BUILT_IN_DF1
PROGRAMS_NOT_BUILT_IN_DF1
ASK_SOL_NOT_BUILT_IN_DF1
SECTION_NOT_APPLICABLE
WORK_SOURCE_CONFLICT
WORK_BLOCKED
WORK_WAITING
EFFECT_UNKNOWN
WAITING_CAPACITY
OWNER_NOT_ESTABLISHED
PROOF_MISSING
PRODUCTION_REGRESSION
SOURCE_TEXT_WITHHELD
```

Deduplicate codes and emit them in that vocabulary order, never source order. Exact source admission and `affects[]` footprints are:

| Source row | Admitted reason codes | Exact `affects[]` |
|---|---|---|
| `CORE_DOCUMENT` | `CORE_DOCUMENT_INVALID`, `CACHE_CURRENTNESS_UNAVAILABLE`, `CACHE_STALE_REFRESHING`, `CACHE_REFRESH_ERROR` | `read_state`, `headline`, `decisions`, `attention`, `changes`, `sol_handling`, `exceptions`, `programs` |
| `CHAIRMAN_ATTENTION` | `EXECUTIVE_INBOX_UNAVAILABLE`, `CHAIRMAN_ATTENTION_INCOMPLETE`, `CHAIRMAN_ATTENTION_CONFLICT`, `SOURCE_TEXT_WITHHELD` | `read_state`, `headline`, `attention`, `sol_handling`, `exceptions` |
| `EXECUTIVE_RUNTIME` | `EXECUTIVE_RUNTIME_UNAVAILABLE` | `read_state`, `headline`, `attention`, `sol_handling`, `exceptions` |
| `AGENT_OS` | `AGENT_OS_UNAVAILABLE`, `WORK_SOURCE_CONFLICT`, `WORK_BLOCKED`, `SOURCE_TEXT_WITHHELD` | `sol_handling`, `exceptions`, `programs` |
| `AUTONOMY_VALIDITY` | `AUTONOMY_VALIDITY_UNAVAILABLE`, `AUTONOMY_VALIDITY_CONFLICT`, `WORK_WAITING`, `EFFECT_UNKNOWN`, `WAITING_CAPACITY`, `OWNER_NOT_ESTABLISHED` | `sol_handling`, `exceptions` |
| `GITHUB_EVIDENCE` | `ACTIVE_BUILDS_UNAVAILABLE`, `PROOF_MISSING`, `PRODUCTION_REGRESSION` | `exceptions`, `programs` |
| `DECISION_PACKETS` | `DECISION_PACKET_SOURCE_NOT_PROJECTED` | `headline`, `decisions` |
| `PROGRAMS_SOURCE` | `PROGRAMS_NOT_BUILT_IN_DF1` | `programs`, `feature_gates.programs` |
| `ASK_SOL_SOURCE` | `ASK_SOL_NOT_BUILT_IN_DF1` | `feature_gates.ask_sol` |
| `ADVANCED_NAVIGATION` | *(none)* | `feature_gates.advanced` |

Every `affects[]` entry belongs to `AFFECTS_KEYS_IN_ORDER`, is unique, and is emitted in that order. Bare `ask_sol` is forbidden as an `affects` token. Bare `advanced` is forbidden as an `affects` token. Bare `actions` is forbidden as an `affects` token. There is a `programs` section, but no Ask Sol, Advanced, or Actions section. `read_state.reason_codes` is the ordered union from rows affecting `read_state`; each actual section receives the ordered union from rows naming that exact section plus its exact section-fixed code. `headline` and feature gates have no `reason_codes` member; their closed fields fail safe while `source_coverage`, `read_state`, and affected sections carry the cause. `MATERIAL_CHANGE_CHECKPOINT_NOT_BUILT_IN_DF1` and `SECTION_NOT_APPLICABLE` are section-fixed codes and are not attributed to nonexistent source rows.

### Feature-gate closure

`feature_gates` has exactly `FEATURE_GATE_KEYS_IN_ORDER`, with no extra metadata or reason-code member. The exact DF1 values and failure behavior are:

```text
feature_gates.advanced = AVAILABLE throughout DF1
feature_gates.programs = UNAVAILABLE throughout DF1
feature_gates.ask_sol = UNAVAILABLE throughout DF1
feature_gates.actions = READ_ONLY throughout DF1
```

`/` is a fixed server contract and is proved by server tests; reducer input never demotes it. Therefore `ADVANCED_NAVIGATION` is always `CURRENT/COMPLETE`, has no reason code, and affects only `feature_gates.advanced`. `PROGRAMS_SOURCE` and `ASK_SOL_SOURCE` remain `NOT_PROJECTED/NOT_PROJECTED`, so their gates remain unavailable. No source result can enable actions. `ADVANCED_NAVIGATION_UNAVAILABLE` is not a generated code and must never be emitted. Feature-gate explanation remains visible through the closed source rows; no synthetic section or gate-level reason-code array is created.

### Canonical digest

Use sorted-key compact UTF-8 JSON with `allow_nan=False`; hash the unmodified source document. Malformed/unserializable source returns typed unavailable rather than raising. The digest binds the original document, not a sanitized/re-timestamped surrogate. The four nested `source` keys are exhaustive; do not expose `composed_at`, `source_validity_schema`, renamed `coverage`, monotonic samples, or the internal currentness envelope there. Store only closed source-coverage rows in `source_coverage`.

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
  correct Control Room schema + safe generated_at
  paired cache_currentness.state == fresh
  valid positive existing publication_seq; no timestamp-based substitute

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
  exact source-validity schema/profile and same positive publication_seq
  exactly one source-validity card matches responsibility_ref + root_job_id
  all three required components card, dispatch, owed_open_age are qualified/current
  each component binds its existing source proof and this document generation
```

Only parse degraded prefix before first colon; discard suffix.

### Existing source-validity envelope: consume, do not reconstruct

The current owner is `_source_validity_snapshot` in `scripts/chairman_control_room.py`, backed by the existing autonomy projection's proof metadata. Require exact schema `mastermind.control_room_source_validity.v1`, exact `profile == b5.darwin-chrome-paired-v1`, and `type(publication_seq) is int`, positive, equal to `cache_currentness.publication_seq` from the same locked snapshot. Envelope keys remain the incumbent `schema`, `profile`, `browser_qualification`, `publication_seq`, and `cards`; do not rename them or build a second envelope/store.

Exactly one card must match the exact `(responsibility_ref, root_job_id)` of the consumed responsibility; duplicate/conflicting matches are unavailable proof, not first-match selection. For each of **`card`, `dispatch`, and `owed_open_age`**, require the incumbent closed component keys exactly `proof_ref`, `qualified_at`, `remaining_ms`, and `state`:

- `proof_ref` matches `[0-9a-f]{64}` and the corresponding existing responsibility validity proof identity; do not recompute or mint it;
- `qualified_at` equals `control_room.generated_at` and the corresponding source qualification generation;
- `type(remaining_ms) is int` and `remaining_ms > 0`; Boolean, missing, null, zero, negative, nonfinite, or string budgets cannot qualify;
- `state == current`; expired/unqualified/unknown/malformed is not reassurance.

`card` binds accountability, `dispatch` binds the consumed `responsibility.dispatch.dispatch_state`, and `owed_open_age` binds the existing owner's current owed-seat/binding/effect-safe placement proof. This preserves the three-component correction in #523 comment `5608528172`; **do not require `decision_current`**, because complete decision packets are deliberately `NOT_PROJECTED`. `browser_qualification=null` is neutral for this organizational claim and never proof of provider execution. No browser-qualification toggle, new clock, proof map, deadline reset, hash policy, or validity classifier is introduced.

Any missing/conflicting/expired/mismatched required evidence removes that row from reassurance, makes Sol coverage incomplete with null totals, and supplies a fixed currentness exception. Known attention and independent source facts remain available under their own coverage. Corrected inputs replace this derived result on ordinary recomposition; no sticky warning/permission state.

Headline precedence:

1. invalid core and no valid retained document → `UNAVAILABLE/NONE`, counts null;
2. non-fresh cache owner result (`stale_refreshing`, `historical_refresh_error`, or unavailable currentness with usable dated facts), or historical admission evidence → `PARTIAL/NONE`, current counts null, known items explicitly dated; no stale-zero exception;
3. admission-capable conflict → `PARTIAL`, totals null, known items visible;
4. incomplete/unavailable Chairman-attention coverage → `PARTIAL`, totals null, known items visible;
5. future complete decisions >0 with complete attention → `DECISIONS_REQUIRED/ATTENTION_AND_DECISIONS`;
6. current Chairman attention >0 with decisions not projected → `ATTENTION_REQUIRED/ATTENTION_ONLY`;
7. only owner-proven `fresh` plus complete/current attention zero with decisions not projected → `CLEAR/ATTENTION_ONLY`, attention 0, decision null;
8. future complete attention+decisions zero → `CLEAR/ATTENTION_AND_DECISIONS`, exact zero counts.

DF1 decisions are always `NOT_PROJECTED`. Optional Agent OS/GitHub failure does not demote complete Chairman-attention truth but makes dependent sections partial/unavailable. Advanced navigation is a fixed server contract and is never inferred unavailable from reducer input.

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

Stable safe ID required. Join only through exactly one `work[].attention_ids[]` claim. Zero exact work claims is valid and emits `work_ref=null`. Two or more claims are source conflict/no winner. First item expanded, next two compact. Complete coverage gets exact overflow; incomplete gets null total/overflow. No approve/hold action.

Unsafe, blank, missing, or oversized `reason` text alone does not demote or discard an otherwise valid attention item. Its summary is the exact fixed withheld replacement, `SOURCE_TEXT_WITHHELD` is added, and this condition alone does not change an otherwise valid source-row state, coverage, exact count, or headline admission. Duplicate or invalid `attention_id`, two or more work claims, or contradictory required identity/evidence references emit no winner for that identity and yield source `CONFLICT/INCOMPLETE`, section `PARTIAL/INCOMPLETE`, null total/overflow/headline count, and `CHAIRMAN_ATTENTION_CONFLICT`. If copy is unsafe and identity/evidence is conflicted, conflict wins and no placeholder item is emitted. A malformed optional non-identity evidence entry is discarded; it does not turn unsafe copy into identity conflict or create a winner.

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

The only permitted value sources are:

```text
outcome = safe(work.agent_os.title)
recorded_next_action = safe(work.agent_os.next_action)
```

Both must be nonblank, accepted source text. No fallback to responsibility title, readiness reason, PR title, copied checkpoint, or model prose. Unsafe/missing title or action suppresses the reassuring row rather than displaying a withheld placeholder as proof that Sol is handling it.

Admission is conjunctive:

1. exact responsibility/work equality, unique responsibility/root identity, accepted query `ok`, current source facts, and the three-component generation-qualified validity above;
2. `responsibility.accountable_seat == ceo` **and** `responsibility.owed_turn.seat == ceo`, with the existing owner's unambiguous current owed-turn evidence; accountability alone never elects the next move;
3. complete/current Chairman-attention admission and exact absence of joined attention/conflict before setting `chairman_action_required=false`; an unavailable/partial attention read cannot prove this negative;
4. no source disagreement, owner ambiguity, blocker, unmet dependency, waiting return, or blocked/done/killed/terminal work;
5. consume exactly `responsibility.dispatch.dispatch_state`, never `dispatch.state`, top-level guessed state, label, or provider liveness. Reject `RETURNED`, `EFFECT_UNKNOWN`, `WAITING_CAPACITY`, refused/unknown/malformed states, and any other state the existing dispatch owner does not positively qualify for this claim;
6. current joined worker/source/placement effect evidence must be present and owner-qualified safe, or explicitly owner-qualified not applicable. Missing/null/unrecognized evidence is not reconciled-none; any active/prepared/pending/unknown modifying effect, conflicting owed turn, or worker/source effect uncertainty suppresses reassurance. Consume incumbent verdicts and proof, not a new dispatch/placement/effect policy.

An explicit owner-qualified absence of a current worker does not become a phantom running worker. Regardless of the admitted source state, `provider_execution_state` stays `NOT_ASSERTED`. Invalid/missing owed-turn, source values, or proof produces typed partial/exception evidence with null totals; no fallback owner, inferred completion, or hidden repair task.

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
| stale-refreshing | SOURCE_UNAVAILABLE | refresh is in progress; retained evidence cannot establish current act/no-act |
| cache currentness unavailable | SOURCE_UNAVAILABLE | currentness cannot be established; dated facts are not current totals |
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

### Item provenance, repair-owner, and internal-reference closure

All derived item clocks remain observations, not new freshness authority:

```text
observed_at = validated control_room.generated_at, or null only on an unavailable/core-invalid exception
source_time = exact validated source-owned time for the asserted field when present, otherwise null
```

Never substitute `observed_at` for missing `source_time`; never derive either from `composed_at`, monotonic samples, browser time, file metadata, or a new clock. Item `freshness_state` is `CURRENT` for owner-qualified fresh facts, `PARTIAL` for a current known subset under incomplete coverage, `HISTORICAL` for retained non-current facts, and `UNAVAILABLE` only for an exception representing absent/unreadable facts. Attention `source_owner` is exactly `EXECUTIVE_INBOX`; no account/provider/actor label may replace it. The current `mastermind.executive_inbox.v2` mapping is exact: `attention_id` consumes its existing stable `attention_id`, `kind` consumes its existing `kind`, and `summary = safe(item.reason)`. The current attention row exposes no accepted per-item source timestamp, so DF1 sets `source_time=null`; `observed_at` is the paired Control Room generation. Its source `evidence[]` may contribute only safe `ref` and `field`: discard source `value`, set `owner=EXECUTIVE_INBOX`, `source_revision=null`, `source_time=null`, and use the derived observation/freshness values. Unsafe, blank, missing, or oversized reason text alone retains the valid item and uses the fixed replacement without changing otherwise-proven identity, state, coverage, counts, or headline admission. Duplicate/invalid IDs, contradictory required identity/evidence references, or multiple work claims produce `CONFLICT/INCOMPLETE`, no winner, and null exact totals rather than a first match. A malformed optional non-identity evidence entry is discarded. If unsafe copy and conflict coexist, conflict wins and no placeholder item is emitted.

For a Sol-accountability row, the protected design remains controlling: `source_time=null`, `observed_at` equals the paired Control Room generation, and `advanced_ref=/#autonomy`; the reducer must not promote `agent_os_state_generated_at` into a per-field authoring time. Evidence `owner` remains one of the protected design's closed owners and is never copied from arbitrary text.

`chairman_action_required` on an exception is three-valued: `true` only for an exact current joined Chairman-attention item; `false` only when complete/current Chairman-attention coverage proves no join; `null` when that negative cannot be established. A null is never coerced to false.

Closed repair-owner values:

```text
CONTROL_ROOM_CACHE
EXECUTIVE_OS
EXECUTIVE_INBOX
AGENT_OS
GITHUB
AUTONOMY_PROJECTION
SOL
UNESTABLISHED
```

Fixed mapping:

| Exception fact | repair_owner |
|---|---|
| stale-refreshing, currentness unavailable, refresh error | `CONTROL_ROOM_CACHE` |
| runtime unavailable, failed Executive job, waiting capacity | `EXECUTIVE_OS` |
| Inbox unavailable | `EXECUTIVE_INBOX` |
| Agent OS unavailable, blocked/dependency | `AGENT_OS` |
| active builds unavailable, exact proof missing, exact production regression | `GITHUB` |
| CEO dispatch RETURNED | `SOL` |
| unmapped responsibility | `AUTONOMY_PROJECTION` |
| source disagreement | `UNESTABLISHED` |
| EFFECT_UNKNOWN | an exact owner-qualified value above when the existing evidence names one; otherwise `UNESTABLISHED` |

The fixed `UNESTABLISHED` value is an explicit missing-owner result, not permission to infer or commission repair. Keep that absence on the affected exception; do not create a second synthetic exception or hidden repair task solely because the owner is unknown.

Only these queryless local references may be emitted: `/`, `/#needs-you`, `/#autonomy`, `/#work`, `/#system`. Attention `advanced_ref` is `/#needs-you`; Sol-accountability `advanced_ref` is `/#autonomy`. Source/cache/conflict/proof/regression exceptions use `diagnostic_ref="/#system"`; work-blocked/failed cases use `/#work`; returned/effect/capacity/owner cases use `/#autonomy`. No source string, work ref, evidence ref, provider locator, or arbitrary URL may become a navigation target.

### Sanitizer

Freeze this **single default-brief presentation restriction** in the planned reducer's `safe` helper; it is not another security-policy owner or an upstream redaction replacement. Existing canonical source/security owners remain unchanged. Do not duplicate the grammar in JavaScript, server handlers, a new service, registry, or package. All source-derived display strings pass through this one helper; the UI additionally uses safe DOM construction, not a second sanitizer.

Deterministic grammar and order:

1. Accept only an actual string with 1–360 Unicode code points before normalization. Never stringify a mapping/list/object; never truncate an oversized value into a safe prefix.
2. Before whitespace normalization, reject every Unicode control/format/surrogate character (categories `Cc`, `Cf`, `Cs`), including tabs/newlines, NUL, DEL, bidi/zero-width controls. No HTML/entity/percent/escape decoding or Unicode compatibility rewrite can launder rejected input.
3. Permit only Unicode letter/mark/number categories, ASCII space, and the explicit punctuation `. , ; : ! ? ' " ( ) [ ] - – — ‘ ’ “ ” % +`. All other characters are rejected. In particular `/`, `\`, `@`, `=`, `<`, `>`, braces, backticks and URI/path markup are not source-text characters. Fixed application routes and closed evidence IDs are generated separately, never passed through as source prose.
4. Use one sensitive-text predicate on two inspection-only views: the original text case-folded, and an ASCII camel/acronym-word-split copy subsequently case-folded. Construct the second view by replacing `([A-Z])([A-Z][a-z])` with `\1 \2`, then `([a-z0-9])([A-Z])` with `\1 \2`, in that order. Do not change display text or decode/normalize an encoded input. On both views reject the following exact case-insensitive whole-word set: `secret`, `secrets`, `token`, `tokens`, `cookie`, `cookies`, `password`, `passwords`, `authorization`, `bearer`, `credential`, `credentials`, `auth`, `authentication`, `passwd`, `passcode`, `passcodes`, `pwd`, `apikey`, `accesskey`, `privatekey`, `passwordvalue`, `authorizationheader`, `authtoken`. Also reject the phrases `api key`, `access key`, `private key` (one or more space/hyphen/underscore separators). Whole-word matching uses the Unicode-aware regular-expression word boundary; do not replace it with arbitrary substring matching: `Secretary`, `Secretarial`, and `Tokenization` are positive controls. This same helper rejects URI prefixes `http:`, `https:`, `file:`; `traceback`, `stack trace`, `system prompt`, `developer prompt`, `hidden prompt`, `private reasoning`, `chain of thought`/`chain-of-thought`, `transcript`, role-delimited prompt markers, and credential prefixes `sk-`, `ghp_`, `github_pat_`, `xoxb-`, `xoxp-`, `xoxa-`, `xoxr-`, `xoxs-`. Rejection operates before any shortening or space collapse. The two inspection views share this one predicate and policy owner; do not introduce another sanitizer or a client-side fallback.
5. Reject UUID-shaped native/provider identifiers (`[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}`, case-insensitive), `task:`, `session:`, `thread:`, `turn:`, `local_`, `tunnel_`, `cdp:`/`ws:`/`wss:` locator forms, standalone opaque alphanumeric runs of 32 or more characters, and three dot-separated JWT/base64url-like segments of at least eight characters each. Also reject bare dotted-host tokens (two or more dot-separated ASCII alphanumeric/hyphen labels ending in a 2–63-letter label), IPv4-shaped tokens, and colon-delimited hexadecimal endpoint forms; these are withheld text, never inferred links. Current source-owned identifier forms must be included in the hostile corpus; unknown structured objects are never serialized as text. Closed source revision/proof/evidence references remain separately generated bounded fields, not prose exceptions.
6. Only after all checks pass, trim and collapse consecutive ASCII spaces. Reject an empty result; preserve the accepted original letters/punctuation rather than lowercasing display text. Every refusal uses the same fixed replacement below, with no reason echo or rejected substring.

This intentionally conservative first-vertical grammar withholds slash-containing prose as well as URLs/paths; no decoded, escaped, shortened, or client-side fallback is allowed. The explicit hostile corpus must include mixed-case `http(s)` URLs, `file://`, macOS/Linux absolute paths rooted at `/Users`, `/home`, `/private`, `/var`, `/opt`, `/tmp`, `/etc`, `/Volumes`, `/Library`, arbitrary slash roots, Windows drive and UNC paths, current native/browser/provider locator forms, credential material, raw tracebacks, prompt/reasoning/transcript markers, control characters, HTML, and 361-character strings. Pair each rejection family with an ordinary executive-language positive control and verify both JSON and DOM. A proposed wider character grammar is a plan repair, not an implementation improvisation.

The hostile corpus must additionally contain all of these labels followed by the synthetic value `demo-value`: `Credentials:`, `Passwords:`, `Tokens:`, `Cookies:`, `Secrets:`, `APIKey:`, `apikey:`, `Auth:`, `Passwd:`, `Pwd:`, `passwordValue:`, `authorizationHeader:`, `authToken:`, `privatekey:`, `accesskey:`, and `Passcode:`. Their characters, lengths, and ordinary value deliberately pass the other grammar clauses: a test must fail for sensitive-label leakage, not for an unrelated slash, oversized string, UUID, or control character. Require both normalized-display positives and fixed-replacement negatives. Restoring only the earlier singular-word/case-fold-only predicate must reintroduce these 16 intended failures while the ordinary-language and older rejection controls remain unchanged. These are required future owning-helper tests; a sandbox interpretation of this prose is not the implementation.

This finite grammar is an additional deterministic disclosure barrier, not a claim that a keyword filter can recognize every unknown secret in arbitrary prose. The closed source-field allowlist, prohibition on raw mappings/transcripts/provider payloads, and independent JSON/DOM hostile-input proof remain mandatory. No test or receipt may infer complete secret detection from the enumerated examples alone.

Unsafe replacement:

```text
Source-owned detail is withheld from the default briefing. Inspect Advanced evidence.
```

---

# Task 0 — Admit one clean carrier

1. Fetch/pin protected master; load same-SHA Skillpack.
2. Verify the already-protected #521 design blob/addendum at the current base; do not request another merge.
3. Read the independently accepted repaired plan; distinguish one-file plan adoption from future ten-path implementation.
4. Consume #424 terminal supersession; prove rejected route/module/assets/mount absence without waking or editing its retired worker/paths.
5. Census the exact ten paths across open PRs, renames, branches, worktrees, process owners, source reservations, and pending effects. Preserve shared #537/#531/C3 custody until explicit owner release; no clean-status substitution.
6. Use the existing admitted implementation carrier, or create the named isolated worktree only when the retained receiver's separate admission explicitly allows it and no carrier already exists.
7. Record pre-start HEAD/tree/base/worktree/path/effect census.

Stop on any uncertain owner/effect.

---

# Task 1 — Build pure contract/read-state red-first

**Files:** create reducer + reducer tests.

RED tests:

- closed top-level/nested keys, including exact four `SOURCE_KEYS`; each forbidden old source key independently fails the contract assertion;
- deterministic byte-identical output;
- all cardinality equations above, including exact `NOT_APPLICABLE` section state/code/item/count behavior;
- exactly ten source rows in declared order, closed `SOURCE_ROW_STATES`, every valid/invalid state-coverage pairing, and all three `INCOMPLETE` branches;
- absent/wrong/malformed core → unavailable;
- every nullable-path positive case plus rejection of null at every non-allowlisted scalar path, including serializable wrong-schema digest versus absent/unserializable null;
- exact `read_state` mapping for no-document, refresh-error history, stale-refreshing/currentness-unknown partiality, admission conflict/incompleteness, and owner-proven current admission;
- exact fixed-order `usable_sections`, closed generated reason-code vocabulary, and exact/fixed-order source `affects[]` with dotted feature-gate targets; bare Ask Sol/Advanced/Actions tokens and unknown/raw source strings cannot enter either array;
- exact feature-gate key order and values: Advanced always available as a fixed server contract, Programs/Ask Sol unavailable, Actions read-only; no navigation-unavailable inference/code;
- exact three keyword-only reducer inputs: `control_room`, `source_validity`, `cache_currentness`; a raw `composed_at`/refresh-flag/error parameter is forbidden, even when described as display-only;
- exact case-sensitive lowercase cache-owner vocabulary; uppercase lookalikes and unknown spellings cannot establish currentness; preserve the separate uppercase public read/section/headline vocabulary;
- all four cache-owner states crossed with empty/nonempty attention; only `fresh` plus complete admission can reach `CLEAR`;
- stale-refreshing with empty retained attention and no error remains partial; invalid/missing currentness never defaults to fresh;
- refresh error → historical/partial even while retry refresh is in flight, raw error absent;
- older generation plus newer currentness/proof sequence is refused; fresh in-flight positive control remains usable;
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
- unsafe/blank/missing/oversized summary alone retains valid identity/counts/coverage with the exact replacement and `SOURCE_TEXT_WITHHELD`;
- duplicate/invalid identity, multiple work claims, contradictory required evidence, unsafe-plus-conflict precedence, and malformed optional evidence each take the exact delivered path;
- exact `source_owner=EXECUTIVE_INBOX`, source-time/observation-time separation, current/partial/historical freshness mapping, and fixed `/#needs-you` internal reference;
- closed evidence only;
- three visible plus exact overflow under complete coverage;
- incomplete coverage retains known items but total/overflow null;
- no decision promotion or action controls.

Implement exact claims, source-order/stable-ID ordering, cardinality invariants. Green and commit.

---

# Task 3 — Add source-qualified Sol accountability and exceptions

Use the real `responsibility.dispatch.dispatch_state`, `responsibility.owed_turn.seat`, and exact validity join on `(responsibility_ref, root_job_id)`. Start from an otherwise admitted fixture with all three required components, not a fixture already failing another guard.

Positive controls assert Agent OS title/next_action exactly, `accountable_seat=ceo` plus `owed_turn.seat=ceo`, all fixed output constants and typed `NOT_PROJECTED` fields, and successful organizational admission with `browser_qualification=null` and absent/unqualified `decision_current`.

Change one load-bearing input per negative case: wrong/missing schema/profile; Boolean/zero/missing/wrong publication sequence; duplicate card or root/ref mismatch; each of `card`, `dispatch`, `owed_open_age` independently missing, expired, unknown, malformed, proof-mismatched or generation-mismatched; uppercase/nonhex/short proof; Boolean/null/nonpositive remaining budget; CEO accountable but worker/COO/unknown/missing owed turn; partial/unavailable Chairman attention; exact joined attention/conflict; wrong dispatch field spelling with the real field absent; RETURNED/EFFECT_UNKNOWN/WAITING_CAPACITY/refused/unknown dispatch; unsafe or uncertain current-worker/source/placement effects; disagreement, blocked/done/killed state, unmet dependency; unsafe/missing Agent OS title or next_action with tempting fallback values present; duplicate responsibility; similar unequal references. Null evidence must not behave like explicit owner-qualified absence.

Mutation discriminators must kill: ignoring cache currentness; checking only `card`; removing publication-sequence equality; replacing `owed_turn.seat` with `accountable_seat`; permitting responsibility-title/readiness fallback; treating missing effects as NONE; requiring `decision_current` or browser qualification. Assert each intended failure rather than passing through an unrelated invalid fixture. No mutation executes against an installed service or another writer's source.

Exception tests cover every fixed admission, exact-token-only behavior, deterministic IDs/order, semantic dedupe, cardinality equations, raw path/secret omission, no proof/regression inference from PR/CI alone. Independently assert the closed repair-owner mapping, tri-valued `chairman_action_required`, null-preserving source/observation clocks, owner-qualified EFFECT_UNKNOWN fallback, and exact queryless `diagnostic_ref` allowlist. Run the full sanitizer hostile/positive corpus from §8; assert whole-value fixed replacement, pre-normalization control rejection, and no source substring in JSON/DOM. Corrected coverage/owed-turn/proof/text input must remove only the derived warning and restore eligible rows on ordinary recomposition, without sticky state or renewed proof budgets.

Add the exact 16 synthetic sensitive-label cases above to the owning sanitizer tests before implementing the amended lexical rule. Keep `Secretary`, `Secretarial`, `Tokenization`, ordinary API prose, Unicode ordinary text, and whitespace-normalization positive controls. Add the old-lexical-only mutation so the new cases cannot pass merely through another guard. Record RED/GREEN against the real helper separately from any proposal-level diagnostic.

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
- existing single-flight refresh; at exact TTL and just beyond it preserve the current owner's strict-greater-than boundary;
- block refresh completion with the existing test harness, GET stale empty cache, and assert immediate partial/no-CLEAR response plus one refresh rather than N;
- exercise successful correction, retained-error-plus-in-flight, no-document, malformed timing, and fresh-in-flight controls;
- race two publications and assert the returned document/currentness/publication sequence/three-component proofs all belong to one locked snapshot; lower-generation completion cannot overwrite or renew it;
- unchanged `/api/state` and X1 closed keys: internal brief bookkeeping must not leak into their envelopes;
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
20. Advanced available while Today partial/unavailable;
21. stale-refreshing empty snapshot is partial, including its visible transition from fresh to stale to corrected;
22. each required validity component and publication-sequence mismatch independently blocks Sol reassurance; `decision_current`/browser qualification remain neutral;
23. CEO accountability with a non-CEO owed turn cannot show Sol handling; unsafe/missing source title/action cannot fall back;
24. all sanitizer hostile families absent from both JSON and actual DOM; ordinary source text and known attention identity preserved.

Browser at 1440×900, 1024×768, 390×844. Assert no overflow, headline visible, no sidebar/dock, Advanced reachable, keyboard drawer/focus, sensitive text absent, reduced motion, truthful network failure, process cleanup. At 390×844, the coverage-qualified answer and first useful outcome/exception must be visible without raw diagnostics dominating the primary hierarchy. Use required-browser execution: a skip or DOM-source-only check is not browser proof. Bind fixture cases separately from actual served-generation proof; no response override establishes installed source.

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
PREFERRED_AVENUE: Terra
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
- current/partial/historical/unavailable distinct with exact public-state mapping and exhaustive nullability law;
- ten source rows always present, closed source-state/coverage mapping, and exact source/section `NOT_APPLICABLE` behavior;
- closed reason/affects vocabularies, dotted feature-gate targets, exact fixed gate values, no navigation-unavailable inference, and deterministic order;
- source time never substituted by observation time; repair owner and Chairman-action unknown remain explicit;
- conflict/effect uncertainty visible;
- exact four nested source keys; cache currentness from the existing owner/lock, no stale empty CLEAR;
- same-generation card/dispatch/owed_open_age proof; no decision_current or browser-qualification gate for organizational accountability;
- Agent OS title/action only, current CEO owed turn, no effect/attention/dispatch inference;
- one deterministic presentation sanitizer with adversarial positive/negative coverage;
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

Return without broadening when current protected-design/accepted-plan/terminal-supersession-absence/ownership gates fail (not because #521 needs another merge or #424 owes a retired-worker reply); required data needs second gather; complete decisions need invention/model fields; safe copy needs privileged leakage; X1/shared assets need change; an eleventh path or POST/action is required; protected movement changes material law; browser proof still requires Advanced; or any modification becomes effect-unknown.

Return exact operation/head/tree/base/effect/blocker/smallest safe next action.

---

## Continuation handoff

Return mission/outcome, current protected+Skillpack, branch/PR/head/tree/base/blob identities, test/run IDs, browser matrix/digests, real local result, capability state, missing proof/disagreements, explicit DF2 hold, requested Sol ruling, and watcher/same-carrier state when reciprocal dialogue is used.

Worker boundary: one Draft/Hold DF1 PR. No merge, default switch, Programs, Ask Sol, action, telemetry, or successor wave without a new explicit edge.

# A1 — typified NON-CEO service principal (2026-09-18)

Operation `vps-service-principal-a1-20260918-fable-001` (parent
`agent-fabric-end-to-end-fable-integration-20260913-sol-001`). New files only:
`control_plane/executive_service_principal.py`,
`tests/test_executive_service_principal.py`, this note. No existing file is
modified.

## What it is

A closed, reviewed *identity type* for one bounded non-CEO principal —
`svc-site-maintenance`, purpose "VPS site/source-health READ/RESEARCH audits" —
plus a derive/submit path that rides the **existing** single mutation sink
(`control_plane.ceo_intent.submit_intent`) and the **existing** Job creation path
(`runtime.jobs.create_job(..., provenance=...)`).

- Closed schema `mastermind.executive_service_principal.v1`, distinct from
  `mastermind.ceo_intent.v1`; a closed registry of exactly one principal;
  look-alike dataclasses confer nothing.
- Task kind `research` only; `READ`/`RESEARCH` authorities only; derived from the
  existing reviewed `research_only` profile (`ceo_request.py:194-197`), so a
  request cannot name its own identity or authority at all — the sink's own
  normalizer refuses `actor`, `schema`, `requested_authorities`,
  `authority_level`, `branch`, `worktree`.
- `owner_seat="coo"` / `escalation_target="coo"` always, so
  `_has_executive_provenance` (`executive_runtime.py:928-942`, called only from
  `:10287-10297` when a seat is not `coo`) is never consulted.

### Identity law (repair round 2, A1)

The intent id is a domain-separated hash of **exactly** (`SCHEMA`, `principal_id`,
normalized `operation_key`) — nothing else. One logical operation keeps one
intent id and one durable command id, so a later envelope for the same operation
(a changed objective, changed grounding SHAs) is adjudicated by the sink's own
whole-envelope fingerprint conflict law (`ceo_intent.py:785-786`, raising
`CeoIntentConflict`) instead of minting a second Job; a different
`operation_key` legitimately gets its own Job. The module does **not** reimplement
the conflict: it relies on `submit_intent`'s command-id lookup
(`ceo_intent.py:986`) and `command_id_for` (`ceo_intent.py:662`).

### Grant law (repair round 2, A2)

The typed block states the **write ceiling** — `write_authorities`, always `[]`
for this tier — *and* the reviewed grant: `requested_authorities` and
`effective_authorities`, both exactly `["READ","RESEARCH"]`, bound to the
registered principal *and* to the reviewed `research_only` profile
(`ceo_request.py:514` `derive_authorities`). `validate_grant` refuses drift in
both directions before any sink call is reachable: a block that disagrees with
the registry/profile, or an envelope whose
`execution_contract.requested_authorities` disagrees with the block.

### Submission is closed while unadmitted (repair round 2, A3)

`submit()` **fails closed**: while `admission_status()["status"] != "ADMITTED"` it
raises the typed `ServicePrincipalNotAdmitted` (carrying the blocking predicates)
*before* it reads its `runtime` argument, so no production-facing callable here
mutates Runtime in this state. There is no "submit anyway" escape hatch: exactly
one module-level callable reaches the sink, and it is the gated one (pinned by an
AST test). The reachable part is still proven — hermetically, by the tests calling
the **unchanged** sink directly
(`ceo_intent.submit_intent(runtime, derived["envelope"])`,
`test_hermetic_sink_reachability_proof_*`): one QUEUED Job, `coo` seats,
`READ`/`RESEARCH`, no dispatch, duplicate reconcile.

## What it is NOT

- **Not the CEO.** The `ceo-sol` stamp (`ceo_request.py:134`, injected at `:696`
  by `build_trusted_envelope`) is never imported, reused, or emulated; actor ids
  matching `ceo-sol`, `chairman*`, `chris*`, or `operator` are refused at
  construction. The module's AST is pinned by test to contain no `.ACTOR` /
  `.build_trusted_envelope` attribute access.
- **Not a second control plane.** Charter P7 and
  `config/strategic_state.yml` `duplicate_control_planes: prohibited`: there is no
  queue, lease, retry ledger, dispatcher, socket, daemon, or submit service here.
- **Not a write path**: no `WRITE_BRANCH`, no `RUN_TESTS`, no argv, no provider,
  no credential, no host/launchd effect.
- **Not yet admitted.** The tier is READ/RESEARCH only *and* its typed schema —
  and a durable `task_kind` marker — are **not** carryable by today's sink. See
  below.

## The pinned blocker (`admission_status()` → `NOT_YET_ADMITTED`)

`derive_intent` returns the sink envelope, the typed provenance block, and an
honest admission verdict. `submit()` is **closed** (see A3 above), so the
reachable part is only reachable by calling the unchanged sink directly: exactly
one QUEUED Job with `actor=svc-site-maintenance`, the unmodified `coo` seats,
`["READ","RESEARCH"]` authorities, `events.actor` untouched at `"operator"`, and
`event.payload["provenance"]` recording the **sink's** schema.

## A2 (per Sol) — what the typed schema actually is

Per Sol's ruling, A2 is a **strict non-CEO schema
`mastermind.executive_service_intent.v1` carried on the EXISTING sink** — it is
**NOT** a Runtime change, and it must not become one:

* the sink (`control_plane/ceo_intent.py`) is the only mutation path; A2 adds an
  exact-keyed, closed, non-CEO *intent* schema there (`mastermind.executive_service_intent.v1`),
  admitted by the same `validate_intent` fence that admits the CEO schemas today;
* no `executive_runtime.py` seat/provenance change is part of A2;
* `executive_inbox.ceo_intent_provenance` (`executive_inbox.py:639`) must keep
  recognizing **CEO schema only** (`CEO_INTENT_PROVENANCE_SCHEMA =
  "mastermind.ceo_intent.v1"` plus the v2 sibling at `:666`). A service-principal
  schema is *not* CEO provenance and must never be reported as such, or the
  inbox/control-room surfaces would attribute a bounded non-CEO audit to the CEO
  seat.

The `KNOWN OPEN GAP` below stays a Runtime-owned residual (PR #699); it is not
the A2 schema slice, and this PR does not touch either file.

Not reachable without editing an owned file, so not done here:

| Predicate | Where | Consequence |
|---|---|---|
| `validate_intent` admits only `mastermind.ceo_intent.v1`/`v2` | `ceo_intent.py:561-568` | the typed envelope is refused outright |
| exact-key-set check on the v1 envelope | `ceo_intent.py:562` → `_exact_keys` `:319` | the typed block cannot ride inside the envelope |
| `_provenance()` sets `"schema": intent["schema"]` | `ceo_intent.py:735` | the durable schema is always the intent schema |
| `_CONSTRAINT_KEYS` is closed (no `task_kind`) and `create_job` has no `task_kind` parameter | `ceo_intent.py:163`, `executive_runtime.py:10088-10130` | no durable `task_kind` carrier |

Each row is triggered for real by `tests/test_executive_service_principal.py`,
which also pins the cited lines so a move is a loud failure rather than a silent
lie.

## KNOWN OPEN GAP (A2 follow-on, owned by `executive_runtime.py` / #699)

The durable provenance this tier emits is **sufficient** to satisfy the
runtime's higher-seat gate for the CEO target, because that gate is
**schema-only**. This is a residual of the OWNED runtime, stated here so A2 does
not have to rediscover it:

```
if target == "ceo":
    return schema == "mastermind.ceo_intent.v1"        # actor is read, then DISCARDED
return schema in {"mastermind.executive_decision.v1",
                  "mastermind.chairman_decision.v1"} and actor in {"chairman", "chris", "chairman-chris"}
```

Predicate: `_has_executive_provenance` (`executive_runtime.py:928-942`; the
schema-only CEO branch is `:937-938`). Gate call sites: `:10287-10297`,
consulted only when `owner_seat != "coo"` **or** `escalation_target != "coo"`.
For `target="ceo"` the schema is compared and the actor is never consulted; for
the human seat the schema **and** the actor are both required.

Reproduced on a temp runtime from this tier's own derived envelope submitted
through the unchanged sink — the durable `event.payload["provenance"]` is
`{"schema": "mastermind.ceo_intent.v1", "actor": "svc-site-maintenance", ...}`:

| Probe with that exact stamp | Result |
|---|---|
| `_has_executive_provenance(stamp, target="ceo")` | **`True`** |
| `_has_executive_provenance(stamp, target="chairman")` | `False` |
| `create_job(..., owner_seat="ceo", provenance=stamp)` | **ADMITTED** (`owner_seat="ceo"`) |
| `create_job(..., owner_seat="ceo", escalation_target="ceo", provenance=stamp)` | **ADMITTED** |
| `create_job(..., owner_seat="chairman", provenance=stamp)` | `StateConflict` (actor-aware branch) |
| `create_job(..., owner_seat="ceo")` with no provenance | `StateConflict` |
| `create_job(..., owner_seat="ceo", provenance=<typed `mastermind.executive_service_principal.v1`>)` | `StateConflict` |

Why this is not a live escalation *from this tier*: this tier never passes
`owner_seat` / `escalation_target`, so its Jobs keep the runtime's `coo` defaults
(`executive_runtime.py:10108-10109`) and the gate is never consulted for them
(asserted in section 4 of the test module) — and `submit()` cannot create a Job at
all while unadmitted (A3). The gap is **reuse**: any later
Runtime holder — or a child `create_job` — that hands this Job's durable
provenance to a non-`coo` seat passes the CEO gate because of the sink's schema
stamp, not because of the actor. There is no in-place reseat API; the exposure
is stamp reuse and child creation.

The fix belongs in the **OWNED runtime** (A2 follow-on, PR #699): make the CEO
branch actor-aware, or require a distinct executive schema for the CEO seat. It
is deliberately **not** fixed in this PR — neither the sink stamp nor the gate
is touched, and no second submit path is introduced. The gap is pinned by
passing tests
(`tests/test_executive_service_principal.py::test_open_gap_executive_provenance_gate_is_schema_only_A2`
and `::test_open_gap_ceo_seat_is_admitted_with_the_sink_stamp_A2`).

## Follow-ons NOT taken (owned-file collisions)

- **A2 — the seat/provenance extension.** `control_plane/executive_runtime.py`
  `_JOB_SEATS` `:146`, `_has_executive_provenance` `:928-942`, call sites
  `:10287-10297`, plus a controlled admission of the typed schema in
  `control_plane/ceo_intent.py`. **OWNED by PR #699**
  (`sol/autonomy-closure-05-20260916`, OPEN/draft/MERGEABLE); the
  `config/authority_map.yml` note it would also want is OWNED by #703. Must be
  coordinated or stacked, never written blind on this worktree.
- **B — the OpenCode native worker adapter.** New
  `control_plane/opencode_worker.py` + `tests/test_opencode_worker.py` (cleanly
  unowned), plus one descriptor line
  `control_plane/worker_adapter.py:65-68` (`implementation=…` while
  `implemented=False`, constructible-but-UNARMED). **OWNED by #762 and #590.**
  Sequenced after A1: without an admitted, typified principal there is no lawful
  Job to claim, so the adapter would be un-exercisable code.

## Verification

```
python3 -m pytest tests/test_executive_service_principal.py -q   # 17 passed
python3 -m pytest tests/test_ceo_intent.py -q                    # 60 passed (sink unregressed)
python3 -m pytest tests/test_ceo_submit_armed_composition.py -q -k d8_template_topology  # 1 passed
```

`git diff --name-only origin/master` is exactly the three new paths above.

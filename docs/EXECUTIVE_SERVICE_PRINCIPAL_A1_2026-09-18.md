# A1/A2 — typified NON-CEO service principal (2026-09-18)

Operation `vps-service-principal-a1-20260918-fable-001` (parent
`agent-fabric-end-to-end-fable-integration-20260913-sol-001`). A1 added the
typed principal. A2 admits the strict non-CEO schema
`mastermind.executive_service_intent.v1` on the **existing** sink
(`control_plane/ceo_intent.py`). No Runtime / inbox / ingress / service / app /
adapter file is modified.

## What it is

A closed, reviewed *identity type* for one bounded non-CEO principal —
`svc-site-maintenance`, purpose "VPS site/source-health READ/RESEARCH audits" —
plus a derive/submit path that rides the **existing** single mutation sink
(`control_plane.ceo_intent.submit_intent`) and the **existing** Job creation path
(`runtime.jobs.create_job(..., provenance=...)`).

- Closed typed-block schema `mastermind.executive_service_principal.v1`, distinct
  from both CEO intent schemas and from the A2 envelope schema
  `mastermind.executive_service_intent.v1`; a closed registry of exactly one
  principal; look-alike dataclasses confer nothing.
- Task kind `research` only; `READ`/`RESEARCH` authorities only; derived from the
  existing reviewed `research_only` profile (`ceo_request.py:194-197`), so a
  request cannot name its own identity or authority at all — the sink's own
  normalizer refuses `actor`, `schema`, `requested_authorities`,
  `authority_level`, `branch`, `worktree`.
- Envelope schema is `mastermind.executive_service_intent.v1`. The sink's service
  branch exact-keys the v1 set plus `principal_id` / `task_kind`, enforces a
  READ/RESEARCH ceiling (plus no `allowed_write_paths`, READ-level `A0` only),
  stamps those fields as durable evidence, and seats the Job with explicit
  `owner_seat="coo"` / `escalation_target="coo"`.
- `admission_status()` reports `ADMITTED`. Public `submit()` mutates only through
  `ceo_intent.submit_intent` after a live re-read of that verdict.

### Identity law (repair round 2, A1)

The intent id is a domain-separated hash of **exactly** (`SCHEMA`, `principal_id`,
normalized `operation_key`) — nothing else. One logical operation keeps one
intent id and one durable command id, so a later envelope for the same operation
(a changed objective, changed grounding SHAs) is adjudicated by the sink's own
whole-envelope fingerprint conflict law (`ceo_intent.py` `L906`, raising
`CeoIntentConflict`) instead of minting a second Job; a different
`operation_key` legitimately gets its own Job. The module does **not** reimplement
the conflict: it relies on `submit_intent`'s command-id lookup
(`ceo_intent.py` `L1103`) and `command_id_for` (`ceo_intent.py` `L761`).

### Grant law (repair round 2, A2)

The typed block states the **write ceiling** — `write_authorities`, always `[]`
for this tier — *and* the reviewed grant: `requested_authorities` and
`effective_authorities`, both exactly `["READ","RESEARCH"]`, bound to the
registered principal *and* to the reviewed `research_only` profile
(`ceo_request.py:514` `derive_authorities`). `validate_grant` refuses drift in
both directions before any sink call is reachable: a block that disagrees with
the registry/profile, or an envelope whose
`execution_contract.requested_authorities` disagrees with the block.

### Submission is open while admitted (A2)

`submit()` is a thin passthrough while `admission_status()["status"] ==
"ADMITTED"`: derive, refuse grant drift, re-read the verdict, then call
`ceo_intent.submit_intent`. The gate stays live — a regression of the verdict
raises typed `ServicePrincipalNotAdmitted` before the `runtime` argument is
read. There is no "submit anyway" escape hatch: exactly one module-level
callable reaches the sink, and it is the gated one (pinned by an AST test).

The reachable path is proven through public `submit()`: one QUEUED Job, explicit
`coo` seats, `READ`/`RESEARCH`, durable `provenance.schema ==
mastermind.executive_service_intent.v1` with the typed evidence fields, no
dispatch, duplicate reconcile.

## What it is NOT

- **Not the CEO.** The `ceo-sol` stamp (`ceo_request.py:134`, injected at `:696`
  by `build_trusted_envelope`) is never imported, reused, or emulated; actor ids
  matching `ceo-sol`, `chairman*`, `chris*`, or `operator` are refused at
  construction and at the sink. The module's AST is pinned by test to contain no
  `.ACTOR` / `.build_trusted_envelope` attribute access.
  `executive_inbox.ceo_intent_provenance` does **not** classify the service stamp
  as CEO-origin (reader unchanged).
- **Not a second control plane.** Charter P7 and
  `config/strategic_state.yml` `duplicate_control_planes: prohibited`: there is no
  queue, lease, retry ledger, dispatcher, socket, daemon, or submit service here.
- **Not a write path**: no `WRITE_BRANCH`, no `RUN_TESTS`, no argv, no provider,
  no credential, no host/launchd effect. The sink itself refuses those requests
  on the service schema.

## The pinned admission (`admission_status()` → `ADMITTED`)

`derive_intent` returns the sink envelope, the typed provenance block (kept
**outside** the envelope), and the admission verdict. `submit()` is **open**.
Public `submit(principal, request, runtime)` reaches exactly one QUEUED Job with
`actor=svc-site-maintenance`, explicit `coo` seats, `["READ","RESEARCH"]`
authorities, `events.actor` untouched at `"operator"`, and
`event.payload["provenance"]` recording the **service** schema plus evidence
fields `principal_id`, `task_kind`, `requested_authorities`,
`effective_authorities` (evidence, not a grant), `write_authorities: []`.

Pinned sink predicates (cited as `L<n>` strings in `admission_status()`):

| Predicate | Where | Consequence |
|---|---|---|
| `validate_intent` admits the third exact-keyed schema | `ceo_intent.py` `L633` | service envelope is legal |
| `_require_service_ceiling` is READ/RESEARCH only | `ceo_intent.py` `L578` | WRITE_BRANCH / RUN_TESTS never requested |
| `_provenance()` stamps the service schema + evidence | `ceo_intent.py` `L855` | durable stamp is not CEO v1 |
| service `create_job` is explicit `coo`/`coo` | `ceo_intent.py` `L1158` | Job cannot be seated above `coo` |

## Residual Runtime gap (unchanged, owned by `executive_runtime.py` / #699)

A2 closed the schema-only hole **for this tier**: the durable service stamp no
longer satisfies the CEO branch of `_has_executive_provenance`. The residual is
what A2 cannot and must not touch: that CEO branch is still **schema-only** on a
RAW `mastermind.ceo_intent.v1` stamp — the stamp any v1 CEO submission receives.
Actor is read and discarded. The human-seat branch still checks schema AND actor.

```
if target == "ceo":
    return schema == "mastermind.ceo_intent.v1"        # actor is read, then DISCARDED
return schema in {"mastermind.executive_decision.v1",
                  "mastermind.chairman_decision.v1"} and actor in {"chairman", "chris", "chairman-chris"}
```

Predicate: `_has_executive_provenance` (`executive_runtime.py:928-942`; the
schema-only CEO branch is `:937-938`). Gate call sites: `:10287-10297`,
consulted only when `owner_seat != "coo"` **or** `escalation_target != "coo"`.

| Probe | Result |
|---|---|
| `_has_executive_provenance(service_stamp, target="ceo")` | **`False`** |
| `create_job(..., owner_seat="ceo", provenance=service_stamp)` | `StateConflict` |
| `_has_executive_provenance(raw_v1_stamp, target="ceo")` | **`True`** (residual) |
| `create_job(..., owner_seat="ceo", provenance=raw_v1_stamp)` | **ADMITTED** (residual) |
| `create_job(..., owner_seat="chairman", provenance=raw_v1_stamp)` | `StateConflict` (actor-aware) |

This tier's own Jobs ride explicit `coo` seats, so the residual is *reuse* of a
raw-v1 stamp by another Runtime holder, never a Job this tier can create. The
fix belongs in the **OWNED runtime** (PR #699): make the CEO branch actor-aware,
or require a distinct executive schema for the CEO seat. It is deliberately
**not** fixed here. Pinned by
`tests/test_executive_service_principal.py::test_open_gap_raw_v1_stamp_still_satisfies_the_schema_only_ceo_branch`.

Authenticated service ingress (A5) remains deferred to the app/gateway lane
(#797 / #779).

## Follow-ons NOT taken (owned-file collisions)

- **Runtime seat/provenance residual.** `control_plane/executive_runtime.py`
  `_JOB_SEATS` `:146`, `_has_executive_provenance` `:928-942`, call sites
  `:10287-10297`. **OWNED by PR #699.** A2 did not touch it.
- **B — the OpenCode native worker adapter.** New
  `control_plane/opencode_worker.py` + `tests/test_opencode_worker.py` (cleanly
  unowned), plus one descriptor line
  `control_plane/worker_adapter.py:65-68`. **OWNED by #762 and #590.**
- **A5 authenticated ingress.** `integrations/mastermind_executive_app/**` and
  `control_plane/executive_ceo_ingress.py` / `executive_service.py`. **OWNED by
  #797 / #779 / #818 / #695.**

## Verification

```
python3 -m pytest tests/test_ceo_intent.py tests/test_executive_service_principal.py tests/test_executive_inbox.py tests/test_executive_inbox_phase1fb.py -q
python3 -m pytest tests/test_ceo_submit_armed_composition.py -q -k d8_template_topology
```

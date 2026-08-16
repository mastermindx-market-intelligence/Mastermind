# Executive Wake Fabric — PR-1 contracts (v1 rework)

**Status:** contracts only. No Control Panel UI, no GUI automation, no Grok
computer-control, no production MCP write arm, no public HTTP endpoint, no
runtime emitter. Globally unarmed.

The Wake Fabric is the missing notification layer between a **canonical source
fact** and the human-or-AI seat that must continue the work.  It does **not**
become a second Job / Attempt / Worker / Event authority, and it does not
classify the business meaning of a transition.  Classification already lives in
Executive OS Runtime schema v2 and Executive Inbox v2.

```text
CANONICAL SOURCE FACT
        ↓
durable WAKE OBLIGATION   (identity from source only)
        ↓
route resolution          (mutable: session / surface / transport / binding)
        ↓
delivery attempt
        ↓
reasoning target
        ↓
acknowledgement
```

A wake exists because something canonical happened.  It does not cease to be
the same wake because the ChatGPT conversation, Grok relay, Codex thread,
account, or transport changed.

A later Control Panel is a view/controller over these contracts.  It must not
invoke Codex, ChatGPT, or Grok directly.

## 1. Where durable state lives

| Concept | Home | Why |
|---|---|---|
| Job / Attempt / Worker / Event / lease | `control_plane/executive_runtime.py` SQLite | Sole lifecycle authority. Unchanged by this PR. |
| Inbox attention | `control_plane/executive_inbox.py` v2 | Reviewed `attention_id` / `kind` / `target`. |
| Wake *obligation* identity | Deterministic `WAKE-*` from `{schema, source_kind, source_ref, wake_kind}` | Reconstructable on replay. Fits `events.command_id`. |
| Wake request / delivery / ack (later) | Existing `events.command_id TEXT NOT NULL UNIQUE` with phase suffixes | Do not add a wake table, queue, or scheduler. |
| Logical session alias | `config/wake_session_targets.json` | Documentation-as-config. Not a lifecycle registry. |
| Runtime / native handle | `RuntimeBinding` only — never this Git file | OHF-P0: Codex App Server thread ids rotate (resume/fork). |
| Inbox `next_actions` / worker prose | Existing Job / Inbox payload | Inert. Router must not execute or route from it. |
| MCP tool surface | Frozen five-tool table in `integrations/executive_mcp/schemas.py` | `acknowledge_ceo_wake` remains a reserved later schema bump. |

This PR creates **no** SQLite table, **no** queue, **no** scheduler, **no** lease,
and **no** second session database.

Delivery guarantee (when a transport is later armed):

```text
at-least-once external nudge
+ idempotent wake consumption
```

Not fictional exactly-once execution.

## 2. Canonical wake obligation

Module: `control_plane/wake_events.py`
Schema: `mastermind.wake_obligation.v1`

```json
{
  "schema": "mastermind.wake_obligation.v1",
  "obligation_id": "WAKE-<32 hex>",
  "wake_kind": "ceo_decision_pending",
  "source_kind": "executive_inbox_attention",
  "source_ref": "eia-<12 hex>",
  "source_created_at": "2026-08-16T15:00:00Z",
  "emitted_at": "2026-08-16T16:00:00Z",
  "declared_target_seat": "ceo",
  "job_id": null,
  "attempt_id": null,
  "root_job_id": null,
  "workstream": null,
  "evidence_refs": ["eia-<12 hex>"]
}
```

`obligation_id` is a **deterministic wake-obligation identity**, not a hash of
the complete envelope.  `source_created_at` and `emitted_at` are recorded and
**excluded** from the hash.  Session alias, transport, reasoning surface,
native handle, account, route configuration, and free-form `project_id` MUST
NOT participate.

```text
WAKE- + sha256(canonical JSON of
  schema, source_kind, source_ref, wake_kind
)[:32]
```

Required invariant:

```text
same canonical source fact + different session alias
    = same WAKE obligation id

different canonical source facts
    = different WAKE obligation ids
    even if job / attempt / reason happen to match
```

There is a single closed `wake_kind`.  There is no independent `event_type` /
`reason_code` pair that can contradict.  Inbox sources may mint Inbox v2 kinds
only.  Runtime sources may mint `review_required` only.

`job_id` / `attempt_id` / `root_job_id` are optional correlation.  CEO attention
with `job_id = null` (`ceo_decision_pending`, source `agent_os`) is a valid
obligation.  Prefer `root_job_id` over any invented project label.

Seats: `chairman | ceo | coo`.  Representation does not grant authority.
Chairman routes `HUMAN_REQUIRED`.

## 3. Four identity layers

Do not model `PROPHET-COO-A = codex-app-server`.

| Layer | Example | Mutability |
|---|---|---|
| Logical session / executive target | `PROPHET-COO-A` | Stable Git identity |
| Reasoning surface | `chatgpt-sol`, `codex`, `workspace-agent`, `human` | Who reasons |
| Wake transport | `grok-computer`, `chatgpt-gui`, `codex-app-server`, `human` | How the nudge is delivered |
| Runtime binding | native thread/conversation handle, account label, `binding_generation` | Rotates. Never checked in. |

Grok can wake ChatGPT Sol without becoming the reasoning seat.  A new wake
transport can replace Grok without changing `PROPHET-COO-A`.  OHF-P0 Codex App
Server thread ids belong in `RuntimeBinding`, not in this file.

## 4. Session targets and resolution precedence

Module: `control_plane/session_targets.py`
Schema: `mastermind.wake_session_targets.v2`

1. Exact `root_job_id` binding, when that higher-scope identity is present and
   well-formed **and** bound.
2. Known workstream default for the declared seat.
3. Seat default, only when workstream and root binding are both **absent**.

An explicit unknown or malformed workstream / root id **REFUSES**.  It never
silently maps `prophett` onto `EXECUTIVE-COO-A`.

One-workstream → one-session is only a default.  Multiple simultaneous Sol COO
sessions are representable: `PROPHET-COO-A` is the prophet COO default;
`PROPHET-COO-B` is reachable via a runtime `root_job_bindings` overlay.  The
checked-in overlay is empty.

Two-key arming: `target_enabled` (on the target) AND `transport_implemented`
(on the transport descriptor).  Delivery is allowed only if both are true and
the route is not `human_required`.  PR-1 keeps every target disabled and every
transport unimplemented.

## 5. Trusted source adapters — not a semantic classifier

Module: `control_plane/wake_router.py`

There is no free `transition` vocabulary
(`architectural_contradiction`, `mandate_change`, `worker_completed`, …).
Callers do not get to assert that those semantic conditions occurred.

| Adapter | Input | Wake? |
|---|---|---|
| Inbox | Projector output via `admit_inbox_projection` | Yes, for known Inbox kinds. `attention_id` is an opaque `source_ref` — it is not recomputed. Uses the reviewed `target`. Unknown kind → remain attention. A mapping that merely contains an `eia-*` string without the Inbox v2 item shape is refused. |
| Runtime | Canonical event + `owner_seat` + `review_job_exists` | `review_required` only when `JOB_COMPLETED`, `review_required`, and no sibling review (`review.reviews_job_id == builder.job_id`). Ordinary continuation uses `owner_seat`, never `escalation_target`. |

Generic worker-finished is **not** a COO wake.  Phase 1F-B may require a review
job, aggregation, deterministic continuation, or no executive wake at all.

`next_actions`, `worker_prose`, `claimed_session_alias`, `claimed_target_seat`,
`claimed_command`, and `claimed_wake_kind` are stored only so they can be listed
as suppressed.  They never select a seat, alias, transport, command, or kind.

PR-2 must not dual-emit: Inbox already wakes `job_failed` / `job_lost` / … from
runtime terminals.  The runtime adapter must not mint those kinds again.

## 6. Delivery, acknowledgement, coalescing

Module: `control_plane/wake_dispatcher.py`

Obligation-global:

```text
WAKE_REQUESTED          command_id = WAKE-<hex>
TARGET_ACKNOWLEDGED     command_id = WAKE-<hex>:ACK
```

Delivery-attempt-specific (route snapshot lives in the future event payload):

```text
DELIVERY_ATTEMPT        command_id = WAKE-<hex>:A<n>
ACCEPTED                command_id = WAKE-<hex>:A<n>:ACCEPTED
DELIVERED               command_id = WAKE-<hex>:A<n>:DELIVERED
FAILED                  command_id = WAKE-<hex>:A<n>:FAILED
```

Payload contract fields: `obligation_id`, `attempt_n`, `phase`, `session_alias`,
`reasoning_surface`, `wake_transport`, `route_digest`, `destination_digest`,
`binding_generation`.

`ACCEPTED != DELIVERED`.  `DELIVERED != ACKNOWLEDGED`.  `ACCEPTED` alone must
not satisfy `ALREADY_DELIVERED`.  Acknowledgement closes obligation consumption.

Delivered to an old route + no ACK + route/binding rotates = the obligation
remains eligible for delivery to the current route.  `ALREADY_DELIVERED` may
only be reconstructed from a `:A<n>:DELIVERED` record whose route snapshot
matches the current route.

A process crash after `WAKE_REQUESTED` and before dispatch leaves
`PENDING_RETRYABLE`.

Coalescing (contract; no queue in PR-1) groups by current destination
(`session_alias` + reasoning surface + wake transport + `binding_generation` /
`destination_digest`):

```text
5 pending WAKE obligations for the same current destination
        ↓
one NudgePlan / one external wake
        ↓
Chat Sol starts one turn
        ↓
retrieves/drains all five pending obligations
        ↓
acknowledges each obligation
```

Mixed binding generations or transports cannot share one nudge.

`authenticate_receipt` binds a success claim to the expected obligation id,
logical session, reasoning surface, wake transport, route digest, and binding
generation.  An implemented adapter that returns `DELIVERED` for a different
wake/session/route is refused.  Receipt details are a closed key set; values pass
`common.redaction.sanitize_external_text`.  No raw provider errors, URLs, or
credentials.

Transport implementation state has one authority:
`control_plane/wake_transport.py`.  Route construction and dispatcher
authentication both read it.

Root resolution never silently falls through from an explicit unbound
`root_job_id`.

## 7. Explicit non-goals (this PR)

- Control Panel UI
- Grok / computer-use automation
- ChatGPT GUI wake relay implementation
- Codex App Server client
- MCP `acknowledge_ceo_wake` or any schema-snapshot bump
- Public HTTP endpoint
- Runtime transition → wake emission (that is PR-2)
- Changing Executive supervisor, broker, service, MCP, or worker-adapter behavior
- A new scheduler, sidecar queue, or session database
- Production arming

## 8. Recommended PR-2+

1. After a trusted Inbox projection (`admit_inbox_projection` on
   `build_inbox` / `project_needs_ceo` output) or the narrow runtime
   `review_required` fact — **not** from `next_actions` prose and not from an
   arbitrary `eia-*` mapping — mint the obligation.
2. Persist `WAKE_REQUESTED` as an Executive OS event with
   `command_id = obligation_id`.  That row is not delivery.
3. Resolve the route.  An explicit unbound `root_job_id` must refuse, not fall
   through.  Coalesce pending obligations that share the current destination
   digest into one nudge.
4. Persist `DELIVERY_ATTEMPT` (`:A<n>`) with the route snapshot in the event
   payload, then dispatch.  On crash before dispatch, status remains
   `PENDING_RETRYABLE`.
5. Persist `:A<n>:ACCEPTED` and `:A<n>:DELIVERED` only from authenticated
   evidence for that attempt/route.  `ALREADY_DELIVERED` reconstructs from a
   matching route snapshot only.  A previous route's delivery does not suppress
   a rotated binding.
6. Target acknowledgement (`:ACK`) is obligation-global and closes consumption.
7. Still no GUI automation and no Control Panel execution authority until a
   separately reviewed transport PR sets **both** `target_enabled` and
   `transport_implemented`. Acknowledgement remains a later MCP / Control
   Panel act and still one reviewed schema bump.

# Executive Wake Fabric — PR-1 contracts (v1 rework, final hardening)

**Status:** PR-1 contracts + PR-2 durable ledger/reconciliation. Globally
unarmed. No Control Panel UI, no GUI automation, no Grok computer-control, no
ChatGPT GUI adapter, no Codex App Server transport, no production MCP write, no
public HTTP endpoint, no daemon, no launchd schedule. PR-3 (delivery/transport)
has not started.

The Wake Fabric is the missing notification layer between a **canonical source
fact** and the human-or-AI seat that must continue the work.  It does **not**
become a second Job / Attempt / Worker / Event authority, and it does not
classify the business meaning of a transition.  Classification already lives in
Executive OS Runtime schema v2 and Executive Inbox v2.

```text
           EXECUTIVE OS / INBOX / AGENT OS
                      |
                      v
            TRUSTED SOURCE ADMISSION
                      |
                      v
               WAKE OBLIGATION W
                      |
                WAKE_REQUESTED
                      |
         +------------+-------------+
         |                          |
         v                          v
source reconciliation          route resolution
         |                          |
         |                          v
         |                   logical target
         |                   reasoning surface
         |                   wake transport
         |                   RuntimeBinding
         |                          |
         |                          v
         |                   DeliveryAttempt
         |                          |
         |                          v
         |                     NudgeAttempt
         |                  W1:A1 W2:A1 W3:A1
         |                          |
         |                     one adapter call
         |                          |
         |                   ACCEPTED/DELIVERED
         |                          |
         +-------------+------------+
                       |
             +---------+---------+
             |                   |
             v                   v
     TARGET_ACKNOWLEDGED    SOURCE_RESOLVED
```

Core laws:

- obligation identity ≠ route identity ≠ delivery identity ≠ acknowledgement
- transport availability must never determine whether a canonical wake obligation exists
- at-least-once external nudge + idempotent reconciliation/consumption
- there is no claim of exactly-once external execution
- **obligation creation precedes route resolution**
- **route refusal ≠ absence of obligation**

A later Control Panel is a view/controller over these contracts.  It must not
invoke Codex, ChatGPT, or Grok directly.

## 1. Where durable state lives

| Concept | Home | Why |
|---|---|---|
| Job / Attempt / Worker / Event / lease | `control_plane/executive_runtime.py` SQLite | Sole lifecycle authority. Unchanged by this PR. |
| Inbox attention | `control_plane/executive_inbox.py` v2 | Reviewed `attention_id` / `kind` / `target`. |
| Wake *obligation* identity | Deterministic `WAKE-*` from `{schema, source_kind, source_ref, wake_kind}` | Reconstructable on replay. Fits `events.command_id`. |
| Wake request / delivery / ack / resolve | Existing `events` table: `aggregate_type="wake"`, `aggregate_id=obligation_id` | **No SQLite table**, queue, or scheduler. PR-2 writes `WAKE_REQUESTED` and `SOURCE_RESOLVED` only. |
| Logical session alias | `config/wake_session_targets.json` | Documentation-as-config. Not a lifecycle registry. |
| Runtime / native handle | `RuntimeBinding` only — never this Git file | OHF-P0: Codex App Server thread ids rotate (resume/fork). |
| Inbox `next_actions` / worker prose | Existing Job / Inbox payload | Inert. Router must not execute or route from it. |
| MCP tool surface | Frozen five-tool table in `integrations/executive_mcp/schemas.py` | `acknowledge_ceo_wake` remains a reserved later schema bump. |

This PR creates **no** SQLite table, **no** queue, **no** scheduler, **no** lease,
and **no** second session database.  State reconstructs from immutable events.

Delivery guarantee (when a transport is later armed):

```text
at-least-once external nudge
+ idempotent wake consumption
```

Not fictional exactly-once execution.

## 2. Canonical wake obligation

Module: `control_plane/wake_events.py`
Schema: `mastermind.wake_obligation.v1`

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
```

`job_id` / `attempt_id` / `root_job_id` are optional correlation.  CEO attention
with `job_id = null` (`ceo_decision_pending`, source `agent_os`) is a valid
obligation.

**Source workstream ≠ routing workstream.**  `source_workstream` is inert
canonical source correlation (Agent OS may label `WS:PROPHET-FUSION`).
`workstream` / `routing_workstream` is the validated Mastermind session-routing
namespace (`prophet` / `terminal` / `executive`).  A source label must not
automatically become a routing alias.  There is no invented mapping
`WS:PROPHET-FUSION → prophet`.  Agent OS no-job CEO attention may route by CEO
seat default while retaining the source workstream as inert correlation.  A
runtime source whose source workstream is not a routing alias must not silently
fall through to seat-default when a `root_job_id` is present but unbound.

Seats: `chairman | ceo | coo`.  Representation does not grant authority.
Chairman is representable, `human_required`, and not automatically delivered.
No Chairman automation is armed.  Do not force a fake `RuntimeBinding` for a
human path.

## 3. Source admission is separate from routing

Public APIs:

- `admit_inbox_projection(...)` / `admit_runtime_review_source(...)` are the
  only trusted constructors for `CanonicalInboxAttention` /
  `CanonicalRuntimeFact`. Direct dataclass construction is refused.
- Inbox source `workstream` is inert correlation (`source_workstream`). It is
  not auto-promoted into the routing `workstream`.
- `obligation_from_inbox(...)` / `obligation_from_runtime(...)` mint a
  `WakeObligation` from an admitted canonical source.
- `route_obligation(obligation, registry, binding=...)` returns a `WakeRoute`
  or a structured `RouteRefusal`.

A canonical source must be able to produce `WAKE-abc...` even when:

- `root_job_id` is currently unbound
- no runtime binding exists
- transport is unavailable
- the target is disabled
- `production_armed` is false

Those affect **delivery**, not **existence**.  Adding a binding later must
resolve the **same** obligation id.

`WakeRouter.from_inbox` / `from_runtime` still exist as convenience.  When the
source is canonical but currently unroutable they return
`WakeAction.UNROUTABLE` **with the obligation present** and `route=None`.

## 4. Trusted source adapters

Module: `control_plane/wake_router.py`

Phase 1F law: ownership ≠ authority, review ≠ execution, escalation ≠ priority.

`admit_inbox_projection` admits validated Inbox-v2 projector output.  A mapping
is not canonical merely because it has `attention_id` / `target` / `kind`.
`ceo_decision_pending` must be Agent OS CEO attention (`source=agent_os`,
`target=ceo`).  Runtime attention kinds must be runtime-projected.  Unknown
combinations remain attention/refused.  The opaque `attention_id` is preserved;
this adapter does not recompute hidden ordinal identity.

`admit_runtime_review_source(event: Event, job: Job, sibling_jobs=...)` is the
trusted constructor for `CanonicalRuntimeFact`.  Callers cannot independently
claim `owner_seat`, `review_job_exists`, source sequence, or root: those are
derived from the typed Phase 1F objects.  Required:

- `event.aggregate_type == "job"`
- `event.aggregate_id == job.job_id`
- `event.sequence >= 1`
- `event.event_type == JOB_COMPLETED`
- `job.status == COMPLETED`
- `job.review_required is True`
- canonical `root_job_id`
- `owner_seat` from `Job`
- `review_job_exists` from siblings (`review.reviews_job_id == builder.job_id`)

Runtime `review_required` cross-field invariants:

- `source_kind = executive_runtime_event`
- `wake_kind = review_required`
- `source_ref = runtime:job:<JOB-ID>:<sequence>`
- `job_id` is that same `<JOB-ID>`
- `root_job_id` present under Runtime schema v2

A runtime review wake must not be mintable from `runtime:worker:...` or
`runtime:attempt:...`, or from a job source ref that disagrees with `job_id`.
Ordinary continuation follows `owner_seat`, never `escalation_target`.

Worker/model prose must not select seat, transport, wake kind, or authority.

## 5. Four identity layers

Do not model `PROPHET-COO-A = codex-app-server`.

| Layer | Example | Mutability |
|---|---|---|
| Logical session / executive target | `PROPHET-COO-A` | Stable Git identity |
| Reasoning surface | `chatgpt-sol`, `codex`, `workspace-agent`, `human` | Who reasons |
| Wake transport | `grok-computer`, `chatgpt-gui`, `codex-app-server`, `human` | How the nudge is delivered |
| Runtime binding | `binding_id` + generation + native handle | Rotates. Never checked in. |

Grok can wake ChatGPT Sol without becoming the reasoning seat.  OHF-P0 Codex
App Server thread ids belong in `RuntimeBinding`, not in Git config.

## 6. Seat-aware root bindings

Module: `control_plane/session_targets.py`
Schema: `mastermind.wake_session_targets.v2` (unreleased outside this PR; not bumped)

`root_job_id -> one session_alias` is insufficient.  One project/root tree can
legitimately generate COO operational continuation, CEO terminal escalation,
and Chairman decision/escalation.

```json
{
  "JOB-001": {
    "coo": "PROPHET-COO-B",
    "ceo": "EXECUTIVE-CEO-A",
    "chairman": "EXECUTIVE-CHAIRMAN-A"
  }
}
```

Resolution precedence:

1. Root absent → workstream / seat-default resolution may operate.
2. Root present + seat-specific binding exists → exact binding.
3. Root present + malformed → refuse.
4. Root present + valid but no binding for the requested seat → refuse.

Do not silently use a COO root binding for CEO.  Routing labels are not
authority grants.

The public routing operation is:

```text
route_obligation(obligation, registry, binding=None) -> WakeRoute | RouteRefusal
```

It derives `declared_target_seat`, `root_job_id`, and routing workstream from
the obligation.  A caller cannot override them.  Lower-level digest
constructors are private.  COO obligation + CEO `RuntimeBinding` refuses.
Mismatched binding session alias or reasoning surface refuses.

## 7. RuntimeBinding is runtime-only and ABA-safe

```text
RuntimeBinding:
  session_alias
  binding_id          # durable opaque bind-* identity
  binding_generation  # actual int >= 1
  native_handle       # runtime only
  account_label       # runtime only
  reasoning_surface
```

`binding_generation=True` / `1.5` must not coerce into an integer.  Concrete
generation `0` is refused; absence is `binding=None` (route generation `0` /
empty `binding_id`).

ABA: process lifetime 1 generation 1 = Chat tab A; restart; process lifetime 2
generation resets to 1 = Chat tab B.  `binding_id` must differ across lives so
old delivery evidence cannot match the new binding.  **Persistence of the
binding is intentionally deferred.**  Future persistence must reuse reviewed
Executive OS authority/event mechanisms.  Do not invent a second session
database.  Native handles stay out of Git config, `WakeObligation`, and
durable public receipts.

## 8. `production_armed` is a true global kill switch

```text
delivery_allowed =
    production_armed
    AND target_enabled
    AND transport_implemented
    AND binding_ready_if_required
    AND NOT human_required
```

`requires_runtime_binding` lives on the transport descriptor.  An automated
transport that needs a native/session target cannot become
`delivery_allowed=true` with no usable `RuntimeBinding`.

PR-1 production file: `production_armed=false`, every `target_enabled=false`,
every `transport_implemented=false`.  The production loader still rejects true
flags.  Tests may construct in-memory fixtures; they must not weaken the
loader.

## 9. DeliveryAttempt, NudgeAttempt, adapter input

`DeliveryAttempt` is exact and durable:

- `obligation_id`, `attempt_n`, `attempt_command_id` (`W:A<n>`)
- `destination_digest`, `route_digest`
- `binding_id` / `binding_generation`
- `session_alias`, `reasoning_surface`, `wake_transport`

The external adapter receipt is bound to the exact `DeliveryAttempt`.  Future
idempotency-capable providers should use `attempt_command_id`.  A receipt for
`W:A1` cannot close `W:A2`.  A receipt for `W:A1` / route R1 cannot close
`W:A1` / route R2.

**NudgeAttempt / NudgePlan is the external transport unit.**  One nudge may
cover N obligations:

```text
DeliveryAttempt W1:A1 \
DeliveryAttempt W2:A1  \
DeliveryAttempt W3:A1   > NudgeAttempt  →  one adapter invocation
DeliveryAttempt W4:A1  /
DeliveryAttempt W5:A1 /
```

One `NudgeReceipt` / `TransportReceipt` maps deterministically onto each
covered delivery attempt.  Invariants: one external transport invocation; all
obligations share the current destination; every covered Wake remains
independently ACKable/resolvable; mixed session/binding/transport/surface
cannot batch.  ACKed and `SOURCE_RESOLVED` obligations are excluded from the
plan before dispatch.

Adapter input (`WakeNudge`) is a fixed nudge: logical session alias, runtime /
native address, opaque obligation ids / attempt command ids.  Grok does not
receive worker prose, objective, result payload, next_actions, or authority
data.  Reasoning state is retrieved by Sol from Executive OS after wake.
Computer-control transports must not be given the entire source obligation
unless necessary.

## 10. Outcome model

`TransportOutcome` (adapter-authorable): `ACCEPTED`, `DELIVERED`,
`TARGET_UNAVAILABLE`, `FAILED`.

`FabricOutcome` (fabric-only): `ALREADY_DELIVERED`, `HUMAN_REQUIRED`,
`UNSUPPORTED`, `REFUSED`.

- `ACCEPTED` = the destination accepted the nudge; it is **not** delivered.
- `DELIVERED` = authenticated evidence that this attempt reached the destination.
- `ALREADY_DELIVERED` is a ledger-reconciliation result, **never** a transport
  result.  `authenticate_receipt()` rejects adapter-authored
  `ALREADY_DELIVERED` regardless of matching route fields.
- `HUMAN_REQUIRED`, `target_disabled`, `transport_not_implemented`, and
  `production_disarmed` are fabric/preflight decisions.

`ACCEPTED != DELIVERED`.  `DELIVERED != ACK`.  `ACK != SOURCE_RESOLVED`.

## 11. Receipt authentication

`authenticate_receipt()` treats a `WakeReceipt` as untrusted adapter output,
including objects constructed by `WakeReceipt(...)` directly.  It revalidates
schema, outcome, closed outcome/reason pairing, reason_code vocabulary,
obligation identity, exact `DeliveryAttempt` identity, session alias, reasoning
surface, transport, route digest, destination digest, binding
identity/generation, target-enabled snapshot, production_armed snapshot,
transport descriptor state, interface version, `created_at` UTC ISO-8601,
detail keys, detail length, and sanitization.

Do not accept `outcome=DELIVERED` + `reason_code=target_unavailable`, or
`outcome=ACCEPTED` + `reason_code=delivered`.

## 12. Ledger contract

Module: `control_plane/wake_ledger.py`

```text
aggregate_type = "wake"
aggregate_id   = obligation_id
```

| Phase | command_id | payload |
|---|---|---|
| `WAKE_REQUESTED` | `W` (the obligation id) | frozen bounded `WakeObligation` envelope; no attempt-only route fields, no binding/native address |
| `DELIVERY_ATTEMPT` | `W:A<n>` | complete attempt + route snapshot |
| `ACCEPTED` | `W:A<n>:ACCEPTED` | complete attempt + route snapshot |
| `DELIVERED` | `W:A<n>:DELIVERED` | complete attempt + route snapshot |
| `FAILED` | `W:A<n>:FAILED` | complete attempt + route snapshot |
| `TARGET_UNAVAILABLE` | `W:A<n>:UNAVAILABLE` | complete attempt + route snapshot; retry/backoff distinct from generic `FAILED` |
| `TARGET_ACKNOWLEDGED` | `W:ACK` | trusted acknowledgement evidence |
| `SOURCE_RESOLVED` | `W:RESOLVED` | closed `SourceResolutionCode` + snapshot digest + source_ref; prose is annotation only |

`command_id` ↔ phase ↔ `attempt_n` ↔ payload shape is enforced by constructors
and `parse_ledger_record`.  Impossible rows are refused (`W:ACK` with
`phase=DELIVERED`; `W:A1:DELIVERED` with no route snapshot; `WAKE_REQUESTED`
carrying a binding/native address).

Causal rules (state is reconstructed from immutable events; no mutable state
row):

- `REQUESTED` precedes delivery attempts
- `DELIVERY_ATTEMPT` exists before `ACCEPTED` / `DELIVERED` / `FAILED` / `TARGET_UNAVAILABLE`
- attempt terminal evidence is tied to that exact attempt; at most one of `DELIVERED` / `FAILED` / `TARGET_UNAVAILABLE` per attempt
- later attempts cannot start while the previous attempt is unfinished
- a causal stream is one obligation; mixed `W1`/`W2` rows refuse
- `ACCEPTED` does not imply `DELIVERED`
- `DELIVERED` does not imply `ACK`
- `ACK` closes target-consumption eligibility
- `SOURCE_RESOLVED` closes source-attention eligibility
- historical duplicate terminal close evidence may be observed idempotently
- the first terminal consumption/resolution determines that no further delivery
  is eligible

## 13. Acknowledgement

`W:ACK` means the target consumed this obligation.  Future MCP / Control Panel
must not close an arbitrary wake because an LLM supplied `obligation_id` +
`session_alias`.  The model must not self-assert its own trusted session
identity.

```text
WakeAcknowledgement
  obligation_id
  ack_mode            # reasoning_session | human_operator
  target_seat
  session_alias
  reasoning_surface
  trusted binding/session context
  acknowledged_at
```

Identity evidence is injected by a trusted host/gateway/control-plane context
(`TrustedAckContext`).  The model may supply obligation ids it says it
consumed.  The gateway supplies registered logical session identity and binding
context.  `SOURCE_RESOLVED` is not an ACK mode.

ACK is **obligation-global**.  A session may consume an obligation after the
route has rotated.  ACK validity does not require the current route digest to
match the historical delivery route.  ACK evidence must still identify the
trusted consuming context.  Human acknowledgement may later be a trusted
Control Panel/operator mode.  The MCP tool is **not** implemented in this PR.

## 14. SOURCE_RESOLVED

An executive wake can become stale before the target reads it (job fails then
later succeeds; `review_required` then sibling review appears; Agent OS
`needs_ceo` item disappears).  ACK alone is insufficient.

`SOURCE_RESOLVED`: the wake historically existed; the source no longer requires
attention; no further external delivery should occur; the target did not
necessarily consume it.  Do not delete history.

**Source resolution requires a sufficiently healthy canonical read.**  Absence
is not proof if the projector was degraded:

```text
healthy canonical read + source condition absent/resolved
    -> SOURCE_RESOLVED eligible

degraded/incomplete canonical read
    -> leave wake unresolved
    -> expose degradation
```

Agent OS brief unavailable must not be interpreted as "previous CEO item is
gone, therefore resolve wake".  Runtime database unreadable must not resolve
runtime-derived wakes.  Source resolution cannot come from model prose.

## 15. Reconciliation is correctness; callbacks are latency

Do not design PR-2 as edge-trigger-only.

### Crash diagram 1 — source committed / wake missing

```text
canonical source commits
        ↓
process dies
        ↓
WAKE_REQUESTED never written
```

Deterministic obligation identity allows repair only if a later process
re-scans canonical state.  Event hooks may provide low latency.  Reconciliation
provides correctness.  PR-2 must operate as an idempotent reconciliation pass:

```text
canonical sources
     ↓
expected wake obligations
     ↓
compare to Executive OS wake events
     ↓
create missing WAKE_REQUESTED
resolve obsolete obligations
attempt eligible delivery
```

The reconciler is **not** implemented here.  Contract-level idempotency is:
the same canonical source always remints the same `WAKE-*` id.

### Crash diagram 2 — delivery attempt committed / transport outcome uncertain

```text
W:A1 persisted
        ↓
external nudge occurs  OR  process dies before the nudge
        ↓
process dies before DELIVERED receipt persisted
```

From durable state alone those are ambiguous.  Restart reconciles unfinished
**A1**.  Do not automatically allocate A2 merely because the process restarted.
If transport supports idempotency, reuse A1's deterministic attempt key.  If
it does not, a duplicate external nudge is possible and is accepted as
at-least-once.  Target consumption stays idempotent.

## 16. Bounded retry law

Wake delivery must not become an infinite notification loop.  Before any
automated transport can be armed, a reviewed `WakeRetryPolicy` must supply:

- max delivery attempts per obligation/destination
- retry cooldown/backoff
- ACCEPTED-but-not-DELIVERED timeout/TTL
- TARGET_UNAVAILABLE behavior
- route/binding rotation behavior

PR-1 defines the required policy shape (`WakeRetryPolicy`) and keeps it
**unarmed**.  Numeric values are a PR-2 policy decision.  Job `attempt_limit`
is not a wake-nudge bound.  No unbounded repeated nudge to the same
destination after authenticated `DELIVERED` evidence unless a reviewed
condition re-enables delivery (binding rotation is such a condition).

## 17. Destination identity vs route/policy audit identity

**Destination identity** (`destination_digest`) =

- logical session
- reasoning surface
- wake transport
- durable binding identity/generation

It **excludes** `policy_version`.  Same Chat session + same binding + same
transport + new policy label is the same destination.

**Route digest** =

- obligation id
- destination digest
- canonical `policy_digest` computed over the validated routing policy/config

`policy_digest` is audit metadata, not destination identity.  Do not trust a
manually edited string as the sole audit proof.

Two questions:

1. Is this exact delivery attempt a replay? → attempt identity + route digest
2. Has this obligation already been delivered to this same destination? →
   obligation + destination identity

An unrelated policy-version/config-audit change must not automatically trigger
another nudge to the same already-delivered destination.  A true binding
rotation must.

## 18. Explicit non-goals (this PR)

- Control Panel UI
- Grok / computer-use automation
- ChatGPT GUI wake relay implementation
- Codex App Server client
- MCP `acknowledge_ceo_wake` or any schema-snapshot bump
- Public HTTP endpoint
- Runtime transition → wake emission as a live daemon (PR-2 is a one-shot reconciler only)
- Live reconciliation daemon
- Changing Executive supervisor, broker, service, MCP, or worker-adapter behavior
- A new scheduler, sidecar queue, or session database
- Production arming (`production_armed` / `target_enabled` /
  `transport_implemented` remain false)
- Delivery attempts, ACK, or any transport from the reconciler
- RuntimeBinding / root-session binding persistence

## 19. PR-2 durable ledger and reconciliation

PR-2 persists source-driven obligations onto the existing Executive OS `events`
table.  It does not add a Wake database, table, queue, scheduler, or mutable
state row.

```text
canonical source state
      ↓  (no write transaction held)
trusted source snapshot
      ↓
expected WakeObligations
      ↓
compare durable wake events
      ↓
persist missing WAKE_REQUESTED
      ↓
persist SOURCE_RESOLVED only from healthy canonical absence proof
```

Reconciliation is deterministic, idempotent, crash-recoverable, source-driven,
and route/transport-independent.  Automatic apply creates only `WAKE_REQUESTED`
and `SOURCE_RESOLVED`.  It does not create `DELIVERY_ATTEMPT`, `ACCEPTED`,
`DELIVERED`, `FAILED`, `TARGET_ACKNOWLEDGED`, or any transport invocation.

Source reads (`WakeSourceSnapshot`) happen before `BEGIN IMMEDIATE`.  Runtime
directly emits `review_required` only, via typed `Event` + `Job` + sibling Jobs
through `admit_runtime_review_source`.  Inbox kinds go through
`admit_inbox_projection` / `obligation_from_inbox` on a validated
`mastermind.executive_inbox.v2` document.  Agent OS no-job CEO attention is a
valid obligation (`job_id` / `attempt_id` null).  Two identical Agent OS rows
remain two obligations because Inbox `attention_id` already disambiguates them.

Degradation is asymmetric: an observed valid source may create a missing
`WAKE_REQUESTED`.  Absence may `SOURCE_RESOLVE` only when that lane's canonical
snapshot positively proves a healthy read.  Unreadable runtime, missing boot
packet, foreign Inbox schema, or a partial projection is not "source
disappeared".

ACK and `SOURCE_RESOLVED` are terminal for automatic delivery eligibility.
Reconciliation does not reopen a terminal Wake merely because the same
deterministic source id reappears.  A new source fact (new Inbox `attention_id`,
or a new `runtime:job:<JOB-*>:<sequence>`) is a new obligation.

The optional one-shot `scripts/executive_wake_reconcile.py` performs one
snapshot, one plan, one apply, one report, and exits.  It is not wired into
`ExecutiveControlService` startup.

## 20. Recommended PR-3+

1. Coalesce eligible pending obligations that share the current
   `destination_digest` into one `NudgeAttempt`.
2. Persist `DELIVERY_ATTEMPT` (`:A<n>`) with the route snapshot, then dispatch
   **one** adapter call.  On crash, reuse unfinished A1.
3. Persist `:A<n>:ACCEPTED` / `:A<n>:DELIVERED` only from authenticated
   transport evidence for that attempt.  `ALREADY_DELIVERED` reconstructs from
   trusted durable destination-level delivery evidence.
4. Target acknowledgement (`:ACK`) is obligation-global, from trusted session
   or human-operator context.  MCP ACK remains a later schema bump.
5. Still no GUI automation and no Control Panel execution authority until a
   separately reviewed transport PR sets **both** `target_enabled` and
   `transport_implemented` **and** `production_armed`, with a reviewed bounded
   retry policy.

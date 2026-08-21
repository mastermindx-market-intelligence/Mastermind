# Executive OS Personal-Pro Relay — state and transport amendment

**Date:** 2026-08-20  
**Linear:** MAS-105 / F0, parent MAS-48  
**Status:** RECORDS-ONLY ARCHITECTURE AMENDMENT. NO PR-A RUNTIME LAW IS CHANGED BY THIS FILE.  
**Parent authority:** Mastermind PR #91 parent architecture and PR #96 PR-A implementation law.

## 0. Purpose and precedence

PR #91/#96 remain authoritative for the first hermetic CEO-ingress implementation. In particular, MAS-75 / PR-A remains exactly:

```text
bounded high-level CEO request
  -> dedicated CeoIngress submit frame
  -> trusted grounding/replay/admission law
  -> existing ceo_intent.submit_intent
  -> one QUEUED Job / JOB_CREATED
  -> dedicated Slack-namespace status frame
  -> zero worker execution
```

PR-A exposes exactly two schemas and must not be widened by implementation convenience.

This F0 amendment freezes **later** architecture discovered while designing the full Personal-Pro product shell:

1. the primary Pro-native read path should not depend on private/custom MCP availability;
2. a small Executive hot-state read should be separated from the rich CEO boot/inbox path;
3. Slack should wrap that Executive snapshot with transport health without becoming canonical state;
4. the read lane should ship before inbound write transport;
5. replay/reconnect can remain storeless if bounded history is used as transport evidence and Executive OS remains idempotency authority.

Where this file discusses a state frame on CeoIngress, it describes **R0 after PR-A acceptance**, not PR-A itself.

## 1. Why the existing MCP `executive_state` is not the hot-state contract

The existing Executive MCP is useful and remains supported infrastructure. Its `executive_state`/inbox surface intentionally composes richer executive orientation, including Agent OS/boot packet information.

That is the wrong shape for a frequent Slack heartbeat:

* boot-packet collection can shell into Macro/Agent OS and is intentionally much broader than runtime telemetry;
* it carries organizational material, degraded prose, handoffs and recommendation-oriented context inappropriate for a private machine heartbeat;
* roots/paths and broad projection details should not be copied into Slack;
* polling the full CEO orientation path every 30 seconds would couple hot-state availability to a slower organizational read.

Therefore V1 introduces a **transport-neutral hot-state projection** rather than using the full boot packet as a heartbeat.

Existing MCP remains an optional independent audit/readback path. It is not a required Personal-Pro dependency once the Slack hot-state lane is accepted.

## 2. `mastermind.executive_hot_state.v1`

Conceptual contract:

```json
{
  "schema": "mastermind.executive_hot_state.v1",
  "generated_at": "2026-08-20T00:00:00Z",
  "snapshot_hash": "<sha256>",
  "grounding": {
    "mastermind_sha": "<40 lowercase hex>",
    "macro_sha": "<40 lowercase hex>",
    "boot_packet_schema": "mastermind.ceo_boot_packet.v1"
  },
  "service": {
    "service_state": "READY",
    "ceo_admission": "READY"
  },
  "generic_operator_mutations": "AVAILABLE",
  "runtime": {
    "projection_state": "OK",
    "jobs": {"total": 0, "by_status": {}},
    "attempts": {"total": 0, "by_status": {}},
    "workers": {"total": 0, "by_status": {}}
  },
  "degraded": [],
  "do_not_submit": false
}
```

Exact field vocabulary is frozen by R0 after PR-A, but these laws are binding now:

* output is deterministic for the same canonical Runtime state, trusted grounding and clock;
* Runtime status breakdown uses the actual Executive enum members; the projector does not invent lifecycle states such as a synthetic Job `BLOCKED` status;
* `grounding` comes from the same trusted, value-only grounding provider used by CeoIngress admission;
* no repository paths/roots, handoff prose, objectives, next actions, arbitrary event payloads, secrets, tokens or provider credentials cross this surface;
* dependency/internal errors become fixed machine-readable degradation codes and bounded opaque public text where text exists;
* `snapshot_hash` hashes canonical semantic JSON excluding `generated_at` and the hash itself;
* the hash detects semantic change and is not authentication;
* output is bounded; oversize is a visible protocol failure, never silent truncation.

### 2.1 Service/admission truth

The state projection must distinguish at least:

* generic Executive service state;
* CEO admission readiness;
* generic Operator mutation availability;
* runtime projection availability.

It must not claim provider-specific diagnoses such as `AUTH_MISSING` unless a canonical typed provider-readiness source is later reviewed into the contract. A human/operator diagnosis does not become runtime truth by being convenient to display.

### 2.2 Database health language

Do not publish generic `database_healthy=true` unless a named integrity check was actually run and has a timestamp.

A frequent hot-state read may truthfully say that typed runtime projection succeeded. A full SQLite health/integrity assertion belongs to a separately named probe/receipt. No green adjective without naming what was tested.

## 3. R0 post-PR-A state frame

After PR-A is merged and Sol-accepted, R0 may authorize one additional closed read schema on the **existing dedicated CeoIngress socket**, conceptually:

```json
{"schema":"mastermind.executive_ceo_ingress_state.v1"}
```

No business input is accepted.

### 3.1 Why same dedicated listener

Rejected alternatives:

**Use the generic Operator socket.** Rejected because it exposes a broad command dispatcher and would require granting the Relay principal access to more authority than its product job needs.

**Create a fourth listener/service.** Rejected because it duplicates startup, shutdown, lock, socket, principal and lifecycle composition for no independently useful authority boundary.

The state read belongs beside submit/status on the dedicated CEO-facing local boundary, but only after PR-A establishes that boundary safely.

### 3.2 Diagnostic availability

Before the dual-listener startup latch is true, the state frame refuses `ingress_unavailable` before business reads.

After successful process/listener startup, state read is diagnostic and may remain available when:

* CEO admission is unarmed;
* generic service state is `AWAITING_CANARY`;
* service state is dynamically `QUARANTINED`.

That is deliberate. A diagnostic read that disappears precisely when mutation is blocked prevents Sol from knowing why work is unsafe.

Read availability grants no mutation authority and does not clear quarantine.

## 4. `MMX/SOL_STATE_V1`

Slack does not copy the Executive document verbatim. The Relay wraps it with transport/publication health:

```text
MMX/SOL_STATE_V1
{
  "schema":"mastermind.sol_state.v1",
  "generated_at":"...",
  "relay_checked_at":"...",
  "state_hash":"...",
  "status":"OK",
  "executive": { ... executive_hot_state.v1 ... },
  "relay": {
    "state_publisher":"READY",
    "command_transport":"NOT_INSTALLED",
    "reconciliation":"NOT_REQUIRED",
    "version":"..."
  },
  "relay_degraded":[],
  "do_not_submit":true
}
```

Executive owns the embedded lifecycle/runtime truth. Relay owns only its own connection/publication/reconciliation facts.

A future carrier may consume `executive_hot_state.v1` without inheriting Slack concepts.

## 5. One atomic state message, no state-message database

Private `#sol-runtime` carries exactly one active Relay-bot-authored `MMX/SOL_STATE_V1` message.

Relay startup:

```text
read bounded #sol-runtime history
  -> filter exact configured Relay bot user
  -> filter exact MMX/SOL_STATE_V1 discriminator
     0 matches: create one
     1 match: recover message ts and update it
     >1 matches: STATE_MESSAGE_AMBIGUOUS; fail closed
```

The Relay does not persist that message timestamp in a new database. Slack history is transport evidence; Executive OS remains lifecycle authority.

If the process dies after creating the message but before remembering the returned timestamp, restart recovers it from Slack.

## 6. Freshness and publication defaults

Initial engineering defaults, subject to measurement but not casual widening:

```text
Executive state poll:       30 seconds
semantic-change publish:    immediate
unchanged heartbeat:        60 seconds
max state age for new write: 120 seconds
SOL_STATE desired size:      ~3–4 KiB
SOL_STATE hard Slack ceiling: 4,500 UTF-8 bytes
CEO source-message ceiling:   4,500 UTF-8 bytes
```

A stale `SOL_STATE` is not repaired by continuing to show old green values with a fresh wrapper timestamp.

If Executive read becomes unavailable, the Relay overwrites the single message with an explicit degraded document and `do_not_submit=true`.

If Slack itself is disconnected and cannot update the message, the stale `relay_checked_at`/message age is the failure signal to the Sol Skillpack.

## 7. Relay connection/reconciliation state

Command transport has explicit state, conceptually:

```text
NOT_INSTALLED
DISCONNECTED
CONNECTED
RECONCILING
READY
```

After a Socket Mode reconnect, the Relay does not accept new modifying work merely because a WebSocket exists. It first completes bounded history reconciliation and only then becomes command-ready.

`SOL_STATE` may still publish current Executive diagnostic truth while command transport is not ready; `do_not_submit` remains true.

## 8. Slack command discriminator

When B2 is eventually implemented, a top-level command message begins exactly:

```text
EXECOS/CEO_REQUEST_V1
```

followed by one JSON object carrying only the accepted high-level request vocabulary.

A bot mention is not required and is not part of the discriminator. The transport should not depend on Slack mention rewriting for executable bytes.

A candidate command requires all transport identity checks, including exact workspace/app/channel/sender identity, top-level message creation, no thread parent, no bot identity and no unsupported subtype.

Slack identity is provenance/eligibility only. Executive authority is still derived inside the canonical control plane.

## 9. Slack protocol ACK versus Executive receipt

Socket Mode envelope acknowledgement is transport flow control only:

```text
Slack ACK
  != Relay acceptance
  != Executive canonical admission
  != dispatch
  != running
  != completion
```

Relay protocol handler acknowledges Slack promptly, then performs bounded business processing.

A user-visible canonical receipt is posted only after Executive status/submit returns a canonical result.

## 10. Storeless command recovery

The Relay creates no durable replay cursor or command database.

Production config/readiness receipt binds an immutable `bridge_epoch_ts` for the currently qualified installation epoch.

On startup/reconnect:

1. enter `RECONCILING`;
2. walk eligible command history from `bridge_epoch_ts` to now, oldest first;
3. exact-filter messages by channel/sender/discriminator/schema;
4. derive deterministic `slack-*` intent identity;
5. reconcile exact Executive status;
6. if committed, restore/post the missing user-visible receipt;
7. if truly absent and still lawful, process according to the current grounding/replay law;
8. if history cannot be traversed completely, remain `RECONCILIATION_INCOMPLETE` and do not accept new writes.

Initial hard safety bounds:

* at most 10 history pages in one reconciliation;
* at most 1,000 eligible CEO command messages in one bridge epoch.

Exceeding a bound is not permission to skip older work. It is a fail-closed operator condition requiring a reviewed epoch rollover or other architecture decision.

An epoch rollover must prove all prior eligible operations are reconciled before changing the epoch. `bridge_epoch_ts` is not a hidden moving cursor.

## 11. Edit/delete law

Only the original top-level message-create event can originate a command candidate.

`message_changed` and `message_deleted` never modify Executive state.

Immediately before canonical submission begins, B2 may re-read the exact source message. If it was deleted or its text no longer matches the candidate, refuse the uncommitted request.

Once canonical synchronous submission begins, a later Slack edit/delete cannot cancel it. Client/transport abandonment does not safely cancel the underlying SQLite mutation. Canonical status wins.

Changed work requires a new message and new operation key.

## 12. Effect-unknown and modifying retry

No server-side cancellation claim is added around started canonical synchronous submission.

If the Relay loses the reply after mutation may have started:

```text
EFFECT_UNKNOWN
  -> derive same deterministic slack-* intent
  -> exact status reconciliation
```

V1 does not blindly retry a modifying submit from an ambiguous state.

If canonical status is unavailable/ambiguous, report uncertainty and remain fail-closed.

If true `not_found` is established, the same logical Slack workflow may re-read current state and decide whether a same-operation resubmit remains lawful.

No automatic failover to MCP, GitHub or another transport.

## 13. Dedicated Slack app / principal boundary

Production Relay uses one dedicated Mastermind Slack app/bot and one least-privilege host principal. Employee ChatGPT user credentials are not automation credentials.

Minimum conceptual Slack shape for the private-channel V1:

* Socket Mode application connection authority;
* private-channel history required for the exact configured channels;
* ability to post/update its own state/receipt messages;
* private-channel message event subscription required by B2.

No DMs, files, workspace administration, GitHub, Linear, SSH, provider, deploy or user-token impersonation authority belongs to the Relay.

The host principal:

* cannot connect to the broad Operator socket;
* cannot read Executive SQLite directly;
* cannot use worker/provider credentials;
* cannot mutate GitHub/Linear/Agent OS;
* cannot merge/deploy/service-control outside its own reviewed service lifecycle.

## 14. Channel security

Production target:

```text
#ceo-control-room   PRIVATE
#sol-runtime        PRIVATE
```

`#ceo-control-room` members: Chairman + approved Sol seats + Relay bot only.

`#sol-runtime` members: Chairman + approved Sol seats + Relay bot only.

Automatic official Linear/GitHub integrations are excluded from both.

Curated portfolio/build visibility belongs in `#build-events`.

## 15. Grounding churn law

V1 retains exact whole-repository Mastermind/Macro SHA grounding as frozen by the existing CEO-intent architecture.

Do not invent a selective grounding epoch inside PR-A/F0 merely because Macro is high-churn.

The Sol Skillpack may compare **material decision-source artifacts** between the Executive-host grounding revision and newer remote state before deciding whether remote repository movement changes the commission. If only unrelated data/render/publication paths moved and the relevant current authority records are byte-identical, Sol may still act against the exact host grounding published by `SOL_STATE`.

The server still performs the accepted exact grounding equality / pre-commit movement checks.

Future v2 grounding architecture is earned only if production evidence shows material usability failure. Falsifier:

> If at least 3 of the first 20 legitimate CEO operations are refused solely because unrelated repository churn changed whole-repository grounding while all decision-source artifacts are byte-identical, commission a v2 authority-grounding design.

## 16. Revised downstream sequence

```text
PR-A / MAS-75
  -> S0 may run independently after F0
  -> Sol accepts PR-A
  -> R0 records-only state-read authorization
  -> B1 state projection + outbound SOL_STATE publisher
  -> C1 production private read proof
  -> require successful S0 as well
  -> B2 / MAS-102 inbound Socket Mode write transport
  -> C2 / MAS-101 production write canary
```

This supersedes the old monolithic `PR-B -> PR-C` sequencing instruction. It does not delete the useful least-privilege/idempotency/failure requirements preserved in those issues.

## 17. No-rebuild / no-arming boundary

F0 does not authorize:

* implementation of the R0 state frame before PR-A acceptance;
* `#sol-runtime` creation before the appropriate build/production wave;
* Slack app/token/host-principal installation;
* inbound CEO write processing;
* generic `#agent-dispatch`;
* new SQLite/store/cursor/inbox/dedupe persistence;
* worker execution or provider-auth repair;
* MCP public schema changes;
* production arming.

The purpose of this record is to freeze the post-PR-A architecture so each later PR can remain one independently useful capability.

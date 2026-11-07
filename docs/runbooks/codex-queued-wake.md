# Queued Codex attention through the existing Wake owner

## Capability and boundaries

`integrations/executive_wake/codex_queued_wake.py` implements the existing
`CodexAppServerWakeClient` contract for an explicitly bound native Codex queue.
The existing `CodexAppServerWakeDispatcher` consumes its typed observations.
The existing `dispatch_persisted_nudge` and `WakeLedgerRepository` retain all
reservation, concurrency, persistence, attempt and retry ownership. This module
introduces no transport ID, queue, connection manager, credential, session
registry, listener, task scheduler or default activation.

This is a source contribution to Executive messaging, not installation or a live
Web-to-native-to-parent receipt. It does not resolve the separate #1112 source
integration, authenticated reply reader selection, account enrollment or Web
return subscription. The OHF current-writer client remains unchanged. A shared
vendor queue does not make arbitrary spawned subagents direct-input eligible.

## Host composition contract

The authorized host must supply ALL of the following, not model-authored values:

1. One exact current `RuntimeBinding` with canonical native-session UUID, Codex
   reasoning surface, account label and durable binding identity/generation.
2. An existing version-qualified and authorized App Server connection. The `rpc`
   callback accepts a complete request frame and returns its matching complete
   response frame. The connection owner retains handshake, authentication,
   request demultiplexing, bounded wire decoding and lifecycle. Do not create a
   replacement server, switch provider homes, or resume the target in another
   process to satisfy this interface.
3. A mandatory `guard(binding, nudge_id, opaque_ids)` callback returning exactly
   `True` (or an awaitable of it). It must verify the actual current native owner,
   account/host/connection identity, inbound/archive/permission policy, exact
   original reservation and the complete opaque obligation/attempt-command set.
   A constant True callback is a test fixture, never production authorization.
   An observation guard is not an atomic native writer fence: the actual host
   still enforces that fence at its RPC submission boundary.
4. The existing Wake reservation, persisted before any provider call. Normal
   integration goes through `dispatch_persisted_nudge`; calling this client
   directly is not a replacement for that owner or its compare-and-swap rules.

Select this client explicitly only for the qualified native queue route. Do not
change the global Codex transport descriptor or replace the OHF current-writer
client for already-owned worker generations. Constructor success, a reachable
socket, saved-thread presence and CLI help output are not activation receipts.

## Wire and identity

There is one modifying operation: `thread/queue/add`, with exactly `threadId`,
`clientUserMessageId`, and one text input. The input contains the existing fixed
Wake instruction plus canonical nudge and opaque identity references. It is not
a new task specification and grants no authority. The text input includes the
upstream `text_elements: []` field.

`clientUserMessageId` is the existing canonical `NUDGE-...` identity. It is stable
across reconstruction and does not depend on arrival time or provider response.
It is a CORRELATION value, not an assumed vendor idempotency key. The native CLI
creates a new client message ID per invocation; this client does not invoke that
CLI or rely on repeated queue insertion being deduplicated. Even a stable ID may
be inserted twice by a caller bypassing the existing Wake reservation. Tests
prove that the real existing reservation permits only one insertion.

The only recovery operation is `thread/queue/list`, scoped to the same native
session. A finite page/row/byte/time budget is enforced. Echoed IDs and the whole
input must agree; repeated rows, multiple matches, changed input, malformed
pagination and incomplete scans refuse. Returned vendor data is detached before
awaited post-read checks. No unrelated queue content or private error message is
returned to the caller.

No `thread/start`, `thread/resume`, `thread/queue/start`, `turn/steer`, update,
delete, fallback transport or provider override can be issued by this module.

## Effect and recovery semantics

| Observation | Result | Permitted next action |
| --- | --- | --- |
| Invalid identity/instruction or guard refuses before RPC entry | `WakePreSubmitError` | Existing owner handles the exact pre-submit outcome. |
| Matching queue-add receipt and current post-send guard | `ACCEPTED`, delivered=false | Await native evidence through its existing owner; do not add again. |
| Lost/malformed/oversized send reply, timeout after entry, or post-send revocation | `WakeEffectUnknownError` | Reconcile the original operation without another add. |
| Exactly one matching row in a complete bounded queue read | `ACCEPTED`, delivered=false | Observation only; no target ACK or parent-consumption upgrade. |
| Missing row, partial page set, changed payload or ambiguous match | Unknown/unresolved | Preserve the original effect; no automatic resend or target substitution. |
| Cancellation | Propagated | Existing persisted attempt remains the recovery authority. |

A missing queue item can mean that it was consumed or deleted. Absence therefore
cannot establish that the original send never happened. The adapter never mints
an ACK projection. Even a successful queue receipt does not prove that the
native session has started a turn, completed useful work, replied, or that the
original Web parent consumed that reply.

For an unfinished persisted attempt, the current Wake owner intentionally
returns reconciliation-required without automatically invoking the provider.
This client's read-only recovery can supply evidence, but it does not mutate
that ledger or bypass its resolution policy. An accepted persisted attempt may
use the existing dispatcher's reconciliation path; that path still cannot send
another queue-add. The independent native ACK/parent-consumption contracts remain
unchanged.

## Source and validation provenance

Source operation: `executive-codex-queue-wake-20261003-c3-001`.
Procedure/base: `bdf2a972e68a70270c24d4b5d61a4d60edc4f288`.
Parent implementation: Mastermind #1112; native-route evidence comment5947880900.
No held #1112 file or original source branch is changed by this contribution.

Protocol reference: OpenAI Codex tag `rust-v0.159.3`,
`codex-rs/app-server-protocol/src/protocol/v2/thread.rs`, blob
`2e166d5506b10996e2da286feb6082d6b8711340` (queue add/list structures).
`schema/typescript/v2/QueuedSubmission.ts`, blob
`f364b8c0deb5347ef98a1ecc1388bd7d11c304c1`, and `UserInput.ts`, blob
`390d9dd59c931e5f1bba2bdff7078766a8f99cd4`, specify the returned and input shapes.
The version-qualified queue source does not supply the host's authorization or
prove a particular installed target is eligible.

Tests:

```sh
python3 -B -m pytest -q -p no:randomly \
  tests/test_codex_queued_wake.py \
  tests/test_codex_queued_wake_persistence.py \
  tests/test_codex_queued_wake_wire.py \
  tests/test_codex_app_server_wake_dispatcher.py \
  tests/test_codex_app_server_wake_rpc.py \
  tests/test_executive_wake_persisted_dispatch.py
```

The persistence tests use the real temporary Runtime/Wake repository and
coordinator, with only provider/current-binding observations faked. The wire
tests use a real local Unix WebSocket and fake vendor implementation; they do
not contact a production socket or native provider. Preserve this distinction
when evaluating release and installed acceptance.

## Required installed acceptance

After independent source review and current release checks, the existing
installation owner must select a qualified original native binding/connection
and real reservation guard. Use one bounded already-authorized message, verify
the exact native pickup, useful reply and original Web-parent consumption. Also
verify busy/archived/offline/revoked behavior, lost replies and reconstruction.
Do not upgrade account/fleet readiness or claim an instantaneous-delivery SLA
from source tests, queue acceptance or the vendor's polling interval.

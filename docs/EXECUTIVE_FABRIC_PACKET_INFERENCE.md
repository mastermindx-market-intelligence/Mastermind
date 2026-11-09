# Packet-only inference under the existing Fabric owner

`control_plane/fabric_packet_inference.py` supplies a bounded text-inference
primitive for draft #1337. It is not wired into the service factory and does not
make `attended-fabric` a production backend. Existing `BackendNotConfiguredError`,
cleanup and assignment-seal refusals remain in force.

## Enforced boundary

Trusted composition supplies a `PacketInferenceContract` from the original
Runtime Job/Attempt, effective grant, commission and claimed physical binding.
The admitted provider owner supplies its fixed `AttemptInferenceBinding` and
forwarder. The session must be that same Attempt and the protocol must be
Anthropic, matching the currently catalogued subscription profiles. No model,
account, host, URL, credential or additional request field can be selected by
the packet or provider response.

The owner supplies `claim_once(identity_bytes)`, using its **existing durable
Attempt fence**. It must compare current grant, route and the full canonical
identity before consuming first-use authority. Returning from a fabricated
callback is not admission. A reconstructed Python object does not prove unused
authority; the owner must refuse an already-used, uncertain or mismatched Attempt.
The in-memory lock only prevents concurrent/repeated use of the current object.
The callback is synchronous, returns `None` only after successful consumption,
and raises on refusal or uncertainty. Boolean verdicts and un-awaited coroutine
objects are rejected before provider forwarding.

The kernel builds a single fixed `messages` request with one plain-text user
packet, explicit model, token bound and streaming enabled. It offers no tool,
function, MCP, file, search, shell or code-execution capability. The forwarder
receives the existing credential-free `ProviderRequest`; provider credentials
remain inside the incumbent owner. The kernel neither retries nor selects a
different route after a refusal or ambiguous result.

The bounded stream is held until the provider receipt and complete Anthropic
text-event sequence validate. Tool-use blocks, unknown content types, thinking
blocks, duplicate JSON fields, changed model/route, truncated output, excessive
bytes and non-`end_turn` completion fail closed. This initial closed subset may
refuse otherwise valid provider features; support requires a reviewed extension,
not a permissive parser fallback. Returned text remains inert, including text
that looks like commands. No returned tool call is ever executed.

## Evidence and cancellation

The result includes canonical receipt bytes binding original lineage, request
and packet digests, physical route/generation, complete response digest/length
and delivered text digest/length. These are **inference evidence**, not producer
authentication. The existing owner must durably retain and independently read
back them and the exact result through its protected receipt channel. A hash
alone does not authenticate a caller or repair a legacy run's missing provenance.

`close()` disables future local calls and signals the original forwarder's
cancellation event. A shutdown receipt is unavailable while that call is still
in flight. After it returns, the receipt describes only local forwarding
shutdown. It explicitly does not prove provider-side cancellation, OS process
absence, shared-UID isolation, workspace access revocation or Worker assignment
revocation. A noncooperative forwarder remains an outer-owner timeout/recovery
obligation; the kernel does not create a timer service, task queue or process
controller to disguise it.

Cancellation observed before the owner claim avoids that claim. Once `execute()`
has entered its active section, shutdown can race an in-flight owner claim;
there is no claim rollback. A successful claim followed by cancellation before
provider forwarding is recorded as `OWNER_CLAIMED_PROVIDER_NOT_INVOKED`, not an
unconfirmed claim or reusable Attempt. Only the incumbent owner can reconcile
that durable effect. Local cancellation cannot atomically revoke remote authority.

## Remaining composition

This source is useful for a future admitted no-tools execution path. Current
subscription profiles require a supported harness and interactive execution;
they forbid unattended production backends. The existing Claude subscription
adapter is an `interactive_canary` with Read/Glob/Grep enabled. This kernel does
not change those policies, turn that adapter into packet-only execution, or
authorize a custom direct-HTTP subscription consumer.

To compose a real backend, the incumbent owners must supply:

1. An admitted exact provider/profile/harness route enforcing no model tools.
2. The real same-Attempt durable first-use fence and grant validation at effect.
3. A supported host launch owner producing actual process/boot/binary/profile
   facts. The bridge's own PID cannot substitute for a Worker process.
4. Original-owner collection, bounded validation and cancellation, with real
   per-run cleanup and an authenticated assignment-revocation producer/readback.
5. Retained original-parent result delivery and RuntimeBinding/Wake proof.

The bridge remains draft and unarmed until that composition is qualified. Tests
use inert forwarders and fake owner fences explicitly; they prove source
enforcement and failure behavior, not provider entitlement, installation,
authenticated Worker execution or native original-parent delivery.

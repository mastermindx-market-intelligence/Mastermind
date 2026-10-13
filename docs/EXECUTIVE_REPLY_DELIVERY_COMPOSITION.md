# Current authenticated reply delivery: executable source, installation still gated

`integrations/session_bridge/runtime_reply_delivery.py` supplies a concrete async
Runtime/Dialogue reply resolver and an explicit default-disabled host composition.
It does not install a listener, tool, native hook, account grant, token cache, watcher
or retry process. `build_runtime_reply_delivery` composes the existing read owner,
Runtime subscription store, current clock and existing `send_once` transport.

The private host entry `deliver_current(VerifiedPrincipal, subscription_id)` requires
the exact current principal from the existing JWT resource owner. It projects and
checks READ scope/lifetime using the existing edge/reader. It cannot authenticate a
model-supplied dict, reconstruct a current grant from stored owner digests, or promote
a native worker's identity into the original subscriber's authority. Reader tools
remain read-only and do not call this SEND entry.

The resolver looks up the immutable original request through the existing Runtime
owner, calls `RuntimeSessionReturn.resolve_read`, reads the exact canonical Dialogue
thread, validates one matching reply key/fingerprint, and re-resolves the full
binding after the awaited read. The resulting real transient `ReplyEventBinding`
feeds the existing synchronous projector. It does not use the fresh subscription
pregrant or current writer `_request` path for a committed reply. Original read
provenance remains usable after worker disarm/cleanup under the existing reader.

Delivery verifies the decrypted current subscription, owner/request/read reference,
expiry and CAS version. A stable reservation is written before external I/O. Current
principal, canonical event and subscription are checked again before the owned I/O
lane is selected. A busy executor can begin later, so READ lifetime, current store
version/expiry and rotation keys are checked and the packet signed on that actual
lane immediately before the one-shot HTTPS transport. The existing DNS/IP/TLS/body
validation and HTTP classification remain unchanged; no alternate peer or retry is
introduced. A revoke after actual send begins cannot cancel an already admitted
external effect and still uses its original reservation for settlement.

The result distinguishes NOT_SENT, EFFECT_UNKNOWN, the existing advisory HTTP
classification, and prior original-attempt state. No response body or signing key
is returned. A transport 2xx remains parent-unproven. Missing/lost observations never
permit a fresh send, including after subscription refresh. A signing grace that has
expired while queued is not used to sign the eventual packet.

Actual production wiring is not proven by this factory or injected tests. A real
background native-COMMIT consumer needs the installed service owner's genuine
current original-account authorization supplier and a lawful call of this entry.
Do not substitute an expired registration principal or worker identity. This source
has no admitted token refresh/cache or account lookup owner to invent. The original
JWT/current-account owner, private native-COMMIT host binding, storage-key custody,
installed service selection, real Work/dot callback, canonical reader invocation,
and parent adjudication remain distinct live gates.

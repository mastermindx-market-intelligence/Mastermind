# Optional principal App receiver

The receiver composes one authenticated App RULING with the existing canonical
source acquisition, Runtime COMMIT and Relay owners. It is default-off source
composition. The Control launcher selects this factory only when the explicit
boolean `coo_principal_dialogue_armed` and existing `coo_principal_armed` are
both true. The factory rechecks namespace custody and binds the same receiving
service and Runtime; it creates no extra listener or Runtime. This change does
not install a provider, enroll a principal, select
an account, add an HTTP/MCP tool, or arm the installed service.

## Required host selection

The incumbent release owner may explicitly supply
`CeoIngressAppBinding.principal_dialogue_provider_factory` at a qualified source
interval. The factory receives the service's existing Runtime and returns a
`PrincipalDialogueAppReceiver` constructed with the existing `CooHostProvider`,
Relay socket path and `HostLocalDialogueObservationReader(service, runtime)`.
The reader requires the exact existing Control service and Runtime, calls its
canonical snapshot reader/reducer, and shares the socket client's strict result
decoder. A selected custom observation facts provider is refused at construction
and on both sides of the physical read; the only admitted provider is the
canonical Runtime reader. It has no Wake or reconciliation methods. It refuses
a replaced Runtime
or closing/not-ready service before and after the physical read. Acquisition and
the COMMIT fence additionally require that exact same Runtime.

Production Control UID 450 cannot connect to the observation socket admitted
only for Agent Relay UID 457. The host-local reader opens no observation socket
and changes no UID/ACL/listener. The request still reads and commits through the
existing Agent Relay source socket. The observation listener readiness flag
tracks that separate socket, so it does not gate an in-process read. Local reads
require current Runtime identity, ingress readiness and READY/AWAITING_CANARY
service state even when the observation socket is absent or not listening. The
existing Unix observation client remains
supported for its eligible Relay host and isolated source fixtures. Dependencies
belong to the installed host and authority generation, never frame arguments.

Selection requires the existing shared `principal_admission_armed` capability
and the factory selected by the separate launcher opt-in above. Neither flag
is a principal authority grant. The ordinary `principal_admission_guard` accepts the bounded-intent schema, so it is not called
with a RULING frame. For this route the receiver's exact `CooHostProvider` invokes
the existing `guard_dialogue` during acquisition and inside COMMIT, validating
current principal, mission, root, capability and owed turn. Host selection must
compose this provider; the arming bit alone is not principal authorization. The kernel
peer must match the current App binding. C1 retains its existing capability set;
the RULING schema remains absent from `executive_ceo_ingress.PRINCIPAL_SCHEMAS`.
Missing selection fails before acquisition. No installed launcher configuration
is modified by accepting this source change.

The receiving service captures the current COO execution binding through
`_require_coo_admission_binding`, preserving the attended foreground qualification
check and pins the returned qualification across the entire request. Its synchronous
request guard checks binding identity, arming, lifecycle, readiness, qualification
and current execution binding. The acquisition factory invokes that
guard before and after awaited source reads; the existing Runtime owner invokes
it inside its sole COMMIT transaction, alongside current principal authority and
the original Wake anchor. The service checks again before returning a response.
A `None` qualification is
valid for ordinary placements and preserves existing admission policy. A finite
attended placement requires its actual live foreground request; App ingress
does not manufacture one. Tests cover a real typed qualification in an explicit
foreground fixture, a change after source reading, a change inside the COMMIT
transaction, and a missing foreground owner. Both changes and missing owner
produce zero new Runtime events and zero Relay posts.

## Wire and outcome contract

The exact selected App schema uses the shared 32 KiB request and 64 KiB inner
principal-result limits. Its outer transport permits exactly 21 additional bytes
for the compact `{"ok":true,"result":...}` wrapper, including the same one newline.
Both serializers use UTF-8 without ASCII escaping. The common protocol owns this
derived bound; the client and service use it only for the exact selected schema.
Other non-release frames retain their existing limits. The original raw
request reaches the strict decoder, so duplicate keys, nonfinite values, foreign
fields and invalid roles cannot be normalized away before validation.

The App helper derives its caller from the original signed request and current
mission, rechecks authentication, then sends exactly once over the configured
CeoIngress socket. It rechecks authentication before exposing the returned
principal result. It does not reacquire a mission after a successful ruling,
which can legitimately change the owed turn.

Any opaque service refusal or withheld response after sending is conservatively
uncertain: the transport does not assert a pre-effect phase that the receiver has
not proved. Decode refusals and post-COMMIT failures share that fixed error. The App
retains the original obligation id. It must not replay, rebuild the acquisition
factory as recovery, select another worker, or treat an absent response as proof
of no effect. The original recovery owner in
`PrincipalDialogueRuntimeCommitOwner.reconcile_obligation` remains read-only;
this patch adds no public recovery RPC.

## Qualification and release boundary

The receiver patch is prepared against frozen #1391 source
`a21c06bd20bae9f6b89d12d9d23f838e66f12298`, with the current seven-file #1455 delta at
`ff5d06c969513197727d55b79dbbb13cb80977b8` against protected
`4c64aec43f9817016f6e0b06b50a45cdc520b04e`, and the separately reviewed App forwarder.
The dependency-boundary assertion is included once in that dependency patch;
the separate journey-only companion contains no duplicate assertion repair.
Its source tests exercise a real local Unix service and kernel App-peer selection,
synthetic signed JWTs, canonical mission reduction, and the real local
Runtime/Wake/Relay owners. The original worker consumes the recorded RULING.
Provider/account facts, Slack storage and service enrollment remain fixtures.

The release owner must compose against the next qualified source interval,
preserve any intervening #1391 changes, and qualify actual producer delivery,
installed provider selection, current account/mission enrollment and real
original-parent consumption. Local source tests and an apply-checkable patch do
not satisfy those installed and live obligations.

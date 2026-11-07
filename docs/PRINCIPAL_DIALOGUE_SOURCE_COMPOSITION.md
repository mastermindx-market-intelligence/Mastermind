# Principal dialogue source composition

These adapters connect existing authority and source owners. They do not install
a principal, create a mission or grant, or expose another App tool. The App owns
authenticated request handling; Executive Control owns Runtime and the final
effect fence. Passing a Runtime object into the App is not this composition.

## Acquire the caller and original source

`CooApp.resolve_principal_dialogue_caller(request, work_ref=..., reasoning_surface=...)`
is an internal authenticated-request helper. It uses the existing signed bearer,
enrolled principal binding, authority and mission readers. The reasoning surface
is descriptive metadata. It cannot authenticate a caller or select a mission.
The helper requires the current governed-orchestration action, open effect gate
and COO accountable/owed seats, and rereads these facts after awaited work.

`read_principal_dialogue_obligation` reads one exact original obligation from
the existing Wake ledger inside an already-authorized work/root scope. It retains
the physical message anchor. Attention acknowledgement is not source resolution.
This helper requires a COO-targeted obligation; it does not turn an existing
CEO-targeted worker-return obligation into a COO principal route.

`read_principal_source` performs one `status` and one
`read_exact_canonical_thread` operation on the existing Relay socket. The
authenticated host supplies the already-minted `PhysicalDialogueSourceIdentity`
from Wake/Executive, never a Slack search result or a model-selected thread.
The exact read checks the actual workspace/channel, physical thread timestamp,
Relay-authored unedited V2 parent, complete parent identity, expected parent
fingerprint, original message key/fingerprint and a bounded mutation-complete
`conversations.replies` history. It does not require a complete history of
unrelated `#agent-dispatch` traffic; it does **not** assert that no other channel
thread can carry a matching parent. The trusted source owner is responsible
for the authoritative physical anchor, and the original channel-wide discovery
and thread-creation paths are left unchanged.

The parent and classified thread come from the **same** exact thread read, with
one sealed response; there is no parent-read/second-thread-read drift window.
A missing, duplicate, edited, deleted, misattributed, wrongly rooted, partially
read or fingerprint-inconsistent parent refuses. All mutation evidence in the
bounded thread refuses, including an edit or deletion whose original created
text the Relay could reconstruct. The frozen result never chooses the latest
message and is only detached evidence: it asserts neither caller authority nor
an unresolved decision nor a current worker attempt. No new Slack scopes,
credential, writer, retry, lifecycle, source registry or alternate carrier exist.

`read_current_principal_source` first checks the authenticated caller against the
host's read context before any source I/O. It joins that Relay observation to one
read from the existing Executive observation client, requiring the same physical
candidate, parent, thread, worker and current attempt. It converts frozen Relay
values back to the existing canonical JSON shape before the binding reducer. A
changed source or epoch refuses; no alternate thread, child or principal is
selected. The result still does not prove that the original request remains
unresolved, and it is not a reusable authority lease.

`require_unanswered_principal_decision` checks that the acquired original source
is still the single unresolved worker `DECISION_REQUEST`. It reuses the existing
semantic history reducer. Quiet updates from that worker preserve the original
request; an answer, fork, another material return, mutation or changed identity
refuses. Both Wake target flags stay false and no attention is created, including
for a foreground thread with watching disabled. This predicate is deliberately
limited to decision requests; it is not a general permission to continue or stop.

`acquire_principal_decision_source` composes these reads for an already
authenticated host. It first checks the actual receiving `CooHostProvider`, then
derives the context from the exact COO-targeted obligation, immutable root
creation source and current child delegation/attempt. It accepts no request-built
physical-source or context object. After Relay and Executive observations, it
checks the unanswered request and rereads the original anchor, context and
authority. The returned decision source can be passed to the fresh effect fence
below; the acquisition itself reserves nothing and sends nothing. An absent or
CEO-targeted obligation still refuses and does not create a principal route.

The canonical turn watcher recognizes accepted COO-principal commands against
the exact worker and trusted root. A principal STOP is consumed only by that
worker's ACK. Existing worker-return targets and source/route grants remain
unchanged; recognizing a command is not enrolling a new principal attention route.

## Carry the authenticated caller to Control

`company_dialogue_principal_app_contract` defines a closed candidate frame for
RULING, one original obligation and the App-derived caller facts. It reuses the
bounded strict JSON framing and the principal tool argument validator. The frame
contains no Runtime object, physical source, child selector or source observation.
Decoding produces detached data; it does not authenticate that data. Its schema
is deliberately absent from the existing ingress allowlist. The existing service
owner must explicitly compose its actual App peer, current binding and admission
checks before admitting this frame. The existing submit/status schemas cannot
be used to forward arbitrary Company Dialogue calls.

`build_acquired_principal_decision_host` then composes canonical acquisition with
the existing RULING source fence. Its required `receiving_request_guard` is a
synchronous callable supplied by that actual service composition, never a frame
field. It rechecks the exact request's peer/binding/admission before and after
awaited acquisition, and around the current authority and original-obligation
checks inside Runtime's COMMIT transaction. Source resolution after acquisition
refuses; attention ACK alone remains compatible. Returned binding mappings are
detached from the resolver's retained snapshot on every resolution.

The principal argument validator also enforces the enum values in its published
tool schema before binding resolution. The shared Dialogue body contract supports
additional authority classes, which does not make those values part of this
bounded COO tool's input contract.

## Preserve the final effect boundary

An optional `principal_decision_source` binds already acquired caller, context,
original physical source and Executive observation client to the host. It
requires the receiving authority guard. In the actual gateway pre-COMMIT
callback, `PrincipalDecisionSourceFence` reacquires the exact Relay and current
Runtime observations, checks the unanswered decision, and supplies the complete
fresh binding to the existing Runtime owner. No await follows the source
validation before that owner runs. A changed resolver binding refuses. This
explicit composition admits RULING only; CONTINUE and STOP require separately
qualified source families and cannot skip the fence.

Relay adjudicates each new principal reply using its existing trusted authority
policy before preparing the send and again immediately before posting. The
original request must exist, its option must be offered, its authority floor
must permit the ruling, and no earlier disposition may answer the same request.
Exact existing-message reconciliation precedes these new-write checks. A policy
change after Runtime COMMIT-start can still cause Relay refusal; the original
Runtime event and reconciliation identity remain, without a replacement send.

The existing principal host accepts `principal_authority_guard=coo_host.guard_dialogue`.
This receiving-side guard rereads the installed enrolled source and current
mission. The Runtime COMMIT owner invokes it synchronously inside the same write
transaction that checks the current child/lease/quota and records the original
COMMIT-start event. Revocation, a changed root/profile/generation, a reserved turn
or an owner failure refuses before the event is recorded. Async guards refuse.
The host imports only `Runtime` and the canonical `PrincipalAdmissionContext`
value object from the control plane. The latter is required by the receiving
guard's exact-type check; this seam does not import envelope builders. The
dependency test pins both module and symbol boundaries, while the MCP adapters
remain independent of Runtime, storage, process and Wake implementations.

The transaction also fences the original child request, not only the outgoing
message key. A second authenticated surface or a principal-generation change
cannot create another disposition for that same child/request. An uncertain
first send retains its original message key and read-only reconciliation path.

The optional product-acceptance parameters, `request_binding_resolver` and
`product_acceptance_macro_root`, compose alongside this guard. Their source,
independent review, ruling and original-parent consumption requirements remain
those in [Source-bound product acceptance](PRODUCT_ACCEPTANCE_REVIEW.md).

## Recovering a lost App response

The App knows the original obligation before sending a ruling, even when it
never receives the resulting message key. The existing Runtime COMMIT owner
therefore exposes `reconcile_obligation`. The authenticated receiving host
supplies that obligation, original principal context and root, and a mandatory
synchronous guard for current read permission. This guard is separate from
new-effect arming; it must still enforce the actual App peer and permitted
caller scope. Serialized facts never supply that permission.

Recovery reads the original, causally validated Wake anchor, including after
`SOURCE_RESOLVED`, then selects the exact retained COMMIT for that original
child, attempt, worker, request, thread and operation. Principal, generation,
mission, work and root must match. The same COMMIT owner reconciles the retained
message key against the original Relay carrier. No new-effect guard, current
send-binding resolver, source acquisition, write or retry runs. Current read
permission is checked again after the awaited carrier read.

An absent matching COMMIT returns `None`: nothing matching was observed at that
instant. It does not prove an in-flight request stopped and never authorizes a
replay. A retained COMMIT with uncertain delivery remains `EFFECT_UNKNOWN`.
Recovery does not grant a successor access to a predecessor's records or
silently translate authority generations. The original unresolved-source reader
continues to reject resolved sources for all fresh sends.

This is an internal receiving-owner method. A public recovery frame, explicit
service admission and authenticated App route still require their own
composition and qualification.

## Remaining installed qualification

The existing App client selects the canonical 32 KiB request and 64 KiB
response ceilings only for a fully validated principal ruling frame. Older
schemas retain their existing transport limits. This supports larger valid
Chinese rulings and evidence lists without changing general ingress budgets.
The receiving service must separately select and enforce the same exact-schema
limits when its owner admits the route; client serialization does not enable
that route or authenticate its peer.

The installed host must authenticate the App-to-Control request on the existing
allowed peer boundary, select this canonical acquisition for an eligible
COO-targeted obligation, and compose the explicit fresh decision-source fence
described above.
These read adapters do not create that installed request frame or its admission.
The existing foreground route can be qualified without claiming an idle Wake;
the separate principal attention route still needs actual source/target evidence.

Tests using the real Relay service with an in-memory Slack transport establish
source and wire behavior. Tests using signed synthetic JWTs, typed observation
fixtures and temporary Runtime stores establish their stated local contracts.
None establishes enrolled-account delivery, a live worker consuming a ruling,
the principal's judgment on actual artifacts, Office presentation or the R2
seven-day installed campaign. Protected publication, installation and those
observed outcomes require their own evidence.

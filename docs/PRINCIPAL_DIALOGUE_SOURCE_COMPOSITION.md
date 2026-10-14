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

`read_principal_source` performs one `status`, `read_bound_parent` and
`read_thread` operation on the same existing Relay socket. It checks the actual
workspace/channel, Relay parent attestation, parent identity and exact original
message key/fingerprint. It refuses thread mutation evidence, including an edit
or deletion whose original created text the Relay can reconstruct. It never
chooses the latest message. Its frozen result
is a detached observation; it asserts neither caller authority nor an unresolved
decision nor a current worker attempt.

`read_current_principal_source` first checks the authenticated caller against the
host's read context before any source I/O. It joins that Relay observation to one
read from the existing Executive observation client, requiring the same physical
candidate, parent, thread, worker and current attempt. It converts frozen Relay
values back to the existing canonical JSON shape before the binding reducer. A
changed source or epoch refuses; no alternate thread, child or principal is
selected. The result still does not prove that the original request remains
unresolved, and it is not a reusable authority lease.

## Preserve the final effect boundary

The existing principal host accepts `principal_authority_guard=coo_host.guard_dialogue`.
This receiving-side guard rereads the installed enrolled source and current
mission. The Runtime COMMIT owner invokes it synchronously inside the same write
transaction that checks the current child/lease/quota and records the original
COMMIT-start event. Revocation, a changed root/profile/generation, a reserved turn
or an owner failure refuses before the event is recorded. Async guards refuse.

The transaction also fences the original child request, not only the outgoing
message key. A second authenticated surface or a principal-generation change
cannot create another disposition for that same child/request. An uncertain
first send retains its original message key and read-only reconciliation path.

The optional product-acceptance parameters, `request_binding_resolver` and
`product_acceptance_macro_root`, compose alongside this guard. Their source,
independent review, ruling and original-parent consumption requirements remain
those in [Source-bound product acceptance](PRODUCT_ACCEPTANCE_REVIEW.md).

## Remaining installed qualification

The complete host must acquire each physical identity from its canonical owner,
authenticate the App-to-Control request on the existing allowed peer boundary,
and compose fresh current-source and unresolved-request validation at COMMIT.
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

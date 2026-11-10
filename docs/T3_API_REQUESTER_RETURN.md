# T3 API requester return

The source profile `principal.t3-api.executive-coo.requester-return.v1` is an
explicit, disabled alternative for an ordinary authenticated T3 MCP caller.
It uses the existing Executive COO OAuth connection and the existing
`coo.requester_return.v1` catalogue. It does not identify a native T3 project,
thread, run, tool call or parent, and it is not a Hermes native publication.

## Existing owners and exact grant

The capability registry owns the distinct grant
`mastermind-executive-coo-t3-api-requester-return-v1`. Its seven tools have the
existing requester-return schema digest
`29d6f504b79e806feefed6ab16f413338dd267de5019c7590fdc3655765537e3`.
`CooInstalledSource` selects this catalogue only for that exact profile/grant
pair and the current authenticated binding. The installed mission must carry
the matching enabled profile digest and explicit
`acknowledge_selected_child_result` action. A stale digest, another principal,
another catalogue, or a removed action does not inherit acknowledgment rights.

The source profile remains disabled and `production_armed` remains false.
All earlier profile and grant entries are preserved. Existing enrolled
profiles do not acquire this catalogue on source upgrade. Source publication
alone does not enroll a caller, enable a mission, acquire an OAuth token or
activate the service.

This catalogue uses the single Executive OAuth resource. It does not contain
`executive_project_help` or a current-DATA context tool, and does not need the
Workspace companion bearer required by the separate project-help contract.
The two source profiles cannot be combined under one installed principal
catalogue. The caller's actual enrollment and OAuth custody remain necessary.

## Admitted child and explicit result review

The existing host freezes an `ExecutiveSelectedChildTarget`. The model names
only its original command with `mmx_delegate`; it cannot supply a new root,
child, ordinal, requester identity or grant. The existing Control owner then
reproves the current target and source authority and performs its existing
claim. The claim transaction retains the original `coo_api_principal` family,
principal/mission/profile digests, original root, actual immediate parent and
selected child. A nested child uses its admitted coordinator's command while
retaining the original root's accounting.

The ordinary model-visible flow is:

1. Invoke `selected_child_submit` with the host-frozen command.
2. Invoke `selected_child_status` on that same command. A completed response
   must include the canonical result and its `requester_return` descriptor.
3. Review that result. If the requester deliberately acknowledges it, invoke
   `acknowledge_result` with the original command and the entire exact
   `requester_return` descriptor returned by status.
4. Read the same command to reconcile its retained receipt if the response
   was lost. Do not replace the command or blindly resend an uncertain ACK.

Status never acknowledges a result automatically. The existing Runtime owner
validates the original claim and the canonical sealed result inside its
existing event transaction. Concurrent identical acknowledgments retain one
receipt. The receipt is acknowledgment by the original API requester:
`parent_consumed` remains false and `acceptance` remains `not_accepted`.
Native-parent consumption, review and product acceptance keep their existing
owners and fences.

## Qualification

`tests/test_t3_api_requester_contract.py` exercises the actual registry,
installed source and signed OAuth/MCP factory, including a single-resource
`ClientSession` negotiation and legacy configuration preservation.

`tests/test_t3_api_requester_ingress.py` requires the incumbent Unix-socket
test capability. It reaches the existing signed App, actual Control service,
admitted child claim, canonical completion and explicit ACK transaction at
depths one through three. It also checks stale source authority, a removed
action, a foreign authenticated caller, changed result digests, concurrent
ACKs and original-command reconciliation after a lost response. Its physical
provider and Mission input are disposable fixtures; it launches no model and
does not qualify a production T3 enrollment or native origin.

# Original COO API-requester result acknowledgment

The selected-child path can retain the original authenticated COO API requester
in the existing Runtime claim and later record that requester's explicit
acknowledgment of the exact reviewed result. The existing Control service remains
the dispatch owner. The same `Job`, `Attempt`, command, result seal and event
transaction remain authoritative throughout.

This feature is an optional source contract. It does not enroll a principal,
enable a profile, install a native plugin, or activate an installed service.

## Qualified contract

The original seven COO tool names remain unchanged. The alternate catalogue
`coo.requester_return.v1` extends only `mmx_delegate` with the explicit action
`acknowledge_result`. Its capability-bearing tools/schema digest is
`29d6f504b79e806feefed6ab16f413338dd267de5019c7590fdc3655765537e3`.

The existing installed capability owner recognizes only the matching pair:

- Profile: `principal.hermes-native.executive-coo.requester-return.v1`.
- MCP grant: `mastermind-executive-coo-requester-return-v1`.
- Current mission action: `acknowledge_selected_child_result`.

The matching native consumer publication is
`mastermind.hermes_native_executive_consumer/v5`. It uses the existing closed
publication fields and exact tools/schema digest. A model argument cannot select
the catalogue or upgrade an older publication. Existing v1-v4 catalogues,
publication shapes, default profiles and installed configuration keep their
current behavior. A separately authorized installation must prove the actual
profile, mission action, captured MCP connection, plugin and native enrollment
before exposing the new native operation.

## Admission and result identity

When the current installed source qualifies this contract, the existing
`ExecutiveSelectedChildComposition` passes its private authenticated context into
the selected child's existing dispatch. At the canonical `JOB_CLAIMED`
transaction, Runtime retains an optional closed `selected_child_requester` field:

- The API principal binding digest, mission authority and authority generation.
- The exact capability profile digest and source work reference.
- The original root, immediate parent, selected Job, plan Attempt/digest/step,
  repair round, expected prior Attempt, frozen ordinal and original command.

The source work reference must already belong to the root's original admission.
It is not inferred from a later model call. Fresh admission and every original
provider/grant restriction remain in force. An old automatic or v1 claim keeps
the optional field absent, including replay under a newer host.

`selected_child_status` joins that retained claim to the incumbent canonical role
completion on one Runtime connection. A result descriptor is exposed only for
the same current authenticated context and profile. The descriptor contains
coordinates and digests, no credential. A descriptor's shape is not authority.
The canonical completion validator and terminal reducer remain the only source
of completion, including their independent review and native evidence rules.

## Explicit native consumer action

The qualified existing native `mmx_delegate` tool first reads the completed
result. Reading, startup qualification, tools/list, submission, and receipt
delivery do not acknowledge it. After review, the caller explicitly invokes:

```python
reviewed = mmx_delegate({"action": "selected_child_status", "command": original_command})
# Review the returned result before deliberately invoking acknowledgment.
acknowledgment = mmx_delegate({
    "action": "acknowledge_result",
    "command": original_command,
    "result": reviewed["requester_return"],
})
```

Here `result` is the complete closed descriptor from that reviewed observation.
The handler uses the
already captured native MCP owner, session, lock and loop. It rechecks the actual
native caller and current binding before the RPC and after the response.
The signed COO App and existing private Unix ingress independently re-prove the
installed API principal, target, mission, profile and action.

Runtime compares all immutable descriptor coordinates with the original claim
and current canonical completion. Under the existing transaction, it records one
`COO_SELECTED_CHILD_RESULT_ACKNOWLEDGED` event on the `coo_requester_return`
aggregate. The deterministic event command is
`coo-requester-consumed:<original-attempt-id>`. The event does not change a Job
lifecycle transition, spend budget, admit work, or dispatch another Attempt.
Concurrent exact invocations return the same original receipt.

The descriptor continues to report `parent_consumed: false` and
`acceptance: "not_accepted"`. This family acknowledges the original COO API
requester. It does not establish native T3 parent consumption, consultation
consumption, independent review, or product acceptance. A signed generic COO
principal does not attest native T3 thread/run/tool-call identity.

## Currentness and uncertainty

A changed or revoked principal, mission generation, capability profile,
descriptor, result seal or terminal digest cannot write a receipt. A guard that
fails before transaction commit rolls back the event. Malformed retained claims
or receipts fail closed; they are not repaired by adding a new requester or
issuing a replacement event.

An unresolved original dispatch must reconcile through its existing command
owner before acknowledgment. After a possible acknowledgment send, a lost or
malformed response is `EFFECT_UNKNOWN`; no layer automatically retries it.
Observe `selected_child_status` for the exact original command to determine
whether the original receipt committed. A changed native session or connection
does not retarget a pending operation. Explicit exact replay is idempotent once
the original current owner is proved again.

## Source qualification

`tests/test_coo_requester_return.py` exercises real Runtime admission, OHF result
seals, receipt transactions, concurrency, rollback, malformed retained evidence
and original-command recovery with inert physical execution.
`tests/test_coo_requester_return_contract.py` proves old contract digests, actual
installed-source profile matching, and explicit native consumer behavior.
`tests/test_coo_requester_return_app.py` qualifies the signed App edge with an
inert ingress response, without presenting that response as Runtime evidence.

`tests/test_coo_requester_return_ingress.py` is the composed proof: real MCP SDK
ClientSession and native consumer, signed App, existing Unix peer/control path,
actual claim and canonical result seal, explicit acknowledgment and original
readback. It requires the test environment's Unix-socket capability. Collection
or the other test layers do not substitute for running that proof. Actual
installed source, grant and native plugin activation remain separate evidence.

# Hermes delegation bridge (WP4)

Source-only adapter. `BUILT_NOT_PROVEN` / `PRODUCTION_INERT`. Importing this
package does not admit an Executive Job, start `fabric_task.py`, call Cursor,
or register a tool into the live Hermes profiles.

Hermes built-in toolset `delegation` and tool `delegate_task` stay disabled
(same disabled set as `integrations/hermes_qualification/preflight.py`). The
only delegation tool this package describes is `mmx_delegate` on toolset
`mmx_delegate`. It submits one bounded `implementation`, `watcher`, or
`computer_use` child after an injected Executive admission port accepts the
same carrier the caller named: Subagent Fabric (`fabric_task.py request`) or a
Cursor cloud agent. The parent-local ledger dedupes that child, cancels it
once, surfaces `UNKNOWN` without replay, keeps refusal text verbatim, and
refuses to move a refused or unknown child onto the other carrier.

**Model authority fence:** The Hermes-visible `mmx_delegate` advertises and
accepts only `submit`, `status`, `cancel`. It never accepts
`review` or `consume` (including forged raw handler calls), nor model-supplied
reviewer IDs, verdicts, hashes, or handoff coordinates. A model cannot invent
a second reviewer to approve its own work, read a protected worker result or
consume its original parent's return. This is enforced in the handler as well
as in the advertised tool schema.

Only the **trusted host-side** `Bridge.review` and `Bridge.consume`
methods represent source-fixture review/consumption. Review requires an
injected verification-only adapter to the *existing independent review owner*:
a genuine non-parent reviewer, exact idempotency key, parent/root/carrier,
verdict and sealed result SHA must all be confirmed. With no binding,
`Bridge.review` returns `INDEPENDENT_REVIEW_NOT_BOUND`; an invalid proof
returns `INDEPENDENT_REVIEW_UNVERIFIED`, a failed verifier returns a
fixed-code `REVIEW_OWNER_UNAVAILABLE` without private error text. In
addition, `Bridge.consume` requires an independently injected
verification-only adapter to the **existing Executive original-parent owner**,
binding the exact child key, parent/root identity, run, carrier and result SHA.
Unbound, refused and unavailable original-parent proof all fail closed
**before the carrier result is read**. A string equal to the recorded parent
ID is not authorization. No new review store, queue, principal or
authentication system exists here. Simulated verifier objects in unit tests
are **not** genuine independent approvals or real Executive admission, and
`Bridge.consume` is **not** canonical WorkerResult acceptance.

After a trusted host consumes the child, a public `mmx_delegate status`
still reports a bounded `CONSUMED` lifecycle state but never includes
`result_text`, `handoff` or `handoff_reason`. The result is revealed only
to an original-parent `Bridge.consume` call *after the existing parent
verification port succeeds*, including idempotent replay. A guessed key,
wrong parent, revoked binding or unavailable owner cannot recover the
already-consumed result. This is local defensive source qualification, not
authorization to expose live child results without the incumbent Executive
return and acceptance consumer.

The default admission port returns `EXECUTIVE_ADMISSION_NOT_BOUND`. Carrier
ports, independent review verification and original-parent owner verification
are all unbound. A consumed child
can carry an `agentos.handoff.v1` draft
for the existing Agent OS writer. This package does not write that store.
`model` must already be one of `fable`, `opus`, `sonnet`, `haiku`, `codex`,
`local`, or `sol`.

```sh
python3 -m unittest discover -s integrations/hermes_delegate/tests -v
python3 -m compileall -q integrations/hermes_delegate
```

## Existing Executive child observation

A trusted host can inject `ExecutiveChildQualification` and call
`Bridge.inspect_executive_binding()` to observe one actual admitted plan's
current work/repair child and current Attempt. This read-only diagnostic is
outside the model tool surface and does not enable admission or a carrier.
See [Executive binding](../../docs/hermes/EXECUTIVE_DELEGATION_BINDING.md) for
exact scope, canonical owners, verification and remaining live integration.

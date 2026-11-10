# Native Hermes → Mastermind Fabric

**Source status:** native plugin composition, profile enrollment, and server-side
origin and installed-package verification are implemented. The installed M2 profile is not enrolled
for worker execution by this change. No live worker START, paid-model inference,
terminal result, or product acceptance is claimed.

Application delivery remains under [#2175](https://github.com/mastermindx-market-intelligence/Mastermind/pull/2175)
and the existing primary-inference/H4 enrollment lane
[#2186](https://github.com/mastermindx-market-intelligence/Mastermind/pull/2186).
This package supplies their native attended-worker consumer. Program evidence
belongs to [#983](https://github.com/mastermindx-market-intelligence/Mastermind/issues/983).

## What is connected

The package is a native standalone Hermes plugin, `mastermind-fabric-worker`,
with the model-visible tool `mmx_fabric_worker`. Its normal `register(ctx)`
entry point uses the installed PluginManager, middleware, tool registry, MCP
client, active native parent, and SessionDB. It works independently of the
primary inference provider.

| Responsibility | Existing owner and binding |
| --- | --- |
| Current profile, session, turn and interruption | Hermes PluginContext and active AIAgent |
| Turn serialization and original conversation | Native SessionDB turn lease and compression lineage |
| Durable original tool intent | Native persisted assistant tool call and stable tool-call UID |
| Per-profile worker enrollment | Existing Hermes plugin settings and enrolled Fabric execution channel |
| Admission and original request reservation | Existing `fabric_task.request` retained request owner |
| AUTO routing, exact manual pins, quotas, placement, model choice | Existing Capacity Fabric and native adapter |
| Execution, continuation and retained result | Existing Fabric controller and original-run lifecycle |
| Result consumption | Native parent with current grant, matching root and parent, complete result digest |
| Acceptance and publication | Existing program/acceptance and protected delivery owners |

No additional session, queue, account, token, scheduler, or result ledger is
introduced.

The read-only durable-intent projection recognizes a direct worker call and the
canonical native lazy-broker envelope: one `tool_call` containing
`calls: [{name: "mmx_fabric_worker", arguments: {...}}]`. Both retain the
persisted **outer** call ID and its native durable UID. The frontend and
independent backend verifier share this projection; neither writes a synthetic
direct-call record. Local batches, nested wrappers and legacy argument coercions
are refused. Matching direct and wrapped intents share the same relevant-copy
bound, original-submit uniqueness and completed-result checks. Unrelated broker
history does not consume that bound.

## Actual native composition

`native_session.py` binds the actual installed native types. It requires an
attended local parent with a live durable turn lease and a persisted current
tool call. Delegated and unattended turns continue through their own admission
paths. The callback fails closed if the native scope, session generation,
interruption state, lease, persisted arguments, or plugin lifecycle changes.

Enrollment is explicit. The native profile must declare
`mastermind.hermes_native_enrollment.v1` before the plugin publishes a tool.
The first persisted, current invocation requires the existing execution facade
to attest that exact contract before any status, request or result operation.
This fits native startup, where plugin discovery precedes MCP initialization.
A plugin MCP allowlist entry supplies transport permission; the enrollment
contract additionally supplies the native-origin policy and stable namespace.

The root uses that namespace, the native profile, and the original native
conversation. It is a namespaced **Hermes attended origin**, never an asserted
Executive Job. The task run ID also includes the stable task key. Compression
and process restarts therefore retain the original logical run. Forked or reset
conversations use their native distinct origin.

The binding checks the persisted native occurrence before submission. Native
single-use dispatch and Fabric's retained exclusive request reservation remain
the actual effect fences. A transcript read or process-local flag is not
described as atomic durable admission.

The same existing Fabric facade has an optional native-scoped mode. Its sealed
backend verifies the selected release revision, native installer record and
closed runtime-file digest before invoking the fixed installed checker.
Its native-origin verifier then reads a bounded read-only projection of the
installed profile and SessionDB. It checks the profile, origin, live turn lease,
runtime generation, persisted call, exact packet, and manual-route grant before
any request effect, again after asynchronous preflight, and before releasing
status or result. Omitted origin metadata cannot turn this channel into a
general operator channel. The mode exposes only capabilities, request, status,
and result.

## Model-visible contract

`mmx_fabric_worker` (toolset `mmx_fabric`) accepts:

- `action: preview | submit | status | result`
- `task_key`: a stable lowercase logical task ID within the native conversation
- for preview or submit: `task_class`, `task_complexity`, and an optional
  factual `escalation_reason`
- for submit: a bounded `work_packet`; an optional pool/model choice only
  when the native profile grants that route

Root, parent, session, run ID, lease holder, host, account, credentials, shell
commands, review, and acceptance are not model-supplied fields.

AUTO is the default. The existing Capacity Fabric selects an eligible pool,
model and host using its policy and live admission state. Exact manual choices
require a profile grant and the incumbent adapter's strict-manual-pin support,
entitlement, availability and consent checks. Existing pre-task quota
continuation is preserved; ambiguous effects never authorize model switching
or task replay.

The preview action uses the installed read-only capacity MCP and its explicit
`PREVIEW_ONLY_NO_RESERVATION_OR_DISPATCH` proof. Both clients handle Hermes's
actual MCP normalization, which can remove duplicated structured content and
retain a single canonical JSON-text result. Preview makes no reservation and
can be unavailable independently of execution enrollment.

## Results, interruption and recovery

Status and result always address the original logical task. The existing typed
port verifies root and parent lineage, incumbent successor evidence, complete
response bytes and SHA-256. A result read does not approve or accept the task.

A controller receipt is not worker START. Lost, partial, detached or malformed
submit responses retain `EFFECT_UNKNOWN` and the original run. A remote
`NOT_FOUND` response alone does not authorize a second submit. A new native
turn cannot resubmit a task key whose earlier submit intent is already retained.

Native consent and currentness are rechecked after remote calls. If permission
changes after a valid submit receipt, only the recorded submission fact is
returned with response withheld and retry disabled. Revocation cannot convert
an effect into absence. Retained prelaunch refusals remain correlated evidence,
without invented worker lineage, retry authority, or accepted results.

Plugin unload revokes this local binding through native registration leases.
It does not claim to cancel a running worker.

## Deployment and qualification

See [NATIVE_ENROLLMENT.md](NATIVE_ENROLLMENT.md) for exact configuration,
installation ordering, source pins, commands and live acceptance obligations.
The package uses the existing native MCP client and existing Fabric backend;
the deployment supplies their qualified paths.

Canonical CI already imports the package tests through
`tests/test_hermes_attended_fabric.py`. The existing
`fabric-backend.test.mjs` CI step now also covers native-channel denial,
omitted-origin bypass, operator-action confinement, configuration completeness,
and disabled-by-default capability reporting.

The explicit `tests/native_owner_qualification.py` suite additionally uses the
installed native classes, SessionDB, real turn leases, middleware and registry.
Its broker cases invoke the original Hermes dispatcher with persisted outer
`tool_call` envelopes and unchanged identity/scope/middleware checks. Its wire
cases execute the actual Node facade and native read-only verifier. Only the
final Fabric command engine is substituted. These checks prove source
composition and recovery boundaries, not paid worker execution.

Prior source records remain in [CONTINUATION.md](CONTINUATION.md). They are
historical evidence; the native composition and enrollment described here
replace the earlier unbound host-composition sketch.

# Hierarchy-scoped Fabric coordination

## Status and consumer

This change implements an advisory coordination policy and integrates it with the
existing Company consultation gateway. It does not yet install or enable that
policy in the fleet. Capability: BUILT_NOT_PROVEN. Parent mission: incomplete.

The intended consumer is an admitted native/Fabric participant which needs to
ask a related participant an implementation question without obtaining authority
to redirect that participant's work. Public operations remain `company.peers`,
`company.consult`, `company.reply`, and `company.consultation`. No new public
endpoint, identity registry, message store, queue, credential, retry loop,
scheduler, or grant issuer is added.

## Implemented policy

| Relationship | Default advisory communication |
| --- | --- |
| Direct parent and child | Bidirectional within the same project, including explicitly collapsed hierarchy levels |
| Project CEO peers | Within the same tenant and portfolio, including different projects |
| COO peers | Within the same project |
| Task operator peers | Within the same project and workstream |
| Worker peers | Within the same project, workstream, and coordination group |
| Otherwise-separated same-rank peers | Only an exact-pair, topic-bound, bilateral dependency grant |
| Cross-tenant or cross-portfolio | Denied, including when a dependency grant is supplied |
| Unrelated cross-rank or self messaging | Denied |

A dependency grant is an observation supplied by the existing authorization
owner. It identifies both exact Runtime identities and binding generations,
both project approvals, topic, validity interval, and revocation. This module
cannot issue such a grant. Role names describe assigned responsibility, not
provider/model/host or command authority. Native provider choice does not change
the organizational policy.

A permitted exchange never grants operational authority or forwarding rights.
Task creation, reassignment, scope changes, approval, cancellation, spend and
release remain subject to their incumbent owners. Content is advisory data, not
an authorization channel; permission to ask a peer cannot launder an otherwise
denied effect. Existing consultation response/forwarding budgets remain intact.

## Source integration

`control_plane/fabric_coordination_policy.py` implements immutable, bounded
owner observations and a deterministic relation policy. Malformed, ambiguous,
expired, terminal, or stale identities fail closed. A snapshot is not a new
registry; it is a short-lived projection of canonical owner state.

`integrations/fabric_coordination.py` implements
`HierarchyScopedPeerResolver` and `HierarchyCompanyConsultationGateway`.
Discovery and direct sending use the same relation checks. Sending re-reads the
current observations after resolving the target and before invoking the existing
dispatcher. A generation change or grant revocation at that boundary prevents
dispatch. Replies and reads require exact consultation-party membership from
the existing consultation owner; only the original recipient may answer.
Request-local selection uses ContextVar and is cleared at the call boundary.

The existing gateway receives a private host-supplied pre-dispatch callback.
No new caller-controlled authorization fields enter the public schema. The
legacy peer resolver now validates discovery through its existing exact resolver
rather than letting `company.peers` bypass peer validation. The public tool
schema digest is unchanged.

## Non-negotiable trust boundary

Only the authenticated host may supply the caller identity, role/membership
observations, topic, grants and consultation parties. A model argument, arbitrary
JSON file, environment variable, PID hint, or self-declared role is not accepted
as authority. Python dataclass/type validation is structural validation, not
proof that an observation came from Runtime.

An authenticated Runtime-backed observation producer and its production host
composition remain to be connected. The new scoped gateway is an opt-in source
consumer; legacy host composition is not automatically enrolled by adding this
module. Existing exact-target resolution and commit fencing must remain in the
effect owner. The pre-dispatch check is not an atomic replacement for that fence.

The current exact selection covers job, attempt, worker, binding ID and binding
generation. Provider/program changes must obey the incumbent generation-change
invariant; this implementation does not independently prove that invariant.

## Live rollout still required

1. Connect one trusted owner observation producer to the existing authenticated
   Company consultation host. It must derive current role and project/workstream
   membership from admitted state, not guess them from model names, provider
   sessions, or Runtime execution-role strings.
2. Preserve exact target, transport, idempotency, commit and return owners. The
   dispatcher must validate current authorization at its own effect boundary.
   Add regression tests against that concrete composition, not only test doubles.
3. Expose the existing consultation client to selected workers through approved
   launch configuration. Do not expand the guarded Studio tool ceiling or use
   generic shell/SSH as a substitute messaging service.
4. Account for native messaging paths. An MCP-only policy cannot assert a
   complete boundary while unrestricted native messaging remains reachable.
   Any isolation/configuration change must preserve admitted native task/team
   communication and use the established configuration/release owner.
5. Review and release the exact protected source through the existing deployment
   path. Verify installed revision and effective configuration separately.
6. Run a real two-host, mixed-provider exchange on admitted Ubuntu workers.
   Demonstrate question and correlated answer consumption, revoked/foreign/stale
   rejections, no duplicate send after uncertain response, no work reassignment,
   and no newly spawned worker merely for message delivery.

Do not call transport success, a test double, a persisted question, a wake
request, or a merged PR proof of recipient consumption or work acceptance.

## Runtime-backed identity composition

`integrations/fabric_coordination_runtime.py` now supplies
`RuntimeCoordinationObservationSource` and `build_runtime_coordination_gateway`.
The source joins the authenticated host's organizational membership snapshot to
actual Executive Jobs, current Attempts and admitted harness bindings. It derives
opaque peer references from those identities instead of trusting a supplied peer
list. Parent lineage and program identity must match canonical Job facts. Missing,
replaced, inactive or unsupported Runtime identities cannot become live peers.

Runtime reads persist no events. The public current-harness reader receives the
same read connection as the identity join. Membership is checked again after the
join; a semantic change refuses the observation. Refreshing a timestamp cannot
extend the original snapshot's expiry. The digest covers actual membership and
grants as well as Runtime identity evidence. Native handles and account labels
are not projected.

The factory reuses the existing hierarchy gateway and dispatcher. It validates
caller membership, checks owner-supplied consultation parties against the actual
consultation INTENT, and retains per-send Runtime revalidation. It requires the
host's observed tool-schema digest rather than self-attesting a constant.

This is not an organizational assignment issuer or a caller-authentication
service. The production host must still supply its authenticated caller and
canonical membership/consultation readers. The factory does not create those
owners, enable a native transport, or replace commit-boundary authorization.
No production host has selected this factory yet.

The current canonical Runtime provider mapper at the pinned base recognizes
`chatgpt` and `openai-codex`; the consultation protocol and native transport must
also support a mapped surface. The native transport descriptor currently marks
`codex-app-server` implemented but not `claude-code-session`. Adding a role policy
or this identity join therefore does not prove mixed-provider delivery. Those
accepted-source native transport gaps remain explicit and were not switched on.

## Verification at the current source milestone

The latest October 11 Runtime-join continuation recorded **577 passed, zero
failures/errors, zero skipped** in the existing MCP-capable Python 3.12 environment.
This includes 24 new Runtime identity/factory cases, 73 hierarchy policy cases,
39 unit gateway cases, seven earlier composed journey cases, the frozen SDK
boundary tests, and existing consultation/host/identity/target/inbox/transport/MCP
regressions. Syntax parsing and `git diff --check` also passed. JUnit SHA256:
`cf341e062fa10bffbb45e7a3c5404d8dd13547600e0cc4678e7757afe906f45f`.

The new factory journey derives peer identities from actual temporary Runtime
records, then completes question, correlated reply and requester consumption
through the real dispatcher and local socket relay. Negative cases cover false
identities, parent/program mismatches, stale scopes, concurrent scope mutation,
unsupported provider mapping, unobserved tool schema, and sanitized owner failures.
Organizational membership and native-consumption signals remain synthetic inputs;
the production authenticated membership source is not thereby proven.

Hosted CI for the original candidate failed
`test_sdk_and_runtime_dependency_boundaries_are_exact`: the runtime integration
adapter had been placed in the frozen SDK package. It now lives at
`integrations/fabric_coordination.py`; its implementation bytes are unchanged.
The SDK package and its exact-boundary assertion were preserved, not relaxed.
A fresh hosted check is required for the repaired candidate.

`tests/test_fabric_coordination_journey.py` connects the hierarchy gateway to the
real Runtime consultation dispatcher, temporary Runtime/Wake records, and a real
local AF_UNIX relay. It verifies a correlated question/answer path after reopening
the Runtime, reply rejection before fixture consumption, idempotent answer and
consumption, no new Jobs merely for delivery, rejection before effects for foreign
or inactive peers, grant revocation at dispatch, and effect-unknown preservation
with read-only reconciliation after a simulated response loss.

Organizational roles, native-consumption signals, and Slack in that journey are
explicit fixtures. The existing unit gateway tests still use a fake dispatcher.
Neither set proves live model consumption, mixed-provider cross-host delivery,
production authentication/enrollment, or installation. No package installation or
dependency mutation was needed for verification.

## Recovery identity

Current authorized mission: implement and harden scoped hierarchy messaging
end to end. Source pin: `8339b60b867c82807dcdeeddd8d86e37e6e4434f` in protected
Mastermind master. Operation: `fabric-peer-messaging-20261010`.
Canonical workspace: `/Volumes/Mastermind/agent-workspaces/web/fabric-peer-messaging-20261010`.
Branch: `sol/web-fabric-peer-messaging-20261010`.

The installed Executive release observed during this work was
`326c8469a21d7f50fc9ecb1848196bf1c6e66685`, with a read-only Executive tool mode and
zero running Attempts in that Runtime. These observations do not imply that all
external pool workers were stopped or that every other action was unavailable.
No worker was dispatched, no live peer message was sent, and no fleet settings
or installed release were changed by this source milestone.

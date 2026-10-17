# Hierarchy-scoped Fabric coordination

## Status and consumer

This change implements an advisory coordination policy and integrates it with the
existing Company consultation gateway. It does not yet install or enable that
policy in the fleet. Capability: BUILT_NOT_PROVEN. Parent mission: incomplete.

**Two independent release gates prevent a circular stall:** Source review/merge
requires the current exact-head hosted checks, meaningful independent semantic
review, and source-level safety evidence. It does **not** require a previously
impossible installed fleet canary. Merge is not deployment, enrollment,
effect authorization, or production acceptance. A separate existing release
owner must verify installation permissions, pin the installed revision, select
the host composition and message-COMMIT fence, and prove real provider
consumption with two admitted Ubuntu workers before reporting
PROVEN_LIVE. This source author cannot mark that second gate complete.
Requesting source review may proceed without changing the latter gate.

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
owner. It identifies both exact admitted actor identities (Runtime Job/Attempt
bindings or authenticated native CEO/COO session generations), both project
approvals, topic, validity interval, and revocation. This module cannot issue
such a grant. Role names describe assigned responsibility, not provider/model/
host or command authority. Native provider choice does not change the
organizational policy.

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
caller membership and checks owner-supplied consultation parties against the
actual consultation INTENT, including the persisted recipient binding ID,
generation **and reasoning surface** against the current admitted harness
facts. A provider remap without a new binding cannot inherit an old question.
Per-send Runtime revalidation remains in place. The factory requires the
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

## Pure native CEO/COO hierarchy identity — source extension

`CoordinationNativeIdentity` is a distinct immutable owner-supplied actor
identity: canonical native session UUID, generation, host reference and
verified-principal reference. It never invents a Runtime Job or Attempt.
`CoordinationActorIdentity` permits it alongside the existing Runtime identity
within the **pure policy**, and `CoordinationParticipant.parent_identity` can
represent an exact native parent of an admitted child. This adds no session
discovery, provider wake, authentication owner or message transport.

Native identities are accepted only for PROJECT_CEO and COO roles, not worker or
task-operator self-enrollment. Native session duplicates (even across hosts, generations or principals),
invalid UUIDs, cross-project parentage, inverted role
hierarchy, expired grants and generation drift fail closed. Existing Runtime
parent_job_id checks, canonical Job/Attempt identity, and peer scopes are kept.
Only exact, owner-present actors can become peers; an asserted but absent parent
is not discoverable. No peer message grants operational or forwarding authority.

**Crucial separation:** the existing Company consultation wire
(`ConsultationPeer`, `HierarchyScopedPeerResolver`, and
`build_runtime_coordination_gateway`) still exclusively admits
`worker_attempt` actor refs and RuntimeBinding tuples; it is not a native
CEO/COO transport. The current worker Runtime adapter explicitly refuses a
snapshot containing a native actor rather than silently enabling a new caller
kind. An authenticated native host must separately attest and compose an
accepted native actor/transport with the *existing* Session Bridge and dialogue
owners. At the current protected master revision the source includes
`integrations/session_bridge/claude_native.py` and guarded native reply seams,
but no installed management-owner proof or supported Claude wake descriptor.
Do not widen a tool schema or mark a transport implemented based on policy tests.

## Read-only native Session Bridge owner join

`integrations/fabric_coordination_native.py` provides a deliberately
**read-only** `NativeCoordinationObservationSource`. It joins the exact current
native CEO/COO identities from owner-supplied membership to the incumbent
`ClaudeNativeTargetProjector`/Session Bridge management owner. The verified
session UUID, generation and host must agree. The authenticated host separately
supplies an exact verified-principal reference per native session; mismatches,
revocations, ambiguous sessions, expired membership, and any mid-read
membership/principal/management changes fail closed.

The result `NativeCoordinationAttestation` includes only verified **native**
identities; it does not claim that Runtime worker identities within the same
membership snapshot have been validated. Workers require the separate
`RuntimeCoordinationObservationSource`. The join is a reusable component, not
an installed native caller-authentication service, message producer, endpoint,
Session Bridge tool registration, or atomically fenced send. No direct native
socket and no provider-management send are invoked. Tests exercise a fake
already-admitted management port; the actual installed host must still inject
and prove its trusted management and verified-principal owners. This cannot
be labeled live cross-host CEO/COO↔worker messaging.

## Mixed native + Runtime observation (source proof)

`integrations/fabric_coordination_composite.py` composes the **existing**
Runtime worker identity join and Claude native management/verified-principal join
against one host-supplied organizational membership snapshot. It validates the
full CEO/COO/operator/worker hierarchy in the shared pure policy, then derives
a bounded `CompositeCoordinationEvidence` with verified native identities
and exact Runtime worker peer references. No synthetic Runtime Jobs, native
worker role self-enrollment, new registry, queue, provider endpoint or message
dispatch are created.

The composite owner checks source scope before and after the two existing
joins, re-reads current Runtime worker generation after the native join, and
re-attests the native session owner after that worker recheck. Exact native
session generation, verified principal and role must still agree. The final
membership read and clock must remain inside every observed expiry; the
returned evidence retains the shortest observed validity interval. Mid-read
role, scope, grant, native principal, session or worker changes fail closed.
**The reads are not atomic across two owners**, and the evidence is not a
bearer permission or authority to send; only the established effect owner
may authenticate the caller and commit a message after its own
current-writer/permission fence.

The existing four-tool Company consultation wire still only accepts
`worker_attempt` actors. Native CEO/COO-to-worker messaging requires the
production Session Bridge owner to implement and bind the corresponding
accepted native dialogue consumer. No fixture or source join automatically
publishes a new public tool or enables unsupported Claude wake.

## Scoped Session Bridge exact-target discovery (source only)

`integrations/fabric_coordination_targets.py` adds a **read-only**, opt-in
`ScopedSessionTargetResolver` over the existing
`RuntimeFabricTargetProjector` and `ClaudeNativeTargetProjector`.
Its authenticated host-provided caller is evaluated against the current mixed
native/Runtime evidence; exact current Session Bridge target references
(`fabric_attempt:<digest>` and `claude:<digest>`) are shown only when
the organization's existing hierarchy policy permits that advisory edge.
It never constructs an alternate target registry or selects a newest session.

Runtime target identity is tied to the current exact Job/Attempt/Worker,
harness epoch-derived binding ID and generation. Native target identity is
tied to the current session UUID, generation, host and independently attested
principal through the composite source. A target's native/worker owner is
rechecked, the organizational scope is re-observed, and exact target resolution
has no fallback after rotation or revocation. After the second owner observation,
a second Session Bridge projection must retain the exact target refs for every
permitted recipient; a physical dialogue-carrier rotation that preserves the
worker's Job/Attempt identity is still refused. Public projections omit native
session UUID, principal reference, provider token, account, dialogue channel,
thread and worktree coordinates. Unrelated or stale targets are not presented.

This projection is **not automatically wired** into `session_targets` or
`company.peers`. Existing `session_send` carries operational instruction
semantics; merely filtering its target list would not turn it into a safe
peer-consultation transport or fence a guessed direct send. Therefore this
adapter implements **discovery and exact validation only**. The production
authenticated host must still select and authenticate the caller, verify the
advisory message contract and enforce the hierarchy at its *actual* canonical
commit boundary. Neither a permitted target nor a return receipt is permission
to change work assignments, spawn agents or grant sender control authority.
Standalone native Codex/other provider management is not silently assumed
from the existing Claude projector.

The hermetic Session Bridge target tests use the actual temporary Runtime/OHF
identity facts and the existing Runtime/Claude target projectors with fake
management/physical carrier observations. These tests prove projection and
stale/foreign/expired refusal, **not live provider delivery or acceptance**.

## Independent native-only and worker-only scopes

A peer-messaging topology cannot require both actor types to be running.
`integrations/fabric_coordination_single.py` provides an opt-in,
**read-only single-domain owner observation** for either a Runtime-only
Job/Attempt/Worker scope or a native CEO/COO-only session scope. It reuses
the corresponding already-admitted identity owner, with no fabricated
Runtime Job for a native session and no requirement to contact a missing
native manager in worker-only mode.

The source requires a single **active** actor domain in the
host-authenticated scope and exactly one selected identity owner. Inactive
members of another domain remain in the full attested snapshot, including
roles, grants and revocation records, but no longer require a running
provider owner for an unavailable session. It **refuses a mixed active
scope**, including another domain becoming active during target discovery,
rather than silently dropping a failed identity layer or weakening
mixed-source checks. All-inactive rosters also refuse. An unreadable owner,
rotated binding, revoked membership, stale timestamp, divergent role or
unrecognized source fails closed.

A completed or revoked native session/Runtime Attempt can remain in that
historical scope alongside its current generation. The policy now enforces
**unique active** Job IDs, Runtime binding IDs and native session UUIDs,
rather than letting an inactive prior generation veto the one admitted
current actor. Exact duplicate participant identities always refuse; two
active generations for the same Job, binding or native session still refuse.
Old generations are **never** allowed to send or claim a dependency grant
addressed to the current generation. Legacy parent-Job resolution uses
the unique active parent, not a later-listed inactive parent record.
The installed Runtime/native owner must still independently verify that
the purported active generation is genuinely current; organizational
history alone provides no addressability or permission. The source returns the same bounded, non-authoritative evidence
shape consumed by `ScopedSessionTargetResolver`. The resolver accepts
the existing composite only with both canonical target projectors, a
worker-only observation only with a Runtime target projector, and a
native-only observation only with a Claude native target projector.
Neither missing/foreign target nor failed authentication triggers
another provider/model or session-selection fallback.

Native owner attestation now includes a digest of its **complete**
organizational membership snapshot (roles, projects, parent edges,
grants, revision and observation time), not merely the native session
UUIDs and an updateable revision label. Homogeneous and mixed
observations compare this digest against the exact scope they use.
Even when two host readers agree on session UUIDs, disagreeing role
or project information cannot be treated as a valid peer permission.
An admitted native CEO can therefore discover an admitted portfolio
CEO peer with no active Executive Attempts, and Fabric workers can
discover their task-group peers with no active native CEO/COO session,
**subject to actual installed transport and commit controls**.

This is source-level discovery only. These read-only components are
not production principal authentication, native delivery, atomically
fenced sends, worker enrollment, operational instructions, Slack
publication or model consumption. Installed selection must be explicit.
A failed mixed observation must NOT automatically downgrade to a
single-domain observation: domain selection follows the authenticated
organizational scope and its authoritative ownership facts.

## Authenticated host-side composition (opt-in; still no send)

`integrations/fabric_coordination_host.py` adds
`AuthenticatedScopedTargetHost`, a production-facing *read-only* assembly
entrypoint that accepts only incumbent host-controlled readers: authenticated
current caller, canonical organizational membership, Runtime and/or native
management-owner projector/principal source, scope topic and clock. It does not
parse identity, role, project, session ID, account or principal from a
public/worker message. The current caller reader is invoked **again on every
target discovery and exact resolution**. The hostname/role label and earlier
discovered peer do not authorize subsequent calls.

The host reads organizational actor kinds and chooses exactly one of three
admitted modes. After discovery or resolution, it re-reads the authenticated
caller AND reauthorizes **every selected recipient** against the newest
organizational scope, checking the original role/relation and exact grant
document digest. A recipient-side revocation or portfolio reassignment that
lands after the underlying target-projector read no longer exposes a stale
permitted peer. This is a read-side disclosure fence, NOT an atomic write
transaction. Host readers are required to be synchronous; asynchronous
credentials or coroutine readers are not silently accepted. Mixed scopes require
**both** Runtime and current native
Session Bridge owners. Worker-only requires the incumbent Runtime and
projector; native-only requires the incumbent Session Bridge Claude projector
and native principal owner. Unexpected optional readers/owners and a changed
actor-domain are refused instead of using another provider or relaxing
authorization. A worker target projector must be bound to the same Runtime
instance as the Runtime identity reader. Existing per-source observations,
hierarchy decisions and exact-target re-resolution remain authoritative.

The only public read operations are `visible_targets()` (filtered public
projections) and `resolve(target_ref)` (internal exact recipient proof). No
`send` / `reply` / `summon` / `register_worker` action exists here. The
installed authenticated host must **explicitly select** this service; merely
importing it cannot enroll workers or expose new tools. The message writer
must bind the authenticated caller and peer/hierarchy policy at its own
canonical transactional COMMIT. A target proof is not a bearer permission;
this module is not a substitute for native attention and answer-consumption
proof. The host may not treat the operational Session Bridge
`session_send` API as an unrestricted same-rank consultation permission.

Hermetic `tests/test_fabric_coordination_host.py` prove host-side mode
selection, dynamically current callers, exact recipients, no mixed downgrade,
domain-change refusal, bad owner/projector rejection, stale principal and
native generation refusal, and absence of transport-side effects.

## Existing effect-owner COMMIT revalidation adapter (source only)

`integrations/fabric_coordination_effect.py` introduces
`HierarchyEffectOwnerGuard`: it accepts the original authenticated sender,
original exact `ScopedSessionTarget`, and fixed topic **only from the
accepted incumbent consultation request**. `verify_inside_owner_effect()`
rechecks the *current* authenticated caller and recomputes the exact scoped
Session Bridge target and authorized role/relation. It checks the original
and current **grant_ref**, preventing a new dependency grant for the same
recipient from silently inheriting an earlier consultation authorization.
An expired current scope, revoked/replaced grant, rotated
Runtime/native binding, changed tenant/project/role, or forged caller refuses
under one opaque error code. An unchanged currently authorized edge remains
valid across ordinary short-lived snapshot refreshes.

The source-level target observation now preserves the internal
`CoordinationDecision.grant_ref` **and a digest of the canonical grant's
full owner-supplied payload**, without exposing either in public discovery.
A replacement grant, even if it reuses the same reference but changes
validity or approved project facts, cannot silently inherit an old request.
Grant identity is tied to the incumbent approval owner; there is **no new
grant issuance, permission store or sender-requested override**. Fresh
short-lived organizational snapshots may renew during long bounded work:
the effect guard independently rechecks the *new* current scope, while
pinning the exact durable grant payload whenever a dependency grant is
needed. It does not require every subsequent reply to finish before the
initial 30-second observation expires.

**Critical installation boundary:** The guard is a *verification hook*, not a
commit writer, lock, atomic transaction, message queue, native prompt or
provider delivery. It MUST run under the incumbent Dialogue/consultation
owner's own active current-writer transaction immediately before its
canonical durable message effect. The owning service also MUST verify the
persisted consultation's requester/recipient/operation identity in that
same transaction; a prior read-only target reference or this hook's
successful return does not confer a reusable permission. The platform
restriction on the production host/commit-owner source inspection remains
unresolved; this additive adapter does **not** select or replace that owner.
No current source fixture proves transaction atomicity or live consumption.

Hermetic `tests/test_fabric_coordination_effect.py` covers original
sender/recipient pinning, native/worker/mixed legitimate hierarchy edges,
rotated principals/generations, revoked or replacement exact dependency
grants, expired/widened scope, and the absence of any sending/commit method.
This is source validation, not permission to bypass incumbent release gates.

## Independent C3 technical review repairs — source only

Independent reviewer `mastermindx-3` identified three deterministic source
counterexamples in PR #1318 at the prior head (GitHub comment
`6108401687`). Formal GitHub review disposition was **not** accepted by
the platform, so the comment is technical evidence, not an `APPROVED`
or `REQUEST_CHANGES` state. The original source owner reproduced the
previous false admits and made these bounded repairs:

1. `ScopedSessionTarget.authorization_context_digest` hashes the
   ORIGINAL host-attested **sender and recipient participant scope plus
   exact topic**. Both identities, organizational tenant/portfolio,
   project/program, roles, workstream/team group, and parent lineage are
   pinned. Snapshot labels and short-lived observation/expiry clocks are
   intentionally excluded, so ordinary authorized snapshot renewal
   still works. The read-only authenticated host's final recipient
   check and `HierarchyEffectOwnerGuard.verify_inside_owner_effect()`
   now require the original contextual digest to match current policy
   facts. Moving both peers together to a new tenant/portfolio, moving
   a CEO to another project, or changing programs can no longer
   authorize an OLD consultation solely because the current relation
   string happens to match. This is **not** a bearer authorization or
   writer transaction.
2. An explicit `parent_identity` is immutable and takes precedence
   over `parent_job_id`. A stale explicit attempt/generation may not
   fall back to a live replacement with the same Job ID. Legacy Job
   parentage remains compatible **only when no explicit parent
   identity is provided**; matching explicit+legacy pins remain valid.
3. The Runtime source `verify_parties()` checks the persisted
   `INTENT` **requester_binding AND recipient_binding** against the
   exact current Harness ID, generation and admitted provider reasoning
   surface. Both owner observations share one Runtime read transaction.
   A new requester epoch/provider cannot inherit the earlier
   consultation's answer even if its Job/Attempt/Worker actor triple
   appears unchanged. Existing Company consultation wire and its
   frozen public schemas are unchanged.

These are source/fixture proof points, not a live cross-host message.
The independent reviewer also flagged the incumbent downstream
consultation detail reader for possible requester-binding parity.
That incumbent production/COMMIT reader was **not** inspected, modified,
or routed via another tool after the prior action-specific platform
denial. Its original owner must independently reconcile the exact
installed effect path and source/permission controls before production
acceptance.

## Verification at the current source milestone

Latest independent C3 security-source repair: M2 selected regression
**461 passed, 0 failures/errors/skips**, PID `53810` exit 0,
JUnit `/tmp/mmx-fabric-c3-security-repairs-full-20261011.xml`.
Focused prior repair suite **160 passed**, PID `47238`,
JUnit `/tmp/mmx-fabric-c3-security-repairs-focused-20261011.xml`;
two additional final host authority-change tests passed (PID `52825`).
The prepatch test runs deliberately reproduced the old authorization
failures (PIDs `41829` and `43040`). These are source-only fixtures;
independent approval, new exact-head hosted CI, production COMMIT
selection, native client consumption and installed release remain
independent acceptance obligations.

Latest historical-generation availability fix: **453 selected tests passed,
zero failures, errors or skips**, M2 PID `25214` exit 0, JUnit
`/tmp/mmx-fabric-history-full-20261011.xml`. Focused pure policy
and authenticated host/projector regression: **104 passed**, PID
`23651`, JUnit `/tmp/mmx-fabric-history-rotation-20261011.xml`.
The unmodified earlier policy had four reproducible false refusals in
retired Attempt/native-generation cases (PID `21924`); after the fix
both these positive cases and simultaneous-live-generation negatives
pass. All source-level/fixture proof, **not** installed native session
sending, production COMMIT atomicity or live model consumption.

Current dormant-roster availability fix: **446 selected tests passed,
zero failures/errors/skips**, M2 PID `91754` (exit 0), JUnit
`/tmp/mmx-fabric-inactive-roster-full-20261011.xml`.
Focused worker/native dormant roster + activation refusal selection:
**38 tests passed**, PID `90174`, JUnit
`/tmp/mmx-fabric-inactive-roster-20261011.xml`.
The active-only domain change retains inactive participant and grant
bytes in current issuer observations. All-inactive scopes and an
unexpected live second domain are refused. No actual provider message or
installed host/COMMIT proof occurred. Exact-head hosted CI and
independent code review remain separate gates.

The current October 11 homogeneous-source increment passed **53 focused
native-only/worker-only/native-integrity/mixed-target tests**, zero failures,
errors or skips (M2 JUnit `/tmp/mmx-fabric-independent-domains-20261011.xml`).
A broader original-owner integration regression selection of **409 tests**
passed, zero failures/errors/skips, exit 0, using the existing MCP-capable
Python 3.12 environment on M2 Studio (JUnit
`/tmp/mmx-fabric-all-related-20261011.xml`, PID `99181`).
It includes native and Runtime attestation, Session Bridge target/projector,
consultation host and dispatch, frozen SDK boundary, native hierarchy and
single-domain discovery tests. Syntax compilation and `git diff --check`
passed. This campaign is source/fixture proof, not hosted CI or
installed cross-host delivery.



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

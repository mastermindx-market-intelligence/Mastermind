# Reply delivery through the existing authenticated receiver and Company host

The source composes a complete default-disabled event path through existing owners.
The MCP receiver validates the original account JWT with its selected resource policy.
`InstalledReplyEventClient` carries the resulting neutral projection and selected
policy fingerprint through the existing UNIX CeoIngress App peer. No bearer, token
issuance API, new listener or account lookup is added. The Executive service requires
the exact App peer, armed existing binding and same Runtime before entering the
nominal private event owner. The public event route's JWT validation stays unchanged.

`RuntimeReplyEventHost` reselects the current receiver policy and uses the actual
`RuntimeOriginalRequestResolver` for fresh subscription admission. The existing
challenge sender verifies one signed callback challenge. Before the original Runtime
store CAS commit, the host rechecks the selected policy and captures a finite READ
authorization inside that subscription's sealed private payload. It binds the
original authenticated account, client, policy, immutable request event and read
reference. Subscription expiry never exceeds the original JWT expiry. No token is
stored or manufactured; a model-supplied identity DTO cannot create this authority.
Legacy subscriptions without the sealed accepted grant are unavailable to this path.

The Company host exposes the concrete same-Runtime event consumer. After the existing
native dispatch owner obtains `require_committed_native_reply`, Executive invokes
that consumer independently. Lookup uses existing canonical subscription events;
there is no new database, index, queue, scheduler or retry ledger. The consumer
revalidates the canonical committed reply using `RuntimeSessionReturn.resolve_read`
and the actual Dialogue read service, matching its message key and fingerprint.
Fresh worker admission is not required for retained committed read after cleanup.
READ tools still never send callbacks. Callback failure does not change the native
writer's committed receipt, repeat the writer, or claim parent consumption.

`RuntimeReplyAuthorizationOwner` rereads the exact active subscription version and
sealed grant. `InstalledReplyPolicySelection` rereads the same sealed MCP document
used by the installed launcher, then runs its existing document, primary and
additional-resource policy validators. It requires the enrolled release identity,
App service UID, web CEO profile and explicit event opt-in. It does not use the
launcher's initial policy object as proof of current policy. A full selected-policy
fingerprint change or actual validated subject denial withholds delivery and records
a tombstone through the existing subscription CAS. A stale observation cannot revoke
a newer accepted grant. Missing/unsealed/invalid policy data and ordinary expiry
withhold delivery without inventing a policy-denial tombstone.

Delivery rechecks account policy, original finite grant, canonical reply, subscription
version, expiry and rotation before reservation and on the actual I/O executor. A
second policy/store check runs after DNS validation and immediately before the owned
connection/request handoff. It signs with the current clock and bounded rotation
keys. Changes after that handoff can leave an external effect in flight; no atomic
remote cancellation is promised. Existing one-shot HTTPS, public-IP/TLS validation,
response limits and classification remain. A stable reservation survives refresh,
restart and unknown transport outcomes, so no automatic replay is allowed. A 2xx
remains transport accepted and parent unproven.

The existing issuer owner provides no OAuth/JTI revocation introspection in this
source. Provider-side revocation that is not reflected in a current local resource
policy is not immediately observable. The honest bounds are original JWT expiry,
subscription expiry, authenticated unsubscribe and current installed policy checks.
No extra refresh grant, token cache or security owner is inferred.

The optional installed source inputs are closed and default off: MCP
`reply_events_armed: true` requires the explicit `web_ceo_v3` profile; Executive
`reply_events` requires explicit absolute MCP document and provisioned key paths plus
key identity, and the existing armed App/native Company composition. The key is an
existing mode-0600, regular, single-link 32-byte file owned by the configured
Executive control UID, under root-sealed parent directories. The executing UID must
match that existing storage owner. It is opened without following a final symlink and checked for read-time changes.
No key, file, config, permission, enrollment or live account grant is created here.
Absent or disarmed selection performs no policy/key I/O. Correct restart, key backup
and previous-key custody remain deployment responsibilities.

Source integration tests use a real synthetic RSA JWT validation, the existing UNIX
App-peer handler and client, disposable canonical Runtime, real native ACK/COMMIT
fences, and a fake HTTPS connection. They prove subscription/disconnect/restart,
finite expiry, unsubscribe after COMMIT, unknown callback no-replay, exact Runtime
binding, and policy-file change while queued denying/tombstoning before HTTP. The
fixture only simulates root sealing of its disposable policy file; it does not prove
installed custody. Required release and live proof remain: independently reviewed
source, exact-head CI, protected landing, approved host key and sealed configuration
enrollment, installed selection, real Work/dot callback and canonical read, then
original-parent adjudication. Ordinary Project Chat is a distinct route.


## Post-COMMIT notification is not a native completion prerequisite

The Executive native finisher schedules the already-committed reply's notification as one separate **existing-service-owned** task and continues native Job finalization and terminal projection without awaiting external HTTP. The task is retained in the Executive service's existing physical-work set; normal service shutdown drains it before closing the Runtime/Dialogue owner. The actual current-account, policy, sealed-subscription and one-shot delivery checks still run in the original consumer. Notification failures cannot relabel or replay the native result.

This is an in-process service task, **not** a durable new queue or a guarantee of exactly-once emission after power failure. A crash before the notification task starts does not constitute a delivered event; existing delivery reservations protect against replay only once the real store has admitted that send. No idle chat wake/response is claimed absent a real Work/dot callback.


### Shutdown handoff of an already-admitted notification

A source regression also demonstrated that a service-close flag set just after notification scheduling could silently discard that accepted event before its task was scheduled to run. Executive now captures the **exact authenticated same-Runtime reply consumer** at the original post-COMMIT scheduling boundary and retains a task directly against that owner. The existing service shutdown drain completes that task even if `_closing` becomes true in the meantime. The consumer still rechecks the bounded audience, subscription version, READ policy, canonical reply and callback destination before network I/O; retaining task custody is not a new authorization grant or replay instruction. Exceptions cannot relabel the native Job result. No durable queue, subscriber registry or fresh writer carrier is created. Power loss before that service-owned task has started remains a documented, **unproven event-delivery gap** rather than an exactly-once guarantee.


### Canonical COMMIT payload accepted at the Executive notification edge

The original native COMMIT owner is `RuntimeSessionReturn.require_committed_native_reply`. It produces the full validated V2 Dialogue `PROGRESS` message. That is distinct from `NativeReplyWriter`'s transport receipt with a `reply_committed` boolean. The Executive post-COMMIT notifier therefore validates the exact returned Dialogue message's native reply key, canonical fingerprint, message type and `body.stage=message_reply` and forwards only the immutable message/fingerprint/reference identity to the existing bound event consumer. A writer transport receipt, malformed message or forged fingerprint is not treated as the full canonical committed message. This validation does not substitute for upstream Runtime COMMIT admission, nor for downstream current original-account authorization. The production path remains default disabled pending installed selection and Work/dot proof.

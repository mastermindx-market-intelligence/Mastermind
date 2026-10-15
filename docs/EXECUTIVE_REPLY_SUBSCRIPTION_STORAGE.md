# Executive reply subscriptions: source contract and installation boundary

This is a concrete extension of the existing Executive Runtime events owner. It is
source code with disposable-Runtime proof, not an installed credential grant or
live Work/dot callback. No new database, table, queue, retry ledger or migration is
created. Selection remains opt-in at the existing authenticated Executive host.

`integrations.session_bridge.runtime_reply_subscriptions.RuntimeReplySubscriptionStore` receives
an exact existing `Runtime`, an `ExecutiveReplyCipher`, and the owner's clock. The
cipher receives one host-provisioned 256-bit at-rest key and safe public `key_id`.
It performs AES-GCM with a fresh nonce and authenticated metadata/cursor binding.
The at-rest key is distinct from the per-subscription `whsec_` signing secret and
callback URL received from ChatGPT on authenticated `events/subscribe`.

The installed Executive service/credential owner must provision and retain that
storage key through its actual approved host custody mechanism before selecting
this composition. The default-off host accepts an explicit provisioned key path
under root-sealed parents, owned privately by the existing Executive control UID,
with strict file and executing-identity validation; it supplies no default path, key
creation command, provider credential reuse, generic vault or installed-readiness
claim. The model/request cannot select a key file or credential account. Key bytes
must stay out of arguments, environment/config JSON, logs, events, Agent OS and tool
responses. Host custody must prove private access, restart recovery, backup/restore
and correct key-id binding. At-rest key rotation needs actual access to previous
ciphertext before replacing a key; changing `key_id` alone makes old rows unreadable.
This is an installation obligation, not an instruction to create a live key here.

Subscription metadata contains public original-request, owner and URL/key digests.
The raw URL (which may contain callback capability material), current signing secret,
and at most one previous signing secret remain in the sealed private payload.
The receiving host can additionally bind its accepted finite original-account READ
grant into the same ciphertext and event CAS, with an authenticated public digest.
It stores no raw JWT. Legacy payloads remain readable but cannot provide retained
background authorization. See `EXECUTIVE_REPLY_DELIVERY_COMPOSITION.md`. Owner
only `delivery_view` opens that payload; its representation hides URL and signing
keys. No public MCP catalog or response exposes this private view.

`SubscriptionSnapshot.version` is the latest canonical subscription command identity.
It is independent of `OriginalReplyGrant.revision`, which identifies original request
access/generation. A never-created subscription has `empty`; a revoked subscription
retains its tombstone version and owner binding even though public `read` returns
None. The adapter takes its snapshot before callback verification and supplies that
exact version and raw callback URL to `commit`. The Runtime owner checks the current
version inside `BEGIN IMMEDIATE`, appends one event, and uses the existing unique
command-id owner for lost-ack recovery. Stale completions cannot overwrite newer
rotation or resurrect a tombstone. An explicit new subscription may use the current
tombstone after a fresh callback and current original-request grant.

Unsubscribe is an authenticated READ caller's withdrawal of its own exact
owner/request/URL binding. It does not require a still-running worker. A virgin
unsubscribe records a tombstone to fence a callback already in flight. An already
revoked same binding needs no second event. Current account authentication remains
with the existing MCP host; the store does not authenticate accounts.

Signing-key rotation retains only the immediately preceding current key, for at most
300 seconds and its previous subscription expiry. Refreshing the current key does
not extend the old key's grace. The existing signer consumes one/two keys. Expiry,
store version and original access must be rechecked on the actual delivery path.

Delivery reservation and observed transport results are also existing Runtime events.
The stable reservation identity binds canonical event id and subscription id, and
survives subscription refresh. The same Runtime transaction checks current active
subscription version/expiry and appends admission before HTTPS. This is admission
only: the trusted host must verify current authenticated account/read access and an
exact canonical committed reply, never merely COMMIT_STARTED. No network/secret
owner I/O is performed while a Runtime write transaction is held.

A restart with admission and no transport observation is EFFECT_UNKNOWN and grants
no resend. Revocation blocks new reservations; an external effect already admitted
may still settle on its original reservation. No cancellation of an in-flight HTTP
request or external exactly-once delivery is claimed. A 2xx observation is transport
received, never original-parent consumption or acceptance. The store has no sender
or retry owner. Contradictory terminal observations refuse; resolving a genuinely
ambiguous external effect requires the original installed I/O owner's evidence.

Required live proof remains separate: approved key custody and existing-writable
Runtime; correct resolver/store/HTTPS composition selected by the current host;
subscribe/refresh/revoke/restart readback; actual callback verification and delivery;
wrong-account/revoked-access/corruption/late-effect negatives; original Work/dot event
and canonical reader invocation; and actual parent adjudication. Ordinary Project
Chat is a distinct route and is not qualified by these source tests.

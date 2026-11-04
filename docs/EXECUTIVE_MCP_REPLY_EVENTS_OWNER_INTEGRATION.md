# Executive MCP Events: existing-owner integration and release gates

Status: **SOURCE READY FOR OWNER INTEGRATION; NOT INSTALLED, NOT PRODUCTION PROVEN**. October 12, 2026. Source operation `cross-client-hooks-r1-20261012-sol-001`; draft Mastermind PR #1362. This is a consumer/transport integration guide, **not** a new schema, provider, lifecycle, source-custody, or authority grant.

## User capability

An authorized ChatGPT **Work** conversation or **dot**, after explicitly subscribing to the Mastermind `session.reply_committed` event for its original request, can receive a verified reference-only update when its bound native Codex/Claude operation commits a reply; the conversation can retrieve full canonical content through the existing `session_reply_read` tool and adjudicate it. No claim of generic ordinary ChatGPT-web push, automatic resume of a dead conversation, or end-to-end exactly-once delivery.

See https://developers.openai.com/plugins/build/mcp-events: MCP 2.0 revision `2026-07-28`, same authenticated `/mcp`, trusted callback challenge, Standard Webhooks signatures, persistent subscriptions and HTTPS SSRF defense.

## Reuse installed owners exactly

| Responsibility | Existing owner; new consumer |
| --- | --- |
| Original request, incumbent writer and output | Executive Runtime, Agent Dialogue V2, `integrations/session_bridge/native_reply.py` |
| Original-authority full-result read | `integrations/session_bridge/native_read.py`, `return_tools.py` (`session_reply_read`) |
| Authorized account identity | Existing Executive JWT resource policy; `NeutralPrincipalProjection` only after a verified token |
| Event projection | `integrations/session_bridge/web_reply_events.py` (`CanonicalReplyEventProjector`) |
| MCP 2.0 discovery and event methods | `web_reply_event_rpc.py`, `web_reply_event_asgi.py`; explicitly selected `reply_event_rpc` in existing Web CEO v3 MCP host |
| Exact signed packet and challenge echo | `web_reply_delivery.py` |
| Single safe HTTPS send | `web_reply_callback_transport.py`, explicitly on the authenticated owner's owned bounded I/O lane |

The SDK currently installed for legacy Executive MCP on M2 rejected modern `2026-07-28` messages. The opt-in ASGI adapter preserves the old tool path and delegates MCP 2.0 tool effects to the exact original Executive handler. It **does not** install or advertise that adapter until the existing host selects it.

## Mandatory existing-owner implementation before arming

The `OriginalReplySubscriptionOwner` remains a **canonical Executive extension**, not a new subscription service in the Web session. A concrete Runtime-event implementation now exists in `integrations/session_bridge/runtime_reply_subscriptions.py`; it requires an explicitly host-provisioned at-rest key and is not installed or armed by source publication. The existing Runtime schema v5 is protected against generic live migrations; do **not** add an ad-hoc SQLite table or append callback secrets to Agent OS/Dialogue/Slack. A real approved subscription/credential persistence capability is required before production arming; source fixtures may use private temporary records but prove no durable production grant.

The existing owner must:
1. Verify the *current authenticated principal*, original request, exact session/parent, and `session_reply_read` grant on each discovery, subscribe, unsubscribe, refresh and send. The user-supplied `request_ref`, callback URL, event fields and subscription ID confer **no** authority on their own.
2. Resolve a stable key covering account/issuer/resource/client, event name, original request filter and canonical callback URL; implement atomic idempotent create/refresh, expires, unsubscribe and restart recovery through an **existing admitted durable** store. Use encrypted/controlled signing-secret custody, including safe rotation, not a new plaintext JSON store or model context.
3. Generate a fresh, short-lived, single-use random challenge per new callback, send a signed verification through a safe host-owned HTTPS transport, verify exact echo in constant time, and retain the accepted callback only after readback. Cache verification only for a bounded principal-and-URL binding. Distinguish a refused callback from an ambiguous late response.
4. Perform DNS/IP validation **for every connection**, pin TCP to the checked public address, validate TLS against the original hostname, reject proxy redirects, local/private/mixed DNS answers, mapped IPv6, 6to4 and well-known NAT64 translation targets; do not let an untrusted event select a hostname or alternate peer.
5. Source the event **only after** a verified canonical reply commit. Project it through `CanonicalReplyEventProjector`; match current subscription principal and original `request_ref`; sign via `prepare_reply_webhook`. Delivery uses exactly one bounded `send_once` on an owner-managed I/O process/async task. The **existing owner** decides/reconciles retries and preserves original event ID across attempts.
6. Preserve `EFFECT_UNKNOWN` for lost send/ACK or ambiguous persistence. A webhook 2xx means **transport received**, never original parent consumption. Let the subscribed chat explicitly invoke the existing canonical reader. No result-body instructions may self-grant a new Job, subscription, carrier or acceptance.
7. Expose no new legacy SDK catalog or ambient tool. Select the Web CEO v3 opt-in only after its original `session_reply_read` is present and after the authenticated subscription owner is current. Production service installation, account plugin selection and optional Work/dot event discovery remain separate.

## Slices already source-verified

- Signing/verification and one-shot network transport: HMAC-SHA256 Standard Webhooks, secret rotation, signed challenge, typed result/status, public-only pinned TLS, no redirects, no retry. The callback code does not read credentials, create a subscription or launch a worker.
- MCP Events protocol and authenticated legacy coexistence: Modern `server/discover`, `tools/list`, `tools/call`, `events/list`, `events/subscribe`, `events/unsubscribe` through the existing OAuth MCP path, plus exact original request authorization and response receipts.
- In-process proof, not live deployment: verified M2 baseline 725 Executive/Session-Bridge regression tests (before the optional HTTPS helper); new protocol/security cases red-first and green. See exact-head PR test evidence for latest source.

## External completion/acceptance gates

1. **Review and source CI:** independent exact-head security review (callback SSRF, plaintext secret exposure, Runtime schema/owner, permission and post-dispatch uncertainty), required PR checks. Draft source must not auto-merge or deploy.
2. **Actual subscription owner:** approved durable state and credentials, live readback after create/refresh/unsubscribe, restart and revoked-access negative proof; production selected by *existing* Executive host. A fixture `EventSubscriptionReceipt` does not qualify.
3. **Actual MCP client:** explicitly connect and select the updated Mastermind plugin in an eligible Work chat/dot; successfully complete `server/discover`, catalog discovery, registration and challenge verification.
4. **Original parent proof:** canonical committed reply -> exactly bound active subscriber -> signed HTTPS 2xx -> same original Work/dot receives event and opens the canonical `session_reply_read`. Verify duplicate, wrong account, parallel original conversations, late unsubscribe, lost ACK, restart, timeout and security failures. Keep response notification, consumption and acceptance as independent evidence.
5. **Rollback:** de-select `reply_event_rpc` in the original host; retained legacy SDK tools remain operational. Do not delete accepted runtime events or clear uncertain external deliveries.

No generic Chrome extension, alternate callback database, parallel Job lifecycle, new provider queue, or unverified model-wake mechanism is authorized or required by this plan.


## Inert original-request owner adapter (same PR, no new state plane)

`integrations/session_bridge/web_reply_subscription_owner.py` is an optional adapter implementing the existing `OriginalReplySubscriptionOwner` protocol **only when** an incumbent authenticated host explicitly injects all three capabilities:

- A trusted current original-request resolver yielding `OriginalReplyGrant` (account principal digest, exact request/read reference, generation, expiration, current permission).
- The incumbent durable + encrypted subscription store with atomic `commit`, `read`, and `remove` operations. The store's `StoredReplySubscription` receipt exposes only keyed metadata and SHA-256 digests. The concrete `RuntimeReplySubscriptionStore` supplies versioned Runtime-event CAS and AES-GCM sealed URL/signing-key custody when its host explicitly provides the storage key. Source fixture proof does not qualify installed key custody.
- A host-owned, bounded HTTPS challenge sender that returns an observed response. The adapter creates a fresh single-use challenge and checks exact signed echo; it does not own transport retries or credentials.

The opt-in flag defaults to **disabled**. The subscription identifier is deterministic by owner principal, event name, original request and callback URL, without becoming an authorization token. A successful callback is followed by a second current-grant check, a single atomic existing-store commit, readback, and a final current-grant check. A missing/changed result or lost post-commit acknowledgment is `EFFECT_UNKNOWN`, not a green subscription or permission to dispatch another attempt.

A recently verified callback can be reused for a short, fixed window **only from the incumbent store's readback** when owner, original request, URL, signing-key digest, current revision, and grant expiry all still agree. Reusing cached verification does not refresh its original verification timestamp. A new/rotated secret, changed generation, expired proof or changed callback URL requires a new verification, not an implicit trust upgrade.

Adapter tests use an in-memory **fake** store; concrete store tests use disposable real Runtime databases and synthetic storage keys. No production grant, key provision, HTTP endpoint, Worker, Runtime migration, or service setting was added. Production stays gated on installed key custody, exact host selection and a real Work/dot callback receipt. See `docs/EXECUTIVE_REPLY_SUBSCRIPTION_STORAGE.md` for the closed CAS/private-payload and installation contract.


## Inert original-request owner adapter (same PR, no new state plane)

`integrations/session_bridge/web_reply_subscription_owner.py` is an optional adapter implementing the existing `OriginalReplySubscriptionOwner` protocol **only when** an incumbent authenticated host explicitly injects all three capabilities:

- A trusted current original-request resolver yielding `OriginalReplyGrant` (account principal digest, exact request/read reference, generation, expiration, current permission).
- The incumbent durable + encrypted subscription store with atomic `commit`, `read`, and `remove` operations. The store's `StoredReplySubscription` receipt exposes only keyed metadata and SHA-256 digests. The concrete `RuntimeReplySubscriptionStore` supplies versioned Runtime-event CAS and AES-GCM sealed URL/signing-key custody when its host explicitly provides the storage key. Source fixture proof does not qualify installed key custody.
- A host-owned, bounded HTTPS challenge sender that returns an observed response. The adapter creates a fresh single-use challenge and checks exact signed echo; it does not own transport retries or credentials.

The opt-in flag defaults to **disabled**. The subscription identifier is deterministic by owner principal, event name, original request and callback URL, without becoming an authorization token. A successful callback is followed by a second current-grant check, a single atomic existing-store commit, readback, and a final current-grant check. A missing/changed result or lost post-commit acknowledgment is `EFFECT_UNKNOWN`, not a green subscription or permission to dispatch another attempt.

A recently verified callback can be reused for a short, fixed window **only from the incumbent store's readback** when owner, original request, URL, signing-key digest, current revision, and grant expiry all still agree. Reusing cached verification does not refresh its original verification timestamp. A new/rotated secret, changed generation, expired proof or changed callback URL requires a new verification, not an implicit trust upgrade.

Adapter tests use an in-memory **fake** store; concrete store tests use disposable real Runtime databases and synthetic storage keys. No production grant, key provision, HTTP endpoint, Worker, Runtime migration, or service setting was added. Production stays gated on installed key custody, exact host selection and a real Work/dot callback receipt. See `docs/EXECUTIVE_REPLY_SUBSCRIPTION_STORAGE.md` for the closed CAS/private-payload and installation contract.


### Same-operation lost acknowledgment and idempotent refresh

When an owner request loses the acknowledgment **after** the incumbent store commits, a later identical `events/subscribe` does not create another subscriber or blindly rewrite the record. The adapter rereads the original, owner-bound subscription metadata, verifies current principal and original-request generation and signing-key/URL identity, reads it a second time, and returns that same stable receipt **without another callback verification or store mutation** when the exact desired record already exists. The store remains the authoritative durable identity and receipt source; no new effect state is inferred from an HTTP response. A changed expiration, secret, callback URL, grant or generation follows the regular callback/atomic-commit path subject to the incumbent owner's own concurrency and retry admission. This source cannot independently reconcile network effects outside the existing store.


### Outbound signed-packet structural integrity

Before *any* DNS lookup or socket attempt, the one-shot transport now validates the signer-produced packet's exact body/header shape: subscription reference, original event ID or signed verification message ID, canonical JSON (including duplicate-key refusal), signing timestamp, bounded Standard Webhooks v1 signature encoding, and one/two-key rotation format. It refuses a fabricated control notification, an event ID/header mismatch, a malformed signature or tampered body without making a network call. **This is structural consistency only**; the trusted existing signer and subscription-secret owner still own HMAC authority. The transport itself does not receive/verify private signing keys.

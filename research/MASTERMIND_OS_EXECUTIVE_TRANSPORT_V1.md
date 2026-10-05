# Mastermind OS authenticated Executive transport

The default-off `enable_os_executive_transport` option on the existing v3
builder adds three fixed POST routes to the same listener and authenticated
App. It requires the exact `OsStaticApp`, v3 1.4.0, and installed ingress
read composition. Existing MCP routes and tool security schemas are unchanged.

| Route | Closed request |
| --- | --- |
| `/os/executive/context` | `{}` |
| `/os/executive/submit` | `{"arguments": <existing submit arguments>}` |
| `/os/executive/status` | `{"arguments": {"intent_id": <original id>}}` |

The public fence requires HTTPS, exact Host `mcp.mastermind-x.com`, an
absent or exact same-origin Origin, literal path, no query, and one bearer.
Every response is no-store. Audited verification of the exact Executive
read + intent.submit policy occurs before body collection. The adapter
pairs each admitted resource's submit verifier with its matching
authenticator; it adds no audience, client, scope, or registration.

The closed context DTO contains `schema`, `principal_scope`,
`verified_expiry`, and `profile: {name: "web_ceo_v3",
server_version: "1.4.0"}`. Scope is an opaque domain-separated SHA-256
namespace over the verified issuer/subject/client/resource tuple. It is
stable across refresh; it is not a caller assertion or a credential.
The audited access-token projection must match the verified principal.
No token or raw identity is returned.

Requests allow at most 65,536 bytes, 32 frames, and a total five-second
receive deadline. JSON rejects duplicate keys and non-finite numbers.
Inner responses have a five-second deadline, at most 262,144 bytes,
one start, and a completed ordered body. The original bearer is forwarded
to the existing inner App and reverified after awaits.

Submit uses the canonical App outcome validator and binds an accepted
receipt to the original deterministic intent ID and workstream. Loss,
malformed replies, or post-effect authorization drift become the original
request's `effect_unknown`, never a replacement submit. Status uses the
closed E1 envelope and binds successful data to the requested intent ID.
Missing status and authorization failures cannot settle or replace a pointer.

## Source validation

The focused OS transport, existing MCP launch journey, App ASGI, and
App composition suites passed together: **123 tests**. The new strict-v2
journey uses signed disposable tokens and a disposable Unix/SQLite
Executive with execution disabled. Both normal acceptance and deliberate
post-accept response loss recreate the App, read the original status,
and prove original work_ref, one ingress submit, one queued job,
zero attempts, and zero workers. Adversarial tests cover unauthorized
body reads, malformed or foreign outcomes, and post-await auth drift.
Independent Sol review accepted this boundary after the fixes.

The frontend `os-executive-host` component composes the existing launch
binding from this verified DTO and the existing private auth owner's
generation. It invalidates before auth changes and suppresses late
context, submit, and status replies. It remains a component until the
platform transport, durable store, and mount wiring are composed.

## Installed gates

Source validation is not installed acceptance. Enabling the route still
requires a qualified OS Executive resource/client registration, matching
immutable client configuration, the approved public DNS/TLS route,
authenticated platform integration, and durable reopen proof. No connector
audience is repurposed, no registration is created here, and no live job
or fabricated app pointer is used as evidence.

# Mastermind OS authenticated Executive transport

The default-off `enable_os_executive_transport` option on the existing v3
builder adds three fixed POST routes to the same listener and authenticated
App. It requires the exact `OsStaticApp`, v3 1.4.0, and installed ingress
read composition. The sealed installed launcher exposes this only through
`os_executive_transport: true` on `web_ceo_v3`; missing/false leaves it off,
and non-boolean values or another enabled profile are refused. Existing MCP
routes and tool security schemas are unchanged.

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

`main.tsx` now calls `composeMissionHost`: the existing web or native private
auth owner supplies the fixed transport; `createOsExecutiveHost` qualifies
OwnerContext from the verified DTO and its private authentication generation;
the existing `createExecutiveLaunchBinding` supplies projects/profiles and
launch mapping; `bindMissionHost` receives that binding. It mounts while
signed out and becomes eligible only after context verification. SEND/STOP
and session providers remain unavailable because no qualified producer exists.

`VITE_MM_EXECUTIVE_RESOURCE` (web) and `MM_EXECUTIVE_RESOURCE` (native Rust)
are optional immutable HTTPS resource configuration. Both use the existing
platform public client, callback, and fresh third PKCE transaction. Missing or
invalid resource leaves Executive unavailable. Exact read + submit scopes
are required; denial preserves the independent workspace tokens. Native bearer
tokens never enter the webview. Auth changes/expiry invalidate before late
context/submit/status results can publish. No token parsing asserts an owner.

`VITE_MM_LAUNCH_CONFIG` is a closed JSON build manifest with `v: 1`, original
`workstream`, `priority`, `projects`, and `profiles`; bounded-code profiles also
require allowed write paths and validation. The decoder validates and freezes
it. There is no catalog, URL, provider, or missing-config fallback. Actual
resource/grant/workstream values must come from the qualified installation.

The principal-scoped IndexedDB store persists only version, operation key,
kind, and original target. The controller awaits `read`, atomic `reserve`, and
atomic `clearIfEqual`; reserve never overwrites even an equal pointer. Only a
committed reservation may submit. Failed/unavailable persistence stops before
submit. Recovery calls status using the stored original operation only. Auth
invalidation hides old visible state but preserves its original-scope hint;
clear failures keep an unknown outcome. Tests compose the actual mount,
verified context, launch port, controller, and IndexedDB adapter to prove one
submit across competing connections and lost-response/reopen recovery. A
separate real Chrome shutdown/restart proof verifies on-disk persistence.

Both web/native frontend builds and the Rust suite pass. The sealed asset
contract accepts exactly the legacy three files or all nine Noir files:
index, hashed CSS/JS/image/two fonts, and the three fixed font-license files.
No partial six-file bundle is accepted. Immutable hashes, path/seal checks,
closed MIME/routes, no-store responses, and query rejection remain enforced.
CSP permits fonts only from self. The actual nine-file production bundle is
served and checked through `OsStaticApp` in the source integration proof.

## Installed gates

Source validation is not installed acceptance. Enabling the route still
requires a qualified OS Executive resource/client registration, matching
immutable client configuration, the approved public DNS/TLS route,
authenticated platform installation, and live original-operation reopen proof. No connector
audience is repurposed, no registration is created here, and no live job
or fabricated app pointer is used as evidence.

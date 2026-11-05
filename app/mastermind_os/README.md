# Mastermind OS shared product

This read-only React/TypeScript product installs a fixed web or Tauri host before
mounting. It consumes the closed Programs envelope and Mission v2 from the
workspace service, preserving the existing Program selection, generation and
abort fences. Historical v1 fixtures remain decoder regression inputs.

Programs join one `work_ref` to exactly one Runtime root. Mission reads carry
exactly `work_ref` and `root_job_id`; no recent-root guessing is performed.
`CURRENT` means current as of the bounded owner observation, under the service's
source-validity checks. It is not a linearizable claim about the moment the UI
renders. The frontend validates the closed receipt, matching selection, sample
consistency, digest formats and the facts in the Mission DTO. The authenticated
service owns binding digests to the full source documents, which are absent
from the Mission response. Runtime completion never implies acceptance.

The Conversation view consumes only the current server-permitted managed turn
window, displays text as text, and clears its contents on authentication or
selection changes. It does not establish full history or product acceptance.
The client has no enrollment, provider-control, send, shell, generic HTTP, or
caller-selected URL command.

## Public configuration still required

No viewer client IDs have been registered or invented in this source change.
Without the build input for its platform, the app displays **Sign-in setup
pending**. Registration and permissions are separate operator-owned work.

| Field | Web | Native macOS |
| --- | --- | --- |
| Public client ID build input | `VITE_MM_WEB_CLIENT_ID` | `MM_NATIVE_CLIENT_ID` |
| Client type | Distinct public SPA with PKCE S256 | Distinct public native client with PKCE S256 |
| Exact callback | `https://mcp.mastermind-x.com/os/auth/callback` | `com.mastermind.os://oauth/callback` |
| App origin/base | `https://mcp.mastermind-x.com`, `/os/` | Bundle `com.mastermind.os` |

The fixed issuer is `https://dev-eo0jf8us5mup7wd5.us.auth0.com/`.
Acquisition requests use only audience
`https://mcp.mastermind-x.com/workspace/read` and scope
`mastermind.workspace.read`. Content uses a separate token for audience
`https://mcp.mastermind-x.com/workspace/window/current` and scope
`mastermind.workspace.content.read`. There are no OIDC identity scopes or
refresh tokens. Each audience requires its corresponding enrolled service
permission; a content refusal can leave acquisition usable.

The web client opens one popup directly in the user gesture, reuses it for two
one-use PKCE transactions, checks exact callback origin/window/state, and
cleans callback query/fragment before the handoff. Codes and tokens never reach
React. Tokens remain in private module memory and disappear on sign-out or
reload. Sign-out is local token disposal, not an Auth0 SSO logout.

Native Rust opens the system browser and receives the registered deep link.
Tokens stay in Rust memory. React uses only `auth_status`, `sign_in`, `sign_out`,
`read_programs`, `read_mission`, and `read_current_window`; it has no token
getter or arbitrary URL bridge. The macOS app must be installed/registered for
its custom scheme before an actual callback can be qualified. This source
change neither installs nor launches it.

The fixed public GET routes are `/workspace/programs/current`,
`/workspace/mission/current`, and `/workspace/window/current`. Every public
response is capped at 2,000,000 bytes. Token responses are capped at 32,768
bytes. The content service's separate internal frame limit remains 544 KiB.
Web hosting must serve the product and exact callback through the `/os/` SPA
fallback and permit the fixed issuer token endpoint in its CSP. The issuer's
web-origin/CORS configuration must match the exact product origin. Native
HTTP runs through Rust and uses no JavaScript network permission.

## Validation

```sh
npm ci --ignore-scripts
npm run typecheck
npm test
npm run build
npm run build -- --mode native
```

The normal web build uses `/os/`; the Tauri pre-build uses `native` mode and
relative packaged assets. Rust checks require a full source revision and a
review build identity, and should place build products in owned external
storage:

```sh
MM_SOURCE_REVISION="$(git rev-parse HEAD)" \
MM_BUILD_IDENTITY="mastermind-os-review" \
CARGO_TARGET_DIR="/path/to/owned/external/target" \
cargo test --manifest-path src-tauri/Cargo.toml
```

The tests use local fixtures and injected transports. Their success is source
validation, not proof of actual Auth0 registration, native callback delivery,
installed workspace services, enrolled content permissions or live product
acceptance. The readiness command retains `BUILT_NOT_PROVEN` until an external
installation qualification exists. No updater, native signing, service
installation, registration, or release is performed by these checks.

Approved design references remain #702's workspace and #704's consumer freeze.
The header uses the existing facts/buttons and the content uses existing cards,
state labels and typography; no additional design system was introduced.

## Web SSO restoration candidate (review required)

The web client now attempts hidden-frame authorization-code + PKCE (`prompt=none`) on
startup and after silent tokens expire. The fixed callback hands a code only to a
same-origin, state/source-checked parent. Access tokens remain in memory, with no
refresh token or bearer serialized into browser storage. A nonsecret localStorage
logout marker prevents an explicit local sign-out being undone by page reload;
interactive sign-in clears that marker. Resource audiences remain distinct.

This is **best-effort SSO restoration, not unlimited sign-in**: third-party cookie
blocking, Auth0 session expiration, tenant iframe restrictions, revocation, and
browser profile cleanup can require interactive sign-in. Full persistence across
those conditions requires a separately reviewed first-party/BFF session owner or
qualified rotating refresh-token implementation, with explicit revoke/logout,
rotation and server-side revocation guarantees. Native macOS Keychain renewal is a
separate implementation. Source tests do not prove live Auth0 tenant behavior.

## Same-tab fallback when the live edge forbids silent frames (stacked draft)

The existing production edge serves `default-src 'none'` without `frame-src`,
and its callback sets `frame-ancestors 'none'`. Consequently hidden-iframe
Auth0 restoration is currently **blocked by CSP**, independently of cookie
availability. The follow-up web-auth candidate does not weaken those headers.
It detects a frame-source CSP denial and, **only for a browser profile with a
previously completed Workspace login**, attempts a single top-level
`prompt=none` PKCE authorization on the fixed Auth0 issuer. The registered
same-tab callback validates state, client, issuer and TTL, scrubs its code and
exchanges it privately before the React app mounts. A nonsecret prior-login
hint and one-attempt marker live in browser storage; tokens never do. Failed
Auth0 SSO restores the ordinary manual sign-in path without an endless loop.
Explicit logout prevents redirect, including if a subsequent popup is blocked.

**This only reacquires the Workspace acquisition audience**: the separate
Content and optional Executive grants can remain unavailable if their iframe
attempts are also blocked. The existing user-initiated Auth0 popup may recover
those scopes. The subsequent OS static-response candidate narrowly permits
`frame-src` to the exact pinned Auth0 issuer and its own callback origin on the OS app, and allows only
the exact OAuth callback to be framed by its own OS origin (`frame-ancestors
'self'`); the app shell and all other assets remain `frame-ancestors 'none'`.
That repairs the OS-controlled CSP denial without permitting arbitrary
embedding. It does **not** alter the Auth0 tenant, its own iframe policy, browser
third-party cookie restrictions, or the deployed edge until installed and
verified. True unattended, all-resource, cross-restart persistence in
privacy-restricted browsers requires an independently reviewed first-party
Auth0 custom domain + scoped CSP changes or a secure cookie/BFF credential
custodian. The redirect fallback and CSP candidate are scoped incremental
repairs, not substitutes for those release/tenant and real-browser acceptance
requirements.

### Authentication restoration and multi-tab safety follow-up

A prior Workspace user whose token expires can try the same **single bounded**
first-party browser-tab `prompt=none` authorization fallback after the
iframe's CSP failure, subject to the user's existing Auth0 cookie/session and
standard expiry policy. A tab that observes an explicit logout from another
tab immediately invalidates its private bearer owner, read generations and
Executive/Research capabilities; it never converts logout into an automatic
new sign-in. Manual Workspace and Research logins reauthorize only after a
successful new grant. Complete Content/Executive renewal remains a distinct
first-party backend/session-owner or qualified Auth0 integration gate.

**Unsent work and automatic authentication:** OS keeps an in-memory navigation
hold on unsent Office and Conversation notes, Session messages, Launch goals,
and unresolved command effects. An automatic Auth0 top-level redirect is
deferred while any such work is active, rather than silently discarding it.
This is a user-data safety gate, not an implementation of indefinite login;
a saved/finished draft may be followed by explicit sign-in or page reopen.
All draft/credential storage, live Auth0 tenant, Content/Executive authorization
and deployment remain with their existing qualified owners.

**Browser-session expiry and privacy:** On an unambiguous passive web token
expiry, user-authored unsent Office/Conversation/Launch/Session text is kept
only in the mounted page until explicitly copied, discarded or replaced by
new authentication. Source data and command authority remain invalid. Both
same-tab and cross-tab logout immediately clear the retained text even if
browser quota prevents writing the logout marker. No draft or credential is
persisted as a workaround for third-party-cookie restrictions.

## Native Keychain refresh-token persistence candidate (not installed)

The macOS Tauri native client has a separate opt-in Auth0 refresh-token
candidate, compiled only with `MM_NATIVE_REFRESH_ENABLED=1` **after**
the existing native public Auth0 client and the Workspace acquisition/content
APIs have been verified to permit `offline_access`, rotating refresh tokens,
and the intended expiration/revocation policy. With the option absent, the
protected native behavior is unchanged: in-memory access tokens only.

In the candidate, the native credential owner stores individual rotating
refresh tokens by client/audience in macOS Keychain; access tokens are never
stored in React or Keychain. Native reads and startup restore per-resource
credentials without requiring the login popup after normal application restart.
Only the acquisition and content grants participate. Executive SEND authority
does not acquire offline renewal by default. The owner serializes refreshes
per resource and records a Keychain pending marker before a rotating exchange;
a crash or unknown response refuses replay and requires explicit sign-in.
Sign-out invalidates the generation and deletes both credentials and markers,
returning an error if deletion could not be confirmed.

**Limitations:** This is source code pending native macOS build/test, independent
security review, configured tenant/client readback, signed installed-app restart
and Keychain access-control acceptance. Keychain locked/refused, token revocation,
absolute/inactivity expiration, ambiguous token rotation, or damaged credentials
can still require interactive sign-in. Never represent the candidate as a
permanent or irrevocable Auth0 login.

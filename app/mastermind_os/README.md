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

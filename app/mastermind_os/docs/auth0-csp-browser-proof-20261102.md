# Auth0 CSP fallback: bounded synthetic-provider Chromium proof

Source candidate: stacked web PR #1928, original #1923 held Draft. The production
CSP header was retrieved by a real GET of `https://mcp.mastermind-x.com/os/`
and the callback: `default-src 'none'` (no `frame-src`) and callback
`frame-ancestors 'none'`. No live tenant change or release occurred.

On Ubuntu2, Chromium `chromium-1248/chrome-linux64/chrome` ran the exact
candidate Vite built assets with a synthetic public client ID
`VITE_MM_WEB_CLIENT_ID=client-fixture`. Request interception served the built
app and callback at their exact HTTPS origins, with **the production CSP
header**. It simulated the existing Auth0 issuer's top-level authorize 302
and code exchange using a synthetic token, without any actual Auth0 user,
client registration, credential, session cookie or identity grant.

1. New browser profile: startup remained `signed_out`, no top-level redirect.
   Chromium emitted `effectiveDirective=frame-src`, with
   `blockedURI=https://dev-eo0jf8us5mup7wd5.us.auth0.com` **without a
   trailing slash**. This exposed a real CSP detection error missed by the
   initial jsdom test.
2. After installing **only** the nonsecret prior-login hint, reload exercised
   a top-level `prompt=none` PKCE redirect (exactly one) and synthetic token
   exchange (exactly one). The app URL returned to `/os/` and host auth status
   became `signed_in`, acquisition=true, content=false. No token was stored
   in localStorage. `authFrames=0` confirms no Auth0 frame request escaped CSP.
3. Browser host `auth.signOut()`, then reload: remained `signed_out`, prior
   login hint removed, explicit logout marker `1`, redirect-attempt state
   absent. Authorize and token-exchange counts remained **1** each, proving
   no unintended reauthentication after logout.

The candidate was corrected to recognize both origin-only CSP `blockedURI`
and full path; the `web-auth.redirect.test.ts` CSP fixture now matches the
actual browser event. This is **real browser execution with a synthetic Auth0
provider**, not end-to-end live Auth0 login or all-resource persistence.
Native Keychain and Workspace Content/Executive remain separate gates.

No browser cookies or confidential values were collected. The synthetic
browser process was closed; no persistent daemon, credential or fixture
identity was created. This evidence never authorizes deployment, bypass of
independent security review, or weakening the public CSP.

## Follow-up canaries: expiry and cross-tab logout (same candidate, synthetic provider)

The next scoped change adds a generation-fenced, token-owner-wide response to
an explicit logout marker arriving as a real browser `storage` event from a
second tab. `valid()` fails closed on a logout marker even before the event is
delivered, preventing a stale tab from using its existing access token.
In-progress Executive and Research paths retain their existing invalidation
rules. A new manually completed Workspace or Research login clears the local
logout marker only after a qualifying token is issued. No auth credentials are
stored or communicated via the `storage` event.

With **two real headless Chromium tabs** of the isolated candidate, the first
tab completed one synthetic `prompt=none` PKCE acquisition; the second tab set
the logout marker on the same HTTPS origin. The first tab immediately reported
`signed_out` without navigation, then stayed `signed_out` after reload. The
counters remained exactly one mock `/authorize` and one mock `/oauth/token`
exchange; no new reauthentication after the cross-tab logout.

In a separate single-tab synthetic test, Auth0 returned a 3-second synthetic
acquisition token. Under the production CSP, the browser completed **two**
top-level silent PKCE authorizations and **two** synthetic token exchanges;
primary Workspace was `signed_in` again following expiry, without writing the
access token to localStorage. Explicit logout afterward prevented another
redirect and remained signed-out on reload. This test is about the *client's*
renewal machinery only; it cannot prove Auth0 actual absolute/idle session
policies, live cookies, tenant grants, Consent, Content or Executive renewal.

Source suite after these changes: `npm run typecheck` PASS, `npm test` 96 files,
**1,988 passed, one skipped**, and `npm run build` PASS, with the pre-existing
Vite bundle-size advisory. No production deployment, Auth0 user session,
client registration or tenant policy was changed.

## User-editing safety: no destructive unattended renewal

A same-tab silent Auth0 redirect reloads the OS app. The earlier synthetic
3-second-token canary proved renewal but did **not** prove unsent UI drafts
survive the reload. The subsequent UI-owner guard is an in-memory, nonsecret
signal only: when the Meta-CEO Office direction, conversation notes, Session
Workspace message, Orchestrator Launch form or an unresolved command is active,
a top-level automatic `prompt=none` redirect is **deferred**. The guard is
checked twice, including after asynchronous PKCE challenge generation and
before writing a pending navigation transaction. The sign-in owner still
requires the same prior-session hint and session-scoped one-attempt gate.
Explicit logout and revocation remain effective regardless of any UI hold.

This protects unsent drafts; it does **not** provide unattended refresh while a
user continues editing or retain authentication beyond the Auth0 session's
absolute lifetime. After preserving/submitting the work, the user can
explicitly sign in or reopen the page to resume an eligible Auth0 session.
No draft text, access token or refresh token enters localStorage or the new
navigation guard. Separate per-resource Content and Executive persistence
remains blocked on tenant/first-party architecture qualification.

## 2026-11-02: passive expiry with unsent draft — corrected real-browser falsifier

The first local draft-navigation guard **FAILED** its real Chrome canary: a
short-lived Auth0 grant expired while `office-direction` held a private unsent
note. The app invalidated the auth generation and cleared the React draft
*before* the top-level redirect guard could protect it. This negative proof
is preserved; green isolated UI tests had missed it. The original remote PR
head was not advanced with that failing candidate.

The correction splits loss of an expiring browser credential (a **one-way**
loss of an acquisition/content grant, no newly gained resource) from explicit
logout, new login or a native identity boundary. Expiry still invalidates all
qualified program/source data, pending authorizations, and effects, and the
state truthfully becomes `signed_out`; the existing in-memory **user-authored
unsent draft only** is advanced to the next local presentation epoch. The
original UI-owner and root expiry guards then defer automatic full-page SSO
navigation while that page has unsent work. An interactive login or any
explicit/cross-tab logout always clears the retained draft, even on the same
public state, and the sign-out marker blocks hidden restoration.

**Real Chrome against exact production CSP, synthetic intercepted Auth0**:
one initial top-level `prompt=none` PKCE authorization and one token exchange;
a synthetic 7-second acquisition grant; after >8 seconds the app reported
`signed_out` with acquisition/content false, still displayed the *exact*
synthetic unsent Office direction, and had **no second top-level redirect**
(redirect and exchange counts both remained 1). A separate real-Chrome run
also invoked the actual owner `signOut()`: the textarea became empty,
prior-login hint disappeared, the explicit logout marker became `1`, and
state stayed signed_out. Both real-browser canaries returned rc0 with zero
page errors. These tests do not use a real Auth0 user/tenant or prove
per-resource renewal after expiry; an active draft takes precedence over
unattended reauthentication. The user can explicitly sign in again after
saving/copying a draft, or reload after it is safely finished.

Source typecheck and full Vitest: 98 files, **1,998 passed, one skipped**;
production Vite build PASS (advisory bundle-size warning). New React tests
exercise passive expiry retention, sign-in privacy boundary, explicit logout
and navigation-hold behavior. Browser content/audience persistence still
requires actual tenant/first-party confirmation and separate security review.
No browser draft, refresh token or bearer is written to persistent storage.

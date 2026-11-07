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

## Independent-review REQUEST_CHANGES repair — 2026-11-02

The separate exact-head independent review of web Draft PR #1928 at
`6b900532fefe123631ce94622925374c474bf4ab` reproduced **two real
privacy/UX blockers**. This follow-up repairs both without another identity,
credential, browser storage, queue, retry, or publication owner:

1. **Logout marker quota failure.** `localStorage.setItem(logoutKey, "1")`
   may throw while storage reads and deletions still work. The existing
   in-memory Auth0 client now sets its own explicit user-sign-out fact before
   touching storage, exposes `USER_SIGNED_OUT` on the same existing auth state,
   clears tokens and effects as before, and suppresses automatic restoration
   even when the marker could not be stored. Each browser cleanup operation is
   individually attempted. The App treats this event as a privacy boundary,
   **never** as passive access-token expiry. Cross-tab `storage` logout uses
   that same existing auth owner. A successful new interactive grant is the
   only way to clear same-page explicit logout; failed popups remain failed.
2. **Off-view and unmounted drafts.** The App's existing local presentation
   owner retains user-authored Launch goal/Session message text when an
   expiring bearer unmounts the authenticated command forms. Only this
   plaintext user draft stays in React memory, not authority-bearing command
   bindings, session history, selection permissions, or a pending effect.
   The signed-out screen offers the text for copying/editing or discarding
   with *no* Launch/Send command. Off-view Office and Conversation drafts are
   considered in the same root navigation hold; it is released as soon as
   retained unsent text is cleared. The source owner/selection/auth epoch
   still fences command composer rehydration; any explicit logout, fresh
   login, changed principal or grant clears private drafts. No draft text is
   moved into localStorage, sessionStorage, cookies or backend services.

**Tests run on M1 Studio source:** TypeScript typecheck PASS; 98 Vitest
files, **2,004 passed, one skipped**; production Vite build PASS with the
pre-existing large-bundle advisory. Added direct falsifiers for same-tab
quota denial, App-level explicit logout with no storage marker, retained
Launch/Session drafts and inaccessible commands after expiry, new-grant
clearance, and off-view Office text on Work/Today transitions. Existing
owner-scoping/operation/PKCE tests remain green.

**Real headless Chrome** with the exact candidate bundle, production CSP and
intercepted SYNTHETIC Auth0 code exchanges: (a) seven-second acquisition
credential expired, state truthfully became `signed_out`, Office direction
remained unchanged, and no second top-level redirect occurred; (b) after
that expiry, artificially rejecting only the logout-marker `setItem` with
`QuotaExceededError` caused the *real App* to clear the draft, report
`USER_SIGNED_OUT`, retain no acquisition permission and remove the prior
login hint despite the missing marker; (c) an independent synthetic
same-origin cross-tab `StorageEvent` for the logout key also cleared the
Office text and set `USER_SIGNED_OUT`. Each browser canary returned rc0.
The synthetic browser runs are not a live tenant or registered API test.

**Non-goals / remaining real-path gates:** no bypass of Auth0 absolute/idle
session expiry, no silent reauthentication while a user has unsent work, no
multi-resource Content/Executive refresh claim from Acquisition-only tests,
no cross-user draft migration, no signed/native install or tenant setting
changes. Browser first-party domain/session grant, current-head independent
security review, formal non-author GitHub approval and installed release proof
remain separate.

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

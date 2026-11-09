# Native persistence rollout — packaged build enables the rotating refresh path (2026-11-09)

The Chairman asked to end repeated Mastermind OS re-login. This change makes
the packaged native app compile the already-reviewed rotating Keychain refresh
path in by default, and records the rollout evidence and the remaining
tenant-side requirements.

## Why re-login kept recurring

The installed unsigned app (build identity `mmos-office-connection-06ef56a3-20261109-01a1a4bf`,
source `06ef56a39c085af72bcbf0866db8e43f99cd6034`) was built without
`MM_NATIVE_REFRESH_ENABLED`. Raw-binary inspection confirmed the compiled-out
state: no `offline_access` scope literal, no rotation grant machinery
reachable. Access tokens lived only in Rust process memory, so every app
restart and every access-token expiry required a fresh interactive browser
sign-in; once the Auth0 SSO session expired, full credential re-entry.

The persistence implementation itself (`src-tauri/src/native_refresh.rs`,
`refresh_one`, `start_restore`, sleep-safe renewal scheduling in `auth.rs`)
was already merged, independently reviewed (PR #1927 REQUEST_CHANGES repair
record) and dual-suite tested in CI; it was simply not compiled into any
installed build.

## What changed

- The CI native package step now builds with `MM_NATIVE_REFRESH_ENABLED=1`
  (`.github/workflows/mastermind-os.yml`), with the workflow contract test
  updated. Without a build-time `MM_NATIVE_CLIENT_ID` the enabled path stays
  inert (no scope change, no Keychain use), so clientless CI artifacts are
  unaffected. A client-configured install requests `offline_access` for the
  Acquisition and Content audiences and persists rotating refresh tokens in
  the macOS Keychain (`com.mastermind.os.auth0.refresh.v1`), renewing
  automatically before expiry and restoring silently on app restart.
- A local client-configured install (Chairman's Mac, `~/Applications`) was
  rebuilt from `3652d8907df1738de551dd3032b42aa2a2acb482` with the flag and
  the registered public client, build identity
  `mmos-persistent-login-20261109-3652d89`. The previous build is preserved at
  `Mastermind OS.app.bak-mmos-office-connection-06ef56a3`.

## Verified facts (2026-11-09)

- The registered native public client (referenced only by its domain-separated
  readiness digest convention; raw value intentionally not stored in source)
  is accepted by the fixed Auth0 issuer with callback
  `com.mastermind.os://oauth/callback`: a `prompt=none` authorize probe for
  both audiences returns `302 …error=login_required` to that exact callback,
  proving client and callback registration.
- The same probe with `offline_access` added for both audiences also returns
  `login_required` (not a scope rejection) at `/authorize`; this proves the
  request shape is admissible, not that a refresh token will be issued —
  issuance depends on the tenant toggles below.
- The rebuilt binary contains the `offline_access` authorize/refresh scope
  literals and the Keychain service constant (absent in the prior install).
- Graceful degradation is source-verified: a token response without
  `offline_access` echo or without a `refresh_token` is accepted for login
  (persistence simply stays absent); a non-rotating refresh response fails
  closed (`REFRESH_TOKEN_NOT_ROTATED`) and an explicit sign-in clears the
  credential and pending marker (recovery path).

## Remaining tenant-side requirements for actual persistence

The Auth0 tenant (dev tenant `dev-eo0jf8us5mup7wd5.us.auth0.com`) must have,
for the registered native client and both workspace APIs:

1. **Refresh Token grant type** enabled on the native application.
2. **Allow Offline Access** enabled on both APIs
   (`workspace/read`, `workspace/window/current`).
3. **Refresh token rotation enabled** (required: the Keychain custody layer
   refuses non-rotating successors) with reuse detection as offered.

If any toggle is missing, the app still signs in normally; persistence stays
absent exactly as before this change (no breakage). The definitive check is
the real login journey: one interactive sign-in, then quit and relaunch —
the app must return to `signed_in` without opening a browser.

## Honest limits

This is persistent-until-revoked, not a guaranteed never-expiring or
irrevocable session: explicit sign-out deletes both Keychain grants; Auth0
revocation, rotation reuse detection, or tenant refresh-token-expiry policy
still terminate persistence; the Executive resource remains deliberately
non-persistent. The web client at `/os/` keeps its in-memory SSO restoration
boundary. Installed-app signing/notarization and the signed-release
qualification (`tools/qualify_macos_release.py`) remain separate gates.

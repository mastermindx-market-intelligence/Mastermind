# Native Auth0 persistence — independent-review repair evidence (2026-11-02 UTC)

This is a source/build qualification, **not production or installed Auth0 acceptance**.
The original independent Fabric reviewer adjudicated PR #1927 head
`fe055771b65d25f444afe355ee493ea36e245404` as REQUEST_CHANGES;
see https://github.com/mastermindx-market-intelligence/Mastermind/pull/1927#issuecomment-6570240012.
The candidate repair originates at isolated repair commit `d41001ec1b1854b232c636846b717618dceec861`
and is integrated into the original existing Draft PR branch only after exact-head reconciliation.

## Repaired original blockers

- Auth0 `invalid_grant` from HTTP **400, 401 or 403** is terminal for the
  existing resource's grant: delete credential and pending marker and clear
  the access token. Arbitrary HTTP error, malformed JSON, lost response,
  server failure and timeouts retain the ambiguous marker instead of replay.
- A positively pre-transmission reqwest connect error is **not** an Auth0
  refresh rotation. Under existing in-process generation/Keychain locks,
  verify the *exact* pending marker matches the old token, delete that item
  and permit a later online retry with the original still-valid grant.
  Timeout and uncertain delivery never use this rollback.
- A second process cannot upsert a signed-out user's refresh token through the
  rotation-success path: obtain and validate the exact existing Keychain
  item and update its data, rather than creating an item by service/account.
  The expired/deleted stale item test confirms an old item reference cannot
  mutate a later login's new item.

## Additional assurance and limitations

- Access-token expiry uses both `Instant` and a wall-clock `SystemTime`
  deadline, with periodic wake/sleep-safe timer checks for renewal; sleeping
  macOS must not blindly trust a monotonic clock that paused in sleep.
- `MM_NATIVE_REFRESH_ENABLED` is **absent/default OFF** or exactly `1`.
  Invalid values must fail the native Cargo build; Cargo tracks changes to the
  flag as a build input. `MM_NATIVE_CLIENT_ID` remains separate public native
  client configuration.
- The existing unsigned CI package remains default-OFF. The native macOS CI
  job additionally compiles and tests the feature-ON branch in a separate
  command with no real tenant/user token or client registration. CI alone is
  not a signed-app or live Auth0 proof.
- Actual M2 Studio macOS test host with locked Rust dependencies: both
  `MM_NATIVE_REFRESH_ENABLED=1` and default-OFF `cargo test --locked
  --all-targets` passed **46 ordinary Rust tests + 14 other target tests**,
  with four manually invoked synthetic Keychain canaries:
  (1) original store/load/delete,
  (2) competing Keychain claim exactly-one winner,
  (3) definite preconnect rollback then online rotation, and
  (4) deleted stale item cannot resurrect a signed-out or newly logged-in grant.
  These tests use uniquely named synthetic fixture credentials, not a user.

## Still blocked from user-facing completion

Exact real native Auth0 public-client registration, allowed callback, per-API
`offline_access` and rotating refresh grants, installed signed app Keychain
identity/ACL, locked-device/sleep/offline/revocation/idle/real-login journey,
independent **new-head** non-author security approval, required CI and
normal reviewed deployment. Browser Content and Executive persistence are
separate first-party architecture/tenant qualifications. Never represent
this as a guaranteed never-expiring or irrevocable session.

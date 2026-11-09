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
required CI and the normal protected deployment. The Chairman's 2026-11-02
completion instruction waives discretionary independent-review holds; it does
not replace actual tenant, signed-app or authenticated journey evidence. Browser Content and Executive persistence are
separate first-party architecture/tenant qualifications. Never represent
this as a guaranteed never-expiring or irrevocable session.

## Stale terminal `invalid_grant` cleanup — cross-instance repair

The retained worker return `mmos-native-stale-grant-20261102-c4-01` started
from `d28287ee6099a05720c722aa413cf4c6758ae9a7`. Its exact patch was consumed;
Mac compilation of the initial composition exposed that security-framework
3.7.0's item `delete()` discards OSStatus and returns unit. The parent repair
uses a small exact-item native binding that preserves the actual status,
with the already-locked core-foundation 0.10.1 and security-framework-sys
2.17.0 versions. No account-level fallback follows a failed exact-item delete.

A captured item reference alone does not prevent an in-place replacement.
Login publication is now atomic add-only: a delayed login callback refuses
an existing credential instead of overwriting it. Successful rotation
retains its existing exact-item update and exclusive pending-marker claim,
so concurrent signout cannot be undone by a delete-and-recreate rotation.

Terminal cleanup requires both the exact old credential and its matching
pending marker. It deletes the credential before releasing that marker.
Missing or changed ownership yields `Superseded` without storage mutation;
an absent credential yields `AlreadyAbsent`. A crash may retain an ambiguous
marker requiring explicit sign-in. It must never release a second refresh
of the old grant. Explicit signout still removes the exact client/audience
credential and marker through its existing account-level operation.

Three ignored synthetic Keychain canaries cover newer-grant preservation,
unchanged old-grant removal with marker custody, and the deterministic
interleaving after cleanup has captured its old item references. They use
PID-qualified synthetic clients and fixture.invalid audiences, and explicitly
prove fixture credential/marker absence on success. The after-lookup case
first proves a delayed overwrite is refused, then replaces both items through
explicit signout/login and proves the newer rotation survives stale cleanup.

The initial worker patch did not compile on the Mac; the parent corrected it
before qualification. Immutable source `3d66c02b5139b69e2b5ec3aa8a35ecd8f5acf6e3`
passed the actual M2 native frontend build and all four locked Rust gates:
default-OFF check/test and flag-ON check/test, each using `--all-targets`.
Each test configuration passed 68 ordinary tests (48 app, 6 local report,
14 update-verifier), with seven synthetic Keychain tests explicitly ignored.
The three stale-cleanup canaries above were then separately invoked on the
same immutable source and all passed, including explicit fixture cleanup.
The four existing synthetic storage, competing-rotation, preconnect rollback
and signout canaries were also rerun on that source and all passed; their
existing cleanup paths remain unchanged.
Evidence logs: `/tmp/mmos-native-c4-repaired-qualification-20261102.log` and
`/tmp/mmos-native-c4-synthetic-canaries-20261102.log` on the M2 host. No real
native client or Executive resource was configured for these runs.
Real tenant configuration, installed-app identity and authenticated restart
remain separate from synthetic source qualification.

# Mastermind OS signed Mac candidate qualification

This is P6 Slice B preparation through the existing Tauri application and release
owner. The merged unsigned native CI gate (#1278) establishes packageability.
This verifier establishes evidence about an already signed, notarized `.app`.
Neither grants permission to publish, install, change credentials, or enable an
updater. Follow the existing review/release owner; retain the original operation.

## Build and signing inputs

Use one exact reviewed protected source SHA, immutable build identity, product
version and the actual existing Apple Developer team. Reconcile the existing
Developer ID Application certificate and notarization account/profile first.
Missing identity or key custody is a release gate; an ad-hoc signature is not a
beta. Keep keys and notarization credentials in their current platform/keychain
owner. This procedure does not create certificates, export keys, or buy access.

The authorized builder must supply the same `MM_SOURCE_REVISION` and
`MM_BUILD_IDENTITY` to Rust's existing build and to a temporary Info.plist merged
by Tauri before signing. The additional keys are `MMSourceRevision` and
`MMBuildIdentity`. For example, with the two public build variables already set:

```python
import os, plistlib
from pathlib import Path

metadata = {
    "MMSourceRevision": os.environ["MM_SOURCE_REVISION"],
    "MMBuildIdentity": os.environ["MM_BUILD_IDENTITY"],
}
Path("/path/to/release-staging/identity.plist").write_bytes(plistlib.dumps(metadata))
```

The release owner's temporary Tauri build-config overlay sets
`bundle.macOS.infoPlist` to that absolute staging path and keeps
`bundle.macOS.hardenedRuntime=true`. The existing Tauri builder accepts that
overlay through `--config`; it must build native bundled assets with locked
dependencies, the approved real app configuration and the existing signing
identity. Never patch Info.plist after signing. The signed metadata binds an
artifact to the builder's source/build claim; the trusted build record and source
review must independently substantiate that claim.

The signing owner performs notarization, receives an accepted ticket and staples
the `.app` through the existing authorized Apple toolchain. Retain the nonsecret
submission/acceptance record. The verifier below cannot submit, sign or staple.
Tauri documents [macOS signing and notarization](https://v2.tauri.app/distribute/sign/macos/)
and the [Info.plist and hardened-runtime build options](https://v2.tauri.app/reference/config/#macconfig).

## Qualify the exact candidate on macOS

Run from the reviewed source used by the release operator, passing real expected
values from that release record, not values inferred from the candidate itself:

```bash
python3 app/mastermind_os/tools/qualify_macos_release.py \
  --app '/path/to/Mastermind OS.app' \
  --source-revision "$MM_SOURCE_REVISION" \
  --build-identity "$MM_BUILD_IDENTITY" \
  --version "$MM_RELEASE_VERSION" \
  --team-id "$MM_APPLE_TEAM_ID" \
  --out '/path/to/evidence/new-macos-release-qualification.json'
```

The checks require bundle ID `com.mastermind.os`, exact version and sealed build
metadata, a strict deep code-signature check, the expected Developer ID team,
hardened runtime, a valid stapled ticket and Gatekeeper's Notarized Developer ID
assessment. Each Apple command has a bounded deadline. There is no alternate
executable, bypass switch, automatic retry, quarantine removal or security-policy
change. Unavailable or failed checks refuse qualification and emit no receipt.

The receipt hashes the `.app` tree before and after verification, including
relative names, permission modes, file bytes and contained relative symlink
targets. A changed tree or escaping link is refused. Keep the candidate immutable
through publication; requalify after any byte/mode change. The tree digest is not
a DMG/archive SHA and does not attest a separately supplied package. A later
archive/DMG must be created from this exact qualified bundle and obtain its own
release-owner digest. Existing receipts are never overwritten, and output cannot
be written inside the qualified bundle.

## Updater and installed acceptance remain separate

The receipt explicitly leaves `release_authorized`, `updater_qualified` and
`installed_journey_qualified` false. Unit fixtures exercise refusal behavior;
they cannot prove a real successful Apple assessment. An unsigned local build's
refusal proves only that it was refused.

Apple code signing and the [Tauri updater's artifact signature](https://v2.tauri.app/plugin/updater/)
are separate checks. The existing app currently has no admitted updater key or
endpoint. Do not publish an update feed, install a plugin or invent a public key
as a side effect of qualification. P6 Slice C must separately bind the immutable
version/source/artifact and expected public key, verify signatures before install,
preserve the current app on failure, and retain a prior signed immutable artifact
for controlled reinstall. Unresolved operations and unsaved drafts must not be
discarded by an automatic restart.

The final installed proof still requires the real native callback/PKCE journey,
Workspace/Content/Executive permissions, original-operation recovery, applicable
15 production scenarios, signed update/tamper rejection and controlled rollback.
Do not substitute this candidate receipt for those outcomes.

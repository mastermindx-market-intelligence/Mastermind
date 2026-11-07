# Mastermind OS update artifact signature qualification

This is the offline signature step in P6 Slice C. The `verify_update` utility is
a separate command-line target in the existing native Cargo package. The default
application remains `mastermind-os`; no second app, updater plugin, endpoint,
installation command or background updater is registered.

Apple Developer ID/notarization and Tauri update signatures answer different
questions. The existing Mac release qualification on #1319 checks an already
signed/notarized `.app`. This tool checks the **exact bytes** of a supplied Tauri
update artifact against its Minisign signature, an independently approved public
key and an independently approved SHA256. It never extracts the archive or
attests its contents, app identity, version or source revision.

## Inputs and trust

The release owner supplies these inputs from the existing approved release record:

- The immutable `.app.tar.gz` produced from the qualified app.
- Its Tauri `.sig` file and the admitted Tauri public-key file. Both use Tauri's
  base64-wrapped Minisign text format. The private signing key is never an input.
- Expected SHA256 of the exact archive bytes.
- Expected SHA256 of the **decoded public-key text**, including its original
  comment/newlines. Outer base64 whitespace does not affect this key pin.
- A new evidence path that does not already exist.

The two expected digests must come from the trusted release record. Computing
them from arbitrary downloaded candidate files and immediately treating them as
approved defeats the independent pin. The release owner must separately bind
version/source/build identity to the archive hash and retain the prior signed
immutable artifact for controlled reinstall. This utility grants no release
authority and cannot make a self-supplied key trusted.

Example, with reviewed non-secret build and release variables already supplied:

```bash
cargo run --locked \
  --manifest-path app/mastermind_os/src-tauri/Cargo.toml \
  --bin verify_update -- \
  --artifact '/release-staging/Mastermind OS.app.tar.gz' \
  --signature '/release-staging/Mastermind OS.app.tar.gz.sig' \
  --public-key '/release-staging/mastermind-os.pub' \
  --expected-artifact-sha256 "$MM_UPDATE_ARTIFACT_SHA256" \
  --expected-public-key-sha256 "$MM_UPDATE_PUBLIC_KEY_SHA256" \
  --out '/release-evidence/new-update-signature-receipt.json'
```

The existing Cargo build requires `MM_SOURCE_REVISION` and `MM_BUILD_IDENTITY`.
Use the source revision of the verifier build for those variables. They do not
claim a source identity for the separately supplied artifact.

## Results and refusal behavior

The verifier uses pinned `minisign-verify 0.3.0`, the verification library also
used by Tauri's updater, rather than implementing signature cryptography. It
verifies the signature's authenticated comment as well as the artifact. Its
legacy-signature support matches Tauri; the independent archive pin is required
in all cases. Public-key/signature inputs are bounded to 8 KiB, and the archive
to 256 MiB. Inputs must be regular files; final-component symlinks are refused,
and file identity/size/timestamps are checked around each read. Errors are fixed
codes and do not echo file contents or cryptographic material.

A successful new receipt has schema
`mastermind.os_update_signature_qualification.v1` and qualification
`ARTIFACT_SIGNATURE_AND_DIGEST_VERIFIED`. It records hashes and byte count, with
release authorization, Apple qualification, bundle-content verification and
installed-journey qualification all **false**. Existing paths and symlinks are
never overwritten. Any verification failure creates no receipt. An I/O failure
while saving can leave an incomplete new file; the nonzero command result means
it is not an accepted receipt and must not be consumed.

The receipt concerns the bytes read and verified during this invocation. Retain
the artifact immutable and recheck it at the actual consumption boundary. The
utility does not copy the artifact or secure a mutable staging directory.

## Remaining updater acceptance

Tauri's update feed version is not, by itself, a signed statement. The updater's
newer signed-version option can bind the announced version to the authenticated
signature comment; require that protection when the admitted production client
and signer support it. An offline digest check is not an automatic-feed replay
policy. Source/owner adjudication of the real key, endpoint and version contract,
client verification before installation, preservation of the current app on
failure, original-operation/draft recovery across restart, and controlled
rollback/reinstall remain separate acceptance gates.

No production key is created, no release is published and no installed app is
modified by this utility. Its public upstream test vector is deliberately not
a Mastermind release. Successful vector tests prove cryptographic behavior only.

References: [Tauri updater format and signing](https://v2.tauri.app/plugin/updater/),
[Tauri updater verification and signed-version checks](https://github.com/tauri-apps/plugins-workspace/blob/updater-v2.13.3/plugins/updater/src/updater.rs#L1663),
and [minisign-verify public test vector](https://docs.rs/minisign-verify/0.3.0/minisign_verify/).

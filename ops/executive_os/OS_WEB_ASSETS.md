# Optional OS web assets in an Executive release

The existing installer accepts `--os-web-assets <qualified-artifact-directory>`.
Without this option its backend-only source/archive flow is unchanged. A supplied
artifact is checked before maintenance and imported into new operation-owned
staging before the existing release manifest is created, verified and published.
No gateway configuration, service lifecycle, database or arming law changes here.

The release owner runs the preparer from the same reviewed protected source SHA.
It validates a clean exact protected checkout, builds an exact Git archive of
the app, and checks source identity again after the build. Ignored checkout
`dist`/dotenv files are not inputs; tracked generated/ dotenv inputs are refused.
The recipe is locked `npm ci --ignore-scripts`, then the app's existing web build.
Only the real public SPA client ID is supplied as a Vite environment input.
LAUNCH/Executive configuration is deliberately absent from this viewer build.

Use the existing trusted operator and its qualified Node/npm. npm never runs as
root: the child has that operator's UID/GID and no supplementary groups. Node
and npm CLI may be operator-owned Homebrew files; their physical names and
pre/post file digests are retained in the build receipt. This is the existing
trusted operator/toolchain build attestation, not a signature proving an
arbitrary compiler's honesty. The sealed receipt is produced by the preparer
after the actual build, not accepted from an HTTP/model-provided source label.

The build output parent must already be a physical root-owned, non-writable
directory traversable by the operator. Do not use a user-writable evidence tree
or an SSD with ownership disabled as the sealed artifact parent. The preparer
creates a fresh artifact; failures leave any partial own artifact for inspection.
Use the provisioned Executive Python, with the paths below resolved physically:

```sh
sudo '<qualified Executive Python>' -I -S -B \
  '<exact protected checkout>/ops/executive_os/os_release_assets.py' prepare \
  --source-repo '<same clean exact protected checkout>' \
  --expected-sha '<actual protected SHA>' \
  --build-user '<existing trusted operator>' \
  --node '<qualified physical Node executable>' \
  --npm-cli '<qualified physical npm-cli.js>' \
  --web-client-id '<real enrolled public SPA client ID>' \
  --output '<new artifact directory under the sealed build parent>'
```

The resulting artifact contains only `app/mastermind_os/dist` and
`build-receipt.json`. The incumbent asset validator enforces its three/nine-file
layout, MIME set, `/os/` index references, hashes and budgets. The receipt binds
the source commit/tree, lockfile/build configuration/helper hashes, public build
input, non-root builder/tool metadata and asset manifest. Root-sealed paths,
single-link regular files, exact closed topology and the current target's source
inputs are checked again by the installer. Symlinks and special files refuse.
Every relevant file/directory and ancestor is checked using the existing
descriptor-bound macOS ACL observer. Any ACL, ACL-query failure or custody/identity
drift refuses before maintenance. A directory ctime change from an unrelated
root publication causes a second ACL observation; file content/metadata stability
remains strict. Output/publication parents and newly created objects
are also checked so inherited write ACLs cannot undermine the root seal. The
existing observer remains inert on Linux; no alternate permission law is added.

Append the option to the already authorized installer command, retaining its
actual source, Python, operator, control and preservation inputs:

```sh
sudo /bin/bash '<reviewed installer checkout>/ops/executive_os/install.sh' \
  <existing qualified installer arguments> \
  --os-web-assets '<qualified artifact directory>'
```

The installer retains the preflight artifact digest, rechecks it at import, and
copies the captured bytes rather than reopening source files for the copy. New
asset directories are `0755`, files `0444`, and the existing release seal covers
them. If the target release already exists, requested assets must be identical
to its packaged bytes and receipt; missing or different assets refuse before
maintenance. Existing sealed 326c is never amended, grafted or restamped.

Preparation establishes build provenance only. It does not register a client,
grant Workspace permission, install the gateway, publish public routing or prove
the UI journey. With no real viewer client available, prepare source/tests only;
do not call a placeholder-ID build a production artifact. After the normal host
owner publishes the matching gateway generation, its existing launcher loads
the packaged `/os/` mount at startup. Public-edge candidate staging remains the
existing `python -m ops.executive_os.os_public_edge --source <qualified-root>
--relay-port <real-port> --out <new-candidate>` command.

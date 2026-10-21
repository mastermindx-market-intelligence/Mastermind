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

## Inert two-phase public-edge transition planning

`ops/executive_os/os_public_edge_transition.py` plans, without touching any
host, the exact two-phase replacement that the installed-HTML switch incident
required. Its inputs bind two distinct source SHAs (retired and candidate), the current observed full Caddy JSON config, both exact asset
manifests and the reserved loopback relay port. The planner refuses unless the
observed config has exactly one `mcp.mastermind-x.com` host route whose GET
matcher already carries exactly the incumbent fixed routes plus the current
manifest's asset paths (either the normalized set or the known fixed+index `/os/` duplicate is accepted;
no other repeat is permitted), exactly the three POST paths, and exactly the two existing
reverse_proxy upstreams at the loopback reserved port. Duplicate hosts, extra
or ambiguous matchers, wildcards, extra paths and wrong upstreams refuse.

The planner accepts two inner shapes only: the three-branch OS shape (GET, POST,
terminal abort) and the five-branch shape that adds the public MCP entrypoint
(GET, POST, MCP metadata GET, MCP POST, terminal abort). The two MCP branches are
observed, never rewritten: metadata is exactly GET `/.well-known/oauth-protected-resource/mcp`,
and MCP is exactly POST `/mcp` with a 64000-byte body limit (an integer) before a
loopback reverse_proxy at the same relay port. A wildcard, extra path or method,
a missing, duplicated or reordered MCP branch, a different body limit or an
unexpected upstream refuses.

`prepare-config` admits the sorted unique union of the retired and candidate
asset routes plus the fixed GET routes, so the publisher can prepare both allowlists before the host switch; actual
asset availability remains a separately verified host/publisher obligation; `final-config` admits only the candidate asset routes
plus the fixed routes, so only retired asset paths are removed. Every other
config field — POST handlers, header rewrites, body limits, TLS, unrelated
sites, the relay — is preserved semantically; only the selected GET path list
differs, and caller inputs are never mutated. For a shared non-index asset
name, the planner compares manifest-declared SHA256, byte count and MIME;
`shared_assets_verified` names only that comparison, and no asset bytes are
read here. The existing host/preparer must verify actual bytes and availability.
Hash-name reuse with changed declarations refuses; `index.html` is deliberately
the switch. Receipts record both source ids and bind canonical JSON SHA256 of
both manifests and the observed, prepare and final configs, with
`installed=false` and `published=false`. Source ids are bindings only; this
planning never asserts protected-source or authentication qualification — that
remains the existing release-owner preparer's custody.

Canonical config digests omit a trailing newline. Staged files contain canonical
JSON followed by one LF; the staging receipt's `files` digests cover those exact
file bytes. Compare like digest families rather than using a staged-file hash
as a canonical config hash. `preparation_complete` compares supplied objects
only: its `prepared` input must be the already-validated `prepare_config` result.
Object equality alone neither validates an arbitrary config nor permits publication.

Staging writes the plan and candidate configs only under an existing physical
parent that is not group/other-writable, with exclusive `0600` creation, fsync,
no symlink following and no overwrite. Partial files remain after any write
failure for reconciliation; a subsequent call cannot overwrite or clean them up. The CLI reads
supplied local JSON with duplicate-key and nonfinite rejection and a bounded
input size, performs no network, SSH, subprocess, daemon, environment override,
`caddy load`/reload or production write, and prints compact binding metadata
only — never the shared config. It holds no live authority token, scheduler or
parallel lifecycle ledger.

A restart comparison here is a pure diagnostic over the observed live config,
the autosave and the effective startup config. It reports mutual equality and
per-config host-route counts, and never treats autosave equality alone as
restart safety: startup uses the adapted `Caddyfile.combined` while `--resume`
loads the autosave, so a startup file whose adapted JSON lacks the OS host
routes is unsafe even with a matching autosave. Config equality is also not an
actually tested restart; `restart_verified` stays false and the diagnostic
suggests no service change. The external publisher and the host owner keep
their existing separate custody of the conditional readback of the prepared
config, the host switch, and the final cleanup, under full request equality,
custody checks and no replay after uncertainty. This staging is preparation
only: it does not compose, install or publish a production release, and it
adds no new policy approval gate.

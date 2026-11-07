# Persistent attended DeepSeek application

The complete native application owns attended chat, its providers, credentials,
streaming, sessions, stop controls and history. A native user conversation does
not require paid GLM worker admission. Company jobs and governed tool execution
still require their existing Executive/Agent OS owners.

## Build and stage

Use the exact clean, built full-app donor and compile the company plugin as
described in [its build instructions](company_plugin/README.md). Then:

```sh
python3 integrations/deepseek_harness/package_attended.py \
  --donor /absolute/clean/donor \
  --pnpm /absolute/pnpm-11.28.5/bin/pnpm.cjs \
  --release /absolute/fresh/release \
  --state /absolute/fresh/persistent-state \
  --public-url https://chat.mastermind-x.com/ \
  --port 4180 --relay-port 4181
node /absolute/fresh/release/launch_attended.mjs --check-only
```

Paths must be canonical and independent. The package copies the complete built
app/dependency tree and rebuilds its owned copy through the native dependency-aware
graph with the public title `Mastermind` and the exact donor commit. The installed
pnpm 11.28.5 build tool is explicit. Its native workspace verification may relink
the copied dependencies from the pinned lockfile before building. The package
retains the native client build record, compiled company plugin, upstream MIT
notice, file/link inventory and exact Node identity, and creates private
persistent state. No provider credential is copied from the host environment.
Before the native build, the packager applies the qualified four-file native
session cancellation patch only to its owned copy. `native-session-receipt.json`
binds the exact patch and native postimages; `app.json` also binds its source
manifest and the compiled private company reader. The protected publication
export compares those identities to the same accepted source revision and
refuses stale host output, altered patch input or native source drift. Older
packages remain tied to their older qualification; a new build must earn its
own `attended-build.json` record.

The donor remains intact. The explicit `--check-only` verifies the complete
closure; normal launches verify immutable controls, app entries and company
artifacts so startup does not reread every development dependency.

The immutable `company.patch.yml` is a native CLI overlay loaded after the
editable web/home profiles. It adds only the company plugin. The native Models
and settings editors may continue saving their own profiles across restarts.
The launcher passes `--patch` before the first application option, as required
by the pinned native CLI parser.

The package is an attended app running with the desktop user's ordinary native
permissions. Separate state and a cleared environment do not provide an OS
filesystem or network sandbox.

## Supplied installation artifacts

| Artifact | Purpose |
| --- | --- |
| `app.json` | Exact package, Node, state, public URL and listener identity |
| `package-manifest.json` | Hashes/modes and internal dependency-link inventory |
| `native-session-receipt.json` | Exact native command patch and four source postimages |
| `company.patch.yml` | Immutable native company plugin insertion |
| `com.mastermind.deepseek.web.plist` | One native app launchd definition; no auto-retry |
| `public-edge.caddy` | Candidate root host route with native auth/cookie/frame semantics |
| `os-build.env` | The matching sealed OS build URL |

Staging and `--check-only` do not bootstrap launchd, create a tunnel, install a
public route, change DNS, enable an Executive worker or call a provider.
The explicit launcher starts one native CLI child and forwards shutdown signals
to that same child. Native credential and session owners remain unchanged.

## Public edge and Mastermind OS

`chat.mastermind-x.com` is the current candidate origin; it is **not a qualified
live route**. A distinct owned HTTPS root origin is required by the OS consumer.
The edge preserves the original Host and native WebSocket behavior, adds Secure
to the HTTP-upstream cookie, and supplies a default frame policy permitting only
`https://mcp.mastermind-x.com`. Existing upstream CSP, including the account
callback's `frame-ancestors 'none'`, remains intact.

The relay port is the VPS-side transport endpoint; the app port is the M2
loopback listener. They are not automatically connected by the generated Caddy
file. Use the incumbent transport/publication owners with a distinct DSH grant.
Do not reuse the fixed OS or Fabric application reverse slots or credentials.
The existing Caddy publication owner uses listener identity, ETag/If-Match and
readback; its current closed OS planner does not authorize a new app host.

Only after the real HTTPS edge and native login are qualified should the OS
build consume `VITE_MM_DSH_APP_URL`. The URL must match the installed root exactly.
Missing installation keeps the existing project-conversation journey available.

## Native login and provider setup

The native app issues a private launch URL for its current process. The first public-authority
browser visit must consume that URL so the native service can issue its signed
cookie. A local-authority cookie is not a public-authority cookie. Never put the
launch token in the OS build URL, project bridge, issue, or evidence report.
Service stdout/stderr belong only in the private state logs.

The pinned DeepSeek account sign-in validator accepts explicit-port loopback
origins. Complete that account flow through the same running app's supported
loopback/SSH-forwarded view and the same DSH_HOME. Alternatively, configure the
native API-key provider in Models. Do not weaken callback origin/framing checks
or route attended chat through the sealed worker gateway to avoid this native
setup step.

After installation, prove a real signed-in desktop/mobile conversation:
send, useful reply, follow-up, stop, history, reconnect and project navigation.
A local HTTP shell, deterministic fixture, successful build or green CI is a
different evidence level.

## Dedicated native ingress

The production binding is closed in source:

| Surface | Binding |
|---|---|
| Native public hostname | chat.mastermind-x.com |
| M2 attended listener | 127.0.0.1:4180 |
| VPS reverse listener | 127.0.0.1:4181 |
| Chisel audience | mastermind-deepseek-app |
| Client label | com.mastermind.executive.deepseek-tunnel |
| Existing transport owner | ops/executive_os/application_tunnel_control.py |
| Fixed DSH CLI | ops/executive_os/deepseek_tunnel_control.py |
| Existing publication owner | ops/executive_os/os_public_edge_publication.py |

The fixed DSH CLI exposes the same finite stage, apply-server, reconcile-server,
apply-client, reconcile, start-client and stop-client operations as the incumbent
application owner. It does not accept alternate ports, hosts, credentials,
executables or provider routes. Carry the original server bundle and root receipt
through the existing qualified deploy carrier. Do not reset either purpose's
original operation to create a successor.

Both new application controllers serialize the shared Chisel authfile. Before
activation, the existing edge owner must reconcile any older controller operation
that predates this shared lock. Source coordination is not exclusion of an old
running writer. A grant receipt proves only the file publication; listener,
native app and public browser acceptance remain distinct observations.

### Capture the accepted build

After the source is accepted on protected master, run the package owner's
export-publication operation with the canonical staged release, protected source
checkout/SHA and one fresh output directory under a sealed root-owned parent:

    python3 integrations/deepseek_harness/package_attended.py export-publication \
      --release /absolute/qualified/native-release \
      --source-repo /absolute/protected/source \
      --source-sha EXACT_PROTECTED_SHA \
      --out /absolute/root-owned/native-export

This requires root and reads the fixed attended-build.json from that protected
commit. The current receipt pins the already-qualified 2026-11-07 full app
package. A future rebuilt package requires its own source-reviewed build receipt;
a caller-local manifest or supplied digest cannot approve changed bytes.

The export checks the complete package without running it, captures the native
index script and stylesheet and records their source/build identities. Keep it
outside the immutable package to avoid a manifest cycle. Transfer its three
private files through the existing edge carrier, preserving root custody.

### Publish through the existing edge owner

On the actual VPS, use the existing publisher's stage-dsh command with
--artifact-path, --artifact-digest, --source-repo, --source-sha, --source-tree and
--out. It captures the complete live Caddy JSON and ETag and produces one bounded
stage. Then publish-dsh accepts only --stage-path, --stage-digest and the observed
--listener-pid.

Before its one conditional Caddy POST, the publisher validates the candidate,
rechecks the exact loopback listener and probes the native unauthenticated root
and the captured asset bytes with Host chat.mastermind-x.com. No launch token,
cookie, API key or provider request is sent by that probe. The existing OS,
Fabric and other sites retain their previous route order, TLS and storage data.

The resulting PUBLISHED receipt is a Caddy configuration receipt. Public DNS/TLS,
native cookie exchange, signed-in provider replies, reconnect/history and the OS
iframe still need their actual browser-path acceptance. Startup/autosave durability
stays with docs/OS_PUBLIC_EDGE_STARTUP.md; this publisher does not activate a
service drop-in, restart Caddy or claim persistence across restart.

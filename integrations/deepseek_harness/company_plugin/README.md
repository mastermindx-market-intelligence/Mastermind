# Mastermind company plugin for the complete DeepSeek application

This package builds and mounts in DeepSeek Harness at
`687f282e8625c6b8d11ff58211a90524be2e4317`. It adds the Mastermind brand,
Noir palette and searchable company projects through supported Cordis slots.
DeepSeek keeps its native conversation, session, workspace, composer and renderer.

## Build and local application

Use the clean, built donor checkout. This does not modify it or install a second
React runtime. The client bundle uses the donor's module loader and native store.

```sh
node integrations/deepseek_harness/company_plugin/build.mjs "$DSH_SOURCE"
node integrations/deepseek_harness/company_plugin/prepare_preview.mjs "$DSH_HOME"
sh integrations/deepseek_harness/run_local.sh --check-only
sh integrations/deepseek_harness/run_local.sh
```

`DSH_SOURCE` is an absolute clean checkout of the pinned donor, with its existing
dependencies and build outputs. `DSH_HOME` must be a **new absolute preview root**.
The preparation command refuses an existing directory and writes only its new
`state/profiles/web/cordis.patch.yml`. The original launcher supplies the isolated
home/workspace and loopback binding. Keep its local login token private.

The patch inserts the absolute `lib/index.js` package entry. Native DSH discovery
reads `package.json` and loads the exported client through `dsh.client`. Do not
edit generated `cordis.yml`, replace the donor's configuration or overwrite a
current user's patch. The host entry has no execution capability.

For native Cordis rendering tests, make the donor dependencies available to this
package (a local ignored `node_modules` symlink is sufficient), then run from this
directory:

```sh
DSH_SOURCE=/absolute/pinned/donor /absolute/pinned/donor/node_modules/.bin/vitest run --config vitest.config.mts
```

## Mastermind OS consumer

The existing Conversations destination contains Chat and Project conversations.
Existing project navigation and research conversations retain their original
owners and guards. An installed chat is the whole application in a separate
origin. The OS never imports the React 18 conversation components into React 19.

Set `VITE_MM_DSH_APP_URL` **at web release build time** to the qualified, installed
company HTTPS root URL. The value must be an exact separate subdomain under
`mastermind-x.com`, with no credentials, query, hash or port. It must not be the
OS origin. No example hostname in the tests denotes an existing installation.

Vite writes that input into the existing sealed index. Both the client URL and
Executive's exact `frame-src` addition come from those same hash-verified bytes.
An absent value preserves the existing Conversations view; an invalid value
fails the build. Configured native/Tauri builds refuse this web-only integration
until their full-app host is separately qualified.

The frame preserves the application while switching its two local tabs and
remounts on authentication generation changes. Sign-out unmounts it and clears
the company view. Native copy actions, downloads and external source links can
operate; the child cannot navigate the parent. No token or project reference
is placed in the application URL.

## Company view contract

`src/protocol.ts` is a closed presentation/navigation message contract shared by
the OS and plugin. Pairing checks exact origin, source window, donor pin and a
fresh parent challenge. Auth generation changes, reloads and view revisions
reject stale messages. A project must still be uniquely listed in the current
OS view when its original guarded navigation callback executes.

Only project titles/references, current selection, locale and theme cross this
bridge. The native snapshot store clears revoked data. Supported slot additions
are `sidebar.brand.mark`, `sidebar.brand.name`, `sidebar.panellist`, and a fresh
`main["mastermind-projects"]` entry. Native `main["conversation"]` is untouched.

## Private native history consumer

The separate host export `@mastermind/dsh-company/company-peer` provides
`createCompanySessionReadBridge(ctx)`. The default Cordis entry remains
presentation-only; loading the client plugin does not activate this export.

The existing installed Executive composition must supply each reader's exact
principal scope, authorization generation, project, native session, retirement
signal and synchronous `requireCurrent` guard. The guard owns current verified
principal, expiry, project and session-association checks. This is an in-process
capability contract, not a public request format or a new authentication source.
Do not construct it from iframe context, a native launch cookie or a caller's
session ID.

One registered non-owner policy allows only `session/projections` and
`session/page` on that exact native session. The reader keeps the donor Peer
private, joins caller/generation/Peer cancellation, and checks the incumbent
guard before dispatch and after each await. A retired reader cannot revive when
the same principal returns. Disposal retires that reader's connection scope; it
does not claim to cancel a model turn or settle an original operation.

`snapshotPage()` obtains its inclusive cut from an actual sequenced native
projection and returns the original page envelope. An absent or
migration-required projection returns no invented page or cursor. Native
`follow` is deliberately excluded because it can acquire the original writer;
this reader never invokes it just to obtain history.

Run the source qualification from this directory with the same pinned donor:

```sh
DSH_SOURCE=/absolute/pinned/donor /absolute/pinned/donor/node_modules/.bin/vitest run --config vitest.host.config.mts
```

The fixture uses the original Connection, Gateway, access policy, Session
Controller and JSONL/zstd persistence. It checks unchanged cold history while a
native writer is held, foreign-session and write refusal, late-result withholding,
generation retirement, caller cancellation and captured-identity mutation. The
fixture supplies inert company authority and makes no provider call. Its existence
does not supply the still-missing installed company session association.

## Runtime boundary and remaining delivery

This package does **not** admit company work or supply provider credentials.
A ready handshake means company project presentation is connected. It does not
prove provider readiness, a company Job, a completed response or production
acceptance.

Governed Send/resume/stop must connect the native session command owner to
existing Executive admission and ACP/MCP grants, retaining the original
operation and cancellation/result identities. A standalone donor loop and an
ACP loop must never execute the same turn. The currently qualified sealed
model-only worker profile does not authorize a streaming native chat loop.

Local proof on 2026-11-07: the compiled package mounted through the actual pinned
Cordis SlotRegistry and renderer; project rendering and revocation passed.
The full donor Web application authenticated locally and included this plugin
in its boot manifest. This proves local boot and native UI integration, not
signed-in company production chat.


## Finite Executive native history carrier

The separate `./executive-read-port` host export attaches one already-connected
Duplex to the original native Context. The injecting caller declares the exported
`inject` dependencies (`connection`, `remoteAccess`, `typertGateway`) before
calling `attachExecutiveReadPort`. The ordinary company plugin entry remains
presentation-only. Importing or exporting this leaf does not activate it.

The original host composition must supply an exact immutable association joining
the company principal namespace, canonical Runtime work/root, native session,
qualified package and composition. Its synchronous current guard and abort
signal remain authoritative. Digest-shaped strings are not package attestation;
a browser project, native cookie, caller session ID or JSON descriptor cannot
construct this capability.

Each bounded request creates a fresh non-owner reader and releases it after
`projections`/`page`. The request ID is correlation for that finite lifetime,
not the OS frontend authorization generation or a new grant. The port uses the
donor's own `createScope` to own its policy and Peers. Disposal retires access
immediately and waits for the active answer and port closure; it does not dispose
the original Session/Agent or claim to stop a provider turn. No listener,
reconnect, retry or queued second request is created.

The Python consumer is `integrations/session_bridge/deepseek_native.py`, using
`OwnedNativeReadPort` from `native_read_port.py`. The existing private bridge
accepts the closed `session_native_read` selection/cursor request. The actual
READ principal, original App binding, custody-bound Runtime, immutable root
creation evidence, exact association and original port are rechecked around the
read. The private caller cannot select a native address or promote a cold writer.
Both the native frame and the complete final CeoIngress response are bounded;
oversized pages are refused whole, including UTF-8 and the final newline.

The real process qualification can be run from the Mastermind repository:

```sh
DSH_SOURCE=/absolute/clean/pinned/donor \
DSH_NODE=/absolute/qualified/node \
python -m pytest -q tests/test_deepseek_native_read.py
```

That optional test passes an actual socket-pair endpoint to a separate Node
process. It exercises the original Gateway, SessionController and JSONL/zstd
store while the original writer remains held. It proves repeat recovery,
explicit paging, native event/stream content, unchanged stored bytes and no
Agent creation/resume. Its named fixture principal and association are not
installed OAuth or production package authority.

The packaged host export imports the original native scope module through one
fixed internal dependency link. It does not bundle another Cordis runtime.
The attended packager validates that link and retains it in the complete package
inventory. Historical build records remain tied to their exact old export set;
every newly staged build requires both private host exports.

Production is still unavailable until the original native launcher/bootstrap
hands Executive a qualified endpoint and an accepted company/root/session
association. The stock browser-owner boundary and authenticated native
Send/resume/Stop remain separate open work. See
[the exact native join frontier](../NATIVE_COMPANY_JOIN_FRONTIER.md).

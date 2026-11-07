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

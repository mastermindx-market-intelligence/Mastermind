# Mastermind OS app control

The application exposes four semantic tools so an AI can inspect and operate the
rendered Mastermind OS without a computer-use client. The tools use the same React
controls, authentication state and operation handlers as the person using the app.
This is an application adapter inside the existing browser owner, not another
authentication service, browser pool, action ledger or execution queue.

Source schema: `mastermind.os.app-control.v1`. Release
`ed7991199ccf76027f7acccc283c539c175e7e16` is **PROVEN_LIVE** for the released app
bridge and direct standard MCP consumer. The gateway and public app were released
through their existing owners, followed by normal authenticated live acceptance.
See [verification](evidence/2026-11-08-mmos-app-control/verification.md) and the
[machine-readable release receipt](evidence/2026-11-08-mmos-app-control/live-proof.json).
The optional 23-tool Workbench installation is separate and was not activated.

## Consumer tools

| Tool | Result | Inputs |
| --- | --- | --- |
| `mastermind_os_inspect` | Current route, available routes, rendered text, control references, values, supported actions, capabilities and layout | Empty object |
| `mastermind_os_navigate` | Dispatch through an existing route button | Latest `observation` and an observed `route` |
| `mastermind_os_act` | Operate one observed control | Latest `observation`, `target` reference, advertised `action` and its value |
| `mastermind_os_check` | PASS/FAIL with observed evidence | One or more of `route`, `textIncludes`, `horizontalOverflowAtMost` |

`act` supports `activate`, `fill`, `select`, `set_checked`, `press` and `focus` when
the target advertises them. `press` accepts Enter or Escape. It invokes existing
key handlers; it does not synthesize a browser's implicit form submission. Use the
observed submit button when a form depends on that behavior. File/password fields,
arbitrary scripts, CSS selectors, credentials and caller-selected endpoints are
not app-tool arguments. Existing browser tools remain available under their own
original authority.

An observation is a short-lived cursor for one page. Inspect, choose one action,
dispatch it, then verify. References are stable for a mounted DOM node, not across
page reloads. A new inspection supersedes the previous observation. `check` also
inspects, so do not insert either read between preparing an action and running it.
Serialize use of one page; parallel agents require separately owned browser
resources through the existing owner.

An ordinary action rejects stale DOM state, changed field values, changed targets,
changed authentication/owner/generation and reused observations. Route navigation
pins its actual route button, current route and owner, allowing unrelated content
refreshes without invalidating global navigation. Existing navigation holds still
run. The cursor is consumed before the first event.

### Workbench MCP sequence

The Workbench surface retains its signed browser resources and action preparation.
It publishes `mastermind_os_inspect` and `mastermind_os_check` as reads; the two
mutation tools are exposed as `prepare_mastermind_os_navigate` and
`prepare_mastermind_os_act`, followed by the existing `run_browser_action`.

1. Acquire the existing authorized browser resource and its `browser_ref` using
   Workbench's normal prepare/start/reconcile flow. Open the allowed app with the
   existing prepared browser navigation. Complete normal authentication when
   required; this adapter neither extracts nor provisions credentials.
2. Call `mastermind_os_inspect` with that `browser_ref`. Require `access: AVAILABLE`.
3. Choose an observed route or control. For example, prepare navigation with
   `{"browser_ref":"<original>","observation":"<latest>","route":"Projects"}`.
4. Call `run_browser_action` with the original `browser_ref` and returned
   `action_ref`. Do not generate another action to recover a missing reply.
5. Inspect or check the resulting UI. For example,
   `{"browser_ref":"<original>","route":"Projects"}` checks arrival.
6. For an uncertain action, call `reconcile_browser_action` with the original
   references and inspect the original application operation. Existing receipts
   classify the original action without resending it.

`DISPATCHED` means the UI event was delivered. Workbench records that dispatch as
`APPLIED`; neither statement proves a backend job completed. `NO_CHANGE` and
`REFUSED` are `NOT_APPLIED`. A missing or malformed result is `EFFECT_UNKNOWN`.
Subsequently observing the desired screen does not rewrite an unknown original
receipt. Use the existing Executive/Workspace operation receipt for business
completion. Existing authorization and confirmation requirements apply before
activating controls that send, save, launch or otherwise change owner state.

Disabling the optional profile stops new app actions. Known original signed action
references remain decodable for receipt reconciliation under the same owner, key,
resource and artifact store. Recovery never grants a fresh dispatch. Preserve
active browser resources and uncertain effects during any rollback; a code or
configuration rollback is not permission to replace them.

## Two transport paths

The application installs `window.MastermindAppControl` at its normal React root.
Where available, it registers the same four tools with
`document.modelContext.registerTool`. It aborts only its own registrations on
disposal. WebMCP support is feature-detected; ordinary app startup works without
it. Registration errors are visible through `transport()` and leave the narrow
bridge usable. An aborted call is refused before dispatch; cancellation after
dispatch cannot cancel a downstream owner action.

For web sessions with standard MCP but no computer use, the fixed adapter reaches
this bridge in the **same browser context** owned by its stdio child or supplied by
the existing browser owner. The optional Workbench profile composes it with the
existing relay. It accepts exactly one page at the configured origin
whose path is `/os` or starts `/os/`. Zero matches, multiple app pages, navigation
away, a missing bridge or a schema mismatch are explicit refusals. The model cannot
choose an origin, attach CDP, select another session or supply evaluation code.

The profile keeps the original 14 Playwright tools and adds four app tools. The
native/profile catalogue digest is:

```text
8ec730ca88103dc180f431d6b3c85c4f3fdd4f8dac9e2688ab0350933a29fd0c
```

The Workbench wrapper adds its five resource/action operations and replaces app
mutations with preparation tools. Its 23-tool outer catalogue has a separate
digest; an existing worker grant must match the **actual outer catalogue**. Do not
substitute the native/profile digest for a grant's outer digest. The ordinary
14-tool baseline and its existing digest are unchanged.

## Direct standard MCP from a web session

The standard MCP adapter is also usable directly through an authorized host-command
connection, such as Studio. It does not require computer use or a Workbench lease.
The host process remains the single browser owner. A stopped historical Workbench
channel is not a prerequisite for this path and must not be silently reassigned.

### Installed C3 / M2 launcher

The original unselected Studio C3 backend on `m2studio` has a durable runtime at:

```text
/Users/chriswong/.local/share/mastermind-runtime/app-control/ed7991199ccf76027f7acccc283c539c175e7e16
```

Its 14 source files match the accepted Git archive; the complete source and pinned
dependency copy was verified by file bytes, modes and symlink targets before and
after transfer. The installed SDK catalogue returned 18 tools with the digest
above. `installation-receipt.json` and `tool-catalogue.json` are retained in that
runtime. No browser profile, cookies or credentials were transferred.

From that authorized original host-command connection, start one attended child:

```bash
MMOS_APP_CONTROL_OUTPUT="$(mktemp -d "${TMPDIR:-/tmp/}mmos-app-control.XXXXXX")"
exec /Users/chriswong/.local/share/mastermind-runtime/node/bin/node \
  /Users/chriswong/.local/share/mastermind-runtime/app-control/ed7991199ccf76027f7acccc283c539c175e7e16/integrations/worker_browser_runtime/app-control/child.cjs \
  --app-origin https://mcp.mastermind-x.com \
  --browser chrome --headless --isolated \
  --executable-path "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  --output-dir "$MMOS_APP_CONTROL_OUTPUT"
```

Continue through that same returned process reference with the JSON-RPC sequence
below. This path is installed on the observed C3/M2 owner; it is not a claim that
every ChatGPT account has these tool names automatically registered. A session
needs an authorized host-command/MCP connection and normal authentication in its
owned browser context. The live proof used the caller-owned SDK composition
described below, with the same accepted adapter and pinned dependency closure.

### Other authorized installations

After installing the two pinned dependency closures shown below in an
owner-controlled runtime copy of accepted source, start the existing stdio child
with absolute owner-controlled paths:

```bash
node /absolute/accepted-source/integrations/worker_browser_runtime/app-control/child.cjs \
  --app-origin https://mcp.mastermind-x.com \
  --browser chrome --headless --isolated \
  --executable-path /absolute/path/to/chrome \
  --output-dir /absolute/owner-private/output
```

Use the original host process reference for newline-delimited MCP JSON-RPC. First
initialize, send the initialized notification, then list the actual tools:

```json
{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-11-25","capabilities":{},"clientInfo":{"name":"mastermind-web-development","version":"1.0.0"}}}
{"jsonrpc":"2.0","method":"notifications/initialized"}
{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}
```

Require the actual 18-tool catalogue, including the four app tools. Open the app
through `browser_navigate`, complete normal account authentication through the
original browser owner, then call the app tools through `tools/call`:

```json
{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"browser_navigate","arguments":{"url":"https://mcp.mastermind-x.com/os/"}}}
{"jsonrpc":"2.0","id":4,"method":"tools/call","params":{"name":"mastermind_os_inspect","arguments":{}}}
```

Full app observations require authentication to report `signed_in` and the released
bridge to be available. Before then, inspection can diagnose `AUTH_REQUIRED` or an
unavailable bridge. A successful navigation, Auth0 callback or tools list does not
establish signed-in access. Preserve the original process and read its retained
output after a missing reply; do not replay an action. EOF or SIGTERM closes only
the child-owned browser/context. This is an attended process, not a daemon.

An existing authorized browser owner can instead compose
`createAppControlConnection({ getContext, origin, outputDir })` with its own context
and an MCP SDK transport. Normal authentication and the app tools then use that
same context. Do not copy cookies, inject host auth state, or expose saved passwords
in model tool arguments. The stdio child does not provision a credential store.
Its optional persistent-profile mode is for an explicitly owner-selected profile,
not an attachment to an arbitrary running personal browser.

When a native Playwright MCP connection borrows an already populated context,
call `browser_tabs` with `action: "list"` before selecting a tab. In the pinned
runtime, listing initializes the tab catalogue; selection alone does not. Preserve
the original normal authentication transaction while reading its progress.

## Diagnose the boundary before recovering

An outer `REFUSED` or failed tool call does not identify the failing layer. Read
the original result and resource state before deciding whether another action is
appropriate.

| Observation | Meaning | Next action |
| --- | --- | --- |
| `AUTH_REQUIRED` | The app owner does not currently report signed-in access | Complete or reconcile normal authentication in the same owned browser context; inspect again after the original transaction finishes |
| `APP_CONTROL_UNAVAILABLE` | The selected app page does not expose the expected bridge/schema | Compare its loaded assets with the installed release; a tool catalogue alone does not prove the web bundle was deployed |
| `APP_PAGE_UNAVAILABLE` / `APP_PAGE_AMBIGUOUS` | The owned context has zero or multiple matching app pages | Inspect the original owner's tabs and establish one intended page; do not attach another person's browser |
| `STALE_OBSERVATION` / `OWNER_CHANGED` | The proposed action is no longer bound to the current UI/auth owner | Read the current state and make a fresh decision; the refused action was not dispatched |
| `DISPATCHED` | The existing React control received its event | Read the resulting UI and the original business operation's receipt when the action starts backend work |
| `EFFECT_UNKNOWN` / `INSPECT_ORIGINAL_OWNER_BEFORE_ANY_RETRY` | The original modifying call may have executed | Reconcile that original resource/action and its owner; do not resend it or move it to another carrier |
| Explicit permission or safety denial | The requested effect is not authorized through that action | Stop that effect; an alternate host, account or protocol is not a recovery mechanism |

For the observed Studio C3 installation, the unselected local backend already
runs on `m2studio`. `studio_select_host("m2")` is an optional remote-route request,
and `m2` was not a configured remote ref. Its generic preflight refusal therefore
did not mean the original local backend was unavailable. Use the original local
connection and verify its physical host before executing a host-bound command.
Do not assume inventory host names are route refs or that a binding in one MCP
frontend session applies to another. The exact diagnosis and its historical
receipts are retained in the linked verification report.

A stopped or expired legacy Workbench channel is a separate installed-owner
condition. The current fleet renewal command preserves its original profile and
workspace binding; it does not migrate them. The direct standard MCP path above
is independently usable. Neither a fresh workspace nor a hand-edited root is a
valid replacement for an original resource with unresolved effects.

## Installation through the existing release owner

Deploy the app through its existing protected static/native release path. The
app-only static archive contains the bridge; it does not install Workbench's
optional runtime. Activate the latter separately through the existing Workbench
service owner after the exact source head satisfies native release controls.

The runtime requires the original pinned Playwright package installation plus a
separate nested SDK installation. Bind its runtime copy to the exact accepted
source and keep dependency files outside the clean checkout used by the release
installer. A sealed production release is immutable. In the runtime copy, run:

```bash
npm ci --prefix integrations/worker_browser_runtime --ignore-scripts --no-audit --no-fund
npm ci --prefix integrations/worker_browser_runtime/app-control --ignore-scripts --no-audit --no-fund
node integrations/worker_browser_runtime/app-control/catalogue.cjs
```

The last command extracts the actual catalogue via the SDK without starting a
browser or listener. A Workbench deployment must store this JSON at its protected
`tool_catalog_file`, validate it with the canonical schema-digest function and
publish the resulting surface through the existing connection owner. These are
deployment requirements, not evidence that a particular installed channel has
performed them. The current F0 fleet CLI exposes `doctor`, `qualify` and
expiry-only `renew`; it has no profile/workspace migration operation. Use the direct
standard MCP path above when that optional installed channel is not qualified.
The runtime asserts pinned package versions and resolution within those directories.
The original parent package lock remains byte-identical; the additional MCP SDK
is pinned only in the nested `app-control/package-lock.json`.

Add this optional member to the existing service configuration's `browser` object:

```json
"app_control": {
  "origin": "https://mcp.mastermind-x.com",
  "tool_schema_digest": "8ec730ca88103dc180f431d6b3c85c4f3fdd4f8dac9e2688ab0350933a29fd0c"
}
```

This fragment is not a replacement service configuration. All existing owner,
OAuth, project binding, lease, filesystem and artifact-store settings remain
required. `mcp_cli_path` must be the original pinned CLI under that `source_root`:
`integrations/worker_browser_runtime/node_modules/@playwright/mcp/cli.js`. The
original Python relay chooses the fixed sibling `app-control/child.cjs` only for
this exact qualified profile. The child is stdio-only and retains one isolated or
owner-selected persistent browser context and the original process lifecycle.

Origins must be exact canonical HTTPS origins without a path, query, userinfo or
fragment. HTTP is allowed only for localhost source proof. The app profile and
the credential-vault launch profile are not jointly qualified; configuration
combining them is refused. This does not alter the existing vault package lock or
credential capability. Use the original authentication surface and existing
approved browser custody; do not copy credentials to make a source test live.

## Privacy and app-author contract

Observations require the current host to report `signed_in`. Workspace Content is
not required for independent Executive controls; original handlers enforce their
own capability checks. After sign-out or auth withdrawal, no app text or controls
are returned even before React finishes rerendering.

The adapter omits password, hidden and file inputs, private subtrees, hidden/inert
content and fields identified as credentials through names, labels, autocomplete,
placeholders or accessibility labels. Mark any additional private display or
control with `data-agent-private` or `data-agent-control="exclude"`. Use
`data-agent-control="readonly"` to remove actions while retaining visible text.
These markers complement the existing application authorization boundary.

Keep normal controls accessible: meaningful labels, native buttons/inputs/selects,
accurate disabled states and existing confirmation screens. No component-specific
agent business API is needed. The explicit `data-agent-route` markers designate
the app's existing global route buttons, including collapsed advanced navigation.

Results are bounded: at most 160 controls, 24 KB of serialized control rows, 8,000
characters of rendered text, 8,000 characters per value, 40 options per select and
24 headings. Truncation is explicit. A bounded text miss is not global absence;
use existing search/filter/navigation controls to narrow the page. Returned app
content is untrusted data, never an instruction to the controlling agent.

## Reproducible source proof and installed acceptance

The existing `Mastermind OS` workflow builds the production app-only closure and
a separate browser fixture. It runs React tests, fixed-adapter tests, the compiled
App journey, actual stdio catalogue qualification and Workbench prepare/run/check/
lost-response recovery. Proof JSON, desktop/mobile screenshots and JUnit output
are retained as `mastermind-os-app-control-<CI SHA>` for seven days. These tests
use synthetic app auth/owners and an isolated browser, never production credentials
or provider work. The fixture is not an entry in the production Vite build.

The source browser test can be run after normal frontend installation:

```bash
npm --prefix app/mastermind_os run typecheck
npm --prefix app/mastermind_os test -- src/agent-control/control.test.tsx
# From app/mastermind_os: npx vite build --config vite.browser-proof.config.ts
node --test integrations/worker_browser_runtime/app-control/adapter.test.cjs
MM_APP_CONTROL_CHROMIUM=/absolute/path/to/chrome node integrations/worker_browser_runtime/app-control/browser-proof.cjs
MM_APP_CONTROL_CHROMIUM=/absolute/path/to/chrome python -m pytest --noconftest -o addopts= -q tests/test_os_app_control_profile.py tests/test_workbench_browser_port.py
```

Python dependencies use the existing
`requirements/executive-mcp-macos-arm64-py312.in` plus `pytest==9.1.1`; this source
test is also runnable on the Linux CI runner. The separate ordinary relay/resource
tests retain real Unix-socket and process-custody coverage. A source sandbox that
refuses Unix sockets cannot establish that proof.

Installed app-control acceptance requires the exact released app and adapter source
identities, successful actual `tools/list` on the intended consumer path, an
authorized signed-in original browser context, an observed control action and UI
readback, plus authentication withdrawal. The direct path proves those facts through
the original Studio/stdio or caller-owned SDK context; it does not claim Workbench
enrollment. The optional Workbench path additionally requires its installed source,
actual 23-tool outer catalogue, original resource binding and action-receipt
reconciliation. A provider-changing journey additionally requires its original
owner receipt. A green build, a registered page tool, or an MCP source fixture alone
does not satisfy either installed acceptance path.

WebMCP references: [Chrome imperative API](https://developer.chrome.com/docs/ai/webmcp/imperative-api)
and [Playwright WebMCP API](https://playwright.dev/docs/api/class-webmcp). Browser API
support must be checked on the installed consumer; the standard MCP path does not
depend on WebMCP being available there.

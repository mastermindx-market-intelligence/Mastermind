# Mastermind OS app control

The application exposes four semantic tools so an AI can inspect and operate the
rendered Mastermind OS without a computer-use client. The tools use the same React
controls, authentication state and operation handlers as the person using the app.
This is an application adapter inside the existing browser owner, not another
authentication service, browser pool, action ledger or execution queue.

Source schema: `mastermind.os.app-control.v1`. Source qualification is recorded in
[`evidence/2026-11-08-mmos-app-control/verification.md`](evidence/2026-11-08-mmos-app-control/verification.md).
Source qualification does not establish that an installed ChatGPT connection has
published these tools or that the production application has been released.

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

For web sessions with standard MCP but no computer use, the optional Workbench
profile reaches this bridge with fixed adapter code in the **same browser context**
owned by the existing relay. It accepts exactly one page at the configured origin
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

## Installation through the existing release owner

Deploy the app through its existing protected static/native release path. The
app-only static archive contains the bridge; it does not install Workbench's
optional runtime. Activate the latter separately through the existing Workbench
service owner after the exact source head satisfies native release controls.

The runtime requires the original pinned Playwright package installation plus a
separate nested SDK installation in the accepted source release:

```bash
npm ci --prefix integrations/worker_browser_runtime --ignore-scripts --no-audit --no-fund
npm ci --prefix integrations/worker_browser_runtime/app-control --ignore-scripts --no-audit --no-fund
node integrations/worker_browser_runtime/app-control/catalogue.cjs
```

The last command extracts the actual catalogue via the SDK without starting a
browser or listener. The existing installer stores this JSON at its protected
`tool_catalog_file`, validates it with the canonical schema-digest function and
publishes the resulting Workbench surface through its existing connection. The
runtime asserts pinned package versions and resolution within those directories.
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

Installed acceptance requires the exact released app and Workbench source
identities, successful actual `tools/list` on the intended web connection, an
authorized signed-in original browser resource, an observed control action and UI
readback, plus authentication withdrawal and original-action reconciliation. A
provider-changing journey additionally requires its original owner receipt. A
green build, a registered page tool, or an MCP source fixture alone does not satisfy
that acceptance.

WebMCP references: [Chrome imperative API](https://developer.chrome.com/docs/ai/webmcp/imperative-api)
and [Playwright WebMCP API](https://playwright.dev/docs/api/class-webmcp). Browser API
support must be checked on the installed consumer; the standard MCP path does not
depend on WebMCP being available there.

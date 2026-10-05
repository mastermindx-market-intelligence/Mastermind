# Browser Fabric — Chrome DevTools MCP backend amendment

Date: 2026-10-05. Operation: `browser-fabric-attached-tabs-20261005-c2-001`.
Protected Mastermind pin: `7eac3ec252475600147ec9a376b8ca16403ac4c5`.
Parent: Draft PR #1259.

**State: SOURCE CANDIDATE / NOT INSTALLED / MISSION_COMPLETE=false.**

## Decision

Use **Chrome DevTools MCP as the low-level actuator for existing interactive
Chrome sessions**, underneath Mastermind's existing Browser owner. Keep the
custom Browser Link extension as optional explicit-share UX/fallback work, not
as the canonical effect, retry, tab-lock or placement owner.

This amendment does not replace the managed isolated/persistent Playwright
browser path. The two actuator families serve different cases:

- managed Playwright: isolated or owner-selected persistent automation browser;
- DevTools auto-connect: an already-running, already-authenticated human Chrome
  profile that deliberately enables remote debugging and accepts the connection.

All Web CEO and native worker callers still terminate in the same Mastermind
Browser facade, Browser/Runtime effect owner and Capacity path. Models never
connect to Chrome DevTools MCP directly.

## Why the pivot

The earlier Browser Link canary used `--load-extension`. Chrome removed that
command-line flag from branded Chrome in milestone 137. The M2 host is Chrome
154. A fresh isolated M2 canary returned no administrator loading error but
also did not register the extension, which is expected after the flag removal.

Chrome DevTools MCP 1.10.1 was then installed into the existing operation
evidence directory. Its current CLI has:

- `--autoConnect` for an already-running Chrome 144+ instance;
- `--pageIdRouting` enabled by default and explicitly described for concurrent
  agent sessions;
- required per-page `pageId` on page-scoped tools;
- Chrome user permission for auto-connecting to an existing session;
- closed category toggles and JavaScript-evaluation disablement;
- URL allow/block policy support;
- screenshot size/format controls.

Official Chrome documentation also states that existing-session connection
inherits the active cookies/login state. That is exactly the desired mechanism,
but it increases the importance of Mastermind-side tab grants: backend access is
broader than any individual Web CEO's authorization.

Primary external references checked:
- https://developer.chrome.com/blog/extension-news-june-2025
- https://developer.chrome.com/docs/devtools/agents/get-started/configuration
- https://developer.chrome.com/docs/devtools/agents/use-cases/auto-connect
- https://github.com/ChromeDevTools/chrome-devtools-mcp/blob/main/docs/tool-reference.md
- https://developer.chrome.com/docs/extensions/how-to/distribute

## Authority and process boundary

Chrome DevTools MCP is a **private actuator dependency**, not a model-facing
authority. It does not own browser placement, caller identity, leases, retries,
effect state, credentials or tab sharing.

Existing #1071 BrowserActionPort remains the intended durable mutation owner:
it already binds resource/caller/generation, claims the action durably,
revalidates immediately before dispatch, records APPLIED/NOT_APPLIED, and keeps
a transport-lost mutation EFFECT_UNKNOWN without replay. #1057's exact
OperatorMaterializationReceipt join remains the launch identity source for
workers.

The DevTools adapter sits *under* that port:

```
Web Browser plugin / native private MCP
          |
Mastermind Browser facade
          |
existing BrowserActionPort + Runtime/Capacity
          |
private DevTools adapter (this amendment)
          |
one broker-owned Chrome DevTools MCP connection
          |
exact Chrome profile / pageId
```

The Browser broker should keep one trusted DevTools connection per enrolled
profile/Chrome instance and multiplex separately authenticated Mastermind
callers above it. This is preferable to N independent agents each attaching to
Chrome.

## Private backend profile

Pinned source version for this candidate: `chrome-devtools-mcp@1.10.1`.

`build_auto_connect_plan` intentionally projects only trusted host config. It
requires the exact installed version and an owner-observed tool-schema digest.
The candidate plan enables auto-connect and page-ID routing, disables usage
statistics, CrUX, performance/network/memory/emulation categories, and
JavaScript evaluation, and bounds screenshots.

The backend may still contain tools Mastermind never grants. The private
adapter exposes only:

```
list_pages
take_snapshot
take_screenshot
wait_for
click
fill
type_text
press_key
navigate_page
```

Mastermind additionally removes file-output arguments, model-controlled
timeouts, full-page screenshots, scripts, uploads, arbitrary new/close/select
page operations, drag/hover, network reads and extension management.

The backend `pageId` is not a durable company identity. The Browser owner
must bind it to host/profile/browser boot/DevTools generation/tab/document and
caller grant. Reconnect invalidates the transient page mapping unless the
existing owner proves the same resource generation.

## Concurrency

Do not use Chrome DevTools MCP's selected-page state as the authority. Every
page-scoped call carries an explicit `pageId`.

Mastermind provides the higher-level concurrency contract:

- multiple admitted readers may observe one exact tab concurrently;
- one mutation holds the exact tab writer fence;
- profile-wide effects require stronger admission;
- another agent cannot reuse a snapshot UID without the owner's current
  page/document binding;
- an uncertain action stays attached to its original resource and cannot be
  load-balanced elsewhere.

Chrome DevTools MCP's page routing removes a major source of accidental
cross-agent targeting, but does not itself implement these ownership rules.

## Installation/distribution consequence

The extension is no longer required to make browser control work. If retained
for Share/Stop UX, test it with the supported DevTools extension-management
tools or Developer Mode, then distribute it through the Chrome Web Store or
managed enterprise extension policy. Do not revive `--load-extension` as a
production or current-Chrome test strategy.

Auto-connect itself requires remote debugging to be enabled in Chrome
(`chrome://inspect/#remote-debugging`) and Chrome presents a user permission
dialog. That consent remains an enrollment step; do not bypass it. A persistent
broker connection minimizes repeated prompts.

## Candidate source and tests

New disjoint source:
- `integrations/mastermind_browser_devtools/contract.py`
- `integrations/mastermind_browser_devtools/__init__.py`
- `tests/test_mastermind_browser_devtools_contract.py`

TDD evidence:
- RED: module absent; collection failed only for that missing module.
- GREEN: **32 passed**.

The source is pure: no subprocess, Chrome, MCP, filesystem write, credential,
socket, clock, scheduling or effect operation. Live backend launch remains a
separate B4/B6 integration step after incumbent browser source is accepted.

## Next vertical

1. Independently review this backend contract.
2. Obtain an actual `tools/list` catalog from the pinned backend and persist
   its selected-schema digest through the existing Browser resource identity.
3. Compose the backend child through #1071's existing `McpStdioSession` /
   relay owner once that incumbent source is accepted; do not copy its relay.
4. Enable remote debugging on one dedicated enrolled Chrome profile and accept
   the Chrome connection prompt.
5. Prove two independently authenticated Mastermind callers reading one page,
   serialized mutation, wrong-page refusal, reconnect generation invalidation,
   late/unknown effect retention and original-parent result consumption.
6. Enroll a second browser host/profile and prove Capacity placement/failover.
7. Create the separate Browser Web plugin/tunnel binding.
8. Auth0 API/client/workspace linking remains last.

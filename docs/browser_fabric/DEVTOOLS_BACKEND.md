# Browser Fabric — Chrome DevTools MCP backend amendment

Date: 2026-10-05. Operation: `browser-fabric-attached-tabs-20261005-c2-001`.
Protected Mastermind pin: `7eac3ec252475600147ec9a376b8ca16403ac4c5`.
Parent: Draft PR #1259.

**State: SOURCE CANDIDATE / NOT INSTALLED / MISSION_COMPLETE=false.**

## 2026-10-06 correction — split managed profiles from shared human Chrome

Current protected compatibility pin: `877b1e7f275da0b6d3558d2667778b32d628bf67`.
The original 2026-10-05 pin remains the source base of the candidate below; the
bounded protected movement did not touch Browser/Capacity/procedure paths relevant
to this correction.

The earlier conclusion that Chrome DevTools MCP `--autoConnect` should be the
canonical actuator for the user's normal signed-in default Chrome profile is
**superseded**. Keep DevTools MCP for Mastermind-managed non-default debugging
profiles. Keep the Browser Link extension/native-host path as the canonical
mechanism for deliberately sharing tabs from normal human Chrome.

This correction is evidence-driven:

- M2 stable Chrome 154 reports the remote-debugging preference as user-enabled.
- the Chrome browser process listens on loopback port 9222, but the normal
  `/json/version`, `/json/list`, `/json/protocol` endpoints return 404;
- the default Chrome data root has no `DevToolsActivePort`;
- pinned `chrome-devtools-mcp@1.10.1` initializes and exposes its full catalog,
  including page-ID routing, but `list_pages` cannot attach to that default
  profile because the required `DevToolsActivePort` is absent;
- current upstream issues #1830/#2283 describe the same Chrome 150+ default-profile
  hardening/permission-proxy behavior. Do not depend on that unresolved upstream
  attach path for Mastermind's core shared-human-browser capability.

The complementary managed-profile lane is proven on real Chrome. A disposable
non-default profile launched with `--remote-debugging-port=0` produced its
`DevToolsActivePort`; pinned backend 1.10.1 then connected through the existing
contract, verified the selected tool schema digest
`a96d57919b458c0ea5e8dd0abf6e290080e0a7b2afb97b9e37147498debedf9b`, routed
by explicit `pageId`, captured a real accessibility snapshot, filled a real input,
clicked a real button, observed the final page state, and left zero owned processes.
The current focused Browser campaign is **146 passed**.

Therefore the two actuator families are now:

1. **managed browser profile** → pinned Chrome DevTools MCP / Playwright under the
   existing Browser owner, suitable for isolated or intentionally persistent
   automation profiles;
2. **shared human Chrome tab** → Browser Link MV3 extension + Native Messaging host,
   with explicit Share/Stop, exact tab/document/consent generation and the same
   Browser/Runtime effect owner above it.

This is not a second scheduler or effect plane. Capacity may choose among already
enrolled compatible resources, but an `EFFECT_UNKNOWN` action remains stuck to its
original resource and caller until reconciled. Auth0 remains a later Web-ingress
linking step, not browser-session authentication.


## Historical 2026-10-05 decision — superseded for default human Chrome

The original amendment proposed **Chrome DevTools MCP as the low-level actuator
for existing interactive Chrome sessions** and treated Browser Link as optional.
The 2026-10-06 evidence above supersedes that part: DevTools MCP remains the
managed-profile actuator; Browser Link is the shared-human-tab actuator. The
existing Browser owner still remains canonical for effect, retry, tab-lock and
placement semantics above either backend.

This amendment does not replace the managed isolated/persistent Playwright
browser path. The two actuator families serve different cases:

- managed Playwright: isolated or owner-selected persistent automation browser;
- DevTools auto-connect: an already-running **Mastermind-managed non-default**
  Chrome profile with a real `DevToolsActivePort`;
- Browser Link: an explicitly shared tab in the user's normal signed-in Chrome.

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


## Real Chrome 154 / MCP 1.10.1 acceptance — 2026-10-06

A real disposable-profile canary now closes the backend-mechanism question for
the reviewed candidate. This is **not** existing-user-profile enrollment,
multi-caller admission, Capacity placement, Auth0, or production installation.

Environment and exact source:

- Mastermind PR #1259 candidate: `a24ef231f45af4f56eef1f9ee420d584b0b82e8c`.
- protected Mastermind observed before this canary:
  `877b1e7f275da0b6d3558d2667778b32d628bf67`; its bounded movement from the
  original 7eac3ec pin touched no Browser/Capacity/procedure paths.
- Google Chrome: `154.0.8037.95`.
- Chrome DevTools MCP: server `chrome_devtools 1.10.1`, stdio transport.
- Browser connection: `--browser-url` to a disposable Chrome user-data
  directory with an ephemeral loopback DevTools port.
- Test page: disposable loopback HTTP content. No existing Chrome profile,
  user cookies, external website credential, OpenAI tunnel, or Auth0 was used.

The actual backend `tools/list` catalog passed
`attest_backend_catalog`. Mastermind selected exactly:

`click, fill, list_pages, navigate_page, press_key, take_screenshot,
take_snapshot, type_text, wait_for`

with selected-schema SHA-256
`45616b0bd85740d998d65a5573b5c574bd83ca19329b47d6aa9f8a9930eb6015`.
The live schemas required `pageId` on every selected page-scoped tool and
did not permit it on `list_pages`. The same Mastermind projector refused
`evaluate_script`.

Real projected calls then succeeded against Chrome:

1. `list_pages` identified page ID 1.
2. `take_snapshot` returned bounded accessibility identities including
   button UID `1_2` and textbox UID `1_4`.
3. projected `click` changed the page-owned state to `clicked`.
4. projected `fill` changed the textbox value to `Mastermind`.
5. projected `wait_for` observed `clicked`.
6. a second projected snapshot observed both the changed text and textbox
   value.
7. projected `take_screenshot` returned a JPEG image payload (14,300
   encoded bytes in this run).

Evidence owner:
`/Volumes/Mastermind/evidence/browser-fabric-attached-tabs-20261005-c2-001/real-devtools-canary-20261006/`.

Receipt SHA-256:
`99abe54110b56d26b98936469880dfeeac4712dd85cb65ab702e306293fded91`.
The retained MCP stdout SHA-256 is
`f376aa123ff4e49682f7ac31dd17950356203723672bc836adce617f8998a4ff`.

This proves the pinned private backend plus Mastermind projection can observe
and mutate one exact real Chrome page without exposing the backend's wider
tool catalog to the intended upper layer. It does not prove that a logged-in
human Chrome profile is enrolled or that two Mastermind callers share one
brokered connection safely. Those remain the next acceptance cases. Official
Chrome DevTools MCP documentation states that `--autoConnect` requires Chrome
144+ with remote debugging enabled through `chrome://inspect/#remote-debugging`
and user approval; page-ID routing is enabled by default for shared-server
concurrent sessions. That human consent remains an enrollment gate, not a
reason to weaken the Mastermind caller/tab/effect owner.

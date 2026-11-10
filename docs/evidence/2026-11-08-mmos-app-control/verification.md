# Mastermind OS app control — release and live acceptance

## Current status — 2026-11-09

**PROVEN_LIVE** for the released app-control bridge and direct standard MCP
consumer. The app-control release acceptance in the execution plan is satisfied.
This is not an application-wide launch-readiness claim or a claim that every
ChatGPT account has the optional Workbench tools installed.

Before this change, a web session without computer use lacked a general semantic
interface to the actual React app. After it, an authorized web tool consumer can
inspect the signed-in app, navigate its existing routes, edit and activate observed
controls, and verify the result through the original browser owner. The four tools
are `mastermind_os_inspect`, `mastermind_os_navigate`, `mastermind_os_act` and
`mastermind_os_check`.

The accepted source is
[`ed7991199ccf76027f7acccc283c539c175e7e16`](https://github.com/mastermindx-market-intelligence/Mastermind/commit/ed7991199ccf76027f7acccc283c539c175e7e16),
tree `a157a30dcee098e43a694836b70047db6328e689`, merged through the protected native
queue in [PR #2305](https://github.com/mastermindx-market-intelligence/Mastermind/pull/2305)
at `2026-11-09T02:54:58Z`. Required integrated CI
[42548210214](https://github.com/mastermindx-market-intelligence/Mastermind/actions/runs/42548210214)
and the Mastermind OS workflow
[42548210279](https://github.com/mastermindx-market-intelligence/Mastermind/actions/runs/42548210279)
succeeded. Full immutable identities, owner receipt locations and the safe call
trace are in [`live-proof.json`](live-proof.json).

### Actual release and consumer proof

| Layer | Observed result |
| --- | --- |
| Accepted static build | Exact accepted source; 12-asset private-entry profile; bundle digest `3fd32f2af9315faddc5546ce2f34dc5c64877f730226cd059b7b2f10b84e8f43` |
| Existing MCP gateway owner | Component update `COMPLETE`; sealed accepted release, configuration/plist after-images, dedicated UID 458 process and exact `127.0.0.1:8443` listener joined; transaction marker absent |
| Existing public edge owner | Publication `FINAL`; new HTML, callback and assets verified; live configuration equals final configuration and startup autosave; existing relay preserved |
| Actual authenticated consumer | Normal Auth0 sign-in in a new owned isolated Chrome 157 context, then the accepted adapter and actual 18-tool MCP catalogue in that same context |
| Granular control | Today → Search → advanced Programs navigation; disclosure activation; React-controlled search fill, readback and restoration; theme dark → light → dark |
| Staleness | Deliberate reuse of a consumed observation returned `REFUSED / STALE_OBSERVATION`; original field value remained unchanged |
| Layout and readback | Desktop 1440×1000 and mobile 390×844 route/overflow checks passed with zero horizontal overflow; desktop restored |
| Authentication withdrawal | Sign-out immediately returned `signed_out / AUTH_REQUIRED`, empty text, controls, routes and headings; independent inspection confirmed the same result |
| Cleanup | Owned browser closed; no browser descendants remained; the original closed proof driver was terminated and its PID absence read back |
| Durable launcher | Accepted 14-file source plus pinned dependencies copied to the original owner's durable runtime; 4,562 inventory objects matched by bytes/modes/link targets; actual 18-tool catalogue and canonical digest reverified |

The live trace contains **26 MCP calls, including 18 app-tool calls**. Its sole
tool error is the deliberate stale-observation refusal. Authentication used the
normal account flow; no synthetic auth, copied cookies, personal-browser
attachment, business SEND or provider launch was used. The test's temporary
search value and theme were restored. The live browser used the accepted cache
runtime; the later durable copy is byte/inventory-qualified and its actual
catalogue was independently read back. It does not claim a second live-browser run.

The [runbook](../../MASTERMIND_OS_APP_CONTROL.md#installed-c3--m2-launcher) contains
the exact durable launcher, MCP initialization sequence and same-context login
requirements. This is an attended process through an authorized host connection,
not a new listener, browser pool or daemon.

### Boundary findings and repairs

The recurring problem was a mixture of missing app-level control, capability
discovery gaps and mismatched installed state. A generic refusal did not identify
which layer had failed.

- The original unselected C3 backend already ran locally on `m2studio`.
  `studio_select_host("m2")` requested an unconfigured optional remote route and
  returned `NOT_APPLIED`; it was not a denial of the working original local path.
- The managed GitHub connection's administrative-read restriction and its missing
  exact-head merge input were real capability limits. The explicitly authorized
  native principal qualified controls and used one exact-head protected queue
  request. No self-approval, administrative bypass or direct merge was used.
- An older component update retained a `START_DISPATCHED` marker. Its original
  sealed reconciliation owner closed it as `ABORTED_UNCHANGED` with both installed
  before-images restored and b4 still serving. The retained stop/start history was
  preserved; this result does not imply that no historical dispatch occurred.
- The old edge publisher understood the old asset profile. The coherent accepted
  publisher, planner and asset closure handled the new profile on both hosts.
  Validation was not weakened and no public MCP family was added.
- The first edge prepare detected another application's concurrent HTTP/HTTPS
  route update before writing intent. A fresh original-owner stage preserved that
  change and completed publication; the refused first stage was not replayed.

### Exact limits and future diagnostics

The dormant C3 F0 Workbench channel was not migrated. Its optional 23-tool
installed surface remains **NOT_INSTALLED**; the current fleet CLI provides no
supported profile/workspace migration action. Direct standard MCP live acceptance
does not depend on that channel.

During live acceptance, `/workspace/programs/current` and
`/workspace/work/current` returned HTTP 503. The UI displayed
`SOURCE_UNAVAILABLE`; its generic producer copy is not proof that no producer or
mission exists. The backend cause remains unqualified by that browser trace.
Diagnosis belongs to the existing Workspace/CeoIngress/CCR owners. This evidence
does not justify a new mission, grant, producer, guessed restart or arming change.
Provider workflow execution was not exercised.

Additional original-owner diagnostics confirmed the original Control, released
gateway, worker and public tunnel processes were running. The exact installed b4
Control status client (Git blob `8c820364adc9568fe9606d1983cf620bc6b5801e`) returned
`ok: true`, `AWAITING_CANARY`, PID 96546, zero active dispatches and zero dispatch
errors. Its [installed dispatch source](https://github.com/mastermindx-market-intelligence/Mastermind/blob/b4a5a8925c6c1412dac67ba296cf65ee81c4d4c8/control_plane/executive_service.py)
permits ordinary Workspace reads in that state without worker arming. A stopped
Control service is ruled out; arming is not a justified repair. The remaining
proof is the original App-peer CeoIngress/Workspace response classification or an
authorized CCR-owner diagnostic of publication, freshness and refresh errors.
The generic status client does not expose those facts. An unrelated inventory
encountered `PermissionError` at `application-tunnel/current`; that exact path was
not retried or accessed through another identity.

The original paid Fabric reservation and historical F2/issuer uncertainty retain
their existing fences. The personal Chrome AppleScript JavaScript denial was not
retried through CDP, copied cookies or another protocol. No Agent OS wave, Linear
projection or Slack dialogue was marked complete by this source contribution.

**Do not redo:** the accepted implementation, completed component update, final
edge publication and successful live app-control journey. Future development
sessions use the installed launcher and current observations. Any separate
backend repair starts with the original owner and concrete current evidence.

---

## Historical source-qualification snapshot

Everything below this heading records the earlier source and boundary observations.
The current section above supersedes their pending-release/installed-consumer
status and the assumption that Workbench activation is required for the direct
path. Original manifests, fixture evidence, denials and uncertain effects retain
their historical meaning; they are not rewritten as production proof.

Operation: `mastermind-os-agent-control-20261108-c3`  
Carrier: `sol/web-mastermind-os-agent-control-20261108-c3`  
Protected procedure/source pin: `5c3d3885234358aefb97ecdbc59be0864df14f8b`  
Plan admission commit: `f39f6299218fc76be34569d5a89465229de10306`  
Capability state: **BUILT_NOT_PROVEN** for installed web consumers.  
Parent mission complete: **false**.

This report qualifies the source represented by the accompanying
`source-manifest.json`, not an installed production revision. The containing
Git commit and its Ready PR are the immutable source delivery references. Native
GitHub checks, release identities and runtime receipts remain their own owners.

## Capability delta

Before this contribution, the normal React app had no general semantic control
catalogue. A signed-out live `/os/` observation returned no page-native WebMCP
tools. Web sessions without a suitable computer-use surface could not use that
path to inspect or operate the application.

The source now provides inspect, navigate, act and check through the normal app
root. The optional standard MCP profile composes these tools with the original
Workbench browser context and resource lifecycle. It preserves existing
authentication, UI handlers, action preparation, durable claims and reconciliation.
No second browser pool, listener, identity store, operation ledger, retry loop or
publication service was introduced.

The source runbook is [MASTERMIND_OS_APP_CONTROL.md](../../MASTERMIND_OS_APP_CONTROL.md).
The parent task tree is [the execution plan](../../plans/2026-11-08-mastermind-os-agent-control.md).
The source plan is `PLAN_NOT_ORG_LINKED`; no existing Agent OS wave or Linear state
was marked complete and no Slack handoff was sent.

## Verified source behavior

| Evidence | Observed result | Limit |
| --- | --- | --- |
| React control, auth-generation and display-preference suites | 44 tests passed | Real handlers with test owners; no production credentials |
| Profile, browser port and signed-contract suites, including explicit Chromium stdio case | 32 tests passed | Actual Node child, rendered App, signed preparation and durable action artifacts; synthetic identity/process binding |
| Fixed adapter tests | Seven passed | Transport/origin/schema/refusal contracts |
| Existing vault adapter tests | Five passed | Original vault closure unchanged; joint app/vault profile remains refused |
| Workflow source contracts | 12 passed | Validates CI source constraints; not a hosted macOS build |
| Typecheck and production Vite build | Passed | Existing chunk-size/import warnings only |
| Separate browser-fixture Vite build | Passed | Fixture has no production Vite entry |
| Existing production static-asset manifest validation | Passed | Built asset layout, not publication |
| Compiled App via standard MCP SDK | 61 calls passed; no page errors | Synthetic signed-in auth/owners, isolated Chromium 153 |
| WebMCP registration | `WEBMCP`, `document.modelContext` present | Registration in local Chromium; no installed remote WebMCP client proof |
| Exact SDK catalogue extraction | 18 native/profile tools, digest matched | Extraction does not start a browser or publish a connection |

An earlier affected Python run also passed 54 cases and three subtests, with its
optional Chromium case skipped; the later explicit Chromium run above executes
that case. These are overlapping suites and must not be summed as unique tests.

The 61-call proof covers primary and advanced navigation (Projects, Inbox,
Conversations, Knowledge, Search and Fleet & Capacity), Executive access without
Workspace Content, project selection, React-controlled search, theme and locale
changes without losing input state, stale and reused observations, mobile layout,
ambiguous app pages and immediate sign-out privacy. Desktop and 390-pixel mobile
screenshots were visually inspected. The machine trace is
[`browser-proof.json`](browser-proof.json).

The real Workbench stdio case prepares and executes original actions, edits the
rendered React search field, rejects a disabled control, and then deliberately
loses the reply **after** an actual route dispatch. Original run and reconcile
calls retain `EFFECT_UNKNOWN` without another dispatch. A subsequent route check
can pass while that original receipt correctly remains uncertain.

Additional cases cover recovery after app-profile opt-out: completed/unknown
original receipts remain readable, but an unrun prepared app action cannot gain
fresh dispatch authority under the baseline profile. Authentication withdrawal,
field privacy, changed targets, closed inputs and bounded observations are covered
by the frontend and adapter suites.

## Catalogue and dependency identities

- Native/profile catalogue: 18 tools; digest
  `8ec730ca88103dc180f431d6b3c85c4f3fdd4f8dac9e2688ab0350933a29fd0c`.
- Workbench outer surface: 23 tools; observed digest
  `352c48fe37caef8a84a71004e0460644f5d0b63023bb5b84450640a79fc5e6b9`.
  Worker grants must validate the actual outer surface under the existing owner.
- Original baseline digest remains
  `ea956fcbb62baedc543f0e8bf299b0a59bdaa30f7c5808faf1ca32a5e9094730`.
- Original parent package-lock SHA-256 remains
  `61fb32ec2c4e3baca8dc9de390b018cfa271908fa4e5501cbdff96ef09f2b5d5`.
- Runtime pins: `@playwright/mcp` 0.0.79; Playwright and playwright-core
  1.63.0-alpha-2026-08-05; nested `@modelcontextprotocol/sdk` 1.32.2.
- Local qualification: Node 24.22.1, Python 3.12, isolated Chromium 153. Hosted
  workflow keeps its existing Node 22.23.3 and macOS/Rust pins.

The hosted app workflow now invokes the actual stdio/profile tests with an explicit
Chromium executable, alongside the in-memory MCP/browser journey. Proof JSON,
screenshots and JUnit XML are retained under its exact CI SHA. This report does
not claim those hosted checks have finished before their canonical run results.

## Proven boundaries and unresolved proof

### Local Unix transport

The full attempted seven-file Python run had 14 socket-dependent failures:
11 direct `PermissionError: [Errno 1] Operation not permitted` socket failures and
three owned-relay startup failures in that socket-restricted environment. No
sandbox escalation or alternate carrier was used to repeat the denied socket
effect. The independent stdio/TCP source proof passed, but does not qualify Unix
peer checks, original process-group custody or resource startup. Ordinary hosted
relay/resource tests and installed proof must supply that evidence.

### Protected release

At the recorded pin, protected master advertises required `test` and `CodeQL`
checks. Active ruleset `22852988` requires the native SQUASH merge queue, with no
bypass actors; the current connection cannot bypass it. The full branch-protection
read returned HTTP 403 `FORBIDDEN` / `Resource not accessible by integration`.
That denial does not establish whether further approval requirements are present
or waived. The exposed auto-merge action has no exact-head lease argument, while
`docs/DELIVERY_WORKFLOW.md` requires one for queue arming. No direct/admin merge,
self-approval, alternate protected reader or head-unleased arming was attempted.

### Installed owner and real web consumer

The original Studio C3 `select_host(hostRef="m2")` returned
`FLEET_ROUTE_PREFLIGHT_REFUSED`, `error_code: INVALID_ARGUMENT`,
`effect_state: NOT_APPLIED`. Original gateway readback showed `selectedHostRef:
null` (gateway 0.1.10). No host command, alternate-host fallback, deployment,
service restart or installed app publication occurred. An exposed fleet listing
is not execution admission. An Executive state read also returned an MCP internal
error, without any modifying effect.

The browser plugin could not attach without its originating extension context.
A direct cloud-browser baseline inspection reached the live signed-out app and
found no page-native tools; no sign-in or account credential access was attempted.
Local source registration and the standard MCP fixture do not prove installed
OAuth, Workbench service/tunnel entry, current web-connection discovery, actual
provider mutations or product acceptance.

## Exact continuation and do-not-redo

The assigned session retains responsibility. Complete the Ready PR's native
checks and consume actual reviews/holds. Queue arming requires restored access to
the missing enforcement facts and a permitted head-leased normal merge action.
After protected release, the existing runtime owner must admit the original
deployment path and install the app and optional Workbench source closure. Then
use the intended authenticated web connection to discover the published tools,
inspect an authorized original browser resource, operate a permitted real control,
verify its UI/owner receipt, and prove auth withdrawal and original-action recovery.

Do not redo the accepted source architecture or reinstall baseline/vault
dependencies under a new owner. Do not switch carrier to replay the refused host
selection, infer release from a PR/CI result, copy credentials, manufacture a
review requirement, or erase uncertain original effects. The remaining blockers
are specific access/release/runtime controls; they are not a requirement for the
historical author or another chat to take ownership.

## Boundary recovery and CI repair

The original repository CI run [42489928865](https://github.com/mastermindx-market-intelligence/Mastermind/actions/runs/42489928865) finished with shard 4 and aggregate `test` failed; other shards passed. The app workflow, native macOS build, CodeQL and credential-engine checks passed. This supersedes the earlier pending-check observation in the PR body.

The failure was `test_d8_template_topology_and_protected_defaults`: the contextual topology scanner reported `['443']` from `validate_app_control_origin`. Ports are intentionally guarded. Replacing the protocol literals with the standard library's `HTTP_PORT` and `HTTPS_PORT` preserves URL validation and leaves the guard untouched. Explicit HTTPS and HTTP-loopback default ports remain rejected.

After the repair, 39 profile/browser-port/browser-resource cases passed, including actual Chromium plus the stdio child. Fifteen selected D8 topology/scope cases passed in an isolated Git validation snapshot containing the complete candidate (local validation tree `261fc5d2e88224a87844685537c35c7049e4d00d`). This is focused source evidence, not the future hosted aggregate result; counts overlap earlier suites.

Current governing procedures were requalified at protected master `1d0579c0540f5281e52faf069dd7dba2f480c7c6`: all 15 applicable law files are byte-identical to the original implementation pin. The affected browser resource contract's base blob is unchanged too. No ancestry-only update or foreign source change is included.

The Studio failure's previous classification was too broad. Exact installed-family source (`gateway.mjs` Git blob `f87ac012339e82fe46bce5ddc70d1d04183d1b6e`, `fleet-routing.mjs` blob `63c47d73ae7b73a61c95cee1803c549ecd6df9c8`) wraps local catalogue, connection, remote catalogue and schema errors in `FLEET_ROUTE_PREFLIGHT_REFUSED`, then discards the inner cause. The same original C3/M2 preflight returned `NOT_APPLIED` again and safe readback remained unbound. A bounded original-local-owner diagnostic subsequently read the installed module hashes, matching both pinned blobs, and the configured route names. It proves `FLEET_ROUTE_HOST_NOT_CONFIGURED`: `m2` is absent; the only remote refs are `mini3` and `mini4`. The existing unbound local C3 backend already runs on `m2studio`; its configuration read and native diagnostic commands succeed. The exact installed preflight consumed the local catalogue (26 tools) and refused the unknown ref before remote initialization (zero remote tools). This resolves the local-owner access boundary without any fleet fallback or host-binding change. New MCP sessions create new route-binding state even when sharing a backend, so account-wide state must not be substituted for explicit original resource identity.

A bounded original-owner diagnostic through Fabric was admitted by economic policy but stopped at `SUPPORT_POLICY_STALE_ACTIVE_REFUSED` before worker START proof. Original run `mastermind-os-agent-control-20261108-c3-route-audit-1` and controller `27206` remain the only diagnostic operation; its effects/reservation are not replayed or cleared. Status reports terminal failure, root verification false and execution absence not proven. This is a support-publication consistency boundary, not evidence that the Chairman must approve the diagnostic again.

The managed GitHub connection's documented exclusion of administration access explains the separate branch-protection 403. That exact denied read is not retried or reconstructed through another account. GitHub's native expected-head mechanism exists, but the exposed auto-merge wrapper omits it. An adapter fix can restore a head fence; it does not manufacture missing enforcement qualification. No release, restart, profile activation or installed acceptance is claimed.

### Corrected local-owner operation

Fleet inventory host names are not configured route refs. `studio_select_host` is optional one-way routing for the named remote refs, not a mandatory readiness step for the existing local backend. After any local backend dispatch, that frontend session is intentionally ineligible for later fleet selection. The original local path is therefore used deliberately for owner diagnosis, with physical host identity observed before commands. No alternate account, gateway, host or credential was used. The previous broad refusal interpretation was a diagnostic error.

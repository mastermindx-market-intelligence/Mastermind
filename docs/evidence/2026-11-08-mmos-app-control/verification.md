# Mastermind OS app control — source qualification

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

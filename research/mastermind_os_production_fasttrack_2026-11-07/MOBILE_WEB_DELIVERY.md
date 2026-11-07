# Hermes-backed mobile web delivery

Operation: `hermes-mobile-web-20261107`.
Parent: `WS:EXECUTIVE-ECOSYSTEM-COMPLETION`; supplement to this directory's README and HANDOFFS, not a new project/task/runtime registry.
Assignment: Chairman-requested secure mobile access to the existing M2 Hermes Meta-CEO, Secretary and other profiles, preserving Mac streaming, formatting, history and tools.
Procedure: Mastermind protected `4fb0d3825b5b4b4439e65e7382660112b7c2ef8c`, Skillpack 1.0.1/bootstrap 1. A subsequent relevant-path comparison changed only BOOTSTRAP_KERNEL; its stronger continuation emphasis is compatible.
Source carrier: isolated GitHub branch `sol/hermes-mobile-web-20261107`. Installed-host effects use the original authorized Studio Direct local M2 carrier. No live writer or started job has been transferred.

## Current outcome

**Built, configured and component-tested; not activated or accepted as a working mobile product.** The existing gateway must restart to load Web Access. Its latest native guard reports a live chat plus scheduled work; no interruption has been authorized or performed. The private HTTPS endpoint therefore returns 502 rather than a working chat app.

Completion still means: the Chairman reaches the M2 gateway from a phone, signs in through the supported existing identity, selects Meta-CEO or Secretary, receives a real formatted streaming reply, reopens the original conversation and reconnects without duplicate sends. Desktop continuity and other services must remain intact. A phone-sized browser is not physical iPhone acceptance.

## Reuse and integration decision

Adopt the installed MIT-licensed Hermes browser build of its actual Desktop renderer and its existing native gateway. Keep Hermes's profiles, sessions, memory, queues, Markdown/tool rendering and OAuth. No new chat framework, DeepSeek-to-Hermes translator, identity store, scheduler or agent runtime was introduced.

The existing Mastermind OS shell and DeepSeek PR #2177 retain their separate integration work. Their active source files were untouched. This usable-first vertical slice does not claim completion of the wider mobile command center, desktop OS or project-execution programme.

Private HTTPS uses the existing Tailscale service on a dedicated port, preserving its root and Studio MCP routes. Hermes stays on loopback; its native `webapp.public_url` engages sign-in. No public Funnel, router forwarding, anonymous proxy, transferred provider key or disabled TLS/origin/auth check. The phone needs the authorized tailnet connection and the supported Nous login.

## Confirmed installed effects

### Native browser renderer

`hermes webapp --build-only` completed with exit 0, original process 805. Donor: Hermes v0.23.0 at `2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19`. Output is the installed donor's `apps/desktop/dist-webapp`.

- Source hash: `1faeb5281c0b84c0d235e64dcebf8709a497e48dcb573181b46b2e959f27b0ca`.
- Output hash: `a9fd70c59c30de37a4fb9fbc7077dc28f35df2d5c530df79cb45cf6197e25d16`.
- Upstream receipt: Darwin/arm64, production mode, Node 26.12.1.
- Upstream's isolated browser-build workspace avoided pruning native Desktop dependencies. Existing mobile viewport/keyboard code and Apple touch icon are included. No generated bundle was hand-edited.

### Sign-in and configuration

Native Web Access registration succeeded using the existing signed-in Nous account, original process 18955/exit 0. Its dedicated client is separate from the dashboard client; the gateway retains the owner-only registration in `webapp/sign-in-registration.json`. No tokens or client/account details are published here.

The gateway home now has Web Access enabled with the dedicated HTTPS public URL. Effective host remains 127.0.0.1 and port 9120. A preservation check found **zero changes to preexisting non-webapp settings**. Staff roles and model/provider choices were not changed.

### Private HTTPS transport

`tailscale serve --bg --https=8443 http://127.0.0.1:9120` succeeded, original process 28220. Readback proved every original Serve route unchanged; public Funnel remains off. The actual private URL is retained in the operation's private host receipts and the Chairman's chat, not exposed as a public service.

An HTTPS request with the correct hostname/SNI and an explicit mapping to the observed Tailscale IP returned curl exit 0, TLS verification 0 and **HTTP 502**. This proves the transport and certificate, not app availability. Default hostname resolution failed on the M2 because its observed Tailscale `CorpDNS` preference is false. That existing global preference was preserved. Phone DNS/reachability remains unverified.

## Validation: 189 passing checks, bounded proof

| Campaign | Scope | Result | Original process |
|---|---|---|---|
| Installed renderer UI | Browser viewport, Web Access API/UI, served-profile selection/launch, gateway boot | 42 passed / 7 files, exit 0 | 19875 |
| Installed renderer streaming | Delta flushing, completion boundaries, duplicate completion, execution-authority events, gateway message stream, reload/resume targeting | 47 passed / 6 files, exit 0 | 27493 |
| Isolated native access tests A | Public URL/auth engagement, OAuth callbacks/trusted hosts, shared Desktop/Webapp owner, socket profile isolation | 40 passed / 3 files, exit 0 | 57678 |
| Isolated native access tests B | Web Access behavior, originless remote WebSocket tickets, page content-security policy | 60 passed / 3 files, exit 0 | 62403 |

These are component and fixture checks, **not a real authenticated phone/provider conversation**. No live inference canary, browser login, production WebSocket denial check or physical-device acceptance is claimed. Renderer tests emitted React act/localStorage warnings without failed assertions. The upstream browser end-to-end cases inspected explicitly skip non-Linux; they were not misreported as executed Mac proof.

### Test-environment failure and resolved qualification

Retain the initial failures as historical evidence. Early runner attempts failed on missing dependencies/bootstrap. The first supported `scripts/run_tests.sh` campaign, original process 34068, ended exit 1 with **89 passed, 3 failed and 8 errors**. The causal stack showed bootstrap probing `root.parent/manifest.json` under the real Hermes home, correctly refused by the test I/O guard. A subprocess fixture also re-bootstrapped an incomplete isolated environment and lacked httpx. This was not accepted production-security evidence.

Qualification then used a disposable source snapshot **outside the live Hermes home**, from the exact donor Git revision plus byte-verified copies of its six existing tracked modifications. No credentials, runtime state or production database were copied. The official per-file test runner and pinned test environment ran all six selected files in two disjoint batches: 40 + 60 passing checks. The production-home guard and all assertions remained intact; no production or test source was patched to force a pass. The archive emitted a nonfatal no-Git-metadata message; its retained input manifest, exact base and delta hashes establish source identity.

### Preservation and evidence

The donor's existing tracked modifications were byte-identical through the native build; combined patch SHA-256 `3cae368c9ca1369184e9ff0e7afae06a57c43cc12f5483ebfec68f93a77177af`. Other writers' fallback/session edits and untracked tests were not reset, stashed or changed.

Private receipts: `~/.local/state/mastermind/hermes-mobile-web-20261107/` on the M2. Relevant names: `build.log`, `mobile-ui-tests.log`, `stream-tests.log`, `auth-boundary-canonical-tests.log`, `auth-isolated-source-tests.log`, `auth-isolated-source-remaining-tests.log`, their exit files, `qualification-source.json`, `configuration-preservation.json`, `oauth-result.json`, `tailscale-serve-after.json`, `https-preactivation-check.json`, `activation-state.json`. Configuration backups are sensitive and must never be published.

## Exact activation boundary

The original background delegation `deleg_4ec60078` watching PR #2155 ceased to appear in the later native guard. The earlier question about interrupting that watcher is therefore **not permission to interrupt the subsequently observed live chat or scheduled work**.

Latest activation preflight, process 65710/exit 0:
- Existing gateway PID 48443, same recorded start identity.
- Web Access enabled in saved config but live gateway state still `off`.
- Native guard reports three live units: one GLM chat turn, one cron job and one managed run.
- `restart_started: false`, `held_for_live_work: true`, validated checks 189.

No restart, force/interrupt, kill, cancellation, replacement gateway, duplicate monitoring job or automatic activation watcher was issued. `restart-result.json` remains absent. All this operation's test/build processes have terminal receipts. No modifying effect is unknown.

**Required next action:** obtain a safe idle opportunity, or exact Chairman permission for a brief gateway interruption after a fresh census of the work it would affect. The default is preservation. Use the native supported restart path only when that condition is satisfied; the general implementation request and the earlier watcher question do not silently widen interruption scope.

Then verify, in order:
1. The same configured gateway serves port 9120 and private HTTPS no longer returns 502.
2. Unauthenticated HTTP/API/WebSocket denial, intended OAuth callback, certificate/origin/cookie behavior.
3. Real signed-in browser selection of Meta-CEO and Secretary; one uniquely marked bounded stream with actual Markdown/code/tool rendering; original history reload, stop/reconnect and native Desktop continuity. Reconcile uncertain sends rather than repeat them.
4. Phone connectivity, narrow layout and keyboard behavior. Preserve a physical-device gap until actually tested.

Do not redo the build, OAuth registration or HTTPS publication. Do not restart another implementation or re-run unchanged passing campaigns merely for activity. Continue on the existing branch and original Studio local carrier.

## Delivery nodes and recovery

| Node | State |
|---|---|
| M1: native renderer adoption | Installed build completed; exact hashes above |
| M2: sign-in and activation | OAuth/configuration complete; activation held by current live work |
| M3: private HTTPS | Route installed and TLS verified; upstream unavailable pending activation |
| M4: streaming/mobile acceptance | 189 component/fixture checks pass; live browser and phone proof still owed |
| M5: demonstrated gap repair | Test isolation corrected through a disposable source snapshot; no speculative UI fork |
| M6: continuity and wider OS | Source evidence retained here; broader incumbent OS work untouched |

Finalization boundary: `EXACT_HUMAN_GATE` for an immediate interrupting restart; safe idle activation remains a permitted alternative in a later attended continuation. `MISSION_COMPLETE: false`. Capability: `BUILT_NOT_PROVEN` / partial installed composition, not production-ready.

Execution reason: `UNIQUE_APPROVED_ACCESS` and `LOWER_TOTAL_OVERHEAD` for native deterministic integration. No Fabric child, delegated lifecycle or post-turn autonomous executor is claimed. Agent OS linkage remains `PLAN_NOT_ORG_LINKED`; this is source evidence, not runtime admission or an adopted organizational completion record.

## Rollback and maintenance

Remove only this operation's route with `tailscale serve --https=8443 off`; never reset all Serve configuration. Disable only `webapp.enabled` through Hermes configuration and safely restart when permitted. Do not restore an old whole config over concurrent changes. Revoke only the dedicated Web Access client through its existing Nous owner interface when that rollback is authorized; preserve dashboard/provider identities.

Use Hermes's own update/build path for renderer maintenance. No hand-edited generated bundle, parallel app daemon or new provider key is required.

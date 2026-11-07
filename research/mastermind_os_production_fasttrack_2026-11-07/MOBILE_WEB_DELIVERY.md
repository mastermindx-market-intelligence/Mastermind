# Hermes-backed mobile web delivery

Operation: `hermes-mobile-web-20261107`.
Parent: `WS:EXECUTIVE-ECOSYSTEM-COMPLETION`; supplement to this directory's README and HANDOFFS, not a new task/runtime registry.
Assignment: current Chairman request to implement secure mobile access to the existing M2 Hermes Meta-CEO, Secretary and other profiles, preserving desktop streaming, history and tool rendering.
Procedure: Mastermind protected `4fb0d3825b5b4b4439e65e7382660112b7c2ef8c`, Skillpack 1.0.1/bootstrap 1. A subsequent relevant-path comparison changed only BOOTSTRAP_KERNEL; continuation emphasis remains compatible.
Source carrier: isolated GitHub branch `sol/hermes-mobile-web-20261107`. Host effects use the original authorized Studio Direct local M2 carrier. No live writer or started job has been transferred.

## Outcome and completion ruler

The Chairman can reach the existing M2 gateway from a phone, authenticate with a supported existing identity, select Meta-CEO or Secretary, receive a real streaming reply with desktop-equivalent formatting, reopen that conversation and reconnect without duplicate sends. Native desktop operation and other exposed services remain intact. A phone-sized browser is not physical iPhone acceptance.

**Current status: installed and configured components, NOT an activated or accepted mobile product.** The running gateway predates Web Access configuration and cannot safely restart while an unrelated background delegation is active. No live mobile/provider reply, authenticated browser journey, phone test or production acceptance is claimed.

## Reuse decision

Use the installed MIT-licensed Hermes browser build of its actual Desktop renderer and native gateway. Preserve its profiles, sessions, memory, queues, Markdown/tool rendering and sign-in. No new chat framework, DeepSeek-to-Hermes protocol translator, scheduler, identity store or agent runtime.

The existing Mastermind OS shell and DeepSeek PR #2177 retain their separate integration work. Their active files were not edited. This vertical slice does not claim completion of the broader command center or all desktop/mobile OS work.

Private HTTPS uses the existing Tailscale service on a dedicated port, preserving its original root and Studio MCP routes. Hermes stays bound to loopback; `webapp.public_url` requires its native sign-in gate. No public Funnel, router forwarding, anonymous proxy or disabled origin/TLS/auth check. The phone must be connected to the same authorized tailnet; the web login uses Nous.

## Confirmed installed effects

1. **Native browser renderer built.** `hermes webapp --build-only` completed with exit 0, original process 805. Installed source is `2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19` (v0.23.0). Output: the installed donor's `apps/desktop/dist-webapp`.
   - Build source hash: `1faeb5281c0b84c0d235e64dcebf8709a497e48dcb573181b46b2e959f27b0ca`.
   - Build output hash: `a9fd70c59c30de37a4fb9fbc7077dc28f35df2d5c530df79cb45cf6197e25d16`.
   - Upstream build receipt reports Darwin/arm64, production mode and Node 26.12.1. The upstream isolated workspace avoided pruning native Desktop dependencies.
2. **Nous Web Access registration succeeded.** Native `webapp_access.register` created the dedicated Web Access client for the private HTTPS callback. Registration remains in the gateway home's owner-only `webapp/sign-in-registration.json`; no tokens/client details are copied here. The existing dashboard client and provider configurations were not replaced.
3. **Web Access configuration saved.** Enabled, default loopback host and port 9120, dedicated HTTPS URL on port 8443. Native status still says the gateway started before the Webapp was enabled and requires a restart. Configuration preservation checked all preexisting non-webapp values: no changes.
4. **Private HTTPS route installed.** Existing Tailscale Serve now forwards port 8443 to `http://127.0.0.1:9120`. Exact original route values were read back unchanged. Public Funnel remains off. The endpoint currently returns **502**, correctly reflecting the unactivated upstream; this is not app availability.
5. **TLS transport checked without weakening certificate validation.** A request to the correct hostname with an explicit mapping to the observed Tailscale IP completed with curl exit 0, TLS verification 0 and HTTP 502. Default hostname resolution failed on the M2; its Tailscale `CorpDNS` preference is false. That global DNS preference was preserved. Phone DNS/reachability remains unverified, not inferred from this local transport check.

The exact private operating URL and non-secret raw receipts are in the operation's owner-only host evidence directory: `~/.local/state/mastermind/hermes-mobile-web-20261107/`. Configuration backups there are sensitive and must never be published.

## Verification completed and limits

**42 UI tests passed across 7 files**, exit 0, original process 19875:
- Browser viewport/keyboard accommodation.
- Web Access API/UI behavior.
- Webapp-served profile selection and profile launch.
- Gateway boot/profile routing.

**47 streaming and continuation tests passed across 6 files**, original process 27493:
- Delta flushing and completion boundaries.
- Duplicate-completion handling.
- Execution-authority event behavior.
- Gateway message-stream processing and reload/resume stream targeting.

These are upstream component tests, not a live mobile conversation. React act/localStorage warnings were present; passing assertions are not visual acceptance.

The Python authentication/boundary campaign is **not clean and not accepted**. Initial runner attempts failed before useful execution because of test-environment dependencies/bootstrap. The supported `scripts/run_tests.sh` campaign (original process 34068, six exact files, two workers) subsequently reported production-home isolation-guard failures in owner-identity/profile-scope fixtures. The guard was not disabled or bypassed. Preserve its actual terminal summary when available; do not describe these checks as passing or as proof of an exploitable production defect.

Upstream browser end-to-end cases inspected here explicitly require Linux and skip on macOS. They were not presented as executed Mac/iPhone proof.

The installed donor's preexisting tracked modifications remained byte-identical through the build: patch SHA-256 `3cae368c9ca1369184e9ff0e7afae06a57c43cc12f5483ebfec68f93a77177af`. They belong to other work and were not reset, stashed or edited. Existing staff providers/roles were not changed. No live inference canary has been sent by this operation.

## Activation hold and exact next action

The last native guard read narrowed five active units to one: background delegation `deleg_4ec60078` in gateway PID 48443, watching Mastermind PR #2155 until terminal state or its own deadline. The PR was still open when checked. It is not this operation's worker. No cancel, interrupt, kill, replacement watcher or forced restart was issued.

The Chairman has been asked specifically whether that watcher may be interrupted. No reply/authorization is assumed. Do not broaden permission to interrupt another session that starts later.

Next action:
1. Reconcile original test process 34068 and its terminal evidence. Reuse completed build/OAuth/HTTPS effects; do not recreate them.
2. At the next actual activation opportunity, read native activity and gateway identity. If clear, use Hermes's supported safe restart path. If the Chairman explicitly permits interruption of the named watcher, verify no additional unrelated active units before applying that exact scope. Never add `--interrupt` by inference.
3. Verify that the same configured gateway is serving port 9120 and HTTPS no longer returns 502. Check unauthorized API/WebSocket denial and the intended OAuth callback with certificate verification intact.
4. Complete a real signed-in browser journey: select Meta-CEO and Secretary, bounded uniquely marked stream, Markdown/code/tool rendering, original history reload, stop/reconnect and desktop continuity. Do not duplicate uncertain sends.
5. Verify an actual phone connection and keyboard/layout. Do not treat current unit tests as that proof.

No new background activation watcher/runner was created. Tailscale Serve is an existing transport service, not a promise that this Web session will continue implementation after its response.

## Delivery nodes

| Node | Evidence/state |
|---|---|
| M1: adopt/build native renderer | Completed installed build; exact source/output hashes above |
| M2: sign-in and gateway activation | OAuth/configuration saved; activation held by live delegation |
| M3: private HTTPS | Route installed and TLS verified; upstream intentionally unavailable pending activation |
| M4: mobile/streaming acceptance | 89 component assertions passed; live/authenticated/mobile journey still owed |
| M5: repair demonstrated gaps | No speculative UI fork; Python test-isolation issues recorded separately |
| M6: operating evidence and recovery | This source record plus private host receipts; broader OS integration remains scoped to its incumbent work |

Execution reason: UNIQUE_APPROVED_ACCESS and LOWER_TOTAL_OVERHEAD for deterministic native installation/integration. No Fabric worker, delegated lifecycle or post-turn autonomous executor is claimed. Agent OS linkage remains PLAN_NOT_ORG_LINKED; this is recoverable source evidence, not runtime admission.

## Rollback and ongoing maintenance

Remove only this operation's private route with `tailscale serve --https=8443 off`; never reset all Serve configuration. Disable only `webapp.enabled` through Hermes configuration and use a safe restart when permitted. Do not restore an entire old config over concurrent changes. Revoke the dedicated Web Access client through the existing Nous owner interface only when that rollback is authorized; leave dashboard/provider identities intact.

Hermes's own update/build mechanism remains the renderer maintenance path. No hand-edited generated bundle, parallel app daemon or extra provider key is required.

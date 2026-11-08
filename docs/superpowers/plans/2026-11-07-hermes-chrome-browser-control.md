# Hermes control of installed Mastermind browsers

Operation: `hermes-chrome-browser-control-20261107-c3`
Repository: mastermindx-market-intelligence/Mastermind
Branch: `sol/web-hermes-chrome-browser-control-20261107-c3`
Procedure and source base: `a4c012e06c6411f89ce8199b8815fbb20917dda8`
Assignment: Chairman requests upgrading the installed Mastermind Chrome/Orbita extension so Hermes harness sessions can actively use those browsers, learning from Codex and Claude browser capabilities.
Organizational linkage: PLAN_NOT_ORG_LINKED; this source plan does not create a workstream, runtime job, admission grant or lifecycle owner.

## Outcome and acceptance

Hermes can discover the existing enrolled browser instances, deliberately select an exact browser and tab, inspect a page, navigate, interact, and verify the resulting page through the existing Mastermind extension/native transport. Concurrent browser profiles stay separate. Unsupported, disconnected, stale, denied and uncertain actions remain distinguishable.

Completion requires source tests, required CI/protected release, exact installed version evidence, and a real Hermes-to-extension round trip on Chrome plus Orbita. A source implementation or synthetic test alone is not live acceptance.

## Current evidence and constraints

- Protected source extension: integrations/chairman_surfaces/web_sol_extension, MV3 version 0.2.0, exact ChatGPT hosts, nativeMessaging/alarms, pinned native-host instance handshake.
- Existing native transport/client/deployment owners must be extended; no second browser daemon, queue, credential store, permission system or browser registry.
- Existing Hermes MCP/runtime composition must remain the consumer; no separate harness.
- PR #836 owns an independent ChatGPT cognition/continuation candidate on overlapping legacy seams. Preserve that branch and its holds; this operation uses its own additive source on protected master and does not release #836.
- PR #940 concerns a separate Workbench-owned Playwright browser; do not replace it or attach to ambient CDP.
- Browser package identity and instance selection must survive multi-profile use. Do not choose the most recent/active browser implicitly.
- New browser permissions require real Chrome consent where Chrome enforces it. No silent default-profile, private-profile, credential export or unrestricted CDP/eval surface.
- Page content is untrusted data. Existing principal/grant/effect owners retain authority. No action replay after uncertain dispatch.
- Existing saved site authentication can be reused in the selected browser; secrets must not be copied into logs or model results.

## Task tree

### P1 — Freeze architecture and capability contract (in_progress)

Inspect the native-host message routing, extension bundle verifier, Hermes MCP seam, installed release/config and active overlaps. Compare primary OpenAI, Anthropic and Chrome API documentation. Freeze exact-browser/target/document identities, permission scope, action result/effect semantics and the minimum integrated consumer.

### P2 — Implement extension and native transport (proposed; depends P1)

Extend the existing package with bounded tab listing, page snapshots and element references, navigation, click/fill/key/scroll, screenshot and diagnostics as supported by the reviewed permission model. Retain the legacy ChatGPT path and negotiated compatibility. Reuse the native connection and reject cross-instance/replayed/stale actions.

### P3 — Integrate Hermes tool consumption (proposed; depends P1)

Expose a bounded schema through the existing Hermes/MCP owner with server-derived session identity and current browser grants. Preserve configuration qualification, tool allowlists and runtime custody. Tools return useful page/action results and explicit degraded states. Supply an in-scope usage skill/reference through the existing skill loader.

### P4 — Verify, publish, release and install (proposed; depends P2, P3)

Test actual JS/Python modules for normal actions, multi-profile isolation, stale elements, navigation races, permission denial, restart, duplicate nonce, post-dispatch loss, bounded outputs and legacy protocol compatibility. Self-review integrated diff; satisfy actual repository gates. Install through the existing deployment owner at the exact protected release and obtain Chrome/Orbita plus Hermes proof. Preserve rollback through that owner.

## Execution ownership

Root retains cross-system architecture, integration, source custody and acceptance. A native advisory child provides principal architecture judgment only. Independently executable routine work should use the admitted paid Fabric; no native labor substitution. Direct work, when needed, records its actual exception and remains on this source carrier.

WHY NOT FABLE: the bounded architecture review does not require an additional scarce principal; the active assigned principal retains the cross-system decision.
No Slack message, background runner or watcher is commissioned by this plan.

## Recovery frontier

Workspace: /Volumes/Mastermind/agent-workspaces/web/hermes-chrome-browser-control-20261107-c3
Known applied effect: managed workspace acquisition at the protected base.
Uncertain effects: none at initial save.
Next action: finish native-host/client/Hermes seam inspection, then freeze and implement the smallest complete browser-control path.

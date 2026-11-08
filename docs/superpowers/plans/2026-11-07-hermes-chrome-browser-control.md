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

### P1 — Freeze architecture and capability contract (source_complete)

Inspect the native-host message routing, extension bundle verifier, Hermes MCP seam, installed release/config and active overlaps. Compare primary OpenAI, Anthropic and Chrome API documentation. Freeze exact-browser/target/document identities, permission scope, action result/effect semantics and the minimum integrated consumer.

### P2 — Implement extension and native transport (source_complete)

Extend the existing package with bounded tab listing, page snapshots and element references, navigation, click/fill/key/scroll, screenshot and diagnostics as supported by the reviewed permission model. Retain the legacy ChatGPT path and negotiated compatibility. Reuse the native connection and reject cross-instance/replayed/stale actions.

### P3 — Integrate Hermes tool consumption (source_qualified)

Expose a bounded schema through the existing Hermes/MCP owner with server-derived session identity and current browser grants. Preserve configuration qualification, tool allowlists and runtime custody. Tools return useful page/action results and explicit degraded states. Supply an in-scope usage skill/reference through the existing skill loader.

### P4 — Verify, publish, release and install (in_progress)

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


## Implementation milestone (2026-11-07)

State: MORE_WORK_EXISTS. Source is implemented and locally qualified; protected CI/release, coordinated installation and actual installed Chrome/Orbita journeys remain owed.

- Added closed browser request/receipt family to the existing extension/native socket/client. Package 0.3.0 and capability digest c3cf6a8186d967b499e74432acc23f10a9a765138fd50e2c8e0cfa54e9a38309 qualify the added command surface; old ChatGPT actions retain their separate schemas.
- Added native Hermes PluginContext consumer, immutable runtime descriptor/source closure, actual native session/profile binding, existing-inventory projection, multimodal screenshot presentation and uncertainty-preserving one-shot subprocess invocation.
- Chrome debugger must be required at install/update (official permissions API); optional tabs/scripting and website grants still gate every browser action. Removed the proposed unsupported optional-debugger toggle. No transport permission-grant operation, browser daemon, alternate account, raw CDP/eval, lifecycle or registry was added.
- Repaired advisory findings within incumbent owners: current connection/expiry checks, document/snapshot invalidation, focus preparation and lost-focus uncertainty, bounded construction, page scrolling and non-sensitive form-state readback. Native advisory child browser_architecture performed judgment only and is terminal. Its earlier-snapshot advice is not final-head or formal GitHub approval.
- Paid Fabric run hermes-browser-page-core-20261107-c3 was REQUEST_REFUSED_BEFORE_LAUNCH / UNCLASSIFIED_PRELAUNCH_REFUSAL, controller exit 75, no result or worker START. One bounded same-run diagnostic completed. No replay. Direct source work continued under NO_ELIGIBLE_PRE_EFFECT_WORKER.
- M2 observed qualification: 739 tests passed, zero failures/skips (Web Sol regression plus native browser plugin tests; /tmp/hermes-browser-qualified-20261107.xml). This includes the existing native census vertical. The final added status package-version field separately passed the focused Node controller contract.
- Actual isolated Google Chrome DOM fixture passed sensitive exclusions, form readback, consumed refs, session separation, target mutation, offscreen refusal, document scrolling, focus proof, same-URL reload and snapshot bounds (tests/browser_page_playwright.cjs). This is fixture proof, not installed-profile acceptance.
- Existing M2 surface inventory contains four multilogin-managed adapter coordinates. Three incumbent socket entries were observed; no upgraded connectivity claim. Compatibility installation wrappers currently refer to an older managed source workspace. Preserve incumbent effect/writer custody before any update. Any installed browser absent from existing validated coordinates requires enrollment-owner reconciliation, not fabricated ChatGPT bindings.
- Actual installed Hermes PluginManager/PluginContext registry probe passed in a temporary profile: mmx_browser registered, four existing coordinates discovered, a missing native session was refused, and unload removed the tool. Zero browser actions were dispatched and no production plugin was installed (tests/hermes_browser_registry_probe.py).
- Actual isolated Chrome settings test passed enable/pause, one-site and explicit all-site grants, removal, invalid-scheme refusal, and required-debugger behavior. Desktop 1100px and mobile 390px screenshots were inspected; no horizontal overflow or script errors (tests/browser_settings_playwright.cjs). The fixture permission boundary is synthetic; real Chrome consent remains a rollout gate.
- Source candidate b5efecb8bee583dae04c971833370ac7d41a63c7 is published in PR #2269: https://github.com/mastermindx-market-intelligence/Mastermind/pull/2269. The source implementation, actual registry probe and settings qualification are complete; this evidence/test delta follows on the same branch.
- Read current protected release rules: master requires the test check, strict status checks and the native squash merge queue. Required approving review count is zero and CODEOWNERS review is not required. Current PR had no auto-merge request, no queue entry, no reviews and no labels when observed. No self-approval, direct merge, admin bypass, installation, enablement or production browser action has run.
- Initial guessed venv Python path was absent (no execution). The actual installed launcher/bootstrap path was then used. A stdin bootstrap probe exited before registry execution; a source-file probe succeeded. These are bounded diagnostic outcomes, not permission denials or uncertain browser effects.

Next: publish this evidence/test delta, mark the qualified PR Ready, consume exact-head hosted CI and protected queue controls, and reconcile the incumbent per-profile installation source/writer/effect state before any update. Actual accepted-release installation, Chrome/Orbita consent and Hermes-to-installed-browser journeys remain owed. No new worker or background observer is running.

# Browser bus implementation checkpoint — 2026-10-22

Status: **source candidate; MISSION_COMPLETE=false; no installed upgrade or live estate bus claimed.**

This continues operation `browser-fabric-attached-tabs-20261005-c2-001` and draft PR #1259. It updates the older documentation-only description: the branch already contains Browser facade/owner code, and this checkpoint adds executable startup, image delivery, extension composition, and connection recovery fixes. Existing Executive admission, Workbench resource/effect ownership, Capacity placement, and profile consent remain authoritative.

## Implemented in this checkpoint

### Browser MCP service

- HTTPS OAuth resource identifiers now pass the canonical Business MCP URL validator and remain exact, including path and case. The signed session, tab, and action references accept those resources without widening other opaque identity fields. Cross-resource replay still fails.
- Workbench service configuration `mastermind.workbench_action_service.v3` has explicit Browser policy and separate audit-directory fields. Normal `run_service` startup now composes the Browser JWT/JWKS validator and its own policy-specific durable audit sink. Versions 1 and 2 retain their existing behavior.
- Browser protected-resource metadata uses a distinct internal route, `/browser-fabric-metadata`. The ingress projection separately identifies the public Browser metadata route and its private upstream, avoiding a collision with Workbench metadata. Public routing has not been deployed.
- Screenshots are emitted as native MCP `ImageContent`, with bounded PNG/JPEG decoding and metadata in the JSON envelope. They no longer consume the 64 KB text budget as base64. The `browser-mcp` dependency profile pins MCP, JWT, and Pillow.
- The DevTools catalog now uses the incumbent canonical schema digest, including input/output schemas and annotations. This repairs attestation consistency; it does not wire the DevTools backend into the resource owner.

### Browser Link and the installed extension composition path

- Added a complete MV3 manifest and packaged sharing popup: connection state, current-tab sharing, shared tabs, and revocation.
- Factored the worker into a scoped component so it can coexist with the classic Web Sol worker. Browser Link responds only to its exact popup route and does not take over Web Sol's toolbar badge.
- Native handshake has a five-second deadline. Both remote and locally initiated disconnects clear sharing and detach owned debugger targets. The reconnect alarm is checked on every worker startup. No command or result is replayed.
- A sharing request captures its connection before asynchronous tab lookup and refuses if that connection changes. A replacement connection never inherits the old UI request's consent.
- A pinned esbuild 0.28.2 build emits a self-contained classic IIFE and four fixed supporting assets. The build receipt includes input and output digests. It performs no installation.
- `render_browser_link_extension_bundle` extends the existing Web Sol deployment owner. It first runs the strict census renderer, transforms only validated immutable artifact bytes, preserves the issued extension key, base worker, native artifacts, instance configuration and session handshake, adds the sharing UI link within the existing popup, and includes every changed/new file in the existing digest, preimage, apply, readback, and rollback machinery.
- The existing census-only renderer still rejects permission widening. The combined renderer explicitly adds only debugger, tabs, and storage permissions to the existing nativeMessaging/alarms permissions; ChatGPT content scripts and host permissions stay as in the base package.

The installed profiles observed during this task contain Web Sol 0.2.0 on CHATGPT1/2 and 0.4.0 on CHATGPT3. A renderer loaded from 0.2 source refuses 0.4 input. The 0.4 worker includes continuation logic; it must be preserved through source integration before any CHATGPT3 installation. No installed profile files were edited.

## Verification

Focused Python campaign before protected-source integration: **601 passed**. After merging protected source `c9cbee5569ba50e30e28715d930809061a169517`, the expanded campaign completed with **849 passed, 2 skipped**. It includes all `test_mastermind_browser_*.py`, `test_workbench_browser_*.py`, `test_worker_browser_*.py`, Browser service/action tests, Workbench service tests, the combined Web Sol renderer, existing deployment/applier/CLI tests, and CI test-runner tests. The merge preserves the protected worker fresh-resource claim checks and relay process-ownership fencing.

Node campaign: **63 passed**. It includes scoped controller/actuator tests, native handshake/disconnect/reconnect behavior, no consent restoration, both ready/unready reconnect races, and execution of the actual classic bundle in a populated Web Sol-style global scope. The build succeeded using the committed package lock.

The combined deployment test installs a base package in a temporary directory, applies the upgrade using the incumbent transactional applier, verifies exact readback, rolls back, and verifies the original files. It also round-trips the combined bundle through the existing CLI decoder.

The service test uses real RSA JWT validation, the canonical JWKS cache, durable policy-specific audit files, the normal service startup function, and the actual MCP ASGI application. Its Browser fleet is empty by design; this is protocol/startup evidence, not connected-browser evidence.

Independent read-only review found and drove fixes for the metadata route collision, native-disconnect cleanup, sharing-generation race, and mutable-source reread. The final review cleared the bounded source slice after those corrections. Static review and synthetic Chrome tests do not establish installed acceptance.

CI now installs the pinned Link build dependency, builds the bundle, executes the Node tests, and installs `.[dev,browser-mcp]` for Python qualification. Required hosted checks, source integration, and release review remain controlling.

## Owner recovery and CI integration follow-up

Explicit resource reconciliation now acquires the same nonblocking ActionArtifactStore writer as startup, then classifies the original claim under that lock. A deterministic paused-finalization test proves that reconciliation cannot finalize an in-flight start and induce cleanup of an already-applied relay. A recreated facade can repopulate its volatile projection after successful explicit reconciliation under the same retained owner. The optional fresh observation runs inside the original admitted executor callback, so a second admission cannot hide a durable APPLIED receipt. This neither adopts a dead owner's relay nor extends a resource lifetime; automatic durable enumeration remains unfinished.

The merged head's hosted Python shards failed during dependency installation because the new Browser extra pinned JWT 2.13.0 while protected source requires 2.14.0. Browser now matches the protected pin. A parsed-extras regression prevents this disagreement. The combined `.[dev,browser-mcp]` dependency dry-run resolves successfully. Both platform locks already contained the three exact Browser dependencies; a bounded comparison proved unchanged base/dev requirements and unchanged versions, extras, and hashes for all 73 locked packages. Their headers record a closure-equivalence qualification against the new project digest, rather than claiming a new platform compile. Future lock regeneration includes both extras. The recovery/inventory group passed 60 tests; a separate temporary environment with actual PyJWT 2.14.0, MCP 1.28.1, and Pillow 12.3.0 passed 625 auth, startup, recovery, and RWE tests. The shared environment was not modified.

## Remaining implementation and real-path work

1. Recover and review the original custom native bridge package. The attached `mastermind-browser-candidate` archive and its source manifest were not found in the accessible bounded search. Preserved partial-upload evidence contains no native implementation.
2. Resolve the historical native-framing transfer hold through its recorded permission/capability path before replaying that upload. The masterplan records a refusal before dispatch, but the raw reason and call ID were not found. Do not describe this secondary record as a proven current global denial.
3. Compose the actual shared-tab native channel with the existing Browser resource and ActionArtifactStore owners. The current high-level Workbench projection uses stock Playwright current-page semantics and intentionally refuses ambiguous multi-tab targeting. Removing that guard would be unsafe; it needs exact tab/document generation at the final actuator.
4. Reconstruct fleet observations from existing durable owner records and verified live resources after restart. The current deployment's active projection is volatile. A separate browser registry or scheduler is not an acceptable fix.
5. Wire authenticated host routes and qualify one-host then two-host operation. The host router currently accepts an injected resolver; source interfaces alone are not an enrolled estate transport.
6. Add admitted new-tab/new-window lifecycle operations through the same owner, including reconciliation and cleanup. Those actions are absent from the current seven-tool facade and Link command set.
7. Integrate with the installed Web Sol release, satisfy required checks/review, perform approved native-host/extension installation, configure public/private ingress and client enrollment, and prove real ChatGPT/Claude/Grok/OpenClaw/Fabric use. The earlier isolated Chromium canary was blocked by administrator policy; no policy change or alternate-browser bypass was attempted.
8. Prove concurrent distinct-tab use, stale-reference rejection, restart recovery, revocation, uncertain-effect reconciliation, and rollback with actual admitted browsers. Same OAuth account/client is not, by itself, unique conversation identity.

The paid Fabric submission in this task was rejected by automatic approval review before dispatch, citing external source disclosure and paid worker effects. No worker run started. The source repairs were completed directly with independent read-only review; no alternate dispatch route was used.

## Reproduce the source checks

Use the repository's supported Python environment with `.[dev,browser-mcp]`. Build the Link assets with:

```bash
npm ci --prefix integrations/mastermind_browser_link --ignore-scripts --no-audit --no-fund
npm run build --prefix integrations/mastermind_browser_link
node --test tests/browser_link/*.test.mjs
```

Generated `dist/` and `node_modules/` are ignored. Build receipts prove byte integrity, not protected-source admission, enrollment, or human consent. No credentials, native enrollment files, runtime logs, generated assets, or installed browser data belong in this source commit.

## Primary implementation references

- Chrome service-worker lifecycle: https://developer.chrome.com/docs/extensions/develop/concepts/service-workers/lifecycle
- Chrome alarm persistence: https://developer.chrome.com/docs/extensions/reference/api/alarms
- Chrome native messaging: https://developer.chrome.com/docs/extensions/develop/concepts/native-messaging
- esbuild browser/IIFE API: https://esbuild.github.io/api/
- Incumbent source owners: `web_sol_deployment.py`, `web_sol_deployment_apply.py`, `workbench_action_mcp/service.py`, `workbench_action_mcp/action_artifacts.py`, and `workbench_browser_mcp/deployment.py`.

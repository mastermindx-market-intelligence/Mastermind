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

The installed profiles observed during this task contain Web Sol 0.2.0 on CHATGPT1/2 and 0.4.0 on CHATGPT3. A separate exact-profile overlay now preserves both installed releases, including the 0.4 continuation code, without substituting the current source tree for the installed base. It qualifies frozen historical asset hashes, the release capability digest, instance configuration, and the actual extension directory. It updates only the manifest and existing popup link, adds five fixed Link assets, and routes all effects through the existing transactional deployment owner. The overlay's original hashes and exact root remain bound through preparation, private-state recovery, applied verification, and rollback. Unknown or changed profiles refuse before mutation.

The overlay campaign passed **118 tests**, including authentic 0.2/0.4 fixtures, temporary apply/readback/rollback, recovered PREPARED and APPLIED state, modified original files, forged bundles with recomputed digests, path/root changes, and definite pre-effect rollback refusals. Independent read-only review cleared the bounded source after the recovered-root and rollback-classification corrections. This is source and transaction-path acceptance, not installed/native-bus acceptance. No installed profile files were edited.

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

## Native owner composition checkpoint

The independently implemented native channel now runs through the normal Workbench v3 service factory, canonical isolated relay bootstrap, existing resource launch barrier, private Unix socket, Chrome native-messaging bridge, exact-profile enrollment, and public Browser facade. The native bridge reuses the incumbent Web Sol framing/private-socket primitives. It has no registry, scheduling, durable action store, browser-launch, or retry authority. Content-addressed profile grants bind enrollment, backend digest, Chrome PID/start identity, existing owner/operation/generation, host/boot, and expiry into the already signed prepared-start profile reference.

The native listener validates peer UID/PID and the enrolled Chrome parent process before accepting a bounded, versioned handshake. A fixed full profile instance identity routes each installed profile to its own native-host name. Correlated inventory carries exact generation, tab, local consent, and document revision. Commands are closed and bounded; arbitrary CDP calls, scripts, selectors, native endpoints, and caller-chosen writer identities are not exposed. Connection status is advisory and contains no tab consent. Fleet listing reads that private status, while a selected tab requires a fresh correlated inventory. A stalled unrelated native profile cannot block selection of a healthy profile.

The legacy Playwright path retains its ambiguity guard. An explicitly attested Link backend projects multiple shared tabs with distinct signed references and exact local consent. Navigation loading/completion retires document revisions; pending navigation cannot grant consent. Unknown effects remain quarantined for writes and appear as read-only inventory capabilities. The final click/type actuator rechecks target sensitivity.

The relay permits bounded concurrency across different tabs. ActionArtifactStore serializes only claim/finalization, releasing its writer during browser I/O; only the invocation that creates the original claim may dispatch. Duplicate and absent-but-potentially-pending actions remain uncertain until matching durable evidence exists. Qualified receipts survive a later EOF or contradictory frame. Partial writes retire the channel without replay. Per-tab writer interlocks and uncertainty fences remain in the native session and extension.

### Verification of the current composed source

The expanded current-contract campaign passed **723 tests, with 2 skipped**, covering Browser/Workbench/worker contracts, source owners, service startup, native transport, inventory, and concurrent action claims. The extension build and Node campaign passed **67 tests**. These are separate campaign results; they must not be summed with overlapping earlier campaigns.

The new service test uses the normal v3 configuration and service factory, launches the actual relay under its canonical `-I -S` bootstrap and the actual native bridge process, obtains public session/tab references, and waits until two commands for different tabs reach the native peer before releasing either reply. Both actions complete and a duplicate returns its durable receipt without another mutation. A new pre-claim regression reconciles while the writer is deliberately held and proves that absence cannot be reported as terminal NOT_APPLIED. Native transport tests also cover competing peers, process identity changes, same-extension/different-profile routing, partial frames, timeouts, result conflicts, and secure enrollment parsing.

Independent read-only review cleared the bounded source after corrections to selected-profile discovery, observation expiry, unresolved-effect capabilities, pre-claim reconciliation, and thread-start cleanup. **The native peer in these tests is synthetic and the test process stands in for the Chrome parent. Actual Chrome process lineage, installed extension acceptance, durable restart recovery, and live estate availability remain unproved. No installed profile files were changed.**

## Native v2 creation checkpoint

The public prepared-action grammar and exact Link backend now support `create_tab` and `create_window` with one HTTP(S) URL. Native hello/ready/observe/inventory/command/result use v2 and the hello requires integer protocol version 2. Every v2 inventory row has a strict `allow_create` boolean. The public catalog generation is v2; both catalog digests change, so old grants/references cannot silently acquire the new capabilities. Unchanged signed envelope and enrollment schemas retain their versions. The legacy Workbench backend retains its five-action ceiling, and ordinary Link tabs retain six actions.

The sharing popup has an optional creation-permission checkbox. Creation is a writer operation anchored to that exact shared tab. Tabs open in its explicit window without activation; windows use fixed normal, non-incognito and unfocused settings. Children receive fresh consent only after exact ID/window, completed loading, no pending URL and requested committed-origin checks. Children do not inherit creation permission. An independent human share is preserved.

The actuator records exact returned creation identity before waiting for child readiness. Known creation remains APPLIED when a child redirects, closes, is replaced, times out, or loses sharing authority. Missing creation evidence remains EFFECT_UNKNOWN and fences the anchor. The readiness waiter invalidates stale asynchronous readbacks on events and grants consent synchronously while its listeners remain installed. It never selects an active, newest or URL-matching tab. A ten-second overall sharing budget begins before the creation API call. Shared-slot reservations and a 64-creation per-connection budget bound concurrent work; dispatched but unshared creations still consume the budget.

The rebuilt extension passes **84 Node tests**, including the actual controller/Chrome actuator composition, concurrent anchors, capacity reservation, known creation with absent window tab data, pending/redirected children, revocation/re-sharing/disconnect, replacement/removal races, exact duplicate receipts, retained-guard refusal and the slow-create deadline. The expanded Python campaign passed 731 tests with 2 skipped and exposed one stale six-action enum assertion; after updating that assertion to the intentional eight-action grammar, its complete 35-test reference suite passed. The full service test now prepares creation, receives its original receipt, obtains a freshly signed child reference from native inventory, and acts on that child through the actual relay/bridge. The Chrome peer remains synthetic.

## Durable recovery and configured activation checkpoint

Browser resource claims now have a closed v2 descriptor containing the original signed start, immutable profile grant, and exact service-owner process identity. Profile grants v2 bind the existing artifact-store device/inode as well as the original scope, host/boot, Chrome PID/start, enrollment and expiry. Descriptor-free v1 claims retain their original 4 KiB grammar. Canonical bounded enumeration refuses overflow, orphan evidence, malformed identities and disappearing process/output evidence. Fleet inspection uses the same claim/result qualification.

A qualified APPLIED start records the native socket's bind-time device/inode, ctime, owner and parent directory identity. Recovery first joins every nonlegacy page-action claim to its original resource and checks uncertainty. Only positive proof that the original owner is absent permits exact relay retirement and matching endpoint cleanup. Replaced sockets or parents, unresolved effects, unknown backends and live previous owners hold the affected activation. Original receipts are never rewritten, and previous generations cannot claim a later generation's endpoint.

Normal service lifespan now activates configured profiles through the existing admitted executor and revisits the same deterministic original attempts. This repopulates the volatile fleet projection without creating a second registry, scheduler or action owner. A physically entered operation that outlives its caller timeout defers later profile launches until the incumbent executor completes it. Missing profiles remain individually unavailable. Lease expiry/revocation stops observation normally. Qualified status observation runs outside the shared artifact writer; long retirement/launch sections defer while the original action owner has an active dispatch.

Native uncertainty now survives connection replacement within the original Chrome process lifetime. Pending, damaged or UNKNOWN durable page-action evidence prevents later fresh mutations on that resource, while concurrent claims still owned by the active invocation set can complete. A stalled profile's status request cannot prevent another profile from durably recording its qualified action result.

The final broad recovery campaign passed **1,033 tests** after the maintenance-contention and lease-expiry corrections; its preceding targeted campaign passed 21 tests. It includes actual service-owner A → B → C process restarts with forced relay termination and orphan sockets, byte-unchanged original receipts, recovery holds for uncertain/unmapped actions, normal public fleet activation, isolated missing profiles, actual executor timeout/deferred activation, and a deliberately stalled profile while another profile completes and records two actions. Independent read-only concurrency and evidence reviews cleared this bounded source. These campaign counts overlap and are not additive. Chrome is still represented by the synthetic native peer/test parent in these tests; installed Chrome and live estate acceptance remain open.

## Native installer checkpoint

A closed Browser Link native bundle now uses the incumbent Web Sol deployment transaction for the qualified profile's native-host directory. Its three artifacts are enrollment v2, an isolated fixed-bootstrap launcher, and the instance-scoped native registration manifest. The manifest is published last and removed first during rollback. The bundle reconstructs exact artifact bytes and Chrome extension origin from typed fields; supplied hashes cannot authorize another launcher, manifest, path, instance or artifact.

Fresh installation requires every target to be absent; a complete byte-identical installation can be verified as unchanged. Mixed fresh plans and updates refuse, leaving interrupted work to the original saved transaction. The native artifact and preimage order remain bound through PREPARED/APPLIED recovery. Preimages must also match the original CREATE/UNCHANGED plan, including exact bytes, modes and owners. This prevents a rehashed rollback capsule from restoring an unqualified registration. Legacy Web Sol and installed-overlay ordering remain unchanged.

The final native/legacy transaction campaign passed **179 tests**. Tests execute the quoted launcher in a temporary release, check exact origin forwarding and Python isolation, prove publication/reverse-removal order, preserve an existing Web Sol registration inode, recover persisted phases, reject bundles and recovery capsules with recomputed digests, and classify interrupted absent/complete/mixed effects without replay. Independent read-only review cleared the source after the prepared-preimage correction. No installed native files were changed; release/interpreter and actual browser registration-root qualification still precede installation. Filesystem rollback does not terminate a process that Chrome has already launched; runtime retirement remains with the existing resource owner.

## Remaining implementation and real-path work

1. Qualify the implemented durable recovery and automatic configured-profile activation against the installed estate. Production service supervision and credential/lease renewal must remain with their existing owners; the source recovery path does not renew its own authority.
2. Wire authenticated host routes and qualify one-host then two-host operation. The host router currently accepts an injected resolver; source interfaces alone are not an enrolled estate transport. The installed Studio Direct fleet transport is a Desktop Commander router with a different source release and fixed tool ceilings; it is not yet a Browser fleet route.
3. Qualify the new creation path against actual Chrome and preserve original creation receipts through durable recovery.
4. Integrate with the installed Web Sol release, satisfy required checks/review, perform approved native-host/extension installation, configure public/private ingress and client enrollment, and prove real ChatGPT/Claude/Grok/OpenClaw/Fabric use. The earlier isolated Chromium canary was blocked by administrator policy; no policy change or alternate-browser bypass was attempted.
5. Prove concurrent distinct-tab use, stale-reference rejection, restart recovery, revocation, uncertain-effect reconciliation, and rollback with actual admitted browsers. Same OAuth account/client is not, by itself, unique conversation identity.

The historical `mastermind-browser-candidate` archive was not found in the bounded search. The recorded historical framing-upload refusal has no recovered raw reason/call ID; that held transfer has not been replayed or reconstructed through another carrier. It is separate from this current-contract native implementation in source custody, which the implementation request and current execution instructions authorize.

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

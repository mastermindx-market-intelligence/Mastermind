# Mastermind Browser Fabric — architecture, execution and continuation

Date: 2026-10-05. Operation: `browser-fabric-attached-tabs-20261005-c2-001`.
Branch: `sol/web-browser-fabric-attached-tabs-20261005-c2-001`.
Protected source/procedure pin: `7eac3ec252475600147ec9a376b8ca16403ac4c5`; Skillpack 1.0.1/bootstrap 1.

**MISSION_COMPLETE=false. Documentation publication is separate from candidate-source publication, installation and production acceptance.**

## 1. Decision and intended outcome

Build one governed Browser capability with two client lanes and two actuator modes. Expose it as a separate **Mastermind Browser** MCP plugin, rather than adding more generic tools to Studio Direct. Preserve the existing Web Sol provider-session extension; add the small, replaceable **Mastermind Browser Link** attachment extension only for explicitly shared existing tabs. Retain existing Playwright isolated/persistent worker browsers for managed automation.

A Web CEO and an admitted native worker should be able to observe the same authorized tab, while other independent tasks use other eligible browsers across the fleet. Mutations are serialized and fenced per tab, with stronger profile-level admission for shared-account/storage effects. All callers use the same original resource and effect owner, regardless of ingress.

The Browser service is not a new scheduler, Job registry, lease issuer, credential store, retry database, provider-account allocator or company lifecycle. Executive OS, Capacity, RuntimeBinding, Workbench and the existing Browser owner retain those responsibilities.

## 2. Existing work to reuse, not rebuild

| Owner/carrier | Observed source identity | Disposition |
|---|---|---|
| Protected Worker Browser B1 / merged #153 | Existing `control_plane/worker_browser_b1.py` and runtime | Preserve. Source protection is not installed browser-fleet proof. |
| Web Sol extension | `integrations/chairman_surfaces/web_sol_extension/` | Preserve exact provider/seat/session semantics. Do not broaden it to all-tab control. |
| Browser resource / #940 -> #993 -> #1051 | #1051 `aafc8c6485481b49b5cfb631f7fb7f59a55e373c`, observed open Draft | Existing signed references, private stdio, grants, admission, recovery and source/release holds remain. |
| Exact launch join / #1057 | `5137c8760a7536728889d8b49b413518ed681c80`, observed open Draft | Already proposes the OperatorMaterializationReceipt join. Reuse/reconcile it; do not invent a WorkerRecoveryBinding substitute. |
| Combined browser integration / #1071 | `458f2c6ce69049956f9b98ed2507633f0ec5f499`, observed open Draft | Retain integration ownership; actual supervisor wiring and real worker/browser acceptance are not proven by its tests. |
| Universal Studio / #1217 | `2cfa4455544de595d6f9f19f9e1d0a7f96b3355a`, observed open Draft | Reuse existing host/tunnel/service/auth and provider-projection patterns. Do not overwrite its writer. |
| Installed Executive observation | `5b244a2bbe4c2a94ec25a887eb4a0d8fafe1ea2f`, readonly at 2026-10-05T08:15:14Z | Not equal to protected source. No dispatch was performed. |

The #1071 resource contract pins Playwright MCP 0.0.79 and explicitly excludes shared-context, arbitrary CDP endpoint and extension attachment from its isolated/persistent modes. Add a distinct reviewed attached-tab contract; do not relax those modes or silently enable a disabled capability.

Eight Studio account routes were observed ready. That is tunnel readiness, not proof of browser installation, profile permission, physical identity or available browser capacity. A namespace census inspected 458 registered workspaces and found no exact collision for the new candidate namespaces; this does not transfer any incumbent shared-source custody.

## 3. Alternatives and tradeoffs

**Recommended hybrid:** managed Playwright browsers plus a narrow attached-tab extension, both behind the existing Browser owner. This preserves controlled worker isolation while permitting deliberate reuse of interactive logged-in tabs.

**Stock Playwright extension:** a strong comparison candidate because it already attaches to existing Chrome/Edge tabs. Before adopting it behind the same owner, prove tab addressing, concurrent-client behavior, caller isolation and uncertain-effect recovery. Profile selection or logged-in-state reuse alone is not Mastermind fleet admission. Prefer adoption over maintaining custom interaction code when the stock adapter passes the same tests.

**Raw DevTools MCP/CDP:** useful behind a managed adapter, but do not expose unrestricted browser-wide debugging endpoints or arbitrary methods to workers/Web CEOs. Chrome profile/debugging restrictions and enterprise policies remain applicable.

**Desktop mouse/keyboard automation:** not the fleet foundation; foreground focus is shared and tab identity is brittle. Use approved application APIs when they are more precise than browser UI automation.

The strongest objection to a custom extension is the ongoing cost of iframe, editor, selector and browser-version compatibility. Keep the actuator replaceable. This first candidate is not a new general automation framework and does not claim feature parity with Claude/ChatGPT browser products.

## 4. Topology and dual lanes

Web CEO -> separate Mastermind Browser plugin -> existing Secure MCP Tunnel infrastructure -> Browser-only authenticated ingress -> existing Browser owner.

Native CEO/worker -> supervisor-private stdio, or existing authenticated internal HTTPS/mTLS -> the same Browser facade and owner.

Existing Capacity/RuntimeBinding -> admitted host/browser/profile -> owned Playwright browser OR Browser Link Native Messaging host -> explicitly shared tab.

The internal lane must not depend on OpenAI's Web tunnel. Both lanes share business references and durable effect fencing, not credentials or caller identity. A transient map of native connections and pending replies is transport state, not a second fleet or action registry.

### Multiple plugins on one tunnel

Reuse the installed tunnel binary, service management and credential custody. Do not assume one existing tunnel ID automatically yields distinct per-plugin catalogs. Official documentation describes forwarding to a configured MCP server and workspace association; per-plugin server multiplexing needs an actual trusted-route canary.

Prefer a separate Browser listener/process/catalog and separately registered tunnel binding when the existing binding is server-specific. A shared tunnel can be retained only after trusted client routing and catalog separation are proven. A different display name or caller-supplied header is not trusted routing.

Separate plugins isolate catalogs, consent and release failures. Sharing one tunnel still shares that tunnel's outage domain. Separation cannot bypass a provider safety refusal or an administrator policy. Do not stop production Studio/Paper services to test Browser independence.

## 5. Identity, persistence and same-tab concurrency

The existing owner binds host, OS/process principal, browser installation, profile, browser boot, connector generation, tab and document generation. An integer Chrome tab ID is neither global nor durable. Models receive opaque owner-issued browser/tab/action references; no model argument selects an actor, token, credential, CDP endpoint, socket or profile path.

Each caller needs its own grant. Shared read does not mean shared authority. Readers can overlap readers; a native mutation holds the tab's write interlock. Profile-wide operations such as login/logout and shared-storage changes need stronger owner admission or stay unavailable. A tab mutex cannot isolate cookies across tabs.

Element references bind consent generation, document revision and expiration. Navigation, revocation, reconnect and observed DOM changes invalidate them. Admission and target checks run immediately before native effects. An expired lease never permits a second writer to duplicate an in-flight action.

The original effect owner persists a pre-send fence. A timeout, cancellation or disconnect after dispatch remains EFFECT_UNKNOWN until that owner reconciles it. No new request ID, alternate lane or different browser authorizes a replay. Late acknowledgements are delivered back to the original owner; cleanup cannot downgrade an acknowledgement already being saved.

A native command returning successfully is not evidence that a website saved, sent a message, paid, or began a provider turn. Observe the separate business result.

Persistent profiles stay on their own enrolled hosts. Do not copy cookies or concurrently mount the same user-data directory. New tasks may be placed on compatible already-enrolled profiles. Exact existing conversations and uncertain effects remain sticky; transparent cross-host migration is not promised.

The candidate reconnects transport but clears local sharing. Production share restoration remains B5: reconcile exact authorized profile/boot/document/consent bindings through the existing owner; otherwise require fresh Share. Never restore from a saved tab integer or instance_ref alone.

## 6. Extension and MCP boundary

The extension has visible Share current tab, Stop sharing and connection status. It uses an exact-origin Native Messaging host, not a public debugging port. Auth0, fleet and OpenAI credentials never enter page scripts or extension storage.

Initial operations are bounded main-frame accessibility snapshot, bounded viewport JPEG, simple element click, replacing permitted INPUT/TEXTAREA fields, bounded scroll and same-origin navigation. Click/type use fixed DOM functions, not trusted pointer/keyboard input. Contenteditable composers, complex editors, complete iframe/shadow DOM coverage, uploads/downloads and general trusted-input parity remain unqualified. Sensitive fields are refused, including a recheck after focus handlers. Same-origin control is not a network-egress sandbox.

One seven-tool catalog serves both MCP lanes:
`browser_fleet`, `browser_tabs`, `browser_snapshot`, `browser_screenshot`, `prepare_browser_action`, `run_browser_action`, `reconcile_browser_action`.

The facade refuses construction without existing-owner methods and a trusted per-call caller resolver. Unknown fields are refused. No default actor, allow-all factory or token passthrough exists. Tool annotations do not replace enforcement; Playwright's catalog digest cannot attest this new catalog.

`resource_channel.py` accepts already-owned streams and exact enrollment. It correlates bounded concurrent requests, rejects ID reuse, and preserves late receipts. It creates no listener, durable authority, scheduler or retry loop. The trusted owner must provide admission and durable pre-send/result handling; fixture callbacks are not production grants.

## 7. Authentication and Auth0 last

Implement fail-closed security before external linking. Reuse `business_mcp_auth` issuer/audience/resource/client/scope/expiry verification, tenant/workspace association and audit. A Studio token does not automatically authorize Browser. Keep Chrome's website authentication separate from MCP authentication.

Native workers reuse their admitted private stdio or existing host-authenticated channel and Runtime grant; no human login per worker. Do not accept a worker's own claim about its Job as authority.

Only after source, integration and installation gates pass: enroll the exact Browser Auth0 API/audience, scopes, OAuth client/callback, PKCE/issuer metadata and workspace association; then have the user perform the necessary sign-in/consent. Auth0 is the last external linking ceremony, not the only remaining engineering gate.

## 8. Full implementation program

| Package | Deliverable and exit condition |
|---|---|
| B0 | Adopt this composition design, reconcile incumbent heads/custody, independently review the new attached mode. |
| B1 | Complete extension/controller/actuator/UI; prove scoped targets, concurrency, stale refs, consent and real browser behavior. Synthetic tests alone do not close it. |
| B2 | Native frame/host/channel over existing enrollment; exact origin, permissions, peer identity, bounded frames and late effects. Qualify macOS/Linux/Windows separately. |
| B3 | Same Browser facade for actual MCP HTTP/private stdio; real protocol, caller isolation, immutable schema and resource-auth tests. |
| B4 | Reconcile #1057/#1051/#1071 and wire the real supervisor/Workbench Browser owner. Preserve Job/Attempt/Worker/fence/profile/process/workspace/network/artifact binding and original-parent result consumption. |
| B5 | Extend existing Capacity with admitted browser/profile observations; one-host then two-host enrollment; persistent reconnect, profile exclusivity, identity affinity, memory/disk pressure and pre-effect failover. |
| B6 | Browser-only listener/plugin/tunnel binding and provider projections. Prove catalog isolation and internal-lane availability during canary Web-ingress outage, without stopping existing production services. |
| B7 | Auth0 and final account/workspace linking; real Web CEO and native worker use the same enrolled system. |
| B8 | Independent review, exact-source required CI, installed version/schema proof, real same-tab/two-host/fault/revocation tests and rollback. Only then PROVEN_LIVE. |

Capacity must first filter identity, policy, admitted tool generation, host/profile health, resource budgets and affinity; only then rank eligible choices. A heartbeat or free CPU is not admission. Preserve human tabs and persistent profile data. An unknown effect fences its original resource rather than moving the same work to another host.

## 9. Candidate built and actual evidence

The local candidate contains 28 source/test/dependency files under `integrations/mastermind_browser_link` and `tests/browser_link`, plus architecture, plan, acceptance and evidence documents. Its source manifest SHA-256 is:
`1b5361c3e5021e78c87576ea8c496991a38987f066474d4b63f74dadc851e9e6`.

Latest local campaign: **54 Node tests and 61 Python tests pass; four Python checks skip.** The 17 resource-channel tests are INCLUDED in 61. Do not add earlier checkpoint counts. Python compilation and JavaScript syntax checks exit 0.

Covered: closed native/model schemas; sharing/re-sharing; stale consent/document/fence; multi-read/single-mutation interlock; exact hello identity; private POSIX socket checks; actual synthetic native-host process; distinct callers sharing one real native stream; out-of-order replies; refusal before send; no action replay; late acknowledgement after timeout/cancel; receipt persistence failure; shutdown during receipt save; sensitive-field mutation after page focus.

These use synthetic Chrome/authority fixtures or controlled local streams. They do not prove real OAuth, installed Chrome, tunnels, production worker admission or fleet placement.

## 10. Explicit failures and holds

- The actual isolated Chromium attempt logged `Loading of unpacked extensions is disabled by the administrator` and timed out awaiting its service worker. No policy was changed or alternate browser used to evade that restriction. Default test runs skip that opt-in canary; the original failed log remains in the package.
- Three actual MCP SDK tests skip locally because `mcp` is unavailable. An isolated Studio venv installed MCP 1.30.0 and pytest 9.0.2, but source transfer did not complete. Local dependency acquisition failed; a bounded diagnostic confirmed DNS resolution unavailable. No protocol pass is claimed.
- A Studio test invocation failed at root conftest because NumPy was missing. A scoped run then showed the expected three RED tests for absent server source. Neither is full repository qualification.
- The `native/framing.py` upload was refused before dispatch by the tool safety layer. It was not replayed or uploaded through another carrier. The three successful partial uploads were preserved under the same operation's evidence directory, outside the source workspace. This document does not clear that refusal.
- The native candidate is POSIX-only. Linux synthetic process/socket tests passed; macOS installation/peer checks and Windows named-pipe support remain unproven.
- Independent code review, protected-source integration, hosted CI, plugin creation, tunnel enrollment, owner admission, two-host placement, persistent grants and user-visible installed acceptance remain open.

No provider worker, Job/Attempt, service, tunnel, private plugin, browser installation, credential, production merge/deployment or policy change was performed by this candidate. Auth0 remains deferred.

## 11. Continuation and non-repetition

The registered operation and branch above remain the same. The product source is NOT published; architecture publication does not imply it is. Full review source and logs are preserved in the attached `mastermind-browser-candidate` package; `SOURCE_MANIFEST.json` pins the bytes. The Studio partial upload is retained as evidence, not an alternative product tree.

Next: independently review the exact local candidate and the existing #1057/#1071 integration seam. Recover the original source-upload permission/capability through its proper owner before another upload of the denied file; do not turn a new session into retry authority. Execute actual SDK tests in a qualified environment. Obtain approved extension distribution/installation for a real browser canary without overriding policy. Then integrate and qualify B4/B5 before B6/B7 release.

Do not rebuild the Web Sol extension, B1, the existing admission join or Studio/Fabric source; do not weaken isolated/persistent mode; do not launch Codex/Work; do not install fake authority; do not multiply schedulers; do not confuse synthetic source tests with PROVEN_LIVE. No automatic wake or background continuation is claimed.

## 12. Primary references

Internal: pinned `docs/sol_skills/INDEX.md`, ACTIVE_EXECUTION, SESSION_RELIABILITY, WEB_CEO_DELEGATION, CLOSEOUT and DELIVERY_WORKFLOW; #1071 browser resource/worker admission/contracts/app; #1051/#1057 source metadata; #1217 fabric-client projection and changed-path census; original Studio/Executive observations.

External documentation checked on 2026-10-05:
- https://developer.chrome.com/docs/extensions/develop/concepts/native-messaging
- https://developer.chrome.com/docs/extensions/reference/api/debugger
- https://developers.openai.com/api/docs/guides/secure-mcp-tunnels
- https://developers.openai.com/plugins/build/mcp-server
- https://developers.openai.com/plugins/deploy/connect-chatgpt
- https://playwright.dev/mcp/configuration/browser-extension
- https://modelcontextprotocol.io/specification/2025-11-25/basic/authorization
- https://py.sdk.modelcontextprotocol.io/v1/

Vendor documentation establishes supported mechanisms, not this system's installed behavior or authority.

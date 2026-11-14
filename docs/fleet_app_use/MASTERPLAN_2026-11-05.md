# Fleet application use — Mastermind OS integration plan

Date: 2026-11-05. Operation: `fleet-app-use-20261105-c2`.
Protected procedure/source: `f4e418163882211c9f0e56ae3d93851543eda2bf`, Skillpack 1.0.1, bootstrap 1.
Source branch: `sol/web-fleet-app-use-20261105-c2`.
Parent architecture: [Workbench fleet #539](https://github.com/mastermindx-market-intelligence/Mastermind/issues/539), existing `WS:CHAIRMAN-CONTROL-ROOM` and `WS:EXECUTIVE-CAPACITY-FABRIC`.
Browser dependency: [Browser Fabric #1259](https://github.com/mastermindx-market-intelligence/Mastermind/pull/1259), observed head `042259c1410146a37b1f5925c540254be9a80b89`; preserve its existing master plan and original source operation.
Related native tool projection: [Universal Studio #1217](https://github.com/mastermindx-market-intelligence/Mastermind/pull/1217).

MISSION_COMPLETE=false. This is an editorial implementation/acceptance tree, not a runtime registry, admission, release, or Agent OS handoff. PLAN_NOT_ORG_LINKED until an eligible Macro Agent OS writer links the committed artifact. Current user assignment authorizes investigation, design, source construction, testing and bounded routine repair; production activation remains subject to the actual existing release and OS permission boundaries.

## Original outcome and completion ruler

A user gives Mastermind OS a useful task. An admitted agent discovers suitable computers, browser profiles and apps; chooses the most reliable permitted interaction route; completes the task using one or several apps; verifies the actual result; returns evidence and continues after interruption without duplicating effects. The same capability works for native harness agents and paid Fabric workers across the enrolled Mac and Ubuntu fleet.

Completion requires live browser and native-app journeys, usable product controls, original-root worker consumption, cross-host artifact custody, human takeover, restart/uncertain-effect reconciliation, and proof on each enrolled host class. A plan, fixture, PR, merged source, successful command or installed package alone does not complete this mission.

## Verified starting point

- Cursor documents both an integrated browser controlled by an extension MCP server and desktop computer use. The attached screenshot's blue frame and “Cursor is using Chromium” indicator do not identify its private implementation.
- Cursor's macOS self-hosted path uses a CLI-managed helper in the logged-in GUI session with Accessibility and Screen Recording permissions; Linux uses X11. These are useful architectural references, not code to copy.
- Protected source already has `control_plane/browser_resource_contract.py`, `worker_browser_b1.py`, the existing Operator Harness resource contracts, and `integrations/workbench_browser_mcp/` with signed resource/action references and original effect owners.
- #1259 already implements a substantial attached-tab Browser Link/fleet candidate. Its current record explicitly owes protected release, installation and real estate acceptance. Do not rebuild its browser broker, extension, OAuth, action store or deployment transactions.
- The exposed Fabric adapter reports availability; actual worker admission/start has not yet been proven for this operation. Executive's read endpoint returned `backend_unavailable`. Studio fleet status returned `FLEET_STATUS_OWNER_RESULT_INVALID`; neither proves all host actions unavailable.
- M2 host shell and canonical Git reads work. The installed workspace owner acquired this operation's clean workspace after the exact base commit became locally available; no workspace guard was removed. M2 has Peekaboo, cliclick and Swift binaries. This is executable discovery, not permission or successful desktop-control proof.

## Architecture decisions

### One authority path, several interaction adapters

Executive OS owns admission, Jobs/Attempts, resource reservations, cancellation, placement and lifecycle. Existing Workbench action/resource owners retain prepare/dispatch/reconcile and effect receipts. Existing Browser Fabric owns browser profiles, attached tabs and browser actions. Agent OS owns durable project continuity. GitHub owns code and verification evidence. Mastermind OS renders these facts and issues admitted user intents.

Add necessary host-local native app execution adapters and a thin harness capability composition. Do not add a second fleet manager, queue, scheduler, credential database, lifecycle registry, session manager or retry engine.

Prefer an app's supported API/MCP where it can satisfy the intended operation and identity, semantic browser control for web work, native accessibility for app UI, then current screenshots and pointer/keyboard input when needed. These routes are task choices; an uncertain mutation cannot be retried through another adapter.

### Identity and capability facts

Bind every action to the existing original root/Job/Attempt and resource ownership, plus enrolled host, boot/session, OS principal, app process/window or browser profile/target, account/tenant/workspace, current surface generation and authority. Observations carry freshness and geometry. Opaque existing owner references, not model-supplied raw endpoints, profile paths or credentials, select targets.

Report capability facts independently: discovered, installed, permission granted, usable in current GUI/display session, admitted for this operation, and proven by a real task. A headless Ubuntu host can support an isolated browser without supporting a physical desktop. Locked/logged-out Macs, absent displays and revoked TCC grants are precise readiness states.

### Concurrency and user control

A native desktop is a shared input seat. Focus, mouse, keyboard, clipboard and modal dialogs require an incumbent-owner reservation broad enough for the actual effect. Separate windows alone are not independent seats. Browser tabs can run concurrently only within existing tab/profile/account reservations; cookies, downloads and account-wide writes remain shared.

Mastermind OS should show the exact computer/app/profile being used, live observation, active task and immediate Pause/Take over/Resume/Stop controls. Takeover fences queued and delayed dispatch at the receiving host; resumption requires a fresh observation. Do not switch focus on a human-active workstation merely because another host is busy.

### Effects, artifacts and recovery

Observe -> prepare bound action -> reserve under existing authority -> dispatch once -> read actual postcondition -> retain canonical receipt. Cancellation/timeout/disconnect after dispatch means uncertain effect until original-owner reconciliation. Lease expiry or missing reply never authorizes a second writer. A successful tool call does not prove a document saved or a website accepted an edit.

Cross-app work is a sequence of separately reconciled effects. Artifacts retain origin host, approved path/reference, content hash, MIME and downstream consumer. Transfer through existing artifact owners. Never copy browser cookies across hosts as a migration strategy. Persist enough accepted state for fresh-session recovery, not screenshots/transcripts as a new memory store.

## Task tree and dependencies

| ID | Deliverable | Depends on | Acceptance / falsifier |
|---|---|---|---|
| P1 | Current Cursor evidence and incumbent source/fleet census | current pin | Primary sources, exact modules and live capability observations; distinguish source from installed. |
| P2 | Native app capability/observation adapter in existing Workbench/harness boundary | P1 | Real local app inventory and explicit permission/session readiness; no application launch or input from a read. |
| P3 | Bounded native UI actions with existing effect and shared-seat ownership | P2 | Actual draft edit/save/readback; stale focus/generation, concurrent input and lost reply counterexamples. |
| P4 | Harness and Fabric tool exposure through current capability grants | P2/P3 | Real admitted worker discovers permitted tools, performs a task and returns consumed evidence; unauthorized tool absent/refused. |
| P5 | Browser integration with #1259 | incumbent browser release/custody | Same browser owner across OS and worker clients; actual persistent/attached profile, no duplicate broker. |
| P6 | Mastermind OS fleet/apps UI | P2/P4 | Real readiness, target selection, task evidence, takeover and precise unavailable states; no fixture-only green status. |
| P7 | Host enrollment and rollout | merged reviewed sources, host access and needed OS ceremony | M2/M1/minis/MacBook and observed Ubuntu hosts have individually verified capabilities, with stable helper identities and rollback. |
| P8 | Cross-app/cross-host journey and restart proof | P3–P7 | Browser download -> native edit -> save -> downstream consumption; original result recovered after connection loss without replay. |
| P9 | Performance and operating proof | P8 | Measure action/observation latency, task success, recovery success, token/bytes and host pressure; no invented benchmark target. |

Exact owned implementation paths will be frozen after the bounded census. Candidate namespace `integrations/workbench_app_use/` may contain data-plane adapters only when the incumbent source lacks them. Preserve #1259/#1217 writers and core runtime grants. A new namespace must not conceal duplicated authority.

## Meaningful verification

Positive journeys: browser read and reversible edit; native app read and draft save/reopen; mixed semantic/vision control; correct account/tenant; original Fabric root and result; at least one Mac and one supported Ubuntu session; then every enrolled host.

Counterexamples: same-title windows; focus/modal change before input; changed browser document; shared profile logout; app/API account mismatch; stale screen geometry; human takeover with queued commands; disconnect after dispatched write; late reply after cancellation; missing host; revoked permission; unavailable GUI; stale artifact/wrong host; untrusted page instructions; malformed tool arguments; bounded output/timeout; no double effect or blind fallback.

Use real-path tests in disposable local drafts and intended enrolled profiles. Do not send messages, trade, change credentials, or submit external business effects as a test. Required protected CI/formal approvals remain separate from the CEO Web self-review waiver.

## Delivery and continuity

Publish source and plan updates on this one operation branch, read back exact revisions, and keep the original browser operation intact. Follow normal exact-head CI and legitimate protected release. Production rollout must name exact merged release, eligible hosts, installed helper identity, permission/readiness readback and actual task proof.

Current next action: consume bounded source census, implement the nearest useful native observation/action vertical through the incumbent owners, verify it, then continue harness/UI/fleet integration. A blocked release or OS approval holds only dependent deployment work.

## Primary reference sources

- https://cursor.com/docs/agent/tools/browser
- https://cursor.com/docs/cloud-agent/self-hosted/computer-use
- https://cursor.com/docs/cloud-agent/capabilities
- https://cursor.com/changelog/2-0

References describe public behavior. Do not infer private Cursor transport internals or claim that screenshots establish exact source implementation.

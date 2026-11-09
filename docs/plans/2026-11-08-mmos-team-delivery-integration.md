# Mastermind OS: Team, T3 Code, Hermes and Capacity Fabric integration

> **Current design amendment — 9 November 2026:** Sections 14–15 retain the accepted Team/Capacity/conversation refinement. Sections 16–18 record the Chairman's expanded T3 donor-integration commission; Section 18 is the current complete Code/settings frame map and integration contract. It covers all eight T3 tool surfaces and all 22 settings families, with Hermes, Teamlink, Capacity Fabric and DSH ownership preserved. Earlier implementation packets remain unexecuted by this session.

Date: 2026-11-08 (America/Vancouver); research and design session continued into 2026-11-09 UTC.
Operation: `t3-hermes-os-team-design-20261108-c3`.
Status: **expanded donor study and 38-board native Paper design package complete; application implementation, runtime activation and measured consumer/performance proof pending**.

- [Product designs](https://app.paper.design/file/01M3NRCX55B452A12819WNE1RH/p-O-0)
- [Maintenance and recovery states](https://app.paper.design/file/01M3NRCX55B452A12819WNE1RH/p-P-0)
- [Architecture and GLM build sequence](https://app.paper.design/file/01M3NRCX55B452A12819WNE1RH/p-Q-0)
- [Existing MMOS V1 integration #2338](https://github.com/mastermindx-market-intelligence/Mastermind/pull/2338)

## 1. Mission and acceptance boundary

The Chairman asked for the architecture, Paper designs and an implementable local-GLM plan that brings the always-on bot team, Hermes, T3 Code, DeepSeek Harness and Capacity Fabric into a coherent Mastermind OS experience while Fable completes maintenance draining.

This document fills the product/UI/Paper gap explicitly deferred by the existing MMOS V1 programme. It extends that programme; it does not create a competing admission, routing, placement or lifecycle system. The current session owns this design extension and its source branch, not Fable's incumbent runtime work.

The design commission is complete when the existing interfaces are reconciled, actual Paper frames cover the company-to-coding journey and failure states, the designs have visual/node readback, and source-linked implementation packets define dependencies, exact scope, acceptance and rollout. Those deliverables are present below. Screenshots and Paper JSX demonstrate authored layouts, not implemented interactions.

Production acceptance remains a separate, stronger result: the installed OS must show the authoritative fleet, preserve real bot conversations, open the exact coding workspace, dispatch a single admitted task through the qualified owner chain, and return a real result to the originating bot/project. Section 12 specifies that proof.

No bot, coding process, worker, restart, drain release, provider activation, deployment or external message was launched by this commission. Implementation packets below are **NOT_STARTED**, not queued work. Their release dependencies are technical/custody checks, not invented human approval ceremonies.

## 2. Evidence and source pins

| Source | Exact inspected revision or observation | Meaning |
|---|---|---|
| Mastermind protected master | `06ef56a39c085af72bcbf0866db8e43f99cd6034` | Governing source and existing OS implementation |
| Mastermind publication-time source refresh | `ed7991199ccf76027f7acccc283c539c175e7e16` | Two subsequent commits add the incumbent OS app-control bridge and CI coverage; governing laws and this owned document path are unchanged |
| Macro main | `4bd1948ac0d9ecf40301caf70cbf8cf1619fd2c4` | Design doctrine and product design system |
| T3 Code upstream | `d0f1f7200dce1229f75314b3d9eb1d7ac3abb607` | Inspected upstream interfaces, not an installed-version claim |
| Hermes upstream | `dcace04df1888a61fec80720e661e4ac7db5bb0e` | Inspected upstream interfaces, not an installed-version claim |
| MMOS V1 #2338 | `81f0ef906acfa48cef8f22028b57e0e752874e8b`, observed Open/Draft | Integration candidate, not production qualification |
| #2308 shared-contract repair | `70a6d57454cadecbfd8f9088dee87ac5ecb2afab` | Later than the `8998d76f` version composed in the observed #2338 candidate |

**Dependency reconciliation is the first implementation task.** Do not use an older composed test count as proof of the repaired current stack. Check exact PR heads, accepted source, installed binaries and current release holds before consuming them. Do not overwrite or restart the incumbent programme.

The existing programme was inspected read-only at:
`/Users/chriswong/.hermes/profiles/engineering/mmos/PROGRAM.md` and `STATUS.md`.
Its title is “PROGRAM — Rev4 V1 (ROUTING + PLACEMENT) as director-level WORK ORDERS”; its Appendix A defers the UI/Paper redesign. These are dated, unversioned runtime observations. GitHub remains the source owner for the reviewable extension.

### What the current application actually represents

At the protected pin, `app/mastermind_os/src/meta-ceo/ByokRolesPanel.tsx` and `byok-role-view.ts` encode two fixed roles. `common/workspace_byok_read_contract.py` likewise has two role entries and a 30-second observation-age rule. These are configuration/read contracts, not a complete live team registry.

`src/organization/OrganizationWorkspace.tsx` and `integrations/hermes_leadership/organization.py` expose an advisory organization structure: eleven charter seats, `SOURCE_LINKED_ADVISORY`, `full_fleet: false`, and live enrollment not observed. Relabeling that structure as twelve live bots would be incorrect.

The Chairman reports twelve always-on bots. A read-only host census observed thirteen named profile directories, with `default` counted separately by the profile helper. Directory presence does not establish company membership, enrollment, gateway serving status or availability. The authenticated `GET /api/profiles` probe returned 401; the investigation stopped at that boundary and did not retrieve credentials or use an alternate roster route.

Installed Hermes source identifies `list_profiles(lazy_skill_count=True)` / `profiles.list` as the profile source; `profiles_to_serve()` also excludes parked, tombstoned and standalone profiles. GLM-00 must resolve the actual authenticated roster and its existing company/role mapping. **Do not hardcode twelve, silently exclude a profile to reach twelve, or equate directory count with live bots.**

Maintenance observations are similarly scoped. A dated #983 comment reported one shared drain expiry/release, but it does not prove all Fable maintenance is complete. Gateway “running” is not a drain-status contract. Read the current owner, affected scope, timestamp and permitted actions immediately before any dependent execution.

### Reuse map

| Concern | Existing source to extend or consume |
|---|---|
| OS conversation state, draft and return behavior | `app/mastermind_os/src/conversations/**` |
| Native Hermes transport and capability envelope | `src/hermes-native/**`, `docs/hermes/THIN_NATIVE_OS.md` |
| Existing office and advisory organization | `src/meta-ceo/MetaCeoOffice.tsx`, `src/organization/**` |
| Attended jobs and inspectable receipts | `src/fabric/AttendedFabricWorkspace.tsx`, `FabricMissionInspector.tsx` |
| Host/provider observations | `src/resources/HostTelemetryPanel.tsx`, `ResourceCapacityRead.tsx`, `RetainedProviderCapacityPanel.tsx`, host observation adapters |
| Existing semantic OS control | `src/agent-control/**`, `docs/MASTERMIND_OS_APP_CONTROL.md` at the publication-time refresh; keep the existing Workbench browser/action owner |
| Host abstraction and native/web distinction | `src/host.ts` and the existing authenticated host implementations |
| Shared execution contract | #2308, `control_plane/child_execution_contracts.py` |
| Existing idempotent admission and durable waiting queue | #2317, `control_plane/child_request_admission.py` |
| Sole placement and claim ownership | #2314, `AttemptRegistry.claim_job`, `control_plane/executive_placement_authority.py` |
| Launch guard | #2329, `ops/executive_os/provider_orchestrator_guard.py` |
| Host readiness/execution | #2331, `control_plane/executive_host_executor.py` |
| Binding compatibility and decision evidence | #2330, `control_plane/execution_binding_compat.py`, `executive_decision_ledger.py` |
| Route preview | #2318, `integrations/executive_mcp/route_preview.py` |
| GLM routing | #2320 and the applicable composed V1 contracts |

Paths beginning `src/` in the UI rows are relative to `app/mastermind_os/`. Candidate PR references identify dependencies to reconcile, not an assertion that every feature is merged or deployed.

## 3. Product decision: Team, Projects, Code and Fleet

Expand the single-office experience into four connected workspaces in the existing Noir/Atelier shell:

- **Team:** the enrolled company, searchable and filterable by role/work. A card opens the existing bot workspace. Meta-CEO remains a leadership workspace within the team; old office links and sessions survive.
- **Projects:** outcome, owner, plan, current coding work, review and delivery evidence. A project collects the work without becoming another job scheduler.
- **Code:** the exact T3 environment/thread/workspace, conversation, changes, terminal/checks, request state and return link.
- **Fleet:** host readiness, provider/account capacity, observations and maintenance scope. Host slots and model quota remain separate.

Today, Inbox, Conversations and Knowledge remain coherent entry points. Twelve teammates do not become twelve permanent navigation tabs. The roster must handle fewer, twelve, or more members, plus partial source coverage.

Proposed client route concepts are `team/:botId`, `projects/:projectId`, `code/:environmentId/:threadId` and `fleet`. These are client navigation concepts, not new backend authority endpoints. Adapt them to the existing router and preserve bookmarks, selected project/bot, draft text, scroll position and return focus.

### Twelve-member design fixture

Paper uses Mastermind CEO, Autonomy CEO, Chief of Staff, Engineering, Delivery, Reliability, Product, Design Lead, Marketing, Intelligence, Assurance and Secretary to demonstrate the full layout. These twelve cards are an illustrative subset for layout capacity, not a complete live roster, a new enrollment policy or twelve newly provisioned identities. The existing Meta-CEO office remains reachable explicitly from TD01 even though Meta-CEO is not one of these twelve sample cards. GLM-00 must resolve actual membership without excluding any profile merely to match the fixture.

Leadership sets direction and coordinates; Engineering, Design and Product develop the product; Assurance, Reliability and Delivery verify and operate it; Intelligence and Marketing contribute specialist work; Secretary preserves communications and follow-through. The actual runtime role mapping comes from the existing owners, not from the card order.

## 4. Runtime ownership

| Layer | Responsibility | Explicit boundary |
|---|---|---|
| Mastermind OS | Human navigation, authenticated read projections, exact-target command translation, source-linked evidence | Does not create its own lifecycle, memory, auth, placement, queue or retry plane |
| Agent OS | Mission continuity, role/work relationships and durable next action | Does not infer successful runtime effects from UI state |
| Hermes gateway | Persistent bot/profile sessions, context, approvals and canonical runtime events | Opening Bot Chat attaches; it does not spawn a fresh coding agent |
| Executive / Capacity Fabric | Company admission, route eligibility, host/account/workspace reservation, leases, job/attempt lineage and return | Remains the sole company placement and admission owner |
| T3 Code environment | Coding thread/workspace, provider session/process, changes, tools and coding events | Starts the selected ACP process for a T3-backed attempt |
| DeepSeek Harness | Qualified coding execution engine beneath T3 ACP | Is not also started independently for that same attempt |
| GLM provider/account | Selected model access under existing account and budget custody | Bot role, engine name and model identity are independent |
| GitHub / release owners | Source, PR, checks, required review, protected release and evidence | A returned coding result does not mean merged, deployed or accepted |

**Core ruling:** for company-admitted T3 work, Fabric dispatches one environment-bound T3 command. T3 alone starts the DSH process for that thread. The native DSH route can remain an alternative for a different attempt; it must not run alongside the T3 route for the same attempt.

No upstream branded UI, proprietary assets or corpus are copied. The designs are original Mastermind layouts using the existing design system. Any code reuse must preserve the applicable upstream license and attribution.

## 5. Identity and read contracts

Keep stable references instead of deriving identity from labels:

| Reference | Purpose |
|---|---|
| Bot ID and Hermes profile ID | Persistent teammate identity and runtime profile |
| Role assignment | Organizational responsibility, separate from bot/provider/model |
| Mission/workstream and project IDs | Why the work exists and where its result returns |
| Host and T3 environment IDs | Physical execution location versus stable T3 instance identity |
| Workspace/repository/base/head references | Exact source custody and checkout |
| Provider instance and account reservation | Engine configuration and capacity owner without secret material |
| Hermes session ID | Persistent bot conversation |
| T3 thread, run and native session IDs | Coding execution lineage |
| Executive job, attempt and admission/command references | Canonical admission, effects and reconciliation |

A hostname, display name, SSH alias or URL is not an environment identity. A bot is not a model. A visible thread is not a new job.

### Projection shape

Extend the incumbent read contracts with typed, non-authoritative projections. Suggested vocabulary below is design guidance; reuse existing shared types rather than installing parallel versions of `ChildExecutionRequest`, `ExecutionBinding` or `RoutePreview`.

Every observed field or aggregate carries a source reference, observation timestamp, freshness and coverage. Unknown values are null/unknown, not zero or false. A partial response must not be rendered as an empty company. Freshness thresholds come from the owning contract; the existing BYOK 30-second limit is not silently applied to every provider.

A team member projection needs stable IDs, display name, role references, enrollment state, observed runtime presence, current project/work references, existing conversation references and available operations. A team snapshot needs pagination/coverage and a nullable authoritative count. Directory/profile visibility and enrolled-company membership are distinct fields.

A coding projection needs environment/project/thread IDs, bound workspace and provider instance, source cursor/revision, connection freshness, separate command/turn/artifact/check states, capabilities and the originating attempt/project/bot references.

A fleet projection needs host role, readiness, heartbeat age, enrolled/eligible slots, current occupancy, maintenance scope, provider account state, quota observation and exclusion reason. “Unknown quota” must remain different from “zero quota”; an unenrolled host must not contribute available slots.

### Commands and capabilities

The authenticated host derives the actor. The renderer does not supply trusted identity, private tickets or credentials. Each modifying user action is tied to the existing operation/attempt reference, exact target and applicable expected revision/generation. Stable request correlation and receipts remain in the incumbent owner's record.

Expose operations individually: read, attach, create, send-next, steer-current, stop, restart, approval response and recovery. An upstream advertised feature is insufficient; availability must be observed on the installed route for this principal, profile, environment and version. Show a useful disabled reason when an action is unavailable.

A response can mean admitted, queued, running, awaiting input, terminal, failed or effect unknown. Preserve that distinction. Reconnection restores subscriptions/read state; it does not resubmit mutations.

## 6. Hermes adapter

Reuse `hermes-native`, the existing conversation components and the same-user gateway attachment model in `THIN_NATIVE_OS.md`.

The inspected gateway protocol supports runtime description, session create/resume, prompt submission and approval response with owner-side IDs and generation checks. Existing bot conversations should use that gateway-owned session path. The upstream HTTP API has its own session ownership: it cannot be used to commandeer a CLI/TUI/Desktop/ACP/messaging conversation.

Important requirements:

1. Resolve profile and stable logical session identity through the existing authorized owner. Attach to that identity; changing a view must not reset memory or create another bot.
2. Keep queue-next separate from steer-current. Steer is capability/generation dependent and can be unsupported for managed workers; an acknowledgement does not make steering durable or safely replayable.
3. A disconnected viewer must not kill the bot. Use the persistent gateway session model, not a browser-tab PTY lifetime.
4. Preserve original creation/submission principals when another authorized operator views the same session. Shared operator access is not impersonation.
5. Profile isolation, auth-generation fences, approvals, transcript access and recovery remain enforced by Hermes. No credentials or provider keys reach the renderer.
6. If the route only supports Meta-CEO and Secretary today, generalize it deliberately through the authoritative roster contract. Do not fabricate other bots as runtime-ready.
7. Hermes as a T3 ACP provider is a **separate coding-session identity**, linked to the requesting bot/mission when appropriate. It is not the persistent bot's conversation.

Primary references: [gateway sessions](https://hermes-agent.nousresearch.com/docs/developer-guide/gateway-local-sessions), [API server](https://hermes-agent.nousresearch.com/docs/user-guide/features/api-server), and [pinned upstream source](https://github.com/NousResearch/hermes-agent/tree/dcace04df1888a61fec80720e661e4ac7db5bb0e).

## 7. T3 and DSH adapter

The inspected T3 provider documentation supports a Local ACP Command and specifically documents executable `dsh` with literal arguments `--profile` and `acp`. Treat that as a supported upstream integration seam to qualify against the installed DSH profile, model configuration and protocol version; it does not prove the local GLM route is currently usable.

Use a narrow, version-pinned adapter to T3's supported external operations and, where necessary for rich events/diffs, its typed client/RPC boundary. The inspected `packages/contracts/src/rpc.ts` and `packages/client-runtime` are source contracts, not an assumed stable published SDK. Avoid DOM scraping or a long-lived fork of T3's whole application.

Start with capability/environment/thread reads and attach. T3's external tools include capability, environment, thread read/list/control, queue and pending-request surfaces. A restricted MCP OAuth token is not general HTTP/WebSocket authority. Choose the richest supported authorized boundary actually available, and preserve explicit unavailable states.

For a qualified managed route:

- Resolve the stable environment ID, provider instance, project and workspace before dispatch.
- Invoke the configured executable directly with literal arguments. No shell interpolation or renderer-supplied executable/SSH command.
- The existing workspace owner supplies the exact admitted checkout for the first integration. T3 uses it. If a later mode delegates worktree creation to T3, the other allocator must not run.
- Do not assume ACP provides provider-account isolation, native child lineage or arbitrary session import. Qualify each separately.
- Preserve event ordering/cursors. A command receipt is not provider-start proof; a provider-finished event is not a finalized diff/result.
- T3 checkpoint rollback may restore files and create a fresh conversation depending on provider capability. Surface that consequence; do not label it transparent continuation.
- “Open in T3” must preserve environment/thread/project/workspace and use a validated owner-supported link. Opening a tab must not launch work.

Primary references: [ACP providers](https://github.com/pingdotgg/t3code/blob/d0f1f7200dce1229f75314b3d9eb1d7ac3abb607/docs/user/providers-acp.md), [architecture](https://github.com/pingdotgg/t3code/blob/d0f1f7200dce1229f75314b3d9eb1d7ac3abb607/docs/internals/overview.md), [remote environments](https://github.com/pingdotgg/t3code/blob/d0f1f7200dce1229f75314b3d9eb1d7ac3abb607/docs/internals/remote.md), [external agents](https://github.com/pingdotgg/t3code/blob/d0f1f7200dce1229f75314b3d9eb1d7ac3abb607/docs/user/outside-agents.md).

### One launch-owner matrix

| Path | Admission/placement | Process owner | Required behavior |
|---|---|---|---|
| View an existing external T3 thread | Existing external owner | Existing T3 process | Read exact environment/thread; no new job, checkout, slot or process |
| New company coding task | Existing Executive/Fabric | T3 launches DSH | Reserve/bind first; dispatch once; save identities in the existing attempt |
| Continue company coding | Existing bound attempt/continuation authority | Existing T3 controller | Validate generation, lease and action; retain binding through queued turns |
| Manual interactive T3 work | User's manual session | T3 | Mark external/manual; exclude shared occupied capacity or use dedicated capacity |
| Persistent Hermes bot chat | Existing gateway and bot supervisor | Hermes gateway | Attach to the same profile/session; coding becomes a linked admitted child |
| Hermes ACP coding | Company coding admission when managed | T3 starts Hermes ACP | Separate coding identity; never replace or clone Bot Chat |
| Adopt external work | Explicit supported adoption flow | Unchanged existing T3 owner | Reconcile existing effects, record provenance, do not relaunch; otherwise observe only |

### Dispatch handshake

1. Existing admission returns the job/attempt and exact host, account and workspace reservation.
2. Preflight installed capabilities, environment identity, provider configuration, permissions, owner generation, drain state and reservation validity without setup/login side effects.
3. Freeze operation/command correlation and target references in the existing attempt/binding record.
4. Dispatch one T3 command. Do not invoke the ordinary DSH launcher for this attempt.
5. Read back the returned environment/thread/run/native-session identities and compare them with the frozen binding.
6. Mark running only after an actual provider-start event.
7. Control and settle through that same owner. Capacity releases only after process/child settlement, not browser disconnect, acknowledgement or model text completion.

The selected external command route must provide adequate stable caller correlation and receipt lookup. T3's internal durable command receipts alone do not prove every MCP call accepts a caller idempotency key. If the launch contract cannot correlate a lost response, the managed route stays unavailable until repaired/qualified. An uncertain dispatch is reconciled on the original environment; it is never replayed with a new title, new thread or native DSH fallback.

Fabric owns waiting before dispatch. Once bound, T3 owns session-local turn ordering while Fabric tracks the same attempt. Do not keep two independent company waiting queues or release a reservation while a continuation remains queued.

Managed T3 tools that create children, linked-environment work or schedules must be disabled or routed through the existing admission/budget lineage. A prompt instruction to avoid delegation is not enforcement. Remote placement or autonomous schedules must not escape the admitted environment and budget.

## 8. Backend, security and operational consistency

Use the existing authenticated application/host adapters. A same-user desktop application may use its existing native gateway attachment. The browser version must consume an authorized server projection or report the operation unavailable; it must not acquire a loopback operator proxy, private bootstrap ticket or arbitrary fleet SSH facility.

The publication-time source refresh adds an existing semantic app-control bridge (`mastermind.os.app-control.v1`) through the incumbent Workbench browser owner. Extend normal accessible route buttons and controls so Team, Code and Fleet remain inspectable through that bridge. Preserve its current observation, owner/generation, privacy/exclusion, disabled-control and original-action reconciliation rules. Do not add component-specific AI business APIs or another browser/controller. Source qualification does not establish installed publication or real-consumer acceptance; GLM-06 must verify the actual intended connection. See [the refreshed app-control contract](https://github.com/mastermindx-market-intelligence/Mastermind/blob/ed7991199ccf76027f7acccc283c539c175e7e16/docs/MASTERMIND_OS_APP_CONTROL.md).

The OS may maintain bounded authenticated view caches and event cursors under the existing conversation/read infrastructure. Those caches are disposable projections, not a second session/memory/event authority. On a cursor gap or reconnect, request a source snapshot; do not manufacture omitted events. Scope subscriptions to the selected workspace and active views, and use existing observer mechanisms rather than another watcher/daemon.

Display host and provider evidence with source/age and a readable exclusion reason. The observed V1 topology made M2 a coordinator, Ubuntu 0 an enrolled worker candidate, and M1/other Ubuntu hosts dependent on qualification; old mini-host assumptions must not become hardcoded availability. Current actual capacity is obtained at request time, including external/manual occupancy.

The DeepSeek route was named but not yet a qualified live adapter in the inspected candidate. Hermes selection also depended on the programme's owned cutover. GLM model labels in Paper are examples; installed provider/model support and account/budget eligibility decide actual routing.

During drain, show affected scope, owner, age, existing runs and which commands remain permitted. The UI re-read improves the preview but does not enforce the launch. The existing execution owner must enforce current scoped drain policy, binding generation, permissions and reservation through its fenced claim/launch check at the actual start or continuation boundary. Continuations follow that owner's scoped drain policy; a second preflight read alone does not close the time-of-check/time-of-use gap. A drain before dispatch blocks a new start; a drain after start preserves the original observation and settlement path. Refreshing a page must not release a drain or abandon work.

## 9. Paper delivery and interaction contract

The existing file is `01M3NRCX55B452A12819WNE1RH`. Original accepted frames are retained. The Start Here directory now contains a Team & Delivery entry (`12UG-0`) directly after the canonical design authority entry.

| Frame | Paper node | Purpose |
|---|---|---|
| TD01 Team | `ZQN-0` | Twelve-card company workspace, role filters, maintenance visibility |
| TD02 Bot workspace | `102K-0` | Persistent Engineering conversation, project/context, linked coding, distinct steer/send-next |
| TD03 Project | `10B8-0` | Outcome, owner, plan, coding session and delivery trail |
| TD04 Code | `10L5-0` | T3 conversation, DSH/GLM/environment context, changes and checks |
| TD05 Fleet | `10WB-0` | Coordinator/worker distinctions, capacity uncertainty, maintenance scope |
| TD06 Route review | `117C-0` | Proposed route, workspace, readiness and explicit request; preview is not execution |
| TD07 Run/result | `11GQ-0` | Request/admission/start/provider-return/result/return distinctions |
| TD08 Team, 390 EN | `11ZB-0` | Narrow roster and persistent navigation/actions |
| TD09 Code, 390 EN | `123Z-0` | Narrow coding continuation, changes/checks tabs and composer |
| TD10 Team, 390 ZH light | `128B-0` | Representative translated copy and light-token mapping |
| TS01 Recovery states | `11QU-0` | Scoped drain, uncertain dispatch, unverified roster components |
| TB01 Architecture | `12DE-0` | Runtime ownership, identity and single-launch rule |
| TB02 Build sequence | `12LO-0` | Eight GLM packets, dependencies and proof |

Product page `p-O-0` contains ten frames; States `p-P-0` contains one three-state board; Build `p-Q-0` contains two boards. Desktop boards are 1600×1040; narrow boards are 390×844. The thirteen artboards were read back, screens visually inspected, layout/contrast errors repaired, and working indicators released. Team, coding and narrow Team JSX were also read back for structural verification.

All model responses, activities, timestamps, counts, available actions and route-readiness claims inside these frames are **design fixtures**. They are not production telemetry, passing tests or an admission/release receipt.

### Interaction requirements for implementation

- Team card opens its persistent bot identity. A linked code card opens its exact environment/thread; back navigation restores the originating bot/project and draft.
- At 390px, conversation, changes and checks become reachable tabs rather than horizontally compressed desktop panes. Preserve all core actions and exact context.
- Keyboard focus is visible. Cards, filters, menus and tabs have meaningful labels; dialogs restore focus to their trigger. Escape closes an overlay without cancelling work.
- Enter/send behavior follows the existing conversation contract; composition/IME must not accidentally send. Queue-next and steer-current are separate accessible controls.
- Stop/restart/approval actions show their target and consequence. Use the actual capability/generation contract; never make a read view's reconnect a restart.
- Announce state changes without flooding assistive technology. Status must be readable in text, not color alone. No essential action depends on hover.
- Preserve long bot names, arbitrary roster size, empty/partial/error/loading states and unknown observations. Do not replace failure with a plausible-looking roster.
- EN/ZH strings and both themes belong in the existing localization/token system. TD10 is a representative layout check, not proof that every screen is already translated or theme-complete.
- Reuse existing component conventions and shared tokens. Do not ship Paper's illustrative JSX as a new runtime framework or duplicate routing/session stores.

## 10. Local GLM implementation packets

All packets use the incumbent paid/local capacity admission path when execution is authorized and qualified. The twelve-bot company size does not imply twelve simultaneous coding slots. Concurrency is limited by live host/account/workspace reservations and current budgets. Persistent leadership bots coordinate the work; bounded GLM coding attempts do the implementation.

Each worker receives this source-linked brief, exact accepted dependency SHAs, owned paths, output/return location, applicable Paper nodes and test commands discovered from the actual repository. It must return a scoped diff, executed checks, unresolved limitations and original attempt/session/PR references. No “done” claim based only on generated artifacts.

### GLM-00 — Baseline and capability reconciliation

**Owner type:** integration lead, with bounded read-only qualification support. **Depends on:** no coding packet.

Resolve #2338/#2308 composition and current accepted source. Record installed Hermes, T3 and DSH versions and route capabilities. Read authenticated profile/company enrollment, reconcile the reported twelve with profile inventory, inspect current maintenance scopes, and identify qualified host/account capacity. Preserve active writers and existing grants.

**Output:** a compact version/capability/roster/dependency manifest with source references and unknowns. **Pass:** no unsupported/live assertions; a concrete authorized route for subsequent work or a precise per-route blocker. Do not start workers merely to test whether a launch is permitted.

### GLM-01 — Team/session read contracts

**Owner type:** backend contract worker. **Depends on:** 00.

Generalize fixed two-role assumptions through the existing host and Hermes adapters. Introduce typed projections for authoritative membership, role mapping, freshness, persistent conversation references and operation capabilities. Preserve existing Meta-CEO/Secretary compatibility and native/web boundaries.

**Owned surface:** roster/read-contract adapter and its focused contract tests; one integration owner handles shared `host.ts` declarations. New file names such as `src/team/team-read-contract.ts` are proposed locations, not existing mandatory paths.

**Pass:** zero, partial, twelve and greater-than-twelve roster cases; archived/parked semantics from the owner; stable session references; unauthorized and stale reads; unknown values do not become available/empty.

### GLM-02 — Team, bot and project UI

**Owner type:** frontend worker. **Depends on:** 01.

Implement TD01–TD03 and TD08/TD10 using existing conversation/project components. Add Team navigation, bot detail, project-to-code links and appropriate legacy office aliases. Use fixtures only in test/story surfaces; product reads the real projection.

**Owned surface:** Team/product UI and route composition assigned to this worker. Other workers consume the shared route contract without editing the same shell files concurrently.

**Pass:** existing app-control route/accessible-control markers and privacy boundaries remain usable; keyboard/deep-link/draft/return behavior; all roster sizes; EN/ZH and light/dark at desktop, tablet and 390px; stale/error states; no provider credentials or new conversation store.

### GLM-03 — T3 read/attach adapter and coding workspace

**Owner type:** integration/backend worker plus bounded frontend slice. **Depends on:** 00, 01.

Qualify a versioned T3 transport; implement environment identity, thread attach/read, events, changes/checks, pending requests and supported external links. Build TD04/TD09 against it. Start with existing sessions; do not enable managed launch in this packet.

**Owned surface:** T3 adapter and Code components, isolated from shared shell/host declaration custody.

**Pass:** two OS viewers see one existing provider process; reconnect/cursor gap restores the same session; worktree mismatch fails closed; unsupported actions stay disabled; token audience and installed capability boundaries hold.

### GLM-04 — Company-admitted T3 execution

**Owner type:** Executive integration worker. **Depends on:** 00, 01, 03, 05.

Extend the existing admission/binding/host execution route for T3-backed DSH. Implement the Section 7 handshake using incumbent records and reservations. Verify caller correlation, no dual launcher, exact checkout, child-tool enforcement, control actions and settlement.

**Owned surface:** the applicable existing route/adapter seam and discriminating execution-contract tests. Do not fork admission/placement or rewrite unrelated V1 work.

**Pass:** the actual owner start/continuation gate enforces current drain policy, binding generation, permissions and reservation; single actual launch; lost acknowledgement produces the same recovered receipt or explicit uncertainty; drain/permission/budget/host races refuse safely; cancellation startup race settles; no cross-environment replay or unadmitted T3 children.

### GLM-05 — Fleet, capacity and maintenance

**Owner type:** operations UI/read-adapter worker. **Depends on:** 01.

Implement TD05/TD06 and TS01 from existing host/provider/placement observations. Keep preview separate from admission. Include maintenance scope/owner/age, live run links, manual occupancy and useful unavailable reasons.

**Owned surface:** resources/fleet projection and presentation slice. Shared provider/executor policy stays with existing owners.

**Pass:** zero vs unknown quota; coordinator cannot appear as a free worker; stale/unenrolled hosts excluded; drain before dispatch blocks the start while existing sessions remain visible; no duplicated observer or polling daemon.

### GLM-06 — Integrated real-path proof

**Owner type:** integration principal with focused verification labor. **Depends on:** 02–05.

Compose exact owned diffs, run affected checks and required CI, then exercise one bounded authorized canary on a qualified worker. Verify the entire trace from a real bot/project request through admission, placement, T3/DSH, changed files/checks and return to the same bot/project. Prove refresh, detach/reconnect and failure paths using the actual surfaces.

**Pass:** Section 12 evidence package. Review and release rules still bind; a CI pass alone is insufficient. Any actual GitHub approval must come from an eligible non-author when required, never from this package's author.

### GLM-07 — Controlled rollout and acceptance

**Owner type:** existing release/operations owner. **Depends on:** 06 and actual release authorization/holds.

Use existing configuration/capability controls to expose read views first, then qualified attach/control, then one managed execution route. Expand only after real consumer proof. Record installed commit/version, source receipt and observed acceptance.

Rollback disables new route admission and returns the UI to supported views while retaining existing sessions, receipts and reservations until their owner settles them. Do not kill persistent bots, clear drains, migrate identities, discard effects or invent a second deployment system.

**Pass:** installed desktop and browser behavior match their permitted capabilities, all enrolled teammates are discoverable, and the canary result is durably linked to its original owner.

### Scheduling and custody

00 precedes 01. After the shared contract is stable, 02, 03 and 05 may proceed on disjoint paths. 04 waits for the launch, host/provider and maintenance contracts. 06 integrates; 07 releases. One source owner coordinates shared imports, navigation, host interfaces and i18n files. Do not launch all eight packets simultaneously or have multiple workers rewrite the same component.

A local GLM quality failure is diagnosed from its concrete return and affected checks. Use the existing qualified fallback/budget route only with authority and reconciled effects. A refusal or uncertain launch is not permission to switch provider/carrier and replay it.

## 11. Required failure and consistency cases

| Case | Passing observation |
|---|---|
| Twelve reported bots, different profile inventory | Authoritative membership and source discrepancy visible; no hardcoded filter to force twelve |
| Profile source unavailable/401 | Unverified roster; existing permitted conversations remain accessible; no invented empty company |
| Same bot opened twice | Same logical Hermes session, no extra bot/runtime |
| Same T3 thread in two OS tabs | One provider process and one company binding |
| Lost dispatch acknowledgement | Same correlated receipt recovered or explicit uncertainty; no second launch |
| Host alias repointed | Environment-ID mismatch refuses attach/dispatch |
| Workspace mismatch | Exact checkout/base/head disagreement refuses the managed launch |
| Drain begins before dispatch | No new start or native DSH fallback |
| Drain begins after start | Original work stays observable and settles under its owner |
| Free host but unverified account/quota | No inference of available model capacity |
| Manual T3 work shares an account | Occupancy excluded/reserved; no conflicting company dispatch |
| Queued continuation then UI closes | One retained queued turn under the original binding |
| Stop during startup | Cancellation targets the actual run and startup race settles once |
| Provider exits or transport drops | Failure/unknown state retained; reconnect does not create another attempt |
| Provider turn ends before diff/checks | Result remains preparing until artifacts settle |
| Bot delegates coding | Bot session survives; distinct coding child and exact return link |
| Hermes ACP provider selected | Separate coding identity; persistent Bot Chat unchanged |
| T3 child or remote schedule escapes scope | Enforced refusal or separately admitted child with lineage/budget |
| Permission/auth generation changes | Current owner refuses stale actions; renderer gains no fallback privilege |
| 390px, long names, keyboard, ZH and theme change | Core actions/context remain reachable and readable; drafts/focus retained |
| Route rollback | New starts disabled; existing sessions/receipts preserved until settlement |

Use focused tests that distinguish these failures. Do not add tests that merely restate a mock implementation. Broaden validation for a concrete remaining risk or binding CI gate.

## 12. Production proof and rollout decision

The eventual acceptance record must contain:

1. Exact source/PR/merge and installed OS, Hermes, T3 and DSH versions.
2. Authenticated roster/enrollment evidence and the observed count at that time.
3. A real bot/profile/session, project and original authorized request reference.
4. Existing Executive job/attempt/admission plus host/account/workspace reservation.
5. Verified T3 environment/thread/run and provider/native-session lineage.
6. Evidence that exactly one provider process started for the canary.
7. Changed-file snapshot, relevant test/check results and reviewed source result.
8. Return into the original bot conversation and project, surviving a refresh/reconnect.
9. Actual permitted desktop/browser paths, keyboard/narrow/theme/language checks, and the existing semantic app-control inspect/navigate/act/check path on the intended connection when available; unavailable installation is reported rather than replaced by a second controller.
10. Current maintenance and capacity observations, rollback behavior and residual limitations.
11. Separate release/deployment/acceptance receipts where owed.

Do not substitute a screenshot, synthetic fixture, successful tool delivery, green CI, queued job or merged PR for this chain. The first implementation milestone is a truthful read-only fleet; the strongest integration milestone is a real consumer completing the joined workflow.

## 13. Design verification and continuity

Verified in this commission: thirteen new artboards and one directory entry, preserved existing boards, representative desktop/narrow/light/ZH layouts, visual inspection of every new artboard, exact node/page readback, structural JSX readback for Team/Code/narrow Team, and explicit Paper finish acknowledgement.

Two pre-dispatch document-drift responses were reconciled by reading the original target and confirming the missing intended node before a fresh edit. One empty-container insertion error was reconciled against the unchanged childless original target, then repaired by replacing that owned container with a proper frame. There are no unresolved Paper effects. No refused action was moved to another carrier.

The next implementation action is GLM-00: reconcile accepted/installed versions, authoritative roster, active maintenance and qualified routes on the incumbent programme. Do not redo the accepted design work unless source, requirements or product feedback changes. The current design branch remains the owner of this document; full worker briefs should link here and return through the existing canonical owner, without a new transport/control plane.


## 14. Paper refinement continuation — 9 November 2026

Current Chairman directive: improve Mastermind OS Paper design only, preserving the Noir Atelier identity and reconciling Capacity Fabric, Teamlink cross messaging, Hermes always-on teams, T3 Code and DeepSeek Harness. This is a design continuation; implementation packets above remain NOT_STARTED by this session.

Procedure pin: Mastermind `ff6d5ab67c3535056d69f603fac0d95c058baad8`; product doctrine pin: Macro `315efde9307bf8a3d241a7683432dfff92cd4a9e`. Source-linked scope receipt: [existing carrier continuation](https://github.com/mastermindx-market-intelligence/Mastermind/pull/2345#issuecomment-6735157236).

### Scoped design plan

- **D1 — Reconcile:** inspect the current editable product, matching state/build pages and source contracts. Separate runtime, harness, model, account pool and execution host. Preserve the original parent and actual return destination.
- **D2 — Compose:** tighten the existing Team, Capacity/Fleet, Team conversation, Code and Today journeys. Keep useful existing features and IDs, with a named destination for every relocated detail. Preserve live/unknown writers and historical Knowledge-only uncertain effects.
- **D3 — Respond:** refine narrow, light and Chinese counterparts and design the important stale/unavailable/queued/working/returned/review states. Define motion, keyboard, focus, context return and render-performance targets outside product copy.
- **D4 — Verify:** inspect actual Paper screenshots, check native node/text readback, record exact mutations and source limitations, and update this existing guide. Do not claim implemented behavior or measured runtime speed from a design file.

DONE_WHEN: cohesive editable Paper primary journeys across all five named integrations, restrained hierarchy and deliberate controls, clear truthful sample/unknown states, usable narrow layouts, explicit builder contracts and verified native visual readback. Original broad product implementation acceptance remains separate.

The current task has no app/runtime writes, provider calls, bot launches, merge or release action. Root retains canvas edits for PRINCIPAL_JUDGMENT and UNIQUE_APPROVED_ACCESS; one bounded native reasoning advisor may critique cross-system semantics with no modifying authority. This advisory role is not paid implementation labor or a new runtime principal. WHY NOT FABLE: bounded architecture critique and direct design composition need no separate principal takeover.

Integration invalidator discovered before edits: the newer native T3 Capacity Fabric provider path and the DSH-backed ACP coding path are distinct; the earlier T3-to-DSH drawing must not be read as a universal path. The live router and the authenticated OS capacity projection also have separate proof boundaries. Further exact source reconciliation is recorded with the design results below.
## 15. Completed Paper refinement — 9 November 2026

**Outcome: PROVEN_OUTCOME for the design-only continuation in Section 14.** D1–D4 are complete. The editable primary journey now runs from Today through Team, the original conversation and Code to the returned result, with Capacity Fabric and source-qualified route details alongside it. This is design acceptance against the scoped DONE_WHEN, not installed application, runtime integration, measured performance or production acceptance.

### 15.1 Authority, source pins and precedence

The Chairman's current instruction explicitly narrowed this continuation to improving the existing Paper design and reconciling Capacity Fabric, Teamlink, Hermes, T3 Code and DeepSeek Harness. Work stayed on the existing Paper file and this existing PR/branch. No application code, service configuration, provider activation, bot launch, external message, merge or deployment was performed.

Procedure and product pins remain those in Section 14. Governing Mastermind documents were read at the same protected revision, not reconstructed from memory.

| Source | Exact observation | Design consequence |
|---|---|---|
| [Capacity Fabric OS integration](https://github.com/mastermindx-market-intelligence/Mastermind/blob/ecbbbc0563c74db0945972ac4cd4481f0853a55f/docs/CAPACITY_FABRIC_OS_INTEGRATION.md) | PR #2351 head ecbbbc0563c74db0945972ac4cd4481f0853a55f | Reuse the authenticated Resources projection; preserve physical allowance scope, independent windows, reset/freshness and consumer evidence. A read preview is not admission. |
| [Native T3 Capacity Fabric wiring](https://github.com/mastermindx-market-intelligence/Mastermind/blob/ecbbbc0563c74db0945972ac4cd4481f0853a55f/docs/T3_CAPACITY_FABRIC_WIRING.md) | Same #2351 head | Native T3 can use the Capacity Fabric provider directly. Company-admitted DSH through ACP remains a distinct path; T3 is not universally a DSH launcher. |
| [Team conversation design source](https://github.com/mastermindx-market-intelligence/Mastermind/blob/ec06a1d70eef254f928bdc7b963a90322efa2b6e/docs/plans/2026-11-08-hermes-team-conversations-paper.md) | PR #2358 head ec06a1d70eef254f928bdc7b963a90322efa2b6e | Preserve the existing conversation, bot creation, group, routine, coding and return designs. Refine the named frames below in place; add HC17 for the separate native provider. |
| Teamlink primary local census | Read-only observation of /Users/chriswong/.hermes/profiles/engineering/mmos/TEAMLINK_CENSUS.md, dated 9 November, forensic window 00:08–00:30 MST; census cites Mastermind source 2f3deba2 | Same-host Hermes Bot Mode DM was observed through queue/ack/execution. Cross-host registration and the Hermes-to-T3 OAuth roundtrip were not established by this census. The twelve-person design roster is illustrative, not the fourteen-profile census or production membership. |
| Teamlink handoff contract | Read-only observation of the same directory's T3_HANDOFF_V2.md, Section 8, on 9 November UTC | TeamLinkMessage.v1 retains operation correlation, idempotency, informational/actionable distinction and hop limits. ContextPacket.v1 contains references with expiry. Compose existing Executive/decision-ledger and T3 MCP transport, without adding a bus. |
| Teamlink refresh | A bounded later check found TEAMLINK_DESIGN.md absent at that exact engineering directory | No adapter-completion or installed return-path claim was inferred from the missing file. Existing observed contracts and explicit capability gates define the design. |

These are exact source/observation boundaries. Branch-head source is not a merge receipt, and a local census is not proof of a later installed generation. The current design uses example labels and keeps implementation validation separate.

### 15.2 Product composition and visual decisions

The existing Noir Atelier identity remains: near-black surfaces, ivory text, restrained champagne emphasis, fine neutral separators and consistent typography. No colored container-edge accents were introduced.

The main Team view was recomposed from twelve equal cards into a scanable roster and a selected teammate inspector. The roster answers who needs input, what each teammate is doing and where to continue. The inspector joins the selected Hermes teammate, project, original conversation, coding session and model route. The page's strongest action is Give direction; the inspector's Open conversation is secondary. Maintenance, the existing Meta-CEO office and project navigation remain reachable.

Today now shares the Team/Code/Resources navigation and makes its composer recipient explicit. It retains the Terminal brief review and projects, and adds a compact team-work entry that leads back to the original conversation. Search remains visible. The former Today navigation is preserved as a reference before replacement.

Capacity is now a purposeful Resources view: one physical allowance per row, independent five-hour/weekly/monthly observations, a concrete limiting allowance, provider reset evidence, consumers and route preview. The old hosts/maintenance content was copied to its named detail reference before recomposition. No percentage was created by adding or averaging different account allowances.

Conversation, coding and return designs use the same Teamlink adapter example and the same OS launch team destination. Explicit recipients, shared visibility and next-turn intent replace an ambiguous send action. Result delivery remains distinct from review, merge, deployment and overall project acceptance. New-bot controls in the primary room and returned-result view are secondary to the conversation action.

The desktop settings retain the DSH-backed ACP path. A separate native Capacity Fabric provider screen explains the alternative T3 engine, exact-model versus automatic policy selection, and the fact that new defaults apply to new threads. Existing threads retain their own route.

### 15.3 Exact frame map

All IDs below are native editable Paper nodes in file 01M3NRCX55B452A12819WNE1RH. Six focused boards were added, sixteen existing boards were refined, and two prior surfaces were preserved as references.

| Page | Frame / native ID | Result |
|---|---|---|
| [Start here](https://app.paper.design/file/01M3NRCX55B452A12819WNE1RH/p-1-0) | Design map A2Q-0 | Current page links, 13 Team & Delivery product frames, Teamlink/state/build descriptions and example-data notice. |
| [Canonical Atelier](https://app.paper.design/file/01M3NRCX55B452A12819WNE1RH/p-D-0) | Today LNV-0; narrow Today N27-0 | Unified primary navigation, explicit Mastermind CEO recipient, retained brief review and projects, linked team activity. |
| [Team & Delivery product](https://app.paper.design/file/01M3NRCX55B452A12819WNE1RH/p-O-0) | TD01 ZQN-0 | Roster plus Engineering inspector; Needs you / Working / Ready vocabulary and one page-primary action. |
| Same product page | TD05 10WB-0 | Capacity Fabric shared pools, independent allowance windows, unknown observations, concrete limit and reset, consumer examples and detail navigation. |
| Same product page | TD06 117C-0 | Exact source/return context, proposed host, T3 workspace, DSH ACP engine, exact GLM 5.3 model and account route; preview remains non-admitting. |
| Same product page | TD08 11ZB-0; TD10 128B-0 | Rebuilt narrow Team layouts in English dark and Chinese light, with touch-sized tabs/actions and a deliberate information order. |
| Same product page | TD09 123Z-0 | Narrow Code with Conversation / Changes / Tools, route, next-turn composer, separate Stop turn, changes/checks and original return destination. |
| Same product page | **New TD11 18LP-0** | Narrow Capacity: limiting-window overview and access to all allowance details. |
| Same product page | **New TD12 193T-0** | Narrow allowance detail: all three windows, independent resets, observation/expiry and evidence entry. |
| Same product page | **New TD13 19EJ-0** | Narrow teammate detail: Engineering mission, persistent conversation, coding session and exact model route. |
| [Team conversations product](https://app.paper.design/file/01M3NRCX55B452A12819WNE1RH/p-R-0) | HC01 12UW-0 | Teamlink linked coding card; message-delivered versus session-working states; explicit next-turn recipient and shared visibility. |
| Same conversation page | HC07 14MJ-0 | Engine/model/provider separation, current-turn versus next-turn behavior, exact session/original-room links and return-pending state. Existing changes/browser/terminal/worktree tools remain. |
| Same conversation page | HC08 14V7-0 | Returned result with original conversation, source/checks/review/release separation, aligned role/status labels and explicit room-message destination. |
| Same conversation page | HC11 15QF-0 | Existing DSH provider settings retained; Capacity Fabric is discoverable as another provider path. |
| Same conversation page | HC14 16CD-0; HC15 16FT-0 | English dark / Chinese light narrow rooms with linked handoff, explicit recipient/next-turn semantics and 44px controls. |
| Same conversation page | **New HC17 18ZE-0** | Native T3 Capacity Fabric provider, automatic Balanced policy, exact-model explanation and existing-thread route retention. |
| [Team & Delivery build](https://app.paper.design/file/01M3NRCX55B452A12819WNE1RH/p-Q-0) | TB01 12DE-0 | Reconciled owner boundaries, Teamlink transport composition and two distinct coding paths. |
| Same build page | **New TB03 18IB-0** | Motion, focus/draft/scroll continuity, responsive composition, render targets and required implementation proof. |
| [Team & Delivery states](https://app.paper.design/file/01M3NRCX55B452A12819WNE1RH/p-P-0) | **New TS02 18JN-0** | Sending, delivered, queued-next, uncertain delivery, capacity wait, starting, working, stopping, return-pending, returned and reconnect states. |
| Same states page | Preserved TD05H 1815-0 | Original hosts/maintenance detail retained before the Capacity redesign. |
| [Noir reference/history](https://app.paper.design/file/01M3NRCX55B452A12819WNE1RH/p-2-0) | Preserved navigation 195I-0 | Original Today navigation, native children retained before shell replacement. |

Final page readback: p-O-0 has 13 product boards; p-R-0 has 17 product boards; p-Q-0 has three build boards; p-P-0 has two state boards plus the preserved host-detail reference. Counts describe those pages, not new boards created by this continuation. Other accepted creation/routine/project/build designs were retained.

### 15.4 Integration contracts for implementation

**Hermes and company continuity.** A teammate is a persistent profile/session identity. Its conversation and project survive a coding delegation. The roster derives from authenticated membership; the example count of twelve must never become a product limit, filter or live-read fallback.

**Teamlink.** The composer declares recipient, visibility and intent. Informational room messages do not silently become actionable assignments. The explicitly selected Next turn action queues a continuation; steering, restart and stop remain distinct capability-gated actions (see the current send-mode correction in Section 17). Delivery, acknowledgement, execution and return have different evidence and states. Uncertain delivery retains the original operation and offers status reconciliation; reconnect does not resend or launch another attempt. Context is reference-based and expiry-aware, with the original project/conversation carried through the return path.

At the observed census, T3 MCP challenged with OAuth and exposed read/operate scope; an authenticated Hermes-to-T3 roundtrip had not been executed. Result return was pull-based through existing T3 reads/wait behavior, without proven push delivery into Hermes. The designed return experience must be implemented through supported existing owners and qualified with a real original-parent receipt. It is not a claim that a new push adapter already exists. Cross-host routes stay unavailable until their actual registration/auth/capability proof exists.

**Capacity Fabric.** Keep account identity, physical/shared allowance identity, model and execution host separate. Five-hour, weekly and monthly windows have their own evidence, reset and freshness. Missing/stale/future/unqualified usage stays null, with no empty progress bar implying zero remaining. An exhausted observed window is an actual zero. Admission requires headroom in every window required for that provider/plan, together with the existing permission, budget and reservation gates. At the pinned source, GLM/MiniMax require five-hour and weekly; Go also requires monthly. The example GLM monthly unknown is not a fabricated exhaustion or a universal third-window requirement.

An exact-model request may be pooled across eligible accounts without substituting another model. An automatic policy such as Balanced can resolve a model through the router's policy; the UI must display the resolved model when known. Do not silently equate the two. Native T3, Hermes and DSH consumer labels are illustrative until qualified runtime receipts establish their actual state. Showing a provider or registered consumer is not RESULT_PROVEN.

**Two T3 paths.** The native T3 Capacity Fabric provider is a direct provider/router path. The existing company-admitted DSH path is T3 plus DSH through ACP with its owner-fenced admission, launch and return contract. Section 7's single T3-to-DSH launch rule applies to the latter path only. It must not be used to route every native provider thread through DSH or to install another router. Refusal or unknown effects keep the original operation; neither path is a replay fallback for the other.

**Return and acceptance.** The result view links the original thread, changed files, checks and project outcome. Returned means the result reached the identified destination with evidence; it does not imply human/project acceptance, GitHub approval, merge or deployment. A partial team result leaves the parent outcome open.

The earlier implementation packet sequence remains a proposed future execution sequence. GLM-00 must add current Teamlink/auth/transport and native-versus-DSH capability reconciliation; GLM-03/04 must preserve both coding paths; GLM-05 uses the existing authenticated Resources projection; GLM-06 must prove the original-parent return and relevant negative cases. No packet was started by this continuation.

### 15.5 Responsive and performance design

Narrow layouts were recomposed at 390×844 rather than scaled from desktop. Team opens a teammate detail, Code separates Conversation/Changes/Tools, and Capacity shows the limiting window first with a dedicated full-allowance detail. English dark and representative Chinese light counterparts were visually checked. This is not a claim that every legacy board has been fully translated or every intermediate breakpoint implemented.

The new/refined narrow tabs and primary controls use 44px hit areas. Long names, IME composition, keyboard focus, focus return, reduced motion and scroll restoration remain implementation acceptance requirements.

TB03 records 160ms state transitions and 200ms reveals, with reduced motion removing travel. Draft, cursor, selection, filter, scroll and focus survive navigation and reconnect. Incoming updates do not steal focus or jump the conversation away from the reader. Loading and live updates keep layout stable.

Proposed runtime targets are local input feedback at or below 100ms p95 and a warm detail reveal at or below 200ms p95. These are design budgets, not measured performance results. Verify cold/warm navigation, typing while streaming, long histories, reconnect and reduced-motion behavior on actual target devices. Reuse current cache/subscriptions and virtualize long lists when justified; do not add a second observer, queue or polling service to make the design appear live.

### 15.6 Verification, receipts and closure

The direct approved Paper carrier was used throughout. Each mutation refreshed the exact file binding/snapshot before the write, used a stable operation ID and received APPLIED_RESPONSE_OBSERVED. The continuation contains 183 confirmed design mutations plus one confirmed finish acknowledgement; operation prefix is mmos-os-design-20261109-c4. First operation: capacity-names-01. Final design operation: return-destination-19. Finish operation: mmos-os-design-20261109-c4-finish-20, acknowledged OK on 9 November 2026 UTC.

Visual review covered the primary desktop journey, all six new boards and representative narrow/light/Chinese counterparts. Final passes checked Team, Capacity, Today, returned result, mobile Team/Code/Capacity, explicit recipient controls, 44px touch updates, text fit and neutral edge treatment. Native JSX/node/page reads confirmed editable structure, the final frame map and both preserved references. The final returned-result composer is native node 19JX-0 under HC08, with visible destination/visibility and retained reply controls.

Paper's screenshot renderer intermittently omitted inherited shell content immediately after edits; original-node/JSX reads and subsequent serial captures reconciled the view. Confirmed writes were not replayed on that basis. Two read-argument/node lookup errors were corrected as read-only schema/target diagnosis; they produced no mutation. There is no unresolved effect for this continuation. Historical Knowledge-only uncertain effects were outside the scope and left untouched.

Working indicators were released only for the 24 authored/refined/preserved target boards listed above. Existing users/writers and unrelated pages were not displaced. A bounded reasoning advisor's semantic findings were consumed; its role did not constitute GitHub APPROVED or a new review gate.

The final source update stays in PR #2345 on sol/t3-hermes-os-team-design-20261108-c3, with exact content/commit readback. The PR remains an open design/documentation carrier. Prior GitHub release restrictions are not waived, and no denied control read was repeated through another carrier.

**DO_NOT_REDO:** the six added boards, refined primary journey, retained references and accepted visual fixes. Reopen them only for a material source/product change or concrete feedback. The current design-only DONE_WHEN is met. Broader application, installed Teamlink return, consumer qualification, performance measurements and release acceptance remain with the incumbent implementation programme and its original proof requirements.

## 16. Expanded T3 donor integration — commissioned scope

> Completion amendment: the design ruler below is satisfied by Section 18. This section preserves the expanded assignment and its original acceptance.

Chairman continuation, 9 November 2026 (America/Vancouver): study T3's actual UI, backend, settings and open-source implementation, then design the complete T3 workspace living inside Mastermind OS. This combines Mastermind OS, Hermes and T3 into one product. The earlier Section 15 design result is accepted prior work, not completion of this newly expanded scope.

**Allowed surfaces:** the existing Mastermind OS Paper file and this existing source design guide/PR. Read-only donor/source and installed-version inspection are included. No app/runtime integration, installation, service changes, execution, merge or deployment is assigned in this continuation.

**Source pins:** T3 upstream pingdotgg/t3code c6ca6056309904f89b90b6055d797973be0a0939; Hermes upstream NousResearch/hermes-agent 109fd8161a509db5a00942152ba48882e446e8b0. Protected procedure remains ff6d5ab67c3535056d69f603fac0d95c058baad8; product doctrine remains Macro 315efde9307bf8a3d241a7683432dfff92cd4a9e. The supplied twelve screenshots are product observations. A read-only Info.plist inspection reports installed T3 Code (Beta) 0.1.7; the clean engineering research clone is separately pinned at 0770446869d247a8b28c27d7ed93f47f8ff0c1e4. Neither is silently equated to the current upstream source.

### Expanded completion ruler

- A source-backed inventory covers all visible T3 settings families and the material workspace/engine capabilities, including donor distinctions absent from the screenshots.
- Native Paper shows a first-class Code inbox/workbench/new-thread flow, all eight surface families (Browser, Terminal, Files, Diff, Pull request, Linked pull requests, Device, Side chat), source/review/context/recovery work, and deliberate tablet/mobile composition.
- Unified settings preserve device, environment, project and teammate/profile scope, inheritance, exact credentials ownership, supported/unsupported controls and real donor feature distinctions.
- Hermes persistent Bot Chat, T3 coding threads, DSH/other ACP engines, Capacity Fabric model/account routing and Executive placement remain joined but distinct owners. No duplicate runtime, settings database, scheduler, credential store or router is proposed.
- Builder documentation maps donor source to the editable frames and existing Mastermind seams, with capability gates, adoption/licence boundaries, interaction/performance constraints and concrete future real-path acceptance.
- Every authored board is visually inspected and natively read back, current working indicators are released, and this existing guide is saved/read back. Research alone and a provider selector alone are not DONE_WHEN.

### Current design decisions grounded in source

The complete embedded workspace should reuse/adapt T3 client-runtime and its authenticated RPC/subscription boundary. MCP remains the agent/control interface; it is insufficient as the whole UI data layer. One Mastermind shell owns product navigation while T3 retains environment-scoped threads/runs/provider effects and Hermes retains profile/gateway conversation ownership.

Settings need a visible concrete scope, not a universal global form. Preserve T3 client preferences versus environment defaults/project overrides and Hermes connection/profile pinning. SnapShots means screen/window capture; code checkpoints/rewind are a different workflow. T3 environment load balancing is placement, not Capacity Fabric model/account routing. Company placement stays with the incumbent Executive/Fabric owner.

**Research roles:** principal retains all Paper/source mutation. Three bounded native reasoning advisors inspect T3 backend, Hermes ownership and T3 settings taxonomy. WHY NOT FABLE: source/architecture critique and design judgment only; no implementation labor or new runtime assignment. Findings are advisory evidence, not GitHub approval.

**Next safe phase:** complete the donor feature/settings map, author the Code and unified Settings pages, verify each meaningful design group, persist the exact native frame map here, and continue through final coverage audit.


## 17. Full donor study and first native workspace milestone — historical checkpoint

This section supersedes older census assumptions where named below. It is a saved/read-back milestone within Section 16, **not** completion of the expanded design commission. Principal remains the sole canvas/source writer; the three bounded reasoning advisors completed their source studies. No runtime work was launched.

### Answer-changing source findings

1. **Full embedding:** [T3 architecture](https://github.com/pingdotgg/t3code/blob/c6ca6056309904f89b90b6055d797973be0a0939/docs/internals/overview.md) assigns shared connection/domain state to packages/client-runtime and execution to the environment server. Reuse the authenticated typed RPC/subscription boundary for the full workspace; retain MCP for outside-agent operations. [Environment authentication](https://github.com/pingdotgg/t3code/blob/c6ca6056309904f89b90b6055d797973be0a0939/docs/internals/environment-auth.md) explicitly refuses mcp-client sessions on other HTTP/WebSocket paths. This is a donor composition design, not a claim that a public stable SDK or installed integration exists.
2. **Send modes:** [ThreadManagementService](https://github.com/pingdotgg/t3code/blob/c6ca6056309904f89b90b6055d797973be0a0939/apps/server/src/orchestration-v2/ThreadManagementService.ts), sendToThread, implements auto, queue, steer and restart. Auto can steer an active steerable run; explicit queue targets the next turn. Fresh-context input does not join the active turn. The UI exposes the intended action and renders actual started/queued/steered/restarted delivery. This replaces any universal “busy T3 sends always queue” interpretation of Section 15.
3. **Completion:** provider turn end, checkpoint/diff finalization, thread settlement and Mastermind objective acceptance remain different milestones. T3's existing receipt/event/projection and effect owners remain authoritative; viewer reconnect does not resubmit writes.
4. **Settings:** [scope resolver](https://github.com/pingdotgg/t3code/blob/c6ca6056309904f89b90b6055d797973be0a0939/apps/web/src/components/settings/settingsScope.ts) preserves stale/unavailable selections and never broadens them to All. All environments is an explicit set of connected, loaded targets. [project resolution](https://github.com/pingdotgg/t3code/blob/c6ca6056309904f89b90b6055d797973be0a0939/packages/shared/src/projectSettings.ts) applies project overrides, then only designated t3.json-backed settings when the effective value is null; it is not a universal three-level inheritance ladder.
5. **Reset correction:** [useSettingsRestore](https://github.com/pingdotgg/t3code/blob/c6ca6056309904f89b90b6055d797973be0a0939/apps/web/src/components/settings/SettingsPanels.tsx) mixes client and server settings despite the donor's device-default wording. Mastermind separates Reset this device, Reset selected environment settings and Remove project override, with target/impact review and per-target outcomes.
6. **Capture:** [SnapShots](https://github.com/pingdotgg/t3code/blob/c6ca6056309904f89b90b6055d797973be0a0939/docs/user/snap-shot.md) means native screen/window capture into the composer. It is separate from hidden-ref code checkpoints and provider conversation rollback.
7. **Portable history:** [portable handoffs](https://github.com/pingdotgg/t3code/blob/c6ca6056309904f89b90b6055d797973be0a0939/docs/user/portable-handoffs.md) and current ContextHandoffService select full messages within a token budget and retain references to omitted history. Older compact activity summaries are not a universal 240-character handoff format. Context transfer does not clone tool state, credentials, reasoning or execution authority.
8. **Persistent teammate:** [Hermes profiles](https://github.com/NousResearch/hermes-agent/blob/109fd8161a509db5a00942152ba48882e446e8b0/website/docs/user-guide/profiles.md), [Bot Mode](https://github.com/NousResearch/hermes-agent/blob/109fd8161a509db5a00942152ba48882e446e8b0/website/docs/user-guide/bot-mode.md) and [settings scope](https://github.com/NousResearch/hermes-agent/blob/109fd8161a509db5a00942152ba48882e446e8b0/apps/desktop/src/store/settings-scope.ts) keep profile-owned configuration/memory/skills/sessions/routines and pin the displayed profile in API requests. Persistent Bot Chat, ordinary Hermes sessions, Hermes ACP coding sessions and T3 threads are distinct objects with links.
9. **Placement and model routing:** T3's device-local environment preferences (Prefer/Normal/Less often/Manual only) do not create another company placement or Capacity Fabric model/account router. App helper consumers—titles, source-control writing, review guides, voice cleanup—retain separate supported model selections.

### Native frames already authored and visually inspected

| Frame | Native ID | Page | Visible workflow |
|---|---|---|---|
| CW01 · Code · Work inbox | 19K7-0 | p-U-0 | Work inbox, pinned/Needs you/Working/Settled, exact origin and selected-work inspector |
| CW02 · Code · Embedded workbench | 19VK-0 | p-U-0 | Embedded thread inbox, conversation, next-turn composer, docked terminal and browser |
| CW03 · Code · New thread and workspace | 1A6U-0 | p-U-0 | New/root/existing worktree, base branch, permission, runtime/model and original return destination |
| CW04 · Code · Files and changes | 1AGU-0 | p-U-0 | Files, turn/branch/commit changes, contextual comments, prompt context and checkpoint entry |
| CW05 · Code · Pull request inbox | 1ASS-0 | p-U-0 | Company PR inbox, filters, selected summary, checks/review and original thread |
| CW06 · Code · Pull request review | 1B49-0 | p-U-0 | PR code review, pending comments, viewed files, linked PRs and repository merge requirements |
| US01 · Settings · One searchable system | 1BFO-0 | p-V-0 | Unified settings taxonomy, control search and retained context |
| US02 · Settings · Projects and sessions | 1BR6-0 | p-V-0 | Project/environment/checkout scope, inherited/overridden session and workspace defaults |
| US03 · Settings · Runtimes and models | 1C3W-0 | p-V-0 | Environment-owned coding runtime, DSH ACP command, model catalog, Fabric route and app helpers |

Code page: [17 · Code workspace · Product](https://app.paper.design/file/01M3NRCX55B452A12819WNE1RH/p-U-0). Settings page: [18 · Unified settings · Product](https://app.paper.design/file/01M3NRCX55B452A12819WNE1RH/p-V-0). At this milestone, states/build pages p-W-0 and p-X-0 were reserved; their complete authored map and verification now appear in Section 18.

### Transport reconciliation

Operation mmos-t3-full-design-20261109-c4-cw06-clone lost its connection response. No automatic replay or cross-carrier Paper write occurred. Three successful full enumerations of the original p-U-0 page on the original Mastermind Paper carrier showed exactly the five acknowledged IDs (19K7-0, 19VK-0, 1A6U-0, 1AGU-0, 1ASS-0), with no unacknowledged clone. After connection recovery and explicit target-state reconciliation, the missing frame was created on that same carrier as 1B49-0 and visually checked. Read-only transport diagnosis changed no service, config, runtime, credentials or application state.

### Milestone design frontier — completed in Section 18

At this milestone, the next phase was to complete all eight tool surfaces and queue/steer/restart, native-session adoption, portable context/history and checkpoint states; complete all 22 T3 settings families plus Hermes teammate/capability/routine scope; add tablet/mobile views, operational/unsupported/partial-save states and source-to-frame build maps. Verify every resulting native board, reconcile the old directory/build links, save/read back final coverage, then release only owned working indicators. Continue in the same healthy turn.

## 18. Complete embedded T3 design — verified native Paper expansion

**Outcome: PROVEN_OUTCOME for the expanded design commission in Section 16.** The new 38-board package is authored in the existing Mastermind OS Paper file, visually inspected and natively enumerated. It builds on the accepted Today, Team, Capacity and conversation work in Section 15. This closes the design frontier recorded at the Section 17 milestone; application integration and real runtime/performance qualification remain unexecuted.

The product is one Mastermind OS shell with an embedded Code workspace, a persistent team and one searchable settings experience. This is a donor-integration design: reuse the depth and contracts of the open-source applications while preserving original Mastermind presentation and the incumbent owners of execution, identity, routing, credentials, scheduling and result delivery.

### 18.1 Navigation and native frame map

| Destination | Native page | Boards |
|---|---|---:|
| [Code workspace](https://app.paper.design/file/01M3NRCX55B452A12819WNE1RH/p-U-0) | `p-U-0` · 17 · Code workspace · Product | 14 |
| [Unified settings](https://app.paper.design/file/01M3NRCX55B452A12819WNE1RH/p-V-0) | `p-V-0` · 18 · Unified settings · Product | 17 |
| [Execution, settings and recovery states](https://app.paper.design/file/01M3NRCX55B452A12819WNE1RH/p-W-0) | `p-W-0` · 17A · Code workspace · States | 4 |
| [Integration and interaction contract](https://app.paper.design/file/01M3NRCX55B452A12819WNE1RH/p-X-0) | `p-X-0` · 17B · Code integration · Build | 3 |

The Start here directory `A2Q-0` retains its accepted content and now includes native entry `1MKF-0` for pages 17–18, all four destinations and Section 18 of this guide. Directory heading/footer text includes the new current pages. The Code and Settings product pages follow Team conversations in the page list. The new state/build pages sit with the existing current state/build pages; all 33 existing page/divider IDs were preserved exactly once.

Desktop boards are 1600×1040. CW11 is 768×1024. CW12, CW13 and US14 are 390×844. The mobile work is deliberately composed for a single focused task; CW13 is Chinese/light and CW12 is English/dark. The accepted Noir Atelier tokens, neutral borders, quiet status colors and selective champagne action accents remain the visual system.


#### Code workspace

Page: [p-U-0](https://app.paper.design/file/01M3NRCX55B452A12819WNE1RH/p-U-0).

| Frame | Native ID | Designed workflow |
|---|---|---|
| CW01 · Work inbox | `19K7-0` | Work inbox; Pinned, Needs you, Working and Settled; selected work, environment and original conversation. |
| CW02 · Embedded workbench | `19VK-0` | Embedded thread list, conversation, Next-turn composer, retained terminal and browser preview. |
| CW03 · New thread and workspace | `1A6U-0` | Project and environment; new/existing/root workspace; base branch and remote start; permission, runtime/model and return destination. |
| CW04 · Files and changes | `1AGU-0` | File tree; Turn/Branch/Commits changes; inline review context; checkpoint entry and PR continuation. |
| CW05 · Pull request inbox | `1ASS-0` | Company pull-request inbox; search/filter/sort, host/repository identity, checks, review and originating thread. |
| CW06 · Pull request review | `1B49-0` | Pull-request review; Summary/Code/Activity/Guide navigation, viewed files, draft comments, checks and release controls. |
| CW07 · Surfaces and device preview | `1CFT-0` | Eight-surface chooser and device preview; viewer attachment separate from agent control and paid/device readiness. |
| CW08 · Queue, steer and side chat | `1CRG-0` | Pending approval with child attribution; queue edit/hold/remove; explicit Queue/Steer/Restart; stop and side chat. |
| CW09 · Adopt a native session | `1EV1-0` | Environment/provider-scoped native-session discovery/adoption; already imported opens existing thread; mismatched project retained visibly. |
| CW10 · Context and history | `1F4U-0` | Selected full-message context; configurable history budget, estimated tokens and source references; new provider session with source workspace retained. |
| CW11 · Tablet focused surface | `1IQU-0` | 768×1024 tablet; focused Browser surface with originating thread, draft and queue preserved. |
| CW12 · Mobile workbench EN | `1IVC-0` | 390×844 English dark mobile; workbench, active work, contextual tools and deliberate sticky composer. |
| CW13 · Mobile inbox ZH light | `1J4C-0` | 390×844 Chinese light mobile; Code inbox, work states and selected destination. |
| CW14 · Linked PRs and stacks | `1KJ0-0` | Linked pull requests versus ordered stack; relationship provenance, dismissed links, per-PR checks/review/hold and selected action environment. |

#### Unified settings

Page: [p-V-0](https://app.paper.design/file/01M3NRCX55B452A12819WNE1RH/p-V-0).

| Frame | Native ID | Designed workflow |
|---|---|---|
| US01 · One searchable system | `1BFO-0` | One searchable settings system, grouped by Personal/Code/Team/System, with return to the retained workspace. |
| US02 · Projects and sessions | `1BR6-0` | Concrete project/environment/checkout scope; sessions and worktrees; inherited versus overridden values and project actions. |
| US03 · Runtimes and models | `1C3W-0` | Provider driver/instance and runtime/model separation; DeepSeek harness ACP command and arguments, native Fabric route and helper entry. |
| US04 · Persistent teammate | `1D2L-0` | Persistent Hermes Engineering profile on Ubuntu 1; role, instructions, working folder, model, approval and distinct memory/context. |
| US05 · Capabilities and connectors | `1DEW-0` | Skills, plugins, connectors and toolsets; installed, enabled, authenticated and tool-permitted states remain distinct. |
| US06 · Environments and access | `1DQW-0` | Environment connections, exact grants, device placement preference, company placement and linked team gateway readiness. |
| US07 · Source control and review | `1E2O-0` | Version-control and forge accounts; project merge/writing defaults; device review preferences; actual repository requirements. |
| US08 · Routines and run history | `1FJX-0` | Unified projection of owned routines; Code and Hermes examples; schedule/timezone, target, prompt/model, webhook deliveries and run history. |
| US09 · Conversation and voice | `1FW2-0` | Notifications, grouping, chat/send behavior and voice; microphone, language, personal/project dictionary and cleanup. |
| US10 · Appearance and capture | `1G8M-0` | Appearance, keyboard/focus and native SnapShots capture; separate system permissions and capture versus code checkpoint. |
| US11 · Browser and devices | `1GL6-0` | Browser profiles/preferences/data/access; device sources, agent access, readiness and cloud lease prerequisites. |
| US12 · Secrets and privacy | `1GX9-0` | Environment-owned secrets and references; dependency impact; privacy and credential-owner boundaries. |
| US13 · Maintenance and cleanup | `1HMN-0` | Maintenance and diagnostics; cleanup preview; active/shared work retained; per-target outcomes. |
| US14 · Mobile scope and recovery | `1J2C-0` | 390×844 mobile scoped settings; offline target stays selected, draft preserved and reconnect action. |
| US15 · Archive and restoration | `1HYM-0` | Archive, read-only history and restore; explicit delete impact; archive distinct from Settled. |
| US16 · About and experiments | `1I96-0` | About, installed version/update channel/CLI/mobile/privacy/notices; Labs with supported, unavailable and prerequisite states. |
| US17 · Accounts and app helpers | `1J6D-0` | Provider authentication and sign-out impact on shared credentials; distinct title/writing/review-guide/voice helper consumers. |

#### Recovery and states

Page: [p-W-0](https://app.paper.design/file/01M3NRCX55B452A12819WNE1RH/p-W-0).

| Frame | Native ID | Designed workflow |
|---|---|---|
| CS01 · Execution and return | `1JO4-0` | Preparation, queue, limited capacity with unknown reset, expired approval, uncertain send and provider-finished/changes-preparing states. |
| CS02 · Scope, saves and resets | `1JXD-0` | Mixed values, partial save, unavailable selection, read-only grants, device reset and removing a project override. |
| CS03 · Setup and capability limits | `1K6T-0` | Expired auth, unavailable catalog, unsupported steering, signed-in connector without tools, unsupported surface and Teamlink setup. |
| CS04 · History and consequential actions | `1KFX-0` | Checkpoint/rollback limits, competing writer, already imported native session, unavailable device quote, environment reset and lifecycle distinctions. |

#### Build contract

Page: [p-X-0](https://app.paper.design/file/01M3NRCX55B452A12819WNE1RH/p-X-0).

| Frame | Native ID | Designed workflow |
|---|---|---|
| CB01 · Full donor composition | `1LSJ-0` | Existing-owner composition and the authenticated T3 UI boundary; Hermes, Teamlink, Executive, Capacity Fabric, DSH/ACP and GitHub. |
| CB02 · Interaction and responsiveness | `1M0G-0` | Interaction targets, retained state, responsive behavior, keyboard/accessibility and explicit future performance proof. |
| CB03 · Source and consumer acceptance | `1M93-0` | Donor pins, installed/research-clone distinction, licence/adoption boundary and seven-step future consumer acceptance. |

### 18.2 Every T3 surface has a place inside Code

| T3 surface | Mastermind location | Integration contract |
|---|---|---|
| Browser | CW02, CW07, CW11; US11 | Preserve environment, thread, browser profile, runtime/preview URL and viewport. Settings presentation and agent access have separate scopes. Unsupported devices retain the thread and explain the unavailable action. |
| Terminal | CW02; surface chooser CW07 | Attach to the existing server PTY and retained output. Reveal/attach, restart, close and terminate are different actions. Navigation never creates a replacement terminal implicitly. |
| Files | CW04; chooser CW07 | Read the exact environment/workspace. File selection, prompt attachments/context and local changes retain their project/thread association. |
| Diff | CW04, CW06; US07 | Keep Turn, Branch and Commits context, file navigation, viewed state and comment drafts. Hidden-ref checkpoints are not user commits. |
| Pull request | CW05, CW06 | Search and review the actual host/repository/number. Checks, required review, merge permission and release holds come from the existing forge. |
| Linked pull requests | CW14; entry CW06 | Related PR collection is distinct from an ordered stack. Preserve relationship source, dismissed links, stack layer and per-PR checks/holds. Selected action and trusted execution environment stay explicit. |
| Device | CW07; US11 | Distinguish viewing a device from granting agent control. Keep source/lease identity; unsupported sources and unavailable quotes remain useful states. Paid launch needs the actual applicable quote/authorization flow. |
| Side chat | CW08; chooser CW07 | Retain the parent thread and attached context while a secondary conversation is open. A side chat does not silently change runtime, approvals or original return destination. |

Source: [surface taxonomy](https://github.com/pingdotgg/t3code/blob/c6ca6056309904f89b90b6055d797973be0a0939/apps/web/src/components/RightPanelTabs.tsx), [panel layout](https://github.com/pingdotgg/t3code/blob/c6ca6056309904f89b90b6055d797973be0a0939/apps/web/src/rightPanelLayout.ts), [terminal ownership](https://github.com/pingdotgg/t3code/blob/c6ca6056309904f89b90b6055d797973be0a0939/docs/internals/terminal-runtime.md), [preview contract](https://github.com/pingdotgg/t3code/blob/c6ca6056309904f89b90b6055d797973be0a0939/packages/contracts/src/preview.ts), [device ownership](https://github.com/pingdotgg/t3code/blob/c6ca6056309904f89b90b6055d797973be0a0939/docs/internals/devices.md) and [PR relationships](https://github.com/pingdotgg/t3code/blob/c6ca6056309904f89b90b6055d797973be0a0939/packages/contracts/src/threadPullRequest.ts). The upstream narrow-panel behavior informs the focused-pane composition; the 1600/768/390 designs are the proposed Mastermind responsive contract, not measured application behavior.

### 18.3 Complete T3 settings-family reconciliation

The pinned donor navigation/search taxonomy contains **22 settings families**, including Voice, SnapShots, Secrets and Archive that are easy to omit when working only from the supplied screenshots. Every family is mapped below. This is comprehensive Paper design and integration-contract coverage with retained donor detail contracts; it does not mean every nested dialog has been independently redrawn. Unified navigation groups them for the user; it does not collapse their different save scopes or discard their detail dialogs. US04–05 add persistent Hermes profile/capability controls, and US14 shows scope recovery on mobile.

| Donor family | Native designs | Controls and retained detail | Scope / owner |
|---|---|---|---|
| General | US09 | Notifications; in-app alerts; repository grouping and order; Working section; confirmations, quit behavior and time preferences. | Device/client |
| Appearance | US10 | Theme/contrast; UI, chat and code fonts/sizes; chat width; math/wrapping; effort visibility, motion and environment identification. | Device/client |
| Chat | US09, CW08 | Rich text, send behavior, slash/skill affordances, follow-up delivery mode and tool visibility; approvals/errors remain visible. | Client preferences plus capability-qualified thread actions |
| Diffs & pull requests | US07, CW04–06 | Diff palette, whitespace, expansion and stacked/split views; proactive in-app PR experience and retained review drafts. | Device review preferences; PR/repository state stays with its owner |
| Keybindings | US10 | Rebind supported actions; visible focus; composer IME safety; command palette and pane traversal. | Device/client |
| Voice | US09, US17 | Microphone/dictation language; personal and project dictionaries; cleanup consumer; model download, test, hardware and unload states. | Device microphone/model; project dictionary and supported helper owner |
| SnapShots | US10 | Window/screen capture to composer; screen-recording and accessibility permissions; shortcut, flash, sound and animation. | Native device permissions and preferences; separate from code checkpoints |
| Providers | US03, US17, CW09 | Manifest/driver, instance, executable/args/env references, health/version, auth, dynamic catalog, custom/favorite models, native session adoption and helpers. | One execution environment; provider-management grants checked separately |
| Threads | US02, CW01/03/08/10 | Default runtime/permission/workspace; streaming/title, snooze/resume/settlement, starting folder/clone and idle-compaction behaviors. | Environment defaults with supported project overrides; existing thread lifecycle |
| Browser | US11, CW02/07/11 | Profiles, import/data reset, viewport/zoom/theme/FPS, input visualization, link/search/floating behavior and agent browser access. | Client presentation versus environment/project access and native profile owner |
| Devices | US11, CW07 | Local simulator, SSH, EAS and Simlock sources; readiness, view/control distinction and lease/quote requirements. | Execution environment and source capability; no implied universal desktop availability |
| Scheduled tasks | US08 | Create/edit, pause/delete/run-now, time/timezone, target, prompt/runtime/model, webhook filter/delivery and run history. | Existing T3 scheduler or Hermes cron owner, shown explicitly |
| Projects | US02 | Name/icon/pin/archive, concrete checkouts, actions/scripts and inherited or overridden defaults. | Exact project/environment/checkout |
| Source control | US07, CW05/06/14 | VCS/forge CLI/account health; auto-pull and merge method; writing instructions/templates; helper and review-guide selections. | Owning environment/account and project; actual forge requirements remain binding |
| Worktrees | US02, US13, CW03 | Folder, start-from-remote, submodules, branch naming, cleanup and retention of local changes. | Existing environment worktree owner; shared/live writers remain protected |
| Environments | US06 | Local/linked peers, connection routes, diagnostics, placement preferences and PR action routing. | Connection/auth owner; placement preferences are client-local |
| Sharing & access | US06, CS02/03 | LAN/Tailscale/WSL and supported relay/tunnel routes; pairing, authorized clients/revocation, webhook/guest-link/published-activity access. | Exact environment grants and observed connection readiness |
| Secrets | US12 | Feature-gated named references, providers/consumers, dependencies and impact of removal. | One selected environment and existing credential owner |
| Maintenance | US13 | Provider updates, background continuation/activity, storage/cleanup with partial results, diagnostics and telemetry/export controls. | Concrete environment/client owner per operation |
| Labs | US16 | Alternate inbox, guest links, linked-environment suggestions, extra-request actions, Simlock and fast Mac worktree options. | Installed-build and environment capability gates; experiments are not promises |
| About | US16 | Installed version, update track, CLI command, mobile entry, privacy and open-source notices. | Existing updater/installation owner and device |
| Archive | US15 | Archived project/thread inventory, read-only history, restore and explicit delete impact. | Existing project/thread owner; separate from working/settled state |

Taxonomy evidence: [settings search inventory](https://github.com/pingdotgg/t3code/blob/c6ca6056309904f89b90b6055d797973be0a0939/apps/web/src/components/settings/settingsSearch.ts) and [settings navigation](https://github.com/pingdotgg/t3code/blob/c6ca6056309904f89b90b6055d797973be0a0939/apps/web/src/components/settings/SettingsSidebarNav.tsx). Aliases such as Integrations → Browser, Storage → Maintenance and Beta → Labs should resolve through this same search/navigation model. Diagnostics and open-source-licence details remain reachable within Maintenance/About. T3 Connect is an account/connection footer capability, not a twenty-third family or a replacement Mastermind human identity.

The concrete donor panels remain the control inventory for implementation: [settings components](https://github.com/pingdotgg/t3code/blob/c6ca6056309904f89b90b6055d797973be0a0939/apps/web/src/components/settings). Preserve provider manifests, environment capabilities and upstream visibility gates when building controls, rather than treating fixture model names, device sources or experiment states in these boards as an available live catalog.

### 18.4 Settings scope, save and reset rules

1. **Retain the concrete owner.** T3 client preferences stay on the device; environment settings stay with the selected execution environment; supported project overrides stay with the exact project/checkout; Hermes settings stay pinned to the displayed connection and profile. UI labels and API keys must agree.
2. **Keep unavailable selections.** An offline environment, missing checkout or removed project stays visibly selected with its last known identity. It must never silently become All projects or All environments. The mobile example US14 retains the draft and reconnects to that owner.
3. **All is a bounded target set.** All environments means the explicitly connected and loaded targets selected for that operation. It does not promise future/offline synchronization. Mixed values remain mixed until the user changes them. Show successful and failed targets separately after a partial save.
4. **Inheritance is specific to each setting.** Preserve project overrides and the donor's designated t3.json-backed fallback when the effective value is null. Do not invent a universal environment → project file → project ladder for every setting. Remove override means inherit again, not write a duplicate default.
5. **Management access is distinct.** Provider installation/update/auth and secret management can require grants different from ordinary settings writes or thread use. Disable the exact operation with the reason; do not turn a provider capability into a generic Full access toggle.
6. **Reset by owner.** Reset this device, Reset selected environment settings and Remove project override are distinct actions with separate target/impact review. The donor's broad restore helper is not imported behind a misleading device-only label.
7. **Keep credentials at their existing owner.** US17 shows provider-confirmed sign-in status and shared native-account impact before sign-out. US12 uses references and dependency impact. No new Mastermind secret copy or universal credential is proposed.
8. **Preserve the working thread.** Opening settings, changing tabs or closing settings retains the thread, draft, cursor/focus, scroll, queue and selected tool. An owner change invalidates only owner-bound data and pending actions; it never carries credentials or stale grants to the new target.

Source: [scope resolver](https://github.com/pingdotgg/t3code/blob/c6ca6056309904f89b90b6055d797973be0a0939/apps/web/src/components/settings/settingsScope.ts), [scoped settings](https://github.com/pingdotgg/t3code/blob/c6ca6056309904f89b90b6055d797973be0a0939/apps/web/src/components/settings/useScopedSettings.ts), [project inheritance](https://github.com/pingdotgg/t3code/blob/c6ca6056309904f89b90b6055d797973be0a0939/packages/shared/src/projectSettings.ts), [restore helper](https://github.com/pingdotgg/t3code/blob/c6ca6056309904f89b90b6055d797973be0a0939/apps/web/src/components/settings/SettingsPanels.tsx), [Hermes profile pinning](https://github.com/NousResearch/hermes-agent/blob/109fd8161a509db5a00942152ba48882e446e8b0/apps/desktop/src/store/settings-scope.ts) and [retained chat route](https://github.com/pingdotgg/t3code/blob/c6ca6056309904f89b90b6055d797973be0a0939/apps/web/src/routes/_chat.tsx).

### 18.5 Donor composition and existing owners

| Responsibility | Existing owner to retain | Mastermind design integration |
|---|---|---|
| Product navigation and human identity | Mastermind OS | One shell, global navigation/search, company project/task context and original conversation links. |
| Full coding UI connection/domain state | T3 client-runtime with authenticated typed RPC/subscriptions | Reuse/adapt the donor client runtime and surface components in Code; retain connection, snapshot/event cursor and environment identity. |
| Files, Git, PTY, browser/device and provider instances | T3 execution environment and existing native owners | Bind every surface/action to the same environment/project/thread/workspace. Grouping repositories in the UI does not migrate execution. |
| Thread/run events, command receipts, effects and completion | Existing T3 orchestration | Project current state and reconcile existing receipts. No new run ledger, queue or replay engine. |
| Persistent teammate, Bot Chat, profile memory/skills/routines | Existing Hermes profile/gateway | Profile-pinned Team and settings views. A viewer does not start another gateway/runtime. |
| Company work admission and placement | Existing Executive authority | Join company tasks to admitted work; retain reservation, budget and execution binding. |
| Model/account selection and fallback | Existing Capacity Fabric | Display eligible routes, allowance and observed limits. Keep model routing distinct from T3's client-local environment placement preferences. |
| DSH or Hermes ACP coding engine | Existing provider/ACP adapter | Select and configure the supported runtime. T3 owns coding workspace/thread/checkpoint; provider owns its tools, skills and credentials. |
| Cross-application messages and result return | Existing Teamlink transport/envelope | Carry original room/message/task/thread/result references and return to the same parent. No second message bus or delivery identity. |
| Recurring work | Existing T3 scheduler or Hermes cron | One Routines UI with explicit owner and per-owner history; no new scheduler or duplicate watcher. |
| PR checks, review and release | Existing GitHub/forge | Inspect actual head and requirements; returned work, approved review, merge and parent acceptance remain different facts. |

**Full-UI auth boundary:** an outside-agent `mcp-client` subject accepted for `/mcp` is not a normal workspace HTTP/WebSocket login. Embedding the full workspace requires the donor's authenticated RPC/subscription path and its method grants. Project identity is organizational context, not a filesystem sandbox. Preserve existing environment/client trust and Mastermind human identity.

Source: [T3 architecture](https://github.com/pingdotgg/t3code/blob/c6ca6056309904f89b90b6055d797973be0a0939/docs/internals/overview.md), [client-runtime](https://github.com/pingdotgg/t3code/blob/c6ca6056309904f89b90b6055d797973be0a0939/packages/client-runtime), [typed RPC contract](https://github.com/pingdotgg/t3code/blob/c6ca6056309904f89b90b6055d797973be0a0939/packages/contracts/src/rpc.ts), [environment auth](https://github.com/pingdotgg/t3code/blob/c6ca6056309904f89b90b6055d797973be0a0939/docs/internals/environment-auth.md), [orchestration](https://github.com/pingdotgg/t3code/blob/c6ca6056309904f89b90b6055d797973be0a0939/apps/server/src/orchestration-v2), [T3 schedule owner](https://github.com/pingdotgg/t3code/blob/c6ca6056309904f89b90b6055d797973be0a0939/apps/server/src/scheduledTasks/ScheduledTaskService.ts) and [Hermes routine API](https://github.com/NousResearch/hermes-agent/blob/109fd8161a509db5a00942152ba48882e446e8b0/apps/desktop/src/api/cron.ts).

The existing Section 15 native Capacity Fabric provider and DSH/ACP paths remain separate. DSH's documented executable is `dsh`, with ordered arguments `--profile`, `acp`; the design does not invent a T3 launch daemon or replace provider-native tools. The previously pinned Mastermind Capacity/Teamlink source seams and exact source receipts in Sections 14–15 remain applicable; this upstream donor study does not overwrite them.

### 18.6 Runtime distinctions that affect the UI

**Send and intervention.** T3 supports auto/queue/steer/restart delivery; auto may steer when the runtime and state permit. CW08 names the requested action, separates Stop, allows editing/removing/holding queued input and reports the actual returned outcome. Steering can interrupt an active tool for some providers; attachment support and steering availability vary. Fresh context never silently joins the active turn. A rejected/expired approval must open the current request, not replay the old answer. Child requests remain attributable in the parent thread.

**Completion and receipts.** Sending, delivery, started/running, provider finished, checkpoint/diff finalization, returned result, review/merge and parent acceptance remain separate. A provider-finished state can still prepare changes. Reconnect restores the snapshot/event cursor and reconciles receipts; uncertainty is not permission to resend a command or duplicate a return message.

**Native adoption.** CW09 discovers sessions within the chosen environment/provider/workspace. Already imported sessions open the existing T3 thread; they do not launch another run. Validate the project again if selection changes between discovery and adoption. A provider's native-session identity remains distinct from the T3 thread ID.

**Portable context.** CW10 selects full messages within a configurable 1,024–64,000 token budget; 16,000 is the shown/default selection, and token counts are estimates. Omitted history retains source references. It starts a new provider session; it does not clone hidden reasoning, files, attachments, tool state, credentials, approvals or execution authority. The source workspace remains identified and accessible. This is not a universal short-summary format.

**Code checkpoints and rollback.** Inspect the target checkpoint/diff and the filesystem impact before restore. The checkpoint store uses hidden Git refs distinct from user commits. Provider conversation rollback is capability-dependent; an unsupported path is refused before filesystem effects, and an active/shared writer blocks the conflicting restore. Native SnapShots capture into the composer is a different workflow.

**PR relationships.** CW14 preserves host/repository/number, relationship source, selected stack layer, dismissed relationships and per-PR checks/review/release holds. Related links do not imply a stack or permission for a bulk action. A selected PR action uses its trusted execution/account route; stack-wide actions must explicitly choose their target layers.

Sources: [sendToThread and thread management](https://github.com/pingdotgg/t3code/blob/c6ca6056309904f89b90b6055d797973be0a0939/apps/server/src/orchestration-v2/ThreadManagementService.ts), [orchestration contract](https://github.com/pingdotgg/t3code/blob/c6ca6056309904f89b90b6055d797973be0a0939/packages/contracts/src/orchestrationV2.ts), [provider capability adapter](https://github.com/pingdotgg/t3code/blob/c6ca6056309904f89b90b6055d797973be0a0939/packages/provider-acp-registry/src/server/adapter.ts), [native session identity](https://github.com/pingdotgg/t3code/blob/c6ca6056309904f89b90b6055d797973be0a0939/packages/contracts/src/agentSessions.ts), [context handoff](https://github.com/pingdotgg/t3code/blob/c6ca6056309904f89b90b6055d797973be0a0939/apps/server/src/orchestration-v2/ContextHandoffService.ts), [portable handoff behavior](https://github.com/pingdotgg/t3code/blob/c6ca6056309904f89b90b6055d797973be0a0939/docs/user/portable-handoffs.md), [checkpoint store](https://github.com/pingdotgg/t3code/blob/c6ca6056309904f89b90b6055d797973be0a0939/apps/server/src/checkpointing/CheckpointStore.ts) and [linked PR contract](https://github.com/pingdotgg/t3code/blob/c6ca6056309904f89b90b6055d797973be0a0939/packages/contracts/src/threadPullRequest.ts).

### 18.7 Hermes persistent team and capability reconciliation

US04 pins Engineering to its existing Ubuntu 1 profile/connection. US06 names the linked team gateway separately from a selected coding environment such as M2 Studio. Installed profiles and gateway-served profiles are distinct; a connected gateway alone does not establish cross-host Teamlink readiness or an original-parent return.

The persistent Bot Chat, ordinary Hermes session, Hermes ACP coding session and T3 coding thread retain separate identities. Profile configuration owns instructions, authentication, memory, skills, sessions and routines. Memory is not the same as the active context window or Agent OS continuity. The UI must pin profile-sensitive requests to the displayed connection/profile and reject or reconcile ambiguous ownership.

Hide changes presentation; Pause affects execution; Archive preserves history; Delete has an explicit target and impact. Canonical Bot Chat compact/reset behavior is distinct from ordinary session reset and T3 thread settlement. Opening or closing a viewer does not create/stop the persistent teammate.

Capabilities includes Skills, Plugins, Connectors and Toolsets. Installed, enabled, authenticated, tool-discovered and permitted are independent states. A signed-in GitHub connector can have no available tools. Model controls distinguish main/fallback/auxiliary/delegation or supported aggregate modes. Hermes manual/smart/off, ACP ask/workspace_session/session and T3 permission modes must keep their own semantics; no lossy shared slider is proposed.

Group conversations retain per-member capability and failure state. Desktop relay and gateway peer routes have different lifetimes and prerequisites. Upstream source capability is not proof that the installed Teamlink route is qualified; CS03 retains that setup-required state.

Sources: [profiles](https://github.com/NousResearch/hermes-agent/blob/109fd8161a509db5a00942152ba48882e446e8b0/website/docs/user-guide/profiles.md), [persistent Bot Chat](https://github.com/NousResearch/hermes-agent/blob/109fd8161a509db5a00942152ba48882e446e8b0/website/docs/user-guide/bot-mode.md), [gateway sessions](https://github.com/NousResearch/hermes-agent/blob/109fd8161a509db5a00942152ba48882e446e8b0/website/docs/developer-guide/gateway-local-sessions.md), [ACP internals](https://github.com/NousResearch/hermes-agent/blob/109fd8161a509db5a00942152ba48882e446e8b0/website/docs/developer-guide/acp-internals.md), [profile settings](https://github.com/NousResearch/hermes-agent/blob/109fd8161a509db5a00942152ba48882e446e8b0/apps/desktop/src/plugins/hermes-bots/profile-config.tsx), [capabilities UI](https://github.com/NousResearch/hermes-agent/blob/109fd8161a509db5a00942152ba48882e446e8b0/apps/desktop/src/app/capabilities/index.tsx), [Hermes approval modes](https://github.com/NousResearch/hermes-agent/blob/109fd8161a509db5a00942152ba48882e446e8b0/apps/desktop/src/store/approval-mode.ts) and [ACP modes](https://github.com/NousResearch/hermes-agent/blob/109fd8161a509db5a00942152ba48882e446e8b0/acp_adapter/modes.py).

### 18.8 Designed negative states

| Board | Explicit variants | Required behavior |
|---|---|---|
| CS01 | Workspace preparation; next turn queued; capacity limited with reset unknown; expired approval; message status unknown; provider finished while changes prepare | Preserve the original target and distinguish actual lifecycle receipts. Do not fabricate availability, replay expired actions or promote a return to acceptance. |
| CS02 | Mixed values; partial save; unavailable checkout; read-only permission; reset this device; remove project override | Retain exact scope, report per-target outcomes and keep reset/inheritance operations distinct. |
| CS03 | Runtime auth expired; model catalog unavailable; steering unsupported; authorized connector without tools; unavailable device surface; Teamlink setup required | Preserve useful independent paths; no invented model list, full-access bypass, host substitution or assumed route readiness. |
| CS04 | Checkpoint/rollback inspection; competing live writer; native session already imported; cloud-device quote unavailable; environment reset; hide/pause/archive/delete | Explain concrete effect and owner, block conflicting/destructive effects appropriately and avoid duplicate execution. |

These 24 variants are native design studies. They do not claim the underlying error, recovery or action has been executed in the installed application.

### 18.9 Interaction, responsiveness and future proof

| Interaction | Proposed design target | Implementation proof owed |
|---|---|---|
| Typing and local feedback | At or below 100 ms p95 | Measure on the target device while the thread streams; keep typing and selection responsive during tool/event updates. |
| Warm thread/tool reveal | At or below 200 ms p95 | Reuse retained caches/subscriptions and measure warm navigation; report cold loading separately. |
| Panel transitions | Short opacity/transform transitions | Avoid width/height animation in the active path; respect reduced motion and interrupt transitions without losing state. |
| Settings open/close | Keep the coding thread mounted | Restore draft, cursor/focus, scroll, queue and tool selection. |
| Large histories and PR lists | Bound the rendered window | Preserve current donor pagination/virtualization, stable identity and scroll anchors. |
| Reconnect | Restore snapshot and event cursor | Reconcile command/message receipts before further effects; no automatic resend. |
| Target change | Invalidate owner-bound data | Key state by environment/thread or connection/profile; avoid stale forms, secrets and pending approvals. |
| Keyboard | Command palette, pane traversal, Escape and surface keys | Visible focus, safe IME composition/send and return focus after overlays. |
| Accessibility | 44 px primary touch controls; readable status text | Semantic labels/states, contrast, reduced motion and keyboard operation in the actual app. |
| Narrow layout | One focused pane with original thread attached | Preserve inactive pane state across desktop/tablet/mobile changes and soft keyboard appearance. |

These are design budgets and acceptance conditions, **not performance measurements or implementation claims**. Desktop can display conversation and tools together; tablet focuses one surface; mobile uses a single-column task and contextual controls. Do not shrink the entire desktop workbench into the phone viewport.

### 18.10 Concrete implementation acceptance path

The eventual implementation must prove the joined consumer journey with real data and applicable authorization:

1. Start from an existing Hermes teammate or team conversation. Retain exact profile, room, originating message and company project/task.
2. Admit the work through existing Executive authority and Capacity Fabric eligibility. Keep its execution binding and actual route/capacity evidence.
3. Enter the embedded Code workspace attached to the owning environment, project, thread, worktree and provider session. Open/close settings and switch surfaces without losing the draft or identity.
4. Exercise real files, retained terminal, browser/device where supported, a queued follow-up and a parent-visible approval. Observe the actual command outcome and reconcile a reconnect without duplicate work.
5. Review the actual resulting diff/PR at its exact head. Show checks, required review/release holds and linked/stack identity. Retain draft review state and source-control account routing.
6. Return one result through Teamlink to the original conversation, with original-parent receipt and source/PR evidence. Demonstrate lost-response reconciliation and avoid a duplicate message or substitute room.
7. Record the parent's actual acceptance or follow-up work separately from runtime completion, returned result, green checks and merge.

Also prove offline/partial settings saves, unavailable provider/model capabilities, expired approval, shared-worktree custody, reduced-motion and keyboard behavior. Measure cold and warm navigation, streaming plus typing, long histories and actual supported device surfaces. A Paper screenshot, service health check, green CI or delivered message alone cannot satisfy this future consumer acceptance.

### 18.11 Source, adoption and verification receipts

**Inputs.** Twelve Chairman-supplied T3 screenshots; read-only installed T3 Code (Beta) 0.1.7 observation; clean engineering research clone `0770446869d247a8b28c27d7ed93f47f8ff0c1e4`; pinned upstream T3 `c6ca6056309904f89b90b6055d797973be0a0939`; pinned upstream Hermes `109fd8161a509db5a00942152ba48882e446e8b0`; existing Mastermind procedure/product/source pins in Sections 15–16. The research clone is not proven to be the source of the installed binary. New upstream capabilities require installed-environment discovery before an enabled control is shown.

**Adoption.** Both examined donor repositories carry MIT licences: [T3 licence](https://github.com/pingdotgg/t3code/blob/c6ca6056309904f89b90b6055d797973be0a0939/LICENSE) and [Hermes licence](https://github.com/NousResearch/hermes-agent/blob/109fd8161a509db5a00942152ba48882e446e8b0/LICENSE). When implementation adopts code, retain required donor notices and dependency licences. Reuse capability and architecture with original Mastermind branding/presentation; no proprietary assets or unverified code provenance is imported by this design work.

**Visual verification.** Every one of the 38 new native boards was inspected at full screenshot scale by the principal or a bounded design/source advisor. The principal corrected actual text-fit issues in device/settings cards, a capability-state annotation, mobile light background, duplicate selector arrows and ambiguous control copy. Final readbacks verified the corrected US04 working-folder helper, explicit US09 personal-dictionary action and CS03 auth annotation. US17's complete provider setup card and helper Save action fit within the final frame. CW14 preserves link/stack distinctions; CW10 preserves estimated budget and source-workspace semantics. Advisory visual review is not GitHub approval or a new independent-review gate.

**Native census.** Final `get_basic_info` reads returned exactly 14, 17, 4 and 3 artboards on p-U-0, p-V-0, p-W-0 and p-X-0 respectively, with every ID in Section 18.1 matching. The current CW13 root is `1J4C-0`; its superseded intermediate root is not part of the design map. Page order was read back equal to the requested 33-ID order. Directory entry `1MKF-0` was visually inspected and its heading/footer text read back.

**Carrier reconciliation.** All final writes were confirmed on the original Mastermind Paper carrier with a fresh snapshot per mutation. The earlier CW06 lost response was reconciled as recorded in Section 17 before same-carrier creation; no unresolved Paper mutation remains. Slower state-board operations returned confirmed results and were not replayed.

**Working-indicator release.** Operation `mmos-t3-full-design-20261109-c4-finish-owned` targeted the 38 current new artboard IDs plus directory `A2Q-0` (39 owned targets). The original carrier returned `APPLIED_RESPONSE_OBSERVED` and `OK`. No unrelated working indicators were cleared.

**Durability and scope.** Native Paper is the editable design owner. This existing guide and PR #2345 remain the canonical source/build handoff; the owned Git diff remains the one design-guide path. Documentation self-check covers source/frame mappings, exact counts, conflict markers, whitespace and scoped claims. No app tests, runtime writes, provider calls, bot/scheduler launches, external messages, repository merge or deployment are part of this design result.

**Reassessment.** The expanded Section 16 design ruler is met: donor study, all eight surfaces, all 22 settings families, Hermes/Fabric/Teamlink/DSH reconciliation, responsive layouts, negative states, native visual/readback proof and owned-indicator release are complete. The next different deliverable is implementation and real consumer qualification against this contract; it is not silently claimed as completed by the Paper work.

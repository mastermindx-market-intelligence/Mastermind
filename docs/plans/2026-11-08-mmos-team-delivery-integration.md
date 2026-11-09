# Mastermind OS: Team, T3 Code, Hermes and Capacity Fabric integration

Date: 2026-11-08 (America/Vancouver); research and design session continued into 2026-11-09 UTC.
Operation: `t3-hermes-os-team-design-20261108-c3`.
Status: **architecture and Paper design package complete; application implementation and runtime activation pending**.

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

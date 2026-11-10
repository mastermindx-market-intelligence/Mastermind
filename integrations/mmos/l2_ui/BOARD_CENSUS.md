# L2 UI lane — board → component → state census (file 01M3NRCX55B452A12819WNE1RH companion)

Verified against current code at worktree `t3/11b494ec` (Mastermind, `app/mastermind_os`).
Read method: every row re-checked in source; `docs/TEAM_CODE_FLEET_UI.md` claims were
re-verified and the code wins on any conflict (deltas listed at the end). Data states:
**LIVE** (real projection through host/native read), **HONEST-NULL** (fed null/absent,
copy names the missing source), **FIXTURE** (sample data in a shipped non-test path —
defect), **MISSING** (no component). Evidence is `file:line` under `app/mastermind_os/`
unless noted.

Census result: **43/54 boards map to shipped components** (30 of the canonical 34; 4
canonical boards MISSING). **0 fixture defects** on any mapped board surface. Board-level
counts: 24 LIVE, 16 HONEST-NULL (incl. null-fed components), 11 MISSING / no-surface,
3 LIVE-partial, plus behavior/meta boards mapped to shared surfaces.

## 1. Census table (54 rows)

| Board | Node | 34? | Component file(s) | Data state + evidence | Test file(s) | Gap (≤12 words) |
|---|---|---|---|---|---|---|
| TD01 Team · Twelve-bot workspace | ZQN-0 | yes | `src/team/TeamWorkspace.tsx` (roster, :515-593) via `src/team/TeamRoute.tsx:67-68` → native port `team_roster` (`src-tauri/src/hermes_native/bridge.py:280-282`) | **LIVE** — one bounded native read, fail-closed parse (`src/hermes-native/native-port.ts:111`); web shows TS01 card (`TeamRoute.tsx:57`) | `TeamWorkspace.test.tsx`, `TeamRoute.test.tsx`, `App.team-code-routes.test.tsx`, `native-port-roster.test.ts`, `team-roster-contract.test.ts` | single read; no presence refresh |
| TD02 Engineering · Persistent bot workspace | 102K-0 | yes | `TeamWorkspace.tsx` detail (:372-513) + `src/hermes-native/HermesNativePanel.tsx` (App.tsx:5916) | **LIVE** — existing native conversation surface; gateway state classified (`TeamWorkspace.tsx:19-29`) | `TeamWorkspace.test.tsx`, `HermesNativePanel.test.tsx`, `contract.test.ts` | one conversation at a time; no per-bot switcher |
| TD03 Project · Work and results | 10B8-0 | yes | `src/projects/ProjectDeliveryPanel.tsx` (App.tsx:5520-5533) + `src/team/DelegatedTaskCard.tsx`, `delegated-task.ts` | **HONEST-NULL** — `objective={null}` `delegatedTask={null}` (App.tsx:5521,5524); trail all `unknown` (:5526-5531) | `ProjectDeliveryPanel.test.tsx`, `DelegatedTaskCard.test.tsx`, `delegated-task.test.ts` | project objective/task source not wired |
| TD04 Code · T3 workbench | 10L5-0 | yes | `src/code/CodeWorkspace.tsx` (App.tsx:5925) + `src/code/t3-thread-projection.ts` | **HONEST-NULL** — `t3-thread-projection.ts:129` "NO host implements `MastermindMissionHost.t3ThreadProjection`"; copy names it (`CodeWorkspace.tsx:32-38,105-129`) | `CodeWorkspace.test.tsx`, `t3-thread-projection.test.ts` | t3ThreadProjection host source unimplemented |
| TD05 Capacity Fabric · Shared pools | 10WB-0 | yes | `src/resources/CapacityFabricRead.tsx` (App.tsx:5884); host read `readCapacityFabric` (`src/host.ts:722-737`) → native `read_capacity_fabric` (`src-tauri/src/main.rs:190`) / web (`src/web-auth.ts:1433`) | **LIVE** — manual authenticated read; expired/unknown stays unknown (`CapacityFabricRead.tsx:22,31-33,74-81`) | `CapacityFabricRead.test.tsx`, `App.fabric-fleet.test.tsx`, `host.resource-capacity.test.ts` | manual read only; no auto refresh |
| TD06 Route · Review execution | 117C-0 | yes | `DelegatedTaskCard.tsx` route chips + PREVIEW/EFFECT·NONE + disabled dispatch (:156-171,202-218); `delegated-task.ts:37` mirrors shared `RoutePreview.v1` | **HONEST-NULL** — null-fed at both mounts (App.tsx:5524,5917); dispatch preview-only reason (`DelegatedTaskCard.tsx:140-147`) | `DelegatedTaskCard.test.tsx`, `delegated-task.test.ts` | RoutePreview producer absent; card null-fed |
| TD07 Run · Result and return path | 11GQ-0 | yes | `src/fabric/FabricRunCatalog.tsx` + `FabricMissionInspector.tsx` + `mission-worker-result.ts` (App.tsx:5899); return review `src/team/ResultReturnCard.tsx` (`ProjectDeliveryPanel.tsx:111-118`) | **LIVE** catalog/mission (native `read_fabric_catalog`/`read_fabric_status`, main.rs:192-193); **HONEST-NULL** return (`executionReturn={null}` App.tsx:5525) | `FabricRunCatalog.test.tsx`, `FabricMissionInspector.test.tsx`, `mission-worker-result.test.ts`, `ResultReturnCard.test.tsx`, `App.retained-results.test.tsx` | execution_return producer absent (Director F gap #2) |
| TD08 Team · 390 EN | 11ZB-0 | yes | `TeamWorkspace.tsx` + `src/team/team.css:586-587` (@media ≤800px stacked cards); roving focus (:356-370) | **LIVE** (same read as TD01) | `TeamWorkspace.test.tsx` (keyboard nav) | no 390-viewport test run |
| TD09 Code · 390 EN | 123Z-0 | yes | `CodeWorkspace.tsx` + `src/code/code.css:139` | **HONEST-NULL** (same as TD04) | `CodeWorkspace.test.tsx` | same missing projection source |
| TD10 Team · 390 ZH · Light | 128B-0 | yes | `TeamWorkspace.tsx` zh strings (:158-219) + theme via `DisplayPreferences` | **LIVE** (same read as TD01) | `TeamWorkspace.test.tsx`, `App.team-code-routes.test.tsx` (zh-CN) | light-theme mobile contrast untested |
| TD11 Capacity Fabric · 390 EN | 18LP-0 | yes | `CapacityFabricRead.tsx` + `src/resources/capacity-fabric.css:49-50` | **LIVE** (same read as TD05) | `CapacityFabricRead.test.tsx` | no 390-viewport test run |
| TD12 Allowance details · 390 EN | 193T-0 | yes | `CapacityFabricRead.tsx` allowance details (:99-104: shared allowance, windows, single-window) | **LIVE** (same read as TD05) | `CapacityFabricRead.test.tsx` | retained per-attempt allowance panel unwired |
| TD13 Teammate detail · 390 EN | 19EJ-0 | yes | `TeamWorkspace.tsx` detail branch (:372-513) | **LIVE** (same single roster read) | `TeamWorkspace.test.tsx` | detail shares single roster read |
| HC01 Team · Live group conversation | 12UW-0 | yes | `HermesNativePanel.tsx` (App.tsx:5916) | **LIVE** — native session list/messages (`HermesNativePanel.tsx:203-210`) | `HermesNativePanel.test.tsx`, `continuity.test.ts` | no group-room model; one session |
| HC02 New bot · Role and launch | 136T-0 | yes | `HermesNativePanel.tsx` role select + new conversation (:168-171) | **LIVE-partial** — native `create` carries `role` (bridge.py:24,84-89) | `HermesNativePanel.test.tsx` | two fixed roles; no bot-profile creation |
| HC03 New group · Members and room behavior | 13GW-0 | yes | MISSING — no group/member-creation UI (grep: none in `src/team`, `src/hermes-native`) | **MISSING** | none | room/member creation surface absent |
| HC04 Bot conversation · Streaming and queued direction | 13RP-0 | yes | `HermesNativePanel.tsx` (:203-210) + `classifyGatewayState` (`TeamWorkspace.tsx:19-29`) | **LIVE** — queued/held/prompt-pending states honest (:209-210) | `HermesNativePanel.test.tsx`, `TeamWorkspace.test.tsx` | no streaming render; queued direction only |
| HC05 Delegated task · Dialogue and parent return | 142O-0 | yes | `DelegatedTaskCard.tsx` in `TeamWorkspace.tsx:500-508`; binding facts (:91-127) mirror `ExecutionBinding` v1/v1.1 | **HONEST-NULL** — `delegatedTask={null}` (App.tsx:5917); requester fields PENDING v1.2 (`delegated-task.ts:64`) | `DelegatedTaskCard.test.tsx`, `delegated-task.test.ts` | v1.2 requester fields pending; null-fed |
| HC06 Start coding · Project and workspace | 14CR-0 | yes | `DelegatedTaskCard.tsx` "Open coding session →" (:219-227) → `TeamRoute` `onOpenCode` → App.tsx:5919-5920 → `CodeWorkspace` (App.tsx:5925) | **HONEST-NULL** entry — wiring LIVE, task source null | `DelegatedTaskCard.test.tsx`, `App.team-code-routes.test.tsx` | entry dead until task projection lands |
| HC07 Code · Thread, changes and host tools | 14MJ-0 | yes | `CodeWorkspace.tsx` thread rows (run state, PR link :140-218) | **HONEST-NULL** — no thread source; no host-tool read | `CodeWorkspace.test.tsx` | thread source + host-tool facts missing |
| HC08 Team · Result delivered to origin | 14V7-0 | yes | `src/team/ResultReturnCard.tsx` (only parsed `mastermind.execution_return/v1`; no `accepted` render — header :1-15) in `ProjectDeliveryPanel.tsx:111-118` | **HONEST-NULL** — `executionReturn={null}` (App.tsx:5525) | `ResultReturnCard.test.tsx`, `execution-return-contract.test.ts` | no execution_return producer wired |
| HC09 Bot settings · Models and capabilities | 155S-0 | yes | MISSING — no bot-settings UI (grep: none) | **MISSING** | none | bot settings surface absent |
| HC10 Routines · Schedule, run and delivery | 15GA-0 | yes | MISSING — no routines UI (only incidental copy `Inbox.tsx:110`) | **MISSING** | none | routine scheduler surface absent |
| HC11 Code settings · Provider, environment and capabilities | 15QF-0 | yes | MISSING — no code-settings surface (global provider read exists: `ModelConfigurationRead`) | **MISSING** | none | code-scoped settings surface absent |
| HC12 Room · Thread replies and message actions | 15Z2-0 | yes | `src/conversations/ConversationWindow.tsx` (context/evidence panels :253-267, original-reply reading :130-136, unsent-notes composer :273-279) + `ObservedTranscript.tsx` | **LIVE** — `read_current_window` (host.ts:1590→main.rs:197; web :1373); send honestly disabled (:279) | `ConversationWindow.test.tsx`, `.reading.test.tsx`, `.presentation.test.tsx`, `ObservedTranscript.test.tsx` | read-only; no reply threading/actions |
| HC13 Team inbox · 390 EN | 168E-0 | yes | `src/inbox/Inbox.tsx` via `InboxWorkspace` (App.tsx:5421-5432) + `inbox.css:61-62` | **LIVE** — office projection via `readPrograms` (native main.rs:153 / web :1310) | `Inbox.test.tsx`, `InboxWorkspace.test.tsx` | no 390-viewport test run |
| HC14 Team room · 390 EN | 16CD-0 | yes | `HermesNativePanel.tsx` + `native-panel.css:28` | **LIVE** (native conversation) | `HermesNativePanel.test.tsx` | no 390-viewport test run |
| HC15 Team room · 390 ZH Light | 16FT-0 | yes | `HermesNativePanel.tsx` (zh :14) + theme | **LIVE** | `HermesNativePanel.test.tsx` | zh/light mobile untested |
| HC16 Task dialogue · 390 EN | 16IW-0 | yes | `TeamWorkspace.tsx` detail + `DelegatedTaskCard` + `team.css:587` | **HONEST-NULL** (task null, App.tsx:5917) | `DelegatedTaskCard.test.tsx`, `TeamWorkspace.test.tsx` | task null; no 390 test |
| HC17 Code · Native Capacity Fabric provider | 18ZE-0 | yes | `CapacityFabricRead.tsx` connected-applications block (hermes/t3_code rows :109-112) + `src/resources/ModelConfigurationRead.tsx` (App.tsx:5894) | **LIVE** — provider/route observations via `read_capacity_fabric` + `read_model_configuration` (main.rs:189-190) | `CapacityFabricRead.test.tsx`, `ModelConfigurationRead.test.tsx` | provider context global, not per-thread |
| HC18 Team · Needs you and exact request | 1NSP-0 | yes | `Inbox.tsx` "Needs you" section (:53-64) with exact-selection guard (:24) + evidence panel (:93-94, Escape) | **LIVE** — mission owed_turn through projection; unqualified stays empty honestly (:59) | `Inbox.test.tsx`, `App.office-existing-reads.test.tsx` | mission-keyed only; no team-channel requests |
| HC19 Team · Two conversations, independent drafts | 1OAV-0 | yes | `src/conversations/ConversationsList.tsx` + `src/conversations/drafts.ts` (per-context draft keys :19-22) | **LIVE** — ephemeral shell-owned drafts; "Unsent draft" chip (`ConversationsList.tsx:79`) | `drafts.test.ts`, `ConversationsList.test.tsx`, `conversation-list-source.test.ts` | draft isolation is client-state only |
| HC20 Team · Search with exact-message context | 1OVH-0 | yes | `ConversationsList.tsx` filter (:13-19; scope honestly stated :115) | **LIVE-partial** — title/project/topic search only | `ConversationsList.test.tsx` | no message-content search |
| HC21 Team · Parent work and scoped task dialogue | 1PB7-0 | yes | `TeamRoute.tsx:92-100` (conversationPanel + scoped delegatedTask) | **LIVE** conversation + **HONEST-NULL** task (App.tsx:5917) | `TeamRoute.test.tsx`, `App.team-code-routes.test.tsx` | scoping by teammate; task null |
| TS01 Roster maintenance/uncertainty states | 11QU-0 | ext | `TeamWorkspace.tsx` UNAVAILABLE card (:273-324) + PENDING card (:326-343) + `TeamRoute.tsx:54-58` | **HONEST-NULL/LIVE-honest** — "never shown as an empty company" (:124); reason code shown (:292) | `TeamWorkspace.test.tsx`, `TeamRoute.test.tsx`, `App.team-code-routes.test.tsx` | — |
| TS02 Teamlink · Delivery, capacity and return | 18JN-0 | ext | contract only: `src/hermes-native/teamlink-contract.ts` (header :1-11 "no UI"); **no view consumes it** (grep: test only) | **MISSING** (as surface) | `teamlink-contract.test.ts` | contract ready; no UI consumer |
| TD05H Hosts & maintenance · Detail reference | 1815-0 | ext | `src/resources/HostTelemetryPanel.tsx` (in `ResourcesSystemsPanel.tsx:137`) | **HONEST-NULL** in shipped wiring — App never passes `capacity` (App.tsx:5886), so :37 honest "no qualified retained host observation"; native `read_host_observation` exists (main.rs:191, `src/resources/host-observation-host.ts`) | `HostTelemetryPanel.test.tsx`, `ResourcesSystemsPanel.test.tsx`, `useRecordedHostObservationWorkspace.test.tsx` | telemetry read exists but unwired in Fleet view |
| TB01 Architecture · Runtime ownership | 12DE-0 | ext | build meta-board — documentation artboard; no runtime surface by design | **MISSING** (meta) | — | build meta-board; census doc is the artifact |
| TB02 Build · Local GLM delivery packets | 12LO-0 | ext | `src/fabric/LocalFabricOwnerImport.tsx` (offline signed-file import; `local-fabric-owner-contract.ts`; mounted `AttendedFabricWorkspace.tsx:24`) | **LIVE-partial** — explicit user-file import only; errors honest (`LocalFabricOwnerImport.tsx:31` error state) | `LocalFabricOwnerImport.test.tsx`, `local-fabric-owner-contract.test.ts` | offline import only; no live packet channel |
| TB03 Interaction · Fast, continuous, responsive | 18IB-0 | ext | behavior board — shared responsive/keyboard surface: `team.css:587`, `code.css:139`, `styles.css:870-1100`, reduced-motion rules (`conversations-list.css:75`, `conversation.css:80`) | **LIVE** (behavior of mapped surfaces) | `TeamWorkspace.test.tsx` keyboard, `useComposerKeyboard.ts` + `SelectedSessionContinuation.keyboard.test.tsx` | no per-board interaction benchmark |
| HC22 Team · Attention inbox · 390 EN (late add) | 1PPR-0 | ext | `Inbox.tsx` + `inbox.css:61-62` | **LIVE** (same projection as HC13) | `Inbox.test.tsx` | no 390-viewport test run |
| HC23 Team · Focused conversation tabs · 390 EN (late add) | 1PTB-0 | ext | `ConversationsList.tsx` (focused open) + `ConversationWindow.tsx` + `conversation.css:70-71` | **LIVE** (current-window read) | `ConversationsList.test.tsx`, `ConversationWindow.test.tsx` | tabs model is list→back, not tabs |
| HC24 Team · Search return · 390 ZH Light (late add) | 1PW0-0 | ext | `ConversationsList.tsx` no-matches honest state (:66) + zh strings | **LIVE-partial** (title search; empty return honest) | `ConversationsList.test.tsx` | no message-content search |
| HS01 Conversation · Reconnect and message states | 16LF-0 | ext | `HermesNativePanel.tsx` (AUTHENTICATION_CHANGED :52-54, unknown admission :209, prompt-pending :210) + `ConversationWindow` refresh | **LIVE-honest** — states derived from native port codes | `HermesNativePanel.test.tsx`, `ConversationWindow.refresh.test.tsx`, `App.conversation-unavailable.test.tsx` | — |
| HS02 Creation · Bot, room and coding launch | 16VK-0 | ext | partial: `HermesNativePanel.tsx:168-171` (conversation+role); coding launch `src/planning/ProjectStartWork.tsx` + `LaunchOrchestrator.tsx` | **LIVE-partial** — bot/room creation MISSING | `HermesNativePanel.test.tsx`, `ProjectStartWork.test.tsx`, `LaunchOrchestrator.test.tsx` | bot/room creation absent; coding launch present |
| HS03 Execution · Access, capabilities and host control | 1767-0 | ext | `src/access/ProjectAccessPanel.tsx` (App.tsx:5611) + `src/supervision/AutonomyPanel.tsx` (App.tsx:5603) + `DelegatedTaskCard` binding block | **LIVE** — `read_project_access` (main.rs:180 / web-auth.ts:1342) + `read_autonomy_policy` (main.rs:185) | `ProjectAccessPanel.test.tsx`, `project-access-*.test.ts`, `AutonomyPanel.test.tsx`, `autonomy-policy.test.ts` | — |
| HS04 Team · Creation, scope and lifecycle recovery | 1PZ9-0 | ext | `native-port.ts` recover ops (:99-108) + `HermesNativePanel` held/unknown (:209) + `src/auth-recovery/NativeDraftRecoveryNotice.tsx`, `useNativeProjectGoalRecovery.ts` | **LIVE-honest** — durable pending pointer; no replay | `native-port.test.ts`, `HermesNativePanel.test.tsx`, `useNativeProjectGoalRecovery.test.tsx`, `native-draft-owner.test.ts` | — |
| HS05 Team · Routine delivery, coordinator and restoration | 1Q7B-0 | ext | MISSING — no routines UI | **MISSING** | none | routine delivery surface absent |
| HS06 Conversations · Drafts selected · Mobile | 1S6D-0 | ext | `ConversationsList.tsx:79` draft chip + `drafts.ts` + `ConversationWindow.tsx:273-279` unsent notes | **LIVE** — ephemeral, honestly unsent | `drafts.test.ts`, `ConversationsList.test.tsx`, `ConversationWindow.test.tsx` | — |
| HS07 Conversations · No drafts in this view · Mobile | 1SBF-0 | ext | same files; rows without drafts render no chip | **LIVE-honest** | same | — |
| HS08 Conversations · Draft search empty · Mobile | 1SD4-0 | ext | MISSING — list search covers titles/topics only (`ConversationsList.tsx:115`), never draft content | **MISSING** (as capability) | none | no draft-content search |
| HB01 Build map · Joined journey and coverage | 17GG-0 | ext | build meta-board — this census + `TEAM_CODE_FLEET_UI.md` are the artifact | **MISSING** (meta) | — | documentation board, not a runtime surface |
| HB02 Build contracts · Reuse, owners and proof | 17R6-0 | ext | contracts exist and are tested: `delegated-task.ts`, `execution-return-contract.ts`, `teamlink-contract.ts`, `t3-attempt-fleet-contract.ts`, `local-fabric-owner-contract.ts` | **MISSING** (meta surface; contracts LIVE in code) | the per-contract `*.test.ts` files | contract set live; no single contracts view |
| HB03 Build · Daily workspace identity and recovery contracts | 1QE6-0 | ext | `src/auth-recovery/native-draft-continuity.ts` + native `read_native_draft_continuity` (main.rs:145, `native_draft_identity.rs`) | **LIVE-honest** (native-only recovery metadata; no web path) | `native-draft-continuity.test.ts`, `native-draft-owner.test.ts`, `draft_recovery_tests.rs` | no web equivalent (by design) |

## 2. Top gaps, ranked by journey impact (Team → conversation → project → T3 deep link → result → Fleet)

1. **Delegated-task projection absent at both mounts** — `delegatedTask={null}` (App.tsx:5524, 5917) plus PENDING v1.2 requester fields (`delegated-task.ts:64`): the Team→project handoff renders no concrete task anywhere (TD03/HC05/HC06/HC16/HC21 all null-fed).
2. **No execution-return producer** — `executionReturn={null}` (App.tsx:5525): the result→Fleet end of the journey (HC08/TD07 return review) never renders a real return.
3. **`MastermindMissionHost.t3ThreadProjection` implemented by no host** (`t3-thread-projection.ts:129`): the Code deep-link board (TD04/HC07/TD09) renders only the honest "not projected" card; the journey's T3 step has no live surface.
4. **Fleet per-attempt T3 read is web-only** — `readT3AttemptFleet` exists in web-auth.ts:1463 and the `MissionHost` binding (host.ts:738-754) but the native client never supplies it and no Tauri command exists, so `T3AttemptFleetBlock` ("Read attempt") is inert in the native app (honest copy at `T3AttemptFleetBlock.tsx:61`).
5. **Team lifecycle boards missing components** — HC03 (new group), HC09 (bot settings), HC10/HS05 (routines), HC11 (code settings), HS08 (draft search), TS02 (teamlink UI): 7 boards have no shipped surface.

Secondary: TD05H host-telemetry read exists natively but is unwired in the Fleet view (App.tsx:5886 passes no `capacity`); TD12's retained per-attempt allowance panel (`RetainedProviderCapacityPanel`) likewise never receives `providerCapacity`; HC02/HS02 have only two fixed roles and no bot-profile creation.

## 3. Native-vs-web read seam

Every method in `createNativeClient`'s read union (`src/host.ts:1209-1255` plus the direct
methods at :1296-1592) resolves to a command present in the Rust `invoke_handler`
(`src-tauri/src/main.rs:135-215`) — all 47 checked, none missing. The gaps are the reads
that exist **only** on the web client or **only** on the native client:

| Host read method | Tauri command | Exists in Rust? | Web (src/web-auth.ts) | Notes |
|---|---|---|---|---|
| `readT3AttemptFleet` | — | **no** | yes (`:1463`, `GET /workspace/resources/t3/attempts/current`) | **GAP** — native app cannot read per-attempt T3 fleet facts; `MissionHost` binding (host.ts:738-754) dormant on native |
| `readControlRoomDiscovery` | — | **no** | yes (`:1316`) | GAP — Discovery read is web-only |
| `readOriginalMissionV4` | — | **no** | yes (`:1492`) | original-owner v4 read is web-only |
| `readMissionV4` + `productAcceptanceOwner` | — | **no** | yes (`:1500-1520`) | product-acceptance read path is web-only |
| `research` (evidence transport) | — | n/a (HTTP) | yes (`:1222` readEvidenceItem) | private Auth0 token stays web-side by design |
| `readHostObservation` | `read_host_observation` (main.rs:191) | yes | no web method | native-only; currently unwired consumer in Fleet view (TD05H) |
| `readByokRoles` | `read_byok_roles` (main.rs:154) | yes | yes (`:1312`) | both |
| `readControlRoomState` | `read_control_room_state` (main.rs:155) | yes | yes (`:1314`) | both; actions (`open/bind/unbind/refresh-builds`) web-only (`:1318-1321`) — native has no `openControlRoomSurface` etc. |
| `readCompanyPriorities` (executive transport) | `read_company_priorities` (main.rs:156) | yes (`native-executive-transport.ts:127`) | yes (`:1233`) | both |
| `readAutonomyPolicy` | `read_autonomy_policy` (main.rs:185) | yes | yes (`:1389`) | both |
| `readCapacityFabric` | `read_capacity_fabric` (main.rs:190) | yes | yes (`:1433`) | both |
| `readModelConfiguration` | `read_model_configuration` (main.rs:189) | yes | yes (`:1430`) | both |
| `readResourceCapacity` | `read_resource_capacity` (main.rs:188) | yes | yes (`:1470`) | both |
| `readRetainedActivity` | `read_retained_activity` (main.rs:187) | yes | yes (`:1478`) | both |
| `readWork` / `readPrograms` | `read_work` :157 / `read_programs` :153 | yes | yes (`:1322`/`:1310`) | both |
| `readMission` / `readMissionV3` / `readResult` / `readMissionResult` / `readResultReferences` / `readCurrentWindow` | `read_mission` :158 / `read_mission_v3` :159 / `read_result` :194 / `read_mission_result` :195 / `read_result_references` :196 / `read_current_window` :197 | yes | yes | both |
| `readAdmittedPlan` / `readProjectPlan` / `readProjectJournal` / `readProjectDirection` / `readProjectSessionAssociation` / `readProjectArchive(Page)` / knowledge ×3 / `readSourceOperationContext` / sourceOperations ×6 | main.rs:160-179 | yes | yes | both |
| `readProjectAccess` / `readProjectInstructions` / admission ×4 / instruction ×4 | main.rs:167-170, 180-184 | yes | yes | both |
| `readAttendedFabric` / `readAttendedFabricCatalog` | `read_fabric_status` :193 / `read_fabric_catalog` :192 | yes | yes (`:1335`/`:1332`) | both |
| hermes-native port (`team_roster`, `list`, `read`, `create`, `send`, `receipt`, `recover_*`) | `hermes_native` (main.rs:144) → `bridge.py:23-28,280-282` | yes | **no** | native-only by design; roster read rides this port |
| `nativeDraftRecovery` | `read_native_draft_continuity` (main.rs:145) | yes | no | native-only by design |
| `terminalSharing` + `openTerminalBriefs` | `terminal_session_*`/`read_terminal_sharing_requests`/`open_terminal_briefs`/`open_terminal_sharing_request` (main.rs:137-142) | yes | no | native-only by design |
| work/primary auth (`read_work_authorization`, `sign_in_for_work`, `sign_in_primary`, `read_authorization_continuation`, `continue_authorization`) | main.rs:146-151 | yes | no (Auth0 web flow instead) | distinct owners by design |

## 4. Deltas vs `docs/TEAM_CODE_FLEET_UI.md` (code wins)

- All mapped rows in the prior doc re-verify at current head (Team roster native read, null-fed
  delegatedTask/executionReturn, Code honest-missing-source, Fleet reuse, seven-destination nav
  — `App.test.tsx:642`, `App.tsx:217-225`). No contradicted row found.
- The doc's "adapter note" proposed the T3 attempt fleet read; as landed it is **web-only**
  (web-auth.ts:1463) with **no Tauri command** — the native Fleet surface cannot read it. The doc
  does not record that seam split.
- Newer than the doc: `src/hermes-native/teamlink-contract.ts` (TS02) exists with tests but **no
  UI consumer** — TS02 is a MISSING surface, not an honest-null one.
- `ResourcesSystemsPanel`'s `capacity`/`providerCapacity` props (HostTelemetryPanel,
  RetainedProviderCapacityPanel) are not passed by App (App.tsx:5886) — TD05H/TD12 ship
  honest-unavailable in the Fleet view despite live native read commands existing.

## 5. Fixture audit

No fixture defects on any board surface: all `*fixture*.ts` modules are imported by test files
or by the separate, explicitly-labeled inert proof-harness HTML entries (`browser-proof.html`,
`project-execution-proof.html`, conversation/`client-reuse-proof.html`,
`project-draft-files-local.tsx` — headers declare "LOCAL INERT … declared fixtures",
"INERT_RECORDED_CLOCK_NOT_REAL_AUTHORIZATION"). These proof pages are standalone Vite
entries, not Paper board surfaces, and no board component renders sample people/jobs/numbers.

# MODULE_MAP — old Mastermind OS app → Paperclip module architecture

Lane L9, DONE_WHEN item 5. Written 2026-11-10 on `t3/mmos-v3-l9` (trunk
`c0263d2d1` merged). Read-only investigation; this file is the lane's one write.

Binding inputs read: `integrations/mmos/PROGRAM_PLAN_V3.md` (§1–5, §8a owner
table, decision 9), `ops/paperclip_fleet/README.md`, Paperclip plugin SDK
README (`~/.paperclip/cli/current/node_modules/@paperclipai/plugin-sdk/README.md`,
"UI slots and launchers" + "Capabilities"),
`~/.mastermind/mmos_evidence/l4-20261110/slice2-path-census.md` (83 paths),
`integrations/mmos/LANE_L9_MODULE_PLATFORM.md` (item 5 amendment: owner column,
build order (a)/(b)/(c)).

## Rules used

- **Disposition** is one of `shell-as-is` (Paperclip already provides it),
  `module: <name>` (Paperclip plugin module under
  `integrations/paperclip_plugins/`, with its slot(s)/tool),
  `window` (thin native window, L8), `wrapped` (one-line reason).
- **Backend** is one of `none`, `paperclip-api`, `executive-local-socket`
  (the L4 Unix-socket door — used conservatively; live wiring is L10),
  `other: <name>`. Paperclip host APIs are the baseline for every module;
  where a module needs a second source the row names the decisive one and the
  "Multi-backend modules" note below lists the rest.
- **Owner of the fact** follows plan §8a: work item → Paperclip; run on an
  agent's Hermes profile → Paperclip run on the Hermes adapter; coding job
  (admission/attempts/effects/recovery) → Executive executed in T3;
  capacity/quotas/placement → Capacity Fabric; bot identity/memory/conversation
  → Hermes profiles; workstream continuity/decisions/handoffs → Agent OS;
  code/PRs/evidence → GitHub; a routine's trigger → one named owner per
  routine. `n/a` marks dropped surfaces.
- **Never rebuilt** (used as-is from Paperclip): tasks, inbox, artifacts,
  routines, dashboard, costs. **Not adopted**: Paperclip's experimental native
  Runner; Paperclip agent chat as a Hermes-conversation replacement.
- Module rules from the lane amendment bind every module: displays and joins,
  never admits/schedules/retries/accepts; ids stay separate fields joined
  explicitly; never "nothing needs you" unless every covered source was
  observed; produced/delivered/reviewed/accepted are four states; no module
  duplicates a routine defined elsewhere.

Module names used below: `mastermind-core` (run health + engineering trunk;
lane item 2, already being built), `mastermind-roster`, `mastermind-coding`,
`mastermind-capacity`, `mastermind-hermes`, `mastermind-agentos`,
`mastermind-search`.

---

## Table 1 — React app screens (`app/mastermind_os/src`)

Navigation entry: `App.tsx:193-253` (`navigation`, `primaryNavigation`,
`OperationalNavigation`, `missionNavigation`, `projectTabs`). Test names
(`App.*.test.tsx`) corroborate each feature.

| Surface | What it was for | Disposition | Backend needed | Owner of the fact |
| --- | --- | --- | --- | --- |
| Today (`today/Today.tsx`) | Hero composer "What would you like done?", selected-task attention card, work state | shell-as-is (Paperclip dashboard + task creation; module widgets add joins) | paperclip-api | Paperclip |
| Team roster table (`team/TeamWorkspace.tsx`, `team/team-roster.ts` over `hermes-native/team-roster-contract.ts` `mastermind.team_roster/v1`) | Bots table: identity, conversation, work per bot | module: mastermind-roster (`dashboardWidget` + `sidebarPanel`; four separate LIVE counts — configured roles, enrolled agents, reachable agents, agents with active work — none hard-coded) | paperclip-api | Hermes profiles (identity) / Paperclip (agents, active work) |
| Team routines (`team/RoutinesPanel.tsx`) | Routine list, schedule, run behavior, latest/recent runs | shell-as-is (Paperclip routines + history; one named trigger owner each) | none | one named owner per routine |
| Inbox-needs-you, delegated task, result return cards (`team/InboxNeedsYouPanel.tsx`, `DelegatedTaskCard.tsx`, `ResultReturnCard.tsx`) | What needs the Chairman, per-task delegation and result return | shell-as-is (Paperclip inbox) + coding/capacity blocker items come from their modules (PC2) | paperclip-api | Paperclip |
| Split conversations / reply threads (`team/SplitConversationsWorkspace.tsx`, `ReplyThreadPanel.tsx`) | Two-pane conversation reading and replies | module: mastermind-hermes (conversation join by id; Paperclip agent chat not adopted as Hermes replacement) | other: hermes-native-bridge | Hermes profiles |
| New bot / bot settings / new group (`team/NewBotPanel.tsx`, `BotSettingsPanel.tsx`, `NewGroupPanel.tsx`) | Hiring and configuring bots and groups | wrapped — bot identity/memory owned by Hermes profiles; agent hiring keeps its task authorization | none | Hermes profiles |
| Work hierarchy (`team/WorkHierarchyView.tsx`) | Parent/delegated work tree | shell-as-is (Paperclip issue subtree/relations) | paperclip-api | Paperclip |
| Projects list + workspace (`projects/Projects.tsx`, `ProjectWorkspace.tsx`, `Projects.root-search`) | Project list, search, selected-project details | shell-as-is (Paperclip projects + issues) | paperclip-api | Paperclip |
| New project draft, planning journey, plan workflows (`projects/NewProjectDraft.tsx`, `ProjectPlanningJourney.tsx`, `planning/PlanAdoptionWorkflow.tsx`, `ProjectPlanProposalWorkflow`, `ProjectStartWork`) | Creating a project and its plan through Executive sessions | shell-as-is (Paperclip project/goal creation); planning-as-work becomes a task routed to an agent | paperclip-api | Paperclip |
| Project delivery / route review / run outcome (`projects/ProjectDeliveryPanel.tsx`, `ProjectRouteReview.tsx`, `ProjectRunOutcome.tsx`) | Following a delivery route and its run outcome | module: mastermind-coding (outputs join: PR/document opened from the task, four states) | other: github-api | GitHub |
| Project archive (`projects/archive/`, `read_project_archive`) | Archived projects | shell-as-is (Paperclip project states) | paperclip-api | Paperclip |
| Project tabs Conversation/Overview/Plan/Work/Evidence/Journal/More (`App.tsx:253`) | Per-project tab workspace | shell-as-is (Paperclip project detail: Overview/Work); Evidence → mastermind-coding join; Journal/Plan continuity → mastermind-agentos links; Conversation tab → mastermind-hermes join | paperclip-api | Paperclip (tab host) |
| Code workspace — T3 thread list (`code/CodeWorkspace.tsx`, `code/t3-thread-projection.ts`) | List of T3 coding threads with evidence | module: mastermind-coding (`detailTab` on `issue`: Executive job/attempt ids, T3 thread link, state — read-only shape + fixture data in L9; live wiring L10) | executive-local-socket | Executive, executed in T3 |
| Code workbench (`code/CodeWorkbench.tsx` — attempts rail, changes/browser/terminal tabs, facts, checks, return footer) | Full coding attempt surface | module: mastermind-coding (same `detailTab`; browser/terminal panes are L10 live wiring) | executive-local-socket | Executive, executed in T3 |
| Code settings (`code/CodeSettingsPanel.tsx`) | Coding tool preferences | module: mastermind-coding (`settingsPage`) | none | n/a |
| Inbox (`inbox/Inbox.tsx`, `InboxWorkspace.tsx`) | Owner-request attention over the current Mission | shell-as-is (Paperclip inbox) | none | Paperclip |
| Terminal/brief sharing inbox (`inbox/TerminalSharingInbox.tsx`, `BriefSharingInbox.tsx`) | Terminal sharing requests from the hosted edge | wrapped — hosted-web sharing surface on a separate edge; out of local-product scope | other: sharing-edge (out of scope) | n/a |
| Conversations list + window (`conversations/ConversationsList.tsx`, `ConversationWindow.tsx`, `ObservedTranscript.tsx`) | Reading observed conversations and transcripts | module: mastermind-hermes (read-only conversation join; Hermes owns conversations) | other: hermes-native-bridge | Hermes profiles |
| New conversation journey (`conversations/new-conversation/*` — draft, turn panel, outcome, continuation) | Starting and continuing an Executive conversation | module: mastermind-hermes (fresh conversation = task routed on the Hermes adapter; result returns to the same task) | paperclip-api | Paperclip (run) / Hermes (conversation) |
| Historical original answers (`conversations/HistoricalOriginalAnswers.tsx`, `ResultSourceReader.tsx`) | Qualified original answer reading | module: mastermind-hermes (join by conversation id) | other: hermes-native-bridge | Hermes profiles |
| Knowledge surfaces (`knowledge/Knowledge.tsx`, `KnowledgeSources.tsx`, `library/KnowledgeLibrary.tsx`, `KnowledgeDraftCompanion.tsx`) | Knowledge catalogue, sources, memory, publication journey | module: mastermind-agentos (decisions/discoveries/handoff links joined from the task/project; `sidebar` + `page`) | other: agent-os | Agent OS |
| Search / Sources / Tools discovery (`discovery/DiscoveryWorkspace.tsx`, `ProjectSearchWorkspace.tsx`, `SavedConversationReader.tsx`, `discovery/contract.ts` modes Search/Sources/Tools) | Cross-surface search over projects, conversations, evidence, results | module: mastermind-search (`page` + `globalToolbarButton`; joins Paperclip issues/artifacts + GitHub evidence + Hermes conversation ids — no second index) | paperclip-api | mixed (per-source owner) |
| Meta-CEO office (`meta-ceo/MetaCeoOffice.tsx` — answer panel, direction intake, draft preview, attention aside) | The company's current operating answer and direction intake | module: mastermind-agentos (direction `page`: current direction = latest accepted `DEC` history; intake becomes a task) | other: agent-os | Agent OS (strategy) / Paperclip (intake task) |
| Company priorities read (`meta-ceo/CompanyPrioritiesRead.tsx`) | Company priorities from the Executive | module: mastermind-agentos (priorities block on the direction page) | other: agent-os | Agent OS (Strategic State P0) |
| BYOK roles (`meta-ceo/ByokRolesPanel.tsx`, `ByokConnectionDrawer.tsx`) | Bring-your-own-key role connections | wrapped — model placement is Capacity Fabric's; no per-role BYOK UI in the local shell | none | Capacity Fabric |
| Office work read / dependencies (`meta-ceo/OfficeWorkRead.tsx`, `OfficeDependencies.tsx`) | Work and dependency reads for the office | shell-as-is (Paperclip dashboard work views) | paperclip-api | Paperclip |
| Work queue / work journey (`workJourney.tsx`, `work.ts` — work document groups) | The work ladder: facts, evidence, stages | shell-as-is (Paperclip issues board) | paperclip-api | Paperclip |
| Programs (`mission.ts` programs, `programs-observation.ts`) | Company programs catalogue | shell-as-is (Paperclip projects/goals) | paperclip-api | Paperclip |
| Control Room (`ControlRoomPanel.tsx` — company overview, observed programme coverage, cross-plane evidence; `ControlRoomSurfaceControls.tsx`) | Company overview and qualified mission access | module: mastermind-core (`dashboardWidget` + `sidebar` + `page` + agent tool: run health, engineering trunk, company overview joins) | paperclip-api | mixed; engineering trunk → GitHub |
| Session Estate (`session-estate/SessionEstate.tsx`) | Sessions, sources, technical detail per session | shell-as-is (Paperclip run history on the task); deep session trace wrapped — sessions are ephemeral, recovery is the coding module's job (DONE_WHEN 9) | paperclip-api | Paperclip (run history) |
| Fleet & Capacity panel (`resources/ResourcesSystemsPanel.tsx`, `CapacityFabricRead.tsx`, `ResourceCapacityRead.tsx`, `ModelConfigurationRead.tsx`, `HostTelemetryPanel.tsx`, `RetainedProviderCapacityPanel.tsx`) | Capacity, quotas, models, host telemetry | module: mastermind-capacity (`dashboardWidget` reading Capacity Fabric, never its own figures) | other: capacity-fabric | Capacity Fabric |
| T3 attempt fleet block (`resources/T3AttemptFleetBlock.tsx`) | T3 attempt fleet read | module: mastermind-coding (attempt fleet section of the `detailTab`) | executive-local-socket | Executive, executed in T3 |
| Attended fabric workspace / inspector / run catalog (`fabric/AttendedFabricWorkspace.tsx`, `AttendedFabricInspector.tsx`, `FabricRunCatalog.tsx`) | Fabric catalog, mission interiors, run inspection | module: mastermind-capacity (`page` + `detailTab` on `agent`/`run`) | other: capacity-fabric | Capacity Fabric |
| Local fabric owner import (`fabric/LocalFabricOwnerImport.tsx`) | Importing a fabric owner | wrapped — enrollment stays with Capacity Fabric; no owner import UI | none | Capacity Fabric |
| Mission Workspace / mission result (`mission.ts`, `mission-result.ts`, `App.tsx:5967`) | The mission view and its result | shell-as-is (Paperclip project/goal detail; the "mission" folds into project + tasks) | paperclip-api | Paperclip |
| Retained results (`RetainedResults.tsx`, `RetainedRootChoice.tsx`, `result.ts`) | Retained result catalogue and selection | shell-as-is (Paperclip artifacts) + PR/document outputs joined by mastermind-coding | paperclip-api | GitHub (PR/document evidence) |
| Activity (`activity/RetainedResultContent.tsx`, `App.tsx:5988`) | Recorded work and results | shell-as-is (Paperclip activity feed) | paperclip-api | Paperclip |
| Connections (`App.tsx:5989`) | Project connections | shell-as-is (Paperclip access/members surfaces) | paperclip-api | Paperclip (access) |
| Evidence / Research Vault (`research/ResearchEvidence.tsx`, `ResearchEvidenceEntry.tsx`, `App.tsx:5990` Evidence tab) | Literal source-evidence passage reading | module: mastermind-coding (evidence/outputs join on the task) | other: github-api | GitHub |
| Product acceptance (`product-acceptance/ProductAcceptancePanel.tsx`) | Product acceptance qualification | module: mastermind-coding (produced/delivered/reviewed/accepted as four separate states on the output row) | other: github-api | GitHub (review evidence); acceptance stays with the Chairman |
| Supervision (`supervision/AutonomyPanel.tsx`, `SupervisionLedger.tsx`, `SupervisionTrace.tsx`) | Autonomy policy, supervision ledger and trace | shell-as-is (Paperclip audit log); deep trace wrapped — governance stays in the control plane, audit read via the shell | none | Paperclip (audit) |
| Project admission (`admission/ProjectAdmissionPanel.tsx` + pause/resume commands) | Admission control, pause and resume | wrapped — admission authority is Executive's; read-only state shows in mastermind-coding's tab, no pause/resume UI | executive-local-socket | Executive |
| Standing instructions / instruction admission (`instructions/StandingInstructionsPanel.tsx`) | Per-project standing instructions and admission control | module: mastermind-agentos (read-only instruction links from the project page; source law lives in the repo) | other: github-api | GitHub (source law) |
| Direction panels (`direction/ProgrammeDirection.tsx`, `AcceptedDirectionPanel.tsx` — current direction + history) | Current direction and its declared history | module: mastermind-agentos (direction page reads accepted `DEC` history) | other: agent-os | Agent OS |
| Project access (`access/ProjectAccessPanel.tsx`) | Project access state | shell-as-is (Paperclip access) | paperclip-api | Paperclip |
| Activation receipts / facts / web session preview (`activation/ActivationReceipt.tsx`, `ActivationFacts.tsx`, `WebSessionPreview.tsx`, `LaunchRequestPreview.tsx`) | Web-session activation ceremony | wrapped — local trusted mode needs no activation ceremony (decision 2) | none | n/a |
| Auth entry and recovery (`auth-entry/AuthEntry.tsx`, `auth-recovery/*`, `NativeAuthorizationContinuationControl.tsx`, `NativePrimaryAccountControl.tsx`, `NativeWorkAuthorizationControl.tsx`, `TransportDiagnosticFields.tsx`) | Auth0 login, partial-auth presentation, draft continuity, authorization continuation | wrapped — Auth0 login repair and edge allowlist work stopped (plan §3) | none | n/a |
| Display preferences / locale (`preferences/DisplayPreferences.tsx`, `app-copy.ts`, `App.display-preferences.test.tsx`) | Theme and locale preferences | shell-as-is (Paperclip settings) | none | n/a |
| Organization workspace (`organization/OrganizationWorkspace.tsx` — Chairman, current workstream, executive root) | Org structure and lineage | module: mastermind-agentos (organization `page`: roles, workstream lineage, executive root) | other: agent-os | Agent OS |
| Hermes native panel (`hermes-native/HermesNativePanel.tsx` — runtime version, local conversations) | Local Hermes bridge status and conversations | module: mastermind-hermes (status `sidebarPanel`; gateway version + conversation join) | other: hermes-native-bridge | Hermes profiles |
| Project journal (`ProjectJournalReader.tsx`, `project-journal.ts`) | Project journal reading | module: mastermind-agentos (handoff/journal links from the project) | other: agent-os | Agent OS |

**Multi-backend modules** (Paperclip host APIs are baseline; these also read a
second source): `mastermind-roster` also reads the Hermes native bridge for
"reachable agents" (the other three counts come from Paperclip);
`mastermind-search` reads GitHub and the Hermes bridge; `mastermind-core` reads
GitHub for engineering-trunk health; `mastermind-coding` reads the Executive
local socket (L10 live; L9 uses fixture data); `mastermind-hermes` uses the
existing Hermes adapter/native bridge, never Paperclip agent chat.

---

## Table 2 — native command surface (`src-tauri`, 58 commands in `auth.rs` + aux modules)

Line numbers are `auth.rs` at trunk `c0263d2d1` (installed `5420bb17` is 66
lower after ~2270). Registration list: `main.rs:135-265`.

| Command group (line range) | What it was for | Disposition | Backend needed | Owner of the fact |
| --- | --- | --- | --- | --- |
| Auth/session: `auth_status` 564, `sign_out` 568, `sign_in` 602; aux `sign_in_primary` (`auth/primary_account.rs:42`), `read_work_authorization`/`sign_in_for_work` (`auth/work_authorization.rs`), `read_authorization_continuation`/`continue_authorization` (`auth/authorization_continuation.rs:421,428`), `read_native_draft_continuity` (`auth/native_draft_identity.rs`) | Auth0 sign-in/out, primary account, work authorization, authorization continuation, draft continuity | wrapped — no login for local use (decision 2); session-in-memory Executive routes are replaced by the L4 local door | none | n/a |
| Workspace reads (the 6 edge-allowed): `read_programs` 1235, `read_work` 1246, `read_mission` 1280, `read_mission_v3` 2608, `read_result` 2640, `read_current_window` 2772 | Feeding Today/Office/RetainedResults/ConversationWindow | shell-as-is (Paperclip dashboard/issues/artifacts supply these facts) | paperclip-api | Paperclip |
| `read_byok_roles` 1213 | BYOK role catalogue | wrapped — model placement owned by Capacity Fabric | none | Capacity Fabric |
| Project knowledge: `read_project_knowledge_catalogue` 1514, `read_project_knowledge_memory` 1518, `read_project_knowledge_source` 1522 | Knowledge catalogue/memory/source | module: mastermind-agentos (links from project) | other: agent-os | Agent OS |
| `read_project_journal` 1537 | Project journal | module: mastermind-agentos | other: agent-os | Agent OS |
| Project admission: `read_project_admission_control` 1670, `pause_project_admission` 1674, `resume_project_admission` 1680, `read_project_admission_operation` 1688 | Admission control and pause/resume | wrapped — admission authority is Executive's; read-only state in the coding tab | executive-local-socket | Executive |
| Source operations: `read_source_operation_context` 1778, `source_operation_{options,prepare,read,submit,reconcile,advance}` 2130-2150 | Git source-operation lifecycle through the edge | wrapped — superseded by the Executive coding-job path on a Paperclip task (decision 6) | none | Executive (via coding module) |
| `read_project_session` 2168, `read_project_direction` 1414 | Project session association and direction | module: mastermind-agentos (direction/continuity links) | other: agent-os | Agent OS |
| `read_autonomy_policy` 2205, `read_admitted_plan` 2232 | Autonomy policy and admitted plan | shell-as-is (audit/plan facts visible via shell audit + agentos links); deep policy views wrapped | none | Paperclip (audit) / Agent OS |
| Fabric/capacity: `read_fabric_catalog` 2316, `read_fabric_status` 2320, `read_capacity_fabric` 2417, `read_model_configuration` 2447, `read_resource_capacity` 2480 | Fabric catalog/status, capacity, models | module: mastermind-capacity (catalog/status/capacity/models) | other: capacity-fabric | Capacity Fabric |
| T3 attempt fleet: `read_t3_attempt_fleet` 2367 | T3 attempts | module: mastermind-coding (attempt fleet section of the `detailTab`) | executive-local-socket | Executive, executed in T3 |
| Activity/results: `read_retained_activity` 2520, `read_result_references` 2573, `read_mission_result` 2708 | Retained activity and result references | shell-as-is (Paperclip activity/artifacts) + mastermind-coding outputs join | paperclip-api | GitHub (PR evidence) |
| Executive conversation family: `executive_fresh_conversation` 3034, `executive_project_conversations_read` 3026 | Starting/reading Executive conversations | module: mastermind-hermes (conversations move to Hermes; the work item stays a Paperclip task) | other: hermes-native-bridge | Hermes profiles |
| Executive execution/planning: `executive_project_execution` 3042, `executive_project_planning` 3048 | Project execution and planning through Executive sessions | module: mastermind-coding (execution becomes a coding job on a task; planning becomes a routed task) | executive-local-socket | Executive, executed in T3 |
| Executive core transport: `executive_auth_status` 3054, `executive_context` 3063, `executive_submit` 3071, `executive_status` 3084 (the 3 edge-allowed POSTs) | Submitting work to the Executive | module: mastermind-coding (L4 Unix-socket door with peer-uid admission; loopback TCP/headers never trusted — decision 6) | executive-local-socket | Executive |
| Direct-native ports: `executive_direct_native_result` 3098, `executive_direct_native_consume` 3105, `executive_direct_correction` 3112 | Direct-native result/consume/correction | module: mastermind-coding (attempts/effects/recovery on the tab; live wiring L10) | executive-local-socket | Executive |
| Session ports: `executive_project_session_references` 3166, `executive_session_send` 3178, `executive_session_context` 3185, `executive_project_history_context` 3201, `executive_session_reply` 3208, `executive_session_references` 3218 | Executive session send/context/history/reply | module: mastermind-hermes (conversation join; session transport wrapped — sessions are ephemeral) | other: hermes-native-bridge | Hermes profiles |
| `hermes_native` (`auth/hermes_native.rs:235`) | Native Hermes bridge operations (create/send/status/recover over `mastermind.team_roster/v1` etc.) | module: mastermind-hermes (bridge status + conversation join) | other: hermes-native-bridge | Hermes profiles |
| `read_control_room_state` (`auth/control_room_read.rs:58`) | Control-room state | module: mastermind-core (company-overview widget) | paperclip-api | mixed (per §8a) |
| `read_company_priorities` (`auth/company_priorities.rs:29`) | Company priorities | module: mastermind-agentos | other: agent-os | Agent OS |
| `read_host_observation` (`auth/host_observation.rs:19`) | Host observation | module: mastermind-capacity (host telemetry widget) | other: capacity-fabric | Capacity Fabric |
| `read_project_access` (`auth/project_access.rs:13`) | Project access | shell-as-is (Paperclip access) | paperclip-api | Paperclip |
| Instruction admission: `read_project_instructions`, `read_instruction_admission_control`, `pause_instruction_admission`, `read_instruction_admission_operation` (`auth/instruction_admission.rs:43-68`) | Standing instructions and their admission control | module: mastermind-agentos (read-only instruction links; source law in the repo) | other: github-api | GitHub (source law) |
| Terminal commands: `readiness` (`main.rs:68`), `open_terminal_briefs` (`terminal_navigation.rs:18`), `terminal_session_status`/`terminal_sign_in`/`terminal_disconnect`/`read_terminal_sharing_requests` (`terminal_session.rs:183-221`), `open_terminal_sharing_request` (`terminal_sharing_navigation.rs:9`) | Terminal briefs, session, sharing requests | wrapped — hosted-edge terminal surfaces, out of local-product scope (plan §3) | other: sharing-edge (out of scope) | n/a |

---

## Table 3 — L4 path census (app → backend, 83 paths, 74 aborted at the edge)

Census: `~/.mastermind/mmos_evidence/l4-20261110/slice2-path-census.md`. Row
numbers (#) are census-table rows. The 9 edge-allowed paths fed only 6 screens;
everything else never reached a working backend — the direct reason the shell
moved to local Paperclip.

| Path group (census rows) | What it fed | Disposition | Backend needed | Owner of the fact |
| --- | --- | --- | --- | --- |
| Allowed GETs `/workspace/{programs,work,mission,mission/v3,result,window}/current` (#1-6) | Today, Office, RetainedResults, ConversationWindow | shell-as-is (Paperclip dashboard/issues/artifacts supply these facts) | paperclip-api | Paperclip |
| Allowed POSTs `/os/executive/{context,submit,status}` (#48-50) | native-executive-transport | module: mastermind-coding (L4 local door; be conservative — live wiring L10) | executive-local-socket | Executive |
| `/workspace/byok/roles/current` (#7) | ByokRolesPanel | wrapped — Capacity Fabric owns placement | none | Capacity Fabric |
| Project reads `/workspace/project-{plan,direction,knowledge,session}/current`, `project-knowledge/{memory,source}`, `projects/archive` (#8-14, 17) | Projects, Knowledge, direction | shell-as-is (projects/tasks) + mastermind-agentos links for direction/continuity (multi-backend: see note below) | paperclip-api | Paperclip / Agent OS |
| `/workspace/project-admission/*` GET+POST (#15, 16, 41, 42) | ProjectAdmissionPanel | wrapped — admission authority is Executive's; read-only state in the coding tab, no pause/resume UI | executive-local-socket | Executive |
| `/workspace/source-operation/*` (#18-20, 43-46) | source-operation lifecycle | wrapped — superseded by the coding-job path on a task (decision 6) | none | Executive (via coding module) |
| `/workspace/{autonomy,plan}/current` (#21, 22) | AutonomyPanel, AdmittedPlanInspector | shell-as-is (audit) + agentos links; deep views wrapped | none | Paperclip (audit) / Agent OS |
| Fabric/resources `/workspace/fabric/{status,catalog}`, `resources/{fabric,models,capacity}`, `operator/activity` (#23-24, 26-29, 33) | Fleet & Capacity, fabric workspace | module: mastermind-capacity | other: capacity-fabric | Capacity Fabric |
| `/workspace/resources/t3/attempts/current` (#25) | T3 attempt fleet | module: mastermind-coding (attempt fleet section of the coding `detailTab`) | executive-local-socket | Executive, executed in T3 |
| Results `/workspace/{result-references,mission-result}/current` (#30, 31) | result references, mission result | shell-as-is (artifacts) + coding outputs join | paperclip-api | GitHub (PR evidence) |
| `/workspace/control-room/state/current` (#32) | ControlRoomPanel | module: mastermind-core | paperclip-api | mixed |
| `/workspace/native-draft-identity/current` (#34) | native-draft continuity | wrapped — login/draft ceremony stops | none | n/a |
| `/workspace/project-access`, `project-instructions`, `instruction-admission/{current,operation,pause}` (#35-38, 47) | access/instructions panels | shell-as-is (access) + agentos read-only instruction links | other: github-api | Paperclip (access) / GitHub (law) |
| `/workspace/native-authorization-identity/{acquisition,content}/current` (#39, 40) | authorization continuation | wrapped — login work stops | none | n/a |
| `/os/executive/direct-native/{result,consume,correction}` (#51-53) | direct-native command port | module: mastermind-coding (attempts/effects/recovery) | executive-local-socket | Executive |
| `/os/executive/session/{references,send,context,history-context,reply}`, `session/conversations*`, `project-executions` (#54-64) | conversations catalogue/read, session ports | module: mastermind-hermes (conversation join; conversations are Hermes facts) | other: hermes-native-bridge | Hermes profiles |
| `/os/executive/project-execution/{preview,submit,status}` (#65-67) | project execution | module: mastermind-coding (execution as coding job) | executive-local-socket | Executive |
| `/os/executive/project-planning/{submit,status,result,consume,prepare_proposal}` (#68-72) | planning journeys | module: mastermind-coding / routed task (planning becomes a task on an agent) | executive-local-socket | Executive (job) / Paperclip (work item) |
| `/os/executive/company-priorities` (#73) | OfficeWorkRead priorities | module: mastermind-agentos | other: agent-os | Agent OS |
| `/os/executive/conversation/{preview,create,status,read,consume,turn*}` (#74-83) | new-conversation journey | module: mastermind-hermes (fresh conversation = routed task; result returns to the same task, DONE_WHEN 4) | paperclip-api | Paperclip (run) / Hermes (conversation) |

Out-of-census hosts (Auth0, terminal sharing edge, Supabase, loopback Hermes
bridge — census appendix) follow their rows above: auth and terminal surfaces
are `wrapped`; the loopback Hermes bridge is `mastermind-hermes`'s backend.

---

## Build order

Ranked by Chairman-visible value, referencing rows above. Ranks 2–4 are placed
exactly as the principal's amendment fixes them; I found no evidence to
reorder — each is unblocked by the platform proof (lane item 3), needs no live
Executive wiring, and directly serves a DONE_WHEN number.

1. **`mastermind-core`** (fixed; lane item 2, already being built) — run health
   + engineering trunk: the Control Room rows (`ControlRoomPanel`, census #32)
   as `dashboardWidget` + `sidebar` + `page` + agent tool. First proof of
   DONE_WHEN 2 (page, sidebar entry, widget, tool, real local data).
2. **Roster-truth widget** (`mastermind-roster`, `dashboardWidget` +
   `sidebarPanel`) — four separate LIVE counts (configured roles, enrolled
   agents, reachable agents, agents with active work; roster rows above),
   none hard-coded. Serves DONE_WHEN 1: the shell shows the real company and
   its agents, truthfully (plan: four different numbers, never one).
3. **Coding-job `detailTab`** (`mastermind-coding`, `detailTab` on `issue`) —
   Executive job/attempt ids, T3 thread link, state: read-only shape + fixture
   data in L9 (Code workspace/workbench rows). Live wiring is L10; this fixes
   the contract early because every later coding surface joins these ids.
4. **Capacity/quota widget** (`mastermind-capacity`, `dashboardWidget`) — reads
   Capacity Fabric, never its own figures (Fleet & Capacity rows). Gives the
   Chairman the resource picture the old app never delivered (census #23-28
   were all aborted at the edge).
5. **`mastermind-hermes`** — conversation join by id + agent-page enrichment +
   Hermes status panel (Conversations rows, `hermes_native` command). Serves
   DONE_WHEN 4 and the conversation half of DONE_WHEN 11; the join is what
   makes a task and its conversation openable side by side.
6. **`mastermind-coding` live phase (L10)** — L4 local-door wiring, attempt
   fleet, outputs on the task with produced/delivered/reviewed/accepted as
   four states (delivery/acceptance rows, direct-native rows). Serves
   DONE_WHEN 5, 9, 11.
7. **`mastermind-agentos`** — workstream/decision/handoff links from the task,
   direction and organization pages (Knowledge, direction, organization,
   Meta-CEO rows). Serves DONE_WHEN 10's blocker visibility (with coding/
   capacity blocker items in the shell inbox, PC2) and the strategy picture.
8. **`mastermind-search`** — discovery `page` + `globalToolbarButton` joining
   Paperclip issues/artifacts, GitHub evidence and Hermes conversation ids
   (Search/Sources/Tools rows). Lower rank: valuable but purely a join over
   surfaces the earlier modules must first make addressable.

Dropped rather than rebuilt: auth/activation/terminal-sharing ceremonies
(decisions 2–3), BYOK roles, local fabric owner import, deep supervision
trace, admission pause/resume controls (see `wrapped` rows). Paperclip-native
tasks, inbox, artifacts, routines, dashboard and costs are used as-is
everywhere; no row above proposes rebuilding them.

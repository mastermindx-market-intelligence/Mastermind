# Team / Code / Fleet UI — board map, tests and data status

Director D implementation map for the Mastermind OS experience (Team, Projects
delivery, Code, Fleet). Design ground truth is the accepted Paper file
(`Mastermind OS — Team/Projects/Code/Fleet`, PRs 2345/2358); every board below
names its Paper node. Typed vitest assertions are the acceptance evidence —
screenshots are not.

## Paper board → component → test

| Paper board (node) | Meaning | Component | Test |
| --- | --- | --- | --- |
| p-O-0 TD01 roster (`ZQN-0`) | Team roster with readiness + current focus | `src/team/TeamWorkspace.tsx` (roster table) rendering Director B's `mastermind.team_roster/v1` (`src/hermes-native/team-roster-contract.ts`) — the duplicate UI-side contract was removed | `src/team/TeamWorkspace.test.tsx` — renders honest ready/degraded/unknown rows with visible reason codes (fixtures built through B's real parser) |
| p-P-0 TS01 (`11QU-0`) | Roster source unavailable / unverified states | `src/team/TeamWorkspace.tsx` (connect card; PENDING reading card) + `src/team/TeamRoute.tsx` (one bounded native-port read) | `TeamWorkspace.test.tsx` — "never shown as an empty company", "Not verified"/"Not observed"; `src/team/TeamRoute.test.tsx` — port-injected read states; `src/App.team-code-routes.test.tsx` — route-level honest state and the live native read (port mocked at the invoke/available/store seam) |
| p-O-0 TD02 Engineering entry (`102K-0`) + p-S-0 HS01 (`16LF-0`) | Bot entry opens the EXISTING conversation surface; distinct gateway states (viewer-disconnected / gateway-busy / quota / unknown) | `TeamWorkspace.tsx` (bot detail, `conversationPanel` slot filled by `src/hermes-native/HermesNativePanel.tsx` in `App.tsx`) + `classifyGatewayState()` | `TeamWorkspace.test.tsx` — classifier table + rendered `role="status"` per state; never a second transport |
| p-O-0 TD03 Project work (`10B8-0`) + p-R-0 HC05 (`142O-0`) | Project work/detail: delegated task card `queued\|running\|unknown\|declined\|terminal`, PREVIEW / EFFECT·NONE chips, disabled dispatch with honest reason, admission-binding identity from the SHARED contract | `src/team/DelegatedTaskCard.tsx` (binding facts block), `src/team/delegated-task.ts` (mirrors `ExecutionBinding` v1/v1.1 field names/vocabularies from `control_plane/child_execution_contracts.py`; fail-closed `parseDelegatedTask`), `src/projects/ProjectDeliveryPanel.tsx` | `src/team/delegated-task.test.ts` (fail-closed parser, sparse v1.1 law, PENDING v1.2 requester fields refused), `src/team/DelegatedTaskCard.test.tsx` (five states, chips, binding facts, no return block), `src/projects/ProjectDeliveryPanel.test.tsx` |
| p-R-0 HC08 (`14V7-0`) | Delivered ≠ accepted | `src/team/ResultReturnCard.tsx` consuming ONLY Director F's parsed `ExecutionReturnRecord` (`mastermind.execution_return/v1`) + optional `ExecutionReturnDeliveryReceipt` from `src/hermes-native/execution-return-contract.ts`; mounted in `ProjectDeliveryPanel`'s "Result return" section (typed prop `executionReturn`, null-fed today). Acceptance is closed to `not_accepted` in v1 — the card has no "accepted" rendering at all; stage and GitHub evidence render as proven, unknown never green | `src/team/ResultReturnCard.test.tsx` — committed-fixture record + contract-minted records, delivered/refused/unknown receipts, mismatch refusal, zh |
| p-O-0 TD04 T3 workbench (`10L5-0`) + p-R-0 HC07 (`14MJ-0`) | Code tab: deep-link to the exact native T3 thread; thread id, environment, run state, last activity, PR link. The not-projected copy NAMES the missing source (`MastermindMissionHost.t3ThreadProjection` — no host implements it) and points per-attempt T3 facts at the Fleet per-attempt read | `src/code/CodeWorkspace.tsx`, `src/code/t3-thread-projection.ts` (`t3ThreadUrl` → `https://app.t3.codes/threads/<env>/<thread>`) | `src/code/t3-thread-projection.test.ts` (fail-closed parser + URL encoding), `src/code/CodeWorkspace.test.tsx` (deep-link href, no embedded editor/terminal, honest missing-source copy en+zh) |
| p-O-0 TD05 Fleet (`10WB-0`) | Fleet capacity reuses the incumbent surfaces — no duplicate fleet UI | `src/fabric/**` + `src/resources/**` (unchanged) | existing: `src/App.fabric-fleet.test.tsx`, `src/resources/HostTelemetryPanel.test.tsx`, `src/resources/CapacityFabricRead.test.tsx`, `src/resources/retained-provider-capacity.test.tsx` |
| p-R-0 HC01 (`12UW-0`), HC04 (`13RP-0`), HC10 (`15GA-0`) | Journey-level honesty: unknown shown as unknown with reason; authority chips; preview-only send disabled | `TeamWorkspace.tsx`, `DelegatedTaskCard.tsx`, `ResultReturnCard.tsx` | covered by the per-component tests above (unknown-with-reason assertions, PREVIEW chips, disabled dispatch) |
| p-Q-0 TB01 (`12DE-0`), TB02 (`12LO-0`) | Roster table behavior (keyboard, responsive collapse) | `TeamWorkspace.tsx` (`ArrowUp/Down/Home/End` roving focus), `src/team/team.css` (`@media (max-width: 800px)` stacked rows) | `TeamWorkspace.test.tsx` — keyboard navigation test |
| p-T-0 HB01 (`17GG-0`), HB02 (`17R6-0`) | Honest board behaviors (no invented states; disabled contrast) | all new components; `team.css`/`code.css` use `--noir-text-secondary` for disabled controls (does not replicate the AT17/22 low-contrast defect) | typecheck + the state tests above |

Navigation: `Team` and `Code` are primary Company destinations
(`App.tsx` `navigation`/`primaryNavigation`); pinned in
`src/App.test.tsx` ("keeps seven Company destinations") and exercised end-to-end
in `src/App.team-code-routes.test.tsx` (en + zh-CN).

## Live data vs projection-pending

| Surface | Status | Source |
| --- | --- | --- |
| Team roster | **Live-path (native op).** `src/team/TeamRoute.tsx` reads it once through the EXISTING native port: one `status` binds the runtime scope, then the read-only `team_roster` dispatch (closed echo check + fail-closed `parseTeamRoster` live in the port). Roster rows render B's richer fields — gateway observed/source/state, closed `readinessReason`/`activityReason` codes (human phrase + `<code>`), `managed`, `host` (`"unknown"` sentinel never shown as a hostname), `lastActivity`. Web/dev (no native host) shows the honest TS01 unverified card with `NATIVE_PLATFORM_UNAVAILABLE`; a PENDING read never renders an empty table. No polling, retry or second transport. | `src-tauri/src/hermes_native/bridge.py` operation `team_roster` (Director B) → `src/hermes-native/native-port.ts` → `src/team/TeamRoute.tsx` → `src/team/TeamWorkspace.tsx` |
| Engineering bot conversation | **Live** through the existing native surface. `App.tsx` mounts the incumbent `HermesNativePanel`; this lane adds no second transport. Gateway state classification is derived from the panel's own state/code. | `src/hermes-native/**` (Director B, read-only consume) |
| Delegated coding tasks | **Projection-pending.** `delegated-task.ts` mirrors the SHARED admission contract (`ExecutionBinding` v1/v1.1 in `control_plane/child_execution_contracts.py`): the binding block carries `root_run_ref`, `immediate_parent_run_ref`, `logical_child_key`, `request_digest`, `effective_complexity`, `task_kind` + the sparse v1.1 extensions `runtime_kind`, `operation_key`, `caller_namespace`, `lease_ref`, validated fail-closed by `parseDelegatedTask` (bounded printable triple, hex64 digest, canonical long-name complexity, open runtime vocabulary, sparse v1.1 schema derivation). The original-requester fields (`teammate_id`/`conversation_id`/`project_id`) are **PENDING the v1.2 requester block** (Director C2; `integrations/mmos/LANE_RETURN_PATH_DIRECTOR_F.md` gap #1) — listed in `PENDING_REQUESTER_FIELDS`, refused by the parser until the Python contract has them. App passes `delegatedTask: null` today → honest copy; dispatch stays disabled (preview-only authority). | `src/team/delegated-task.ts` |
| Execution return (HC08) | **Projection-pending, null-fed.** `ProjectDeliveryPanel` takes a typed `executionReturn: ExecutionReturnRecord \| null` (+ optional `deliveryReceipt`) and mounts `ResultReturnCard` on it; App passes `null` today → "No execution return is projected yet." When a producer lands (Executive wiring per `LANE_RETURN_PATH_DIRECTOR_F.md` gap #2), the SAME prop carries F's parsed `mastermind.execution_return/v1` record — stage ladder, GitHub evidence, `not_accepted` acceptance (no `accepted` producer exists in v1), and the delivery receipt's `delivered\|unknown\|refused` states, with "Delivered ≠ accepted" explicit. | `src/hermes-native/execution-return-contract.ts` (Director F, read-only consume) → `src/team/ResultReturnCard.tsx` → `src/projects/ProjectDeliveryPanel.tsx` |
| T3 thread list | **Projection-pending; source honestly missing.** Reads `window.MastermindMissionHost.t3ThreadProjection.read()` (fail-closed) and parses `mastermind.t3_thread_projection_list.v1`; **no host implements that source**, and the not-projected copy says so by name instead of implying a pending load. The source of truth for per-attempt T3 facts is the Fleet per-attempt read (adapter note below), not this list. Deep links are pure and always well-formed. | `src/code/t3-thread-projection.ts` |
| Project delivery panel | **Projection-pending.** Objective/task/trail read as `null`/"unknown" until the project source exposes them; the panel says so rather than inventing progress. | `src/projects/ProjectDeliveryPanel.tsx` |
| Fleet capacity | **Live as before** — the incumbent Fabric/Capacity/Resources views are reused unchanged, with their existing honest-unknown guarantees (unknown host telemetry stays unknown; zero vs missing stays distinct; malformed quota receipts are rejected). | `src/fabric/**`, `src/resources/**` |

Fixtures live only in `*.test.*` files; no production path renders sample bots
or threads. The execution-return fixtures under
`integrations/mmos/fixtures/execution_return_v1/` are read by tests only; the
production card is fed `null` until a real producer exists.

## Per-attempt T3 facts — adapter note (typed, no new transport)

Per-attempt T3 facts (thread/run ids, harness process, duplicate-launcher
observation, the `exactly_one_thread` / `exactly_one_harness` invariants,
freshness) are owned by the Fleet per-attempt read, NOT by the Code thread
list:

- Contract: `mastermind.t3_attempt_fleet/v1`, fail-closed owner
  `control_plane/t3_attempt_fleet_projection.py::validate_attempt`; TS mirror
  proposed as `parseT3AttemptFleet` in
  `src/hermes-native/t3-attempt-fleet-contract.ts`
  (`integrations/mmos/FLEET_ATTEMPT_CONTRACT_PROPOSAL.md` §1).
- Read route: `GET /workspace/resources/t3/attempts/<attempt_id>` on the
  Workspace read service (integrator decision, proposal §5; Director G2
  landing) — the same signed HTTP read family the Capacity Fabric panel uses
  (`/workspace/resources/fabric/current`, #2351). The attempt list source is
  the existing attended-Fabric catalog run list (an attempt's `attempt_id` IS
  the run id); no second list API.
- Fleet rendering home: the "T3 attempt fleet" details block beside the run
  inspector (proposal §3) — invariant chips PROVEN / VIOLATED / UNKNOWN(+reason),
  never healthy-by-default. The Code view links there for per-attempt truth
  and keeps its own thread-list projection separate; this lane adds no
  transport, host or daemon for either.

## Known Paper defects deliberately not replicated

- Sidebar collision on AT22: roster/detail layouts use the shell's existing
  fixed lanes rather than overlapping absolutely-positioned regions.
- Low-contrast disabled states on AT17/22: disabled dispatch uses
  `--noir-text-secondary`, keeping the reason text readable.

# Team / Code / Fleet UI — board map, tests and data status

Director D implementation map for the Mastermind OS experience (Team, Projects
delivery, Code, Fleet). Design ground truth is the accepted Paper file
(`Mastermind OS — Team/Projects/Code/Fleet`, PRs 2345/2358); every board below
names its Paper node. Typed vitest assertions are the acceptance evidence —
screenshots are not.

## Paper board → component → test

| Paper board (node) | Meaning | Component | Test |
| --- | --- | --- | --- |
| p-O-0 TD01 roster (`ZQN-0`) | Team roster with readiness + current focus | `src/team/TeamWorkspace.tsx` (roster table) | `src/team/TeamWorkspace.test.tsx` — renders honest ready/degraded/unknown rows |
| p-P-0 TS01 (`11QU-0`) | Roster source unavailable / unverified states | `src/team/TeamWorkspace.tsx` (connect card) | `TeamWorkspace.test.tsx` — "never shown as an empty company", "Not verified"/"Not observed"; `src/App.team-code-routes.test.tsx` — route-level honest state |
| p-O-0 TD02 Engineering entry (`102K-0`) + p-S-0 HS01 (`16LF-0`) | Bot entry opens the EXISTING conversation surface; distinct gateway states (viewer-disconnected / gateway-busy / quota / unknown) | `TeamWorkspace.tsx` (bot detail, `conversationPanel` slot filled by `src/hermes-native/HermesNativePanel.tsx` in `App.tsx`) + `classifyGatewayState()` | `TeamWorkspace.test.tsx` — classifier table + rendered `role="status"` per state; never a second transport |
| p-O-0 TD03 Project work (`10B8-0`) + p-R-0 HC05 (`142O-0`) | Project work/detail: delegated task card `queued\|running\|unknown\|declined\|terminal`, PREVIEW / EFFECT·NONE chips, disabled dispatch with honest reason | `src/team/DelegatedTaskCard.tsx`, `src/projects/ProjectDeliveryPanel.tsx` | `src/team/DelegatedTaskCard.test.tsx` (all five states, chips, aria-describedby reason, terminal result), `src/projects/ProjectDeliveryPanel.test.tsx` |
| p-R-0 HC08 (`14V7-0`) | Delivered ≠ accepted | `src/team/ResultReturnCard.tsx` | `src/team/ResultReturnCard.test.tsx` — separate Delivered/Accepted states, evidence, zh |
| p-O-0 TD04 T3 workbench (`10L5-0`) + p-R-0 HC07 (`14MJ-0`) | Code tab: deep-link to the exact native T3 thread; thread id, environment, run state, last activity, PR link | `src/code/CodeWorkspace.tsx`, `src/code/t3-thread-projection.ts` (`t3ThreadUrl` → `https://app.t3.codes/threads/<env>/<thread>`) | `src/code/t3-thread-projection.test.ts` (fail-closed parser + URL encoding), `src/code/CodeWorkspace.test.tsx` (deep-link href, no embedded editor/terminal) |
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
| Team roster | **Projection-pending.** Reads `window.MastermindMissionHost.teamRoster.read()` and parses `mastermind.team_roster/v1` fail-closed. Until Director B's projection is installed every host reports no source and the view shows the honest TS01 unverified state. | `src/team/team-roster-contract.ts` |
| Engineering bot conversation | **Live** through the existing native surface. `App.tsx` mounts the incumbent `HermesNativePanel`; this lane adds no second transport. Gateway state classification is derived from the panel's own state/code. | `src/hermes-native/**` (Director B, read-only consume) |
| Delegated coding tasks | **Projection-pending.** `DelegatedTaskCard` renders only what a caller passes; App passes `null` today → "No delegated coding task is projected…" honest copy. Dispatch stays disabled (preview-only authority). | `src/team/delegated-task.ts` |
| T3 thread list | **Projection-pending.** Reads `window.MastermindMissionHost.t3ThreadProjection.read()` and parses `mastermind.t3_thread_projection_list.v1` fail-closed; today every host reports no source → honest "not projected yet" card with the reason code. Deep links are pure and always well-formed. | `src/code/t3-thread-projection.ts` |
| Project delivery panel | **Projection-pending.** Objective/task/trail read as `null`/"unknown" until the project source exposes them; the panel says so rather than inventing progress. | `src/projects/ProjectDeliveryPanel.tsx` |
| Fleet capacity | **Live as before** — the incumbent Fabric/Capacity/Resources views are reused unchanged, with their existing honest-unknown guarantees (unknown host telemetry stays unknown; zero vs missing stays distinct; malformed quota receipts are rejected). | `src/fabric/**`, `src/resources/**` |

Fixtures live only in `*.test.*` files; no production path renders sample bots
or threads.

## Known Paper defects deliberately not replicated

- Sidebar collision on AT22: roster/detail layouts use the shell's existing
  fixed lanes rather than overlapping absolutely-positioned regions.
- Low-contrast disabled states on AT17/22: disabled dispatch uses
  `--noir-text-secondary`, keeping the reason text readable.

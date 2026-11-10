# LANE L2 — Product UI (DONE_WHEN row 6)

Lead lane branch `t3/mmos-v2-l2`; lands on trunk `feat/mmos-v1-integration-t3`
(plain merge, non-force). Mission: a real usable UI from the 34 canonical Paper
boards (TD01–TD13 + HC01–HC21, file 01M3NRCX55B452A12819WNE1RH) for the journey
**Team → conversation → project → T3 deep link → result → Fleet**, with honest
unknown/queued/declined/backend-unavailable states, responsive layouts and
keyboard navigation. Evidence companions (same directory): `BOARD_INVENTORY.md`
(54-board census of the file), `BOARD_EXTRACTIONS.md` (authored structure+copy),
`BOARD_CENSUS.md` (board → component → state table at lane start).

## Board coverage (canonical 34)

| Boards | Surface | State |
|---|---|---|
| TD01/TS01, TD02, HC01, HC04, HC10→* | `src/team/TeamWorkspace.tsx` + `TeamRoute.tsx` (live `team_roster` native read) | LIVE (pre-lane) |
| TD03, TD06, TD07 | `src/projects/ProjectDeliveryPanel.tsx` + NEW `ProjectRouteReview.tsx`, `ProjectRunOutcome.tsx`, `delivery-route-run.ts` | MERGED (l2/a4): route-review + run/result sections, honest null projections |
| TD04, TD09, HC07 | `src/code/CodeWorkspace.tsx` + NEW `CodeWorkbench.tsx`, `attempt-fleet-read.ts` | MERGED (l2/a2): per-attempt facts via `readT3AttemptFleet`, execution-return panels, activity trail, return footer |
| TD05, TD11, HC17 | `src/resources/CapacityFabricRead.tsx` + `ModelConfigurationRead.tsx` | LIVE (pre-lane) |
| TD08, TD10 | Team responsive + zh strings | LIVE (pre-lane); mobile hardening in wave B css |
| TD12, TD13 | `ResourceCapacityRead` + retained panels | LIVE via real `readResourceCapacity` when a capacity attempt is selected |
| TD13 | teammate detail | LIVE (pre-lane) |
| HC02, HC03, HC09 (+HS02) | NEW `NewBotPanel`/`NewGroupPanel`/`BotSettingsPanel` (B1, in flight) | IN FLIGHT `l2/b1-team-conversation-surfaces` |
| HC05 | `src/team/DelegatedTaskCard.tsx` | LIVE (pre-lane), null-fed at mounts (producer upstream, see OWNER ASKS) |
| HC06 | Start coding → project/workspace | LIVE (pre-lane) |
| HC08 | `src/team/ResultReturnCard.tsx` | LIVE honest-null (producer upstream) |
| HC10 | NEW `RoutinesPanel.tsx` (B5) | MERGED (l2/b5); mount lands with the Team integration commit |
| HC11 | NEW `CodeSettingsPanel.tsx` (B5) | MERGED (l2/b5) + MOUNTED in `CodeWorkspace` (honest null provider/env sources) |
| HC12, HC18, HC19 (+HC22/23) | NEW `InboxNeedsYouPanel.tsx`, `ReplyThreadPanel.tsx`, `SplitConversationsWorkspace.tsx`, `conversation-surfaces.css` (B4) | MERGED (l2/b4); mount lands with the Team integration commit |
| HC13–HC16 | mobile variants of Team surfaces | covered by responsive css (wave B) |
| HC20, HC21 (+HC24) | NEW `SearchContextView.tsx`, `WorkHierarchyView.tsx` (B6, in flight) | IN FLIGHT `l2/b6-search-work-hierarchy` |

Extended companions: TB01–03/HB01–03 are meta/architecture boards (no UI);
TS02 is contract-only by census (see OWNER ASKS); TD05H host telemetry has no
qualified producer (honest state by design); HS01/HS04–08 map onto the same
components as their primary boards.

## Lane changes (trunk delta `85f0f91af..` lane HEAD)

1. **Native T3 attempt-fleet read (l2/a1)** — `read_t3_attempt_fleet` Tauri
   command (`src-tauri/src/auth.rs`) + `host.ts` native client method. Rust
   `t3_attempt_id_valid` mirrors `validT3AttemptId` byte-for-byte (grammar
   `[A-Za-z0-9][A-Za-z0-9_./:%=-]{0,159}`, closed secret refusal, case-
   insensitive); one signed GET, `bounded_json` cap 16 384, schema check
   `mastermind.t3_attempt_fleet/v1`, release-generation check. Closes the
   census gap "Fleet attempt block web-only": `T3AttemptFleetBlock` now reads
   on both transports.
2. **HC07 code workbench (l2/a2)** — per-attempt workbench consuming the fleet
   read + typed `execution_return/v1` props + retained-activity trail; honest
   states for every missing source (no invented deltas, no fake streaming).
3. **TD06/TD07 project journey (l2/a4)** — route-review and run/outcome
   sections on `ProjectDeliveryPanel`.
4. **Conversation surfaces (l2/b4)** — HC18/HC12/HC19 components (create-only).
5. **HC10/HC11 (l2/b5)** — Routines + Code settings panels (create-only);
   HC11 mounted in `CodeWorkspace` with honest null sources.
6. **Fleet→Code attempt context (lead)** — `AttendedFabricWorkspace` gains
   `onOpenAttemptInCode` (exact-run inspect only); App holds `codeAttemptId`,
   cleared by nav-rail Code entry; `CodeWorkspace attemptId` switches to the
   per-attempt workbench. Activity-selection ids (WS:/JOB-/ATT-) are a
   different id space and are deliberately NOT joined to T3 run ids.
7. **HC02/HC03/HC09 (l2/b1, in flight)** and **HC20/HC21 (l2/b6, in flight)**.

## Proven (commands + counts, lane worktree)

- `npm run typecheck` — clean at every merge (A1, A2, A4, B4, B5, HC11 mount,
  trunk merge).
- `npx vitest run src/team src/code src/projects src/fabric src/resources/T3AttemptFleetBlock.test.tsx src/resources/t3-attempt-fleet-contract.test.ts src/host.t3-attempt-fleet-read.test.ts` on the
  trunk-merged result — 45 files / 551 tests passed.
- After HC11 mount: `npx vitest run src/code/` — 4 files / 49 tests.
- `MM_SOURCE_REVISION=$(git rev-parse HEAD) MM_BUILD_IDENTITY=mastermind-os-review cargo check` (src-tauri, post-A1) — PASS (48s, 14 pre-existing warnings).
- `cargo test t3_attempt_fleet_read_tests` (A1 worktree) — 2/2.
- Paper parity: structure+copy extracted via `get_tree_summary` (committed in
  `BOARD_EXTRACTIONS.md`); visual parity pass pending at wave close.

## Honest-state law (binding on every surface)

Real projection or honest unavailable/unknown-with-reason — never Paper sample
data (names "Meta-CEO"/"Engineering"/"Secretary"/"Ryan", "12 teammates",
"Ubuntu 2", "DeepSeek Harness", sample times/counts), never fake success,
never zero-for-unknown. Fixtures live only in `*.test.*`. No send/launch/
dispatch path is faked: composers and submits without a backend render
disabled with a visible reason.

## OWNER ASKS (upstream producers, not this lane)

1. `delegatedTask`/`executionReturn` producers (App mounts render honest
   null states): `ChildExecutionRequest` v1.2 requester block (Director C2)
   and the execution-return read route (Director F gap list) are the missing
   sources.
2. `t3ThreadProjection` host source — `MastermindMissionHost.t3ThreadProjection`
   is implemented by no host; Code deep links render the honest wall naming it.
3. Qualified host-capacity producer for `HostTelemetryPanel` (`capacity` prop):
   `qualifyHostCapacityRead` requires an expected binding from existing
   Runtime/collector ownership; wiring it from browser selection is forbidden
   by the contract (`src/resources/README.md`). Owner: the server-side reader.
4. TS02 Teamlink surface: contract exists (`teamlink-contract.ts`), no view
   consumes it; a surface owner should be named if the board is promoted.
5. Conversation-search + routines-schedule + provider-configuration reads do
   not exist; the new surfaces render honest "not projected" states until
   they do.

## OPEN

- B1 (HC02/03/09) + B6 (HC20/21) merges, then the TeamWorkspace/TeamRoute
  integration commit mounting Routines/Inbox/ReplyThread/Split/Search/Work
  surfaces with real roster reads.
- Mobile hardening pass across the new css (TD08–TD13, HC13–HC16, HC22–24).
- One adversarial pass on the final lane delta (in flight on the merged base).
- Visual parity pass vs Paper (minimax-m3/gemini-4-argon) at wave close.
- Full `npx vitest run` + `cargo check` at release candidate, then trunk land.

# Work-to-Mission navigation leaf implementation plan

**Goal:** Give the existing Work view a tested, navigation-only Mission link without changing the incumbent app or transport writer's files.
**Architecture:** A pure resolver consumes an already-admitted Programs index and the selected Work root. A React leaf renders that result, retains the root on refusal, and emits only a valid pair to the existing navigation callback. It owns no acquisition, freshness, lifecycle, queue or authorization.
**Tech stack:** Existing locked React/TypeScript/Vitest; no new dependency.
**Spec:** Mastermind #948 comments 5809364311 and 5810099480; #600 checkpoint 5808685414. N9 Figma 163:188 and N9X 164:206 are visual/behavior references, not production state.
**Authority:** Current Chairman continuation of mastermind-os-vnext-convergence-20260924-sol-001. Direct principal work on these new paths only. The shared app/host/native owner is not replaced.
**Base:** 294b4c00ed668b497edb834be8108f14bc1bee8a.

## Constraints

- Exactly four new source/test paths below plus this plan. No edits to App.tsx, App.test.tsx, host.ts, styles.css, Rust, auth, producer or decoder ownership.
- Reuse normalizeSelection and programsFromControlRoom; never match titles, choose a recent root or coerce COO.
- Caller supplies whether Work remains admitted and acquisition is allowed. Those booleans are input gates, not a new grant or freshness clock.
- Unavailable Programs is not an empty index. A matching root in another returned candidate makes the link ambiguous.
- Work and Programs observations are independent. Navigation always re-enters the incumbent authorized Mission reader.
- Existing card/primary/muted CSS only. Component is not wired into App by this unit; no live Work-page claim.

## Task 1: exact resolver

Files: src/work-mission-link.ts and src/work-mission-link.test.ts under app/mastermind_os.
Interface: resolveWorkMissionLink({rootJobId, programs, acquisitionAllowed, workObservationAvailable}) returns RESOLVED with selection/title or UNAVAILABLE with reason; no I/O.

- Write tests using realControlRoomFixture through programsFromControlRoom; synthetic edits are labelled controls.
- Verify missing-feature RED, then an exported unavailable-only scaffold's positive-case RED.
- Implement one bounded pass: require both input gates; admitted AVAILABLE index; one exact normalized pair; singleton matching candidates; no competing mention. Refuse malformed/oversized index and duplicate work refs.
- Test missing, unavailable, conflicting, malformed, duplicate, nonmutating and title-independent cases.
- Run npm test -- src/work-mission-link.test.ts.

## Task 2: render and click

Files: src/WorkMissionLink.tsx and src/WorkMissionLink.test.tsx.
Interface: WorkMissionLink(props plus onOpenMission) renders raw root, optional qualified title, reason and one button. Recompute from current props at render/click; no asynchronous action ownership.

- Write a rendered positive test and observe RED before implementation.
- Add native button semantics, aria description and explicit navigation-only disclosure.
- Verify keyboard activation emits the exact tuple once. Verify auth/Work/Programs withdrawal, changed root, ambiguity and title injection on re-render cannot use the previous pair.
- Verify unmount has no callbacks or external effects.
- Run both new suites, typecheck and the complete existing frontend suite.

## Review focus

1. No lost old selection after re-render: current props determine each click.
2. No unsafe friendly title after join refusal: retain raw root only.
3. Another Program's candidate reference conflicts even when it is not RESOLVED.
4. Renderer treats source-provided title as inert React text.
5. Missing source/input permission disables navigation; no transport is invented.

## Acceptance ceiling and continuation

This unit is an independently testable leaf, not a shipped Work page. The incumbent consumes it when wiring released #943/#949/#950 through readWork, existing web/native auth and the N9 route. Independent review and natural CI precede source acceptance; installed authenticated proof is still owed.

## Execution evidence (source unit, not product acceptance)

- M1 baseline: locked `npm ci --ignore-scripts --no-audit --no-fund`; 267 passed / 1 existing skipped.
- Resolver RED: missing module, then explicit unavailable-only scaffold gave 9 failed / 9 passed. The unchanged recorded B5 input specifically failed expected RESOLVED. Initial table-driven candidate test syntax was corrected before implementation.
- Resolver GREEN: 18 passed and TypeScript check exit 0.
- Render RED: missing module, then a null component failed the positive raw-root/render/keyboard test. Render GREEN: 10 passed, including in-place conflict and no silent retarget, plus typecheck exit 0.
- Follow-up boundary cases cover the existing 500/50 limits, malformed row, valid-empty and unrelated-unresolved input.
- Workspace invocation disclosure: acquisition initially used the pinned versioned administrative seam. The installed `mmx-workspace` was then inspected and its read-only `status` recognized this exact operation/branch/path as PRESERVED_DIRTY, under the same installed source and workspace roots. No re-home, replacement workspace or cleanup was performed. Future workspace actions use the installed launcher.
- The Work reader, App wiring and installed authenticated journey are intentionally not included. No source or runtime custody was taken from #909/#943/#949/#950.

# O3 mount contract for S0

This directory is a presentation over Office's existing qualified Mission. It does not fetch a second Mission, enroll a session, create a source store, or start work. O3 remains **BUILT_NOT_PROVEN** until the original user journey is verified through the composed app.

## Apply one matching patch

| Integration source | Exact preimage | Patch |
| --- | --- | --- |
| Current S0/AppIntegration composition | `26604f550b42505808ea1b7ca2816be771aee5f5` | [s0-appintegration-mount.patch](s0-appintegration-mount.patch) |
| Incumbent #2180 Office/native source | `d7d5bfdb4bc656473a7e940dee07d0b437aed40d` | [incumbent-office-mount.patch](incumbent-office-mount.patch) |

These are **alternative preimages of one mount**, not cumulative patches. S0 owns the final shared App/Office/native join. Neither patch was applied to either incumbent worktree. The S0 patch preserves its current Work presentation, project journal, composer, criteria, preview and proposal changes. The #2180 patch preserves its Hermes panel and native routing. If either source advances or the two branches are joined, inspect the exact shared-file preimages and carry only the same minimal additions into that join.

Both patches passed an isolated Git index `git apply --cached --check` against the named commits. Read-only TypeScript 7.0.2 virtual compositions used the entire named production source plus the current O3 directory, with unchanged package locks: #2180 had 286 root files / 460 source files / zero diagnostics; S0 had 290 / 465 / zero diagnostics. These are composition checks, not an app install or authenticated-path receipt.

## Inputs and ownership

| Input | Existing owner and required behavior |
| --- | --- |
| `binding`, `missionState`, `missionProjection` | Pass Office's current projection/context directly. O3 reuses `completeMissionOfficeRead`, the actual Mission decoders, `missionInteriors` and `qualifyWorkerResultRef`. Target, auth generation, source revision and digest checks remain intact. |
| `loading` | Derive only from the incumbent pending acquisition, `LOCAL_UNAVAILABLE / SOURCE_READ_PENDING`. |
| `onOpenProjects`, `onOpenProject` | Reuse the existing navigation owner. Opening a project verifies current read permission and exact work/root before selecting Projects/Conversation. It does not assign or launch work. |
| `onInspectWorkerResult` | Pass App's existing exact-result callback. Keep the original project/root/job/attempt/envelope digest and current owner generation. |
| `planReader` | Move the existing admitted-plan inspector into this view using its current read, activity, generation and permission callbacks. Remove the old inspector instance; never mount both. |
| `observation` | Optional existing leadership observation. Only the incumbent host may associate the enrolled native session, viewer authorization and actual Mission revision. An absent binding stays explicitly unavailable. Never manufacture a current revision for an unrelated brief. |

Configured reporting/role charters remain advisory. They do not establish an enrolled session, available worker, executing Attempt, employment relationship, or company-wide agent count.

## External result return is still owed

At #2180's named head, `openOfficeWorkerResult` selects Projects/Overview and calls `pickResult`; Office consequently unmounts. O3's local search and selected row do not survive that unmount. The new internal Back/Escape behavior and same-target refresh preservation do not close this gap.

S0 must use the incumbent navigation/history ownership to preserve the original project, selected work, query and return focus while its existing result inspector opens. Keep the agreed mount inputs; do not introduce a parallel navigation store or new acquisition path.

Required acceptance case: choose a nonfirst row under a nonempty search, open its real retained result, return, and observe the same project/search/row and useful keyboard focus. Repeat across a current-source refresh. Revoke authorization while the inspector is open: the old result must be withheld, not restored as current.

## Remaining acceptance

The source guide is [OPERATOR_RUNBOOK.md](OPERATOR_RUNBOOK.md). The existing [O3 plan](../../../../docs/superpowers/plans/2026-11-07-paperclip-company-organization-bridge.md) and [S6 evidence](../../../../docs/evidence/organization-live-experience-20261107-c3/s6-qualification.json) retain exact test and negative-proof receipts.

After the single shared composition is qualified, verify current provider routing and draft/history continuity separately for DeepSeek and Hermes, then project/work/result Back, empty/denied/stale/partial states, EN/ZH, light/dark, keyboard, 390px and desktop. Record real load/navigation durations and errors. Existing S0 composer fixture screenshots do not prove the changed O3 view. No browser/native performance or S2/S3 assignment/worker execution acceptance is claimed.

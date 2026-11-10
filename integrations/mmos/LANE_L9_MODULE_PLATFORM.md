# Lane L9 — module platform (ledger)

Lead: L9 lane lead (glm-5.3). Principal: Fable program principal.
Plan: `PROGRAM_PLAN_V3.md`; method: `OPERATING_METHOD_V3.md` (+ V2 CI/review/return/safety).
Lane branch: `t3/mmos-v3-l9`. Trunk: `origin/feat/mmos-v1-integration-t3` (`46621f5ad` at lane
start; merged to `c0263d2d1` same day — see amendment below).
Evidence root: `~/.mastermind/mmos_evidence/l9-20261110/`.

Facts held at start (from brief, not re-derived):
- Default instance `http://127.0.0.1:3100`, prefix `MAS`, 13 agents, `hermes_local`, local
  trusted, launchd, embedded Postgres 54329. `GET /api/plugins` = `[]`. Port 3179 also taken.
- `paperclipai run -d <dir> -i <id>` and `paperclipai test-drive -d <dir> --no-browser` isolate
  from `~/.paperclip`. SDK: `~/.paperclip/cli/current/node_modules/@paperclipai/plugin-sdk/`.
- SDK caveats read by lead: `ctx.assets` unsupported in this build; local-path install is the
  dev workflow (needs writable FS + npm at runtime); plugin UI is trusted same-origin code,
  manifest capabilities are not a frontend sandbox; `runWorker(plugin, import.meta.url)` required.
- Default instance / `~/.paperclip/instances/default` / `~/.hermes` are READ-ONLY for this lane.

## Item state

| # | Item | Owner | State |
| --- | --- | --- | --- |
| 1 | Dev instance script + contract test | child glm-5.3 (`e56972f1`) | DEAD 08:13Z fabric cooling; relaunch queued (r2) |
| 2 | Module template + first module (`mastermind-core`) | lead + children | blocked on scout + item 1 |
| 3 | Platform proof in dev instance | lead | blocked on item 2 |
| 4 | Attack on item 3 | child grok-4.7 | blocked on item 3 |
| 5 | Module map of old app (+ amendment columns) | child glm-5.3 | DEAD 08:10–08:14Z (all 4 carriers); relaunch after r2 pair returns |
| 6 | Run-failure notes (default instance, READ_ONLY) | child glm-5.3 (`10a288da`) | DEAD 08:1xZ fabric cooling; relaunch after r2 pair returns |
| 7 | Dev skill `skills/mmos-module-dev/SKILL.md` | lead | blocked on item 3 |
| 8 | Cold-agent test (deepseek-v4.1-flash) | lead + child | blocked on item 7 |
| 9 | Runtime cannot do item 3 -> report at once | — | not triggered |

## Children log

| Time (UTC) | Model | Slice | Branch/attempt | Result |
| --- | --- | --- | --- | --- |
| 06:2x | glm-5.3 | item 1 dev instance | `e56972f1` | DEAD 08:13Z: 503 fabric routing refused, FABRIC_ALL_ROUTES_COOLING (no branch, no evidence pushed) |
| 06:2x | glm-5.3 | item 6 run failure notes | `10a288da` | DEAD ~08:1xZ: same 503 cooling (no branch pushed) |
| 06:26 | glm-5.3 | SDK scout (evidence only) | `fc2ebfd4` | DEAD 08:11Z: same 503 cooling (evidence dir empty) |
| 06:2x | gemini-4-argon (high) | item 5 module map | `6fc554e9` | DEAD: provider API 400 `thought_signature` missing in functionCall parts (Gemini-side schema failure; not a denial) |
| 07:00 | gemini-4-argon (high) | item 5 retry 1 | `0359ed93` | DEAD: identical 400 (launched from an errored parent turn; result was lost, lead unaware) |
| 07:16 | gemini-4-argon (high) | item 5 retry 2 | `02c856d3` | DEAD: identical 400 |
| 07:23–07:24 | glm-5.3 (high) | item 5 — FOUR carriers stacked | `722476d1`, `b34af5d8`, `5224d040`, `647e3c43` | ALL DEAD 08:10–08:14Z: 503 fabric cooling. Furthest was `b34af5d8` (100 items), none returned, none pushed a branch. Chairman ordered one writer per output; duplicates cancelled (already dead) |
| relaunch | glm-5.3 | SDK scout r2 (`clientRequestId: l9-scout-r2`) | — | pending |
| relaunch | glm-5.3 | item 1 r2 (`clientRequestId: l9-item1-r2`) | — | pending |

## Incident: how four duplicate item-5 children arose (for the improvement lane, per Chairman)

Cause: the parent (this lead) hit a run of internal tool-result-loss errors ("Tool result
missing due to internal error"). `delegate_task` calls landed server-side while their results
never returned, so the lead could not know a child had started and re-issued dispatches. Three
identical item-5 dispatches stacked within 07:23–07:24 alongside the lead's one deliberate
relaunch. The same turn also duplicated ledger edits (5x) — every call in it fired.

Contributing factor: 7 concurrent L9 children (plus a full fleet, ~20 threads) just before the
fabric entered all-routes cooling at ~08:10Z. Width is bounded by shared resources (method V3).

Fixes to propose to the improvement lane (L11):
1. `delegate_task` should honor `clientRequestId` as an idempotency key: a replayed dispatch
   with the same key returns the existing taskId instead of starting a second child. (This lane
   now sends `clientRequestId` on every dispatch as a workaround.)
2. A parent turn that reports lost tool results should trigger a `t3_thread_list` check before
   any re-dispatch of the same slice — surface this as a standing rule in the dev skill.
3. Fabric cooling response should be classified as a backoff signal for the WHOLE lane, not a
   per-task failure: on `FABRIC_ALL_ROUTES_COOLING`, a lead halts new dispatches rather than
   per-slice retrying into the same wall.

## Standing rulings recorded (2026-11-10)

- Chairman: `gemini-4-argon` is no longer used in this program — flaky, inconsistently priced.
  No new dispatch to it by this lead or any descendant. Designs/memos -> `glm-5.3` (effort
  high); attack/second opinion -> `grok-4.7`. (Consistent with the outage observed above: 3/3
  transport failures, distinct request ids.)
- Dispatch discipline for this lane until fabric health is proven: at most 2 concurrent
  children; every dispatch carries a `clientRequestId`; after any errored turn, re-read
  `t3_thread_list` before re-dispatching the same slice.

## Decisions / notes

- Lane branch named `t3/mmos-v3-l9` per LANDING (worktree was on
  `t3/l9-paperclip-module-platform`, same commit `46621f5ad`; branch created from it).
- Guard suites to run on new source at integration: identity/registry suites
  (`tests/test_installed_source_git_identity.py`, `tests/test_project_source_installed_registry.py`
  and neighbours) — verified by lead at merge time; fix source, never the guard.

## Plan amendment merged 2026-11-10 (trunk `c0263d2d1`)

Principal update applied; running children keep their original briefs and get the
delta as their rework round. Changes binding L9:

1. Item 5 (MODULE_MAP.md) gains two columns: "owner of the fact" (from the section 8a
   owner table: work item -> Paperclip; run -> Paperclip-on-Hermes-adapter; coding job
   -> Executive executed in T3; capacity/quota -> Capacity Fabric; identity/memory/
   conversation -> Hermes; workstream continuity -> Agent OS; code/PR/evidence ->
   GitHub; routine trigger -> one named owner) and "shell provides / module adds
   join / drop". Tasks, inbox, artifacts, routines, dashboard, costs are used as-is
   from Paperclip; the map must never propose rebuilding them. Not adopted: Paperclip
   experimental Runner; Paperclip agent chat as Hermes-conversation replacement.
2. Build order after `mastermind-core` (feeds item 5's ranked order):
   (a) roster-truth widget — four separate live counts (configured roles, enrolled
   agents, reachable agents, agents with active work), none hard-coded;
   (b) `detailTab` on a task for a coding job (Executive job/attempt ids, T3 thread
   link, state) — read-only shape + fixture data in L9; live wiring is L10;
   (c) capacity/quota widget that reads Capacity Fabric and never computes its own figures.
3. Module rules (go verbatim into the template README and the dev skill, item 7):
   - A module displays and joins; it never admits, schedules, retries or accepts work.
   - Ids of work item, coding job/attempt, native run, conversation and output stay
     separate fields, joined explicitly.
   - A widget never says "nothing needs you" unless it observed every source it
     covers; otherwise it names the source it could not read.
   - Produced / delivered / reviewed / accepted are four states, never one "done".
   - No module registers a scheduled job that duplicates a routine defined elsewhere.
4. DONE_WHEN 9–12 now exist program-wide (recovery without second launch; blocker
   visibility; output opened from task and conversation after reconnect, four states;
   routine single trigger owner). L9's item 3 proof of truthful state after worker
   kill/instance restart feeds DONE_WHEN 6.

## Returns to principal

**2026-11-10, close under PROGRAM_PLAN_V4 (L9 → test bed).** Items 1–3 proven
in the dev instance (`http://127.0.0.1:3190`, script
`tools/mmos_dev/paperclip_dev.sh`); evidence under
`~/.mastermind/mmos_evidence/l9r-20261110/`: plugin listed by API
(`plugins_listed.json`, `restart_plugins.json`); page + sidebar + roster-truth
widget render headlessly (`page_mastermind.*`, `page_dashboard.*`,
`widget_roster_truth.png`); `mastermind.core:roster-report` tool executed from
CLI with live counts (`tool_roster_report.json`); source edit visible after
reload without restart (`reload_before.json`/`reload_after.json`,
`moduleRevision` r2); logs on both surfaces (`logs_proof.txt`,
`logs_api_rows.json` — ctx.logger → server log, metrics.write → plugin_logs);
truthful state after plugin-worker kill (`worker_kill_*.json`: crash recorded,
auto-restart, state survived) and after instance restart (`restart_*.json`).
Module template + module README with rules verbatim landed. Adapter census for
the next lane: `adapters_listed.json` + `tools/mmos_dev/README.md`. Dropped
per V4 steer: module map work (already landed), cold-agent test, page/sidebar
polish, offline launcher refusal test (not started). Lane closed.

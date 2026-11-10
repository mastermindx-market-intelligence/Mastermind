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
| 1 | Dev instance script + contract test | child glm-5.3 | launched 2026-11-10 |
| 2 | Module template + first module (`mastermind-core`) | lead + children | blocked on scout + item 1 |
| 3 | Platform proof in dev instance | lead | blocked on item 2 |
| 4 | Attack on item 3 | child grok-4.7 | blocked on item 3 |
| 5 | Module map of old app (+ amendment columns) | child glm-5.3 (effort high) | running 2026-11-10, after route switch |
| 6 | Run-failure notes (default instance, READ_ONLY) | child glm-5.3 | launched 2026-11-10 |
| 7 | Dev skill `skills/mmos-module-dev/SKILL.md` | lead | blocked on item 3 |
| 8 | Cold-agent test (deepseek-v4.1-flash) | lead + child | blocked on item 7 |
| 9 | Runtime cannot do item 3 -> report at once | — | not triggered |

## Children log

| Time (UTC) | Model | Slice | Branch | Result |
| --- | --- | --- | --- | --- |
| launch | glm-5.3 | item 1 dev instance | t3/l9-dev-instance | pending |
| launch | gemini-4-argon (effort high) | item 5 module map | t3/l9-module-map | DEAD: provider API 400, `thought_signature` missing in functionCall parts (Gemini-side transport/schema failure; not a task denial, not a permission refusal) |
| ~07:00Z | gemini-4-argon (effort high) | item 5 module map, retry 1 (`0359ed93`, launched from an errored turn whose result was lost) | t3/l9-module-map | DEAD: identical provider API 400 |
| ~07:16Z | gemini-4-argon (effort high) | item 5 module map, retry 2 (`02c856d3`) | t3/l9-module-map | DEAD: identical provider API 400 |
| ~07:2xZ | glm-5.3 (effort high) | item 5 module map (`647e3c43`) — route switched after three identical transport failures on gemini-4-argon; that model's function-calling route is broken on capacity_fabric today. glm-5.3 is the method's co-designated model for census/statement outputs. Outage goes to the scoreboard in the next return. No partial branch was ever pushed by the dead children. | t3/l9-module-map | pending |
| launch | glm-5.3 | item 6 run failure notes | t3/l9-run-failure-notes | pending |
| launch | glm-5.3 | SDK scout (evidence only) | — | pending |

## Decisions / notes

- Lane branch named `t3/mmos-v3-l9` per LANDING (worktree was on
  `t3/l9-paperclip-module-platform`, same commit `46621f5ad`; branch created from it).
- Guard suites to run on new source at integration: identity/registry suites
  (`tests/test_installed_source_git_identity.py`, `tests/test_project_source_installed_registry.py`
  and neighbours) — verified by lead at merge time; fix source, never the guard.
- gemini-4-argon is UNUSABLE today for function-calling children on capacity_fabric
  (3/3 transport failures, distinct request ids). Do not route children to it until the
  provider route is fixed; use glm-5.3 (statement) or grok-4.7 (attack/diff) instead.

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

(none yet — first return due when items 1–3 pass)

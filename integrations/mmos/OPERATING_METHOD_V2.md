# MMOS program operating method V2 (Chairman directive 2026-11-10)

Binding on every agent in the Mastermind OS / Hermes Rev5 program from head `e6479f848` onward.
Mission and constraints are unchanged: `~/.hermes/profiles/engineering/mmos/T3_HANDOFF_V2.md`
(DONE_WHEN rows 1-7, section 6 failure matrix, section 7 hard constraints).

## Why this exists (measured, first 17 hours)

| Tier | Children | Agent-minutes | Share spent on the #2329 shell guard |
|---|---|---|---|
| Opus 5.5 | 26 | 985 | 674 min (17 children, r6 to r13, nine distinct reviews) |
| GLM 5.3 | 21 | 925 | 0 |
| Flash leaves | 0 | 0 | n/a |

No DONE_WHEN row is installed-proven. Product lanes idled while one CRITICAL row looped
serially through Opus author plus Opus reviewer. CI was dispatched on about ten intermediate
heads and the principal watched it. Those three habits end here.

## Graph

```
Fable meta-orchestrator   decisions, briefs, acceptance of lead reports, continuity. No merges,
  |                       no test runs, no CI reads, no fix commits.
  +- Integrator (GLM 5.3, one bounded task per merge wave; sole writer of the build branch)
  +- Lane leads (GLM 5.3 by default; Opus only for the single hardest lane)
       +- Workers (GLM 5.3) and leaves (deepseek-v4.1-flash, glm-5.3-flash, minimax-m3.1-flash)
```

- Leads delegate. A lead that types more than a few hundred lines itself is doing it wrong:
  split into disjoint-file leaves, verify their diffs, integrate inside the lane branch.
- Max 4 concurrent children per lead, depth stops at the leaf. Never inherit a model: every
  `delegate_task` names `target: {providerInstanceId: "capacity_fabric", model: <id>}`.
- Children get only their brief. Give goal, exact paths, the test command, and the return format.

## Model tiers (cheapest tier that can do the job)

| Work | Model |
|---|---|
| Lane lead, integrator, implementation, routine review | `glm-5.3` |
| Bounded leaf: one file, one test row, one board, census, extraction | `deepseek-v4.1-flash`, `glm-5.3-flash`, `minimax-m3.1-flash` |
| Vision / Paper parity check | `minimax-m3`, `gemini-4-argon` |
| Cheap adversarial second opinion on a diff | `grok-4.7`, `gemini-4-argon` |
| CI steward (dispatch, wait, classify, rerun infra-only) | `glm-5.3-flash` or `deepseek-v4.1-flash` |
| Hardest lane lead, one final CRITICAL review bundle | `claude-opus-5-5` (effort high, not xhigh) |
| Fable-grade escalation when Opus is unavailable or fails | `kimi-k3.1-pro` |

Escalate one tier only after the cheaper tier failed twice on the same bounded problem, and say so.

## CI and release rule

1. Lane gate: the lane's affected tests, run locally by the lane.
   Python: `env -u PYTHONPATH /opt/homebrew/bin/python3.12 -m pytest -q <files>`.
   Frontend: `npm run typecheck` and `npx vitest run <files>` in `app/mastermind_os`.
2. Merge gate: the integrator's union of touched suites on the build branch. Push after every merge.
   A push does not start CI on this branch.
3. GitHub CI runs once, on the release candidate head, after every lane is integrated. A flash-tier
   steward owns the run. Nobody above flash tier waits on, polls, or reads CI.
4. Installed acceptance is built from the release candidate head and does not wait for CI or the
   protected merge. Publication (#2338 update, Ready, queue, merge readback) is a parallel tail.
5. Never weaken a gate, self-approve, push master, or bypass the queue. Speed comes from not
   waiting, not from skipping.

## Review rule

- Each lane diff gets one cheap adversarial pass (GLM, Grok or Gemini) inside the lane.
- CRITICAL rows (auth, permissions, exactly-once, release automation, identity pins) get one
  distinct Opus READ_ONLY bundle review at the release candidate, covering all deltas since the
  last accepted review. Not per delta.
- Stop rule: two rework rounds on one finding family, then the principal makes a structural
  decision (narrow the feature, fail closed, or pin a documented limit). No third round.
- Guard #2329: re-check #9 returned ACCEPT on r13 (`REVIEW9_GUARD_R13_OPUS_20261110.md`).
  The lane is closed. Its minors are pinned as documented limits by a leaf. No r14.

## Return format (every lead, at most 40 lines)

`STATUS` DONE / PARTIAL / BLOCKED, `BRANCH@SHA` pushed to origin, `PROVEN` by test or live with
the command and counts, `FILES` touched, `PIN MOVES`, `OPEN` items, `OWNER ASKS` with the exact
act and owner. Long evidence goes in the lane ledger under `integrations/mmos/`, not in the reply.

## Safety that does not change

Handoff section 7 in full. Read-only on `~/.hermes` profiles, never restart the Hermes gateway,
never edit #2351, #2182, #2177 hunks, #2186, #2342 live. One writer per checkout. Commit and push
the lane branch often: a worktree was wiped once mid-run on 2026-11-10.

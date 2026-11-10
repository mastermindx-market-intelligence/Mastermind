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

## Graph (revised 2026-11-10, Chairman directive: leads fan out, they do not type)

```
Fable meta-orchestrator   decisions, briefs, acceptance of lead reports, continuity. No merges,
  |                       no test runs, no CI reads, no fix commits.
  +- Lane lead            plans, splits, briefs, verifies returns, integrates, lands on the trunk.
       |                  Writes no implementation and runs no long investigation itself.
       +- Sub-lead        owns one slice of the lane end to end (GLM 5.3 or Gemini 4 Argon)
       |    +- Workers    Grok 4.7, GLM 5.3, DeepSeek V4.1 Flash
       +- Workers         direct leaves for slices too small to need a sub-lead
```

- Delegation is the default, lead labour is the exception. Before a lead opens an editor or
  starts a multi-step investigation it asks: can a worker do this from a written brief? If yes,
  it spawns. A lead may itself do only: reading enough to split the work, writing briefs,
  checking returned evidence, merge and conflict resolution, the trunk push, and a fix of at
  most about 30 lines when briefing would cost more than the fix. Anything larger done by the
  lead is reported in its return under `LEAD LABOUR` with the reason.
- Fan-out: up to 12 concurrent children per lead and 8 per sub-lead, three levels below Fable
  (lead, sub-lead, worker). Launch independent children in one batch, not one at a time. If the
  runtime refuses a nested `delegate_task`, the parent keeps those workers as its own direct
  children; nobody falls back to doing the work alone.
- First act of every lead: a split plan of at least four parallel slices (or a one-line reason
  the lane cannot be split), launched before any other work.
- Cross-model pairs are the standard unit: one model writes, a different model checks. GLM 5.3
  writes and Grok 4.7 attacks, or the reverse. Two cheap models that disagree are worth more
  than one expensive model that is alone.
- Never inherit a model: every `delegate_task` names
  `target: {providerInstanceId: "capacity_fabric", model: <id>}`. One writer per checkout:
  writing children use `isolation: "worktree"` or disjoint files in the parent's lane.
- Children get only their brief. Give goal, exact paths, the test command, and the return format.
- Evidence rule, every model, every level: a child's claim counts only when the parent has
  opened the artifact itself (commit SHA on the branch, test output file, capture on disk,
  command transcript). Grok 4.7 returned invented statistics once and reported captures that
  did not exist once in this program, so prose-only returns are rejected, not trusted.

## Model tiers (cheapest tier that can do the job)

| Work | Model |
|---|---|
| Core fleet: lane lead, sub-lead, implementation, integration, routine review | `glm-5.3` |
| Core fleet: implementation worker, adversarial check of a diff, vision, computer use (app click-through, captures) | `grok-4.7` |
| Bounded worker: one file, one test row, one board, census, extraction, log reading | `deepseek-v4.1-flash` (first choice), `glm-5.3-flash`, `minimax-m3.1-flash` |
| Opus-grade judgment at lower cost: hard diagnosis, design of a risky change, CRITICAL-row pre-review, lead of a hard lane | `gemini-4-argon` |
| Vision / Paper parity check | `grok-4.7`, `gemini-4-argon`, `minimax-m3` |
| CI steward (dispatch, wait, classify, rerun infra-only) | `deepseek-v4.1-flash` or `glm-5.3-flash` |
| Lead of the single hardest lane, one final CRITICAL review bundle | `claude-opus-5-5` (effort high, not xhigh), and it still fans out as above |
| Fable-grade escalation when Opus is unavailable or fails | `kimi-k3.1-pro` |

Opus and Kimi are not needed for anything GLM, Grok, Gemini or DeepSeek can do. Escalate one
tier only after the cheaper tier failed twice on the same bounded problem, and say so.

## CI and release rule

1. Lane gate: the lane's affected tests, run locally by the lane.
   Python: `env -u PYTHONPATH /opt/homebrew/bin/python3.12 -m pytest -q <files>`.
   Frontend: `npm run typecheck` and `npx vitest run <files>` in `app/mastermind_os`.
2. Merge gate (trunk-based, no per-lane PR): the lead fetches `origin/feat/mmos-v1-integration-t3`,
   plain-merges it into the lane, runs the lane's affected suites on the merged result, then pushes
   `HEAD:feat/mmos-v1-integration-t3` without force. A rejected push means someone landed first:
   fetch, merge, retest, push again. Land small and often. A push does not start CI on this branch.
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
act and owner, `FLEET` (children launched per model, accepted, rejected) and `LEAD LABOUR`. Long evidence goes in the lane ledger under `integrations/mmos/`, not in the reply.

## Safety that does not change

Handoff section 7 in full. Read-only on `~/.hermes` profiles, never restart the Hermes gateway,
never edit #2351, #2182, #2177 hunks, #2186, #2342 live. One writer per checkout. Commit and push
the lane branch often: a worktree was wiped once mid-run on 2026-11-10.

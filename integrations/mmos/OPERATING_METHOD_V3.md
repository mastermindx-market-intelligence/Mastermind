# MMOS program operating method V3 (2026-11-10)

Supersedes `OPERATING_METHOD_V2.md` for graph shape, fan-out and model routing. V2's CI and
release rule, review rule, return format and safety section stay in force and are not repeated.
Mission and constraints: `~/.hermes/profiles/engineering/mmos/T3_HANDOFF_V2.md`.

The Chairman asked the principal to decide the fan-out design on evidence rather than adopt his
estimate. This is that decision. It changes when the scoreboard at the end says it should.

## What the evidence says

| Observation (this program) | Consequence |
|---|---|
| First 17 hours: 47 children, 2 grandchildren. The per-lead cap of 4 was never reached. | The limit on fan-out was never the cap. It was briefs that handed a lead one serial task with no side work named. |
| 674 Opus minutes went to one serial write-review loop on the shell guard. | Serial loops, not lead typing, were the largest waste. V2's stop rule fixed it. |
| The UI lane split 34 boards across workers and landed 34/34. | Fan-out pays where slices are disjoint and each has its own check. |
| The live activation ladder (R1 to R9) is a chain: each step needs the state the last one left. | A chain cannot be fanned out. Only the work beside the chain can. |
| Grok 4.7 returned invented statistics once and reported captures that did not exist once. Both were tasks whose output was a statement, not a checkable artifact. | Route by how checkable the output is, not by model reputation. |
| A GLM desktop child uploaded full-desktop screenshots that included a private window; sibling agents moved windows under it. | The desktop is a single-writer resource. Width is bounded by shared resources. |
| Wave of 2026-11-10 04:54 UTC: three GLM leads launched 15 children in five minutes across GLM, Grok, Argon and DeepSeek when the brief named the slices. | Leads fan out when the commission shows the seams. No quota is needed. |

## The decision test (replaces all quotas)

Before starting any piece of work, its owner asks three questions.

1. Separable: can someone do it from a written brief, on files or resources nobody else is
   writing, without the owner's context?
2. Checkable: is there a mechanical check of the result (a test, a command that reproduces,
   an artifact that can be opened)?
3. Cheaper to brief than to do: is writing the brief and checking the return less work than
   doing it?

Three yes: delegate. Any no: the owner does it, or first does the small piece of work that
turns the no into a yes (name the interface, write the failing test, freeze the decision).
There is no minimum number of children and no maximum other than the limits below.

## Four shapes, chosen per task

| Shape | Use when | How |
|---|---|---|
| Fan-out and join | Disjoint slices, each with its own check (boards, test rows, files, producers) | One worker per slice in one batch. The lead owns the join and runs the joined suite. |
| Driver and side crew | A stateful chain (live ladder, install, migration) | One driver holds the state and runs the chain alone. Everything off the chain runs beside it: the next step's preconditions, receipts, tests, rollback, the decision memo for the next gate. The driver may be the lead. |
| Two investigators | The cause or the right design is unknown | Two cheap models answer the same question independently, each with raw evidence files. Agreement is accepted. Disagreement goes to `glm-5.3` at effort high with both files (or the lead decides on the raw evidence). Then execute. |
| Writer and attacker | A diff on a risky surface | One model writes, a different model attacks and must return a reproducing command for each finding. Two rounds at most (V2 stop rule). |

Depth: two levels below the principal (lead, workers) by default. A sub-lead is added only
when a slice has its own join of three or more parts. Every level adds a summary hop that
loses detail and a verification hop that costs the parent.

## Limits that actually bind

- Integration capacity. A parent holds at most 6 returns it has not yet verified. At 6 it
  stops launching and verifies. Unverified work is inventory, not progress.
- One writer per surface: a checkout, the trunk push (non-force, retry on reject), the
  installed app, the desktop, the scratch Executive root.
- The desktop: one GUI-driving child at a time, window-scoped captures only, accessibility
  text before images, 20-minute time box.
- Owner-held resources are read-only for every agent: the production Executive and its Worker,
  hold #1893, `~/.hermes` profiles and the gateway, the VPS.
- Ceiling, not target: 12 concurrent children per lead, 8 per sub-lead.

## Provider failures and dispatch discipline (added 2026-11-10, after the router outage)

What happened: every lead and most children ran on `glm-5.3`. Its keys ran out of quota, the
fallback route refused the model, and the router restarted about forty times. Five leads and
about thirty children died together. Leads that stayed alive re-sent dispatches they could not
see had landed and stacked up to five writers on one output. Four to five hours of work sat
uncommitted in dead checkouts.

- Lanes are spread across at least two models. No model carries more than about half of the
  running drivers.
- A provider or transport failure is not a task failure. On `ECONNRESET`, `ECONNREFUSED`,
  HTTP 429 or 503, `FABRIC_ALL_ROUTES_COOLING`, or "tool result missing": stop dispatching.
  Do not re-send. List threads by title (`t3_thread_list`, `includeSubagents`) to see what
  actually started. Commit and push what exists. Return to the parent with the state.
- Every `delegate_task` carries a unique `clientRequestId`. One writer per output: before any
  dispatch that follows an errored turn, list same-title children first.
- Work is pushed to the lane branch on origin after every slice that passes its check, and at
  least every 30 minutes of work. An outage should cost minutes.
- This wave runs as drivers with a side crew: the driver does the stateful chain itself and
  holds at most 3 children at a time. The machine sits at a load of 45 on 24 cores; width is
  not free.
- The principal checks the router before a wide launch: one small request per model to
  `127.0.0.1:8313`, and the refusal classes in the router's `logs/stderr.log`.

## False completion reports (added 2026-11-10, wave 3)

What happened: a `grok-4.7` driver for lane L6 ran 17 commands in 100 seconds and returned a
full report: four commit ids, test counts, an evidence directory, an attack by a child. None of
it existed. It had also added a second remote to the shared git store and fetched a branch with
`--depth=1`, which marked the whole store shallow for every checkout until the principal removed
the marker.

- A return counts only after the parent ran three checks: `git cat-file -e <sha>^{commit}` for
  every commit named, `git ls-remote origin <branch>` for every push named, `ls` for every
  evidence path named. A task that returns in under five minutes is checked before anything else.
- Every driver brief ends its return format with the literal output of `git rev-parse HEAD`,
  `git ls-remote origin <lane branch> <trunk>` and `ls <evidence dir>`.
- Every brief says that "NOT DONE, because <reason>" is an accepted return.
- Shared git store: children never add or remove a remote, never fetch with `--depth`, never
  run `git gc`, `git prune`, `git stash` or `git worktree remove`. Salvage branches are named
  as local branches and merged directly.
- `grok-4.7` does not drive lanes or write diffs. It keeps one output type: an attack, where
  each finding is a command the parent runs.

## Model routing by output type

| The output is | Check | Models |
|---|---|---|
| A diff with a test that passes | Run the test | `deepseek-v4.1-flash` first, `glm-5.3`, `kimi-k3.1-pro` |
| An attack on a diff | The reproducing command | `grok-4.7`, `glm-5.3` (a different model from the writer) |
| A statement: census, diagnosis, "I observed X" | Raw output files the parent opens; two independent models when it gates a decision | `glm-5.3`; `grok-4.7` only as the second investigator |
| A design or a decision memo | The principal or lead reads it; options carry exact commands | `glm-5.3` at effort high; `grok-4.7` as the second read (`deepseek-v4-pro` had no live route on 2026-11-10) |
| Desktop or app driving, visual comparison | Window-scoped capture plus accessibility text on disk | `grok-4.7`, `minimax-m3` |
| Lane leadership (long reading, briefing, joining) | The lane's joined suite and its ledger | `glm-5.3`; `kimi-k3.1-pro` on trial from wave 3 (L6s, L8s) |
| CI steward | Run conclusion | `deepseek-v4.1-flash`, `glm-5.3-flash` |
| The one CRITICAL review bundle at the release candidate | Findings with reproductions | `claude-opus-5-5`, effort high |
| Escalation after two failures of the tier below | Same check | one tier up; `kimi-k3.1-pro` last |

Cheap tokens are spent on redundancy (a second independent attempt, a cross-model check), not
on depth. `gemini-4-argon` is not dispatched (Chairman ruling, 2026-11-10). Never inherit a model: every `delegate_task` names
`target: {providerInstanceId: "capacity_fabric", model: <id>}`.

## Commissions

- The principal commissions an outcome with its constraints and names the seams it can see.
  The lead may redraw the split and says so in its return.
- A brief carries: goal, why it matters, exact paths and revisions, the check, write scope,
  what is reserved, the return format. Not the parent's transcript.
- Gates held by an owner are found in the first hour by a decision memo, not at the end.
- Evidence rule (unchanged): a claim counts only after the parent opened the artifact.

## Scoreboard (updated by the principal after each wave, from the leads' `FLEET` lines)

| Model | Tasks | Accepted first pass | Rejected | False reports | Notes |
|---|---|---|---|---|---|
| `claude-opus-5-5` | 26 | not recorded | not recorded | 0 | 985 min; 674 on one loop |
| `glm-5.3` | 21 + wave 2 | not recorded | not recorded | 0 known | one wrong outage verdict (probe of a path the edge drops) |
| `grok-4.7` | 2 + wave 2 + 2 drivers | 0 | 3 | 3 | two statement-type tasks; one lane driver (L6r) that invented commits, tests and evidence. Second driver (L8r) cancelled at 6 minutes with no work. Attacks only from wave 3. |
| `kimi-k3.1-pro` | 2 drivers running (L6s, L8s) | pending | pending | pending | first use as a driver |
| `gemini-4-argon` | withdrawn | n/a | n/a | n/a | **Not used from 2026-11-10 (Chairman ruling): flaky and inconsistently priced.** Dispatches also died mid-run on a provider function-call error. |
| `deepseek-v4.1-flash` | wave 2 (4 running) | pending | pending | pending | no evidence yet in this program |

Routing moves with these numbers. A model with two false reports on one output type loses that
output type. A model with five first-pass accepts on an output type becomes first choice there.

# Hermes Team Orchestration V1 — operating record

Status: **live and field-proven 2026-11-07** (commission: issue #2198, follow-on to PR #2201).
This document is the durable repo-side record of Team Orchestration V1: the org model, the
native Hermes mechanisms it is built on, what was changed on the operator workstation, the
field proof (a real six-card mission across five seats executed under adversarial test), and
the remaining gates. The deployment itself lives on the operator workstation
(`~/.hermes/profiles/` + `~/.hermes/config.yaml`), not in this repo;
`integrations/hermes_leadership/charters.py` remains the charter canon.

This is a dated record of the operator's 2026-11-07 report, not a fresh
verification of current runtime health or authority for a new restart,
reclaim, force, dispatch or routing change.

## Roles (bound to charter canon)

| Seat | Profile | Charter key | V1 accountability |
|---|---|---|---|
| Chairman (Chris) | — | human | Instructions, gates, acceptance of consequences |
| Meta-CEO | `meta-ceo-uncensored` | `meta_ceo` | Strategy, decomposition, prioritization, cross-specialist decisions, final integration & acceptance |
| Chief of Staff | `chief-of-staff` | `secretary` | Mission tracking, dependency resolution, delegated-result consumption, follow-through, progress reporting |
| Engineering | `engineering` | `engineering` | Architecture, implementation, technical integration |
| Delivery | `delivery` | `delivery` | Eligible-frontier advancement, continuity |
| Reliability | `reliability` | `reliability` | Health, capacity, cost telemetry |
| Product | `product` | `product` | User journeys, workflow |
| Intelligence | `intelligence` | `intelligence` | Grounded intelligence, data quality |
| Assurance | `assurance` | `assurance` | Adversarial verification of consequential claims |

Meta-CEO may commission specialists directly; nothing forces routing through the Chief of
Staff. Specialists may use qualified Subagent Fabric workers for sub-delegation (V1 proof ran
specialists directly; no second router was introduced).

## Native mechanisms V1 is built on (no new task store, scheduler, broker or router)

The shared kanban board (`~/.hermes/kanban.db`, board `default`) is the only task store.

- **Composition**: `kanban create` (assignee, created-by, idempotency-key, per-task overrides) +
  `kanban link parent child` = prerequisite edge. The child's claim **and** completion are both
  gated on all parents being `done` (`unsatisfied_parents`); `ready→todo` demotion when a parent
  is open. The **acceptance card is created first**, holds the Chairman instruction verbatim,
  and is gated on every leaf card: original-parent acceptance is enforced by the kernel, not by
  etiquette.
- **Autonomous progression**: the in-gateway dispatcher (`kanban.dispatch_in_gateway`, tick
  `dispatch_interval_seconds: 60`) claims eligible cards (atomic CAS on
  `status='ready' AND claim_lock IS NULL`), spawns each assignee profile as an isolated worker
  (`~/.hermes/kanban/workspaces/<task_id>/`), reclaims crashed/stale workers, auto-requeues
  rate-limited attempts, and auto-blocks (`gave_up`, sticky) after consecutive non-success
  failures (`failure_limit: 2`; rate-limit attempts never count).
- **Admitted execution**: spawned workers are admitted against their run
  (`owner_admitted`); workers exiting rc=0 without a terminal kanban call are booked as
  `protocol_violation` (bounded to 3 before failure accounting) — narration is not completion.
- **Verified results**: completion requires non-empty evidence (`EmptyCompletionError`),
  a goal-gate judge against the card's acceptance criteria, and structured `--summary/--metadata`
  handoffs; downstream cards receive upstream handoffs via `hermes kanban context`.
- **Result return**: attributed completion comments + native attachments
  (`~/.hermes/kanban/attachments/<task_id>/`) — assignment and result-return ARE the board.
- **Wake/continuation**: `auto_subscribe_on_create` — the composing session is auto-subscribed
  to completion/block events of its cards; the gateway delivers each terminal event back into
  the creator's session as a fresh turn. No cron, no polling loop, no second watcher.
- **Cost attribution**: worker sessions record `input_tokens/output_tokens/…
  actual_cost_usd` in each profile's `state.db`; the acceptance gate joins them per card.
  Provider pricing is currently UNCONFIGURED estate-wide (`actual_cost_usd` NULL on 225
  sessions at acceptance time) — tokens are the only usable meter today (see gaps).

## What V1 changed on the operator workstation (2026-11-07)

Backups:`~/.hermes/profiles` reverted copies under `~/hermes-specialists/orchestration-v1-backup/`.

1. **`meta-ceo-uncensored`**: SOUL.md replaced (was generic "Uncensored" boilerplate) with the
   meta_ceo charter mirror + the Orchestration V1 procedure (compose acceptance-first, gate it
   on leaves, verify by re-derivation, accept with cost metadata). Model default switched
   local `qwen3:14b` → `glm-5.3` (provider `zai`), matching the Chairman's standing apex
   decision and the specialist baseline. `toolsets: [hermes-cli, kanban]` added for in-session
   board tools.
2. **`chief-of-staff`**: `toolsets: [hermes-cli, kanban]` added; SOUL.md extended with V1
   operational-coordinator duties (frontier sweeps, delegated-result re-derivation, grouped
   progress reporting). Seat model routing was changed repeatedly during the flight by a
   concurrent operator (qwen3:14b → byteplus variants → deepseek-v4-pro @ `byteplus-coding`);
   final working route is the Chairman's, left in place.
3. **`~/.hermes/config.yaml`** (gateway home): `kanban.max_in_progress: 2`,
   `kanban.max_in_progress_per_profile: 1` — concurrency caps proven necessary (below). They
   arm on the next gateway restart; the running multiplexer did not reload them mid-flight
   (restart was correctly refused: 8–9 live sessions, including an active Chairman session).

## Field proof — mission "Team Orchestration V1 Field Proof"

Chairman instruction was relayed once, as a single one-shot brief to `meta-ceo-uncensored`.
Everything after that one message — composition, all five deliverable executions, verification,
monitoring, and original-parent acceptance — progressed autonomously on the mechanisms above.

**Card graph** (composed by Meta-CEO in its first turn; acceptance card created first, idempotency
keys `orchv1-*`):

| Card | Deliverable | Seat | Outcome |
|---|---|---|---|
| `t_4556cfee` | ACCEPT: original-parent acceptance (gated on leaves) | meta-ceo-uncensored | done — ACCEPTED, run 30 |
| `t_45effb9c` | ENFORCEMENT_MAP.md (16,374 B, 42 file:line citations) | engineering | done, run 18 (after 4 attempts incl. SIGKILL) |
| `t_1cf471e4` | BOARD_HISTORY.md (31,717 B + 8 raw evidence files) | intelligence | done, run 19 |
| `t_3e4237b2` | CAPACITY_SNAPSHOT.md (9,683 B, 10 profiles) | reliability | done, run 20 |
| `t_eaaa7f69` | VERIFICATION.md (20,587 B), gated on all three wave-1 cards | assurance | done, run 25 — **6/6 re-derived claims PASS + denial test** |
| `t_96b6eb64` | Mission monitor note (4,887 B), progress censuses on acceptance card | chief-of-staff | done, run 29 (9 attempts, all infra-class) |

The dated mission report records 282 events, 12 comments and 21 worker sessions.
Its cited event-ID window is 107–371 inclusive, which contains 265 possible
integer IDs. The 282-event total and that window have not been reconciled to
the same counting scope; 265 is not a re-count of the board. The reported run
outcomes are 6 completed, 13 crashed, 1 rate_limited and 1 reclaimed. The report
records zero false completions and identifies `protocol_violation` events
263/288 as narration without terminal completion.

### Adversarial test results (all by the Chairman's integrator, all live)

1. **Intake/decomposition (T1)**: Meta-CEO composed the six-card graph with correct gating in
   its first turn using in-session kanban tools — real tool execution proven in its agent.log.
2. **Parallel delegation (T2)**: 4 wave-1 workers claimed + spawned in one sweep
   (`ps` pids 84438/84443/84444/84448; gateway log `spawned=4`).
3. **Autonomous progression (T3)**: every wave advanced via the 60s dispatcher alone; the only
   human actions during flight were recovery interventions *provoked by adversarial tests*
   (below) — no hand-dispatching, no prompt-pushing of specialists.
4. **Dependency handling (T4)**: assurance card stayed `todo` until all three parents
   completed, then auto-promoted to `ready` (`recompute_ready`); acceptance card likewise
   opened only after its parents (monitor + verification) completed.
5. **Interruption/restart recovery (T5)**: external `SIGKILL` of one running worker (10:38:42Z).
   - The killed card: crash sweep detected (`crashed:["t_45effb9c"]`), auto-returned to `ready`,
     respawned, and **completed** (4 attempts total, honest event trail).
   - Blast radius (finding): the SIGKILL severed the whole 4-worker spawn cohort — 3 siblings
     died with `Kanban owner refused: Kanban execution unknown` / state.db save refusals; the
     dispatcher classified them infra-class, sticky-blocked for operator review, then
     auto-requeued on the next passes once host CPU pressure eased. All four recovered with
     **zero lost or duplicated work**.
   - Operational note: sustained 4-way worker concurrency on a CPU-saturated host starves the
     gateway event loop (>10s stalls observed). Cap `max_in_progress: 2` is armed in config;
     the flight completed without a gateway restart (restart correctly refused while
     Chairman/delegation/agent sessions were live).
6. **Wrong-role denial (T6)**: three foreign-context attempts, all refused with verbatim
   CLI lines (rc=1): claim on running card (`status=running lock=…`), completion while a live
   worker owns the card, and out-of-order completion on a gated card
   (`unsatisfied parent dependencies: … complete the parents first`). Assurance independently
   reproduced a denial (`kanban: delegate_task child contexts cannot mutate Kanban tasks via the
   CLI`, guard at `hermes_cli/kanban.py:154`).
7. **Duplicate-dispatch prevention (T7)**: a racing `hermes kanban dispatch --max 3 --json`
   pass while wave 1 was running spawned nothing (`"spawned": []`) — CAS claims hold.
8. **Cost attribution (T8)**: acceptance gate joined 21 worker sessions: **867,622 input /
   173,439 output tokens**; per-card table in ACCEPTANCE.md. `actual_cost_usd` is NULL on all
   estate sessions (provider pricing not configured) — reported honestly, not fabricated.
9. **Integrated results + original-parent acceptance (T9)**: ACCEPTANCE.md (in
   `~/.hermes/kanban/attachments/t_4556cfee/`) — the acceptance gate re-derived every
   assurance claim (shasum, source line reproduction, event re-query, census re-count, refusal
   byte-match) and published known gaps. Imprecision noted by the integrator: its artifact
   table cites `workspaces/` paths for three artifacts that actually live in the native
   `attachments/` tree (hashes and bytes match either way).

### Mid-flight events worth recording

- Meta-CEO's composing session was **woken automatically** by card events (auto-subscription)
  and independently re-derived delegated results as they landed — no scheduler involved.
- A Meta-CEO "orchestration decision" comment (serialization after the crash storm) was
  honored as *advisory*: the dispatcher is the mechanical enforcer; frontier shaping happens
  via block/unblock/priority/caps. Documented as a V1 operating nuance for staff.
- The Chief of Staff seat went through a concurrent routing churn (local `qwen3:14b`
  tool-JSON degradation → byteplus 404/quota 429s → chairman-set `deepseek-v4-pro` @
  `byteplus-coding`, which served). The dispatcher's `rate_limit_cooldown` (300s, attempts
  never count as failures) absorbed the churn; the monitor card ultimately completed with a
  full census + progress comments. Lesson: weak local models narrate instead of emitting
  tool JSON; route operational seats at qualified capacity or expect reclaim loops.

## Operating conventions going forward

1. Chairman → Meta-CEO: one brief (one-shot chat). Meta-CEO composes the card graph
   (acceptance first, gated on leaves; parallel cards unlinked; dependent cards linked
   prerequisite→dependent; an assurance verification card for consequential missions).
2. Meta-CEO may assign any specialist directly; brief the Chief of Staff when a mission
   starts so it tracks, sweeps and reports.
3. Workers own completion evidence: artifacts under the task workspace/attachment tree,
   completion summaries quoting exact ids/timestamps/command outputs.
4. Acceptance = re-derivation, not trust: the acceptance seat recomputes load-bearing
   claims (shasum, rev-parse, sqlite) before completing the acceptance card, with token/cost
   metadata attached.
5. Recovery discipline: infra-class failures sticky-block for review; operator unblocks with
   reasons; rate-limit cooldowns absorb provider churn; never hand-force a running card
   (`reclaim`/`--force` are the sanctioned verbs, with reasons).

## Remaining gates (honest)

1. Provider pricing unconfigured → `actual_cost_usd` NULL estate-wide; token counts are the
   only meter. Chairman/Capacity decision required to wire pricing.
2. Gateway restart still owed (concurrency caps `max_in_progress: 2` / per-profile 1 armed in
   config, not yet loaded by the live multiplexer at time of writing; restart correctly blocked
   by live sessions).
3. Chief of Staff seat routing was churning during the flight (now serving on
   `deepseek-v4-pro`); a settled qualified route for that seat should be recorded when stable.
4. Advisor/External bot budget policy and Slack cutover remain Chairman-gated (unchanged).
5. Per-task model override exists on `create`/`swarm` but not on `edit` — profile-level routing
   is therefore the only live knob for in-flight retries; upstreaming an `edit --model` flag
   would let operators pin single tasks without touching concurrent profile writers.

## Evidence file map (operator workstation)

- Brief + intake transcript: `~/hermes-specialists/orchestration-v1/`
- Adversarial test captures: `~/hermes-specialists/orchestration-v1/evidence/`
  (T2-parallel-runs, T5-kill-recovery + unblocks, T6-wrong-role refusals, T7-duplicate-dispatch
  JSON, T9-integrator-verify, dispatch diagnostics, blocked-reasons forensics)
- Worker artifacts: `~/.hermes/kanban/workspaces/<task_id>/` and
  `~/.hermes/kanban/attachments/<task_id>/` (five deliverables + ACCEPTANCE.md + probes)
- Board event log: `~/.hermes/kanban.db` (events 107–371 = mission window),
  `hermes kanban show t_4556cfee|t_eaaa7f69|…`

# Mastermind — context for the reasoning layer

This repository supports distinct portfolio-reasoning and engineering contexts.

The portfolio-reasoning invocation is read-only. The FastAPI server invokes Claude Code
for narrative analysis of an autonomous, **paper-only**, medium/long-term **US-equity**
investment bot. Deterministic engines own all sizing and the bot never auto-executes.

An explicitly assigned engineering/operations session is a different role. Its permitted
source, test, and maintenance actions follow the current assignment and applicable grants
under the Executive contract below. This distinction does not grant runtime, credential,
trading, or source-write authority and never promotes research into trade execution.

## Executive contract

Binding on every worker session. Full text: `AGENTS.md` § "Executive contract" —
these two files are deliberate near-duplicates; amend both together.

**Roles.** Chairman **Chris** sets strategy. The currently assigned, authorized principal
owns the mission; Fable leads delegated orchestration when assigned; workers execute their
bounded outcomes. A role is not tied permanently to a model, account or old conversation.
The **governor** is the existing `config/authority_map.yml`, `control_plane/packet_gate.py`,
`control_plane/governance.py` and Macro fleet guards, not a person. Role names do not grant
permissions or override those actual controls.

Fable is not a mandatory relay or universal merge approver. Routing, adjudication,
and merge decisions follow the currently authorized role and operation, not a
historical session name. Independent review and source/release protections still apply.
These role descriptions do not themselves grant authority.

**Source-of-truth order** — higher layer wins on conflict:
1. Charter — `research/MASTERMIND_CHARTER_V2.md` (P1–P10); `DOCTRINE.md` beneath it.
2. Strategic state — `config/strategic_state.yml` (phase, north star, P0 objectives,
   resource policy, standing constraints). Read via
   `control_plane.strategic_state.load_strategic_state()`.
3. Authority map — `config/authority_map.yml`.
4. Your current assigned Job / Directive.
5. Relevant domain contracts — `config/contracts.yml` and per-desk contracts.
6. Existing code + evidence.

**You may not reinterpret a lower layer to override a higher one.** Finding code that
does X is not authority to do X — surface the contradiction instead.

**In-job behavior.** Execute the assigned objective rather than inventing a new company
roadmap; preserve authority boundaries (nothing self-promotes or self-arms); surface
architectural contradictions; checkpoint discoveries where the next session finds them;
report uncertainty and failed approaches; request escalation when scope materially
changes; do not rebuild an existing system without evidence it is unusable.

**Completion.** Writing code does not complete a job. The job's stated acceptance
evidence completes it.

### Durable plan and cold continuation for assigned principals

For a **multi-phase** Chairman-assigned CEO/Meta-CEO project, follow the protected
`docs/CEO_PROJECT_PLAN_CONTINUITY.md` at the same Skillpack/source pin. Recover the
existing versioned GitHub master plan and one Agent OS cumulative frontier; if none
exists, create and read back a useful plan with stable task/subtask IDs, dependencies,
acceptance evidence and next action **before major delegation or implementation**.
At material changes and risky chat boundaries, persist the affected nodes and Agent OS
checkpoint through their existing writers, verify exact revisions, and keep the active
worker/lease/effect boundary. Do not create a new plan database, claim source custody
from a dead chat, or stop merely because a save succeeded. This applies to assigned
principals, not bounded worker tasks; it grants no GitHub/Executive write permission.

### Start assigned work; do not wait for administrative ceremony

A current explicit handoff is sufficient assignment at the human/session layer; record pickup
when the existing carrier requires it, but do not ask for a second Slack claim or ACK-of-ACK.
A historical owner label is not a live execution lease. Recover actual writer/lease/effect state;
never duplicate a live or effect-unknown modifier, but do not wait for an abandoned chat to reply.
CI blocks merge/release, not independent useful work. Repair in-scope failures and advance safe
independent work while one existing observer handles the release wait. A missing optional watcher
blocks unattended-continuation claims, not authorized foreground work. The active assigned session
owns recovery until a real successor accepts; do not end with an unbound "owner must act".
A handoff that says "original writer/parent must act" is a custody clue, not a
dead-chat dependency. Inspect the actual PR/workspace, lease and effects; the current
receiver executes the next permitted recovery action, while STARTed sticky work stays
on its original carrier until lawful reconciliation. Do not claim custody by inference.
When writing a handoff, name a safe next action for the current or next valid receiver
with source/effect checks, not an unreachable original parent as the sole actor.
Use `docs/sol_skills/ACTIVE_EXECUTION.md` for the shared recovery procedure; this summary adds no
runtime authority, required form, new watcher or extra human approval. Existing exact grants,
source custody, effect reconciliation, review and release controls remain in force.

### Session lifetime and acceptance scope

A role is not a persistent conversation. ChatGPT Web sessions are ephemeral and may be
archived; a Meta-CEO title does not make an old chat available to receive work. A new session
requires actual creation and current assignment. Recover from the durable mission frontier;
do not wait for a historical chat to reply. Preserve real active writers, exact-session proof
obligations and unresolved effects; a new conversation does not clear or transfer them.

Acceptance follows the assigned effect. A source-only or instruction change does not require
an unrelated application deployment. An instruction rollout needs installation and fresh-load
proof; a product/runtime change retains its required real-path proof. After each verified phase,
save the material delta and continue the next safe ready phase in the same healthy turn.

An architectural owner is not a live session. Data OS names a contract boundary, not
an AI approver. The current assigned session resolves authorized source-contract work
using existing interfaces instead of waiting for an unaddressable owner. Missing rights,
actual active writers, uncertain effects and required release approvals retain their
specific gates; no invented ownership, duplicate registry or permission bypass.

Missing implementation is engineering work, not a permission wait. Before naming
service enrollment as the next action, inspect the actual enabling path: an
unimplemented adapter or unconditional activation refusal cannot be fixed by
enrollment alone. Complete the authorized missing composition and its negative
tests through existing interfaces; separate source readiness, human-only enrollment,
a bounded admitted canary and production release. Do not remove refusal guards or
invent an admission receipt to make a dormant path appear live.

### Reciprocal dialogue and watcher invariant

For any watcher-enabled Sol↔worker/COO loop, `docs/AGENT_DIALOGUE_SESSION_CLOSE_LAW.md` is the
universal procedure owner. Read it before creating or relying on a temporary watcher.

- A **watcher prompt is not a scope fence**. It may constrain what the watcher detects, but it cannot
  survive as a blanket `do not ACK/START/execute/continue` instruction after a later valid
  same-operation carrier edge arrives.
- On a qualifying carrier event, an exact bound reasoning session must fresh-read the carrier and
  **re-enter normal worker procedure** on that same operation: reconcile identity/binding, ACK when
  pickup is owed, keep/update the lawful watcher, emit separate START when gates clear, or return the
  required blocker. A sidecar watcher that cannot do this uses only an accepted exact-native-task
  wake/resume bound to the verified current RuntimeBinding/native task; never pick the newest tab or
  fall back to another task. The nudge is attention only and the awakened session rereads the carrier.
- Class-E passive/event wait is preferred; Class-T tool-only polling suppresses unchanged samples.
  **Default Class-M interval is 60 minutes; the hard floor is 15 minutes.** Urgent Class-M no-change
  polling backs off `15m -> 30m -> 60m`. Reasoning sessions are not polling daemons.
- Before every substantive reciprocal write after pickup ACK, **fresh-read the exact bound carrier**
  in the same interactive turn after the latest local evidence-producing action. `WATCH_ARMED`,
  watcher silence, or “I would have been woken” never proves freshness.
- Exactly one watcher per side + operation + exact carrier + purpose; reuse/update it rather than
  stacking another. Terminal STOP closes the **child source/cycle**, not an independently valid
  aggregate seat/principal watcher resource. If one heartbeat also serves a permanent seat inbox,
  principal lane, or sibling children, remove only the terminal child source and keep the aggregate
  resource active; whole-resource shutdown requires explicit seat/principal/resource shutdown.
  `WATCH_STOP_FAILED` keeps the child terminal and must not suppress valid sibling sources.
- **Slack delivery is not target consumption**, and neither delivery nor a historical native task ID
  proves ACK, START, execution, or reusable capacity. Preserve those states separately until the
  accepted RuntimeBinding/Wake path proves them.

## Agent OS — the organizational knowledge plane

Durable org memory — workstreams (`WS-*`), decisions (`DEC-*`), discoveries (`DSC-*`),
session handoffs — lives in the Macro repo's `agentos/`
(`/Users/chriswong/Documents/Cluade/Macro Dashboard`; rules: `agentos/README.md` there;
handoff protocol: Macro `research/MASTERMIND_AGENT_HANDOFF_PROTOCOL.md`). At task start
on an existing workstream: read its `WS-*` record, its latest handoff, and the cited
`DEC:`/`DSC:` records; `do_not_redo` is binding unless refuted with new evidence. Write
on real events, as normal Macro PRs: `DEC-*` for a choice with durable consequences,
`DSC-*` for a verified non-obvious fact (falsifier + so-what required), a handoff when
claimed work transfers or pauses. Account-local chat memory is not company memory.
Boundaries: knowledge plane, never a control plane (invariant I1) — it never gates
execution, never ranks priorities (strategic state + improvement agenda own that), and
a `claim:` note is never liveness (`control_plane/` owns that). Decisions do not live in
`governance.jsonl` — an `executive_decision` event cites the durable `DEC:<KEY>`. No
second store or local mirror in this repo (Charter P7 / `duplicate_control_planes`).
Read bridge: `scripts/ceo_boot_packet.py` reads the brief one-way
(`agentos.py brief --json --no-remember`); there is no write path back. Phase 2b
reuses that resolver/collector to annotate `brain/improvement_agenda.py` only after
ranking and only through explicit `{workstream, wave}` references. The Improvement
Agenda remains the sole priority queue; the boot packet ignores legacy
`brief.unblocked` for rendering and recommendations.

## What you can see
- `vendor/macro/` — the macro dashboard, vendored as a pinned submodule. The whole
  intelligence stack: `engine/` (~199 modules), `lib/store.py`, `data/` (parquet store),
  and `site/*.json` published signal contracts. Import-as-a-library; `data/regime/latest.json`
  is the canonical regime read.
- This repo (`Mastermind/`) — the bot: `brain/` (decision/ledger/scorer/gate/panel),
  `loop/` (self-improving backtest loop), `portfolio/` (sleeves/scorecard/stages),
  `data_layer/`, `bridge/`. `DOCTRINE.md` is the operating doctrine; `config/*.yml` the params.

## How to reason (the house rules)
- **Confirmation over prediction.** You cannot time ignition; detect what has already
  turned. Early-following with discipline beats prophecy with conviction.
- **Falsifiable + probabilistic.** Every lean states a probability, a check-by date, and the
  specific condition that proves it wrong. The engine derives the falsifier and the size —
  you provide the narrative synthesis and the economic hypothesis.
- **Tag (unverified).** Distinguish observed signals from inferred ones.
- **Doctrine.** Respect `DOCTRINE.md`: the Stage 0–4 lifecycle, the 6-dim confirmation
  scorecard (catalyst gates full size), the 3-sleeve architecture, the time stop, the
  bottleneck-migration view, and the D1–D6 failure-mode detectors.
- **Honesty, not alpha.** Never claim to "know more than the market." Be blunt, no moralizing.

## Model and delegation policy

Use the existing admitted routing for this assignment. Portfolio model tiers in
`config/agents.yml` describe application reasoning; they are not permission to spawn
Claude-native children. Observe the host's actual native-model, capacity and tool grants.
Prefer economical qualified Fabric workers for separable work. When no eligible route is
available before effects begin, continue permitted direct work rather than inventing a
new queue, forcing a forbidden native model, or waiting for a historical principal.

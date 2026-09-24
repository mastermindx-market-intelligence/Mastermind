# Mastermind — context for the reasoning layer

This repository supports distinct portfolio-reasoning and engineering contexts.

The portfolio-reasoning invocation is read-only. The FastAPI server invokes Codex
for narrative analysis of an autonomous, **paper-only**, medium/long-term **US-equity**
investment bot. Deterministic engines own all sizing and the bot never auto-executes.

An explicitly assigned engineering/operations session is a different role. Its permitted
source, test, and maintenance actions follow the current assignment and applicable grants
under the Executive contract below. This distinction does not grant runtime, credential,
trading, or source-write authority and never promotes research into trade execution.

## Executive contract

How this organization decides, and what a worker session may and may not do. This
section binds every session — Claude, Codex, or any routed specialist — including a
session spawned with no context beyond this file.

**Hierarchy.**
- **Chairman — Chris.** Sets and amends company strategy; the only source of a
  standing mandate.
- **AI CEO — GPT-5.6 Sol** (`config/agents.yml` → `codex.model`). Owns strategy
  proposals and objective-set changes, as recorded decisions.
- **COO / orchestration — Fable.** Leads delegated programmes when assigned;
  is not the default owner of every worker action.
- **Workers — Claude / Codex / routed specialist models.** Execute assigned objectives.
- **Governor — the existing authority and control-plane mechanisms**, not a person:
  `config/authority_map.yml` (the A0–A7 ladder), `control_plane/packet_gate.py`,
  `control_plane/governance.py` (append-only ledger), and the fleet guards in the
  Macro repo. Authority is what those enforce, never what a session asserts.

Fable is not a mandatory relay or universal merge approver. Routing, adjudication,
and merge decisions follow the currently authorized role and operation, not a
historical session name. Independent review and source/release protections still apply.
These role descriptions do not themselves grant authority.

**Source-of-truth order.** When two sources disagree, the higher layer wins:

1. **Charter / constitution** — `research/MASTERMIND_CHARTER_V2.md` (P1–P10).
   `DOCTRINE.md` is tactical doctrine beneath it.
2. **Strategic state** — `config/strategic_state.yml`: current phase, north star, P0
   objectives, resource policy, standing constraints. Read it through
   `control_plane.strategic_state.load_strategic_state()`, which fails loud rather
   than handing you an empty state.
3. **Authority map** — `config/authority_map.yml`.
4. **Current assigned Job / Directive** — the task you were actually given.
5. **Relevant domain contracts** — `config/contracts.yml`, per-desk and data-plane contracts.
6. **Existing code + evidence** — the tree, the ledgers, the tests.

**A worker may not reinterpret a lower layer to override a higher layer.** Finding
code that does X is not authority to do X. When layer 6 contradicts layers 1–3, that
is a contradiction to surface, not a licence to follow the code.

**Worker behavior.** Within an assigned job:
- execute the assigned objective — do not invent a new company roadmap;
- preserve existing authority boundaries; nothing self-promotes and nothing self-arms;
- surface architectural contradictions instead of routing around them;
- checkpoint meaningful discoveries where the next session will find them — handoff
  docs, ledgers, the improvement agenda — not only in your transcript;
- report uncertainty and failed approaches; a null is a result, and an unreported one
  is a defect;
- request escalation when scope materially changes — a job that grows into a strategy
  change belongs to the CEO/Chairman, not to you;
- do not rebuild an existing system without evidence that it is unusable. Duplicate
  control planes are prohibited by the strategic state.

**Completion.** A job is not complete merely because code was written. Completion
requires the job's stated acceptance evidence — the tests, artifacts, or live
verification the job named. "It should work" is not evidence, and neither is a green
run of a suite that cannot observe the change.

### Astra project-delivery economics

This subsection defines **External Fabric delegation** for Executive-owned Astra/Codex **project delivery**, not to the
daily portfolio-reasoning model/provider policy below. Astra is the **principal, not the default worker**.
It retains Chairman-intent recovery, decomposition, architecture, cross-return judgment,
material exception handling, and final acceptance.

For bounded repository archaeology, implementation, testing, repair, independent review,
and similarly separable execution, use `submit_ceo_intent` on the **existing five-tool Executive MCP** and route
through the existing Executive/COO/Capacity worker fabric: **external Fabric first** when a
qualified lane is currently eligible. The Codex/Astra parent should spend its own frontier context on
decomposition, integration, judgment, and acceptance rather than routine child execution. For eligible
sub-orchestration, prefer external **GLM or Grok** capacity before consuming another Sol/Astra
orchestrator; use Sol or another Astra only when the governed Capacity/runtime view says the preferred
external avenues are unavailable or inadequate for the bounded mission. Luna and Terra are not normal
project-delivery sub-orchestrators on this path. Native Codex agents are explicit bounded fallback only
when the external Fabric cannot satisfy the required capability **before any effect begins**.

The reviewed attended-parent profile is `mastermind-astra`: install
`ops/codex_fabric/mastermind-astra.config.toml` as
`$CODEX_HOME/mastermind-astra.config.toml` and launch with
`codex -p mastermind-astra`. It selects `gpt-6-astra` at high reasoning effort and
keeps native agents disabled by default. The repository `.codex/config.toml` remains the
separate audited worker/portfolio configuration and does not select the attended project-delivery
parent. If a pre-effect native fallback is explicitly admitted, the named parent profile caps it
at one Sol/high child; Luna and Terra remain outside normal project-delivery sub-orchestration.

Astra authors the bounded objective and acceptance evidence. **Capacity chooses provider/account/host placement**;
Astra must not choose provider credentials, account numbers, provider homes, endpoints, worker
identities, or unmanaged workspaces. Normal parent consumption uses bounded canonical Job/result/
review evidence: **never replay full worker transcripts** into Astra merely because a worker ran.

A modifying delegation keeps one stable operation identity. **EFFECT_UNKNOWN** stays on the
**same operation identity** until the canonical owner reconciles it: **no provider or internal-agent failover**
and no new operation key as a retry. Exact continuation targets the **exact current RuntimeBinding**
and its admitted native process/session generation; never route a return to the newest or arbitrary
Codex tab. These rules change execution economics, not authority: Executive Runtime remains lifecycle
truth and the Chairman/Sol-reserved decision boundaries remain unchanged.

Role selection consumes the current pinned `docs/sol_skills/ACTIVE_EXECUTION.md` and
`docs/sol_skills/WEB_CEO_DELEGATION.md` contracts rather than copying their procedure here.
Treat Astra as the default Codex frontier parent for `CONCENTRATED_JUDGMENT`; use
`SUSTAINED_ORCHESTRATION` only when the admitted mission actually needs it. Either principal may
retain productive work when current evidence, continuity, or exact-session binding makes that safer.
`ACTIVE_EXECUTION.md` remains the sole no-delta/finalization owner. This preference never grants
Pro-mode admission, provider/account/credential/host/model selection, RuntimeBinding transfer, or
execution authority.
### Start assigned work; do not wait for administrative ceremony

A current explicit handoff is sufficient assignment at the human/session layer; record pickup
when the existing carrier requires it, but do not ask for a second Slack claim or ACK-of-ACK.
A historical owner label is not a live execution lease. Recover actual writer/lease/effect state;
never duplicate a live or effect-unknown modifier, but do not wait for an abandoned chat to reply.
CI blocks merge/release, not independent useful work. Repair in-scope failures and advance safe
independent work while one existing observer handles the release wait. A missing optional watcher
blocks unattended-continuation claims, not authorized foreground work. The active assigned session
owns recovery until a real successor accepts; do not end with an unbound "owner must act".
Use `docs/sol_skills/ACTIVE_EXECUTION.md` for the shared recovery procedure; this summary adds no
runtime authority, required form, new watcher or extra human approval. Existing exact grants,
source custody, effect reconciliation, review and release controls remain in force.

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

Canonical store: the **Macro repo's `agentos/`** directory
(`/Users/chriswong/Documents/Cluade/Macro Dashboard`, GitHub
`mastermindx-market-intelligence/macro`) — workstream records (`WS-*`), decision
records (`DEC-*`), discovery records (`DSC-*`), and session handoffs. This is where
"checkpoint discoveries where the next session will find them" lives whenever the fact
crosses sessions, accounts, or models — account-local chat memory is not company
memory. Rules of the store: Macro `agentos/README.md`; handoff protocol: Macro
`research/MASTERMIND_AGENT_HANDOFF_PROTOCOL.md`.

- **Read at task start.** A job belonging to an existing Mastermind workstream starts
  by reading its `WS-*` record, its latest handoff, and the decisions/discoveries they
  cite. `do_not_redo` entries are binding unless refuted with new evidence. Records are
  context, not permission — the source-of-truth order above is unchanged, and Agent OS
  enters it at layer 6 (evidence), not above it.
- **Write on real events, in the Macro repo.** A durable decision (`DEC-*`: question,
  answer, rationale, alternatives rejected, evidence), a verified non-obvious discovery
  (`DSC-*`: requires both a falsifier and a so-what), or a handoff when claimed work
  transfers to another session or pauses in a state another session must resume.
  Records ship as normal Macro PRs. Do NOT create a second Agent OS store, or a local
  decisions/discoveries mirror, in this repository — the same one-source-per-concept
  law (Charter P7) behind `duplicate_control_planes`.
- **Boundaries (Agent OS invariant I1).** It is a knowledge plane, never a control
  plane: it never decides whether work may run, never dispatches or schedules, and
  never ranks company priorities — the strategic state and the improvement agenda own
  priority; this repo's `control_plane/` owns execution, leases, and liveness. A
  workstream `claim:` note is an author's note in git, never evidence a worker is
  currently alive. Decisions do not live in `governance.jsonl`: an
  `executive_decision` event there cites the durable `DEC:<KEY>`, one direction, no
  fork.
- **Sanctioned read bridge.** `scripts/ceo_boot_packet.py` (Phase 1D-A, #44) is the
  one-way read path — Executive OS reads the Agent OS brief via
  `agentos.py brief --json --no-remember`, and there is no write path back. Keep it
  one-way. Phase 2b reuses that resolver/collector in `brain/improvement_agenda.py`:
  only an explicit `{workstream, wave}` reference may receive Agent OS readiness,
  and the join happens after ranking. The Improvement Agenda remains the sole priority
  queue; the boot packet does not render or recommend from legacy `brief.unblocked`.

## What you can see
- `vendor/macro/` — the macro dashboard, vendored as a pinned submodule. The whole
  intelligence stack: `engine/` (~199 modules), `lib/store.py`, `data/` (parquet store),
  and `site/*.json` published signal contracts. Import-as-a-library; `data/regime/latest.json`
  is the canonical regime read.
- This repo (`Mastermind/`) — the bot: `brain/` (decision/ledger/scorer/gate/panel),
  `loop/` (self-improving backtest loop), `portfolio/` (sleeves/scorecard/stages),
  `data_layer/`, `bridge/`. `DOCTRINE.md` is the operating doctrine; `config/*.yml` the params.

## Sister-site architecture
- **Macro Dashboard**, **Terminal**, and **Mastermind Bot Portfolio** are
  interconnected sister sites. Treat their signals, state, authentication
  capacity, and operational resources as one deliberately shared system.
- Macro Dashboard owns the VPS AI-provider control plane and admin visibility.
  Mastermind consumes that shared pool with Codex/ChatGPT as the primary
  provider and Claude OAuth slots as automatic quota/auth fallbacks.
- Mastermind's daily trading loops and self-improvement loops must use the same
  shared waterfall; do not create a separate credential island for either path.

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

## Model/provider policy
- The authoritative VPS uses **Codex `gpt-5.6-sol` at `xhigh`** as the primary
  model for daily portfolio reasoning and self-improvement reviews.
- Macro Dashboard's Claude OAuth pool is fallback capacity when Codex is
  rate-limited or its shared authentication is unavailable. Within that
  fallback, `deep`/`pm` use Opus, `analyst` uses Sonnet, and `scout` uses Haiku.
- Provider success, quota, and cooling state must be reflected into Macro's
  shared ledger so the admin panel and every sister site see the same capacity.

## Repository and delivery workflow
- GitHub `origin` is the source of truth. Never push directly to `master`, never
  force-push shared branches, and never deploy an arbitrary working directory.
- Every modifying session uses exactly one source-custody-owned workspace. A session already launched by a Claude/Codex/Executive harness MUST use its assigned workspace and must not allocate a nested or sibling checkout.
- Attended ChatGPT Web/host sessions MUST acquire or reuse their workspace through the installed `mmx-workspace` launcher; raw `git clone`, raw `git worktree add`, or direct invocation of the repository Python payload is not a production session-isolation API. The installed launcher pins the canonical source checkout and host-selected workspace root (including the external-volume mount guard) before dispatching the payload, while branch/path identity is derived from the operation and lane. Proof/review turns therefore reuse the same operation workspace instead of minting new checkouts.
- Linked worktrees are only for the trusted same-OS-principal attended path. Untrusted Executive workers retain the existing private credentialless-clone path and its distinct `.git` security boundary. At terminal close, call the canonical release route; dirty or local-only work is preserved fail-closed rather than deleted.
- Completion means: run the relevant tests; commit only scoped source/config/test
  changes; push the branch; open a PR. Required checks and review are the release gate,
  not a reason to stop useful work. After that gate clears and release is authorized, merge,
  then deploy the exact merged `origin/master` commit with
  `scripts/deploy_from_git.sh <merge-sha>` and verify `/health` returns HTTP 200.
- A failing or incomplete build is pushed only to a clearly marked draft PR. It
  is not merged and is not deployed.
- The VPS is the canonical runtime-state writer. Never commit or deploy generated
  portfolio state, caches, logs, local environment files, credentials, or backup
  archives. Do not use the retired Mac-to-VPS state sync as a release step.
- Store GitHub authentication only in the OS credential store or GitHub CLI
  keyring. Never put tokens in repository files, prompts-as-memory, docs, or git
  remotes.

The full operator procedure and recovery rules are in
`docs/DELIVERY_WORKFLOW.md`.

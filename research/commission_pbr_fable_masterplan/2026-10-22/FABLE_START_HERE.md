# Portfolio Bot Rebuild (PBR) — Fable CEO commission. Start here.

**Commissioned:** 2026-10-22 ~07:30Z by the Chairman (Chris) to the Fable Meta-CEO session
(worktree `mastermind-fable-ceo-rebuild-421ce3`, session `ed665c78-1bca-45e2-ba40-bc78b8444002`).
**Program issue + risk register:** mastermindx-market-intelligence/Mastermind#1693.
**Program carrier PR (docs/ledger only):** recorded in `ORCHESTRATION.md` row `W0 seat` once opened.
**Masterplan:** `./MASTERPLAN.md` — verbatim copy of
`~/Downloads/Mastermind_Portfolio_Audit_and_Fable_CEO_Rebuild_Masterplan_2026-10-21.md`,
sha256 `4c7a0d449f02de080e4d8d310af5db09515af86683ac6a3bca1298f2e034d970`, 804 lines.
**Procedure pin:** `docs/sol_skills/*` and `skills/mastermind-fabric-orchestration/*` at `origin/master`
230e9a301 (the audit pin c9cbee556 is its ancestor; the two later commits touch no audited path).
**Packets, owners, status:** `WORK_PACKAGES.md`. **Ledger:** `ORCHESTRATION.md`. **Lane packets/returns:** `lanes/`.

## 1. Frontier facts verified at commissioning (07:15–07:30Z, read-only)
- `origin/master` 230e9a301. Audited source files unchanged since the pin.
- Carriers at the audit's heads, unchanged: #1357 draft 1e127060 · #673 draft 0b960590 · #1147 draft 6f192387 ·
  #824 open non-draft MERGEABLE 8aa934c1 · #726 draft 5eb4154a · #727 draft MERGEABLE 4e97c323 ·
  #728 draft MERGEABLE b2d1ce9b · #1432 draft 9dda10f1 · #1433 issue open · #1434 draft d5fec1eb · #1614 MERGED 43f83e068.
- Production = VPS `root@146.190.142.17` (ssh key `~/.ssh/macro_dashboard_deploy_v2`), tree `/opt/mastermind`,
  `mastermind.service` active, MainPID 876885, started 2026-10-22 06:02:15Z (the audit saw PID 179202 from 10-21 15:55Z).
  `/opt/mastermind` is **not** a git checkout. `data/deploy_lag.json` claims head `131290a0` == master, but 131290a0 is
  985 commits behind `origin/master` → stale metadata, never an identity. `portfolio/price_evidence.py` absent ⇒ #1614
  not installed. **Installed identity is proven only by blob comparison of installed files against `origin/master`.**
- Live data root `/opt/mastermind/data` (VPS authoritative writer since 2026-08-19; the Mac copy is a retired writer).
  Autonomous book = legacy default storage `data/portfolio/{account.json,fills.jsonl,nav_history.jsonl,pending_target.json,
  pending_orders.json,positions_ledger.json,latest.json,safety.json,mandate_packet.json}`; `china`/`hk` resolve to
  `data/portfolios/<id>/` through `portfolio/registry.py` + `portfolio/paper_account.py` (verify on the host).
  **Read-only for every lane. Never rsync or scp toward the VPS. Never run the bot against live data.**
- The audit's companion evidence archive (R1–R9 JSON, `reproduce_audit.py`) is **not on this host**. Every figure in the
  masterplan is the audit's claim; W1 re-derives from the live ledger and records agreement or disagreement.
- Agent OS (Macro `agentos/`): no workstream for this program. PRODUCT owner creates `WS-PORTFOLIO-BOT-REBUILD` + handoff.
- Executive MCP ingress needs OAuth this session (unavailable). Admitted delivery path = the pool kit (`pool remote`,
  broker on m2studio). Executive admission QUEUED is not STARTED.

## 2. Admitted delivery graph (what exists today — not the aspirational one)
```
Fable seat (strategic judgment, cross-domain arbitration, final acceptance; never routine labor)
 └─ Opus native suborchestrator per domain  (ROUTE: ORCHESTRATION · bounded · commissions and adjudicates)
     └─ fabric lanes via `pool remote <host> <mode> <packet> <remote_cwd> <model> --run-id <id> --out <file>`
          operator-class lanes (classes design/decompose/architecture/review/adjudicate/operator → tier frontier-labor):
              glm-5.3 (mode glm)  ·  qwen3.8-max (mode qwen)
          worker-class lanes (classes build/fix_build/census/extract/probe → tier leaf-labor):
              glm-5.3-flash (glm) · qwen3.8-flash (qwen) · MiniMax-M3 (minimax; skips the economic check)
```
Nested fabric operator→worker spawning is **not admitted** (`operator` is a selection class in `model_tier.CLASS_TIER`,
"never a grant of recursive authority"; lane hosts carry no `pool` binary). Grok: EXHAUSTED (402) — human top-up gate,
never purchase. Native Sonnet/Haiku children are refused by the routing guard; Opus children need the three guard lines.

Capacity 07:15Z: glm 20 free (3 chairman-max accounts × 8) · bailian 20 free (Ryan live everywhere; Chris 403-cooling on
ubuntu0/2/3/mb) · minimax 5 free · go 9 · cursor 18/month. Hosts (all have `~/lanes/repos/Mastermind` + `~/lanes/venv`):
ubuntu0 0 active 440G · ubuntu1 0 active 332G load 2.5 · ubuntu2 3 active 368G · ubuntu3 3 active 411G ·
mb 1 active (cap 2) 119G · m1 0 active 164G (window Mon–Fri 02–11Z). ssh aliases `mmx-ubuntu0..3`, `mb`, `m1`.

### Launch recipe (proven 10-12 → 10-21; see memory `remote-sub-launch-economic-policy`)
1. Mint on the host (the seat/orchestrator runs every git step; workers never commit/push):
   `ssh <h> 'cd ~/lanes/repos/Mastermind && git fetch origin "+refs/heads/<BR>:refs/remotes/origin/<BR>" && git worktree add --detach ~/lanes/wt/<lane> origin/<BR> && git -C ~/lanes/wt/<lane> sparse-checkout disable'`
   (braces + quotes on the refspec: remote zsh eats `:r`). Put aux inputs under `~/lanes/tmp/<lane>/` with `cat > file` over ssh.
2. Export before launch: `POOL_ORCHESTRATOR_ID=pbr-<domain>-ed665c78 POOL_TASK_CLASS=<class> POOL_TASK_COMPLEXITY=<C0|C1|C2|C3> REMOTE_SUB_MAX_SECS=<secs≤7200>`;
   glm-5.3 on a leaf class additionally needs `POOL_ESCALATION_REASON="<honest sentence ≥12 chars naming the failed flash run>"`.
3. Launch detached with stdin closed: `pool remote <host> <mode> <packet.md> /home/<user>/lanes/wt/<lane> <model> --run-id <lane-id> --out <local.out> < /dev/null &`.
   Read `ECONOMIC_POLICY`, `LEASE_OK`, `POLL` in the launcher log before calling it RUNNING. A refused launch keeps its run-id → relaunch as `<lane-id>-r2`.
   A remote admission refusal surfaces 2–3 min later as `DONE rc=75 … remote_admission_refused`.
4. `--out` captures ONLY the worker's final assistant message → every packet ends with "emit the full RETURN block as your last message".
5. Collect: `ssh <h> 'git -C ~/lanes/wt/<lane> diff'` → apply in the orchestrator's own SSD worktree → run the named tests → commit → push → PR. Clean the lane tree the same hour.
6. Review ≠ build: a separate reviewer lane (glm-5.3 / qwen3.8-max, class `review`) on the exact PR head; its `VERDICT:` line is the disposition. A PENDING read note is not a review.

## 3. Owner map — one writer per artifact family
| Domain | Owner id | Packets | Owned artifacts (sole writer) | Incumbent carriers to continue |
|---|---|---|---|---|
| ECON | `pbr-econ` | W1, W2 → W3 | `portfolio/paper_account.py`, `portfolio/marks.py`, `portfolio/price_evidence.py`, `bot/settle.py`, `portfolio/benchmark*.py`, their tests, evidence under `research/commission_pbr_fable_masterplan/2026-10-22/lanes/ECON/` | #824 #726 #727 #728 #1432 #1433 #1434; consume #1614 |
| RUNTIME | `pbr-runtime` | W4 | `brain/provider_waterfall.py`, `brain/autonomous_mcp.py`, `app/scheduler.py`, `app/provider_diagnostic_read.py`, manager-cycle disposition in `bot/autonomous.py` / `bot/china.py` / `bot/hk.py` (lifecycle only), `ops/` install proof | #1147 |
| RESEARCH | `pbr-research` | W5, W6 → W7, W8 | `brain/decision_context.py`, `brain/decision_submission.py`, `portfolio/forward_evaluation.py`, new `brain/thesis*`, `brain/claims*`, `brain/shadow*`, experiment protocols under `docs/superpowers/specs/` | #673 #1357 |
| PRODUCT | `pbr-product` | W9 (+ Agent OS WS record) | `app/web.py`, `app/static/**`, `app/account.py`, `app/pfolio.py`, `app/decision_availability*.py`, UI templates, browser proof under `review_evidence/` | consumers #1572 #1580 #1586 (merged) |
A change outside your family → write a **contract request** row in your ledger and stop at that boundary; never a competing writer.
`paper_account.py`, settlement, shared API/auth and shared contracts are serialized through ECON / PRODUCT as named above.

## 4. Gates (MASTERPLAN §11.3) — status
G0 owned baseline: **OPEN** (closes when all four owners ACK scope in `ORCHESTRATION.md`). G1–G7: NOT STARTED.

## 5. Three verdicts (every checkpoint reports all three, separately)
Operationally correct: **NOT YET** · Economically qualified: **NOT YET** · Investment value demonstrated: **INCONCLUSIVE** (by design until W10).

## 6. Standing rules for every orchestrator and lane
1. Live data is read-only; no account reset, no seed rewrite, no balancing fill, no "repair" trade. An adjustment is an event with type, reason, evidence, effective time, recorded time, reviewer.
2. Preserve: book ids, V2 marker (sha256 75d5182d…), August-11 cohort, baseline exclusions, lessons, archived books, pending targets/receipts.
3. Shadow work terminates in isolated storage: no registry membership, no pending-target route, no settlement authority. Prove with negative cases.
4. Every PR: discriminating tests that fail on the old code; reviewer independent of builder; `VERDICT:` line retained in `lanes/<DOMAIN>/`.
5. "Merged" ≠ "installed" ≠ "accepted". Installed identity = blob comparison. Product truth = authenticated browser + API agreement.
6. Two equivalent no-delta cycles → change tier, split the packet, or change owner; never a third identical round.
7. An explicit refusal (permission, safety, admission) ends that effect's retry; never switch accounts/models/carriers to obtain it.
8. Report: what changed, exact evidence, what remains uncertain, the owner, the next bounded action, and the one reserved decision for the seat.

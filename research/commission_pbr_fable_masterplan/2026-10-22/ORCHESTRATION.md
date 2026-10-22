# PBR orchestration ledger

One row per commissioned unit. The seat (Fable) appends; domain owners return ledger rows in
their reports and the seat pastes them. A row is evidence of a commission or a return, never of
acceptance: acceptance is a separate row citing the artifact and the independent review.

Columns: `when (UTC)` · `unit` (orchestrator or lane id) · `host/model` · `class` · `run-id` ·
`state` (COMMISSIONED / RUNNING / RETURNED / ACCEPTED / REJECTED / REPAIR-n / HELD) · `artifact` ·
`note (one line)`.

## Wave 1 — 2026-10-22 (commissioning + W1 · W2 · W4 · W5 · W6-contract · W9-design)

| when | unit | host/model | class | run-id | state | artifact | note |
|---|---|---|---|---|---|---|---|
| 07:30 | W0 seat | m2 / Fable | commission | — | COMMISSIONED | this directory; issue #1693; PR #1695 | frontier recovered; four domain owners briefed; see FABLE_START_HERE.md |
| 07:45 | pbr-econ | m2 / Opus native | domain_orchestration | agent | COMMISSIONED | SSD wt claude/44ff44e73b840f81/pbr-econ-5cdda3f3a9259411 (branch claude/ssd-pbr-econ-5cdda3f3a9259411) | W1 + W2 (ledger truth, prices/replay); sole writer of paper_account/marks/price_evidence/settle |
| 07:45 | pbr-runtime | m2 / Opus native | domain_orchestration | agent | COMMISSIONED | SSD wt claude/44ff44e73b840f81/pbr-runtime-85f3de87bc7b8894 (branch claude/ssd-pbr-runtime-85f3de87bc7b8894) | W4 (manager lifecycle, provider terminal, installed-identity proof) |
| 07:45 | pbr-research | m2 / Opus native | domain_orchestration | agent | COMMISSIONED | SSD wt claude/44ff44e73b840f81/pbr-research-f428e2e2c1d3f7a9 (branch claude/ssd-pbr-research-f428e2e2c1d3f7a9) | W5 + W6-contract (+ W7/W8 protocol freeze) |
| 07:45 | pbr-product | m2 / Opus native | domain_orchestration | agent | COMMISSIONED | SSD wt claude/44ff44e73b840f81/pbr-product-2fcf6d6d0fd2ddc5 (branch claude/ssd-pbr-product-2fcf6d6d0fd2ddc5) | W9 design + truthful partial views; Agent OS WS record |

### Exit gate for wave 1 (written before launch)
- W1: a per-book bridge document + any ledger-owner PR with tests; HK discrepancy either explained with evidence or bounded with an explicit unsupported interval. No balancing trades. ACCEPTED only with an independent review disposition.
- W2: A02 and A03 fixed on master-track PRs with counterexample tests that fail on the old code; #824 reconciled; #1614 consumption proven in tests. Install on production is a separate ledger row.
- W4: the China/HK rejected-cycle cause named from original run identities; the "error result: success" terminal replaced by a typed semantic result; a negative proof that an ambiguous retry creates no duplicate effect; production installed-identity proven by blob.
- W5: one real snapshot→inspector journey on a real book with the account and pending effects bound; negative cases for missing/future/forged context.
- W6-contract: typed fact contract + three regression cases (MU date, MU amendment, 688062 budget) as failing-then-passing tests; no allocator behaviour change yet.
- W9-design: frozen page specs (7 views) under the design system + one truthful partial view PR with API/browser agreement.

### Pre-mortem (wave 1)
1. Two owners edit `paper_account.py` → ECON is the sole writer; RESEARCH/RUNTIME request contracts in their ledger.
2. A lane reads the Mac copy of `data/` instead of the VPS → every econ lane receives a captured read-only snapshot with sha256s from ECON's seat pull.
3. Lanes mint on ubuntu2/3 and hit `active_lane_limit_reached` → preferred hosts assigned per owner; refusal consumes the run-id → bump `-rN`.
4. A reviewer never returns → every build lane has a reserved review lane and a bounded wait; silence is absence of evidence.
5. A worker "fixes" by resetting a book or inventing a balancing fill → forbidden in every packet; seat greps diffs for `reset`, `seed`, balancing writes before any merge.
6. deploy_lag.json is trusted as installed identity → forbidden; blob comparison only.
| 07:35 | seat | m2 / Fable | fact | — | RECORDED | FABLE_START_HERE.md §1 correction | live data root is /opt/mastermind-live-data (BindPaths); all captures redirected; .deployed_git_sha ff16c192 10-21 15:32Z |
| 08:20 | seat | m2 / Fable | ruling | — | RECORDED | CR-RT-1..4 | RT-1 granted narrow (cli_bridge + sdk_diagnostics error-literal surfacing only); RT-2 granted (thinking_log provider label); RT-3 SDK pin = release-row item (reserved PR allowed); RT-4 failover semantics reserved, typing only in wave 1 |
| 09:05 | seat | m2 / Fable | ruling | — | RECORDED | RESEARCH SR-1..4, CR-R4 | SR-1: public repo ⇒ fixtures keep typed/numeric fields, narrative → sha256+len; verbatim rows stay in /Volumes/Mastermind/evidence/pbr behind PBR_DECISION_CASE_INPUT_DIR. SR-2: #1357 clock set; CALLER_SUPPLIED never qualifies; add MACRO_VENDORED rights. SR-3: decision_research* → RESEARCH, later wave. SR-4: L-S4→#673 merge reserved to seat. CR-R4: RESEARCH owns bot/decision_rows.py additive identity fields; fill→decision link lives on the fill (ECON). Findings 7/8 accepted as W5 facts |
| 09:05–11:10 | all four owners | m2 / Opus native | outage | — | RESUMED 11:12 | — | Opus session limit (HTTP 429, resets 04:10 Vancouver = 11:10Z) killed ECON/RUNTIME/RESEARCH/PRODUCT mid-wave; fabric lanes kept running on hosts; owners resumed from saved state with reconcile-first instructions |
| 11:12 | seat | m2 / Fable | census | — | RECORDED | gh pr list "1693 in:body" | MERGED: #1698 ECON capture, #1704 W7/W8 protocols, #1707 L-P3a held-pending chip, #1710 product census. OPEN green: #1699 #1702 #1705 #1712 (ECON docs), #1708 A02 NAV (reserved), #1709 A03 marks (reserved), #1701 W6 spec, #1703 fixtures (SR-1 amendment pending), #1711 L-R3 projection, #1715 O-1, #1716 label, #1718 typed provider failure (reserved), #1719 self-directed unavailable. #1714 SDK pin: 1 failing check (reserved release item) |
| 11:45 | pbr-econ | m2 / Opus native | domain_orchestration | agent | RETURNED → ACCEPTED (wave 1) | lanes/ECON/*, reviews/lr-*.md; PRs #1698 #1699 #1702 #1705 #1712 (docs, owner-merged) #1708 #1709 (seat) | 16 launches / 11 delivered / 4 admission refusals / 1 key-cooldown; all lanes glm-5.3(-flash); HK bridge EXPLAINED 6/6 (06-22 open strike vs 06-18 close fill price; bound 7,026.14 HKD = 0.70% NAV; fills.jsonl trail error, not NAV/cash); cash residuals fully explained (yield sweep + CN 136.89 repair + HK 2-day row); A02 #1708 PASS (lr-a02-r1 + delta); A03 #1709 FAIL→repair→PASS (lr-a03-r2 at b4426142); #1614 produces but nothing consumes price_evidence (fill_pending caller bot/phase2.py:2702) |
| 11:46 | seat | m2 / Fable | acceptance | — | MERGE REQUESTED | #1708 @ 8ed3fe1b, #1709 @ b4426142 (squash, --match-head-commit) | seat verified: CI 9/9 SUCCESS, mergeable CLEAN, files in family (+ disclosed polygon.py raw path, default path byte-identical), review records at exact heads, authority grep clean (seed = injected-price mechanism). No workflow auto-deploys to the VPS ⇒ master merge is source-only; install stays a release row |
| 11:46 | seat | m2 / Fable | ruling | — | RECORDED | ECON rulings | HK bridge CLOSED, no account change; prospective HK opening checkpoint = 2026-06-24 backup account (corroborated: strikes/qty/cash via one external source; ASSUMED: 06-22-open settlement timing, seeding code not in git) — disclosed in every HK performance claim. D-ACCT-1 = wave-2 P0 for ECON: an existing-but-invalid account.json must FAIL CLOSED (no mark, no save, quarantine copy, alert), never a fresh book; remove reset_cost_basis_to_market() (no caller) — reserved acceptance. #1432 never merges alone: fold into the A12 common-window build with #1433 falsifiers. firm_allocator._latest_benchmark sorted-glob hazard → ECON wave 2. #726/#727/#728 close as superseded after #1709 lands; #824 continues. W3 census lane AUTHORIZED (one C1 lane, read-only) |

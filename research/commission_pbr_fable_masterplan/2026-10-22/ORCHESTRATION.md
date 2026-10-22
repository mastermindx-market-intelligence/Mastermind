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

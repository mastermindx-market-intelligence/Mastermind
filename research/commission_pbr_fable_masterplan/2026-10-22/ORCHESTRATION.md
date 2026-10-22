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
| 07:30 | W0 seat | m2 / Fable | commission | — | COMMISSIONED | this directory | frontier recovered; four domain owners briefed; see FABLE_START_HERE.md |

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

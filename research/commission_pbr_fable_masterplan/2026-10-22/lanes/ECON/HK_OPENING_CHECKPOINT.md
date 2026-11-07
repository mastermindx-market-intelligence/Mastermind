# HK opening checkpoint and required performance disclosure (pbr-econ, 2026-10-22)

Status: **RULED.** The seat accepted ECON wave 1 on 2026-10-22; the ruling is recorded in
`research/commission_pbr_fable_masterplan/2026-10-22/ORCHESTRATION.md` (commit 8e86d17a).
Evidence: `HK_BRIDGE.md` §10 and `hk_bridge_external_quotes.csv` in this directory (they land via #1712).

## Ruling

1. **The HK quantity bridge is CLOSED.** There is no account change, repair trade, balancing fill or seed
   rewrite. `fills.jsonl` stays append-only and unedited. Rows 1–15 are annotated by the bridge
   table and the external-quote table.
2. **Prospective HK opening checkpoint (MASTERPLAN §11.3).** The HK book's qualified opening state is
   the **2026-06-24 backup account**, which is equivalent to the live account replayed to that date.

| Component | Status | Basis |
|---|---|---|
| Strikes | CORROBORATED (one external source) | Exact match to the external 2026-06-22 open (Yahoo) for all six symbols |
| Quantities | CORROBORATED (one external source) | Strikes and notional (H1), plus the fills replay from 06-24 (H2) |
| Cash | CORROBORATED (one external source) | Same notional on both ledgers; the residual equals the documented cash-yield accrual |
| Settlement timing (06-22 open) | **ASSUMED** | Doctrine. The VPS-era seeding code is not in git, so this is not read from the code that ran |

## Required disclosure: every HK performance claim

Every HK book performance claim must carry the disclosure below, verbatim or with the same content. This covers
NAV, return, alpha, benchmark-relative, drawdown, attribution and any page, report or model
narrative that quotes them. A claim without it is not economically qualified.

> HK book opening state = the 2026-06-24 backup account (prospective checkpoint, MASTERPLAN §11.3).
> Strikes, quantities and cash are corroborated against one external source (Yahoo). The
> 2026-06-22-open settlement timing is ASSUMED: it is doctrine, and the seeding code is not in git. The fills log
> carries a bounded audit-trail error (7,026.14 HKD, 0.6993% of NAV) in six seed rows. It is not a NAV
> or cash misstatement.

## What would upgrade it

- A second independent price series (an exchange or Stooq) for the six 2026-06-22 opens. This would raise
  "corroborated by one source" to "independently corroborated".
- The VPS-era seeding code, or a contemporaneous log of it. This would move settlement timing from ASSUMED to
  CORROBORATED.

Operational correctness, economic qualification and investment value stay separate verdicts. This
file supports only the first two. No investment-value claim is made.

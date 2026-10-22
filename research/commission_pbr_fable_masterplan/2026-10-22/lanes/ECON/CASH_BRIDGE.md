# CASH BRIDGE — dated non-trade cash residual decomposition (packet pbr-econ L-E2, census C1)

Date: 2026-10-22 · Author: bounded census worker (ECON lane) · Read-only over the
capture copy `~/lanes/tmp/pbr-econ-le2/live-data/` (captured 2026-10-22T07:31:19Z).

## Result in one line

**The entire non-trade cash residual in all three books is the daily cash-yield sweep.**
Zero UNEXPLAINED cents remain in US, CN, or HK. The CN book additionally carries one
repair artifact (the 2026-06-22 tiny-trim scrub) whose cash effect is exactly preserved —
it only *looks* like residual because the fx repair deleted the 06-23 NAV row that hid it.

## Method

For consecutive `nav_history.jsonl` rows t−1 → t:

```
non_trade_t = cash_t − cash_{t−1} − net_fill_cash(dates in (t−1, t])
net_fill_cash(d) = Σ(sell value) − Σ(buy value)   from fills.jsonl (persisted 2dp values)
```

First row uses `starting_nav` as base (minus fills dated ≤ it); the tail uses
`account.json` `cash` (minus fills dated after the last row). Sweep model from
`portfolio/paper_account.py::accrue_cash_yield` (repo @ origin/master, this worktree):
one accrual per (book, calendar date), before `mark()`,
`cash = round(cash × (1 + rate/252), 2)`, rate = env `CASH_YIELD_ANNUAL` default 0.04,
skipped when `cash_yield_through == asof`, `cash <= 0`, or settlement receipts are
pending; called from `app/scheduler.py` (~line 1348) inside `daily_mark` behind a
per-venue trading-date gate (US: `portfolio/market_calendar`; CN/HK:
`portfolio/china_calendar`) and a book lock. Classification tries k = 1..10 compounded
accrual days on two bases (previous row's cash; previous cash + that day's fills —
builds can fill before or after the day's sweep), tolerance 0.02 per accrual day.

**Accrual start (commit):** `2b04b5e72` — 2026-06-23 01:32:16 −0700,
"feat(desk): Flagship multi-seat desk + accountability loop + observability"
(`git log -S accrue_cash_yield -- portfolio/paper_account.py app/scheduler.py` → exactly
one commit). No accrual can predate 2026-06-23; observed first accrual is the US book on
2026-06-23 (+71.37 on 449,600.81 — exact). The US 06-21/06-22 rows show zero accrual,
consistent with the commit date.

Input integrity: every manifest entry present in the local copy was sha256-verified —
**180/180 match, 0 mismatches** (the other 232 manifest entries are `benchmark/**` and
are not part of the local capture; unused here). All 23 files actually used are among
the verified (list in the RETURN block).

## Per-book totals (residual identity closes to the cent)

| Book | Residual | Σ YIELD (k=1) | Σ YIELD_MULTI (k≥2) | Σ REPAIR | Σ ROUNDING | Σ UNEXPLAINED |
|---|---|---|---|---|---|---|
| US (USD) | **+9,214.51** | +9,214.49 (84 days) | — | 0.00 | +0.02 | **0.00** |
| CN (CNY) | **+5,782.62** | +5,645.73 (77 days) | — | **+136.89** | 0.00 | **0.00** |
| HK (HKD) | **+5,240.56** | +5,170.71 (81 days) | +69.85 (1 row, k=2) | 0.00 | 0.00 | **0.00** |

Accrual-day totals: US 84, CN 79 (77 visible + 2 hidden behind the deleted 06-23 row),
HK 83 (81 single-day rows + one k=2 row spanning the deleted 06-23 row).

Cash identity (ending cash = opening + Σ flows + residual), exact for all three:

- US: 1,000,000.00 − 306,529.32 (net fills) + 9,214.51 = **702,685.19** = `account.cash` ✓
- CN: 1,000,000.00 − 616,463.68 + 5,782.62 = **389,318.94** ✓
- HK: 1,000,000.00 − 629,677.87 + 5,240.56 = **375,562.69** ✓

Tails: all three books end with `account.cash` == last NAV row cash (US 10-22 row is a
pre-sweep re-mark of the 10-21 state; `cash_yield_through` = 2026-10-21 in all books),
and no fills are dated after the last row → tail non-trade = 0.00 for all books.
**Negative cash: never** — no `account.json` state or NAV row in any book has cash < 0
(the `max(0.0, cash − value)` clamp in the buy paths was never the binding explanation
for any bridge row).

## UNEXPLAINED rows

None, in any book. (Every non-zero non-trade delta matched either a k≥1 sweep candidate
within 0.02/accrual-day, or a cited repair with a verified backup decomposition.)

## REPAIR rows (CN only) — the 2026-06-22 tiny-trim scrub

Two CSV rows, same root cause, netting to +136.89 = exactly the two sweep days the
deleted row hid:

1. **CN 2026-06-22: +14,015.61** — `scripts/scrub_cn_tiny_trims.py` +
   `portfolios/china/_backup_scrub_tiny_trims_20260623-052644/`: the 2026-06-23 01:36 UTC
   rebalance manufactured two fractional sells (688411.SS 19.826594 @ 286.98 = 5,689.84;
   688585.SS 51.207122 @ 162.59 = 8,325.77) that the Brain never intended. The scrub
   removed those two fills from `fills.jsonl` and debited the proceeds from cash — but
   the proceeds were already inside the 06-22 NAV row when it was written:
   `1,000,000 − 568,841.84 (7 remaining fills) + 14,015.61 = 445,173.77` exact (matches
   the pre-scrub account backup cash 445,173.7680). So against the *current* fills
   ledger the 06-22 row is overstated by exactly the scrubbed proceeds.
2. **CN 2026-06-24: −13,878.72** — the debit side, surfacing from behind the NAV row the
   fx repair deleted. Verified decomposition against the backup chain
   (`_backup_fx_repair_20260624-173547/`): post-scrub account cash 431,158.16 →
   (+68.44 sweep 06-23) → deleted 06-23 row 431,226.60 → (+68.45 sweep 06-24) → backup
   06-24 row/account 431,295.05 (`cash_yield_through` 2026-06-24) → (+242,746.04 net of
   the four 06-24 fills, executed after the 17:35Z repair) → current 06-24 row
   674,041.09. Sum: −14,015.61 + 68.44 + 68.45 = −13,878.72 exact.

The scrub is cash-neutral overall (fills removed AND cash debited); what leaked into the
"residual" is only the two accrual days preserved on either side of the deleted row.

## Deleted / rewritten NAV rows

- **CN + HK: 2026-06-23 row DELETED** by the fx repair (`_backup_fx_repair_20260624-173547/`,
  both books carry it). Deleted rows: CN `{cash: 431226.60, invested: 82996.93, nav: 514223.53}`,
  HK `{cash: 220034.92, invested: 97051.40, nav: 317086.32}` — both are the phantom-crash
  artifact of CNY/HKD positions marked at USD values (invested ÷ ~7). The deletion HID one
  accrual day per book; the accrual cash itself is intact (CN's two hidden days are the
  +136.89 inside the REPAIR rows above; HK's is the k=2 YIELD_MULTI row
  06-24 = +69.85 = two sweep days on 220,000.00 → 220,069.85 exact, matching the deleted
  row chain 220,000 → 220,034.92 → 220,069.85).
- **CN + HK: 2026-06-24 row REWRITTEN** (same repair): invested corrected
  (CN 559,941.84 → 317,195.81; HK 759,446.23 → 685,565.02); **cash not altered by the
  repair** — the current row's cash equals backup cash + that day's fills exactly
  (CN 431,295.05 + 242,746.04 = 674,041.09; HK 220,069.85 + 73,881.21 = 293,951.06),
  i.e. the row was later replaced by the normal post-fill `mark()`.
- **US: 2026-06-21 row REWRITTEN** by the NVDA/AVGO removal
  (`_backup_remove_nvda_avgo_20260622-221155/autonomous/`): cash 260,000.00 → 480,000.00
  (+220,000.00), NVDA (522.094 sh) / AVGO (267.412 sh) lots and their fills removed in the
  same operation — the visible ledger (starting_nav, fills, rows) is self-consistent
  afterwards (first-row non-trade = 0.00), so it contributes nothing to the residual.
- **CN + HK: 2026-07-30 row REWRITTEN** by the incident repairs
  (`_incident_backup_ashare_quote_route_20260730T231834Z/` for CN via
  `scripts/repair_live_books_20260730.py`; `_incident_backup_20260730_missing_yfinance/`
  for HK): invested/spy_nav rewritten, **cash byte-identical** in backup vs current row
  (CN 428,151.94; HK 333,220.14; both backups' accounts agree). No cash effect.
- `scripts/repair_live_books_20260730.py` also repaired the *flagship* book, which is not
  one of the three census books.

## Sweep behavior findings (the two packet questions)

- **Non-trading days: never accrued.** Every NAV row dated on a weekend or venue holiday
  shows zero non-trade delta (e.g. US Sun 06-28/07-19 rows, CN Golden-Week rows 10-01…10-07,
  HK Mon 10-19 row = same cash as 10-16). Notably the CN book has Sunday NAV rows with
  FILLS (06-28 +48,200.80; 07-05 −91,722.53; 07-12 −39,935.17 — build paths are not
  venue-gated) and **still zero sweep on those Sundays** — the accrual gate held.
- **Never twice per date.** `cash_yield_through` makes the sweep idempotent per (book,
  date); every bridge row matched exactly k=1 (or k=2 only where a row was deleted).
  Base ordering varies with build timing: on 0 US / 8 CN / 11 HK fill-days the sweep
  ran BEFORE the day's fills (base = previous row's cash; the day's later fills land in
  the replaced row), and on 26 US / 22 CN / 18 HK fill-days fills preceded the sweep
  (base = prev+fills). Both orderings are the same single accrual. (Counts corrected
  2026-10-22 per lr-w1-r1 finding 1; the earlier text inverted the two labels.)
- **Missed accrual days are lost forever** (no backfill): 2026-07-27 and 2026-07-28
  (Mon/Tue) have no NAV rows and no accruals in ALL THREE books — only one sweep day
  exists across the 07-25 → 07-29 span (k=1 matches exactly on 07-29). This coincides
  with the 07-27 heavyweight clobber-repair incident window. Foregone yield ≈ 0.16‰ of
  cash/day (US ~205 USD, CN ~136 CNY, HK ~106 HKD total) — context only; it is *missing*
  from the residual, not part of it.

## Evidence still missing / open questions

1. **Venue-calendar ground truth**: the capture contains no exchange-calendar artifact,
   so "closed venue" vs "lock-held/mark-skipped" cannot be distinguished for single-book
   weekday skips with a row but no accrual (e.g. HK Mon 2026-10-19; typhoon days are
   plausible). Residual impact: zero either way.
2. **Rounding provenance of the US +0.02** (2026-06-22 row): cash is applied unrounded
   (`state["cash"] ± shares×px`) while fills persist 2dp values, so ±0.005/fill drift is
   expected; the 0.02 leftover is within that envelope and cannot be attributed to
   specific fills without unrounded execution values (not persisted anywhere).
3. **CASH_YIELD_ANNUAL env**: the live service's env was not captured; the bridge assumes
   the default 0.04. Every one of the 246 accrual-day matches at rate/252 within 0.02
   confirms 4% empirically (a 4.05% rate would misfit by >1.2/day), so the assumption is
   self-verifying from data.
4. The 07-27/07-28 outage root cause (which process was down, why `daily_mark` missed two
   weekdays) is outside this capture — `agentos`/incident records in the Macro repo would
   carry it.

## Files

- `cash_bridge_us.csv`, `cash_bridge_cn.csv`, `cash_bridge_hk.csv` — one row per NAV-row
  gap + tail; columns `date,cash_prev,cash,net_fill_cash,non_trade,expected_yield,k_accruals,class,evidence`.
- `tools/cash_bridge.py` — stdlib-only reproducer: `python3 tools/cash_bridge.py
  <live-data-dir> --outdir <outdir>` (reads only; writes only the three CSVs; prints the
  totals and the bridge-vs-residual identity check).

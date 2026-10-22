# PBR ECON W3 — economic-truth census (census, C1, read-only)

Worker: `pbr-econ-w3c-r1` · 2026-10-22 · capture `~/lanes/tmp/pbr-econ-w3c/live-data/`
(taken 2026-10-22T07:31:19Z from `root@146.190.142.17:/opt/mastermind-live-data`).

**Inputs verified.** All **412/412** manifest files sha256-verified against `MANIFEST.json`,
**0 mismatches**; **104** of them read by this census. Reference
`ref/yahoo_close_reference.csv` sha256 matches `d1fa0c44…689b` (Yahoo closes, US symbols,
2026-06-15..2026-09-17, split/dividend **adjusted** — a reference, not truth). Tool:
`tools/w3_census.py` (stdlib + the single allowed `portfolio.paper_account.valuation`
import, always called with an explicit pure `state=` dict; no network; reads only).
CSVs: `w3/w3_t{1..5}_*.csv`.

**Method notes.** T1 held positions come from reverse replay of the final `account.json`
through `fills.jsonl` (fills dated d apply on d; |shares| < 1e-6 is flat). T2 compares each
`polygon-eod` price to the reference close of the same date (when it exists) and of the
previous reference date; symbols whose mark/reference ratio sits at a persistent offset
k≠1 with <1% dispersion are flagged `REFERENCE_ADJUSTED` and excluded from the
after-hours statistic (both views reported). T4 matches each fill price against
REF_CLOSE_D → REF_CLOSE_PREV → MARK_D → MARK_PREV (relative 1e-6, then 0.5 bp).

---

## T1 — A02 `valuation()` incidence on historical NAV rows (`w3_t1_a02_incidence.csv`)

| book | rows | classified | no-evidence/undeterminable | FRESH | CARRIED | UNATTESTED | UNPRICED | QUALIFIED | PROVISIONAL | WITHHELD |
|---|---|---|---|---|---|---|---|---|---|---|
| US (`portfolio/`) | 40 | 22 | 18 | 141 | 0 | 0 | 5 | 20 | 0 | 2 |
| autonomous | 91 | 77 | 14 | 321 | 1 | 0 | 0 | 76 | 1 | 0 |
| hk | 89 | 1 | 89 | 0 | 7 | 0 | 0 | 0 | 1 | 0 |
| china | 88 | 1 | 88 | 0 | 9 | 0 | 0 | 0 | 1 | 0 |

- US rows without a same-day marks file (18 → `NO_EVIDENCE_FILE`): 06-18..07-02
  (14 rows, incl. a **pre-inception 06-18 row** — nav 993,732.86 / invested 741,900 —
  and 3 weekend rows) plus the no-file weekend dates 07-04, 07-05, 07-12, 07-19.
- **WITHHELD/PROVISIONAL rows and their non-FRESH symbols:**
  - US 2026-07-03 WITHHELD — `JNJ` (held 154 sh; absent from that day's union-mark file).
  - US 2026-07-30 WITHHELD — `LNG MTUM SMH XLK` (the quote-route incident day: the 07-30
    marks file is 15 `yahoo-parquet` + 3 `last-good-carry` + **0** `polygon-eod`; held
    XLV was priced from it, the four above were absent).
  - autonomous 2026-07-30 PROVISIONAL — `MCY` (`last-good-carry`, stale_days 1 → CARRIED).
  - hk / china final states (2026-10-21, persisted-carry path, all lines CARRIED):
    PROVISIONAL; nav 1,004,800.23 / 944,849.17.
- Held symbol absent from that day's union-mark file (or null price): exactly
  `2026-07-03:JNJ; 2026-07-30:LNG MTUM SMH XLK` — nothing else in 99 classified rows.
- **Reading:** on clean days the captured union-mark files covered every held line, so the
  A02 builder path yields QUALIFIED rows; both US WITHHELD rows coincide exactly with
  evidence degradation (the 07-03 single-name gap and the 07-30 incident), not with
  valuation-rule conservatism.

## T2 — after-hours effect vs the reference (`w3_t2_afterhours.csv`)

77 files · 1,071 entries · 994 `polygon-eod`-with-price. Reference window ends 09-17 →
266 rows have no same-day reference. **54 rows REFERENCE_ADJUSTED** (constant scale offset
k≠1 vs the adjusted Yahoo series): APH k≈2.00131 (2:1 split scale), BLK 1.00618,
JNJ 1.00592, SGOV 1.00534. MCY/QUAL pin k≈1 (marks == reference closes).

| statistic (676 compared, adjusted excluded) | value |
|---|---|
| exact (|dev| < 0.5 bp) | 136 (20.1%) |
| median |dev| | 9.80 bp |
| p95 / max |dev| | 60.18 bp / **887.69 bp** (URI 07-22: mark 1125.00 vs close 1033.28 — also +1,119 bp vs the *previous* close, i.e. above both sessions) |
| >10 bp / >50 bp | 334 (49.4%) / 44 |
| including adjusted rows (728) | median 11.09 bp · p95 79.81 bp · max 10,135 bp (APH ≈ 2× scale) |
| equal to previous reference close | 33 within half a cent (5 exactly): **20 on 07-03** (the half-day has no reference row; marks equal the 07-02 close), **8 on 09-07 — Labor Day, no session — stamped `polygon-eod`, `stale_days: null`, at Friday's close**, 5 scattered (07-13, 07-20, 08-06, 09-16, 10-07) |
| prices with >2 decimals | 134 (e.g. EME 812.4485, CBRS 193.2541 — raw aggregates) |
| file `ts` UTC hour | 76 files at 22:3x (post-close); **1 file (as_of 07-15) written 2026-07-16T01:06:50Z** |

**Reading:** the `polygon-eod` label is not reliably a same-session EOD close — only a
fifth of comparable entries match the adjusted reference within 0.5 bp, half deviate
>10 bp, and the extremes are intraday/rounded quotes (URI) or prior-session closes on
holidays/short days presented with no staleness marker. A02 classes all of these FRESH
whenever `stale_days` is null — the label alone cannot qualify a bar.

## T3 — missing-bar rate (`w3_t3_missing_bars.csv`)

- **Overall missing rate 7.19%** (missing = entry not `polygon-eod`-with-price;
  77 files, 1,071 entries). **60 of 77 dates** have rate > 0.
- **2026-07-30: rate 1.0** — 0/18 polygon (15 yahoo-parquet + 3 last-good-carry, the
  peer-sentinel / missing-yfinance incident day). Thereafter **`^HSI` is a null-price
  entry in every file** 07-31..10-21 (11.1% of a 9-symbol union, 5.6% of 18) — an
  unpriced HK index placeholder, the persistent background miss.
- **Gap dates (US weekdays 07-03..10-21 with NO marks file): 2026-07-27 and 2026-07-28
  only** — no autonomous NAV rows those days either; 07-28 is the day the flagship
  pending-target test-contamination was neutralized (snapshot README).
- Holiday note: 09-07 has a file, but its 8 priced entries are prior-close stamps (T2).

## T4 — fill-writer stamp per fill (`w3_t4_fill_stamps.csv`)

**Writer intent (current code).** `bot/settle.py:1036-1044` (`settle_open` docstring):
fills are booked "at the live open marks"; "USD Brain books retain their Open-price
preference (Polygon day.o → Yahoo Open → last-price fallback)", selected in
`_open_price_usd` (`bot/settle.py:526-616`). `execute_or_queue` (`bot/settle.py:182-186`)
books fills only when OPEN and uses "`prices` — the same marks the book uses for NAV, so
fills and NAV stay consistent"; when CLOSED it queues and books **no** fills.
`fill_pending` (`portfolio/paper_account.py:2691-2705`) likewise fills "at the live
`prices` (the market price at the open)" and stamps `from_pending: true`
(`:2761`, `:2789`). So the current writer intends the **settlement-session open — a
SETTLEMENT_PRICE — never the decision-time quote** (the decision quote is retained only as
`decision_snapshot` metadata). Fill facts persist as shares 6dp / price 4dp / value 2dp
(`_persisted_fill_facts`, `portfolio/paper_account.py:147-153`); the id-stamping WAL writer
is `_commit_account_and_fills` (`portfolio/paper_account.py:1320-1377`).

**Match → stamp mapping:** REF_CLOSE_D / MARK_D → SETTLEMENT_PRICE (same-session EOD
close); REF_CLOSE_PREV / MARK_PREV → DECISION_QUOTE (prior-session close, the quote known
at decision time); NO_MATCH → attests neither; UNDETERMINABLE → no evidence.

| book × writer | REF_CLOSE_D | REF_CLOSE_PREV | MARK_D | MARK_PREV | NO_MATCH | UNDET. |
|---|---|---|---|---|---|---|
| US × FROM_PENDING (→ stamp) | 9 SETTLE | 1 DECISION | 0 | 0 | 166 neither | 0 |
| US × LEGACY | 1 SETTLE | 0 | 0 | 1 DECISION | 4 neither | 0 |
| autonomous × SETTLE_IDS | 0 | 0 | 0 | 1 DECISION | 11 neither | 0 |
| autonomous × LEGACY | 2 SETTLE | 2 DECISION | 0 | 0 | 74 neither | 6 |
| hk × SETTLE_IDS / LEGACY | — | — | — | — | — | 15 / 81 |
| china × SETTLE_IDS / LEGACY | — | — | — | — | — | 32 / 80 |

- The 9 US REF_CLOSE_D hits are one batch: the **07-02 liquidation sells** (SMH, XLK, DY,
  LQDT, ANET, IREN, ADAM + INCY buy/sell) priced **exactly at that day's Yahoo close**
  (dev 0.0 bp, −454…−1,039 bp vs the prior close) — an EOD settlement stamp.
- The remaining 170 US and 11 id-stamped autonomous fills match neither EOD close at
  0.5 bp: 82 sit **between** the prior and same-day closes, 89 gapped beyond both
  (e.g. MSFT 10-09 buy at 528.235: +612 bp vs prior close, −123 bp vs the day's mark;
  USMV 08-12 sell at 100.62: +18 bp vs close, −11 bp vs prior mark) — consistent with the
  intended open/intraday settlement stamp, and proof the stamp is not either EOD close.
- **Value check** (`|shares·price − value| ≤ 0.01`): 486/487 pass. Failure: **US 07-02
  INCY sell — 51,300.1791 vs booked 51,300.16 (1.91¢)**. (China 688062.SS 08-13 buy lands
  exactly on the 1¢ boundary and passes.)

## T5 — US book repair direction (`w3_t5_us_repairs.csv`)

| event (book, snapshot date) | direction | mechanism |
|---|---|---|
| pre_nvda_avgo_exit (US, 06-22) | **AWAY** | NVDA 22.3077 + AVGO 65.3944 removed from the account with **no exit fills** (0 NVDA/AVGO rows in live fills). Replay@06-22 from the final account matches the snapshot on all 23 other names (max share diff = AVGO 65.394 exactly); replay cash +33,935.16 vs snapshot (intraday 15:01 snapshot vs full-day replay). No committed repair script in this repo (pre-rebuild op; cf. `a81448b40` conviction de-overfit). |
| remove_nvda_avgo_autonomous (06-21) | **AWAY** | Backup holds the PRE state (NVDA 522.0941 + AVGO 267.4122, cash 260,000). Live autonomous fills contain **zero** NVDA/AVGO rows; replay@06-21 diff = NVDA 522.094 exactly, cash +229,214.51 → the later removal edited the account only. |
| remove_nvda_avgo_heavyweight / self_directed | UNDETERMINABLE | PRE-state backups only; neither book is live in the capture. |
| test_contamination (US, 07-28) | **NEUTRAL** | Deleted a contaminated `pending_target.json` (`{SMH: 0.25}`, asof 07-01, queued_at 07-25 — the pytest fixture, per the snapshot README). No account/fills touched. Root cause closed by conftest book-root isolation (`265baae57`, `6c8a0a556`). |
| peer_sentinel_liquidation (US, 07-30) | **TOWARD_FILLS** | `scripts/repair_live_books_20260730.py::_restore_flagship` (L128-250) removed exactly the 5 false liquidation sells from `fills.jsonl` and restored the pre-incident lots (SMH/MTUM/XLK/XLV/LNG). Reconstructed repaired state vs live-ledger replay@07-30: **max share diff 0.000000** (cash accrual deliberately preserved). The snapshot itself — post-liquidation DD dust + cash 946,916.89 — diverges from live replay by max 332.0 sh (XLK) / −262,289.07 cash, which is the divergence the repair removed. |
| heavyweight_clobber (07-27) | UNDETERMINABLE | `account.json.clobbered` (cash 0, no positions, inception null) + `nav_history.jsonl.clobbered` quarantined; no live heavyweight book in the capture — book left unenrolled (cf. ECON `CONTRACTS.md` E7). |

**Reading:** of the six events, one (peer-sentinel) is a documented, fill-restoring repair
whose result is exactly fill-consistent; the June NVDA/AVGO removals moved accounts **away
from** the fills ledger (still visible today as the only replay inconsistency in the US
and autonomous books); the contamination fix and the clobber quarantine had no account
direction.

## Caveats

- The reference is Yahoo **adjusted** closes ending 09-17; deviations conflate timing with
  corporate-action scale — `REFERENCE_ADJUSTED` separates the scale family (APH/BLK/JNJ/
  SGOV), the rest is timing.
- Reverse replay assumes fills fully explain share history; where repairs edited accounts
  (AWAY events) the replay inherits and measures exactly that divergence.
- T5 snapshot dates are "max fill date inside the snapshot" — coarse for intraday backups
  (the 06-22 15:01 pre-nvda snapshot predates part of that day's fills; its cash diff
  reflects that).
- 07-03 has no reference row (half-day absent from the parquet), so 07-03 marks were
  tested against 07-02 only.
- HK/CN per-date evidence does not exist in the capture: their historical rows are
  UNDETERMINABLE by design; only final states were classified (persisted-carry path).
- `valuation()` was called pure with explicit `state=` throughout;
  `portfolio.marks._stale_max_days()` reads worktree config (read-only). Nothing outside
  `research/.../ECON/{tools/w3_census.py, w3/}` was written; capture tree untouched.

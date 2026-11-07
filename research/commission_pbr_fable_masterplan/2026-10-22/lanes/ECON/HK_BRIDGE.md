# HK six-symbol quantity bridge — census (pbr-econ L-E1, 2026-10-22)

Worker: bounded census lane under `pbr-econ` (Portfolio Bot Rebuild #1693).
Inputs: read-only capture `~/lanes/tmp/pbr-econ-le1/live-data/` + this worktree's git history.
Tool: `tools/hk_bridge.py` (stdlib-only, read-only) → `hk_bridge.csv`.

## 0. Input integrity (MANIFEST.json verification)

Every file used was sha256-verified against `MANIFEST.json` (paths matched on the suffix after
`opt/mastermind-live-data/`). Result: **180/180 MATCH, 0 mismatches, 0 unlisted** —
102 non-marks files (all HK book files, both HK backups, deploy_lag, US/CN/legacy files consulted
for context) + 78 marks files. AppleDouble `._*` entries excluded (not in manifest).

## 1. Verdict summary

> **ECON adjudication (§10) supersedes the per-symbol BOUNDED status below.** An independent
> public daily series shows every account strike equals the 2026-06-22 HK open and every
> `fills.jsonl` initial price equals the 2026-06-18 close. All six symbols are **EXPLAINED**.
> §1–§9 are the census lane's report, kept as delivered.

| Question | Verdict |
|---|---|
| **H1** (all six diffs created 2026-06-21/22, present in 06-24 fx-repair backup; account struck same notional at a different price) | **CONFIRMED** — reproduces to ≤3.4e-9 shares for all six (tolerance 1e-6) |
| **H2** (no later event changed any HK quantity outside fills) | **CONFIRMED** — replay(06-24 backup + all later fills) reproduces the final account and the 07-30 incident backup to ≤7.2e-7 shares; the only non-fill cash movement is the documented cash-yield accrual |
| Per-symbol status | All six **BOUNDED**: mechanism proven with evidence; which side carried the true market price is **undecidable from this capture** |
| Price origin | `entry_price` in `positions_ledger.json` carries the account strikes verbatim (downstream copy). The seeding code itself is **NOT in the captured git history** — the VPS ran pre-commit code (`bot/hk.py` first appears in `2b04b5e7`, 2026-06-23 08:32 UTC, after the 06-22T16:02Z ledger open). No seed table, no commit containing the strike prices or notionals (`git log -S` for `439.0`, `140000`, share counts: no hits). |

## 2. Mechanism (proven)

The account was seeded on 2026-06-21 (8 legs) and 2026-06-22 (7 legs) by striking each HKD
notional at an account-side price that differs from the price `fills.jsonl` recorded for the same
legs. Both sides are internally consistent — each divides the same notional by its own price:

- fills leg: `shares = value / fill_price` (e.g. 1024.HK 80000 / 47.24 = 1693.480102)
- account leg: `shares = value / account_strike` (e.g. 1024.HK 80000 / 46.9 = 1705.75692964)

Cash is identical on both legs (same notional), so **cash never diverged — only share counts did**.
The implied account strike per symbol, derived from the 06-24 backup as
`(net initial notional) / backup_shares`, lands on an exact 2-dp price for all eight seeded
symbols, and the residual at that clean strike is ≤3.4e-9 shares:

| symbol | account strike | fill price(s) | notional (HKD) | backup shares 06-24 | fill-side replay | diff at backup |
|---|---|---|---|---|---|---|
| 0700.HK | **439.00** | 440.20 (buy 140000 06-21; sell −10000 06-22) | 130,000 | 296.12756264 | 295.320309 | **+0.807254** |
| 0981.HK | **78.80** | 76.50 (120000 06-21; 10000 06-22) | 130,000 | 1649.74619289 | 1699.346405 | **−49.600212** |
| 1024.HK | **46.90** | 47.24 (80000 06-21) | 80,000 | 1705.75692964 | 1693.480102 | **+12.276828** |
| 1929.HK | **12.33** | 12.39 (100000 06-21; 10000 06-22) | 110,000 | 8921.33008921 | 8878.127522 | **+43.202567** |
| 3988.HK | **5.23** | 5.27 (50000 06-22) | 50,000 | 9560.22944551 | 9487.666034 | **+72.563412** |
| 3993.HK | **18.94** | 18.87 (110000 06-21; 10000 06-22) | 120,000 | 6335.79725449 | 6359.300477 | **−23.503222** |
| 1398.HK | 6.85 | 6.85 | 80,000 | 8759.12408759 | 8759.124088 | 0 (control) |
| 2628.HK | 28.02 | 28.02 | 100,000 | 3568.87937188 | 3568.879372 | 0 (control) |

Notes:
- 0700.HK's strike fits BOTH initial legs simultaneously with one price (buy 140000/439 − sell
  10000/439 = 296.12756264 exactly), so the account applied one strike per symbol across legs.
- 1398.HK and 2628.HK are natural controls: for them the two sources happened to agree, and they
  show zero diff — the mechanism only bites where the two prices differ.
- The 06-24 backup contains **no 06-24 fill effects** (0981/3993/1929 06-24 sells and the 0700
  06-24 buy are absent from the backup quantities), confirming the snapshot predates the 06-24
  fills — and therefore that all six diffs existed before any later event.
- The final per-symbol diffs equal the backup-date diffs (later fills moved both ledgers
  identically): +0.807253 / −49.600212 / +12.276828 / +43.202567 / +72.563412 / −23.503222 —
  matching the commission packet's reproduced values.

`first_seen`: every diff is already fully present in the earliest captured account snapshot
(`portfolios/hk/_backup_fx_repair_20260624-173547/account.json`, taken 2026-06-24 17:35 local);
by construction they were created on the 2026-06-21/06-22 initial legs (rows 1–15 of
`fills.jsonl`, 1-indexed).

## 3. Oversell trace (four cited rows)

Replaying `fills.jsonl` from empty, exactly four sells take fill-side inventory negative — the
cited rows — and each is a **full-position close sized from the (phantom-enlarged) account
inventory**:

| row (1-idx) | date | symbol | sell shares @ price | replay inventory before | account inventory before | result |
|---|---|---|---|---|---|---|
| 26 | 2026-06-29 | 1024.HK | 926.771442 @ 41.00 | 914.494614 | 926.771442 (= 914.494614 + 12.276828) | account 0, replay **−12.276828** |
| 32 | 2026-07-01 | 1929.HK | 3496.234366 @ 10.90 | 3453.031799 | 3496.234366 (= 3453.031799 + 43.202567) | account 0, replay **−43.202567** |
| 63 | 2026-08-03 | 3988.HK | 5994.595648 @ 5.51 | 5922.032236 | 5994.595648 (= 5922.032236 + 72.563412) | account 0, replay **−72.563412** |
| 78 | 2026-08-07 | 1024.HK | 561.000000 @ 44.24 | 548.723172 | 561.000000 (= 548.723172 + 12.276828) | account 0, replay **−12.276828** |

In each case the sell size equals the account's own position to the last decimal (the seller sold
"everything it held"), so the account-side ledger closed cleanly while the fill-side ledger went
negative by exactly the phantom quantity. No clamping fired because in account-land the shares
existed. (A fifth sub-1e-4 "deficit" on 9988.HK row 82 is 6-dp rounding dust, not an oversell.)

Direction by symbol:
- **1024.HK, 1929.HK, 3988.HK** (account strike < fill price → account over-issued shares):
  phantom shares were *sold for cash* at the close-out prices above.
- **0981.HK, 3993.HK** (account strike > fill price → account under-issued shares): the account
  sold only its (under-sized) position; per the fill-side truth **49.600212 sh (0981)** and
  **23.503222 sh (3993)** remained held-but-never-recorded and were never monetized.
- **0700.HK** (over-issued, strike 439 < 440.2): still open — the account carries 0.807253 more
  shares than the fills justify.

## 4. H2 verification (no later quantity event outside fills)

Three independent checks, all from `tools/hk_bridge.py`:

1. **06-24 backup → final account.** Seeding the replay with the backup's exact positions/cash
   and applying every fill dated > 2026-06-23 (recorded share counts, fill prices) reproduces the
   final `account.json` for all seven held symbols with residual ≤ 3.5e-7 shares (float64 dust
   from 6-dp recorded shares), and cash 370,391.98 vs actual 375,562.69 — residual +5,170.71,
   consistent with the documented ~4%/yr cash-yield accrual (119 days × ~4%/365 × avg cash
   ≈ 397k → ≈ 5.2k). The 0700.HK avg_cost is also reproduced from the backup base:
   replayed 448.3610594 / value-based 448.3610632 vs account 448.3610620 (agreement to ~6e-9
   relative; the tiny gap is the same 6-dp/2-dp rounding seam).
2. **06-24 backup → 07-30 incident backup.** Applying fills 2026-06-24..2026-07-29 reproduces all
   ten positions of `_incident_backup_20260730_missing_yfinance/account.json` to ≤ 7.2e-7 shares;
   cash residual +1,493.89 over 36 days (same accrual, avg cash ≈ 379k). The 07-30 incident
   recovery (`INCIDENT.json`: "re-mark live account") therefore changed **marks only, zero
   quantities**.
3. **The 06-24 fx repair changed no HK quantity.** Its backup preserves the pre-repair account
   with the same six diff-bearing quantities; the repair's visible effect in the capture is on
   NAV rows only — the FX-broken 2026-06-23 nav row (nav 317,086.32, `spy_nav` 128,705.63) present
   in `_backup_fx_repair_20260624-173547/nav_history.jsonl` is absent from the live
   `nav_history.jsonl` (jumps 06-22 → 06-24). Cash reconciles across it exactly.

**H2: CONFIRMED for quantities.** The only HK quantity changes after inception are the fills
themselves. Non-fill cash movement is limited to the documented cash-yield accrual.

## 5. Price origin — what was found, what was not

Found:
- The account strikes are recorded verbatim as `entry_price` in `positions_ledger.json`
  (`brain:0700.HK` → 439.0, `brain:0981.HK` → 78.8, `brain:1929.HK` → 12.33, `brain:3988.HK` →
  5.23, `brain:3993.HK` → 18.94; `brain:1024.HK` shows 45.52 from its 2026-08-05 re-open, after
  the first generation closed). All initial lots share one `opened_at`:
  **2026-06-22T16:02:17.968634Z** — a backfill/open sweep, downstream of the account, not the
  origin.
- Precision fingerprint: the strikes are clean 2-dp decimals with **no float32 artifacts**, while
  every later ledger price carries yfinance's float32 trace (e.g. 84.80000305175781,
  428.79998779296875, 45.52000045776367). The strikes therefore came from a decimal-precision
  source (direct JSON / hand-entered snapshot), not the yfinance float32 quote path that priced
  everything from 06-24 onward. The fill-side initial prices (440.20 / 76.50 / 47.24 / 12.39 /
  5.27 / 18.87) are equally clean and self-consistent.
- The pattern is **not HK-specific**: the US book's 2026-06-22 backup
  (`portfolio/_backup_pre_nvda_avgo_exit_20260622-150122/account.json`) shows the same
  fractional-shares × clean-2dp-avg_cost seeding, with avg_costs (170.11, 166.36, 844.95, 528.93,
  670.345, 1077.0) that differ from its fill prices (169.67, 163.96, 836.59, 523.69, 659.88,
  1076.81). The US/CN books reconcile fills↔account **today** (zero per-symbol diffs), so their
  seeding-time divergence was later repaired away; the HK book is the only one still carrying it.
- Ledger direction differs by book: the US ledger opened 2026-06-21T14:26:56Z with the **fill**
  prices (entry 169.67 = fills), the HK ledger with the **account** strikes (439.0 = account) —
  the two books' ledgers were opened from different artifacts, so the ledger cannot arbitrate.

Not found (searched, absent):
- No commit in 2026-06-19..06-26 contains the strike prices, the notionals, or the seeded share
  counts (`git log --all -S` for `439.0`, `140000`, `318.037256`, `296.12756264`: no hits;
  `git log --all` window reviewed commit-by-commit).
- `bot/hk.py` first appears in `2b04b5e7` (2026-06-23 01:32 -0700 = 08:32 UTC) — **after** the
  2026-06-22T16:02Z ledger open and the 06-21/22 fills. The HK book was seeded by VPS code that
  was never committed in this form, so the exact strike-source code path is not recoverable from
  this repo's history.
- No seed table / config with HK strikes exists in the tree (`git grep` for seed/inaugural
  machinery shows only the generic target paths; current `portfolio/paper_account.py` `rebalance()`
  and `fill_pending()` are single-price single-transaction writers — account and fills cannot
  diverge through the current code, confirming the divergence predates it).

**Which side was the true market price is undecidable from this capture.** The capture holds no
independent HK quote for 06-19..06-22: `marks/` starts 2026-07-03 and contains no .HK tickers at
all; `nav_history.jsonl` has no per-symbol prices; the two candidate price sets disagree by
−0.27%..+3.00% with mixed signs (not an FX or fee factor). Saying more requires an external
06-19/06-22 HK close series, which is outside this lane's inputs.

## 6. Economic bound (per the commission formula)

Bound = quantity-diff shares monetized at the **actual later sell prices** (cash received for
shares the fills log never bought, if the fill-side price is right); for the still-open 0700.HK,
diff × `current_price` (393.8, 2026-10-21, `paper_account_mark`):

| symbol | bound components | bound (HKD) |
|---|---|---|
| 0700.HK | +0.807253 sh × 393.80 (still open; NAV overstatement) | **317.90** |
| 0981.HK | 49.600212 sh residual × 89.40 (last sell, 07-01) | **4,434.26** |
| 1024.HK | 12.276828 sh phantom × 41.00 (06-29) + 12.276828 sh × 44.24 (08-07) | **1,046.48** |
| 1929.HK | 43.202567 sh phantom × 10.90 (07-01) | **470.91** |
| 3988.HK | 72.563412 sh phantom × 5.51 (08-03) | **399.82** |
| 3993.HK | 23.503222 sh residual × 15.18 (06-30) | **356.78** |
| **Total** | | **7,026.14** = **0.6993%** of NAV 1,004,800.23 (2026-10-21) |

Reading of the bound:
- This is an **upper-bound magnitude on the misstatement, not a cash loss**. Because every leg
  used the same notional on both ledgers, **net realized cash is identical** under either truth;
  what differs is the share count (and hence recorded avg_cost, per-symbol PnL, and NAV while
  positions were open).
- Direction: 0700.HK (+317.90) overstates today's NAV if the fill side is right; 0981/3993
  understate (residual shares that fills say were still held were never sold); 1024's phantom was
  monetized twice (once per position generation). For the four closed names the distortion
  existed while each position was open and vanished at the close-out.
- Largest single term (0981.HK 4,434.26) prices the residual at the symbol's own last actual sell
  price (89.40, 07-01); it was never sold, so this term is a monetization assumption, not an
  observed cash flow.

## 7. What evidence would decide the remaining question

1. An independent HK close series for 0700/0981/1024/1929/3988/3993 covering 2026-06-19 and
   2026-06-22 (yfinance/Stooq/exchange) — decides whether 439.0/78.8/46.9/12.33/5.23/18.94 or
   440.2/76.5/47.24/12.39/5.27/18.87 matches a real close, and on which date.
2. The VPS-era seeding code that ran 2026-06-21/22 (pre-dating commit `2b04b5e7`) — would name the
   strike source (decision-time snapshot vs fill-time quote) and show which artifact was
   authoritative.
3. `decisions.jsonl` / `_pending_decision.json` from 06-21/06-22 for the HK book (not in the
   capture; the earliest captured decision artifacts are the 07-30 incident backup) — the
   Brain's submission prices would identify the decision-side snapshot.
4. Any pre-06-24 `fills.jsonl` backup (the capture's HK backups preserve account/nav only).

## 8. Files

- `HK_BRIDGE.md` — this report.
- `hk_bridge.csv` — one row per symbol:
  `symbol,account_qty,replay_qty,diff,first_seen,account_strike,fill_price,notional,h1_reproduces,bound_hkd,status,evidence`
- `tools/hk_bridge.py` — stdlib-only generator; run:
  `python3 tools/hk_bridge.py ~/lanes/tmp/pbr-econ-le1/live-data --out hk_bridge.csv --verbose`
- `hk_bridge_external_quotes.csv` — ECON (§10): which session open/close each price set equals.
- `tools/hk_external_quotes.py` — stdlib-only, offline generator for that table.
- `HK_EXTERNAL_QUOTES_MANIFEST.json` — source URL and sha256 of the eight saved public quote files
  (the files stay under `/Volumes/Mastermind/evidence/pbr/`, not committed).

## 9. Reproduction commands

```
python3 /tmp/verify_manifest.py            # 180/180 sha256 MATCH vs MANIFEST.json
python3 research/commission_pbr_fable_masterplan/2026-10-22/lanes/ECON/tools/hk_bridge.py \
        ~/lanes/tmp/pbr-econ-le1/live-data --out hk_bridge.csv --verbose
git log --since=2026-06-19 --until=2026-06-26 --format='%h %ci %s'
git log --all -S'439.0' -- bot/ portfolio/ scripts/        # no hits
git log --all -S'318.037256'                                # no hits
git show 2b04b5e7 --stat                                    # bot/hk.py created 2026-06-23
```

## 10. ECON adjudication — external quotes resolve the price question (pbr-econ, 2026-10-22)

§5 and §7 left one question open: which of the two price sets was a real market price, and on
which date. ECON answered it with an independent public daily series.

**Evidence.** Yahoo Finance chart API, daily bars for all eight seeded symbols, 2026-06-15 to
2026-06-27. The fetch was read-only, used no credentials, and was saved outside git at
`/Volumes/Mastermind/evidence/pbr/econ-hk-external-quotes-20261022T082655Z/`. Each file's sha256
is in `HK_EXTERNAL_QUOTES_MANIFEST.json`. `tools/hk_external_quotes.py` (stdlib, offline) derives
`hk_bridge_external_quotes.csv` from those files:

| symbol | account strike | fills.jsonl price | close 06-18 | open 06-22 | close 06-22 | strike equals | fill price equals | resolution |
|---|---|---|---|---|---|---|---|---|
| 0700.HK | 439.00 | 440.20 | 440.200 | 439.000 | 433.000 | 06-22 open | 06-18 close | EXPLAINED |
| 0981.HK | 78.80 | 76.50 | 76.500 | 78.800 | 78.900 | 06-22 open | 06-18 close | EXPLAINED |
| 1024.HK | 46.90 | 47.24 | 47.240 | 46.900 | 45.520 | 06-22 open | 06-18 close | EXPLAINED |
| 1929.HK | 12.33 | 12.39 | 12.390 | 12.330 | 12.220 | 06-22 open | 06-18 close | EXPLAINED |
| 3988.HK | 5.23 | 5.27 | 5.270 | 5.230 | 5.270 | 06-22 open | 06-18 close | EXPLAINED |
| 3993.HK | 18.94 | 18.87 | 18.870 | 18.940 | 19.400 | 06-22 open | 06-18 close | EXPLAINED |
| 1398.HK | 6.85 | 6.85 | 6.850 | 6.850 | 6.880 | both | both | CONTROL (zero diff) |
| 2628.HK | 28.02 | 28.02 | 28.020 | 28.020 | 30.260 | both | both | CONTROL (zero diff) |

The series has no 2026-06-19 bar (an HK market holiday). 2026-06-20 and 06-21 are a weekend.
2026-06-18 was therefore the last close before the first legs, which `fills.jsonl` dates
2026-06-21, a Sunday.

**Why this is discriminating.**
- The mechanism predicts a zero diff exactly where the 06-18 close equals the 06-22 open, and a
  non-zero diff everywhere else.
- Both controls (1398, 2628) are the only two symbols where those two prices coincide. The six
  diff-bearing symbols are the six where they differ.
- All 16 two-decimal price matches hold to the cent: 8 strikes against the 06-22 open, and
  8 fill prices against the 06-18 close.
- A scan of every open, high, low and close in the nine sessions (06-15 to 06-26) finds one
  session field common to all eight symbols on each side: the 06-22 open for the strikes, and
  the 06-18 close for the fill prices.
  - No strike equals any 06-18 price, except on the two controls.
  - The fill prices hit other fields only sporadically: 0981 (06-17 high, 06-23 low) and 3988
    (06-22 and 06-24 closes). No other session field fits all eight.

**Mechanism, now complete.**
- The HK book's opening decision was taken over the 06-19 holiday and the weekend.
- `fills.jsonl` recorded the decision-time quote, which was the stale 2026-06-18 close. It then
  derived `shares = notional / that quote`.
- The account struck each leg at the **2026-06-22 HK open**, which is the first executable price
  after the decision, as `shares = notional / open`.
- That matches the book's settlement doctrine: "queue on close, settle at the open". The doctrine
  is the `bot/settle.py` module docstring, first committed in `2b04b5e7` on 2026-06-23, the same
  commit that introduced `bot/hk.py`. The seeding code that ran on 06-21/22 was never committed
  (§5).
- So the account applied the settlement rule correctly. The fills log stamped the leg with the
  decision quote instead of the settlement price.

**Verdicts. These three are kept separate.**
- *Operational correctness.* The HK **account** is correct. Its quantities, cash and avg_cost
  follow from the 06-22 open strikes and every later fill (§4, H2 confirmed). The **fills log is
  wrong** for the 15 initial legs, rows 1–15: their `price` is the 06-18 close and their
  `shares` is notional divided by that price.
  - The four "oversells" (§3) are artifacts of the fills log. In account terms the shares existed
    and were sold.
  - The 0981 and 3993 "residuals" are also fills-log artifacts. Those shares were never held.
- *Economic qualification.* The account NAV is not misstated by this mechanism, and the cash
  ledger is identical under both readings (§2). The 7,026.14 HKD in §6 is therefore the **size of
  the audit-trail error** in the fills log, not a NAV or cash misstatement. The cash residual of
  +5,170.71 HKD is the documented cash-yield accrual (§4).
- *Investment value.* No claim.

**Proposed W1 ruling, for the seat's acceptance row.**
1. **Close the bridge.** Make no account change, no repair trade, no balancing fill and no seed
   rewrite. `fills.jsonl` stays append-only and unedited. This bridge table, together with
   `hk_bridge_external_quotes.csv`, is the durable annotation of rows 1–15.
2. **Prospective HK opening checkpoint (MASTERPLAN §11.3).** Record the HK book's qualified
   opening state as the 2026-06-24 backup account, which is equivalent to the live account
   replayed to that date.

   | Component | Status | Basis |
   |---|---|---|
   | Strikes | CORROBORATED | Exact match to an external open, from one source |
   | Quantities | CORROBORATED | Strikes and notional (H1), plus fills replay from 06-24 (H2) |
   | Cash | CORROBORATED | Same notional on both ledgers; residual equals the accrual |
   | Settlement timing (06-22 open) | ASSUMED | Doctrine, not a committed seeding code path |

3. **Prospective check (W3).** Confirm that the current fill writer stamps the *settlement* price
   (the open used by `settle_open`), not the decision quote. Through the current code, account and
   fills cannot diverge (§5), but the fill row's price field should be checked against the
   settlement receipt.

**Caveats.**
- *Single external source.* Yahoo is one public vendor and no second source was obtained. A
  second series (exchange or Stooq) would raise this from "corroborated by one source" to
  "independently corroborated".
- *Seeding code not in git.* The VPS-era seeding code is still not recoverable from git (§5), so
  the settlement timing is inferred from the price match and the contemporaneous doctrine, not read
  from the code that ran.
- *US book.* It carried the same seeding pattern (§5) and reconciles today. Whether its later
  repair moved the account to the decision quotes or the fills to the settlement prices is
  **not examined here**. It is listed as a W3 census item.

**Reproduce:**
```
python3 -I research/commission_pbr_fable_masterplan/2026-10-22/lanes/ECON/tools/hk_external_quotes.py \
        /Volumes/Mastermind/evidence/pbr/econ-hk-external-quotes-20261022T082655Z \
        --out hk_bridge_external_quotes.csv
shasum -a 256 /Volumes/Mastermind/evidence/pbr/econ-hk-external-quotes-20261022T082655Z/*.HK.json
```

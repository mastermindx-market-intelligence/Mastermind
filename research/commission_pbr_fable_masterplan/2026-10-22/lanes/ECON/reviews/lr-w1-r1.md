# Review record — lr-w1-r1 (PRs #1705 cash bridge, #1712 HK bridge)

Lane: pool `ubuntu1`, model glm-5.3, class review C2_COMPLEX_BOUNDED, run-id `pbr-econ-lr-w1-r1`, 2026-10-22T08:58Z–09:19Z, rc=0.
Reviewed heads: #1705 8af2db50; #1712 0b037b71.
Verdicts: PASS #1705 (2 MINOR). PASS #1712 (no findings).

ECON disposition: the parent recounted both #1705 MINORs from the CSVs. Sweep-before-fills (prev base) fill-days: US 0 / CN 8 / HK 11. Fills-before-sweep (prev+fills): US 26 / CN 22 / HK 18. HK k=1 YIELD rows: 81. Fixed in 297a391d; wording only, so no re-review.

---

All checks are complete. The `-S` negatives confirm §5's claim (no commit contains the strikes/notionals/share counts). Here is the full review report.

---

# Independent review — packet pbr-econ LR-W1 (PRs #1705, #1712)

All numbers below were re-derived with my own code in `~/lanes/tmp/pbr-econ-lr-w1/scratch/` (never trusting the tools under review). The capture is intact: **all 412 files on disk sha256-match MANIFEST.json (0 mismatches, 0 unlisted)**, which covers every file either tool reads and every backup either md cites; the 6 `fingerprint_checks` book hashes also match (the 2 legacy-store MISMATCH entries are the manifest's own recorded cross-check, not defects).

## PR #1705 — cash bridge

**What reproduced exactly (independent recomputation):**
- **Reproduction:** `cash_bridge.py` output **identical** to all three committed CSVs (`cmp` clean).
- **Independent totals:** US +9,214.51 / CN +5,782.62 / HK +5,240.56; opening 1,000,000 each; net fills −306,529.32 / −616,463.68 / −629,677.87; ending cash 702,685.19 / 389,318.94 / 375,562.69 — cash identity closes to the cent in all three books; Σ CSV `non_trade` equals the residual per book.
- **Sweep model at origin/master:** `round(cash*(1+rate/252),2)` (`_TRADING_DAYS=252`), default 0.04 via `CASH_YIELD_ANNUAL`, once-per-date guard (`cash_yield_through==asof`), `cash<=0` skip, pending-receipt skip, called in `daily_mark` behind a trading-date gate and book lock; `git log -S accrue_cash_yield` names exactly one commit, `2b04b5e7` (2026-06-23 01:32:16 −0700).
- **Spot-checks:** all 12 chosen rows (≥2 YIELD/book, HK YIELD_MULTI, both CN REPAIR, US ROUNDING, CN Sunday-with-fills) recompute exactly from raw files; `expected_yield` matches the formula.
- **CN repair decomposition:** the two removed sells are in the scrub backup (688411.SS 19.826594@286.98 = 5,689.84; 688585.SS 51.207122@162.59 = 8,325.77; both 2026-06-22; absent from current fills); chain 445,173.768 −14,015.61 = 431,158.16 → +68.44 → 431,226.60 (backup 06-23 row, deleted from current) → +68.45 → 431,295.05 (backup 06-24 row/account, `cash_yield_through` 06-24) → +242,746.04 (four 06-24 fills) → 674,041.09 (current row); −14,015.61+68.44+68.45 = −13,878.72 exact.
- **Deleted/rewritten rows:** CN/HK 06-23 rows exist only in the fx-repair backup (values exactly as cited); 06-24 invested rewrites (559,941.84→317,195.81 CN; 759,446.23→685,565.02 HK) with cash = backup + that day's fills; 07-30 incident backups' cash byte-equal to current rows (CN 428,151.94; HK 333,220.14); US 06-21 rewrite 260,000.00→480,000.00 with NVDA (522.094 sh)/AVGO (267.412 sh) lots and fills removed.
- **Behaviour:** every weekend row shows zero non-trade (US 06-28/07-12/07-19; CN 06-28/07-05/07-12 — the CN Sundays *with fills* +48,200.80/−91,722.53/−39,935.17 still zero sweep; HK 06-28/07-05/07-12); no NAV rows on 07-27/28 in any book; cash never negative anywhere; CN Golden-Week 10-01…10-07 rows zero.
- **No plug bucket:** `classify` assigns REPAIR only inside explicitly cited windows and only when no sweep candidate matches; the fallback is UNEXPLAINED (count: **0 rows in all three CSVs**). Tool is stdlib-only, opens no network, writes only `--outdir` (verified). No authority breach — repairs are described as historical artifacts; nothing recommends reset/seed rewrite/balancing fill/repair trade.

**Findings:**

1. **[MINOR]** `CASH_BRIDGE.md` §"Sweep behavior findings" inverts the two base labels: it claims "on 26 US / 22 CN / 18 HK fill-days the sweep ran BEFORE the day's fills (base = previous row's cash)". Independent count over same-day-fill YIELD rows by evidence base: **prev-base (sweep-before-fills) = US 0, CN 8, HK 11; prev+fills (fills-before-sweep) = US 26, CN 22, HK 18** — the quoted 26/22/18 are exactly the *prev+fills* counts (for US the inversion is complete: zero prev-base fill-days). E.g. US 06-24: non_trade +67.27 = round((449,672.18−25,896.34)×(1+0.04/252),2)−423,775.84 (prev+fills); the prev-base candidate +71.37 misses by 4.10 ≫ tolerance. The counts themselves reproduce; no amount, class, k-value or total is affected, and the committed CSV evidence column is correct — but the sentence should be fixed before merge.
2. **[MINOR]** "Accrual-day totals: … HK 83 (82 single-day rows + one k=2 row…)": the HK CSV has **81** k=1 rows (81+2=83 ✓ headline correct); "82" contradicts both the CSV and the md's own total (82+2=84). CN "77 visible + 2 hidden = 79" and US 84 are correct.

## PR #1712 — HK quantity bridge

**What reproduced exactly:**
- **Integrity:** capture 412/412 (above); the 8 quote files' sha256 **and** byte sizes match `HK_EXTERNAL_QUOTES_MANIFEST.json` exactly (committed manifest byte-identical to the lane copy; PR head = `0b037b7`).
- **Reproduction:** both tools' outputs **identical** to the committed CSVs. The BOUNDED-vs-EXPLAINED supersession is unambiguous: §1's top banner ("ECON adjudication (§10) supersedes the per-symbol BOUNDED status below… All six symbols are EXPLAINED") plus §10 and the external-quotes CSV agree.
- **H1:** all eight implied strikes (net initial notional / 06-24 backup shares) land on exact 2-dp prices (439.00/78.80/46.90/12.33/5.23/18.94/6.85/28.02), share residuals ≤3.4e-9, six diffs +0.807254/−49.600212/+12.276828/+43.202567/+72.563412/−23.503222 (controls 0).
- **External match (decisive, my own parser):** gmtoffset 28800/Asia-Hong_Kong; **06-22 open = strike for all 8** (max dev 3.1e-6); **06-18 close = fill price for all 8**; **no 06-19 bar** (nor 06-20/21); exhaustive (date × open/high/low/close) scan of 06-15..06-26: **(06-22, open) is the only field common to all 8 strikes and (06-18, close) the only one common to all 8 fill prices**; sporadic extras exactly as §10 lists (0981: 06-17 high, 06-23 low; 3988: 06-22/06-24 closes); controls exactly {1398, 2628} = the symbols where close 06-18 = open 06-22.
- **Oversell trace:** exactly rows 26/32/63/78 below −1e-4 with deficits −12.276828/−43.202567/−72.563412/−12.276828 (inventory-before values match §3's table); row-82 9988.HK is −0.000001 dust.
- **H2:** backup→final positions ≤3.5e-7; backup→07-30-incident positions ≤7.2e-7; cash residuals **exactly +5,170.71 and +1,493.89**; per-date sweep replay (`round(cash*(1+0.04/252),2)`) lands within 1–2 cents (float rounding across ~81 applications), and the residual interlocks with #1705 to the cent: 5,240.56 − 69.85 (sweeps embedded in the 06-24 backup) = 5,170.71. 0700 avg_cost triplet (448.3610594/448.3610632/448.3610620) verified.
- **Bound:** every §6 term and total **7,026.14** (unrounded 7,026.143408) reproduce; 0.6993% of NAV 1,004,800.23 = the 2026-10-21 HK nav row.
- **Doctrine:** `2b04b5e72:bot/settle.py` opens with "queue on close, settle at the open" and the `execute_or_queue`/`settle_open` discipline; `git log --diff-filter=A -- bot/hk.py bot/settle.py` names only `2b04b5e` (2026-06-23). §5's `git log -S` negatives (439.0 / 140000 / 318.037256 / 296.12756264) return no hits, and the ledger `entry_price` values (439.0, 78.8, 12.33, 5.23, 18.94, 6.85, 28.02; 1024.HK 45.52 from its 08-05 re-open) and shared `opened_at` 2026-06-22T16:02:17Z verify; US/CN reconcile today (CN zero diffs; US only a 1e-6 APH share at 6dp recording precision).
- **Verdict discipline & authority:** the three verdicts are kept separate; "Settlement timing (06-22 open) | ASSUMED"; the single-source caveat is present; "Investment value. No claim."; §10's ruling explicitly makes **no account change, no repair trade, no balancing fill, no seed rewrite, fills.jsonl append-only and unedited** — no BLOCKER text anywhere. Tools are stdlib-only, `hk_external_quotes.py` has no network path, each writes only `--out`; committed files carry derived values only. Both review records carry `VERDICT:` lines and name their lane (pool `ubuntu1`, glm-5.3, run-ids `pbr-econ-lr-a02-r1`/`pbr-econ-lr-docs-r2`).

**Findings: none.**

---

```
RETURN pbr-econ-lr-w1
PR #1705 findings:
1. [MINOR] CASH_BRIDGE.md inverts the base-ordering labels: claims 26 US / 22 CN / 18 HK fill-days had "sweep BEFORE fills (base = previous row's cash)"; independent count of same-day-fill YIELD rows: prev-base = US 0 / CN 8 / HK 11, prev+fills = US 26 / CN 22 / HK 18 — the quoted numbers are the prev+fills counts (evidence: counting script over cash_bridge_*.csv evidence strings; US 2026-06-24 non_trade +67.27 matches round((449672.18-25896.34)*(1+0.04/252),2)-423775.84, prev-base candidate +71.37 misses by 4.10). Counts reproduce; no numeric consequence; fix the sentence.
2. [MINOR] "HK 83 (82 single-day rows + one k=2 row)" — CSV has 81 k=1 rows (81+2=83 headline correct; "82" contradicts CSV and own total). Evidence: grep -c ',1,YIELD,' cash_bridge_hk.csv = 81; my class counts YIELD n=81, YIELD_MULTI n=1.
VERDICT: PASS #1705 — residuals, totals, sweep model, repairs, deletions and behaviour claims all reproduce exactly; two wording-level miscounts only.
PR #1712 findings: none
VERDICT: PASS #1712 — H1 (exact 2-dp strikes, resid ≤3.4e-9), decisive external-quote match (06-22 open / 06-18 close unique common fields, controls exact), oversell trace, H2 (+5,170.71/+1,493.89 exact), bound 7,026.14 = 0.6993% of NAV 1,004,800.23, doctrine and discipline all reproduce; no authority breach.
independent_totals: US +9,214.51 USD (cash 702,685.19 − 1,000,000 − net fills −306,529.32); CN +5,782.62 CNY (389,318.94, net fills −616,463.68); HK +5,240.56 HKD (375,562.69, net fills −629,677.87); Σ CSV non_trade equals residual in each book
commands_run: git diff --name-status origin/master...{pbr/econ-cash-bridge,pbr/econ-hk-bridge}; git show <ref>:<ECON files> (extract to scratch); python3 -I cash_bridge.py <live-data> --outdir scratch/out1705 + cmp ×3 (identical); python3 -I verify_manifest.py (412/412 sha MATCH, 0 mismatch/unlisted); python3 -I indep_totals.py; git show origin/master:portfolio/paper_account.py (accrue_cash_yield/_cash_yield_rate/_TRADING_DAYS) + app/scheduler.py caller; git log -S accrue_cash_yield (→ 2b04b5e only); python3 -I spotcheck1705.py (12 rows + weekend/07-27-28/negative-cash); python3 -I (same-day-fill base count per book); cat/parse of _backup_scrub_tiny_trims_*, _backup_fx_repair_20260624-173547 (CN+HK), _incident_backup_* (CN+HK), _backup_remove_nvda_avgo_*; python3 -I pr1712/tools/hk_bridge.py --out + cmp (identical); python3 -I pr1712/tools/hk_external_quotes.py <hk-quotes> --out + cmp (identical); sha256sum hk-quotes/*.json vs HK_EXTERNAL_QUOTES_MANIFEST.json (8/8 sha+bytes); python3 -I indep1712.py (H1/oversell/H2/H2-B/sweep-replay/bound); python3 -I indep_quotes.py (own JSON parse, HK-date conversion, exhaustive 06-15..06-26 field scan, controls); git show 2b04b5e72:bot/settle.py | head -60; git log --diff-filter=A -- bot/hk.py bot/settle.py; git log --all -S{439.0,140000,318.037256,296.12756264} (no hits); python3 -I final_checks.py (US nvda/avgo backup, US pre-exit avg_costs, US/CN zero-diff); grep VERDICT reviews/lr-a02-r1.md reviews/lr-docs-r2.md
not_verified: (a) the census lanes' own capture copies (~/lanes/tmp/pbr-econ-le2, -le1) are not on this host — their "180/180" restatements and CASH_BRIDGE.md's "other 232 benchmark entries not part of the local capture" could not be checked against those copies (in this LR-W1 copy all 412 manifest files are present and match; lr-docs-r2 corroborates "412 captured files"; immaterial to every number reviewed); (b) live-service env CASH_YIELD_ANNUAL not captured — 4%/252 assumed and empirically self-verifying (every accrual row fits within 0.02/day); (c) the Yahoo series' authenticity as market truth beyond the sha-pinned files (single vendor, no second source — caveat carried in the PR itself); (d) 07-27/07-28 outage root cause (outside the capture; the behavioral absence is verified); (e) §5's git-window review was spot-verified (-S searches + first-add commits), not a commit-by-commit re-read of 2026-06-19..06-26.
```

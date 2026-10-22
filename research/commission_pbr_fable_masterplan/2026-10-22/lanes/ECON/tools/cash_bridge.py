#!/usr/bin/env python3
"""Dated non-trade cash residual decomposition for the three paper books.

Reproduces cash_bridge_{us,cn,hk}.csv from a read-only capture of the live data
directory (the copy under ~/lanes/tmp/pbr-econ-le2/live-data/). Stdlib only; no
network, no repo imports, reads only.

For consecutive nav_history rows t-1 -> t:

    non_trade_t = cash_t - cash_{t-1} - net_fill_cash(dates in (t-1, t])

where net_fill_cash(d) = sum(sell value) - sum(buy value) from fills.jsonl.
The first row uses starting_nav as its base (minus fills dated on/before it);
the tail uses account.json cash (minus fills dated after the last row).

Non-trade deltas are classified:
  ROUNDING  |x| < 0.05 (incl. exact zero)
  YIELD     matches one cash sweep: round(cash_base * (1 + 0.04/252), 2)
  YIELD_MULTI  matches k >= 2 compounded sweep days (rounding applied per day)
  REPAIR    date falls in a known repair/migration window (evidence cited);
            the best yield candidate is still reported inside the evidence
  UNEXPLAINED  nothing above matched

The sweep model comes from portfolio/paper_account.accrue_cash_yield() as of
commit 2b04b5e72 (2026-06-23): once per (book, calendar date), before mark(),
rate = CASH_YIELD_ANNUAL (default 0.04) / 252, compounded onto cents, skipped
when cash <= 0 / already accrued through asof / settlement receipts pending.
Accruals cannot predate 2026-06-23 (the introducing commit). Two bases are
tried per row: the previous row's cash, and previous cash + that day's fills
(a build can execute fills before the day's accrual+mark).

Usage: cash_bridge.py <live-data-dir> [--outdir DIR]
"""
from __future__ import annotations

import argparse
import csv
import json
import os
from datetime import date, timedelta

RATE = 0.04 / 252.0
ACCRUAL_START = date(2026, 6, 23)   # commit 2b04b5e72 2026-06-23: sweep introduced
ROUNDING_EPS = 0.05
YIELD_TOL_PER_ACCRUAL = 0.02

BOOKS = [
    ("us", "US", "portfolios/autonomous", "USD"),
    ("cn", "CN", "portfolios/china", "CNY"),
    ("hk", "HK", "portfolios/hk", "HKD"),
]

# Known out-of-band (non-fill, non-sweep) cash events, from the repo scripts and
# the backup directories shipped inside the capture. Windows are inclusive.
REPAIRS = {
    "US": [
        ("2026-06-22", "2026-06-22", "nvda_avgo_removal",
         "_backup_remove_nvda_avgo_20260622-221155/autonomous: 06-21 nav row rewritten "
         "cash 260000.00->480000.00 (+220000.00), NVDA/AVGO lots+fills removed from "
         "account.json/fills.jsonl; visible ledger is self-consistent afterwards"),
        ("2026-08-11", "2026-08-12", "legacy_etf_migration",
         "legacy_etf_migration.jsonl: USMV/XLP/XLV sells of 2026-08-12 recorded as "
         "normal fills (no out-of-band cash)"),
        ("2026-08-11", "2026-08-11", "pending_target_quarantine",
         "pending_target_quarantine.jsonl: pending target quarantined (no cash effect "
         "expected)"),
    ],
    "CN": [
        ("2026-06-22", "2026-06-22", "scrub_cn_tiny_trims",
         "scripts/scrub_cn_tiny_trims.py + _backup_scrub_tiny_trims_20260623-052644: two "
         "06-22 sell fills (688411.SS 5689.84 + 688585.SS 8325.77 = 14015.61) were credited "
         "into cash BEFORE the 06-22 nav row was written, then REMOVED from fills.jsonl and "
         "debited from cash after it; the 06-22 row still embeds the proceeds "
         "(1000000 - 568841.84 + 14015.61 = 445173.77 exact)"),
        ("2026-06-24", "2026-06-24", "fx_repair",
         "_backup_fx_repair_20260624-173547: 06-23 nav row DELETED (cash 431226.60, "
         "invested 82996.93 - USD-marked CNY positions); 06-24 row invested rewritten "
         "559941.84->317195.81, row later replaced by post-fill mark (cash unchanged by "
         "the repair itself). Verified decomposition of this row's delta: "
         "-14015.61 scrub debit (fills removed from ledger) + 68.44 (06-23 sweep) + "
         "68.45 (06-24 sweep) = -13878.72; backup chain 431158.16 (post-scrub account) "
         "-> 431226.60 (deleted 06-23 row) -> 431295.05 (backup 06-24 row/account, "
         "yield_through 06-24) -> +242746.04 06-24 fills = 674041.09 exact"),
        ("2026-07-30", "2026-07-30", "ashare_quote_route_incident",
         "_incident_backup_ashare_quote_route_20260730T231834Z: 07-30 row rewritten "
         "(invested/spy_nav); cash identical 428151.94 in backup and current row"),
    ],
    "HK": [
        ("2026-06-23", "2026-06-24", "fx_repair",
         "_backup_fx_repair_20260624-173547: 06-23 nav row DELETED (cash 220034.92); "
         "06-24 row invested rewritten 759446.23->685565.02, row later replaced by "
         "post-fill mark (cash unchanged by the repair itself)"),
        ("2026-07-30", "2026-07-30", "missing_yfinance_incident",
         "_incident_backup_20260730_missing_yfinance: 07-30 row rewritten "
         "(invested/spy_nav); cash identical 333220.14 in backup and current row"),
    ],
}


def _read_jsonl(path):
    rows = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _compound(base, k):
    """k sweep days, rounding to cents after each, exactly like accrue_cash_yield."""
    cash = round(float(base), 2)
    for _ in range(k):
        cash = round(cash * (1.0 + RATE), 2)
    return cash


def _weekdays_between(prev_date, asof):
    """Mon-Fri days in (prev_date, asof] — an upper bound on sweep days for the gap
    (weekend/holiday accruals are not expected; +2 slack is added by callers)."""
    d, n = prev_date + timedelta(days=1), 0
    while d <= asof:
        if d.weekday() < 5:
            n += 1
        d += timedelta(days=1)
    return n


def _yield_candidates(cash_prev, fill_same_day, asof):
    """(k, base_kind, expected_non_trade) candidates for one row gap."""
    out = []
    d = date.fromisoformat(asof)
    if d >= ACCRUAL_START:
        # bound: no book goes >10 weekday sessions between NAV rows; +3 slack for
        # weekend/holiday accruals on rows that do exist.
        k_max = min(10, _weekdays_between(d - timedelta(days=45), d) + 3)
        for base_kind, base in (("prev", round(float(cash_prev), 2)),
                                ("prev+fills", round(float(cash_prev) + float(fill_same_day), 2))):
            if base <= 0:
                continue
            for k in range(1, k_max + 1):
                grown = _compound(base, k)
                if base_kind == "prev":
                    expected = grown - round(float(cash_prev), 2)
                else:
                    expected = grown - (round(float(cash_prev), 2) + round(float(fill_same_day), 2))
                out.append((k, base_kind, round(expected, 2)))
    return out


def classify(book, d_iso, cash_prev, cash, fill_gap, fill_same_day):
    """Return (class, expected_yield, k_accruals, evidence)."""
    non_trade = round(cash - cash_prev - fill_gap, 2)
    if abs(non_trade) < 0.005:
        return "ROUNDING", 0.0, 0, "exact zero non-trade delta"
    if abs(non_trade) < ROUNDING_EPS:
        return "ROUNDING", 0.0, 0, f"|{non_trade:.2f}| < 0.05 sub-cent fill/sweep rounding"

    best = None
    for k, base_kind, expected in _yield_candidates(cash_prev, fill_same_day, d_iso):
        tol = YIELD_TOL_PER_ACCRUAL * max(k, 1) + 0.005
        if abs(non_trade - expected) <= tol:
            best = (k, base_kind, expected)
            break

    repair = [r for r in REPAIRS[book] if r[0] <= d_iso <= r[1]]
    if best is not None:
        # a sweep fully explains the delta even inside a repair window: the repair
        # itself left cash unchanged (verified against the backup), so it stays YIELD
        # and the window is only recorded as context.
        k, base_kind, expected = best
        cls = "YIELD" if k == 1 else "YIELD_MULTI"
        ev = f"sweep {k}d on {base_kind} base"
        if repair:
            ev += f"; inside repair window '{repair[0][2]}' (backup shows cash unchanged by it)"
        return cls, expected, k, ev
    if repair:
        _, _, label, evidence = repair[0]
        return "REPAIR", 0.0, 0, evidence + "; no sweep candidate matches the delta"
    return "UNEXPLAINED", 0.0, 0, "no sweep/repair candidate matches"


def bridge_book(root, key, book, subpath, ccy):
    book_dir = os.path.join(root, subpath)
    account = json.load(open(os.path.join(book_dir, "account.json"), encoding="utf-8"))
    fills = _read_jsonl(os.path.join(book_dir, "fills.jsonl"))
    nav = _read_jsonl(os.path.join(book_dir, "nav_history.jsonl"))
    nav.sort(key=lambda r: r["date"])

    net_fill = {}
    for f in fills:
        signed = float(f["value"]) if f["side"] == "sell" else -float(f["value"])
        net_fill[f["date"]] = round(net_fill.get(f["date"], 0.0) + signed, 2)

    rows_out = []
    totals = {"YIELD": 0.0, "YIELD_MULTI": 0.0, "REPAIR": 0.0, "ROUNDING": 0.0, "UNEXPLAINED": 0.0}
    unexplained_dates = []
    negative_cash = []

    def emit(d_iso, cash_prev, cash, fill_gap, fill_same_day):
        non_trade = round(cash - cash_prev - fill_gap, 2)
        cls, expected, k, evidence = classify(book, d_iso, cash_prev, cash, fill_gap, fill_same_day)
        totals[cls] = round(totals[cls] + non_trade, 2)
        if cls == "UNEXPLAINED":
            unexplained_dates.append(f"{d_iso}:{non_trade:+.2f}")
        if cash < 0:
            negative_cash.append(f"{d_iso}:{cash:.2f}")
        rows_out.append({
            "date": d_iso, "cash_prev": f"{cash_prev:.2f}", "cash": f"{cash:.2f}",
            "net_fill_cash": f"{fill_gap:.2f}", "non_trade": f"{non_trade:.2f}",
            "expected_yield": f"{expected:.2f}", "k_accruals": k,
            "class": cls, "evidence": evidence,
        })

    # first row: base = starting_nav, fills on/before the first date
    first = nav[0]
    fill_le_first = round(sum(v for d, v in net_fill.items() if d <= first["date"]), 2)
    emit(first["date"], round(float(account["starting_nav"]), 2), round(float(first["cash"]), 2),
         fill_le_first, fill_le_first)

    for prev, row in zip(nav, nav[1:]):
        gap = round(sum(v for d, v in net_fill.items() if prev["date"] < d <= row["date"]), 2)
        same = round(net_fill.get(row["date"], 0.0), 2)
        emit(row["date"], round(float(prev["cash"]), 2), round(float(row["cash"]), 2), gap, same)

    # tail: account.cash vs last row, fills after the last nav date
    last = nav[-1]
    tail_fills = round(sum(v for d, v in net_fill.items() if d > last["date"]), 2)
    tail = round(float(account["cash"]) - float(last["cash"]) - tail_fills, 2)
    tail_fills_only = tail  # tail row shows residual after removing post-ledger fills
    rows_out.append({
        "date": f"{last['date']}+tail", "cash_prev": f"{float(last['cash']):.2f}",
        "cash": f"{float(account['cash']):.2f}", "net_fill_cash": f"{tail_fills:.2f}",
        "non_trade": f"{tail:.2f}", "expected_yield": "0.00", "k_accruals": 0,
        "class": "ROUNDING" if abs(tail) < 0.005 else ("UNEXPLAINED" if abs(tail) >= 0.05 else "ROUNDING"),
        "evidence": "account.cash vs last nav row" + (f" minus {tail_fills:.2f} post-ledger fills" if tail_fills else ""),
    })
    totals["ROUNDING" if abs(tail) < 0.05 else "UNEXPLAINED"] = round(
        totals["ROUNDING" if abs(tail) < 0.05 else "UNEXPLAINED"] + tail, 2)

    residual = round(float(account["cash"]) - float(account["starting_nav"])
                     - sum(float(f["value"]) for f in fills if f["side"] == "sell")
                     + sum(float(f["value"]) for f in fills if f["side"] == "buy"), 2)
    bridged = round(sum(float(r["non_trade"]) for r in rows_out), 2)

    return {
        "key": key, "book": book, "ccy": ccy,
        "rows": rows_out, "totals": totals,
        "residual": residual, "bridged": bridged,
        "unexplained": unexplained_dates, "negative_cash": negative_cash,
        "cash_end": float(account["cash"]), "starting_nav": float(account["starting_nav"]),
        "net_fills_total": round(sum(v for v in net_fill.values()), 2),
        "cash_yield_through": account.get("cash_yield_through"),
        "first_row": {"date": first["date"], "cash": float(first["cash"])},
        "last_row": {"date": last["date"], "cash": float(last["cash"])},
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root", help="live-data capture dir (contains portfolios/)")
    ap.add_argument("--outdir", default=".", help="where the CSVs are written")
    args = ap.parse_args()

    summaries = []
    for key, book, subpath, ccy in BOOKS:
        res = bridge_book(args.root, key, book, subpath, ccy)
        out_csv = os.path.join(args.outdir, f"cash_bridge_{key}.csv")
        with open(out_csv, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=["date", "cash_prev", "cash", "net_fill_cash",
                                               "non_trade", "expected_yield", "k_accruals",
                                               "class", "evidence"])
            w.writeheader()
            w.writerows(res["rows"])
        summaries.append(res)
        print(f"[{book}] residual {res['residual']:+.2f} {res['ccy']} | bridged "
              f"{res['bridged']:+.2f} | yield {res['totals']['YIELD'] + res['totals']['YIELD_MULTI']:+.2f} "
              f"repair {res['totals']['REPAIR']:+.2f} rounding {res['totals']['ROUNDING']:+.2f} "
              f"unexplained {res['totals']['UNEXPLAINED']:+.2f}")
        if res["unexplained"]:
            print(f"  UNEXPLAINED: {', '.join(res['unexplained'])}")
        if res["negative_cash"]:
            print(f"  NEGATIVE CASH: {', '.join(res['negative_cash'])}")

    ok = all(abs(r["residual"] - r["bridged"]) < 0.005 for r in summaries)
    print(f"bridge-vs-residual identity: {'OK' if ok else 'MISMATCH'}")


if __name__ == "__main__":
    main()

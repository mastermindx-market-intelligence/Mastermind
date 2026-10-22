#!/usr/bin/env python3
"""HK six-symbol quantity bridge — census tool (pbr-econ L-E1).

Replays the HK book's fills.jsonl from an empty account and against the
2026-06-24 fx-repair backup account, explains the per-symbol
(account_qty - replay_qty) diffs, tests H1 (the 2026-06-21/22 initial legs
were struck at a different account-side price on the same notional) and
H2 (no later quantity event outside fills), and emits hk_bridge.csv.

Stdlib only. Read-only: takes one input-dir argument (the captured
live-data dir containing `portfolios/hk/`), plus optional --out for the CSV
path (default: stdout). No network, no repo imports, never writes into the
input dir.

Usage:
    python3 hk_bridge.py /path/to/live-data [--out hk_bridge.csv] [--verbose]
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys

SIX = ["0700.HK", "0981.HK", "1024.HK", "1929.HK", "3988.HK", "3993.HK"]

# 1-indexed fills row numbers (as cited in the commission packet) of the four
# oversells: a sell larger than replayed inventory.
CITED_OVERSELL_ROWS = [26, 32, 63, 78]


# --------------------------------------------------------------------------- io
def _read_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _read_jsonl(path: str) -> list[dict]:
    rows = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


# --------------------------------------------------------------------- replay
def replay(fills: list[dict], dates="all", strike: dict[str, float] | None = None,
           use_recorded_shares=True, start_qty: dict[str, float] | None = None,
           start_cash: float = 0.0):
    """Replay fills. Share counting: recorded `shares` when allowed; a leg is
    counted at `strike[ticker]` (value/strike) when a strike override is given
    for that ticker (H1: the account struck the initial legs at its own price).
    Cash moves the recorded notional `value` (buys subtract, sells add)."""
    qty = dict(start_qty or {})
    cash = start_cash
    for rowno, r in enumerate(fills, start=1):
        if dates != "all" and not (dates[0] <= r["date"] <= dates[1]):
            continue
        tk = r["ticker"]
        sign = 1.0 if r["side"] == "buy" else -1.0
        if strike and tk in strike:
            shares = round(r["value"] / strike[tk], 8)
        elif use_recorded_shares:
            shares = float(r["shares"])
        else:
            shares = round(r["value"] / r["price"], 8)
        qty[tk] = qty.get(tk, 0.0) + sign * shares
        cash -= sign * r["value"]
    return qty, cash


def avg_cost_path(base_shares: float, base_avg: float, rows: list[dict],
                  value_based: bool = False) -> tuple[float, float]:
    """paper_account convention: a buy re-averages cost across the added
    shares; a sell leaves avg_cost unchanged. value_based=True re-averages on
    the recorded notional instead of shares*price."""
    shares, avg = base_shares, base_avg
    for r in rows:
        sign = 1.0 if r["side"] == "buy" else -1.0
        added = float(r["shares"])
        new_shares = shares + sign * added
        if sign > 0 and new_shares > 0:
            cost = r["value"] if value_based else added * r["price"]
            avg = (shares * avg + cost) / new_shares
        shares = new_shares
    return shares, avg


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("indir", help="captured live-data dir (contains portfolios/hk/)")
    ap.add_argument("--out", default=None, help="CSV output path (default stdout)")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    hk = os.path.join(args.indir, "portfolios", "hk")
    fills = _read_jsonl(os.path.join(hk, "fills.jsonl"))
    account = _read_json(os.path.join(hk, "account.json"))
    backup = _read_json(os.path.join(hk, "_backup_fx_repair_20260624-173547", "account.json"))
    incident = _read_json(os.path.join(hk, "_incident_backup_20260730_missing_yfinance", "account.json"))
    nav = _read_jsonl(os.path.join(hk, "nav_history.jsonl"))
    ledger = _read_json(os.path.join(hk, "positions_ledger.json"))
    nav_last = nav[-1]

    initial = [r for i, r in enumerate(fills, start=1) if r["date"] <= "2026-06-23"]

    # ---- H1: implied account strike per symbol from the 06-24 backup --------
    # strike = net initial notional / backup shares; test the clean 2-dp price.
    net_notional: dict[str, float] = {}
    for r in initial:
        sign = 1.0 if r["side"] == "buy" else -1.0
        net_notional[r["ticker"]] = net_notional.get(r["ticker"], 0.0) + sign * r["value"]
    h1 = {}
    strikes = {}
    for tk, pos in sorted(backup["positions"].items()):
        want = float(pos["shares"])
        implied = net_notional[tk] / want
        clean = round(implied, 2)
        qty_clean, _ = replay(initial, strike={tk: clean})
        resid = want - qty_clean[tk]
        strikes[tk] = clean
        h1[tk] = {"backup_shares": want, "implied_strike": implied, "clean_strike": clean,
                  "resid_at_clean": resid, "ok": abs(resid) < 1e-6,
                  "fill_qty": replay(initial)[0].get(tk, 0.0)}

    # ---- final diff (account vs fill-side replay), per symbol ---------------
    replay_final, replay_cash_final = replay(fills)
    acct_final = {tk: float(p["shares"]) for tk, p in account["positions"].items()}

    # ---- H2-A: backup + fills after 06-23 vs final account ------------------
    h2_qty, h2_cash = replay(fills, dates=("2026-06-24", "9999-12-31"),
                             start_qty={tk: float(p["shares"]) for tk, p in backup["positions"].items()},
                             start_cash=float(backup["cash"]))
    h2_final = {tk: acct_final.get(tk, 0.0) - h2_qty.get(tk, 0.0) for tk in sorted(acct_final)}
    # avg_cost reproduction for the surviving six-symbol name
    b0700 = backup["positions"]["0700.HK"]
    rows0700 = [r for r in fills if r["ticker"] == "0700.HK" and r["date"] > "2026-06-23"]
    s_pp, a_pp = avg_cost_path(float(b0700["shares"]), float(b0700["avg_cost"]), rows0700, value_based=False)
    s_vb, a_vb = avg_cost_path(float(b0700["shares"]), float(b0700["avg_cost"]), rows0700, value_based=True)
    acct_avg0700 = float(account["positions"]["0700.HK"]["avg_cost"])

    # ---- H2-B: backup + fills 06-24..07-29 vs 07-30 incident backup ---------
    inc_qty, inc_cash = replay(fills, dates=("2026-06-24", "2026-07-29"),
                               start_qty={tk: float(p["shares"]) for tk, p in backup["positions"].items()},
                               start_cash=float(backup["cash"]))
    h2_inc = {tk: float(p["shares"]) - inc_qty.get(tk, 0.0)
              for tk, p in sorted(incident["positions"].items())}

    # ---- per-symbol bound + status for the six ------------------------------
    rows_out = []
    bound_total = 0.0
    for tk in SIX:
        acct_qty = acct_final.get(tk, 0.0)
        rep_qty = replay_final.get(tk, 0.0)
        diff = acct_qty - rep_qty
        h = h1.get(tk, {})
        # Walk both ledgers side by side to find where the diff was monetized.
        # Account leg: initial (<= 2026-06-23) legs struck at the account price,
        # later legs at the recorded fill shares (H2: fills-only afterwards).
        acct_q = rep_q = 0.0
        bound = 0.0
        kinds = []
        for rowno, r in enumerate(fills, start=1):
            if r["ticker"] != tk:
                continue
            sign = 1.0 if r["side"] == "buy" else -1.0
            if r["date"] <= "2026-06-23":
                acct_q += sign * round(r["value"] / strikes[tk], 8)
            else:
                acct_q += sign * float(r["shares"])
            rep_q += sign * float(r["shares"])
            if r["side"] == "sell" and acct_q <= 1e-6 and rep_q < -1e-6:
                # account closed flat; fill-side went negative -> phantom
                # shares (never recorded as bought) were sold for cash
                bound += (-rep_q) * r["price"]
                kinds.append(f"phantom_sold row{rowno} {r['date']} @{r['price']:.2f}")
            elif r["side"] == "sell" and acct_q <= 1e-6 and rep_q > 1e-6:
                # account closed flat; fill-side still holds a residual that
                # the over-struck account never owned -> un-monetized residual
                bound += rep_q * r["price"]
                kinds.append(f"residual_unsold row{rowno} {r['date']} @{r['price']:.2f}")
        if abs(diff) < 1e-9:
            bound, bound_kind = 0.0, "n/a"
        elif acct_qty > 1e-9:  # still open: mark-to-market the diff
            px = float(account["positions"][tk]["current_price"])
            bound = abs(diff) * px
            bound_kind = f"open_diff_x_current({px:g})"
            kinds.append(bound_kind)
        else:
            bound_kind = "; ".join(kinds)
        bound_total += bound
        rows_out.append({
            "symbol": tk,
            "account_qty": f"{acct_qty:.6f}",
            "replay_qty": f"{rep_qty:.6f}",
            "diff": f"{diff:+.6f}",
            "first_seen": "2026-06-24_backup (created on 2026-06-21/22 initial legs)",
            "account_strike": f"{h['clean_strike']:.2f}" if h else "",
            "fill_price": "; ".join(f"{r['price']:.2f}" for r in initial if r["ticker"] == tk),
            "notional": f"{net_notional.get(tk, 0.0):.2f}",
            "h1_reproduces": "YES" if h.get("ok") else "NO",
            "bound_hkd": f"{bound:.2f}",
            "status": "BOUNDED" if h.get("ok") else "UNEXPLAINED",
            "evidence": bound_kind,
        })

    # ---- oversell trace (fill-side inventory goes negative) -----------------
    oversells = []
    q: dict[str, float] = {}
    for rowno, r in enumerate(fills, start=1):
        tk = r["ticker"]
        sign = 1.0 if r["side"] == "buy" else -1.0
        before = q.get(tk, 0.0)
        q[tk] = before + sign * float(r["shares"])
        if r["side"] == "sell" and q[tk] < -1e-4 and before >= -1e-9:
            oversells.append((rowno, r, q[tk]))  # >1e-4 shares deficit = real, not 6dp dust
    cited_ok = all(any(o[0] == n for o in oversells) for n in CITED_OVERSELL_ROWS)

    # ---- report --------------------------------------------------------------
    fh = sys.stdout if not args.out else open(args.out, "w", newline="", encoding="utf-8")
    w = csv.DictWriter(fh, fieldnames=list(rows_out[0].keys()))
    w.writeheader()
    for row in rows_out:
        w.writerow(row)
    if args.out:
        fh.close()

    verbose = args.verbose or not args.out
    if verbose:
        P = print
        P(f"fills rows={len(fills)}  initial(<=2026-06-23) rows={len(initial)}")
        P("== H1: implied account strike (net initial notional / 06-24-backup shares)")
        for tk, h in h1.items():
            P(f"  {tk}: implied={h['implied_strike']:.8f} clean={h['clean_strike']:.2f} "
              f"resid_at_clean={h['resid_at_clean']:+.3e} ok={h['ok']} "
              f"fill_side_qty={h['fill_qty']:.6f} backup_shares={h['backup_shares']:.8f} "
              f"diff_at_backup={h['backup_shares']-h['fill_qty']:+.6f}")
        P("== final per-symbol diff (account - fill-side replay)")
        for r in rows_out:
            P(f"  {r['symbol']}: account={r['account_qty']} replay={r['replay_qty']} diff={r['diff']}")
        P("== H2-A backup(06-24) + fills>06-23 -> final account")
        for tk in sorted(h2_final):
            P(f"  {tk}: resid={h2_final[tk]:+.3e}")
        P(f"  cash: account={account['cash']:.2f} replay={h2_cash:.2f} resid={account['cash']-h2_cash:+.2f}")
        P(f"  0700.HK avg_cost replayed: shares*price={a_pp:.13f} value-based={a_vb:.13f} "
          f"account={acct_avg0700!r}")
        P("== H2-B backup + fills 06-24..07-29 -> incident backup(07-30)")
        for tk, v in h2_inc.items():
            P(f"  {tk}: resid={v:+.3e}")
        P(f"  cash: incident={incident['cash']:.2f} replay={inc_cash:.2f} resid={incident['cash']-inc_cash:+.2f}")
        P("== oversells (first sell taking fill-side inventory negative)")
        for rowno, r, after in oversells:
            P(f"  row {rowno}: {r['date']} {r['ticker']} sell {float(r['shares']):.6f} @{r['price']:.2f} -> {after:+.6f}")
        P(f"  cited oversell rows {CITED_OVERSELL_ROWS} all reproduce: {cited_ok}")
        P(f"== ledger entry_price (downstream record): "
          f"{', '.join(tk + '=' + str(ledger.get('brain:' + tk, {}).get('entry_price')) for tk in SIX)}")
        P(f"== NAV last row: {nav_last['date']} nav={nav_last['nav']} cash={nav_last['cash']}")
        P(f"== bound total HKD: {bound_total:.2f} "
          f"({bound_total/float(nav_last['nav'])*100:.4f}% of NAV {nav_last['date']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

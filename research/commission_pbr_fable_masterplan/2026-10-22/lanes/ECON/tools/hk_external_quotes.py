#!/usr/bin/env python3
"""Match the HK bridge's two price sets to an independent daily open/close series.

Reads the saved Yahoo chart responses (one ``<SYMBOL>.json`` per symbol, captured read-only
under ``/Volumes/Mastermind/evidence/pbr/econ-hk-external-quotes-*/``) and writes one row per
symbol: which session open/close each price set equals. Stdlib only, no network, read-only.

    python3 hk_external_quotes.py <quotes_dir> [--out hk_bridge_external_quotes.csv]
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import sys

# account strike (06-24 backup implied) and fills.jsonl price for the initial 06-21/22 legs
STRIKE = {"0700.HK": 439.00, "0981.HK": 78.80, "1024.HK": 46.90, "1929.HK": 12.33,
          "3988.HK": 5.23, "3993.HK": 18.94, "1398.HK": 6.85, "2628.HK": 28.02}
FILL = {"0700.HK": 440.20, "0981.HK": 76.50, "1024.HK": 47.24, "1929.HK": 12.39,
        "3988.HK": 5.27, "3993.HK": 18.87, "1398.HK": 6.85, "2628.HK": 28.02}
HKT = dt.timezone(dt.timedelta(hours=8))


def _bars(path):
    res = json.load(open(path, encoding="utf-8"))["chart"]["result"][0]
    q = res["indicators"]["quote"][0]
    out = {}
    for i, t in enumerate(res.get("timestamp") or []):
        day = dt.datetime.fromtimestamp(t, HKT).date().isoformat()
        out[day] = (q["open"][i], q["close"][i])
    return out


def _eq(x, v):
    return x is not None and abs(round(float(x), 2) - v) < 0.005


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("quotes_dir")
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    rows = []
    for sym in sorted(STRIKE):
        bars = _bars(os.path.join(a.quotes_dir, f"{sym}.json"))
        o22, c22 = bars.get("2026-06-22", (None, None))
        o18, c18 = bars.get("2026-06-18", (None, None))
        strike_is = "2026-06-22_open" if _eq(o22, STRIKE[sym]) else "no_match"
        fill_is = "2026-06-18_close" if _eq(c18, FILL[sym]) else "no_match"
        control = STRIKE[sym] == FILL[sym]
        resolution = ("CONTROL_ZERO_DIFF" if control else
                      "EXPLAINED" if strike_is != "no_match" and fill_is != "no_match" else
                      "BOUNDED")
        rows.append({"symbol": sym, "account_strike": f"{STRIKE[sym]:.2f}",
                     "fill_price": f"{FILL[sym]:.2f}",
                     "close_2026_06_18": f"{c18:.3f}", "open_2026_06_22": f"{o22:.3f}",
                     "close_2026_06_22": f"{c22:.3f}", "account_strike_equals": strike_is,
                     "fill_price_equals": fill_is, "resolution": resolution})
    fh = open(a.out, "w", newline="", encoding="utf-8") if a.out else sys.stdout
    w = csv.DictWriter(fh, fieldnames=list(rows[0]))
    w.writeheader()
    w.writerows(rows)
    if a.out:
        fh.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

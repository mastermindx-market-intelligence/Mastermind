#!/usr/bin/env python3
"""pbr-econ W3 — economic-truth census over the 2026-10-22 capture copy.

Read-only. Inputs: the verified capture copy (`--capture`, sha256-checked against
`--manifest`), the offline Yahoo close reference (`--ref`), and this worktree's
`portfolio.paper_account.valuation` (the ONLY bot entry point used; always called
with an explicit pure `state=` dict).

Outputs (into `--out`):
  w3_t1_a02_incidence.csv   per-book A02 valuation() incidence on historical NAV rows
  w3_t2_afterhours.csv      one row per polygon-eod entry compared to the reference
  w3_t3_missing_bars.csv    one row per dated marks file
  w3_t4_fill_stamps.csv     one row per live fill
  w3_t5_us_repairs.csv      one row per repair event
  summary printed to stdout (the md is authored from it)

stdlib + the single allowed valuation import; no network; reads only.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[6]))  # this worktree root

from portfolio import paper_account  # noqa: E402  (valuation only; pure when state= given)

BOOKS = [
    ("US", "portfolio"),
    ("autonomous", "portfolios/autonomous"),
    ("hk", "portfolios/hk"),
    ("china", "portfolios/china"),
]
US_BOOKS = {"US", "autonomous"}
FLAT = 1e-6


class Used:
    """Registry of capture files this census actually read."""

    def __init__(self) -> None:
        self.paths: set[str] = set()

    def add(self, *paths: Path) -> None:
        for p in paths:
            self.paths.add(str(p))


USED = Used()


def read_json(path: Path):
    USED.add(path)
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict]:
    USED.add(path)
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


# ---------------------------------------------------------------------------
# manifest verification
# ---------------------------------------------------------------------------

def verify_capture(capture: Path, manifest_path: Path) -> tuple[int, int, list[str]]:
    """Return (n_verified, n_listed, mismatch descriptions); also n_used via USED."""
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    listed = manifest["files"]
    assert listed and all(e["path"].startswith("opt/mastermind-live-data/") for e in listed)
    verified, mismatches, missing = 0, [], []
    for entry in listed:
        rel = entry["path"][len("opt/mastermind-live-data/"):]
        local = capture / rel
        if not local.exists():
            missing.append(rel)
            mismatches.append(f"MISSING {rel}")
            continue
        h = hashlib.sha256(local.read_bytes()).hexdigest()
        if h == entry["sha256"]:
            verified += 1
        else:
            mismatches.append(f"SHA_MISMATCH {rel} manifest={entry['sha256']} local={h}")
    return verified, len(listed), mismatches


# ---------------------------------------------------------------------------
# reference closes
# ---------------------------------------------------------------------------

def load_ref(ref_csv: Path) -> dict[str, dict[str, float]]:
    USED.add(ref_csv)
    out: dict[str, dict[str, float]] = defaultdict(dict)
    with ref_csv.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            out[row["symbol"]][row["date"]] = float(row["close"])
    return out


def ref_prev(symbol: str, d: str, ref: dict[str, dict[str, float]]):
    """(prev_date, prev_close) strictly before d, or (None, None)."""
    days = sorted(ref.get(symbol, {}))
    prev = [x for x in days if x < d]
    if not prev:
        return None, None
    p = prev[-1]
    return p, ref[symbol][p]


# ---------------------------------------------------------------------------
# reverse replay from a final account
# ---------------------------------------------------------------------------

def replay_shares(final_positions: dict, fills: list[dict], d: str) -> dict[str, float]:
    """shares_d[s] = final - buys(dated > d) + sells(dated > d); fills dated d are applied on d.

    ``final_positions`` maps symbol -> shares float or {"shares": float} (either shape)."""
    out = {}
    for s, p in (final_positions or {}).items():
        out[s] = float(p.get("shares") or 0.0) if isinstance(p, dict) else float(p or 0.0)
    for f in fills:
        fd = str(f.get("date") or "")[:10]
        if fd <= d:
            continue
        sh = float(f.get("shares") or 0.0)
        t = str(f.get("ticker") or "").upper()
        if str(f.get("side") or "").lower() == "sell":
            out[t] = out.get(t, 0.0) + sh
        else:
            out[t] = out.get(t, 0.0) - sh
    return {s: x for s, x in out.items() if abs(x) >= FLAT}


def replay_cash(final_cash: float, fills: list[dict], d: str):
    """cash_d = final - buy values(after d) + sell values(after d)."""
    cash = float(final_cash or 0.0)
    for f in fills:
        fd = str(f.get("date") or "")[:10]
        if fd <= d:
            continue
        v = float(f.get("value") or 0.0)
        if str(f.get("side") or "").lower() == "sell":
            cash -= v
        else:
            cash += v
    return cash


# ---------------------------------------------------------------------------
# T1 — A02 incidence on historical NAV rows
# ---------------------------------------------------------------------------

def t1(capture: Path, ref: dict) -> tuple[list[dict], list[str]]:
    rows_out: list[dict] = []
    notes: list[str] = []
    nonfresh_detail: list[str] = []
    absent_syms: set[str] = set()
    for label, reldir in BOOKS:
        base = capture / reldir
        account = read_json(base / "account.json")
        fills = read_jsonl(base / "fills.jsonl")
        nav_rows = read_jsonl(base / "nav_history.jsonl")
        final_shares = {s: float(p.get("shares") or 0.0) for s, p in (account.get("positions") or {}).items()}

        n_class = n_noev = 0
        lines = Counter()
        rows_status = Counter()
        detail_rows = []

        if label in US_BOOKS:
            for row in nav_rows:
                d = str(row.get("date") or "")[:10]
                shares_d = replay_shares(final_shares, fills, d)
                held = {s: x for s, x in shares_d.items() if abs(x) >= FLAT}
                mpath = capture / "marks" / f"{d}.json"
                if not mpath.exists():
                    n_noev += 1
                    continue
                m = read_json(mpath)
                ev = m.get("sources") or {}
                prices = {}
                for s in held:
                    e = ev.get(s)
                    if isinstance(e, dict) and e.get("price") is not None:
                        prices[s] = e["price"]
                    else:
                        absent_syms.add(f"{d}:{s}")
                state_d = {"cash": row.get("cash"),
                           "positions": {s: {"shares": x, "avg_cost": 0.0} for s, x in held.items()}}
                v = paper_account.valuation(prices, d, price_evidence=ev, state=state_d)
                n_class += 1
                for t, ln in v["lines"].items():
                    lines[ln["class"]] += 1
                    if ln["class"] != "FRESH":
                        detail_rows.append((d, t, ln["class"], ln.get("source"), ln.get("age_days")))
                rows_status[v["nav_status"]] += 1
                if v["nav_status"] != "QUALIFIED":
                    nf = sorted({r[1] for r in detail_rows if r[0] == d})
                    nonfresh_detail.append(
                        f"{label} {d} {v['nav_status']}: non-FRESH {' '.join(nf)}")
        else:
            # HK / China: no per-date evidence in the capture; classify only the final state.
            n_noev = len(nav_rows)
            last_d = str(nav_rows[-1].get("date") or "")[:10]
            v = paper_account.valuation({}, last_d, state=account)
            n_class = 1
            for t, ln in v["lines"].items():
                lines[ln["class"]] += 1
            rows_status[v["nav_status"]] += 1
            nf = sorted({t for t, ln in v["lines"].items() if ln["class"] != "FRESH"})
            notes.append(f"{label}: final-state valuation at {last_d} -> {v['nav_status']}; "
                         f"lines: {dict(lines)}; nav={v['nav']} (persisted-carry path, "
                         f"current_price_asof per position); {len(nav_rows) - 1} historical rows UNDETERMINABLE")
            if v["nav_status"] != "QUALIFIED":
                nonfresh_detail.append(f"{label} {last_d} {v['nav_status']}: non-FRESH {' '.join(nf)}")

        rows_out.append({
            "book": label,
            "rows": len(nav_rows),
            "rows_classified": n_class,
            "rows_no_evidence_or_undeterminable": n_noev,
            "lines_FRESH": lines["FRESH"],
            "lines_CARRIED": lines["CARRIED"],
            "lines_UNATTESTED": lines["UNATTESTED"],
            "lines_UNPRICED": lines["UNPRICED"],
            "rows_QUALIFIED": rows_status["QUALIFIED"],
            "rows_PROVISIONAL": rows_status["PROVISIONAL"],
            "rows_WITHHELD": rows_status["WITHHELD"],
        })

    notes.append("WITHHELD/PROVISIONAL rows and non-FRESH symbols:")
    notes.extend("  " + s for s in nonfresh_detail)
    notes.append("held symbol absent from that day's union-mark file (or null price): "
                 + ("; ".join(sorted(absent_syms)) if absent_syms else "none"))
    return rows_out, notes


# ---------------------------------------------------------------------------
# T2 — after-hours effect vs the reference
# ---------------------------------------------------------------------------

def t2(capture: Path, ref: dict) -> tuple[list[dict], dict]:
    files = sorted((capture / "marks").glob("20*.json"))
    per_row: list[dict] = []
    ts_hours = Counter()
    sym_ratios: dict[str, list[float]] = defaultdict(list)
    all_entries = 0

    for fp in files:
        m = read_json(fp)
        d = str(m.get("as_of") or fp.stem)[:10]
        ts = str(m.get("ts") or "")
        hour = ts[11:13] if len(ts) >= 13 else ""
        if hour:
            ts_hours[hour] += 1
        for sym, e in sorted((m.get("sources") or {}).items()):
            all_entries += 1
            if not isinstance(e, dict) or e.get("source") != "polygon-eod":
                continue
            px = e.get("price")
            if px is None:
                continue
            px = float(px)
            rc = ref.get(sym, {}).get(d)
            rec = {
                "date": d, "symbol": sym, "mark": px, "ref": rc,
                "ref_prev_date": None, "ref_prev": None,
                "dev_bp": None, "dev_prev_bp": None,
                "equal_prev_close": None,
                "gt2dp": int(abs(px * 100 - round(px * 100)) > 1e-6),
                "ts_hour": hour,
                "adjusted": 0, "compared": 0,
            }
            if rc:
                rec["compared"] = 1
                dev = (px / rc - 1.0) * 1e4
                rec["dev_bp"] = dev
                sym_ratios[sym].append(px / rc)
            pd_, pc = ref_prev(sym, d, ref)
            if pd_:
                rec["ref_prev_date"], rec["ref_prev"] = pd_, pc
                rec["dev_prev_bp"] = (px / pc - 1.0) * 1e4
                rec["equal_prev_close"] = int(px == pc or abs(px - pc) <= 0.005)
            per_row.append(rec)

    # adjustment detector: a symbol whose mark/reference ratio sits at a persistent
    # offset k≠1 (corporate-action adjustment scale) with negligible dispersion is
    # REFERENCE_ADJUSTED — a scaled series, not day-level after-hours drift. Yahoo's
    # adjusted closes make k drift slightly with each distribution, so tolerance is
    # a coefficient of variation < 1%, not an exact constant.
    adjusted_syms, near_adj_syms, adjusted_k = set(), set(), {}
    for sym, ratios in sym_ratios.items():
        if len(ratios) < 5:
            continue
        mean = sum(ratios) / len(ratios)
        var = sum((r - mean) ** 2 for r in ratios) / len(ratios)
        cv = (var ** 0.5) / mean
        if abs(mean - 1.0) > 5e-3 and cv < 0.01:
            adjusted_syms.add(sym)
            adjusted_k[sym] = mean
        elif abs(mean - 1.0) <= 5e-3 and cv < 0.0005:
            near_adj_syms.add(sym)  # ratio pinned at k≈1: marks == reference closes
    for rec in per_row:
        if rec["symbol"] in adjusted_syms:
            rec["adjusted"] = 1

    hh = [r for r in per_row if r["compared"] and not r["adjusted"]]
    devs = sorted(abs(r["dev_bp"]) for r in hh)
    def pct(p):
        return devs[min(len(devs) - 1, int(round(p / 100 * len(devs) - 0.5)))] if devs else None
    all_c = [r for r in per_row if r["compared"]]
    all_devs = sorted(abs(r["dev_bp"]) for r in all_c)
    def pct_all(p):
        return all_devs[min(len(all_devs) - 1, int(round(p / 100 * len(all_devs) - 0.5)))] if all_devs else None
    summary = {
        "n_files": len(files),
        "n_entries": all_entries,
        "n_polygon_priced": len(per_row),
        "n_compared_excl_adjusted": len(hh),
        "n_compared_incl_adjusted": len(all_c),
        "n_no_reference": sum(1 for r in per_row if not r["compared"]),
        "n_excluded_reference_adjusted": sum(1 for r in per_row if r["adjusted"]),
        "exact": sum(1 for r in hh if abs(r["dev_bp"]) < 0.5),
        "median_bp": pct(50),
        "p95_bp": pct(95),
        "max_bp": max((r["dev_bp"] for r in hh), key=abs, default=None),
        "gt10bp": sum(1 for r in hh if abs(r["dev_bp"]) > 10),
        "gt50bp": sum(1 for r in hh if abs(r["dev_bp"]) > 50),
        "incl_adjusted_median_bp": pct_all(50),
        "incl_adjusted_p95_bp": pct_all(95),
        "incl_adjusted_max_bp": max((r["dev_bp"] for r in all_c), key=abs, default=None),
        "equal_prev_close_half_cent": sum(1 for r in per_row if r["equal_prev_close"]),
        "equal_prev_close_exact": sum(1 for r in per_row
                                      if r["equal_prev_close"] and r["ref_prev"] is not None
                                      and r["mark"] == r["ref_prev"]),
        "gt2dp": sum(1 for r in per_row if r["gt2dp"]),
        "adjusted_syms": {s: round(k, 8) for s, k in sorted(adjusted_k.items())},
        "constant_k1_syms": sorted(near_adj_syms),
        "ts_hours": dict(sorted(ts_hours.items())),
    }
    return per_row, summary


# ---------------------------------------------------------------------------
# T3 — missing-bar rate
# ---------------------------------------------------------------------------

def t3(capture: Path, ref: dict) -> tuple[list[dict], dict, list[str]]:
    files = sorted((capture / "marks").glob("20*.json"))
    have = {fp.stem for fp in files}
    rows: list[dict] = []
    sym_missing = defaultdict(set)
    for fp in files:
        m = read_json(fp)
        src = Counter()
        stale_not_null = stale_gt0 = null_price = 0
        total = 0
        for sym, e in sorted((m.get("sources") or {}).items()):
            total += 1
            e = e if isinstance(e, dict) else {}
            s = e.get("source")
            src[s if s else "null"] += 1
            sd = e.get("stale_days")
            if sd is not None:
                stale_not_null += 1
                try:
                    if float(sd) > 0:
                        stale_gt0 += 1
                except (TypeError, ValueError):
                    pass
            if e.get("price") is None:
                null_price += 1
                sym_missing[fp.stem].add(sym)
            if s != "polygon-eod" or e.get("price") is None:
                sym_missing[fp.stem].add(sym)
        poly = src.get("polygon-eod", 0)
        rows.append({
            "date": fp.stem, "total": total,
            "n_polygon_eod": poly, "n_yahoo_parquet": src.get("yahoo-parquet", 0),
            "n_last_good_carry": src.get("last-good-carry", 0), "n_null_source": src.get("null", 0),
            "n_stale_not_null": stale_not_null, "n_stale_gt0": stale_gt0,
            "n_null_price": null_price,
            "missing_rate": (total - poly) / total if total else None,
        })

    # US weekdays in the window with no marks file
    gaps, gap_notes = [], []
    nav_auto = read_jsonl(capture / "portfolios/autonomous/nav_history.jsonl")
    nav_dates = {str(r.get("date"))[:10] for r in nav_auto}
    d0, d1 = date(2026, 7, 3), date(2026, 10, 21)
    d = d0
    while d <= d1:
        ds = d.isoformat()
        if d.weekday() < 5 and ds not in have:
            gaps.append(ds)
        d += timedelta(days=1)
    for g in gaps:
        note = ""
        if g in nav_dates:
            note = "autonomous traded/marked a NAV row this date but no marks file"
        gap_notes.append(f"{g}: {note or 'US weekday with no marks file; no autonomous NAV row either'}")
    gap_notes.append("note: 2026-09-07 (Labor Day, market closed) HAS a marks file whose 8 priced "
                     "entries are all source=polygon-eod with stale_days=null yet equal the "
                     "prior session's close exactly — see T2 equal_prev_close")

    total_entries = sum(r["total"] for r in rows)
    total_missing = sum((r["total"] - r["n_polygon_eod"]) for r in rows)
    summary = {
        "n_mark_files": len(rows),
        "overall_missing_rate": (total_missing / total_entries) if total_entries else None,
        "dates_rate_gt0": [(r["date"], round(r["missing_rate"], 4)) for r in rows if r["missing_rate"]],
        "gap_dates": gaps,
    }
    return rows, summary, gap_notes + [f"symbols involved on imperfect dates: " + "; ".join(
        f"{k}: {','.join(sorted(v))}" for k, v in sorted(sym_missing.items()) if v)]


# ---------------------------------------------------------------------------
# T4 — fill-writer stamp per fill
# ---------------------------------------------------------------------------

def writer_of(f: dict) -> str:
    if f.get("transaction_id") and f.get("fill_id"):
        return "SETTLE_IDS"
    if f.get("from_pending"):
        return "FROM_PENDING"
    return "LEGACY"


def match_category(book: str, f: dict, marks_by_date: dict[str, dict], mark_dates: list[str], ref: dict):
    """(category, matched_price, source_label, delta_bp, tier, devs, position).

    ``devs`` carries the bp deviation vs every available anchor (regardless of match);
    ``position`` locates the fill price between the prev-close and same-day-close
    anchors (open-session stamps typically sit BETWEEN the two EOD closes)."""
    d = str(f.get("date"))[:10]
    sym = str(f.get("ticker") or "").upper()
    px = float(f.get("price") or 0.0)

    def beats(a, b):
        rel = abs(a - b) / b if b else 9e9
        if rel <= 1e-6:
            return 2  # tier 1: relative 1e-6
        if rel <= 5e-5:
            return 1  # tier 2: 0.5 bp
        return 0

    devs: dict[str, float] = {}
    cands = []
    rc = ref.get(sym, {}).get(d)
    if rc is not None:
        devs["ref_d"] = (px / rc - 1.0) * 1e4
        cands.append(("REF_CLOSE_D", rc, "yahoo_close(fill_date)", beats(px, rc)))
    pd_, pc = ref_prev(sym, d, ref)
    if pc is not None:
        devs["ref_prev"] = (px / pc - 1.0) * 1e4
        cands.append(("REF_CLOSE_PREV", pc, f"yahoo_close({pd_})", beats(px, pc)))
    md = marks_by_date.get(d, {}).get("sources", {}).get(sym)
    if isinstance(md, dict) and md.get("price") is not None:
        devs["mark_d"] = (px / float(md["price"]) - 1.0) * 1e4
        cands.append(("MARK_D", float(md["price"]), f"marks/{d}({md.get('source')})", beats(px, float(md["price"]))))
    prev_md_date = max([x for x in mark_dates if x < d], default=None)
    if prev_md_date:
        mp = marks_by_date[prev_md_date]["sources"].get(sym)
        if isinstance(mp, dict) and mp.get("price") is not None:
            devs["mark_prev"] = (px / float(mp["price"]) - 1.0) * 1e4
            cands.append(("MARK_PREV", float(mp["price"]), f"marks/{prev_md_date}({mp.get('source')})",
                          beats(px, float(mp["price"]))))
    best = None
    for cat, price, label, score in cands:  # spec order = priority order
        if score:
            best = (cat, price, label, score)
            break
    # where does the stamp sit between the two session anchors?
    lo_anchor = pc if pc is not None else (float(mp["price"]) if prev_md_date and isinstance(
        marks_by_date.get(prev_md_date, {}).get("sources", {}).get(sym), dict)
        and marks_by_date[prev_md_date]["sources"][sym].get("price") is not None else None)
    hi_anchor = rc
    position = ""
    if lo_anchor and hi_anchor:
        lo_v, hi_v = sorted((lo_anchor, hi_anchor))
        tol = 5e-5
        if abs(px / rc - 1) <= tol:
            position = "EQUAL_D"
        elif abs(px / lo_anchor - 1) <= tol:
            position = "EQUAL_PREV"
        elif lo_v <= px <= hi_v:
            position = "BETWEEN(prev,d)" if lo_anchor == lo_v else "BETWEEN(d,prev)"
        elif px > hi_v:
            position = "ABOVE_BOTH"
        else:
            position = "BELOW_BOTH"
    if best:
        cat, price, label, score = best
        rel = (px / price - 1.0) * 1e4 if price else None
        return cat, price, label, rel, "1e-6" if score == 2 else "0.5bp", devs, position
    if rc is None and (not isinstance(md, dict) or md.get("price") is None):
        return "UNDETERMINABLE", None, None, None, None, devs, position
    return "NO_MATCH", None, None, None, None, devs, position


STAMP_OF = {
    "REF_CLOSE_D": "SETTLEMENT_PRICE(same-day EOD close)",
    "MARK_D": "SETTLEMENT_PRICE(same-day union-mark EOD)",
    "REF_CLOSE_PREV": "DECISION_QUOTE(prior-session close)",
    "MARK_PREV": "DECISION_QUOTE(prior-session union-mark)",
    "NO_MATCH": "ATTESTS_NEITHER",
    "UNDETERMINABLE": "NO_EVIDENCE",
}


def t4(capture: Path, ref: dict) -> tuple[list[dict], dict, list[str]]:
    mark_dates = sorted(fp.stem for fp in (capture / "marks").glob("20*.json"))
    marks_by_date = {d: read_json(capture / "marks" / f"{d}.json") for d in mark_dates}
    rows: list[dict] = []
    failures: list[str] = []
    grid = Counter()
    for label, reldir in BOOKS:
        fills = read_jsonl(capture / reldir / "fills.jsonl")
        for f in fills:
            w = writer_of(f)
            shares, price, value = float(f.get("shares") or 0), float(f.get("price") or 0), float(f.get("value") or 0)
            vok = abs(round(shares * price - value, 6)) <= 0.01
            cat, mprice, mlabel, dbp, tier, devs, position = match_category(
                label, f, marks_by_date, mark_dates, ref)
            grid[(label, w, cat)] += 1
            rows.append({
                "book": label, "date": f.get("date"), "ticker": f.get("ticker"),
                "side": f.get("side"), "shares": shares, "price": price, "value": value,
                "writer": w, "value_ok": int(vok),
                "match": cat, "stamp": STAMP_OF[cat], "matched_price": mprice,
                "match_source": mlabel, "delta_bp": (round(dbp, 3) if dbp is not None else None),
                "match_tier": tier, "position_vs_anchors": position,
                "dev_ref_d_bp": (round(devs["ref_d"], 2) if "ref_d" in devs else None),
                "dev_ref_prev_bp": (round(devs["ref_prev"], 2) if "ref_prev" in devs else None),
                "dev_mark_d_bp": (round(devs["mark_d"], 2) if "mark_d" in devs else None),
                "dev_mark_prev_bp": (round(devs["mark_prev"], 2) if "mark_prev" in devs else None),
            })
            if not vok:
                failures.append(f"{label} {f.get('date')} {f.get('ticker')} {f.get('side')}: "
                                f"shares*price={shares * price:.4f} vs value={value:.2f}")
    summary = {"grid": {"%s | %s | %s" % k: v for k, v in sorted(grid.items())},
               "positions": dict(sorted(Counter(
                   (r["book"], r["position_vs_anchors"] or "NO_ANCHORS")
                   for r in rows if r["writer"] != "LEGACY" or r["book"] == "US").items())),
               "value_failures": failures}
    notes = [f"{k}: {v}" for k, v in summary["grid"].items()]
    notes.append("position of the stamp between the two session closes (US + id-writers): "
                 + json.dumps({"%s|%s" % k: v for k, v in summary["positions"].items()},
                              default=str))
    return rows, summary, notes


# ---------------------------------------------------------------------------
# T5 — US book repair direction
# ---------------------------------------------------------------------------

EVENTS = [
    ("pre_nvda_avgo_exit", "US", "portfolio/_backup_pre_nvda_avgo_exit_20260622-150122"),
    ("remove_nvda_avgo_autonomous", "autonomous", "_backup_remove_nvda_avgo_20260622-221155/autonomous"),
    ("remove_nvda_avgo_heavyweight", "heavyweight", "_backup_remove_nvda_avgo_20260622-221155/heavyweight"),
    ("remove_nvda_avgo_self_directed", "self_directed", "_backup_remove_nvda_avgo_20260622-221155/self_directed"),
    ("test_contamination", "US", "portfolio/_backup_test_contamination_20260728"),
    ("peer_sentinel_liquidation", "US", "portfolio/_incident_backup_peer_sentinel_liquidation_20260730T231832Z"),
    ("heavyweight_clobber", "heavyweight", "portfolios/heavyweight/_backup_clobber_repair_20260727"),
]


def snapshot_date(snap_dir: Path, capture: Path) -> str | None:
    """Best-effort as-of date of a snapshot: max fills date, else latest.json date, else None."""
    f = snap_dir / "fills.jsonl"
    if f.exists():
        rows = read_jsonl(f)
        ds = [str(r.get("date"))[:10] for r in rows if r.get("date")]
        if ds:
            return max(ds)
    lj = snap_dir / "latest.json"
    if lj.exists():
        m = read_json(lj)
        for k in ("asof", "as_of", "date"):
            if m.get(k):
                return str(m[k])[:10]
    return None


def replay_diff(capture: Path, book_dir: str, target_date: str | None, snap: dict):
    """Max |share diff| and cash diff of a snapshot vs reverse replay from the final account."""
    base = capture / book_dir
    account = read_json(base / "account.json")
    fills = read_jsonl(base / "fills.jsonl")
    if target_date is None:
        return None, None, None
    rep = replay_shares(account.get("positions") or {}, fills, target_date)
    snap_pos = {s: float(p.get("shares") or 0.0) for s, p in (snap.get("positions") or {}).items()}
    syms = set(rep) | set(snap_pos)
    max_sd = max((abs(rep.get(s, 0.0) - snap_pos.get(s, 0.0)) for s in syms), default=0.0)
    cash_rep = replay_cash(account.get("cash"), fills, target_date)
    cash_diff = (cash_rep - float(snap.get("cash") or 0.0)) if snap.get("cash") is not None else None
    return max_sd, cash_diff, cash_rep


def t5(capture: Path) -> tuple[list[dict], list[str]]:
    rows_out: list[dict] = []
    notes: list[str] = []
    for name, book, rel in EVENTS:
        snap_dir = capture / rel
        ev_note = []
        snap_account = None
        # the snapshot may hold account.json (whole-book copy) or a *.clobbered pair
        acct_path = snap_dir / "account.json"
        if acct_path.exists():
            snap_account = read_json(acct_path)
        clob = snap_dir / "account.json.clobbered"
        if clob.exists():
            snap_account = read_json(clob)
            ev_note.append("holds account.json.clobbered + nav_history.jsonl.clobbered (the wiped state)")
        extra = sorted(p.name for p in snap_dir.iterdir()) if snap_dir.exists() else []
        ev_note.append("snapshot holds: " + ", ".join(extra))

        sd = snapshot_date(snap_dir, capture)
        max_sd = cash_diff = None
        live_dir = dict(BOOKS).get(book)
        if live_dir and snap_account is not None and (capture / live_dir / "account.json").exists():
            max_sd, cash_diff, _ = replay_diff(capture, live_dir, sd, snap_account)

        wrote_fills = None
        positions_changed = None
        next_state = None
        if name == "peer_sentinel_liquidation":
            incident = read_json(snap_dir / "INCIDENT.json")
            rev = incident.get("reversed_fills") or []
            wrote_fills = f"REMOVED {len(rev)} false fills (rewrote fills.jsonl without them)"
            positions_changed = f"restored pre-incident lots for {sorted({r['ticker'] for r in rev})}"
            # next state = final live account
            nxt = read_json(capture / "portfolio/account.json")
            next_state = f"final live account {nxt.get('cash')} cash, {sorted(nxt.get('positions') or {})}"
            snap_fills = read_jsonl(snap_dir / "fills.jsonl")
            live_fills = read_jsonl(capture / "portfolio/fills.jsonl")
            ev_note.append(f"snapshot fills={len(snap_fills)}, live fills={len(live_fills)} "
                           f"(live = snapshot minus the {len(rev)} reversed rows: "
                           f"{len(snap_fills) - len(rev) == len(live_fills)})")
        elif name == "pre_nvda_avgo_exit":
            live_fills = read_jsonl(capture / "portfolio/fills.jsonl")
            nv = [f for f in live_fills if str(f.get("ticker")).upper() in ("NVDA", "AVGO")]
            wrote_fills = f"NO balancing fills: {len(nv)} NVDA/AVGO rows in live fills.jsonl"
            nxt = read_json(capture / "portfolio/account.json")
            next_state = f"final live account: NVDA/AVGO present={sorted(set(snap_account.get('positions') or {}) - set(nxt.get('positions') or {}))} removed; cash {snap_account.get('cash')} -> {nxt.get('cash')}"
            snaps = snap_account.get("positions") or {}
            positions_changed = (f"NVDA {float(snaps.get('NVDA', {}).get('shares', 0)):.4f} + "
                                 f"AVGO {float(snaps.get('AVGO', {}).get('shares', 0)):.4f} shares "
                                 f"removed from the live account with no exit fills")
        elif name.startswith("remove_nvda_avgo"):
            wrote_fills = "unknown from capture (backup is the PRE state; no repair script in this repo)"
            if isinstance(snap_account, dict) and snap_account.get("positions"):
                snaps = snap_account["positions"]
                positions_changed = (f"PRE-removal state holds NVDA "
                                     f"{float(snaps.get('NVDA', {}).get('shares', 0)):.4f} + AVGO "
                                     f"{float(snaps.get('AVGO', {}).get('shares', 0)):.4f}; "
                                     f"book cash {snap_account.get('cash')}")
            nxt = None
            if live_dir and (capture / live_dir / "account.json").exists():
                nxt = read_json(capture / live_dir / "account.json")
                next_state = f"final live account: cash {snap_account.get('cash')} -> {nxt.get('cash')}, positions {sorted(snap_account.get('positions') or {})} -> {sorted(nxt.get('positions') or {})}"
            else:
                next_state = "book not live in capture (heavyweight has no account.json; self_directed archived)"
        elif name == "test_contamination":
            wrote_fills = "none (deleted/neutralized a contaminated pending_target.json only)"
            positions_changed = "none (no account file in snapshot)"
            pt = read_json(snap_dir / "pending_target.json.contaminated")
            next_state = (f"contaminated queue {pt.get('target')} asof={pt.get('asof')} "
                          f"queued_at={pt.get('queued_at')} removed; no account effect")
        elif name == "heavyweight_clobber":
            nav_clob = snap_dir / "nav_history.jsonl.clobbered"
            nrows = read_jsonl(nav_clob) if nav_clob.exists() else []
            wrote_fills = "unknown (clobbered pair only; no live heavyweight book in capture)"
            next_state = (f"no live account.json in portfolios/heavyweight/ — book left unenrolled; "
                          f"clobbered nav rows={len(nrows)}")
            positions_changed = "n/a (book not live)"

        # replay_consistent_after: does the post-repair state match the live-ledger replay
        # at the event date? Only computable where the capture holds the repaired state
        # (peer-sentinel: reconstruct repaired = snapshot + inverse of the reversed fills).
        after = "UNDETERMINABLE (no post-repair snapshot in capture)"
        if name == "peer_sentinel_liquidation":
            incident = read_json(snap_dir / "INCIDENT.json")
            rep_sh = defaultdict(float)
            rep_cash = float(snap_account.get("cash") or 0.0)
            for r in incident.get("reversed_fills") or []:
                rep_sh[str(r["ticker"]).upper()] += float(r["shares"])
                rep_cash -= float(r["value"])
            live_replay = replay_shares(
                read_json(capture / "portfolio/account.json").get("positions") or {},
                read_jsonl(capture / "portfolio/fills.jsonl"), "2026-07-30")
            syms = set(live_replay) | set(rep_sh)
            adiff = max(abs(live_replay.get(s, 0.0) - rep_sh.get(s, 0.0)) for s in syms) if syms else 0.0
            after = (f"reconstructed repaired state vs live replay@2026-07-30: "
                     f"max_share_diff={adiff:.6f}; cash diff vs live replay n/a "
                     f"(repair deliberately preserved the 07-30 cash-sweep accrual)")
        elif name == "pre_nvda_avgo_exit":
            live_replay = replay_shares(
                read_json(capture / "portfolio/account.json").get("positions") or {},
                read_jsonl(capture / "portfolio/fills.jsonl"), sd or "")
            live_replay = {s: x for s, x in live_replay.items() if abs(x) >= FLAT}
            live_replay_cash = replay_cash(
                read_json(capture / "portfolio/account.json").get("cash"),
                read_jsonl(capture / "portfolio/fills.jsonl"), sd or "")
            after = (f"live-ledger replay@{sd}: cash={live_replay_cash:.2f} "
                     f"positions={sorted(live_replay)} — the live replay STILL holds NVDA/AVGO "
                     f"(no exit fills), while the live final account does not: the removal "
                     f"diverged the account from the fills ledger")

        # direction: does the next live state stay explainable by that book's fills?
        if name == "peer_sentinel_liquidation":
            direction = "TOWARD_FILLS"   # removes the account-only fills and restores their lots
        elif name == "pre_nvda_avgo_exit":
            live_fills = read_jsonl(capture / "portfolio/fills.jsonl")
            nv = [f for f in live_fills if str(f.get("ticker")).upper() in ("NVDA", "AVGO")]
            direction = "AWAY" if not nv else "TOWARD_FILLS"  # positions vanish with no exit fills
        elif name.startswith("remove_nvda_avgo"):
            if live_dir and (capture / live_dir / "account.json").exists():
                live_fills = read_jsonl(capture / live_dir / "fills.jsonl")
                nv = [f for f in live_fills if str(f.get("ticker")).upper() in ("NVDA", "AVGO")]
                direction = "AWAY" if not nv else "TOWARD_FILLS"
            else:
                direction = "UNDETERMINABLE"
        elif name == "test_contamination":
            direction = "NEUTRAL"        # a queue file only; no account or fills touched
        else:
            direction = "UNDETERMINABLE"  # heavyweight wiped pair; no live book to reconcile
        rows_out.append({
            "event": name, "book": book, "snapshot_path": rel, "date": sd,
            "positions_changed": positions_changed or "see evidence",
            "cash_delta": (f"{cash_diff:+.2f} vs fills-implied" if cash_diff is not None else "n/a"),
            "wrote_fills": wrote_fills or "unknown",
            "replay_consistent_before": (f"max_share_diff={max_sd}" if max_sd is not None
                                         else "UNDETERMINABLE") + (f", cash_diff(replay-snapshot)={cash_diff:.2f}"
                                                                   if cash_diff is not None else ""),
            "replay_consistent_after": after,
            "direction": direction,
            "code_ref": CODE_REF[name],
            "evidence": "; ".join(ev_note),
        })
        notes.append(f"{name} [{book}] snapshot@{sd}: {json.dumps(snap_account, default=str)[:300]}")
    return rows_out, notes


CODE_REF = {
    "pre_nvda_avgo_exit": "no committed repair script in this repo (pre-rebuild op); ref git a81448b40 'fix(conviction): de-overfit the AVGO/NVDA override'; snapshot dir is the pre-state",
    "remove_nvda_avgo_autonomous": "no committed repair script; snapshot dir holds PRE-removal state (NVDA/AVGO still present)",
    "remove_nvda_avgo_heavyweight": "no committed repair script; PRE-removal state",
    "remove_nvda_avgo_self_directed": "no committed repair script; PRE-removal state (book later archived)",
    "test_contamination": "README.md in snapshot; root cause closed by tests/conftest.py autouse _isolate_book_state (git 265baae57 'share ONE isolated book root per session', 6c8a0a556 'close the live-book test-write gap')",
    "peer_sentinel_liquidation": "scripts/repair_live_books_20260730.py::_restore_flagship (L128-250): removes the 5 false fills and restores positions from this snapshot",
    "heavyweight_clobber": "no committed repair script in this repo; CONTRAINTS noted in ECON CONTRACTS.md E7 (heavyweight has only the clobbered pair)",
}


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--capture", required=True, type=Path)
    ap.add_argument("--ref", required=True, type=Path)
    ap.add_argument("--manifest", type=Path, default=None)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--summary-path", type=Path, default=None,
                    help="optional sidecar for the stdout report (kept out of the repo by default)")
    a = ap.parse_args()
    manifest = a.manifest or a.capture.parent / "MANIFEST.json"

    n_verified, n_listed, mismatches = verify_capture(a.capture, manifest)
    ref_sha = hashlib.sha256(a.ref.read_bytes()).hexdigest()
    ref_ok = ref_sha == "d1fa0c44f96d608d84a7a22377d5cade94159976c94aa18856ac31961431689b"
    ref = load_ref(a.ref)
    print(f"manifest: {n_verified}/{n_listed} verified; mismatches={len(mismatches)}")
    for m in mismatches[:10]:
        print("  ", m)
    print(f"ref sha256 ok: {ref_ok}; symbols={len(ref)}")

    a.out.mkdir(parents=True, exist_ok=True)
    report: list[str] = []

    t1_rows, t1_notes = t1(a.capture, ref)
    write_csv(a.out / "w3_t1_a02_incidence.csv", t1_rows)
    report.append("== T1 A02 incidence ==")
    report.extend(t1_notes)

    t2_rows, t2s = t2(a.capture, ref)
    write_csv(a.out / "w3_t2_afterhours.csv", t2_rows)
    report.append("== T2 after-hours ==")
    report.append(json.dumps(t2s, indent=1, default=str))
    top = sorted((r for r in t2_rows if r["compared"] and not r["adjusted"]),
                 key=lambda r: -abs(r["dev_bp"]))[:10]
    report.append("top10 deviations: " + "; ".join(
        f"{r['symbol']} {r['date']} mark={r['mark']} ref={r['ref']} {r['dev_bp']:.1f}bp" for r in top))

    t3_rows, t3s, t3_notes = t3(a.capture, ref)
    write_csv(a.out / "w3_t3_missing_bars.csv", t3_rows)
    report.append("== T3 missing bars ==")
    report.append(json.dumps(t3s, indent=1, default=str))
    report.extend(t3_notes)

    t4_rows, t4s, t4_notes = t4(a.capture, ref)
    write_csv(a.out / "w3_t4_fill_stamps.csv", t4_rows)
    report.append("== T4 fill stamps ==")
    report.extend(t4_notes)
    report.append("value-check failures: " + ("; ".join(t4s["value_failures"]) or "none"))

    t5_rows, t5_notes = t5(a.capture)
    write_csv(a.out / "w3_t5_us_repairs.csv", t5_rows)
    report.append("== T5 repairs ==")
    report.extend(t5_notes)

    if a.summary_path:
        a.summary_path.write_text("\n".join(report) + "\n", encoding="utf-8")
    print("\n".join(report))
    print(f"\nfiles used from capture: {len(USED.paths)}")
    print("wrote:", sorted(p.name for p in a.out.iterdir()))
    return 0


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    keys: list[str] = []
    for r in rows:
        for k in r:
            if k not in keys:
                keys.append(k)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    raise SystemExit(main())

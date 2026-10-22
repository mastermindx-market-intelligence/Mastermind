#!/usr/bin/env python3
"""Deterministic builder for the PBR redacted decision-case fixtures.

Usage:
    python _build_decision_cases.py <case_rows.jsonl> <case_fills.jsonl> <MANIFEST.json> <out_dir>

Regenerates every fixture in tests/fixtures/pbr/decision_cases/ byte-for-byte.
Stdlib only. Imports nothing from the repository and reads nothing beyond the
three input paths given on the command line.

Inputs are the read-only research capture extracts under
~/lanes/tmp/pbr-res-ls2-fixtures/ (schema: one JSON object per line, each
carrying {source_book, source_host_path, source_in_service_path,
source_file_sha256, line_index_0based, line_sha256, row}).

Redaction policy (applied identically to every fixture): retain all row-level
fields verbatim except drop ``perception_input``; filter ``holdings`` and
``effective_holdings`` to the case ticker.

Constant verified by reading (not imported or executed) at authoring time on
worktree Mastermind @ origin/master 230e9a301: the regional sizing policy in
brain/decision_submission.py defines conviction_caps
{"high": 0.18, "medium": 0.12, "low": 0.06} at line 450 (policy
deterministic_incremental_regional_allocator.v1). The verbatim quote is
embedded below as CAP_REFERENCE and is NOT re-read from the repo by this
script.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

SCHEMA = "pbr.decision_case_fixture.v1"
MANIFEST_SHA256 = "4c55f3f8df454ecfcb2742b0b7bec5043ac35d4919a66026888541fa4bf976aa"
CAPTURE_DIR = "/Volumes/Mastermind/evidence/pbr/research-capture-20261022T073549Z"
REDACTION_POLICY = (
    "retain all row-level fields verbatim except: drop perception_input; "
    "filter holdings and effective_holdings to the case ticker"
)

# Cited by the program audit; NOT re-fetched when this builder runs.
EXTERNAL_FACTS_MU_ENTRY = [
    {
        "fact": "Micron announced on 2026-08-26 that fiscal Q4 2026 results would be reported on 2026-09-30",
        "event_date": "2026-09-30",
        "published": "2026-08-26",
        "url": "https://investors.micron.com/news/press-release/2026/Micron-Technology-to-Report-Fiscal-Fourth-Quarter-Results-on-September-30-2026/default.aspx",
        "verification_status": "cited_by_audit_not_refetched",
    },
    {
        "fact": "Micron reported fiscal Q4 and full-year 2026 results on 2026-09-30",
        "event_date": "2026-09-30",
        "published": "2026-09-30",
        "url": "https://investors.micron.com/news/press-release/2026/Micron-Technology-Inc--Reports-Record-Fiscal-Fourth-Quarter-and-Full-Year-2026-Results/",
        "verification_status": "cited_by_audit_not_refetched",
    },
    {
        "fact": "SEC-hosted fiscal Q4 2026 results release (exhibit 99.1)",
        "published": "2026-09-30",
        "url": "https://www.sec.gov/Archives/edgar/data/723125/000072312526000018/a2026q4ex991-pressrelease.htm",
        "verification_status": "cited_by_audit_not_refetched",
    },
]

# Verified by reading brain/decision_submission.py line 450 in this worktree at
# authoring time (commit 230e9a301). The builder does not read the repo.
CAP_REFERENCE = {
    "file": "brain/decision_submission.py",
    "line": 450,
    "policy_name": "deterministic_incremental_regional_allocator.v1",
    "caps": {"high": 0.18, "medium": 0.12, "low": 0.06},
    "quote": '        "conviction_caps": {"high": 0.18, "medium": 0.12, "low": 0.06},',
    "verification": (
        "read verbatim from the worktree file at fixture authoring time "
        "(origin/master 230e9a301); not imported, executed, or re-read by this builder"
    ),
}

# (case_id, case_role, defect_ref, ticker, ticker_name, fill_mode, [(book, line_index), ...])
# fill_mode: "linked"  -> only fills of the ticker whose fill_id appears in a
#                       provided record's settlement_fill_ids;
#            "none"    -> no fills;
#            "all"     -> every fill of the ticker in the fills extract.
CASES = [
    (
        "mu_2026-10-02_entry",
        "regression",
        "A14",
        "MU",
        None,
        "linked",
        [("autonomous", 75)],
    ),
    (
        "mu_2026-10-05_amendment",
        "regression",
        "A15",
        "MU",
        None,
        "none",
        [("autonomous", 75), ("autonomous", 76)],
    ),
    (
        "mu_2026-10-22_planless_summary",
        "regression",
        "A15",
        "MU",
        None,
        "none",
        [("autonomous", 89), ("autonomous", 78)],
    ),
    (
        "cn_688062_2026-08-12_sizing",
        "regression",
        "A16",
        "688062.SS",
        "迈威生物",
        "all",
        [("china", 35), ("china", 36), ("china", 37)],
    ),
    (
        "xom_2026-08-12_positive_control",
        "positive_control",
        "none",
        "XOM",
        None,
        "all",
        [("autonomous", 38), ("autonomous", 39), ("autonomous", 40)],
    ),
]

LINKAGE_KEY_BY_TICKER = {
    "MU": "MU entry settlement",
    "688062.SS": "688062.SS entry",
    "XOM": "XOM entry",
}


def canon_bytes(obj) -> bytes:
    return (json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def records_sha256(records) -> str:
    payload = json.dumps(records, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def load_inputs(rows_path: str, fills_path: str, manifest_path: str):
    rows = [json.loads(line) for line in Path(rows_path).read_text(encoding="utf-8").splitlines() if line.strip()]
    fills = [json.loads(line) for line in Path(fills_path).read_text(encoding="utf-8").splitlines() if line.strip()]
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    rows_by_key = {(r["source_book"], r["line_index_0based"]): r for r in rows}
    return rows_by_key, fills, manifest


def provenance(rec) -> dict:
    return {
        "source_book": rec["source_book"],
        "source_host_path": rec["source_host_path"],
        "source_in_service_path": rec["source_in_service_path"],
        "source_file_sha256": rec["source_file_sha256"],
        "line_index_0based": rec["line_index_0based"],
        "line_sha256": rec["line_sha256"],
        "decision_id": rec["row"]["decision_id"],
    }


def matches_case(text: str, ticker: str, name) -> bool:
    return ticker in text or (name is not None and name in text)


def redact_row(row: dict, ticker: str):
    retained = {k: v for k, v in row.items() if k != "perception_input"}
    dropped = [k for k in row if k == "perception_input"]
    retained["holdings"] = [h for h in row["holdings"] if h.get("ticker") == ticker]
    retained["effective_holdings"] = [h for h in row["effective_holdings"] if h.get("ticker") == ticker]
    return retained, dropped


def build_record(rec, ticker: str, name) -> dict:
    row = rec["row"]
    case_holding = next((h for h in row["holdings"] if h.get("ticker") == ticker), None)
    case_effective = next((h for h in row["effective_holdings"] if h.get("ticker") == ticker), None)
    case_falsifiers = [f for f in row["falsifiers"] if isinstance(f, str) and matches_case(f, ticker, name)]
    retained_row, _dropped = redact_row(row, ticker)
    return {
        "line_index_0based": rec["line_index_0based"],
        "decision_id": row["decision_id"],
        "row": retained_row,
        "case_holding": case_holding,
        "case_effective_holding": case_effective,
        "case_row_falsifiers": case_falsifiers,
    }


def build_redaction(rows, ticker: str) -> dict:
    other = []
    dropped_per_record = []
    for rec in rows:
        row = rec["row"]
        dropped = [k for k in row if k == "perception_input"]
        dropped_per_record.append({"line_index_0based": rec["line_index_0based"], "dropped_fields": dropped})
        for h in row["holdings"]:
            if h.get("ticker") != ticker:
                other.append(
                    {
                        "line_index_0based": rec["line_index_0based"],
                        "ticker": h.get("ticker"),
                        "weight": h.get("weight"),
                        "conviction": h.get("conviction"),
                    }
                )
    return {
        "policy": REDACTION_POLICY,
        "dropped_row_fields": dropped_per_record,
        "other_holdings": other,
    }


def build_fills(fill_records, provided_rows, ticker: str, fill_mode: str) -> list:
    if fill_mode == "none":
        return []
    settlement_ids = {
        fill_id
        for rec in provided_rows
        for fill_id in (rec["row"].get("settlement_fill_ids") or [])
    }
    out = []
    for f in fill_records:
        frow = f["row"]
        if frow.get("ticker") != ticker:
            continue
        if fill_mode == "linked" and frow.get("fill_id") not in settlement_ids:
            continue
        linked = [
            rec["row"]["decision_id"]
            for rec in provided_rows
            if frow.get("fill_id") in (rec["row"].get("settlement_fill_ids") or [])
        ]
        out.append(
            {
                "line_index_0based": f["line_index_0based"],
                "line_sha256": f["line_sha256"],
                "linked_decision_ids": linked,
                "row": frow,
            }
        )
    return out


def leaf_strings(obj, path: str):
    if isinstance(obj, str):
        yield path, obj
    elif isinstance(obj, dict):
        for key, value in obj.items():
            yield from leaf_strings(value, f"{path}.{key}" if path else str(key))
    elif isinstance(obj, list):
        for index, value in enumerate(obj):
            yield from leaf_strings(value, f"{path}[{index}]")


def sentences_with_terms(text: str, terms) -> list:
    return [s for s in (part.strip() for part in text.split(". ")) if s and any(t in s for t in terms)]


def collect_sentences(rows, ticker: str, terms) -> list:
    out = []
    for rec in rows:
        row = rec["row"]
        for field, text in leaf_strings({"summary": row.get("summary"), "decision_memo": row.get("decision_memo")}, ""):
            if not field.startswith(("summary", "decision_memo")):
                continue
            for sentence in sentences_with_terms(text, terms):
                out.append(
                    {
                        "line_index_0based": rec["line_index_0based"],
                        "field": field,
                        "sentence": sentence,
                    }
                )
    return out


def holding_changes(old_holding, new_holding) -> dict:
    changes = {}
    for key in list(old_holding) + [k for k in new_holding if k not in old_holding]:
        old_value = old_holding.get(key)
        new_value = new_holding.get(key)
        if old_value != new_value:
            changes[key] = {"old": old_value, "new": new_value}
    return changes


def row_falsifier_changes(old_rec, new_rec, ticker: str, name) -> dict:
    return {
        "old": [f for f in old_rec["row"]["falsifiers"] if matches_case(f, ticker, name)],
        "new": [f for f in new_rec["row"]["falsifiers"] if matches_case(f, ticker, name)],
    }


def derived_for(case_id: str, ticker: str, name, rows, fills, records, rows_by_key) -> dict:
    by_line = {rec["line_index_0based"]: rec for rec in rows}
    if case_id == "mu_2026-10-02_entry":
        # Row 75 lists two settlement fill ids; only those present in the
        # capture's fills extract can appear in "fills". Record the gap.
        settlement_ids = by_line[75]["row"].get("settlement_fill_ids") or []
        captured = {f["row"]["fill_id"] for f in fills}
        return {
            "settlement_fill_ids_absent_from_capture": [i for i in settlement_ids if i not in captured]
        }
    if case_id == "mu_2026-10-05_amendment":
        old_holding = next(h for h in by_line[75]["row"]["holdings"] if h.get("ticker") == ticker)
        new_holding = next(h for h in by_line[76]["row"]["holdings"] if h.get("ticker") == ticker)
        return {
            "case_holding_changes": holding_changes(old_holding, new_holding),
            "case_row_falsifier_changes": row_falsifier_changes(by_line[75], by_line[76], ticker, name),
        }
    if case_id == "mu_2026-10-22_planless_summary":
        in_holdings = {}
        mu_requested = []
        mu_exit = []
        prior_thesis_refs = []
        for rec in rows:
            line = rec["line_index_0based"]
            row = rec["row"]
            in_holdings[str(line)] = any(h.get("ticker") == ticker for h in row["holdings"])
            for field, sink in (
                ("requested_exit_decisions", mu_requested),
                ("exit_decisions", mu_exit),
            ):
                for entry in row.get(field) or []:
                    if entry.get("ticker") == ticker:
                        sink.append({"line_index_0based": line, "entry": entry})
        for line in (75, 76):
            holding = next(h for h in rows_by_key[("autonomous", line)]["row"]["holdings"] if h.get("ticker") == ticker)
            prior_thesis_refs.append(
                {
                    "line_index_0based": line,
                    "decision_id": rows_by_key[("autonomous", line)]["row"]["decision_id"],
                    "falsifier": holding["falsifier"],
                    "exit_plan": holding["exit_plan"],
                }
            )
        return {
            "ticker_in_holdings": in_holdings,
            "mu_requested_exit_decisions": mu_requested,
            "mu_exit_decisions": mu_exit,
            "prior_thesis_refs": prior_thesis_refs,
            "summary_and_memo_sentences": collect_sentences(rows, ticker, [ticker, "held_without_active_plan"]),
        }
    if case_id == "cn_688062_2026-08-12_sizing":
        return {"cap_reference": CAP_REFERENCE}
    return {}


def fixture_for(case_id: str, case_role: str, defect_ref: str, ticker: str, name,
                fill_mode: str, rows, fill_records, manifest, rows_by_key) -> dict:
    records = [build_record(rec, ticker, name) for rec in rows]
    return {
        "schema": SCHEMA,
        "case_id": case_id,
        "case_role": case_role,
        "defect_ref": defect_ref,
        "ticker": ticker,
        "capture": {
            "capture_dir": CAPTURE_DIR,
            "manifest_sha256": MANIFEST_SHA256,
            "captured_utc": manifest["host_sha256_before_at"],
        },
        "provenance": [provenance(rec) for rec in rows],
        "redaction": build_redaction(rows, ticker),
        "records": records,
        "fills": build_fills(fill_records, rows, ticker, fill_mode),
        "linkage_note": manifest["related_links"][LINKAGE_KEY_BY_TICKER[ticker]],
        "external_facts": EXTERNAL_FACTS_MU_ENTRY if case_id == "mu_2026-10-02_entry" else [],
        "derived": derived_for(case_id, ticker, name, rows, fill_records, records, rows_by_key),
        "records_sha256": records_sha256(records),
    }


def main(argv) -> int:
    if len(argv) != 5:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    rows_path, fills_path, manifest_path, out_dir = argv[1:5]
    rows_by_key, fills, manifest = load_inputs(rows_path, fills_path, manifest_path)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for case_id, case_role, defect_ref, ticker, name, fill_mode, keys in CASES:
        rows = [rows_by_key[(book, line)] for book, line in keys]
        fixture = fixture_for(
            case_id, case_role, defect_ref, ticker, name, fill_mode, rows, fills, manifest, rows_by_key
        )
        (out / f"{case_id}.json").write_bytes(canon_bytes(fixture))
        print(f"wrote {out / (case_id + '.json')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

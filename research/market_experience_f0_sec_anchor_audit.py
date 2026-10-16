"""Read-only audit of the existing broad SEC Item-2.02 anchor store.

This module does not fetch SEC, mutate Macro data, publish event workspaces, or
admit a training corpus. It reads exact Git objects from a caller-supplied Macro
checkout and reports whether the committed anchor store can support exact filing
identity required by Market Experience historical reconstruction.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
from typing import Any

import pandas as pd

MACRO_COMMIT = "836379db84f9e34354f54e2fb26cd2065d186034"
COLLECTOR_PATH = "collectors/edgar_earnings_8k.py"
COLLECTOR_BLOB = "19665592a256bb4ef8af6ebc2fdd0f74bfdf992f"
STORE_PATH = "data/edgar/earnings_8k_dates.parquet"
STORE_BLOB = "e1fdf2c9717b02a98f6fe7cfab7e88e51bf912d6"
MANIFEST_PATH = "data/edgar/earnings_8k_dates_manifest.json"
MANIFEST_BLOB = "a45bc80a3cea8b2cd554624cdeda19cb66d47b5d"
REFRESH_PATH = "scripts/refresh_event_workspaces.py"
REFRESH_BLOB = "7d01aacb3bec29e42de799eeed480d16f930389b"

LEGACY_COLUMNS = (
    "ticker",
    "cik",
    "filing_date",
    "acceptance_datetime",
    "items",
)
CURRENT_COLUMNS = (
    "ticker",
    "cik",
    "accession",
    "form",
    "filing_date",
    "acceptance_datetime",
    "report_date",
    "items",
)
REQUIRED_IDENTITY_COLUMNS = ("cik", "accession", "report_date")
REQUIRED_REVISION_COLUMNS = ("accession", "form", "report_date")
MAX_OBJECT_BYTES = 64 * 1024 * 1024


class SecAnchorAuditError(ValueError):
    pass


def git_blob_sha1(body: bytes) -> str:
    return hashlib.sha1(
        b"blob " + str(len(body)).encode("ascii") + b"\0" + body
    ).hexdigest()


def read_git_blob(
    root: Path,
    path: str,
    *,
    expected_blob: str,
    commit: str = MACRO_COMMIT,
) -> bytes:
    if not re.fullmatch(r"[a-f0-9]{40}", commit):
        raise SecAnchorAuditError("commit must be an exact SHA")
    allowed = {
        COLLECTOR_PATH: COLLECTOR_BLOB,
        STORE_PATH: STORE_BLOB,
        MANIFEST_PATH: MANIFEST_BLOB,
        REFRESH_PATH: REFRESH_BLOB,
    }
    if path not in allowed or expected_blob != allowed[path]:
        raise SecAnchorAuditError("unregistered source reference")
    env = {
        **__import__("os").environ,
        "GIT_NO_LAZY_FETCH": "1",
        "GIT_TERMINAL_PROMPT": "0",
    }
    spec = f"{commit}:{path}"
    cmd = ["git", "--no-pager", "-C", str(root), "cat-file"]
    size = int(
        subprocess.check_output(cmd + ["-s", spec], env=env, timeout=30).decode()
    )
    if size <= 0 or size > MAX_OBJECT_BYTES:
        raise SecAnchorAuditError("source object exceeds audit bound")
    body = subprocess.check_output(cmd + ["blob", spec], env=env, timeout=30)
    if len(body) != size or git_blob_sha1(body) != expected_blob:
        raise SecAnchorAuditError("source identity mismatch")
    return body


def _iso_day(series: pd.Series) -> pd.Series:
    parsed = pd.to_datetime(series, errors="coerce", utc=True)
    return parsed


def analyze_store(frame: pd.DataFrame) -> dict[str, Any]:
    columns = tuple(str(c) for c in frame.columns)
    if columns not in {LEGACY_COLUMNS, CURRENT_COLUMNS}:
        raise SecAnchorAuditError(f"unexpected store columns: {columns!r}")
    if frame.empty:
        raise SecAnchorAuditError("SEC anchor store is empty")
    filing = _iso_day(frame["filing_date"])
    acceptance = _iso_day(frame["acceptance_datetime"])
    if filing.isna().any():
        raise SecAnchorAuditError("store contains unparseable filing_date")
    if acceptance.isna().any():
        raise SecAnchorAuditError("store contains unparseable acceptance_datetime")
    tokens_ok = frame["items"].fillna("").astype(str).map(
        lambda raw: "2.02" in [part.strip() for part in raw.split(",")]
    )
    if not bool(tokens_ok.all()):
        raise SecAnchorAuditError("store contains a non-Item-2.02 row")

    by_cik = (
        pd.DataFrame(
            {
                "cik": frame["cik"],
                "filing": filing,
            }
        )
        .groupby("cik", dropna=False)
        .agg(rows=("filing", "size"), first=("filing", "min"), last=("filing", "max"))
    )
    span_years = (by_cik["last"] - by_cik["first"]).dt.days / 365.25
    missing_identity = [
        name for name in REQUIRED_IDENTITY_COLUMNS if name not in frame.columns
    ]
    missing_revision = [
        name for name in REQUIRED_REVISION_COLUMNS if name not in frame.columns
    ]
    result: dict[str, Any] = {
        "rows": int(len(frame)),
        "columns": list(columns),
        "schema_state": (
            "CURRENT_CANONICAL_FILING_KEY"
            if not missing_revision
            else "LEGACY_DATE_KEY_MISSING_CANONICAL_IDENTITY"
        ),
        "missing_identity_columns": missing_identity,
        "missing_revision_columns": missing_revision,
        "tickers": int(frame["ticker"].nunique()),
        "ciks": int(frame["cik"].nunique()),
        "filing_min": filing.min().date().isoformat(),
        "filing_max": filing.max().date().isoformat(),
        "valid_filing_dates": int(filing.notna().sum()),
        "valid_acceptance_datetimes": int(acceptance.notna().sum()),
        "exact_item_202_rows": int(tokens_ok.sum()),
        "ciks_with_8y_span": int((span_years >= 8).sum()),
        "ciks_with_20_rows": int((by_cik["rows"] >= 20).sum()),
        "row_count_quantiles": {
            str(k): float(v)
            for k, v in by_cik["rows"].quantile([0, .1, .25, .5, .75, .9, 1]).items()
        },
        "span_year_quantiles": {
            str(k): float(v)
            for k, v in span_years.quantile([0, .1, .25, .5, .75, .9, 1]).items()
        },
    }
    if not missing_revision:
        accession = frame["accession"].fillna("").astype(str)
        result["accession_present"] = int(accession.str.len().gt(0).sum())
        result["report_date_present"] = int(
            pd.to_datetime(frame["report_date"], errors="coerce").notna().sum()
        )
        result["form_present"] = int(
            frame["form"].fillna("").astype(str).str.len().gt(0).sum()
        )
        result["canonical_key_duplicates"] = int(
            frame.loc[accession.ne(""), ["cik", "accession"]].duplicated().sum()
        )
    return result


def analyze_manifest(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or not value:
        raise SecAnchorAuditError("manifest is not a non-empty object")
    statuses: dict[str, int] = {}
    filings = 0
    missing_shards = 0
    clocks: list[str] = []
    malformed = 0
    for key, row in value.items():
        if not isinstance(row, dict):
            malformed += 1
            continue
        status = str(row.get("status"))
        statuses[status] = statuses.get(status, 0) + 1
        filings += int(row.get("n_filings") or 0)
        missing_shards += int(row.get("n_shards_missing") or 0)
        if row.get("ts"):
            clocks.append(str(row["ts"]))
        try:
            int(key)
        except (TypeError, ValueError):
            malformed += 1
    return {
        "entries": len(value),
        "status_counts": statuses,
        "sum_manifest_filings": filings,
        "sum_missing_shards": missing_shards,
        "malformed_entries": malformed,
        "ts_min": min(clocks) if clocks else None,
        "ts_max": max(clocks) if clocks else None,
    }


def parse_manifest(body: bytes) -> dict[str, Any]:
    try:
        value = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SecAnchorAuditError("manifest is invalid JSON") from exc
    return analyze_manifest(value)


def audit(macro_root: Path) -> dict[str, Any]:
    collector = read_git_blob(
        macro_root, COLLECTOR_PATH, expected_blob=COLLECTOR_BLOB
    )
    refresh = read_git_blob(
        macro_root, REFRESH_PATH, expected_blob=REFRESH_BLOB
    )
    store_body = read_git_blob(
        macro_root, STORE_PATH, expected_blob=STORE_BLOB
    )
    manifest_body = read_git_blob(
        macro_root, MANIFEST_PATH, expected_blob=MANIFEST_BLOB
    )
    if b'"accession"' not in collector or b'"report_date"' not in collector:
        raise SecAnchorAuditError("collector no longer declares the canonical key fields")
    if b"discover_new_homebuilder_revisions" not in refresh:
        raise SecAnchorAuditError("expected existing Company Intelligence revision path absent")

    frame = pd.read_parquet(io.BytesIO(store_body))
    store = analyze_store(frame)
    manifest = parse_manifest(manifest_body)
    delta = manifest["sum_manifest_filings"] - store["rows"]
    return {
        "schema": "market_experience.f0_sec_anchor_audit.v1",
        "status": "FOUNDATION_PRESENT_MIGRATION_REQUIRED",
        "source": {
            "repository": "mastermindx-market-intelligence/macro",
            "commit": MACRO_COMMIT,
            "collector": {"path": COLLECTOR_PATH, "git_blob": COLLECTOR_BLOB},
            "store": {"path": STORE_PATH, "git_blob": STORE_BLOB},
            "manifest": {"path": MANIFEST_PATH, "git_blob": MANIFEST_BLOB},
            "event_refresh": {"path": REFRESH_PATH, "git_blob": REFRESH_BLOB},
        },
        "store": store,
        "manifest": manifest,
        "manifest_minus_store_rows": int(delta),
        "interpretation": {
            "canonical_filing_key_required": ["cik", "accession"],
            "event_grouping_requires": ["cik", "report_date"],
            "revision_metadata_required": ["accession", "form", "report_date"],
            "store_ready_for_exact_revision_join": (
                store["schema_state"] == "CURRENT_CANONICAL_FILING_KEY"
                and store.get("canonical_key_duplicates", 1) == 0
            ),
            "migration_required": bool(store["missing_revision_columns"]),
            "delta_cause_proven": False,
        },
        "authority": {
            "production_write": False,
            "training_admitted": False,
            "forecast_trial": False,
            "trade_authority": False,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--macro-root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    receipt = audit(args.macro_root)
    text = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

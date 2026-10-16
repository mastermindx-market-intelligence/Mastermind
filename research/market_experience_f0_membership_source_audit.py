"""Offline qualification for the existing historical S&P membership source.

This is a research/audit utility, not a collector, store, production reader, or
rights grant. It reads two caller-supplied files, verifies their pinned Git blob
identities, validates interval/snapshot structure, and compares fixed dates.
"""
from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import date
import hashlib
import io
import json
from pathlib import Path
from typing import Iterable

UPSTREAM_REPOSITORY = "fja05680/sp500"
UPSTREAM_COMMIT = "a2430f2af0c79ddf0748e91de11bdeb1616ab5a7"
INTERVAL_PATH = "sp500_ticker_start_end.csv"
INTERVAL_GIT_BLOB = "3ed3b0e8d9e6e63730c153ee1f13ddaf6ed281bb"
INTERVAL_BYTES = 28058
SNAPSHOT_PATH = "S&P 500 Historical Components & Changes (Updated).csv"
SNAPSHOT_GIT_BLOB = "656b033be9418db272f1903f4f8e79a2a8664e6a"
SNAPSHOT_BYTES = 5530907
LICENSE_GIT_BLOB = "1702a4df51e2c2a0a96ede6b10afeb880b976bbd"
README_GIT_BLOB = "43072b7901eaaedbc63a523a1040ac91b5c65dbb"
QUARTER_ENDS = tuple(
    date(year, month, day)
    for year in range(2019, 2024)
    for month, day in ((3, 31), (6, 30), (9, 30), (12, 31))
)


class MembershipAuditError(ValueError):
    pass


@dataclass(frozen=True)
class Interval:
    raw_symbol: str
    symbol: str
    start: date
    end: date | None


@dataclass(frozen=True)
class Snapshot:
    on: date
    members: frozenset[str]


def _git_blob_sha1(body: bytes) -> str:
    header = f"blob {len(body)}\0".encode("ascii")
    return hashlib.sha1(header + body).hexdigest()


def _strict_date(value: str, *, field: str) -> date:
    text = str(value or "").strip()
    try:
        parsed = date.fromisoformat(text)
    except ValueError as exc:
        raise MembershipAuditError(f"{field}: invalid date {value!r}") from exc
    if parsed.isoformat() != text:
        raise MembershipAuditError(f"{field}: date must be canonical YYYY-MM-DD")
    return parsed


def normalize_symbol(value: str) -> str:
    symbol = str(value or "").strip().replace(".", "-")
    if not symbol or "," in symbol or any(ch.isspace() for ch in symbol):
        raise MembershipAuditError(f"invalid symbol {value!r}")
    return symbol


def _decode_utf8(body: bytes, *, label: str) -> str:
    try:
        return body.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise MembershipAuditError(f"{label} is not UTF-8") from exc


def load_intervals(body: bytes) -> tuple[list[Interval], dict]:
    if len(body) != INTERVAL_BYTES or _git_blob_sha1(body) != INTERVAL_GIT_BLOB:
        raise MembershipAuditError("interval source identity mismatch")
    reader = csv.DictReader(io.StringIO(_decode_utf8(body, label="interval source")))
    if reader.fieldnames != ["ticker", "start_date", "end_date"]:
        raise MembershipAuditError(f"unexpected interval header {reader.fieldnames!r}")
    rows: list[Interval] = []
    raw_by_normalized: dict[str, set[str]] = {}
    exact_rows: set[tuple[str, str, str]] = set()
    duplicate_rows: list[tuple[str, str, str]] = []
    for line_number, row in enumerate(reader, start=2):
        if set(row) != {"ticker", "start_date", "end_date"}:
            raise MembershipAuditError(f"interval line {line_number}: unexpected columns")
        raw = str(row["ticker"] or "").strip()
        symbol = normalize_symbol(raw)
        start = _strict_date(row["start_date"], field=f"interval line {line_number} start")
        end_text = str(row["end_date"] or "").strip()
        end = _strict_date(end_text, field=f"interval line {line_number} end") if end_text else None
        if end is not None and end <= start:
            raise MembershipAuditError(
                f"interval line {line_number}: end must be strictly after start"
            )
        key = (raw, start.isoformat(), end.isoformat() if end else "")
        if key in exact_rows:
            duplicate_rows.append(key)
        exact_rows.add(key)
        raw_by_normalized.setdefault(symbol, set()).add(raw)
        rows.append(Interval(raw, symbol, start, end))
    if duplicate_rows:
        raise MembershipAuditError(f"duplicate interval rows: {duplicate_rows[:3]}")
    collisions = {
        symbol: sorted(raws)
        for symbol, raws in raw_by_normalized.items()
        if len(raws) > 1
    }
    if collisions:
        raise MembershipAuditError(f"symbol normalization collisions: {collisions}")
    by_symbol: dict[str, list[Interval]] = {}
    for item in rows:
        by_symbol.setdefault(item.symbol, []).append(item)
    overlaps: list[dict] = []
    for symbol, spans in by_symbol.items():
        spans.sort(key=lambda item: item.start)
        for previous, current in zip(spans, spans[1:]):
            if previous.end is None or current.start < previous.end:
                overlaps.append(
                    {
                        "symbol": symbol,
                        "previous": [previous.start.isoformat(), previous.end.isoformat() if previous.end else None],
                        "current": [current.start.isoformat(), current.end.isoformat() if current.end else None],
                    }
                )
    if overlaps:
        raise MembershipAuditError(f"overlapping intervals: {overlaps[:3]}")
    finite_ends = [item.end for item in rows if item.end is not None]
    return rows, {
        "rows": len(rows),
        "unique_symbols": len(by_symbol),
        "start_min": min(item.start for item in rows).isoformat(),
        "finite_end_max": max(finite_ends).isoformat(),
        "open_intervals": sum(item.end is None for item in rows),
        "normalization_collisions": 0,
        "overlaps": 0,
        "duplicate_rows": 0,
    }


def load_snapshots(body: bytes) -> tuple[list[Snapshot], dict]:
    if len(body) != SNAPSHOT_BYTES or _git_blob_sha1(body) != SNAPSHOT_GIT_BLOB:
        raise MembershipAuditError("snapshot source identity mismatch")
    reader = csv.DictReader(io.StringIO(_decode_utf8(body, label="snapshot source")))
    if reader.fieldnames != ["date", "tickers"]:
        raise MembershipAuditError(f"unexpected snapshot header {reader.fieldnames!r}")
    snapshots: list[Snapshot] = []
    seen_dates: set[date] = set()
    raw_by_normalized: dict[str, set[str]] = {}
    for line_number, row in enumerate(reader, start=2):
        on = _strict_date(row["date"], field=f"snapshot line {line_number}")
        if on in seen_dates:
            raise MembershipAuditError(f"duplicate snapshot date {on}")
        seen_dates.add(on)
        raw_members = [value for value in str(row["tickers"] or "").split(",") if value]
        members: list[str] = []
        for raw in raw_members:
            symbol = normalize_symbol(raw)
            raw_by_normalized.setdefault(symbol, set()).add(raw)
            members.append(symbol)
        if len(members) != len(set(members)):
            raise MembershipAuditError(f"snapshot line {line_number}: duplicate normalized symbol")
        snapshots.append(Snapshot(on, frozenset(members)))
    snapshots.sort(key=lambda item: item.on)
    collisions = {
        symbol: sorted(raws)
        for symbol, raws in raw_by_normalized.items()
        if len(raws) > 1
    }
    if collisions:
        raise MembershipAuditError(f"snapshot normalization collisions: {collisions}")
    return snapshots, {
        "rows": len(snapshots),
        "unique_symbols": len(raw_by_normalized),
        "date_min": snapshots[0].on.isoformat(),
        "date_max": snapshots[-1].on.isoformat(),
        "normalization_collisions": 0,
        "duplicate_dates": 0,
    }


def _members_from_intervals(
    intervals: Iterable[Interval], on: date, *, inclusive_end: bool
) -> frozenset[str]:
    result = set()
    for item in intervals:
        end_ok = item.end is None or (item.end >= on if inclusive_end else item.end > on)
        if item.start <= on and end_ok:
            result.add(item.symbol)
    return frozenset(result)


def _latest_snapshot(snapshots: list[Snapshot], on: date) -> Snapshot | None:
    if not snapshots or on < snapshots[0].on or on > snapshots[-1].on:
        return None
    chosen = None
    for item in snapshots:
        if item.on > on:
            break
        chosen = item
    return chosen


def member_digest(members: Iterable[str]) -> str:
    material = ",".join(sorted(set(members))).encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def _set_diff(left: frozenset[str], right: frozenset[str]) -> tuple[int, list[str]]:
    values = sorted(left - right)
    return len(values), values[:10]


def compare_date(
    intervals: list[Interval], snapshots: list[Snapshot], on: date
) -> dict:
    source = _latest_snapshot(snapshots, on)
    if source is None:
        return {"date": on.isoformat(), "covered": False}
    exclusive = _members_from_intervals(intervals, on, inclusive_end=False)
    inclusive = _members_from_intervals(intervals, on, inclusive_end=True)
    ex_extra_n, ex_extra = _set_diff(exclusive, source.members)
    ex_missing_n, ex_missing = _set_diff(source.members, exclusive)
    in_extra_n, in_extra = _set_diff(inclusive, source.members)
    in_missing_n, in_missing = _set_diff(source.members, inclusive)
    return {
        "date": on.isoformat(),
        "covered": True,
        "snapshot_date": source.on.isoformat(),
        "snapshot_count": len(source.members),
        "exclusive": {
            "count": len(exclusive),
            "extra": ex_extra_n,
            "missing": ex_missing_n,
            "extra_sample": ex_extra,
            "missing_sample": ex_missing,
            "member_sha256": member_digest(exclusive),
        },
        "inclusive": {
            "count": len(inclusive),
            "extra": in_extra_n,
            "missing": in_missing_n,
            "extra_sample": in_extra,
            "missing_sample": in_missing,
            "member_sha256": member_digest(inclusive),
        },
        "snapshot_member_sha256": member_digest(source.members),
    }


def audit(interval_body: bytes, snapshot_body: bytes) -> dict:
    intervals, interval_stats = load_intervals(interval_body)
    snapshots, snapshot_stats = load_snapshots(snapshot_body)
    quarter_ends = [compare_date(intervals, snapshots, on) for on in QUARTER_ENDS]
    boundaries = [
        compare_date(intervals, snapshots, snapshots[0].on),
        compare_date(intervals, snapshots, snapshots[-1].on),
    ]
    return {
        "schema": "market_experience.f0_membership_source_audit.v1",
        "status": "source_representation_checks_passed",
        "source": {
            "repository": UPSTREAM_REPOSITORY,
            "commit": UPSTREAM_COMMIT,
            "interval": {
                "path": INTERVAL_PATH,
                "git_blob": INTERVAL_GIT_BLOB,
                "bytes": INTERVAL_BYTES,
            },
            "snapshot": {
                "path": SNAPSHOT_PATH,
                "git_blob": SNAPSHOT_GIT_BLOB,
                "bytes": SNAPSHOT_BYTES,
            },
            "license_git_blob": LICENSE_GIT_BLOB,
            "readme_git_blob": README_GIT_BLOB,
        },
        "interval_stats": interval_stats,
        "snapshot_stats": snapshot_stats,
        "quarter_end": {
            "requested": len(quarter_ends),
            "covered": sum(item["covered"] for item in quarter_ends),
            "exclusive_exact": sum(
                item.get("covered", False)
                and item["exclusive"]["extra"] == 0
                and item["exclusive"]["missing"] == 0
                for item in quarter_ends
            ),
            "inclusive_exact": sum(
                item.get("covered", False)
                and item["inclusive"]["extra"] == 0
                and item["inclusive"]["missing"] == 0
                for item in quarter_ends
            ),
            "comparisons": quarter_ends,
        },
        "coverage_boundaries": boundaries,
        "rights": {
            "repository_license": "MIT_FILE_PRESENT",
            "underlying_index_data_rights": "UNKNOWN",
            "training_eligible": False,
            "redistribution_eligible": False,
            "use": "internal_source_qualification_only",
        },
        "authority": {
            "stock_pilot_admitted": False,
            "production_data_admitted": False,
            "forecast_trial": False,
            "promotion_eligible": False,
        },
    }


def _read_bounded(path: Path, *, expected_bytes: int) -> bytes:
    body = path.read_bytes()
    if len(body) != expected_bytes:
        raise MembershipAuditError(
            f"{path}: expected {expected_bytes} bytes, got {len(body)}"
        )
    return body


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--interval", type=Path, required=True)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    receipt = audit(
        _read_bounded(args.interval, expected_bytes=INTERVAL_BYTES),
        _read_bounded(args.snapshot, expected_bytes=SNAPSHOT_BYTES),
    )
    text = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

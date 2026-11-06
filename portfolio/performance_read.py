"""Bounded, non-recovering persisted inputs for the existing performance owner.

This consumer never acquires a transaction lock, creates an account, repairs a
ledger, or reads transaction contents. File observation is not an account clock.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

MAX_BYTES = 16_000_000
MAX_ROWS = 8192
# Cached benchmark observation bound; approximately two trading years.
MAX_BENCHMARK_ROWS = 504


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def _invalid_constant(_value):
    raise ValueError("non-finite JSON number")


def _decode(raw):
    return json.loads(raw, object_pairs_hook=_unique_pairs, parse_constant=_invalid_constant)


def _signature(path: Path):
    try:
        stat = path.stat()
        return ("present", stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns)
    except FileNotFoundError:
        return ("missing",)
    except OSError:
        return ("unavailable",)


def _read(path: Path):
    try:
        with path.open("rb") as stream:
            raw = stream.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            return None, {"file": path.name, "status": "invalid", "issue": "source_too_large"}
        return raw, {"file": path.name, "status": "available",
                     "sha256": hashlib.sha256(raw).hexdigest()}
    except FileNotFoundError:
        return None, {"file": path.name, "status": "missing"}
    except OSError:
        return None, {"file": path.name, "status": "unavailable"}


def _bound(row: dict, portfolio_id: str, currency: str | None = None) -> bool:
    book_matches = all(key not in row or row[key] == portfolio_id
                       for key in ("portfolio_id", "book"))
    return book_matches and (currency is None or "currency" not in row
                             or row["currency"] == currency)


def _metadata_agrees(row: dict, state: dict | None) -> bool:
    """Reject explicit cross-source contradictions; absent episode identity stays unverified."""
    if state is None:
        return True
    for key in ("inception_date", "starting_nav", "episode_id", "account_id"):
        if key not in state or key not in row:
            continue
        left, right = state[key], row[key]
        if key == "starting_nav":
            if any(isinstance(value, bool) or not isinstance(value, (int, float))
                   for value in (left, right)) or left != right:
                return False
        elif type(left) is not type(right) or left != right:
            return False
    return True


def read_performance_sources(paths: dict[str, Path], portfolio_id: str,
                             *, currency: str | None = None) -> dict[str, Any]:
    """Read an explicitly resolved book; preserve missing, invalid and partial states."""
    files = {"account": Path(paths["account"]), "history": Path(paths["nav"]),
             "transaction": Path(paths["data"]) / "paper_transaction.json"}
    before = {key: _signature(path) for key, path in files.items()}
    sources = {}
    issues = []
    raw, sources["account"] = _read(files["account"])
    state = None
    if raw is not None:
        try:
            state = _decode(raw)
            if not isinstance(state, dict) or not _bound(state, portfolio_id, currency):
                raise ValueError("account shape or binding")
        except (ValueError, TypeError, UnicodeError, RecursionError):
            state = None
            sources["account"].update(status="invalid", issue="account_invalid_or_foreign")

    raw, sources["history"] = _read(files["history"])
    rows = []
    if raw is not None:
        try:
            lines = raw.decode("utf-8").splitlines()
        except UnicodeError:
            lines = []
            sources["history"].update(status="invalid", issue="history_encoding_invalid")
        if len(lines) > MAX_ROWS:
            lines = lines[-MAX_ROWS:]
            sources["history"].update(status="partial", issue="history_truncated")
        for line in lines:
            if not line.strip():
                continue
            try:
                row = _decode(line)
                if not isinstance(row, dict) or not _bound(row, portfolio_id, currency):
                    raise ValueError("history shape or binding")
                if not _metadata_agrees(row, state):
                    sources["history"].update(status="partial", issue="history_account_metadata_conflict")
                    continue
                rows.append(row)
            except (ValueError, TypeError, RecursionError):
                sources["history"].update(status="partial", issue="history_row_invalid_or_foreign")

    after = {key: _signature(path) for key, path in files.items()}
    changed = before != after
    transaction_state = after["transaction"][0]
    sources["transaction"] = {"file": files["transaction"].name,
                              "status": transaction_state, "contents_read": False}
    if changed:
        issues.append("source_changed_during_read")
    if transaction_state == "unavailable":
        issues.append("transaction_presence_unavailable")
    for source in sources.values():
        if source.get("issue"):
            issues.append(source["issue"])
    # Unknown consistency must never be represented as a recovered/settled account.
    return {
        "state": state, "rows": rows,
        "account_status": sources["account"]["status"],
        "history_status": sources["history"]["status"],
        "transaction_pending": transaction_state != "missing" or changed,
        "consistency": "changed" if changed else (
            "unavailable" if transaction_state == "unavailable" else "observed_stable"),
        "sources": sources, "issues": sorted(set(issues)),
    }

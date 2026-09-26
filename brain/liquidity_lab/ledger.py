"""Append-only keep-first ledgers for W-LIQ.3 research evidence."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Mapping

from brain.liquidity_lab.contracts import (
    ContractError,
    ForecastGrade,
    ForwardForecast,
    ShockRecord,
    _snapshot_hash,
    _utc_timestamp,
    canonical_hash,
)


class LedgerCorruptionError(RuntimeError):
    """Raised when append-only history cannot be parsed without dropping rows."""


class KeepFirstConflict(RuntimeError):
    """Raised when an immutable identity is reused with different content."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _canonical(payload: Mapping[str, Any]) -> str:
    try:
        return json.dumps(
            dict(payload), sort_keys=True, separators=(",", ":"), allow_nan=False
        )
    except (TypeError, ValueError) as exc:
        raise ContractError("ledger payload must be canonical-JSON serializable") from exc


def _parse_rows(text: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, raw in enumerate(text.splitlines(), start=1):
        if not raw.strip():
            continue
        try:
            row = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise LedgerCorruptionError(f"invalid JSONL at line {line_number}") from exc
        if not isinstance(row, dict):
            raise LedgerCorruptionError(f"ledger row {line_number} is not an object")
        rows.append(row)
    return rows


class _AppendOnlyStore:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)

    @contextmanager
    def _locked(self) -> Iterator[tuple[Any, list[dict[str, Any]]]]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a+", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                handle.seek(0)
                rows = _parse_rows(handle.read())
                yield handle, rows
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    @staticmethod
    def _append(handle: Any, row: Mapping[str, Any]) -> None:
        handle.seek(0, os.SEEK_END)
        handle.write(_canonical(row) + "\n")
        handle.flush()
        os.fsync(handle.fileno())

    def rows(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        with self.path.open("r", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_SH)
            try:
                return _parse_rows(handle.read())
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


class ShockRegistry(_AppendOnlyStore):
    """Immutable shocks plus append-only amendments.

    ``record`` returns ``created`` or ``duplicate``.  Reusing a ``shock_id``
    with different first-detection evidence fails closed; corrections must use
    ``amend`` and leave the original row byte-addressable.
    """

    def record(self, shock: ShockRecord) -> str:
        payload = shock.to_dict()
        with self._locked() as (handle, rows):
            matches = [
                row for row in rows if row.get("kind") == "shock" and row.get("shock_id") == shock.shock_id
            ]
            if matches:
                original = matches[0].get("payload")
                if original == payload:
                    return "duplicate"
                raise KeepFirstConflict(f"shock_id collision: {shock.shock_id}")
            self._append(
                handle,
                {
                    "kind": "shock",
                    "shock_id": shock.shock_id,
                    "registered_at": _now_iso(),
                    "payload_hash": canonical_hash(payload),
                    "payload": payload,
                },
            )
        return "created"

    def amend(
        self,
        shock_id: str,
        *,
        amended_at: datetime,
        reason: str,
        replacement_fields: Mapping[str, Any],
        source_snapshot_hash: str,
    ) -> str:
        reason = str(reason or "").strip()
        if not reason:
            raise ContractError("amendment reason is required")
        if not isinstance(replacement_fields, Mapping) or not replacement_fields:
            raise ContractError("replacement_fields must be a non-empty object")
        amended = _utc_timestamp("amended_at", amended_at)
        amended_iso = amended.isoformat().replace("+00:00", "Z")
        source_snapshot_hash = _snapshot_hash(source_snapshot_hash)
        amendment_payload = {
            "shock_id": shock_id,
            "amended_at": amended_iso,
            "reason": reason,
            "replacement_fields": dict(replacement_fields),
            "source_snapshot_hash": source_snapshot_hash,
        }
        amendment_id = "sha_" + hashlib.sha256(
            _canonical(amendment_payload).encode("utf-8")
        ).hexdigest()[:20]
        with self._locked() as (handle, rows):
            shock_row = next(
                (
                    row
                    for row in rows
                    if row.get("kind") == "shock" and row.get("shock_id") == shock_id
                ),
                None,
            )
            if shock_row is None:
                raise ContractError(f"cannot amend unknown shock_id: {shock_id}")
            first_detected = _utc_timestamp(
                "first_detected", shock_row.get("payload", {}).get("first_detected")
            )
            if amended < first_detected:
                raise ContractError("amended_at may not precede first_detected")
            matches = [row for row in rows if row.get("amendment_id") == amendment_id]
            if matches:
                return "duplicate"
            self._append(
                handle,
                {
                    "kind": "shock_amendment",
                    "shock_id": shock_id,
                    "amendment_id": amendment_id,
                    "registered_at": _now_iso(),
                    "payload_hash": canonical_hash(amendment_payload),
                    "payload": amendment_payload,
                },
            )
        return "created"

    def shocks(self) -> list[dict[str, Any]]:
        return [row["payload"] for row in self.rows() if row.get("kind") == "shock"]

    def amendments(self, shock_id: str | None = None) -> list[dict[str, Any]]:
        rows = [row for row in self.rows() if row.get("kind") == "shock_amendment"]
        if shock_id is not None:
            rows = [row for row in rows if row.get("shock_id") == shock_id]
        return [row["payload"] for row in rows]


class ForwardLedger(_AppendOnlyStore):
    """Keep-first forecast rows and keep-first realized grades."""

    def record(self, forecast: ForwardForecast) -> str:
        payload = forecast.to_dict()
        key = forecast.forecast_key
        with self._locked() as (handle, rows):
            matches = [
                row for row in rows if row.get("kind") == "forecast" and row.get("forecast_key") == key
            ]
            if matches:
                if matches[0].get("payload") == payload:
                    return "duplicate"
                raise KeepFirstConflict(f"forecast_key collision: {key}")
            self._append(
                handle,
                {
                    "kind": "forecast",
                    "forecast_key": key,
                    "registered_at": _now_iso(),
                    "payload_hash": canonical_hash(payload),
                    "payload": payload,
                },
            )
        return "created"

    def grade(self, grade: ForecastGrade) -> str:
        payload = grade.to_dict()
        key = grade.forecast_key
        with self._locked() as (handle, rows):
            forecast_row = next(
                (
                    row
                    for row in rows
                    if row.get("kind") == "forecast" and row.get("forecast_key") == key
                ),
                None,
            )
            if forecast_row is None:
                raise ContractError(f"cannot grade unknown forecast_key: {key}")
            predicted_at = _utc_timestamp(
                "predicted_at", forecast_row.get("payload", {}).get("predicted_at")
            )
            if grade.resolved_at < predicted_at:
                raise ContractError("resolved_at may not precede predicted_at")
            matches = [
                row for row in rows if row.get("kind") == "forecast_grade" and row.get("forecast_key") == key
            ]
            if matches:
                if matches[0].get("payload") == payload:
                    return "duplicate"
                raise KeepFirstConflict(f"forecast grade collision: {key}")
            self._append(
                handle,
                {
                    "kind": "forecast_grade",
                    "forecast_key": key,
                    "registered_at": _now_iso(),
                    "payload_hash": canonical_hash(payload),
                    "payload": payload,
                },
            )
        return "created"

    def forecasts(self) -> list[dict[str, Any]]:
        return [row["payload"] for row in self.rows() if row.get("kind") == "forecast"]

    def grades(self) -> list[dict[str, Any]]:
        return [row["payload"] for row in self.rows() if row.get("kind") == "forecast_grade"]

"""portfolio.decision_snapshot_sources — fixed, clock-honest V3 Decision Snapshot capture.

Bounded, read-only capture of the fixed internal Portfolio book state and the fixed
external Macro context artifacts consumed by the S0 Decision Snapshot. No persistence,
no model/provider/network access, and no caller-supplied path/root/url ever reaches a
filesystem expression — every source is a closed, checked-in literal path or a contract
key resolved through ``control_plane.contracts.contract``.

Two distinct clock laws (Task 2 controller ruling):
  * Internal, first-party canonical Portfolio files may use a *stable* file mtime as
    market-relevant ``known_at`` — proven by a dual-fstat stable read — labeled
    ``clock_basis=FILE_MTIME_FIRST_PARTY_STATE``. ``recorded_at`` (the caller's collector
    observation clock) is echoed onto every receipt as ``observed_at`` regardless.
  * External Macro filesystem mtime is NEVER promoted to market ``known_at``. It is
    recorded only as ``filesystem_observed_at``. A qualified ``known_at`` exists only when
    one of the source's own declared clock fields is present, in which case
    ``clock_basis=DECLARED_SOURCE_FIELD``; otherwise ``known_at=None``,
    ``clock_basis=UNQUALIFIED_EXTERNAL_CLOCK``, ``status=UNQUALIFIED_CLOCK``.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from portfolio import decision_snapshot_contracts as c
from portfolio import registry

_ROOT = Path(__file__).resolve().parent.parent
_V = _ROOT / "vendor" / "macro"

MAX_SOURCE_BYTES = c.MAX_SOURCE_BYTES
MAX_JSONL_TAIL_ROWS = c.MAX_JSONL_TAIL_ROWS
MAX_SECTION_ROWS = c.MAX_SECTION_ROWS

_EMPTY_DIGEST = "sha256:" + hashlib.sha256(b"").hexdigest()

_CORRECTION_DECLARED_FIELDS = ("revision", "bundle_id", "content_generation")


@dataclass(frozen=True)
class SourceSpec:
    source_id: str
    contract_key: str
    domains: tuple[str, ...]
    required: bool
    authority_class: str
    rights_class: str
    projection: str
    known_at_fields: tuple[str, ...] = ()
    observed_at_fields: tuple[str, ...] = ()
    as_of_fields: tuple[str, ...] = ()
    generated_at_fields: tuple[str, ...] = ()
    schema_fields: tuple[str, ...] = ("schema",)
    definition_fields: tuple[str, ...] = ("definition_id",)


EXTERNAL_SOURCE_SPECS: tuple[SourceSpec, ...] = (
    SourceSpec(
        "macro.risk_envelope",
        "portfolio-v3-risk-envelope-settled",
        ("risk_truth",),
        True,
        "MARKET_RISK_CONTEXT",
        "FIRST_PARTY_INTERNAL",
        "risk_envelope",
        known_at_fields=("known_at", "available_at", "generated_at"),
        as_of_fields=("as_of", "asof"),
        generated_at_fields=("generated_at", "produced_at"),
    ),
    SourceSpec(
        "macro.regime",
        "regime-latest",
        ("market_structure",),
        False,
        "CONTEXT_ONLY",
        "FIRST_PARTY_INTERNAL",
        "regime",
        known_at_fields=("known_at", "available_at", "generated_at"),
        as_of_fields=("as_of", "asof", "date"),
        generated_at_fields=("generated_at", "produced_at"),
    ),
    SourceSpec(
        "macro.sector_rotation",
        "portfolio-v3-sector-central",
        ("market_structure",),
        False,
        "CONTEXT_ONLY",
        "FIRST_PARTY_INTERNAL",
        "receipt_only_pr548",
        as_of_fields=("as_of",),
    ),
    SourceSpec(
        "macro.r_orth",
        "portfolio-v3-covariance-spine",
        ("independence",),
        False,
        "CONTEXT_ONLY",
        "FIRST_PARTY_INTERNAL",
        "covariance_spine",
        known_at_fields=("known_at", "generated_at"),
        as_of_fields=("as_of",),
        generated_at_fields=("generated_at",),
    ),
    SourceSpec(
        "macro.factor_betas",
        "portfolio-v3-factor-betas",
        ("factor_risk",),
        False,
        "MEASUREMENT_ONLY",
        "FIRST_PARTY_INTERNAL",
        "factor_betas",
        known_at_fields=("known_at", "generated_at"),
        as_of_fields=("as_of", "asof"),
        generated_at_fields=("generated_at",),
    ),
    SourceSpec(
        "macro.prophet",
        "portfolio-v3-prophet-index",
        ("candidate_geometry",),
        False,
        "DISPLAY_ONLY",
        "FIRST_PARTY_INTERNAL",
        "prophet",
        known_at_fields=("known_at", "generated_at"),
        as_of_fields=("as_of", "asof"),
        generated_at_fields=("generated_at",),
    ),
    SourceSpec(
        "macro.neural_web",
        "site-neural-web-mastermind-context",
        ("relationships",),
        False,
        "CONTEXT_ONLY",
        "FIRST_PARTY_INTERNAL",
        "neural_web",
        known_at_fields=("known_at", "generated_at"),
        as_of_fields=("as_of",),
        generated_at_fields=("generated_at",),
    ),
    SourceSpec(
        "macro.portfolio_context",
        "portfolio-v3-portfolio-context",
        ("fundamental_state", "positioning", "event_state", "priceability"),
        False,
        "CONTEXT_ONLY",
        "FIRST_PARTY_INTERNAL",
        "portfolio_context",
        known_at_fields=("known_at", "generated_at"),
        as_of_fields=("as_of", "asof"),
        generated_at_fields=("generated_at",),
    ),
    SourceSpec(
        "macro.intelligence",
        "site-intelligence-by-ticker",
        ("fundamental_state", "positioning", "event_state"),
        False,
        "CONTEXT_ONLY",
        "FIRST_PARTY_INTERNAL",
        "held_ticker_bundle",
        known_at_fields=("known_at", "generated_at"),
        as_of_fields=("as_of", "asof"),
        generated_at_fields=("generated_at",),
    ),
    SourceSpec(
        "macro.altdata",
        "site-altdata-by-ticker",
        ("positioning",),
        False,
        "CONTEXT_ONLY",
        "FIRST_PARTY_INTERNAL",
        "held_ticker_bundle",
        known_at_fields=("known_at", "generated_at"),
        as_of_fields=("as_of", "asof"),
        generated_at_fields=("generated_at",),
    ),
    SourceSpec(
        "macro.news",
        "site-news-by-ticker",
        ("event_state",),
        False,
        "CONTEXT_ONLY",
        "FIRST_PARTY_INTERNAL",
        "held_ticker_bundle",
        known_at_fields=("known_at", "generated_at"),
        as_of_fields=("as_of", "asof"),
        generated_at_fields=("generated_at",),
    ),
)

# Fixed internal book-state files, relative to the book's data directory.
# (source_id, relative_path, required, section_id, projection)
_INTERNAL_FILE_SPECS: tuple[tuple[str, str, bool, str, str], ...] = (
    ("book.account", "account.json", True, "book_truth", "account"),
    ("book.latest", "latest.json", False, "book_truth", "latest"),
    ("book.pending_orders", "pending_orders.json", False, "book_truth", "raw_object"),
    ("book.pending_target", "pending_target.json", False, "book_truth", "raw_object"),
    ("book.positions_ledger", "positions_ledger.json", False, "historical_memory", "raw_object"),
)
_INTERNAL_JSONL_SPECS: tuple[tuple[str, str, str], ...] = (
    ("book.decisions", "decisions.jsonl", "historical_memory"),
    ("book.fills", "fills.jsonl", "historical_memory"),
)
_SETTLEMENT_RECEIPTS_SOURCE_ID = "book.settlement_receipts"
_SETTLEMENT_RECEIPTS_DIR = "settlement_receipts"


# ---------------------------------------------------------------------------
# Digests, clocks, gaps
# ---------------------------------------------------------------------------

def _digest(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _utc_from_epoch_seconds(seconds: float) -> str:
    return datetime.fromtimestamp(int(seconds), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _canonical_or_none(value: Any) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return c.parse_utc_timestamp(value, field="declared_clock")
    except c.DecisionSnapshotContractError:
        return None


def _first_declared(payload: Any, fields: tuple[str, ...]) -> str | None:
    if not isinstance(payload, Mapping):
        return None
    for name in fields:
        normalized = _canonical_or_none(payload.get(name))
        if normalized is not None:
            return normalized
    return None


def _first_present_str(payload: Any, fields: tuple[str, ...]) -> str | None:
    if not isinstance(payload, Mapping):
        return None
    for name in fields:
        value = payload.get(name)
        if isinstance(value, str) and value:
            return value
    return None


def _is_usable_declared_generation_value(value: Any) -> bool:
    """True for a scalar the declared-generation rule may hash: a non-empty, printable
    string, an int, or a finite float. Booleans, empty/control-bearing strings, non-finite
    floats, mappings, and sequences are all rejected."""
    if isinstance(value, bool):
        return False
    if isinstance(value, str):
        return bool(value) and value.isprintable()
    if isinstance(value, int):
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    return False


def _correction_generation(payload: Any, digest: str) -> str:
    """Digest-shaped correction generation. When the source declares a usable scalar
    ``revision``/``bundle_id``/``content_generation``, hash the declared field/value together
    with the current ``artifact_digest`` — so a content change always changes the generation
    even under an unchanged declared revision. Otherwise fall back to the artifact digest."""
    if isinstance(payload, Mapping):
        for name in _CORRECTION_DECLARED_FIELDS:
            if name not in payload:
                continue
            value = payload[name]
            if not _is_usable_declared_generation_value(value):
                continue
            return c.content_digest({
                "declared_field": name,
                "declared_value": value,
                "artifact_digest": digest,
            })
    return digest


def _gap(
    code: str,
    *,
    source_id: str | None = None,
    section_id: str | None = None,
    owner: str | None = None,
    detail: str | None = None,
) -> dict[str, Any]:
    return {
        "code": code,
        "source_id": source_id,
        "section_id": section_id,
        "owner": owner,
        "detail": detail,
    }


# ---------------------------------------------------------------------------
# Receipt scaffold
# ---------------------------------------------------------------------------

def _base_receipt(
    *,
    source_id: str,
    domains: Sequence[str],
    producer: str,
    owner: str,
    artifact: str,
    rights_class: str,
    authority_class: str,
    required: bool,
    observed_at: str,
) -> dict[str, Any]:
    return {
        "schema": c.SOURCE_RECEIPT_SCHEMA,
        "source_id": source_id,
        "domains": list(domains),
        "producer": producer,
        "owner": owner,
        "artifact": artifact,
        "source_schema": None,
        "schema_version": None,
        "definition_id": None,
        "artifact_digest": _EMPTY_DIGEST,
        "observed_at": observed_at,
        "known_at": None,
        "as_of": None,
        "generated_at": None,
        "filesystem_observed_at": None,
        "correction_generation": _EMPTY_DIGEST,
        "freshness_state": "UNKNOWN",
        "coverage_state": "UNKNOWN",
        "rights_class": rights_class,
        "authority_class": authority_class,
        "status": "MISSING",
        "required": required,
        "bytes": 0,
        "rows_total": 0,
        "rows_returned": 0,
        "omitted_rows": 0,
        "clock_basis": "UNKNOWN",
        "error_code": None,
    }


def _section(section_id: str, source_ids: Sequence[str]) -> dict[str, Any]:
    return {
        "schema": c.SECTION_SCHEMA,
        "section_id": section_id,
        "coverage_state": "COMPLETE",
        "source_ids": list(source_ids),
        "rows_total": 0,
        "rows_returned": 0,
        "omitted_rows": 0,
        "rows": [],
        "gaps": [],
    }


_COVERAGE_RANK = {"BLOCKED": 3, "PARTIAL": 2, "UNKNOWN": 1, "COMPLETE": 0}


def _worse_coverage(a: str, b: str) -> str:
    return a if _COVERAGE_RANK[a] >= _COVERAGE_RANK[b] else b


def _append_capped(section: dict[str, Any], rows: list[Any]) -> int:
    """Append ``rows`` to ``section["rows"]``, capping at ``MAX_SECTION_ROWS``.

    Returns the number of rows dropped by the cap so the caller can fold that count into
    ``omitted_rows`` — a cap drop must never vanish from coverage.
    """
    combined = section["rows"] + rows
    kept = combined[:MAX_SECTION_ROWS]
    section["rows"] = kept
    return len(combined) - len(kept)


def _merge_into_section(section: dict[str, Any], *, rows: list[Any], coverage_state: str,
                         omitted_rows: int, gaps: list[dict[str, Any]]) -> None:
    """Fold one source's contribution into a section, keeping counts self-consistent.

    ``rows_returned`` and ``rows_total`` are always derived from the section's own row list
    and cumulative omissions — never independently summed — so a section can never carry
    rows its counts deny, or drop rows its counts never report.
    """
    cap_dropped = _append_capped(section, rows)
    section["coverage_state"] = _worse_coverage(section["coverage_state"], coverage_state)
    section["omitted_rows"] += omitted_rows + cap_dropped
    section["rows_returned"] = len(section["rows"])
    section["rows_total"] = section["rows_returned"] + section["omitted_rows"]
    section["gaps"].extend(gaps)


# ---------------------------------------------------------------------------
# Bounded fixed-path readers
# ---------------------------------------------------------------------------

def _read_json_bytes(path: Path) -> tuple[bytes | None, int, str | None]:
    """Non-stable bounded read for external (Macro) artifacts. Returns (raw, size, error_code)."""
    try:
        size = path.stat().st_size
    except FileNotFoundError:
        return None, 0, "MISSING"
    except OSError:
        return None, 0, "INVALID"
    if size > MAX_SOURCE_BYTES:
        return None, size, "OVERSIZE"
    try:
        raw = path.read_bytes()
    except OSError:
        return None, size, "INVALID"
    return raw, size, None


def _stable_first_party_read(path: Path) -> tuple[bytes | None, Any | None, int, str | None]:
    """Dual-fstat stable read for internal, first-party canonical Portfolio files.

    Returns (raw, stat_after, size, error_code). A device/inode/size/mtime_ns mismatch
    between the pre- and post-read fstat means the file changed during the read; no rows
    are ever produced from an unstable read.
    """
    try:
        fd = os.open(str(path), os.O_RDONLY)
    except FileNotFoundError:
        return None, None, 0, "MISSING"
    except OSError:
        return None, None, 0, "INVALID"
    try:
        pre = os.fstat(fd)
        size = pre.st_size
        if size > MAX_SOURCE_BYTES:
            return None, pre, size, "OVERSIZE"
        try:
            raw = os.read(fd, size)
        except OSError:
            return None, pre, size, "INVALID"
        post = os.fstat(fd)
        stable = (
            pre.st_dev == post.st_dev
            and pre.st_ino == post.st_ino
            and pre.st_size == post.st_size
            and pre.st_mtime_ns == post.st_mtime_ns
        )
        if not stable:
            return None, post, size, "SOURCE_CHANGED_DURING_READ"
        return raw, post, size, None
    finally:
        os.close(fd)


def _parse_json(raw: bytes) -> tuple[Any | None, str | None]:
    try:
        return json.loads(raw.decode("utf-8")), None
    except UnicodeDecodeError:
        return None, "MALFORMED"
    except json.JSONDecodeError:
        return None, "MALFORMED"


def _parse_jsonl_tail(raw: bytes, *, max_rows: int = MAX_JSONL_TAIL_ROWS) -> dict[str, Any]:
    """Parse a bounded JSONL tail from bytes already produced by a single stable read.

    Never re-reads or re-stats the source: rows, the caller's digest, and the caller's
    file-write clock must all describe the exact same bytes. Invalid lines increment
    ``omitted_rows`` rather than vanishing from coverage.
    """
    text = raw.decode("utf-8", errors="replace")
    valid: list[Any] = []
    omitted = 0
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            omitted += 1
            continue
        if not isinstance(obj, dict):
            omitted += 1
            continue
        valid.append(obj)
    tail = valid[-max_rows:] if max_rows else []
    return {
        "rows": tail,
        "rows_total": len(valid) + omitted,
        "rows_returned": len(tail),
        "omitted_rows": omitted + (len(valid) - len(tail)),
    }


# ---------------------------------------------------------------------------
# Internal book-state capture
# ---------------------------------------------------------------------------

def _book_dir(book: str) -> Path:
    """The book's data directory, remapped under this module's own (test-patchable) root.

    ``registry.data_dir`` remains the single source of truth for the book-id allowlist and
    the canonical relative layout; it fails closed (``ValueError``) on an unknown id. This
    module never reads through the absolute path it returns — it strips the real repo root
    registry.py resolves against and re-anchors the same relative subpath under its own
    module-owned ``_ROOT``, which is what tests are allowed to redirect.
    """
    canonical_absolute = registry.data_dir(book)
    registry_root_now = Path(getattr(registry, "_ROOT", _ROOT))
    relative = canonical_absolute.relative_to(registry_root_now)
    return _ROOT / relative


def _project_account(payload: Any) -> dict[str, Any] | None:
    if not isinstance(payload, Mapping):
        return None
    row: dict[str, Any] = {}
    if "cash" in payload:
        row["cash"] = payload.get("cash")
    if "starting_nav" in payload:
        row["starting_nav"] = payload.get("starting_nav")
    positions = payload.get("positions")
    if isinstance(positions, Mapping):
        projected_positions: dict[str, Any] = {}
        for ticker, pos in positions.items():
            if not isinstance(pos, Mapping):
                continue
            projected_positions[ticker] = {
                field: pos[field]
                for field in ("shares", "avg_cost", "identity_status", "holding_mark_source", "weight")
                if field in pos
            }
        row["positions"] = projected_positions
    return row


def _project_latest(payload: Any) -> dict[str, Any] | None:
    if not isinstance(payload, Mapping):
        return None
    row: dict[str, Any] = {}
    if "as_of" in payload:
        row["as_of"] = payload.get("as_of")
    positions = payload.get("positions")
    if isinstance(positions, list):
        row["positions"] = [
            {
                field: pos[field]
                for field in ("ticker", "weight", "identity_status", "holding_mark_source")
                if field in pos
            }
            for pos in positions
            if isinstance(pos, Mapping)
        ]
    return row


def capture_book_state(book: str, *, decision_cutoff: str, recorded_at: str) -> dict[str, Any]:
    observed_at = c.parse_utc_timestamp(recorded_at, field="recorded_at")
    c.parse_utc_timestamp(decision_cutoff, field="decision_cutoff")
    book_dir = _book_dir(book)

    sources_out: list[dict[str, Any]] = []
    gaps_out: list[dict[str, Any]] = []
    sections: dict[str, dict[str, Any]] = {
        "book_truth": _section("book_truth", []),
        "historical_memory": _section("historical_memory", []),
    }

    def emit(section_id: str, source_id: str) -> None:
        sections[section_id]["source_ids"].append(source_id)

    for source_id, rel_path, required, section_id, projection in _INTERNAL_FILE_SPECS:
        path = book_dir / rel_path
        receipt = _base_receipt(
            source_id=source_id,
            domains=(section_id,),
            producer="mastermind_portfolio",
            owner="portfolio_desk",
            artifact=f"data/portfolios/{book}/{rel_path}",
            rights_class="FIRST_PARTY_INTERNAL",
            authority_class="BOOK_STATE",
            required=required,
            observed_at=observed_at,
        )
        raw, stat_after, size, error_code = _stable_first_party_read(path)
        receipt["bytes"] = size
        emit(section_id, source_id)

        if error_code == "MISSING":
            receipt["status"] = "ABSENT_OPTIONAL" if not required else "MISSING"
            receipt["coverage_state"] = "COMPLETE" if not required else "PARTIAL"
            if required:
                gaps_out.append(_gap("MISSING_REQUIRED_INTERNAL_SOURCE", source_id=source_id,
                                      section_id=section_id))
                _merge_into_section(sections[section_id], rows=[], coverage_state="BLOCKED",
                                     omitted_rows=0, gaps=[])
            sources_out.append(receipt)
            continue

        if error_code in ("OVERSIZE", "INVALID", "SOURCE_CHANGED_DURING_READ"):
            receipt["status"] = "INVALID" if error_code == "SOURCE_CHANGED_DURING_READ" else error_code
            receipt["error_code"] = error_code
            receipt["coverage_state"] = "BLOCKED"
            if stat_after is not None:
                receipt["filesystem_observed_at"] = _utc_from_epoch_seconds(stat_after.st_mtime_ns / 1e9)
            gaps_out.append(_gap(error_code, source_id=source_id, section_id=section_id))
            _merge_into_section(sections[section_id], rows=[], coverage_state="BLOCKED",
                                 omitted_rows=0,
                                 gaps=[_gap(error_code, source_id=source_id, section_id=section_id)])
            sources_out.append(receipt)
            continue

        # Stable read succeeded.
        mtime_utc = _utc_from_epoch_seconds(stat_after.st_mtime_ns / 1e9)
        receipt["known_at"] = mtime_utc
        receipt["filesystem_observed_at"] = mtime_utc
        receipt["clock_basis"] = "FILE_MTIME_FIRST_PARTY_STATE"
        receipt["artifact_digest"] = _digest(raw)

        payload, parse_error = _parse_json(raw)
        if parse_error:
            receipt["status"] = "MALFORMED"
            receipt["error_code"] = parse_error
            receipt["coverage_state"] = "PARTIAL" if not required else "BLOCKED"
            gaps_out.append(_gap(parse_error, source_id=source_id, section_id=section_id))
            _merge_into_section(sections[section_id], rows=[], coverage_state=receipt["coverage_state"],
                                 omitted_rows=0,
                                 gaps=[_gap(parse_error, source_id=source_id, section_id=section_id)])
            sources_out.append(receipt)
            continue

        receipt["correction_generation"] = _correction_generation(payload, receipt["artifact_digest"])
        as_of = _first_present_str(payload, ("as_of", "asof"))
        if as_of is not None:
            receipt["as_of"] = as_of
        receipt["status"] = "AVAILABLE"
        receipt["coverage_state"] = "COMPLETE"

        if projection == "account":
            row = _project_account(payload)
        elif projection == "latest":
            row = _project_latest(payload)
        else:
            row = payload if isinstance(payload, (Mapping, list)) else {"value": payload}

        rows = [row] if row is not None else []
        receipt["rows_total"] = len(rows)
        receipt["rows_returned"] = len(rows)
        _merge_into_section(sections[section_id], rows=rows, coverage_state="COMPLETE",
                             omitted_rows=0, gaps=[])
        sources_out.append(receipt)

    for source_id, rel_path, section_id in _INTERNAL_JSONL_SPECS:
        path = book_dir / rel_path
        receipt = _base_receipt(
            source_id=source_id,
            domains=(section_id,),
            producer="mastermind_portfolio",
            owner="portfolio_desk",
            artifact=f"data/portfolios/{book}/{rel_path}",
            rights_class="FIRST_PARTY_INTERNAL",
            authority_class="BOOK_STATE",
            required=False,
            observed_at=observed_at,
        )
        sections.setdefault(section_id, _section(section_id, []))
        emit(section_id, source_id)

        raw, stat_after, size, error_code = _stable_first_party_read(path)
        receipt["bytes"] = size

        if error_code == "MISSING":
            receipt["status"] = "ABSENT_OPTIONAL"
            receipt["coverage_state"] = "COMPLETE"
            sources_out.append(receipt)
            continue

        if error_code in ("OVERSIZE", "INVALID", "SOURCE_CHANGED_DURING_READ"):
            receipt["status"] = "INVALID" if error_code == "SOURCE_CHANGED_DURING_READ" else error_code
            receipt["error_code"] = error_code
            receipt["coverage_state"] = "BLOCKED"
            if stat_after is not None:
                receipt["filesystem_observed_at"] = _utc_from_epoch_seconds(stat_after.st_mtime_ns / 1e9)
            gaps_out.append(_gap(error_code, source_id=source_id, section_id=section_id))
            _merge_into_section(sections[section_id], rows=[], coverage_state="BLOCKED",
                                 omitted_rows=0,
                                 gaps=[_gap(error_code, source_id=source_id, section_id=section_id)])
            sources_out.append(receipt)
            continue

        # Stable read succeeded — rows, digest, and mtime all come from the same bytes.
        mtime_utc = _utc_from_epoch_seconds(stat_after.st_mtime_ns / 1e9)
        receipt["known_at"] = mtime_utc
        receipt["filesystem_observed_at"] = mtime_utc
        receipt["clock_basis"] = "FILE_MTIME_FIRST_PARTY_STATE"
        receipt["artifact_digest"] = _digest(raw)

        tail = _parse_jsonl_tail(raw)
        receipt["status"] = "AVAILABLE"
        receipt["coverage_state"] = "COMPLETE"
        receipt["rows_total"] = tail["rows_total"]
        receipt["rows_returned"] = tail["rows_returned"]
        receipt["omitted_rows"] = tail["omitted_rows"]
        _merge_into_section(sections[section_id], rows=tail["rows"], coverage_state="COMPLETE",
                             omitted_rows=tail["omitted_rows"], gaps=[])
        sources_out.append(receipt)

    # Settlement receipts: sorted, metadata-bounded directory listing (no content parsing).
    settlement_dir = book_dir / _SETTLEMENT_RECEIPTS_DIR
    receipt = _base_receipt(
        source_id=_SETTLEMENT_RECEIPTS_SOURCE_ID,
        domains=("historical_memory",),
        producer="mastermind_portfolio",
        owner="portfolio_desk",
        artifact=f"data/portfolios/{book}/{_SETTLEMENT_RECEIPTS_DIR}",
        rights_class="FIRST_PARTY_INTERNAL",
        authority_class="BOOK_STATE",
        required=False,
        observed_at=observed_at,
    )
    sections.setdefault("historical_memory", _section("historical_memory", []))
    emit("historical_memory", _SETTLEMENT_RECEIPTS_SOURCE_ID)
    if settlement_dir.is_dir():
        names = sorted(p.name for p in settlement_dir.glob("*.json"))
        bounded = names[-MAX_SECTION_ROWS:]
        rows = [{"file": name} for name in bounded]
        manifest_digest = _digest(json.dumps(bounded, sort_keys=True).encode("utf-8"))
        receipt["artifact_digest"] = manifest_digest
        receipt["correction_generation"] = manifest_digest
        receipt["status"] = "AVAILABLE"
        receipt["coverage_state"] = "COMPLETE"
        receipt["rows_total"] = len(names)
        receipt["rows_returned"] = len(bounded)
        receipt["omitted_rows"] = len(names) - len(bounded)
        _merge_into_section(sections["historical_memory"], rows=rows, coverage_state="COMPLETE",
                             omitted_rows=len(names) - len(bounded), gaps=[])
    else:
        receipt["status"] = "ABSENT_OPTIONAL"
        receipt["coverage_state"] = "COMPLETE"
    sources_out.append(receipt)

    return {"sources": sources_out, "sections": sections, "gaps": gaps_out}


# ---------------------------------------------------------------------------
# External Macro source capture
# ---------------------------------------------------------------------------

def _resolve_external_path(spec: SourceSpec):
    from control_plane import contracts as contracts_module
    entry = contracts_module.contract(spec.contract_key)
    if not isinstance(entry, dict):
        return None
    rel_path = entry.get("path")
    if not isinstance(rel_path, str) or not rel_path:
        return None
    return _V / rel_path


def _project_risk_envelope(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        return {}
    allowed = (
        "schema", "definition_id", "known_at", "generated_at", "as_of", "data_state",
        "measured_state", "hazard_summary", "capital_policy", "coherence", "authority",
    )
    return {k: payload[k] for k in allowed if k in payload}


def _project_regime(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        return {}
    allowed = ("state", "quad", "liquidity", "cycle", "transition", "contradictions", "as_of")
    return {k: payload[k] for k in allowed if k in payload}


def _project_covariance_spine(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        return {}
    allowed = (
        "schema", "as_of", "data_state", "rates", "factors", "dispersion", "lobes",
        "coverage", "missing_inputs", "authority",
    )
    return {k: payload[k] for k in allowed if k in payload}


def _project_factor_betas(payload: Any, held_tickers: Sequence[str]) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        return {}
    held = {t.upper() for t in held_tickers}
    row: dict[str, Any] = {k: payload[k] for k in ("schema", "as_of", "generated_at") if k in payload}
    betas = payload.get("betas")
    if isinstance(betas, Mapping):
        row["betas"] = {t: v for t, v in betas.items() if t.upper() in held}
    return row


def _project_prophet(payload: Any, held_tickers: Sequence[str]) -> tuple[list[Any], int]:
    """Held-ticker plans, then the first 50 non-held plans, in producer order within each
    group. A non-Mapping (malformed) plan is never silently dropped from coverage — it
    always counts as an omitted row, exactly like an excess plan beyond either 50-cap."""
    if not isinstance(payload, Mapping):
        return [], 0
    plans = payload.get("plans")
    if not isinstance(plans, list):
        return [], 0
    held = {t.upper() for t in held_tickers}
    held_plans: list[Any] = []
    non_held_plans: list[Any] = []
    malformed = 0
    for plan in plans:
        if not isinstance(plan, Mapping):
            malformed += 1
            continue
        if str(plan.get("ticker", "")).upper() in held:
            held_plans.append(plan)
        else:
            non_held_plans.append(plan)
    selected_held = held_plans[:50]
    selected_non_held = non_held_plans[:50]
    selected = (selected_held + selected_non_held)[:MAX_SECTION_ROWS]
    omitted = (len(plans)) - len(selected)
    return selected, max(omitted, 0)


def _project_neural_web(payload: Any, held_tickers: Sequence[str]) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        return {}
    held = {t.upper() for t in held_tickers}
    row: dict[str, Any] = {
        k: payload[k] for k in ("authority", "effective_hard_false_fence", "market_summary") if k in payload
    }
    candidates = payload.get("candidates")
    if isinstance(candidates, list):
        row["candidates"] = [
            cand for cand in candidates
            if isinstance(cand, Mapping) and str(cand.get("ticker", "")).upper() in held
        ]
    return row


def _project_portfolio_context(
    payload: Any, held_tickers: Sequence[str]
) -> dict[str, tuple[list[Any], int]]:
    """Held-ticker rows per domain, each independently capped at 100. Returns
    ``{domain: (rows, omitted)}`` — ``omitted`` is the pre-slice held-ticker candidate
    count beyond the 100-row cap, so a cap drop is always counted, never silently lost."""
    domains = ("fundamental_state", "positioning", "event_state", "priceability")
    out: dict[str, tuple[list[Any], int]] = {domain: ([], 0) for domain in domains}
    if not isinstance(payload, Mapping):
        return out
    held = {t.upper() for t in held_tickers}
    for domain in domains:
        rows_field = payload.get(domain)
        if isinstance(rows_field, list):
            filtered = [
                row for row in rows_field
                if isinstance(row, Mapping) and str(row.get("ticker", "")).upper() in held
            ]
            selected = filtered[:MAX_SECTION_ROWS]
            out[domain] = (selected, len(filtered) - len(selected))
    return out


def _project_held_ticker_bundle(payload: Any, held_tickers: Sequence[str]) -> tuple[list[Any], int]:
    """The held-ticker rows from a ``{"tickers": {...}}`` bundle, capped at 100. The same
    ``(rows, omitted)`` pair is mirrored into every sibling domain this source feeds —
    callers must not multiply the counts by the number of domains."""
    if not isinstance(payload, Mapping):
        return [], 0
    tickers = payload.get("tickers")
    if not isinstance(tickers, Mapping):
        return [], 0
    held = {t.upper() for t in held_tickers}
    filtered = [
        {"ticker": ticker, **record}
        for ticker, record in tickers.items()
        if ticker.upper() in held and isinstance(record, Mapping)
    ]
    selected = filtered[:MAX_SECTION_ROWS]
    return selected, len(filtered) - len(selected)


def capture_external_sources(*, held_tickers: Sequence[str], decision_cutoff: str,
                              recorded_at: str) -> dict[str, Any]:
    observed_at = c.parse_utc_timestamp(recorded_at, field="recorded_at")
    cutoff = c.parse_utc_timestamp(decision_cutoff, field="decision_cutoff")

    section_ids = sorted({domain for spec in EXTERNAL_SOURCE_SPECS for domain in spec.domains})
    sections: dict[str, dict[str, Any]] = {sid: _section(sid, []) for sid in section_ids}
    sources_out: list[dict[str, Any]] = []
    gaps_out: list[dict[str, Any]] = []

    for spec in EXTERNAL_SOURCE_SPECS:
        for domain in spec.domains:
            sections[domain]["source_ids"].append(spec.source_id)

        artifact_path = _resolve_external_path(spec)
        receipt = _base_receipt(
            source_id=spec.source_id,
            domains=spec.domains,
            producer="macro_engine",
            owner="macro_engine",
            artifact=spec.contract_key,
            rights_class=spec.rights_class,
            authority_class=spec.authority_class,
            required=spec.required,
            observed_at=observed_at,
        )

        if artifact_path is None:
            receipt["status"] = "INVALID"
            receipt["error_code"] = "CONTRACT_UNAVAILABLE"
            receipt["coverage_state"] = "BLOCKED"
            gaps_out.append(_gap("CONTRACT_UNAVAILABLE", source_id=spec.source_id))
            for domain in spec.domains:
                _merge_into_section(sections[domain], rows=_risk_missing_placeholder(spec, domain),
                                     coverage_state="BLOCKED",
                                     omitted_rows=0, gaps=[_gap("CONTRACT_UNAVAILABLE", source_id=spec.source_id)])
            sources_out.append(receipt)
            continue

        raw, size, error_code = _read_json_bytes(artifact_path)
        receipt["bytes"] = size
        try:
            fs_mtime = artifact_path.stat().st_mtime
            receipt["filesystem_observed_at"] = _utc_from_epoch_seconds(fs_mtime)
        except OSError:
            pass

        if error_code == "MISSING":
            receipt["status"] = "MISSING"
            receipt["coverage_state"] = "PARTIAL"
            gaps_out.append(_gap("MISSING", source_id=spec.source_id))
            for domain in spec.domains:
                placeholder = _risk_missing_placeholder(spec, domain)
                _merge_into_section(
                    sections[domain], rows=placeholder, coverage_state="PARTIAL",
                    omitted_rows=0,
                    gaps=[_gap("MISSING", source_id=spec.source_id)],
                )
            sources_out.append(receipt)
            continue

        if error_code in ("OVERSIZE", "INVALID"):
            receipt["status"] = error_code
            receipt["error_code"] = error_code
            receipt["coverage_state"] = "PARTIAL"
            gaps_out.append(_gap(error_code, source_id=spec.source_id))
            for domain in spec.domains:
                _merge_into_section(sections[domain], rows=[], coverage_state="PARTIAL",
                                     omitted_rows=0,
                                     gaps=[_gap(error_code, source_id=spec.source_id)])
            sources_out.append(receipt)
            continue

        receipt["artifact_digest"] = _digest(raw)
        payload, parse_error = _parse_json(raw)
        if parse_error:
            receipt["status"] = "MALFORMED"
            receipt["error_code"] = parse_error
            receipt["coverage_state"] = "PARTIAL"
            gaps_out.append(_gap(parse_error, source_id=spec.source_id))
            for domain in spec.domains:
                _merge_into_section(sections[domain], rows=[], coverage_state="PARTIAL",
                                     omitted_rows=0,
                                     gaps=[_gap(parse_error, source_id=spec.source_id)])
            sources_out.append(receipt)
            continue

        receipt["correction_generation"] = _correction_generation(payload, receipt["artifact_digest"])
        receipt["source_schema"] = _first_present_str(payload, spec.schema_fields)
        receipt["definition_id"] = _first_present_str(payload, spec.definition_fields)
        as_of = _first_present_str(payload, spec.as_of_fields)
        if as_of is not None:
            receipt["as_of"] = as_of
        generated_at = _first_present_str(payload, spec.generated_at_fields)
        if generated_at is not None:
            normalized_generated = _canonical_or_none(generated_at)
            if normalized_generated is not None:
                receipt["generated_at"] = normalized_generated

        # PR #548-owned Sector Central: receipt/digest + explicit gap only, never rows.
        if spec.projection == "receipt_only_pr548":
            receipt["status"] = "DEPENDENCY_PARTIAL"
            receipt["coverage_state"] = "PARTIAL"
            gap = _gap(
                "DEPENDENCY_OWNED_ELSEWHERE",
                source_id=spec.source_id,
                owner="Mastermind PR #548",
                detail="non-lossy Sector Central reader is owned by PR #548; S0 captures receipt only",
            )
            gaps_out.append(gap)
            for domain in spec.domains:
                _merge_into_section(sections[domain], rows=[], coverage_state="PARTIAL",
                                     omitted_rows=0, gaps=[gap])
            sources_out.append(receipt)
            continue

        declared_known_at = _first_declared(payload, spec.known_at_fields)
        if declared_known_at is None:
            receipt["known_at"] = None
            receipt["clock_basis"] = "UNQUALIFIED_EXTERNAL_CLOCK"
            receipt["status"] = "UNQUALIFIED_CLOCK"
            receipt["coverage_state"] = "PARTIAL"
            gap = _gap("UNQUALIFIED_CLOCK", source_id=spec.source_id)
            gaps_out.append(gap)
            for domain in spec.domains:
                _merge_into_section(sections[domain], rows=[], coverage_state="PARTIAL",
                                     omitted_rows=0, gaps=[gap])
            sources_out.append(receipt)
            continue

        receipt["known_at"] = declared_known_at
        receipt["clock_basis"] = "DECLARED_SOURCE_FIELD"

        if declared_known_at > cutoff:
            receipt["status"] = "FUTURE_AT_CUTOFF"
            receipt["coverage_state"] = "BLOCKED"
            gap = _gap("FUTURE_AT_CUTOFF", source_id=spec.source_id)
            gaps_out.append(gap)
            for domain in spec.domains:
                _merge_into_section(sections[domain], rows=[], coverage_state="BLOCKED",
                                     omitted_rows=0, gaps=[gap])
            sources_out.append(receipt)
            continue

        receipt["status"] = "AVAILABLE"
        receipt["coverage_state"] = "COMPLETE"

        if spec.projection == "risk_envelope":
            row = _project_risk_envelope(payload)
            rows = [row] if row else []
            _merge_into_section(sections["risk_truth"], rows=rows, coverage_state="COMPLETE",
                                 omitted_rows=0, gaps=[])
            receipt["rows_total"] = receipt["rows_returned"] = len(rows)
        elif spec.projection == "regime":
            row = _project_regime(payload)
            rows = [row] if row else []
            _merge_into_section(sections["market_structure"], rows=rows, coverage_state="COMPLETE",
                                 omitted_rows=0, gaps=[])
            receipt["rows_total"] = receipt["rows_returned"] = len(rows)
        elif spec.projection == "covariance_spine":
            row = _project_covariance_spine(payload)
            rows = [row] if row else []
            _merge_into_section(sections["independence"], rows=rows, coverage_state="COMPLETE",
                                 omitted_rows=0, gaps=[])
            receipt["rows_total"] = receipt["rows_returned"] = len(rows)
        elif spec.projection == "factor_betas":
            row = _project_factor_betas(payload, held_tickers)
            rows = [row] if row else []
            _merge_into_section(sections["factor_risk"], rows=rows, coverage_state="COMPLETE",
                                 omitted_rows=0, gaps=[])
            receipt["rows_total"] = receipt["rows_returned"] = len(rows)
        elif spec.projection == "prophet":
            rows, omitted = _project_prophet(payload, held_tickers)
            _merge_into_section(sections["candidate_geometry"], rows=rows, coverage_state="COMPLETE",
                                 omitted_rows=omitted, gaps=[])
            receipt["rows_total"] = len(rows) + omitted
            receipt["rows_returned"] = len(rows)
            receipt["omitted_rows"] = omitted
        elif spec.projection == "neural_web":
            row = _project_neural_web(payload, held_tickers)
            rows = [row] if row else []
            _merge_into_section(sections["relationships"], rows=rows, coverage_state="COMPLETE",
                                 omitted_rows=0, gaps=[])
            receipt["rows_total"] = receipt["rows_returned"] = len(rows)
        elif spec.projection == "portfolio_context":
            by_domain = _project_portfolio_context(payload, held_tickers)
            total_returned = 0
            total_omitted = 0
            for domain, (rows, omitted) in by_domain.items():
                _merge_into_section(sections[domain], rows=rows, coverage_state="COMPLETE",
                                     omitted_rows=omitted, gaps=[])
                total_returned += len(rows)
                total_omitted += omitted
            receipt["rows_returned"] = total_returned
            receipt["omitted_rows"] = total_omitted
            receipt["rows_total"] = total_returned + total_omitted
        elif spec.projection == "held_ticker_bundle":
            rows, omitted = _project_held_ticker_bundle(payload, held_tickers)
            for domain in spec.domains:
                _merge_into_section(sections[domain], rows=rows, coverage_state="COMPLETE",
                                     omitted_rows=omitted, gaps=[])
            receipt["rows_returned"] = len(rows)
            receipt["omitted_rows"] = omitted
            receipt["rows_total"] = len(rows) + omitted

        sources_out.append(receipt)

    return {"sources": sources_out, "sections": sections, "gaps": gaps_out}


def _risk_missing_placeholder(spec: SourceSpec, domain: str) -> list[dict[str, Any]]:
    if spec.source_id == "macro.risk_envelope" and domain == "risk_truth":
        return [{
            "market_risk_state": "UNKNOWN_PROTECTIVE",
            "reason": f"{spec.source_id}:MISSING",
        }]
    return []


# ---------------------------------------------------------------------------
# Combined capture
# ---------------------------------------------------------------------------

def _held_tickers_from_book_sections(sections: Mapping[str, Any]) -> list[str]:
    tickers: list[str] = []
    seen: set[str] = set()
    for row in sections.get("book_truth", {}).get("rows", []):
        if not isinstance(row, Mapping):
            continue
        positions = row.get("positions")
        if isinstance(positions, Mapping):
            for ticker in positions:
                if ticker not in seen:
                    seen.add(ticker)
                    tickers.append(ticker)
        elif isinstance(positions, list):
            for pos in positions:
                if isinstance(pos, Mapping):
                    ticker = pos.get("ticker")
                    if isinstance(ticker, str) and ticker not in seen:
                        seen.add(ticker)
                        tickers.append(ticker)
    return tickers


def capture_all(book: str, *, decision_cutoff: str, recorded_at: str) -> dict[str, Any]:
    book_capture = capture_book_state(book, decision_cutoff=decision_cutoff, recorded_at=recorded_at)
    held_tickers = _held_tickers_from_book_sections(book_capture["sections"])
    external_capture = capture_external_sources(
        held_tickers=held_tickers, decision_cutoff=decision_cutoff, recorded_at=recorded_at,
    )

    sections: dict[str, dict[str, Any]] = {}
    for section_id, section in book_capture["sections"].items():
        sections[section_id] = section
    for section_id, section in external_capture["sections"].items():
        if section_id in sections:
            existing = sections[section_id]
            cap_dropped = _append_capped(existing, section["rows"])
            existing["source_ids"] = existing["source_ids"] + section["source_ids"]
            existing["coverage_state"] = _worse_coverage(existing["coverage_state"], section["coverage_state"])
            existing["omitted_rows"] += section["omitted_rows"] + cap_dropped
            existing["rows_returned"] = len(existing["rows"])
            existing["rows_total"] = existing["rows_returned"] + existing["omitted_rows"]
            existing["gaps"] = existing["gaps"] + section["gaps"]
        else:
            sections[section_id] = section

    return {
        "sources": book_capture["sources"] + external_capture["sources"],
        "sections": sections,
        "gaps": book_capture["gaps"] + external_capture["gaps"],
    }

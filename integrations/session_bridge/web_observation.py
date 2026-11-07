"""Bounded Web-Sol evidence projection; no browser I/O or retained state.

A census row is a tab observation, not an addressable session, RuntimeBinding,
execution receipt, conversation transcript, or proof of response delivery.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

from integrations.chairman_surfaces.web_sol_census_protocol import (
    decode_snapshot, validate_census_receipt,
)

SCHEMA = "mastermind.web_session_observations.v1"
MAX_SOURCES = 8
# The incumbent producer accepts 128 rows per profile. This independent display
# budget keeps eight source summaries plus rows inside the existing MCP envelope.
MAX_ROWS = 64
MAX_OUTPUT_BYTES = 64 * 1024
MAX_AGE_SECONDS = 120
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_COUNTS = (
    "initial_tab_count", "final_tab_count", "excluded_private_count",
    "omitted_tab_count", "unobserved_added_count", "unique_conversation_count",
    "duplicate_tab_count", "probed_tab_count", "generation_cue_count", "unknown_cue_count",
)


class ObservationBudgetError(ValueError):
    pass


def validate_adapters(value: Any) -> tuple[str, ...]:
    if (type(value) is not tuple or len(value) > MAX_SOURCES
            or any(type(x) is not str or _DIGEST.fullmatch(x) is None for x in value)
            or len(set(value)) != len(value)):
        raise ValueError("invalid authorized adapter projection")
    return value


def validate_clock(now: Any) -> datetime:
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("an aware owner clock is required")
    return now


def bounded_bytes(value: Any) -> bytes:
    raw = json.dumps(value, ensure_ascii=True, separators=(",", ":"), allow_nan=False).encode("ascii")
    if len(raw) > MAX_OUTPUT_BYTES:
        raise ObservationBudgetError("observation exceeds output budget")
    return raw


def _age(timestamp: str, now: datetime) -> tuple[str, float]:
    observed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    seconds = (now - observed).total_seconds()
    freshness = "FUTURE" if seconds < 0 else "STALE" if seconds > MAX_AGE_SECONDS else "FRESH"
    return freshness, round(seconds, 3)


def _unavailable(adapter: str, status: str) -> dict[str, Any]:
    return {
        "adapter_instance_id": adapter, "status": status,
        "scope": "CURRENT_PROFILE_NORMAL_CHATGPT_TABS",
        "inventory_coverage": "UNAVAILABLE", "probe_coverage": "NONE",
        "consistency": "UNKNOWN", "reason": None, "started_at": None,
        "completed_at": None, "freshness": "UNKNOWN", "source_age_seconds": None,
        "source_counts": None, "returned_rows": 0, "output_omitted_rows": 0, "rows": [],
    }


def _row(value: dict[str, Any], now: datetime, source_freshness: str) -> dict[str, Any]:
    freshness = _age(value["observed_at"], now)[0] if value["observed_at"] is not None else "UNKNOWN"
    usable = (
        source_freshness == freshness == "FRESH" and value["status"] == "OBSERVED"
        and not value["duplicate_cue_disagreement"]
        and value["auth_required"] is False and value["provider_error_present"] is False
    )
    cue = value["generation_cue"]
    activity = (
        "GENERATION_CUE_PRESENT" if usable and cue == "PRESENT" else
        "GENERATION_NOT_OBSERVED" if usable and cue == "NOT_OBSERVED" else "UNKNOWN"
    )
    return {
        "slot": value["slot"],
        "conversation_fingerprint": value["conversation_fingerprint"],
        "identity_evidence": value["identity_evidence"],
        "document_binding": value["document_binding"],
        "observed_status": value["status"], "observed_generation_cue": cue,
        "observed_at": value["observed_at"], "freshness": freshness,
        "duplicate_count": value["duplicate_count"],
        "duplicate_cue_disagreement": value["duplicate_cue_disagreement"],
        "current_activity": activity, "runtime_status": "UNKNOWN",
        "response_delivery": "NOT_ESTABLISHED", "control_eligibility": "NOT_ESTABLISHED",
    }


def project_observations(
    receipts: Any, *, authorized_adapters: tuple[str, ...],
    now: datetime, max_rows: int = 64,
) -> dict[str, Any]:
    """Project only closed incumbent receipts from the caller's authorized sources.

    The caller obtains authorized_adapters from the existing authorization owner,
    never from model arguments. A missing source remains NOT_RETURNED. Output
    truncation is independent of the producer's source completeness.
    """
    validate_adapters(authorized_adapters)
    validate_clock(now)
    if type(max_rows) is not int or not 1 <= max_rows <= MAX_ROWS:
        raise ValueError("invalid row bound")
    if type(receipts) not in (list, tuple) or len(receipts) > MAX_SOURCES:
        raise ValueError("invalid census collection")
    by_adapter = {}
    for raw in receipts:
        value = validate_census_receipt(raw)
        adapter = value["adapter_instance_id"]
        if adapter not in authorized_adapters or adapter in by_adapter:
            raise ValueError("census source is outside the exact projection")
        by_adapter[adapter] = value

    sources, remaining, omitted = [], max_rows, 0
    for adapter in authorized_adapters:
        receipt = by_adapter.get(adapter)
        if receipt is None or receipt["status"] != "COLLECTED":
            sources.append(_unavailable(adapter, receipt["status"] if receipt else "NOT_RETURNED"))
            continue
        snapshot = decode_snapshot(receipt["snapshot"])
        freshness, age = _age(snapshot["completed_at"], now)
        rows = snapshot["rows"]
        selected = rows[:remaining]
        hidden = len(rows) - len(selected)
        remaining -= len(selected)
        omitted += hidden
        sources.append({
            "adapter_instance_id": adapter, "status": "COLLECTED",
            "scope": snapshot["scope"], "inventory_coverage": snapshot["inventory_coverage"],
            "probe_coverage": snapshot["probe_coverage"], "consistency": snapshot["consistency"],
            "reason": snapshot["reason"], "started_at": snapshot["started_at"],
            "completed_at": snapshot["completed_at"], "freshness": freshness,
            "source_age_seconds": age,
            "source_counts": {key: snapshot[key] for key in _COUNTS},
            "returned_rows": len(selected), "output_omitted_rows": hidden,
            "rows": [_row(row, now, freshness) for row in selected],
        })
    collected = sum(source["status"] == "COLLECTED" for source in sources)
    output_coverage = (
        "NO_AUTHORIZED_SOURCES" if not sources else
        "UNAVAILABLE" if not collected else
        "PARTIAL" if omitted or collected != len(sources) else
        "COMPLETE_FOR_RETURNED_SOURCE_ROWS"
    )
    result = {
        "schema": SCHEMA, "visibility": (
            "AUTHORIZED_SOURCES_ONLY" if authorized_adapters else "NO_AUTHORIZED_SOURCES"),
        "account_history_coverage": "UNKNOWN", "account_conversation_count": None,
        "transcript_coverage": "NOT_COLLECTED", "authorized_source_count": len(authorized_adapters),
        "returned_row_count": max_rows - remaining, "output_omitted_rows": omitted,
        "output_coverage": output_coverage,
        "sources": sources,
        "authority_note": (
            "Observations only. Profile scope is not account history. Fingerprints do not "
            "establish identity, work ownership, RuntimeBinding, execution or delivery. "
            "No registered-target or workstream join is inferred."
        ),
    }
    bounded_bytes(result)
    return result

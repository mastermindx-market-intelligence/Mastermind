"""Bounded Web-Sol continuation projection over existing Agent OS reads.

This module owns no memory, lifecycle, transcript, queue, or provider session state.
It reduces the already-authoritative ``collect_agentos`` result into a small,
deterministic packet suitable for a fresh ChatGPT Web conversation.  Agent OS
remains the durable organizational owner; Executive OS remains the runtime/effect
owner.  The projection deliberately excludes record excerpts and raw tool output.
"""
from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any


SCHEMA = "mastermind.web_sol_continuation/v1"
MAX_PACKET_BYTES = 8 * 1024
MAX_NEXT_ACTION_BYTES = 2048
MAX_BLOCKER_BYTES = 512
MAX_WAVE_ACTION_BYTES = 768
MAX_BLOCKERS = 6
MAX_ACTIVE_WAVES = 16
MAX_EVIDENCE_REFS = 24
_WS_RE = re.compile(r"^WS:[A-Z0-9][A-Z0-9-]*$")


class WebSolContinuationError(ValueError):
    """Canonical Agent OS material cannot produce a safe bounded continuation."""


def canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise WebSolContinuationError("continuation is not canonical JSON data") from exc


def _token(value: Any, *, name: str, maximum: int = 256) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum or "\x00" in value:
        raise WebSolContinuationError(f"{name} is not a bounded non-empty string")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise WebSolContinuationError(f"{name} is not UTF-8") from exc
    return value


def _nullable_token(value: Any, *, name: str, maximum: int = 256) -> str | None:
    if value is None:
        return None
    return _token(value, name=name, maximum=maximum)


def _bounded_text(value: Any, *, name: str, maximum_bytes: int) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, str) or "\x00" in value:
        raise WebSolContinuationError(f"{name} must be text or null")
    try:
        encoded = value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise WebSolContinuationError(f"{name} is not UTF-8") from exc
    if len(encoded) <= maximum_bytes:
        return {"text": value, "truncated": False, "original_bytes": len(encoded)}

    # Byte-bound without emitting invalid UTF-8.  Truncation is always explicit.
    prefix = encoded[:maximum_bytes]
    while prefix:
        try:
            text = prefix.decode("utf-8")
            break
        except UnicodeDecodeError:
            prefix = prefix[:-1]
    else:
        text = ""
    return {"text": text, "truncated": True, "original_bytes": len(encoded)}


def _string_list(value: Any, *, name: str, maximum: int) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise WebSolContinuationError(f"{name} must be a list")
    result: list[str] = []
    for index, item in enumerate(value[:maximum]):
        result.append(_token(item, name=f"{name}[{index}]", maximum=256))
    return result


def _find_workstream(state: Mapping[str, Any], workstream: str) -> Mapping[str, Any]:
    rows = state.get("workstreams")
    if not isinstance(rows, list):
        raise WebSolContinuationError("Agent OS state has no workstreams list")
    key = workstream[3:]
    matches = [row for row in rows if isinstance(row, Mapping) and row.get("key") == key]
    if len(matches) != 1:
        raise WebSolContinuationError("Agent OS state does not contain exactly one requested workstream")
    return matches[0]


def _find_context(contexts: Any, workstream: str) -> Mapping[str, Any]:
    if not isinstance(contexts, list):
        raise WebSolContinuationError("Agent OS contexts must be a list")
    matches: list[Mapping[str, Any]] = []
    for context in contexts:
        if not isinstance(context, Mapping):
            continue
        target = context.get("target")
        if isinstance(target, Mapping) and target.get("workstream") == workstream:
            matches.append(context)
    if len(matches) != 1:
        raise WebSolContinuationError("Agent OS contexts do not contain exactly one requested workstream")
    return matches[0]


def _wave_projection(row: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    raw = row.get("wave_detail")
    if raw is None:
        return [], []
    if not isinstance(raw, list):
        raise WebSolContinuationError("workstream wave_detail must be a list")
    active: list[dict[str, Any]] = []
    do_not_redo: list[str] = []
    for index, wave in enumerate(raw):
        if not isinstance(wave, Mapping):
            raise WebSolContinuationError(f"wave_detail[{index}] must be an object")
        wave_id = _token(wave.get("id"), name=f"wave_detail[{index}].id", maximum=128)
        status = _token(wave.get("status"), name=f"wave_detail[{index}].status", maximum=64)
        if status in {"done", "dropped"}:
            do_not_redo.append(wave_id)
            continue
        if len(active) >= MAX_ACTIVE_WAVES:
            raise WebSolContinuationError("active wave set exceeds continuation ceiling")
        prs = wave.get("prs") or []
        if not isinstance(prs, list) or any(type(item) is not int or item < 1 for item in prs):
            raise WebSolContinuationError(f"wave_detail[{index}].prs must contain positive integers")
        active.append(
            {
                "id": wave_id,
                "status": status,
                "depends_on": _string_list(
                    wave.get("depends_on") or [], name=f"wave_detail[{index}].depends_on", maximum=16
                ),
                "deps_satisfied": wave.get("deps_satisfied") if isinstance(wave.get("deps_satisfied"), bool) else None,
                "next_action": _bounded_text(
                    wave.get("next_action"),
                    name=f"wave_detail[{index}].next_action",
                    maximum_bytes=MAX_WAVE_ACTION_BYTES,
                ),
                "prs": prs[:16],
                "wait": wave.get("wait") if isinstance(wave.get("wait"), Mapping) or wave.get("wait") is None else None,
            }
        )
    return active, do_not_redo


def _evidence_refs(context: Mapping[str, Any]) -> tuple[list[dict[str, Any]], int]:
    sections = context.get("sections")
    if not isinstance(sections, list):
        raise WebSolContinuationError("Agent OS context sections must be a list")
    refs: list[dict[str, Any]] = []
    total = 0
    for section in sections:
        if not isinstance(section, Mapping):
            continue
        items = section.get("items")
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, Mapping):
                continue
            locator = item.get("locator")
            path = item.get("path")
            if not isinstance(locator, str) or not locator or not isinstance(path, str) or not path:
                continue
            total += 1
            if len(refs) >= MAX_EVIDENCE_REFS:
                continue
            refs.append(
                {
                    "kind": item.get("kind") if isinstance(item.get("kind"), str) else None,
                    "key": item.get("key") if isinstance(item.get("key"), str) else None,
                    "path": path,
                    "locator": locator,
                    "authority_class": item.get("authority_class") if isinstance(item.get("authority_class"), str) else None,
                    "status": item.get("status") if isinstance(item.get("status"), str) else None,
                    "updated": item.get("updated") if isinstance(item.get("updated"), str) else None,
                }
            )
    return refs, total


def build_continuation(agentos: Mapping[str, Any], workstream: str) -> dict[str, Any]:
    """Build one strict continuation packet from ``collect_agentos`` output.

    The packet is a read-only projection.  It does not become the owner of any
    included fact and must be refreshed from Agent OS before modifying work after
    a material gap.
    """

    if not isinstance(workstream, str) or _WS_RE.fullmatch(workstream) is None:
        raise WebSolContinuationError("workstream must use exact WS:<KEY> form")
    if not isinstance(agentos, Mapping) or agentos.get("available") is not True:
        raise WebSolContinuationError("canonical Agent OS read is unavailable")
    source_sha = _token(agentos.get("source_sha"), name="agentos.source_sha", maximum=64)
    state = agentos.get("state")
    if not isinstance(state, Mapping) or state.get("schema") != "agent_os_state.v1":
        raise WebSolContinuationError("Agent OS state schema is incompatible")
    row = _find_workstream(state, workstream)
    context = _find_context(agentos.get("contexts"), workstream)
    if context.get("schema") != "context_bundle.v1":
        raise WebSolContinuationError("Agent OS context schema is incompatible")

    active_waves, do_not_redo = _wave_projection(row)
    refs, ref_total = _evidence_refs(context)
    blockers_raw = row.get("blocked_by") or []
    if not isinstance(blockers_raw, list):
        raise WebSolContinuationError("workstream blocked_by must be a list")
    blockers = [
        _bounded_text(item, name=f"blocked_by[{index}]", maximum_bytes=MAX_BLOCKER_BYTES)
        for index, item in enumerate(blockers_raw[:MAX_BLOCKERS])
    ]

    packet = {
        "schema": SCHEMA,
        "workstream": workstream,
        "generated_at": context.get("generated_at") if isinstance(context.get("generated_at"), str) else None,
        "agentos_source_sha": source_sha,
        "source_records_digest": context.get("source_records_digest") if isinstance(context.get("source_records_digest"), str) else None,
        "state": {
            "status": _token(row.get("status"), name="workstream.status", maximum=64),
            "program": _nullable_token(row.get("program"), name="workstream.program"),
            "owner": _nullable_token(row.get("owner"), name="workstream.owner"),
            "p0": _nullable_token(row.get("p0"), name="workstream.p0"),
            "next_action": _bounded_text(
                row.get("next_action"), name="workstream.next_action", maximum_bytes=MAX_NEXT_ACTION_BYTES
            ),
            "blocked_by": blockers,
            "blocked_by_total": len(blockers_raw),
            "wait": row.get("wait") if isinstance(row.get("wait"), Mapping) or row.get("wait") is None else None,
            "needs_ceo": row.get("needs_ceo") if isinstance(row.get("needs_ceo"), Mapping) or row.get("needs_ceo") is None else None,
            "claim": row.get("claim") if isinstance(row.get("claim"), Mapping) or row.get("claim") is None else None,
            "collisions": row.get("collisions") if isinstance(row.get("collisions"), list) else [],
            "source": _token(row.get("source"), name="workstream.source", maximum=1024),
        },
        "active_waves": active_waves,
        "do_not_redo": do_not_redo,
        "evidence_refs": refs,
        "evidence_ref_total": ref_total,
        "evidence_refs_truncated": ref_total > len(refs),
        "warnings": [str(item) for item in (agentos.get("warnings") or [])][:8],
        "authority_note": (
            "Projection only: Agent OS owns organizational continuity; Executive OS owns runtime/effect truth. "
            "Refresh canonical owners before modifying work."
        ),
    }
    size = len(canonical_bytes(packet))
    if size > MAX_PACKET_BYTES:
        raise WebSolContinuationError(
            f"continuation exceeds strict {MAX_PACKET_BYTES}-byte ceiling ({size} bytes)"
        )
    packet["packet_bytes"] = size
    final_size = len(canonical_bytes(packet))
    if final_size > MAX_PACKET_BYTES:
        raise WebSolContinuationError("continuation exceeds strict byte ceiling after accounting")
    packet["packet_bytes"] = final_size
    return packet

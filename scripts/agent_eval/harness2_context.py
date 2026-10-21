"""Read the existing Agent OS context bundle as bounded Harness2 experience.

No files, network, model, database, indexing, scheduling or Agent OS writes.
The caller acquires raw bytes and expected identity through its existing trusted
context owner. Byte agreement is not authentication or verified learning.
The COMPLETE bundle, including higher law and every omission/degradation, stays
available to the consuming harness; the experience view is not a replacement.
"""
from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any

from scripts.agent_eval import contracts
from scripts.agent_eval.canonical import parse_digest_string, parse_source_qualified_ref
from scripts.agent_eval.harness2_native import MAX_JSON_BYTES, decode_json, sha256_bytes

_EXPERIENCE_FIELDS = frozenset({
    "schema", "domain", "harness_artifact", "source_run_ids", "method_source_ref",
    "claim", "falsifier", "so_what", "verified_by", "verified_at", "confidence",
})
_SECTIONS = frozenset({"higher_law", "workstream", "decisions", "discoveries", "handoff", "artifacts"})
_KEY = re.compile(r"DSC:[A-Z0-9][A-Z0-9-]{0,127}")


class Harness2ContextError(ValueError):
    """Invalid or conflicting source identity; never a new runtime gate."""


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise Harness2ContextError(code)


def _text(value: Any, limit: int, code: str) -> str:
    _require(type(value) is str and bool(value.strip()) and len(value) <= limit
             and "\x00" not in value, code)
    return value


def _moment(value: Any) -> datetime:
    _text(value, 64, "CONTEXT_TIME_INVALID")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise Harness2ContextError("CONTEXT_TIME_INVALID") from exc
    _require(parsed.tzinfo is not None, "CONTEXT_TIMEZONE_REQUIRED")
    return parsed.astimezone(timezone.utc)


@dataclass(frozen=True)
class HarnessContext:
    """Detached source data, not an authorization or immutable attestation object."""

    bundle: dict
    bundle_digest: str
    repository_sha: str
    workstream: str
    source_records_digest: str
    experience: tuple[dict, ...]
    experience_exclusions: tuple[dict, ...]
    evidence_scope: str = "BYTE_AND_IDENTITY_CHECKED_NOT_AUTHENTICATED"


def read_context_bundle(*, bundle_bytes: bytes, expected_bundle_digest: str,
                        expected_repository_sha: str, expected_workstream: str,
                        task_domain: str, not_after: str) -> HarnessContext:
    """Consume only typed lessons already selected by the native compiler.

    A structured lesson can still be merely probable/suspected; retain its original
    confidence. Future-dated or other-domain lessons do not become the prior library.
    Native exclusions/omissions/degradation remain on the whole returned bundle.
    No pathname or artifact reference obtained from this input is followed here.
    """
    _require(type(bundle_bytes) is bytes and 0 < len(bundle_bytes) <= MAX_JSON_BYTES,
             "CONTEXT_BYTE_BOUND")
    parse_digest_string(expected_bundle_digest)
    _require(sha256_bytes(bundle_bytes) == expected_bundle_digest, "CONTEXT_BYTES_CHANGED")
    _require(type(expected_repository_sha) is str
             and re.fullmatch(r"[0-9a-f]{40}", expected_repository_sha) is not None,
             "CONTEXT_REPOSITORY_SHA_REQUIRED")
    _require(type(expected_workstream) is str
             and re.fullmatch(r"WS:[A-Z0-9][A-Z0-9-]{0,127}", expected_workstream) is not None,
             "CONTEXT_WORKSTREAM_REQUIRED")
    _text(task_domain, 128, "CONTEXT_DOMAIN_REQUIRED")
    cutoff = _moment(not_after)
    bundle = decode_json(bundle_bytes)
    _require(bundle.get("schema") == "context_bundle.v1", "CONTEXT_SCHEMA_UNSUPPORTED")
    _require(bundle.get("repo_sha") == expected_repository_sha, "CONTEXT_SOURCE_GENERATION_MISMATCH")
    target = bundle.get("target")
    _require(type(target) is dict and target.get("workstream") == expected_workstream
             and target.get("resolution") == "explicit", "CONTEXT_TARGET_MISMATCH")
    generated = _moment(bundle.get("generated_at"))
    _require(generated <= cutoff, "CONTEXT_FROM_THE_FUTURE")
    records_digest = bundle.get("source_records_digest")
    parse_digest_string(records_digest)
    for tail in ("excluded", "omitted_due_to_budget", "degraded"):
        _require(type(bundle.get(tail)) is list and len(bundle[tail]) <= 4096,
                 "CONTEXT_COMPLETENESS_TAIL_REQUIRED")
    sections = bundle.get("sections")
    _require(type(sections) is list and len(sections) == len(_SECTIONS), "CONTEXT_SECTIONS_INVALID")
    section_map: dict[str, dict] = {}
    for section in sections:
        _require(type(section) is dict and type(section.get("id")) is str
                 and section["id"] in _SECTIONS and section["id"] not in section_map,
                 "CONTEXT_SECTION_CONFLICT")
        _require(type(section.get("items")) is list and len(section["items"]) <= 4096,
                 "CONTEXT_ITEMS_INVALID")
        section_map[section["id"]] = section
    unavailable: set[str] = set()
    for row in bundle["excluded"] + bundle["omitted_due_to_budget"]:
        _require(type(row) is dict, "CONTEXT_OMISSION_INVALID")
        if type(row.get("key")) is str:
            unavailable.add(row["key"])
    accepted: list[dict] = []
    exclusions: list[dict] = []
    seen: set[str] = set()
    for item in section_map["discoveries"]["items"]:
        _require(type(item) is dict, "CONTEXT_DISCOVERY_INVALID")
        key = item.get("key")
        _require(type(key) is str and _KEY.fullmatch(key) is not None and key not in seen,
                 "CONTEXT_DISCOVERY_IDENTITY_CONFLICT")
        seen.add(key)
        _require(key not in unavailable, "CONTEXT_INCLUDED_AND_EXCLUDED")
        if "harness_experience" not in item:
            exclusions.append({"key": key, "reason": "NO_STRUCTURED_HARNESS_EXPERIENCE"})
            continue
        _require(item.get("kind") == "discovery" and item.get("authority_class") == "A3",
                 "CONTEXT_DISCOVERY_KIND_MISMATCH")
        _text(item.get("path"), 4096, "CONTEXT_DISCOVERY_SOURCE_MISSING")
        _text(item.get("locator"), 4096, "CONTEXT_DISCOVERY_SOURCE_MISSING")
        experience = item["harness_experience"]
        _require(type(experience) is dict and set(experience) == _EXPERIENCE_FIELDS
                 and experience["schema"] == "agentos.harness_experience.v1", "CONTEXT_EXPERIENCE_SHAPE")
        _text(experience["domain"], 128, "CONTEXT_EXPERIENCE_DOMAIN")
        for field in ("claim", "falsifier", "so_what", "verified_by"):
            _text(experience[field], 8192, "CONTEXT_EXPERIENCE_TEXT")
        contracts.v_artifact_pair(experience["harness_artifact"], "$.experience.harness_artifact")
        parse_source_qualified_ref(experience["method_source_ref"])
        refs = experience["source_run_ids"]
        _require(type(refs) is list and 2 <= len(refs) <= 128, "CONTEXT_RUN_REFERENCE_BOUND")
        for ref in refs:
            contracts.v_run_id(ref, "$.experience.source_run_ids")
        _require(len(set(refs)) == len(refs), "CONTEXT_DUPLICATE_RUN_REFERENCE")
        confidence = experience["confidence"]
        _require(confidence in ("verified", "probable", "suspected") and item.get("status") == confidence,
                 "CONTEXT_CONFIDENCE_CONFLICT")
        try:
            verified = date.fromisoformat(experience["verified_at"])
        except (ValueError, TypeError) as exc:
            raise Harness2ContextError("CONTEXT_VERIFICATION_DATE_INVALID") from exc
        if verified > generated.date():
            exclusions.append({"key": key, "reason": "VERIFICATION_POSTDATES_CONTEXT"})
            continue
        if experience["domain"] != task_domain:
            exclusions.append({"key": key, "reason": "OTHER_DOMAIN"})
            continue
        _require(len(accepted) < 32, "CONTEXT_EXPERIENCE_COUNT_BOUND")
        accepted.append({
            "discovery_ref": key,
            # A context-item locator is honest for both production Git and a
            # temporary native compiler fixture; do not invent a Git-tracked path.
            "source_ref": "context:" + expected_bundle_digest + "#" + key,
            "domain": task_domain, "claim": experience["claim"],
            "falsifier": experience["falsifier"], "so_what": experience["so_what"],
            "harness_artifact": copy.deepcopy(experience["harness_artifact"]),
            "confidence": confidence, "source_run_ids": list(refs),
            "method_source_ref": experience["method_source_ref"],
        })
    return HarnessContext(copy.deepcopy(bundle), expected_bundle_digest, expected_repository_sha,
                          expected_workstream, records_digest, tuple(accepted), tuple(exclusions))

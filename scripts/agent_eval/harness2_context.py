"""Read the existing Agent OS context bundle as bounded Harness2 experience.

No direct file, network, model, indexing, scheduling or Agent OS writes.
The draft producer resolves explicit IDs through the existing native evidence owner.
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

from scripts.agent_eval import contracts, verification
from scripts.agent_eval.canonical import parse_digest_string, parse_source_qualified_ref
from scripts.agent_eval.harness2_native import (
    MAX_JSON_BYTES, configuration_lock, decode_json, harness_digest, sha256_bytes,
)
from scripts.agent_eval.resolver import ArtifactResolver

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


def build_discovery_payload(*, refinement: dict, resolver: ArtifactResolver,
                            key: str, workstream: str, method_source_ref: str,
                            checked_at: str) -> dict | None:
    """Prepare input for the incumbent Agent OS ``draft-discovery`` command.

    This is a DRAFT with confidence ``suspected``, not verified institutional
    learning. Existing EVAL graph validation authenticates no issuer and reads no
    external evidence contents. Caller supplies the existing trusted resolver;
    no fallback, file write, memory admission, scorer or deployment happens here.
    Empty reflection and unchanged harnesses yield no positive learning draft.
    """
    _require(type(refinement) is dict, "DISCOVERY_REFINEMENT_REQUIRED")
    _require(type(key) is str and len(key) <= 128
             and re.fullmatch(r"[A-Z0-9]+(?:-[A-Z0-9]+)*", key) is not None,
             "DISCOVERY_KEY_INVALID")
    _require(type(workstream) is str and re.fullmatch(r"WS:[A-Z0-9]+(?:-[A-Z0-9]+)*", workstream)
             is not None and len(workstream) <= 131, "DISCOVERY_WORKSTREAM_INVALID")
    parse_source_qualified_ref(method_source_ref)
    checked = _moment(checked_at)
    domain = _text(refinement.get("domain"), 128, "DISCOVERY_DOMAIN_INVALID")
    k = refinement.get("k")
    mode = refinement.get("mode")
    _require(type(k) is int and 1 <= k <= 16 and mode in ("agg", "seq"), "DISCOVERY_MODE_INVALID")
    _require(refinement.get("promotion") == "NONE"
             and refinement.get("automatic_memory_write") is False, "DISCOVERY_AUTHORITY_EXPANSION")
    retained = refinement.get("retained_native_runs")
    baselines = refinement.get("baseline_native_run_ids")
    _require(type(retained) is tuple and len(retained) == 4 * k, "DISCOVERY_RUN_COUNT_INVALID")
    _require(type(baselines) is tuple and len(baselines) == k, "DISCOVERY_BASELINE_COUNT_INVALID")
    for ident in retained + baselines:
        contracts.v_run_id(ident, "$.native_runs")
    _require(len(set(retained)) == len(retained) and len(set(baselines)) == k,
             "DISCOVERY_DUPLICATE_RUN")
    _require(baselines == retained[:k], "DISCOVERY_BASELINE_ORDER_INVALID")
    chosen = refinement.get("selected_native_run_id")
    contracts.v_run_id(chosen, "$.selected_native_run_id")
    stem = "agg" if mode == "agg" else "c"
    _require(refinement.get("selected_label") in {stem + str(i) for i in range(1, k + 1)}
             and chosen in retained and chosen not in baselines, "DISCOVERY_SELECTION_UNBOUND")
    expected_lock = refinement.get("factor_lock_digest")
    base_digest = refinement.get("baseline_harness_digest")
    parse_digest_string(expected_lock)
    parse_digest_string(base_digest)
    records: dict[str, tuple[dict, dict]] = {}
    for ident in retained:
        run = resolver.resolve_run(ident)
        _require(type(run) is dict and run.get("run_id") == ident, "DISCOVERY_RUN_NOT_RETAINED")
        verification.verify_run_graph(run, resolver)
        _require(run["validity"]["status"] == "VALID" and run["effect"]["state"] == "NO_EFFECT",
                 "DISCOVERY_RUN_NOT_VALID")
        _require(_moment(run["timing"]["completed_at"]) <= checked, "DISCOVERY_CHECK_PREDATES_RUN")
        config = resolver.resolve_configuration(run["configuration"]["configuration_id"])
        _require(type(config) is dict, "DISCOVERY_CONFIGURATION_NOT_RETAINED")
        _require(configuration_lock(run["scenario"], config) == expected_lock,
                 "DISCOVERY_FACTOR_LOCK_CHANGED")
        if ident in baselines:
            _require(config["procedure"]["instruction_bundle"]["digest"] == base_digest,
                     "DISCOVERY_BASELINE_HARNESS_CHANGED")
        records[ident] = (copy.deepcopy(run), copy.deepcopy(config))
    selected_run, selected_config = records[chosen]
    selected_artifact = refinement.get("selected_harness_artifact")
    contracts.v_artifact_pair(selected_artifact, "$.selected_harness_artifact")
    _require(selected_artifact == selected_config["procedure"]["instruction_bundle"],
             "DISCOVERY_SELECTED_ARTIFACT_CHANGED")
    _require(harness_digest(refinement.get("selected_harness")) == selected_artifact["digest"],
             "DISCOVERY_SELECTED_HARNESS_CHANGED")
    _require(sha256_bytes(refinement.get("selected_output")) == selected_run["evidence"]["output"]["digest"],
             "DISCOVERY_SELECTED_OUTPUT_CHANGED")
    reflection = refinement.get("experience_candidate")
    if reflection is None:
        return None
    _require(type(reflection) is dict and set(reflection) ==
             {"claim", "falsifier", "so_what", "evidence_run_ids"}, "DISCOVERY_REFLECTION_SHAPE")
    for field in ("claim", "falsifier", "so_what"):
        _text(reflection[field], 7800, "DISCOVERY_REFLECTION_TEXT_BOUND")
    refs = reflection["evidence_run_ids"]
    _require(type(refs) is list and 2 <= len(refs) <= 128, "DISCOVERY_REFLECTION_RUN_BOUND")
    for ident in refs:
        contracts.v_run_id(ident, "$.reflection.evidence_run_ids")
    _require(len(set(refs)) == len(refs) and set(refs) <= set(retained)
             and chosen in refs and bool(set(refs) & set(baselines)),
             "DISCOVERY_REFLECTION_BASELINE_AND_SELECTED_REQUIRED")
    if selected_artifact["digest"] == base_digest:
        return None
    return {
        "key": key,
        "claim": "Unvalidated harness hypothesis: " + reflection["claim"],
        "falsifier": ("Inspect the retained comparison with scripts/agent_eval/verification.py; "
                      "external-content and outcome review are still required. " + reflection["falsifier"]),
        "so_what": "Test this candidate before any operational use. " + reflection["so_what"],
        "kind": "architecture", "verified_at": checked.date().isoformat(),
        "verified_by": ("scripts/agent_eval/verification.py checks retained graph associations, not efficacy "
                        "or issuer authenticity; source runs: " + ", ".join(refs)),
        "scope": [workstream], "confidence": "suspected",
        "harness_experience": {
            "domain": domain, "harness_artifact": copy.deepcopy(selected_artifact),
            "source_run_ids": list(refs), "method_source_ref": method_source_ref,
        },
    }

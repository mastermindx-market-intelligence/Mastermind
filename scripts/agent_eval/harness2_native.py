"""Byte-bound Harness2 import into the EXISTING Agent Evaluation run contracts.

This adapter is pure: callers resolve bytes through their existing authorized
owners. A digest establishes byte agreement, NOT issuer authentication, runtime
admission, judge quality, holdout secrecy, or permission to promote a harness.
The native observation supplies effect, model, freshness and cleanup facts;
third-party summary flags never manufacture or overwrite those observations.

Upstream serialization: google-research/harness2@1cfe254e8d25b15f37048c3730134686abe60335,
core/schedule.py::_run_one_mode and core/runmark.py::fingerprint. No upstream
launcher, dependencies, scheduler, library or provider is imported here.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from scripts.agent_eval import contracts, validity
from scripts.agent_eval.canonical import (
    canonical_json_bytes, digest_value, parse_digest_string,
    parse_source_qualified_ref, require_canonical_json_tree,
)

UPSTREAM_SOURCE_REF = (
    "git:google-research/harness2@1cfe254e8d25b15f37048c3730134686abe60335"
)
BINDING_SCHEMA = "mastermind.harness2_artifact_binding.v1"
TREE_SCHEMA = "mastermind.harness2_file_manifest.v1"
MAX_JSON_BYTES = 1_048_576
MAX_TREE_BYTES = 4_194_304
MAX_FILES = 128
MAX_NODES = 32768
MAX_DEPTH = 32
_BINDING_FIELDS = frozenset({
    "schema", "upstream_source_ref", "task_id", "domain", "mode", "k",
    "upstream_run_id", "native_run_id", "summary", "native_observation",
    "harness", "output",
})
_PAIR_FIELDS = frozenset({"artifact_ref", "digest"})


class Harness2ImportError(ValueError):
    """Malformed, incomplete, changed or incorrectly correlated input."""


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise Harness2ImportError(code)


def sha256_bytes(raw: bytes) -> str:
    _require(type(raw) is bytes, "BYTES_REQUIRED")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _bounded_text(value: Any, label: str, maximum: int = 256) -> str:
    _require(type(value) is str and bool(value.strip()) and len(value) <= maximum,
             label + "_INVALID")
    _require(all(ord(c) >= 32 and ord(c) != 127 for c in value), label + "_CONTROL")
    _require(unicodedata.normalize("NFC", value) == value, label + "_NOT_NFC")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise Harness2ImportError(label + "_UTF8") from exc
    return value


def _reject_constant(value: str) -> None:
    raise Harness2ImportError("NONFINITE_JSON_NUMBER")


def _object_pairs(pairs: list[tuple[str, Any]]) -> dict:
    result: dict[str, Any] = {}
    for key, value in pairs:
        _require(key not in result, "DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def decode_json(raw: bytes, *, canonical: bool = False) -> dict:
    """Bounded strict JSON reader; nested/unicode/finite checks precede consumers."""
    _require(type(raw) is bytes and 0 < len(raw) <= MAX_JSON_BYTES,
             "JSON_BYTE_BOUND")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_object_pairs,
                           parse_constant=_reject_constant)
    except (UnicodeError, ValueError, RecursionError) as exc:
        if isinstance(exc, Harness2ImportError):
            raise
        raise Harness2ImportError("INVALID_JSON") from exc
    _require(type(value) is dict, "JSON_OBJECT_REQUIRED")
    pending = [(value, 0)]
    nodes = 0
    while pending:
        item, depth = pending.pop()
        nodes += 1
        _require(nodes <= MAX_NODES and depth <= MAX_DEPTH, "JSON_COMPLEXITY_BOUND")
        if type(item) is dict:
            for key, child in item.items():
                _bounded_text(key, "KEY", MAX_JSON_BYTES)
                pending.append((child, depth + 1))
        elif type(item) is list:
            pending.extend((child, depth + 1) for child in item)
        elif type(item) is str:
            _require(unicodedata.normalize("NFC", item) == item, "STRING_NOT_NFC")
            try:
                item.encode("utf-8")
            except UnicodeEncodeError as exc:
                raise Harness2ImportError("STRING_UTF8") from exc
        elif type(item) is float:
            _require(math.isfinite(item), "NONFINITE_JSON_NUMBER")
        elif type(item) is int:
            _require(-(2**63) <= item < 2**63, "INTEGER_BOUND")
    if canonical:
        require_canonical_json_tree(value)
    return value


def _pair(value: Any) -> dict:
    _require(type(value) is dict and set(value) == _PAIR_FIELDS, "ARTIFACT_PAIR_INVALID")
    _bounded_text(value["artifact_ref"], "ARTIFACT_REF", 2048)
    # Artifact references use the incumbent artifact-pair grammar; source-code
    # refs have a different closed grammar and cannot parse '#file' locators.
    contracts.v_artifact_pair(value, "$.artifact")
    parse_digest_string(value["digest"])
    return value


def harness_manifest(files: Mapping[str, bytes]) -> dict:
    """Strong identity over an explicitly complete caller-resolved file inventory.

    This does not traverse the filesystem or attest that the inventory is complete.
    An authorized native exporter must enumerate all materialized harness files.
    Cross-platform aliases and runmark-ignored byproducts are refused, not hidden.
    """
    _require(type(files) is dict and 0 < len(files) <= MAX_FILES, "HARNESS_FILE_BOUND")
    total = 0
    aliases: set[str] = set()
    nodes: dict[str, tuple[str, bool]] = {}
    for path, raw in files.items():
        _bounded_text(path, "HARNESS_PATH", 512)
        parts = path.split("/")
        _require(not path.startswith("/") and "\\" not in path and ":" not in path
                 and all(p and p not in (".", "..") and p == p.strip()
                         and not p.endswith(".") for p in parts), "UNSAFE_HARNESS_PATH")
        _require(not any(p in (".git", "__pycache__", ".DS_Store", ".adapt_complete")
                         for p in parts) and not path.endswith(".pyc"), "HARNESS_BYPRODUCT")
        alias = path.casefold()
        _require(alias not in aliases, "HARNESS_PATH_ALIAS")
        aliases.add(alias)
        for index in range(1, len(parts) + 1):
            prefix = "/".join(parts[:index])
            node = (prefix, index == len(parts))
            prior = nodes.get(prefix.casefold())
            _require(prior is None or prior == node, "HARNESS_FILE_DIRECTORY_OR_CASE_ALIAS")
            nodes[prefix.casefold()] = node
        _require(type(raw) is bytes and len(raw) <= MAX_JSON_BYTES, "HARNESS_FILE_BYTES")
        try:
            raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise Harness2ImportError("HARNESS_FILE_UTF8") from exc
        total += len(raw)
    _require(total <= MAX_TREE_BYTES, "HARNESS_TREE_BYTE_BOUND")
    return {"schema": TREE_SCHEMA, "files": [
        {"path": p, "digest": sha256_bytes(files[p]), "size_bytes": len(files[p])}
        for p in sorted(files)
    ]}


def harness_digest(files: Mapping[str, bytes]) -> str:
    return digest_value(harness_manifest(files))


def upstream_fingerprint(files: Mapping[str, bytes]) -> str:
    """Upstream 64-bit truncated SHA1 convention, ONLY for format compatibility."""
    harness_manifest(files)
    digest = hashlib.sha1()
    for path in sorted(files):
        digest.update(path.encode("utf-8") + b"\0" + files[path] + b"\0")
    return digest.hexdigest()[:16]


@dataclass(frozen=True)
class Harness2Import:
    """Detached comparison data; not an authentication/admission/result authority."""

    draft: dict
    binding_digest: str
    summary_digest: str
    harness_digest: str
    upstream_run_id: str
    native_run_id: str
    evidence_scope: str = "BYTE_AND_IDENTITY_CHECKED_NOT_AUTHENTICATED"
    promotion: str = "NONE"


def import_selected_run(
    *, binding_bytes: bytes, expected_binding_digest: str,
    summary_bytes: bytes, native_observation_bytes: bytes,
    output_bytes: bytes, harness_files: Mapping[str, bytes],
    scenario: dict, configuration: dict, experiment: dict | None,
) -> Harness2Import:
    """Join an upstream selected rollout to its pre-existing native observation.

    The expected binding digest must arrive through the caller's actual trusted
    owner channel. Passing a self-authored binding is not independent provenance.
    Invalid native effects/cleanup remain representable: native validity decides
    them and this importer must not turn an invalid run into an absent record.
    """
    parse_digest_string(expected_binding_digest)
    _require(type(binding_bytes) is bytes and 0 < len(binding_bytes) <= MAX_JSON_BYTES,
             "BINDING_BYTE_BOUND")
    _require(sha256_bytes(binding_bytes) == expected_binding_digest, "BINDING_BYTES_CHANGED")
    binding = decode_json(binding_bytes, canonical=True)
    _require(set(binding) == _BINDING_FIELDS and binding["schema"] == BINDING_SCHEMA,
             "BINDING_SCHEMA_INVALID")
    _require(binding["upstream_source_ref"] == UPSTREAM_SOURCE_REF, "UPSTREAM_SOURCE_UNSUPPORTED")
    for field in ("task_id", "domain", "upstream_run_id", "native_run_id"):
        _bounded_text(binding[field], field.upper())
    contracts.v_run_id(binding["native_run_id"], "$.native_run_id")
    mode, k = binding["mode"], binding["k"]
    _require(type(mode) is str and mode in ("agg", "seq"), "MODE_INVALID")
    _require(type(k) is int and 1 <= k <= 64, "RECURSION_BUDGET_INVALID")
    for key in ("summary", "native_observation", "harness", "output"):
        _pair(binding[key])
    refs = [binding[key]["artifact_ref"] for key in
            ("summary", "native_observation", "harness", "output")]
    _require(len(set(refs)) == len(refs), "ARTIFACT_REF_COLLISION")
    for key, raw in (("summary", summary_bytes), ("native_observation", native_observation_bytes),
                     ("output", output_bytes)):
        _require(type(raw) is bytes and 0 < len(raw) <= MAX_JSON_BYTES, key.upper() + "_BYTE_BOUND")
        _require(sha256_bytes(raw) == binding[key]["digest"], key.upper() + "_BYTES_CHANGED")
    summary = decode_json(summary_bytes)
    draft = decode_json(native_observation_bytes, canonical=True)
    tree_digest = harness_digest(harness_files)
    _require(tree_digest == binding["harness"]["digest"], "HARNESS_BYTES_CHANGED")
    _require(summary.get("task_id") == binding["task_id"]
             and summary.get("domain") == binding["domain"]
             and type(summary.get("k")) is int and summary["k"] == k,
             "SUMMARY_TASK_BINDING_MISMATCH")
    _require(summary.get("status") == "ok" and summary.get("errors") == [],
             "SUMMARY_NOT_COMPLETE")
    modes, selections = summary.get("modes"), summary.get("selections")
    _require(type(modes) is dict and type(selections) is dict
             and mode in modes and mode in selections, "MODE_MISSING")
    record, selection = modes[mode], selections[mode]
    _require(type(record) is dict and type(selection) is dict, "MODE_RECORD_INVALID")
    for item in (record, selection):
        _require(item.get("mode") == mode and item.get("task_id") == binding["task_id"]
                 and type(item.get("k")) is int and item["k"] == k,
                 "MODE_TASK_BINDING_MISMATCH")
        _require(item.get("ok") is True, "MODE_NOT_COMPLETE")
    _require(record.get("errors") == [] and record.get("fell_back") == [],
             "REFINEMENT_ERROR_OR_FALLBACK")
    finals = [f"{'agg' if mode == 'agg' else 'c'}{i}" for i in range(1, k + 1)]
    _require(record.get("finals") == finals, "FINALS_INCOMPLETE")
    label = selection.get("chosen_label")
    _require(type(label) is str and label in finals, "SELECTION_NOT_A_FINAL")
    _require(selection.get("chosen_run_id") == binding["upstream_run_id"], "SELECTED_RUN_MISMATCH")
    _require(selection.get("fallback") is False and selection.get("error") == "",
             "SELECTION_ERROR_OR_FALLBACK")
    _require(selection.get("chosen_is_base") is False, "SELECTION_LABEL_CONFLICT")
    _require(selection.get("harness_fingerprint") == upstream_fingerprint(harness_files),
             "UPSTREAM_FINGERPRINT_MISMATCH")
    # Absolute chosen_run_dir is deliberately never read or turned into a capability.
    contracts.validate_scenario_shape(scenario)
    contracts.validate_configuration_shape(configuration)
    contracts.validate_run_draft_shape(draft)
    _require(draft["run_id"] == binding["native_run_id"], "NATIVE_RUN_MISMATCH")
    _require(configuration["procedure"]["instruction_bundle"] == binding["harness"],
             "CONFIGURATION_HARNESS_MISMATCH")
    _require(draft["evidence"]["output"] == binding["output"], "NATIVE_OUTPUT_MISMATCH")
    # This calls the incumbent graph/identity/validity owner, not a new validity rule.
    validity.evaluate_validity(scenario, configuration, experiment, draft)
    result = copy.deepcopy(draft)
    additions = [dict(binding[key], kind="OTHER") for key in
                 ("summary", "native_observation", "harness")]
    existing = {a["artifact_ref"]: a for a in result["evidence"]["artifacts"]}
    _require(len(existing) == len(result["evidence"]["artifacts"]), "DUPLICATE_NATIVE_ARTIFACT")
    for artifact in additions:
        prior = existing.get(artifact["artifact_ref"])
        _require(prior is None or prior == artifact, "NATIVE_ARTIFACT_CONFLICT")
        existing[artifact["artifact_ref"]] = artifact
    result["evidence"]["artifacts"] = [existing[key] for key in sorted(existing)]
    contracts.validate_run_draft_shape(result)
    return Harness2Import(result, expected_binding_digest, binding["summary"]["digest"],
                          tree_digest, binding["upstream_run_id"], draft["run_id"])


def finalize_selected_run(*, scenario: dict, configuration: dict, experiment: dict | None,
                          validator_id: str, validator_version: str, validator_code_ref: str,
                          validated_at: str, created_at: str, **inputs: Any) -> dict:
    """Recheck raw bytes and use the incumbent finalizer; no publication or new store."""
    imported = import_selected_run(scenario=scenario, configuration=configuration,
                                   experiment=experiment, **inputs)
    return validity.finalize_run_receipt(
        scenario, configuration, experiment, imported.draft,
        validator_id=validator_id, validator_version=validator_version,
        validator_code_ref=validator_code_ref, validated_at=validated_at,
        created_at=created_at,
    )


def configuration_lock(scenario_ref: dict, c: dict) -> str:
    """Factor lock over the declared comparison, not a lock invented by its first return."""
    return digest_value({
        "scenario": scenario_ref, "execution": c["execution"],
        "protected_source_ref": c["procedure"]["protected_source_ref"],
        "skillpack_source_ref": c["procedure"]["skillpack_source_ref"],
        "skillpack_version": c["procedure"]["skillpack_version"],
        "handoff": c["procedure"]["handoff"], "context": c["context"],
        "capabilities": c["capabilities"], "randomness": c["randomness"],
    })

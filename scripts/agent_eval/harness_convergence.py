"""Provider-free H1/H2 contracts for the Agent Evaluation successor wave.

This module is deliberately additive.  It creates no evaluator, store, runner,
provider path, lifecycle, routing, promotion, or execution authority.  It
produces two provenance-bound artifacts that plug into existing Agent
Evaluation v1 configuration and scorer evidence seams:

* an opaque holdout commitment that never persists holdout contents or paths;
* an environment manifest whose digest is bound by
  ``configuration.capabilities.environment_digest``.
"""
from __future__ import annotations

from typing import Any

from scripts.agent_eval.canonical import (
    add_document_digest,
    digest_value,
    parse_digest_string,
    parse_prefixed_uuid4,
    parse_source_qualified_ref,
    parse_utc_z,
    require_canonical_json_tree,
    verify_document_digest,
)
from scripts.agent_eval.contracts import (
    CONFIGURATION_SCHEMA,
    v_artifact_list,
    validate_configuration_shape,
)
from scripts.agent_eval.errors import ContractDefect, ContractError

HOLDOUT_COMMITMENT_SCHEMA = "mastermind.agent_evaluation_holdout_commitment.v1"
ENVIRONMENT_MANIFEST_SCHEMA = "mastermind.agent_evaluation_environment_manifest.v1"

EXPOSURE_STATES = frozenset({"SEALED_PRIVATE", "EXPOSED_DEVELOPMENT", "BURNED_PUBLIC"})
EXECUTION_MODES = frozenset({"FACTOR_LOCKED", "SYSTEM_REALISTIC"})
CLAIM_SCOPES = frozenset(
    {"FACTOR_LOCKED_STRUCTURAL_COMPARISON", "SYSTEM_REALISTIC_DESCRIPTIVE_OBSERVATION"}
)
RNG_POLICIES = frozenset({"DETERMINISTIC_SEED", "PREREGISTERED_REPLICATES", "OBSERVED_UNKNOWN"})

_HOLDOUT_FIELDS = frozenset(
    {
        "schema",
        "commitment_id",
        "task_class",
        "family",
        "sample_count",
        "content_digest",
        "source_ref",
        "committed_at",
        "privacy",
        "exposure_state",
        "commitment_digest",
    }
)
_MANIFEST_FIELDS = frozenset(
    {
        "schema",
        "manifest_id",
        "source_ref",
        "captured_at",
        "execution_mode",
        "claim_scope",
        "configuration_snapshot",
        "owner_native_evidence",
        "provider_principal_evidence",
        "grader_provenance",
        "rng_policy",
        "replicate_count",
        "authority",
        "promotion",
        "manifest_digest",
    }
)
_SNAPSHOT_FIELDS = frozenset({"execution", "procedure", "context", "capabilities", "randomness"})
_EXECUTION_FIELDS = frozenset(
    {
        "execution_surface",
        "execution_surface_version",
        "provider",
        "model_requested",
        "reasoning_effort",
        "auth_realm_class",
    }
)
_PROCEDURE_FIELDS = frozenset(
    {"protected_source_ref", "skillpack_source_ref", "skillpack_version", "instruction_bundle_digest"}
)
_CONTEXT_FIELDS = frozenset({"context_packet_digest", "retrieval_configuration_digest"})
_CAPABILITY_FIELDS = frozenset(
    {
        "profile_id",
        "profile_digest",
        "declared_capability_ids",
        "declared_tool_schema_digests",
        "sandbox_digest",
        "network_policy_digest",
    }
)
_RANDOMNESS_FIELDS = frozenset({"seed", "sampling_parameters_digest"})


def _raise(path: str, code: str, message: str) -> None:
    raise ContractError([ContractDefect(path, code, message)])


def _closed(value: Any, fields: frozenset[str], path: str) -> dict:
    if not isinstance(value, dict):
        _raise(path, "NOT_AN_OBJECT", "expected a JSON object")
    defects: list[ContractDefect] = []
    for key in value:
        if key not in fields:
            defects.append(ContractDefect(f"{path}.{key}", "UNKNOWN_FIELD", "field is not in the closed schema"))
    for key in fields:
        if key not in value:
            defects.append(ContractDefect(f"{path}.{key}", "FIELD_MISSING", "required field is missing"))
    if defects:
        raise ContractError(defects)
    require_canonical_json_tree(value, path)
    return value


def _string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value:
        _raise(path, "NOT_A_NONEMPTY_STRING", "expected a non-empty string")
    require_canonical_json_tree(value, path)
    return value


def _integer(value: Any, path: str, *, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        _raise(path, "NOT_AN_INT", "expected an integer")
    if value < minimum:
        _raise(path, "INT_BELOW_MINIMUM", f"value must be at least {minimum}")
    return value


def _enum(value: Any, allowed: frozenset[str], path: str) -> str:
    if value not in allowed:
        _raise(path, "NOT_IN_ENUM", f"value must be one of {sorted(allowed)}")
    return value


def _string_list(value: Any, path: str) -> list[str]:
    if not isinstance(value, list):
        _raise(path, "NOT_A_LIST", "expected a list")
    items = [_string(item, f"{path}[{index}]") for index, item in enumerate(value)]
    if items != sorted(set(items)):
        _raise(path, "LIST_NOT_SORTED_UNIQUE", "list must be sorted and contain no duplicates")
    return items


def _artifact_list(value: Any, path: str, *, nonempty: bool) -> list[dict]:
    items = v_artifact_list(value, path)
    if nonempty and not items:
        _raise(path, "EVIDENCE_REQUIRED", "at least one provenance-bearing artifact is required")
    return items


def _validate_snapshot(snapshot: Any, path: str = "$.configuration_snapshot") -> dict:
    _closed(snapshot, _SNAPSHOT_FIELDS, path)
    execution = _closed(snapshot["execution"], _EXECUTION_FIELDS, f"{path}.execution")
    for key in _EXECUTION_FIELDS:
        _string(execution[key], f"{path}.execution.{key}")

    procedure = _closed(snapshot["procedure"], _PROCEDURE_FIELDS, f"{path}.procedure")
    parse_source_qualified_ref(procedure["protected_source_ref"], f"{path}.procedure.protected_source_ref")
    parse_source_qualified_ref(procedure["skillpack_source_ref"], f"{path}.procedure.skillpack_source_ref")
    _string(procedure["skillpack_version"], f"{path}.procedure.skillpack_version")
    parse_digest_string(procedure["instruction_bundle_digest"], f"{path}.procedure.instruction_bundle_digest")

    context = _closed(snapshot["context"], _CONTEXT_FIELDS, f"{path}.context")
    parse_digest_string(context["context_packet_digest"], f"{path}.context.context_packet_digest")
    if context["retrieval_configuration_digest"] is not None:
        parse_digest_string(
            context["retrieval_configuration_digest"], f"{path}.context.retrieval_configuration_digest"
        )

    capabilities = _closed(snapshot["capabilities"], _CAPABILITY_FIELDS, f"{path}.capabilities")
    _string(capabilities["profile_id"], f"{path}.capabilities.profile_id")
    parse_digest_string(capabilities["profile_digest"], f"{path}.capabilities.profile_digest")
    _string_list(capabilities["declared_capability_ids"], f"{path}.capabilities.declared_capability_ids")
    tool_digests = capabilities["declared_tool_schema_digests"]
    if not isinstance(tool_digests, list):
        _raise(f"{path}.capabilities.declared_tool_schema_digests", "NOT_A_LIST", "expected a list")
    for index, digest in enumerate(tool_digests):
        parse_digest_string(digest, f"{path}.capabilities.declared_tool_schema_digests[{index}]")
    if tool_digests != sorted(set(tool_digests)):
        _raise(
            f"{path}.capabilities.declared_tool_schema_digests",
            "LIST_NOT_SORTED_UNIQUE",
            "list must be sorted and contain no duplicates",
        )
    parse_digest_string(capabilities["sandbox_digest"], f"{path}.capabilities.sandbox_digest")
    parse_digest_string(capabilities["network_policy_digest"], f"{path}.capabilities.network_policy_digest")

    randomness = _closed(snapshot["randomness"], _RANDOMNESS_FIELDS, f"{path}.randomness")
    if isinstance(randomness["seed"], bool) or not isinstance(randomness["seed"], int):
        _raise(f"{path}.randomness.seed", "NOT_AN_INT", "seed must be an integer")
    parse_digest_string(randomness["sampling_parameters_digest"], f"{path}.randomness.sampling_parameters_digest")
    return snapshot


def build_holdout_commitment(
    *,
    commitment_id: str,
    task_class: str,
    family: str,
    sealed_items: list[Any],
    source_ref: str,
    committed_at: str,
) -> dict:
    """Return an opaque commitment; sealed holdout contents never appear in it."""
    parse_prefixed_uuid4(commitment_id, "holdout", "$.commitment_id")
    _string(task_class, "$.task_class")
    _string(family, "$.family")
    if not isinstance(sealed_items, list) or not sealed_items:
        _raise("$.sealed_items", "HOLDOUT_ITEMS_REQUIRED", "sealed_items must be a non-empty list")
    require_canonical_json_tree(sealed_items, "$.sealed_items")
    parse_source_qualified_ref(source_ref, "$.source_ref")
    parse_utc_z(committed_at, "$.committed_at")
    document = {
        "schema": HOLDOUT_COMMITMENT_SCHEMA,
        "commitment_id": commitment_id,
        "task_class": task_class,
        "family": family,
        "sample_count": len(sealed_items),
        "content_digest": digest_value(sealed_items),
        "source_ref": source_ref,
        "committed_at": committed_at,
        "privacy": "PRIVATE",
        "exposure_state": "SEALED_PRIVATE",
    }
    result = add_document_digest(document, "commitment_digest")
    validate_holdout_commitment(result)
    return result


def validate_holdout_commitment(document: Any) -> str:
    _closed(document, _HOLDOUT_FIELDS, "$")
    _enum(document["schema"], frozenset({HOLDOUT_COMMITMENT_SCHEMA}), "$.schema")
    parse_prefixed_uuid4(document["commitment_id"], "holdout", "$.commitment_id")
    _string(document["task_class"], "$.task_class")
    _string(document["family"], "$.family")
    _integer(document["sample_count"], "$.sample_count", minimum=1)
    parse_digest_string(document["content_digest"], "$.content_digest")
    parse_source_qualified_ref(document["source_ref"], "$.source_ref")
    parse_utc_z(document["committed_at"], "$.committed_at")
    _enum(document["privacy"], frozenset({"PRIVATE"}), "$.privacy")
    _enum(document["exposure_state"], EXPOSURE_STATES, "$.exposure_state")
    parse_digest_string(document["commitment_digest"], "$.commitment_digest")
    verify_document_digest(document, "commitment_digest")
    return "HOLDOUT_COMMITMENT_VALID"


def verify_holdout_confirmation_eligibility(document: dict) -> str:
    validate_holdout_commitment(document)
    if document["exposure_state"] != "SEALED_PRIVATE":
        _raise(
            "$.exposure_state",
            "HOLDOUT_NOT_CONFIRMATION_ELIGIBLE",
            "confirmatory holdout must remain SEALED_PRIVATE",
        )
    return "HOLDOUT_CONFIRMATION_ELIGIBLE"


def build_environment_manifest(
    *,
    manifest_id: str,
    source_ref: str,
    captured_at: str,
    execution_mode: str,
    claim_scope: str,
    configuration_snapshot: dict,
    owner_native_evidence: list[dict],
    provider_principal_evidence: list[dict],
    grader_provenance: list[dict],
    rng_policy: str,
    replicate_count: int,
) -> dict:
    parse_prefixed_uuid4(manifest_id, "envmanifest", "$.manifest_id")
    parse_source_qualified_ref(source_ref, "$.source_ref")
    parse_utc_z(captured_at, "$.captured_at")
    _validate_snapshot(configuration_snapshot)
    document = {
        "schema": ENVIRONMENT_MANIFEST_SCHEMA,
        "manifest_id": manifest_id,
        "source_ref": source_ref,
        "captured_at": captured_at,
        "execution_mode": execution_mode,
        "claim_scope": claim_scope,
        "configuration_snapshot": configuration_snapshot,
        "owner_native_evidence": owner_native_evidence,
        "provider_principal_evidence": provider_principal_evidence,
        "grader_provenance": grader_provenance,
        "rng_policy": rng_policy,
        "replicate_count": replicate_count,
        "authority": "NONE",
        "promotion": "NONE",
    }
    result = add_document_digest(document, "manifest_digest")
    validate_environment_manifest(result)
    return result


def validate_environment_manifest(document: Any) -> str:
    _closed(document, _MANIFEST_FIELDS, "$")
    _enum(document["schema"], frozenset({ENVIRONMENT_MANIFEST_SCHEMA}), "$.schema")
    parse_prefixed_uuid4(document["manifest_id"], "envmanifest", "$.manifest_id")
    parse_source_qualified_ref(document["source_ref"], "$.source_ref")
    parse_utc_z(document["captured_at"], "$.captured_at")
    mode = _enum(document["execution_mode"], EXECUTION_MODES, "$.execution_mode")
    scope = _enum(document["claim_scope"], CLAIM_SCOPES, "$.claim_scope")
    _validate_snapshot(document["configuration_snapshot"])
    owner = _artifact_list(document["owner_native_evidence"], "$.owner_native_evidence", nonempty=True)
    provider = _artifact_list(
        document["provider_principal_evidence"], "$.provider_principal_evidence", nonempty=False
    )
    _artifact_list(document["grader_provenance"], "$.grader_provenance", nonempty=True)
    rng_policy = _enum(document["rng_policy"], RNG_POLICIES, "$.rng_policy")
    replicate_count = _integer(document["replicate_count"], "$.replicate_count", minimum=1)
    _enum(document["authority"], frozenset({"NONE"}), "$.authority")
    _enum(document["promotion"], frozenset({"NONE"}), "$.promotion")
    parse_digest_string(document["manifest_digest"], "$.manifest_digest")

    defects: list[ContractDefect] = []
    expected_scope = (
        "FACTOR_LOCKED_STRUCTURAL_COMPARISON"
        if mode == "FACTOR_LOCKED"
        else "SYSTEM_REALISTIC_DESCRIPTIVE_OBSERVATION"
    )
    if scope != expected_scope:
        defects.append(
            ContractDefect(
                "$.claim_scope", "CLAIM_SCOPE_MODE_MISMATCH", "claim_scope does not match execution_mode"
            )
        )
    if mode == "FACTOR_LOCKED" and not provider:
        defects.append(
            ContractDefect(
                "$.provider_principal_evidence",
                "PROVIDER_PRINCIPAL_EVIDENCE_REQUIRED",
                "FACTOR_LOCKED comparison requires owner-proven provider-principal evidence",
            )
        )
    if not owner:
        defects.append(
            ContractDefect(
                "$.owner_native_evidence", "OWNER_NATIVE_EVIDENCE_REQUIRED", "owner-native evidence is required"
            )
        )
    if rng_policy in {"PREREGISTERED_REPLICATES", "OBSERVED_UNKNOWN"} and replicate_count < 2:
        defects.append(
            ContractDefect(
                "$.replicate_count",
                "REPLICATES_REQUIRED_WHEN_RNG_UNSEEDED",
                "unseeded/unknown RNG requires at least two preregistered replicates",
            )
        )
    if defects:
        raise ContractError(defects)
    verify_document_digest(document, "manifest_digest")
    return "ENVIRONMENT_MANIFEST_VALID"


def _snapshot_from_configuration(configuration: dict) -> dict:
    retrieval = configuration["context"].get("retrieval_configuration")
    return {
        "execution": dict(configuration["execution"]),
        "procedure": {
            "protected_source_ref": configuration["procedure"]["protected_source_ref"],
            "skillpack_source_ref": configuration["procedure"]["skillpack_source_ref"],
            "skillpack_version": configuration["procedure"]["skillpack_version"],
            "instruction_bundle_digest": configuration["procedure"]["instruction_bundle"]["digest"],
        },
        "context": {
            "context_packet_digest": configuration["context"]["context_packet"]["digest"],
            "retrieval_configuration_digest": None if retrieval is None else retrieval["digest"],
        },
        "capabilities": {
            key: configuration["capabilities"][key]
            for key in (
                "profile_id",
                "profile_digest",
                "declared_capability_ids",
                "declared_tool_schema_digests",
                "sandbox_digest",
                "network_policy_digest",
            )
        },
        "randomness": dict(configuration["randomness"]),
    }


def verify_configuration_environment_binding(configuration: dict, manifest: dict) -> str:
    validate_configuration_shape(configuration)
    validate_environment_manifest(manifest)
    if configuration.get("schema") != CONFIGURATION_SCHEMA:
        _raise("$.configuration.schema", "CONFIGURATION_SCHEMA_MISMATCH", "unexpected configuration schema")
    defects: list[ContractDefect] = []
    actual_digest = configuration["capabilities"]["environment_digest"]
    if actual_digest != manifest["manifest_digest"]:
        defects.append(
            ContractDefect(
                "$.configuration.capabilities.environment_digest",
                "ENVIRONMENT_DIGEST_MISMATCH",
                "configuration environment_digest does not bind the manifest",
            )
        )
    actual_snapshot = _snapshot_from_configuration(configuration)
    if actual_snapshot != manifest["configuration_snapshot"]:
        defects.append(
            ContractDefect(
                "$.configuration_snapshot",
                "ENVIRONMENT_SNAPSHOT_MISMATCH",
                "configuration fields do not match the bound environment snapshot",
            )
        )
    if defects:
        raise ContractError(defects)
    return "CONFIGURATION_ENVIRONMENT_BINDING_VERIFIED"


def build_convergence_input_evidence(
    *, manifest_ref: str, manifest: dict, holdout_ref: str, holdout_commitment: dict
) -> list[dict]:
    """Return existing scorer-pass artifact pairs; no new evidence store is created."""
    validate_environment_manifest(manifest)
    verify_holdout_confirmation_eligibility(holdout_commitment)
    evidence = sorted(
        [
            {"artifact_ref": _string(manifest_ref, "$.manifest_ref"), "digest": manifest["manifest_digest"]},
            {
                "artifact_ref": _string(holdout_ref, "$.holdout_ref"),
                "digest": holdout_commitment["commitment_digest"],
            },
        ],
        key=lambda item: item["artifact_ref"],
    )
    return v_artifact_list(evidence, "$.input_evidence")

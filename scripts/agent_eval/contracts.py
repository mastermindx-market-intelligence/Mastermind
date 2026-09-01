"""EVAL-R0 closed contracts: scenario, configuration, experiment, run, run draft.

Implements design §7 and plan §5.1/§5.2/Tasks 2-4. Every persisted document
is a CLOSED object: unknown fields fail, missing required fields fail, and
every field carries an explicit grammar. Shape validators never consult a
resolver (that is graph verification's job, see verification.py) and never
read ambient state.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Callable

from scripts.agent_eval.canonical import (
    add_document_digest,
    digest_value,
    parse_decimal_string,
    parse_digest_string,
    parse_prefixed_uuid4,
    parse_source_qualified_ref,
    parse_utc_z,
    require_canonical_json_tree,
    verify_document_digest,
)
from scripts.agent_eval.errors import ContractDefect, ContractError

# ---------------------------------------------------------------------------
# Schema names (design §5.1 / plan §5.1)
# ---------------------------------------------------------------------------

SCENARIO_SCHEMA = "mastermind.agent_evaluation_scenario.v1"
CONFIGURATION_SCHEMA = "mastermind.agent_evaluation_configuration.v1"
EXPERIMENT_SCHEMA = "mastermind.agent_evaluation_experiment.v1"
RUN_SCHEMA = "mastermind.agent_evaluation_run.v1"
RUN_DRAFT_SCHEMA = "mastermind.agent_evaluation_run_draft.v1"

Validator = Callable[[Any, str], Any]

# ---------------------------------------------------------------------------
# Generic closed-object validation DSL
# ---------------------------------------------------------------------------


def validate_closed_object(
    document: Any,
    path: str,
    field_validators: dict[str, Validator],
    *,
    optional: frozenset = frozenset(),
) -> dict:
    """Validate a CLOSED JSON object: no unknown fields, no missing required
    fields, every present field runs its validator. Defects are collected
    and raised together (deterministic ordering via ContractError)."""
    if not isinstance(document, dict):
        raise ContractError([ContractDefect(path, "NOT_AN_OBJECT", "expected a JSON object")])
    defects: list[ContractDefect] = []
    allowed = set(field_validators)
    for key in document:
        if key not in allowed:
            defects.append(ContractDefect(f"{path}.{key}", "UNKNOWN_FIELD", "field is not part of the closed schema"))
    for key in field_validators:
        if key not in document and key not in optional:
            defects.append(ContractDefect(f"{path}.{key}", "FIELD_MISSING", "required field is missing"))
    if defects:
        raise ContractError(defects)
    result: dict[str, Any] = {}
    for key, validator in field_validators.items():
        if key not in document:
            continue
        try:
            result[key] = validator(document[key], f"{path}.{key}")
        except ContractError as exc:
            defects.extend(exc.defects)
    if defects:
        raise ContractError(defects)
    return result


def run_checks(*thunks: Callable[[], Any]) -> None:
    """Run each zero-arg thunk, collecting ContractError defects, then raise
    once with everything gathered (or return cleanly if none raised)."""
    defects: list[ContractDefect] = []
    for thunk in thunks:
        try:
            thunk()
        except ContractError as exc:
            defects.extend(exc.defects)
    if defects:
        raise ContractError(defects)


# ---------------------------------------------------------------------------
# Reusable field validators
# ---------------------------------------------------------------------------


def v_bool(value: Any, path: str) -> bool:
    if not isinstance(value, bool):
        raise ContractError([ContractDefect(path, "NOT_A_BOOL", "expected a boolean")])
    return value


def v_str(value: Any, path: str) -> str:
    if not isinstance(value, str) or value == "":
        raise ContractError([ContractDefect(path, "NOT_A_NONEMPTY_STRING", "expected a non-empty string")])
    require_canonical_json_tree(value, path)
    return value


def v_int(value: Any, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ContractError([ContractDefect(path, "NOT_AN_INT", "expected an integer")])
    require_canonical_json_tree(value, path)
    return value


def v_nonneg_int(value: Any, path: str) -> int:
    value = v_int(value, path)
    if value < 0:
        raise ContractError([ContractDefect(path, "NEGATIVE_NOT_ALLOWED", "value must be non-negative")])
    return value


def v_pos_int(value: Any, path: str) -> int:
    value = v_nonneg_int(value, path)
    if value < 1:
        raise ContractError([ContractDefect(path, "NOT_POSITIVE", "value must be positive")])
    return value


def v_enum(allowed: frozenset) -> Validator:
    def validator(value: Any, path: str) -> Any:
        if value not in allowed:
            raise ContractError(
                [ContractDefect(path, "NOT_IN_ENUM", f"value must be one of {sorted(allowed)}")]
            )
        return value

    return validator


def v_optional(inner: Validator) -> Validator:
    def validator(value: Any, path: str) -> Any:
        if value is None:
            return None
        return inner(value, path)

    return validator


def v_digest(value: Any, path: str) -> str:
    return parse_digest_string(value, path)


def v_source_ref(value: Any, path: str) -> str:
    return parse_source_qualified_ref(value, path)


def v_timestamp(value: Any, path: str) -> str:
    parse_utc_z(value, path)
    return value


def v_decimal(value: Any, path: str) -> str:
    return parse_decimal_string(value, path)


def v_artifact_pair(value: Any, path: str) -> dict:
    return validate_closed_object(value, path, {"artifact_ref": v_str, "digest": v_digest})


def v_list_of(item_validator: Validator) -> Validator:
    def validator(value: Any, path: str) -> list:
        if not isinstance(value, list):
            raise ContractError([ContractDefect(path, "NOT_A_LIST", "expected a list")])
        defects: list[ContractDefect] = []
        items = []
        for index, item in enumerate(value):
            try:
                items.append(item_validator(item, f"{path}[{index}]"))
            except ContractError as exc:
                defects.extend(exc.defects)
        if defects:
            raise ContractError(defects)
        return items

    return validator


def v_sorted_unique_str_list(value: Any, path: str) -> list[str]:
    items = v_list_of(v_str)(value, path)
    if items != sorted(items):
        raise ContractError([ContractDefect(path, "LIST_NOT_SORTED", "list must be sorted")])
    if len(set(items)) != len(items):
        raise ContractError([ContractDefect(path, "LIST_HAS_DUPLICATES", "list must not contain duplicates")])
    return items


def v_sorted_unique_digest_list(value: Any, path: str) -> list[str]:
    items = v_list_of(v_digest)(value, path)
    if items != sorted(items):
        raise ContractError([ContractDefect(path, "LIST_NOT_SORTED", "list must be sorted")])
    if len(set(items)) != len(items):
        raise ContractError([ContractDefect(path, "LIST_HAS_DUPLICATES", "list must not contain duplicates")])
    return items


def v_artifact_list(value: Any, path: str) -> list[dict]:
    items = v_list_of(v_artifact_pair)(value, path)
    refs = [item["artifact_ref"] for item in items]
    digests = [item["digest"] for item in items]
    defects: list[ContractDefect] = []
    if refs != sorted(refs):
        defects.append(ContractDefect(path, "LIST_NOT_SORTED", "artifact list must be sorted by artifact_ref"))
    if len(set(refs)) != len(refs):
        defects.append(ContractDefect(path, "DUPLICATE_ARTIFACT_REF", "artifact list has duplicate artifact_ref"))
    if len(set(digests)) != len(digests):
        defects.append(ContractDefect(path, "DUPLICATE_ARTIFACT_DIGEST", "artifact list has duplicate digest"))
    if defects:
        raise ContractError(defects)
    return items


# ---------------------------------------------------------------------------
# ID grammar
# ---------------------------------------------------------------------------

_SLUG_RE = r"[a-z0-9][a-z0-9_-]{0,63}"
_SCENARIO_ID_RE = re.compile(rf"^scenario:({_SLUG_RE}):({_SLUG_RE})$")
_SCENARIO_FAMILY_RE = re.compile(r"^mastermind\.[a-z][a-z0-9_]*\.v[1-9][0-9]*$")
_SCORER_ID_RE = re.compile(r"^mastermind\.[a-z][a-z0-9_]*\.v[1-9][0-9]*$")
_ARM_ID_RE = re.compile(rf"^{_SLUG_RE}$")


def parse_scenario_id(value: Any, path: str = "$") -> tuple[str, str]:
    if not isinstance(value, str):
        raise ContractError([ContractDefect(path, "SCENARIO_ID_NOT_STRING", "scenario_id must be a string")])
    match = _SCENARIO_ID_RE.match(value)
    if not match:
        raise ContractError(
            [ContractDefect(path, "SCENARIO_ID_SHAPE", "scenario_id must match scenario:<family>:<case>")]
        )
    return match.group(1), match.group(2)


def v_scenario_id(value: Any, path: str) -> str:
    parse_scenario_id(value, path)
    return value


def v_scenario_family(value: Any, path: str) -> str:
    if not isinstance(value, str) or not _SCENARIO_FAMILY_RE.match(value):
        raise ContractError(
            [
                ContractDefect(
                    path,
                    "SCENARIO_FAMILY_SHAPE",
                    "scenario_family must match mastermind.<task_family>.v<integer> (design §5.1)",
                )
            ]
        )
    return value


def v_scorer_id(value: Any, path: str) -> str:
    if not isinstance(value, str) or not _SCORER_ID_RE.match(value):
        raise ContractError(
            [ContractDefect(path, "SCORER_ID_SHAPE", "scorer id must match mastermind.<name>.v<integer>")]
        )
    return value


def parse_configuration_id(value: Any, path: str = "$"):
    return parse_prefixed_uuid4(value, "configuration", path)


def v_configuration_id(value: Any, path: str) -> str:
    parse_configuration_id(value, path)
    return value


def parse_experiment_id(value: Any, path: str = "$"):
    return parse_prefixed_uuid4(value, "experiment", path)


def v_experiment_id(value: Any, path: str) -> str:
    parse_experiment_id(value, path)
    return value


def parse_run_id(value: Any, path: str = "$"):
    return parse_prefixed_uuid4(value, "run", path)


def v_run_id(value: Any, path: str) -> str:
    parse_run_id(value, path)
    return value


def v_arm_id(value: Any, path: str) -> str:
    if not isinstance(value, str) or not _ARM_ID_RE.match(value):
        raise ContractError([ContractDefect(path, "ARM_ID_SHAPE", "arm_id must be a lower-case slug")])
    return value


def v_corpus_revision(value: Any, path: str) -> str:
    return v_source_ref(value, path)


# ---------------------------------------------------------------------------
# Scenario nested objects
# ---------------------------------------------------------------------------

_RISK_TIERS = frozenset({"LOW", "MEDIUM", "HIGH", "CRITICAL"})
_NETWORK_POLICIES = frozenset({"DENY_ALL", "ALLOWLIST"})
_EFFECT_MODES = frozenset({"NO_EFFECT_ONLY", "DECLARED_EFFECT_ALLOWED"})
_PRIVACY_CLASSIFICATIONS = frozenset({"PUBLIC_SAFE", "PRIVATE_RESTRICTED"})
_RETENTION_CLASSES = frozenset({"EPHEMERAL", "BOUNDED", "DURABLE_SANITIZED"})


def _v_temporal(value: Any, path: str) -> dict:
    return validate_closed_object(
        value, path, {"cutoff_at": v_timestamp, "authored_at": v_timestamp}
    )


def _v_source_policy(value: Any, path: str) -> dict:
    return validate_closed_object(
        value,
        path,
        {
            "allowlist_artifacts": v_artifact_list,
            "denylist_refs": v_sorted_unique_str_list,
            "solution_refs_hidden": v_sorted_unique_str_list,
        },
    )


def _v_capability_policy(value: Any, path: str) -> dict:
    return validate_closed_object(
        value,
        path,
        {
            "profile_id": v_str,
            "profile_digest": v_digest,
            "allowed_capability_ids": v_sorted_unique_str_list,
            "forbidden_capability_ids": v_sorted_unique_str_list,
            "allowed_tool_schema_digests": v_sorted_unique_digest_list,
        },
    )


def _v_execution_policy(value: Any, path: str) -> dict:
    return validate_closed_object(
        value,
        path,
        {
            "fresh_process_required": v_bool,
            "fresh_workspace_required": v_bool,
            "fresh_session_required": v_bool,
            "resume_allowed": v_bool,
            "network_policy": v_enum(_NETWORK_POLICIES),
            "network_allowlist": v_sorted_unique_str_list,
            "max_elapsed_ms": v_pos_int,
            "max_tool_calls": v_pos_int,
            "allowed_degradations": v_sorted_unique_str_list,
        },
    )


def _v_effect_policy(value: Any, path: str) -> dict:
    return validate_closed_object(
        value,
        path,
        {"mode": v_enum(_EFFECT_MODES), "allowed_operation_refs": v_sorted_unique_str_list},
    )


def _v_scoring_policy(value: Any, path: str) -> dict:
    return validate_closed_object(
        value,
        path,
        {
            "required_scorers": v_list_of(v_scorer_id),
            "optional_scorers": v_list_of(v_scorer_id),
            "required_dimensions": v_sorted_unique_str_list,
        },
    )


def _v_privacy(value: Any, path: str) -> dict:
    return validate_closed_object(
        value,
        path,
        {
            "classification": v_enum(_PRIVACY_CLASSIFICATIONS),
            "model_visible_artifact_refs": v_sorted_unique_str_list,
            "retention_class": v_enum(_RETENTION_CLASSES),
        },
    )


def _v_authorship(value: Any, path: str) -> dict:
    return validate_closed_object(value, path, {"author_ref": v_str, "independent_reviewer_ref": v_str})


_SCENARIO_FIELDS: dict[str, Validator] = {
    "schema": v_enum(frozenset({SCENARIO_SCHEMA})),
    "scenario_id": v_scenario_id,
    "scenario_version": v_pos_int,
    "scenario_family": v_scenario_family,
    "corpus_revision": v_corpus_revision,
    "risk_tier": v_enum(_RISK_TIERS),
    "objective": v_str,
    "input_fixture": v_artifact_pair,
    "expected_contract": v_artifact_pair,
    "temporal": _v_temporal,
    "source_policy": _v_source_policy,
    "capability_policy": _v_capability_policy,
    "execution_policy": _v_execution_policy,
    "effect_policy": _v_effect_policy,
    "scoring_policy": _v_scoring_policy,
    "privacy": _v_privacy,
    "authorship": _v_authorship,
    "supersedes": v_optional(v_scenario_id),
    "scenario_digest": v_digest,
}


def _scenario_cross_field_defects(document: dict) -> list[ContractDefect]:
    defects: list[ContractDefect] = []
    execution_policy = document.get("execution_policy", {})
    if isinstance(execution_policy, dict):
        network_policy = execution_policy.get("network_policy")
        allowlist = execution_policy.get("network_allowlist")
        if isinstance(allowlist, list):
            if network_policy == "DENY_ALL" and allowlist:
                defects.append(
                    ContractDefect(
                        "$.execution_policy.network_allowlist",
                        "DENY_ALL_REQUIRES_EMPTY_ALLOWLIST",
                        "DENY_ALL network policy requires an empty network_allowlist",
                    )
                )
            if network_policy == "ALLOWLIST" and not allowlist:
                defects.append(
                    ContractDefect(
                        "$.execution_policy.network_allowlist",
                        "ALLOWLIST_REQUIRES_NONEMPTY",
                        "ALLOWLIST network policy requires a nonempty network_allowlist",
                    )
                )
    effect_policy = document.get("effect_policy", {})
    if isinstance(effect_policy, dict):
        mode = effect_policy.get("mode")
        refs = effect_policy.get("allowed_operation_refs")
        if isinstance(refs, list):
            if mode == "NO_EFFECT_ONLY" and refs:
                defects.append(
                    ContractDefect(
                        "$.effect_policy.allowed_operation_refs",
                        "NO_EFFECT_ONLY_REQUIRES_EMPTY_REFS",
                        "NO_EFFECT_ONLY requires an empty allowed_operation_refs",
                    )
                )
            if mode == "DECLARED_EFFECT_ALLOWED" and not refs:
                defects.append(
                    ContractDefect(
                        "$.effect_policy.allowed_operation_refs",
                        "DECLARED_EFFECT_ALLOWED_REQUIRES_NONEMPTY",
                        "DECLARED_EFFECT_ALLOWED requires a nonempty allowed_operation_refs",
                    )
                )
    source_policy = document.get("source_policy", {})
    if isinstance(source_policy, dict):
        hidden = source_policy.get("solution_refs_hidden")
        denylist = source_policy.get("denylist_refs")
        if isinstance(hidden, list) and isinstance(denylist, list):
            if not set(hidden).issubset(set(denylist)):
                defects.append(
                    ContractDefect(
                        "$.source_policy.solution_refs_hidden",
                        "HIDDEN_SOLUTION_NOT_IN_DENYLIST",
                        "solution_refs_hidden must be a subset of denylist_refs",
                    )
                )
    temporal = document.get("temporal", {})
    if isinstance(temporal, dict) and isinstance(temporal.get("cutoff_at"), str) and isinstance(
        temporal.get("authored_at"), str
    ):
        try:
            cutoff = parse_utc_z(temporal["cutoff_at"])
            authored = parse_utc_z(temporal["authored_at"])
        except ContractError:
            pass
        else:
            if cutoff > authored:
                defects.append(
                    ContractDefect(
                        "$.temporal.cutoff_at",
                        "CUTOFF_AFTER_AUTHORED",
                        "temporal.cutoff_at must be at or before temporal.authored_at",
                    )
                )
    privacy = document.get("privacy", {})
    source_policy_allow = source_policy.get("allowlist_artifacts") if isinstance(source_policy, dict) else None
    if isinstance(privacy, dict) and isinstance(source_policy_allow, list):
        visible_refs = set(privacy.get("model_visible_artifact_refs") or [])
        allowed_refs = {
            item["artifact_ref"] for item in source_policy_allow if isinstance(item, dict) and "artifact_ref" in item
        }
        input_fixture = document.get("input_fixture")
        expected_contract = document.get("expected_contract")
        for artifact in (input_fixture, expected_contract):
            if isinstance(artifact, dict) and "artifact_ref" in artifact:
                allowed_refs.add(artifact["artifact_ref"])
        if not visible_refs.issubset(allowed_refs):
            defects.append(
                ContractDefect(
                    "$.privacy.model_visible_artifact_refs",
                    "PRIVACY_REF_NOT_ALLOWLISTED",
                    "model_visible_artifact_refs must be a subset of allowlisted/fixture artifact refs",
                )
            )
    authorship = document.get("authorship", {})
    if isinstance(authorship, dict) and authorship.get("author_ref") == authorship.get("independent_reviewer_ref"):
        if authorship.get("author_ref") is not None:
            defects.append(
                ContractDefect(
                    "$.authorship.independent_reviewer_ref",
                    "REVIEWER_NOT_INDEPENDENT",
                    "independent_reviewer_ref must differ from author_ref",
                )
            )
    scenario_id = document.get("scenario_id")
    supersedes = document.get("supersedes")
    if isinstance(scenario_id, str) and isinstance(supersedes, str):
        try:
            family, _case = parse_scenario_id(scenario_id)
            super_family, _super_case = parse_scenario_id(supersedes)
        except ContractError:
            pass
        else:
            if family != super_family or _case != _super_case:
                defects.append(
                    ContractDefect(
                        "$.supersedes",
                        "SUPERSEDES_LINEAGE_MISMATCH",
                        "supersedes must reference an earlier version of the same scenario family/case",
                    )
                )
            elif document.get("scenario_version") == 1:
                defects.append(
                    ContractDefect(
                        "$.supersedes",
                        "SUPERSEDES_ON_FIRST_VERSION",
                        "scenario_version 1 must not supersede another version",
                    )
                )
    return defects


def _check_scenario_fields(document: Any, *, require_digest: bool) -> dict:
    optional = frozenset({"scenario_digest"}) if not require_digest else frozenset()
    validated = validate_closed_object(document, "$", _SCENARIO_FIELDS, optional=optional)
    cross_defects = _scenario_cross_field_defects(document if isinstance(document, dict) else {})
    if cross_defects:
        raise ContractError(cross_defects)
    if require_digest:
        verify_document_digest(document, "scenario_digest")
    return validated


def validate_scenario_shape(document: Any) -> str:
    """Validate a persisted scenario document. Returns literal 'SHAPE_VALID'."""
    _check_scenario_fields(document, require_digest=True)
    return "SHAPE_VALID"


def build_scenario(fields: dict) -> dict:
    """Assemble, validate, and digest a scenario document from field values.

    ``fields`` must NOT include ``schema`` or ``scenario_digest``.
    """
    if not isinstance(fields, dict) or "schema" in fields or "scenario_digest" in fields:
        raise ContractError(
            [ContractDefect("$", "BUILD_FIELDS_MUST_EXCLUDE_SCHEMA_AND_DIGEST", "fields must omit schema and scenario_digest")]
        )
    document = {"schema": SCENARIO_SCHEMA, **fields}
    _check_scenario_fields(document, require_digest=False)
    return add_document_digest(document, "scenario_digest")


# ---------------------------------------------------------------------------
# Configuration nested objects
# ---------------------------------------------------------------------------

_REASONING_EFFORTS = frozenset({"low", "medium", "high"})
_AUTH_REALM_CLASS_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")


def v_auth_realm_class(value: Any, path: str) -> str:
    if not isinstance(value, str) or not _AUTH_REALM_CLASS_RE.match(value):
        raise ContractError(
            [ContractDefect(path, "AUTH_REALM_CLASS_SHAPE", "auth_realm_class must be an upper-case identifier")]
        )
    return value


def _v_execution(value: Any, path: str) -> dict:
    return validate_closed_object(
        value,
        path,
        {
            "execution_surface": v_str,
            "execution_surface_version": v_str,
            "provider": v_str,
            "model_requested": v_str,
            "reasoning_effort": v_enum(_REASONING_EFFORTS),
            "auth_realm_class": v_auth_realm_class,
        },
    )


def _v_procedure(value: Any, path: str) -> dict:
    return validate_closed_object(
        value,
        path,
        {
            "protected_source_ref": v_source_ref,
            "skillpack_source_ref": v_source_ref,
            "skillpack_version": v_str,
            "instruction_bundle": v_artifact_pair,
            "handoff": v_optional(v_artifact_pair),
        },
    )


def _v_context(value: Any, path: str) -> dict:
    return validate_closed_object(
        value,
        path,
        {
            "context_packet": v_artifact_pair,
            "retrieval_configuration": v_optional(v_artifact_pair),
        },
    )


def _v_capabilities_config(value: Any, path: str) -> dict:
    return validate_closed_object(
        value,
        path,
        {
            "profile_id": v_str,
            "profile_digest": v_digest,
            "declared_capability_ids": v_sorted_unique_str_list,
            "declared_tool_schema_digests": v_sorted_unique_digest_list,
            "sandbox_digest": v_digest,
            "network_policy_digest": v_digest,
            "environment_digest": v_digest,
        },
    )


def _v_randomness(value: Any, path: str) -> dict:
    return validate_closed_object(value, path, {"seed": v_int, "sampling_parameters_digest": v_digest})


_CONFIGURATION_FIELDS: dict[str, Validator] = {
    "schema": v_enum(frozenset({CONFIGURATION_SCHEMA})),
    "configuration_id": v_configuration_id,
    "execution": _v_execution,
    "procedure": _v_procedure,
    "context": _v_context,
    "capabilities": _v_capabilities_config,
    "randomness": _v_randomness,
    "authorship": _v_authorship,
    "created_at": v_timestamp,
    "supersedes": v_optional(v_configuration_id),
    "configuration_digest": v_digest,
}


def _configuration_cross_field_defects(document: dict) -> list[ContractDefect]:
    defects: list[ContractDefect] = []
    authorship = document.get("authorship", {})
    if isinstance(authorship, dict) and authorship.get("author_ref") == authorship.get("independent_reviewer_ref"):
        if authorship.get("author_ref") is not None:
            defects.append(
                ContractDefect(
                    "$.authorship.independent_reviewer_ref",
                    "REVIEWER_NOT_INDEPENDENT",
                    "independent_reviewer_ref must differ from author_ref",
                )
            )
    supersedes = document.get("supersedes")
    configuration_id = document.get("configuration_id")
    if isinstance(supersedes, str) and supersedes == configuration_id:
        defects.append(
            ContractDefect(
                "$.supersedes", "SUPERSEDES_SELF", "configuration must not supersede its own configuration_id"
            )
        )
    return defects


def _check_configuration_fields(document: Any, *, require_digest: bool) -> dict:
    optional = frozenset({"configuration_digest"}) if not require_digest else frozenset()
    validated = validate_closed_object(document, "$", _CONFIGURATION_FIELDS, optional=optional)
    cross_defects = _configuration_cross_field_defects(document if isinstance(document, dict) else {})
    if cross_defects:
        raise ContractError(cross_defects)
    if require_digest:
        verify_document_digest(document, "configuration_digest")
    return validated


def validate_configuration_shape(document: Any) -> str:
    """Validate a persisted configuration document. Returns 'SHAPE_VALID'."""
    _check_configuration_fields(document, require_digest=True)
    return "SHAPE_VALID"


def build_configuration(fields: dict) -> dict:
    """Assemble, validate, and digest a configuration document from field values.

    ``fields`` must NOT include ``schema`` or ``configuration_digest``.
    """
    if not isinstance(fields, dict) or "schema" in fields or "configuration_digest" in fields:
        raise ContractError(
            [
                ContractDefect(
                    "$", "BUILD_FIELDS_MUST_EXCLUDE_SCHEMA_AND_DIGEST", "fields must omit schema and configuration_digest"
                )
            ]
        )
    document = {"schema": CONFIGURATION_SCHEMA, **fields}
    _check_configuration_fields(document, require_digest=False)
    return add_document_digest(document, "configuration_digest")


# ---------------------------------------------------------------------------
# Scenario <-> configuration compatibility (Task 2)
# ---------------------------------------------------------------------------


def compute_scenario_network_policy_digest(scenario: dict) -> str:
    policy = scenario["execution_policy"]
    return digest_value(
        {"network_policy": policy["network_policy"], "network_allowlist": list(policy["network_allowlist"])}
    )


def scenario_configuration_defects(scenario: dict, configuration: dict) -> tuple[ContractDefect, ...]:
    """Return compatibility defects between a scenario and a configuration.

    Empty tuple means compatible. Never raises for an incompatible pair —
    the caller (graph verification / finalizer) decides how to react.
    """
    defects: list[ContractDefect] = []
    cap_policy = scenario.get("capability_policy", {})
    cap = configuration.get("capabilities", {})
    if cap.get("profile_id") != cap_policy.get("profile_id") or cap.get("profile_digest") != cap_policy.get(
        "profile_digest"
    ):
        defects.append(
            ContractDefect(
                "$.capabilities.profile_id",
                "CAPABILITY_PROFILE_MISMATCH",
                "configuration capability profile does not match scenario capability policy",
            )
        )
    allowed = set(cap_policy.get("allowed_capability_ids", []))
    forbidden = set(cap_policy.get("forbidden_capability_ids", []))
    declared = set(cap.get("declared_capability_ids", []))
    if not declared.issubset(allowed):
        defects.append(
            ContractDefect(
                "$.capabilities.declared_capability_ids",
                "CAPABILITY_NOT_ALLOWED",
                "declared capability is not in the scenario's allowed set",
            )
        )
    if declared & forbidden:
        defects.append(
            ContractDefect(
                "$.capabilities.declared_capability_ids",
                "CAPABILITY_FORBIDDEN",
                "declared capability is in the scenario's forbidden set",
            )
        )
    allowed_tools = set(cap_policy.get("allowed_tool_schema_digests", []))
    declared_tools = set(cap.get("declared_tool_schema_digests", []))
    if not declared_tools.issubset(allowed_tools):
        defects.append(
            ContractDefect(
                "$.capabilities.declared_tool_schema_digests",
                "TOOL_SCHEMA_NOT_ALLOWED",
                "declared tool schema digest is not in the scenario's allowed set",
            )
        )
    try:
        expected_network_digest = compute_scenario_network_policy_digest(scenario)
    except KeyError:
        expected_network_digest = None
    if expected_network_digest is not None and cap.get("network_policy_digest") != expected_network_digest:
        defects.append(
            ContractDefect(
                "$.capabilities.network_policy_digest",
                "NETWORK_POLICY_DIGEST_MISMATCH",
                "configuration network-policy digest does not match scenario network policy",
            )
        )
    return tuple(sorted(defects))


# ---------------------------------------------------------------------------
# Experiment contract (design §7.3, plan Task 3)
# ---------------------------------------------------------------------------

_PAIRING_METHODS = frozenset({"PAIRED_BY_SCENARIO", "BLOCKED", "UNPAIRED"})
_STOPPING_RULE_KINDS = frozenset({"FIXED_REPLICATES_PER_ARM"})
_EXPERIMENT_PHASES = frozenset({"RETROSPECTIVE", "REPLAY", "PROSPECTIVE_SHADOW", "CANARY", "PROMOTED"})


def _v_scenario_ref(value: Any, path: str) -> dict:
    return validate_closed_object(
        value,
        path,
        {
            "scenario_id": v_scenario_id,
            "scenario_version": v_pos_int,
            "scenario_digest": v_digest,
            "corpus_revision": v_corpus_revision,
        },
    )


def _v_arm(value: Any, path: str) -> dict:
    return validate_closed_object(
        value,
        path,
        {"arm_id": v_arm_id, "configuration_id": v_configuration_id, "configuration_digest": v_digest},
    )


def _v_pairing(value: Any, path: str) -> dict:
    return validate_closed_object(value, path, {"method": v_enum(_PAIRING_METHODS), "random_seed": v_optional(v_int)})


def _v_stopping_rule(value: Any, path: str) -> dict:
    return validate_closed_object(value, path, {"kind": v_enum(_STOPPING_RULE_KINDS), "value": v_pos_int})


def _v_scenario_ref_list(value: Any, path: str) -> list[dict]:
    items = v_list_of(_v_scenario_ref)(value, path)
    keys = [(item["scenario_id"], item["scenario_version"]) for item in items]
    defects: list[ContractDefect] = []
    if not items:
        defects.append(ContractDefect(path, "EMPTY_LIST", "scenario_refs must be nonempty"))
    if keys != sorted(keys):
        defects.append(
            ContractDefect(path, "LIST_NOT_SORTED", "scenario_refs must be sorted by (scenario_id, scenario_version)")
        )
    if len(set(keys)) != len(keys):
        defects.append(
            ContractDefect(path, "LIST_HAS_DUPLICATES", "scenario_refs must not repeat the same scenario_id/version")
        )
    if defects:
        raise ContractError(defects)
    return items


def _v_arm_list(value: Any, path: str) -> list[dict]:
    items = v_list_of(_v_arm)(value, path)
    arm_ids = [item["arm_id"] for item in items]
    config_ids = [item["configuration_id"] for item in items]
    config_digests = [item["configuration_digest"] for item in items]
    defects: list[ContractDefect] = []
    if len(items) < 2:
        defects.append(ContractDefect(path, "TOO_FEW_ARMS", "an experiment must declare at least two unique arms"))
    if arm_ids != sorted(arm_ids):
        defects.append(ContractDefect(path, "LIST_NOT_SORTED", "arms must be sorted by arm_id"))
    if len(set(arm_ids)) != len(arm_ids):
        defects.append(ContractDefect(path, "LIST_HAS_DUPLICATES", "arm_id values must be unique"))
    if len(set(config_ids)) != len(config_ids):
        defects.append(
            ContractDefect(path, "DUPLICATE_ARM_CONFIGURATION_ID", "each arm must bind a distinct configuration_id")
        )
    if len(set(config_digests)) != len(config_digests):
        defects.append(
            ContractDefect(
                path, "DUPLICATE_ARM_CONFIGURATION_DIGEST", "each arm must bind a distinct configuration_digest"
            )
        )
    if defects:
        raise ContractError(defects)
    return items


_EXPERIMENT_FIELDS: dict[str, Validator] = {
    "schema": v_enum(frozenset({EXPERIMENT_SCHEMA})),
    "experiment_id": v_experiment_id,
    "scenario_refs": _v_scenario_ref_list,
    "arms": _v_arm_list,
    "pairing": _v_pairing,
    "replicates_per_arm_target": v_pos_int,
    "stopping_rule": _v_stopping_rule,
    "primary_dimensions": v_sorted_unique_str_list,
    "guardrail_dimensions": v_sorted_unique_str_list,
    "analysis_version": v_str,
    "phase": v_enum(_EXPERIMENT_PHASES),
    "authorship": _v_authorship,
    "created_at": v_timestamp,
    "experiment_digest": v_digest,
}


def _experiment_cross_field_defects(document: dict) -> list[ContractDefect]:
    defects: list[ContractDefect] = []
    primary = set(document.get("primary_dimensions") or [])
    guardrail = set(document.get("guardrail_dimensions") or [])
    if primary & guardrail:
        defects.append(
            ContractDefect(
                "$.guardrail_dimensions",
                "DIMENSION_NOT_DISJOINT",
                "primary_dimensions and guardrail_dimensions must be disjoint",
            )
        )
    stopping_rule = document.get("stopping_rule")
    if isinstance(stopping_rule, dict) and stopping_rule.get("value") != document.get("replicates_per_arm_target"):
        defects.append(
            ContractDefect(
                "$.stopping_rule.value",
                "STOPPING_RULE_MISMATCH",
                "stopping_rule.value must equal replicates_per_arm_target",
            )
        )
    pairing = document.get("pairing")
    if isinstance(pairing, dict):
        method = pairing.get("method")
        seed = pairing.get("random_seed")
        if method == "BLOCKED" and seed is None:
            defects.append(
                ContractDefect(
                    "$.pairing.random_seed", "BLOCKED_REQUIRES_SEED", "BLOCKED pairing requires a non-null random_seed"
                )
            )
        if method in {"PAIRED_BY_SCENARIO", "UNPAIRED"} and seed is not None:
            defects.append(
                ContractDefect(
                    "$.pairing.random_seed",
                    "SEED_NOT_ALLOWED_EXCEPT_BLOCKED",
                    "random_seed must be null except for BLOCKED pairing",
                )
            )
    authorship = document.get("authorship")
    if isinstance(authorship, dict) and authorship.get("author_ref") == authorship.get("independent_reviewer_ref"):
        if authorship.get("author_ref") is not None:
            defects.append(
                ContractDefect(
                    "$.authorship.independent_reviewer_ref",
                    "REVIEWER_NOT_INDEPENDENT",
                    "independent_reviewer_ref must differ from author_ref",
                )
            )
    return defects


def _check_experiment_fields(document: Any, *, require_digest: bool) -> dict:
    optional = frozenset({"experiment_digest"}) if not require_digest else frozenset()
    validated = validate_closed_object(document, "$", _EXPERIMENT_FIELDS, optional=optional)
    cross_defects = _experiment_cross_field_defects(document if isinstance(document, dict) else {})
    if cross_defects:
        raise ContractError(cross_defects)
    if require_digest:
        verify_document_digest(document, "experiment_digest")
    return validated


def validate_experiment_shape(document: Any) -> str:
    """Validate a persisted experiment document. Returns 'SHAPE_VALID'."""
    _check_experiment_fields(document, require_digest=True)
    return "SHAPE_VALID"


def build_experiment(fields: dict) -> dict:
    """Assemble, validate, and digest an experiment document from field values.

    ``fields`` must NOT include ``schema`` or ``experiment_digest``.
    """
    if not isinstance(fields, dict) or "schema" in fields or "experiment_digest" in fields:
        raise ContractError(
            [
                ContractDefect(
                    "$", "BUILD_FIELDS_MUST_EXCLUDE_SCHEMA_AND_DIGEST", "fields must omit schema and experiment_digest"
                )
            ]
        )
    document = {"schema": EXPERIMENT_SCHEMA, **fields}
    _check_experiment_fields(document, require_digest=False)
    return add_document_digest(document, "experiment_digest")


# ---------------------------------------------------------------------------
# Generic persisted-schema dispatch (extended by later tasks)
# ---------------------------------------------------------------------------

_SHAPE_VALIDATORS: dict[str, Callable[[Any], str]] = {
    SCENARIO_SCHEMA: validate_scenario_shape,
    CONFIGURATION_SCHEMA: validate_configuration_shape,
    EXPERIMENT_SCHEMA: validate_experiment_shape,
}


def register_shape_validator(schema: str, validator: Callable[[Any], str]) -> None:
    """Register a persisted-schema validator (used by verification.py/scoring.py
    to extend the generic dispatcher without a circular import at module load
    time)."""
    _SHAPE_VALIDATORS[schema] = validator


def validate_document_shape(document: Any) -> str:
    """Generic persisted-schema dispatch. Rejects the transient draft schema
    and any unknown schema. Returns the literal scope 'SHAPE_VALID'."""
    if not isinstance(document, dict) or "schema" not in document:
        raise ContractError([ContractDefect("$", "SCHEMA_MISSING", "document has no schema field")])
    schema = document["schema"]
    if schema == RUN_DRAFT_SCHEMA:
        raise ContractError(
            [ContractDefect("$.schema", "DRAFT_SCHEMA_REJECTED", "draft schema is not a persisted artifact")]
        )
    validator = _SHAPE_VALIDATORS.get(schema)
    if validator is None:
        # scorer-pass / evidence-ref validators live in scoring.py; import
        # lazily to avoid a circular import at module load time (scoring.py
        # imports this module).
        try:
            from scripts.agent_eval import scoring as _scoring  # noqa: PLC0415
        except ImportError:  # pragma: no cover - defensive
            _scoring = None
        if _scoring is not None:
            validator = _SHAPE_VALIDATORS.get(schema)
    if validator is None:
        raise ContractError([ContractDefect("$.schema", "UNKNOWN_SCHEMA", f"unknown persisted schema {schema!r}")])
    validator(document)
    return "SHAPE_VALID"

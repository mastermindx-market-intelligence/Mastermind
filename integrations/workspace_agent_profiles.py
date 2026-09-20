"""Pure Workspace Agent profile and pre-activation binding contracts.

These contracts freeze reviewed supervisory behavior and finite economic inputs
before any provider publication or trigger. They create no authority, do not
read secrets, do not publish agents, do not trigger runs, and own no lifecycle
or accounting state. Every live effect owner must still re-read current
authority, current target, provider configuration and economic evidence.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from collections.abc import Mapping
from typing import Any

from integrations.slack_agent_dialogue.contract import MAX_TEXT_CHARS

CATALOG_SCHEMA = "mastermind.workspace_agent_profile_catalog.v1"
ECONOMIC_SCHEMA = "mastermind.workspace_agent_economic_envelope.v1"
ACTIVATION_SCHEMA = "mastermind.workspace_agent_activation_binding.v1"
PUBLICATION_STATE = "DRAFT_NOT_PUBLISHED"
OVERFLOW_POLICY = "REFUSE"
MAX_ACTIVATION_WINDOW_MS = 24 * 60 * 60 * 1000
MAX_TRIGGER_COUNT = 16
MAX_USAGE_QUANTITY = 10**12
MAX_SPEND_MINOR_UNITS = 10**9

_PROFILE_IDS = frozenset(
    {"program-continuity-adviser", "independent-outcome-reviewer"}
)
_PROFILE_ROLES = frozenset({"supervisory_adviser", "independent_reviewer"})
_ALLOWED_STATUS = ("PASS", "PARTIAL", "BLOCKED", "FAIL")
_ALLOWED_TOOL_NAMES = frozenset(
    {
        "list_responsibilities",
        "get_responsibility",
        "get_attention",
        "get_current_runtime",
        "explain_blocker",
        "resolve_surface",
        "read_project_file",
        "submit_candidate",
    }
)
_ALLOWED_APP_BINDINGS = frozenset(
    {
        "mastermind-steward",
        "mastermind-workbench-read",
        "mastermind-workspace-agent-return",
    }
)
_COMMON_PROHIBITED = frozenset(
    {
        "source_write",
        "provider_trigger",
        "credential_change",
        "production_deploy",
        "merge_or_release",
        "canonical_result_acceptance",
        "wake_acknowledgement",
        "job_attempt_or_worker_mutation",
    }
)
_PROFILE_KEYS = frozenset(
    {
        "profile_id",
        "revision",
        "role",
        "mission",
        "required_inputs",
        "permitted_tools",
        "required_app_bindings",
        "prohibited_effects",
        "instructions",
        "output_contract",
    }
)
_OUTPUT_INPUT_KEYS = frozenset(
    {
        "kind",
        "allowed_status",
        "evidence_required_when_claiming_external_fact",
        "authority_effect",
    }
)
_OUTPUT_NORMALIZED_KEYS = _OUTPUT_INPUT_KEYS | {"max_result_chars"}
_ECONOMIC_KEYS = frozenset(
    {
        "schema",
        "authority_ref",
        "accounting_source_ref",
        "billing_currency",
        "incremental_spend_cap_minor_units",
        "usage_unit",
        "usage_cap_quantity",
        "max_trigger_count",
        "overflow_policy",
        "issued_at_ms",
        "expires_at_ms",
    }
)
_ACTIVATION_KEYS = frozenset(
    {
        "schema",
        "profile_id",
        "profile_revision",
        "profile_digest",
        "provider_channel_ref",
        "agent_version_ref",
        "app_bindings",
        "economic_envelope",
        "economic_envelope_digest",
        "concurrency_limit",
        "live_source_write_allowed",
        "production_release_allowed",
    }
)
_PUBLIC_REF = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._:-]{2,255}\Z", re.ASCII)
_CHANNEL_REF = re.compile(r"\Aagtch_[A-Za-z0-9_-]{1,192}\Z", re.ASCII)
_REVISION = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z", re.ASCII)
_CURRENCY = re.compile(r"\A[A-Z]{3}\Z", re.ASCII)
_USAGE_UNIT = re.compile(r"\A[A-Za-z][A-Za-z0-9._:-]{0,63}\Z", re.ASCII)
_SHA256 = re.compile(r"\A[0-9a-f]{64}\Z", re.ASCII)
_AGENT_VERSION = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._:-]{2,255}\Z", re.ASCII)


class WorkspaceProfileError(ValueError):
    """Fixed-code profile/activation refusal with no caller content."""


def _refuse(code: str) -> None:
    raise WorkspaceProfileError(code)


def _canonical_json(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
    except (TypeError, ValueError, UnicodeError, RecursionError):
        _refuse("INVALID_DOCUMENT")


def _text(value: Any, *, maximum: int) -> str:
    if (
        type(value) is not str
        or not value
        or len(value) > maximum
        or value != value.strip()
        or any(ord(char) < 0x20 or ord(char) == 0x7F for char in value)
    ):
        _refuse("INVALID_TEXT")
    try:
        value.encode("ascii")
    except UnicodeEncodeError:
        _refuse("INVALID_TEXT")
    return value


def _string_list(
    value: Any,
    *,
    maximum_items: int,
    maximum_chars: int,
    unique: bool,
) -> list[str]:
    if (
        not isinstance(value, list)
        or not 1 <= len(value) <= maximum_items
    ):
        _refuse("INVALID_LIST")
    result = [_text(item, maximum=maximum_chars) for item in value]
    if unique and len(result) != len(set(result)):
        _refuse("INVALID_LIST")
    return result


def _bounded_int(value: Any, *, minimum: int, maximum: int, code: str) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        _refuse(code)
    return value


def profile_digest(profile: Mapping[str, Any]) -> str:
    normalized = validate_profile(profile)
    return hashlib.sha256(_canonical_json(normalized)).hexdigest()


def validate_profile(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        _refuse("INVALID_PROFILE")
    raw = copy.deepcopy(dict(value))
    if set(raw) != _PROFILE_KEYS:
        _refuse("INVALID_PROFILE")
    profile_id = _text(raw["profile_id"], maximum=96)
    if profile_id not in _PROFILE_IDS:
        _refuse("INVALID_PROFILE")
    revision = _text(raw["revision"], maximum=64)
    if _REVISION.fullmatch(revision) is None:
        _refuse("INVALID_PROFILE")
    role = _text(raw["role"], maximum=64)
    if role not in _PROFILE_ROLES:
        _refuse("INVALID_PROFILE")
    mission = _text(raw["mission"], maximum=MAX_TEXT_CHARS)
    required_inputs = _string_list(
        raw["required_inputs"],
        maximum_items=16,
        maximum_chars=240,
        unique=True,
    )
    permitted_tools = _string_list(
        raw["permitted_tools"],
        maximum_items=16,
        maximum_chars=96,
        unique=True,
    )
    if not set(permitted_tools) <= _ALLOWED_TOOL_NAMES:
        _refuse("INVALID_PROFILE")
    app_bindings = _string_list(
        raw["required_app_bindings"],
        maximum_items=8,
        maximum_chars=96,
        unique=True,
    )
    if app_bindings != sorted(app_bindings) or not set(app_bindings) <= _ALLOWED_APP_BINDINGS:
        _refuse("INVALID_PROFILE")
    prohibited = _string_list(
        raw["prohibited_effects"],
        maximum_items=20,
        maximum_chars=96,
        unique=True,
    )
    if not _COMMON_PROHIBITED <= set(prohibited):
        _refuse("INVALID_PROFILE")
    instructions = _string_list(
        raw["instructions"],
        maximum_items=16,
        maximum_chars=MAX_TEXT_CHARS,
        unique=True,
    )
    output = raw["output_contract"]
    if not isinstance(output, Mapping):
        _refuse("INVALID_PROFILE")
    output = copy.deepcopy(dict(output))
    if set(output) not in {_OUTPUT_INPUT_KEYS, _OUTPUT_NORMALIZED_KEYS}:
        _refuse("INVALID_PROFILE")
    if (
        "max_result_chars" in output
        and output["max_result_chars"] != MAX_TEXT_CHARS
    ):
        _refuse("INVALID_PROFILE")
    kind = _text(output["kind"], maximum=64)
    if profile_id == "program-continuity-adviser" and kind != "continuity_candidate":
        _refuse("INVALID_PROFILE")
    if profile_id == "independent-outcome-reviewer" and kind != "review_candidate":
        _refuse("INVALID_PROFILE")
    max_result_chars = MAX_TEXT_CHARS
    if output["allowed_status"] != list(_ALLOWED_STATUS):
        _refuse("INVALID_PROFILE")
    if output["evidence_required_when_claiming_external_fact"] is not True:
        _refuse("INVALID_PROFILE")
    if output["authority_effect"] != "NONE":
        _refuse("INVALID_PROFILE")
    if "submit_candidate" not in permitted_tools:
        _refuse("INVALID_PROFILE")
    if "mastermind-workspace-agent-return" not in app_bindings:
        _refuse("INVALID_PROFILE")
    if profile_id == "program-continuity-adviser":
        if "read_project_file" in permitted_tools:
            _refuse("INVALID_PROFILE")
        expected_apps = [
            "mastermind-steward",
            "mastermind-workspace-agent-return",
        ]
    else:
        if "read_project_file" not in permitted_tools:
            _refuse("INVALID_PROFILE")
        expected_apps = [
            "mastermind-steward",
            "mastermind-workbench-read",
            "mastermind-workspace-agent-return",
        ]
    if app_bindings != expected_apps:
        _refuse("INVALID_PROFILE")
    return {
        "profile_id": profile_id,
        "revision": revision,
        "role": role,
        "mission": mission,
        "required_inputs": required_inputs,
        "permitted_tools": permitted_tools,
        "required_app_bindings": app_bindings,
        "prohibited_effects": prohibited,
        "instructions": instructions,
        "output_contract": {
            "kind": kind,
            "max_result_chars": max_result_chars,
            "allowed_status": list(_ALLOWED_STATUS),
            "evidence_required_when_claiming_external_fact": True,
            "authority_effect": "NONE",
        },
    }


def validate_profile_catalog(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        _refuse("INVALID_CATALOG")
    raw = copy.deepcopy(dict(value))
    if set(raw) != {"schema", "catalog_revision", "publication_state", "profiles"}:
        _refuse("INVALID_CATALOG")
    if raw["schema"] != CATALOG_SCHEMA or raw["publication_state"] != PUBLICATION_STATE:
        _refuse("INVALID_CATALOG")
    revision = _text(raw["catalog_revision"], maximum=64)
    if _REVISION.fullmatch(revision) is None:
        _refuse("INVALID_CATALOG")
    profiles = raw["profiles"]
    if not isinstance(profiles, list) or len(profiles) != 2:
        _refuse("INVALID_CATALOG")
    normalized = [validate_profile(item) for item in profiles]
    ids = [item["profile_id"] for item in normalized]
    if ids != ["program-continuity-adviser", "independent-outcome-reviewer"]:
        _refuse("INVALID_CATALOG")
    return {
        "schema": CATALOG_SCHEMA,
        "catalog_revision": revision,
        "publication_state": PUBLICATION_STATE,
        "profiles": normalized,
    }


def catalog_digest(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(validate_profile_catalog(value))).hexdigest()


def profile_by_id(catalog: Mapping[str, Any], profile_id: str) -> dict[str, Any]:
    normalized = validate_profile_catalog(catalog)
    for profile in normalized["profiles"]:
        if profile["profile_id"] == profile_id:
            return copy.deepcopy(profile)
    _refuse("PROFILE_NOT_FOUND")


def validate_economic_envelope(value: Mapping[str, Any]) -> dict[str, Any]:
    """Validate finite accounting evidence; this does not grant spend authority."""

    if not isinstance(value, Mapping):
        _refuse("INVALID_ECONOMIC_ENVELOPE")
    raw = copy.deepcopy(dict(value))
    if set(raw) != _ECONOMIC_KEYS or raw["schema"] != ECONOMIC_SCHEMA:
        _refuse("INVALID_ECONOMIC_ENVELOPE")
    authority_ref = _text(raw["authority_ref"], maximum=256)
    accounting_source_ref = _text(raw["accounting_source_ref"], maximum=256)
    if (
        _PUBLIC_REF.fullmatch(authority_ref) is None
        or _PUBLIC_REF.fullmatch(accounting_source_ref) is None
    ):
        _refuse("INVALID_ECONOMIC_ENVELOPE")
    currency = _text(raw["billing_currency"], maximum=3)
    if _CURRENCY.fullmatch(currency) is None:
        _refuse("INVALID_ECONOMIC_ENVELOPE")
    spend_cap = _bounded_int(
        raw["incremental_spend_cap_minor_units"],
        minimum=0,
        maximum=MAX_SPEND_MINOR_UNITS,
        code="INVALID_ECONOMIC_ENVELOPE",
    )
    usage_unit = _text(raw["usage_unit"], maximum=64)
    if _USAGE_UNIT.fullmatch(usage_unit) is None:
        _refuse("INVALID_ECONOMIC_ENVELOPE")
    usage_cap = _bounded_int(
        raw["usage_cap_quantity"],
        minimum=1,
        maximum=MAX_USAGE_QUANTITY,
        code="INVALID_ECONOMIC_ENVELOPE",
    )
    trigger_cap = _bounded_int(
        raw["max_trigger_count"],
        minimum=1,
        maximum=MAX_TRIGGER_COUNT,
        code="INVALID_ECONOMIC_ENVELOPE",
    )
    if raw["overflow_policy"] != OVERFLOW_POLICY:
        _refuse("INVALID_ECONOMIC_ENVELOPE")
    issued = _bounded_int(
        raw["issued_at_ms"],
        minimum=0,
        maximum=2**63 - 1,
        code="INVALID_ECONOMIC_ENVELOPE",
    )
    expires = _bounded_int(
        raw["expires_at_ms"],
        minimum=1,
        maximum=2**63 - 1,
        code="INVALID_ECONOMIC_ENVELOPE",
    )
    if expires <= issued or expires - issued > MAX_ACTIVATION_WINDOW_MS:
        _refuse("INVALID_ECONOMIC_ENVELOPE")
    return {
        "schema": ECONOMIC_SCHEMA,
        "authority_ref": authority_ref,
        "accounting_source_ref": accounting_source_ref,
        "billing_currency": currency,
        "incremental_spend_cap_minor_units": spend_cap,
        "usage_unit": usage_unit,
        "usage_cap_quantity": usage_cap,
        "max_trigger_count": trigger_cap,
        "overflow_policy": OVERFLOW_POLICY,
        "issued_at_ms": issued,
        "expires_at_ms": expires,
    }


def economic_envelope_digest(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(validate_economic_envelope(value))).hexdigest()


def build_activation_binding(
    *,
    catalog: Mapping[str, Any],
    profile_id: str,
    provider_channel_ref: str,
    agent_version_ref: str,
    economic_envelope: Mapping[str, Any],
) -> dict[str, Any]:
    """Freeze a pre-effect binding; live owners must revalidate all referenced facts."""

    profile = profile_by_id(catalog, profile_id)
    channel = _text(provider_channel_ref, maximum=256)
    if _CHANNEL_REF.fullmatch(channel) is None:
        _refuse("INVALID_ACTIVATION_BINDING")
    version = _text(agent_version_ref, maximum=256)
    if _AGENT_VERSION.fullmatch(version) is None:
        _refuse("INVALID_ACTIVATION_BINDING")
    envelope = validate_economic_envelope(economic_envelope)
    return {
        "schema": ACTIVATION_SCHEMA,
        "profile_id": profile["profile_id"],
        "profile_revision": profile["revision"],
        "profile_digest": profile_digest(profile),
        "provider_channel_ref": channel,
        "agent_version_ref": version,
        "app_bindings": list(profile["required_app_bindings"]),
        "economic_envelope": envelope,
        "economic_envelope_digest": economic_envelope_digest(envelope),
        "concurrency_limit": 1,
        "live_source_write_allowed": False,
        "production_release_allowed": False,
    }


def validate_activation_binding(
    value: Mapping[str, Any],
    *,
    catalog: Mapping[str, Any],
    now_ms: int,
) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _ACTIVATION_KEYS:
        _refuse("INVALID_ACTIVATION_BINDING")
    if type(now_ms) is not int or now_ms < 0:
        _refuse("INVALID_ACTIVATION_BINDING")
    raw = copy.deepcopy(dict(value))
    if raw["schema"] != ACTIVATION_SCHEMA:
        _refuse("INVALID_ACTIVATION_BINDING")
    rebuilt = build_activation_binding(
        catalog=catalog,
        profile_id=raw["profile_id"],
        provider_channel_ref=raw["provider_channel_ref"],
        agent_version_ref=raw["agent_version_ref"],
        economic_envelope=raw["economic_envelope"],
    )
    if raw != rebuilt:
        _refuse("ACTIVATION_BINDING_DRIFT")
    if not _SHA256.fullmatch(raw["profile_digest"]):
        _refuse("INVALID_ACTIVATION_BINDING")
    envelope = validate_economic_envelope(raw["economic_envelope"])
    if now_ms < envelope["issued_at_ms"] or now_ms > envelope["expires_at_ms"]:
        _refuse("ECONOMIC_ENVELOPE_NOT_CURRENT")
    return rebuilt


def activation_binding_digest(
    value: Mapping[str, Any],
    *,
    catalog: Mapping[str, Any],
    now_ms: int,
) -> str:
    normalized = validate_activation_binding(value, catalog=catalog, now_ms=now_ms)
    return hashlib.sha256(_canonical_json(normalized)).hexdigest()


__all__ = [
    "ACTIVATION_SCHEMA",
    "CATALOG_SCHEMA",
    "ECONOMIC_SCHEMA",
    "MAX_ACTIVATION_WINDOW_MS",
    "OVERFLOW_POLICY",
    "PUBLICATION_STATE",
    "WorkspaceProfileError",
    "activation_binding_digest",
    "build_activation_binding",
    "catalog_digest",
    "economic_envelope_digest",
    "profile_by_id",
    "profile_digest",
    "validate_activation_binding",
    "validate_economic_envelope",
    "validate_profile",
    "validate_profile_catalog",
]

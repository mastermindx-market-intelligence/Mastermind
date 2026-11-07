"""Closed read-only Workspace view of the existing routing-policy owner.

No account, private endpoint, key reference or caller-selected filesystem path
crosses this boundary. Configured routing never establishes live pool capacity.
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime

from common.executive_workspace_contract import (
    PRINCIPAL_KEYS, RESOURCE, SCOPE, canonical,
)

FRAME_SCHEMA = "mastermind.workspace_model_configuration_read.v1"
BODY_SCHEMA = "mastermind.workspace_model_configuration.v1"
CONFIGURATION_SCHEMA = "mastermind.model_router_configuration.v1"
OPERATION = "model_configuration"
MAX_REQUEST_BYTES = 8192
MAX_RESPONSE_BYTES = 278_528
_FACT_KEYS = frozenset({"policy_version", "capability_policy_version", "capability_policy_digest",
                        "providers", "models", "routes"})
_CONFIG_KEYS = _FACT_KEYS | {"schema", "owner", "scope", "revision", "physical_account_pools",
                             "live_capacity", "admission_authorized", "writes_applied",
                             "credential_resolution_performed"}
_HEX = re.compile(r"[0-9a-f]{64}\Z")
_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/+-]{0,127}\Z")
_SECRET = re.compile(r"(?i)(?:xox[baprs]-|xapp-|github_pat_|gh[pousr]_|sk-[A-Za-z0-9_-]{16,}|bearer\s)")
_REASONS = frozenset({"SOURCE_UNAVAILABLE", "SOURCE_CHANGED", "RESPONSE_OVER_BUDGET"})


def _token(value):
    return type(value) is str and _TOKEN.fullmatch(value) is not None and _SECRET.search(value) is None


def _tokens(value):
    return type(value) is list and len(value) <= 64 and all(_token(item) for item in value)


def validate_frame(value):
    if (type(value) is not dict
            or set(value) != {"schema", "operation", "selection", "principal"}
            or value["schema"] != FRAME_SCHEMA or value["operation"] != OPERATION
            or value["selection"] is not None
            or type(value["principal"]) is not dict or set(value["principal"]) != PRINCIPAL_KEYS
            or value["principal"]["resource"] != RESOURCE
            or value["principal"]["scopes"] != [SCOPE]
            or any(type(value["principal"][key]) is not str
                   or not 1 <= len(value["principal"][key]) <= 256
                   for key in PRINCIPAL_KEYS - {"scopes"})
            or len(canonical(value)) + 1 > MAX_REQUEST_BYTES):
        raise ValueError("invalid_input")
    return value


def validate_configuration(value):
    if (type(value) is not dict or set(value) != _CONFIG_KEYS
            or value["schema"] != CONFIGURATION_SCHEMA or value["owner"] != "model_router"
            or value["scope"] != "EXECUTIVE_ROUTING_POLICY"
            or value["physical_account_pools"] != "NOT_JOINED"
            or value["live_capacity"] != "NOT_OBSERVED"
            or value["admission_authorized"] is not False
            or value["writes_applied"] is not False
            or value["credential_resolution_performed"] is not False
            or not _token(value["policy_version"]) or not _token(value["capability_policy_version"])
            or type(value["revision"]) is not str or _HEX.fullmatch(value["revision"]) is None
            or type(value["capability_policy_digest"]) is not str
            or _HEX.fullmatch(value["capability_policy_digest"]) is None):
        raise ValueError("invalid_model_configuration")
    providers, models, routes = value["providers"], value["models"], value["routes"]
    if (type(providers) is not dict or len(providers) > 128
            or type(models) is not dict or len(models) > 1024
            or type(routes) is not dict or len(routes) > 128):
        raise ValueError("invalid_model_configuration")
    for alias, row in providers.items():
        if (not _token(alias) or type(row) is not dict
                or set(row) != {"adapter_id", "enabled", "autonomous_allowed"}
                or not _token(row["adapter_id"]) or type(row["enabled"]) is not bool
                or type(row["autonomous_allowed"]) is not bool):
            raise ValueError("invalid_model_configuration")
    for alias, row in models.items():
        if (not _token(alias) or type(row) is not dict
                or set(row) != {"provider_alias", "adapter_id", "model", "effort", "cost_class",
                                "capabilities", "worker_eligible", "execution_profile_id", "execution_profile_digest"}
                or any(not _token(row[key]) for key in (
                    "provider_alias", "adapter_id", "model", "effort", "cost_class", "execution_profile_id"))
                or row["provider_alias"] not in providers
                or row["adapter_id"] != providers[row["provider_alias"]]["adapter_id"]
                or type(row["worker_eligible"]) is not bool or not _tokens(row["capabilities"])
                or type(row["execution_profile_digest"]) is not str
                or _HEX.fullmatch(row["execution_profile_digest"]) is None):
            raise ValueError("invalid_model_configuration")
    for kind, row in routes.items():
        if (not _token(kind) or type(row) is not dict
                or set(row) != {"required_capabilities", "routine", "elevated"}
                or not _tokens(row["required_capabilities"])):
            raise ValueError("invalid_model_configuration")
        for risk in ("routine", "elevated"):
            if type(row[risk]) is not list or len(row[risk]) > 64:
                raise ValueError("invalid_model_configuration")
            for tier in row[risk]:
                if (type(tier) is not dict or set(tier) != {"tier_id", "model_aliases"}
                        or not _token(tier["tier_id"]) or not _tokens(tier["model_aliases"])
                        or any(alias not in models for alias in tier["model_aliases"])):
                    raise ValueError("invalid_model_configuration")
    if hashlib.sha256(canonical({key: value[key] for key in _FACT_KEYS})).hexdigest() != value["revision"]:
        raise ValueError("invalid_model_configuration_revision")
    if len(canonical(value)) > 262_144:
        raise ValueError("model_configuration_over_budget")
    return value


def unavailable(reason="SOURCE_UNAVAILABLE"):
    if reason not in _REASONS:
        raise ValueError("invalid_unavailable_reason")
    return {"ok": True, "result": {
        "schema": BODY_SCHEMA, "availability": "UNAVAILABLE", "observed_at": None,
        "source_owner": "model_router", "reason_codes": [reason], "configuration": None,
    }}


def validate_result(value):
    if (type(value) is not dict or set(value) != {
            "schema", "availability", "observed_at", "source_owner", "reason_codes", "configuration"}
            or value["schema"] != BODY_SCHEMA or value["source_owner"] != "model_router"):
        raise ValueError("invalid_model_configuration_result")
    if value["availability"] == "UNAVAILABLE":
        if (type(value["reason_codes"]) is not list or len(value["reason_codes"]) != 1
                or value["reason_codes"][0] not in _REASONS
                or value != unavailable(value["reason_codes"][0])["result"]):
            raise ValueError("invalid_model_configuration_result")
    elif value["availability"] == "AVAILABLE":
        if value["reason_codes"] != [] or type(value["observed_at"]) is not str:
            raise ValueError("invalid_model_configuration_result")
        stamp = datetime.fromisoformat(value["observed_at"].replace("Z", "+00:00"))
        if stamp.utcoffset() is None:
            raise ValueError("invalid_model_configuration_result")
        validate_configuration(value["configuration"])
    else:
        raise ValueError("invalid_model_configuration_result")
    if len(canonical(value)) + 1 > MAX_RESPONSE_BYTES - 128:
        raise ValueError("model_configuration_over_budget")
    return value

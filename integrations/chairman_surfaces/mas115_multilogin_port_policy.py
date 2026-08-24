"""Pure fixed-port policy for the MAS-115 disposable Multilogin canary.

This module owns no credential, transport, browser, process, or durable
control-plane state.  It validates an already bounded Profile Metas response,
constructs the single permitted update body, and returns only closed redacted
configuration receipts.
"""
from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass


CANARY_PORT = 65535
CANARY_ORIGIN = "http://127.0.0.1:65535"
ORIGIN_POLICY = "mas115_fixed_loopback_v1"
LEGACY_PROVISION_SCHEMA = "mastermind.mas115_nonseat_canary_provision.v2"
LEGACY_BENIGN_ORIGIN = "http://127.0.0.1:7777"
CONFIG_RECEIPT_SCHEMA = "mastermind.mas115_multilogin_port_configuration.v1"

DEFAULT_MASKED = "DEFAULT_MASKED"
EXACT_CONFIGURED = "EXACT_CONFIGURED"
UNSUPPORTED_PORT_STATE = "UNSUPPORTED_PORT_STATE"
MALFORMED_PROFILE_METAS = "MALFORMED_PROFILE_METAS"

CONFIG_CODES = frozenset({
    "CONFIGURED",
    "ALREADY_CONFIGURED",
    "CONFIGURED_AFTER_RECONCILIATION",
    "AUTH_EXPIRED_NO_PROOF",
    "REJECTED_NO_PROOF",
    "EFFECT_UNKNOWN",
    UNSUPPORTED_PORT_STATE,
    "PRESERVATION_DRIFT",
    "VENDOR_ERROR",
})
_PASS_CODES = frozenset({
    "CONFIGURED", "ALREADY_CONFIGURED", "CONFIGURED_AFTER_RECONCILIATION",
})
_HOLD_CODES = frozenset({"EFFECT_UNKNOWN", "PRESERVATION_DRIFT"})


class PortPolicyRefusal(ValueError):
    """Closed pure-policy refusal with no caller-controlled detail."""

    CODES = frozenset({MALFORMED_PROFILE_METAS, UNSUPPORTED_PORT_STATE})

    def __init__(self, code: str):
        if code not in self.CODES:
            raise ValueError("unknown port-policy refusal")
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class PortPolicySnapshot:
    """Redacted comparison material for one exact profile configuration."""

    state: str
    auto_update_core: bool
    preservation_digest: str


def _preservation_digest(profile: dict) -> str:
    preserved = copy.deepcopy(profile)
    preserved.pop("last_update_at", None)
    preserved.pop("last_updated_by", None)
    parameters = preserved["parameters"]
    parameters["flags"].pop("ports_masking", None)
    parameters["fingerprint"].pop("ports", None)
    material = json.dumps(preserved, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def classify_profile_metas(
    payload, *, profile_id: str, folder_id: str,
) -> PortPolicySnapshot:
    """Classify only the exact disposable Mimic profile port states."""

    malformed = (
        not isinstance(payload, dict)
        or set(payload) != {"status", "data"}
        or payload.get("status") != {
            "error_code": "",
            "http_code": 200,
            "message": "List of profiles metadata",
        }
        or not isinstance(payload.get("data"), dict)
        or set(payload["data"]) != {"profiles"}
        or not isinstance(payload["data"].get("profiles"), list)
        or len(payload["data"]["profiles"]) != 1
    )
    if malformed:
        raise PortPolicyRefusal(MALFORMED_PROFILE_METAS)

    profile = payload["data"]["profiles"][0]
    required = {
        "id", "folder_id", "browser_type", "in_use_by", "is_auto_update",
        "parameters",
    }
    malformed = (
        not isinstance(profile, dict)
        or not required.issubset(profile)
        or not isinstance(profile_id, str)
        or not isinstance(folder_id, str)
        or profile.get("id") != profile_id
        or profile.get("folder_id") != folder_id
        or profile.get("browser_type") != "mimic"
        or profile.get("in_use_by") != ""
        or type(profile.get("is_auto_update")) is not bool
        or not isinstance(profile.get("parameters"), dict)
    )
    if malformed:
        raise PortPolicyRefusal(MALFORMED_PROFILE_METAS)

    parameters = profile["parameters"]
    flags = parameters.get("flags")
    fingerprint = parameters.get("fingerprint")
    if not isinstance(flags, dict) or not isinstance(fingerprint, dict):
        raise PortPolicyRefusal(MALFORMED_PROFILE_METAS)
    mode = flags.get("ports_masking")
    ports = fingerprint.get("ports", [])
    if not isinstance(ports, list) or any(type(item) is not int for item in ports):
        raise PortPolicyRefusal(MALFORMED_PROFILE_METAS)
    if mode == "mask" and ports == []:
        state = DEFAULT_MASKED
    elif mode == "mask" and ports == [CANARY_PORT]:
        state = EXACT_CONFIGURED
    else:
        raise PortPolicyRefusal(UNSUPPORTED_PORT_STATE)

    return PortPolicySnapshot(
        state=state,
        auto_update_core=profile["is_auto_update"],
        preservation_digest=_preservation_digest(profile),
    )


def build_partial_update_body(profile_id: str, snapshot: PortPolicySnapshot) -> dict:
    """Build the single allowed profile mutation from a default snapshot."""

    if not isinstance(profile_id, str) or snapshot.state != DEFAULT_MASKED:
        raise PortPolicyRefusal(UNSUPPORTED_PORT_STATE)
    return {
        "profile_id": profile_id,
        "auto_update_core": snapshot.auto_update_core,
        "parameters": {
            "flags": {"ports_masking": "mask"},
            "fingerprint": {"ports": [CANARY_PORT]},
        },
    }


def configuration_receipt(
    code: str,
    *,
    updated: bool,
    reconciled: bool,
    preservation_unchanged: bool,
    auto_update_unchanged: bool,
    exact_profile_stopped: bool,
) -> dict:
    """Return one closed receipt containing predicates but no live identity."""

    if code not in CONFIG_CODES:
        raise ValueError("unknown configuration result")
    predicates = (
        updated,
        reconciled,
        preservation_unchanged,
        auto_update_unchanged,
        exact_profile_stopped,
    )
    if any(type(value) is not bool for value in predicates):
        raise ValueError("configuration receipt fields must be boolean")
    verdict = "PASS" if code in _PASS_CODES else "HOLD" if code in _HOLD_CODES else "REFUSED"
    return {
        "schema": CONFIG_RECEIPT_SCHEMA,
        "verdict": verdict,
        "code": code,
        "updated": updated,
        "reconciled": reconciled,
        "predicates": {
            "preservation_unchanged": preservation_unchanged,
            "auto_update_unchanged": auto_update_unchanged,
            "exact_profile_stopped": exact_profile_stopped,
        },
    }

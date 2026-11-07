"""Prepare current native COO selectors for the existing stopped install path.

Quota registration is additive: a catalogue upgrade cannot rewrite an old class.
This is the catalogue-derived naming used by the host's install-input builder,
including the Operator binary identity that is immutable quota metadata too.
The caller supplies already validated Control/Worker inputs and the protected
source's ModelRouter. Nothing here reads or writes host files, Runtime or auth.
The existing installer publishes the explicitly prepared input; the service and
Runtime retain registration, held-Attempt and current-binding admission.
"""

from __future__ import annotations

import copy
import dataclasses
import hashlib
import json
import re
from typing import Any, Mapping

from control_plane.model_router import ModelRouter
from ops.executive_os.acceptance import _validate_operator_harness_policy


class COOQuotaSelectionError(ValueError):
    """The input is outside the disarmed ordinary native composition."""


_SELECTORS = {
    "coo_quota_class": "codex-coo",
    "coo_default_quota_class": "codex-coo-default",
    "coo_operator_quota_class": "codex-coo-operator",
}


def prepare_current_coo_quota_selection(
    control: Mapping[str, Any],
    worker: Mapping[str, Any],
    *,
    router: ModelRouter,
) -> dict[str, Any]:
    """Return a copy changing only the three native catalogue selectors.

    This is explicit source/install preparation, never an arm-time fallback or
    a repair of existing Runtime rows. It supplies no availability evidence.
    Historical custom, attended and native-return selections are not adopted.
    Repeating preparation at an unchanged catalogue/harness is deterministic;
    proof-source movement alone does not create another capacity identity.
    """
    out = copy.deepcopy(dict(control))
    if any(out.get(key) is not False for key in (
        "coo_autonomy_armed", "coo_operator_harness_armed", "ceo_submit_armed",
    )) or out.get("ceo_ingress_armed", False) is not False:
        raise COOQuotaSelectionError("native selector preparation requires disarmed Control")
    if worker.get("operator_harness_armed") is not False:
        raise COOQuotaSelectionError("native selector preparation requires disarmed Worker")
    if (
        out.get("coo_model_alias") != "coo.sealed"
        or out.get("coo_operator_model_alias") != "coo.operator.readonly"
        or out.get("subscription_canary_realm") is not None
        or out.get("coo_attended_work_placements", []) not in ([], ())
        or out.get("dialogue_wake_canary_activation") is not None
    ):
        raise COOQuotaSelectionError("only the ordinary native COO composition is supported")
    company = out.get("company_consultation", {})
    if not isinstance(company, dict) or company.get("native_return_armed", False) is not False:
        raise COOQuotaSelectionError("native-return selection must remain closed")
    _validate_operator_harness_policy(out, worker)
    for field, prefix in _SELECTORS.items():
        if re.fullmatch(re.escape(prefix) + r"(?:-[0-9a-f]{16})?", out[field]) is None:
            raise COOQuotaSelectionError("unsupported incumbent native quota selector")

    digest = out.get("operator_harness_binary_digest")
    version = out.get("operator_harness_version")
    if (
        type(digest) is not str
        or re.fullmatch(r"[0-9a-f]{64}", digest) is None
        or digest == "0" * 64
        or type(version) is not str
        or not version.strip()
        or version != version.strip()
        or len(version) > 128
        or version == "unproven"
        or any(ord(char) < 32 or ord(char) == 127 for char in version)
    ):
        raise COOQuotaSelectionError("an observed Operator harness identity is required")
    binding = {
        "routing_policy_version": router.policy_version,
        "aliases": {
            name: dataclasses.asdict(router.resolve_model_alias(name))
            for name in ("coo.sealed", "coo.operator.readonly")
        },
        "operator_harness_binary_digest": digest,
        "operator_harness_version": version,
    }
    suffix = hashlib.sha256(json.dumps(
        binding, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")).hexdigest()[:16]
    for field, prefix in _SELECTORS.items():
        out[field] = prefix + "-" + suffix
    _validate_operator_harness_policy(out, worker)
    return out

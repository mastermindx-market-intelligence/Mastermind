#!/usr/bin/env python3
"""Pure plan/compile/orchestration for the owned Control component update.

This module owns NO lock, NO marker, NO journal, NO controller, NO authority
and NO readback.  It compiles the exact candidate the existing Executive
transaction owner will publish, renders the closed plan document and its
digest, and orchestrates that incumbent owner.  Every installed-file write,
launchd effect, receipt correlation, transaction marker and consumed-config
readback belongs to ``ops.executive_os.autonomy_control`` -- the ONE existing
``AUTONOMY_TRANSACTION`` owner -- which this module calls and never replaces.

What the update changes, and nothing else:

* the Control configuration: ``proof_base_sha`` and the installer-owned
  ``proof_source_repository`` ONLY (the installed Macro root is preserved and
  never exported);
* the Control LaunchDaemon plist: the target release-root substitutions ONLY;
* the already-inert Worker LaunchDaemon plist: the target release-root
  substitutions ONLY (the Worker is never started, stopped, enabled or
  disarmed here -- it must already be absent AND disabled);
* the existing disarmed authority receipt: a correlation of the source and
  configuration digests through the incumbent validator, changing no
  authority, state, evidence, policy, scope or timestamp;
* the existing nonsecret control observation, published by the actual held
  transaction owner.

Every other Control field, the whole Worker configuration and the whole Worker
runtime state are preserved.  No Relay, MCP, Backup or privileged-broker
action is taken, and the original publish-os-gateway receipt and its history
are excluded.

The plan output carries only allowed hashes, source identifiers, precondition
states and the closed effect list.  No installed configuration, token or
credential content is ever placed in the plan, in any argv, or in any
caller-readable staging.
"""

from __future__ import annotations

import copy
import dataclasses
import hashlib
import json
import plistlib
import re
from typing import Any, Mapping

PLAN_SCHEMA = "mastermind.control_component_update_plan.v1"

CONTROL_CONFIG_PATH = "/Library/Application Support/MastermindExecutive/config/control.json"
CONTROL_PLIST_PATH = "/Library/LaunchDaemons/com.mastermind.executive.control.plist"
WORKER_PLIST_PATH = "/Library/LaunchDaemons/com.mastermind.executive.worker.codex.plist"
ADMIN_CHECKOUT_ROOT = "/var/db/mastermind-executive/control/admin-checkout"

HEX40 = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")

# The closed effect list.  These are the only commands the owner may dispatch
# for this operation, in this order.  The list is inside the plan digest, so
# the operator's approved effect set is digest-bound.
EFFECTS = (
    "bootout system/com.mastermind.executive.control",
    "replace " + CONTROL_CONFIG_PATH,
    "replace " + CONTROL_PLIST_PATH,
    "replace " + WORKER_PLIST_PATH,
    "correlate " + "/Library/Application Support/MastermindExecutive/config/autonomy-state-v1.json",
    "bootstrap system/" + CONTROL_PLIST_PATH,
    "publish control observation",
)

# The closed precondition vocabulary.  Every one of these must hold before a
# plan exists; a false precondition is a refusal with zero cutover.
PRECONDITIONS = (
    "prior_release_sealed",
    "target_release_sealed",
    "interpreter_qualified",
    "target_admin_checkout_ready",
    "schema_compatible",
    "prior_control_config_matches",
    "prior_control_plist_matches",
    "prior_worker_plist_matches",
    "global_transaction_absent",
    "autonomy_receipt_valid",
    "autonomy_receipt_disarmed",
    "owner_quiescent",
    "control_registered",
    "control_enabled",
    "worker_absent",
    "worker_disabled",
)

WARNINGS = (
    "the Control service is booted out and bootstrapped once: the endpoint is briefly unavailable",
    "the Worker daemon is never started, stopped, enabled or disarmed; it must already be absent and disabled",
    "there is no automatic rollback after a file is replaced; the sealed preimages are preserved in the "
    "transaction marker for a separately approved restore",
    "the consumed-config proof is the wrapper-owned attestation: it binds the live pid, the boot identity, "
    "the target release and the exact consumed configuration digest",
)


class ComponentError(ValueError):
    """The supplied or observed state cannot produce this component update."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def canonical(value: Any) -> bytes:
    """One canonical JSON encoding used for every digest in this module."""

    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def plan_digest(plan: Mapping[str, Any]) -> str:
    return digest(canonical(plan))


def _strict_json(raw: bytes) -> dict[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in items:
            if key in value:
                raise ValueError("duplicate key")
            value[key] = item
        return value

    try:
        document = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ComponentError("control_config_not_json") from exc
    if type(document) is not dict:
        raise ComponentError("control_config_not_object")
    return document


def _flat_text(value: Any) -> str:
    """Every string reachable inside one plist value."""

    if type(value) is str:
        return value
    if type(value) is list:
        return "".join(_flat_text(item) for item in value)
    if type(value) is dict:
        return "".join(
            _flat_text(key) + _flat_text(item) for key, item in value.items()
        )
    return ""


@dataclasses.dataclass(frozen=True)
class Candidate:
    """The exact bytes one Control component update would publish."""

    target_sha: str
    prior_sha: str
    control_config_before: bytes
    control_config_after: bytes
    control_plist_before: bytes
    control_plist_after: bytes
    worker_plist_before: bytes
    worker_plist_after: bytes
    worker_config_sha256: str
    changed_control_fields: tuple[str, ...]

    @property
    def control_config_before_sha256(self) -> str:
        return digest(self.control_config_before)

    @property
    def control_config_after_sha256(self) -> str:
        return digest(self.control_config_after)

    @property
    def control_plist_before_sha256(self) -> str:
        return digest(self.control_plist_before)

    @property
    def control_plist_after_sha256(self) -> str:
        return digest(self.control_plist_after)

    @property
    def worker_plist_before_sha256(self) -> str:
        return digest(self.worker_plist_before)

    @property
    def worker_plist_after_sha256(self) -> str:
        return digest(self.worker_plist_after)


def substitute_release_root(
    document: Mapping[str, Any], *, prior_root: str, target_root: str
) -> dict[str, Any]:
    """Retarget ONLY the release-root coordinates of one installed plist.

    The installed plist is the closed launchd profile of one role.  Exactly
    two coordinates carry the release source: ``WorkingDirectory`` and the
    ``ProgramArguments`` entries that name the release tree.  Every other
    coordinate -- the label, the sockets, the environment, the limits, the
    log paths, the user and group -- is preserved byte for byte.  A release
    root mentioned anywhere else refuses the substitution.
    """

    if prior_root == target_root:
        raise ComponentError("release_root_not_retargeted")
    value = copy.deepcopy(dict(document))
    if value.get("WorkingDirectory") != prior_root:
        raise ComponentError("plist_release_root_unexpected")
    value["WorkingDirectory"] = target_root
    arguments = value.get("ProgramArguments")
    if type(arguments) is not list or not arguments:
        raise ComponentError("plist_program_arguments_unexpected")
    substituted = 0
    for index, item in enumerate(arguments):
        if type(item) is not str:
            raise ComponentError("plist_program_arguments_unexpected")
        if item == prior_root:
            arguments[index] = target_root
            substituted += 1
        elif item.startswith(prior_root + "/"):
            arguments[index] = target_root + item[len(prior_root):]
            substituted += 1
    if substituted == 0:
        raise ComponentError("plist_release_root_unexpected")
    for key, item in value.items():
        if key in ("WorkingDirectory", "ProgramArguments"):
            continue
        if prior_root in _flat_text(item):
            raise ComponentError("plist_release_root_unexpected")
    return value


def _encode_plist(document: Mapping[str, Any]) -> bytes:
    return plistlib.dumps(dict(document), fmt=plistlib.FMT_XML, sort_keys=False)


def compile_candidate(
    prior_control_config: bytes,
    prior_control_plist: bytes,
    prior_worker_plist: bytes,
    *,
    target_sha: str,
    prior_sha: str,
    worker_config_sha256: str,
    prior_release_root: str,
    target_release_root: str,
) -> Candidate:
    """Compile the exact candidate.  Pure: no file, no command, no state."""

    if HEX40.fullmatch(target_sha) is None or HEX40.fullmatch(prior_sha) is None:
        raise ComponentError("release_sha_invalid")
    if target_sha == prior_sha:
        raise ComponentError("release_not_retargeted")
    if HEX64.fullmatch(worker_config_sha256) is None:
        raise ComponentError("worker_config_digest_invalid")

    document = _strict_json(prior_control_config)
    if document.get("proof_base_sha") != prior_sha:
        raise ComponentError("control_config_source_mismatch")

    from ops.executive_os.prepare_control_successor import (
        PreparationError,
        build_component_successor,
    )

    try:
        successor = build_component_successor(document, source_sha=target_sha)
    except PreparationError as exc:
        raise ComponentError("control_config_successor_invalid") from exc
    changed = tuple(
        sorted(key for key in document if document[key] != successor[key])
    )
    if changed != ("proof_base_sha", "proof_source_repository"):
        raise ComponentError("control_config_scope_invalid")
    if successor.get("proof_source_repository") != (
        ADMIN_CHECKOUT_ROOT + "/" + target_sha
    ):
        raise ComponentError("control_config_source_repository_invalid")
    control_config_after = (json.dumps(
        successor, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False
    ) + "\n").encode("utf-8")

    try:
        control_plist = plistlib.loads(prior_control_plist)
        worker_plist = plistlib.loads(prior_worker_plist)
    except (plistlib.InvalidFileException, ValueError, TypeError) as exc:
        raise ComponentError("plist_not_readable") from exc
    if type(control_plist) is not dict or type(worker_plist) is not dict:
        raise ComponentError("plist_not_readable")
    control_plist_after = _encode_plist(
        substitute_release_root(
            control_plist, prior_root=prior_release_root, target_root=target_release_root
        )
    )
    worker_plist_after = _encode_plist(
        substitute_release_root(
            worker_plist, prior_root=prior_release_root, target_root=target_release_root
        )
    )
    return Candidate(
        target_sha=target_sha,
        prior_sha=prior_sha,
        control_config_before=prior_control_config,
        control_config_after=control_config_after,
        control_plist_before=prior_control_plist,
        control_plist_after=control_plist_after,
        worker_plist_before=prior_worker_plist,
        worker_plist_after=worker_plist_after,
        worker_config_sha256=worker_config_sha256,
        changed_control_fields=changed,
    )


def plan_document(
    candidate: Candidate,
    *,
    preconditions: Mapping[str, bool],
    prior_release_manifest_sha256: str,
    target_release_manifest_sha256: str,
    admin_checkout_commit: str,
) -> dict[str, Any]:
    """The closed plan document: hashes, source ids, states and effects only."""

    if set(preconditions) != set(PRECONDITIONS):
        raise ComponentError("precondition_vocabulary_invalid")
    if any(type(state) is not bool for state in preconditions.values()):
        raise ComponentError("precondition_state_invalid")
    return {
        "schema": PLAN_SCHEMA,
        "target_sha": candidate.target_sha,
        "prior_sha": candidate.prior_sha,
        "control_config": {
            "path": CONTROL_CONFIG_PATH,
            "before_sha256": candidate.control_config_before_sha256,
            "after_sha256": candidate.control_config_after_sha256,
            "changed_fields": list(candidate.changed_control_fields),
        },
        "control_plist": {
            "path": CONTROL_PLIST_PATH,
            "before_sha256": candidate.control_plist_before_sha256,
            "after_sha256": candidate.control_plist_after_sha256,
        },
        "worker_plist": {
            "path": WORKER_PLIST_PATH,
            "before_sha256": candidate.worker_plist_before_sha256,
            "after_sha256": candidate.worker_plist_after_sha256,
        },
        "worker_config_sha256": candidate.worker_config_sha256,
        "prior_release_manifest_sha256": prior_release_manifest_sha256,
        "target_release_manifest_sha256": target_release_manifest_sha256,
        "admin_checkout_commit": admin_checkout_commit,
        "preconditions": {key: bool(preconditions[key]) for key in PRECONDITIONS},
        "effects": list(EFFECTS),
    }


# ---------------------------------------------------------------------------
# Orchestration.  These functions hold no authority of their own: each one
# calls the incumbent owner in ``ops.executive_os.autonomy_control`` and
# returns its typed result.
# ---------------------------------------------------------------------------


def plan(host: Any, *, target_sha: str) -> dict[str, Any]:
    """Compile and prove the plan.  Read-only: no marker, no effect."""

    if HEX40.fullmatch(target_sha) is None:
        raise ComponentError("release_sha_invalid")
    observation = host.observe_control_component_update(target_sha=target_sha)
    document = observation["plan"]
    return {
        "ok": True,
        "outcome": "PLANNED",
        "plan": document,
        "plan_sha256": plan_digest(document),
        "warnings": list(WARNINGS),
    }


def apply(host: Any, *, target_sha: str, plan_sha256: str) -> dict[str, Any]:
    """Publish exactly the approved plan through the incumbent owner."""

    from ops.executive_os import autonomy_control as owner

    if HEX40.fullmatch(target_sha) is None:
        raise ComponentError("release_sha_invalid")
    if HEX64.fullmatch(plan_sha256) is None:
        raise ComponentError("plan_sha256_invalid")
    return owner.execute_control_component_update(
        host, target_sha=target_sha, plan_sha256=plan_sha256
    )


def reconcile(host: Any, *, target_sha: str) -> dict[str, Any]:
    """Prove one interrupted update to its exact retained postimages."""

    from ops.executive_os import autonomy_control as owner

    if HEX40.fullmatch(target_sha) is None:
        raise ComponentError("release_sha_invalid")
    return owner.reconcile_control_component_update(host, target_sha=target_sha)

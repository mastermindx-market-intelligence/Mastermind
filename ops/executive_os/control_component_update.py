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
  transaction owner;
* OPTIONALLY, and only when the caller supplies the PAIRED Hermes host-read
  selection: the two Fabric-binding selector coordinates of the Control
  configuration, together with the ONE immutable binding artifact they name.

Every other Control field, the whole Worker configuration and the whole Worker
runtime state are preserved.  No Relay, MCP, Backup or privileged-broker
action is taken, and the original publish-os-gateway receipt and its history
are excluded.

The Hermes host-read selection is NOT a second operation.  It is one optional,
paired input to the SAME verbs: both coordinates absent preserve the
source-only behaviour byte-for-byte, and exactly one of them refuses.  It is
composed in memory, published exactly once as one derived immutable artifact,
and reconstructed from the sealed bytes during a reconciliation.

Exactly two closed input states exist and the installed state selects one of
them.  LIVE: the Control service is registered and enabled.  OFFLINE: the
Control service is genuinely absent AND explicitly disabled, which is the
state the incumbent stop leaves behind.  Every other combination refuses
before any effect.

The plan output carries only allowed hashes, source identifiers, precondition
states, the receipt preimages (presence and the exact raw-byte digest of
every receipt this operation may replace), the mode and the closed effect list.
No installed configuration, token or credential content is ever placed in the
plan, in any argv, or in any caller-readable staging.
"""

from __future__ import annotations

import copy
import dataclasses
import hashlib
import json
import plistlib
import re
from typing import Any, Mapping, Sequence

PLAN_SCHEMA = "mastermind.control_component_update_plan.v1"

CONFIG_ROOT_PATH = "/Library/Application Support/MastermindExecutive/config"
CONTROL_CONFIG_PATH = "/Library/Application Support/MastermindExecutive/config/control.json"
CONTROL_PLIST_PATH = "/Library/LaunchDaemons/com.mastermind.executive.control.plist"
WORKER_PLIST_PATH = "/Library/LaunchDaemons/com.mastermind.executive.worker.codex.plist"
ADMIN_CHECKOUT_ROOT = "/var/db/mastermind-executive/control/admin-checkout"
AUTHORITY_RECEIPT_PATH = (
    "/Library/Application Support/MastermindExecutive/config/autonomy-state-v1.json"
)
CEO_SUBMIT_RECEIPT_PATH = (
    "/Library/Application Support/MastermindExecutive/config/ceo-submit-state-v1.json"
)
COMPONENT_RECEIPT_PATH = (
    "/Library/Application Support/MastermindExecutive/config/control-component-update-v1.json"
)

HEX40 = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")

# The closed mode vocabulary.  Exactly two input states exist, and the
# observed installed state selects exactly one of them.  Any other
# combination -- unknown, mixed or mismatched -- refuses before any effect.
LIVE_MODE = "live"
OFFLINE_MODE = "offline"
COMPONENT_MODES = (LIVE_MODE, OFFLINE_MODE)

# The closed effect lists.  These are the only commands the owner may dispatch
# for this operation, in this order, for the given mode.  The list is inside
# the plan digest, so the operator's approved effect set is digest-bound.
#
# The order below is the order the owner actually dispatches the effects in:
# both installed plists are retargeted first, the Control configuration is
# replaced next, the receipt correlations follow, and only then is the
# Control boundary changed.  The list is a SEQUENCE, not an unordered set:
# it names the exact order the approved effects happen in.
#
# LIVE: the Control service is registered and enabled, so it is booted out
# once and bootstrapped once.
#
# OFFLINE: the Control service is already genuinely absent AND explicitly
# disabled, so there is NO bootout to dispatch and NO bootout to record.  The
# publications and the receipt correlations are identical, and the enable
# happens after them, immediately before the single bootstrap.  The Worker is
# never started, stopped, enabled or disarmed in either mode.
LIVE_EFFECTS = (
    "bootout system/com.mastermind.executive.control",
    "replace " + CONTROL_PLIST_PATH,
    "replace " + WORKER_PLIST_PATH,
    "replace " + CONTROL_CONFIG_PATH,
    "correlate " + AUTHORITY_RECEIPT_PATH,
    "bootstrap system/" + CONTROL_PLIST_PATH,
    "publish control observation",
)

OFFLINE_EFFECTS = (
    "replace " + CONTROL_PLIST_PATH,
    "replace " + WORKER_PLIST_PATH,
    "replace " + CONTROL_CONFIG_PATH,
    "correlate " + AUTHORITY_RECEIPT_PATH,
    "enable system/com.mastermind.executive.control",
    "bootstrap system/" + CONTROL_PLIST_PATH,
    "publish control observation",
)

# The ONE immutable Fabric-binding artifact a selection publishes.  Its name
# is DERIVED from the digest of the exact composed bytes, so the destination
# is a function of its own content and the caller never supplies a path.
BINDING_ARTIFACT_PREFIX = "fabric-bindings-"
BINDING_ARTIFACT_SUFFIX = ".json"
# The closed effect of that publication.  It is inserted into the ordered
# effect list between the stopped-boundary proof and the installed
# publications, because the Control configuration may only name a binding
# artifact that already exists.
BINDING_EFFECT_PREFIX = "publish "


# The closed precondition vocabulary.  Every one of these must hold before a
# plan exists; a false precondition is a refusal with zero cutover.  The two
# modes differ ONLY in the Control boundary state they require.
_COMMON_PRECONDITIONS = (
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
)

LIVE_PRECONDITIONS = _COMMON_PRECONDITIONS + (
    "control_registered",
    "control_enabled",
    "worker_absent",
    "worker_disabled",
)

OFFLINE_PRECONDITIONS = _COMMON_PRECONDITIONS + (
    "control_absent",
    "control_disabled",
    "worker_absent",
    "worker_disabled",
)

# The receipt preimages this operation binds.  Every receipt it may replace is
# named, so an unbound receipt can never be overwritten silently.
RECEIPT_PREIMAGE_NAMES = (
    "authority_receipt",
    "ceo_submit_receipt",
    "component_receipt",
)

WARNINGS = (
    "the Control service is booted out and bootstrapped once: the endpoint is briefly unavailable",
    "the Worker daemon is never started, stopped, enabled or disarmed; it must already be absent and disabled",
    "there is no automatic rollback after a file is replaced; the sealed preimages are preserved in the "
    "transaction marker for a separately approved restore",
    "the consumed-config proof is the wrapper-owned attestation: it binds the live pid, the boot identity, "
    "the target release and the exact consumed configuration digest",
    "the offline mode requires the Control service to be already absent AND explicitly disabled; it "
    "enables and bootstraps the Control exactly once and never records a bootout it did not dispatch",
)


class ComponentError(ValueError):
    """The supplied or observed state cannot produce this component update."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def preconditions_for_mode(mode: str) -> tuple[str, ...]:
    """The closed precondition vocabulary of exactly one mode."""

    if mode == LIVE_MODE:
        return LIVE_PRECONDITIONS
    if mode == OFFLINE_MODE:
        return OFFLINE_PRECONDITIONS
    raise ComponentError("component_mode_invalid")


def binding_destination(candidate_sha256: str) -> str:
    """The derived destination of one composed Fabric-binding artifact."""

    if HEX64.fullmatch(candidate_sha256) is None:
        raise ComponentError("binding_candidate_digest_invalid")
    return (
        CONFIG_ROOT_PATH
        + "/"
        + BINDING_ARTIFACT_PREFIX
        + candidate_sha256
        + BINDING_ARTIFACT_SUFFIX
    )


def binding_effect(destination: str) -> str:
    """The closed, ordered effect of the one immutable binding publication."""

    return BINDING_EFFECT_PREFIX + destination

def effects_for_mode(mode: str, *, binding_destination: str | None = None) -> tuple[str, ...]:
    """The closed effect list of exactly one mode.

    Without a selection the list is byte-for-byte the historical one.  With
    a selection the ONE immutable binding publication is inserted between the
    stopped-boundary proof and the installed publications, because the
    Control configuration may only name a binding artifact that already
    exists.
    """

    if mode == LIVE_MODE:
        base = LIVE_EFFECTS
    elif mode == OFFLINE_MODE:
        base = OFFLINE_EFFECTS
    else:
        raise ComponentError("component_mode_invalid")
    if binding_destination is None:
        return base
    effect = binding_effect(binding_destination)
    if effect in base:
        raise ComponentError("binding_effect_already_present")
    # The bootout is the first live effect and there is no bootout at all in
    # the offline mode, so the publication follows it in the live mode and
    # leads the list in the offline mode.
    index = 1 if mode == LIVE_MODE else 0
    return base[:index] + (effect,) + base[index:]


@dataclasses.dataclass(frozen=True)
class ReceiptPreimage:
    """One receipt's exact prior state.

    ``present`` says whether the receipt existed at all; ``sha256`` is the
    digest of the EXACT raw bytes that were on disk, never of a re-encoded
    parse of them.  An absent receipt binds the digest of no bytes at all.
    """

    path: str
    present: bool
    sha256: str


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
class BindingSelectionInputs:
    """The qualified composition inputs of ONE Hermes host-read selection.

    ``input_document`` is the accepted read member and ``prior_bindings`` and
    ``prior_remote_transports`` are the EXACT execution rows of the prior
    selected binding, in their original order.  The digests and the two
    EXPLICIT presence flags are what the plan and the sealed marker carry;
    the composition itself is derived from these inputs alone.
    """

    input_document: Mapping[str, Any]
    prior_bindings: tuple[Mapping[str, Any], ...]
    prior_remote_transports: tuple[Mapping[str, Any], ...]
    input_sha256: str
    prior_binding_sha256: str
    prior_selector_present: bool
    destination_present: bool
    prior_secretary_conversation: Mapping[str, Any] | None = None
    prior_meta_conversation: Mapping[str, Any] | None = None
    prior_native_conversation: Mapping[str, Any] | None = None
    input_kind: str | None = None


@dataclasses.dataclass(frozen=True)
class BindingSelection:
    """The closed selection metadata of ONE Hermes host-read selection.

    Only hashes, EXPLICIT presence, the derived destination and the ordered
    effect are carried.  No configuration, endpoint, key or credential
    content ever reaches the plan, the sealed marker or a caller-readable
    staging.
    """

    input_sha256: str
    candidate_sha256: str
    destination: str
    destination_present: bool
    prior_selector_present: bool
    prior_binding_sha256: str
    bindings_count: int
    remote_transports_count: int
    execution_present: bool
    effect: str
    input_kind: str | None = None

    def document(self) -> dict[str, Any]:
        """The closed selection member of the plan and of the sealed marker."""

        value = {
            "input_sha256": self.input_sha256,
            "candidate_sha256": self.candidate_sha256,
            "destination": self.destination,
            "destination_present": self.destination_present,
            "prior_selector_present": self.prior_selector_present,
            "prior_binding_sha256": self.prior_binding_sha256,
            "bindings_count": self.bindings_count,
            "remote_transports_count": self.remote_transports_count,
            "execution_present": self.execution_present,
            "effect": self.effect,
        }
        if self.input_kind is not None:
            value["input_kind"] = self.input_kind
        return value


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
    # The optional closed selection metadata.  It is ABSENT -- and the
    # historical source-only behaviour is byte-for-byte unchanged -- when the
    # operation carries no Hermes host-read selection.
    selection: BindingSelection | None = None

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


def changed_keys(before: Mapping[str, Any], after: Mapping[str, Any]) -> tuple[str, ...]:
    """The changed keys of TWO documents, with EXPLICIT presence semantics.

    The comparison covers the UNION of both key sets, so a key that only one
    side carries is a change.  A newly added key is never silently accepted
    because the prior document did not mention it.
    """

    changed: list[str] = []
    for key in set(before) | set(after):
        if (key in before) != (key in after):
            changed.append(key)
        elif before[key] != after[key]:
            changed.append(key)
    return tuple(sorted(changed))


def compose_binding_candidate(
    *,
    input_document: Mapping[str, Any],
    prior_bindings: Sequence[Mapping[str, Any]],
    prior_remote_transports: Sequence[Mapping[str, Any]],
    prior_secretary_conversation: Mapping[str, Any] | None = None,
    prior_meta_conversation: Mapping[str, Any] | None = None,
    prior_native_conversation: Mapping[str, Any] | None = None,
) -> bytes:
    """The exact immutable Fabric-binding document ONE selection publishes.

    The pinned execution rows, transports and any qualified conversation
    members are carried over exactly. Only the requested host-read member
    replaces its prior selection. Legacy inputs retain the existing v3 bytes;
    Secretary, dual-role and native inputs retain their v4/v5/v6 schema.
    A v1 binding with no transports contributes an empty transport list.

    This function composes bytes and nothing else.  The read member and the
    carried rows are qualified by the incumbent owners before they arrive
    here, and the composed document is proved loadable by the incumbent
    parser before it is ever published.
    """

    from control_plane.executive_fabric_composition import (
        HOST_READ_CONFIG_SCHEMA_VERSION, SECRETARY_CONFIG_SCHEMA_VERSION,
        CONVERSATION_CONFIG_SCHEMA_VERSION, NATIVE_CONFIG_SCHEMA_VERSION,
    )

    if (prior_secretary_conversation is not None and not isinstance(prior_secretary_conversation, Mapping)
            or prior_meta_conversation is not None and not isinstance(prior_meta_conversation, Mapping)
            or prior_meta_conversation is not None and prior_secretary_conversation is None
            or prior_native_conversation is not None and (
                not isinstance(prior_native_conversation, Mapping)
                or prior_secretary_conversation is None or prior_meta_conversation is None)):
        raise ComponentError('control_component_hermes_read_binding_conflict')
    document = {
        "schema_version": HOST_READ_CONFIG_SCHEMA_VERSION,
        "bindings": [copy.deepcopy(dict(item)) for item in prior_bindings],
        "remote_transports": [
            copy.deepcopy(dict(item)) for item in prior_remote_transports
        ],
        "hermes_role_metadata_read": copy.deepcopy(dict(input_document)),
    }
    if prior_secretary_conversation is not None:
        document["schema_version"] = SECRETARY_CONFIG_SCHEMA_VERSION
        document["hermes_secretary_conversation"] = copy.deepcopy(dict(prior_secretary_conversation))
    if prior_meta_conversation is not None:
        document["schema_version"] = CONVERSATION_CONFIG_SCHEMA_VERSION
        document["hermes_meta_conversation"] = copy.deepcopy(dict(prior_meta_conversation))
    if prior_native_conversation is not None:
        document["schema_version"] = NATIVE_CONFIG_SCHEMA_VERSION
        document["native_conversation"] = copy.deepcopy(dict(prior_native_conversation))
    return (json.dumps(
        document, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False
    ) + "\n").encode("utf-8")


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
    selection: BindingSelectionInputs | None = None,
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

    selection_metadata: BindingSelection | None = None
    selector: dict[str, str] | None = None
    if selection is not None:
        if (selection.input_kind not in (None, "native_conversation")
                or selection.input_kind == "native_conversation" and (
                    not selection.prior_selector_present
                    or selection.prior_native_conversation is None
                    or selection.prior_secretary_conversation is None
                    or selection.prior_meta_conversation is None)):
            raise ComponentError("control_component_native_conversation_binding_conflict")
        if HEX64.fullmatch(selection.input_sha256) is None:
            raise ComponentError("binding_input_digest_invalid")
        if selection.prior_selector_present and (
            HEX64.fullmatch(selection.prior_binding_sha256) is None
        ):
            raise ComponentError("binding_prior_digest_invalid")
        composed = compose_binding_candidate(
            input_document=selection.input_document,
            prior_bindings=selection.prior_bindings,
            prior_remote_transports=selection.prior_remote_transports,
            prior_secretary_conversation=selection.prior_secretary_conversation,
            prior_meta_conversation=selection.prior_meta_conversation,
            prior_native_conversation=selection.prior_native_conversation,
        )
        candidate_sha256 = digest(composed)
        destination = binding_destination(candidate_sha256)
        selector = {"path": destination, "sha256": candidate_sha256}
        selection_metadata = BindingSelection(
            input_sha256=selection.input_sha256,
            candidate_sha256=candidate_sha256,
            destination=destination,
            destination_present=bool(selection.destination_present),
            prior_selector_present=bool(selection.prior_selector_present),
            prior_binding_sha256=selection.prior_binding_sha256,
            bindings_count=len(selection.prior_bindings),
            remote_transports_count=len(selection.prior_remote_transports),
            execution_present=bool(
                selection.prior_bindings or selection.prior_remote_transports
            ),
            effect=binding_effect(destination),
            input_kind=selection.input_kind,
        )

    try:
        successor = build_component_successor(
            document, source_sha=target_sha, fabric_bindings=selector
        )
    except PreparationError as exc:
        raise ComponentError("control_config_successor_invalid") from exc
    changed = changed_keys(document, successor)
    allowed = ("proof_base_sha", "proof_source_repository")
    if selector is not None:
        allowed = (
            "fabric_bindings_path",
            "fabric_bindings_sha256",
            "proof_base_sha",
            "proof_source_repository",
        )
    if (selection is not None and selection.input_kind == "native_conversation"
            and document.get("fabric_bindings_path") == selector["path"]
            and document.get("fabric_bindings_sha256") == selector["sha256"]):
        allowed = ("proof_base_sha", "proof_source_repository")
    if changed != allowed:
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
        selection=selection_metadata,
    )


def plan_document(
    candidate: Candidate,
    *,
    mode: str,
    preconditions: Mapping[str, bool],
    prior_release_manifest_sha256: str,
    target_release_manifest_sha256: str,
    admin_checkout_commit: str,
    receipts: Mapping[str, ReceiptPreimage],
    launchd_disabled: Mapping[str, bool],
) -> dict[str, Any]:
    """The closed plan document: hashes, source ids, states and effects only."""

    expected = preconditions_for_mode(mode)
    if set(preconditions) != set(expected):
        raise ComponentError("precondition_vocabulary_invalid")
    if any(type(state) is not bool for state in preconditions.values()):
        raise ComponentError("precondition_state_invalid")
    if set(launchd_disabled) != {"control", "worker"}:
        raise ComponentError("launchd_preimage_invalid")
    if any(type(state) is not bool for state in launchd_disabled.values()):
        raise ComponentError("launchd_preimage_invalid")
    # The Worker is disabled in BOTH modes, and the Control is explicitly
    # disabled in exactly the offline mode.  A preimage that contradicts the
    # mode is a mismatched state and never reaches a plan.
    if launchd_disabled["worker"] is not True:
        raise ComponentError("launchd_preimage_invalid")
    if (mode == OFFLINE_MODE) is not (launchd_disabled["control"] is True):
        raise ComponentError("launchd_preimage_invalid")
    if set(receipts) != set(RECEIPT_PREIMAGE_NAMES):
        raise ComponentError("receipt_preimage_invalid")
    for value in receipts.values():
        if type(value) is not ReceiptPreimage:
            raise ComponentError("receipt_preimage_invalid")
        if HEX64.fullmatch(value.sha256) is None:
            raise ComponentError("receipt_preimage_invalid")
    document = {
        "schema": PLAN_SCHEMA,
        "mode": mode,
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
        "receipts": {
            name: {
                "path": receipts[name].path,
                "present": receipts[name].present,
                "before_sha256": receipts[name].sha256,
            }
            for name in RECEIPT_PREIMAGE_NAMES
        },
        "launchd_disabled": {
            "control": launchd_disabled["control"],
            "worker": launchd_disabled["worker"],
        },
        "prior_release_manifest_sha256": prior_release_manifest_sha256,
        "target_release_manifest_sha256": target_release_manifest_sha256,
        "admin_checkout_commit": admin_checkout_commit,
        "preconditions": {key: bool(preconditions[key]) for key in expected},
        "effects": list(
            effects_for_mode(
                mode,
                binding_destination=(
                    candidate.selection.destination
                    if candidate.selection is not None
                    else None
                ),
            )
        ),
    }
    if candidate.selection is not None:
        # The closed selection metadata: hashes, EXPLICIT presence, the
        # derived destination and the ordered effect.  It is ABSENT when the
        # operation carries no selection, so the source-only plan stays
        # byte-for-byte unchanged.
        document["selection"] = candidate.selection.document()
    return document


# ---------------------------------------------------------------------------
# Orchestration.  These functions hold no authority of their own: each one
# calls the incumbent owner in ``ops.executive_os.autonomy_control`` and
# returns its typed result.
# ---------------------------------------------------------------------------


def hermes_read_selector(
    input_path: str | None, input_sha256: str | None
) -> tuple[str, str] | None:
    """The PAIRED Hermes host-read selection, or NOTHING.

    The two coordinates are one selection: the exact qualified input path
    and the exact digest of its raw bytes.  Both absent preserve the
    existing source-only behaviour byte-for-byte; exactly one of them is a
    refusal and is never treated as an absent selection.
    """

    if input_path is None and input_sha256 is None:
        return None
    if input_path is None or input_sha256 is None:
        raise ComponentError("control_component_hermes_read_selector_incomplete")
    if type(input_path) is not str or not input_path:
        raise ComponentError("control_component_hermes_read_input_invalid")
    if HEX64.fullmatch(input_sha256) is None:
        raise ComponentError("control_component_hermes_read_input_invalid")
    return (input_path, input_sha256)


def native_conversation_selector(input_path: str | None, input_sha256: str | None) -> tuple[str, str] | None:
    """One explicit expected native selection on the incumbent update carrier."""
    if input_path is None and input_sha256 is None:
        return None
    if input_path is None or input_sha256 is None:
        raise ComponentError("control_component_native_conversation_selector_incomplete")
    if (type(input_path) is not str or not input_path
            or type(input_sha256) is not str or HEX64.fullmatch(input_sha256) is None):
        raise ComponentError("control_component_native_conversation_input_invalid")
    return input_path, input_sha256


def plan(
    host: Any,
    *,
    target_sha: str,
    hermes_read_input: str | None = None,
    hermes_read_sha256: str | None = None,
    native_conversation_input: str | None = None,
    native_conversation_sha256: str | None = None,
) -> dict[str, Any]:
    """Compile and prove the plan.  Read-only: no marker, no effect."""

    if HEX40.fullmatch(target_sha) is None:
        raise ComponentError("release_sha_invalid")
    selector = hermes_read_selector(hermes_read_input, hermes_read_sha256)
    native = native_conversation_selector(native_conversation_input, native_conversation_sha256)
    if native is not None and selector is not None:
        raise ComponentError("control_component_selection_conflict")
    options = dict(target_sha=target_sha, hermes_read=selector)
    if native is not None:
        options["native_conversation"] = native
    observation = host.observe_control_component_update(**options)
    document = observation["plan"]
    return {
        "ok": True,
        "outcome": "PLANNED",
        "plan": document,
        "plan_sha256": plan_digest(document),
        "warnings": list(WARNINGS),
    }


def apply(
    host: Any,
    *,
    target_sha: str,
    plan_sha256: str,
    hermes_read_input: str | None = None,
    hermes_read_sha256: str | None = None,
    native_conversation_input: str | None = None,
    native_conversation_sha256: str | None = None,
) -> dict[str, Any]:
    """Publish exactly the approved plan through the incumbent owner."""

    from ops.executive_os import autonomy_control as owner

    if HEX40.fullmatch(target_sha) is None:
        raise ComponentError("release_sha_invalid")
    if HEX64.fullmatch(plan_sha256) is None:
        raise ComponentError("plan_sha256_invalid")
    selector = hermes_read_selector(hermes_read_input, hermes_read_sha256)
    native = native_conversation_selector(native_conversation_input, native_conversation_sha256)
    if native is not None and selector is not None:
        raise ComponentError("control_component_selection_conflict")
    options = dict(target_sha=target_sha, plan_sha256=plan_sha256, hermes_read=selector)
    if native is not None:
        options["native_conversation"] = native
    return owner.execute_control_component_update(host, **options)


def reconcile(host: Any, *, target_sha: str) -> dict[str, Any]:
    """Prove one interrupted update to its exact retained postimages.

    A reconciliation takes NO replacement input: the original selection is
    reconstructed from the SEALED bytes of the original operation.
    """

    from ops.executive_os import autonomy_control as owner

    if HEX40.fullmatch(target_sha) is None:
        raise ComponentError("release_sha_invalid")
    return owner.reconcile_control_component_update(host, target_sha=target_sha)

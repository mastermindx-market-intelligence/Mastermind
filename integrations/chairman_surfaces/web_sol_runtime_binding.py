"""Pure exact-target and boot-bound RuntimeBinding projection for Web-Sol.

This module owns no browser, filesystem, lifecycle, persistence, navigation
write, provider action, retry, wake, or semantic acknowledgement.  It accepts
one already-validated managed-profile navigation coordinate, one complete live
profile census, one logical SessionTarget, and one current native transport
boot nonce.  The result is an immutable projection onto the existing
``control_plane.session_targets.RuntimeBinding`` type.

``surface_bindings`` remains navigation only.  Its conversation URL is not
promoted to authority and is deliberately absent from every projected value.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any

from control_plane import surface_bindings as sb
from control_plane.session_targets import RuntimeBinding, SessionTarget

from . import web_sol_census_protocol as census
from . import web_sol_instance as instance
from . import web_sol_protocol as protocol


_TARGET_SCHEMA = "mastermind.web_sol_exact_runtime_target.v1"
_BINDING_SCHEMA = "mastermind.web_sol_runtime_binding_projection.v1"
_BINDING_FINGERPRINT_SCHEMA = "mastermind.web_sol_runtime_binding_fingerprint.v1"
_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
_BINDING_ID_PREFIX = "bind-wsx-"
_NATIVE_HANDLE_PREFIX = "wsx-runtime-"
_RUNTIME_REASONING_SURFACE = "chatgpt-sol"
_SESSION_ALIAS_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{2,255}$")


class WebSolRuntimeBindingError(ValueError):
    """Stable, secret-free refusal from exact target/binding projection."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _refuse(code: str) -> None:
    raise WebSolRuntimeBindingError(code)


def _canonical_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError):
        _refuse("projection_value_invalid")


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _hex64(value: Any) -> bool:
    return isinstance(value, str) and _HEX64_RE.fullmatch(value) is not None


def _transport_nonce(value: Any) -> str:
    if (
        not isinstance(value, str)
        or not 16 <= len(value) <= 128
        or any(character.isspace() for character in value)
    ):
        _refuse("boot_nonce_invalid")
    return value


def _accepted_navigation_binding(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        _refuse("navigation_binding_invalid")
    problems = sb.validate_bindings_document(
        {"schema": sb.SCHEMA, "bindings": [value]}
    )
    if problems:
        _refuse("navigation_binding_invalid")
    if (
        value.get("provider") != "chatgpt"
        or value.get("locator_kind") != "chatgpt_managed_env"
        or not isinstance(value.get("seat_ref"), str)
        or not value["seat_ref"].strip()
    ):
        _refuse("navigation_binding_invalid")
    return value


@dataclass(frozen=True, slots=True)
class ExactWebSolTarget:
    """Secret-free exact target proven by one bounded profile census."""

    adapter_instance_id: str
    seat_ref: str
    env_manager: str
    folder_id: str | None
    profile_id: str
    conversation_fingerprint: str
    census_digest: str

    def __post_init__(self) -> None:
        if not _hex64(self.adapter_instance_id):
            _refuse("exact_target_invalid")
        if not isinstance(self.seat_ref, str) or not self.seat_ref.strip():
            _refuse("exact_target_invalid")
        if self.env_manager not in sb.ENV_MANAGERS:
            _refuse("exact_target_invalid")
        if not isinstance(self.profile_id, str) or not self.profile_id:
            _refuse("exact_target_invalid")
        if self.env_manager == "multilogin":
            if (
                not isinstance(self.folder_id, str)
                or sb.UUID_RE.fullmatch(self.folder_id) is None
                or sb.UUID_RE.fullmatch(self.profile_id) is None
            ):
                _refuse("exact_target_invalid")
        elif (
            self.folder_id is not None
            or sb.GOLOGIN_PROFILE_ID_RE.fullmatch(self.profile_id) is None
        ):
            _refuse("exact_target_invalid")
        if not _hex64(self.conversation_fingerprint) or not _hex64(
            self.census_digest
        ):
            _refuse("exact_target_invalid")

    def identity_document(self) -> dict[str, Any]:
        """Return a detached closed identity document with no URL/title/text."""

        return {
            "schema": _TARGET_SCHEMA,
            "adapter_instance_id": self.adapter_instance_id,
            "seat_ref": self.seat_ref,
            "env_manager": self.env_manager,
            "folder_id": self.folder_id,
            "profile_id": self.profile_id,
            "conversation_fingerprint": self.conversation_fingerprint,
        }


def exact_target_from_census(
    navigation_binding: dict[str, Any],
    census_receipt: dict[str, Any],
) -> ExactWebSolTarget:
    """Project the sole exact authenticated idle conversation in one profile.

    The navigation row contributes only the already-reviewed managed profile
    coordinate and seat label.  Its URL is not compared, copied, returned, or
    treated as current authority.  Exact conversation identity comes from the
    bounded live census and is admitted only when no alternate normal ChatGPT
    conversation, duplicate tab, private tab, omission, or inventory movement
    exists in that profile.
    """

    binding = _accepted_navigation_binding(navigation_binding)
    try:
        accepted_receipt = census.validate_census_receipt(census_receipt)
    except (protocol.WebSolProtocolError, TypeError, ValueError):
        _refuse("census_invalid")

    if accepted_receipt["status"] != "COLLECTED":
        _refuse("census_not_collected")

    try:
        expected_instance = instance.adapter_instance_id(binding)
    except instance.WebSolInstanceError:
        _refuse("navigation_binding_invalid")
    if accepted_receipt["adapter_instance_id"] != expected_instance:
        _refuse("adapter_instance_mismatch")

    try:
        snapshot = census.decode_snapshot(accepted_receipt["snapshot"])
    except (protocol.WebSolProtocolError, TypeError, ValueError):
        _refuse("census_invalid")

    complete = (
        snapshot["inventory_coverage"] == "COMPLETE_IN_SCOPE"
        and snapshot["consistency"] == "STABLE_AT_BOUNDARIES"
        and snapshot["reason"] == "NONE"
        and snapshot["excluded_private_count"] == 0
        and snapshot["omitted_tab_count"] == 0
        and snapshot["unobserved_added_count"] == 0
        and snapshot["probe_coverage"] in {"NONE", "COMPLETE_IN_SCOPE"}
    )
    if not complete:
        _refuse("census_incomplete")

    cardinality = (
        snapshot["initial_tab_count"],
        snapshot["final_tab_count"],
        snapshot["unique_conversation_count"],
        snapshot["duplicate_tab_count"],
        snapshot["probed_tab_count"],
        len(snapshot["rows"]),
    )
    if cardinality == (0, 0, 0, 0, 0, 0):
        _refuse("exact_conversation_missing")
    if cardinality != (1, 1, 1, 0, 1, 1):
        _refuse("exact_conversation_ambiguous")

    row = snapshot["rows"][0]
    if (
        row["status"] != "OBSERVED"
        or row["identity_evidence"] != "LOCATOR_AND_V1_PROBE"
        or row["duplicate_count"] != 1
        or row["duplicate_cue_disagreement"] is not False
        or row["discarded"] is True
        or row["frozen"] is True
        or not _hex64(row["conversation_fingerprint"])
    ):
        _refuse("exact_conversation_invalid")
    if row["auth_required"] is not False:
        _refuse("authentication_required")
    if row["provider_error_present"] is not False:
        _refuse("provider_error")
    if row["generation_cue"] != "NOT_OBSERVED":
        _refuse("generation_not_idle")

    locator = binding["locator"]
    return ExactWebSolTarget(
        adapter_instance_id=expected_instance,
        seat_ref=str(binding["seat_ref"]),
        env_manager=str(locator["env_manager"]),
        folder_id=locator.get("folder_id"),
        profile_id=str(locator["profile_id"]),
        conversation_fingerprint=row["conversation_fingerprint"],
        census_digest=_digest(accepted_receipt),
    )


def _accepted_session_alias(value: Any) -> str:
    if not isinstance(value, str) or _SESSION_ALIAS_RE.fullmatch(value) is None:
        _refuse("session_alias_invalid")
    return value


def _accepted_logical_target(value: Any) -> SessionTarget:
    if (
        not isinstance(value, SessionTarget)
        or value.target_seat != "ceo"
        or value.reasoning_surface != _RUNTIME_REASONING_SURFACE
    ):
        _refuse("logical_target_mismatch")
    _accepted_session_alias(value.session_alias)
    return value


def _binding_projection_document(
    *,
    adapter_instance_id: str,
    conversation_fingerprint: str,
    session_alias: str,
    boot_nonce: str,
) -> dict[str, Any]:
    return {
        "schema": _BINDING_SCHEMA,
        "adapter_instance_id": adapter_instance_id,
        "conversation_fingerprint": conversation_fingerprint,
        "session_alias": session_alias,
        "reasoning_surface": _RUNTIME_REASONING_SURFACE,
        "boot_nonce": boot_nonce,
    }


def _runtime_binding_fingerprint_values(
    *,
    adapter_instance_id: str,
    conversation_fingerprint: str,
    session_alias: str,
    runtime_binding_id: str,
    runtime_binding_generation: int,
) -> str:
    return _digest(
        {
            "schema": _BINDING_FINGERPRINT_SCHEMA,
            "adapter_instance_id": adapter_instance_id,
            "conversation_fingerprint": conversation_fingerprint,
            "session_alias": session_alias,
            "reasoning_surface": _RUNTIME_REASONING_SURFACE,
            "runtime_binding_id": runtime_binding_id,
            "runtime_binding_generation": runtime_binding_generation,
        }
    )


def derive_runtime_binding_wire(
    *,
    adapter_instance_id: str,
    conversation_fingerprint: str,
    session_alias: str,
    boot_nonce: str,
) -> dict[str, Any]:
    """Derive the host-verifiable boot-bound RuntimeBinding wire identity."""

    try:
        instance.validate_instance_id(adapter_instance_id)
    except instance.WebSolInstanceError:
        _refuse("adapter_instance_invalid")
    if not _hex64(conversation_fingerprint):
        _refuse("conversation_fingerprint_invalid")
    alias = _accepted_session_alias(session_alias)
    boot = _transport_nonce(boot_nonce)
    digest = _digest(
        _binding_projection_document(
            adapter_instance_id=adapter_instance_id,
            conversation_fingerprint=conversation_fingerprint,
            session_alias=alias,
            boot_nonce=boot,
        )
    )
    binding_id = f"{_BINDING_ID_PREFIX}{digest[:48]}"
    generation = 1
    return {
        "session_alias": alias,
        "runtime_binding_id": binding_id,
        "runtime_binding_generation": generation,
        "runtime_binding_fingerprint": _runtime_binding_fingerprint_values(
            adapter_instance_id=adapter_instance_id,
            conversation_fingerprint=conversation_fingerprint,
            session_alias=alias,
            runtime_binding_id=binding_id,
            runtime_binding_generation=generation,
        ),
        "native_handle": f"{_NATIVE_HANDLE_PREFIX}{digest[48:]}",
    }


def project_runtime_binding(
    target: ExactWebSolTarget,
    logical_target: SessionTarget,
    *,
    boot_nonce: str,
) -> RuntimeBinding:
    """Project one current native-host life onto the existing RuntimeBinding.

    Generation is one within this immutable boot-bound identity. Restarting
    the native host changes ``binding_id`` itself, so a later generation-one
    projection cannot ABA-match the prior life.
    """

    if not isinstance(target, ExactWebSolTarget):
        _refuse("exact_target_invalid")
    logical = _accepted_logical_target(logical_target)
    wire = derive_runtime_binding_wire(
        adapter_instance_id=target.adapter_instance_id,
        conversation_fingerprint=target.conversation_fingerprint,
        session_alias=logical.session_alias,
        boot_nonce=boot_nonce,
    )
    return RuntimeBinding(
        session_alias=wire["session_alias"],
        binding_id=wire["runtime_binding_id"],
        binding_generation=wire["runtime_binding_generation"],
        native_handle=wire["native_handle"],
        account_label=target.seat_ref,
        reasoning_surface=_RUNTIME_REASONING_SURFACE,
    )


def runtime_binding_fingerprint(
    binding: RuntimeBinding,
    target: ExactWebSolTarget,
) -> str:
    """Return host-verifiable closed correlation for one binding/target."""

    if not isinstance(binding, RuntimeBinding) or not isinstance(
        target, ExactWebSolTarget
    ):
        _refuse("runtime_binding_invalid")
    if (
        binding.reasoning_surface != _RUNTIME_REASONING_SURFACE
        or binding.account_label != target.seat_ref
        or type(binding.binding_generation) is not int
        or binding.binding_generation < 1
    ):
        _refuse("runtime_binding_invalid")
    _accepted_session_alias(binding.session_alias)
    return _runtime_binding_fingerprint_values(
        adapter_instance_id=target.adapter_instance_id,
        conversation_fingerprint=target.conversation_fingerprint,
        session_alias=binding.session_alias,
        runtime_binding_id=binding.binding_id,
        runtime_binding_generation=binding.binding_generation,
    )


@dataclass(frozen=True, slots=True)
class WebSolRuntimeBindingLease:
    """One detached exact target plus its current boot-bound RuntimeBinding."""

    target: ExactWebSolTarget
    runtime_binding: RuntimeBinding
    runtime_binding_fingerprint: str

    def __post_init__(self) -> None:
        if not isinstance(self.target, ExactWebSolTarget) or not isinstance(
            self.runtime_binding, RuntimeBinding
        ):
            _refuse("runtime_binding_lease_invalid")
        expected = runtime_binding_fingerprint(self.runtime_binding, self.target)
        if self.runtime_binding_fingerprint != expected:
            _refuse("runtime_binding_lease_invalid")


__all__ = [
    "ExactWebSolTarget",
    "WebSolRuntimeBindingError",
    "WebSolRuntimeBindingLease",
    "derive_runtime_binding_wire",
    "exact_target_from_census",
    "project_runtime_binding",
    "runtime_binding_fingerprint",
]

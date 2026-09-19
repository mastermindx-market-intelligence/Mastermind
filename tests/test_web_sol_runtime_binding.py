"""Exact managed Web-Sol target and boot-bound RuntimeBinding contracts."""
from __future__ import annotations

import copy
import dataclasses
import re

import pytest

from control_plane import surface_bindings as sb
from control_plane.session_targets import RuntimeBinding, SessionTarget
from integrations.chairman_surfaces import web_sol_census_protocol as census
from integrations.chairman_surfaces import web_sol_instance as instance
from integrations.chairman_surfaces import web_sol_runtime_binding as runtime_binding


FOLDER_ID = "7ddbe74e-5c8e-4edf-bf05-7260c4233025"
PROFILE_ID = "717baf42-a7b9-4c5c-ae82-dfdd5832eee3"
CONVERSATION_URL = "https://chatgpt.com/c/disposable-r3-fixture"
CONVERSATION_FINGERPRINT = "b" * 64
BOOT_NONCE = "boot-nonce-fixture-0000000001"


def _binding(**changes) -> dict:
    value = sb.new_binding(
        work_ref="WS:WEB-SOL-R3",
        role="ceo",
        provider="chatgpt",
        locator_kind="chatgpt_managed_env",
        locator={
            "env_manager": "multilogin",
            "folder_id": FOLDER_ID,
            "profile_id": PROFILE_ID,
            "url": CONVERSATION_URL,
        },
        observed_at="2026-09-18T20:00:00Z",
        last_verified_at="2026-09-18T20:00:00Z",
        seat_ref="chatgpt3",
        binding_id="11111111-1111-4111-8111-111111111111",
    )
    value.update(changes)
    return value


def _session_target(**changes) -> SessionTarget:
    values = {
        "session_alias": "EXECUTIVE-CEO-A",
        "target_seat": "ceo",
        "reasoning_surface": "chatgpt-sol",
        "wake_transport": "chatgpt-gui",
        "allowed_transports": ("chatgpt-gui",),
        "workstream": "executive",
        "target_enabled": True,
    }
    values.update(changes)
    return SessionTarget(**values)


def _snapshot(
    *,
    adapter_instance_id: str,
    fingerprints: tuple[str, ...] = (CONVERSATION_FINGERPRINT,),
    generation_cues: tuple[str, ...] | None = None,
    auth_required: bool = False,
    provider_error_present: bool = False,
) -> dict:
    if generation_cues is None:
        generation_cues = tuple("NOT_OBSERVED" for _ in fingerprints)
    assert len(generation_cues) == len(fingerprints)
    rows = []
    groups = {fingerprint: fingerprints.count(fingerprint) for fingerprint in fingerprints}
    for index, (fingerprint, cue) in enumerate(zip(fingerprints, generation_cues, strict=True), start=1):
        rows.append(
            {
                "slot": index,
                "conversation_fingerprint": fingerprint,
                "identity_evidence": "LOCATOR_AND_V1_PROBE",
                "document_binding": "UNVERIFIED",
                "status": "OBSERVED",
                "generation_cue": cue,
                "selected_in_window": index == 1,
                "discarded": False,
                "frozen": False,
                "visibility": "VISIBLE" if index == 1 else "HIDDEN",
                "auth_required": auth_required,
                "provider_error_present": provider_error_present,
                "duplicate_count": groups[fingerprint],
                "duplicate_cue_disagreement": len(
                    {
                        generation_cues[position]
                        for position, value in enumerate(fingerprints)
                        if value == fingerprint
                    }
                )
                > 1,
                "observed_at": "2026-09-18T20:00:00.500Z",
                "selected_model": None,
                "selected_effort": None,
                "served_model": None,
                "model_evidence": "UNVERIFIED",
            }
        )
    unique = set(fingerprints)
    return {
        "schema": census.LOCAL_SCHEMA,
        "scope": "CURRENT_PROFILE_NORMAL_CHATGPT_TABS",
        "adapter_instance_id": adapter_instance_id,
        "started_at": "2026-09-18T20:00:00.000Z",
        "completed_at": "2026-09-18T20:00:01.000Z",
        "duration_ms": 1000,
        "inventory_coverage": "COMPLETE_IN_SCOPE",
        "consistency": "STABLE_AT_BOUNDARIES",
        "reason": "NONE",
        "initial_tab_count": len(rows),
        "final_tab_count": len(rows),
        "excluded_private_count": 0,
        "omitted_tab_count": 0,
        "unobserved_added_count": 0,
        "unique_conversation_count": len(unique),
        "duplicate_tab_count": len(rows) - len(unique),
        "probed_tab_count": len(rows),
        "generation_cue_count": sum(cue == "PRESENT" for cue in generation_cues),
        "unknown_cue_count": sum(cue == "UNKNOWN" for cue in generation_cues),
        "probe_coverage": "COMPLETE_IN_SCOPE" if rows else "NONE",
        "rows": rows,
    }


def _receipt(
    binding: dict | None = None,
    *,
    adapter_instance_id: str | None = None,
    fingerprints: tuple[str, ...] = (CONVERSATION_FINGERPRINT,),
    generation_cues: tuple[str, ...] | None = None,
    auth_required: bool = False,
    provider_error_present: bool = False,
    status: str = "COLLECTED",
) -> dict:
    navigation = binding or _binding()
    adapter = adapter_instance_id or instance.adapter_instance_id(navigation)
    snapshot = None
    if status == "COLLECTED":
        snapshot = census.encode_snapshot(
            _snapshot(
                adapter_instance_id=adapter,
                fingerprints=fingerprints,
                generation_cues=generation_cues,
                auth_required=auth_required,
                provider_error_present=provider_error_present,
            )
        )
    return {
        "schema": census.RECEIPT_SCHEMA,
        "adapter_instance_id": adapter,
        "operation_key": "web-sol-r3-census-fixture",
        "nonce": "census-nonce-fixture-00000001",
        "status": status,
        "snapshot": snapshot,
    }


def _exact_target():
    navigation = _binding()
    return runtime_binding.exact_target_from_census(navigation, _receipt(navigation))


def test_exact_target_requires_one_complete_stable_authenticated_idle_conversation() -> None:
    navigation = _binding()
    target = runtime_binding.exact_target_from_census(navigation, _receipt(navigation))

    assert target.adapter_instance_id == instance.adapter_instance_id(navigation)
    assert target.seat_ref == "chatgpt3"
    assert target.env_manager == "multilogin"
    assert target.folder_id == FOLDER_ID
    assert target.profile_id == PROFILE_ID
    assert target.conversation_fingerprint == CONVERSATION_FINGERPRINT
    assert re.fullmatch(r"[0-9a-f]{64}", target.census_digest)

    public = dataclasses.asdict(target)
    assert set(public) == {
        "adapter_instance_id",
        "seat_ref",
        "env_manager",
        "folder_id",
        "profile_id",
        "conversation_fingerprint",
        "census_digest",
    }
    serialized = repr(public)
    assert CONVERSATION_URL not in serialized
    assert "WEB-SOL-R3" not in serialized
    assert "title" not in serialized.lower()
    assert "transcript" not in serialized.lower()


@pytest.mark.parametrize(
    ("receipt_factory", "code"),
    [
        (lambda binding: _receipt(binding, adapter_instance_id="f" * 64), "adapter_instance_mismatch"),
        (lambda binding: _receipt(binding, fingerprints=()), "exact_conversation_missing"),
        (
            lambda binding: _receipt(binding, fingerprints=("b" * 64, "c" * 64)),
            "exact_conversation_ambiguous",
        ),
        (lambda binding: _receipt(binding, auth_required=True), "authentication_required"),
        (lambda binding: _receipt(binding, provider_error_present=True), "provider_error"),
        (
            lambda binding: _receipt(binding, generation_cues=("PRESENT",)),
            "generation_not_idle",
        ),
        (
            lambda binding: _receipt(binding, status="COLLECTOR_UNAVAILABLE"),
            "census_not_collected",
        ),
    ],
)
def test_exact_target_refuses_unsuitable_or_ambiguous_census(receipt_factory, code) -> None:
    navigation = _binding()
    with pytest.raises(runtime_binding.WebSolRuntimeBindingError) as excinfo:
        runtime_binding.exact_target_from_census(navigation, receipt_factory(navigation))
    assert excinfo.value.code == code


def test_exact_target_refuses_duplicate_tab_for_same_conversation() -> None:
    navigation = _binding()
    with pytest.raises(runtime_binding.WebSolRuntimeBindingError) as excinfo:
        runtime_binding.exact_target_from_census(
            navigation,
            _receipt(
                navigation,
                fingerprints=(CONVERSATION_FINGERPRINT, CONVERSATION_FINGERPRINT),
            ),
        )
    assert excinfo.value.code == "exact_conversation_ambiguous"


def test_runtime_binding_projection_is_deterministic_and_bound_to_native_boot() -> None:
    target = _exact_target()
    logical = _session_target()

    first = runtime_binding.project_runtime_binding(
        target,
        logical,
        boot_nonce=BOOT_NONCE,
    )
    repeated = runtime_binding.project_runtime_binding(
        target,
        logical,
        boot_nonce=BOOT_NONCE,
    )
    restarted = runtime_binding.project_runtime_binding(
        target,
        logical,
        boot_nonce="boot-nonce-fixture-0000000002",
    )

    assert isinstance(first, RuntimeBinding)
    assert first == repeated
    assert first.session_alias == logical.session_alias
    assert first.reasoning_surface == "chatgpt-sol"
    assert first.account_label == "chatgpt3"
    assert first.binding_generation == 1
    assert first.binding_id.startswith("bind-wsx-")
    assert first.binding_id != restarted.binding_id
    assert first.native_handle != restarted.native_handle

    first_fingerprint = runtime_binding.runtime_binding_fingerprint(first, target)
    assert re.fullmatch(r"[0-9a-f]{64}", first_fingerprint)
    assert first_fingerprint == runtime_binding.runtime_binding_fingerprint(repeated, target)
    assert first_fingerprint != runtime_binding.runtime_binding_fingerprint(restarted, target)


@pytest.mark.parametrize(
    ("logical", "boot_nonce", "code"),
    [
        (_session_target(target_seat="coo"), BOOT_NONCE, "logical_target_mismatch"),
        (
            _session_target(reasoning_surface="codex"),
            BOOT_NONCE,
            "logical_target_mismatch",
        ),
        (_session_target(), "short", "boot_nonce_invalid"),
        (_session_target(), "boot nonce with spaces", "boot_nonce_invalid"),
    ],
)
def test_runtime_binding_projection_refuses_wrong_target_or_boot(logical, boot_nonce, code) -> None:
    with pytest.raises(runtime_binding.WebSolRuntimeBindingError) as excinfo:
        runtime_binding.project_runtime_binding(
            _exact_target(),
            logical,
            boot_nonce=boot_nonce,
        )
    assert excinfo.value.code == code


def test_runtime_binding_projection_detaches_inputs_and_never_embeds_navigation_url() -> None:
    navigation = _binding()
    target = runtime_binding.exact_target_from_census(navigation, _receipt(navigation))
    projected = runtime_binding.project_runtime_binding(
        target,
        _session_target(),
        boot_nonce=BOOT_NONCE,
    )
    navigation["locator"]["url"] = "https://chatgpt.com/c/mutated-after-projection"
    wire = dataclasses.asdict(projected)
    assert CONVERSATION_URL not in repr(wire)
    assert "mutated-after-projection" not in repr(wire)
    assert projected.account_label == "chatgpt3"

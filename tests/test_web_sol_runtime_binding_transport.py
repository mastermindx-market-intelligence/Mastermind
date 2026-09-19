"""RuntimeBinding-gated Web-Sol continuation transport contracts."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import inspect

import pytest

from control_plane import surface_bindings as sb
from control_plane.session_targets import SessionTarget
from integrations.chairman_surfaces import web_sol_census_protocol as census
from integrations.chairman_surfaces import web_sol_client as client
from integrations.chairman_surfaces import web_sol_instance as instance
from integrations.chairman_surfaces import web_sol_native_host as native
from integrations.chairman_surfaces import web_sol_protocol as protocol
from integrations.chairman_surfaces import web_sol_runtime_binding as runtime


PROFILE_ID = "aaaaaaaaaaaaaaaaaaaaaaaa"
CONVERSATION_FINGERPRINT = "b" * 64
BOOT_ONE = "runtime-boot-nonce-000000000001"
BOOT_TWO = "runtime-boot-nonce-000000000002"
TURN_ID = "ohf-turn-runtime-bound-0001"
WAKE_IDS = ("WAKE-" + "a" * 32,)
WAKE_DIGEST = protocol.wake_obligation_digest(WAKE_IDS)
NONCE = "runtime-bound-nonce-00000001"
OPERATION = "web-sol-exact-continuation-return-r3-20260918-sol-001"


def navigation_binding() -> dict:
    return sb.new_binding(
        work_ref="WS:WEB-SOL-R3",
        role="ceo",
        provider="chatgpt",
        locator_kind="chatgpt_managed_env",
        locator={
            "env_manager": "gologin",
            "profile_id": PROFILE_ID,
            "url": "https://chatgpt.com/c/stale-navigation-only",
        },
        observed_at="2026-09-18T20:00:00Z",
        seat_ref="chatgpt-test-seat",
        binding_id="11111111-1111-4111-8111-111111111111",
    )


def logical_target() -> SessionTarget:
    return SessionTarget(
        session_alias="EXECUTIVE-CEO-A",
        target_seat="ceo",
        reasoning_surface="chatgpt-sol",
        wake_transport="chatgpt-gui",
        allowed_transports=("chatgpt-gui",),
        workstream="executive",
        target_enabled=True,
    )


def exact_target(binding: dict | None = None) -> runtime.ExactWebSolTarget:
    row = binding or navigation_binding()
    return runtime.ExactWebSolTarget(
        adapter_instance_id=instance.adapter_instance_id(row),
        seat_ref=row["seat_ref"],
        env_manager=row["locator"]["env_manager"],
        folder_id=row["locator"].get("folder_id"),
        profile_id=row["locator"]["profile_id"],
        conversation_fingerprint=CONVERSATION_FINGERPRINT,
        census_digest="c" * 64,
    )


def lease(boot_nonce: str = BOOT_ONE) -> runtime.WebSolRuntimeBindingLease:
    target = exact_target()
    binding = runtime.project_runtime_binding(
        target,
        logical_target(),
        boot_nonce=boot_nonce,
    )
    return runtime.WebSolRuntimeBindingLease(
        target=target,
        runtime_binding=binding,
        runtime_binding_fingerprint=runtime.runtime_binding_fingerprint(binding, target),
    )


def now_window() -> tuple[str, str]:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    return (
        now.isoformat().replace("+00:00", "Z"),
        (now + timedelta(seconds=30)).isoformat().replace("+00:00", "Z"),
    )


def continuation_request(
    *,
    current_lease: runtime.WebSolRuntimeBindingLease | None = None,
    **overrides,
) -> dict:
    issued, expires = now_window()
    current = current_lease or lease()
    value = {
        "schema": protocol.ACTION_SCHEMA,
        "binding_id": "11111111-1111-4111-8111-111111111111",
        "conversation_fingerprint": current.target.conversation_fingerprint,
        "binding_fingerprint": "d" * 64,
        "action": "SUBMIT_CONTINUATION",
        "operation_key": OPERATION,
        "issued_at": issued,
        "expires_at": expires,
        "nonce": NONCE,
        "turn_id": TURN_ID,
        "directive_digest": protocol.CONTINUATION_DIRECTIVE_DIGEST,
        "session_alias": current.runtime_binding.session_alias,
        "runtime_binding_id": current.runtime_binding.binding_id,
        "runtime_binding_generation": current.runtime_binding.binding_generation,
        "runtime_binding_fingerprint": current.runtime_binding_fingerprint,
        "wake_obligation_ids": list(WAKE_IDS),
        "wake_obligation_digest": WAKE_DIGEST,
    }
    value.update(overrides)
    return value


def observation(generation_state: str = "idle") -> dict:
    return {
        "schema": protocol.PROBE_SCHEMA,
        "target_present": True,
        "exact_conversation_loaded": True,
        "page_responsive": True,
        "document_ready_state": "complete",
        "visibility": "visible",
        "composer_available": True,
        "generation_state": generation_state,
        "auth_required": False,
        "provider_error_present": False,
    }


def continuation_receipt(request: dict, status: str) -> dict:
    return {
        "schema": protocol.RECEIPT_SCHEMA,
        "binding_id": request["binding_id"],
        "conversation_fingerprint": request["conversation_fingerprint"],
        "binding_fingerprint": request["binding_fingerprint"],
        "action": request["action"],
        "operation_key": request["operation_key"],
        "nonce": request["nonce"],
        "status": status,
        "observed_at": "2026-09-18T20:00:01Z",
        "observation": observation(
            "active" if status == "CONTINUATION_STARTED" else "idle"
        ),
        "turn_id": request["turn_id"],
        "directive_digest": request["directive_digest"],
        "session_alias": request["session_alias"],
        "runtime_binding_id": request["runtime_binding_id"],
        "runtime_binding_generation": request["runtime_binding_generation"],
        "runtime_binding_fingerprint": request["runtime_binding_fingerprint"],
        "wake_obligation_ids": request["wake_obligation_ids"],
        "wake_obligation_digest": request["wake_obligation_digest"],
    }


def collected_census_receipt(binding: dict) -> dict:
    adapter = instance.adapter_instance_id(binding)
    snapshot = {
        "schema": census.LOCAL_SCHEMA,
        "scope": "CURRENT_PROFILE_NORMAL_CHATGPT_TABS",
        "adapter_instance_id": adapter,
        "started_at": "2026-09-18T20:00:00.000Z",
        "completed_at": "2026-09-18T20:00:01.000Z",
        "duration_ms": 1000,
        "inventory_coverage": "COMPLETE_IN_SCOPE",
        "consistency": "STABLE_AT_BOUNDARIES",
        "reason": "NONE",
        "initial_tab_count": 1,
        "final_tab_count": 1,
        "excluded_private_count": 0,
        "omitted_tab_count": 0,
        "unobserved_added_count": 0,
        "unique_conversation_count": 1,
        "duplicate_tab_count": 0,
        "probed_tab_count": 1,
        "generation_cue_count": 0,
        "unknown_cue_count": 0,
        "probe_coverage": "COMPLETE_IN_SCOPE",
        "rows": [
            {
                "slot": 1,
                "conversation_fingerprint": CONVERSATION_FINGERPRINT,
                "identity_evidence": "LOCATOR_AND_V1_PROBE",
                "document_binding": "UNVERIFIED",
                "status": "OBSERVED",
                "generation_cue": "NOT_OBSERVED",
                "selected_in_window": True,
                "discarded": False,
                "frozen": False,
                "visibility": "VISIBLE",
                "auth_required": False,
                "provider_error_present": False,
                "duplicate_count": 1,
                "duplicate_cue_disagreement": False,
                "observed_at": "2026-09-18T20:00:00.500Z",
                "selected_model": None,
                "selected_effort": None,
                "served_model": None,
                "model_evidence": "UNVERIFIED",
            }
        ],
    }
    return {
        "schema": census.RECEIPT_SCHEMA,
        "adapter_instance_id": adapter,
        "operation_key": OPERATION,
        "nonce": "runtime-binding-census-nonce-001",
        "status": "COLLECTED",
        "snapshot": census.encode_snapshot(snapshot),
    }


def test_runtime_bound_continuation_is_package_generation_four_and_closed() -> None:
    assert protocol.WEB_SOL_PACKAGE_VERSION == "0.5.0"
    accepted = protocol.validate_request(continuation_request())
    assert accepted["runtime_binding_generation"] == 1
    assert accepted["session_alias"] == "EXECUTIVE-CEO-A"
    assert protocol.validate_receipt(
        continuation_receipt(accepted, "CONTINUATION_STARTED")
    )["runtime_binding_id"] == accepted["runtime_binding_id"]

    for missing in (
        "session_alias",
        "runtime_binding_id",
        "runtime_binding_generation",
        "runtime_binding_fingerprint",
    ):
        malformed = continuation_request()
        del malformed[missing]
        with pytest.raises(protocol.WebSolProtocolError):
            protocol.validate_request(malformed)
    for field, value in (
        ("session_alias", "bad alias"),
        ("runtime_binding_id", "not-a-binding"),
        ("runtime_binding_generation", 0),
        ("runtime_binding_generation", True),
        ("runtime_binding_fingerprint", "f" * 63),
    ):
        with pytest.raises(protocol.WebSolProtocolError):
            protocol.validate_request(continuation_request(**{field: value}))


def test_acquire_runtime_binding_uses_one_census_and_current_handshake_boot(monkeypatch) -> None:
    row = navigation_binding()
    sent: list[dict] = []

    def exchange(request, *, path, expected_instance_id, on_handshake=None, before_action=None):
        assert before_action is None
        assert request["schema"] == census.REQUEST_SCHEMA
        assert expected_instance_id == instance.adapter_instance_id(row)
        if on_handshake is not None:
            on_handshake({"boot_nonce": BOOT_ONE})
        sent.append(request)
        receipt = collected_census_receipt(row)
        return {
            **receipt,
            "operation_key": request["operation_key"],
            "nonce": request["nonce"],
        }

    monkeypatch.setattr(client, "_exchange_web_sol_socket", exchange)
    now = datetime.now(timezone.utc).replace(microsecond=0)
    issued = now.isoformat().replace("+00:00", "Z")
    expires = (now + timedelta(seconds=10)).isoformat().replace("+00:00", "Z")
    acquired = client.acquire_runtime_binding_via_extension(
        row,
        logical_target(),
        operation_key=OPERATION,
        issued_at=issued,
        expires_at=expires,
        nonce="runtime-binding-census-nonce-001",
    )

    assert len(sent) == 1
    assert acquired.target.conversation_fingerprint == CONVERSATION_FINGERPRINT
    assert acquired.runtime_binding == runtime.project_runtime_binding(
        acquired.target,
        logical_target(),
        boot_nonce=BOOT_ONE,
    )
    assert acquired.runtime_binding_fingerprint == runtime.runtime_binding_fingerprint(
        acquired.runtime_binding,
        acquired.target,
    )


def test_stale_runtime_binding_refuses_before_continuation_action_frame(monkeypatch) -> None:
    row = navigation_binding()
    stale = lease(BOOT_ONE)
    sent: list[dict] = []

    def exchange(request, *, path, expected_instance_id, on_handshake=None, before_action=None):
        handshake = {"boot_nonce": BOOT_TWO}
        if on_handshake is not None:
            on_handshake(handshake)
        if before_action is not None:
            before_action(handshake)
        sent.append(request)
        raise AssertionError("stale request must not be written")

    monkeypatch.setattr(client, "_exchange_web_sol_socket", exchange)
    issued, expires = now_window()
    with pytest.raises(client.WebSolExtensionError) as excinfo:
        client.submit_continuation_via_extension(
            row,
            stale,
            operation_key=OPERATION,
            turn_id=TURN_ID,
            wake_obligation_ids=WAKE_IDS,
            issued_at=issued,
            expires_at=expires,
            nonce=NONCE,
        )
    assert excinfo.value.code == "runtime_binding_stale"
    assert sent == []


def test_current_runtime_binding_submits_exactly_once_and_correlates_receipt(monkeypatch) -> None:
    row = navigation_binding()
    current = lease(BOOT_ONE)
    sent: list[dict] = []

    def exchange(request, *, path, expected_instance_id, on_handshake=None, before_action=None):
        handshake = {"boot_nonce": BOOT_ONE}
        if on_handshake is not None:
            on_handshake(handshake)
        if before_action is not None:
            before_action(handshake)
        sent.append(request)
        return continuation_receipt(request, "CONTINUATION_STARTED")

    monkeypatch.setattr(client, "_exchange_web_sol_socket", exchange)
    issued, expires = now_window()
    result = client.submit_continuation_via_extension(
        row,
        current,
        operation_key=OPERATION,
        turn_id=TURN_ID,
        wake_obligation_ids=WAKE_IDS,
        issued_at=issued,
        expires_at=expires,
        nonce=NONCE,
    )
    assert result["status"] == "CONTINUATION_STARTED"
    assert len(sent) == 1
    assert sent[0]["runtime_binding_id"] == current.runtime_binding.binding_id
    assert sent[0]["runtime_binding_generation"] == 1
    assert sent[0]["runtime_binding_fingerprint"] == current.runtime_binding_fingerprint


def test_native_host_rederives_runtime_binding_before_chrome_forward() -> None:
    current = lease(BOOT_ONE)
    good = continuation_request(current_lease=current)
    writes: list[dict] = []
    native._SUBMIT_CONTINUATION_NONCES.clear()
    native._SUBMIT_CONTINUATION_TURNS.clear()

    result = native.forward_request(
        good,
        write_chrome=writes.append,
        read_chrome=lambda _remaining: continuation_receipt(
            good, "CONTINUATION_STARTED"
        ),
        timeout_seconds=1.0,
        expected_instance_id=current.target.adapter_instance_id,
        boot_nonce=BOOT_ONE,
    )
    assert result["status"] == "CONTINUATION_STARTED"
    assert writes == [good]

    native._SUBMIT_CONTINUATION_NONCES.clear()
    native._SUBMIT_CONTINUATION_TURNS.clear()
    stale = continuation_request(
        current_lease=current,
        runtime_binding_id=runtime.project_runtime_binding(
            current.target,
            logical_target(),
            boot_nonce=BOOT_TWO,
        ).binding_id,
    )
    writes.clear()
    with pytest.raises(native.NativeHostError) as excinfo:
        native.forward_request(
            stale,
            write_chrome=writes.append,
            read_chrome=lambda _remaining: None,
            timeout_seconds=1.0,
            expected_instance_id=current.target.adapter_instance_id,
            boot_nonce=BOOT_ONE,
        )
    assert excinfo.value.code == "runtime_binding_stale"
    assert writes == []


def test_continuation_api_has_no_caller_text_url_selector_or_retry() -> None:
    signature = inspect.signature(client.submit_continuation_via_extension)
    assert list(signature.parameters) == [
        "binding",
        "runtime_binding_lease",
        "operation_key",
        "turn_id",
        "wake_obligation_ids",
        "issued_at",
        "expires_at",
        "nonce",
    ]
    for forbidden in (
        "prompt",
        "message",
        "text",
        "instruction",
        "selector",
        "url",
        "retry",
        "account",
    ):
        assert forbidden not in signature.parameters

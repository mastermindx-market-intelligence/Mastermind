"""Web-Sol exact-session Wake acknowledgement contract.

The model-authored surface remains only sorted opaque WAKE-* ids.  All session,
binding, nudge and conversation evidence below represents trusted host projection
and must never be accepted from tool arguments or persisted as a second identity
store.

Web-Sol's accepted ``WebSolRuntimeBindingLease`` is runtime-only and detached, so
the ingress cannot re-derive the exact target the way the worker seam projects a
durable RuntimeBinding.  The current lease is therefore carried into the ingress
as the live proof, and every trusted identity fact is discriminated against it
before any acknowledgement is persisted.
"""
from __future__ import annotations

import dataclasses
from dataclasses import fields

import pytest

from control_plane import wake_ack_ingress as ack_ingress
from control_plane.executive_runtime import Runtime
from control_plane.session_targets import (
    SCHEMA as TARGET_SCHEMA,
    SessionTarget,
    SessionTargetRegistry,
    route_obligation,
)
from control_plane.wake_dispatcher import mint_nudge_id
from control_plane.wake_events import mint_obligation, mint_obligation_id
from control_plane.wake_ledger import (
    LedgerPhase,
    ack_event_payload,
    attempt_record,
    make_delivery_attempt,
    requested_record,
)
from control_plane.wake_persist import WakeLedgerRepository
from integrations.chairman_surfaces import web_sol_runtime_binding as wrb


_OID_A = mint_obligation_id(
    source_kind="executive_inbox_attention",
    source_ref="eia-000000000081",
    wake_kind="job_failed",
)
_OID_B = mint_obligation_id(
    source_kind="executive_inbox_attention",
    source_ref="eia-000000000082",
    wake_kind="job_failed",
)

_ADAPTER_INSTANCE_ID = "a" * 64
_CENSUS_DIGEST = "9" * 64
_CONVERSATION_FINGERPRINT = "d" * 64
_BOOT_NONCE = "boot-nonce-0000000001"
_ROTATED_BOOT_NONCE = "boot-nonce-0000000002"


def _symbols():
    projection = getattr(ack_ingress, "TrustedWebSolWakeAckProjection", None)
    acknowledge = getattr(ack_ingress, "acknowledge_consumed_web_sol_wakes", None)
    assert projection is not None, "Web-Sol trusted ACK projection is missing"
    assert callable(acknowledge), "Web-Sol Wake ACK ingress is missing"
    return projection, acknowledge


def test_web_sol_ack_projection_is_closed_and_model_claim_stays_ids_only() -> None:
    projection, _acknowledge = _symbols()
    assert [field.name for field in fields(ack_ingress.WakeAckClaim)] == [
        "obligation_ids"
    ]
    assert [field.name for field in fields(projection)] == [
        "session_alias",
        "reasoning_surface",
        "binding_id",
        "binding_generation",
        "native_handle",
        "runtime_binding_fingerprint",
        "conversation_fingerprint",
        "nudge_id",
        "obligation_ids",
        "terminal_ack_trailer",
    ]


def _logical_target(session_alias: str = "EXECUTIVE-CEO-A") -> SessionTarget:
    return SessionTarget(
        session_alias=session_alias,
        target_seat="ceo",
        reasoning_surface="chatgpt-sol",
        wake_transport="chatgpt-gui",
        allowed_transports=("chatgpt-gui",),
        workstream=None,
        target_enabled=True,
    )


def _lease(
    *,
    session_alias: str = "EXECUTIVE-CEO-A",
    boot_nonce: str = _BOOT_NONCE,
    conversation_fingerprint: str = _CONVERSATION_FINGERPRINT,
) -> wrb.WebSolRuntimeBindingLease:
    """Return one self-proving current Web-Sol lease; no persistence involved."""

    target = wrb.ExactWebSolTarget(
        adapter_instance_id=_ADAPTER_INSTANCE_ID,
        seat_ref="ceo",
        env_manager="gologin",
        folder_id=None,
        profile_id="0" * 24,
        conversation_fingerprint=conversation_fingerprint,
        census_digest=_CENSUS_DIGEST,
    )
    binding = wrb.project_runtime_binding(
        target,
        _logical_target(session_alias),
        boot_nonce=boot_nonce,
    )
    return wrb.WebSolRuntimeBindingLease(
        target=target,
        runtime_binding=binding,
        runtime_binding_fingerprint=wrb.runtime_binding_fingerprint(binding, target),
    )


@dataclasses.dataclass(frozen=True)
class _Fixture:
    runtime: Runtime
    repository: WakeLedgerRepository
    lease: wrb.WebSolRuntimeBindingLease
    obligations: tuple[object, ...]
    nudge_id: str
    trusted: object

    @property
    def binding(self):
        return self.lease.runtime_binding


def _fixture(
    tmp_path,
    *,
    obligation_count: int = 1,
    delivered_indices: set[int] | None = None,
    delivery_overrides: dict[str, object] | None = None,
) -> _Fixture:
    projection, _acknowledge = _symbols()
    runtime = Runtime.at(tmp_path)
    target = _logical_target()
    registry = SessionTargetRegistry(
        schema=TARGET_SCHEMA,
        lifecycle_authority="executive_os",
        production_armed=True,
        policy_version="web-sol-wake-ack-test",
        default_alias_by_seat={"ceo": target.session_alias},
        workstream_alias_by_seat={},
        root_job_bindings={},
        targets={target.session_alias: target},
    )
    lease = _lease()
    binding = lease.runtime_binding
    ids = (_OID_A, _OID_B)[:obligation_count]
    obligations = tuple(
        mint_obligation(
            wake_kind="job_failed",
            source_kind="executive_inbox_attention",
            source_ref=f"eia-{ordinal + 129:012x}",
            declared_target_seat="ceo",
        )
        for ordinal in range(obligation_count)
    )
    assert tuple(item.obligation_id for item in obligations) == ids
    routes = tuple(
        route_obligation(obligation, registry, binding=binding)
        for obligation in obligations
    )
    base_attempts = tuple(
        make_delivery_attempt(obligation, route, attempt_n=1)
        for obligation, route in zip(obligations, routes, strict=True)
    )
    command_ids = tuple(sorted(item.attempt_command_id for item in base_attempts))
    nudge_id = mint_nudge_id(routes[0].destination_digest, command_ids)
    attempts = tuple(
        dataclasses.replace(
            attempt,
            nudge_id=nudge_id,
            nudge_attempt_command_ids=command_ids,
            **(delivery_overrides or {}),
        )
        for attempt in base_attempts
    )
    delivered = (
        set(range(obligation_count))
        if delivered_indices is None
        else set(delivered_indices)
    )
    rows = []
    for ordinal, (obligation, attempt) in enumerate(
        zip(obligations, attempts, strict=True)
    ):
        rows.extend(
            (
                (requested_record(obligation), obligation),
                (attempt_record(attempt, LedgerPhase.DELIVERY_ATTEMPT), obligation),
                (
                    attempt_record(
                        attempt,
                        LedgerPhase.DELIVERED
                        if ordinal in delivered
                        else LedgerPhase.ACCEPTED,
                    ),
                    obligation,
                ),
            )
        )
    repository = WakeLedgerRepository(runtime)
    repository.append_records_atomic(tuple(rows))
    trusted = projection(
        session_alias=binding.session_alias,
        reasoning_surface="chatgpt-sol",
        binding_id=binding.binding_id,
        binding_generation=binding.binding_generation,
        native_handle=str(binding.native_handle),
        runtime_binding_fingerprint=lease.runtime_binding_fingerprint,
        conversation_fingerprint=lease.target.conversation_fingerprint,
        nudge_id=nudge_id,
        obligation_ids=tuple(sorted(ids)),
        terminal_ack_trailer=True,
    )
    return _Fixture(
        runtime=runtime,
        repository=repository,
        lease=lease,
        obligations=obligations,
        nudge_id=nudge_id,
        trusted=trusted,
    )


def _ack_rows(fixture: _Fixture, obligation_id: str):
    return tuple(
        item
        for item in fixture.repository.list_records(obligation_id)
        if item.record.phase is LedgerPhase.TARGET_ACKNOWLEDGED
    )


def test_exact_web_sol_delivery_persists_one_ack_and_identical_replay_is_idempotent(
    tmp_path,
) -> None:
    _projection, acknowledge = _symbols()
    fixture = _fixture(tmp_path)
    claim = ack_ingress.WakeAckClaim(fixture.trusted.obligation_ids)
    first = acknowledge(
        fixture.runtime, claim=claim, trusted=fixture.trusted, lease=fixture.lease
    )
    second = acknowledge(
        fixture.runtime, claim=claim, trusted=fixture.trusted, lease=fixture.lease
    )

    assert len(first) == len(second) == 1
    assert first[0].inserted is True
    assert second[0].inserted is False
    oid = fixture.trusted.obligation_ids[0]
    rows = _ack_rows(fixture, oid)
    assert len(rows) == 1
    payload = ack_event_payload(rows[0].record.ack)
    assert payload["target_seat"] == "ceo"
    assert payload["session_alias"] == fixture.binding.session_alias
    assert payload["reasoning_surface"] == "chatgpt-sol"
    assert payload["binding_id"] == fixture.binding.binding_id
    assert payload["binding_generation"] == fixture.binding.binding_generation
    for forbidden in (
        "native_handle",
        "conversation_fingerprint",
        "runtime_binding_fingerprint",
        "nudge_id",
    ):
        assert forbidden not in payload


def test_exact_replay_stays_idempotent_without_a_still_current_lease(tmp_path) -> None:
    """A durable identical ACK replays without re-proving the old live lease."""

    _projection, acknowledge = _symbols()
    fixture = _fixture(tmp_path)
    claim = ack_ingress.WakeAckClaim(fixture.trusted.obligation_ids)
    first = acknowledge(
        fixture.runtime, claim=claim, trusted=fixture.trusted, lease=fixture.lease
    )
    assert first[0].inserted is True

    replay = acknowledge(fixture.runtime, claim=claim, trusted=fixture.trusted)
    assert len(replay) == 1
    assert replay[0].inserted is False
    assert len(_ack_rows(fixture, fixture.trusted.obligation_ids[0])) == 1


def test_first_persistence_requires_the_live_web_sol_proof(tmp_path) -> None:
    _projection, acknowledge = _symbols()
    fixture = _fixture(tmp_path)
    claim = ack_ingress.WakeAckClaim(fixture.trusted.obligation_ids)
    with pytest.raises(ack_ingress.WakeAckIngressError, match="lease"):
        acknowledge(fixture.runtime, claim=claim, trusted=fixture.trusted)
    assert _ack_rows(fixture, fixture.obligations[0].obligation_id) == ()


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("native_handle", "wsx-runtime-" + "f" * 16),
        ("runtime_binding_fingerprint", "e" * 64),
        ("conversation_fingerprint", "f" * 64),
    ],
)
def test_valid_format_but_wrong_exact_session_evidence_refuses(
    tmp_path,
    field_name,
    value,
) -> None:
    """Syntactically valid identity facts must still match the current lease."""

    _projection, acknowledge = _symbols()
    fixture = _fixture(tmp_path)
    trusted = dataclasses.replace(fixture.trusted, **{field_name: value})
    assert getattr(fixture.trusted, field_name) != value
    claim = ack_ingress.WakeAckClaim(trusted.obligation_ids)
    with pytest.raises(ack_ingress.WakeAckIngressError):
        acknowledge(
            fixture.runtime, claim=claim, trusted=trusted, lease=fixture.lease
        )
    assert _ack_rows(fixture, fixture.obligations[0].obligation_id) == ()


def test_rotated_native_boot_refuses_the_pre_rotation_ack(tmp_path) -> None:
    """A restarted native host cannot retroactively ACK the prior life."""

    _projection, acknowledge = _symbols()
    fixture = _fixture(tmp_path)
    rotated = _lease(boot_nonce=_ROTATED_BOOT_NONCE)
    assert rotated.runtime_binding.binding_id != fixture.binding.binding_id
    assert rotated.runtime_binding.native_handle != fixture.binding.native_handle
    claim = ack_ingress.WakeAckClaim(fixture.trusted.obligation_ids)
    with pytest.raises(ack_ingress.WakeAckIngressError):
        acknowledge(
            fixture.runtime, claim=claim, trusted=fixture.trusted, lease=rotated
        )
    assert _ack_rows(fixture, fixture.obligations[0].obligation_id) == ()


def test_wrong_conversation_lease_refuses_even_with_matching_binding(tmp_path) -> None:
    """Another exact conversation in the same seat is still the wrong target."""

    _projection, acknowledge = _symbols()
    fixture = _fixture(tmp_path)
    other = _lease(conversation_fingerprint="b" * 64)
    claim = ack_ingress.WakeAckClaim(fixture.trusted.obligation_ids)
    with pytest.raises(ack_ingress.WakeAckIngressError):
        acknowledge(fixture.runtime, claim=claim, trusted=fixture.trusted, lease=other)
    assert _ack_rows(fixture, fixture.obligations[0].obligation_id) == ()


def test_non_web_sol_proof_object_refuses(tmp_path) -> None:
    """Only the accepted Web-Sol lease shape is admissible as live proof."""

    _projection, acknowledge = _symbols()
    fixture = _fixture(tmp_path)
    claim = ack_ingress.WakeAckClaim(fixture.trusted.obligation_ids)
    impostor = dataclasses.replace(fixture.trusted)
    with pytest.raises(ack_ingress.WakeAckIngressError, match="lease"):
        acknowledge(
            fixture.runtime, claim=claim, trusted=fixture.trusted, lease=impostor
        )
    assert _ack_rows(fixture, fixture.obligations[0].obligation_id) == ()


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("session_alias", "EXECUTIVE-CEO-B"),
        ("binding_id", "bind-wsx-" + "f" * 48),
        ("binding_generation", 2),
        ("nudge_id", "NUDGE-" + "f" * 32),
    ],
)
def test_stale_wrong_session_binding_generation_or_nudge_refuses_without_ack(
    tmp_path,
    field_name,
    value,
) -> None:
    _projection, acknowledge = _symbols()
    fixture = _fixture(tmp_path)
    trusted = dataclasses.replace(fixture.trusted, **{field_name: value})
    claim = ack_ingress.WakeAckClaim(trusted.obligation_ids)
    with pytest.raises(ack_ingress.WakeAckIngressError):
        acknowledge(
            fixture.runtime, claim=claim, trusted=trusted, lease=fixture.lease
        )
    assert _ack_rows(fixture, fixture.obligations[0].obligation_id) == ()


def test_wrong_delivery_surface_or_transport_refuses(tmp_path) -> None:
    _projection, acknowledge = _symbols()
    fixture = _fixture(
        tmp_path,
        delivery_overrides={"wake_transport": "codex-app-server"},
    )
    claim = ack_ingress.WakeAckClaim(fixture.trusted.obligation_ids)
    with pytest.raises(ack_ingress.WakeAckIngressError, match="chatgpt-gui"):
        acknowledge(
            fixture.runtime, claim=claim, trusted=fixture.trusted, lease=fixture.lease
        )


def test_claim_must_cover_the_complete_delivered_nudge_group(tmp_path) -> None:
    _projection, acknowledge = _symbols()
    fixture = _fixture(tmp_path, obligation_count=2)
    partial_ids = (fixture.obligations[0].obligation_id,)
    partial = dataclasses.replace(fixture.trusted, obligation_ids=partial_ids)
    with pytest.raises(ack_ingress.WakeAckIngressError, match="complete nudge group"):
        acknowledge(
            fixture.runtime,
            claim=ack_ingress.WakeAckClaim(partial_ids),
            trusted=partial,
            lease=fixture.lease,
        )
    assert all(_ack_rows(fixture, item.obligation_id) == () for item in fixture.obligations)

    complete = acknowledge(
        fixture.runtime,
        claim=ack_ingress.WakeAckClaim(fixture.trusted.obligation_ids),
        trusted=fixture.trusted,
        lease=fixture.lease,
    )
    assert len(complete) == 2
    assert all(item.inserted is True for item in complete)


def test_missing_member_delivery_refuses_the_entire_coalesced_ack(tmp_path) -> None:
    _projection, acknowledge = _symbols()
    fixture = _fixture(tmp_path, obligation_count=2, delivered_indices={0})
    with pytest.raises(ack_ingress.WakeAckIngressError, match="DELIVERED"):
        acknowledge(
            fixture.runtime,
            claim=ack_ingress.WakeAckClaim(fixture.trusted.obligation_ids),
            trusted=fixture.trusted,
            lease=fixture.lease,
        )
    assert all(_ack_rows(fixture, item.obligation_id) == () for item in fixture.obligations)


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("reasoning_surface", "codex"),
        ("native_handle", "browser-tab-from-model"),
        ("runtime_binding_fingerprint", "not-a-digest"),
        ("conversation_fingerprint", "not-a-digest"),
        ("terminal_ack_trailer", False),
    ],
)
def test_trusted_web_sol_projection_refuses_unsealed_or_non_web_evidence(
    field_name,
    value,
) -> None:
    projection, _acknowledge = _symbols()
    values = {
        "session_alias": "EXECUTIVE-CEO-A",
        "reasoning_surface": "chatgpt-sol",
        "binding_id": "bind-wsx-" + "a" * 48,
        "binding_generation": 1,
        "native_handle": "wsx-runtime-" + "b" * 16,
        "runtime_binding_fingerprint": "c" * 64,
        "conversation_fingerprint": "d" * 64,
        "nudge_id": "NUDGE-" + "e" * 32,
        "obligation_ids": (_OID_A,),
        "terminal_ack_trailer": True,
    }
    values[field_name] = value
    with pytest.raises(ack_ingress.WakeAckIngressError):
        projection(**values)

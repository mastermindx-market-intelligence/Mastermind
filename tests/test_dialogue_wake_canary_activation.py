from __future__ import annotations

import builtins
import dataclasses
import math
import socket
from typing import Any

import pytest

import control_plane.dialogue_wake_canary_activation as activation_contract
from control_plane.dialogue_wake_canary_activation import (
    ActivationRefusalCode,
    DialogueWakeCanaryActivationError,
    DialogueWakeCanaryActivationGrant,
    DialogueWakeCanaryCurrentFacts,
    DialogueWakeCanaryProfile,
    effective_dialogue_wake_canary_route,
    GRANT_FIELDS,
    IDENTITY_FIELDS,
    MAX_CONTAINER_DEPTH,
    MAX_BINDING_GENERATION,
    MAX_IDENTITY_TEXT_BYTES,
    MAX_NODE_COUNT,
    MAX_VALIDITY_SECONDS,
    SCHEMA,
    match_dialogue_wake_canary_activation,
    parse_dialogue_wake_canary_activation,
)
from control_plane.session_targets import WakeRoute


NOW = 1_788_585_651


def valid_wire(**overrides: Any) -> dict[str, Any]:
    value: dict[str, Any] = {
        "schema": SCHEMA,
        "installed_release_sha": "a" * 40,
        "operation_key": "runtime-continuity-r2-wake-ack-source-20260905-001",
        "source_root_job_id": "JOB-100",
        "source_job_id": "JOB-101",
        "source_attempt_id": "ATT-" + "1" * 32,
        "source_worker_id": "WORKER-SOL-1",
        "source_semantic_digest": "2" * 64,
        "obligation_id": "WAKE-" + "3" * 32,
        "target_seat": "ceo",
        "target_session_alias": "SOL-EXEC",
        "target_attempt_id": "ATT-" + "4" * 32,
        "binding_id": "bind-sol-exec-0001",
        "binding_generation": 7,
        "process_generation_id": "generation:sol:0007",
        "policy_digest": "5" * 16,
        "valid_from_epoch_seconds": NOW - 60,
        "expires_at_epoch_seconds": NOW + 60,
    }
    value.update(overrides)
    return value


def parsed(**overrides: Any) -> DialogueWakeCanaryActivationGrant:
    result = parse_dialogue_wake_canary_activation(valid_wire(**overrides))
    assert result is not None
    return result


def facts(**overrides: Any) -> DialogueWakeCanaryCurrentFacts:
    value = {field: valid_wire()[field] for field in IDENTITY_FIELDS}
    value.update(overrides)
    return DialogueWakeCanaryCurrentFacts(**value)


def _base_route(grant: DialogueWakeCanaryActivationGrant) -> WakeRoute:
    from control_plane.session_targets import destination_digest, route_digest, SessionTarget

    target = SessionTarget(
        session_alias=grant.target_session_alias,
        target_seat=grant.target_seat,
        reasoning_surface="codex",
        wake_transport="codex-app-server",
        allowed_transports=("codex-app-server",),
        workstream=None,
        target_enabled=False,
    )
    destination = destination_digest(
        target=target,
        binding_id=grant.binding_id,
        binding_generation=grant.binding_generation,
    )
    return WakeRoute(
        obligation_id=grant.obligation_id,
        session_alias=grant.target_session_alias,
        target_seat=grant.target_seat,
        reasoning_surface="codex",
        wake_transport="codex-app-server",
        binding_id=grant.binding_id,
        binding_generation=grant.binding_generation,
        route_digest=route_digest(obligation_id=grant.obligation_id, destination=destination, policy_digest=grant.policy_digest),
        destination_digest=destination,
        policy_digest=grant.policy_digest,
        root_job_id=grant.source_root_job_id,
        workstream="WS:TEST",
        production_armed=False,
        target_enabled=False,
        transport_implemented=True,
        requires_runtime_binding=True,
        binding_ready=True,
        human_required=False,
        policy_version="test",
        interface_version="wake/v1",
    )


def test_closed_profile_derives_one_effective_route_and_null_never_arms() -> None:
    grant = parsed()
    base = _base_route(grant)
    effective = effective_dialogue_wake_canary_route(
        DialogueWakeCanaryProfile(grant), base
    )

    assert effective.production_armed is True
    assert effective.target_enabled is True
    assert effective.policy_digest != base.policy_digest
    assert effective.route_digest != base.route_digest
    with pytest.raises(DialogueWakeCanaryActivationError, match="unavailable"):
        effective_dialogue_wake_canary_route(DialogueWakeCanaryProfile(None), base)
    with pytest.raises(DialogueWakeCanaryActivationError, match="disarmed"):
        effective_dialogue_wake_canary_route(
            DialogueWakeCanaryProfile(grant),
            dataclasses.replace(base, production_armed=True),
        )


def test_nullable_absence_is_disarmed_and_no_match() -> None:
    assert parse_dialogue_wake_canary_activation(None) is None
    assert match_dialogue_wake_canary_activation(None, facts(), now_epoch_seconds=NOW) is None


@pytest.mark.parametrize("forged", ["grant", "current"])
def test_matching_refuses_subclasses_that_bypass_construction(forged: str) -> None:
    class ForgedGrant(DialogueWakeCanaryActivationGrant):
        def __post_init__(self) -> None:
            pass

    class ForgedCurrent(DialogueWakeCanaryCurrentFacts):
        def __post_init__(self) -> None:
            pass

    grant = (
        ForgedGrant(**valid_wire(schema="mastermind.dialogue_wake_canary_activation.v2"))
        if forged == "grant" else parsed()
    )
    current = (
        ForgedCurrent(**facts().to_dict()) if forged == "current" else facts()
    )
    with pytest.raises(DialogueWakeCanaryActivationError) as raised:
        match_dialogue_wake_canary_activation(grant, current, now_epoch_seconds=NOW)
    assert raised.value.code is ActivationRefusalCode.MALFORMED


def test_exact_closed_grant_matches_one_obligation_without_authority_flags() -> None:
    grant = parsed()
    result = match_dialogue_wake_canary_activation(grant, facts(), now_epoch_seconds=NOW)

    assert result is not None
    assert result.grant is grant
    assert result.grant_digest == grant.digest
    assert set(grant.to_dict()) == set(GRANT_FIELDS)
    assert dataclasses.is_dataclass(result)
    forbidden = {"authorized", "production_armed", "target_enabled", "wake_route"}
    assert not forbidden.intersection(grant.to_dict())
    assert MAX_CONTAINER_DEPTH == 1
    assert MAX_NODE_COUNT == 1 + len(GRANT_FIELDS)


@pytest.mark.parametrize("field", IDENTITY_FIELDS)
def test_each_current_identity_mismatch_refuses(field: str) -> None:
    alternate: dict[str, Any] = {
        "installed_release_sha": "b" * 40,
        "operation_key": "runtime-continuity-r2-wake-ack-source-20260905-002",
        "source_root_job_id": "JOB-200",
        "source_job_id": "JOB-201",
        "source_attempt_id": "ATT-" + "6" * 32,
        "source_worker_id": "WORKER-SOL-2",
        "source_semantic_digest": "7" * 64,
        "obligation_id": "WAKE-" + "8" * 32,
        "target_seat": "coo",
        "target_session_alias": "COO-FABLE",
        "target_attempt_id": "ATT-" + "9" * 32,
        "binding_id": "bind-coo-fable-0002",
        "binding_generation": 8,
        "process_generation_id": "generation:coo:0008",
        "policy_digest": "a" * 16,
    }
    with pytest.raises(DialogueWakeCanaryActivationError) as raised:
        match_dialogue_wake_canary_activation(
            parsed(), facts(**{field: alternate[field]}), now_epoch_seconds=NOW
        )
    assert raised.value.code is ActivationRefusalCode.CURRENT_FACT_MISMATCH
    assert raised.value.field == field


def test_not_yet_valid_and_expired_are_distinct_typed_refusals() -> None:
    future = parsed(valid_from_epoch_seconds=NOW + 1, expires_at_epoch_seconds=NOW + 2)
    with pytest.raises(DialogueWakeCanaryActivationError) as not_yet:
        match_dialogue_wake_canary_activation(future, facts(), now_epoch_seconds=NOW)
    assert not_yet.value.code is ActivationRefusalCode.NOT_YET_VALID

    with pytest.raises(DialogueWakeCanaryActivationError) as expired:
        match_dialogue_wake_canary_activation(parsed(), facts(), now_epoch_seconds=NOW + 60)
    assert expired.value.code is ActivationRefusalCode.EXPIRED


def test_validity_window_has_a_finite_fifteen_minute_ceiling() -> None:
    parsed(
        valid_from_epoch_seconds=NOW,
        expires_at_epoch_seconds=NOW + MAX_VALIDITY_SECONDS,
    )
    with pytest.raises(DialogueWakeCanaryActivationError) as raised:
        parsed(
            valid_from_epoch_seconds=NOW,
            expires_at_epoch_seconds=NOW + MAX_VALIDITY_SECONDS + 1,
        )
    assert raised.value.code is ActivationRefusalCode.MALFORMED
    assert raised.value.field == "expires_at_epoch_seconds"

    boundary = parsed(
        valid_from_epoch_seconds=NOW,
        expires_at_epoch_seconds=NOW + MAX_VALIDITY_SECONDS,
    )
    assert match_dialogue_wake_canary_activation(
        boundary, facts(), now_epoch_seconds=NOW
    ) is not None
    assert match_dialogue_wake_canary_activation(
        boundary,
        facts(),
        now_epoch_seconds=NOW + MAX_VALIDITY_SECONDS - 1,
    ) is not None


@pytest.mark.parametrize(
    ("field", "bad"),
    [
        ("schema", "mastermind.dialogue_wake_canary_activation.v2"),
        ("installed_release_sha", "A" * 40),
        ("operation_key", " short "),
        ("source_root_job_id", "not-a-job"),
        ("source_job_id", "JOB-1"),
        ("source_attempt_id", "ATT-short"),
        ("source_worker_id", "worker with spaces"),
        ("source_semantic_digest", "b" * 63),
        ("obligation_id", "WAKE-" + "F" * 32),
        ("target_seat", "worker"),
        ("target_session_alias", "sol-exec"),
        ("target_attempt_id", "ATT-" + "g" * 32),
        ("binding_id", "binding-1"),
        ("binding_generation", True),
        ("process_generation_id", " generation "),
        ("policy_digest", "f" * 64),
        ("valid_from_epoch_seconds", math.nan),
        ("expires_at_epoch_seconds", math.inf),
    ],
)
def test_each_malformed_field_is_typed_refusal(field: str, bad: Any) -> None:
    with pytest.raises(DialogueWakeCanaryActivationError) as raised:
        parsed(**{field: bad})
    assert raised.value.code is ActivationRefusalCode.MALFORMED


def test_unknown_missing_and_widened_scope_fields_refuse() -> None:
    for extra in (
        {"second_obligation_id": "WAKE-" + "6" * 32},
        {"obligation_ids": ["WAKE-" + "6" * 32]},
        {"production_armed": True},
        {"authorized": True},
        {"api_token": "opaque"},
    ):
        with pytest.raises(DialogueWakeCanaryActivationError) as raised:
            parse_dialogue_wake_canary_activation({**valid_wire(), **extra})
        assert raised.value.code is ActivationRefusalCode.MALFORMED

    missing = valid_wire()
    missing.pop("obligation_id")
    with pytest.raises(DialogueWakeCanaryActivationError):
        parse_dialogue_wake_canary_activation(missing)


@pytest.mark.parametrize(
    "hostile",
    [
        [],
        {**valid_wire(), "obligation_id": [valid_wire()["obligation_id"]]},
        {**valid_wire(), "source_semantic_digest": {"nested": {"deeper": "x"}}},
        {**valid_wire(), "\ud800": "surrogate-key"},
        {**valid_wire(), "source_worker_id": "\ud800"},
    ],
)
def test_nonobject_depth_and_surrogate_inputs_refuse_without_recursion(hostile: Any) -> None:
    with pytest.raises(DialogueWakeCanaryActivationError) as raised:
        parse_dialogue_wake_canary_activation(hostile)
    assert raised.value.code is ActivationRefusalCode.MALFORMED


def test_digest_is_order_stable_and_every_material_field_changes_it() -> None:
    baseline = parsed()
    reversed_wire = dict(reversed(tuple(valid_wire().items())))
    reordered = parse_dialogue_wake_canary_activation(reversed_wire)
    assert reordered is not None
    assert reordered.digest == baseline.digest

    changes: dict[str, Any] = {
        "installed_release_sha": "b" * 40,
        "operation_key": "runtime-continuity-r2-wake-ack-source-20260905-002",
        "source_root_job_id": "JOB-200",
        "source_job_id": "JOB-201",
        "source_attempt_id": "ATT-" + "6" * 32,
        "source_worker_id": "WORKER-SOL-2",
        "source_semantic_digest": "d" * 64,
        "obligation_id": "WAKE-" + "e" * 32,
        "target_seat": "coo",
        "target_session_alias": "COO-FABLE",
        "target_attempt_id": "ATT-" + "7" * 32,
        "binding_id": "bind-coo-fable-0002",
        "binding_generation": 8,
        "process_generation_id": "generation:coo:0008",
        "valid_from_epoch_seconds": NOW - 61,
        "expires_at_epoch_seconds": NOW + 61,
        "policy_digest": "f" * 16,
    }
    assert set(changes) == set(GRANT_FIELDS) - {"schema"}
    for field, value in changes.items():
        assert parsed(**{field: value}).digest != baseline.digest


def test_contract_is_immutable_and_performs_no_io_runtime_or_provider_effect(monkeypatch) -> None:
    def forbidden(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("I/O was attempted")

    monkeypatch.setattr(builtins, "open", forbidden)
    monkeypatch.setattr(socket, "socket", forbidden)
    grant = parsed()
    result = match_dialogue_wake_canary_activation(grant, facts(), now_epoch_seconds=NOW)
    assert result is not None
    with pytest.raises(dataclasses.FrozenInstanceError):
        grant.binding_generation = 9  # type: ignore[misc]


def test_direct_constructor_and_replace_enforce_the_same_finite_identity_bounds() -> None:
    wire = valid_wire()
    oversized_job_id = "JOB-" + "9" * 9_000
    with pytest.raises(DialogueWakeCanaryActivationError) as direct:
        DialogueWakeCanaryActivationGrant(
            **{**wire, "source_job_id": oversized_job_id}
        )
    assert direct.value.code is ActivationRefusalCode.MALFORMED
    assert direct.value.field == "source_job_id"

    grant = parsed()
    with pytest.raises(DialogueWakeCanaryActivationError) as replaced:
        dataclasses.replace(
            grant, source_root_job_id=oversized_job_id
        )
    assert replaced.value.code is ActivationRefusalCode.MALFORMED
    assert replaced.value.field == "source_root_job_id"


def test_current_facts_enforce_finite_identity_and_generation_bounds() -> None:
    with pytest.raises(DialogueWakeCanaryActivationError) as oversized:
        facts(source_job_id="JOB-" + "9" * (MAX_IDENTITY_TEXT_BYTES + 1))
    assert oversized.value.field == "source_job_id"

    for generation in (MAX_BINDING_GENERATION + 1, 10**5000):
        with pytest.raises(DialogueWakeCanaryActivationError) as huge:
            facts(binding_generation=generation)
        assert huge.value.code is ActivationRefusalCode.MALFORMED
        assert huge.value.field == "binding_generation"

    with pytest.raises(DialogueWakeCanaryActivationError) as direct:
        DialogueWakeCanaryActivationGrant(
            **{**valid_wire(), "binding_generation": 10**5000}
        )
    assert direct.value.field == "binding_generation"

    with pytest.raises(DialogueWakeCanaryActivationError) as replaced:
        dataclasses.replace(parsed(), binding_generation=MAX_BINDING_GENERATION + 1)
    assert replaced.value.field == "binding_generation"


def test_schema_requires_an_exact_string_before_comparison() -> None:
    class SchemaPretender:
        def __eq__(self, _other: object) -> bool:
            return True

    with pytest.raises(DialogueWakeCanaryActivationError) as raised:
        DialogueWakeCanaryActivationGrant(**{**valid_wire(), "schema": SchemaPretender()})
    assert raised.value.code is ActivationRefusalCode.MALFORMED
    assert raised.value.field == "schema"

    with pytest.raises(DialogueWakeCanaryActivationError) as replaced:
        dataclasses.replace(parsed(), schema=SchemaPretender())  # type: ignore[arg-type]
    assert replaced.value.field == "schema"


def test_unknown_field_refusal_does_not_echo_hostile_key() -> None:
    hostile_key = "secret-" + "x" * 20_000
    with pytest.raises(DialogueWakeCanaryActivationError) as raised:
        parse_dialogue_wake_canary_activation({**valid_wire(), hostile_key: "token"})
    assert raised.value.code is ActivationRefusalCode.MALFORMED
    assert hostile_key not in str(raised.value)
    assert len(str(raised.value)) < 200


def test_canonical_serialization_failures_are_typed_and_opaque(monkeypatch) -> None:
    grant = parsed()

    def broken_serializer(_value: object) -> bytes:
        raise ValueError("secret serializer detail")

    monkeypatch.setattr(activation_contract, "canonical_json_bytes", broken_serializer)
    with pytest.raises(DialogueWakeCanaryActivationError) as raised:
        _ = grant.digest
    assert raised.value.code is ActivationRefusalCode.MALFORMED
    assert "secret serializer detail" not in str(raised.value)

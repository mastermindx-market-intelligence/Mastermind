"""Native Skill turn transport; source fixtures, never production admission.

The real remote proxy, broker dispatcher and Codex adapter reach the existing
fake App Server subprocess. Session materialization is an explicit fixture.
No live provider, credential, Browser or Executive Job is created.
"""
from __future__ import annotations

import asyncio
from dataclasses import replace
import json

import pytest

from control_plane.executive_worker_broker import (
    BrokerProtocolError, BrokerStateError, _BrokerOperatorRun,
)
from control_plane.operator_harness_contract import OperationId, TurnRef
from control_plane.operator_skill_selection import (
    MAX_OPERATOR_PROMPT_BYTES,
    OperatorSkillSelection,
    OperatorSkillSelectionError,
    OperatorSkillTurnInput,
    skill_selection_to_wire,
)
from control_plane.remote_operator_harness_adapter import RemoteOperatorHarnessAdapter
from tests.test_codex_operator_adapter import (
    _make_skill_harness, _stage_cap_s1_binding, _start,
)
from tests.test_executive_operator_broker import _fixture, _request


class _InProcessClient:
    """JSON-roundtrip delivery through the real authenticated broker dispatcher."""

    def __init__(self, broker, peer):
        self.broker = broker
        self.peer = peer
        self.payloads = []
        self.mutate = None

    def request_sync(self, operation, payload, **_options):
        payload = json.loads(json.dumps(payload))
        if self.mutate is not None:
            self.mutate(payload)
        self.payloads.append(payload)
        result = asyncio.run(self.broker.execute(
            _request(operation, payload, f"skill-{len(self.payloads)}"), peer=self.peer,
        ))
        return result["result"]


@pytest.fixture
def chain(tmp_path):
    binding = _stage_cap_s1_binding(tmp_path, owning_process_generation="gen-1")
    harness = _make_skill_harness(tmp_path, binding)
    harness.requested = replace(
        harness.requested, capabilities=binding.profile.capability_manifest(
            harness_binary_digest=harness.adapter.binary_digest,
        ),
    )
    _observation, _observed, launch = _start(harness)
    broker, peer, _profile, _sweeper, _adapters = _fixture(tmp_path / "broker")
    state = _BrokerOperatorRun(
        adapter=harness.adapter, requested=harness.requested,
        epoch=harness.epoch, generation=harness.generation,
        provider_session_id=_observation.provider_session_id,
    )
    broker._operator_run = state
    harness.adapter.turn_input_loader = lambda turn: state.prompts[turn.turn_id]
    client = _InProcessClient(broker, peer)
    grant = binding.profile.skill_grants[0]
    selection = OperatorSkillSelection(
        grant.capability_id, grant.skill_content_digest,
        binding.generation.package_generation_digest,
    )
    selected = OperatorSkillTurnInput("Execute this bounded source-fixture instruction.", selection)
    remote = RemoteOperatorHarnessAdapter(
        client, turn_input_loader=lambda turn: selected,
        capabilities=harness.adapter.describe_capabilities(),
    )
    turn = TurnRef(
        "turn-skill-transport", harness.epoch.session_epoch_id,
        harness.generation.process_generation_id, harness.epoch.attempt_id,
    )
    value = dict(
        binding=binding, harness=harness, broker=broker, state=state,
        client=client, remote=remote, selected=selected, turn=turn, launch=launch,
    )
    try:
        yield value
    finally:
        for generation_state in harness.adapter._generations.values():
            generation_state.client.close()


def _begin(chain):
    return chain["remote"].begin_turn(
        operation_id=OperationId("ohf-op:skill-transport"),
        turn=chain["turn"], generation=chain["harness"].generation,
        launch=chain["launch"],
    )


def _native_turns(chain):
    client = chain["harness"].adapter._state(chain["harness"].generation).client
    return [params for method, params in client.calls if method == "turn/start"]


def test_remote_broker_real_adapter_selects_worker_local_skill(chain):
    assert _native_turns(chain) == []
    assert _begin(chain).acknowledged
    grant = chain["binding"].profile.skill_grants[0]
    local_path = f'{chain["binding"].projection.skills_root}/{grant.runtime_name}/SKILL.md'
    assert _native_turns(chain)[-1]["input"] == [
        {"type": "text", "text": chain["selected"].text},
        {"type": "skill", "name": grant.runtime_name, "path": local_path},
    ]
    wire = chain["client"].payloads[-1]["skill_selection"]
    assert wire == skill_selection_to_wire(chain["selected"].selection)
    assert set(wire) == {
        "capability_id", "skill_content_digest", "package_generation_digest",
    }
    assert local_path not in json.dumps(wire)
    assert chain["state"].prompts == {}
    assert chain["state"].busy is False


def test_legacy_text_transport_is_unchanged(chain):
    chain["remote"].turn_input_loader = lambda turn: "Legacy text."
    assert _begin(chain).acknowledged
    assert "skill_selection" not in chain["client"].payloads[-1]
    assert _native_turns(chain)[-1]["input"] == [{"type": "text", "text": "Legacy text."}]


@pytest.mark.parametrize("field,value", [
    ("capability_id", "mastermind-operator.ungranted.v1"),
    ("skill_content_digest", "0" * 64),
    ("package_generation_digest", "0" * 64),
])
def test_selection_identity_drift_is_refused_before_native_turn(chain, field, value):
    selected = chain["selected"]
    changed = replace(selected.selection, **{field: value})
    chain["remote"].turn_input_loader = lambda turn: replace(selected, selection=changed)
    with pytest.raises(BrokerProtocolError):
        _begin(chain)
    assert _native_turns(chain) == []
    assert chain["state"].prompts == {}
    assert chain["state"].busy is False


@pytest.mark.parametrize("field", [
    "skill_md_path", "runtime_name", "projection", "verified", "profile", "resource",
])
def test_caller_cannot_supply_worker_path_or_verification(chain, field):
    chain["client"].mutate = lambda payload: payload["skill_selection"].update({
        field: "/private/untrusted/Skill.md",
    })
    with pytest.raises(BrokerProtocolError, match="fields"):
        _begin(chain)
    assert _native_turns(chain) == []


@pytest.mark.parametrize("bad_selection", [None, [], {}, "skill", [
    {"capability_id": "mastermind-operator.receive-commission.v1"},
]])
def test_selection_shape_is_closed_before_native_turn(chain, bad_selection):
    chain["client"].mutate = lambda payload: payload.update(skill_selection=bad_selection)
    with pytest.raises(BrokerProtocolError):
        _begin(chain)
    assert _native_turns(chain) == []


@pytest.mark.parametrize("target,field", [
    ("turn", "attempt_id"), ("turn", "session_epoch_id"),
    ("turn", "process_generation_id"), ("generation", "process_generation_id"),
])
def test_existing_generation_and_attempt_fences_precede_skill_selection(chain, target, field):
    chain["client"].mutate = lambda payload: payload[target].update({field: "foreign"})
    with pytest.raises((BrokerProtocolError, BrokerStateError)):
        _begin(chain)
    assert _native_turns(chain) == []
    assert chain["state"].busy is False


def test_launch_profile_drift_is_refused_before_selection(chain):
    chain["client"].mutate = lambda payload: payload["launch"]["requested"].update(
        authority_policy_hash="0" * 64,
    )
    with pytest.raises(BrokerProtocolError):
        _begin(chain)
    assert _native_turns(chain) == []


def test_missing_local_binding_is_not_repaired_from_caller_data(chain):
    chain["harness"].adapter.skill_canary_binding = None
    with pytest.raises(BrokerProtocolError, match="local package binding"):
        _begin(chain)
    assert _native_turns(chain) == []


def test_browser_resource_cannot_be_combined_with_native_skill(chain):
    chain["state"].resource = object()
    with pytest.raises(BrokerProtocolError, match="compatible local adapter"):
        _begin(chain)
    assert _native_turns(chain) == []


def test_revoked_autonomy_refuses_before_native_skill_effect(chain):
    def revoked():
        raise RuntimeError("fixture revocation")
    chain["broker"].autonomy_guard = revoked
    with pytest.raises(BrokerStateError, match="autonomy receipt refused"):
        _begin(chain)
    assert _native_turns(chain) == []


@pytest.mark.parametrize(
    "text", ["", " ", "\ud800", "x" * (MAX_OPERATOR_PROMPT_BYTES + 1)],
    ids=["empty", "whitespace", "invalid-unicode", "oversized"],
)
def test_typed_text_is_bounded_before_broker_dispatch(text):
    selection = OperatorSkillSelection("mastermind-operator.receive-commission.v1", "a" * 64, "b" * 64)
    with pytest.raises(OperatorSkillSelectionError):
        OperatorSkillTurnInput(text, selection)


@pytest.mark.parametrize(
    "text", ["", " ", "\ud800", "x" * (MAX_OPERATOR_PROMPT_BYTES + 1)],
    ids=["empty", "whitespace", "invalid-unicode", "oversized"],
)
def test_broker_revalidates_typed_text_from_wire(chain, text):
    chain["client"].mutate = lambda payload: payload.update(prompt=text)
    with pytest.raises(BrokerProtocolError, match="closed byte bound"):
        _begin(chain)
    assert _native_turns(chain) == []
    assert chain["state"].busy is False


def test_local_projection_must_belong_to_active_generation(chain):
    binding = chain["binding"]
    chain["harness"].adapter.skill_canary_binding = replace(
        binding, projection=replace(
            binding.projection, owning_process_generation="foreign-generation",
        ),
    )
    with pytest.raises(BrokerProtocolError, match="bound generation"):
        _begin(chain)
    assert _native_turns(chain) == []


def test_requested_manifest_cannot_omit_the_selected_skill_grant(chain):
    requested = chain["state"].requested
    narrowed = replace(requested, capabilities=replace(
        requested.capabilities, required=(),
    ))
    chain["state"].requested = narrowed
    chain["launch"] = replace(chain["launch"], requested=narrowed)
    with pytest.raises(BrokerProtocolError, match="bound generation"):
        _begin(chain)
    assert _native_turns(chain) == []


@pytest.mark.parametrize("field", [
    "allowed_ambient", "forbidden", "unclassified_policy",
])
def test_full_capability_manifest_must_match_local_binding(chain, field):
    requested = chain["state"].requested
    original = requested.capabilities
    changed_value = {
        "allowed_ambient": original.required[:1],
        "forbidden": ("fixture.unexpected-capability",),
        "unclassified_policy": "lab_allow_unclassified_readonly",
    }[field]
    changed = replace(original, **{field: changed_value})
    assert changed != original
    assert changed.required == original.required
    drifted = replace(requested, capabilities=changed)
    chain["state"].requested = drifted
    chain["launch"] = replace(chain["launch"], requested=drifted)
    with pytest.raises(BrokerProtocolError, match="bound generation"):
        _begin(chain)
    assert _native_turns(chain) == []
    assert chain["state"].prompts == {}
    assert chain["state"].busy is False

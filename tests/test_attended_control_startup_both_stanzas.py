"""Control startup with BOTH the finite probe stanza and the Wake retry policy.

S2 acceptance (release 08d7887335ee8aea11f0809e0660a5298c3ef68c) crashed Control
at startup once control.json carried ``fabric_attended_probe`` and
``dialogue_wake_retry_policy`` together: ``load_control_config`` turns the policy
into the frozen ``WakeRetryPolicy`` dataclass, ``_jsonable`` passed it through
unchanged and ``digest`` raised ``TypeError: Object of type WakeRetryPolicy is
not JSON serializable`` (phase1c.py:2916 -> fabric_attended_canary.py:145 -> :25).

Inert: no service, credentials, launchd or provider effects.
"""
import asyncio
import dataclasses
import hashlib
import json
from pathlib import Path

import pytest

from control_plane.fabric_attended_canary import AttendedControlProbeSource, digest
from control_plane.model_router import ModelRouter
from control_plane.wake_ledger import WakeRetryPolicy
from control_plane.executive_worker_broker import BrokerStateError
from scripts import executive_os_phase1c as cli
from tests.test_ceo_submit_armed_composition import _raw, _write
from tests.test_executive_fabric_composition import root_stats
from tests.test_executive_fabric_phase1c import staged
from tests.test_executive_launchd_config import _hf1b_bind, _hf1b_control_fixture
from tests.test_fabric_attended_factory_placement import selected
from tests.test_fabric_attended_routing import router

DIALOGUE_STANZA = {
    "dialogue_observation_socket_path": (
        "/var/run/mastermind-dialogue-observation/dialogue-observation.sock"
    ),
    "dialogue_observation_launchd_socket_name": "DialogueObservation",
    "dialogue_observation_peer_uid": 457,
    "dialogue_bridge_armed": False,
    "dialogue_wake_retry_policy": {
        "max_delivery_attempts": None,
        "retry_cooldown_s": None,
        "accepted_ttl_s": None,
        "target_unavailable_backoff_s": None,
        "reenable_on_binding_rotation": True,
        "armed": False,
    },
}

# digest() of the mapping below computed with the pre-change ``_jsonable``
# (to_dict / Mapping / list+tuple / Path only). A config without a dataclass
# value must keep this exact digest.
BASELINE_CONFIG = {
    "schema_version": "x/v1",
    "runtime_root": Path("/var/runtime"),
    "allowed_peer_uids": (450, 451),
    "nested": {"b": [1, Path("/p")], "a": None},
    "armed": False,
}
BASELINE_DIGEST = "2cdd61466f0bdf72c969055e866bab6d0ab79ad31e10bf64e38ce89a58a71edb"


def both_stanza_config(tmp_path: Path) -> Path:
    raw = _raw(tmp_path)
    raw.update(staged(tmp_path, raw))
    raw["fabric_attended_probe"] = {"worker_config_path": str(tmp_path / "worker.json")}
    raw.update(json.loads(json.dumps(DIALOGUE_STANZA)))
    return _write(tmp_path, raw)


def test_jsonable_expands_dataclass_to_plain_dict():
    policy = WakeRetryPolicy(armed=False)
    value = cli._jsonable(policy)
    assert type(value) is dict
    assert value == dataclasses.asdict(policy)
    assert digest(value) == digest(dataclasses.asdict(policy))
    nested = cli._jsonable({"a": {"policy": policy}, "b": [policy], "c": (policy,)})
    assert nested == {"a": {"policy": value}, "b": [value], "c": [value]}
    json.dumps(nested)  # plain JSON data all the way down


def test_jsonable_leaves_dataclass_types_and_to_dict_owners_alone():
    assert cli._jsonable(WakeRetryPolicy) is WakeRetryPolicy

    @dataclasses.dataclass
    class Owner:
        hidden: int = 1

        def to_dict(self):
            return {"exposed": 2}

    assert cli._jsonable(Owner()) == {"exposed": 2}


def test_config_without_dataclass_digests_to_pre_change_value():
    assert digest(cli._jsonable(BASELINE_CONFIG)) == BASELINE_DIGEST


def test_both_stanzas_digest_on_startup_and_reload(tmp_path, root_stats):
    path = both_stanza_config(tmp_path)
    loaded = cli.load_control_config(path)
    assert type(loaded["dialogue_wake_retry_policy"]) is WakeRetryPolicy
    assert loaded["fabric_attended_probe"] == {"worker_config_path": str(tmp_path / "worker.json")}
    source = AttendedControlProbeSource.from_startup(path, loaded, {"config_sha256": "a" * 64})
    again = cli.load_control_config(path)
    assert digest(cli._jsonable(again)) == digest(cli._jsonable(loaded)) == source.definition_sha256
    source.require_definition(again)


def test_policy_change_is_covered_by_the_definition_digest(tmp_path, root_stats):
    path = both_stanza_config(tmp_path)
    source = AttendedControlProbeSource.from_startup(
        path, cli.load_control_config(path), {"config_sha256": "a" * 64})
    changed = json.loads(path.read_text())
    changed["dialogue_wake_retry_policy"]["max_delivery_attempts"] = 3
    path.write_text(json.dumps(changed))
    with pytest.raises(BrokerStateError, match="finite attended probe definition"):
        source.require_definition(cli.load_control_config(path))


class _DefinitionCheckPassed(Exception):
    """Stops the run right after the real second definition check passed."""


def test_serve_from_config_real_loader_passes_service_definition_check(tmp_path, monkeypatch, root_stats, router):
    """Production order with the REAL ``load_control_config``: ``_serve_from_config``
    loads control.json (both stanzas), digests it in ``from_startup``, then
    ``_service_from_config`` calls ``require_definition(raw)``, which re-digests the
    raw loaded object it was passed (there is no second load).  Only host reads and
    external effects are patched; the run is stopped right after that check so no
    service is constructed."""
    from ops.executive_os import coo_principal_host, dialogue_wake_canary_control
    path = both_stanza_config(tmp_path)
    monkeypatch.setattr(cli, "_load_control_environment_attestation", lambda *a, **kw: {"config_sha256": "a" * 64})
    monkeypatch.setattr(cli, "_bind_exact_worker_target_source", lambda *a, **kw: None)
    monkeypatch.setattr(cli, "_bind_hot_content_profile_source", lambda *a, **kw: None)
    monkeypatch.setattr(cli, "_ceo_admission_guard", lambda *a, **kw: lambda: None)
    monkeypatch.setattr(coo_principal_host, "validate_control_coo", lambda raw: False)
    monkeypatch.setattr(dialogue_wake_canary_control, "load_verified_profile", lambda **kw: None)
    monkeypatch.setattr(ModelRouter, "load", classmethod(lambda cls, **kw: router))
    checked = []
    real_require_definition = AttendedControlProbeSource.require_definition

    def spy(self, raw):
        real_require_definition(self, raw)  # real re-digest of the raw object, real comparison
        checked.append(raw)
        raise _DefinitionCheckPassed

    monkeypatch.setattr(AttendedControlProbeSource, "require_definition", spy)
    with pytest.raises(_DefinitionCheckPassed) as stopped:
        asyncio.run(cli._serve_from_config(path, attended_work_placements=(selected(),)))
    assert [entry.name for entry in stopped.traceback if entry.name == "_service_from_config"]
    assert len(checked) == 1
    assert type(checked[0]["dialogue_wake_retry_policy"]) is WakeRetryPolicy
    assert checked[0]["fabric_attended_probe"] == {"worker_config_path": str(tmp_path / "worker.json")}


def test_fixed_exact_worker_target_with_wake_policy_loads_and_stays_current(tmp_path):
    """Before this fix ``load_control_config`` itself raised (``_canonical_sha256`` over a
    ``WakeRetryPolicy`` at the ``_LoadedTargetConfig`` digest) for a fixed
    ``exact_worker_claim_target`` plus the wake stanza; the whole Control load failed."""
    cli_, _, _, work, _, raw, path, _ = _hf1b_control_fixture(tmp_path)
    raw.update(json.loads(json.dumps(DIALOGUE_STANZA)))
    data = json.dumps(raw, sort_keys=True).encode()
    path.write_bytes(data)
    attestation = {"config_sha256": hashlib.sha256(data).hexdigest(),
                   "process_identity": {"pid": 4242}, "release_commit_sha": "a" * 40}
    loaded = cli_.load_control_config(path)
    assert type(loaded["dialogue_wake_retry_policy"]) is WakeRetryPolicy
    assert loaded["exact_worker_claim_target"]["mode"] == "fixed"
    source = _hf1b_bind(cli_, loaded, path, attestation)  # runs require_current() on construction
    source.require_current()
    assert loaded._normalized_sha256 == digest(cli._jsonable(loaded))
    loaded["dialogue_wake_retry_policy"] = dataclasses.replace(
        loaded["dialogue_wake_retry_policy"], reenable_on_binding_rotation=False)
    with pytest.raises(cli.ServiceError, match="modified"):  # still bound to the loaded bytes
        source.require_current()

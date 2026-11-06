"""Receiving Control guard uses enrolled owners, not a role supplied by a caller."""
import copy
import dataclasses

import pytest

from control_plane.coo_principal_envelope import PrincipalAdmissionContext
from tests.test_executive_coo_host import setup, mandate, MISSION_AUTHORITY_VERSION


def prepared(tmp_path, monkeypatch):
    host, config, _, _ = setup(tmp_path)
    row = config["missions"][0]
    row.update(authority_version=MISSION_AUTHORITY_VERSION,
               principal_actions=["bounded_intent", "governed_orchestration"])
    document = mandate.mission_doc()
    monkeypatch.setattr(host.workspace, "read_mission_for_work_ref",
                        lambda work_ref: copy.deepcopy(document))
    _, principal, authority = host.source.snapshot(row["work_ref"])
    args = dict(context=PrincipalAdmissionContext(row["work_ref"],
        principal.principal_binding_digest, authority.mission_authority_ref,
        authority.authority_generation_digest), root_job_id="JOB-100",
        capability_profile_digest=authority.capability_profile_digest)
    return host, config, document, args


def test_current_explicit_mission_authority_passes_without_mutating_owners(tmp_path, monkeypatch):
    host, config, document, args = prepared(tmp_path, monkeypatch)
    before = copy.deepcopy((config, document))
    assert host.guard_dialogue(**args) is None
    assert (config, document) == before


@pytest.mark.parametrize("field,value", [
    ("work_ref", "WS:FOREIGN"), ("principal_binding_digest", "0" * 64),
    ("authority_generation_digest", "1" * 64), ("mission_authority_ref", "authority:foreign"),
])
def test_foreign_principal_context_refuses(tmp_path, monkeypatch, field, value):
    host, _, _, args = prepared(tmp_path, monkeypatch)
    args["context"] = dataclasses.replace(args["context"], **{field: value})
    with pytest.raises(ValueError, match="installed COO authority unavailable"):
        host.guard_dialogue(**args)


@pytest.mark.parametrize("change", [
    {"root_job_id": "JOB-999"}, {"root_job_id": None},
    {"capability_profile_digest": "0" * 64}, {"context": {"seat": "ceo"}},
])
def test_claimed_root_profile_or_role_is_not_authority(tmp_path, monkeypatch, change):
    host, _, _, args = prepared(tmp_path, monkeypatch)
    with pytest.raises(ValueError):
        host.guard_dialogue(**{**args, **change})


@pytest.mark.parametrize("change", [
    {"read_state": "HISTORICAL"}, {"owner_state": "UNKNOWN"},
    {"accountable_seat": "ceo"}, {"owed_seat": "chairman"},
    {"source_generation_state": "STALE"}, {"root_ambiguous": True},
])
def test_currentness_and_reserved_turns_are_enforced(tmp_path, monkeypatch, change):
    host, _, _, args = prepared(tmp_path, monkeypatch)
    monkeypatch.setattr(host.workspace, "read_mission_for_work_ref",
                        lambda work_ref: mandate.mission_doc(**change))
    with pytest.raises(ValueError):
        host.guard_dialogue(**args)


def test_legacy_unknown_diagnostic_preserves_current_owner_qualification(tmp_path, monkeypatch):
    host, _, _, args = prepared(tmp_path, monkeypatch)
    monkeypatch.setattr(host.workspace, "read_mission_for_work_ref",
                        lambda work_ref: mandate.mission_doc(source_generation_state="UNKNOWN"))
    assert host.guard_dialogue(**args) is None


def test_disarming_or_removing_action_revokes_existing_caller(tmp_path, monkeypatch):
    host, config, _, args = prepared(tmp_path, monkeypatch)
    config["missions"][0]["enabled"] = False
    with pytest.raises(ValueError):
        host.guard_dialogue(**args)
    config["missions"][0]["enabled"] = True
    config["missions"][0]["principal_actions"] = ["bounded_intent"]
    with pytest.raises(ValueError):
        host.guard_dialogue(**args)


@pytest.mark.parametrize("mutate", ["source", "mission", "raise"])
def test_owner_movement_or_exception_during_read_refuses(tmp_path, monkeypatch, mutate):
    host, config, document, args = prepared(tmp_path, monkeypatch)
    calls = []
    def read(work_ref):
        calls.append(work_ref)
        if len(calls) == 2:
            if mutate == "source":
                config["missions"][0]["enabled"] = False
            elif mutate == "mission":
                return mandate.mission_doc(owed_seat="chairman")
            else:
                raise PermissionError("PRIVATE_CANARY /private/authority")
        return copy.deepcopy(document)
    monkeypatch.setattr(host.workspace, "read_mission_for_work_ref", read)
    with pytest.raises(ValueError) as error:
        host.guard_dialogue(**args)
    assert str(error.value) == "installed COO authority unavailable"
    assert error.value.__cause__ is None

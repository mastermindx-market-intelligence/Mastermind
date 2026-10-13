"""The Fleet read stays behind existing workspace permission and source owners."""
import asyncio
import copy
import inspect

import pytest

from common import executive_workspace_contract as contract
from control_plane.workspace_read_service import WorkspaceReadService
from control_plane.fleet_health import compose_fleet_health, unavailable_fleet

try:
    from common.fleet_health_contract import validate_fleet_document
except ImportError:
    validate_fleet_document = None

NOW = 1_791_890_400


def frame(window="24h"):
    return {"schema": contract.FRAME_SCHEMA, "operation": "fleet", "selection": {"window": window},
            "principal": {"policy_id": "test", "issuer_digest": "a" * 64,
                          "subject_digest": "b" * 64, "client_ref": "c" * 64,
                          "resource": contract.RESOURCE, "scopes": [contract.SCOPE]}}


def document():
    return compose_fleet_health({"m2": {"platform": "darwin", "ssh_alias": None}},
                               {}, "", window="24h", now=NOW)


def service(reader=None, authorize=lambda _: True):
    assert "fleet_read" in inspect.signature(WorkspaceReadService).parameters, "Fleet service binding absent"
    return WorkspaceReadService(cache=None, runtime=None, authorize=authorize,
                                armed=lambda: False, runtime_identity=lambda: None, fleet_read=reader)


def test_fleet_frame_accepts_only_fixed_window_without_host_or_path():
    try:
        actual = contract.validate_frame(frame())
    except ValueError:
        pytest.fail("The fixed Fleet frame is not wired")
    assert actual == frame()
    for selected in (None, {"window": "all"}, {"window": "1h", "path": "/private"}, {"host": "m2"}):
        request = frame()
        request["selection"] = selected
        with pytest.raises(ValueError):
            contract.validate_frame(request)


def test_fleet_service_does_not_require_or_construct_runtime_or_control_room():
    called = []
    def reader(*, window):
        called.append(window)
        return document()
    result = asyncio.run(service(reader).handle_frame(frame()))
    assert result == {"ok": True, "result": document()}
    assert called == ["24h"]


def test_no_trusted_fleet_source_is_explicit_unavailable_not_empty_success():
    result = asyncio.run(service().handle_frame(frame()))
    assert result["ok"] is True
    assert result["result"]["availability"] == "UNAVAILABLE"
    assert result["result"]["reason_codes"] == ["SOURCE_UNAVAILABLE"]


def test_permission_denial_prevents_fleet_source_read():
    def forbidden(**_):
        pytest.fail("unauthorized source read")
    assert asyncio.run(service(forbidden, lambda _: False).handle_frame(frame()))["status"] == 403


def test_revocation_during_fleet_read_discards_the_result():
    allowed = [True]
    def reader(**_):
        allowed[0] = False
        return document()
    result = asyncio.run(service(reader, lambda _: allowed[0]).handle_frame(frame()))
    assert result["status"] == 403
    assert "hosts" not in repr(result)


def test_wrong_window_and_extra_private_fields_are_refused_at_service_boundary():
    for mutate in (lambda d: d.update(window="7d"), lambda d: d.update(private_path="/secret")):
        d = document()
        mutate(d)
        result = asyncio.run(service(lambda **_: d).handle_frame(frame()))
        assert result["status"] == 503
        assert "/secret" not in repr(result)


def test_validator_detaches_data_and_rejects_nested_extra_nonfinite_or_unknown_shapes():
    assert callable(validate_fleet_document), "Fleet closed DTO validator absent"
    d = document()
    validated = validate_fleet_document(d, expected_window="24h")
    assert validated == d and validated is not d and validated["hosts"] is not d["hosts"]
    cases = []
    for update in ({"private": "not public"}, {"cpu_busy_pct": True}, {"cpu_temp_c": float("nan")},
                   {"memory_total_bytes": 10, "memory_available_bytes": 11}):
        bad = copy.deepcopy(d)
        bad["hosts"][0]["metrics"].update(update)
        cases.append(bad)
    bad = copy.deepcopy(d)
    bad["hosts"] *= 2
    cases.append(bad)
    for bad in cases:
        with pytest.raises(ValueError):
            validate_fleet_document(bad, expected_window="24h")
    unavailable = unavailable_fleet("24h", NOW)
    assert validate_fleet_document(unavailable, expected_window="24h") == unavailable

def test_control_service_fleet_source_binding_is_operator_selected_and_optional(tmp_path):
    from scripts.executive_os_phase1c import _workspace_fleet_reader_from_config
    assert _workspace_fleet_reader_from_config({}) is None
    assert _workspace_fleet_reader_from_config({"workspace_acquisition": "enrolled"}) is None
    root = tmp_path / "fabric"
    (root / "state" / "hosts").mkdir(parents=True)
    (root / "hosts.json").write_text('{"ubuntu2":{"platform":"linux","roles":["lanes"]}}')
    (root / "state" / "hosts" / "ubuntu2.json").write_text('{"host":"ubuntu2","ts":1791890400,"reachable":true,"ncpu":32}')
    reader = _workspace_fleet_reader_from_config(
        {"workspace_acquisition": "enrolled", "workspace_fleet_observer_root": root})
    assert callable(reader)
    d = reader(window="1h")
    assert d["schema"] == "mastermind.fleet_health.v1"
    assert len(d["hosts"]) == 1
    assert d["hosts"][0]["id"] == "ubuntu2"
    assert d["admission_authoritative"] is False


@pytest.mark.parametrize("path", ["relative/fabric", "/tmp/../secret", 123, None])
def test_control_service_rejects_untrusted_fleet_root(path):
    from scripts.executive_os_phase1c import _workspace_fleet_reader_from_config
    with pytest.raises(ValueError):
        _workspace_fleet_reader_from_config(
            {"workspace_acquisition": "enrolled", "workspace_fleet_observer_root": path})


def test_fleet_source_requires_explicit_workspace_enrollment():
    from scripts.executive_os_phase1c import _workspace_fleet_reader_from_config
    with pytest.raises(ValueError):
        _workspace_fleet_reader_from_config({"workspace_fleet_observer_root": "/srv/not-enrolled"})

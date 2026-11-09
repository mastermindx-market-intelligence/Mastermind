"""Original-run sidecar validation with inert local files only."""
import hashlib
import json

import pytest

from integrations.session_bridge.bound_launch_capture import fabric_launch_reservation as fence
from integrations.session_bridge.bound_launch_capture import fabric_launch_transport as wire


def fixture(tmp_path):
    args = dict(run_id="attempt-1", routing_root_id="native-chat", routing_parent_run_id="operator-1")
    context = dict(schema_version=fence.CORRELATION_SCHEMA, routing_root_id="native-chat",
                   routing_parent_run_id="operator-1", runtime_binding=dict(
                       root_id="runtime-job-root", job_id="job-2", attempt_id="attempt-1",
                       effective_grant_sha256="a" * 64, commission_sha256="b" * 64,
                       physical_binding_sha256="c" * 64, start_request_sha256="d" * 64))
    source, log = tmp_path / "input.json", tmp_path / "attempt-1.log"
    source.write_bytes(wire.canonical(context)); source.chmod(0o600)
    fence.reserve_correlation_log(log, context, **args)
    directory = tmp_path / "lanes/tmp/attempt-1.launch-bound"
    directory.mkdir(parents=True, mode=0o700)
    target = directory / "correlation.json"
    digest = wire.prepare_snapshot(source, log, target, **args)
    env = dict(FABRIC_LAUNCH_SNAPSHOT_SHA256=digest, POOL_ORCHESTRATOR_ID="native-chat",
               POOL_PARENT_RUN_ID="operator-1")
    return args, context, source, log, target, env


def test_wire_derives_original_paths_and_preserves_both_namespaces(tmp_path):
    args, context, _, _, target, env = fixture(tmp_path)
    result = wire.remote_launch_arguments(tmp_path, args["run_id"], env)
    assert result["launch_receipt_path"] == target.parent / "launch.json"
    assert result["launch_receipt_metadata"] == context["runtime_binding"]
    assert result["launch_receipt_metadata"]["root_id"] != env["POOL_ORCHESTRATOR_ID"]
    assert result["launch_receipt_context_sha256"] == hashlib.sha256(target.read_bytes()).hexdigest()


@pytest.mark.parametrize("field,value", [
    ("POOL_ORCHESTRATOR_ID", "runtime-job-root"), ("POOL_PARENT_RUN_ID", "other-parent"),
    ("FABRIC_LAUNCH_SNAPSHOT_SHA256", "f" * 64), ("FABRIC_LAUNCH_SNAPSHOT_SHA256", ""),
])
def test_wrong_lineage_or_changed_digest_refuses(tmp_path, field, value):
    args, _, _, _, _, env = fixture(tmp_path)
    env[field] = value
    with pytest.raises(fence.ReservationRefused):
        wire.remote_launch_arguments(tmp_path, args["run_id"], env)


def test_lost_sidecar_does_not_authorize_replay_or_erase_reservation(tmp_path):
    args, context, _, log, target, env = fixture(tmp_path)
    target.unlink()
    with pytest.raises(FileNotFoundError):
        wire.remote_launch_arguments(tmp_path, args["run_id"], env)
    with pytest.raises(FileExistsError):
        fence.reserve_correlation_log(log, context, **args)


def test_source_changed_after_reservation_is_not_forwarded(tmp_path):
    args, context, source, log, _, _ = fixture(tmp_path)
    context["runtime_binding"]["physical_binding_sha256"] = "f" * 64
    source.write_bytes(wire.canonical(context))
    with pytest.raises(fence.ReservationRefused, match="request_conflict"):
        wire.prepare_snapshot(source, log, tmp_path / "changed.json", **args)
    assert not (tmp_path / "changed.json").exists()


def test_unbound_calls_remain_unbound_without_creating_paths(tmp_path):
    before = set(tmp_path.iterdir())
    assert wire.remote_launch_arguments(tmp_path, "ordinary-run", {}) == {}
    assert set(tmp_path.iterdir()) == before


def test_upload_digest_is_checked_against_original_reservation(tmp_path):
    args, _, _, log, target, env = fixture(tmp_path)
    assert wire.reserved_snapshot_digest(target, log, **args) == env["FABRIC_LAUNCH_SNAPSHOT_SHA256"]
    value = json.loads(target.read_text())
    value["correlation"]["runtime_binding"]["effective_grant_sha256"] = "f" * 64
    value["reservation_sha256"] = hashlib.sha256(
        fence.CORRELATION_PREFIX + wire.canonical(value["correlation"])).hexdigest()
    target.write_bytes(wire.canonical(value))
    with pytest.raises(fence.ReservationRefused, match="request_conflict"):
        wire.reserved_snapshot_digest(target, log, **args)


def test_backend_conversion_keeps_every_runtime_binding_field(tmp_path):
    _, context, _, _, _, _ = fixture(tmp_path)
    expected = dict(context["runtime_binding"])
    expected["effective_grant_digest"] = expected.pop("effective_grant_sha256")
    mapped = fence.backend_start_context(context)
    assert {**mapped["binding"], **{k: v for k, v in mapped.items() if k != "binding"}} == expected
    from control_plane.executive_fabric_bridge_broker import _binding
    assert _binding(mapped["binding"]) == mapped["binding"]

"""Execute patched owner fragments with inert files; no transport or provider I/O."""
import ast
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from integrations.session_bridge.bound_launch_capture import fabric_launch_reservation as fence
from integrations.session_bridge.bound_launch_capture import fabric_launch_transport as wire

BUNDLE = Path(__file__).resolve().parents[1] / "integrations/session_bridge/bound_launch_capture"


def patched(tmp_path, name, manifest_name):
    source = BUNDLE / "fixtures" / (name.removesuffix(".sh").removesuffix(".py") + ".base" + Path(name).suffix)
    manifest = json.loads((BUNDLE / manifest_name).read_text())
    raw = source.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == manifest["source_sha256"]
    (tmp_path / name).write_bytes(raw)
    result = subprocess.run(["patch", "--batch", "-p1", "-i", str(BUNDLE / (name + ".patch"))],
                            cwd=tmp_path, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stdout + result.stderr
    result = (tmp_path / name).read_bytes()
    assert hashlib.sha256(result).hexdigest() == manifest["candidate_sha256"]
    return result.decode()


def envelope():
    return dict(schema_version=fence.CORRELATION_SCHEMA, routing_root_id="native-root",
                routing_parent_run_id="native-parent", runtime_binding=dict(
                    root_id="runtime-root", job_id="runtime-job", attempt_id="attempt-1",
                    effective_grant_sha256="a" * 64, commission_sha256="b" * 64,
                    physical_binding_sha256="c" * 64, start_request_sha256="d" * 64))


def reserve_fragment(tmp_path, overrides=None):
    source = patched(tmp_path, "remote_sub.sh", "RESERVATION_SOURCE.json")
    fragment = source.split("<<'PY_RESERVE'\n", 1)[1].split("\nPY_RESERVE", 1)[0]
    packet = tmp_path / "context.json"
    packet.write_text(json.dumps(envelope())); packet.chmod(0o600)
    environment = {**os.environ, "REMOTE_SUB_START_CORRELATION_FILE": str(packet),
                   "POOL_ORCHESTRATOR_ID": "native-root", "POOL_PARENT_RUN_ID": "native-parent"}
    environment.pop("REMOTE_SUB_START_BINDING_FILE", None)
    environment.update(overrides or {})
    result = subprocess.run([sys.executable, "-", str(tmp_path / "attempt-1.log"),
                             "attempt-1", "ubuntu-test", "glm", "glm-model", "packet", "~", str(BUNDLE)],
                            input=fragment, env=environment, capture_output=True, text=True, timeout=10)
    return result


def test_actual_reservation_fragment_preserves_distinct_roots_and_durable_snapshot(tmp_path):
    result = reserve_fragment(tmp_path)
    assert result.returncode == 0, result.stderr
    snapshot = tmp_path / "attempt-1.launch-correlation.json"
    value = wire.load_snapshot(snapshot, expected_sha256=hashlib.sha256(snapshot.read_bytes()).hexdigest(),
                               run_id="attempt-1", routing_root_id="native-root", routing_parent_run_id="native-parent")
    assert value["correlation"] == envelope()
    original = snapshot.read_bytes()
    assert reserve_fragment(tmp_path).returncode == 75
    assert snapshot.read_bytes() == original


@pytest.mark.parametrize("overrides", [
    {"POOL_ORCHESTRATOR_ID": "runtime-root"}, {"POOL_PARENT_RUN_ID": ""},
    {"REMOTE_SUB_START_BINDING_FILE": "ambiguous-v1-input"},
])
def test_actual_fragment_refuses_bad_lineage_before_reserving(tmp_path, overrides):
    result = reserve_fragment(tmp_path, overrides)
    assert result.returncode == 73
    assert not (tmp_path / "attempt-1.log").exists()
    assert not (tmp_path / "attempt-1.launch-correlation.json").exists()


def test_actual_executor_missing_sidecar_refuses_before_physical_admission(tmp_path, monkeypatch):
    source = patched(tmp_path, "remote_sub_exec.py", "EXECUTOR_SOURCE.json")
    tree = ast.parse(source)
    execute = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "_execute")
    module = ast.Module(body=[execute], type_ignores=[])
    calls = []
    def forbidden(*args, **kwargs):
        pytest.fail("missing bound sidecar reached physical admission")
    monkeypatch.setitem(sys.modules, "fabric_launch_transport", wire)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setenv("FABRIC_LAUNCH_SNAPSHOT_SHA256", "a" * 64)
    monkeypatch.setenv("POOL_ORCHESTRATOR_ID", "native-root")
    monkeypatch.setenv("POOL_PARENT_RUN_ID", "native-parent")
    scope = dict(Path=Path, __file__=str(tmp_path / "remote_sub_exec.py"), os=os,
                 _fail=lambda text, rc: (calls.append(text) or rc), load_runtime_config=forbidden,
                 LaneLease=SimpleNamespace(acquire=forbidden))
    exec(compile(module, "patched-remote-executor", "exec"), scope)
    packet = tmp_path / "packet.txt"; packet.write_text("inert source fixture")
    state = {"started": False}
    result = scope["_execute"](["remote_sub_exec.py", "attempt-1", "glm", str(packet), "~", "glm-model"], state)
    assert result == 78
    assert calls == ["BOUND_LAUNCH_CONTEXT_REFUSED before_spawn=1"]
    assert state["started"] is False


def test_bound_receipt_collection_failure_does_not_settle_or_retry(tmp_path):
    source = patched(tmp_path, "remote_sub.sh", "RESERVATION_SOURCE.json")
    start = source.index('if [ -n "${REMOTE_SUB_START_CORRELATION_FILE:-}" ]; then\n  if "$RSYNC_CMD"')
    fragment = source[start:source.index('\nif [ "$RSYNC_RC" -ne 0 ]; then', start)]
    script = ('REMOTE_SUB_START_CORRELATION_FILE=fixture\nRSYNC_CMD=false\nSSH_ALIAS=inert\n'
              'ID=attempt-1\nLOG_DIR=fixture\nPRESERVE_LEASE=1\nRC=76\n'
              'log() { printf "%s\\n" "$*"; }\n' + fragment +
              '\ntest "$PRESERVE_LEASE" = 1 && test "$RC" = 76\n')
    result = subprocess.run(["bash", "-c", script], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0
    assert "retry_authorized=0" in result.stdout
    assert "remote_artifact_preserved=1" in result.stdout


def test_actual_launch_fragment_refuses_consistent_sidecar_drift(tmp_path):
    result = reserve_fragment(tmp_path)
    assert result.returncode == 0
    source = patched(tmp_path, "remote_sub.sh", "RESERVATION_SOURCE.json")
    fragment = source.split("<<'PY_BOUND_SHA'\n", 1)[1].split("\nPY_BOUND_SHA", 1)[0]
    snapshot = tmp_path / "attempt-1.launch-correlation.json"
    environment = {**os.environ, "POOL_ORCHESTRATOR_ID": "native-root",
                   "POOL_PARENT_RUN_ID": "native-parent"}
    def read():
        return subprocess.run([sys.executable, "-", str(snapshot), str(tmp_path / "attempt-1.log"),
                               str(BUNDLE), "attempt-1"], input=fragment,
                              env=environment, capture_output=True, text=True, timeout=10)
    good = read()
    assert good.returncode == 0
    assert good.stdout.strip() == hashlib.sha256(snapshot.read_bytes()).hexdigest()
    changed = json.loads(snapshot.read_text())
    changed["correlation"]["runtime_binding"]["job_id"] = "foreign-job"
    changed["reservation_sha256"] = hashlib.sha256(
        fence.CORRELATION_PREFIX + wire.canonical(changed["correlation"])).hexdigest()
    snapshot.write_bytes(wire.canonical(changed))
    refused = read()
    assert refused.returncode == 78
    assert "BOUND_SNAPSHOT_RESERVATION_MISMATCH" in refused.stderr
    assert refused.stdout == ""

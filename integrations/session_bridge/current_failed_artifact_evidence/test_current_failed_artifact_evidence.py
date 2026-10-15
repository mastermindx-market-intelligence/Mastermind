"""Inert qualification/publication tests; no host or worker calls."""
import base64
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import types

import pytest


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def env(tmp_path, monkeypatch):
    candidate = Path(os.environ["RF_EVIDENCE_CANDIDATE"])
    reader = load("artifact_reader", candidate / "baseline-artifact_reader.py")
    d = load("artifact_delivery", candidate / "artifact_delivery.py")
    m = load("current_failed_artifact_evidence", Path(__file__).with_name("current_failed_artifact_evidence.py"))
    monkeypatch.setenv("CODEX_THREAD_ID", m.ROOT)
    monkeypatch.delenv("POOL_ORCHESTRATOR_ID", raising=False)
    monkeypatch.setattr(d, "HERE", tmp_path)
    monkeypatch.setattr(d, "DESTINATION_ROOT", tmp_path)
    (tmp_path / "state/remote_sub").mkdir(parents=True)
    status = dict(run_id=m.RUN_ID, state="TERMINAL", rc=65, signal="other", root_id=m.ROOT,
                  parent_run_id=m.PARENT, lineage_state="VERIFIED_TERMINAL", accepted=None,
                  acceptance_state="UNVERIFIED", result_available=True)
    monkeypatch.setitem(sys.modules, "fabric_task", types.SimpleNamespace(inspect_run=lambda rid: copy.deepcopy(status)))
    log = "\n".join(f"2026-10-13T05:09Z [remote_sub id={m.RUN_ID} host=ubuntu0] {event}" for event in [
        "LAUNCH_ATTEMPT attempt=1", f"LAUNCH stdout=lanes_{m.RUN_ID}.stdout rc_file=ext/lanes_{m.RUN_ID}.rc cwd=~",
        "REMOTE_DONE rc=65", "DONE rc=65 signal=other reason=remote_nonzero"])
    process = dict(schema="mastermind.local_owned_process_receipt.v1", label=m.RUN_ID, returncode=0,
                   timed_out=False, pid=42, pgid=42, runtime_failure_code=None, stdout_bytes=5702,
                   stdout_sha256="d738dc3336aaef80c3845cecac686adae628586c12fd97ac4997984c85817fdc",
                   stdout_truncated=False, stderr_truncated=False,
                   started_at="2026-10-13T04:38:44.277Z", ended_at="2026-10-13T05:08:57.494Z",
                   cleanup=dict(identity_verified=True, census_proven=True, status="not_needed", error_code=None,
                                residual_count=0, stdin_delivery_complete=True, stdin_delivery_error=None,
                                stdout_capture_complete=True, stdout_capture_error=None,
                                stderr_capture_complete=True, stderr_capture_error=None))
    raws = {"log": log.encode(), "process.jsonl": reader.canonical(process)}
    monkeypatch.setattr(m, "SOURCE_HASHES", {k: d.digest(v) for k, v in raws.items()})
    for suffix, raw in raws.items():
        path = tmp_path / "state/remote_sub" / (m.RUN_ID + "." + suffix)
        path.write_bytes(raw); path.chmod(0o600)
    (tmp_path / "hosts.json").write_text(json.dumps({"ubuntu0": {"ssh_alias": "ubuntu0", "allowed_modes": ["glm"]}}))
    (tmp_path / "artifact_reader.py").write_bytes((candidate / "baseline-artifact_reader.py").read_bytes())
    monkeypatch.setattr(m, "DESTINATION", tmp_path / "retained")
    # Existing publisher does not need the native-only modules during these tests.
    monkeypatch.setattr(d, "transport", lambda *a, **k: pytest.fail("unexpected live transport"))
    return m, d, reader, status, process, tmp_path


def test_nonzero_unverified_projection_qualifies_without_stdout(env):
    m, d, r, status, process, path = env
    assert m.qualify(m.RUN_ID)["original_projection"]["acceptance_state"] == "UNVERIFIED"
    assert not list(path.glob("**/*stdout*"))


@pytest.mark.parametrize("key,value", [
    ("run_id", "another"), ("state", "EFFECT_UNKNOWN"), ("state", "ACTIVE_OR_WAITING"),
    ("rc", 0), ("rc", True), ("root_id", "another"), ("parent_run_id", "another"),
    ("lineage_state", "UNKNOWN"), ("accepted", True), ("acceptance_state", "ACCEPTED")])
def test_conflicting_projection_refuses(env, key, value):
    m, d, r, status, process, path = env
    status[key] = value
    with pytest.raises(ValueError, match="projection_unqualified"):
        m.qualify(m.RUN_ID)


def test_wrong_run_cannot_change_scope(env):
    with pytest.raises(ValueError, match="not_admitted"):
        env[0].request_for("another")


@pytest.mark.parametrize("thread,pool", [(None, None), ("another", None),
    ("01a1333c-a475-7052-95a8-72a88eb8c17b", "another")])
def test_wrong_or_missing_invoker_cannot_spend_read(env, monkeypatch, thread, pool):
    m, d, r, status, process, path = env
    for name, value in (("CODEX_THREAD_ID", thread), ("POOL_ORCHESTRATOR_ID", pool)):
        if value is None: monkeypatch.delenv(name, raising=False)
        else: monkeypatch.setenv(name, value)
    monkeypatch.setattr(m, "qualify", lambda *a: pytest.fail("qualification before caller discipline"))
    with pytest.raises(ValueError, match="assigning_parent_required"):
        m.export(m.RUN_ID, m.DESTINATION)
    assert not m.DESTINATION.exists()


@pytest.mark.parametrize("mode", [0o644, 0o664, 0o666])
def test_nonprivate_binding_refuses(env, mode):
    m, d, r, status, process, path = env
    (path / "state/remote_sub" / (m.RUN_ID + ".log")).chmod(mode)
    with pytest.raises(ValueError, match="private_source_required"):
        m.qualify(m.RUN_ID)


def test_changed_source_and_mixed_family_refuse(env):
    m, d, r, status, process, path = env
    log = path / "state/remote_sub" / (m.RUN_ID + ".log")
    log.write_bytes(log.read_bytes() + b"changed")
    with pytest.raises(ValueError, match="original_source_changed"):
        m.qualify(m.RUN_ID)
    (path / "state/remote_sub" / (m.RUN_ID + ".go-run.json")).write_text("{}")
    with pytest.raises(ValueError, match="mixed_capsule"):
        m.qualify(m.RUN_ID)


@pytest.mark.parametrize("mutation", ["cleanup", "capture", "time", "returncode"])
def test_process_metadata_negatives(env, mutation):
    m, d, r, status, process, path = env
    if mutation == "cleanup": process["cleanup"]["residual_count"] = 1
    if mutation == "capture": process["cleanup"]["stdout_capture_complete"] = False
    if mutation == "time": process["ended_at"] = "2026-10-12T05:08:57.494Z"
    if mutation == "returncode": process["returncode"] = 65
    with pytest.raises(ValueError): m.validate_process(r.canonical(process))


def setup_export(env, monkeypatch, negative=False, mismatch=False):
    m, d, r, status, process, path = env
    data = (b"source", b"test")
    files = tuple((original[0], len(raw), d.digest(raw)) for original, raw in zip(m.FILES, data))
    monkeypatch.setattr(m, "FILES", files)
    calls = []
    def transport(alias, request):
        calls.append((alias, copy.deepcopy(request)))
        entries = []
        for i, ((name, size, digest), raw) in enumerate(zip(files, data)):
            if negative and i == 0:
                entries.append(dict(path=name, status="UNAVAILABLE", reason="directory_owner_or_mode")); continue
            if mismatch and i == 0: raw = b"wrong"
            entries.append(dict(path=name, status="RETRIEVED", bytes=len(raw), sha256=d.digest(raw),
                                data_base64=base64.b64encode(raw).decode(),
                                observed_file=dict(device=1, inode=i + 1, mtime_ns=1, uid=1000, mode=0o600)))
        return r.canonical(dict(schema=r.SCHEMA, request_sha256=d.digest(r.canonical(request)), files=entries))
    monkeypatch.setattr(d, "transport", transport)
    return calls


def test_current_export_complete_retains_failure_and_prevents_repeat(env, monkeypatch):
    m, d, r, status, process, path = env
    calls = setup_export(env, monkeypatch)
    receipt = m.export(m.RUN_ID, m.DESTINATION)
    assert receipt["state"] == "COMPLETE" and receipt["requested_content_constraints_matched"]
    assert receipt["original_execution_rc"] == 65
    for key in ("original_artifact_contract_passed", "historical_worker_bytes_attested", "stdout_reverified",
                "producer_manifest_verified", "execution_replayed", "original_operation_mutated", "outcome_accepted"):
        assert receipt[key] is False
    assert json.loads((m.DESTINATION / "receipt.json").read_text()) == receipt
    with pytest.raises(FileExistsError): m.export(m.RUN_ID, m.DESTINATION)
    with pytest.raises(ValueError, match="destination_not_admitted"):
        m.export(m.RUN_ID, path / "alternate")
    assert len(calls) == 1 and status["rc"] == 65 and status["accepted"] is None


@pytest.mark.parametrize("failure,expected", [("mode", "PARTIAL"), ("content", "UNAVAILABLE")])
def test_read_guard_and_content_failures_are_retained_without_retry(env, monkeypatch, failure, expected):
    m, d, r, status, process, path = env
    calls = setup_export(env, monkeypatch, negative=failure == "mode", mismatch=failure == "content")
    receipt = m.export(m.RUN_ID, m.DESTINATION)
    assert receipt["state"] == expected and not receipt["requested_content_constraints_matched"]
    with pytest.raises(FileExistsError): m.export(m.RUN_ID, m.DESTINATION)
    assert len(calls) == 1


def test_publication_source_change_invalidates_published_inode(env, monkeypatch):
    m, d, r, status, process, path = env
    setup_export(env, monkeypatch)
    original = m.qualify
    calls = []
    def qualify(run):
        calls.append(run)
        # Initial, pre-read, post-read, pre-publication, post-publication.
        if len(calls) == 5: raise ValueError("changed original")
        return original(run)
    monkeypatch.setattr(m, "qualify", qualify)
    with pytest.raises(ValueError, match="local_publication_unconfirmed"):
        m.export(m.RUN_ID, m.DESTINATION)
    receipt = json.loads((m.DESTINATION / "receipt.json").read_text())
    assert receipt["state"] == "UNAVAILABLE"
    assert receipt["requested_content_constraints_matched"] is False
    assert receipt["outcome_accepted"] is False


def test_cli_exact_branch_and_existing_profiles(env, monkeypatch, capsys):
    m, d, r, status, process, path = env
    calls = []
    monkeypatch.setattr(m, "export", lambda run, dest: calls.append((run, dest)) or {"state": "COMPLETE"})
    monkeypatch.setattr(sys, "argv", ["artifact_delivery.py", "--capsule-current", m.RUN_ID, "--destination", str(m.DESTINATION)])
    assert d.main() == 0 and len(calls) == 1
    assert r.capsule_request(r.CAPSULE_INTENT["run_id"])["schema"] == r.CAPSULE_SCHEMA
    assert r.capsule_request(r.BRIDGE_INTENT["run_id"])["schema"] == r.CAPSULE_SCHEMA
    monkeypatch.setattr(sys, "argv", ["artifact_delivery.py", "--capsule-current", "other", "--destination", str(m.DESTINATION)])
    assert d.main() == 75 and len(calls) == 1

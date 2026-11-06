"""Finite source behavior only; synthetic owners confer no host admission."""
import ast
from contextlib import contextmanager
import copy
import dataclasses
import hashlib
import inspect
import json
import sqlite3
import os
import runpy
import subprocess
import sys
from types import SimpleNamespace
from pathlib import Path

import pytest

from ops.executive_os import macro_adoption as adoption
from ops.executive_os import autonomy_control as control
from ops.executive_os import control_observation
from test_prepare_control_successor import control_input


@pytest.fixture
def operands(control_input):
    value = copy.deepcopy(control_input)
    sha = value["proof_base_sha"]
    old = str(control.SYSTEM_ROOT / "macro-sources" / ("a" * 40))
    new = str(control.SYSTEM_ROOT / "macro-sources" / ("b" * 40))
    value["ceo_ingress_app_macro_root"] = old
    raw = adoption.encoded(value)
    request = dict(expected_release_sha=sha, current_control_sha256=adoption.digest(raw),
                   current_worker_sha256="c" * 64, expected_old_macro_root=old,
                   target_macro_root=new, target_macro_sha="b" * 40,
                   target_generation_seal_sha256="d" * 64,
                   target_artifact_sha256="e" * 64,
                   expected_receipts={key: None for key in adoption.RECEIPTS})
    return value, raw, request


def test_candidate_changes_only_macro_preserves_transport_and_inert_wake(operands):
    value, _, document = operands
    value["dialogue_wake_canary_activation"] = {"retained": "inert historical source"}
    raw = adoption.encoded(value)
    document["current_control_sha256"] = adoption.digest(raw)
    before = copy.deepcopy(value)
    result = json.loads(adoption.prepare_candidate(adoption.parse_request(document), raw))
    assert value == before
    assert set(result) == set(value)
    assert {key for key in value if value[key] != result[key]} == {"ceo_ingress_app_macro_root"}
    assert result["ceo_ingress_app_armed"] is True
    assert result["dialogue_wake_canary_activation"] == value["dialogue_wake_canary_activation"]
    assert result["proof_base_sha"] == value["proof_base_sha"]


@pytest.mark.parametrize("field", ["ceo_submit_armed", "coo_autonomy_armed", "coo_operator_harness_armed"])
@pytest.mark.parametrize("bad", [True, None, 0])
def test_candidate_refuses_open_or_nonboolean_intake(operands, field, bad):
    value, _, document = operands
    value[field] = bad
    raw = adoption.encoded(value)
    document["current_control_sha256"] = adoption.digest(raw)
    with pytest.raises(adoption.AdoptionError):
        adoption.prepare_candidate(adoption.parse_request(document), raw)


@pytest.mark.parametrize("mutation", ["unknown", "hash", "uppercase", "root", "basename", "same", "receipt", "receipt_bool"])
def test_closed_request_refuses_malformed_or_unbound_values(operands, mutation):
    _, _, value = operands
    if mutation == "unknown": value["arm"] = True
    if mutation == "hash": value["target_artifact_sha256"] = "0" * 63
    if mutation == "uppercase": value["expected_release_sha"] = "A" * 40
    if mutation == "root": value["target_macro_root"] = "/tmp/" + value["target_macro_sha"]
    if mutation == "basename": value["target_macro_sha"] = "f" * 40
    if mutation == "same": value["target_macro_root"] = value["expected_old_macro_root"]
    if mutation == "receipt": value["expected_receipts"].pop("autonomy")
    if mutation == "receipt_bool": value["expected_receipts"]["autonomy"] = False
    with pytest.raises(adoption.AdoptionError): adoption.parse_request(value)


def test_request_copies_receipt_input_and_is_immutable(operands):
    _, _, value = operands
    request = adoption.parse_request(value)
    value["expected_receipts"]["autonomy"] = "f" * 64
    assert request.expected_receipts["autonomy"] is None
    with pytest.raises(TypeError): request.expected_receipts["autonomy"] = "a" * 64


def test_json_duplicate_key_and_control_cas_fail_closed(operands):
    with pytest.raises(adoption.AdoptionError, match="duplicate_key"):
        adoption.decoded(b'{"a":1,"a":2}')
    _, raw, value = operands
    request = adoption.parse_request(value)
    with pytest.raises(adoption.AdoptionError, match="control_preimage_mismatch"):
        adoption.prepare_candidate(request, raw + b" ")


class Held:
    def __init__(self, fail=None, interrupt=False):
        self.events = []
        self.fail = fail
        self.interrupt = interrupt
        self.rows = [{"job_id": "original-root", "status": "QUEUED", "attempt_count": 0},
                     {"job_id": "completed-child", "status": "COMPLETED", "attempt_count": 1}]
        self.receipts = {"old": b"historical authority"}
    def call(self, name, result=None):
        self.events.append(name)
        if name == self.fail:
            if self.interrupt: raise KeyboardInterrupt()
            raise RuntimeError(name)
        return result
    def recheck_preimage(self): self.call("preflight")
    def begin(self): self.call("begin")
    def recheck_before_replace(self): self.call("final_gates")
    def phase(self, phase): self.call(phase)
    def replace_control(self): self.call("replace")
    def recheck_postimage(self): self.call("postimage")
    def publish_observation(self): return self.call("observation", "a" * 64)
    def publish_receipt(self, observed):
        assert observed == "a" * 64
        return self.call("receipt", {"authority_resumed": False})
    def complete(self): self.call("closeout")


class Host:
    def __init__(self, held, qualification_error=False):
        self.held, self.qualification_error = held, qualification_error
    @contextmanager
    def qualified(self, request):
        if self.qualification_error: raise RuntimeError("qualification")
        yield self.held


SEQUENCE = ["preflight", "begin", "final_gates", "CONFIG_RENAME_STARTED", "replace", "postimage",
            "OBSERVATION_PUBLICATION_STARTED", "observation", "RECEIPT_PUBLICATION_STARTED",
            "receipt", "COMPLETE", "closeout"]


def test_success_is_ordered_and_does_not_edit_queued_rows_or_historical_receipts(operands):
    held = Held()
    rows, receipts = copy.deepcopy(held.rows), copy.deepcopy(held.receipts)
    assert adoption.adopt(Host(held), adoption.parse_request(operands[2])) == {"authority_resumed": False}
    assert held.events == SEQUENCE
    assert held.rows == rows and held.receipts == receipts


@pytest.mark.parametrize("stage", SEQUENCE)
@pytest.mark.parametrize("interrupt", [False, True])
def test_each_boundary_failure_holds_without_rollback_retry_or_rearm(operands, stage, interrupt):
    held = Held(stage, interrupt)
    with pytest.raises(adoption.AdoptionError) as error:
        adoption.adopt(Host(held), adoption.parse_request(operands[2]))
    assert error.value.effect_unknown is (stage != "preflight")
    assert held.events == SEQUENCE[:SEQUENCE.index(stage) + 1]


def test_failed_owner_qualification_has_no_effect(operands):
    held = Held()
    with pytest.raises(adoption.AdoptionError) as error:
        adoption.adopt(Host(held, True), adoption.parse_request(operands[2]))
    assert not error.value.effect_unknown and not held.events


def test_control_observation_rejects_forged_type_and_unheld_real_type():
    with pytest.raises(control.TransactionEffectUnknown):
        control_observation.publish_for_macro_adoption(object())
    forged = adoption._HeldAdoption.__new__(adoption._HeldAdoption)
    with pytest.raises(adoption.AdoptionError, match="held_owner_required"):
        control_observation.publish_for_macro_adoption(forged)


def test_actual_existing_ceo_binding_predicate_rejects_new_macro(operands):
    value, _, request = operands
    value.update(ceo_ingress_app_peer_uid=458, ceo_ingress_peer_uid=452)
    binding = control.ExecutiveAppBinding(
        present=True, app_peer_user=control.EXECUTIVE_APP_USER, app_peer_uid=458,
        app_armed=True, app_macro_root=request["expected_old_macro_root"], ingress_peer_uid=452,
        ingress_socket_path=value["ceo_ingress_socket_path"],
        launchd_socket_name=value["ceo_ingress_launchd_socket_name"],
        binding_valid=True, acl_valid=True, topology_valid=True)
    assert control._ceo_submit_binding_matches_control(value, binding)
    value["ceo_ingress_app_macro_root"] = request["target_macro_root"]
    assert not control._ceo_submit_binding_matches_control(value, binding)


def test_status_has_no_modifying_calls_and_production_has_no_lifecycle_or_db_writes():
    status_tree = ast.parse(inspect.getsource(adoption.status))
    called = {n.func.attr for n in ast.walk(status_tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
    assert not called & {"replace", "rename", "unlink", "rmdir", "mkdir", "run", "_atomic_file"}
    source = inspect.getsource(adoption)
    assert '"service-control.sh"' not in source
    assert "execute_ceo_submit_arm(" not in source
    assert "execute_disarm(" not in source
    assert "_allow_synthetic_fixture=True" not in source
    assert not any(word in source for word in ('"UPDATE ', '"INSERT ', '"DELETE ', '"PRAGMA wal_checkpoint'))


def test_production_host_offers_no_public_effect_to_synthetic_or_nonroot_source(operands):
    # Real production entry must fail on this noninstalled test checkout before
    # invoking launchctl, collector, lock or a write. No production guard patched.
    with pytest.raises(adoption.AdoptionError):
        with adoption.ProductionHost().qualified(adoption.parse_request(operands[2])):
            pytest.fail("uninstalled source acquired production custody")


def test_actual_full_autonomy_guard_rejects_changed_config_without_renewal():
    from tests import test_ceo_submit_autonomy_coexistence as fixtures
    from tests import test_executive_autonomy as receipts
    from tests import test_executive_autonomy_control as hosts
    host = fixtures.full_host()
    before = host.load_ceo_submit_configs(hosts.SHA)
    proof = fixtures.full_receipt(before)
    assert control.coexistence_receipt_eligible(before, proof, receipts._metadata(), expected_sha=hosts.SHA, now=hosts.NOW)
    changed = dict(before.control, ceo_ingress_app_macro_root=str(control.SYSTEM_ROOT / "macro-sources" / ("b" * 40)))
    raw = control.encode_config(changed)
    after = dataclasses.replace(before, control=changed, control_bytes=raw, control_sha256=adoption.digest(raw))
    assert not control.coexistence_receipt_eligible(after, proof, receipts._metadata(), expected_sha=hosts.SHA, now=hosts.NOW)


@pytest.mark.parametrize("stamp, reference, admitted", [
    ("2026-10-31T05:28:23Z", "2026-11-02T05:28:22Z", True),
    ("2026-10-31T05:28:23Z", "2026-11-02T05:28:23Z", False),
    ("2026-10-31T05:28:23Z", "2026-11-02T05:28:24Z", False),
    ("2026-10-31T06:28:24Z", "2026-10-31T05:28:23Z", False),
    (None, "2026-10-31T05:28:23Z", False),
])
def test_actual_mapper_budget_remains_positive_at_adoption_edge(stamp, reference, admitted):
    if admitted: adoption._require_current(stamp, reference)
    else:
        with pytest.raises(adoption.AdoptionError): adoption._require_current(stamp, reference)


@pytest.fixture
def quiescent_db():
    db = sqlite3.connect(":memory:")
    db.executescript("CREATE TABLE jobs(status TEXT); CREATE TABLE attempts(status TEXT);"
                     "CREATE TABLE worker_quota_classes(held_attempt_id TEXT);"
                     "INSERT INTO jobs VALUES ('QUEUED'),('COMPLETED');"
                     "INSERT INTO attempts VALUES ('COMPLETED');"
                     "INSERT INTO worker_quota_classes VALUES (NULL);")
    yield db
    db.close()


def test_quiescence_preserves_actual_sql_queued_and_completed_rows(quiescent_db):
    before = list(quiescent_db.iterdump())
    writes = quiescent_db.total_changes
    adoption._runtime_quiescent(quiescent_db)
    assert list(quiescent_db.iterdump()) == before
    assert quiescent_db.total_changes == writes


@pytest.mark.parametrize("change", [
    "UPDATE attempts SET status='CLAIMED'", "UPDATE attempts SET status='RUNNING'",
    "UPDATE attempts SET status='MYSTERY'", "UPDATE jobs SET status='RUNNING'",
    "UPDATE jobs SET status='CHECKPOINTED'", "UPDATE jobs SET status='CANCEL_REQUESTED'",
    "UPDATE jobs SET status='MYSTERY'", "UPDATE worker_quota_classes SET held_attempt_id='held'",
])
def test_actual_quiescence_queries_refuse_live_unknown_or_held_work(quiescent_db, change):
    quiescent_db.execute(change)
    with pytest.raises((adoption.AdoptionError, control.ArmAdmissionError)):
        adoption._runtime_quiescent(quiescent_db)


@pytest.fixture
def completed(operands):
    _, raw, document = operands
    worker = b'{}'
    document["current_worker_sha256"] = adoption.digest(worker)
    request = adoption.parse_request(document)
    candidate = adoption.prepare_candidate(request, raw)
    manifest = dict(schema=adoption.SCHEMA, operation="MACRO_ADOPT",
                    operation_id="autonomy-" + request.current_control_sha256[:12],
                    request=request.document(), candidate_sha256=adoption.digest(candidate), phase="COMPLETE")
    archives = {"prior-control.json": raw, "prior-worker.json": worker}
    archives.update({"prior-" + key + ".json": b"" for key in adoption.RECEIPTS})
    target = dict(source_sha=request.expected_release_sha, macro_sha=request.target_macro_sha,
                  macro_seal_sha256=request.target_generation_seal_sha256,
                  artifact_sha256=request.target_artifact_sha256,
                  generated_at="2026-10-31T05:28:23Z", observed_at="2026-10-31T21:00:00Z")
    observation = b'actual independently encoded observation'
    acceptance = "f" * 64
    receipt = dict(schema=adoption.RECEIPT_SCHEMA, operation_id=manifest["operation_id"],
                   request_sha256=adoption.digest(adoption.encoded(document)), release_sha=request.expected_release_sha,
                   old_control_sha256=request.current_control_sha256, new_control_sha256=adoption.digest(candidate),
                   worker_sha256=request.current_worker_sha256, old_macro_root=request.expected_old_macro_root,
                   target_macro_root=request.target_macro_root, target=target,
                   historical_acceptance_sha256=acceptance, control_observation_sha256=adoption.digest(observation),
                   authority_resumed=False, services_started=False, observed_at=target["observed_at"])
    current = {key: None for key in adoption.RECEIPTS}
    current.update(adoption=adoption.encoded(receipt), control_observation=observation)
    return [request, manifest, archives, candidate, worker, current, observation, acceptance]


@pytest.mark.parametrize("phase", ["COMPLETE", "RECEIPT_PUBLICATION_STARTED"])
def test_same_operation_closeout_requires_completed_bytes_without_replaying_publications(completed, phase):
    completed[1]["phase"] = phase
    before = copy.deepcopy(completed[1:])
    result = adoption.validate_completed(*completed)
    assert result["authority_resumed"] is False
    assert completed[1:] == before


@pytest.mark.parametrize("defect", ["phase", "operation", "request", "candidate", "worker", "missing_archive",
    "archive", "missing_receipt", "receipt_authority", "receipt_target", "observation", "acceptance", "authority_changed"])
def test_incomplete_or_conflicting_closeout_bytes_stay_held(completed, defect):
    if defect == "phase": completed[1]["phase"] = "CONFIG_RENAME_STARTED"
    if defect == "operation": completed[1]["operation_id"] = "autonomy-other"
    if defect == "request": completed[1]["request"] = {}
    if defect == "candidate": completed[3] += b" "
    if defect == "worker": completed[4] += b" "
    if defect == "missing_archive": completed[2].pop("prior-control.json")
    if defect == "archive": completed[2]["prior-adoption.json"] = b"unexpected"
    if defect == "missing_receipt": completed[5]["adoption"] = None
    if defect in {"receipt_authority", "receipt_target"}:
        value = json.loads(completed[5]["adoption"])
        if defect == "receipt_authority": value["authority_resumed"] = True
        else: value["target"]["macro_sha"] = "a" * 40
        completed[5]["adoption"] = adoption.encoded(value)
    if defect == "observation": completed[6] += b" "
    if defect == "acceptance": completed[7] = "0" * 64
    if defect == "authority_changed": completed[5]["autonomy"] = b"new authority"
    with pytest.raises(adoption.AdoptionError): adoption.validate_completed(*completed)


def test_documented_script_delegates_to_canonical_package_before_owner_definition(monkeypatch):
    # This substitutes CLI dispatch only, never a Root/custody verdict. The
    # actual canonical owner class and process-local state retain identity.
    canonical = adoption._HeldAdoption
    observed = []
    def command():
        observed.append(adoption._HeldAdoption)
        return 19
    monkeypatch.setattr(adoption, "main", command)
    with pytest.raises(SystemExit) as error:
        runpy.run_path(adoption.__file__, run_name="__main__")
    assert error.value.code == 19 and observed == [canonical]


def test_actual_script_help_uses_canonical_entry_without_root_effect():
    process = subprocess.run([sys.executable, adoption.__file__, "--help"],
                             capture_output=True, text=True, check=False)
    assert process.returncode == 0
    assert "close-complete" in process.stdout


def test_parent_target_freshness_is_not_shadowed_by_subprocess_result(operands, monkeypatch):
    request = adoption.parse_request(operands[2])
    observed = dict(source_sha=request.expected_release_sha, macro_sha=request.target_macro_sha,
                    macro_seal_sha256=request.target_generation_seal_sha256,
                    artifact_sha256=request.target_artifact_sha256,
                    generated_at="2000-01-01T00:00:00Z", observed_at="2000-01-01T00:00:00Z")
    holder = adoption._HeldAdoption.__new__(adoption._HeldAdoption)
    holder.request = request
    monkeypatch.setattr(adoption.pwd, "getpwnam", lambda _: SimpleNamespace(pw_dir="/synthetic-control"))
    calls = []
    def reader(argv, **_):
        calls.append(argv)
        return SimpleNamespace(returncode=0, stdout=adoption.encoded(observed))
    monkeypatch.setattr(adoption.subprocess, "run", reader)
    with pytest.raises(adoption.AdoptionError, match="target_artifact_not_current"):
        holder._target()
    assert "qualify-target" in calls[-1]
    holder._target(completed=True)  # Read-only completed-byte observation only.
    assert "observe-completed-target" in calls[-1]


def test_public_artifact_budget_does_not_reuse_private_config_limit_and_rejects_duplicate_stamp():
    raw = json.dumps({"generated_at": "2026-10-31T00:00:00Z", "public_source": "x" * 200000}).encode()
    assert adoption.decoded(raw, maximum=2 * 1024 * 1024)["generated_at"]
    with pytest.raises(adoption.AdoptionError, match="document_too_large"):
        adoption.decoded(raw)
    with pytest.raises(adoption.AdoptionError, match="duplicate_key"):
        adoption.decoded(b'{"generated_at":"old","generated_at":"new"}', maximum=2 * 1024 * 1024)


@pytest.mark.skipif(sys.platform != "darwin", reason="actual Darwin exclusive-rename primitive")
@pytest.mark.parametrize("lost_ack", [False, True])
def test_atomic_completed_archive_preserves_every_byte_even_after_lost_ack(tmp_path, monkeypatch, lost_ack):
    marker, archive = tmp_path / "canonical", tmp_path / "retained"
    marker.mkdir()
    expected = {"transaction.json": b"complete original phase", "prior-control.json": b"exact original bytes"}
    for name, raw in expected.items(): (marker / name).write_bytes(raw)
    fd = os.open(marker, os.O_RDONLY | os.O_DIRECTORY)
    try:
        if lost_ack:
            monkeypatch.setattr(adoption.control, "_fsync_directory",
                                lambda _: (_ for _ in ()).throw(OSError("lost close acknowledgement")))
            with pytest.raises(OSError): adoption._archive_generation(marker, archive, fd)
        else:
            adoption._archive_generation(marker, archive, fd)
        assert not marker.exists()
        assert {path.name: path.read_bytes() for path in archive.iterdir()} == expected
        assert archive.stat().st_ino == os.fstat(fd).st_ino
    finally:
        os.close(fd)


def test_existing_archive_never_loses_or_overwrites_either_generation(tmp_path):
    marker, archive = tmp_path / "canonical", tmp_path / "retained"
    marker.mkdir(); archive.mkdir()
    (marker / "proof").write_bytes(b"original")
    (archive / "proof").write_bytes(b"other")
    fd = os.open(marker, os.O_RDONLY | os.O_DIRECTORY)
    try:
        with pytest.raises(adoption.AdoptionError): adoption._archive_generation(marker, archive, fd)
        assert (marker / "proof").read_bytes() == b"original"
        assert (archive / "proof").read_bytes() == b"other"
    finally:
        os.close(fd)


def test_status_reports_receipt_even_when_marker_manifest_is_torn(completed):
    request, _, _, candidate, _, current, _, _ = completed
    receipt = adoption.decoded(current["adoption"])
    facts = adoption._status_facts(request, adoption.digest(candidate), "CANONICAL", None, receipt)
    assert facts["state"] == "HELD_UNKNOWN"
    assert facts["receipt_state"] == "MATCHING_POSTIMAGE_OBSERVATION"
    assert facts["configuration"] == "POSTIMAGE" and facts["modifying_action"] is False


def test_status_distinguishes_completed_retained_archive_without_admitting_authority(completed):
    request, manifest, _, candidate, _, current, _, _ = completed
    facts = adoption._status_facts(request, adoption.digest(candidate), "PRIVATE", manifest,
                                   adoption.decoded(current["adoption"]))
    assert facts["state"] == "COMPLETED_ARCHIVE_OBSERVED_REQUIRES_ADJUDICATION"
    assert facts["phase"] == "COMPLETE" and facts["modifying_action"] is False

"""PREPARED byte-proof and real namespace faults; never Root/host proof."""
import ast
import copy
import inspect
import os
from pathlib import Path
import stat
import sys

import pytest

from ops.executive_os import macro_adoption as adoption
from tests.test_executive_macro_adoption import operands
from test_prepare_control_successor import control_input


@pytest.fixture
def prepared(operands):
    _, before, document = operands
    worker = adoption.encoded({"operator_harness_armed": False})
    document["current_worker_sha256"] = adoption.digest(worker)
    request = adoption.parse_request(document)
    archives = {"prior-control.json": before, "prior-worker.json": worker}
    archives.update({"prior-" + key + ".json": b"" for key in adoption.RECEIPTS})
    candidate = adoption.prepare_candidate(request, before)
    manifest = {"schema": adoption.SCHEMA, "operation": "MACRO_ADOPT",
                "operation_id": "autonomy-" + request.current_control_sha256[:12],
                "request": request.document(), "candidate_sha256": adoption.digest(candidate),
                "phase": "PREPARED"}
    return dict(request=request, manifest=manifest, archives=archives,
                candidate_control=candidate, current_control=before, current_worker=worker,
                current_receipts={key: None for key in adoption.RECEIPTS})


def test_exact_prepared_join_proves_no_live_bytes_changed(prepared):
    original = {key: (value if key == "request" else copy.deepcopy(value))
                for key, value in prepared.items()}
    assert adoption.validate_prepared(**prepared) == prepared["candidate_control"]
    assert prepared == original


@pytest.mark.parametrize("phase", [None, "CONFIG_RENAME_STARTED", "OBSERVATION_PUBLICATION_STARTED", "RECEIPT_PUBLICATION_STARTED", "COMPLETE", "UNKNOWN"])
def test_only_literal_prepared_phase_qualifies(prepared, phase):
    prepared["manifest"]["phase"] = phase
    with pytest.raises(adoption.AdoptionError):
        adoption.validate_prepared(**prepared)


@pytest.mark.parametrize("fault", ["schema", "operation", "operation_id", "request", "checksum", "candidate", "control", "worker", "receipt", "prior_receipt", "archive_missing", "archive_extra", "manifest_extra"])
def test_each_closed_join_mismatch_stays_held(prepared, fault):
    manifest, archives = prepared["manifest"], prepared["archives"]
    if fault in {"schema", "operation", "operation_id"}:
        manifest[fault] = "untrusted"
    elif fault == "request":
        manifest["request"]["target_macro_sha"] = "f" * 40
    elif fault == "checksum":
        manifest["candidate_sha256"] = "0" * 64
    elif fault in {"candidate", "control", "worker"}:
        key = {"candidate": "candidate_control", "control": "current_control", "worker": "current_worker"}[fault]
        prepared[key] += b" "
    elif fault == "receipt":
        prepared["current_receipts"]["adoption"] = b"unexpected"
    elif fault == "prior_receipt":
        archives["prior-adoption.json"] = b"unexpected"
    elif fault == "archive_missing":
        archives.pop("prior-worker.json")
    elif fault == "archive_extra":
        archives["unbound.json"] = b"unexpected"
    else:
        manifest["unbound"] = True
    with pytest.raises(adoption.AdoptionError):
        adoption.validate_prepared(**prepared)


@pytest.mark.parametrize("device,inode", [(True, 1), (1, True), (-1, 1), (1, 0), (2**64, 1), (1, 2**64)])
def test_owner_token_is_finite_exact_integers(prepared, device, inode):
    with pytest.raises(adoption.AdoptionError, match="prepared_owner_token_invalid"):
        adoption.close_prepared(prepared["request"], owner_device=device, owner_inode=inode)


def test_no_effect_close_has_no_config_receipt_phase_or_service_writer():
    source = inspect.getsource(adoption.close_prepared) + "\n" + inspect.getsource(adoption._close_prepared_generation)
    calls = {getattr(node.func, "attr", getattr(node.func, "id", ""))
             for node in ast.walk(ast.parse(source)) if isinstance(node, ast.Call)}
    assert "_archive_generation" in calls
    assert {"_atomic_file", "publish_observation", "publish_receipt", "phase", "replace_control",
            "start_services", "arm", "execute", "commit"}.isdisjoint(calls)
    assert {"_check_source", "_check_config_mutex", "require_services_already_stopped",
            "require_service_uids_quiescent", "_ServiceAdmissionLock", "_UnstartedPreproofGuard",
            "_quiescent_database", "_runtime_quiescent", "validate_prepared"} <= calls


@pytest.mark.skipif(sys.platform != "darwin", reason="actual Darwin exclusive rename primitive")
@pytest.mark.parametrize("lost_ack", [False, True])
def test_exact_generation_archive_preserves_all_bytes_after_success_or_lost_ack(prepared, tmp_path, monkeypatch, lost_ack):
    # Low-level namespace primitive only: this does not qualify Root ownership.
    marker, archive = tmp_path / "selected-marker", tmp_path / "closed-prepared"
    marker.mkdir(mode=stat.S_IRWXU)
    files = dict(prepared["archives"], **{"transaction.json": adoption.encoded(prepared["manifest"]),
                                         "candidate-control.json": prepared["candidate_control"]})
    for name, raw in files.items():
        (marker / name).write_bytes(raw)
    live = {key: tmp_path / ("live-" + key) for key in ("control", "worker", "receipt", "runtime")}
    for key, path in live.items():
        path.write_bytes((key + "-unchanged").encode())
    before = {key: path.read_bytes() for key, path in live.items()}
    real_fsync = adoption.control._fsync_directory
    def close_ack(path):
        real_fsync(path)
        if lost_ack:
            raise OSError("lost namespace close acknowledgement")
    monkeypatch.setattr(adoption.control, "_fsync_directory", close_ack)
    fd = os.open(marker, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    identity = os.fstat(fd)
    try:
        if lost_ack:
            with pytest.raises(OSError):
                adoption._archive_generation(marker, archive, fd)
        else:
            adoption._archive_generation(marker, archive, fd)
        assert not marker.exists()
        assert (archive.stat().st_dev, archive.stat().st_ino) == (identity.st_dev, identity.st_ino)
        assert {name: (archive / name).read_bytes() for name in files} == files
        assert {key: path.read_bytes() for key, path in live.items()} == before
    finally:
        os.close(fd)


def test_prospective_begin_keeps_actual_owner_edge_proof_at_both_publications():
    source = inspect.getsource(adoption._publish_prepared_generation)
    assert 'tempfile.mkdtemp(' in source and 'TemporaryDirectory' not in source
    assert source.index('stage / "candidate-control.json"') < source.index('control._fsync_directory(stage)')
    assert source.index('control._fsync_directory(stage)') < source.index('_rename_exclusive(stage, private)')
    assert source.index('_rename_exclusive(stage, private)') < source.index('_rename_exclusive(private, control.AUTONOMY_TRANSACTION)')
    assert source.count('check()') == 2
    assert 'self.recheck_preimage' in inspect.getsource(adoption._HeldAdoption.begin)
    calls = {getattr(node.func, "attr", getattr(node.func, "id", ""))
             for node in ast.walk(ast.parse(source)) if isinstance(node, ast.Call)}
    assert {"unlink", "rmdir", "rmtree"}.isdisjoint(calls)


@pytest.mark.skipif(sys.platform != "darwin", reason="actual Darwin exclusive rename primitive")
@pytest.mark.parametrize("fault", ["occupied_archive", "changed_named_inode"])
def test_archive_refuses_collision_or_same_bytes_different_owner(tmp_path, fault):
    marker, archive = tmp_path / "marker", tmp_path / "archive"
    marker.mkdir(mode=stat.S_IRWXU)
    (marker / "retained").write_bytes(b"exact original proof")
    fd = os.open(marker, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        if fault == "occupied_archive":
            archive.mkdir(mode=stat.S_IRWXU)
            (archive / "other-operation").write_bytes(b"do not replace")
        else:
            marker.rename(tmp_path / "original-held")
            marker.mkdir(mode=stat.S_IRWXU)
            (marker / "retained").write_bytes(b"exact original proof")
        before = {str(path.relative_to(tmp_path)): path.read_bytes()
                  for path in tmp_path.rglob("*") if path.is_file()}
        with pytest.raises(adoption.AdoptionError, match="occupied_or_changed"):
            adoption._archive_generation(marker, archive, fd)
        assert {str(path.relative_to(tmp_path)): path.read_bytes()
                for path in tmp_path.rglob("*") if path.is_file()} == before
        assert marker.is_dir()
    finally:
        os.close(fd)


def test_unprivileged_real_close_refuses_before_any_adoption_effect(prepared, tmp_path):
    if os.geteuid() == 0:
        pytest.skip("requires the actual unprivileged source-test principal")
    retained = tmp_path / "unrelated-live-preimage"
    retained.write_bytes(b"never an installed config")
    before = retained.read_bytes(), retained.stat()
    with pytest.raises(adoption.AdoptionError, match="root_darwin_required"):
        adoption.close_prepared(prepared["request"], owner_device=retained.stat().st_dev,
                                owner_inode=retained.stat().st_ino)
    assert retained.read_bytes() == before[0]
    assert retained.stat() == before[1]


def test_real_stage_owner_failure_retains_only_unselected_stage(prepared, tmp_path, monkeypatch):
    # Exercise the actual failure on this unprivileged Mac, without pretending
    # Root custody or replacing any source/admission predicate with success.
    if os.geteuid() == 0:
        pytest.skip("requires the actual unprivileged source-test principal")
    from contextlib import ExitStack
    request = prepared["request"]
    parent = tmp_path / "configuration"
    parent.mkdir(mode=stat.S_IRWXU)
    marker = parent / "autonomy-transaction.lock"
    monkeypatch.setattr(adoption.control, "CONFIG_ROOT", parent)
    monkeypatch.setattr(adoption.control, "AUTONOMY_TRANSACTION", marker)
    with ExitStack() as stack:
        private = parent / ".macro-adoption-autonomy-fixture"
        with pytest.raises(PermissionError):
            adoption._publish_prepared_generation(private, "fixture", {}, b"candidate", 0, stack,
                                                  lambda: pytest.fail("owner edge proof not reached"))
        stages = list(parent.iterdir())
        assert len(stages) == 1 and stages[0].name.startswith(".macro-adoption-stage-")
        assert stages[0].is_dir() and list(stages[0].iterdir()) == []
        assert stat.S_IMODE(stages[0].stat().st_mode) == stat.S_IRWXU
        assert not private.exists() and not marker.exists()


@pytest.fixture
def filesystem_mechanism(prepared, tmp_path, monkeypatch):
    """Real filesystem mechanisms; only raw privilege observations are synthetic.

    This never calls/qualifies the outer installed-source/host authority. No
    custody predicate is replaced: UID/GID syscall facts are explicit, all real
    mode/ACL/FD/inode/path/bytes and exclusive flock/rename/fsync stay in use.
    """
    from types import SimpleNamespace
    parent = tmp_path.resolve() / "configuration"
    parent.mkdir(mode=stat.S_IRWXU)
    marker = parent / "autonomy-transaction.lock"
    real_lstat, real_fstat = Path.lstat, os.fstat
    real_chown, real_fchown = os.chown, os.fchown
    real_uid, real_gid = os.getuid(), os.getgid()
    def privilege(info):
        values = {key: getattr(info, key) for key in dir(info) if key.startswith("st_")}
        values.update(st_uid=0, st_gid=0)
        return SimpleNamespace(**values)
    class FixtureOS:
        def __getattr__(self, name):
            return getattr(os, name)
        def fstat(self, fd):
            return privilege(real_fstat(fd))
        def chown(self, path, uid, gid):
            assert Path(path).is_relative_to(parent) and (uid, gid) == (0, 0)
            return real_chown(path, real_uid, real_gid)
        def fchown(self, fd, uid, gid):
            assert (uid, gid) == (0, 0)
            return real_fchown(fd, real_uid, real_gid)
    monkeypatch.setattr(Path, "lstat", lambda path, *a, **kw: privilege(real_lstat(path, *a, **kw)))
    monkeypatch.setattr(adoption, "os", FixtureOS())
    monkeypatch.setattr(adoption.control, "os", FixtureOS())
    monkeypatch.setattr(adoption.control, "CONFIG_ROOT", parent)
    monkeypatch.setattr(adoption.control, "AUTONOMY_TRANSACTION", marker)
    files = dict(prepared["archives"], **{"transaction.json": adoption.encoded(prepared["manifest"])})
    live = {}
    for name, raw in {"control": prepared["current_control"], "worker": prepared["current_worker"],
                      "receipt": b"actual absent receipt fixture", "runtime": b"nonexecuting runtime fixture"}.items():
        live[name] = parent / ("live-" + name)
        live[name].write_bytes(raw)
    def proof():
        # Observable preimages for mechanism qualification only. Real outer
        # close_prepared supplies its closed-over source/Runtime/lock proof.
        return live["control"].read_bytes(), live["worker"].read_bytes(), {k: None for k in adoption.RECEIPTS}
    return SimpleNamespace(parent=parent, marker=marker, files=files, live=live,
                           proof=proof, request=prepared["request"], candidate=prepared["candidate_control"])


@pytest.mark.skipif(sys.platform != "darwin", reason="actual Darwin exclusive publication")
@pytest.mark.parametrize("fault", [None, "complete_stage", "between_publications"])
def test_actual_complete_stage_and_exclusive_publication_faults(filesystem_mechanism, monkeypatch, fault):
    from contextlib import ExitStack
    f = filesystem_mechanism
    private = f.parent / ".private-complete"
    expected = dict(f.files, **{"candidate-control.json": f.candidate})
    before = {k: p.read_bytes() for k, p in f.live.items()}
    real_sync = adoption.control._fsync_directory
    synced, calls = [], []
    def sync(path):
        real_sync(path)
        synced.append(Path(path))
    monkeypatch.setattr(adoption.control, "_fsync_directory", sync)
    def edge():
        calls.append(True)
        path = private if private.exists() else next(f.parent.glob(".macro-adoption-stage-*"))
        assert path in synced or f.parent in synced
        assert {p.name: p.read_bytes() for p in path.iterdir()} == expected
        if (fault == "complete_stage" and len(calls) == 1
                or fault == "between_publications" and len(calls) == 2):
            raise OSError("actual owner edge proof refused")
    with ExitStack() as stack:
        if fault:
            with pytest.raises(OSError, match="edge proof refused"):
                adoption._publish_prepared_generation(private, "fixture", f.files, f.candidate, 0, stack, edge)
        else:
            fd = adoption._publish_prepared_generation(private, "fixture", f.files, f.candidate, 0, stack, edge)
            assert (os.fstat(fd).st_dev, os.fstat(fd).st_ino) == (f.marker.stat().st_dev, f.marker.stat().st_ino)
        path = (next(f.parent.glob(".macro-adoption-stage-*")) if fault == "complete_stage"
                else private if fault else f.marker)
        assert {p.name: p.read_bytes() for p in path.iterdir()} == expected
        assert f.marker.exists() is (fault is None)
        assert private.exists() is (fault == "between_publications")
        assert {k: p.read_bytes() for k, p in f.live.items()} == before
    assert len(calls) == (1 if fault == "complete_stage" else 2)


@pytest.mark.skipif(sys.platform != "darwin", reason="actual Darwin exclusive archive")
@pytest.mark.parametrize("fault", [None, "lost_ack", "wrong_token", "foreign_namespace", "live_flock", "corrupt_candidate", "changed_preimage"])
def test_actual_token_close_and_archive_observation(filesystem_mechanism, monkeypatch, fault):
    import fcntl
    f = filesystem_mechanism
    f.marker.mkdir(mode=stat.S_IRWXU)
    for name, raw in dict(f.files, **{"candidate-control.json": f.candidate}).items():
        p = f.marker / name
        p.write_bytes(raw)
        p.chmod((stat.S_IRUSR | stat.S_IRGRP) if name == "candidate-control.json" else stat.S_IRUSR)
    info = f.marker.stat()
    device, inode = info.st_dev, info.st_ino
    archive = adoption._prepared_archive(f.request, device, inode)
    if fault == "foreign_namespace":
        archive.mkdir(mode=stat.S_IRWXU)
    if fault == "corrupt_candidate":
        corrupt = f.marker / "candidate-control.json"
        corrupt.chmod(stat.S_IRUSR | stat.S_IWUSR)
        corrupt.write_bytes(b"unbound candidate")
        corrupt.chmod(stat.S_IRUSR | stat.S_IRGRP)
    if fault == "changed_preimage":
        f.live["control"].write_bytes(b"changed before proof")
    before_live = {k: p.read_bytes() for k, p in f.live.items()}
    before_marker = {p.name: p.read_bytes() for p in f.marker.iterdir()}
    held = None
    if fault == "live_flock":
        held = os.open(f.marker, os.O_RDONLY | os.O_DIRECTORY)
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
    real_sync = adoption.control._fsync_directory
    def sync(path):
        real_sync(path)
        if fault == "lost_ack":
            raise OSError("lost archive acknowledgement")
    monkeypatch.setattr(adoption.control, "_fsync_directory", sync)
    try:
        if fault is None:
            result = adoption._close_prepared_generation(f.request, device, inode, 0, f.proof)
            assert result["closeout"] == "PREPARED_CLOSED"
        else:
            with pytest.raises(adoption.AdoptionError) as error:
                adoption._close_prepared_generation(f.request, device, inode + (1 if fault == "wrong_token" else 0), 0, f.proof)
            assert error.value.effect_unknown is (fault == "lost_ack")
        if fault in {None, "lost_ack"}:
            assert not f.marker.exists()
            assert (archive.stat().st_dev, archive.stat().st_ino) == (device, inode)
            assert {p.name: p.read_bytes() for p in archive.iterdir()} == before_marker
            # Same-token reopening must execute actual directory/file predicates
            # and preimage proof; an archive basename alone is never acceptance.
            observed = adoption._close_prepared_generation(f.request, device, inode, 0, f.proof)
            assert observed["closeout"] == "PREPARED_CLOSED"
            candidate = archive / "candidate-control.json"
            candidate.chmod(stat.S_IRUSR | stat.S_IWUSR)
            candidate.write_bytes(b"corrupt archived candidate")
            candidate.chmod(stat.S_IRUSR | stat.S_IRGRP)
            with pytest.raises(adoption.AdoptionError):
                adoption._close_prepared_generation(f.request, device, inode, 0, f.proof)
        else:
            assert f.marker.is_dir()
            assert {p.name: p.read_bytes() for p in f.marker.iterdir()} == before_marker
        assert {k: p.read_bytes() for k, p in f.live.items()} == before_live
    finally:
        if held is not None:
            os.close(held)


@pytest.mark.skipif(sys.platform != "darwin", reason="actual Darwin inode-bound archive observation")
def test_same_archive_name_with_identical_bytes_never_substitutes_owner(filesystem_mechanism):
    f = filesystem_mechanism
    f.marker.mkdir(mode=stat.S_IRWXU)
    files = dict(f.files, **{"candidate-control.json": f.candidate})
    for name, raw in files.items():
        p = f.marker / name
        p.write_bytes(raw)
        p.chmod((stat.S_IRUSR | stat.S_IRGRP) if name == "candidate-control.json" else stat.S_IRUSR)
    info = f.marker.stat()
    archive = adoption._prepared_archive(f.request, info.st_dev, info.st_ino)
    original = f.parent / "preserved-original-owner"
    f.marker.rename(original)
    archive.mkdir(mode=stat.S_IRWXU)
    for name, raw in files.items():
        p = archive / name
        p.write_bytes(raw)
        p.chmod((stat.S_IRUSR | stat.S_IRGRP) if name == "candidate-control.json" else stat.S_IRUSR)
    before = {k: p.read_bytes() for k, p in f.live.items()}
    with pytest.raises(adoption.AdoptionError, match="prepared_owner_custody_invalid"):
        adoption._close_prepared_generation(f.request, info.st_dev, info.st_ino, 0, f.proof)
    assert {p.name: p.read_bytes() for p in original.iterdir()} == files
    assert {p.name: p.read_bytes() for p in archive.iterdir()} == files
    assert {k: p.read_bytes() for k, p in f.live.items()} == before

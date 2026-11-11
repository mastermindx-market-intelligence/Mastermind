"""Panel repair round (on c89427598): R1–R3, R5-shell LOWs.

Written to the panel's spec (SCORE.md), not to the implementation: against
the pre-repair code each test FAILS on the behaviour the panel named; the fix
commit turns it green. Pure-python tests here (no launchd, no network, no
real port); the launchd-shaped panel tests live in
tests/test_mmos_team_server_ops.py beside the harness they need.
"""
import hashlib
import importlib.util
import json
import os
import subprocess
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

REPO = Path(__file__).resolve().parent.parent
TOOL = REPO / "tools" / "mmos_team_server" / "node_install.py"
RUNNER = REPO / "tools" / "mmos_team_server" / "server_runner.sh"
PY = "/opt/homebrew/bin/python3.12"
LABEL = "com.mastermind.t3-team-panel"

_loader = importlib.util.spec_from_file_location("node_install_panel", TOOL)
node_install = importlib.util.module_from_spec(_loader)
_loader.loader.exec_module(node_install)

PREFIX = f"node-v{node_install.VERSION}-darwin-arm64"


def _digest_file(rel, body: bytes):
    return {"path": rel, "bytes": len(body),
            "sha256": hashlib.sha256(body).hexdigest()}


def packed_runtime(tmp_path, tamper=None, extra_files=(), omit_digests=False):
    """A receipt-consistent synthetic root: pinned node tree + packed server
    dist + file-digests.json exactly as pack_server.mjs leaves them.

    tamper: (relpath, new_bytes) applied AFTER the digests are recorded.
    extra_files: files planted under dist/ that file-digests.json does NOT
    record (R1's unrecorded-file refusal).
    """
    root = tmp_path / "server"
    root.mkdir(mode=0o700)
    install_dir = root / "runtime" / PREFIX
    (install_dir / "bin").mkdir(parents=True)
    node = install_dir / "bin" / "node"
    node.write_text("#!/bin/sh\n")
    node.chmod(0o700)
    build = root / "runtime" / "packed" / "dist"
    bodies = {name: f"body of {name}\n".encode() for name in node_install.REQUIRED_DIST_FILES}
    bodies["bin.mjs"] = b"// packed server entrypoint\n"
    recorded = []
    for rel, body in bodies.items():
        target = build / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(body)
        recorded.append(_digest_file(rel, body))
    if tamper:
        rel, new_bytes = tamper
        (build / rel).write_bytes(new_bytes)
    for rel, body in extra_files:
        target = build / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(body)
    node_receipt = {
        "schemaVersion": node_install.SCHEMA_VERSION,
        "kind": "official-nodejs-install",
        "version": "v" + node_install.VERSION,
        "architecture": "arm64", "platform": "darwin",
        "nodePath": str(node), "installDir": str(install_dir),
        "archiveSha256": node_install.OFFICIAL_SHA256,
        "treeSha256": node_install.tree_sha256(install_dir),
    }
    # the pack writes this INTO dist after hashing — never digest-recorded
    (build / "BUILD_RECEIPT.json").write_text(
        json.dumps({"schemaVersion": 2, "kind": "t3-packed-server-runtime"}) + "\n")
    payload = json.dumps(node_receipt, indent=2) + "\n"
    (install_dir / "INSTALL_RECEIPT.json").write_text(payload)
    (root / "config").mkdir()
    (root / "config" / "node-runtime.json").write_text(payload)
    (root / "config" / "server-runtime.json").write_text(json.dumps({
        "schemaVersion": node_install.SCHEMA_VERSION,
        "serverBin": str(build / "bin.mjs"),
        "buildDir": str(build),
    }))
    if not omit_digests:
        (root / "runtime" / "packed" / "file-digests.json").write_text(
            json.dumps(recorded, indent=2) + "\n")
    return root, node, build


# --------------------------------------------------------------------------
# R1 — the packed SERVER tree (the code that boots) must be digest-verified
# --------------------------------------------------------------------------

class TestR1ServerTreeDigest:
    def test_r1_stat_cache_hits_are_still_tripwired(self, tmp_path):
        # Boot-cost fix on the R1 gate: a real packed tree is ~4500 files /
        # 344 MB (~15 s per full hash, three passes per first boot), so
        # after a file's digest matches the record once its
        # (size, mtime_ns, ctime_ns) triple is cached beside the record and
        # later verifies skip re-hashing it. The cache must not open a hole:
        # an in-place SAME-SIZE edit with mtime restored to the recorded
        # nanoseconds still fails — ctime is kernel-set and cannot be
        # restored without root.
        root, _, build = packed_runtime(tmp_path)
        want = len(node_install.REQUIRED_DIST_FILES)
        assert node_install.verify_packed_server(str(build)) == want
        cache_path = build.parent / "verify-stat-cache.json"
        assert cache_path.exists()
        # second pass rides the cache and still verifies the whole set
        assert node_install.verify_packed_server(str(build)) == want
        target = build / "bin.mjs"
        before = os.stat(target)
        body = bytearray(target.read_bytes())
        body[0] ^= 0x20
        target.write_bytes(bytes(body))
        os.utime(target, ns=(before.st_atime_ns, before.st_mtime_ns))
        with pytest.raises(node_install.InstallError, match="digest"):
            node_install.verify_packed_server(str(build))

    def test_r1_resolve_refuses_tampered_dist_bin(self, tmp_path):
        # Panel R1 (HIGH): flip one byte in runtime/<rel>/dist/bin.mjs after
        # pack — resolve must refuse; today it returns the path happily.
        root, _, _ = packed_runtime(tmp_path, tamper=("bin.mjs", b"// tampered\n"))
        with pytest.raises(node_install.InstallError, match="server"):
            node_install.runtime_paths(str(root))

    def test_r1_resolve_refuses_missing_digest_file(self, tmp_path):
        # file-digests.json absent (deleted by a writer): the server tree is
        # unverifiable and must not resolve.
        root, _, _ = packed_runtime(tmp_path, omit_digests=True)
        with pytest.raises(node_install.InstallError, match="file-digests"):
            node_install.runtime_paths(str(root))

    def test_r1_resolve_refuses_unrecorded_planted_file(self, tmp_path):
        # A file planted under dist/ that the pack never recorded refuses:
        # verifying only the recorded set would bless a planted payload.
        root, _, _ = packed_runtime(
            tmp_path, extra_files=[("node_modules/evil.js", b"module.exports=1\n")])
        with pytest.raises(node_install.InstallError, match="unrecorded"):
            node_install.runtime_paths(str(root))

    def test_r1_doctor_verifies_and_names_both_trees(self, tmp_path, capsys):
        # Doctor's line must say exactly what was verified: the Node tree AND
        # the packed server tree, with the verified file count.
        root, _, _ = packed_runtime(tmp_path)
        with patch.object(node_install.subprocess, "run",
                          return_value=Mock(returncode=1, stdout="")):
            code = node_install.doctor(str(root), LABEL)
        out = capsys.readouterr().out
        assert code == 1  # label not loaded (stubbed launchd) — but rows print
        assert "treeVerified=node+server" in out
        assert f"serverTreeFiles={len(node_install.REQUIRED_DIST_FILES)}" in out

    def test_r1_doctor_fails_on_tampered_server_tree(self, tmp_path, capsys):
        root, _, _ = packed_runtime(tmp_path, tamper=("bin.mjs", b"// tampered\n"))
        with patch.object(node_install.subprocess, "run",
                          return_value=Mock(returncode=1, stdout="")):
            code = node_install.doctor(str(root), LABEL)
        out = capsys.readouterr().out
        assert code == 1
        assert "treeVerified=node+server" not in out
        errors = [line for line in out.splitlines()
                  if line.startswith("doctor_error=")]
        # the error must name the server tree itself, not an unrelated row
        assert errors and ("server tree" in errors[0] or "digest" in errors[0]), out

    def test_r1_runner_refuses_to_boot_tampered_server_tree(self, tmp_path):
        # The runner boots whatever it resolves: with a tampered dist it must
        # refuse in one line (exit 69), never exec the changed bytes.
        root, _, _ = packed_runtime(tmp_path, tamper=("bin.mjs", b"// tampered\n"))
        (root / "config" / "python3-path").write_text(PY + "\n")
        (root / "run").mkdir()
        (root / "run" / "port").write_text("50899\n")
        (root / "fabric.env").write_text("X=1\n")
        os.chmod(root / "fabric.env", 0o600)
        shutil_copy_runner(root)
        proc = subprocess.run(["/bin/sh", str(root / "bin" / "server_runner.sh"),
                               str(root)], capture_output=True, text=True, timeout=90)
        assert proc.returncode == 69
        assert "server_runner:" in proc.stderr
        assert "server" in proc.stderr and "digest" in proc.stderr
        assert "Traceback" not in proc.stderr


def shutil_copy_runner(root):
    import shutil
    (root / "bin").mkdir(exist_ok=True)
    shutil.copy(REPO / "tools" / "mmos_team_server" / "server_runner.sh",
                root / "bin" / "server_runner.sh")
    shutil.copy(TOOL, root / "bin" / "node_install.py")
    os.chmod(root / "bin" / "server_runner.sh", 0o700)
    os.chmod(root / "bin" / "node_install.py", 0o700)


# --------------------------------------------------------------------------
# R2 — the runner must not boot a config/server-bin that contradicts the
# receipts (a writer of that one config file redirects every later boot)
# --------------------------------------------------------------------------

class TestR2RunnerServerBin:
    def test_r2_runner_refuses_server_bin_contradicting_receipts(self, tmp_path):
        # Both receipts present (packed mode) but config/server-bin names a
        # different executable: boot must refuse naming both paths, not exec
        # the writer's choice.
        root, _, _ = packed_runtime(tmp_path)
        (root / "config" / "python3-path").write_text(PY + "\n")
        (root / "run").mkdir()
        (root / "run" / "port").write_text("50899\n")
        (root / "fabric.env").write_text("X=1\n")
        os.chmod(root / "fabric.env", 0o600)
        impostor = tmp_path / "impostor"
        impostor.write_text("#!/bin/sh\nexit 0\n")
        os.chmod(impostor, 0o755)
        (root / "config" / "server-bin").write_text(str(impostor) + "\n")
        shutil_copy_runner(root)
        proc = subprocess.run(["/bin/sh", str(root / "bin" / "server_runner.sh"),
                               str(root)], capture_output=True, text=True, timeout=90)
        assert proc.returncode == 69
        assert str(impostor) in proc.stderr
        assert "Going back" in proc.stderr  # names the designed rollback

    def test_r2_rollback_server_bin_boots_without_receipts(self, tmp_path):
        # Keep the rollback working: with the receipts moved aside (runbook
        # 'Going back'), the operator-named config/server-bin still boots.
        root, _, _ = packed_runtime(tmp_path)
        (root / "config" / "python3-path").write_text(PY + "\n")
        (root / "run").mkdir()
        (root / "run" / "port").write_text("50899\n")
        (root / "fabric.env").write_text("X=1\n")
        os.chmod(root / "fabric.env", 0o600)
        for name in ("server-runtime.json", "node-runtime.json"):
            (root / "config" / name).rename(root / "config" / (name + ".migrated"))
        legacy = tmp_path / "legacy-server"
        legacy.write_text("#!/bin/sh\necho legacy-booted\nexec /bin/sleep 5\n")
        os.chmod(legacy, 0o755)
        (root / "config" / "server-bin").write_text(str(legacy) + "\n")
        shutil_copy_runner(root)
        proc = subprocess.run(["/bin/sh", str(root / "bin" / "server_runner.sh"),
                               str(root)], capture_output=True, text=True, timeout=90)
        assert "legacy-booted" in proc.stdout  # it really exec'd the named binary


# --------------------------------------------------------------------------
# R3 — buildDir must be the runtime release folder, not any in-root */dist
# --------------------------------------------------------------------------

class TestR3BuildDirConstraint:
    def test_r3_resolve_refuses_build_dir_outside_runtime(self, tmp_path):
        # A writer of config/server-runtime.json alone points serverBin at
        # any in-root */dist (every stated check passes). buildDir must be
        # exactly <root>/runtime/<release-ID>/dist.
        root, _, _ = packed_runtime(tmp_path)
        sneaky = root / "home" / "userdata" / "dist"
        sneaky.mkdir(parents=True)
        for name in node_install.REQUIRED_DIST_FILES + ("bin.mjs",):
            target = sneaky / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"x")
        sneaky_digests = [_digest_file(name, b"x")
                          for name in node_install.REQUIRED_DIST_FILES + ("bin.mjs",)]
        (root / "home" / "userdata" / "file-digests.json").write_text(
            json.dumps(sneaky_digests) + "\n")
        receipt = json.loads((root / "config" / "server-runtime.json").read_text())
        receipt["buildDir"] = str(sneaky)
        receipt["serverBin"] = str(sneaky / "bin.mjs")
        (root / "config" / "server-runtime.json").write_text(json.dumps(receipt))
        with pytest.raises(node_install.InstallError, match="runtime"):
            node_install.runtime_paths(str(root))


# --------------------------------------------------------------------------
# Repair round 3 — A: the pinned Node tree is re-hashed on EVERY resolve
# (twice per boot, ~199 MB each); that, not the (cached) server tree, is
# what kept a launchd start in state U for minutes at load 25-107.
# --------------------------------------------------------------------------

class TestA1NodeTreeStatCache:
    def test_a1_node_tree_stat_cache_written_and_tripwired(self, tmp_path):
        # After one verified digest the node tree's (mode,size,mtime_ns,
        # ctime_ns) triples are cached beside runtime/ and later verifies
        # skip re-hashing; any change falls back to a full digest. Same
        # tripwire semantics as the server-tree cache, proved the same way:
        # a same-size in-place edit with mtime restored still refuses.
        root, node, _ = packed_runtime(tmp_path)
        node_install.runtime_paths(str(root))          # full pass, writes cache
        cache = root / "runtime" / "node-tree-stat-cache.json"
        assert cache.exists()
        node_install.runtime_paths(str(root))          # cached pass, still verifies
        before = os.stat(node)
        body = bytearray(node.read_bytes())
        body[0] ^= 0x01
        node.write_bytes(bytes(body))
        os.utime(node, ns=(before.st_atime_ns, before.st_mtime_ns))
        with pytest.raises(node_install.InstallError, match="Node tree"):
            node_install.runtime_paths(str(root))
        cache.unlink()                                  # a deleted cache = slow, not wrong
        with pytest.raises(node_install.InstallError, match="Node tree"):
            node_install.runtime_paths(str(root))


# --------------------------------------------------------------------------
# Repair round 3 — C: a slow or empty lsof must never relabel our own
# listener as "foreign". Unknown is unknown, with one retry.
# --------------------------------------------------------------------------

class TestC1AttributionUnknown:
    def test_c1_empty_lsof_is_unknown_with_retry_not_foreign(self):
        # First lookup returns nothing (lsof slow/failed under load), the
        # retry finds the job's own pid: ours.
        calls = {"n": 0}

        def flaky(_port):
            calls["n"] += 1
            return [] if calls["n"] == 1 else [os.getpid()]

        with patch.object(node_install, "_listener_pids", side_effect=flaky):
            assert node_install.answering_process(50817, os.getpid()) == "ours"
        assert calls["n"] == 2

    def test_c1_persistent_empty_lsof_reports_unknown_not_foreign(self):
        # Nothing identifiable at all: the verdict must say unknown (with the
        # probe named), never claim an impostor was found.
        with patch.object(node_install, "_listener_pids", return_value=[]):
            verdict = node_install.answering_process(50817, os.getpid())
        assert verdict.startswith("unknown"), verdict
        assert "foreign" not in verdict

    def test_c1_a_real_foreign_listener_is_still_foreign(self):
        # The impostor finding survives: listener pids exist, none is ours.
        with patch.object(node_install, "_listener_pids", return_value=[999999]):
            verdict = node_install.answering_process(50817, os.getpid())
        assert verdict.startswith("foreign"), verdict


# --------------------------------------------------------------------------
# Repair round 3 — follow-up 3: doctor --full forces a re-hash past the
# stat caches; follow-up 7: doctor --port and a named recovery when
# config/server-bin is unreadable.
# --------------------------------------------------------------------------

class TestFUDoctorFullAndPort:
    def test_fu3_doctor_full_rehashes_past_a_poisoned_stat_cache(self, tmp_path, capsys):
        # The cache is a performance artifact a same-user writer can forge
        # (recorded in the limits). doctor --full ignores it and re-hashes:
        # a tampered file whose stat triple was forged into the cache is
        # still refused.
        root, _, build = packed_runtime(tmp_path, tamper=("bin.mjs", b"// tampered\n"))
        cache_path = build.parent / "verify-stat-cache.json"
        digest_path = build.parent / "file-digests.json"
        recorded = {e["path"]: e for e in json.loads(digest_path.read_text())}
        forged = {}
        for rel, entry in recorded.items():
            target = build / rel
            st = os.stat(target)
            forged[rel] = [st.st_size, st.st_mtime_ns, st.st_ctime_ns]
        # fix the forged entry for the tampered file (recorded bytes, real stat)
        cache_path.write_text(json.dumps(forged))
        with patch.object(node_install.subprocess, "run",
                          return_value=Mock(returncode=1, stdout="")):
            code = node_install.doctor(str(root), LABEL, verify_tree="full")
        out = capsys.readouterr().out
        assert code == 1
        errors = [line for line in out.splitlines() if line.startswith("doctor_error=")]
        assert errors and ("digest" in errors[0] or "server tree" in errors[0]), out

    def test_fu7_doctor_port_flag_reaches_the_recovery_line(self, tmp_path, capsys):
        # run/port unreadable: doctor --port N probes N and prints a
        # runnable recovery carrying --port N; without the flag the error
        # names the flag instead of inventing a port.
        root, _, _ = packed_runtime(tmp_path)
        (root / "run").mkdir(exist_ok=True)
        (root / "run" / "port").unlink(missing_ok=True)
        with patch.object(node_install.subprocess, "run",
                          return_value=Mock(returncode=1, stdout="")):
            code = node_install.doctor(str(root), LABEL, port="50899")
        out = capsys.readouterr().out
        assert code == 1
        assert "port=50899" in out
        line = next(l for l in out.splitlines()
                    if l.startswith("doctor_error=label not loaded"))
        assert "--port 50899" in line
        with patch.object(node_install.subprocess, "run",
                          return_value=Mock(returncode=1, stdout="")):
            node_install.doctor(str(root), LABEL)
        out2 = capsys.readouterr().out
        line2 = next(l for l in out2.splitlines()
                     if l.startswith("doctor_error=label not loaded"))
        assert "--port" in line2 and "pass --port" in line2

    def test_fu7_unreadable_server_bin_names_its_recovery(self, tmp_path, capsys):
        # Rollback mode whose config/server-bin cannot be read: the error
        # names the recovery (Going back / step 3), not a bare exception.
        root, _, _ = packed_runtime(tmp_path)
        (root / "config" / "server-runtime.json").unlink()   # force rollback mode
        legacy = tmp_path / "legacy-server"
        legacy.write_text("#!/bin/sh\n")
        (root / "config" / "server-bin").write_text(str(legacy) + "\n")
        os.chmod(root / "config" / "server-bin", 0o000)
        with patch.object(node_install.subprocess, "run",
                          return_value=Mock(returncode=1, stdout="")):
            code = node_install.doctor(str(root), LABEL)
        out = capsys.readouterr().out
        assert code == 1
        errors = [line for line in out.splitlines() if line.startswith("doctor_error=")]
        assert errors and "server-bin" in errors[0] and "recovery" in errors[0], out

    def test_fu2_doctor_launchagents_dir_seam_is_gated(self, tmp_path, capsys,
                                                       monkeypatch):
        # FU2: doctor hardcoded ~/Library/LaunchAgents for the expected plist;
        # it now honors TEAM_SERVER_LAUNCHAGENTS_DIR — but only as a gated
        # test seam. Set without MMOS_TEST_SEAMS=1 it refuses instead of
        # quietly judging another directory "the" plist location.
        root, _, _ = packed_runtime(tmp_path)
        monkeypatch.setenv("TEAM_SERVER_LAUNCHAGENTS_DIR", "/tmp/t6-elsewhere")
        monkeypatch.delenv("MMOS_TEST_SEAMS", raising=False)
        with patch.object(node_install.subprocess, "run",
                          return_value=Mock(returncode=1, stdout="")):
            code = node_install.doctor(str(root), LABEL)
        out = capsys.readouterr().out
        assert code == 1
        errors = [l for l in out.splitlines() if l.startswith("doctor_error=")]
        assert errors and "TEAM_SERVER_LAUNCHAGENTS_DIR" in errors[0], out
        # gated open: the seam is honored and doctor proceeds normally
        monkeypatch.setenv("MMOS_TEST_SEAMS", "1")
        with patch.object(node_install.subprocess, "run",
                          return_value=Mock(returncode=1, stdout="")):
            node_install.doctor(str(root), LABEL)
        out2 = capsys.readouterr().out
        assert "doctor_error=label not loaded" in out2, out2

    def test_fu5_runner_exit78_names_runbook_step_3(self, tmp_path):
        # FU5: the exit-78 recovery said "re-run team_server.sh install",
        # which never writes config/python3-path — runbook step 3
        # (node_install.py install) does. The message must name step 3.
        root, _, _ = packed_runtime(tmp_path)
        (root / "run").mkdir()
        (root / "run" / "port").write_text("50899\n")
        (root / "fabric.env").write_text("X=1\n")
        os.chmod(root / "fabric.env", 0o600)
        (root / "config" / "python3-path").write_text("/nonexistent/python3\n")
        shutil_copy_runner(root)
        proc = subprocess.run(["/bin/sh", str(root / "bin" / "server_runner.sh"),
                               str(root)], capture_output=True, text=True,
                              timeout=30)
        assert proc.returncode == 78
        assert "step 3" in proc.stderr, proc.stderr
        assert "team_server.sh install" not in proc.stderr

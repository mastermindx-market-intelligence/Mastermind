"""Actual native launch configuration; no provider or OS sandbox inference."""
from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from control_plane.worker_execution_contract import BinaryAttestation, WorkerLaunchSpec
from integrations.acp_worker.native import AcpNativeProcessError, AcpNativeProcessOwner, AcpNativeProfile


PROBE = """
import json, os, pathlib, sys
print(json.dumps({
    'cwd': os.getcwd(), 'home': os.environ.get('HOME'),
    'tmp': os.environ.get('TMPDIR'), 'path': os.environ.get('PATH'),
    'keys': sorted(os.environ),
    'config': [p.read_text() for p in
        (pathlib.Path('.env'), pathlib.Path(os.environ['HOME']) / '.env') if p.exists()],
}), flush=True)
sys.stdin.read()
"""


@pytest.fixture
def launch(tmp_path: Path):
    root = tmp_path.resolve()
    workspace, run_dir = root / "workspace", root / "run"
    workspace.mkdir(mode=0o700)
    run_dir.mkdir(mode=0o700)
    (run_dir / "input").mkdir(mode=0o700)
    # A real tracked startup-config poison, kept clean for the real git owner.
    (workspace / ".env").write_text("WORKSPACE_CONFIG_MUST_NOT_LOAD")
    env = {"PATH": os.defpath, "HOME": str(root), "GIT_CONFIG_GLOBAL": os.devnull,
           "GIT_CONFIG_NOSYSTEM": "1", "GIT_TERMINAL_PROMPT": "0"}
    def git(*args):
        return subprocess.run(["git", *args], cwd=workspace, env=env, check=True,
                              capture_output=True, text=True, timeout=10).stdout.strip()
    git("init", "--template=", "-q")
    git("add", ".env")
    git("-c", "user.name=ACP Startup", "-c", "user.email=startup@example.invalid",
        "-c", "commit.gpgsign=false", "commit", "-qm", "config poison")
    schema = run_dir / "input/result.schema.json"
    schema.write_text('{"type":"object"}')
    binary = Path(sys.executable).resolve(strict=True)
    info = binary.stat()
    attestation = BinaryAttestation(
        str(binary), str(binary), sys.version.split()[0], hashlib.sha256(binary.read_bytes()).hexdigest(),
        None, info.st_size, info.st_dev, info.st_ino, info.st_mode & 0o7777,
        info.st_uid, info.st_gid, info.st_mtime_ns,
    )
    probe = root / "probe.py"
    probe.write_text(PROBE)
    profile = AcpNativeProfile(
        "startup-probe", attestation, (str(binary), "-B", str(probe)),
        private_startup=True, allowed_environment_keys=("PATH", "LANG", "MMX_TEST_SECRET"),
    )
    spec = WorkerLaunchSpec(
        "startup-run", "startup-job", "startup-worker", workspace, run_dir,
        "Launch configuration probe only.", schema, authorities=("READ",), model="fixture",
        timeout_seconds=5, cancel_grace_seconds=2, expected_base_sha=git("rev-parse", "HEAD"),
        expected_worker_uid=os.geteuid(), expected_worker_gid=os.getegid(),
    )
    return profile, spec


def test_actual_child_has_private_startup_and_no_ambient_configuration(launch, tmp_path, monkeypatch):
    profile, spec = launch
    ambient = tmp_path / "ambient-home"
    ambient.mkdir()
    (ambient / ".env").write_text("AMBIENT_CONFIG_MUST_NOT_LOAD")
    monkeypatch.setenv("HOME", str(ambient))
    monkeypatch.setenv("TMPDIR", str(ambient))
    monkeypatch.setenv("NODE_OPTIONS", "AMBIENT_INJECTION")
    monkeypatch.setenv("PATH", "/nonexistent/ambient/path")
    loaded = {"PATH": os.defpath, "LANG": "C.UTF-8", "MMX_TEST_SECRET": "fixture-secret-sentinel"}
    owner = AcpNativeProcessOwner(profile, environment_loader=lambda: loaded)
    async def exercise():
        resources = await owner.open_run(spec)
        try:
            observed = json.loads(await asyncio.wait_for(resources.reader.readline(), timeout=3))
        finally:
            completion = await resources.finish(None)
        assert completion.settled and completion.exit_code == 0
        assert owner._active is None
        assert owner._runs[spec.run_id].stdout_task.done()
        assert owner._runs[spec.run_id].stderr_task.done()
        assert not owner._identity_matches(resources.process_ref)
        root = spec.run_dir / "startup"
        # macOS framework Python can add this OS text-encoding key after exec.
        # It is not part of the owner's submitted environment or credential set.
        if sys.platform == "darwin" and "__CF_USER_TEXT_ENCODING" in observed["keys"]:
            observed["keys"].remove("__CF_USER_TEXT_ENCODING")
        assert observed == {
            "cwd": str(root), "home": str(root / "home"), "tmp": str(root / "tmp"),
            "path": os.defpath, "keys": sorted((*loaded, "HOME", "TMPDIR")), "config": [],
        }
        proof = resources.launch_attestation["private_startup"]
        assert resources.launch_attestation["environment_keys"] == sorted((*loaded, "HOME", "TMPDIR"))
        assert proof["os_sandbox_proven"] is False
        for name, path in (("cwd", root), ("home", root / "home"), ("tmp", root / "tmp")):
            info = path.stat()
            assert info.st_mode & 0o777 == 0o700
            assert proof["directories"][name]["inode"] == info.st_ino
        assert "fixture-secret-sentinel" not in json.dumps(resources.launch_attestation)
        assert "HOME" not in loaded and "TMPDIR" not in loaded  # loader map stays untouched
    asyncio.run(exercise())


@pytest.mark.parametrize("key", ["HOME", "TMPDIR", "NODE_OPTIONS", "PYTHONPATH"])
def test_unadmitted_loader_key_refuses_before_spawn(launch, monkeypatch, key):
    profile, spec = launch
    async def forbidden_spawn(*args, **kwargs):
        pytest.fail("unadmitted environment reached native spawn")
    monkeypatch.setattr(asyncio, "create_subprocess_exec", forbidden_spawn)
    owner = AcpNativeProcessOwner(profile, environment_loader=lambda: {key: "injected"})
    with pytest.raises(AcpNativeProcessError, match="environment exceeds"):
        asyncio.run(owner.open_run(spec))
    assert owner._active is None and not owner._runs
    assert not (spec.run_dir / "startup").exists()
    assert not (spec.run_dir / "logs").exists()


@pytest.mark.parametrize("symlink", [False, True])
def test_existing_startup_is_never_reused(launch, tmp_path, monkeypatch, symlink):
    profile, spec = launch
    startup = spec.run_dir / "startup"
    target = tmp_path / "foreign-startup"
    target.mkdir(mode=0o700)
    sentinel = target / "keep"
    sentinel.write_text("untouched")
    if symlink:
        startup.symlink_to(target, target_is_directory=True)
    else:
        startup.mkdir(mode=0o700)
    async def forbidden_spawn(*args, **kwargs):
        pytest.fail("reused startup reached native spawn")
    monkeypatch.setattr(asyncio, "create_subprocess_exec", forbidden_spawn)
    owner = AcpNativeProcessOwner(profile, environment_loader=lambda: {})
    with pytest.raises(AcpNativeProcessError, match="not fresh"):
        asyncio.run(owner.open_run(spec))
    assert sentinel.read_text() == "untouched"
    assert list(target.iterdir()) == [sentinel]
    assert owner._active is None and not owner._runs


@pytest.mark.parametrize("changes", [
    {"private_startup": False}, {"private_startup": 1}, {"allowed_environment_keys": None},
    {"allowed_environment_keys": ("PATH", "PATH")}, {"allowed_environment_keys": ("HOME",)},
    {"allowed_environment_keys": ("TMPDIR",)}, {"allowed_environment_keys": ("BAD=KEY",)},
    {"allowed_environment_keys": "PATH"}, {"allowed_environment_keys": (["PATH"],)},
])
def test_invalid_fixed_startup_profile_refused(launch, changes):
    with pytest.raises(ValueError):
        dataclasses.replace(launch[0], **changes)


def test_empty_ceiling_and_legacy_profile_remain_explicit(launch):
    profile, _ = launch
    assert dataclasses.replace(profile, allowed_environment_keys=()).private_startup
    legacy = dataclasses.replace(profile, private_startup=False, allowed_environment_keys=None)
    assert legacy.allowed_environment_keys is None


@pytest.mark.parametrize("failure", ["stderr", "result", "spawn"])
def test_failed_open_retains_evidence_but_settles_capture_descriptors(launch, monkeypatch, failure):
    profile, spec = launch
    opened, closed = [], []
    from integrations.acp_worker import native
    create, close = native._create_private_file, os.close
    def track_create(path):
        if ((failure == "stderr" and path.name == "acp-stderr.log")
                or (failure == "result" and path.name == "result.json")):
            raise OSError("fixture open failure")
        fd = create(path)
        opened.append(fd)
        return fd
    def track_close(fd):
        closed.append(fd)
        close(fd)
    async def failed_spawn(*args, **kwargs):
        raise OSError("fixture open failure")
    monkeypatch.setattr(native, "_create_private_file", track_create)
    monkeypatch.setattr(os, "close", track_close)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", failed_spawn)
    owner = AcpNativeProcessOwner(profile, environment_loader=lambda: {})
    with pytest.raises(OSError, match="fixture open failure"):
        asyncio.run(owner.open_run(spec))
    assert set(opened).issubset(closed)
    assert len(opened) == {"stderr": 1, "result": 2, "spawn": 3}[failure]
    assert owner._active is None and not owner._runs
    # Failed-run artifacts are retained for reconciliation, never silently
    # deleted to authorize a retry. The adapter also quarantines open failure.
    startup = spec.run_dir / "startup"
    identity = startup.stat().st_ino
    with pytest.raises(AcpNativeProcessError, match="not fresh"):
        asyncio.run(owner.open_run(spec))
    assert startup.stat().st_ino == identity


def test_owner_added_environment_counts_toward_existing_limit(launch, monkeypatch):
    profile, spec = launch
    keys = tuple(f"FIXTURE_{i}" for i in range(128))
    profile = dataclasses.replace(profile, allowed_environment_keys=keys)
    async def forbidden_spawn(*args, **kwargs):
        pytest.fail("oversized final environment reached native spawn")
    monkeypatch.setattr(asyncio, "create_subprocess_exec", forbidden_spawn)
    owner = AcpNativeProcessOwner(profile, environment_loader=lambda: dict.fromkeys(keys, "x"))
    with pytest.raises(AcpNativeProcessError, match="environment is invalid"):
        asyncio.run(owner.open_run(spec))
    assert not (spec.run_dir / "startup").exists()

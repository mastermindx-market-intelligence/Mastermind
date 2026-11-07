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
    from integrations.acp_worker import native, process_resource
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
    monkeypatch.setattr(process_resource, "_create_private_file", track_create)
    monkeypatch.setattr(os, "close", track_close)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", failed_spawn)
    owner = AcpNativeProcessOwner(profile, environment_loader=lambda: {})
    with pytest.raises(OSError, match="fixture open failure"):
        asyncio.run(owner.open_run(spec))
    assert set(opened).issubset(closed)
    assert len(opened) == {"stderr": 2, "result": 0, "spawn": 3}[failure]
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


def test_trusted_launch_argv_builder_controls_effective_argv_and_attestation(launch):
    profile, spec = launch
    probe = Path(profile.argv[2])
    probe.write_text(
        "import json,sys; print(json.dumps({'argv':sys.argv[1:]}), flush=True); sys.stdin.read()\n"
    )
    calls = []

    def builder(bound_spec, workspace, run_dir):
        calls.append((bound_spec, workspace, run_dir))
        return (*profile.argv, "builder-marker")

    owner = AcpNativeProcessOwner(
        profile,
        environment_loader=lambda: {},
        launch_argv_builder=builder,
    )

    async def exercise():
        resources = await owner.open_run(spec)
        observed = json.loads(await asyncio.wait_for(resources.reader.readline(), timeout=3))
        completion = await resources.finish(None)
        return resources, observed, completion

    resources, observed, completion = asyncio.run(exercise())
    assert observed["argv"] == ["builder-marker"]
    assert calls == [(spec, spec.workspace_path.resolve(), spec.run_dir.resolve())]
    rendered = (*profile.argv, "builder-marker")
    assert resources.launch_attestation["argv_sha256"] == hashlib.sha256(
        json.dumps(rendered, separators=(",", ":"), ensure_ascii=True).encode()
    ).hexdigest()
    assert resources.launch_attestation["rendered_argv"] == list(rendered)
    assert completion.settled


@pytest.mark.parametrize(
    "rendered",
    [
        ("/bin/false",),
        (),
        ("bad\x00binary",),
    ],
)
def test_launch_argv_builder_refuses_unattested_or_invalid_exec_before_spawn(
    launch, monkeypatch, rendered
):
    profile, spec = launch
    calls = []

    async def forbidden_spawn(*args, **kwargs):
        calls.append((args, kwargs))
        pytest.fail("invalid rendered argv reached native spawn")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", forbidden_spawn)
    owner = AcpNativeProcessOwner(
        profile,
        environment_loader=lambda: {},
        launch_argv_builder=lambda _spec, _workspace, _run_dir: rendered,
    )
    with pytest.raises(AcpNativeProcessError, match="launch argv"):
        asyncio.run(owner.open_run(spec))
    assert calls == []


def test_completed_native_child_gets_existing_budget_for_cooperative_teardown(launch, tmp_path):
    profile, spec = launch
    probe = tmp_path / "cooperative-teardown.py"
    probe.write_text(
        "import sys,time\n"
        "print('READY', flush=True)\n"
        "sys.stdin.read()\n"
        "time.sleep(0.45)\n"
        "print('CLEAN_SHUTDOWN', flush=True)\n"
    )
    profile = dataclasses.replace(profile, argv=(profile.argv[0], "-B", str(probe)))
    owner = AcpNativeProcessOwner(profile, environment_loader=lambda: {})

    async def run():
        resources = await owner.open_run(spec)
        assert await asyncio.wait_for(resources.reader.readline(), 3) == b"READY\n"
        completion = await asyncio.wait_for(resources.finish(None), spec.cancel_grace_seconds)
        assert completion.settled
        assert completion.exit_code == 0
        assert completion.cancellation is None
        assert b"CLEAN_SHUTDOWN" in Path(resources.process_ref.stdout_path).read_bytes()
        assert owner._active is None and not owner._identity_matches(resources.process_ref)

    asyncio.run(run())


@pytest.mark.parametrize("signal_refused", [False, True])
def test_rejected_launch_group_never_becomes_a_signal_target(launch, tmp_path, monkeypatch, signal_refused):
    from types import SimpleNamespace
    from integrations.acp_worker import process_resource as resource
    profile, _spec = launch
    killed, descriptors = [], []
    create = resource._create_private_file
    def capture_file(path):
        fd = create(path)
        descriptors.append(fd)
        return fd
    class Child:
        pid = 123456
        returncode = None
        stdin = stdout = stderr = object()
        def kill(self):
            killed.append(self.pid)
            if signal_refused:
                raise PermissionError("fixture signaling denied")
            self.returncode = -9
        async def communicate(self):
            return b"", b""
    child = Child()
    async def spawn(*_args, **_kwargs):
        return child
    class Inspector:
        def boot_session_id(self):
            return "fixture-boot"
        def inspect(self, _pid):
            return SimpleNamespace(pgid=1, session_id=1, start_identity="fixture-start",
                                   effective_uid=os.geteuid(), effective_gid=os.getegid(),
                                   real_uid=os.getuid(), real_gid=os.getgid())
    def foreign_group(*_args):
        raise AssertionError("rejected process group was signaled")
    monkeypatch.setattr(resource, "_create_private_file", capture_file)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    monkeypatch.setattr(os, "killpg", foreign_group)
    with pytest.raises(AcpNativeProcessError, match="own process/session generation"):
        asyncio.run(resource.NativeProcessResource.open(
            binary=profile.binary, argv=profile.argv, environment={}, cwd=tmp_path,
            stdout_path=tmp_path/"stdout", stderr_path=tmp_path/"stderr",
            stdout_limit_bytes=1024, stderr_limit_bytes=1024, settle_seconds=1,
            inspector=Inspector(),
        ))
    assert killed == [child.pid]
    assert len(descriptors) == 2
    for fd in descriptors:
        with pytest.raises(OSError):
            os.fstat(fd)


def test_cancelled_writer_close_is_not_physical_settlement():
    from types import SimpleNamespace
    from integrations.acp_worker.process_resource import NativeCapture, NativeProcessResource
    async def exercise():
        resource = NativeProcessResource()
        resource.settle_seconds, resource.close_hook = 1.0, None
        resource.process = SimpleNamespace(returncode=0)
        class Writer:
            def is_closing(self):
                return True
            async def wait_closed(self):
                raise asyncio.CancelledError
        resource.writer = Writer()
        loop = asyncio.get_running_loop()
        resource.wait_task = loop.create_future()
        resource.wait_task.set_result(0)
        for name in ("stdout_task", "stderr_task"):
            task = loop.create_future()
            task.set_result(NativeCapture(hashlib.sha256(b"").hexdigest(), 0, False))
            setattr(resource, name, task)
        result = await resource.finish(None)
        assert result.exit_code == 0 and result.already_exited
        assert result.settled is False
        assert await resource.finish(None) is result
    asyncio.run(exercise())


def test_failed_post_spawn_admission_retains_unsettled_original_resource(launch, monkeypatch):
    from integrations.acp_worker import native
    from integrations.acp_worker.process_resource import NativeProcessResource
    profile, spec = launch
    finish = NativeProcessResource.finish
    async def unproven_finish(resource, reason):
        # Settle the actual fixture child; model the missing settlement receipt.
        actual = await finish(resource, reason)
        assert actual.settled
        return dataclasses.replace(actual, settled=False)
    def failed_worker_ref(**_kwargs):
        raise ValueError("fixture post-spawn admission failed")
    monkeypatch.setattr(NativeProcessResource, "finish", unproven_finish)
    monkeypatch.setattr(native, "WorkerProcessRef", failed_worker_ref)
    owner = AcpNativeProcessOwner(profile, environment_loader=lambda: {})
    async def exercise():
        with pytest.raises(ValueError, match="post-spawn admission"):
            await owner.open_run(spec)
        assert owner._opening is not None and owner._opening.finish_task is not None
        assert not owner._opening.identity_matches()
        assert not owner._runs and owner._active is None
        with pytest.raises(AcpNativeProcessError, match="active or known work"):
            await owner.open_run(dataclasses.replace(spec, run_id="different-run"))
    asyncio.run(exercise())

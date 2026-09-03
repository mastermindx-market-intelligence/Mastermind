"""Lifecycle and authority tests for the disposable pinned Zoekt host runner."""

from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

from experiments.code_discovery import processes as processes_module
from experiments.code_discovery.index_manifest import (
    load_index_manifest,
    source_tree_digest,
)
from experiments.code_discovery.processes import (
    ZOEKT_SOURCE_COMMIT,
    ExecutableSpec,
    ExecutableVerificationError,
    LoopbackEndpoint,
    ProcessOutputOverflow,
    StaleShardGenerationError,
    ZoektProcessError,
    ZoektProcessExited,
    ZoektProcessSet,
)


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _manifest(tmp_path: Path) -> object:
    source = tmp_path / "source"
    source.mkdir()
    _git(source, "init", "-q", "-b", "master")
    _git(source, "config", "user.name", "CodeIntel test")
    _git(source, "config", "user.email", "codeintel@example.invalid")
    _git(
        source,
        "remote",
        "add",
        "origin",
        "git@github.com:mastermindx-market-intelligence/Mastermind.git",
    )
    (source / "engine").mkdir()
    (source / "engine" / "core.py").write_text("VALUE = 'source'\n")
    _git(source, "add", ".")
    _git(source, "commit", "-qm", "source snapshot")
    includes = ("engine/**",)
    excludes: tuple[str, ...] = ()
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "mastermind.codeintel_index_manifest.v1",
                "repositories": [
                    {
                        "repository_id": "mastermind",
                        "repository_name": "mastermindx-market-intelligence/Mastermind",
                        "source_snapshot_root": str(source),
                        "ref_label": "master",
                        "commit_sha": _git(source, "rev-parse", "HEAD"),
                        "included_prefixes": includes,
                        "excluded_globs": excludes,
                        "source_tree_digest": source_tree_digest(
                            source, includes, excludes
                        ),
                    }
                ],
            }
        )
    )
    return load_index_manifest(manifest_path)


def _script(
    path: Path, body: str, *, role: str = "zoekt-git-index"
) -> ExecutableSpec:
    interpreter = Path(sys.executable).resolve()
    path.write_text(f"#!{interpreter}\n" + body)
    path.chmod(0o700)
    return ExecutableSpec(
        path=path,
        role=role,
        sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        source_commit=ZOEKT_SOURCE_COMMIT,
    )


def _indexer(path: Path, trace: Path, *, mutate_self: bool = False) -> ExecutableSpec:
    mutation = f"Path({str(path)!r}).write_text('changed')\n" if mutate_self else ""
    return _script(
        path,
        (
            "import os, sys\n"
            "from pathlib import Path\n"
            f"Path({str(trace)!r}).write_text('\\n'.join(sys.argv[1:]) + "
            "'\\nsecret=' + os.environ.get('INHERITED_TEST_SECRET', ''))\n"
            f"{mutation}"
        ),
    )


def _webserver(path: Path, trace: Path) -> ExecutableSpec:
    return _script(
        path,
        (
            "import socket, sys, time\n"
            "from pathlib import Path\n"
            "listen = next(argument.split('=', 1)[1] for argument in sys.argv "
            "if argument.startswith('--listen='))\n"
            "host, port = listen.rsplit(':', 1)\n"
            "listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)\n"
            "listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)\n"
            "listener.bind((host, int(port)))\n"
            "listener.listen()\n"
            f"Path({str(trace)!r}).write_text('\\n'.join(sys.argv[1:]))\n"
            "while True: time.sleep(1)\n"
        ),
        role="zoekt-webserver",
    )


def _process_set(
    tmp_path: Path,
    indexer: ExecutableSpec,
    webserver: ExecutableSpec,
    *,
    suffix: str = "",
) -> ZoektProcessSet:
    return ZoektProcessSet(
        indexer=indexer,
        webserver=webserver,
        shard_root=tmp_path / f"disposable-shards{suffix}",
        log_root=tmp_path / f"disposable-logs{suffix}",
        startup_timeout_seconds=2.0,
    )


def test_test_executables_bind_the_exact_interpreter(tmp_path: Path) -> None:
    executable = _script(tmp_path / "exact-python", "pass\n")
    first_line = executable.path.read_text(encoding="utf-8").splitlines()[0]
    assert first_line == f"#!{Path(sys.executable).resolve()}"
    assert "/usr/bin/env" not in first_line


def test_executable_spec_refuses_path_lookup_symlinks_and_mutable_binaries(
    tmp_path: Path,
) -> None:
    """Every invoked binary is an immutable exact digest, never ambient PATH."""

    binary = _script(tmp_path / "binary", "pass\n")
    binary.verify()

    with pytest.raises(ExecutableVerificationError, match="absolute"):
        ExecutableSpec(
            path=Path("zoekt-webserver"),
            role="zoekt-webserver",
            sha256=binary.sha256,
            source_commit=ZOEKT_SOURCE_COMMIT,
        ).verify()

    symlink = tmp_path / "binary-link"
    symlink.symlink_to(binary.path)
    with pytest.raises(ExecutableVerificationError, match="symlink"):
        ExecutableSpec(
            path=symlink,
            role="zoekt-webserver",
            sha256=binary.sha256,
            source_commit=ZOEKT_SOURCE_COMMIT,
        ).verify()

    binary.path.chmod(0o720)
    with pytest.raises(ExecutableVerificationError, match="writable"):
        binary.verify()


def test_closed_role_and_process_group_cleanup_leave_no_child_or_scratch(
    tmp_path: Path,
) -> None:
    """Only the two named Zoekt roles run, and closing one generation kills its group."""

    binary = _script(tmp_path / "binary", "pass\n")
    with pytest.raises(ExecutableVerificationError, match="role"):
        ExecutableSpec(
            path=binary.path,
            role="shell",
            sha256=binary.sha256,
            source_commit=ZOEKT_SOURCE_COMMIT,
        ).verify()

    manifest = _manifest(tmp_path)
    trace = tmp_path / "indexer-argv.txt"
    child_pid = tmp_path / "descendant.pid"
    server = _script(
        tmp_path / "zoekt-webserver",
        (
            "import socket, subprocess, sys, time\n"
            "from pathlib import Path\n"
            "listen = next(argument.split('=', 1)[1] for argument in sys.argv "
            "if argument.startswith('--listen='))\n"
            "host, port = listen.rsplit(':', 1)\n"
            "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
            f"Path({str(child_pid)!r}).write_text(str(child.pid))\n"
            "listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)\n"
            "listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)\n"
            "listener.bind((host, int(port)))\n"
            "listener.listen()\n"
            "while True: time.sleep(1)\n"
        ),
        role="zoekt-webserver",
    )
    processes = _process_set(tmp_path, _indexer(tmp_path / "zoekt-git-index", trace), server)
    processes.build_indexes(manifest)
    endpoint = processes.start_search()
    for _ in range(100):
        if child_pid.exists():
            break
        time.sleep(0.01)
    assert child_pid.exists()
    descendant = int(child_pid.read_text())

    processes.close()

    with pytest.raises(OSError):
        socket.create_connection((endpoint.host, endpoint.port), timeout=0.1)
    for _ in range(100):
        if not _pid_is_live(descendant):
            break
        time.sleep(0.01)
    assert not _pid_is_live(descendant)
    assert not (tmp_path / "disposable-shards").exists()
    assert not (tmp_path / "disposable-logs").exists()


def _pid_is_live(pid: int) -> bool:
    completed = subprocess.run(
        ["ps", "-o", "stat=", "-p", str(pid)], check=False, capture_output=True, text=True
    )
    state = completed.stdout.strip()
    return bool(state) and not state.startswith("Z")


def test_loopback_endpoint_rejects_every_non_loopback_listener() -> None:
    """The disposable server has no LAN, wildcard, or public binding option."""

    endpoint = LoopbackEndpoint("127.0.0.1", 6070)
    assert endpoint.url == "http://127.0.0.1:6070"
    for host in ("0.0.0.0", "::", "localhost", "10.0.0.1"):
        with pytest.raises(ValueError, match="loopback"):
            LoopbackEndpoint(host, 6070)


def test_build_uses_frozen_pinned_argv_closed_environment_and_exact_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Indexer invocation is one host-owned process per logical shard namespace."""

    manifest = _manifest(tmp_path)
    trace = tmp_path / "indexer-argv.txt"
    indexer = _indexer(tmp_path / "zoekt-git-index", trace)
    webserver = _webserver(tmp_path / "zoekt-webserver", tmp_path / "webserver-argv.txt")
    monkeypatch.setenv("INHERITED_TEST_SECRET", "must-not-reach-child")
    processes = _process_set(tmp_path, indexer, webserver)

    statuses = processes.build_indexes(manifest)

    assert len(statuses) == 1
    status = statuses[0]
    assert status.repository_id == "mastermind"
    assert status.ref_label == "master"
    assert status.indexed_commit_sha == manifest.repositories[0].commit_sha
    assert status.source_tree_digest == manifest.repositories[0].source_tree_digest
    assert status.health == "healthy"
    assert status.coverage == "covered"

    argv = trace.read_text().splitlines()
    assert argv[:6] == [
        f"--index={tmp_path / 'disposable-shards' / status.shard_namespace}",
        "--branches=master",
        "--prefix=refs/heads/",
        "--incremental=false",
        "--submodules=false",
        f"--meta={tmp_path / 'disposable-shards' / status.shard_namespace / 'z0-index-meta.json'}",
    ]
    assert argv[-2] == str(manifest.repositories[0].source_snapshot_root)
    assert argv[-1] == "secret="
    processes.close()


def test_refuses_stale_generation_and_detects_binary_change_after_index(
    tmp_path: Path,
) -> None:
    """Stale shards and time-of-check/time-of-use binary drift fail closed."""

    manifest = _manifest(tmp_path)
    trace = tmp_path / "indexer-argv.txt"
    indexer = _indexer(tmp_path / "zoekt-git-index", trace)
    webserver = _webserver(tmp_path / "zoekt-webserver", tmp_path / "webserver-argv.txt")
    processes = _process_set(tmp_path, indexer, webserver)
    stale = tmp_path / "disposable-shards" / manifest.repositories[0].shard_namespace
    stale.mkdir(parents=True)
    (stale / "prior-generation").write_text("do not merge")

    with pytest.raises(StaleShardGenerationError, match="stale"):
        processes.build_indexes(manifest)

    changed_indexer = _indexer(tmp_path / "changed-indexer", trace, mutate_self=True)
    changed = _process_set(tmp_path, changed_indexer, webserver, suffix="-changed")
    with pytest.raises(ExecutableVerificationError, match="digest"):
        changed.build_indexes(manifest)
    changed.close()


def test_tampered_logical_shard_receipt_refuses_serving(tmp_path: Path) -> None:
    """Serving rechecks repository/ref/SHA identity after each index build."""

    manifest = _manifest(tmp_path)
    trace = tmp_path / "indexer-argv.txt"
    processes = _process_set(
        tmp_path,
        _indexer(tmp_path / "zoekt-git-index", trace),
        _webserver(tmp_path / "zoekt-webserver", tmp_path / "webserver-argv.txt"),
    )
    status = processes.build_indexes(manifest)[0]
    receipt = (
        tmp_path
        / "disposable-shards"
        / status.shard_namespace
        / "z0-index-receipt.json"
    )
    receipt.write_text("{}")

    with pytest.raises(ZoektProcessError, match="receipt mismatch"):
        processes.start_search()
    processes.close()


def test_first_bind_collision_is_cleaned_and_second_attempt_starts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest = _manifest(tmp_path)
    trace = tmp_path / "indexer-argv.txt"
    processes = _process_set(
        tmp_path,
        _indexer(tmp_path / "zoekt-git-index", trace),
        _webserver(tmp_path / "zoekt-webserver", tmp_path / "webserver-argv.txt"),
    )
    processes.build_indexes(manifest)

    occupant = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    occupant.bind(("127.0.0.1", 0))
    occupant.listen()
    occupied_port = int(occupant.getsockname()[1])
    real_reserve = processes_module._reserve_loopback_port
    ports = iter((occupied_port, real_reserve()))
    reservations = 0

    def selected_port() -> int:
        nonlocal reservations
        reservations += 1
        return next(ports)

    monkeypatch.setattr(processes_module, "_reserve_loopback_port", selected_port)
    try:
        endpoint = processes.start_search()
        assert endpoint.port != occupied_port
        assert reservations == 2
        receipts = processes.startup_attempt_receipts
        assert [receipt.category for receipt in receipts] == [
            "BIND_COLLISION",
            "STARTED",
        ]
        failed = receipts[0]
        assert failed.attempt == 1
        assert failed.return_code not in (None, 0)
        assert failed.endpoint_disposition == "EXTERNAL_OCCUPIED"
        assert failed.cleanup_complete is True
        assert failed.diagnostics_truncated is False
        assert len(failed.diagnostics_sha256) == 64
        assert not (tmp_path / "disposable-logs" / "startup-1").exists()
        assert (tmp_path / "disposable-logs" / "startup-2").is_dir()
    finally:
        occupant.close()
        processes.close()


def test_non_bind_exit_is_not_retried_and_public_diagnostics_do_not_echo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest = _manifest(tmp_path)
    trace = tmp_path / "indexer-argv.txt"
    message = b"token=never-echo /Users/private/secret\n"
    server = _script(
        tmp_path / "failing-webserver",
        "import sys\n"
        f"sys.stderr.buffer.write({message!r})\n"
        "sys.stderr.flush()\n"
        "raise SystemExit(7)\n",
        role="zoekt-webserver",
    )
    processes = _process_set(
        tmp_path,
        _indexer(tmp_path / "zoekt-git-index", trace),
        server,
    )
    processes.build_indexes(manifest)
    reservations = 0
    real_reserve = processes_module._reserve_loopback_port

    def counted_port() -> int:
        nonlocal reservations
        reservations += 1
        return real_reserve()

    monkeypatch.setattr(processes_module, "_reserve_loopback_port", counted_port)
    with pytest.raises(ZoektProcessExited, match="ZOEKT_PROCESS_EXITED"):
        processes.start_search()

    assert reservations == 1
    receipt = processes.startup_attempt_receipts[0]
    assert receipt.category == "PROCESS_EXITED"
    assert receipt.return_code == 7
    assert receipt.stdout_bytes == 0
    assert receipt.stderr_bytes == len(message)
    assert receipt.diagnostics_truncated is False
    expected_digest = hashlib.sha256(
        b"stdout\0\0stderr\0" + message
    ).hexdigest()
    assert receipt.diagnostics_sha256 == expected_digest
    assert receipt.endpoint_disposition == "RELEASED"
    assert receipt.cleanup_complete is True
    rendered = json.dumps(asdict(receipt), sort_keys=True)
    assert "never-echo" not in rendered
    assert "/Users/" not in rendered
    assert "token" not in rendered.lower()
    assert not (tmp_path / "disposable-shards").exists()
    assert not (tmp_path / "disposable-logs").exists()


def test_output_overflow_is_terminal_and_dominates_bind_collision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest = _manifest(tmp_path)
    trace = tmp_path / "indexer-argv.txt"
    server = _script(
        tmp_path / "overflow-webserver",
        "import sys, time\n"
        "sys.stderr.write('address already in use ' + ('x' * (65 * 1024)))\n"
        "sys.stderr.flush()\n"
        "time.sleep(2)\n",
        role="zoekt-webserver",
    )
    processes = _process_set(
        tmp_path,
        _indexer(tmp_path / "zoekt-git-index", trace),
        server,
    )
    processes.build_indexes(manifest)
    reservations = 0
    real_reserve = processes_module._reserve_loopback_port

    def counted_port() -> int:
        nonlocal reservations
        reservations += 1
        return real_reserve()

    monkeypatch.setattr(processes_module, "_reserve_loopback_port", counted_port)
    with pytest.raises(ProcessOutputOverflow):
        processes.start_search()

    assert reservations == 1
    receipt = processes.startup_attempt_receipts[0]
    assert receipt.category == "OUTPUT_OVERFLOW"
    assert receipt.diagnostics_truncated is True
    assert receipt.cleanup_complete is True
    assert receipt.endpoint_disposition == "RELEASED"


def test_bounded_output_and_search_process_exit_are_typed_and_cleanup_is_idempotent(
    tmp_path: Path,
) -> None:
    """A noisy child or crash cannot look like a completed healthy index."""

    manifest = _manifest(tmp_path)
    noisy = _script(
        tmp_path / "noisy-indexer",
        "import sys\nsys.stdout.write('x' * (65 * 1024))\n",
    )
    webserver = _webserver(tmp_path / "zoekt-webserver", tmp_path / "webserver-argv.txt")
    noisy_processes = _process_set(tmp_path, noisy, webserver, suffix="-noisy")
    with pytest.raises(ProcessOutputOverflow):
        noisy_processes.build_indexes(manifest)
    noisy_processes.close()

    trace = tmp_path / "indexer-argv.txt"
    noisy_server = _script(
        tmp_path / "noisy-webserver",
        "import sys, time\n"
        "sys.stderr.write('x' * (65 * 1024))\n"
        "sys.stderr.flush()\n"
        "time.sleep(2)\n",
        role="zoekt-webserver",
    )
    noisy_server_processes = _process_set(
        tmp_path,
        _indexer(tmp_path / "server-indexer", trace),
        noisy_server,
        suffix="-noisy-server",
    )
    noisy_server_processes.build_indexes(manifest)
    with pytest.raises(ProcessOutputOverflow):
        noisy_server_processes.start_search()
    assert noisy_server_processes.startup_attempt_receipts[0].category == "OUTPUT_OVERFLOW"
    noisy_server_processes.close()

    processes = _process_set(
        tmp_path,
        _indexer(tmp_path / "zoekt-git-index", trace),
        webserver,
    )
    processes.build_indexes(manifest)
    endpoint = processes.start_search()
    assert endpoint.host == "127.0.0.1"
    webserver_argv = (tmp_path / "webserver-argv.txt").read_text().splitlines()
    assert webserver_argv == [
        f"--listen={endpoint.authority}",
        f"--index={tmp_path / 'disposable-shards'}",
        f"--log_dir={tmp_path / 'disposable-logs' / 'startup-1'}",
        "--html=true",
        "--rpc=false",
        "--indexserver_proxy=false",
        "--pprof=false",
    ]
    processes._search_process.kill()  # type: ignore[union-attr]
    for _ in range(20):
        if processes._search_process.poll() is not None:  # type: ignore[union-attr]
            break
        time.sleep(0.01)
    with pytest.raises(ZoektProcessExited, match="ZOEKT_PROCESS_EXITED"):
        processes.assert_search_alive()
    processes.close()
    processes.close()

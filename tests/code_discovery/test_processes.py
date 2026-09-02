"""Lifecycle and authority tests for the disposable pinned Zoekt host runner."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
from pathlib import Path

import pytest

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


def _script(path: Path, body: str) -> ExecutableSpec:
    path.write_text("#!/usr/bin/env python3\n" + body)
    path.chmod(0o700)
    return ExecutableSpec(
        path=path,
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


def test_executable_spec_refuses_path_lookup_symlinks_and_mutable_binaries(
    tmp_path: Path,
) -> None:
    """Every invoked binary is an immutable exact digest, never ambient PATH."""

    binary = _script(tmp_path / "binary", "pass\n")
    binary.verify()

    with pytest.raises(ExecutableVerificationError, match="absolute"):
        ExecutableSpec(
            path=Path("zoekt-webserver"),
            sha256=binary.sha256,
            source_commit=ZOEKT_SOURCE_COMMIT,
        ).verify()

    symlink = tmp_path / "binary-link"
    symlink.symlink_to(binary.path)
    with pytest.raises(ExecutableVerificationError, match="symlink"):
        ExecutableSpec(
            path=symlink,
            sha256=binary.sha256,
            source_commit=ZOEKT_SOURCE_COMMIT,
        ).verify()

    binary.path.chmod(0o720)
    with pytest.raises(ExecutableVerificationError, match="writable"):
        binary.verify()


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
    noisy_server_processes.close()

    processes = _process_set(
        tmp_path,
        _indexer(tmp_path / "zoekt-git-index", trace),
        webserver,
    )
    processes.build_indexes(manifest)
    endpoint = processes.start_search()
    assert endpoint.host == "127.0.0.1"
    assert "--listen=" + endpoint.authority in (tmp_path / "webserver-argv.txt").read_text()
    processes._search_process.kill()  # type: ignore[union-attr]
    for _ in range(20):
        if processes._search_process.poll() is not None:  # type: ignore[union-attr]
            break
        time.sleep(0.01)
    with pytest.raises(ZoektProcessExited, match="ZOEKT_PROCESS_EXITED"):
        processes.assert_search_alive()
    processes.close()
    processes.close()

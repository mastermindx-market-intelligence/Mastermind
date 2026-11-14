"""Lifecycle and authority tests for the disposable pinned Zoekt host runner."""

from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from experiments.code_discovery import index_manifest as index_manifest_module
from experiments.code_discovery import processes as processes_module
from experiments.code_discovery.index_manifest import (
    IndexManifest,
    load_index_manifest,
    source_tree_digest,
)


@pytest.fixture(autouse=True)
def _readonly_snapshot_mounts(monkeypatch: pytest.MonkeyPatch) -> None:
    """Process fixtures represent host-provisioned immutable snapshot mounts."""

    monkeypatch.setattr(
        index_manifest_module,
        "_filesystem_is_read_only",
        lambda _path: True,
        raising=False,
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


def _manifest(
    tmp_path: Path,
    *,
    repository_id: str = "mastermind",
    repository_name: str = "mastermindx-market-intelligence/Mastermind",
) -> object:
    source = tmp_path / "source"
    source.mkdir(parents=True)
    _git(source, "init", "-q", "-b", "master")
    _git(source, "config", "user.name", "CodeIntel test")
    _git(source, "config", "user.email", "codeintel@example.invalid")
    _git(
        source,
        "remote",
        "add",
        "origin",
        f"git@github.com:{repository_name}.git",
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
                        "repository_id": repository_id,
                        "repository_name": repository_name,
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
    path.write_text(f"#!{interpreter} -S\n" + body)
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
            "import json, socket, sys, time\n"
            "from pathlib import Path\n"
            "listen = next(argument.split('=', 1)[1] for argument in sys.argv "
            "if argument.startswith('--listen='))\n"
            "host, port = listen.rsplit(':', 1)\n"
            "listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)\n"
            "listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)\n"
            "listener.bind((host, int(port)))\n"
            "listener.listen()\n"
            f"Path({str(trace)!r}).write_text('\\n'.join(sys.argv[1:]))\n"
            "index = Path(next(argument.split('=', 1)[1] for argument in sys.argv "
            "if argument.startswith('--index=')))\n"
            "metadata_path = next(index.rglob('z0-index-meta.json'))\n"
            "metadata = json.loads(metadata_path.read_text())\n"
            "identity = metadata['Metadata']\n"
            "payload = json.dumps({'List': {'Repos': [{'Repository': {'Name': metadata['Name'], "
            "'Metadata': identity, 'Branches': [{'Name': identity['ref_label'], "
            "'Version': identity['commit_sha']}]}, 'IndexMetadata': {}, 'Stats': {}}], "
            "'ReposMap': {}, 'Crashes': 0, 'Stats': {}}}).encode()\n"
            "while True:\n"
            "    connection, _ = listener.accept()\n"
            "    with connection:\n"
            "        connection.settimeout(0.2)\n"
            "        try:\n"
            "            request = connection.recv(4096)\n"
            "        except TimeoutError:\n"
            "            continue\n"
            "        if request.startswith(b'POST /api/list HTTP/'):\n"
            "            response = (b'HTTP/1.1 200 OK\\r\\nContent-Type: application/json\\r\\n' "
            "+ f'Content-Length: {len(payload)}\\r\\nConnection: close\\r\\n\\r\\n'.encode() + payload)\n"
            "            connection.sendall(response)\n"
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
    assert first_line == f"#!{Path(sys.executable).resolve()} -S"
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
    seal = manifest.repositories[0].snapshot_seal
    assert seal is not None
    assert seal.git_dir == seal.common_dir
    assert seal.git_dir_is_common_dir is True
    trace = tmp_path / "indexer-argv.txt"
    child_pid = tmp_path / "descendant.pid"
    server = _script(
        tmp_path / "zoekt-webserver",
        (
            "import json, socket, subprocess, sys, time\n"
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
            "index = Path(next(argument.split('=', 1)[1] for argument in sys.argv if argument.startswith('--index=')))\n"
            "metadata = json.loads(next(index.rglob('z0-index-meta.json')).read_text())\n"
            "identity = metadata['Metadata']\n"
            "payload = json.dumps({'List': {'Repos': [{'Repository': {'Name': metadata['Name'], 'Metadata': identity, 'Branches': [{'Name': identity['ref_label'], 'Version': identity['commit_sha']}]}, 'IndexMetadata': {}, 'Stats': {}}], 'ReposMap': {}, 'Crashes': 0, 'Stats': {}}}).encode()\n"
            "while True:\n"
            "    connection, _ = listener.accept()\n"
            "    with connection:\n"
            "        connection.settimeout(0.2)\n"
            "        try:\n"
            "            request = connection.recv(4096)\n"
            "        except TimeoutError:\n"
            "            continue\n"
            "        if request.startswith(b'POST /api/list HTTP/'):\n"
            "            response = (b'HTTP/1.1 200 OK\\r\\nContent-Type: application/json\\r\\n' + f'Content-Length: {len(payload)}\\r\\nConnection: close\\r\\n\\r\\n'.encode() + payload)\n"
            "            connection.sendall(response)\n"
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
    assert argv[:7] == [
        f"--index={tmp_path / 'disposable-shards' / ('generation-' + processes._generation_id)}",
        "--branches=master",
        "--prefix=refs/heads/",
        "--incremental=false",
        "--submodules=false",
        "--disable_ctags=true",
        f"--meta={tmp_path / 'disposable-shards' / ('generation-' + processes._generation_id) / status.shard_namespace / 'z0-index-meta.json'}",
    ]
    assert argv[-2] == str(manifest.repositories[0].source_snapshot_root)
    assert argv[-1] == "secret="
    metadata = json.loads(
        (
            tmp_path
            / "disposable-shards"
            / ("generation-" + processes._generation_id)
            / status.shard_namespace
            / "z0-index-meta.json"
        ).read_text()
    )
    assert set(metadata) == {"Name", "Metadata"}
    assert metadata["Name"] == "mastermindx-market-intelligence/Mastermind"
    assert metadata["Metadata"] == {
        "schema": "mastermind.codeintel_index_identity.v1",
        "generation_id": processes._generation_id,
        "logical_repository_id": "mastermind",
        "canonical_repository": "mastermindx-market-intelligence/Mastermind",
        "ref_label": "master",
        "commit_sha": manifest.repositories[0].commit_sha,
        "source_tree_digest": manifest.repositories[0].source_tree_digest,
        "shard_namespace": status.shard_namespace,
    }
    processes.close()


def test_indexer_environment_is_hermetic_and_can_resolve_pinned_git(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The pinned indexer gets only a fixed Git-capable environment."""

    manifest = _manifest(tmp_path)
    trace = tmp_path / "indexer-environment.json"
    indexer = _script(
        tmp_path / "zoekt-git-index",
        "import json, os\n"
        "from pathlib import Path\n"
        f"Path({str(trace)!r}).write_text(json.dumps(dict(os.environ), sort_keys=True))\n",
    )
    webserver = _webserver(tmp_path / "zoekt-webserver", tmp_path / "webserver-argv.txt")
    monkeypatch.setenv("HOME", "/private/inherited-home")
    monkeypatch.setenv("HTTPS_PROXY", "http://inherited.invalid")
    processes = _process_set(tmp_path, indexer, webserver)

    processes.build_indexes(manifest)

    observed = json.loads(trace.read_text())
    observed.pop("__CF_USER_TEXT_ENCODING", None)
    assert observed == {
        "GIT_ASKPASS": "/bin/false",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_NO_REPLACE_OBJECTS": "1",
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_TERMINAL_PROMPT": "0",
        "LANG": "C",
        "LC_ALL": "C",
        "PATH": "/usr/bin:/bin",
        "TZ": "UTC",
    }
    processes.close()


def test_operation_index_root_exposes_all_distinct_built_shards_to_the_webserver(
    tmp_path: Path,
) -> None:
    """Pinned direct-root shard discovery must see every logical repository in one run."""

    first = _manifest(tmp_path / "first")
    second = _manifest(
        tmp_path / "second",
        repository_id="mastermind-terminal",
        repository_name="mastermindx-market-intelligence/Mastermind-Terminal",
    )
    manifest = IndexManifest(
        schema_version=first.schema_version,  # type: ignore[union-attr]
        repositories=(
            first.repositories[0],  # type: ignore[union-attr]
            second.repositories[0],  # type: ignore[union-attr]
        ),
    )
    indexer = _script(
        tmp_path / "visible-indexer",
        "import sys\n"
        "from pathlib import Path\n"
        "index = Path(next(argument.split('=', 1)[1] for argument in sys.argv if argument.startswith('--index=')))\n"
        "metadata = Path(next(argument.split('=', 1)[1] for argument in sys.argv if argument.startswith('--meta=')))\n"
        "(index / (metadata.parent.name + '.zoekt')).write_text(metadata.read_text())\n",
    )
    webserver = _script(
        tmp_path / "visible-webserver",
        "import json, socket, sys\n"
        "from pathlib import Path\n"
        "listen = next(argument.split('=', 1)[1] for argument in sys.argv if argument.startswith('--listen='))\n"
        "host, port = listen.rsplit(':', 1)\n"
        "listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)\n"
        "listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)\n"
        "listener.bind((host, int(port)))\n"
        "listener.listen()\n"
        "index = Path(next(argument.split('=', 1)[1] for argument in sys.argv if argument.startswith('--index=')))\n"
        "repos = []\n"
        "for shard in sorted(index.glob('*.zoekt')):\n"
        "    metadata = json.loads(shard.read_text())\n"
        "    identity = metadata['Metadata']\n"
        "    repos.append({'Repository': {'Name': metadata['Name'], 'Metadata': identity, 'Branches': [{'Name': identity['ref_label'], 'Version': identity['commit_sha']}]}, 'IndexMetadata': {}, 'Stats': {}})\n"
        "payload = json.dumps({'List': {'Repos': repos, 'ReposMap': {}, 'Crashes': 0, 'Stats': {}}}).encode()\n"
        "while True:\n"
        "    connection, _ = listener.accept()\n"
        "    with connection:\n"
        "        connection.recv(4096)\n"
        "        response = (b'HTTP/1.1 200 OK\\r\\nContent-Type: application/json\\r\\n' + f'Content-Length: {len(payload)}\\r\\nConnection: close\\r\\n\\r\\n'.encode() + payload)\n"
        "        connection.sendall(response)\n",
        role="zoekt-webserver",
    )
    processes = _process_set(tmp_path, indexer, webserver)

    statuses = processes.build_indexes(manifest)
    try:
        endpoint = processes.start_search()
        assert endpoint.host == "127.0.0.1"
        assert {status.repository_id for status in statuses} == {
            "mastermind",
            "mastermind-terminal",
        }
        assert len(processes._repository_identities) == 2
    finally:
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
    stale = tmp_path / "disposable-shards" / ("generation-" + processes._generation_id)
    stale.mkdir(parents=True)
    (stale / "prior-generation").write_text("do not merge")

    with pytest.raises(StaleShardGenerationError, match="stale"):
        processes.build_indexes(manifest)

    changed_indexer = _indexer(tmp_path / "changed-indexer", trace, mutate_self=True)
    changed = _process_set(tmp_path, changed_indexer, webserver, suffix="-changed")
    with pytest.raises(ExecutableVerificationError, match="digest"):
        changed.build_indexes(manifest)
    changed.close()


def test_index_build_rechecks_the_frozen_source_seal_before_indexer_launch(
    tmp_path: Path,
) -> None:
    """A source change after manifest validation cannot receive a healthy receipt."""

    manifest = _manifest(tmp_path)
    source = manifest.repositories[0].source_snapshot_root
    (source / "engine" / "core.py").write_text("VALUE = 'changed after seal'\n")
    trace = tmp_path / "indexer-argv.txt"
    processes = _process_set(
        tmp_path,
        _indexer(tmp_path / "zoekt-git-index", trace),
        _webserver(tmp_path / "zoekt-webserver", tmp_path / "webserver-argv.txt"),
    )

    with pytest.raises(ZoektProcessError, match="source snapshot seal"):
        processes.build_indexes(manifest)

    assert not trace.exists()
    assert processes._statuses == ()
    processes.close()


def test_index_build_rechecks_the_frozen_git_common_dir_identity(
    tmp_path: Path,
) -> None:
    """Replacing metadata with byte-identical Git files cannot evade the source seal."""

    manifest = _manifest(tmp_path)
    source = manifest.repositories[0].source_snapshot_root
    original_common_dir = source / ".git"
    moved_common_dir = tmp_path / "moved-common-dir"
    original_common_dir.rename(moved_common_dir)
    shutil.copytree(moved_common_dir, original_common_dir)
    trace = tmp_path / "indexer-argv.txt"
    processes = _process_set(
        tmp_path,
        _indexer(tmp_path / "zoekt-git-index", trace),
        _webserver(tmp_path / "zoekt-webserver", tmp_path / "webserver-argv.txt"),
    )

    with pytest.raises(ZoektProcessError, match="source snapshot seal"):
        processes.build_indexes(manifest)

    assert not trace.exists()
    assert processes._statuses == ()
    processes.close()


def test_index_build_rechecks_the_source_seal_after_restored_during_run_mutation(
    tmp_path: Path,
) -> None:
    """A restored byte sequence still changes the frozen file identity during indexing."""

    manifest = _manifest(tmp_path)
    marker = tmp_path / "indexer-mutated-source"
    indexer = _script(
        tmp_path / "mutating-indexer",
        "import time\n"
        "from pathlib import Path\n"
        "target = Path('engine/core.py')\n"
        "original = target.read_bytes()\n"
        "target.write_bytes(b\"VALUE = 'transient mutation'\\n\")\n"
        "time.sleep(0.02)\n"
        "target.write_bytes(original)\n"
        f"Path({str(marker)!r}).write_text('restored')\n",
    )
    processes = _process_set(
        tmp_path,
        indexer,
        _webserver(tmp_path / "zoekt-webserver", tmp_path / "webserver-argv.txt"),
    )

    with pytest.raises(ZoektProcessError, match="source snapshot seal"):
        processes.build_indexes(manifest)

    assert marker.read_text() == "restored"
    assert processes._statuses == ()
    processes.close()


def test_indexer_cannot_read_a_replacement_object_through_its_closed_git_env(
    tmp_path: Path,
) -> None:
    """Pinned Zoekt's internal git cat-file must see canonical, not replacement, bytes."""

    manifest = _manifest(tmp_path)
    source = manifest.repositories[0].source_snapshot_root
    original_blob = _git(source, "rev-parse", "HEAD:engine/core.py")
    original_bytes = (source / "engine" / "core.py").read_bytes()
    replacement_bytes = b"VALUE = 'replacement object'\n"
    replacement = subprocess.run(
        ["/usr/bin/git", "-C", str(source), "hash-object", "-w", "--stdin"],
        check=True,
        input=replacement_bytes,
        capture_output=True,
    ).stdout.decode().strip()
    _git(source, "replace", original_blob, replacement)
    trace = tmp_path / "indexer-read-bytes"
    indexer = _script(
        tmp_path / "replacement-reading-indexer",
        "import os, subprocess\n"
        "from pathlib import Path\n"
        f"result = subprocess.run(['/usr/bin/git', 'cat-file', 'blob', {original_blob!r}], "
        "check=True, capture_output=True, env=dict(os.environ))\n"
        f"Path({str(trace)!r}).write_bytes(result.stdout)\n",
    )
    processes = _process_set(
        tmp_path,
        indexer,
        _webserver(tmp_path / "zoekt-webserver", tmp_path / "webserver-argv.txt"),
    )

    processes.build_indexes(manifest)

    assert trace.read_bytes() == original_bytes
    processes.close()


def _linked_worktree_manifest(tmp_path: Path) -> tuple[IndexManifest, Path, Path, Path]:
    """Build a real linked checkout whose Git dir differs from the common dir."""

    owner = tmp_path / "owner"
    owner.mkdir()
    _git(owner, "init", "-q", "-b", "master")
    _git(owner, "config", "user.name", "CodeIntel test")
    _git(owner, "config", "user.email", "codeintel@example.invalid")
    _git(owner, "remote", "add", "origin", "git@github.com:mastermindx-market-intelligence/Mastermind.git")
    (owner / "engine").mkdir()
    (owner / "engine" / "core.py").write_text("VALUE = 'linked source'\n")
    _git(owner, "add", ".")
    _git(owner, "commit", "-qm", "linked source snapshot")
    _git(owner, "branch", "snapshot")
    source = tmp_path / "linked-source"
    _git(owner, "worktree", "add", "-q", str(source), "snapshot")
    includes = ("engine/**",)
    manifest_path = tmp_path / "linked-manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "mastermind.codeintel_index_manifest.v1",
                "repositories": [
                    {
                        "repository_id": "mastermind",
                        "repository_name": "mastermindx-market-intelligence/Mastermind",
                        "source_snapshot_root": str(source),
                        "ref_label": "snapshot",
                        "commit_sha": _git(source, "rev-parse", "HEAD"),
                        "included_prefixes": includes,
                        "excluded_globs": [],
                        "source_tree_digest": source_tree_digest(source, includes, ()),
                    }
                ],
            }
        )
    )
    manifest = load_index_manifest(manifest_path)
    git_dir_text = _git(source, "rev-parse", "--git-dir")
    git_dir = Path(git_dir_text)
    if not git_dir.is_absolute():
        git_dir = source / git_dir
    common_dir_text = _git(source, "rev-parse", "--git-common-dir")
    common_dir = Path(common_dir_text)
    if not common_dir.is_absolute():
        common_dir = source / common_dir
    return manifest, source, git_dir.resolve(), common_dir.resolve()


def test_linked_worktree_writable_git_dir_refuses_before_indexer_launch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A read-only root/common pair is insufficient if per-worktree metadata is writable."""

    manifest, source, git_dir, common_dir = _linked_worktree_manifest(tmp_path)
    assert git_dir != common_dir
    monkeypatch.setattr(
        index_manifest_module,
        "_filesystem_is_read_only",
        lambda path: Path(path).resolve() != git_dir,
    )
    trace = tmp_path / "indexer-argv.txt"
    processes = _process_set(
        tmp_path,
        _indexer(tmp_path / "zoekt-git-index", trace),
        _webserver(tmp_path / "zoekt-webserver", tmp_path / "webserver-argv.txt"),
    )

    with pytest.raises(ZoektProcessError, match="source snapshot seal"):
        processes.build_indexes(manifest)

    assert not trace.exists()
    assert processes._statuses == ()
    processes.close()


def test_linked_worktree_replaced_git_dir_refuses_before_indexer_launch(
    tmp_path: Path,
) -> None:
    """Byte-identical replacement of worktree-local Git metadata changes its seal."""

    manifest, _source, git_dir, common_dir = _linked_worktree_manifest(tmp_path)
    assert git_dir != common_dir
    moved_git_dir = tmp_path / "moved-worktree-git-dir"
    git_dir.rename(moved_git_dir)
    shutil.copytree(moved_git_dir, git_dir)
    trace = tmp_path / "indexer-argv.txt"
    processes = _process_set(
        tmp_path,
        _indexer(tmp_path / "zoekt-git-index", trace),
        _webserver(tmp_path / "zoekt-webserver", tmp_path / "webserver-argv.txt"),
    )

    with pytest.raises(ZoektProcessError, match="source snapshot seal"):
        processes.build_indexes(manifest)

    assert not trace.exists()
    assert processes._statuses == ()
    processes.close()


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
        / ("generation-" + processes._generation_id)
        / status.shard_namespace
        / "z0-index-receipt.json"
    )
    receipt.write_text("{}")

    with pytest.raises(ZoektProcessError, match="receipt mismatch"):
        processes.start_search()
    processes.close()


def test_identity_probe_rejects_missing_wrong_and_ambiguous_repositories(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Readiness needs one exact pinned-Zoekt identity, never just a listening port."""

    manifest = _manifest(tmp_path)
    trace = tmp_path / "indexer-argv.txt"
    processes = _process_set(
        tmp_path,
        _indexer(tmp_path / "zoekt-git-index", trace),
        _webserver(tmp_path / "zoekt-webserver", tmp_path / "webserver-argv.txt"),
    )
    processes.build_indexes(manifest)
    identity = processes._repository_identities[0]
    endpoint = LoopbackEndpoint("127.0.0.1", 6070)

    def exact_payload() -> dict[str, object]:
        return {
            "Repos": [
                {
                    "Repository": {
                        "Name": identity.repository_name,
                        "Metadata": identity.metadata,
                        "Branches": [
                            {"Name": identity.ref_label, "Version": identity.commit_sha}
                        ],
                    }
                }
            ]
        }

    for payload in (
        {"Repos": []},
        {"Repos": [{"Repository": {}}]},
        {
            "Repos": [
                {
                    "Repository": {
                        "Name": "wrong/repository",
                        "Metadata": identity.metadata,
                        "Branches": [
                            {"Name": identity.ref_label, "Version": identity.commit_sha}
                        ],
                    }
                }
            ]
        },
        {
            "Repos": [
                {
                    "Repository": {
                        "Name": identity.repository_name,
                        "Metadata": identity.metadata,
                        "Branches": [
                            {"Name": identity.ref_label, "Version": identity.commit_sha},
                            {"Name": identity.ref_label, "Version": identity.commit_sha},
                        ],
                    }
                }
            ]
        },
        {"Repos": [exact_payload()["Repos"][0], exact_payload()["Repos"][0]]},
        {"not_repos": []},
    ):
        monkeypatch.setattr(processes_module, "_post_loopback_list", lambda _endpoint, result=payload: result)
        assert not processes_module._loopback_has_exact_identities(
            endpoint, processes._repository_identities
        )

    assert processes_module._loopback_has_exact_identities(endpoint, ()) is False
    with pytest.raises(ValueError, match="duplicate"):
        json.loads(
            '{"Repos":[],"Repos":[]}',
            object_pairs_hook=processes_module._reject_duplicate_json_keys,
            parse_constant=processes_module._reject_non_finite_json_constant,
        )
    with pytest.raises(ValueError, match="forbidden"):
        json.loads(
            '{"Repos":NaN}',
            object_pairs_hook=processes_module._reject_duplicate_json_keys,
            parse_constant=processes_module._reject_non_finite_json_constant,
        )
    processes.close()


def test_identity_probe_accepts_pinned_list_envelope_and_rejects_crashes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only the real pinned List/RepoListEntry wire contract can establish readiness."""

    manifest = _manifest(tmp_path)
    trace = tmp_path / "indexer-argv.txt"
    processes = _process_set(
        tmp_path,
        _indexer(tmp_path / "zoekt-git-index", trace),
        _webserver(tmp_path / "zoekt-webserver", tmp_path / "webserver-argv.txt"),
    )
    processes.build_indexes(manifest)
    identity = processes._repository_identities[0]
    endpoint = LoopbackEndpoint("127.0.0.1", 6071)

    def pinned_payload(*, crashes: int) -> dict[str, object]:
        return {
            "List": {
                "Repos": [
                    {
                        "Repository": {
                            "Name": identity.repository_name,
                            "Metadata": identity.metadata,
                            "Branches": [
                                {
                                    "Name": identity.ref_label,
                                    "Version": identity.commit_sha,
                                }
                            ],
                        },
                        "IndexMetadata": {"LanguageMap": {}},
                        "Stats": {"Repos": 1},
                    }
                ],
                "ReposMap": {},
                "Crashes": crashes,
                "Stats": {"Repos": 1},
            }
        }

    monkeypatch.setattr(
        processes_module, "_post_loopback_list", lambda _endpoint: pinned_payload(crashes=0)
    )
    assert processes_module._loopback_has_exact_identities(
        endpoint, processes._repository_identities
    )

    monkeypatch.setattr(
        processes_module, "_post_loopback_list", lambda _endpoint: pinned_payload(crashes=1)
    )
    assert not processes_module._loopback_has_exact_identities(
        endpoint, processes._repository_identities
    )
    processes.close()


@pytest.mark.parametrize(
    "mutate",
    [
        lambda listing: listing.pop("ReposMap"),
        lambda listing: listing.__setitem__("ReposMap", None),
        lambda listing: listing.__setitem__("ReposMap", []),
        lambda listing: listing.__setitem__("ReposMap", {"unexpected": {}}),
        lambda listing: listing.__setitem__("Stats", []),
        lambda listing: listing["Repos"][0].__setitem__("Unexpected", {}),
        lambda listing: listing["Repos"][0].__setitem__("IndexMetadata", []),
        lambda listing: listing["Repos"][0].__setitem__("Stats", []),
    ],
)
def test_identity_probe_rejects_non_pinned_list_envelope_and_entry_shape(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutate: object
) -> None:
    """Only the exact pinned RepoList and RepoListEntry JSON shape can establish readiness."""

    manifest = _manifest(tmp_path)
    trace = tmp_path / "indexer-argv.txt"
    processes = _process_set(
        tmp_path,
        _indexer(tmp_path / "zoekt-git-index", trace),
        _webserver(tmp_path / "zoekt-webserver", tmp_path / "webserver-argv.txt"),
    )
    processes.build_indexes(manifest)
    identity = processes._repository_identities[0]
    listing: dict[str, object] = {
        "Repos": [
            {
                "Repository": {
                    "Name": identity.repository_name,
                    "Metadata": identity.metadata,
                    "Branches": [
                        {"Name": identity.ref_label, "Version": identity.commit_sha}
                    ],
                },
                "IndexMetadata": {},
                "Stats": {},
            }
        ],
        "ReposMap": {},
        "Crashes": 0,
        "Stats": {},
    }
    mutate(listing)  # type: ignore[operator]
    monkeypatch.setattr(
        processes_module, "_post_loopback_list", lambda _endpoint: {"List": listing}
    )

    assert not processes_module._loopback_has_exact_identities(
        LoopbackEndpoint("127.0.0.1", 6072), processes._repository_identities
    )
    processes.close()


def test_final_identity_probe_collision_marker_vetoes_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A marker captured during the final successful probe cannot be lost before STARTED."""

    class AliveProcess:
        returncode = None

        def poll(self) -> None:
            return None

    class Capture:
        marker_present = False

        def raise_if_overflow(self) -> None:
            return None

        def snapshot(self) -> object:
            if self.marker_present:
                return processes_module._CaptureSnapshot(
                    stdout=b"",
                    stderr=b"address already in use",
                    stdout_bytes=0,
                    stderr_bytes=len(b"address already in use"),
                    truncated=False,
                    sha256="0" * 64,
                )
            return processes_module._empty_capture_snapshot()

    capture = Capture()
    probe_calls = 0

    def successful_probe(_endpoint: LoopbackEndpoint, _expected: object) -> bool:
        nonlocal probe_calls
        probe_calls += 1
        if probe_calls == 2:
            capture.marker_present = True
        return True

    monkeypatch.setattr(processes_module, "_loopback_has_exact_identities", successful_probe)
    monkeypatch.setattr(processes_module, "_STARTUP_STABILITY_SECONDS", 0.0)
    with pytest.raises(processes_module.ZoektProcessTimeout):
        processes_module._wait_for_loopback(
            AliveProcess(),  # type: ignore[arg-type]
            capture,  # type: ignore[arg-type]
            LoopbackEndpoint("127.0.0.1", 6072),
            0.08,
            endpoint_was_open_before_spawn=False,
            expected_identities=(),
        )


def test_identity_http_boundary_rejects_redirect_oversize_and_strict_json(
    tmp_path: Path,
) -> None:
    """The real private HTTP boundary rejects malformed and non-success list replies."""

    manifest = _manifest(tmp_path)
    trace = tmp_path / "indexer-argv.txt"
    processes = _process_set(
        tmp_path,
        _indexer(tmp_path / "zoekt-git-index", trace),
        _webserver(tmp_path / "zoekt-webserver", tmp_path / "webserver-argv.txt"),
    )
    processes.build_indexes(manifest)
    identity = processes._repository_identities[0]
    valid = json.dumps(
        {
            "List": {
                "Repos": [
                    {
                        "Repository": {
                            "Name": identity.repository_name,
                            "Metadata": identity.metadata,
                            "Branches": [
                                {"Name": identity.ref_label, "Version": identity.commit_sha}
                            ],
                        },
                        "IndexMetadata": {},
                        "Stats": {},
                    }
                ],
                "ReposMap": {},
                "Crashes": 0,
                "Stats": {},
            }
        },
        separators=(",", ":"),
    ).encode()

    def probe(status: int, body: bytes, *, content_length: int | None = None) -> bool:
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = int(listener.getsockname()[1])

        def reply() -> None:
            with listener:
                connection, _ = listener.accept()
                with connection:
                    connection.recv(4096)
                    length = len(body) if content_length is None else content_length
                    connection.sendall(
                        f"HTTP/1.1 {status} reply\r\nContent-Length: {length}\r\n"
                        "Connection: close\r\n\r\n".encode()
                        + body
                    )

        thread = threading.Thread(target=reply)
        thread.start()
        try:
            return processes_module._loopback_has_exact_identities(
                LoopbackEndpoint("127.0.0.1", port), processes._repository_identities
            )
        finally:
            thread.join(timeout=1)

    assert probe(200, valid)
    assert not probe(302, valid)
    assert not probe(200, b'{"List":NaN}')
    assert not probe(200, b'{"List":{},"List":{}}')
    assert not probe(
        200,
        b"{}",
        content_length=processes_module._MAX_IDENTITY_RESPONSE_BYTES + 1,
    )
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


def test_delayed_bind_failure_cannot_use_an_unrelated_listener_as_readiness(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest = _manifest(tmp_path)
    trace = tmp_path / "indexer-argv.txt"
    server = _script(
        tmp_path / "delayed-bind-webserver",
        (
            "import socket, sys, time\n"
            "listen = next(argument.split('=', 1)[1] for argument in sys.argv "
            "if argument.startswith('--listen='))\n"
            "host, port = listen.rsplit(':', 1)\n"
            "listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)\n"
            "listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)\n"
            "try:\n"
            "    listener.bind((host, int(port)))\n"
            "except OSError:\n"
            "    sys.stderr.write('address already in use\\n')\n"
            "    sys.stderr.flush()\n"
            "    time.sleep(0.6)\n"
            "    raise SystemExit(98)\n"
            "listener.listen()\n"
            "while True:\n"
            "    connection, _ = listener.accept()\n"
            "    with connection:\n"
            "        connection.settimeout(0.2)\n"
            "        try:\n"
            "            request = connection.recv(4096)\n"
            "        except TimeoutError:\n"
            "            continue\n"
            "        if request.startswith(b'POST /api/list HTTP/'):\n"
            "            import json\n"
            "            from pathlib import Path\n"
            "            index = Path(next(argument.split('=', 1)[1] for argument in sys.argv if argument.startswith('--index=')))\n"
            "            metadata = json.loads(next(index.rglob('z0-index-meta.json')).read_text())\n"
            "            identity = metadata['Metadata']\n"
            "            payload = json.dumps({'List': {'Repos': [{'Repository': {'Name': metadata['Name'], 'Metadata': identity, 'Branches': [{'Name': identity['ref_label'], 'Version': identity['commit_sha']}]}, 'IndexMetadata': {}, 'Stats': {}}], 'ReposMap': {}, 'Crashes': 0, 'Stats': {}}}).encode()\n"
            "            response = (b'HTTP/1.1 200 OK\\r\\nContent-Type: application/json\\r\\n' + f'Content-Length: {len(payload)}\\r\\nConnection: close\\r\\n\\r\\n'.encode() + payload)\n"
            "            connection.sendall(response)\n"
        ),
        role="zoekt-webserver",
    )
    processes = _process_set(
        tmp_path,
        _indexer(tmp_path / "zoekt-git-index", trace),
        server,
    )
    processes.build_indexes(manifest)

    occupant = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    occupant.bind(("127.0.0.1", 0))
    occupant.listen()
    occupied_port = int(occupant.getsockname()[1])
    real_reserve = processes_module._reserve_loopback_port
    ports = iter((occupied_port, real_reserve()))

    monkeypatch.setattr(processes_module, "_reserve_loopback_port", lambda: next(ports))
    try:
        endpoint = processes.start_search()
        assert endpoint.port != occupied_port
        assert [
            receipt.category for receipt in processes.startup_attempt_receipts
        ] == ["BIND_COLLISION", "STARTED"]
    finally:
        occupant.close()
        processes.close()


def test_late_wrong_identity_listener_cannot_false_start_before_bind_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An endpoint opened after spawn is not the launched server without its identity."""

    manifest = _manifest(tmp_path)
    trace = tmp_path / "indexer-argv.txt"
    server = _script(
        tmp_path / "late-bind-webserver",
        (
            "import socket, sys, time\n"
            "listen = next(argument.split('=', 1)[1] for argument in sys.argv "
            "if argument.startswith('--listen='))\n"
            "host, port = listen.rsplit(':', 1)\n"
            "time.sleep(0.45)\n"
            "listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)\n"
            "try:\n"
            "    listener.bind((host, int(port)))\n"
            "except OSError:\n"
            "    sys.stderr.write('address already in use\\n')\n"
            "    sys.stderr.flush()\n"
            "    raise SystemExit(98)\n"
            "listener.listen()\n"
            "while True:\n"
            "    connection, _ = listener.accept()\n"
            "    with connection:\n"
            "        connection.settimeout(0.2)\n"
            "        try:\n"
            "            request = connection.recv(4096)\n"
            "        except TimeoutError:\n"
            "            continue\n"
            "        if request.startswith(b'POST /api/list HTTP/'):\n"
            "            import json\n"
            "            from pathlib import Path\n"
            "            index = Path(next(argument.split('=', 1)[1] for argument in sys.argv if argument.startswith('--index=')))\n"
            "            metadata = json.loads(next(index.rglob('z0-index-meta.json')).read_text())\n"
            "            identity = metadata['Metadata']\n"
            "            payload = json.dumps({'List': {'Repos': [{'Repository': {'Name': metadata['Name'], 'Metadata': identity, 'Branches': [{'Name': identity['ref_label'], 'Version': identity['commit_sha']}]}, 'IndexMetadata': {}, 'Stats': {}}], 'ReposMap': {}, 'Crashes': 0, 'Stats': {}}}).encode()\n"
            "            response = (b'HTTP/1.1 200 OK\\r\\nContent-Type: application/json\\r\\n' + f'Content-Length: {len(payload)}\\r\\nConnection: close\\r\\n\\r\\n'.encode() + payload)\n"
            "            connection.sendall(response)\n"
        ),
        role="zoekt-webserver",
    )
    processes = _process_set(
        tmp_path,
        _indexer(tmp_path / "zoekt-git-index", trace),
        server,
    )
    processes.build_indexes(manifest)

    first_listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    first_listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    first_ready = threading.Event()
    first_stop = threading.Event()

    def serve_wrong_identity(port: int) -> None:
        first_listener.bind(("127.0.0.1", port))
        first_listener.listen()
        first_listener.settimeout(0.05)
        first_ready.set()
        while not first_stop.is_set():
            try:
                connection, _ = first_listener.accept()
            except TimeoutError:
                continue
            with connection:
                connection.recv(4096)
                connection.sendall(
                    b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
                    b"Content-Length: 12\r\nConnection: close\r\n\r\n{\"Repos\":[]}"
                )

    real_reserve = processes_module._reserve_loopback_port
    first_port, second_port = real_reserve(), real_reserve()
    ports = iter((first_port, second_port))
    real_spawn = processes_module._spawn_exact

    def spawn_then_open_listener(*args: object, **kwargs: object) -> subprocess.Popen[bytes]:
        process = real_spawn(*args, **kwargs)  # type: ignore[arg-type]
        if not first_ready.is_set():
            threading.Thread(
                target=serve_wrong_identity, args=(first_port,), daemon=True
            ).start()
            assert first_ready.wait(timeout=1)
        return process

    monkeypatch.setattr(processes_module, "_reserve_loopback_port", lambda: next(ports))
    monkeypatch.setattr(processes_module, "_spawn_exact", spawn_then_open_listener)
    try:
        endpoint = processes.start_search()
        assert endpoint.port == second_port
        assert [receipt.category for receipt in processes.startup_attempt_receipts] == [
            "BIND_COLLISION",
            "STARTED",
        ]
    finally:
        first_stop.set()
        first_listener.close()
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
        f"--index={tmp_path / 'disposable-shards' / ('generation-' + processes._generation_id)}",
        f"--log_dir={tmp_path / 'disposable-logs' / 'startup-1'}",
        "--html=true",
        "--rpc=true",
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

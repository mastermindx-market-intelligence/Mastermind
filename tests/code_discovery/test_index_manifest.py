"""Tests for the host-owned, immutable Z0 repository/ref manifest."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path

import pytest

from experiments.code_discovery import index_manifest as index_manifest_module
from experiments.code_discovery.index_manifest import (
    IndexManifestError,
    load_index_manifest,
    material_source_manifest_digest,
    source_tree_digest,
)


@pytest.fixture(autouse=True)
def _readonly_snapshot_mounts(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unit fixtures model host-provisioned read-only snapshot mounts explicitly."""

    monkeypatch.setattr(
        index_manifest_module,
        "_filesystem_is_read_only",
        lambda _path: True,
        raising=False,
    )


def _run_git(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "GIT_AUTHOR_DATE": "2026-08-30T00:00:00+00:00",
            "GIT_COMMITTER_DATE": "2026-08-30T00:00:00+00:00",
        },
    )
    return completed.stdout.strip()


def _snapshot(
    root: Path,
    *,
    sentinel: str = "SENTINEL",
    repository_name: str = "mastermindx-market-intelligence/Mastermind",
) -> Path:
    root.mkdir(parents=True)
    _run_git(root, "init", "-q", "-b", "master")
    _run_git(root, "config", "user.name", "CodeIntel test")
    _run_git(root, "config", "user.email", "codeintel@example.invalid")
    _run_git(
        root,
        "remote",
        "add",
        "origin",
        f"git@github.com:{repository_name}.git",
    )
    (root / "engine").mkdir()
    (root / "engine" / "core.py").write_text(f'VALUE = "{sentinel}"\n')
    (root / "docs").mkdir()
    (root / "docs" / "README.md").write_text(f"{sentinel}\n")
    (root / "site").mkdir()
    (root / "site" / "rendered.html").write_text("<p>generated</p>\n")
    _run_git(root, "add", ".")
    _run_git(root, "commit", "-qm", "exact source snapshot")
    return root


def _record(
    root: Path,
    *,
    repository_id: str = "mastermind",
    repository_name: str = "mastermindx-market-intelligence/Mastermind",
    ref_label: str = "master",
    included_prefixes: tuple[str, ...] = ("engine/**", "docs/**"),
    excluded_globs: tuple[str, ...] = ("site/**",),
) -> dict[str, object]:
    return {
        "repository_id": repository_id,
        "repository_name": repository_name,
        "source_snapshot_root": str(root),
        "ref_label": ref_label,
        "commit_sha": _run_git(root, "rev-parse", "HEAD"),
        "included_prefixes": list(included_prefixes),
        "excluded_globs": list(excluded_globs),
        "source_tree_digest": source_tree_digest(
            root, included_prefixes, excluded_globs
        ),
    }


def _write_manifest(path: Path, records: list[dict[str, object]]) -> Path:
    path.write_text(
        json.dumps(
            {
                "schema_version": "mastermind.codeintel_index_manifest.v1",
                "repositories": records,
            },
            sort_keys=True,
        )
    )
    return path


def _literal_selected_digest(root: Path, relatives: tuple[str, ...]) -> str:
    """Build the reviewed fixture digest independently from the manifest loader."""

    digest = hashlib.sha256()
    for relative in sorted(relatives):
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256((root / relative).read_bytes()).digest())
        digest.update(b"\0")
    return digest.hexdigest()


def test_loads_exact_clean_snapshots_and_uses_root_free_material_digest(
    tmp_path: Path,
) -> None:
    """The root is host-local; source identity is the immutable material payload."""

    first = _snapshot(tmp_path / "one" / "shared")
    second = _snapshot(tmp_path / "two" / "shared")
    first_manifest = load_index_manifest(
        _write_manifest(tmp_path / "first.json", [_record(first)])
    )
    second_manifest = load_index_manifest(
        _write_manifest(tmp_path / "second.json", [_record(second)])
    )

    repository = first_manifest.repositories[0]
    assert repository.repository_id == "mastermind"
    assert repository.source_snapshot_root == first
    assert repository.source_tree_digest == source_tree_digest(
        first, ("engine/**", "docs/**"), ("site/**",)
    )
    assert material_source_manifest_digest(first_manifest) == material_source_manifest_digest(
        second_manifest
    )


def test_duplicate_logical_identity_and_repository_ref_pairs_fail_closed(
    tmp_path: Path,
) -> None:
    """A manifest cannot merge independent rows through a convenient alias."""

    first = _snapshot(tmp_path / "first")
    second = _snapshot(
        tmp_path / "second", repository_name="mastermindx-market-intelligence/Other"
    )
    third = _snapshot(tmp_path / "third")
    same_id = _write_manifest(
        tmp_path / "same-id.json",
        [
            _record(first),
            _record(
                second,
                repository_id="mastermind",
                repository_name="mastermindx-market-intelligence/Other",
            ),
        ],
    )
    same_name_ref = _write_manifest(
        tmp_path / "same-name-ref.json",
        [
            _record(first),
            _record(third, repository_id="other"),
        ],
    )

    with pytest.raises(IndexManifestError, match="duplicate repository_id"):
        load_index_manifest(same_id)
    with pytest.raises(IndexManifestError, match="duplicate repository_name/ref"):
        load_index_manifest(same_name_ref)


def test_same_snapshot_basename_has_disjoint_logical_shard_namespaces(
    tmp_path: Path,
) -> None:
    """Zoekt namespaces cannot derive from the mutable local basename alone."""

    left = _snapshot(
        tmp_path / "left" / "shared", sentinel="LEFT", repository_name="org-left/shared"
    )
    right = _snapshot(
        tmp_path / "right" / "shared", sentinel="RIGHT", repository_name="org-right/shared"
    )
    manifest = load_index_manifest(
        _write_manifest(
            tmp_path / "manifest.json",
            [
                _record(
                    left,
                    repository_id="shared-left",
                    repository_name="org-left/shared",
                ),
                _record(
                    right,
                    repository_id="shared-right",
                    repository_name="org-right/shared",
                ),
            ],
        )
    )

    assert tuple(spec.repository_id for spec in manifest.repositories) == (
        "shared-left",
        "shared-right",
    )
    assert manifest.repositories[0].shard_namespace != manifest.repositories[1].shard_namespace
    assert manifest.repositories[0].source_snapshot_root.name == "shared"
    assert manifest.repositories[1].source_snapshot_root.name == "shared"


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda record, root: record.update(commit_sha="not-a-commit"),
            "commit_sha",
        ),
        (
            lambda record, root: record.update(
                included_prefixes=["engine/**", "site/**"], excluded_globs=[]
            ),
            "source_tree_digest",
        ),
        (
            lambda record, root: record.update(
                included_prefixes=["engine/**"], excluded_globs=["engine/**"]
            ),
            "overlap",
        ),
        (
            lambda record, root: record.update(included_prefixes=["/outside/**"]),
            "relative",
        ),
        (
            lambda record, root: record.update(excluded_globs=["../outside/**"]),
            "traversal",
        ),
        (
            lambda record, root: record.update(
                included_prefixes=[f"engine/{index}/**" for index in range(33)]
            ),
            "at most",
        ),
    ],
)
def test_rejects_invalid_identity_or_unbounded_path_policy(
    tmp_path: Path, mutate: object, message: str
) -> None:
    """Malformed rows cannot become a silently broad source selection."""

    root = _snapshot(tmp_path / "snapshot")
    record = _record(root)
    mutate(record, root)  # type: ignore[operator]

    with pytest.raises(IndexManifestError, match=message):
        load_index_manifest(_write_manifest(tmp_path / "manifest.json", [record]))


def test_rejects_symlink_roots_dirty_snapshots_and_changed_source_bytes(
    tmp_path: Path,
) -> None:
    """The runner must read a clean immutable checkout, never a convenient tree."""

    root = _snapshot(tmp_path / "snapshot")
    symlink = tmp_path / "snapshot-link"
    symlink.symlink_to(root, target_is_directory=True)

    symlink_record = _record(root)
    symlink_record["source_snapshot_root"] = str(symlink)
    with pytest.raises(IndexManifestError, match="symlink"):
        load_index_manifest(_write_manifest(tmp_path / "symlink.json", [symlink_record]))

    dirty_record = _record(root)
    (root / "untracked.py").write_text("UNTRACKED = True\n")
    with pytest.raises(IndexManifestError, match="clean Git snapshot"):
        load_index_manifest(_write_manifest(tmp_path / "dirty.json", [dirty_record]))


def test_closed_git_inspection_ignores_ambient_path_credentials_and_fsmonitor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Snapshot inspection may not invoke an ambient Git, config, hook, or helper."""

    root = _snapshot(tmp_path / "snapshot")
    record = _record(root)
    manifest_path = _write_manifest(tmp_path / "manifest.json", [record])
    hostile_bin = tmp_path / "hostile-bin"
    hostile_bin.mkdir()
    ambient_marker = tmp_path / "ambient-git-ran"
    fsmonitor_marker = tmp_path / "fsmonitor-ran"
    global_config = tmp_path / "inherited-global-config"
    global_config.write_text("[credential]\n\thelper = !false\n")
    (hostile_bin / "git").write_text(
        "#!/bin/sh\n"
        f"printf '%s' \"$HOME|$GIT_ASKPASS|$HTTPS_PROXY\" > {ambient_marker!s}\n"
        "exec /usr/bin/git \"$@\"\n"
    )
    (hostile_bin / "git").chmod(0o700)
    fsmonitor = tmp_path / "hostile-fsmonitor"
    fsmonitor.write_text(f"#!/bin/sh\n: > {fsmonitor_marker!s}\n")
    fsmonitor.chmod(0o700)
    _run_git(root, "config", "core.fsmonitor", str(fsmonitor))
    monkeypatch.setenv("PATH", str(hostile_bin))
    monkeypatch.setenv("HOME", str(tmp_path / "inherited-home"))
    monkeypatch.setenv("GIT_ASKPASS", str(tmp_path / "inherited-askpass"))
    monkeypatch.setenv("HTTPS_PROXY", "http://credential-proxy.invalid")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(global_config))
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "credential.helper")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "!false")

    manifest = load_index_manifest(manifest_path)

    assert manifest.repositories[0].repository_id == "mastermind"
    assert not ambient_marker.exists()
    assert not fsmonitor_marker.exists()


def test_refuses_clean_but_writable_snapshot_mount_before_identity_checks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Permission bits and a clean Git index cannot substitute for a read-only mount."""

    root = _snapshot(tmp_path / "snapshot")
    record = _record(root)
    monkeypatch.setattr(
        index_manifest_module,
        "_filesystem_is_read_only",
        lambda _path: False,
        raising=False,
    )

    with pytest.raises(IndexManifestError, match="read-only"):
        load_index_manifest(_write_manifest(tmp_path / "manifest.json", [record]))


def test_refuses_wrong_remote_and_ref_identity(tmp_path: Path) -> None:
    """A matching commit alone cannot substitute for exact checkout identity and census."""

    root = _snapshot(tmp_path / "snapshot")
    wrong_ref = _record(root, ref_label="main")
    with pytest.raises(IndexManifestError, match="ref_label"):
        load_index_manifest(_write_manifest(tmp_path / "wrong-ref.json", [wrong_ref]))

    wrong_remote = _record(root, repository_name="mastermindx-market-intelligence/Other")
    with pytest.raises(IndexManifestError, match="remote"):
        load_index_manifest(_write_manifest(tmp_path / "wrong-remote.json", [wrong_remote]))



def test_accepts_distinct_repository_paths_with_the_same_basename(tmp_path: Path) -> None:
    """Git path plus blob identity—not basename—governs the source census."""

    root = _snapshot(tmp_path / "snapshot")
    first = root / "experiments" / "code_discovery" / "__init__.py"
    second = root / "control_plane" / "__init__.py"
    first.parent.mkdir(parents=True)
    second.parent.mkdir()
    first.write_text("DISCOVERY = True\n")
    second.write_text("CONTROL = True\n")
    _run_git(root, "add", ".")
    _run_git(root, "commit", "-qm", "add distinct package initializers")
    selected = ("experiments/code_discovery/__init__.py", "control_plane/__init__.py")
    record = {
        "repository_id": "mastermind",
        "repository_name": "mastermindx-market-intelligence/Mastermind",
        "source_snapshot_root": str(root),
        "ref_label": "master",
        "commit_sha": _run_git(root, "rev-parse", "HEAD"),
        "included_prefixes": ["experiments/code_discovery/**", "control_plane/**"],
        "excluded_globs": [],
        "source_tree_digest": _literal_selected_digest(root, selected),
    }

    manifest = load_index_manifest(_write_manifest(tmp_path / "manifest.json", [record]))

    assert manifest.repositories[0].source_tree_digest == _literal_selected_digest(root, selected)


@pytest.mark.parametrize(
    "body",
    [
        '{{"schema_version":"mastermind.codeintel_index_manifest.v1","schema_version":"mastermind.codeintel_index_manifest.v1","repositories":{repositories}}}',
        '{{"schema_version":"mastermind.codeintel_index_manifest.v1","repositories":{repositories},"not_finite":NaN}}',
    ],
)
def test_manifest_decoder_rejects_duplicate_keys_and_non_finite_constants(
    tmp_path: Path, body: str
) -> None:
    """Malformed JSON cannot reach manifest schema validation by being silently normalized."""

    root = _snapshot(tmp_path / "snapshot")
    record = _record(root)
    path = tmp_path / "manifest.json"
    path.write_text(body.format(repositories=json.dumps([record], sort_keys=True)))

    with pytest.raises(IndexManifestError, match="valid UTF-8 JSON"):
        load_index_manifest(path)


def test_seed_fixture_carries_all_three_initial_logical_entries() -> None:
    """The reviewed fixture starts from the F0 repository/ref census."""

    fixture = Path(__file__).parent.parent / "fixtures" / "code_discovery" / "manifest.json"
    payload = json.loads(fixture.read_text())

    assert payload["schema_version"] == "mastermind.codeintel_index_manifest.v1"
    assert [
        (row["repository_id"], row["ref_label"]) for row in payload["repositories"]
    ] == [
        ("mastermind", "master"),
        ("mastermind-terminal", "master"),
        ("macro", "main"),
    ]
    macro = payload["repositories"][2]
    assert {
        "engine/**",
        "lib/**",
        "scripts/**",
        "tests/**",
        "agentos/**",
        "app/**",
    }.issubset(
        macro["included_prefixes"]
    )
    assert {"site/**", "data/**", "vendor/**", "node_modules/**"}.issubset(
        macro["excluded_globs"]
    )

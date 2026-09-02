"""Tests for the host-owned, immutable Z0 repository/ref manifest."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from experiments.code_discovery.index_manifest import (
    IndexManifestError,
    load_index_manifest,
    material_source_manifest_digest,
    source_tree_digest,
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


def _snapshot(root: Path, *, sentinel: str = "SENTINEL") -> Path:
    root.mkdir(parents=True)
    _run_git(root, "init", "-q", "-b", "master")
    _run_git(root, "config", "user.name", "CodeIntel test")
    _run_git(root, "config", "user.email", "codeintel@example.invalid")
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
    second = _snapshot(tmp_path / "second")
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
            _record(second, repository_id="other"),
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

    left = _snapshot(tmp_path / "left" / "shared", sentinel="LEFT")
    right = _snapshot(tmp_path / "right" / "shared", sentinel="RIGHT")
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

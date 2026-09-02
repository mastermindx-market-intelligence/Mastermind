from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path

import pytest

from control_plane.executive_capability_packages import (
    CAPABILITY_PACKAGE_CONTENT_SCHEMA,
    CAPABILITY_PACKAGE_GENERATION_SCHEMA,
    CAPABILITY_PACKAGE_SOURCE_SCHEMA,
    EFFECTIVE_SKILL_CLOSURE_SCHEMA,
    EFFECTIVE_SKILL_GRANT_SCHEMA,
    CapabilityPackageError,
    CapabilityPackageFile,
    build_capability_package_generation,
    capability_package_content_digest,
    effective_skill_content_digest,
    verify_capability_package_source,
)
from control_plane import executive_capability_packages as package_module


def _canonical_digest(value: object) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _row(path: str, data: bytes, *, executable: bool = False) -> dict[str, object]:
    return {
        "relative_path": path,
        "sha256": hashlib.sha256(data).hexdigest(),
        "byte_length": len(data),
        "executable": executable,
    }


def _raw_package(rows: list[dict[str, object]]) -> dict[str, object]:
    package_id = "example-operator.p1"
    generation = "example-operator.p1.2026-09-01"
    repository = "example/example"
    source_commit = "1" * 40
    source_tree_sha = "2" * 40
    package_root = "plugins/example-operator"
    manifest_path = ".codex-plugin/plugin.json"
    ordered_rows = sorted(rows, key=lambda row: str(row["relative_path"]).encode("utf-8"))
    content_digest = _canonical_digest(
        {
            "schema_version": CAPABILITY_PACKAGE_CONTENT_SCHEMA,
            "files": ordered_rows,
        }
    )
    source_digest = _canonical_digest(
        {
            "schema_version": CAPABILITY_PACKAGE_SOURCE_SCHEMA,
            "capability_id": package_id,
            "kind": "skills-only-source",
            "repository": repository,
            "source_commit": source_commit,
            "source_tree_sha": source_tree_sha,
            "package_root": package_root,
            "manifest_path": manifest_path,
            "package_content_digest": content_digest,
            "required_app_references": [],
        }
    )
    closure_paths = (
        "references/boundary.md",
        "skills/receive/SKILL.md",
    )
    row_by_path = {str(row["relative_path"]): row for row in ordered_rows}
    closure_digest = _canonical_digest(
        {
            "schema_version": EFFECTIVE_SKILL_CLOSURE_SCHEMA,
            "skill_name": "receive",
            "entrypoint_path": "skills/receive/SKILL.md",
            "files": [row_by_path[path] for path in closure_paths],
        }
    )
    skill_id = "example-operator.receive.v1"
    grant_digest = _canonical_digest(
        {
            "schema_version": EFFECTIVE_SKILL_GRANT_SCHEMA,
            "capability_id": skill_id,
            "runtime_name": "receive",
            "entrypoint_path": "skills/receive/SKILL.md",
            "closure_paths": list(closure_paths),
            "skill_content_digest": closure_digest,
            "package_capability_id": package_id,
            "package_generation": generation,
            "package_source_digest": source_digest,
        }
    )
    generation_digest = _canonical_digest(
        {
            "schema_version": CAPABILITY_PACKAGE_GENERATION_SCHEMA,
            "capability_id": package_id,
            "generation": generation,
            "source_state": "SOURCE_PROTECTED",
            "revoked": False,
            "package_source_digest": source_digest,
            "skills": [
                {"capability_id": skill_id, "grant_digest": grant_digest}
            ],
        }
    )
    return {
        "kind": "skills-only-source",
        "repository": repository,
        "source_commit": source_commit,
        "source_tree_sha": source_tree_sha,
        "package_root": package_root,
        "manifest_path": manifest_path,
        "generation": generation,
        "source_state": "SOURCE_PROTECTED",
        "revoked": False,
        "package_content_digest": content_digest,
        "package_source_digest": source_digest,
        "files": ordered_rows,
        "skills": {
            skill_id: {
                "runtime_name": "receive",
                "entrypoint_path": "skills/receive/SKILL.md",
                "closure_paths": list(closure_paths),
                "skill_content_digest": closure_digest,
                "grant_digest": grant_digest,
            }
        },
        "required_app_references": [],
        "package_generation_digest": generation_digest,
    }


def _make_source(tmp_path: Path) -> tuple[Path, dict[str, bytes]]:
    contents = {
        ".codex-plugin/plugin.json": b'{"name":"example"}\n',
        "references/boundary.md": b"shared boundary\n",
        "skills/receive/SKILL.md": b"receive procedure\n",
    }
    package_root = tmp_path / "plugins" / "example-operator"
    for relative, data in contents.items():
        destination = package_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
        destination.chmod(0o644)
    return tmp_path, contents


def _generation(tmp_path: Path):
    source_root, contents = _make_source(tmp_path)
    rows = [_row(path, data) for path, data in sorted(contents.items())]
    raw = _raw_package(rows)
    generation = build_capability_package_generation(
        capability_id="example-operator.p1",
        raw=raw,
    )
    return source_root, generation


def test_package_content_digest_is_canonical_and_order_independent() -> None:
    files = (
        CapabilityPackageFile(
            relative_path="references/boundary.md",
            sha256="a" * 64,
            byte_length=7,
            executable=False,
        ),
        CapabilityPackageFile(
            relative_path="skills/receive/SKILL.md",
            sha256="b" * 64,
            byte_length=11,
            executable=False,
        ),
    )
    expected = "90d672e2cd40329584b16129f47ea3e0ebf5f7e7944f15a20df7687f7b42e722"
    assert capability_package_content_digest(files) == expected
    assert capability_package_content_digest(tuple(reversed(files))) == expected
    changed = (
        files[0],
        CapabilityPackageFile(
            relative_path=files[1].relative_path,
            sha256=files[1].sha256,
            byte_length=12,
            executable=False,
        ),
    )
    assert capability_package_content_digest(changed) != expected


def test_effective_skill_digest_excludes_unrelated_rows() -> None:
    reference = CapabilityPackageFile("references/boundary.md", "a" * 64, 7, False)
    entrypoint = CapabilityPackageFile("skills/receive/SKILL.md", "b" * 64, 11, False)
    unrelated = CapabilityPackageFile("other.txt", "c" * 64, 3, False)
    expected = effective_skill_content_digest(
        runtime_name="receive",
        entrypoint_path=entrypoint.relative_path,
        closure_files=(reference, entrypoint),
    )
    assert expected == effective_skill_content_digest(
        runtime_name="receive",
        entrypoint_path=entrypoint.relative_path,
        closure_files=(entrypoint, reference),
    )
    assert unrelated.relative_path not in (reference.relative_path, entrypoint.relative_path)
    moved_reference = CapabilityPackageFile(reference.relative_path, "d" * 64, 7, False)
    assert expected != effective_skill_content_digest(
        runtime_name="receive",
        entrypoint_path=entrypoint.relative_path,
        closure_files=(moved_reference, entrypoint),
    )


@pytest.mark.parametrize(
    "path",
    ["", "/absolute", "../escape", "a/../b", "a\\b", "a//b", "a/./b", "a\x00b"],
)
def test_file_paths_fail_closed(path: str) -> None:
    with pytest.raises(CapabilityPackageError):
        CapabilityPackageFile(path, "a" * 64, 1, False)


@pytest.mark.parametrize("length", [-1, 1024 * 1024 + 1])
def test_file_byte_bounds_fail_closed(length: int) -> None:
    with pytest.raises(CapabilityPackageError):
        CapabilityPackageFile("a", "a" * 64, length, False)


def test_builder_refuses_unsorted_rows_and_digest_drift(tmp_path: Path) -> None:
    _, contents = _make_source(tmp_path)
    rows = [_row(path, data) for path, data in sorted(contents.items())]
    raw = _raw_package(rows)
    raw["files"] = list(reversed(raw["files"]))
    with pytest.raises(CapabilityPackageError, match="sorted"):
        build_capability_package_generation(
            capability_id="example-operator.p1", raw=raw
        )

    raw = _raw_package(rows)
    raw["package_content_digest"] = "0" * 64
    with pytest.raises(CapabilityPackageError, match="package_content_digest"):
        build_capability_package_generation(
            capability_id="example-operator.p1", raw=raw
        )


def test_builder_refuses_casefold_collision() -> None:
    rows = [
        _row("A.txt", b"a"),
        _row("a.txt", b"b"),
        _row(".codex-plugin/plugin.json", b"{}"),
        _row("references/boundary.md", b"r"),
        _row("skills/receive/SKILL.md", b"s"),
    ]
    raw = _raw_package(rows)
    with pytest.raises(CapabilityPackageError, match="case-fold"):
        build_capability_package_generation(
            capability_id="example-operator.p1", raw=raw
        )


def test_verify_happy_path_returns_bounded_receipt(tmp_path: Path) -> None:
    source_root, generation = _generation(tmp_path)
    receipt = verify_capability_package_source(source_root, generation)
    assert receipt.capability_id == "example-operator.p1"
    assert receipt.package_content_digest == generation.package_content_digest
    assert receipt.package_source_digest == generation.package_source_digest
    assert receipt.package_generation_digest == generation.package_generation_digest
    assert receipt.file_count == 3
    assert receipt.total_bytes == sum(row.byte_length for row in generation.files)
    assert receipt.skill_content_digests == (
        ("example-operator.receive.v1", generation.skills[0].skill_content_digest),
    )
    assert not hasattr(receipt, "source_root")


def test_verify_refuses_source_root_symlink(tmp_path: Path) -> None:
    real = tmp_path / "real"
    source_root, generation = _generation(real)
    link = tmp_path / "link"
    link.symlink_to(source_root, target_is_directory=True)
    with pytest.raises(CapabilityPackageError, match="symlink"):
        verify_capability_package_source(link, generation)


def test_verify_refuses_package_root_symlink(tmp_path: Path) -> None:
    real = tmp_path / "real"
    source_root, generation = _generation(real)
    target = tmp_path / "target"
    shutil.copytree(source_root / "plugins" / "example-operator", target)
    shutil.rmtree(source_root / "plugins" / "example-operator")
    (source_root / "plugins" / "example-operator").symlink_to(
        target, target_is_directory=True
    )
    with pytest.raises(CapabilityPackageError):
        verify_capability_package_source(source_root, generation)


def test_verify_refuses_symlinked_file(tmp_path: Path) -> None:
    source_root, generation = _generation(tmp_path)
    path = source_root / "plugins/example-operator/references/boundary.md"
    replacement = tmp_path / "replacement"
    replacement.write_bytes(path.read_bytes())
    path.unlink()
    path.symlink_to(replacement)
    with pytest.raises(CapabilityPackageError, match="symlink"):
        verify_capability_package_source(source_root, generation)


def test_verify_refuses_hardlinked_file(tmp_path: Path) -> None:
    source_root, generation = _generation(tmp_path)
    path = source_root / "plugins/example-operator/references/boundary.md"
    os.link(path, tmp_path / "hardlink")
    with pytest.raises(CapabilityPackageError, match="link count"):
        verify_capability_package_source(source_root, generation)


def test_verify_refuses_fifo(tmp_path: Path) -> None:
    source_root, generation = _generation(tmp_path)
    os.mkfifo(source_root / "plugins/example-operator/extra.fifo")
    with pytest.raises(CapabilityPackageError, match="non-regular"):
        verify_capability_package_source(source_root, generation)


@pytest.mark.parametrize("mutation", ["extra", "missing", "content", "mode"])
def test_verify_refuses_tree_and_file_drift(tmp_path: Path, mutation: str) -> None:
    source_root, generation = _generation(tmp_path)
    package_root = source_root / "plugins/example-operator"
    if mutation == "extra":
        (package_root / "extra.txt").write_text("x", encoding="utf-8")
    elif mutation == "missing":
        (package_root / "references/boundary.md").unlink()
    elif mutation == "content":
        (package_root / "references/boundary.md").write_bytes(b"shared boundarz\n")
    else:
        (package_root / "references/boundary.md").chmod(0o755)
    with pytest.raises(CapabilityPackageError):
        verify_capability_package_source(source_root, generation)


def test_verify_terminal_recensus_detects_insertion(tmp_path: Path) -> None:
    source_root, generation = _generation(tmp_path)
    extra = source_root / "plugins/example-operator/extra.txt"
    with pytest.raises(CapabilityPackageError, match="changed after"):
        package_module._verify_capability_package_source(
            source_root,
            generation,
            before_final_census=lambda: extra.write_text("race", encoding="utf-8"),
        )


def test_verify_terminal_file_identity_detects_replacement(tmp_path: Path) -> None:
    source_root, generation = _generation(tmp_path)
    target = source_root / "plugins/example-operator/references/boundary.md"

    def replace() -> None:
        replacement = target.with_suffix(".replacement")
        replacement.write_bytes(target.read_bytes())
        replacement.chmod(0o644)
        os.replace(replacement, target)

    with pytest.raises(CapabilityPackageError):
        package_module._verify_capability_package_source(
            source_root,
            generation,
            before_final_census=replace,
        )


def test_verifier_closes_descriptors_on_success_and_refusal(tmp_path: Path) -> None:
    fd_root = Path("/proc/self/fd")
    if not fd_root.exists():
        pytest.skip("Linux descriptor census unavailable")
    source_root, generation = _generation(tmp_path)
    before = len(list(fd_root.iterdir()))
    verify_capability_package_source(source_root, generation)
    after_success = len(list(fd_root.iterdir()))
    (source_root / "plugins/example-operator/extra.txt").write_text("x", encoding="utf-8")
    with pytest.raises(CapabilityPackageError):
        verify_capability_package_source(source_root, generation)
    after_refusal = len(list(fd_root.iterdir()))
    assert after_success <= before + 1
    assert after_refusal <= before + 1

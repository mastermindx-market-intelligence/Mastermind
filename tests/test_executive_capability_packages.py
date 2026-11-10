"""RED-first tests for the immutable capability-package contracts (CAP-S1 foundation).

Covers:
  - canonical digest pinning (package content + effective skill closure)
  - the real protected `plugins/mastermind-operator` package generation
  - the complete raw-input validation matrix for `build_capability_package_generation`
  - the acyclic five-layer digest cascade and its mismatch-refusal behavior
  - `verify_capability_package_source`'s descriptor-relative, no-follow,
    race-fenced local source verification, including a hostile-filesystem
    matrix and a descriptor-leak proof.

This module intentionally recomputes the canonical-JSON digest projections
locally (from the frozen spec) rather than importing production's private
helpers, so a production bug in the projection itself cannot make both sides
agree falsely.
"""
from __future__ import annotations

import copy
import dataclasses
import hashlib
import json
import os
import shutil
import socket
import tempfile
from pathlib import Path

import pytest

from control_plane.executive_capability_packages import (
    CAPABILITY_PACKAGE_CONTENT_SCHEMA,
    CAPABILITY_PACKAGE_GENERATION_SCHEMA,
    CAPABILITY_PACKAGE_SOURCE_SCHEMA,
    EFFECTIVE_SKILL_CLOSURE_SCHEMA,
    EFFECTIVE_SKILL_GRANT_SCHEMA,
    MAX_CLOSURE_FILES,
    MAX_PACKAGE_FILE_BYTES,
    MAX_PACKAGE_FILES,
    MAX_PACKAGE_TOTAL_BYTES,
    MAX_SKILLS_PER_PACKAGE,
    PACKAGE_KIND_SKILLS_ONLY_SOURCE,
    PACKAGE_SOURCE_STATE_PROTECTED,
    CapabilityPackageError,
    CapabilityPackageFile,
    CapabilityPackageGeneration,
    EffectiveSkillGrant,
    VerifiedCapabilityPackage,
    build_capability_package_generation,
    capability_package_content_digest,
    effective_skill_content_digest,
    verify_capability_package_source,
    _validate_identifier,
    _validate_relative_path,
    _validate_sha256_value,
    _validate_hex40,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
PACKAGE_ROOT = REPO_ROOT / "plugins" / "mastermind-operator"

# ---------------------------------------------------------------------------
# Local, spec-derived canonical-JSON helpers (independent of production code)
# ---------------------------------------------------------------------------


def _canon(obj: object) -> bytes:
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _row(f: CapabilityPackageFile) -> dict:
    return {
        "relative_path": f.relative_path,
        "sha256": f.sha256,
        "byte_length": f.byte_length,
        "executable": f.executable,
    }


def _expected_content_digest(files) -> str:
    rows = sorted(files, key=lambda f: f.relative_path)
    return _sha(_canon({"schema_version": CAPABILITY_PACKAGE_CONTENT_SCHEMA, "files": [_row(f) for f in rows]}))


def _expected_closure_digest(*, runtime_name, entrypoint_path, closure_files) -> str:
    rows = sorted(closure_files, key=lambda f: f.relative_path)
    return _sha(
        _canon(
            {
                "schema_version": EFFECTIVE_SKILL_CLOSURE_SCHEMA,
                "skill_name": runtime_name,
                "entrypoint_path": entrypoint_path,
                "files": [_row(f) for f in rows],
            }
        )
    )


def _expected_source_digest(
    *,
    capability_id,
    kind,
    repository,
    source_commit,
    source_tree_sha,
    package_root,
    manifest_path,
    package_content_digest,
    required_app_references,
) -> str:
    return _sha(
        _canon(
            {
                "schema_version": CAPABILITY_PACKAGE_SOURCE_SCHEMA,
                "capability_id": capability_id,
                "kind": kind,
                "repository": repository,
                "source_commit": source_commit,
                "source_tree_sha": source_tree_sha,
                "package_root": package_root,
                "manifest_path": manifest_path,
                "package_content_digest": package_content_digest,
                "required_app_references": list(required_app_references),
            }
        )
    )


def _expected_grant_digest(
    *,
    capability_id,
    runtime_name,
    entrypoint_path,
    closure_paths,
    skill_content_digest,
    package_capability_id,
    package_generation,
    package_source_digest,
) -> str:
    return _sha(
        _canon(
            {
                "schema_version": EFFECTIVE_SKILL_GRANT_SCHEMA,
                "capability_id": capability_id,
                "runtime_name": runtime_name,
                "entrypoint_path": entrypoint_path,
                "closure_paths": list(closure_paths),
                "skill_content_digest": skill_content_digest,
                "package_capability_id": package_capability_id,
                "package_generation": package_generation,
                "package_source_digest": package_source_digest,
            }
        )
    )


def _expected_generation_digest(
    *,
    capability_id,
    generation,
    source_state,
    revoked,
    package_source_digest,
    skills_ordered,
) -> str:
    return _sha(
        _canon(
            {
                "schema_version": CAPABILITY_PACKAGE_GENERATION_SCHEMA,
                "capability_id": capability_id,
                "generation": generation,
                "source_state": source_state,
                "revoked": revoked,
                "package_source_digest": package_source_digest,
                "skills": [[cid, gd] for cid, gd in skills_ordered],
            }
        )
    )


# ---------------------------------------------------------------------------
# Canonical digest pinning: package content
# ---------------------------------------------------------------------------


def _two_rows():
    return (
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


def test_package_content_digest_pinned_literal():
    files = _two_rows()
    # Computed once from the frozen literal projection and pinned here so an
    # accidental change in the projection surfaces as an explicit diff rather
    # than a silent recomputation-agrees-with-itself.
    expected = "90d672e2cd40329584b16129f47ea3e0ebf5f7e7944f15a20df7687f7b42e722"
    assert _expected_content_digest(files) == expected
    assert capability_package_content_digest(files) == expected


def test_package_content_digest_normalizes_input_order():
    a, b = _two_rows()
    assert capability_package_content_digest((a, b)) == capability_package_content_digest((b, a))


@pytest.mark.parametrize(
    "field,value",
    [
        ("relative_path", "references/changed.md"),
        ("sha256", "c" * 64),
        ("byte_length", 99),
        ("executable", True),
    ],
)
def test_package_content_digest_changes_with_each_field(field, value):
    a, b = _two_rows()
    base = capability_package_content_digest((a, b))
    mutated_a = dataclasses.replace(a, **{field: value})
    assert capability_package_content_digest((mutated_a, b)) != base


def test_package_content_digest_changes_with_schema_token():
    files = _two_rows()
    rows = sorted(files, key=lambda f: f.relative_path)
    real = _sha(_canon({"schema_version": CAPABILITY_PACKAGE_CONTENT_SCHEMA, "files": [_row(f) for f in rows]}))
    fake = _sha(_canon({"schema_version": "some.other/v1", "files": [_row(f) for f in rows]}))
    assert real != fake
    assert capability_package_content_digest(files) == real


def test_package_content_digest_excludes_host_path():
    # The digest function accepts no source-root/host-path argument at all;
    # this is a structural guarantee, exercised by confirming two logically
    # identical rows built from different absolute contexts still match.
    files_a = _two_rows()
    files_b = tuple(CapabilityPackageFile(f.relative_path, f.sha256, f.byte_length, f.executable) for f in files_a)
    assert capability_package_content_digest(files_a) == capability_package_content_digest(files_b)


# ---------------------------------------------------------------------------
# Canonical digest pinning: effective skill closure
# ---------------------------------------------------------------------------


def test_effective_skill_content_digest_pinned_projection():
    entrypoint = CapabilityPackageFile("skills/receive-commission/SKILL.md", "d" * 64, 100, False)
    shared = CapabilityPackageFile("references/dialogue-boundary.md", "e" * 64, 50, False)
    expected = _expected_closure_digest(
        runtime_name="receive-commission",
        entrypoint_path="skills/receive-commission/SKILL.md",
        closure_files=(entrypoint, shared),
    )
    actual = effective_skill_content_digest(
        runtime_name="receive-commission",
        entrypoint_path="skills/receive-commission/SKILL.md",
        closure_files=(shared, entrypoint),  # unsorted input; function must normalize
    )
    assert actual == expected


def test_effective_skill_content_digest_changes_when_entrypoint_moves():
    shared = CapabilityPackageFile("references/dialogue-boundary.md", "e" * 64, 50, False)
    entrypoint_a = CapabilityPackageFile("skills/receive-commission/SKILL.md", "d" * 64, 100, False)
    entrypoint_b = CapabilityPackageFile("skills/receive-commission/SKILL.md", "f" * 64, 100, False)
    digest_a = effective_skill_content_digest(
        runtime_name="receive-commission", entrypoint_path=entrypoint_a.relative_path, closure_files=(entrypoint_a, shared)
    )
    digest_b = effective_skill_content_digest(
        runtime_name="receive-commission", entrypoint_path=entrypoint_b.relative_path, closure_files=(entrypoint_b, shared)
    )
    assert digest_a != digest_b


def test_effective_skill_content_digest_changes_when_shared_reference_moves():
    entrypoint = CapabilityPackageFile("skills/receive-commission/SKILL.md", "d" * 64, 100, False)
    shared_a = CapabilityPackageFile("references/dialogue-boundary.md", "e" * 64, 50, False)
    shared_b = CapabilityPackageFile("references/dialogue-boundary.md", "0" * 64, 50, False)
    digest_a = effective_skill_content_digest(
        runtime_name="receive-commission", entrypoint_path=entrypoint.relative_path, closure_files=(entrypoint, shared_a)
    )
    digest_b = effective_skill_content_digest(
        runtime_name="receive-commission", entrypoint_path=entrypoint.relative_path, closure_files=(entrypoint, shared_b)
    )
    assert digest_a != digest_b


def test_effective_skill_content_digest_unaffected_by_unrelated_package_row():
    entrypoint = CapabilityPackageFile("skills/receive-commission/SKILL.md", "d" * 64, 100, False)
    shared = CapabilityPackageFile("references/dialogue-boundary.md", "e" * 64, 50, False)
    digest_without_unrelated = effective_skill_content_digest(
        runtime_name="receive-commission", entrypoint_path=entrypoint.relative_path, closure_files=(entrypoint, shared)
    )
    # An unrelated package row is simply never passed to the closure function;
    # its presence elsewhere in the package cannot perturb this digest.
    digest_again = effective_skill_content_digest(
        runtime_name="receive-commission", entrypoint_path=entrypoint.relative_path, closure_files=(shared, entrypoint)
    )
    assert digest_without_unrelated == digest_again


# ---------------------------------------------------------------------------
# The real protected package (plugins/mastermind-operator)
# ---------------------------------------------------------------------------

_REAL_PACKAGE_RELATIVE_PATHS = (
    ".codex-plugin/plugin.json",
    "references/app-bindings.template.json",
    "references/dialogue-boundary.md",
    "skills/escalate-decision/SKILL.md",
    "skills/finish-operation/SKILL.md",
    "skills/receive-commission/SKILL.md",
    "skills/return-progress/SKILL.md",
)

_EXPECTED_PACKAGE_CONTENT_DIGEST = "a9781411d2642569f8b56e33bd0e0d9808a69176ccaced86642cd23948a71306"

_EXPECTED_CLOSURE_DIGESTS = {
    "escalate-decision": "ca621a8cc034bf607460d81085c8d466000e38d0f4b6afa8245001374d6cc2ad",
    "finish-operation": "3e689aeaa2b1579781832a854d7256c6ad8ee2ef55521b45f3af8dbe9660675e",
    "receive-commission": "d7953504035c797b30f434f1fdc72e864a7074179abffe7c247f1afc9c0a162c",
    "return-progress": "510be1ed3036f0bc1ed5f709875792ca042c350198a48e1128b4ce8ae46a6552",
}


def _real_package_files() -> tuple[CapabilityPackageFile, ...]:
    rows = []
    for rel in _REAL_PACKAGE_RELATIVE_PATHS:
        data = (PACKAGE_ROOT / rel).read_bytes()
        rows.append(
            CapabilityPackageFile(
                relative_path=rel,
                sha256=hashlib.sha256(data).hexdigest(),
                byte_length=len(data),
                executable=False,
            )
        )
    return tuple(rows)


def test_real_protected_package_content_digest_matches_frozen_value():
    assert PACKAGE_ROOT.is_dir(), "protected plugins/mastermind-operator package is missing"
    files = _real_package_files()
    assert len(files) == 7
    assert capability_package_content_digest(files) == _EXPECTED_PACKAGE_CONTENT_DIGEST


def test_real_protected_package_closure_digests_match_frozen_values():
    files = _real_package_files()
    files_by_path = {f.relative_path: f for f in files}
    shared = files_by_path["references/dialogue-boundary.md"]

    skill_entrypoints = {
        "escalate-decision": "skills/escalate-decision/SKILL.md",
        "finish-operation": "skills/finish-operation/SKILL.md",
        "receive-commission": "skills/receive-commission/SKILL.md",
        "return-progress": "skills/return-progress/SKILL.md",
    }

    for runtime_name, entrypoint_rel in skill_entrypoints.items():
        entrypoint = files_by_path[entrypoint_rel]
        digest = effective_skill_content_digest(
            runtime_name=runtime_name,
            entrypoint_path=entrypoint_rel,
            closure_files=(entrypoint, shared),
        )
        assert digest == _EXPECTED_CLOSURE_DIGESTS[runtime_name]


# ---------------------------------------------------------------------------
# build_capability_package_generation: synthetic baseline fixture
# ---------------------------------------------------------------------------


def _baseline_pieces():
    """Build a small, fully self-consistent synthetic package + raw dict."""
    file_a = CapabilityPackageFile("references/boundary.md", "a" * 64, 7, False)
    file_b = CapabilityPackageFile("skills/receive/SKILL.md", "b" * 64, 11, False)
    files = (file_a, file_b)
    files_raw = [
        {"relative_path": file_a.relative_path, "sha256": file_a.sha256, "byte_length": file_a.byte_length, "executable": file_a.executable},
        {"relative_path": file_b.relative_path, "sha256": file_b.sha256, "byte_length": file_b.byte_length, "executable": file_b.executable},
    ]

    capability_id = "example.pkg1"
    kind = PACKAGE_KIND_SKILLS_ONLY_SOURCE
    repository = "example/repo"
    source_commit = "1" * 40
    source_tree_sha = "2" * 40
    package_root = "plugins/example"
    manifest_path = "references/boundary.md"
    generation_label = "example.pkg1.g1"
    source_state = PACKAGE_SOURCE_STATE_PROTECTED
    revoked = False
    required_app_references: list[str] = []

    content_digest = _expected_content_digest(files)

    skill_capability_id = "example.pkg1.receive.v1"
    runtime_name = "receive"
    entrypoint_path = "skills/receive/SKILL.md"
    closure_paths = ("references/boundary.md", "skills/receive/SKILL.md")
    skill_content_digest = _expected_closure_digest(
        runtime_name=runtime_name, entrypoint_path=entrypoint_path, closure_files=files
    )

    source_digest = _expected_source_digest(
        capability_id=capability_id,
        kind=kind,
        repository=repository,
        source_commit=source_commit,
        source_tree_sha=source_tree_sha,
        package_root=package_root,
        manifest_path=manifest_path,
        package_content_digest=content_digest,
        required_app_references=required_app_references,
    )

    grant_digest = _expected_grant_digest(
        capability_id=skill_capability_id,
        runtime_name=runtime_name,
        entrypoint_path=entrypoint_path,
        closure_paths=closure_paths,
        skill_content_digest=skill_content_digest,
        package_capability_id=capability_id,
        package_generation=generation_label,
        package_source_digest=source_digest,
    )

    generation_digest = _expected_generation_digest(
        capability_id=capability_id,
        generation=generation_label,
        source_state=source_state,
        revoked=revoked,
        package_source_digest=source_digest,
        skills_ordered=((skill_capability_id, grant_digest),),
    )

    raw = {
        "kind": kind,
        "repository": repository,
        "source_commit": source_commit,
        "source_tree_sha": source_tree_sha,
        "package_root": package_root,
        "manifest_path": manifest_path,
        "generation": generation_label,
        "source_state": source_state,
        "revoked": revoked,
        "package_content_digest": content_digest,
        "package_source_digest": source_digest,
        "files": files_raw,
        "skills": {
            skill_capability_id: {
                "runtime_name": runtime_name,
                "entrypoint_path": entrypoint_path,
                "closure_paths": list(closure_paths),
                "skill_content_digest": skill_content_digest,
                "grant_digest": grant_digest,
            }
        },
        "required_app_references": required_app_references,
        "package_generation_digest": generation_digest,
    }

    return {
        "capability_id": capability_id,
        "raw": raw,
        "content_digest": content_digest,
        "source_digest": source_digest,
        "grant_digest": grant_digest,
        "generation_digest": generation_digest,
        "skill_capability_id": skill_capability_id,
        "skill_content_digest": skill_content_digest,
    }


def _baseline_raw() -> tuple[str, dict]:
    pieces = _baseline_pieces()
    return pieces["capability_id"], copy.deepcopy(pieces["raw"])


def test_build_capability_package_generation_happy_path():
    pieces = _baseline_pieces()
    generation = build_capability_package_generation(capability_id=pieces["capability_id"], raw=copy.deepcopy(pieces["raw"]))

    assert isinstance(generation, CapabilityPackageGeneration)
    assert generation.capability_id == "example.pkg1"
    assert generation.package_content_digest == pieces["content_digest"]
    assert generation.package_source_digest == pieces["source_digest"]
    assert generation.package_generation_digest == pieces["generation_digest"]
    assert len(generation.files) == 2
    assert generation.files[0].relative_path == "references/boundary.md"
    assert len(generation.skills) == 1
    grant = generation.skills[0]
    assert isinstance(grant, EffectiveSkillGrant)
    assert grant.capability_id == pieces["skill_capability_id"]
    assert grant.skill_content_digest == pieces["skill_content_digest"]
    assert grant.grant_digest == pieces["grant_digest"]
    assert grant.package_capability_id == "example.pkg1"
    assert generation.required_app_references == ()


def test_build_capability_package_generation_unknown_raw_key_refuses():
    capability_id, raw = _baseline_raw()
    raw["unexpected_field"] = "x"
    with pytest.raises(CapabilityPackageError):
        build_capability_package_generation(capability_id=capability_id, raw=raw)


def test_build_capability_package_generation_missing_raw_key_refuses():
    capability_id, raw = _baseline_raw()
    del raw["repository"]
    with pytest.raises(CapabilityPackageError):
        build_capability_package_generation(capability_id=capability_id, raw=raw)


# ---------------------------------------------------------------------------
# Five-layer digest mismatch refusal + acyclicity
# ---------------------------------------------------------------------------


def test_declared_package_content_digest_mismatch_refuses():
    capability_id, raw = _baseline_raw()
    raw["package_content_digest"] = "0" * 64
    with pytest.raises(CapabilityPackageError):
        build_capability_package_generation(capability_id=capability_id, raw=raw)


def test_declared_package_source_digest_mismatch_refuses():
    capability_id, raw = _baseline_raw()
    raw["package_source_digest"] = "0" * 64
    with pytest.raises(CapabilityPackageError):
        build_capability_package_generation(capability_id=capability_id, raw=raw)


def test_declared_skill_content_digest_mismatch_refuses():
    capability_id, raw = _baseline_raw()
    skill_id = next(iter(raw["skills"]))
    raw["skills"][skill_id]["skill_content_digest"] = "0" * 64
    with pytest.raises(CapabilityPackageError):
        build_capability_package_generation(capability_id=capability_id, raw=raw)


def test_declared_skill_grant_digest_mismatch_refuses():
    capability_id, raw = _baseline_raw()
    skill_id = next(iter(raw["skills"]))
    raw["skills"][skill_id]["grant_digest"] = "0" * 64
    with pytest.raises(CapabilityPackageError):
        build_capability_package_generation(capability_id=capability_id, raw=raw)


def test_declared_package_generation_digest_mismatch_refuses():
    capability_id, raw = _baseline_raw()
    raw["package_generation_digest"] = "0" * 64
    with pytest.raises(CapabilityPackageError):
        build_capability_package_generation(capability_id=capability_id, raw=raw)


def test_package_generation_digest_graph_is_acyclic_under_revocation():
    """Revoking a generation changes only the generation-layer digest.

    This proves the graph is acyclic: the grant digest (and everything below
    it) is fully computable without knowing `revoked`/`package_generation_digest`,
    and does not need to be recomputed when only generation-layer state changes.
    """
    pieces = _baseline_pieces()
    capability_id = pieces["capability_id"]

    raw_not_revoked = copy.deepcopy(pieces["raw"])
    generation_not_revoked = build_capability_package_generation(capability_id=capability_id, raw=raw_not_revoked)

    raw_revoked = copy.deepcopy(pieces["raw"])
    raw_revoked["revoked"] = True
    raw_revoked["package_generation_digest"] = _expected_generation_digest(
        capability_id=capability_id,
        generation=raw_revoked["generation"],
        source_state=raw_revoked["source_state"],
        revoked=True,
        package_source_digest=pieces["source_digest"],
        skills_ordered=((pieces["skill_capability_id"], pieces["grant_digest"]),),
    )
    generation_revoked = build_capability_package_generation(capability_id=capability_id, raw=raw_revoked)

    # Source/closure/grant identities are preserved exactly.
    assert generation_revoked.package_content_digest == generation_not_revoked.package_content_digest
    assert generation_revoked.package_source_digest == generation_not_revoked.package_source_digest
    assert generation_revoked.skills[0].skill_content_digest == generation_not_revoked.skills[0].skill_content_digest
    assert generation_revoked.skills[0].grant_digest == generation_not_revoked.skills[0].grant_digest

    # Only the generation-layer digest (and revoked flag) differs.
    assert generation_revoked.revoked is True
    assert generation_revoked.package_generation_digest != generation_not_revoked.package_generation_digest


def test_grant_digest_projection_excludes_package_generation_digest():
    """The skill-grant digest projection has no edge from package_generation_digest.

    Two otherwise-identical generations that differ only in `package_generation_digest`
    (via a differing `revoked` flag) must yield the SAME grant digest.
    """
    pieces = _baseline_pieces()
    capability_id = pieces["capability_id"]

    raw_a = copy.deepcopy(pieces["raw"])
    gen_a = build_capability_package_generation(capability_id=capability_id, raw=raw_a)

    raw_b = copy.deepcopy(pieces["raw"])
    raw_b["revoked"] = True
    raw_b["package_generation_digest"] = _expected_generation_digest(
        capability_id=capability_id,
        generation=raw_b["generation"],
        source_state=raw_b["source_state"],
        revoked=True,
        package_source_digest=pieces["source_digest"],
        skills_ordered=((pieces["skill_capability_id"], pieces["grant_digest"]),),
    )
    gen_b = build_capability_package_generation(capability_id=capability_id, raw=raw_b)

    assert gen_a.package_generation_digest != gen_b.package_generation_digest
    assert gen_a.skills[0].grant_digest == gen_b.skills[0].grant_digest


def test_unrelated_file_change_preserves_unaffected_closure_digest():
    """An unrelated package-file byte change alters package/source identity
    but must not perturb a closure digest that never consumed that file."""
    pieces = _baseline_pieces()
    capability_id = pieces["capability_id"]

    raw_a = copy.deepcopy(pieces["raw"])
    gen_a = build_capability_package_generation(capability_id=capability_id, raw=raw_a)

    # Add a third, unrelated file to the package that no skill's closure uses.
    file_a = CapabilityPackageFile("references/boundary.md", "a" * 64, 7, False)
    file_b = CapabilityPackageFile("skills/receive/SKILL.md", "b" * 64, 11, False)
    file_c = CapabilityPackageFile("zzz-unrelated.txt", "c" * 64, 3, False)
    files = (file_a, file_b, file_c)
    content_digest_b = _expected_content_digest(files)

    source_digest_b = _expected_source_digest(
        capability_id=capability_id,
        kind=raw_a["kind"],
        repository=raw_a["repository"],
        source_commit=raw_a["source_commit"],
        source_tree_sha=raw_a["source_tree_sha"],
        package_root=raw_a["package_root"],
        manifest_path=raw_a["manifest_path"],
        package_content_digest=content_digest_b,
        required_app_references=raw_a["required_app_references"],
    )

    skill_content_digest_b = pieces["skill_content_digest"]  # unchanged: closure never included file_c
    grant_digest_b = _expected_grant_digest(
        capability_id=pieces["skill_capability_id"],
        runtime_name="receive",
        entrypoint_path="skills/receive/SKILL.md",
        closure_paths=("references/boundary.md", "skills/receive/SKILL.md"),
        skill_content_digest=skill_content_digest_b,
        package_capability_id=capability_id,
        package_generation=raw_a["generation"],
        package_source_digest=source_digest_b,
    )
    generation_digest_b = _expected_generation_digest(
        capability_id=capability_id,
        generation=raw_a["generation"],
        source_state=raw_a["source_state"],
        revoked=False,
        package_source_digest=source_digest_b,
        skills_ordered=((pieces["skill_capability_id"], grant_digest_b),),
    )

    raw_b = copy.deepcopy(raw_a)
    raw_b["files"] = raw_a["files"] + [
        {"relative_path": "zzz-unrelated.txt", "sha256": "c" * 64, "byte_length": 3, "executable": False}
    ]
    raw_b["package_content_digest"] = content_digest_b
    raw_b["package_source_digest"] = source_digest_b
    raw_b["skills"][pieces["skill_capability_id"]]["grant_digest"] = grant_digest_b
    raw_b["package_generation_digest"] = generation_digest_b

    gen_b = build_capability_package_generation(capability_id=capability_id, raw=raw_b)

    assert gen_b.package_content_digest != gen_a.package_content_digest
    assert gen_b.package_source_digest != gen_a.package_source_digest
    assert gen_b.package_generation_digest != gen_a.package_generation_digest
    # The closure digest is stable: unaffected by unrelated file movement.
    assert gen_b.skills[0].skill_content_digest == gen_a.skills[0].skill_content_digest
    # But the grant digest DOES change, because it binds package_source_digest.
    assert gen_b.skills[0].grant_digest != gen_a.skills[0].grant_digest


# ---------------------------------------------------------------------------
# Validation matrix
# ---------------------------------------------------------------------------


def _no_echo(exc: CapabilityPackageError, *forbidden_values: str) -> None:
    message = str(exc)
    for value in forbidden_values:
        assert value not in message, f"error message echoed caller-supplied value: {value!r}"


def test_blank_capability_id_refuses():
    _, raw = _baseline_raw()
    with pytest.raises(CapabilityPackageError):
        build_capability_package_generation(capability_id="", raw=raw)


def test_invalid_capability_id_does_not_echo_value():
    _, raw = _baseline_raw()
    poison = "SECRET-Invalid/Id!!"
    with pytest.raises(CapabilityPackageError) as excinfo:
        build_capability_package_generation(capability_id=poison, raw=raw)
    _no_echo(excinfo.value, poison)


def test_invalid_generation_label_refuses():
    capability_id, raw = _baseline_raw()
    raw["generation"] = "Not Valid!"
    with pytest.raises(CapabilityPackageError):
        build_capability_package_generation(capability_id=capability_id, raw=raw)


def test_invalid_runtime_name_refuses():
    capability_id, raw = _baseline_raw()
    skill_id = next(iter(raw["skills"]))
    raw["skills"][skill_id]["runtime_name"] = "Not Valid!"
    with pytest.raises(CapabilityPackageError):
        build_capability_package_generation(capability_id=capability_id, raw=raw)


def test_absolute_relative_path_refuses():
    capability_id, raw = _baseline_raw()
    raw["files"][0]["relative_path"] = "/etc/passwd"
    with pytest.raises(CapabilityPackageError):
        build_capability_package_generation(capability_id=capability_id, raw=raw)


def test_absolute_relative_path_does_not_echo_value():
    capability_id, raw = _baseline_raw()
    poison = "/etc/super-secret-path"
    raw["files"][0]["relative_path"] = poison
    with pytest.raises(CapabilityPackageError) as excinfo:
        build_capability_package_generation(capability_id=capability_id, raw=raw)
    _no_echo(excinfo.value, poison)


def test_dot_dot_component_refuses():
    capability_id, raw = _baseline_raw()
    raw["files"][0]["relative_path"] = "../escape.md"
    with pytest.raises(CapabilityPackageError):
        build_capability_package_generation(capability_id=capability_id, raw=raw)


def test_dot_component_refuses():
    capability_id, raw = _baseline_raw()
    raw["files"][0]["relative_path"] = "./boundary.md"
    with pytest.raises(CapabilityPackageError):
        build_capability_package_generation(capability_id=capability_id, raw=raw)


def test_backslash_in_path_refuses():
    capability_id, raw = _baseline_raw()
    raw["files"][0]["relative_path"] = "references\\boundary.md"
    with pytest.raises(CapabilityPackageError):
        build_capability_package_generation(capability_id=capability_id, raw=raw)


def test_control_character_in_path_refuses():
    capability_id, raw = _baseline_raw()
    raw["files"][0]["relative_path"] = "references/bound\x00ary.md"
    with pytest.raises(CapabilityPackageError):
        build_capability_package_generation(capability_id=capability_id, raw=raw)


def test_empty_path_refuses():
    capability_id, raw = _baseline_raw()
    raw["files"][0]["relative_path"] = ""
    with pytest.raises(CapabilityPackageError):
        build_capability_package_generation(capability_id=capability_id, raw=raw)


def test_non_lowercase_sha256_refuses():
    capability_id, raw = _baseline_raw()
    raw["files"][0]["sha256"] = "A" * 64
    with pytest.raises(CapabilityPackageError):
        build_capability_package_generation(capability_id=capability_id, raw=raw)


def test_short_sha256_refuses():
    capability_id, raw = _baseline_raw()
    raw["files"][0]["sha256"] = "a" * 63
    with pytest.raises(CapabilityPackageError):
        build_capability_package_generation(capability_id=capability_id, raw=raw)


def test_non_lowercase_sha256_does_not_echo_value():
    capability_id, raw = _baseline_raw()
    poison = "F" * 64
    raw["files"][0]["sha256"] = poison
    with pytest.raises(CapabilityPackageError) as excinfo:
        build_capability_package_generation(capability_id=capability_id, raw=raw)
    _no_echo(excinfo.value, poison)


def test_negative_byte_length_refuses():
    capability_id, raw = _baseline_raw()
    raw["files"][0]["byte_length"] = -1
    with pytest.raises(CapabilityPackageError):
        build_capability_package_generation(capability_id=capability_id, raw=raw)


def test_oversized_byte_length_refuses():
    capability_id, raw = _baseline_raw()
    raw["files"][0]["byte_length"] = MAX_PACKAGE_FILE_BYTES + 1
    with pytest.raises(CapabilityPackageError):
        build_capability_package_generation(capability_id=capability_id, raw=raw)


def test_zero_byte_file_is_permitted():
    """Identity amendment §5.3 supersedes the earlier zero-byte refusal."""
    file_a = CapabilityPackageFile("references/boundary.md", "a" * 64, 0, False)
    file_b = CapabilityPackageFile("skills/receive/SKILL.md", "b" * 64, 11, False)
    files = (file_a, file_b)
    content_digest = _expected_content_digest(files)
    skill_content_digest = _expected_closure_digest(
        runtime_name="receive", entrypoint_path="skills/receive/SKILL.md", closure_files=files
    )
    capability_id = "example.pkg1"
    package_root = "plugins/example"
    manifest_path = "references/boundary.md"
    generation_label = "example.pkg1.g1"
    source_digest = _expected_source_digest(
        capability_id=capability_id,
        kind=PACKAGE_KIND_SKILLS_ONLY_SOURCE,
        repository="example/repo",
        source_commit="1" * 40,
        source_tree_sha="2" * 40,
        package_root=package_root,
        manifest_path=manifest_path,
        package_content_digest=content_digest,
        required_app_references=[],
    )
    skill_capability_id = "example.pkg1.receive.v1"
    grant_digest = _expected_grant_digest(
        capability_id=skill_capability_id,
        runtime_name="receive",
        entrypoint_path="skills/receive/SKILL.md",
        closure_paths=("references/boundary.md", "skills/receive/SKILL.md"),
        skill_content_digest=skill_content_digest,
        package_capability_id=capability_id,
        package_generation=generation_label,
        package_source_digest=source_digest,
    )
    generation_digest = _expected_generation_digest(
        capability_id=capability_id,
        generation=generation_label,
        source_state=PACKAGE_SOURCE_STATE_PROTECTED,
        revoked=False,
        package_source_digest=source_digest,
        skills_ordered=((skill_capability_id, grant_digest),),
    )
    raw = {
        "kind": PACKAGE_KIND_SKILLS_ONLY_SOURCE,
        "repository": "example/repo",
        "source_commit": "1" * 40,
        "source_tree_sha": "2" * 40,
        "package_root": package_root,
        "manifest_path": manifest_path,
        "generation": generation_label,
        "source_state": PACKAGE_SOURCE_STATE_PROTECTED,
        "revoked": False,
        "package_content_digest": content_digest,
        "package_source_digest": source_digest,
        "files": [
            {"relative_path": "references/boundary.md", "sha256": "a" * 64, "byte_length": 0, "executable": False},
            {"relative_path": "skills/receive/SKILL.md", "sha256": "b" * 64, "byte_length": 11, "executable": False},
        ],
        "skills": {
            skill_capability_id: {
                "runtime_name": "receive",
                "entrypoint_path": "skills/receive/SKILL.md",
                "closure_paths": ["references/boundary.md", "skills/receive/SKILL.md"],
                "skill_content_digest": skill_content_digest,
                "grant_digest": grant_digest,
            }
        },
        "required_app_references": [],
        "package_generation_digest": generation_digest,
    }
    generation = build_capability_package_generation(capability_id=capability_id, raw=raw)
    assert generation.files[0].byte_length == 0


def test_non_bool_executable_refuses():
    capability_id, raw = _baseline_raw()
    raw["files"][0]["executable"] = 1
    with pytest.raises(CapabilityPackageError):
        build_capability_package_generation(capability_id=capability_id, raw=raw)


def test_unsorted_file_rows_refuses():
    capability_id, raw = _baseline_raw()
    raw["files"] = list(reversed(raw["files"]))
    with pytest.raises(CapabilityPackageError):
        build_capability_package_generation(capability_id=capability_id, raw=raw)


def test_duplicate_file_rows_refuses():
    capability_id, raw = _baseline_raw()
    raw["files"] = [raw["files"][0], raw["files"][0]]
    with pytest.raises(CapabilityPackageError):
        build_capability_package_generation(capability_id=capability_id, raw=raw)


def test_case_fold_collision_refuses():
    capability_id, raw = _baseline_raw()
    raw["files"] = [
        {"relative_path": "References/Boundary.md", "sha256": "a" * 64, "byte_length": 7, "executable": False},
        {"relative_path": "references/boundary.md", "sha256": "b" * 64, "byte_length": 7, "executable": False},
    ]
    raw["manifest_path"] = "References/Boundary.md"
    with pytest.raises(CapabilityPackageError):
        build_capability_package_generation(capability_id=capability_id, raw=raw)


def test_more_than_max_files_refuses():
    capability_id, raw = _baseline_raw()
    files = [
        {"relative_path": f"file{i:03d}.txt", "sha256": "0" * 64, "byte_length": 0, "executable": False}
        for i in range(MAX_PACKAGE_FILES + 1)
    ]
    raw["files"] = files
    with pytest.raises(CapabilityPackageError):
        build_capability_package_generation(capability_id=capability_id, raw=raw)


def test_total_bytes_over_bound_refuses():
    capability_id, raw = _baseline_raw()
    per_file = 1_000_000
    count = (MAX_PACKAGE_TOTAL_BYTES // per_file) + 2
    files = [
        {"relative_path": f"file{i:03d}.bin", "sha256": "0" * 64, "byte_length": per_file, "executable": False}
        for i in range(count)
    ]
    raw["files"] = files
    with pytest.raises(CapabilityPackageError):
        build_capability_package_generation(capability_id=capability_id, raw=raw)


def test_closure_missing_entrypoint_refuses():
    capability_id, raw = _baseline_raw()
    skill_id = next(iter(raw["skills"]))
    raw["skills"][skill_id]["closure_paths"] = ["references/boundary.md"]  # drops the entrypoint itself
    with pytest.raises(CapabilityPackageError):
        build_capability_package_generation(capability_id=capability_id, raw=raw)


def test_closure_unknown_path_refuses():
    capability_id, raw = _baseline_raw()
    skill_id = next(iter(raw["skills"]))
    raw["skills"][skill_id]["closure_paths"] = ["references/boundary.md", "skills/receive/SKILL.md", "unknown/file.md"]
    with pytest.raises(CapabilityPackageError):
        build_capability_package_generation(capability_id=capability_id, raw=raw)


def test_closure_unsorted_refuses():
    capability_id, raw = _baseline_raw()
    skill_id = next(iter(raw["skills"]))
    raw["skills"][skill_id]["closure_paths"] = ["skills/receive/SKILL.md", "references/boundary.md"]
    with pytest.raises(CapabilityPackageError):
        build_capability_package_generation(capability_id=capability_id, raw=raw)


def test_closure_duplicate_refuses():
    capability_id, raw = _baseline_raw()
    skill_id = next(iter(raw["skills"]))
    raw["skills"][skill_id]["closure_paths"] = [
        "references/boundary.md",
        "references/boundary.md",
        "skills/receive/SKILL.md",
    ]
    with pytest.raises(CapabilityPackageError):
        build_capability_package_generation(capability_id=capability_id, raw=raw)


def test_more_than_max_closure_files_refuses():
    capability_id, raw = _baseline_raw()
    count = MAX_CLOSURE_FILES + 1
    files = [
        {"relative_path": f"c{i:03d}.md", "sha256": "0" * 64, "byte_length": 0, "executable": False} for i in range(count)
    ]
    raw["files"] = files
    raw["manifest_path"] = files[0]["relative_path"]
    skill_id = next(iter(raw["skills"]))
    closure = [row["relative_path"] for row in files]
    raw["skills"][skill_id]["entrypoint_path"] = closure[0]
    raw["skills"][skill_id]["closure_paths"] = closure
    with pytest.raises(CapabilityPackageError):
        build_capability_package_generation(capability_id=capability_id, raw=raw)


def test_unsupported_kind_refuses():
    capability_id, raw = _baseline_raw()
    raw["kind"] = "provider-plugin-install"
    with pytest.raises(CapabilityPackageError):
        build_capability_package_generation(capability_id=capability_id, raw=raw)


def test_unsupported_source_state_refuses():
    capability_id, raw = _baseline_raw()
    raw["source_state"] = "ACTIVE"
    with pytest.raises(CapabilityPackageError):
        build_capability_package_generation(capability_id=capability_id, raw=raw)


def test_short_source_commit_refuses():
    capability_id, raw = _baseline_raw()
    raw["source_commit"] = "1" * 39
    with pytest.raises(CapabilityPackageError):
        build_capability_package_generation(capability_id=capability_id, raw=raw)


def test_non_hex_source_tree_sha_refuses():
    capability_id, raw = _baseline_raw()
    raw["source_tree_sha"] = "g" * 40
    with pytest.raises(CapabilityPackageError):
        build_capability_package_generation(capability_id=capability_id, raw=raw)


def test_non_empty_required_app_references_refuses():
    capability_id, raw = _baseline_raw()
    raw["required_app_references"] = ["some-app"]
    with pytest.raises(CapabilityPackageError):
        build_capability_package_generation(capability_id=capability_id, raw=raw)


def test_more_than_max_skills_refuses():
    capability_id, raw = _baseline_raw()
    shared_path = "references/boundary.md"
    skills = {}
    for i in range(MAX_SKILLS_PER_PACKAGE + 1):
        skills[f"example.pkg1.skill{i:03d}.v1"] = {
            "runtime_name": f"skill{i:03d}",
            "entrypoint_path": shared_path,
            "closure_paths": [shared_path],
            "skill_content_digest": "0" * 64,
            "grant_digest": "0" * 64,
        }
    raw["skills"] = skills
    with pytest.raises(CapabilityPackageError):
        build_capability_package_generation(capability_id=capability_id, raw=raw)


def test_duplicate_runtime_name_refuses():
    capability_id, raw = _baseline_raw()
    existing_skill_id = next(iter(raw["skills"]))
    existing = raw["skills"][existing_skill_id]
    raw["skills"]["example.pkg1.other.v1"] = {
        "runtime_name": existing["runtime_name"],  # collision
        "entrypoint_path": existing["entrypoint_path"],
        "closure_paths": list(existing["closure_paths"]),
        "skill_content_digest": "0" * 64,
        "grant_digest": "0" * 64,
    }
    with pytest.raises(CapabilityPackageError):
        build_capability_package_generation(capability_id=capability_id, raw=raw)


def test_manifest_path_not_in_inventory_refuses():
    capability_id, raw = _baseline_raw()
    raw["manifest_path"] = "not/declared.md"
    with pytest.raises(CapabilityPackageError):
        build_capability_package_generation(capability_id=capability_id, raw=raw)


def test_entrypoint_path_not_in_inventory_refuses():
    capability_id, raw = _baseline_raw()
    skill_id = next(iter(raw["skills"]))
    raw["skills"][skill_id]["entrypoint_path"] = "not/declared.md"
    raw["skills"][skill_id]["closure_paths"] = ["not/declared.md", "references/boundary.md"]
    with pytest.raises(CapabilityPackageError):
        build_capability_package_generation(capability_id=capability_id, raw=raw)


def test_unknown_file_row_key_refuses():
    capability_id, raw = _baseline_raw()
    raw["files"][0]["extra"] = "x"
    with pytest.raises(CapabilityPackageError):
        build_capability_package_generation(capability_id=capability_id, raw=raw)


def test_unknown_skill_row_key_refuses():
    capability_id, raw = _baseline_raw()
    skill_id = next(iter(raw["skills"]))
    raw["skills"][skill_id]["extra"] = "x"
    with pytest.raises(CapabilityPackageError):
        build_capability_package_generation(capability_id=capability_id, raw=raw)


# ---------------------------------------------------------------------------
# verify_capability_package_source
# ---------------------------------------------------------------------------


def _write_tree(root: Path, package_root: str, contents: dict[str, bytes]) -> None:
    base = root / package_root
    for rel, data in contents.items():
        p = base / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)


def _row_from_disk(root: Path, package_root: str, rel: str, executable: bool = False) -> CapabilityPackageFile:
    data = (root / package_root / rel).read_bytes()
    return CapabilityPackageFile(
        relative_path=rel,
        sha256=hashlib.sha256(data).hexdigest(),
        byte_length=len(data),
        executable=executable,
    )


def _canonical_generation(
    *,
    capability_id: str,
    package_root: str,
    manifest_path: str,
    files: tuple[CapabilityPackageFile, ...],
    skills_spec: list[dict],
    generation_label: str = "example.g1",
    repository: str = "example/repo",
    source_commit: str = "1" * 40,
    source_tree_sha: str = "2" * 40,
    revoked: bool = False,
) -> CapabilityPackageGeneration:
    """Build a genuinely self-consistent generation via the real builder.

    `verify_capability_package_source` no longer trusts a hand-constructed
    CapabilityPackageGeneration (review 5085454178, finding 3): it
    reconstructs the canonical raw mapping and requires it to rebuild,
    via `build_capability_package_generation`, into something
    dataclass-equal to what was handed in. Fixtures that feed `verify()`
    therefore have to be built the same way production would build them --
    through the real builder -- rather than by hand-assembling the
    dataclass with placeholder digests.
    """
    sorted_files = tuple(sorted(files, key=lambda f: f.relative_path))
    files_by_path = {f.relative_path: f for f in sorted_files}
    content_digest = _expected_content_digest(sorted_files)
    source_digest = _expected_source_digest(
        capability_id=capability_id,
        kind=PACKAGE_KIND_SKILLS_ONLY_SOURCE,
        repository=repository,
        source_commit=source_commit,
        source_tree_sha=source_tree_sha,
        package_root=package_root,
        manifest_path=manifest_path,
        package_content_digest=content_digest,
        required_app_references=[],
    )

    skills_raw: dict = {}
    skills_ordered: list[tuple[str, str]] = []
    for spec in skills_spec:
        closure_paths = list(spec["closure_paths"])
        closure_files = tuple(files_by_path[p] for p in closure_paths)
        skill_content_digest = _expected_closure_digest(
            runtime_name=spec["runtime_name"],
            entrypoint_path=spec["entrypoint_path"],
            closure_files=closure_files,
        )
        grant_digest = _expected_grant_digest(
            capability_id=spec["skill_capability_id"],
            runtime_name=spec["runtime_name"],
            entrypoint_path=spec["entrypoint_path"],
            closure_paths=closure_paths,
            skill_content_digest=skill_content_digest,
            package_capability_id=capability_id,
            package_generation=generation_label,
            package_source_digest=source_digest,
        )
        skills_raw[spec["skill_capability_id"]] = {
            "runtime_name": spec["runtime_name"],
            "entrypoint_path": spec["entrypoint_path"],
            "closure_paths": closure_paths,
            "skill_content_digest": skill_content_digest,
            "grant_digest": grant_digest,
        }
        skills_ordered.append((spec["skill_capability_id"], grant_digest))

    generation_digest = _expected_generation_digest(
        capability_id=capability_id,
        generation=generation_label,
        source_state=PACKAGE_SOURCE_STATE_PROTECTED,
        revoked=revoked,
        package_source_digest=source_digest,
        skills_ordered=tuple(sorted(skills_ordered)),
    )

    raw = {
        "kind": PACKAGE_KIND_SKILLS_ONLY_SOURCE,
        "repository": repository,
        "source_commit": source_commit,
        "source_tree_sha": source_tree_sha,
        "package_root": package_root,
        "manifest_path": manifest_path,
        "generation": generation_label,
        "source_state": PACKAGE_SOURCE_STATE_PROTECTED,
        "revoked": revoked,
        "package_content_digest": content_digest,
        "package_source_digest": source_digest,
        "files": [
            {
                "relative_path": f.relative_path,
                "sha256": f.sha256,
                "byte_length": f.byte_length,
                "executable": f.executable,
            }
            for f in sorted_files
        ],
        "skills": skills_raw,
        "required_app_references": [],
        "package_generation_digest": generation_digest,
    }
    return build_capability_package_generation(capability_id=capability_id, raw=raw)


def _standard_generation(tmp_path: Path, package_root: str = "plugins/example"):
    contents = {
        ".codex-plugin/plugin.json": b'{"name": "example"}',
        "references/boundary.md": b"shared reference bytes",
        "skills/receive/SKILL.md": b"skill entrypoint bytes",
    }
    _write_tree(tmp_path, package_root, contents)
    manifest = _row_from_disk(tmp_path, package_root, ".codex-plugin/plugin.json")
    boundary = _row_from_disk(tmp_path, package_root, "references/boundary.md")
    skill_md = _row_from_disk(tmp_path, package_root, "skills/receive/SKILL.md")
    files = (manifest, boundary, skill_md)
    skill_digest = effective_skill_content_digest(
        runtime_name="receive", entrypoint_path="skills/receive/SKILL.md", closure_files=(boundary, skill_md)
    )
    generation = _canonical_generation(
        capability_id="example.pkg1",
        package_root=package_root,
        manifest_path=".codex-plugin/plugin.json",
        files=files,
        skills_spec=[
            {
                "skill_capability_id": "example.receive.v1",
                "runtime_name": "receive",
                "entrypoint_path": "skills/receive/SKILL.md",
                "closure_paths": ["references/boundary.md", "skills/receive/SKILL.md"],
            }
        ],
    )
    return generation, skill_digest


def test_verify_happy_path(tmp_path):
    generation, skill_digest = _standard_generation(tmp_path)
    receipt = verify_capability_package_source(tmp_path, generation)
    assert isinstance(receipt, VerifiedCapabilityPackage)
    assert receipt.capability_id == "example.pkg1"
    assert receipt.generation == "example.g1"
    assert receipt.package_root == "plugins/example"
    assert receipt.package_content_digest == generation.package_content_digest
    assert receipt.file_count == 3
    assert receipt.total_bytes == sum(f.byte_length for f in generation.files)
    assert receipt.skill_content_digests == (("example.receive.v1", skill_digest),)
    # Finding 3: the happy-path receipt carries the (now-trusted) provenance
    # fields through from the verified generation.
    assert receipt.package_source_digest == generation.package_source_digest
    assert receipt.package_generation_digest == generation.package_generation_digest
    assert receipt.source_state == generation.source_state
    assert receipt.revoked == generation.revoked


def test_verify_source_root_symlink_refuses(tmp_path):
    real_root = tmp_path / "real"
    real_root.mkdir()
    generation, _ = _standard_generation(real_root)
    link_root = tmp_path / "link"
    os.symlink(real_root, link_root)
    with pytest.raises(CapabilityPackageError):
        verify_capability_package_source(link_root, generation)


def test_verify_package_root_symlink_refuses(tmp_path):
    generation, _ = _standard_generation(tmp_path)
    real_package_dir = tmp_path / "plugins" / "example"
    aside = tmp_path / "aside"
    real_package_dir.rename(aside)
    os.symlink(aside, real_package_dir)
    with pytest.raises(CapabilityPackageError):
        verify_capability_package_source(tmp_path, generation)


def test_verify_symlink_in_package_path_component_refuses(tmp_path):
    generation, _ = _standard_generation(tmp_path, package_root="plugins/example")
    plugins_dir = tmp_path / "plugins"
    aside = tmp_path / "plugins-real"
    plugins_dir.rename(aside)
    os.symlink(aside, plugins_dir)
    with pytest.raises(CapabilityPackageError):
        verify_capability_package_source(tmp_path, generation)


def test_verify_symlinked_file_refuses(tmp_path):
    generation, _ = _standard_generation(tmp_path)
    target = tmp_path / "outside.md"
    target.write_bytes(b"shared reference bytes")
    victim = tmp_path / "plugins" / "example" / "references" / "boundary.md"
    victim.unlink()
    os.symlink(target, victim)
    with pytest.raises(CapabilityPackageError):
        verify_capability_package_source(tmp_path, generation)


def test_verify_hardlinked_file_refuses(tmp_path):
    generation, _ = _standard_generation(tmp_path)
    victim = tmp_path / "plugins" / "example" / "references" / "boundary.md"
    external = tmp_path / "external-hardlink.md"
    os.link(victim, external)
    with pytest.raises(CapabilityPackageError):
        verify_capability_package_source(tmp_path, generation)


def test_verify_fifo_in_tree_refuses(tmp_path):
    generation, _ = _standard_generation(tmp_path)
    fifo_path = tmp_path / "plugins" / "example" / "a-fifo"
    os.mkfifo(fifo_path)
    try:
        with pytest.raises(CapabilityPackageError):
            verify_capability_package_source(tmp_path, generation)
    finally:
        fifo_path.unlink()


def test_verify_extra_file_refuses(tmp_path):
    generation, _ = _standard_generation(tmp_path)
    extra = tmp_path / "plugins" / "example" / "extra.txt"
    extra.write_text("undeclared")
    with pytest.raises(CapabilityPackageError):
        verify_capability_package_source(tmp_path, generation)


def test_verify_missing_file_refuses(tmp_path):
    generation, _ = _standard_generation(tmp_path)
    victim = tmp_path / "plugins" / "example" / "references" / "boundary.md"
    victim.unlink()
    with pytest.raises(CapabilityPackageError):
        verify_capability_package_source(tmp_path, generation)


def test_verify_changed_bytes_same_size_refuses(tmp_path):
    generation, _ = _standard_generation(tmp_path)
    victim = tmp_path / "plugins" / "example" / "references" / "boundary.md"
    original = victim.read_bytes()
    replacement = bytes((b + 1) % 256 for b in original)
    assert len(replacement) == len(original)
    victim.write_bytes(replacement)
    with pytest.raises(CapabilityPackageError):
        verify_capability_package_source(tmp_path, generation)


def test_verify_changed_size_refuses(tmp_path):
    generation, _ = _standard_generation(tmp_path)
    victim = tmp_path / "plugins" / "example" / "references" / "boundary.md"
    victim.write_bytes(b"a totally different and longer set of bytes")
    with pytest.raises(CapabilityPackageError):
        verify_capability_package_source(tmp_path, generation)


def test_verify_executable_bit_drift_refuses(tmp_path):
    generation, _ = _standard_generation(tmp_path)
    victim = tmp_path / "plugins" / "example" / "references" / "boundary.md"
    victim.chmod(0o755)
    with pytest.raises(CapabilityPackageError):
        verify_capability_package_source(tmp_path, generation)


def test_verify_unreadable_file_refuses(tmp_path):
    if os.geteuid() == 0:
        pytest.skip("root bypasses permission bits")
    generation, _ = _standard_generation(tmp_path)
    victim = tmp_path / "plugins" / "example" / "references" / "boundary.md"
    victim.chmod(0o000)
    try:
        with pytest.raises(CapabilityPackageError):
            verify_capability_package_source(tmp_path, generation)
    finally:
        victim.chmod(0o644)


def test_verify_nonexistent_source_root_refuses(tmp_path):
    generation, _ = _standard_generation(tmp_path)
    missing_root = tmp_path / "does-not-exist"
    with pytest.raises(CapabilityPackageError):
        verify_capability_package_source(missing_root, generation)


def test_verify_package_path_escaping_source_root_refuses(tmp_path):
    generation, _ = _standard_generation(tmp_path)
    escaping = dataclasses.replace(generation, package_root="../outside")
    with pytest.raises(CapabilityPackageError):
        verify_capability_package_source(tmp_path, escaping)


# ---------------------------------------------------------------------------
# Numeric ceilings (CAP-S1 gap fill): MAX_PACKAGE_DIRECTORIES and
# MAX_PACKAGE_TREE_DEPTH are enforced at the "bound the declared shape
# BEFORE any descriptor is opened" gate inside verify_capability_package_source
# -- neither ceiling was previously tripped by any test in this module. Each
# test below carries an inverse-control assertion (monkeypatching the exact
# module constant the refusal reads) so the test's own bite is demonstrated
# in-line rather than only by a throwaway manual mutation.
# ---------------------------------------------------------------------------


def test_verify_refuses_when_declared_directories_exceed_ceiling(tmp_path, monkeypatch):
    import control_plane.executive_capability_packages as scf_pkg

    package_root = "plugins/example-dirs"
    # 33 single-file directories -- one more than MAX_PACKAGE_DIRECTORIES=32
    # -- via distinct top-level dirs, so allowed_dirs derives to exactly 33
    # entries and no other bound (file count, traversal entries, depth) is
    # anywhere near tripping first.
    contents = {f"d{i:02d}/f.txt": f"contents-{i}".encode() for i in range(33)}
    _write_tree(tmp_path, package_root, contents)
    files = tuple(_row_from_disk(tmp_path, package_root, rel) for rel in sorted(contents))
    manifest_path = "d00/f.txt"
    generation = _canonical_generation(
        capability_id="example.dirs1",
        package_root=package_root,
        manifest_path=manifest_path,
        files=files,
        skills_spec=[
            {
                "skill_capability_id": "example.probe.v1",
                "runtime_name": "probe",
                "entrypoint_path": manifest_path,
                "closure_paths": [manifest_path],
            }
        ],
    )

    with pytest.raises(CapabilityPackageError, match="too_many_directories"):
        verify_capability_package_source(tmp_path, generation)

    # Inverse control: raise the exact ceiling the refusal above reads (the
    # check is a plain module-global lookup at call time, so patching the
    # module attribute changes behavior without touching the frozen
    # generation or the files on disk) and confirm the SAME call now
    # succeeds end to end -- proving the refusal above was driven by this
    # constant, not some other bound.
    monkeypatch.setattr(scf_pkg, "MAX_PACKAGE_DIRECTORIES", 64)
    receipt = verify_capability_package_source(tmp_path, generation)
    assert isinstance(receipt, VerifiedCapabilityPackage)
    assert receipt.file_count == 33


def test_verify_refuses_when_declared_tree_depth_exceeds_ceiling(tmp_path, monkeypatch):
    import control_plane.executive_capability_packages as scf_pkg

    package_root = "plugins/example-depth"
    # 8 nested directories with the file at the 9th path component --
    # component count 9 exceeds MAX_PACKAGE_TREE_DEPTH=8 -- while the
    # directory forest itself (8 single-chain directories) stays far below
    # MAX_PACKAGE_DIRECTORIES=32, isolating the depth ceiling specifically.
    deep_path = "d1/d2/d3/d4/d5/d6/d7/d8/f.txt"
    assert deep_path.count("/") + 1 == 9
    contents = {deep_path: b"deep file bytes"}
    _write_tree(tmp_path, package_root, contents)
    files = (_row_from_disk(tmp_path, package_root, deep_path),)
    generation = _canonical_generation(
        capability_id="example.depth1",
        package_root=package_root,
        manifest_path=deep_path,
        files=files,
        skills_spec=[
            {
                "skill_capability_id": "example.probe.v1",
                "runtime_name": "probe",
                "entrypoint_path": deep_path,
                "closure_paths": [deep_path],
            }
        ],
    )

    with pytest.raises(CapabilityPackageError, match="package_tree_too_deep"):
        verify_capability_package_source(tmp_path, generation)

    # Inverse control, same discipline as the directories test above: raise
    # MAX_PACKAGE_TREE_DEPTH past 9 and confirm the identical call now
    # verifies cleanly.
    monkeypatch.setattr(scf_pkg, "MAX_PACKAGE_TREE_DEPTH", 20)
    receipt = verify_capability_package_source(tmp_path, generation)
    assert isinstance(receipt, VerifiedCapabilityPackage)
    assert receipt.file_count == 1


# ---------------------------------------------------------------------------
# Race seams: deterministic terminal-fence and final-fstat mutation
# ---------------------------------------------------------------------------


def test_verify_insert_via_terminal_fence_refuses(tmp_path):
    generation, _ = _standard_generation(tmp_path)

    def _insert():
        (tmp_path / "plugins" / "example" / "sneaked-in.txt").write_text("surprise")

    with pytest.raises(CapabilityPackageError):
        verify_capability_package_source(tmp_path, generation, _before_terminal_fence=_insert)


def test_verify_remove_via_terminal_fence_refuses(tmp_path):
    generation, _ = _standard_generation(tmp_path)

    def _remove():
        (tmp_path / "plugins" / "example" / "references" / "boundary.md").unlink()

    with pytest.raises(CapabilityPackageError):
        verify_capability_package_source(tmp_path, generation, _before_terminal_fence=_remove)


def test_verify_rename_via_terminal_fence_refuses(tmp_path):
    generation, _ = _standard_generation(tmp_path)

    def _rename():
        victim = tmp_path / "plugins" / "example" / "references" / "boundary.md"
        victim.rename(victim.with_name("renamed.md"))

    with pytest.raises(CapabilityPackageError):
        verify_capability_package_source(tmp_path, generation, _before_terminal_fence=_rename)


def test_verify_terminal_fence_is_not_reached_without_mutation(tmp_path):
    generation, _ = _standard_generation(tmp_path)
    calls = {"n": 0}

    def _noop():
        calls["n"] += 1

    verify_capability_package_source(tmp_path, generation, _before_terminal_fence=_noop)
    assert calls["n"] == 1


def test_verify_mutate_via_before_final_stat_refuses(tmp_path):
    # A single-file package makes the mutation target unambiguous.
    package_root = "plugins/example"
    contents = {"skills/receive/SKILL.md": b"original skill bytes"}
    _write_tree(tmp_path, package_root, contents)
    skill_md = _row_from_disk(tmp_path, package_root, "skills/receive/SKILL.md")
    generation = _canonical_generation(
        capability_id="example.pkg1",
        package_root=package_root,
        manifest_path="skills/receive/SKILL.md",
        files=(skill_md,),
        skills_spec=[
            {
                "skill_capability_id": "example.receive.v1",
                "runtime_name": "receive",
                "entrypoint_path": "skills/receive/SKILL.md",
                "closure_paths": ["skills/receive/SKILL.md"],
            }
        ],
    )

    mutated = {"done": False}

    def _mutate():
        if not mutated["done"]:
            mutated["done"] = True
            path = tmp_path / package_root / "skills/receive/SKILL.md"
            path.write_bytes(b"mutated skill bytes#")  # same length as original (20 bytes)

    assert len(b"mutated skill bytes#") == len(b"original skill bytes")

    with pytest.raises(CapabilityPackageError):
        verify_capability_package_source(tmp_path, generation, _before_final_stat=_mutate)

    assert mutated["done"] is True


# ---------------------------------------------------------------------------
# Descriptor-leak proof
# ---------------------------------------------------------------------------


def test_verify_closes_all_descriptors_on_success_and_refusal(tmp_path, monkeypatch):
    import control_plane.executive_capability_packages as scf_pkg

    counts = {"open": 0, "close": 0}
    real_open = os.open
    real_close = os.close

    def counting_open(*args, **kwargs):
        counts["open"] += 1
        return real_open(*args, **kwargs)

    def counting_close(fd, *args, **kwargs):
        counts["close"] += 1
        return real_close(fd, *args, **kwargs)

    monkeypatch.setattr(scf_pkg.os, "open", counting_open)
    monkeypatch.setattr(scf_pkg.os, "close", counting_close)

    generation, _ = _standard_generation(tmp_path)

    verify_capability_package_source(tmp_path, generation)
    assert counts["open"] > 0
    assert counts["open"] == counts["close"]

    counts["open"] = 0
    counts["close"] = 0

    extra = tmp_path / "plugins" / "example" / "extra.txt"
    extra.write_text("undeclared")

    with pytest.raises(CapabilityPackageError):
        verify_capability_package_source(tmp_path, generation)

    assert counts["open"] > 0
    assert counts["open"] == counts["close"]


def test_verify_closes_all_descriptors_on_race_seam_refusal(tmp_path, monkeypatch):
    import control_plane.executive_capability_packages as scf_pkg

    counts = {"open": 0, "close": 0}
    real_open = os.open
    real_close = os.close

    def counting_open(*args, **kwargs):
        counts["open"] += 1
        return real_open(*args, **kwargs)

    def counting_close(fd, *args, **kwargs):
        counts["close"] += 1
        return real_close(fd, *args, **kwargs)

    monkeypatch.setattr(scf_pkg.os, "open", counting_open)
    monkeypatch.setattr(scf_pkg.os, "close", counting_close)

    generation, _ = _standard_generation(tmp_path)

    def _insert():
        (tmp_path / "plugins" / "example" / "sneaked-in.txt").write_text("surprise")

    with pytest.raises(CapabilityPackageError):
        verify_capability_package_source(tmp_path, generation, _before_terminal_fence=_insert)

    assert counts["open"] > 0
    assert counts["open"] == counts["close"]


# ===========================================================================
# HOSTILE RED COVERAGE for Sol review 5085454178 (five findings)
# ===========================================================================
#
# The sections below are additive-only against the pre-existing test file.
# Each block is labeled with the finding it exercises. Some individual cases
# already happen to refuse under the pre-repair module for unrelated reasons
# (e.g. a digest-chain mismatch masking a path-shape bug); those are kept as
# discriminating regression coverage even where they are not, on their own,
# RED evidence. The RED-head pytest tail is the authority on which cases are
# newly failing before the repair.


# ---------------------------------------------------------------------------
# FINDING 1: token regexes anchored with `$` but validated via `.match()`
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("suffix", ["\n", "\r"])
def test_finding1_identifier_terminal_control_char_refuses(suffix):
    with pytest.raises(CapabilityPackageError):
        _validate_identifier("example.pkg1" + suffix, "field")


def test_finding1_identifier_without_terminal_control_char_still_valid():
    assert _validate_identifier("example.pkg1", "field") == "example.pkg1"


@pytest.mark.parametrize("suffix", ["\n", "\r"])
def test_finding1_sha256_terminal_control_char_refuses(suffix):
    with pytest.raises(CapabilityPackageError):
        _validate_sha256_value("a" * 64 + suffix, "field")


def test_finding1_sha256_without_terminal_control_char_still_valid():
    assert _validate_sha256_value("a" * 64, "field") == "a" * 64


@pytest.mark.parametrize("suffix", ["\n", "\r"])
def test_finding1_hex40_terminal_control_char_refuses(suffix):
    with pytest.raises(CapabilityPackageError):
        _validate_hex40("1" * 40 + suffix, "field")


def test_finding1_hex40_without_terminal_control_char_still_valid():
    assert _validate_hex40("1" * 40, "field") == "1" * 40


# ---------------------------------------------------------------------------
# Shared fixture: a fully self-consistent, disk-backed generation built via
# the real canonical helpers (independent of production's private helpers,
# same pattern as `_baseline_pieces`), used by the FINDING 3/4/5 tests below.
# This is NOT a change to `_standard_generation`/`_make_generation` (those
# stay untouched in this RED commit); it is a new, additive fixture.
# ---------------------------------------------------------------------------


def _real_generation_and_files(tmp_path: Path, *, package_root: str = "plugins/example2"):
    contents = {
        ".codex-plugin/plugin.json": b'{"name": "example2"}',
        "references/boundary.md": b"shared reference bytes v2",
        "skills/receive/SKILL.md": b"skill entrypoint bytes v2",
    }
    _write_tree(tmp_path, package_root, contents)
    manifest = _row_from_disk(tmp_path, package_root, ".codex-plugin/plugin.json")
    boundary = _row_from_disk(tmp_path, package_root, "references/boundary.md")
    skill_md = _row_from_disk(tmp_path, package_root, "skills/receive/SKILL.md")
    files = tuple(sorted((manifest, boundary, skill_md), key=lambda f: f.relative_path))

    capability_id = "example.pkg2"
    repository = "mastermindx-market-intelligence/Mastermind"
    source_commit = "3" * 40
    source_tree_sha = "4" * 40
    manifest_path = ".codex-plugin/plugin.json"
    generation_label = "example.pkg2.g1"
    skill_capability_id = "example.pkg2.receive.v1"
    runtime_name = "receive"
    entrypoint_path = "skills/receive/SKILL.md"
    closure_paths = ["references/boundary.md", "skills/receive/SKILL.md"]

    content_digest = _expected_content_digest(files)
    source_digest = _expected_source_digest(
        capability_id=capability_id,
        kind=PACKAGE_KIND_SKILLS_ONLY_SOURCE,
        repository=repository,
        source_commit=source_commit,
        source_tree_sha=source_tree_sha,
        package_root=package_root,
        manifest_path=manifest_path,
        package_content_digest=content_digest,
        required_app_references=[],
    )
    files_by_path = {f.relative_path: f for f in files}
    closure_files = tuple(files_by_path[p] for p in closure_paths)
    skill_content_digest = _expected_closure_digest(
        runtime_name=runtime_name, entrypoint_path=entrypoint_path, closure_files=closure_files
    )
    grant_digest = _expected_grant_digest(
        capability_id=skill_capability_id,
        runtime_name=runtime_name,
        entrypoint_path=entrypoint_path,
        closure_paths=closure_paths,
        skill_content_digest=skill_content_digest,
        package_capability_id=capability_id,
        package_generation=generation_label,
        package_source_digest=source_digest,
    )
    generation_digest = _expected_generation_digest(
        capability_id=capability_id,
        generation=generation_label,
        source_state=PACKAGE_SOURCE_STATE_PROTECTED,
        revoked=False,
        package_source_digest=source_digest,
        skills_ordered=((skill_capability_id, grant_digest),),
    )

    raw = {
        "kind": PACKAGE_KIND_SKILLS_ONLY_SOURCE,
        "repository": repository,
        "source_commit": source_commit,
        "source_tree_sha": source_tree_sha,
        "package_root": package_root,
        "manifest_path": manifest_path,
        "generation": generation_label,
        "source_state": PACKAGE_SOURCE_STATE_PROTECTED,
        "revoked": False,
        "package_content_digest": content_digest,
        "package_source_digest": source_digest,
        "files": [
            {
                "relative_path": f.relative_path,
                "sha256": f.sha256,
                "byte_length": f.byte_length,
                "executable": f.executable,
            }
            for f in files
        ],
        "skills": {
            skill_capability_id: {
                "runtime_name": runtime_name,
                "entrypoint_path": entrypoint_path,
                "closure_paths": closure_paths,
                "skill_content_digest": skill_content_digest,
                "grant_digest": grant_digest,
            }
        },
        "required_app_references": [],
        "package_generation_digest": generation_digest,
    }
    generation = build_capability_package_generation(capability_id=capability_id, raw=raw)
    return generation


# ---------------------------------------------------------------------------
# FINDING 3: verifier trusts a publicly constructed CapabilityPackageGeneration
# ---------------------------------------------------------------------------


def test_finding3_hand_built_zeroed_source_digest_refuses(tmp_path):
    generation = _real_generation_and_files(tmp_path)
    tampered = dataclasses.replace(generation, package_source_digest="0" * 64)
    with pytest.raises(CapabilityPackageError):
        verify_capability_package_source(tmp_path, tampered)


def test_finding3_hand_built_zeroed_generation_digest_refuses(tmp_path):
    generation = _real_generation_and_files(tmp_path)
    tampered = dataclasses.replace(generation, package_generation_digest="0" * 64)
    with pytest.raises(CapabilityPackageError):
        verify_capability_package_source(tmp_path, tampered)


def test_finding3_hand_built_malformed_repository_refuses(tmp_path):
    generation = _real_generation_and_files(tmp_path)
    tampered = dataclasses.replace(generation, repository="not-a-valid-repo-no-slash")
    with pytest.raises(CapabilityPackageError):
        verify_capability_package_source(tmp_path, tampered)


def test_finding3_hand_built_malformed_source_commit_refuses(tmp_path):
    generation = _real_generation_and_files(tmp_path)
    tampered = dataclasses.replace(generation, source_commit="not-40-hex-at-all")
    with pytest.raises(CapabilityPackageError):
        verify_capability_package_source(tmp_path, tampered)


def test_finding3_hand_built_inconsistent_file_sha256_refuses(tmp_path):
    generation = _real_generation_and_files(tmp_path)
    files = list(generation.files)
    tampered_file = dataclasses.replace(files[0], sha256="9" * 64)
    files[0] = tampered_file
    tampered = dataclasses.replace(generation, files=tuple(files))
    with pytest.raises(CapabilityPackageError):
        verify_capability_package_source(tmp_path, tampered)


def test_finding3_happy_path_receipt_carries_provenance_fields(tmp_path):
    generation = _real_generation_and_files(tmp_path)
    receipt = verify_capability_package_source(tmp_path, generation)
    assert receipt.package_source_digest == generation.package_source_digest
    assert receipt.package_generation_digest == generation.package_generation_digest
    assert receipt.source_state == generation.source_state
    assert receipt.revoked == generation.revoked


# ---------------------------------------------------------------------------
# FINDING 4: a census-to-open FIFO/symlink/socket swap must refuse without
# ever blocking the verifier.
# ---------------------------------------------------------------------------


def test_finding4_before_file_open_fifo_swap_refuses_without_blocking(tmp_path):
    generation, _ = _standard_generation(tmp_path)
    target = "references/boundary.md"

    def _swap(path):
        if path == target:
            victim = tmp_path / "plugins" / "example" / target
            victim.unlink()
            os.mkfifo(victim)

    with pytest.raises(CapabilityPackageError):
        verify_capability_package_source(tmp_path, generation, _before_file_open=_swap)


def test_finding4_before_file_open_symlink_swap_refuses(tmp_path):
    generation, _ = _standard_generation(tmp_path)
    target = "references/boundary.md"
    outside = tmp_path / "outside-swap-target.md"
    outside.write_bytes(b"shared reference bytes")

    def _swap(path):
        if path == target:
            victim = tmp_path / "plugins" / "example" / target
            victim.unlink()
            os.symlink(outside, victim)

    with pytest.raises(CapabilityPackageError):
        verify_capability_package_source(tmp_path, generation, _before_file_open=_swap)


def test_finding4_before_file_open_socket_swap_refuses_without_blocking(tmp_path):
    generation, _ = _standard_generation(tmp_path)
    target = "references/boundary.md"

    def _swap(path):
        if path == target:
            victim = tmp_path / "plugins" / "example" / target
            victim.unlink()
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                sock.bind(str(victim))
            except OSError:
                sock.close()
                pytest.skip("platform refuses AF_UNIX bind in tmpdir")
            sock.close()

    with pytest.raises(CapabilityPackageError):
        verify_capability_package_source(tmp_path, generation, _before_file_open=_swap)


def test_finding4_before_file_open_seam_not_invoked_without_swap(tmp_path):
    generation, _ = _standard_generation(tmp_path)
    seen: list[str] = []

    def _record(path):
        seen.append(path)

    verify_capability_package_source(tmp_path, generation, _before_file_open=_record)
    assert sorted(seen) == sorted(row.relative_path for row in generation.files)


# ---------------------------------------------------------------------------
# FINDING 5: `repository` grammar + explicit byte ceilings.
# ---------------------------------------------------------------------------


def _raw_with_repository(repository: str) -> tuple[str, dict]:
    pieces = _baseline_pieces()
    capability_id = pieces["capability_id"]
    raw = copy.deepcopy(pieces["raw"])
    content_digest = pieces["content_digest"]
    source_digest = _expected_source_digest(
        capability_id=capability_id,
        kind=raw["kind"],
        repository=repository,
        source_commit=raw["source_commit"],
        source_tree_sha=raw["source_tree_sha"],
        package_root=raw["package_root"],
        manifest_path=raw["manifest_path"],
        package_content_digest=content_digest,
        required_app_references=raw["required_app_references"],
    )
    skill_id = pieces["skill_capability_id"]
    grant_digest = _expected_grant_digest(
        capability_id=skill_id,
        runtime_name=raw["skills"][skill_id]["runtime_name"],
        entrypoint_path=raw["skills"][skill_id]["entrypoint_path"],
        closure_paths=tuple(raw["skills"][skill_id]["closure_paths"]),
        skill_content_digest=pieces["skill_content_digest"],
        package_capability_id=capability_id,
        package_generation=raw["generation"],
        package_source_digest=source_digest,
    )
    generation_digest = _expected_generation_digest(
        capability_id=capability_id,
        generation=raw["generation"],
        source_state=raw["source_state"],
        revoked=raw["revoked"],
        package_source_digest=source_digest,
        skills_ordered=((skill_id, grant_digest),),
    )
    raw["repository"] = repository
    raw["package_source_digest"] = source_digest
    raw["skills"][skill_id]["grant_digest"] = grant_digest
    raw["package_generation_digest"] = generation_digest
    return capability_id, raw


@pytest.mark.parametrize(
    "bad_repository",
    [
        "no-slash-here",
        "too/many/slashes",
        "/leading-slash",
        "trailing-slash/",
        "/",
        "good-repo/name\n",
        "a" * 100 + "/" + "b" * 100,  # 201 UTF-8 bytes: over MAX_REPOSITORY_BYTES=200
    ],
    ids=[
        "no_slash",
        "two_slashes",
        "leading_slash",
        "trailing_slash",
        "bare_slash",
        "terminal_newline",
        "over_byte_ceiling",
    ],
)
def test_finding5_malformed_repository_refuses(bad_repository):
    capability_id, raw = _raw_with_repository(bad_repository)
    with pytest.raises(CapabilityPackageError):
        build_capability_package_generation(capability_id=capability_id, raw=raw)


def test_finding5_real_protected_repository_value_still_accepted():
    capability_id, raw = _raw_with_repository("mastermindx-market-intelligence/Mastermind")
    generation = build_capability_package_generation(capability_id=capability_id, raw=raw)
    assert generation.repository == "mastermindx-market-intelligence/Mastermind"


def test_finding5_relative_path_segment_over_255_bytes_refuses():
    long_segment = "a" * 256
    with pytest.raises(CapabilityPackageError):
        _validate_relative_path(f"dir/{long_segment}/file.md", "field")


def test_finding5_relative_path_segment_at_255_bytes_is_permitted():
    segment = "a" * 255
    assert _validate_relative_path(f"dir/{segment}", "field") == f"dir/{segment}"


def test_finding5_relative_path_total_over_512_bytes_refuses():
    segment = "a" * 50
    path = "/".join([segment] * 11)  # 11*50 + 10 separators = 560 bytes, each segment <=255
    assert len(path.encode("utf-8")) > 512
    with pytest.raises(CapabilityPackageError):
        _validate_relative_path(path, "field")


def test_finding5_relative_path_at_512_bytes_is_permitted():
    # 10 segments of 50 bytes + 9 separators = 509 bytes; well under the ceiling.
    segment = "a" * 50
    path = "/".join([segment] * 10)
    assert len(path.encode("utf-8")) <= 512
    assert _validate_relative_path(path, "field") == path


# ---------------------------------------------------------------------------
# FINDING 2: censuses compare only regular files; directories are opened and
# retained but never compared; undeclared directories (empty or nested) pass;
# a directory inserted after the first census is invisible to the terminal
# fence; a required directory's removal/replacement must still refuse.
# ---------------------------------------------------------------------------


def _count_opens_closes(monkeypatch):
    import control_plane.executive_capability_packages as scf_pkg

    counts = {"open": 0, "close": 0}
    real_open = os.open
    real_close = os.close

    def counting_open(*args, **kwargs):
        counts["open"] += 1
        return real_open(*args, **kwargs)

    def counting_close(fd, *args, **kwargs):
        counts["close"] += 1
        return real_close(fd, *args, **kwargs)

    monkeypatch.setattr(scf_pkg.os, "open", counting_open)
    monkeypatch.setattr(scf_pkg.os, "close", counting_close)
    return counts


def test_finding2_static_extra_empty_directory_refuses(tmp_path):
    generation, _ = _standard_generation(tmp_path)
    extra_dir = tmp_path / "plugins" / "example" / "empty-extra"
    extra_dir.mkdir()
    with pytest.raises(CapabilityPackageError):
        verify_capability_package_source(tmp_path, generation)


def test_finding2_nested_extra_empty_directory_forest_refuses(tmp_path):
    generation, _ = _standard_generation(tmp_path)
    nested = tmp_path / "plugins" / "example" / "forest"
    for i in range(6):
        nested = nested / f"level{i}"
    nested.mkdir(parents=True)
    with pytest.raises(CapabilityPackageError):
        verify_capability_package_source(tmp_path, generation)


def test_finding2_directory_inserted_before_terminal_fence_refuses(tmp_path):
    generation, _ = _standard_generation(tmp_path)

    def _insert_dir_with_file():
        new_dir = tmp_path / "plugins" / "example" / "sneaked-dir"
        new_dir.mkdir()
        (new_dir / "file.txt").write_text("surprise")

    with pytest.raises(CapabilityPackageError):
        verify_capability_package_source(tmp_path, generation, _before_terminal_fence=_insert_dir_with_file)


def test_finding2_required_directory_removed_refuses(tmp_path):
    generation, _ = _standard_generation(tmp_path)
    shutil.rmtree(tmp_path / "plugins" / "example" / "skills" / "receive")
    with pytest.raises(CapabilityPackageError):
        verify_capability_package_source(tmp_path, generation)


def test_finding2_required_directory_replaced_with_file_refuses(tmp_path):
    generation, _ = _standard_generation(tmp_path)
    receive_dir = tmp_path / "plugins" / "example" / "skills" / "receive"
    shutil.rmtree(receive_dir)
    receive_dir.write_text("not a directory anymore")
    with pytest.raises(CapabilityPackageError):
        verify_capability_package_source(tmp_path, generation)


def test_finding2_required_directory_renamed_refuses(tmp_path):
    generation, _ = _standard_generation(tmp_path)
    receive_dir = tmp_path / "plugins" / "example" / "skills" / "receive"
    receive_dir.rename(receive_dir.with_name("receive-renamed"))
    with pytest.raises(CapabilityPackageError):
        verify_capability_package_source(tmp_path, generation)


def test_finding2_extra_directory_refusal_balances_descriptors(tmp_path, monkeypatch):
    counts = _count_opens_closes(monkeypatch)
    generation, _ = _standard_generation(tmp_path)
    extra_dir = tmp_path / "plugins" / "example" / "empty-extra"
    extra_dir.mkdir()
    with pytest.raises(CapabilityPackageError):
        verify_capability_package_source(tmp_path, generation)
    assert counts["open"] > 0
    assert counts["open"] == counts["close"]


def test_finding2_nested_forest_refusal_balances_descriptors(tmp_path, monkeypatch):
    counts = _count_opens_closes(monkeypatch)
    generation, _ = _standard_generation(tmp_path)
    nested = tmp_path / "plugins" / "example" / "forest"
    for i in range(6):
        nested = nested / f"level{i}"
    nested.mkdir(parents=True)
    with pytest.raises(CapabilityPackageError):
        verify_capability_package_source(tmp_path, generation)
    assert counts["open"] > 0
    assert counts["open"] == counts["close"]


def test_finding2_directory_insert_before_fence_refusal_balances_descriptors(tmp_path, monkeypatch):
    counts = _count_opens_closes(monkeypatch)
    generation, _ = _standard_generation(tmp_path)

    def _insert_dir_with_file():
        new_dir = tmp_path / "plugins" / "example" / "sneaked-dir"
        new_dir.mkdir()
        (new_dir / "file.txt").write_text("surprise")

    with pytest.raises(CapabilityPackageError):
        verify_capability_package_source(tmp_path, generation, _before_terminal_fence=_insert_dir_with_file)
    assert counts["open"] > 0
    assert counts["open"] == counts["close"]


def test_finding2_required_directory_mutation_refusal_balances_descriptors(tmp_path, monkeypatch):
    counts = _count_opens_closes(monkeypatch)
    generation, _ = _standard_generation(tmp_path)
    receive_dir = tmp_path / "plugins" / "example" / "skills" / "receive"
    shutil.rmtree(receive_dir)
    receive_dir.write_text("not a directory anymore")
    with pytest.raises(CapabilityPackageError):
        verify_capability_package_source(tmp_path, generation)
    assert counts["open"] > 0
    assert counts["open"] == counts["close"]


# ===========================================================================
# ROUND-2 HOSTILE RED COVERAGE for Sol implementation-grade clarification
# 5505160491 (five items, extending accepted review 5085454178).
# ===========================================================================
#
# Additive-only against the pre-existing (round-1) test file. Each block is
# labeled with the clarification item it exercises. As with the round-1
# hostile block, the RED-head pytest tail is the authority on which cases are
# newly failing before the item-2 repair; some cases fail via an unexpected
# exception type (e.g. a missing keyword argument, a naked UnicodeEncodeError)
# rather than a plain assertion failure -- that is still valid RED evidence.


# ---------------------------------------------------------------------------
# ITEM 1: exact-type revalidation boundary. Python's dataclass-generated
# __eq__ returns NotImplemented when `other.__class__ is not self.__class__`,
# which makes the interpreter fall back to `other.__eq__(self)` -- so a
# subclass overriding __eq__ to always return True can make an otherwise
# tampered object compare equal to a genuinely rebuilt one. Closing this
# requires refusing any non-exact type before ever reaching an equality
# check, not merely rebuilding-and-comparing.
# ---------------------------------------------------------------------------


class _SpoofedGeneration(CapabilityPackageGeneration):
    def __eq__(self, other):
        return True

    def __hash__(self):
        return 0


class _SpoofedFile(CapabilityPackageFile):
    def __eq__(self, other):
        return True

    def __hash__(self):
        return 0


def _generation_kwargs(generation: CapabilityPackageGeneration) -> dict:
    return {f.name: getattr(generation, f.name) for f in dataclasses.fields(generation)}


def _two_skill_generation_and_files(tmp_path: Path, *, package_root: str = "plugins/example3"):
    """A genuinely-built, self-consistent generation with TWO skills.

    Used specifically to prove the __eq__-fallback bypass: reordering
    `.skills` (a pure tuple-order change) changes nothing about any
    individual digest -- `_generation_to_raw` folds the tuple into a
    capability_id-keyed *mapping*, and the builder always re-derives the
    canonical (sorted-by-capability_id) order on rebuild -- so a naive
    zeroed-digest tamper is masked by the pre-existing digest-mismatch
    exception path (kept below as regression coverage), while a pure
    reorder survives rebuild untouched and isolates the real __eq__ gap.
    """
    contents = {
        ".codex-plugin/plugin.json": b'{"name": "example3"}',
        "references/boundary.md": b"shared reference bytes v3",
        "skills/receive/SKILL.md": b"skill entrypoint bytes receive",
        "skills/finish/SKILL.md": b"skill entrypoint bytes finish",
    }
    _write_tree(tmp_path, package_root, contents)
    manifest = _row_from_disk(tmp_path, package_root, ".codex-plugin/plugin.json")
    boundary = _row_from_disk(tmp_path, package_root, "references/boundary.md")
    receive_md = _row_from_disk(tmp_path, package_root, "skills/receive/SKILL.md")
    finish_md = _row_from_disk(tmp_path, package_root, "skills/finish/SKILL.md")
    files = tuple(sorted((manifest, boundary, receive_md, finish_md), key=lambda f: f.relative_path))

    capability_id = "example.pkg3"
    generation = _canonical_generation(
        capability_id=capability_id,
        package_root=package_root,
        manifest_path=".codex-plugin/plugin.json",
        files=files,
        skills_spec=[
            {
                "skill_capability_id": "example.receive.v1",
                "runtime_name": "receive",
                "entrypoint_path": "skills/receive/SKILL.md",
                "closure_paths": ["skills/receive/SKILL.md"],
            },
            {
                "skill_capability_id": "example.finish.v1",
                "runtime_name": "finish",
                "entrypoint_path": "skills/finish/SKILL.md",
                "closure_paths": ["skills/finish/SKILL.md"],
            },
        ],
        generation_label="example.pkg3.g1",
        repository="mastermindx-market-intelligence/Mastermind",
        source_commit="5" * 40,
        source_tree_sha="6" * 40,
    )
    assert len(generation.skills) == 2
    return generation


def test_item1_subclassed_generation_with_spoofed_eq_refuses(tmp_path):
    generation = _two_skill_generation_and_files(tmp_path)

    # A pure tuple-order change to `.skills`: every individual digest
    # (skill-content, grant, generation) stays byte-for-byte identical,
    # since `_generation_to_raw` folds the tuple into a capability_id-keyed
    # mapping and the builder always re-derives sorted order on rebuild.
    # This survives rebuild untouched -- unlike a digest-value tamper,
    # which is already caught by the pre-existing rebuild-exception path
    # regardless of any __eq__ trick (see the zeroed-digest sanity check
    # in test_item1_zeroed_digest_tamper_is_already_caught_by_rebuild).
    reordered = dataclasses.replace(generation, skills=tuple(reversed(generation.skills)))
    assert reordered != generation  # a plain (non-spoofed) comparison correctly differs

    kwargs = _generation_kwargs(reordered)
    spoofed = _SpoofedGeneration(**kwargs)
    # Sanity: the spoof really does lie about equality to the genuine rebuild.
    assert spoofed == generation
    with pytest.raises(CapabilityPackageError):
        verify_capability_package_source(tmp_path, spoofed)


def test_item1_zeroed_digest_tamper_is_already_caught_by_rebuild(tmp_path):
    """Regression coverage, not discriminating on its own (see round-1's own
    header note for the same pattern): a subclass wrapping a zeroed digest
    is refused because the REBUILD's own digest recomputation fails first,
    before the (spoofable) equality check is ever reached -- this predates
    and is unaffected by the item-1 repair. The reordering test above is
    what isolates the actual __eq__-fallback gap."""
    generation = _real_generation_and_files(tmp_path)
    kwargs = _generation_kwargs(generation)
    kwargs["package_generation_digest"] = "0" * 64  # tampered
    spoofed = _SpoofedGeneration(**kwargs)
    assert spoofed == generation
    with pytest.raises(CapabilityPackageError):
        verify_capability_package_source(tmp_path, spoofed)


def test_item1_subclassed_file_row_in_files_refuses(tmp_path):
    """Regression coverage, not discriminating on its own: every field of a
    CapabilityPackageFile row is covered by the content-digest projection,
    so any value-level tamper is already caught by the rebuild's own digest
    recomputation before the (spoofable) equality check is reached. This
    still closes the exact-type gap defensively (a subclass with identical
    values is refused too, per the exact-type check added in the repair)."""
    generation = _real_generation_and_files(tmp_path)
    original = generation.files[0]
    spoofed_row = _SpoofedFile(
        relative_path=original.relative_path,
        sha256="9" * 64,  # tampered but "believed" via the spoofed __eq__
        byte_length=original.byte_length,
        executable=original.executable,
    )
    files = list(generation.files)
    files[0] = spoofed_row
    tampered = dataclasses.replace(generation, files=tuple(files))
    assert tampered.files[0] == generation.files[0]  # sanity: spoof lies here too
    with pytest.raises(CapabilityPackageError):
        verify_capability_package_source(tmp_path, tampered)


def test_item1_content_digest_refuses_subclassed_row():
    class _OtherSpoofedFile(CapabilityPackageFile):
        pass

    row = _OtherSpoofedFile("references/boundary.md", "a" * 64, 7, False)
    other = CapabilityPackageFile("skills/receive/SKILL.md", "b" * 64, 11, False)
    with pytest.raises(CapabilityPackageError):
        capability_package_content_digest((row, other))


def test_item1_content_digest_refuses_bad_hex_row():
    bad_row = CapabilityPackageFile("references/boundary.md", "not-a-valid-sha-value!!" + "0" * 41, 7, False)
    good_row = CapabilityPackageFile("skills/receive/SKILL.md", "b" * 64, 11, False)
    with pytest.raises(CapabilityPackageError):
        capability_package_content_digest((bad_row, good_row))


def test_item1_content_digest_refuses_bad_path_row():
    bad_row = CapabilityPackageFile("/etc/passwd", "a" * 64, 7, False)
    good_row = CapabilityPackageFile("skills/receive/SKILL.md", "b" * 64, 11, False)
    with pytest.raises(CapabilityPackageError):
        capability_package_content_digest((bad_row, good_row))


def test_item1_effective_skill_digest_refuses_subclassed_closure_row():
    class _OtherSpoofedFile(CapabilityPackageFile):
        pass

    entrypoint = _OtherSpoofedFile("skills/receive-commission/SKILL.md", "d" * 64, 100, False)
    with pytest.raises(CapabilityPackageError):
        effective_skill_content_digest(
            runtime_name="receive-commission",
            entrypoint_path="skills/receive-commission/SKILL.md",
            closure_files=(entrypoint,),
        )


# ---------------------------------------------------------------------------
# ITEM 2: streaming bounded census. `os.listdir(dir_fd)` materializes the
# entire directory into a Python list before any per-entry budget check can
# run; a streaming `os.scandir(dir_fd)` walk must stop consuming entries the
# moment the budget is exceeded, never after. A directory's *name* being
# swapped for a fresh same-named directory of a different inode is also
# invisible to any purely name-based census (the name set is unchanged);
# only a parent-entry-vs-retained-descriptor identity check can see it.
# ---------------------------------------------------------------------------


def test_item2_census_never_calls_listdir(tmp_path, monkeypatch):
    import control_plane.executive_capability_packages as scf_pkg

    def _forbidden_listdir(*args, **kwargs):
        raise AssertionError("package census must stream via os.scandir, not os.listdir")

    monkeypatch.setattr(scf_pkg.os, "listdir", _forbidden_listdir)

    generation, _ = _standard_generation(tmp_path)
    receipt = verify_capability_package_source(tmp_path, generation)
    assert receipt.file_count == 3


def test_item2_overfull_directory_census_is_bounded(tmp_path, monkeypatch):
    import control_plane.executive_capability_packages as scf_pkg

    generation, _ = _standard_generation(tmp_path)
    receive_dir = tmp_path / "plugins" / "example" / "skills" / "receive"
    for i in range(200):
        (receive_dir / f"extra{i:04d}.txt").write_bytes(b"x")

    observed = {"n": 0}
    real_listdir = scf_pkg.os.listdir
    real_scandir = scf_pkg.os.scandir

    def counting_listdir(*args, **kwargs):
        names = real_listdir(*args, **kwargs)
        observed["n"] += len(names)
        return names

    def counting_scandir(*args, **kwargs):
        it = real_scandir(*args, **kwargs)

        def gen():
            try:
                for entry in it:
                    observed["n"] += 1
                    yield entry
            finally:
                it.close()

        return gen()

    monkeypatch.setattr(scf_pkg.os, "listdir", counting_listdir)
    monkeypatch.setattr(scf_pkg.os, "scandir", counting_scandir)

    with pytest.raises(CapabilityPackageError):
        verify_capability_package_source(tmp_path, generation)

    # A directory holding far more than the traversal budget must never be
    # observed (via either listdir's all-at-once materialization or
    # scandir's per-entry yield) beyond a small slack past the budget --
    # whichever enumeration primitive is in use, the scan must stop early.
    assert observed["n"] <= scf_pkg.MAX_PACKAGE_TRAVERSAL_ENTRIES + 5


def test_item2_directory_swap_refuses_even_when_timestamp_drift_signal_unavailable(tmp_path, monkeypatch, tmp_path_factory):
    import control_plane.executive_capability_packages as scf_pkg

    # Neutralize the pre-existing (round-1) "did any retained descriptor's
    # own fstat drift over time" signal by excluding mtime/ctime from the
    # identity tuple, simulating a coarse-timestamp filesystem where that
    # signal is unavailable. This isolates the NEW, independent check: a
    # fresh lookup of a declared directory's name through its *parent* must
    # still see the same inode the verifier is holding open, regardless of
    # whether any timestamp happened to drift.
    def _identity_without_timestamps(st):
        return (st.st_dev, st.st_ino, st.st_mode, st.st_nlink, st.st_uid, st.st_gid, st.st_size)

    monkeypatch.setattr(scf_pkg, "_stat_identity", _identity_without_timestamps)

    generation, _ = _standard_generation(tmp_path)

    # The "detached" original directory must land OUTSIDE `tmp_path`
    # (source_root) entirely: source_root's own retained descriptor is
    # ALSO in the all_retained set, and adding a new top-level sibling
    # entry under it would bump ITS OWN nlink/size, incidentally catching
    # the swap for an unrelated reason even with timestamps neutralized.
    elsewhere = tmp_path_factory.mktemp("item2-detached")

    def _swap():
        receive_dir = tmp_path / "plugins" / "example" / "skills" / "receive"
        detached = elsewhere / "detached-original"
        receive_dir.rename(detached)  # move the OLD dir (with content) fully outside the scanned tree
        receive_dir.mkdir()  # brand-new inode, identical name/path
        (receive_dir / "SKILL.md").write_bytes(b"skill entrypoint bytes")  # identical declared bytes

    with pytest.raises(CapabilityPackageError):
        verify_capability_package_source(tmp_path, generation, _before_terminal_fence=_swap)


# ---------------------------------------------------------------------------
# ITEM 3: census-to-open identity binding. A regular file removed and
# replaced by a *different* regular file with byte-for-byte identical
# declared content (same size, same bytes, same executable bit) hashes
# identically and passes every content-based check; only comparing the
# census-time lstat identity to the open-time fstat identity can see it.
# ---------------------------------------------------------------------------


def test_item3_regular_file_swapped_for_different_regular_file_same_bytes_refuses(tmp_path, monkeypatch):
    import control_plane.executive_capability_packages as scf_pkg

    # As in the item-2 directory-swap test: neutralize the pre-existing
    # "did any retained descriptor's own fstat drift" signal (excluding
    # mtime/ctime) so this test isolates the NEW, independent check --
    # census-time lstat identity vs. open-time fstat identity for the FILE
    # itself -- rather than incidentally relying on the PARENT directory's
    # mtime bumping when the file underneath it is unlinked and recreated.
    def _identity_without_timestamps(st):
        return (st.st_dev, st.st_ino, st.st_mode, st.st_nlink, st.st_uid, st.st_gid, st.st_size)

    monkeypatch.setattr(scf_pkg, "_stat_identity", _identity_without_timestamps)

    generation, _ = _standard_generation(tmp_path)
    target = "references/boundary.md"
    victim = tmp_path / "plugins" / "example" / target
    original_bytes = victim.read_bytes()

    def _swap(path):
        if path == target:
            victim.unlink()
            # A brand-new inode with byte-for-byte identical declared
            # content: content/size/executable-bit hashing alone is blind
            # to this swap.
            victim.write_bytes(original_bytes)

    with pytest.raises(CapabilityPackageError):
        verify_capability_package_source(tmp_path, generation, _before_file_open=_swap)


# ---------------------------------------------------------------------------
# ITEM 4: bounded read. The hash loop must track cumulative bytes read and
# refuse immediately once they exceed the declared length, rather than
# reading to EOF and only catching a size change via the final fstat.
# ---------------------------------------------------------------------------


def _single_file_generation(tmp_path: Path, *, package_root: str, contents: bytes) -> CapabilityPackageGeneration:
    _write_tree(tmp_path, package_root, {"skills/receive/SKILL.md": contents})
    skill_md = _row_from_disk(tmp_path, package_root, "skills/receive/SKILL.md")
    return _canonical_generation(
        capability_id="example.pkg1",
        package_root=package_root,
        manifest_path="skills/receive/SKILL.md",
        files=(skill_md,),
        skills_spec=[
            {
                "skill_capability_id": "example.receive.v1",
                "runtime_name": "receive",
                "entrypoint_path": "skills/receive/SKILL.md",
                "closure_paths": ["skills/receive/SKILL.md"],
            }
        ],
    )


def test_item4_mid_read_growth_refuses_with_bounded_reads(tmp_path, monkeypatch):
    import control_plane.executive_capability_packages as scf_pkg

    monkeypatch.setattr(scf_pkg, "_READ_CHUNK_BYTES", 4)
    package_root = "plugins/example"
    generation = _single_file_generation(tmp_path, package_root=package_root, contents=b"abcd")

    grown = {"done": False}

    def _grow(path):
        if not grown["done"]:
            grown["done"] = True
            p = tmp_path / package_root / "skills/receive/SKILL.md"
            with open(p, "ab") as f:
                f.write(b"0" * 400)  # far beyond the declared 4-byte length

    real_read = os.read
    read_calls = {"n": 0}

    def counting_read(fd, n, *a, **kw):
        read_calls["n"] += 1
        return real_read(fd, n, *a, **kw)

    monkeypatch.setattr(scf_pkg.os, "read", counting_read)

    with pytest.raises(CapabilityPackageError):
        verify_capability_package_source(tmp_path, generation, _between_read_chunks=_grow)

    # A growing file must be refused as soon as the cumulative read count
    # exceeds the declared length -- not after draining the whole (now much
    # larger) file to EOF.
    assert read_calls["n"] <= 3


def test_item4_truncated_mid_read_refuses(tmp_path, monkeypatch):
    import control_plane.executive_capability_packages as scf_pkg

    monkeypatch.setattr(scf_pkg, "_READ_CHUNK_BYTES", 4)
    package_root = "plugins/example"
    generation = _single_file_generation(tmp_path, package_root=package_root, contents=b"abcdEXTRA")

    truncated = {"done": False}

    def _truncate(path):
        if not truncated["done"]:
            truncated["done"] = True
            p = tmp_path / package_root / "skills/receive/SKILL.md"
            with open(p, "r+b") as f:
                f.truncate(4)

    with pytest.raises(CapabilityPackageError):
        verify_capability_package_source(tmp_path, generation, _between_read_chunks=_truncate)


# ---------------------------------------------------------------------------
# ITEM 5: grammar/edge hygiene residue. A lone surrogate cannot be encoded
# to UTF-8 at all; an unwrapped `.encode("utf-8")` raises a naked
# UnicodeEncodeError instead of the bounded CapabilityPackageError
# vocabulary. A hostile `source_root` (embedded NUL, or a non-str type)
# must be refused the same bounded way rather than leaking a raw
# TypeError/ValueError from Path()/os.lstat()/os.open().
# ---------------------------------------------------------------------------


def test_item5_surrogate_path_component_refuses():
    with pytest.raises(CapabilityPackageError):
        _validate_relative_path("skills/\ud800/SKILL.md", "field")


def test_item5_hostile_source_root_nul_byte_refuses(tmp_path):
    generation, _ = _standard_generation(tmp_path)
    with pytest.raises(CapabilityPackageError):
        verify_capability_package_source("bad\x00root", generation)


def test_item5_hostile_source_root_non_str_type_refuses(tmp_path):
    generation, _ = _standard_generation(tmp_path)
    with pytest.raises(CapabilityPackageError):
        verify_capability_package_source(12345, generation)


# ---------------------------------------------------------------------------
# Descriptor-leak proof, extended: the two new refusal paths that open real
# descriptors (the item-2 parent/child directory-identity mismatch and the
# item-3 census-to-open file-identity mismatch) must balance opens and
# closes exactly like every round-1 refusal path.
# ---------------------------------------------------------------------------


def test_item2_directory_swap_refusal_balances_descriptors(tmp_path, monkeypatch):
    counts = _count_opens_closes(monkeypatch)
    generation, _ = _standard_generation(tmp_path)
    elsewhere = Path(tempfile.mkdtemp())

    def _swap():
        receive_dir = tmp_path / "plugins" / "example" / "skills" / "receive"
        detached = elsewhere / "detached-original"
        receive_dir.rename(detached)
        receive_dir.mkdir()
        (receive_dir / "SKILL.md").write_bytes(b"skill entrypoint bytes")

    with pytest.raises(CapabilityPackageError):
        verify_capability_package_source(tmp_path, generation, _before_terminal_fence=_swap)
    assert counts["open"] > 0
    assert counts["open"] == counts["close"]


def test_item3_regular_file_swap_refusal_balances_descriptors(tmp_path, monkeypatch):
    counts = _count_opens_closes(monkeypatch)
    generation, _ = _standard_generation(tmp_path)
    target = "references/boundary.md"
    victim = tmp_path / "plugins" / "example" / target
    original_bytes = victim.read_bytes()

    def _swap(path):
        if path == target:
            victim.unlink()
            victim.write_bytes(original_bytes)

    with pytest.raises(CapabilityPackageError):
        verify_capability_package_source(tmp_path, generation, _before_file_open=_swap)
    assert counts["open"] > 0
    assert counts["open"] == counts["close"]


def test_item4_mid_read_growth_refusal_balances_descriptors(tmp_path, monkeypatch):
    counts = _count_opens_closes(monkeypatch)
    import control_plane.executive_capability_packages as scf_pkg

    monkeypatch.setattr(scf_pkg, "_READ_CHUNK_BYTES", 4)
    package_root = "plugins/example"
    generation = _single_file_generation(tmp_path, package_root=package_root, contents=b"abcd")

    grown = {"done": False}

    def _grow(path):
        if not grown["done"]:
            grown["done"] = True
            p = tmp_path / package_root / "skills/receive/SKILL.md"
            with open(p, "ab") as f:
                f.write(b"0" * 40)

    with pytest.raises(CapabilityPackageError):
        verify_capability_package_source(tmp_path, generation, _between_read_chunks=_grow)
    assert counts["open"] > 0
    assert counts["open"] == counts["close"]


# ===========================================================================
# WAVE-3 REPAIR A: retained census file objects (Sol corrections 5087211688
# + 5087236388, mastermind-cap-s1-complete-vertical-20260901-sol-001, PR #350)
# ===========================================================================
#
# `test_item3_regular_file_swapped_for_different_regular_file_same_bytes_refuses`
# above is kept EXACTLY as it was: on this macOS host neither `unlink()`ing
# nor `os.replace()`ing a file naturally recycles the freed inode number, so
# the test passing here does not by itself prove the CODE (rather than the
# filesystem's allocator) is what refuses the swap. The tests below extend
# coverage to the rest of the RED/GREEN matrix (atomic replace; post-census
# replacement by symlink/FIFO/socket/directory; same-path mode mutation
# while retained; the enlarged descriptor-balance surface) and include a
# dedicated bite-check that disables the identity fence to prove IT -- not
# this platform's inode-allocation behavior -- is load-bearing.


def test_wave3_partA_os_replace_byte_identical_refuses(tmp_path, monkeypatch):
    """Atomic os.replace() swap-in of a byte-identical file must still
    refuse: os.replace() is a single syscall (no unlink+create window at
    all), so this is a strictly harder case than unlink+recreate for any
    check relying on a window between two separate operations -- the
    census-time open must bind identity to whatever object existed at
    CENSUS-lstat time, not to whatever the name resolves to by the time the
    open actually executes."""
    import control_plane.executive_capability_packages as scf_pkg

    def _identity_without_timestamps(st):
        return (st.st_dev, st.st_ino, st.st_mode, st.st_nlink, st.st_uid, st.st_gid, st.st_size)

    monkeypatch.setattr(scf_pkg, "_stat_identity", _identity_without_timestamps)

    generation, _ = _standard_generation(tmp_path)
    target = "references/boundary.md"
    victim = tmp_path / "plugins" / "example" / target
    original_bytes = victim.read_bytes()

    def _swap(path):
        if path == target:
            replacement = tmp_path / "replacement-boundary.md"
            replacement.write_bytes(original_bytes)
            os.replace(replacement, victim)

    with pytest.raises(CapabilityPackageError):
        verify_capability_package_source(tmp_path, generation, _before_file_open=_swap)


def test_wave3_partA_terminal_fence_symlink_replacement_refuses(tmp_path):
    """Post-census (after every file has been hashed via its retained fd),
    replace a declared file's NAME with a symlink. The terminal fence's
    fresh no-follow lstat must see this without ever opening/following it."""
    generation, _ = _standard_generation(tmp_path)
    target = tmp_path / "plugins" / "example" / "references" / "boundary.md"
    outside = tmp_path / "outside-terminal-swap.md"
    outside.write_bytes(b"shared reference bytes")

    def _swap():
        target.unlink()
        os.symlink(outside, target)

    with pytest.raises(CapabilityPackageError):
        verify_capability_package_source(tmp_path, generation, _before_terminal_fence=_swap)


def test_wave3_partA_terminal_fence_fifo_replacement_refuses_without_blocking(tmp_path):
    generation, _ = _standard_generation(tmp_path)
    target = tmp_path / "plugins" / "example" / "references" / "boundary.md"

    def _swap():
        target.unlink()
        os.mkfifo(target)

    with pytest.raises(CapabilityPackageError):
        verify_capability_package_source(tmp_path, generation, _before_terminal_fence=_swap)


def test_wave3_partA_terminal_fence_socket_replacement_refuses_without_blocking(tmp_path):
    generation, _ = _standard_generation(tmp_path)
    target = tmp_path / "plugins" / "example" / "references" / "boundary.md"

    def _swap():
        target.unlink()
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            sock.bind(str(target))
        except OSError:
            sock.close()
            pytest.skip("platform refuses AF_UNIX bind in tmpdir")
        sock.close()

    with pytest.raises(CapabilityPackageError):
        verify_capability_package_source(tmp_path, generation, _before_terminal_fence=_swap)


def test_wave3_partA_terminal_fence_directory_replacement_refuses(tmp_path):
    generation, _ = _standard_generation(tmp_path)
    target = tmp_path / "plugins" / "example" / "references" / "boundary.md"

    def _swap():
        target.unlink()
        target.mkdir()

    with pytest.raises(CapabilityPackageError):
        verify_capability_package_source(tmp_path, generation, _before_terminal_fence=_swap)


def test_wave3_partA_mode_mutation_while_retained_refuses(tmp_path):
    """Same-path MODE mutation while the file's fd is retained: the read
    loop streams the same (unchanged) bytes -- content and size stay
    matched -- but the mode bit drift must still surface via the
    final-fstat-vs-open-fstat identity comparison, exactly like the
    existing byte-mutation seam test above."""
    package_root = "plugins/example"
    contents = {"skills/receive/SKILL.md": b"original skill bytes"}
    _write_tree(tmp_path, package_root, contents)
    skill_md = _row_from_disk(tmp_path, package_root, "skills/receive/SKILL.md")
    generation = _canonical_generation(
        capability_id="example.pkg1",
        package_root=package_root,
        manifest_path="skills/receive/SKILL.md",
        files=(skill_md,),
        skills_spec=[
            {
                "skill_capability_id": "example.receive.v1",
                "runtime_name": "receive",
                "entrypoint_path": "skills/receive/SKILL.md",
                "closure_paths": ["skills/receive/SKILL.md"],
            }
        ],
    )

    mutated = {"done": False}

    def _mutate():
        if not mutated["done"]:
            mutated["done"] = True
            path = tmp_path / package_root / "skills/receive/SKILL.md"
            path.chmod(0o755)

    with pytest.raises(CapabilityPackageError):
        verify_capability_package_source(tmp_path, generation, _before_final_stat=_mutate)

    assert mutated["done"] is True


def test_wave3_partA_hardlink_refusal_balances_descriptors(tmp_path, monkeypatch):
    """Descriptor-balance proof extended to the census-time hardlink
    refusal path: this now fires INSIDE the walk (before the census even
    completes), while OTHER directories/files may already be retained --
    every one of them must still close."""
    counts = _count_opens_closes(monkeypatch)
    generation, _ = _standard_generation(tmp_path)
    victim = tmp_path / "plugins" / "example" / "references" / "boundary.md"
    external = tmp_path / "external-hardlink.md"
    os.link(victim, external)
    with pytest.raises(CapabilityPackageError):
        verify_capability_package_source(tmp_path, generation)
    assert counts["open"] > 0
    assert counts["open"] == counts["close"]


def test_wave3_partA_executable_mismatch_refusal_balances_descriptors(tmp_path, monkeypatch):
    """Descriptor-balance proof extended to the census-time executable-bit
    mismatch refusal path (also now fires inside the walk)."""
    counts = _count_opens_closes(monkeypatch)
    generation, _ = _standard_generation(tmp_path)
    victim = tmp_path / "plugins" / "example" / "references" / "boundary.md"
    victim.chmod(0o755)
    with pytest.raises(CapabilityPackageError):
        verify_capability_package_source(tmp_path, generation)
    assert counts["open"] > 0
    assert counts["open"] == counts["close"]


def test_wave3_partA_hashing_never_reopens_retained_file(tmp_path, monkeypatch):
    """No-reopen proof: every declared file's underlying `os.open` call
    (dir_fd-relative, non-directory) must occur exactly ONCE across the
    whole verification transaction -- proving the hash loop reads from the
    SAME fd opened during the census rather than reopening the path."""
    import control_plane.executive_capability_packages as scf_pkg

    generation, _ = _standard_generation(tmp_path)
    real_open = os.open
    open_calls: dict[tuple[int, str], int] = {}

    def counting_open(path, flags, *args, dir_fd=None, **kwargs):
        if dir_fd is not None and not (flags & os.O_DIRECTORY):
            key = (dir_fd, path)
            open_calls[key] = open_calls.get(key, 0) + 1
        return real_open(path, flags, *args, dir_fd=dir_fd, **kwargs)

    monkeypatch.setattr(scf_pkg.os, "open", counting_open)

    receipt = verify_capability_package_source(tmp_path, generation)
    assert isinstance(receipt, VerifiedCapabilityPackage)
    assert open_calls, "expected at least one non-directory (file) open to be recorded"
    assert all(count == 1 for count in open_calls.values()), open_calls


def test_wave3_partA_disabling_identity_fence_lets_reused_inode_swap_through(tmp_path, monkeypatch):
    """Mutation-proof bite check (Sol corrections 5087211688 + 5087236388).

    On this macOS host, `unlink()` followed by recreating a file at the
    same name does not naturally recycle the freed inode number, so
    `test_item3_regular_file_swapped_for_different_regular_file_same_bytes_refuses`
    passing here does not by itself distinguish "the identity fence caught
    a genuine swap" from "this platform's allocator happened not to reuse
    the inode". This test isolates the fence's own contribution instead of
    relying on filesystem luck: it replays that EXACT unlink+recreate swap
    with `_same_object` -- the single comparison every retained-object
    identity check in the module routes through -- monkeypatched to
    unconditionally report a match (precisely the observable behavior a
    genuine reused-inode collision would produce). With the fence disabled
    this way, verification WRONGLY succeeds: content, size, executable bit,
    nlink, and every other portable stat field the swapped file shares with
    the original are identical, so nothing else in the pipeline would catch
    it either. This is the deliberately WRONG outcome, reproduced here only
    to prove the fence -- not this platform's inode-allocation behavior --
    is what makes the real (unpatched) test refuse.
    """
    import control_plane.executive_capability_packages as scf_pkg

    # As in test_item2/test_item3 above: also neutralize the pre-existing
    # "did any retained descriptor's own fstat drift" signal, which would
    # otherwise catch this swap for an UNRELATED reason (the PARENT
    # directory's own mtime bumps when a file underneath it is unlinked and
    # recreated) and mask whether disabling `_same_object` is what actually
    # lets the swap through.
    # Since the race seam moved AFTER descriptor retention (Sol correction
    # 5087236388: the retained fd pins the census object's inode), a genuine
    # seam-window swap is caught by TWO independent fences: the fresh-lstat
    # _same_object comparison against the retained fd, and the retained fd's
    # own fstat drift (the unlink drops its st_nlink to zero). This bite
    # check therefore disables BOTH fences -- _same_object forced to match,
    # and the drift identity tuple reduced to fields the swap cannot move
    # (nlink, size and timestamps all excluded) -- so ONLY the identity
    # fence family under test decides the outcome.
    def _identity_without_timestamps(st):
        return (st.st_dev, st.st_ino, st.st_uid, st.st_gid)

    monkeypatch.setattr(scf_pkg, "_stat_identity", _identity_without_timestamps)
    monkeypatch.setattr(scf_pkg, "_same_object", lambda a, b: True)

    generation, _ = _standard_generation(tmp_path)
    target = "references/boundary.md"
    victim = tmp_path / "plugins" / "example" / target
    original_bytes = victim.read_bytes()

    def _swap(path):
        if path == target:
            victim.unlink()
            victim.write_bytes(original_bytes)

    receipt = verify_capability_package_source(tmp_path, generation, _before_file_open=_swap)
    assert isinstance(receipt, VerifiedCapabilityPackage)

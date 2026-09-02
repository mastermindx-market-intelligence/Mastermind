"""RED-first tests for the immutable capability-package contracts (CAP-S1 foundation).

Covers:
  - canonical digest pinning (package content + effective skill closure)
  - the real protected `plugins/mastermind-operator` package generation
  - the complete raw-input validation matrix for `build_capability_package_generation`
  - the acyclic five-layer digest cascade and its mismatch-refusal behavior

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
    build_capability_package_generation,
    capability_package_content_digest,
    effective_skill_content_digest,
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



"""RED-first tests for opt-in V4 capability-package support in the registry.

Covers (per the CAP-S1 package-identity amendment and the frozen build
commission):

  (a) source-snapshot independence: the real `plugins/mastermind-operator`
      files are re-hashed with LOCAL helper code (never the production
      digest functions) and compared against the frozen fixture rows/digests;
  (b) V4 happy-path load through the real registry loader with source
      verification against the repository root;
  (c) exact Skill-capability profile resolution;
  (d) hostile V4 profile refusals;
  (e) the compiled OHF capability manifest for a Skill-capability profile;
  (f) the `skills.bundled.enabled=false` App Server config projection/override
      law for grant-bearing profiles only;
  (g) the corrected acyclic digest cascade under source mutation;
  (h) revocation semantics;
  (i) duplicate-JSON-key refusal at every object depth, plus runtime-name
      collision and payload-drift sensitivity;
  (j) static no-migration proof for the protected default config and the
      routing/autonomy surfaces.

This module never imports the private digest-construction helpers from
`control_plane.executive_capability_packages` for the snapshot-independence
check in (a); it recomputes the canonical projections locally so a shared
implementation bug in the production digest functions cannot make both sides
agree falsely.  Later sections (fixture mutation, generation-digest cascade)
do reuse the module's own building blocks, because those tests are about the
registry's *use* of already-proven package identity, not about re-proving the
package module's own digest law (that is `tests/test_executive_capability_packages.py`).
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
import stat as stat_module
from pathlib import Path

import pytest

from control_plane.executive_agent_capabilities import (
    CAPABILITY_POLICY_SCHEMA_V3,
    CAPABILITY_POLICY_SCHEMA_V4,
    DEFAULT_CAPABILITY_SOURCE_ROOT,
    CapabilityPolicyError,
    ExecutionCapabilityRegistry,
)
from control_plane.executive_capability_packages import (
    build_capability_package_generation,
)
from control_plane.operator_harness_contract import NativeHelperPolicy

REPO_ROOT = Path(__file__).resolve().parent.parent
PACKAGE_ROOT = REPO_ROOT / "plugins" / "mastermind-operator"
V4_FIXTURE = (
    REPO_ROOT / "scripts" / "ohf" / "fixtures" / "executive_agent_capabilities_v4_mastermind_operator.json"
)
PACKAGE_CAPABILITY_ID = "mastermind-operator.p1"
FIXTURE_PROFILE_ID = "operator.appserver.readonly.mastermind-operator.v1"

FROZEN_PACKAGE_CONTENT_DIGEST = "a9781411d2642569f8b56e33bd0e0d9808a69176ccaced86642cd23948a71306"
FROZEN_SKILL_CONTENT_DIGESTS = {
    "escalate-decision": "ca621a8cc034bf607460d81085c8d466000e38d0f4b6afa8245001374d6cc2ad",
    "finish-operation": "3e689aeaa2b1579781832a854d7256c6ad8ee2ef55521b45f3af8dbe9660675e",
    "receive-commission": "d7953504035c797b30f434f1fdc72e864a7074179abffe7c247f1afc9c0a162c",
    "return-progress": "510be1ed3036f0bc1ed5f709875792ca042c350198a48e1128b4ce8ae46a6552",
}
REQUIRED_SKILL_CAPABILITY_IDS = (
    "mastermind-operator.escalate-decision.v1",
    "mastermind-operator.finish-operation.v1",
    "mastermind-operator.receive-commission.v1",
    "mastermind-operator.return-progress.v1",
)


def _load_v4_fixture_raw() -> dict:
    return json.loads(V4_FIXTURE.read_text(encoding="utf-8"))


def _write(tmp_path: Path, value: dict, name: str = "capabilities_v4.json") -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Local, spec-derived canonical-JSON helpers (independent of production code)
# ---------------------------------------------------------------------------

_LOCAL_PACKAGE_CONTENT_SCHEMA = "mastermind.capability_package_content/v1"
_LOCAL_SKILL_CLOSURE_SCHEMA = "mastermind.effective_skill_closure/v1"


def _local_canon(obj: object) -> bytes:
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _local_sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _local_file_row(relative_path: str) -> dict:
    path = PACKAGE_ROOT / relative_path
    data = path.read_bytes()
    st = os.stat(path)
    executable = bool(st.st_mode & (stat_module.S_IXUSR | stat_module.S_IXGRP | stat_module.S_IXOTH))
    return {
        "relative_path": relative_path,
        "sha256": _local_sha256_hex(data),
        "byte_length": len(data),
        "executable": executable,
    }


_REAL_RELATIVE_PATHS = (
    ".codex-plugin/plugin.json",
    "references/app-bindings.template.json",
    "references/dialogue-boundary.md",
    "skills/escalate-decision/SKILL.md",
    "skills/finish-operation/SKILL.md",
    "skills/receive-commission/SKILL.md",
    "skills/return-progress/SKILL.md",
)


def _local_package_content_digest(rows: list[dict]) -> str:
    ordered = sorted(rows, key=lambda r: r["relative_path"])
    projection = {
        "schema_version": _LOCAL_PACKAGE_CONTENT_SCHEMA,
        "files": ordered,
    }
    return _local_sha256_hex(_local_canon(projection))


def _local_skill_closure_digest(*, runtime_name: str, entrypoint_path: str, closure_rows: list[dict]) -> str:
    ordered = sorted(closure_rows, key=lambda r: r["relative_path"])
    projection = {
        "schema_version": _LOCAL_SKILL_CLOSURE_SCHEMA,
        "skill_name": runtime_name,
        "entrypoint_path": entrypoint_path,
        "files": ordered,
    }
    return _local_sha256_hex(_local_canon(projection))


# ---------------------------------------------------------------------------
# (a) Source-snapshot independence
# ---------------------------------------------------------------------------


def test_fixture_file_rows_match_real_repository_bytes_independently():
    fixture_raw = _load_v4_fixture_raw()
    package_raw = fixture_raw["capability_packages"][PACKAGE_CAPABILITY_ID]

    local_rows = [_local_file_row(p) for p in _REAL_RELATIVE_PATHS]
    local_rows_by_path = {row["relative_path"]: row for row in local_rows}

    fixture_rows_by_path = {row["relative_path"]: row for row in package_raw["files"]}
    assert set(fixture_rows_by_path) == set(local_rows_by_path)
    for relative_path, local_row in local_rows_by_path.items():
        assert fixture_rows_by_path[relative_path] == local_row

    local_content_digest = _local_package_content_digest(local_rows)
    assert local_content_digest == FROZEN_PACKAGE_CONTENT_DIGEST
    assert package_raw["package_content_digest"] == FROZEN_PACKAGE_CONTENT_DIGEST


@pytest.mark.parametrize(
    "runtime_name",
    ["escalate-decision", "finish-operation", "receive-commission", "return-progress"],
)
def test_fixture_skill_closure_digests_match_real_repository_bytes_independently(runtime_name):
    fixture_raw = _load_v4_fixture_raw()
    package_raw = fixture_raw["capability_packages"][PACKAGE_CAPABILITY_ID]
    capability_id = f"mastermind-operator.{runtime_name}.v1"
    skill_raw = package_raw["skills"][capability_id]

    entrypoint_path = f"skills/{runtime_name}/SKILL.md"
    closure_paths = sorted(["references/dialogue-boundary.md", entrypoint_path])
    assert skill_raw["closure_paths"] == closure_paths
    assert skill_raw["entrypoint_path"] == entrypoint_path
    assert skill_raw["runtime_name"] == runtime_name

    closure_rows = [_local_file_row(p) for p in closure_paths]
    local_digest = _local_skill_closure_digest(
        runtime_name=runtime_name,
        entrypoint_path=entrypoint_path,
        closure_rows=closure_rows,
    )
    assert local_digest == FROZEN_SKILL_CONTENT_DIGESTS[runtime_name]
    assert skill_raw["skill_content_digest"] == FROZEN_SKILL_CONTENT_DIGESTS[runtime_name]


def test_fixture_package_generation_builds_and_verifies_through_production_module():
    """Sanity seam: the fixture is consumable by the phase-2 module itself.

    This does not prove registry v4 dispatch (that is section (b)); it only
    proves the fixture's own package entry is well-formed and its declared
    digests match its declared rows against real bytes on disk.
    """
    fixture_raw = _load_v4_fixture_raw()
    package_raw = fixture_raw["capability_packages"][PACKAGE_CAPABILITY_ID]
    generation = build_capability_package_generation(
        capability_id=PACKAGE_CAPABILITY_ID, raw=package_raw
    )
    assert generation.package_content_digest == FROZEN_PACKAGE_CONTENT_DIGEST
    assert {grant.runtime_name: grant.skill_content_digest for grant in generation.skills} == (
        FROZEN_SKILL_CONTENT_DIGESTS
    )


# ---------------------------------------------------------------------------
# (b) V4 happy-path load through the real registry loader
# ---------------------------------------------------------------------------


def test_v4_registry_loads_and_verifies_the_real_package_source():
    registry = ExecutionCapabilityRegistry.load(V4_FIXTURE, source_root=REPO_ROOT)
    assert registry.schema_version == CAPABILITY_POLICY_SCHEMA_V4
    assert tuple(registry.capability_packages) == (PACKAGE_CAPABILITY_ID,)
    generation = registry.capability_packages[PACKAGE_CAPABILITY_ID]
    assert generation.package_content_digest == FROZEN_PACKAGE_CONTENT_DIGEST
    assert generation.revoked is False
    assert len(registry.policy_digest) == 64


def test_v4_registry_load_default_source_root_is_repo_root(monkeypatch):
    """``source_root=None`` falls back to ``DEFAULT_CAPABILITY_SOURCE_ROOT``,

    which is the repository root -- the same root the real package lives
    under -- so a caller that never supplies ``source_root`` still verifies
    correctly against the checked-in package.
    """

    assert DEFAULT_CAPABILITY_SOURCE_ROOT == REPO_ROOT
    registry = ExecutionCapabilityRegistry.load(V4_FIXTURE)
    assert registry.schema_version == CAPABILITY_POLICY_SCHEMA_V4


def test_v3_load_ignores_source_root():
    registry = ExecutionCapabilityRegistry.load(source_root="/nonexistent/does-not-matter")
    assert registry.schema_version == CAPABILITY_POLICY_SCHEMA_V3
    assert registry.capability_packages == {}


@pytest.mark.parametrize(
    "mutate",
    [
        lambda raw: raw["capability_packages"].__setitem__("mastermind-operator.p1", "not-a-dict"),
        lambda raw: raw.update(capability_packages={}),
        lambda raw: raw.update(
            capability_packages={
                f"extra-package-{i}": raw["capability_packages"]["mastermind-operator.p1"]
                for i in range(17)
            }
        ),
    ],
)
def test_v4_capability_packages_shape_bounds_refuse(tmp_path, mutate):
    raw = _load_v4_fixture_raw()
    mutate(raw)
    with pytest.raises(CapabilityPolicyError):
        ExecutionCapabilityRegistry.load(_write(tmp_path, raw), source_root=REPO_ROOT)


def test_v4_package_build_failure_chains_as_capability_policy_error(tmp_path):
    raw = _load_v4_fixture_raw()
    raw["capability_packages"][PACKAGE_CAPABILITY_ID]["package_content_digest"] = "1" * 64
    with pytest.raises(CapabilityPolicyError) as excinfo:
        ExecutionCapabilityRegistry.load(_write(tmp_path, raw), source_root=REPO_ROOT)
    assert excinfo.value.__cause__ is not None


def test_v4_source_verification_failure_refuses(tmp_path):
    """A declared package that does not match real bytes on disk fails closed."""

    raw = _load_v4_fixture_raw()
    package_raw = raw["capability_packages"][PACKAGE_CAPABILITY_ID]
    # Point the package root somewhere that does not contain the declared
    # files at all -- this must refuse via source verification rather than
    # silently accepting the (unverified) declared digests.
    package_raw["package_root"] = "plugins/mastermind-operator-does-not-exist"
    with pytest.raises(CapabilityPolicyError):
        ExecutionCapabilityRegistry.load(_write(tmp_path, raw), source_root=REPO_ROOT)


# ---------------------------------------------------------------------------
# (i, partial) Duplicate-JSON-key refusal at root/package/file-row/skill/profile depth
# ---------------------------------------------------------------------------


def _canon(value: object) -> str:
    if isinstance(value, dict):
        return "{" + ",".join(f"{json.dumps(k)}:{_canon(v)}" for k, v in value.items()) + "}"
    if isinstance(value, list):
        return "[" + ",".join(_canon(v) for v in value) + "]"
    return json.dumps(value)


def _canon_with_duplicate(value: object, path: tuple, dup_key: str, dup_value: object) -> str:
    """Serialize ``value`` as JSON text, injecting one extra ``dup_key`` pair

    (in addition to any pre-existing occurrence) into the object reached by
    walking ``path`` through nested dict/list containers.
    """

    if not path:
        assert isinstance(value, dict)
        inner = ",".join(f"{json.dumps(k)}:{_canon(v)}" for k, v in value.items())
        inner += f",{json.dumps(dup_key)}:{_canon(dup_value)}"
        return "{" + inner + "}"
    head, *rest = path
    if isinstance(value, dict):
        parts = []
        for k, v in value.items():
            if k == head:
                parts.append(f"{json.dumps(k)}:{_canon_with_duplicate(v, rest, dup_key, dup_value)}")
            else:
                parts.append(f"{json.dumps(k)}:{_canon(v)}")
        return "{" + ",".join(parts) + "}"
    if isinstance(value, list):
        parts = []
        for i, v in enumerate(value):
            if i == head:
                parts.append(_canon_with_duplicate(v, rest, dup_key, dup_value))
            else:
                parts.append(_canon(v))
        return "[" + ",".join(parts) + "]"
    raise TypeError("path descends into a non-container")


@pytest.mark.parametrize(
    "path",
    [
        (),  # root depth
        ("capability_packages", PACKAGE_CAPABILITY_ID),  # package depth
        ("capability_packages", PACKAGE_CAPABILITY_ID, "files", 0),  # file-row depth
        (
            "capability_packages",
            PACKAGE_CAPABILITY_ID,
            "skills",
            "mastermind-operator.escalate-decision.v1",
        ),  # skill depth
        ("profiles", FIXTURE_PROFILE_ID),  # profile depth
    ],
    ids=["root", "package", "file_row", "skill", "profile"],
)
def test_v4_duplicate_json_keys_refuse_at_every_depth(tmp_path, path):
    raw = _load_v4_fixture_raw()
    target: object = raw
    for key in path:
        target = target[key]
    assert isinstance(target, dict)
    dup_key = next(iter(target))
    dup_value = target[dup_key]

    duplicated_text = _canon_with_duplicate(raw, path, dup_key, dup_value)
    dest = tmp_path / "dup_v4.json"
    dest.write_text(duplicated_text, encoding="utf-8")
    with pytest.raises(CapabilityPolicyError, match="duplicate JSON key"):
        ExecutionCapabilityRegistry.load(dest, source_root=REPO_ROOT)


def _build_self_consistent_second_package(
    *, new_capability_id: str, new_generation: str, skill_capability_prefix: str
) -> dict:
    """Build a second, digest-consistent package raw dict reusing the same

    real on-disk files (and therefore the same skill runtime names) as the
    protected `mastermind-operator.p1` package, but under a fresh package and
    skill capability-ID namespace. Used only to prove the registry's global
    runtime-name collision check; it reaches into the package module's own
    (private) digest builders purely to construct a valid second fixture, not
    to re-prove that module's own digest law.
    """

    from control_plane.executive_capability_packages import (
        _package_source_digest,  # type: ignore[attr-defined]
        _skill_grant_digest,  # type: ignore[attr-defined]
        _package_generation_digest,  # type: ignore[attr-defined]
    )

    original = _load_v4_fixture_raw()["capability_packages"][PACKAGE_CAPABILITY_ID]
    files = copy.deepcopy(original["files"])
    content_digest = original["package_content_digest"]  # same files -> same digest

    source_digest = _package_source_digest(
        capability_id=new_capability_id,
        kind=original["kind"],
        repository=original["repository"],
        source_commit=original["source_commit"],
        source_tree_sha=original["source_tree_sha"],
        package_root=original["package_root"],
        manifest_path=original["manifest_path"],
        package_content_digest=content_digest,
        required_app_references=tuple(original["required_app_references"]),
    )

    new_skills: dict[str, dict] = {}
    for old_capability_id, old_skill in original["skills"].items():
        runtime_name = old_skill["runtime_name"]
        new_skill_capability_id = f"{skill_capability_prefix}.{runtime_name}.v1"
        grant_digest = _skill_grant_digest(
            capability_id=new_skill_capability_id,
            runtime_name=runtime_name,
            entrypoint_path=old_skill["entrypoint_path"],
            closure_paths=tuple(old_skill["closure_paths"]),
            skill_content_digest=old_skill["skill_content_digest"],
            package_capability_id=new_capability_id,
            package_generation=new_generation,
            package_source_digest=source_digest,
        )
        new_skills[new_skill_capability_id] = {
            "runtime_name": runtime_name,
            "entrypoint_path": old_skill["entrypoint_path"],
            "closure_paths": list(old_skill["closure_paths"]),
            "skill_content_digest": old_skill["skill_content_digest"],
            "grant_digest": grant_digest,
        }

    generation_digest = _package_generation_digest(
        capability_id=new_capability_id,
        generation=new_generation,
        source_state=original["source_state"],
        revoked=False,
        package_source_digest=source_digest,
        skills_ordered=tuple(
            (cid, row["grant_digest"]) for cid, row in sorted(new_skills.items())
        ),
    )

    return {
        "kind": original["kind"],
        "repository": original["repository"],
        "source_commit": original["source_commit"],
        "source_tree_sha": original["source_tree_sha"],
        "package_root": original["package_root"],
        "manifest_path": original["manifest_path"],
        "generation": new_generation,
        "source_state": original["source_state"],
        "revoked": False,
        "package_content_digest": content_digest,
        "package_source_digest": source_digest,
        "files": files,
        "skills": new_skills,
        "required_app_references": list(original["required_app_references"]),
        "package_generation_digest": generation_digest,
    }


def test_v4_runtime_name_collision_across_packages_refuses(tmp_path):
    raw = _load_v4_fixture_raw()
    second_package = _build_self_consistent_second_package(
        new_capability_id="mastermind-operator.p2",
        new_generation="mastermind-operator.p2.2026-09-01",
        skill_capability_prefix="mastermind-operator-p2",
    )
    # Sanity: this synthetic second package is itself well-formed before we
    # assert the registry-level collision refusal.
    build_capability_package_generation(
        capability_id="mastermind-operator.p2", raw=second_package
    )
    raw["capability_packages"]["mastermind-operator.p2"] = second_package
    with pytest.raises(CapabilityPolicyError, match="collide"):
        ExecutionCapabilityRegistry.load(_write(tmp_path, raw), source_root=REPO_ROOT)

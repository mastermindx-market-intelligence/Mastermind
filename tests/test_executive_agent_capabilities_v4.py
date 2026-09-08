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
    app_server_security_config_digest,
)
from control_plane.executive_capability_packages import (
    CapabilityPackageFile,
    build_capability_package_generation,
    capability_package_content_digest,
    effective_skill_content_digest,
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


# ---------------------------------------------------------------------------
# WAVE-3 REPAIR A, Part 2: fixed non-echoing duplicate-JSON-key refusal
# (review 5087139217 BLOCKER 4), exercised against a real V4 document at a
# nested nested depth.
# ---------------------------------------------------------------------------


def test_wave3_partB_v4_duplicate_key_shaped_like_secret_does_not_echo(tmp_path, capsys, caplog):
    poison = "sk-live-EXAMPLESECRETTOKEN"
    raw = _load_v4_fixture_raw()
    # `_canon_with_duplicate` appends ONE extra `dup_key` pair on top of
    # whatever the target object already holds -- so the target must
    # already carry an occurrence of `poison` for the appended pair to
    # produce a genuine DUPLICATE (two occurrences) rather than a single
    # novel key with no ambiguity at all.
    raw["capability_packages"][PACKAGE_CAPABILITY_ID][poison] = "irrelevant-value-1"
    duplicated_text = _canon_with_duplicate(
        raw,
        ("capability_packages", PACKAGE_CAPABILITY_ID),
        poison,
        "irrelevant-value-2",
    )
    dest = tmp_path / "dup_v4_secret.json"
    dest.write_text(duplicated_text, encoding="utf-8")

    with pytest.raises(CapabilityPolicyError) as excinfo:
        ExecutionCapabilityRegistry.load(dest, source_root=REPO_ROOT)

    exc = excinfo.value
    assert poison not in str(exc)
    assert poison not in repr(exc)

    cause = exc.__cause__
    context = exc.__context__
    assert cause is None or poison not in str(cause)
    assert cause is None or poison not in repr(cause)
    assert context is None or poison not in str(context)
    assert context is None or poison not in repr(context)

    captured = capsys.readouterr()
    assert poison not in captured.out
    assert poison not in captured.err
    assert poison not in caplog.text


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


def test_v4_changed_payload_under_same_capability_id_changes_generation_and_policy_digest(
    tmp_path,
):
    """A byte-identical re-declaration of the same package/policy loads with

    the same digests; changing the payload under the same capability ID
    (here: revoking it, which is a declared-field change, not a source-file
    change) must move the generation and policy digest.
    """

    baseline = ExecutionCapabilityRegistry.load(V4_FIXTURE, source_root=REPO_ROOT)
    raw = _load_v4_fixture_raw()
    package_raw = raw["capability_packages"][PACKAGE_CAPABILITY_ID]
    _flip_revoked(package_raw, revoked=True)
    # The fixture profile references this package's skills, so it must be
    # dropped for this raw to still resolve to a loadable (if diagnostic)
    # registry -- revocation-vs-profile-reference refusal is covered by the
    # dedicated revocation tests below.
    raw["profiles"].pop(FIXTURE_PROFILE_ID)
    mutated = ExecutionCapabilityRegistry.load(_write(tmp_path, raw), source_root=REPO_ROOT)
    assert (
        mutated.capability_packages[PACKAGE_CAPABILITY_ID].package_generation_digest
        != baseline.capability_packages[PACKAGE_CAPABILITY_ID].package_generation_digest
    )
    assert mutated.policy_digest != baseline.policy_digest


def _flip_revoked(package_raw: dict, *, revoked: bool) -> dict:
    """Mutate ``package_raw`` in place to the given revocation state,

    recomputing ``package_generation_digest`` (the only digest revocation
    affects per the acyclic identity graph -- source/closure/grant digests
    are untouched by revocation).
    """

    from control_plane.executive_capability_packages import (
        _package_generation_digest,  # type: ignore[attr-defined]
    )

    package_raw["revoked"] = revoked
    skills_ordered = tuple(
        (cid, row["grant_digest"]) for cid, row in sorted(package_raw["skills"].items())
    )
    package_raw["package_generation_digest"] = _package_generation_digest(
        capability_id=PACKAGE_CAPABILITY_ID,
        generation=package_raw["generation"],
        source_state=package_raw["source_state"],
        revoked=revoked,
        package_source_digest=package_raw["package_source_digest"],
        skills_ordered=skills_ordered,
    )
    return package_raw


# ---------------------------------------------------------------------------
# (c) Exact Skill-capability profile resolution
# ---------------------------------------------------------------------------


def test_v4_profile_resolves_exact_skill_grants_and_compatibility_names():
    registry = ExecutionCapabilityRegistry.load(V4_FIXTURE, source_root=REPO_ROOT)
    profile = registry.resolve(FIXTURE_PROFILE_ID)
    assert profile.skills == (
        "escalate-decision",
        "finish-operation",
        "receive-commission",
        "return-progress",
    )
    assert tuple(grant.capability_id for grant in profile.skill_grants) == (
        REQUIRED_SKILL_CAPABILITY_IDS
    )
    assert profile.plugins == ()
    assert profile.write_capable is False
    assert profile.native_helper_policy is NativeHelperPolicy.DISABLED
    assert profile.execution_surface == "codex-app-server"
    assert profile.sandbox_policy == "read-only"


def test_v4_default_config_profiles_have_no_skill_grants_when_capabilities_empty():
    """A V4 profile with ``skill_capabilities: []`` behaves exactly like the

    V3 runtime-name path: ``skill_grants`` stays empty and ``skills`` is
    whatever the raw ``skills`` field says (empty for every default profile
    copied unchanged into the fixture).
    """

    registry = ExecutionCapabilityRegistry.load(V4_FIXTURE, source_root=REPO_ROOT)
    for profile_id, profile in registry.profiles.items():
        if profile_id == FIXTURE_PROFILE_ID:
            continue
        assert profile.skill_grants == ()


# ---------------------------------------------------------------------------
# (d) Hostile V4 profile refusals
# ---------------------------------------------------------------------------


def _raw_with_mutated_fixture_profile(**overrides) -> dict:
    raw = _load_v4_fixture_raw()
    raw["profiles"][FIXTURE_PROFILE_ID] = {
        **raw["profiles"][FIXTURE_PROFILE_ID],
        **overrides,
    }
    return raw


def test_v4_profile_refuses_unknown_skill_capability_id(tmp_path):
    raw = _raw_with_mutated_fixture_profile(
        skill_capabilities=["mastermind-operator.does-not-exist.v1"]
    )
    with pytest.raises(CapabilityPolicyError, match="unknown"):
        ExecutionCapabilityRegistry.load(_write(tmp_path, raw), source_root=REPO_ROOT)


def test_v4_profile_refuses_duplicate_skill_capability_id_in_list(tmp_path):
    raw = _raw_with_mutated_fixture_profile(
        skill_capabilities=[
            "mastermind-operator.escalate-decision.v1",
            "mastermind-operator.escalate-decision.v1",
        ]
    )
    with pytest.raises(CapabilityPolicyError, match="duplicate"):
        ExecutionCapabilityRegistry.load(_write(tmp_path, raw), source_root=REPO_ROOT)


def test_v4_profile_refuses_revoked_package_generation_reference(tmp_path):
    raw = _load_v4_fixture_raw()
    _flip_revoked(raw["capability_packages"][PACKAGE_CAPABILITY_ID], revoked=True)
    with pytest.raises(CapabilityPolicyError, match="revoked"):
        ExecutionCapabilityRegistry.load(_write(tmp_path, raw), source_root=REPO_ROOT)


def test_v4_profile_refuses_non_empty_skills_combined_with_skill_capabilities(tmp_path):
    raw = _raw_with_mutated_fixture_profile(
        skills=["escalate-decision"],
        skill_capabilities=list(REQUIRED_SKILL_CAPABILITY_IDS),
    )
    with pytest.raises(CapabilityPolicyError, match="combine"):
        ExecutionCapabilityRegistry.load(_write(tmp_path, raw), source_root=REPO_ROOT)


def test_v4_profile_refuses_codex_exec_with_skill_capabilities(tmp_path):
    raw = _raw_with_mutated_fixture_profile(execution_surface="codex-exec")
    with pytest.raises(CapabilityPolicyError, match="codex-exec"):
        ExecutionCapabilityRegistry.load(_write(tmp_path, raw), source_root=REPO_ROOT)


def test_v4_profile_refuses_write_capable_with_skill_capabilities(tmp_path):
    raw = _raw_with_mutated_fixture_profile(
        write_capable=True, sandbox_policy="workspace-write"
    )
    with pytest.raises(CapabilityPolicyError, match="write-capable"):
        ExecutionCapabilityRegistry.load(_write(tmp_path, raw), source_root=REPO_ROOT)


def test_v4_browser_profile_refuses_skill_capabilities(tmp_path):
    raw = _load_v4_fixture_raw()
    raw["profiles"]["operator.browser.local-review.v1"]["skill_capabilities"] = [
        "mastermind-operator.escalate-decision.v1"
    ]
    with pytest.raises(CapabilityPolicyError, match="browser"):
        ExecutionCapabilityRegistry.load(_write(tmp_path, raw), source_root=REPO_ROOT)


def test_v4_profile_refuses_non_empty_plugins_regardless_of_skill_capabilities(tmp_path):
    raw = _raw_with_mutated_fixture_profile(plugins=["something"])
    with pytest.raises(CapabilityPolicyError, match="plugins"):
        ExecutionCapabilityRegistry.load(_write(tmp_path, raw), source_root=REPO_ROOT)


# ---------------------------------------------------------------------------
# (e) Compiled OHF capability manifest
# ---------------------------------------------------------------------------


def test_v4_capability_manifest_compiles_exact_skill_closure_identities():
    registry = ExecutionCapabilityRegistry.load(V4_FIXTURE, source_root=REPO_ROOT)
    profile = registry.resolve(FIXTURE_PROFILE_ID)
    manifest = profile.capability_manifest(harness_binary_digest="a" * 64)
    assert [
        (item.kind, item.name, item.skill_content_digest) for item in manifest.required
    ] == [
        ("skill", "escalate-decision", FROZEN_SKILL_CONTENT_DIGESTS["escalate-decision"]),
        ("skill", "finish-operation", FROZEN_SKILL_CONTENT_DIGESTS["finish-operation"]),
        ("skill", "receive-commission", FROZEN_SKILL_CONTENT_DIGESTS["receive-commission"]),
        ("skill", "return-progress", FROZEN_SKILL_CONTENT_DIGESTS["return-progress"]),
    ]
    assert all(item.harness_binary_digest == "a" * 64 for item in manifest.required)
    assert manifest.allowed_ambient == ()
    assert manifest.forbidden == ()
    assert manifest.unclassified_policy == "fail_closed_on_write"


# ---------------------------------------------------------------------------
# (f) skills.bundled.enabled=false projection/override law
# ---------------------------------------------------------------------------


def test_v4_grant_bearing_profile_disables_bundled_skills():
    registry = ExecutionCapabilityRegistry.load(V4_FIXTURE, source_root=REPO_ROOT)
    profile = registry.resolve(FIXTURE_PROFILE_ID)
    assert profile.app_server_config_projection()["skills"] == {
        "bundled": {"enabled": False},
        "config": None,
    }
    assert "skills.bundled.enabled=false" in profile.app_server_config_overrides()


@pytest.mark.parametrize(
    "profile_id",
    [
        "operator.appserver.readonly.v1",
        "operator.appserver.readonly.docs-mcp.v1",
        "operator.browser.local-review.v1",
    ],
)
def test_v4_copied_v3_shaped_profiles_keep_current_skills_projection(profile_id):
    registry = ExecutionCapabilityRegistry.load(V4_FIXTURE, source_root=REPO_ROOT)
    profile = registry.resolve(profile_id)
    assert profile.app_server_config_projection()["skills"] == {"config": None}
    assert "skills.bundled.enabled=false" not in profile.app_server_config_overrides()


def test_v4_observed_config_projection_matches_expected_digest_with_bundled_disabled():
    """CAP-S1 config-digest attestation gap closure (protocol amendment §5).

    The observed-side projection (``app_server_security_config_projection``)
    must now agree with the policy-side projection
    (``ExecutionCapabilityProfile.app_server_config_projection``) on the
    ``skills`` shape for a V4 skill-grant profile: both must carry
    ``bundled.enabled=False``. A config whose reported ``skills.bundled`` is
    malformed (not a mapping, or a non-boolean ``enabled``) must stay
    distinguishable from the well-formed shape and therefore digest
    differently -- this is the fail-closed drift signal the amendment
    requires.
    """

    registry = ExecutionCapabilityRegistry.load(V4_FIXTURE, source_root=REPO_ROOT)
    profile = registry.resolve(FIXTURE_PROFILE_ID)
    expected_projection = profile.app_server_config_projection()
    assert expected_projection["skills"] == {
        "bundled": {"enabled": False},
        "config": None,
    }

    # A raw ``config/read`` response shaped exactly like the policy
    # projection (this is what the fixed observed-side projection now
    # produces from a real App Server that echoes ``skills.bundled``).
    assert app_server_security_config_digest(expected_projection) == (
        profile.expected_config_digest
    )

    # Malformed: "bundled" present but not a mapping.
    non_mapping_bundled = copy.deepcopy(expected_projection)
    non_mapping_bundled["skills"]["bundled"] = "not-a-mapping"
    assert app_server_security_config_digest(non_mapping_bundled) != (
        profile.expected_config_digest
    )

    # Malformed: "bundled" is a mapping but "enabled" is not a boolean.
    non_bool_enabled = copy.deepcopy(expected_projection)
    non_bool_enabled["skills"]["bundled"] = {"enabled": "false"}
    assert app_server_security_config_digest(non_bool_enabled) != (
        profile.expected_config_digest
    )

    # Malformed: "bundled" key present but empty -- absence of "enabled"
    # must not be silently treated as False.
    missing_enabled = copy.deepcopy(expected_projection)
    missing_enabled["skills"]["bundled"] = {}
    assert app_server_security_config_digest(missing_enabled) != (
        profile.expected_config_digest
    )


# ---------------------------------------------------------------------------
# (g) Corrected acyclic digest cascade under source mutation
# ---------------------------------------------------------------------------


def _copy_package_source(tmp_path: Path) -> Path:
    source_root = tmp_path / "source_root"
    dest = source_root / "plugins" / "mastermind-operator"
    dest.parent.mkdir(parents=True)
    shutil.copytree(PACKAGE_ROOT, dest)
    return source_root


def _rebuild_package_raw_from_disk(source_root: Path) -> dict:
    """Recompute a fully self-consistent V4 package raw dict from whatever

    bytes currently sit under ``source_root/plugins/mastermind-operator``,
    using the package module's own (public and private) digest builders.
    This is a registry-consumption test helper, not a re-proof of the
    package module's own digest law (that lives in
    ``tests/test_executive_capability_packages.py``); it exists so this
    module can prove the REGISTRY's exact acyclic propagation of a source
    mutation into profile/policy identity.
    """

    from control_plane.executive_capability_packages import (
        _package_source_digest,  # type: ignore[attr-defined]
        _skill_grant_digest,  # type: ignore[attr-defined]
        _package_generation_digest,  # type: ignore[attr-defined]
    )

    package_dir = source_root / "plugins" / "mastermind-operator"
    original = _load_v4_fixture_raw()["capability_packages"][PACKAGE_CAPABILITY_ID]

    file_objs = []
    for rel in _REAL_RELATIVE_PATHS:
        data = (package_dir / rel).read_bytes()
        st = os.stat(package_dir / rel)
        executable = bool(st.st_mode & (stat_module.S_IXUSR | stat_module.S_IXGRP | stat_module.S_IXOTH))
        file_objs.append(
            CapabilityPackageFile(
                relative_path=rel,
                sha256=_local_sha256_hex(data),
                byte_length=len(data),
                executable=executable,
            )
        )
    files_by_path = {f.relative_path: f for f in file_objs}
    content_digest = capability_package_content_digest(tuple(file_objs))

    source_digest = _package_source_digest(
        capability_id=PACKAGE_CAPABILITY_ID,
        kind=original["kind"],
        repository=original["repository"],
        source_commit=original["source_commit"],
        source_tree_sha=original["source_tree_sha"],
        package_root=original["package_root"],
        manifest_path=original["manifest_path"],
        package_content_digest=content_digest,
        required_app_references=tuple(original["required_app_references"]),
    )

    skills_raw: dict[str, dict] = {}
    skill_content_digests: dict[str, str] = {}
    for capability_id, old_skill in sorted(original["skills"].items()):
        runtime_name = old_skill["runtime_name"]
        entrypoint_path = old_skill["entrypoint_path"]
        closure_paths = tuple(old_skill["closure_paths"])
        closure_files = tuple(files_by_path[p] for p in closure_paths)
        skill_digest = effective_skill_content_digest(
            runtime_name=runtime_name,
            entrypoint_path=entrypoint_path,
            closure_files=closure_files,
        )
        skill_content_digests[runtime_name] = skill_digest
        grant_digest = _skill_grant_digest(
            capability_id=capability_id,
            runtime_name=runtime_name,
            entrypoint_path=entrypoint_path,
            closure_paths=closure_paths,
            skill_content_digest=skill_digest,
            package_capability_id=PACKAGE_CAPABILITY_ID,
            package_generation=original["generation"],
            package_source_digest=source_digest,
        )
        skills_raw[capability_id] = {
            "runtime_name": runtime_name,
            "entrypoint_path": entrypoint_path,
            "closure_paths": list(closure_paths),
            "skill_content_digest": skill_digest,
            "grant_digest": grant_digest,
        }

    generation_digest = _package_generation_digest(
        capability_id=PACKAGE_CAPABILITY_ID,
        generation=original["generation"],
        source_state=original["source_state"],
        revoked=False,
        package_source_digest=source_digest,
        skills_ordered=tuple(
            (cid, row["grant_digest"]) for cid, row in sorted(skills_raw.items())
        ),
    )

    return {
        "kind": original["kind"],
        "repository": original["repository"],
        "source_commit": original["source_commit"],
        "source_tree_sha": original["source_tree_sha"],
        "package_root": original["package_root"],
        "manifest_path": original["manifest_path"],
        "generation": original["generation"],
        "source_state": original["source_state"],
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
            for f in file_objs
        ],
        "skills": skills_raw,
        "required_app_references": list(original["required_app_references"]),
        "package_generation_digest": generation_digest,
    }, skill_content_digests


def _load_registry_from_source_root(tmp_path: Path, source_root: Path, name: str):
    package_raw, skill_digests = _rebuild_package_raw_from_disk(source_root)
    raw = _load_v4_fixture_raw()
    raw["capability_packages"][PACKAGE_CAPABILITY_ID] = package_raw
    policy_path = _write(tmp_path, raw, name=name)
    registry = ExecutionCapabilityRegistry.load(policy_path, source_root=source_root)
    return registry, skill_digests


def test_v4_baseline_mutation_helper_reproduces_the_frozen_fixture(tmp_path):
    """Sanity: rebuilding from an UNMUTATED copy reproduces the exact frozen

    digests, so every mutation assertion below is measured against a proven
    baseline rather than an already-drifted one.
    """

    source_root = _copy_package_source(tmp_path)
    registry, skill_digests = _load_registry_from_source_root(tmp_path, source_root, "baseline.json")
    generation = registry.capability_packages[PACKAGE_CAPABILITY_ID]
    assert generation.package_content_digest == FROZEN_PACKAGE_CONTENT_DIGEST
    assert generation.package_generation_digest == (
        "37836a5986c916a58217b95d1976220eae8827e4e588a50677011c2543e43b97"
    )
    assert skill_digests == FROZEN_SKILL_CONTENT_DIGESTS
    baseline_registry = ExecutionCapabilityRegistry.load(V4_FIXTURE, source_root=REPO_ROOT)
    assert registry.policy_digest == baseline_registry.policy_digest
    assert registry.resolve(FIXTURE_PROFILE_ID).profile_digest == (
        baseline_registry.resolve(FIXTURE_PROFILE_ID).profile_digest
    )


def test_v4_entrypoint_byte_change_moves_only_its_own_closure_and_the_cascade(tmp_path):
    source_root = _copy_package_source(tmp_path)
    baseline_registry, baseline_skill_digests = _load_registry_from_source_root(
        tmp_path, source_root, "baseline.json"
    )
    baseline_generation = baseline_registry.capability_packages[PACKAGE_CAPABILITY_ID]
    baseline_profile_digest = baseline_registry.resolve(FIXTURE_PROFILE_ID).profile_digest

    entrypoint = source_root / "plugins" / "mastermind-operator" / "skills" / "escalate-decision" / "SKILL.md"
    entrypoint.write_bytes(entrypoint.read_bytes() + b"\n<!-- mutated -->\n")

    mutated_registry, mutated_skill_digests = _load_registry_from_source_root(
        tmp_path, source_root, "mutated.json"
    )
    mutated_generation = mutated_registry.capability_packages[PACKAGE_CAPABILITY_ID]

    assert mutated_skill_digests["escalate-decision"] != baseline_skill_digests["escalate-decision"]
    for runtime_name in ("finish-operation", "receive-commission", "return-progress"):
        assert mutated_skill_digests[runtime_name] == baseline_skill_digests[runtime_name]

    assert mutated_generation.package_content_digest != baseline_generation.package_content_digest
    assert mutated_generation.package_generation_digest != baseline_generation.package_generation_digest
    assert (
        mutated_registry.resolve(FIXTURE_PROFILE_ID).profile_digest != baseline_profile_digest
    )
    assert mutated_registry.policy_digest != baseline_registry.policy_digest


def test_v4_shared_dialogue_reference_change_moves_all_four_closures(tmp_path):
    source_root = _copy_package_source(tmp_path)
    _baseline_registry, baseline_skill_digests = _load_registry_from_source_root(
        tmp_path, source_root, "baseline.json"
    )

    shared = source_root / "plugins" / "mastermind-operator" / "references" / "dialogue-boundary.md"
    shared.write_bytes(shared.read_bytes() + b"\n<!-- mutated -->\n")

    _mutated_registry, mutated_skill_digests = _load_registry_from_source_root(
        tmp_path, source_root, "mutated.json"
    )
    for runtime_name in FROZEN_SKILL_CONTENT_DIGESTS:
        assert mutated_skill_digests[runtime_name] != baseline_skill_digests[runtime_name]


@pytest.mark.parametrize(
    "relative_path",
    [
        "references/app-bindings.template.json",
        ".codex-plugin/plugin.json",
    ],
    ids=["unrelated_app_binding", "manifest"],
)
def test_v4_unrelated_or_manifest_file_change_leaves_all_closures_stable(tmp_path, relative_path):
    source_root = _copy_package_source(tmp_path)
    baseline_registry, baseline_skill_digests = _load_registry_from_source_root(
        tmp_path, source_root, "baseline.json"
    )
    baseline_generation = baseline_registry.capability_packages[PACKAGE_CAPABILITY_ID]
    baseline_profile_digest = baseline_registry.resolve(FIXTURE_PROFILE_ID).profile_digest

    target = source_root / "plugins" / "mastermind-operator" / relative_path
    target.write_bytes(target.read_bytes() + b"\n")

    mutated_registry, mutated_skill_digests = _load_registry_from_source_root(
        tmp_path, source_root, "mutated.json"
    )
    mutated_generation = mutated_registry.capability_packages[PACKAGE_CAPABILITY_ID]

    assert mutated_skill_digests == baseline_skill_digests
    assert mutated_generation.package_content_digest != baseline_generation.package_content_digest
    assert mutated_generation.package_generation_digest != baseline_generation.package_generation_digest
    assert (
        mutated_registry.resolve(FIXTURE_PROFILE_ID).profile_digest != baseline_profile_digest
    )
    assert mutated_registry.policy_digest != baseline_registry.policy_digest


def test_v4_loader_refuses_mutated_source_bytes_against_stale_declared_digests(tmp_path):
    """The loader must never accept changed source against the OLD declared

    digests: mutate a real file on disk but keep the frozen fixture's
    (now-stale) declared digests, and require refusal via source
    verification rather than silent acceptance.
    """

    source_root = _copy_package_source(tmp_path)
    entrypoint = source_root / "plugins" / "mastermind-operator" / "skills" / "return-progress" / "SKILL.md"
    entrypoint.write_bytes(entrypoint.read_bytes() + b"\n<!-- drift -->\n")

    raw = _load_v4_fixture_raw()  # still declares the OLD (now-stale) digests
    policy_path = _write(tmp_path, raw, name="stale.json")
    with pytest.raises(CapabilityPolicyError):
        ExecutionCapabilityRegistry.load(policy_path, source_root=source_root)


# ---------------------------------------------------------------------------
# (h) Revocation semantics (load-time refusal chosen per FROZEN SPEC)
# ---------------------------------------------------------------------------


def test_v4_revoked_generation_still_parses_for_diagnostics_when_unreferenced(tmp_path):
    raw = _load_v4_fixture_raw()
    _flip_revoked(raw["capability_packages"][PACKAGE_CAPABILITY_ID], revoked=True)
    del raw["profiles"][FIXTURE_PROFILE_ID]
    registry = ExecutionCapabilityRegistry.load(_write(tmp_path, raw), source_root=REPO_ROOT)
    generation = registry.capability_packages[PACKAGE_CAPABILITY_ID]
    assert generation.revoked is True
    # No source row is rewritten by revocation: files/skills/digests besides
    # package_generation_digest are exactly the frozen values.
    assert generation.package_content_digest == FROZEN_PACKAGE_CONTENT_DIGEST
    assert {g.runtime_name: g.skill_content_digest for g in generation.skills} == (
        FROZEN_SKILL_CONTENT_DIGESTS
    )


def test_v4_revocation_changes_policy_digest_but_not_source_identity(tmp_path):
    raw_live = _load_v4_fixture_raw()
    del raw_live["profiles"][FIXTURE_PROFILE_ID]
    live_registry = ExecutionCapabilityRegistry.load(
        _write(tmp_path, raw_live, name="live.json"), source_root=REPO_ROOT
    )

    raw_revoked = _load_v4_fixture_raw()
    _flip_revoked(raw_revoked["capability_packages"][PACKAGE_CAPABILITY_ID], revoked=True)
    del raw_revoked["profiles"][FIXTURE_PROFILE_ID]
    revoked_registry = ExecutionCapabilityRegistry.load(
        _write(tmp_path, raw_revoked, name="revoked.json"), source_root=REPO_ROOT
    )

    assert revoked_registry.policy_digest != live_registry.policy_digest
    assert (
        revoked_registry.capability_packages[PACKAGE_CAPABILITY_ID].package_content_digest
        == live_registry.capability_packages[PACKAGE_CAPABILITY_ID].package_content_digest
    )


# ---------------------------------------------------------------------------
# (j) Static no-migration proof
# ---------------------------------------------------------------------------


def test_default_config_has_not_migrated_to_v4():
    raw = json.loads(Path("config/executive_agent_capabilities.json").read_text(encoding="utf-8"))
    assert raw["schema_version"] == CAPABILITY_POLICY_SCHEMA_V3
    assert raw["plugins"] == {}
    assert "capability_packages" not in raw
    assert FIXTURE_PROFILE_ID not in raw["profiles"]
    for profile in raw["profiles"].values():
        assert "skill_capabilities" not in profile


@pytest.mark.parametrize(
    "path",
    [
        Path("config/executive_worker_routes.json"),
        Path("control_plane/executive_autonomy.py"),
    ],
)
def test_routing_and_autonomy_surfaces_carry_no_v4_package_identifiers(path):
    text = path.read_text(encoding="utf-8")
    assert PACKAGE_CAPABILITY_ID not in text
    assert "2026-09-01.mastermind-operator-p1-fixture" not in text

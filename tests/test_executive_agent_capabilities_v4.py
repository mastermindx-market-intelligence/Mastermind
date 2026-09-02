from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from control_plane.executive_agent_capabilities import (
    CAPABILITY_POLICY_SCHEMA,
    CAPABILITY_POLICY_SCHEMA_V3,
    CAPABILITY_POLICY_SCHEMA_V4,
    CapabilityPolicyError,
    ExecutionCapabilityRegistry,
)
from control_plane.operator_harness_contract import NativeHelperPolicy


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE = (
    REPO_ROOT
    / "scripts"
    / "ohf"
    / "fixtures"
    / "executive_agent_capabilities_v4_mastermind_operator.json"
)
PROFILE_ID = "operator.appserver.readonly.mastermind-operator.v1"
PACKAGE_ID = "mastermind-operator.p1"
SKILL_IDS = (
    "mastermind-operator.escalate-decision.v1",
    "mastermind-operator.finish-operation.v1",
    "mastermind-operator.receive-commission.v1",
    "mastermind-operator.return-progress.v1",
)
RUNTIME_NAMES = (
    "escalate-decision",
    "finish-operation",
    "receive-commission",
    "return-progress",
)
CLOSURE_DIGESTS = (
    "ca621a8cc034bf607460d81085c8d466000e38d0f4b6afa8245001374d6cc2ad",
    "3e689aeaa2b1579781832a854d7256c6ad8ee2ef55521b45f3af8dbe9660675e",
    "d7953504035c797b30f434f1fdc72e864a7074179abffe7c247f1afc9c0a162c",
    "510be1ed3036f0bc1ed5f709875792ca042c350198a48e1128b4ce8ae46a6552",
)


def _fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _write(tmp_path: Path, raw: dict, *, name: str = "policy.json") -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(raw, sort_keys=True), encoding="utf-8")
    return path


def _copy_source(tmp_path: Path) -> Path:
    source_root = tmp_path / "source"
    package = source_root / "plugins" / "mastermind-operator"
    package.parent.mkdir(parents=True)
    shutil.copytree(REPO_ROOT / "plugins" / "mastermind-operator", package)
    return source_root


def test_default_schema_alias_and_v3_identity_remain_exact() -> None:
    assert CAPABILITY_POLICY_SCHEMA == CAPABILITY_POLICY_SCHEMA_V3
    assert CAPABILITY_POLICY_SCHEMA_V3 == "mastermind.executive_agent_capabilities/v3"
    assert CAPABILITY_POLICY_SCHEMA_V4 == "mastermind.executive_agent_capabilities/v4"

    registry = ExecutionCapabilityRegistry.load()
    assert registry.schema_version == CAPABILITY_POLICY_SCHEMA_V3
    assert registry.capability_packages == {}
    assert registry.plugins == {}
    assert registry.policy_digest == (
        "b8fbfd9065764206b03f835f7fbc09910326f806584a8185229474aff59008b7"
    )
    assert registry.resolve(
        "operator.appserver.readonly.docs-mcp.native-helper.v1"
    ).profile_digest == (
        "536853fb01d69ae8deca9a028b55c90aea0d1529f1fc80d83bb20d5d54f2cc44"
    )
    assert all(profile.skill_grants == () for profile in registry.profiles.values())


def test_v4_fixture_resolves_exact_package_and_four_skill_profile() -> None:
    registry = ExecutionCapabilityRegistry.load(FIXTURE, source_root=REPO_ROOT)
    assert registry.schema_version == CAPABILITY_POLICY_SCHEMA_V4
    assert tuple(registry.capability_packages) == (PACKAGE_ID,)
    assert registry.plugins == {}
    assert registry.production_armed is False

    package = registry.capability_packages[PACKAGE_ID]
    assert package.package_content_digest == (
        "a9781411d2642569f8b56e33bd0e0d9808a69176ccaced86642cd23948a71306"
    )
    assert len(package.package_source_digest) == 64
    assert len(package.package_generation_digest) == 64
    assert package.revoked is False
    assert tuple(skill.capability_id for skill in package.skills) == SKILL_IDS
    assert tuple(skill.runtime_name for skill in package.skills) == RUNTIME_NAMES
    assert tuple(skill.skill_content_digest for skill in package.skills) == CLOSURE_DIGESTS
    assert all(len(skill.grant_digest) == 64 for skill in package.skills)

    profile = registry.resolve(PROFILE_ID)
    assert profile.execution_surface == "codex-app-server"
    assert profile.write_capable is False
    assert profile.skills == RUNTIME_NAMES
    assert tuple(skill.capability_id for skill in profile.skill_grants) == SKILL_IDS
    assert profile.native_helper_policy is NativeHelperPolicy.DISABLED
    assert profile.mcp_servers == ()
    assert profile.resource_grants == ()
    assert profile.plugins == ()
    assert profile.required_capability_names == RUNTIME_NAMES


def test_v4_profile_compiles_exact_skill_content_into_existing_manifest() -> None:
    profile = ExecutionCapabilityRegistry.load(
        FIXTURE, source_root=REPO_ROOT
    ).resolve(PROFILE_ID)
    binary_digest = "a" * 64
    manifest = profile.capability_manifest(harness_binary_digest=binary_digest)
    assert tuple((item.kind, item.name) for item in manifest.required) == tuple(
        ("skill", name) for name in RUNTIME_NAMES
    )
    assert tuple(item.skill_content_digest for item in manifest.required) == CLOSURE_DIGESTS
    assert all(item.harness_binary_digest == binary_digest for item in manifest.required)
    assert manifest.allowed_ambient == ()
    assert manifest.forbidden == ()
    assert manifest.unclassified_policy == "fail_closed_on_write"


def test_v4_skill_profile_disables_bundled_skills_without_changing_v3() -> None:
    v4 = ExecutionCapabilityRegistry.load(FIXTURE, source_root=REPO_ROOT).resolve(
        PROFILE_ID
    )
    projection = v4.app_server_config_projection()
    assert projection["skills"] == {
        "config": None,
        "bundled": {"enabled": False},
    }
    assert "skills.bundled.enabled=false" in v4.app_server_config_overrides()

    v3 = ExecutionCapabilityRegistry.load().resolve("operator.appserver.readonly.v1")
    assert v3.app_server_config_projection()["skills"] == {"config": None}
    assert "skills.bundled.enabled=false" not in v3.app_server_config_overrides()


def test_v4_load_verifies_the_real_seven_file_source_snapshot() -> None:
    registry = ExecutionCapabilityRegistry.load(FIXTURE, source_root=REPO_ROOT)
    package = registry.capability_packages[PACKAGE_ID]
    assert tuple(row.relative_path for row in package.files) == (
        ".codex-plugin/plugin.json",
        "references/app-bindings.template.json",
        "references/dialogue-boundary.md",
        "skills/escalate-decision/SKILL.md",
        "skills/finish-operation/SKILL.md",
        "skills/receive-commission/SKILL.md",
        "skills/return-progress/SKILL.md",
    )


@pytest.mark.parametrize(
    "relative_path",
    [
        ".codex-plugin/plugin.json",
        "references/app-bindings.template.json",
        "references/dialogue-boundary.md",
        "skills/receive-commission/SKILL.md",
    ],
)
def test_v4_load_refuses_source_byte_drift(tmp_path: Path, relative_path: str) -> None:
    source_root = _copy_source(tmp_path)
    path = source_root / "plugins" / "mastermind-operator" / relative_path
    path.write_bytes(path.read_bytes() + b"drift")
    with pytest.raises(CapabilityPolicyError):
        ExecutionCapabilityRegistry.load(FIXTURE, source_root=source_root)


def test_v4_duplicate_json_keys_refuse_at_every_depth(tmp_path: Path) -> None:
    original = FIXTURE.read_text(encoding="utf-8")
    duplicate_root = original.replace(
        '"schema_version": "mastermind.executive_agent_capabilities/v4",',
        '"schema_version": "mastermind.executive_agent_capabilities/v4",\n'
        '  "schema_version": "mastermind.executive_agent_capabilities/v4",',
        1,
    )
    path = tmp_path / "duplicate-root.json"
    path.write_text(duplicate_root, encoding="utf-8")
    with pytest.raises(CapabilityPolicyError, match="duplicate JSON key"):
        ExecutionCapabilityRegistry.load(path, source_root=REPO_ROOT)

    duplicate_skill = original.replace(
        '"runtime_name": "receive-commission",',
        '"runtime_name": "receive-commission",\n'
        '          "runtime_name": "receive-commission",',
        1,
    )
    path = tmp_path / "duplicate-skill.json"
    path.write_text(duplicate_skill, encoding="utf-8")
    with pytest.raises(CapabilityPolicyError, match="duplicate JSON key"):
        ExecutionCapabilityRegistry.load(path, source_root=REPO_ROOT)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("unknown", "unknown Skill"),
        ("revoked", "revoked"),
        ("write", "read-only"),
        ("codex-exec", "codex-exec"),
        ("runtime-name-collision", "runtime name"),
        ("runtime-plugins", "plugins"),
    ],
)
def test_v4_profile_and_package_widening_fail_closed(
    tmp_path: Path, mutation: str, message: str
) -> None:
    raw = _fixture()
    package = raw["capability_packages"][PACKAGE_ID]
    profile = raw["profiles"][PROFILE_ID]
    if mutation == "unknown":
        profile["skill_capabilities"][0] = "mastermind-operator.unknown.v1"
    elif mutation == "revoked":
        package["revoked"] = True
    elif mutation == "write":
        profile["write_capable"] = True
        profile["sandbox_policy"] = "workspace-write"
    elif mutation == "codex-exec":
        profile["execution_surface"] = "codex-exec"
    elif mutation == "runtime-name-collision":
        package["skills"][SKILL_IDS[1]]["runtime_name"] = "escalate-decision"
    else:
        raw["plugins"] = {"ambient": {}}
    with pytest.raises(CapabilityPolicyError, match=message):
        ExecutionCapabilityRegistry.load(_write(tmp_path, raw), source_root=REPO_ROOT)


def test_v4_digest_cascade_is_deterministic_and_revocation_changes_generation(
    tmp_path: Path,
) -> None:
    first = ExecutionCapabilityRegistry.load(FIXTURE, source_root=REPO_ROOT)
    second = ExecutionCapabilityRegistry.load(FIXTURE, source_root=REPO_ROOT)
    assert first.policy_digest == second.policy_digest
    assert first.capability_packages[PACKAGE_ID].package_generation_digest == (
        second.capability_packages[PACKAGE_ID].package_generation_digest
    )

    raw = _fixture()
    raw["capability_packages"][PACKAGE_ID]["revoked"] = True
    with pytest.raises(CapabilityPolicyError, match="revoked"):
        ExecutionCapabilityRegistry.load(_write(tmp_path, raw), source_root=REPO_ROOT)

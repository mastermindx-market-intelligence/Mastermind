"""R15 source-only admission tests for the COO domain execution profile.

R15 narrows the source contract for ``operator.coo.domain.readonly.v1``:
the canonical config stays ``enabled=false`` and ordinary resolve keeps
refusing disabled, but a temporary explicitly-enabled copy of the same
policy must load through the real ``ExecutionCapabilityRegistry`` and
resolve with the exact same identity -- only the ``enabled`` Boolean
flips. Authority widening on the enabled domain is still refused.

Scope: real ``ExecutionCapabilityRegistry`` source construction /
profile / digest identity only. Runtime quota admission, dispatch,
chain, install, network and other carriers are out of scope for this
slice and remain open.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from control_plane.executive_agent_capabilities import (
    CAPABILITY_POLICY_SCHEMA,
    COO_DOMAIN_EXECUTION_PROFILE,
    CapabilityPolicyError,
    ExecutionCapabilityRegistry,
)


# R15-ROOT-DECISION: the helper profile whose digest must remain
# unchanged after the source contract amendment is the operator
# appserver docs-MCP native-helper profile ("#1007 helper profile").
_HELPER_PROFILE_ID = "operator.appserver.readonly.docs-mcp.native-helper.v1"
_HELPER_PROFILE_DIGEST = (
    "028fce73ff8c4cb8f8ada7b514e89b74fba64b92f29db3780004a360e0995d39"
)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_policy_bytes() -> bytes:
    source = Path("config/executive_agent_capabilities.json")
    return source.read_bytes()


def _canonical_sha256() -> str:
    return _sha256_bytes(_canonical_policy_bytes())


def _load_canonical_raw() -> dict:
    return json.loads(_canonical_policy_bytes())


def _write_raw(tmp_path: Path, raw: dict) -> Path:
    path = tmp_path / "capabilities.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    return path


def _with_domain_enabled(raw: dict, enabled: object) -> dict:
    """Return a deep-copied policy with only the COO domain ``enabled`` toggled.

    Every other field is preserved verbatim. A non-boolean value is
    serialized as-is so the loader's strict Boolean guard is exercised
    rather than being smoothed out by Python's ``bool`` coercion.
    """

    mutated = json.loads(json.dumps(raw))
    mutated["profiles"][COO_DOMAIN_EXECUTION_PROFILE]["enabled"] = enabled
    return mutated


# ---------------------------------------------------------------------------
# 1. Canonical (default-installed) policy is byte-identical and refuses resolve.
# ---------------------------------------------------------------------------


def test_canonical_policy_bytes_and_default_disabled_resolve_refusal():
    raw_bytes = _canonical_policy_bytes()
    assert _sha256_bytes(raw_bytes) == (
        "31c2dccb5c3185dc92aac0cc8906fc007d3249d40c8f4483ef1f83990ccb87cd"
    )

    registry = ExecutionCapabilityRegistry.load()
    assert registry.production_armed is False
    assert registry.lifecycle_authority == "executive_os"
    assert registry.schema_version == CAPABILITY_POLICY_SCHEMA
    # The default canonical COO domain profile exists in the registry but
    # is disabled -- ordinary resolve must refuse without ever admitting
    # dispatch authority. This is the unchanged production refusal.
    profile = registry.profiles[COO_DOMAIN_EXECUTION_PROFILE]
    assert profile.enabled is False
    assert profile.write_capable is False
    assert profile.network_policy == "disabled"
    assert profile.native_helper_policy.value == "DISABLED"
    with pytest.raises(CapabilityPolicyError, match="is disabled"):
        registry.resolve(COO_DOMAIN_EXECUTION_PROFILE)


# ---------------------------------------------------------------------------
# 2. Explicitly enabled temporary copy loads and resolves with exact identity.
# ---------------------------------------------------------------------------


def test_explicitly_enabled_temporary_domain_loads_and_resolves(tmp_path):
    raw_enabled = _with_domain_enabled(_load_canonical_raw(), True)
    registry = ExecutionCapabilityRegistry.load(_write_raw(tmp_path, raw_enabled))

    profile = registry.resolve(COO_DOMAIN_EXECUTION_PROFILE)
    assert profile.enabled is True
    # Authority surface is identical to the canonical disabled shape:
    # only the activation Boolean flips, every other field stays exact.
    assert profile.execution_surface == "codex-app-server"
    assert profile.auth_realm == "dedicated-worker-account"
    assert profile.sandbox_policy == "read-only"
    assert profile.approval_policy == "never"
    assert profile.network_policy == "disabled"
    assert profile.write_capable is False
    assert profile.native_helper_policy.value == "DISABLED"
    assert profile.skills == ()
    assert profile.mcp_servers == ()
    assert profile.resource_grants == ()
    assert profile.plugins == ()
    # The resolved enabled domain still cannot grant any forbidden
    # capability, mirror the canonical disabled contract.
    assert profile.forbidden == ()


# ---------------------------------------------------------------------------
# 3. Identity of the enabled temporary copy is reproducible on reload.
# ---------------------------------------------------------------------------


def test_enabled_temporary_domain_profile_and_policy_digests_are_stable(tmp_path):
    raw_enabled = _with_domain_enabled(_load_canonical_raw(), True)
    path = _write_raw(tmp_path, raw_enabled)

    first = ExecutionCapabilityRegistry.load(path)
    second = ExecutionCapabilityRegistry.load(path)
    enabled_profile = first.resolve(COO_DOMAIN_EXECUTION_PROFILE)

    assert first.profiles[COO_DOMAIN_EXECUTION_PROFILE].profile_digest == (
        second.profiles[COO_DOMAIN_EXECUTION_PROFILE].profile_digest
    )
    assert first.policy_digest == second.policy_digest
    assert len(enabled_profile.profile_digest) == 64
    assert len(first.policy_digest) == 64

    # The #1007 helper profile is untouched by the COO domain activation
    # amendment: its digest and identity remain byte-identical to the
    # canonical default. This is the helper-profile ceiling proof.
    helper_first = first.resolve(_HELPER_PROFILE_ID)
    helper_default = ExecutionCapabilityRegistry.load().resolve(_HELPER_PROFILE_ID)
    assert helper_first.profile_digest == _HELPER_PROFILE_DIGEST
    assert helper_first.profile_digest == helper_default.profile_digest
    assert helper_first == helper_default


# ---------------------------------------------------------------------------
# 4. Disabled vs enabled same-shape policy differ in identity and digest.
# ---------------------------------------------------------------------------


def test_disabled_vs_enabled_policies_have_distinct_identity(tmp_path):
    raw_disabled = _with_domain_enabled(_load_canonical_raw(), False)
    raw_enabled = _with_domain_enabled(_load_canonical_raw(), True)

    disabled_dir = tmp_path / "disabled"
    disabled_dir.mkdir()
    enabled_dir = tmp_path / "enabled"
    enabled_dir.mkdir()

    disabled_registry = ExecutionCapabilityRegistry.load(
        _write_raw(disabled_dir, raw_disabled)
    )
    enabled_registry = ExecutionCapabilityRegistry.load(
        _write_raw(enabled_dir, raw_enabled)
    )

    disabled_profile = disabled_registry.profiles[COO_DOMAIN_EXECUTION_PROFILE]
    enabled_profile = enabled_registry.profiles[COO_DOMAIN_EXECUTION_PROFILE]

    # The activation Boolean is the only field that changed; everything
    # else is byte-identical, so profile and policy digests MUST diverge.
    assert disabled_profile.enabled is False
    assert enabled_profile.enabled is True
    assert disabled_profile.profile_digest != enabled_profile.profile_digest
    assert disabled_registry.policy_digest != enabled_registry.policy_digest

    # Resolve status flips exactly with the activation Boolean.
    with pytest.raises(CapabilityPolicyError, match="is disabled"):
        disabled_registry.resolve(COO_DOMAIN_EXECUTION_PROFILE)
    enabled_registry.resolve(COO_DOMAIN_EXECUTION_PROFILE)


# ---------------------------------------------------------------------------
# 5. Non-Boolean enabled is refused for the COO domain profile.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "non_boolean",
    ["true", 1, 0, None, [], {}, "false"],
)
def test_non_boolean_enabled_for_coo_domain_is_refused(tmp_path, non_boolean):
    raw = _with_domain_enabled(_load_canonical_raw(), non_boolean)
    with pytest.raises(CapabilityPolicyError, match="enabled must be boolean"):
        ExecutionCapabilityRegistry.load(_write_raw(tmp_path, raw))


# ---------------------------------------------------------------------------
# 6. Enabled COO domain refuses authority widening in every direction.
# ---------------------------------------------------------------------------


def _widening_cases():
    base = _load_canonical_raw()["profiles"][COO_DOMAIN_EXECUTION_PROFILE]
    return [
        pytest.param({"write_capable": True}, id="write_capable_true"),
        pytest.param({"network_policy": "loopback-browser-only"}, id="network_loopback"),
        pytest.param({"network_policy": "open"}, id="network_open"),
        pytest.param({"native_helper_policy": "parent_read_only_ceiling"}, id="helper_enabled"),
        pytest.param({"skills": ["operator.coo.domain.readonly.v1"]}, id="skills_grant"),
        pytest.param({"mcp_servers": ["openai-developer-docs-v1"]}, id="mcp_grant"),
        pytest.param({"resources": ["worker-browser-b1-local"]}, id="resource_grant"),
        pytest.param({"plugins": ["any-plugin"]}, id="plugin_grant"),
        pytest.param({"execution_surface": "codex-exec"}, id="execution_surface_sealed"),
        pytest.param({"approval_policy": "on-request"}, id="approval_on_request"),
        pytest.param({"sandbox_policy": "workspace-write"}, id="sandbox_workspace_write"),
        pytest.param({"auth_realm": "shared-corp-account"}, id="auth_realm_widened"),
    ]


@pytest.mark.parametrize("mutation", _widening_cases())
def test_enabled_coo_domain_refuses_authority_widening(tmp_path, mutation):
    raw = json.loads(json.dumps(_load_canonical_raw()))
    raw["profiles"][COO_DOMAIN_EXECUTION_PROFILE]["enabled"] = True
    raw["profiles"][COO_DOMAIN_EXECUTION_PROFILE].update(mutation)
    with pytest.raises(CapabilityPolicyError):
        ExecutionCapabilityRegistry.load(_write_raw(tmp_path, raw))


# ---------------------------------------------------------------------------
# 7. Canonical policy bytes are unchanged after the source amendment.
# ---------------------------------------------------------------------------


def test_canonical_policy_bytes_are_byte_identical_after_r15():
    """The shipped canonical config must remain untouched; only the COO

    domain shape validator in source is amended. This test exists to
    fail loudly if the amendment inadvertently mutates installed policy.
    """

    assert _canonical_sha256() == (
        "31c2dccb5c3185dc92aac0cc8906fc007d3249d40c8f4483ef1f83990ccb87cd"
    )


# ---------------------------------------------------------------------------
# 8. R16: V4 skill_capabilities ceiling for the COO domain in both enabled
#    states.  The domain guard iterates COO_DOMAIN_PROFILE_SHAPE (V3 keys) and
#    skips only ``enabled``; V4 ``skill_capabilities`` therefore leaks past
#    the guard and resolves into runtime grants in both disabled and
#    enabled forms.  These regressions prove the empty-domain-grant
#    authority ceiling holds for V4 too, that each valid nonempty V4
#    grant and their combination are refused at load in both enabled
#    states, and that the non-domain V4 grant path stays unchanged.
# ---------------------------------------------------------------------------

V4_FIXTURE_REPO_ROOT = Path(__file__).resolve().parent.parent
V4_FIXTURE_PATH = (
    V4_FIXTURE_REPO_ROOT
    / "scripts"
    / "ohf"
    / "fixtures"
    / "executive_agent_capabilities_v4_mastermind_operator.json"
)
V4_NON_DOMAIN_FIXTURE_PROFILE_ID = (
    "operator.appserver.readonly.mastermind-operator.v1"
)
V4_HELPER_PROFILE_ID = (
    "operator.appserver.readonly.docs-mcp.native-helper.v1"
)
V4_HELPER_PROFILE_DIGEST = (
    "c17033d389b316851dba3b19684e8614a18b4113e7de60197ff27009b01a264e"
)
V4_NON_DOMAIN_FIXTURE_POLICY_DIGEST = (
    "dee789035df3e2acf3578995722f7dc41c5c1a31abed2e489de588497ff9e438"
)
V4_REQUIRED_SKILL_CAPABILITY_IDS = (
    "mastermind-operator.escalate-decision.v1",
    "mastermind-operator.finish-operation.v1",
    "mastermind-operator.receive-commission.v1",
    "mastermind-operator.return-progress.v1",
)
V4_EXPECTED_RUNTIME_NAMES = (
    "escalate-decision",
    "finish-operation",
    "receive-commission",
    "return-progress",
)


def _load_v4_fixture() -> dict:
    return json.loads(V4_FIXTURE_PATH.read_text(encoding="utf-8"))


def _write_v4(tmp_path: Path, raw: dict, name: str = "capabilities_v4.json") -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(raw), encoding="utf-8")
    return path


def _coo_domain_profile_v4(*, enabled: bool, skill_capabilities: list[str]) -> dict:
    """Construct a V4 COO domain profile with the exact read-only shape.

    V4 schema requires the ``skill_capabilities`` field; the empty
    default here matches the V3 ceiling and the only legal V4 ceiling.
    """

    return {
        "enabled": enabled,
        "execution_surface": "codex-app-server",
        "auth_realm": "dedicated-worker-account",
        "sandbox_policy": "read-only",
        "approval_policy": "never",
        "network_policy": "disabled",
        "write_capable": False,
        "native_helper_policy": "disabled",
        "native_helper": None,
        "skills": [],
        "skill_capabilities": list(skill_capabilities),
        "mcp_servers": [],
        "resources": [],
        "plugins": [],
        "forbidden": [],
    }


def _v4_with_coo_domain(
    tmp_path: Path, *, enabled: bool, skill_capabilities: list[str]
) -> Path:
    raw = _load_v4_fixture()
    raw["profiles"][COO_DOMAIN_EXECUTION_PROFILE] = _coo_domain_profile_v4(
        enabled=enabled, skill_capabilities=skill_capabilities
    )
    return _write_v4(tmp_path, raw)


def test_v4_empty_domain_grant_enabled_loads_and_resolves_with_empty_authority(
    tmp_path,
):
    """V4 COO domain with empty skill_capabilities still loads and resolves
    with empty effective authority. Real ``load(path, source_root=...)``
    against the V4 fixture; no mocks or proxies.
    """

    path = _v4_with_coo_domain(tmp_path, enabled=True, skill_capabilities=[])
    registry = ExecutionCapabilityRegistry.load(
        path, source_root=V4_FIXTURE_REPO_ROOT
    )
    profile = registry.resolve(COO_DOMAIN_EXECUTION_PROFILE)
    assert profile.enabled is True
    assert profile.skills == ()
    assert profile.skill_grants == ()
    assert profile.required_capability_names == ()


def test_v4_empty_domain_grant_disabled_loads_but_resolve_refuses(tmp_path):
    """V4 COO domain disabled with empty skill_capabilities still loads but
    ordinary ``resolve()`` refuses the disabled domain. Empty grants must
    not bypass the production disabled refusal.
    """

    path = _v4_with_coo_domain(tmp_path, enabled=False, skill_capabilities=[])
    registry = ExecutionCapabilityRegistry.load(
        path, source_root=V4_FIXTURE_REPO_ROOT
    )
    assert registry.profiles[COO_DOMAIN_EXECUTION_PROFILE].enabled is False
    with pytest.raises(CapabilityPolicyError, match="is disabled"):
        registry.resolve(COO_DOMAIN_EXECUTION_PROFILE)


@pytest.mark.parametrize("grant_id", V4_REQUIRED_SKILL_CAPABILITY_IDS)
def test_v4_nonempty_domain_grant_enabled_refuses_each_valid_grant(
    tmp_path, grant_id
):
    """V4 COO domain enabled with any single valid skill_capability is
    refused at load. Real package source on disk.
    """

    path = _v4_with_coo_domain(
        tmp_path, enabled=True, skill_capabilities=[grant_id]
    )
    with pytest.raises(CapabilityPolicyError):
        ExecutionCapabilityRegistry.load(path, source_root=V4_FIXTURE_REPO_ROOT)


@pytest.mark.parametrize("grant_id", V4_REQUIRED_SKILL_CAPABILITY_IDS)
def test_v4_nonempty_domain_grant_disabled_refuses_each_valid_grant(
    tmp_path, grant_id
):
    """V4 COO domain disabled with any single valid skill_capability is
    refused at load. The disabled ceiling must refuse the latent grant
    so a later enable cannot accidentally admit it.
    """

    path = _v4_with_coo_domain(
        tmp_path, enabled=False, skill_capabilities=[grant_id]
    )
    with pytest.raises(CapabilityPolicyError):
        ExecutionCapabilityRegistry.load(path, source_root=V4_FIXTURE_REPO_ROOT)


def test_v4_nonempty_domain_grant_combined_enabled_refuses(tmp_path):
    """V4 COO domain enabled with all four valid skill_capability ids is
    refused at load.
    """

    path = _v4_with_coo_domain(
        tmp_path,
        enabled=True,
        skill_capabilities=list(V4_REQUIRED_SKILL_CAPABILITY_IDS),
    )
    with pytest.raises(CapabilityPolicyError):
        ExecutionCapabilityRegistry.load(path, source_root=V4_FIXTURE_REPO_ROOT)


def test_v4_nonempty_domain_grant_combined_disabled_refuses(tmp_path):
    """V4 COO domain disabled with all four valid skill_capability ids is
    refused at load.
    """

    path = _v4_with_coo_domain(
        tmp_path,
        enabled=False,
        skill_capabilities=list(V4_REQUIRED_SKILL_CAPABILITY_IDS),
    )
    with pytest.raises(CapabilityPolicyError):
        ExecutionCapabilityRegistry.load(path, source_root=V4_FIXTURE_REPO_ROOT)


def test_v4_non_domain_mastermind_operator_profile_still_resolves_with_four_grants(
    tmp_path,
):
    """The non-domain mastermind-operator V4 profile still loads and
    resolves with the four valid skill grants; the domain guard amendment
    must not touch the non-domain V4 grant path.
    """

    raw = _load_v4_fixture()
    path = _write_v4(tmp_path, raw)
    registry = ExecutionCapabilityRegistry.load(
        path, source_root=V4_FIXTURE_REPO_ROOT
    )
    profile = registry.resolve(V4_NON_DOMAIN_FIXTURE_PROFILE_ID)
    assert profile.enabled is True
    assert sorted(profile.skills) == sorted(V4_EXPECTED_RUNTIME_NAMES)
    assert len(profile.skill_grants) == 4
    assert sorted(grant.runtime_name for grant in profile.skill_grants) == sorted(
        V4_EXPECTED_RUNTIME_NAMES
    )


def test_v4_unmodified_fixture_policy_and_helper_profile_digests_are_stable(
    tmp_path,
):
    """Loading the unmodified V4 fixture must yield the same policy
    digest and the same native-helper profile digest as the R15
    composition. The domain guard amendment does not touch any other
    profile.
    """

    raw = _load_v4_fixture()
    path = _write_v4(tmp_path, raw)
    registry = ExecutionCapabilityRegistry.load(
        path, source_root=V4_FIXTURE_REPO_ROOT
    )
    assert registry.policy_digest == V4_NON_DOMAIN_FIXTURE_POLICY_DIGEST
    assert (
        registry.profiles[V4_HELPER_PROFILE_ID].profile_digest
        == V4_HELPER_PROFILE_DIGEST
    )

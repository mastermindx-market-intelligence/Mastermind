"""Fail-closed full-workspace write scope for verified rich Codex Skills.

The adapter must not turn a Job with no admitted writable paths (or a path
narrower than the actual workspace sandbox) into workspace-wide writes.
"""
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from control_plane.codex_operator_adapter import CodexOperatorAdapter
from control_plane.executive_agent_capabilities import ExecutionCapabilityRegistry
from control_plane.operator_harness_contract import (
    NativeHelperPolicy, RequestedExecutionProfile, WorkspaceIdentity,
)

REPO = Path(__file__).resolve().parent.parent
PROFILE_FIXTURE = (
    REPO / "scripts/ohf/fixtures/"
    "executive_agent_capabilities_v4_rich_write_operator.json"
)
WORKSPACE = "/private/tmp/exact-owned-rich-workspace"


def _admission():
    profile = ExecutionCapabilityRegistry.load(
        PROFILE_FIXTURE, source_root=REPO,
    ).resolve("operator.appserver.write.mastermind-operator.v1")
    digest = "a" * 64
    workspace = WorkspaceIdentity(WORKSPACE, "b" * 40, 1, 2, 501, 20)
    requested = RequestedExecutionProfile(
        worker_id="worker-rich", provider="openai-codex",
        requested_model="gpt-5.6-sol", harness_kind="codex-app-server",
        harness_binary_digest=digest, harness_version="0.159.3",
        workspace=workspace, sandbox_policy="workspace-write",
        approval_policy="never", network_policy="disabled",
        capabilities=profile.capability_manifest(harness_binary_digest=digest),
        native_helper_policy=NativeHelperPolicy.DISABLED,
        authority_policy_hash="c" * 64,
        expected_config_digest=profile.expected_config_digest,
        allowed_write_paths=(WORKSPACE,), write_capable=True,
    )
    adapter = SimpleNamespace(
        worker_id="worker-rich", binary_digest=digest,
        expected_harness_version="0.159.3", configured_workspace=workspace,
        skill_canary_binding=SimpleNamespace(profile=profile),
        native_helper_grant=None, network_policy="disabled",
        expected_config_digest=profile.expected_config_digest,
        workspace_root=Path(WORKSPACE),
    )
    return adapter, requested


def test_exact_full_workspace_write_scope_can_be_admitted():
    adapter, requested = _admission()
    actual = CodexOperatorAdapter.validate_requested_profile(adapter, requested)
    assert actual.accepted is True
    assert actual.reasons == ()


@pytest.mark.parametrize("bad_paths", [
    (),
    ("src/",),
    ("/tmp",),
    (WORKSPACE, "/tmp"),
    (WORKSPACE, WORKSPACE),
])
def test_missing_or_wider_write_scope_refuses_before_provider_start(bad_paths):
    adapter, requested = _admission()
    actual = CodexOperatorAdapter.validate_requested_profile(
        adapter, replace(requested, allowed_write_paths=bad_paths),
    )
    assert not actual.accepted
    assert "write_capable_ohf_not_armed" in actual.reasons

from __future__ import annotations

from pathlib import Path

import control_plane.codex_worker as codex_worker
import control_plane.executive_agent_capabilities as capabilities
from ops.executive_os import capacity_broker_topology
from ops.executive_os import c1_private_preimage
from ops.executive_os import provider_identity_probe
from ops.executive_os import provider_inference_canary
from ops.executive_os import provider_readiness
from scripts.ohf.p1a_capability_policy import render_minimal_surface_config


ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.159.2"
CODEX_SHA256 = "16593cc2f422d5f398a8e40f550ebbaf1245392528957be342c295920a300704"
CODE_MODE_HOST_SHA256 = "ed79fbc9e1683feb29d73fb421f3e16932d178a459f63741754014c6c7ea6107"
INSTALLED = f"/Library/Application Support/MastermindExecutive/bin/codex-{VERSION}"

NEWLY_CLOSED_FEATURES = {
    "auth_elicitation",
    "browser_use_external",
    "browser_use_full_cdp_access",
    "daemon_auto_start",
    "enable_mcp_apps",
    "mcp_2026_07_28",
    "multi_agent_v2",
    "shell_snapshot",
    "shell_snapshot_v2",
    "skill_mcp_dependency_install",
    "skill_search",
    "tool_call_mcp_elicitation",
    "workspace_dependencies",
}


def _source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_generation_pin_is_identical_across_installed_runtime_owners() -> None:
    assert provider_readiness.CODEX_VERSION == VERSION
    assert str(provider_readiness.CODEX_BINARY) == INSTALLED
    assert provider_readiness.CODEX_SHA256 == CODEX_SHA256

    assert provider_identity_probe.PINNED_CODEX_VERSION == VERSION
    assert str(provider_identity_probe.INSTALLED_CODEX_BINARY) == INSTALLED
    assert provider_identity_probe.PINNED_CODEX_SHA256 == CODEX_SHA256

    assert provider_inference_canary.PINNED_CODEX_VERSION == VERSION
    assert str(provider_inference_canary.INSTALLED_CODEX_BINARY) == INSTALLED
    assert provider_inference_canary.PINNED_CODEX_SHA256 == CODEX_SHA256

    assert capacity_broker_topology.CODEX_VERSION == VERSION
    assert str(capacity_broker_topology.CODEX_BINARY) == INSTALLED

    assert c1_private_preimage.CODEX_BINARY == INSTALLED
    assert c1_private_preimage.CODEX_ATTESTATION.endswith(
        f"/codex-attestation-{VERSION}.json"
    )


def test_installer_and_host_preparation_pin_the_same_signed_package() -> None:
    install = _source("ops/executive_os/install.sh")
    assert f'CODEX_VERSION="{VERSION}"' in install
    assert f'CODEX_SHA256="{CODEX_SHA256}"' in install
    assert f'CODEX_CODE_MODE_HOST_SHA256="{CODE_MODE_HOST_SHA256}"' in install
    assert f'[ "$CODEX_VERSION" = "{VERSION}" ]' in install

    provision = _source("ops/executive_os/provision-worker-auth.sh")
    assert f'CODEX_VERSION="{VERSION}"' in provision
    assert f'CODEX_SHA256="{CODEX_SHA256}"' in provision

    capacity = _source("ops/executive_os/prepare-capacity-host.sh")
    assert f'CODEX_VERSION="{VERSION}"' in capacity
    assert f'CODEX_SHA256="{CODEX_SHA256}"' in capacity


def test_batch_worker_and_readiness_canary_disable_new_generation_surface() -> None:
    assert NEWLY_CLOSED_FEATURES <= set(codex_worker._DISABLED_FEATURES)
    assert NEWLY_CLOSED_FEATURES <= set(provider_inference_canary._DISABLED_FEATURES)


def test_app_server_profiles_disable_new_generation_surface() -> None:
    overrides = set(capabilities._BASE_APP_SERVER_OVERRIDES)
    expected = {f"features.{name}=false" for name in NEWLY_CLOSED_FEATURES}
    assert expected <= overrides


def test_generation_minimal_surface_renderer_closes_new_features() -> None:
    rendered = render_minimal_surface_config(
        model="gpt-5.6-sol",
        mcp_command="/usr/bin/true",
        mcp_args=[],
        mcp_cwd="/tmp",
    )
    for name in NEWLY_CLOSED_FEATURES:
        assert f"{name} = false" in rendered
    assert "apps = false" in rendered
    assert "[skills.bundled]\nenabled = false" in rendered
    assert 'codex_version": "codex-cli 0.159.2"' in _source(
        "scripts/ohf/p1a_minimal_surface.py"
    )

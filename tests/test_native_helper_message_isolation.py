"""Provider-free qualification of generated Codex helper communication policy."""
from copy import deepcopy
import tomllib

import pytest

from control_plane.executive_agent_capabilities import (
    ExecutionCapabilityRegistry, app_server_security_config_digest,
)

PROFILE = "operator.appserver.readonly.docs-mcp.native-helper.v1"


def test_generated_helper_disables_direct_message_without_disabling_spawn():
    profile = ExecutionCapabilityRegistry.load().resolve(PROFILE)
    config = profile.app_server_config_projection()
    native = config["features"]["multi_agent_v2"]
    assert native["disable_direct_message"] is True
    assert native["enabled"] is True
    assert config["agents"]["enabled"] is True
    assert config["agents"]["max_depth"] == 1
    assert native["max_concurrent_threads_per_session"] == 2
    assert config["agents"]["max_concurrent_threads_per_session"] == 1


def test_launch_override_and_expected_readback_agree_on_message_isolation():
    profile = ExecutionCapabilityRegistry.load().resolve(PROFILE)
    rows = [v for v in profile.app_server_config_overrides()
            if v.startswith("features.multi_agent_v2=")]
    assert len(rows) == 1
    value = tomllib.loads(rows[0])["features"]["multi_agent_v2"]
    assert value["disable_direct_message"] is True
    assert value == profile.app_server_config_projection()["features"]["multi_agent_v2"]


@pytest.mark.parametrize("mutated", [False, None, "true", 1])
def test_disabled_missing_or_malformed_message_guard_cannot_reuse_attestation(mutated):
    profile = ExecutionCapabilityRegistry.load().resolve(PROFILE)
    value = deepcopy(profile.app_server_config_projection())
    native = value["features"]["multi_agent_v2"]
    if mutated is None:
        native.pop("disable_direct_message", None)
    else:
        native["disable_direct_message"] = mutated
    assert app_server_security_config_digest(value) != profile.expected_config_digest

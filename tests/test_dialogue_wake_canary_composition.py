"""Trust-bearing installed composition; no launchd/provider effects in fixtures."""
from unittest.mock import MagicMock

import pytest

from control_plane.dialogue_wake_canary_activation import DialogueWakeCanaryProfile
from control_plane.wake_ledger import WakeRetryPolicy
from integrations.executive_mcp.web_ceo_v3 import WEB_CEO_V3_PROFILE
from tests.test_c1_ceo_ingress_composition import _app_raw, _capture_service, _module
from tests.test_dialogue_wake_canary_activation import parsed


def observation_config(raw, module, *, armed=False):
    from ops.executive_os.a2_agent_relay_enrollment import RELAY_UID
    raw.update(
        dialogue_bridge_armed=armed,
        dialogue_observation_launchd_socket_name="DialogueObservation",
        dialogue_observation_peer_uid=RELAY_UID,
        dialogue_observation_socket_path=module._CANONICAL_DIALOGUE_OBSERVATION_SOCKET,
        dialogue_wake_retry_policy=WakeRetryPolicy(1, 1, 60, 1, False, armed),
    )
    return raw


@pytest.mark.parametrize("generic,raw_grant,verified,present", [
    (False, False, False, False),
    (False, True, False, False),
    (False, True, True, True),
    (True, False, False, True),
])
def test_only_trusted_grant_can_compose_bridge_with_generic_flags_false(
    tmp_path, monkeypatch, generic, raw_grant, verified, present,
):
    from control_plane import remote_codex_operator_adapter as remote
    module = _module()
    raw = observation_config(_app_raw(tmp_path), module, armed=generic)
    raw["dialogue_wake_canary_activation"] = parsed() if raw_grant else None
    captured = _capture_service(module, monkeypatch)
    listeners = []
    monkeypatch.setattr(module, "activate_launchd_socket", lambda name: listeners.append(name) or object())
    monkeypatch.setattr(remote, "RemoteCodexOperatorAdapter", lambda *a, **k: MagicMock())
    profile = DialogueWakeCanaryProfile(parsed() if verified else None)
    module._service_from_config(raw, dialogue_canary_profile=profile)
    assert ("DialogueObservation" in listeners) is present
    assert ("dialogue_wake_handler" in captured) is present
    if present:
        assert captured["dialogue_wake_handler"]._canary_profile == profile
    assert raw["dialogue_bridge_armed"] is generic
    assert raw["dialogue_wake_retry_policy"].armed is generic


@pytest.mark.parametrize("w3c_installed", [False, True])
def test_continue_carrier_does_not_require_or_arm_attention(
    tmp_path, monkeypatch, w3c_installed,
):
    from integrations.session_bridge import installed
    from ops.executive_os import a2_agent_relay_enrollment as enrollment
    module = _module()
    raw = observation_config(_app_raw(tmp_path), module)
    raw["executive_mcp_profile"] = WEB_CEO_V3_PROFILE
    captured = _capture_service(module, monkeypatch)
    bound = {}
    def bridge(runtime, **kwargs):
        bound.update(kwargs)
        return object()
    checked = []
    monkeypatch.setattr(installed, "build_runtime_session_bridge", bridge)
    monkeypatch.setattr(enrollment, "w3c_plist_configured",
                        lambda **kwargs: checked.append(kwargs) or w3c_installed)
    service = module._service_from_config(raw)
    service._namespace_custody = MagicMock()
    service._ceo_ingress_app_binding = captured["ceo_ingress_app_binding"]
    service._ceo_ingress_app_binding.session_bridge_provider_factory(object())
    assert bound["codex_owner_configured"]() is w3c_installed
    assert checked == [{"release_sha": raw["proof_base_sha"]}]
    assert "dialogue_wake_handler" not in captured
    assert raw["dialogue_bridge_armed"] is False
    assert raw["dialogue_wake_retry_policy"].armed is False

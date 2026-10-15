"""web_ceo_v3 joins at the release-observation boundary only.

Regression for the narrow observation compatibility repair: the five-role
World capture and the pure _config_join accept the exact supported installed
gateway profile web_ceo_v3, while the privileged peer profile tuple and
_verify_role_config keep refusing it and every existing acceptance/refusal
behaviour is preserved. Hermetic fixtures only: the synthetic World facts and
the existing installed-peer trusted-config fixtures; no native service,
network, provider or file effect outside this artifact.
"""

import json

import pytest

from control_plane import executive_release_observation as o
import tests.test_executive_installed_peer as installed_peer_suite
from tests.test_executive_installed_peer import (
    _gateway_install_document,
    _installed_config_read,
)
from tests.test_executive_release_observation import World

RELEASE = "a" * 40
STALE_RELEASE = "c" * 40
V3_PROFILE = "web_ceo_v3"
INSTALLED_PROFILES = ("release_control_v1", "web_ceo_release_v1")
JOIN_REFUSED = "CONFIG_JOIN_REFUSED"

# The installed-peer suite resolves the privileged production module as ``m``
# and its refusal type through ``peer``; reuse both names verbatim so this
# module exercises the exact same _verify_role_config boundary.
_PEER = installed_peer_suite.m
_PEER_ERROR = getattr(installed_peer_suite, "peer", _PEER).PeerIdentityError
_GATEWAY_SPEC = next(s for s in o._SPECS if s.role == "gateway")
_RELAY_SPEC = next(s for s in o._SPECS if s.role == "relay")


def _gateway_document(profile):
    return _gateway_install_document(RELEASE, profile)


def _set_gateway_profile(world, profile):
    document = json.loads(world.artifacts[_GATEWAY_SPEC.config])
    document["executive_mcp_profile"] = profile
    world.artifacts[_GATEWAY_SPEC.config] = json.dumps(document).encode()


def _age_relay_artifacts(world):
    stale = o._RELEASES + STALE_RELEASE
    world.artifacts[_RELAY_SPEC.plist] = world.artifacts[_RELAY_SPEC.plist].replace(
        (o._RELEASES + RELEASE).encode(), stale.encode()
    )
    document = json.loads(world.artifacts[_RELAY_SPEC.config])
    document["relay_version"] = STALE_RELEASE
    world.artifacts[_RELAY_SPEC.config] = json.dumps(document).encode()


def _refuses_join(document):
    with pytest.raises(o.ReleaseObservationError, match=JOIN_REFUSED):
        o._config_join(_GATEWAY_SPEC, document, RELEASE)


def test_five_role_capture_joins_exact_v3_gateway_profile(monkeypatch):
    """New positive case: full capture succeeds on the repair, refuses on old source."""
    world = World(monkeypatch)
    _set_gateway_profile(world, V3_PROFILE)
    snapshot = world.capture()
    assert snapshot is not None
    assert all(world.commands[role] >= 1 for role in o._ROLES)
    assert world.write_calls == []
    assert world.runtime_calls == []


def test_observation_join_accepts_exact_v3_profile():
    o._config_join(_GATEWAY_SPEC, _gateway_document(V3_PROFILE), RELEASE)


@pytest.mark.parametrize("profile", INSTALLED_PROFILES)
def test_observation_join_still_accepts_installed_profiles(profile):
    o._config_join(_GATEWAY_SPEC, _gateway_document(profile), RELEASE)


def test_privileged_peer_still_refuses_exact_v3_profile(monkeypatch):
    _installed_config_read(monkeypatch, _gateway_document(V3_PROFILE))
    with pytest.raises(_PEER_ERROR):
        _PEER._verify_role_config(_PEER._role_topology("gateway"), RELEASE, _PEER._Budget(25))


@pytest.mark.parametrize("profile", INSTALLED_PROFILES)
def test_privileged_peer_still_accepts_installed_profiles(monkeypatch, profile):
    _installed_config_read(monkeypatch, _gateway_document(profile))
    observed = _PEER._verify_role_config(
        _PEER._role_topology("gateway"), RELEASE, _PEER._Budget(25)
    )
    assert observed.release == RELEASE


def test_privileged_peer_profiles_exclude_v3():
    assert V3_PROFILE not in _PEER._GATEWAY_MCP_PROFILES
    assert set(_PEER._GATEWAY_MCP_PROFILES) == set(INSTALLED_PROFILES)


@pytest.mark.parametrize("profile", [
    "web_ceo_v3 ",
    "web_ceo_V3",
    "web_ceo_v31",
    "web_ceo_v4",
    "personal_read",
])
def test_observation_join_refuses_close_alias_profiles(profile):
    _refuses_join(_gateway_document(profile))


@pytest.mark.parametrize("mutation", [
    lambda document: document.update(release_sha="b" * 40),
    lambda document: document.update(service_uid=459),
    lambda document: document.update(service_uid="458"),
    lambda document: document.pop("schema"),
    lambda document: document.update(schema="mastermind.executive_mcp_install.v2"),
])
def test_observation_join_refuses_malformed_v3_fields(mutation):
    document = _gateway_document(V3_PROFILE)
    mutation(document)
    _refuses_join(document)


def test_old_relay_artifact_pair_still_fails_mixed_content_convergence(monkeypatch):
    world = World(monkeypatch)
    _set_gateway_profile(world, V3_PROFILE)
    _age_relay_artifacts(world)
    with pytest.raises(o.ReleaseObservationError, match="RELEASE_OBSERVATION_MIXED_CONTENT"):
        world.capture()

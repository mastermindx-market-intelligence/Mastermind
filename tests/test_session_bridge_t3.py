"""Session Bridge ``t3`` target kind: reader default, schema, installed wiring."""
from __future__ import annotations

import asyncio
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from control_plane.executive_runtime import Runtime
from control_plane.t3_environment_projection import (
    T3EnvironmentObservation,
    project,
    to_session_targets,
)
from integrations.business_mcp_auth.contracts import VerifiedPrincipal
from integrations.session_bridge.native_backends import CanonicalTargetReader
from integrations.session_bridge.schemas import (
    TARGET_KINDS,
    BridgeError,
    validate_tool_arguments,
)

ISSUER = "https://auth.example.test/"
PRINCIPAL = VerifiedPrincipal(
    policy_id="session-profile",
    issuer=ISSUER,
    issuer_digest=hashlib.sha256(ISSUER.encode()).hexdigest(),
    resource="https://exec.example.test/mcp",
    subject_digest="1" * 64,
    client_ref="2" * 64,
    scopes=("mastermind.executive.read",),
    issued_at=1791000000,
    expires_at=1791003600,
    jti_digest="3" * 64,
)
OBSERVED_AT = "2026-11-08T14:09:03Z"
CLOCK = datetime(2026, 11, 8, 14, 9, 10, tzinfo=timezone.utc)


def _reader(**readers):
    return CanonicalTargetReader(
        fabric_reader=readers.get("fabric_reader", lambda: []),
        codex_reader=readers.get("codex_reader", lambda: []),
        claude_reader=readers.get("claude_reader", lambda: []),
        **({"t3_reader": readers["t3_reader"]} if "t3_reader" in readers else {}),
    )


def test_target_kinds_carries_t3_exactly_once():
    assert TARGET_KINDS.count("t3") == 1
    assert len(TARGET_KINDS) == 6
    assert set(TARGET_KINDS) == {
        "fabric_attempt",
        "codex",
        "claude",
        "hermes_secretary",
        "hermes_meta",
        "t3",
    }
    assert validate_tool_arguments("session_targets", {"kind": "t3"}) == {"kind": "t3"}


def test_reader_without_a_t3_owner_returns_empty_and_does_not_raise():
    reader = _reader()
    assert reader("t3") == []
    # The legacy omitted-kind inventory shape is preserved unchanged.
    assert reader(None) == {"fabric_attempt": [], "codex": [], "claude": []}


def test_reader_with_a_t3_owner_returns_its_projection():
    reader = _reader(t3_reader=lambda: [{"target_ref": "t3:env-1"}])
    assert reader("t3") == [{"target_ref": "t3:env-1"}]
    # The omitted kind still returns the per-provider inventory.
    assert reader(None) == {
        "fabric_attempt": [],
        "codex": [],
        "claude": [],
        "t3": [{"target_ref": "t3:env-1"}],
    }


def test_reader_still_refuses_an_unknown_kind():
    with pytest.raises(BridgeError) as error:
        _reader()("t4")
    assert error.value.code == "invalid_input"


def projection(launch_eligible=True):
    host = {
        "schema": "mastermind.host_readiness_snapshot/v1",
        "host_id": "m2-studio",
        "reachable": True,
        "observed_at_utc": OBSERVED_AT,
        "disk_free_gib": {"runtime_dir": 271.65},
        "thermal": "nominal" if launch_eligible else "unknown",
    }
    facts = T3EnvironmentObservation.from_dict(
        {
            "environment_id": "t3-m2-studio-01",
            "server_endpoint": "127.0.0.1:43110",
            "service_state": "running",
            "service_persistence": "lingering",
            "auth_state": "paired",
            "provider_instance_ids": ["provider-instance-1"],
            "reachable": True,
            "observed_at_utc": OBSERVED_AT,
            "source": "wb:t3-environment-census",
        }
    )
    return project(host, facts, CLOCK)


def _provider(projector):
    from integrations.session_bridge.installed import InstalledSessionBridgeProvider

    return InstalledSessionBridgeProvider(
        target_projector=projector,
        reply_handler=lambda *_: {},
        summon_handler=lambda *_: {},
    )


def test_installed_provider_exposes_projected_t3_targets():
    from integrations.session_bridge.installed import PRIVATE_SCHEMA, principal_frame

    seen = []

    def projector(principal, kind):
        seen.append((principal, kind))
        return [to_session_targets(projection())]

    result = asyncio.run(
        _provider(projector).handle_frame(
            {
                "schema": PRIVATE_SCHEMA,
                "tool": "session_targets",
                "principal": principal_frame(PRINCIPAL),
                "arguments": {"kind": "t3"},
            }
        )
    )
    assert result["ok"] is True
    target, = result["data"]
    assert target["kind"] == "t3"
    assert target["target_ref"] == "t3:t3-m2-studio-01"
    assert target["launch_eligible"] is True
    assert seen and seen[0][1] == "t3"


def test_installed_provider_returns_an_empty_list_when_no_t3_target_is_eligible():
    from integrations.session_bridge.installed import PRIVATE_SCHEMA, principal_frame

    result = asyncio.run(
        _provider(lambda *_: []).handle_frame(
            {
                "schema": PRIVATE_SCHEMA,
                "tool": "session_targets",
                "principal": principal_frame(PRINCIPAL),
                "arguments": {"kind": "t3"},
            }
        )
    )
    assert result["ok"] is True
    assert result["data"] == []


def test_build_runtime_session_bridge_refuses_a_non_callable_t3_projector():
    from integrations.session_bridge.installed import build_runtime_session_bridge

    # Validated before any Runtime owner is touched, so no runtime is needed.
    with pytest.raises(TypeError) as error:
        build_runtime_session_bridge(
            None,
            dialogue_socket_path=Path("/private/tmp/unused-dialogue.sock"),
            t3_target_projector=42,
        )
    assert "t3_target_projector" in str(error.value)


def _runtime_handle():
    """A body-less Runtime handle: only the target branch under test is reached.

    The t3 branch reads no store, ledger, socket or dialogue source, so this
    composition stays hermetic; no Runtime is started, armed or persisted.
    """
    runtime = Runtime.__new__(Runtime)
    object.__setattr__(runtime, "jobs", SimpleNamespace(list_jobs=lambda: []))
    return runtime


def _targets_via(build, **kwargs):
    from integrations.session_bridge.installed import PRIVATE_SCHEMA, principal_frame

    owner = build(
        _runtime_handle(),
        dialogue_socket_path=Path("/private/tmp/unused-dialogue.sock"),
        **kwargs,
    )
    return asyncio.run(
        owner.handle_frame(
            {
                "schema": PRIVATE_SCHEMA,
                "tool": "session_targets",
                "principal": principal_frame(PRINCIPAL),
                "arguments": {"kind": "t3"},
            }
        )
    )


def test_runtime_composition_without_a_t3_projector_yields_no_t3_targets():
    from integrations.session_bridge.installed import build_runtime_session_bridge

    result = _targets_via(build_runtime_session_bridge)
    assert result["ok"] is True
    assert result["data"] == []


def test_runtime_composition_routes_the_t3_projector():
    from integrations.session_bridge.installed import build_runtime_session_bridge

    calls = []

    def projector(principal):
        calls.append(principal)
        return [to_session_targets(projection())]

    result = _targets_via(build_runtime_session_bridge, t3_target_projector=projector)
    assert result["ok"] is True
    target, = result["data"]
    assert target["target_ref"] == "t3:t3-m2-studio-01"
    assert len(calls) == 1
    assert type(calls[0]).__name__ == "NeutralPrincipalProjection"

"""Source-only contract for the disabled Stage-B Codex CEO target."""
from __future__ import annotations

import json

import pytest

from control_plane.session_targets import (
    DEFAULT_TARGETS_PATH,
    RouteRefusalError,
    RuntimeBinding,
    SessionTargetError,
    evaluate_delivery_allowed,
    load_session_targets,
)
from control_plane.wake_transport import wake_transport_descriptor


_ALIAS = "EXECUTIVE-CEO-CODEX-A"
_ROOT = "JOB-900"
_BINDING_ID = "bind-stageb000001"


def test_checked_in_codex_ceo_target_is_exact_disabled_and_disarmed() -> None:
    registry = load_session_targets()
    target = registry.get(_ALIAS)

    assert target.to_dict() == {
        "session_alias": _ALIAS,
        "target_seat": "ceo",
        "reasoning_surface": "codex",
        "wake_transport": "codex-app-server",
        "allowed_transports": ["codex-app-server"],
        "workstream": "executive",
        "target_enabled": False,
    }
    descriptor = wake_transport_descriptor(target.wake_transport)
    assert descriptor.transport_implemented is True
    assert descriptor.requires_runtime_binding is True
    assert registry.production_armed is False
    assert evaluate_delivery_allowed(
        production_armed=registry.production_armed,
        target_enabled=target.target_enabled,
        transport_implemented=descriptor.transport_implemented,
        binding_ready=True,
        human_required=False,
        requires_runtime_binding=descriptor.requires_runtime_binding,
    ) is False


def test_catalog_presence_never_elects_codex_for_default_or_workstream_routes() -> None:
    registry = load_session_targets()

    assert registry.root_job_bindings == {}
    assert registry.default_alias_by_seat["ceo"] == "EXECUTIVE-CEO-A"
    assert {
        stream: seat_map["ceo"]
        for stream, seat_map in registry.workstream_alias_by_seat.items()
    } == {
        "prophet": "EXECUTIVE-CEO-A",
        "terminal": "EXECUTIVE-CEO-A",
        "executive": "EXECUTIVE-CEO-A",
    }
    assert registry.resolve("ceo").session_alias == "EXECUTIVE-CEO-A"
    assert registry.resolve("ceo", workstream="executive").session_alias == "EXECUTIVE-CEO-A"


def test_explicit_root_overlay_requires_the_exact_codex_runtime_binding() -> None:
    registry = load_session_targets().with_root_job_bindings(
        {_ROOT: {"ceo": _ALIAS}}
    )
    binding = RuntimeBinding(
        session_alias=_ALIAS,
        binding_id=_BINDING_ID,
        binding_generation=1,
        reasoning_surface="codex",
    )

    assert registry.resolve("ceo", root_job_id=_ROOT, binding=binding).session_alias == _ALIAS

    with pytest.raises(SessionTargetError, match="session_alias does not match"):
        registry.resolve(
            "ceo",
            root_job_id=_ROOT,
            binding=RuntimeBinding(
                session_alias="EXECUTIVE-CEO-A",
                binding_id=_BINDING_ID,
                binding_generation=1,
                reasoning_surface="chatgpt-sol",
            ),
        )

    with pytest.raises(SessionTargetError, match="reasoning_surface does not match"):
        registry.resolve(
            "ceo",
            root_job_id=_ROOT,
            binding=RuntimeBinding(
                session_alias=_ALIAS,
                binding_id=_BINDING_ID,
                binding_generation=1,
                reasoning_surface="chatgpt-sol",
            ),
        )


def test_unbound_root_still_refuses_instead_of_falling_back_to_catalog_or_default() -> None:
    registry = load_session_targets()

    with pytest.raises(RouteRefusalError) as raised:
        registry.resolve(
            "ceo",
            root_job_id=_ROOT,
            obligation_id="WAKE-stage-b-target-definition",
        )

    assert raised.value.refusal.reason == f"root_job_id {_ROOT} has no binding for seat ceo"


def test_policy_digest_is_order_invariant_and_binds_catalog_membership(tmp_path) -> None:
    """Full Stage-B target fingerprints remain a separate assignment-law concern."""

    registry = load_session_targets()
    document = json.loads(DEFAULT_TARGETS_PATH.read_text(encoding="utf-8"))

    reordered = dict(document)
    reordered["targets"] = dict(reversed(tuple(document["targets"].items())))
    reordered_path = tmp_path / "reordered.json"
    reordered_path.write_text(json.dumps(reordered), encoding="utf-8")
    assert load_session_targets(reordered_path).policy_digest() == registry.policy_digest()

    without_codex = json.loads(DEFAULT_TARGETS_PATH.read_text(encoding="utf-8"))
    without_codex["targets"].pop(_ALIAS)
    without_codex_path = tmp_path / "without-codex.json"
    without_codex_path.write_text(json.dumps(without_codex), encoding="utf-8")
    assert load_session_targets(without_codex_path).policy_digest() != registry.policy_digest()
    assert load_session_targets(without_codex_path).root_job_bindings == {}

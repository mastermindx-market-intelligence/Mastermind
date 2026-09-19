from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest

from control_plane.wake_dispatcher import WakeEffectUnknownError, WakePreSubmitError
from integrations.chairman_surfaces import web_sol_client
from integrations.chairman_surfaces.web_sol_wake import WebSolWakeClient
from tests.test_web_sol_continuation_submit import binding, runtime_lease


NOW = datetime(2026, 9, 18, 22, 0, tzinfo=timezone.utc)
NUDGE = "NUDGE-" + "e" * 32


def _exact_kwargs(lease):
    current = lease.runtime_binding
    return {
        "native_handle": current.native_handle,
        "binding_id": current.binding_id,
        "binding_generation": current.binding_generation,
        "session_alias": current.session_alias,
        "nudge_id": NUDGE,
        "obligation_ids": ("WAKE-" + "d" * 32, "WAKE-" + "f" * 32),
    }

def _client(submitter, observer=lambda *_args, **_kwargs: {"status": "CONTINUATION_ACK_PENDING"}):
    row = binding()
    lease = runtime_lease(row)
    return (
        WebSolWakeClient(
            row,
            lease,
            submitter=submitter,
            observer=observer,
            now=lambda: NOW,
            nonce_factory=lambda: "wake-nonce-00000000000001",
        ),
        lease,
    )


def test_exact_wake_maps_to_one_fixed_continuation_without_result_body():
    calls = []

    def submitter(row, lease, **kwargs):
        calls.append((row, lease, kwargs))
        return {"status": "CONTINUATION_STARTED"}

    client, lease = _client(submitter)
    observation = asyncio.run(client.deliver_wake(**_exact_kwargs(lease)))

    assert observation.generation_started is True
    assert observation.nudge_id == NUDGE
    assert len(calls) == 1
    kwargs = calls[0][2]
    assert kwargs["turn_id"] == NUDGE
    assert kwargs["operation_key"] == f"web-sol-wake:{NUDGE}"
    assert kwargs["issued_at"] == "2026-09-18T22:00:00Z"
    assert kwargs["expires_at"] == "2026-09-18T22:00:30Z"
    assert kwargs["wake_obligation_ids"] == _exact_kwargs(lease)["obligation_ids"]
    assert set(kwargs) == {
        "operation_key", "turn_id", "wake_obligation_ids",
        "issued_at", "expires_at", "nonce"
    }
    rendered = repr(calls)
    assert "role_result" not in rendered
    assert "transcript" not in rendered


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("native_handle", "wsx-runtime-stale"),
        ("binding_id", "bind-wsx-" + "f" * 48),
        ("binding_generation", 2),
        ("session_alias", "EXECUTIVE-CEO-B"),
    ],
)
def test_stale_wrong_session_or_generation_refuses_before_submit(field, value):
    calls = []

    def submitter(*args, **kwargs):
        calls.append((args, kwargs))
        return {"status": "CONTINUATION_STARTED"}
    client, lease = _client(submitter)
    kwargs = _exact_kwargs(lease)
    kwargs[field] = value
    with pytest.raises(WakePreSubmitError, match="RuntimeBinding"):
        asyncio.run(client.deliver_wake(**kwargs))
    assert calls == []


def test_not_submitted_is_known_no_effect():
    client, lease = _client(lambda *_args, **_kwargs: {"status": "CONTINUATION_NOT_SUBMITTED"})
    with pytest.raises(WakePreSubmitError, match="not submitted"):
        asyncio.run(client.deliver_wake(**_exact_kwargs(lease)))

def test_uncertain_receipt_stays_unresolved():
    client, lease = _client(
        lambda *_args, **_kwargs: {"status": "CONTINUATION_SUBMIT_EFFECT_UNKNOWN"}
    )
    with pytest.raises(WakeEffectUnknownError, match="may have taken effect"):
        asyncio.run(client.deliver_wake(**_exact_kwargs(lease)))

def test_native_uncertainty_is_not_downgraded_to_no_effect():
    def submitter(*_args, **_kwargs):
        raise web_sol_client.WebSolExtensionError("continuation_submit_effect_unknown")

    client, lease = _client(submitter)
    with pytest.raises(WakeEffectUnknownError, match="remains unknown"):
        asyncio.run(client.deliver_wake(**_exact_kwargs(lease)))


def test_exact_completed_turn_builds_transient_semantic_projection():
    calls = []

    def observer(row, lease, **kwargs):
        calls.append((row, lease, kwargs))
        return {
            "status": "CONTINUATION_ACKNOWLEDGED",
            "provider_native_turn_id": "assistant-turn-current-001",
            "acknowledged_obligation_ids": list(kwargs["wake_obligation_ids"]),
            "terminal_ack_trailer": True,
        }

    client, lease = _client(
        lambda *_args, **_kwargs: {"status": "CONTINUATION_STARTED"},
        observer=observer,
    )
    observed = asyncio.run(client.observe_wake_ack(**_exact_kwargs(lease)))
    assert observed.runtime_binding_lease is lease
    assert observed.projection.provider_native_turn_id == "assistant-turn-current-001"
    assert observed.projection.obligation_ids == _exact_kwargs(lease)["obligation_ids"]
    assert calls[0][2]["nudge_id"] == NUDGE
    assert calls[0][2]["wake_obligation_ids"] == _exact_kwargs(lease)["obligation_ids"]


def test_pending_semantic_ack_is_read_only_hold():
    client, lease = _client(
        lambda *_args, **_kwargs: {"status": "CONTINUATION_STARTED"},
        observer=lambda *_args, **_kwargs: {"status": "CONTINUATION_ACK_PENDING"},
    )
    with pytest.raises(WakePreSubmitError, match="not ready"):
        asyncio.run(client.observe_wake_ack(**_exact_kwargs(lease)))


def test_reconcile_never_infers_prior_browser_effect():
    client, _lease = _client(lambda *_args, **_kwargs: {"status": "CONTINUATION_STARTED"})
    with pytest.raises(WakeEffectUnknownError, match="cannot infer"):
        asyncio.run(client.reconcile_wake())

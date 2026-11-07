"""Causal control-path tests for invalid prestart-verdict cleanup.

Provider transports and credential/cost ledger effects are recording fakes.
The real dispatcher, waterfall, guard, SDK loop and Codex error routing run.
"""
from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

FIXED_REFUSAL = "source admission revoked before provider start"


def invalid_verdict(location, error):
    if location == "attribute":
        class Verdict:
            @property
            def close(self):
                raise error
    else:
        class Verdict:
            def close(self):
                raise error
    return Verdict()


@pytest.fixture
def control_paths(monkeypatch):
    from brain import cli_bridge, codex_bridge, key_rotor
    from brain import provider_waterfall as pw

    observed = {
        "guard_calls": 0, "sdk_entries": 0, "sdk_queries": 0,
        "cli_fallback_entries": 0, "processes": [], "cooling": [],
        "classified": [], "sessions": [],
    }
    monkeypatch.setattr(cli_bridge, "_SDK", True)
    monkeypatch.setattr(cli_bridge, "cli_path", lambda: "/synthetic/claude")
    monkeypatch.setattr(cli_bridge, "_cfg", lambda: {"reasoning": {
        "allowed_tools": [], "add_dirs": [], "max_turns": 1,
        "permission_mode": "default",
    }})
    monkeypatch.setattr(cli_bridge, "_Options", lambda **kw: SimpleNamespace(**kw))
    monkeypatch.setattr(cli_bridge, "_subscription_env", lambda *_a, **_k: {})
    monkeypatch.setattr(cli_bridge, "_record_cli_cost", lambda *_a, **_k: None)
    monkeypatch.setattr(codex_bridge, "codex_path", lambda: "/synthetic/codex")
    monkeypatch.setattr(codex_bridge, "available", lambda: True)
    monkeypatch.setattr(codex_bridge, "_subprocess_env", lambda: {})
    monkeypatch.setattr(codex_bridge, "_mcp_secret_bundle", lambda: (None, None))

    def classify(value, **_kwargs):
        observed["classified"].append(value)
        if "access token could not be refreshed" in str(value or ""):
            return ("auth", "synthetic cleanup text")
        return None

    def cool(*args, **kwargs):
        observed["cooling"].append((args, kwargs))

    def record(*args, **kwargs):
        observed["sessions"].append((args, kwargs))

    monkeypatch.setattr(key_rotor, "classify_failure", classify)
    monkeypatch.setattr(key_rotor, "mark_cooling", cool)
    monkeypatch.setattr(key_rotor, "record_session", record)
    monkeypatch.setattr(key_rotor, "candidates", lambda: [])
    auth = SimpleNamespace(
        _is_auth_error=lambda _exc: False,
        _is_rate_limit_error=lambda _exc: False,
    )
    pool = SimpleNamespace(mark_cooling=cool, record_session=record)
    monkeypatch.setattr(pw, "_shared_modules", lambda: (auth, pool))
    monkeypatch.setattr(pw, "provider_rungs", lambda _role: [
        {"provider": "codex", "key_id": "synthetic-codex",
         "env_name": None, "cooling": False},
        {"provider": "oauth", "key_id": "synthetic-oauth",
         "env_name": "SYNTHETIC_UNUSED_TOKEN", "cooling": False},
    ])

    async def query(**_kwargs):
        observed["sdk_queries"] += 1
        yield SimpleNamespace(
            result="synthetic SDK continuation", total_cost_usd=0,
            session_id="synthetic-session", usage={},
        )

    monkeypatch.setattr(cli_bridge, "_sdk_query", query)
    actual_sdk = cli_bridge._via_sdk
    actual_cli = cli_bridge._via_subprocess

    async def sdk_entry(*args, **kwargs):
        observed["sdk_entries"] += 1
        return await actual_sdk(*args, **kwargs)

    async def cli_entry(*args, **kwargs):
        observed["cli_fallback_entries"] += 1
        return await actual_cli(*args, **kwargs)

    monkeypatch.setattr(cli_bridge, "_via_sdk", sdk_entry)
    monkeypatch.setattr(cli_bridge, "_via_subprocess", cli_entry)

    class Process:
        returncode = 0

        async def communicate(self, _payload):
            return json.dumps({
                "result": "synthetic CLI continuation", "is_error": False,
                "total_cost_usd": 0, "session_id": "synthetic-cli",
            }).encode(), b""

    async def process(*argv, **_kwargs):
        observed["processes"].append(list(argv))
        return Process()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", process)

    def execute(lane, verdict):
        def guard():
            observed["guard_calls"] += 1
            # A second check would allow. Any continuation after the first
            # invalid verdict must therefore be observable, not masked by
            # repeatedly returning the same invalid value.
            return verdict if observed["guard_calls"] == 1 else None

        common = dict(
            role="pm", arm=False, allowed_tools=[], add_dirs=[],
            mcp_servers={}, log_run=False, before_provider_start=guard,
        )
        if lane == "codex-waterfall":
            return asyncio.run(pw.reason("Synthetic veto test", **common))
        candidates = [
            {"key_id": "synthetic-1", "env_name": "SYNTHETIC_UNUSED_1"},
            {"key_id": "synthetic-2", "env_name": "SYNTHETIC_UNUSED_2"},
        ]
        return asyncio.run(cli_bridge._reason(
            "Synthetic veto test", **common, _backend_override="cli",
            _subscription_slots=candidates if lane == "sdk-rotation" else candidates[:1],
        ))

    return execute, observed


@pytest.mark.parametrize("location", ["attribute", "call"])
@pytest.mark.parametrize("lane", [
    "codex-waterfall", "sdk-fallback", "sdk-rotation",
])
def test_invalid_cleanup_cannot_turn_veto_into_provider_retry(
    control_paths, location, lane,
):
    from brain.cli_bridge import ProviderStartRefused

    execute, observed = control_paths
    detail = (
        "SYNTHETIC_PRIVATE_CLEANUP access token could not be refreshed"
        if lane != "sdk-fallback" else "SYNTHETIC_PRIVATE_CLEANUP ordinary failure"
    )
    verdict = invalid_verdict(location, RuntimeError(detail))
    try:
        result = execute(lane, verdict)
    except ProviderStartRefused as exc:
        assert str(exc) == FIXED_REFUSAL
        assert "SYNTHETIC_PRIVATE_CLEANUP" not in str(exc)
    else:
        pytest.fail(
            f"Invalid-verdict veto became a result: {result!r}; observed={observed!r}"
        )
    assert observed["guard_calls"] == 1
    assert observed["sdk_queries"] == 0
    assert observed["processes"] == []
    assert observed["cli_fallback_entries"] == 0
    assert observed["cooling"] == []
    assert observed["classified"] == []
    assert observed["sessions"] == []
    assert observed["sdk_entries"] == (0 if lane == "codex-waterfall" else 1)


@pytest.mark.parametrize("location", ["attribute", "call"])
@pytest.mark.parametrize("lane", ["codex-waterfall", "sdk-fallback"])
def test_cleanup_cancellation_preserves_identity_without_provider_entry(
    control_paths, location, lane,
):
    execute, observed = control_paths
    interruption = asyncio.CancelledError("synthetic cleanup cancellation")
    with pytest.raises(asyncio.CancelledError) as caught:
        execute(lane, invalid_verdict(location, interruption))
    assert caught.value is interruption
    assert observed["guard_calls"] == 1
    assert observed["sdk_queries"] == 0
    assert observed["processes"] == []
    assert observed["cli_fallback_entries"] == 0
    assert observed["cooling"] == []
    assert observed["classified"] == []
    assert observed["sessions"] == []

"""Veto-only source guard must execute at the ORIGINAL physical provider boundary.

Synthetic in-process tests only: no subscription, network, provider process,
credential, tool mutation or trading authority is touched.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest


def deny_source():
    raise ValueError("SYNTHETIC_PRIVATE_SOURCE_REASON_DO_NOT_LEAK")


def test_public_bridge_preserves_optional_prestart_veto_without_new_authority(monkeypatch):
    from brain import cli_bridge

    received=[]
    async def intercepted(prompt, **kwargs):
        received.append((prompt,kwargs))
        return {"ok":False,"error":"not_started"}

    monkeypatch.setattr(cli_bridge,"_reason",intercepted)
    asyncio.run(cli_bridge.reason(
        "Synthetic nontrading input", before_provider_start=deny_source,
    ))
    assert len(received)==1
    assert received[0][1]["before_provider_start"] is deny_source


def test_claude_agent_sdk_veto_prevents_first_provider_message(monkeypatch):
    from brain import cli_bridge

    seen=[]
    monkeypatch.setattr(cli_bridge,"_Options",lambda **kw:SimpleNamespace(**kw))
    async def no_sdk_query(*_args,**_kwargs):
        seen.append("SDK_START")
        if False:yield object()
    monkeypatch.setattr(cli_bridge,"_sdk_query",no_sdk_query)

    with pytest.raises(RuntimeError,match="source admission revoked before provider start") as caught:
        asyncio.run(cli_bridge._via_sdk(
            "synthetic input","claude-test","pm",None,None,[],[],1,
            None,"default",None,None,False,
            before_provider_start=deny_source,
        ))
    assert "SYNTHETIC_PRIVATE_SOURCE" not in str(caught.value)
    assert seen==[]


def test_claude_subprocess_veto_refuses_spawn(monkeypatch):
    from brain import cli_bridge

    seen=[]
    async def no_process(*_args,**_kwargs):
        seen.append("SUBPROCESS_STARTED")
        raise AssertionError("source denial leaked to provider process")
    monkeypatch.setattr(asyncio,"create_subprocess_exec",no_process)
    with pytest.raises(RuntimeError,match="source admission revoked before provider start"):
        asyncio.run(cli_bridge._via_subprocess(
            "synthetic input","claude-test","pm",None,None,[],[],1,None,
            "default",{},before_provider_start=deny_source,
        ))
    assert seen==[]


def test_codex_original_sealed_submitter_veto_prevents_process_start(monkeypatch,tmp_path):
    from brain import codex_bridge

    seen=[]
    monkeypatch.setattr(codex_bridge,"codex_path",lambda:"/usr/bin/codex-fake")
    monkeypatch.setattr(codex_bridge,"available",lambda:True)
    async def no_process(*_args,**_kwargs):
        seen.append("CODEX_STARTED")
        raise AssertionError("source denial leaked to Codex process")
    monkeypatch.setattr(asyncio,"create_subprocess_exec",no_process)

    with pytest.raises(RuntimeError,match="source admission revoked before provider start"):
        asyncio.run(codex_bridge.reason(
            "synthetic source-checked prompt",
            role="deep",arm=True,book="autonomous",
            allowed_tools=[],cwd=str(tmp_path),
            before_provider_start=deny_source,
        ))
    assert seen==[]


def test_bridge_without_veto_retains_prior_public_signature(monkeypatch):
    from brain import cli_bridge

    async def existing_backend(prompt, **kwargs):
        assert kwargs.get("before_provider_start") is None
        return {"ok":True,"text":"synthetic"}
    monkeypatch.setattr(cli_bridge,"_reason",existing_backend)
    assert asyncio.run(cli_bridge.reason("existing daily prompt"))["ok"] is True


def test_waterfall_veto_propagates_without_codex_to_oauth_replay(monkeypatch):
    from brain import cli_bridge, provider_waterfall as pw

    rungs = [
        {"provider": "codex", "key_id": "codex_account",
         "env_name": None, "cooling": False},
        {"provider": "oauth", "key_id": "claude_code_oauth_3",
         "env_name": "CLAUDE_CODE_OAUTH_TOKEN_3", "cooling": False},
    ]
    monkeypatch.setattr(pw, "provider_rungs", lambda _role: rungs)
    monkeypatch.setattr(pw, "_note_codex", lambda *_a, **_k: None)
    seen = []

    async def original_runner(_prompt, **kwargs):
        seen.append(kwargs["_backend_override"])
        assert kwargs["before_provider_start"] is deny_source
        cli_bridge._require_provider_start(kwargs["before_provider_start"])
        raise AssertionError("veto should have refused before this point")

    monkeypatch.setattr(cli_bridge, "_reason", original_runner)
    with pytest.raises(cli_bridge.ProviderStartRefused,
                       match="source admission revoked before provider start"):
        asyncio.run(pw.reason(
            "Synthetic no-provider test",
            role="deep", before_provider_start=deny_source,
        ))
    assert seen == ["codex"]


def test_rejected_callback_verdict_and_async_callbacks_never_grant_provider():
    from brain import cli_bridge

    async def async_guard():
        return None

    for callback in (lambda: False, lambda: True, lambda: "allow", async_guard):
        with pytest.raises(cli_bridge.ProviderStartRefused):
            cli_bridge._require_provider_start(callback)


def test_source_exception_details_do_not_escape_to_model_response():
    from brain import cli_bridge

    with pytest.raises(cli_bridge.ProviderStartRefused) as raised:
        cli_bridge._require_provider_start(deny_source)
    assert str(raised.value) == "source admission revoked before provider start"
    assert "SYNTHETIC_PRIVATE_SOURCE" not in str(raised.value)


def test_no_guard_is_backwards_compatible_and_cannot_create_permission():
    from brain import cli_bridge

    assert cli_bridge._require_provider_start(None) is None
    assert cli_bridge._require_provider_start(lambda: None) is None


def test_sdk_candidate_rotation_cannot_consume_denied_veto(monkeypatch):
    from brain import cli_bridge

    monkeypatch.setattr(cli_bridge, "_SDK", True)
    monkeypatch.setattr(cli_bridge, "cli_path", lambda: "/usr/bin/claude-fake")
    monkeypatch.setattr(cli_bridge, "_selected_backend", lambda *_: "cli")
    calls = []
    class Rotor:
        @staticmethod
        def candidates():
            return [
                {"key_id":"fixture-1","env_name":"FAKE_TOKEN_1"},
                {"key_id":"fixture-2","env_name":"FAKE_TOKEN_2"},
            ]
        @staticmethod
        def classify_failure(*_args, **_kwargs):
            return ("quota", "false-quota")

        @staticmethod
        def mark_cooling(*_args, **_kwargs):
            calls.append("cooled")
    from brain import key_rotor
    monkeypatch.setattr(key_rotor, "candidates", Rotor.candidates)
    monkeypatch.setattr(key_rotor, "classify_failure", Rotor.classify_failure)
    monkeypatch.setattr(key_rotor, "mark_cooling", Rotor.mark_cooling)
    async def refused(*_args, **_kwargs):
        calls.append("attempt")
        raise cli_bridge.ProviderStartRefused(
            "source admission revoked before provider start"
        )
    monkeypatch.setattr(cli_bridge, "_via_sdk", refused)
    with pytest.raises(cli_bridge.ProviderStartRefused):
        asyncio.run(cli_bridge._reason(
            "Synthetic no-provider prompt", role="pm", arm=True,
            before_provider_start=deny_source,
        ))
    assert calls == ["attempt"]

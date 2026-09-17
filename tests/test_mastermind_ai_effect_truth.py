"""Mastermind Portfolio Loop mutation failures preserve effect certainty."""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest


def _body(resp):
    return json.loads(resp.body)


def _call(web, kind):
    if kind == "settings":
        return web.api_mastermind_ai_settings(web._MMAISettingsReq(settings={"nudges_max": 4}))
    if kind == "directive":
        return web.api_mastermind_ai_directive(web._MMAIDirectiveReq(text="clean directive"))
    if kind == "nudges":
        return web.api_mastermind_ai_act_on_nudges(web._MMAIActNudgesReq(codes=["N1"]))
    return web.api_mastermind_ai_run()


@pytest.mark.parametrize("kind", ["settings", "directive", "nudges", "run"])
def test_engine_owned_result_passes_through_unchanged(monkeypatch, kind):
    from app import web

    expected = {"ok": False, "error": "expected engine rejection", "kind": kind}
    fake = SimpleNamespace(
        update_settings=lambda _s: expected,
        add_directive=lambda _t: expected,
        draft_directives_from_nudges=lambda _c: expected,
        run_cycle=lambda trigger="manual": expected,
    )
    monkeypatch.setattr(web, "_mastermind_ai_mutation_module", lambda: fake)
    assert _body(_call(web, kind)) == expected


@pytest.mark.parametrize(
    ("kind", "code"),
    [
        ("settings", "mastermind_ai_settings_unavailable"),
        ("directive", "mastermind_ai_directive_unavailable"),
        ("nudges", "mastermind_ai_act_on_nudges_unavailable"),
        ("run", "mastermind_ai_run_unavailable"),
    ],
)
def test_pre_effect_setup_failure_is_not_applied_and_retry_safe(monkeypatch, kind, code):
    from app import web

    def fail():
        raise RuntimeError("secret /Users/private/setup token=bad")

    monkeypatch.setattr(web, "_mastermind_ai_mutation_module", fail)
    response = _call(web, kind)
    payload = _body(response)
    assert response.status_code == 500
    assert payload == {
        "ok": False,
        "effect_status": "not_applied",
        "retry_safe": True,
        "error": code,
    }
    raw = response.body.decode()
    assert "secret" not in raw and "/Users/private" not in raw and "token=bad" not in raw


@pytest.mark.parametrize(
    ("kind", "code"),
    [
        ("settings", "mastermind_ai_settings_effect_unknown"),
        ("directive", "mastermind_ai_directive_effect_unknown"),
        ("nudges", "mastermind_ai_act_on_nudges_effect_unknown"),
        ("run", "mastermind_ai_run_effect_unknown"),
    ],
)
def test_invocation_failure_is_effect_unknown_and_not_retry_safe(monkeypatch, kind, code):
    from app import web

    def boom(*_args, **_kwargs):
        raise RuntimeError("secret /Users/private/effect token=bad")

    fake = SimpleNamespace(
        update_settings=boom,
        add_directive=boom,
        draft_directives_from_nudges=boom,
        run_cycle=boom,
    )
    monkeypatch.setattr(web, "_mastermind_ai_mutation_module", lambda: fake)
    response = _call(web, kind)
    payload = _body(response)
    assert response.status_code == 500
    assert payload == {
        "ok": False,
        "effect_status": "unknown",
        "retry_safe": False,
        "error": code,
    }
    raw = response.body.decode()
    assert "secret" not in raw and "/Users/private" not in raw and "token=bad" not in raw

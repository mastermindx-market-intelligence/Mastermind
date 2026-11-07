"""Mastermind Portfolio Loop mutation failures preserve effect certainty."""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest



def _bind_owner(monkeypatch, web, loader, *, fail_before_owner=False):
    """Control only the incumbent imports made by the actual web mutation handler."""
    import builtins
    original_import = builtins.__import__
    trace = {"bot_imports": 0, "owner_loads": 0}
    def imported(name, globals=None, locals=None, fromlist=(), level=0):
        if globals is web.__dict__ and level == 0:
            if name == "bot":
                trace["bot_imports"] += 1
                if fail_before_owner:
                    return loader()
                return SimpleNamespace()
            if name == "brain" and tuple(fromlist or ()) == ("mastermind_ai",):
                trace["owner_loads"] += 1
                return SimpleNamespace(mastermind_ai=loader())
        return original_import(name, globals, locals, fromlist, level)
    monkeypatch.setattr(builtins, "__import__", imported)
    return trace


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
    _bind_owner(monkeypatch, web, lambda: fake)
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

    _bind_owner(monkeypatch, web, fail)
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
    _bind_owner(monkeypatch, web, lambda: fake)
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


_DEFAULT_PAYLOAD = object()


def _code(kind, suffix):
    action = "act_on_nudges" if kind == "nudges" else kind
    return "mastermind_ai_" + action + "_" + suffix


def _engine(action):
    return SimpleNamespace(
        update_settings=lambda *args, **kwargs: action("update_settings", args, kwargs),
        add_directive=lambda *args, **kwargs: action("add_directive", args, kwargs),
        draft_directives_from_nudges=lambda *args, **kwargs: action("draft_directives_from_nudges", args, kwargs),
        run_cycle=lambda *args, **kwargs: action("run_cycle", args, kwargs),
    )


def _asgi_call(web, kind, payload=_DEFAULT_PAYLOAD):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    paths = {
        "settings": "/api/mastermind_ai/settings",
        "directive": "/api/mastermind_ai/directive",
        "nudges": "/api/mastermind_ai/act_on_nudges",
        "run": "/api/mastermind_ai/run",
    }
    if payload is _DEFAULT_PAYLOAD:
        payload = {
            "settings": {"settings": {"nudges_max": 4}},
            "directive": {"text": "clean directive"},
            "nudges": {"codes": ["N1"]},
            "run": None,
        }[kind]
    app = FastAPI()
    app.include_router(web.router)
    with TestClient(app) as client:
        return client.post(paths[kind], json=payload)


def _assert_failure(response, kind, *, unknown, caplog):
    assert response.status_code == 500
    assert response.json() == {
        "ok": False,
        "effect_status": "unknown" if unknown else "not_applied",
        "retry_safe": not unknown,
        "error": _code(kind, "effect_unknown" if unknown else "unavailable"),
    }
    assert "private" not in response.text and "token=" not in response.text
    assert "private" not in caplog.text and "token=" not in caplog.text


@pytest.mark.parametrize("kind", ["settings", "directive", "nudges", "run"])
def test_actual_asgi_setup_failure_stops_before_target_dispatch(monkeypatch, caplog, kind):
    from app import web
    def loader():
        raise RuntimeError("private setup token=hidden")
    trace = _bind_owner(monkeypatch, web, loader)
    response = _asgi_call(web, kind)
    _assert_failure(response, kind, unknown=False, caplog=caplog)
    assert trace == {"bot_imports": 1, "owner_loads": 1}
    assert "RuntimeError" in caplog.text


@pytest.mark.parametrize("kind", ["settings", "directive", "nudges", "run"])
def test_actual_asgi_effect_then_exception_is_unknown_without_retry(monkeypatch, caplog, kind):
    from app import web
    calls, effects = [], []
    def act(method, args, kwargs):
        calls.append((method, args, kwargs))
        effects.append("recorded")
        raise RuntimeError("private mutation result token=hidden")
    trace = _bind_owner(monkeypatch, web, lambda: _engine(act))
    response = _asgi_call(web, kind)
    _assert_failure(response, kind, unknown=True, caplog=caplog)
    assert len(calls) == 1 and effects == ["recorded"]
    assert trace == {"bot_imports": 1, "owner_loads": 1}
    assert "RuntimeError" in caplog.text


@pytest.mark.parametrize("kind", ["settings", "directive", "nudges", "run"])
@pytest.mark.parametrize("bad_result", ["object", "nan"])
def test_actual_asgi_response_encoding_failure_preserves_effect_uncertainty(monkeypatch, caplog, kind, bad_result):
    from app import web
    calls, effects = [], []
    def act(method, args, kwargs):
        calls.append((method, args, kwargs))
        effects.append("recorded")
        return {"result": object() if bad_result == "object" else float("nan")}
    trace = _bind_owner(monkeypatch, web, lambda: _engine(act))
    response = _asgi_call(web, kind)
    _assert_failure(response, kind, unknown=True, caplog=caplog)
    assert len(calls) == 1 and effects == ["recorded"]
    assert trace == {"bot_imports": 1, "owner_loads": 1}
    assert ("TypeError" if bad_result == "object" else "ValueError") in caplog.text


@pytest.mark.parametrize(("kind", "payload"), [
    ("settings", {"settings": []}),
    ("directive", {"text": None}),
    ("nudges", {"codes": "N1"}),
])
def test_actual_request_validation_precedes_owner_loading(monkeypatch, kind, payload):
    from app import web
    called = []
    def loader():
        called.append("load")
        raise AssertionError("invalid request must not reach owner")
    trace = _bind_owner(monkeypatch, web, loader)
    response = _asgi_call(web, kind, payload)
    assert response.status_code == 422
    assert called == [] and trace == {"bot_imports": 0, "owner_loads": 0}


@pytest.mark.parametrize(("kind", "payload", "method", "args", "kwargs"), [
    ("settings", {"settings": {"nudges_max": 4}}, "update_settings", [{"nudges_max": 4}], {}),
    ("settings", {"settings": {}}, "update_settings", [{}], {}),
    ("directive", {"text": "clean directive"}, "add_directive", ["clean directive"], {}),
    ("nudges", {"codes": ["N1"]}, "draft_directives_from_nudges", [["N1"]], {}),
    ("nudges", {}, "draft_directives_from_nudges", [None], {}),
    ("run", None, "run_cycle", [], {"trigger": "manual"}),
])
def test_actual_loader_and_route_preserve_incumbent_method_arguments(monkeypatch, kind, payload, method, args, kwargs):
    from app import web
    calls = []
    expected = {"ok": True, "kind": kind}
    def act(name, actual_args, actual_kwargs):
        calls.append((name, list(actual_args), actual_kwargs))
        return expected
    trace = _bind_owner(monkeypatch, web, lambda: _engine(act))
    response = _asgi_call(web, kind, payload)
    assert response.status_code == 200
    assert response.json() == expected
    assert calls == [(method, args, kwargs)]
    assert trace == {"bot_imports": 1, "owner_loads": 1}


@pytest.mark.parametrize("kind", ["settings", "directive", "nudges", "run"])
def test_first_import_failure_is_closed_before_owner_lookup(monkeypatch, caplog, kind):
    from app import web
    def fail():
        raise ModuleNotFoundError("private bootstrap token=hidden")
    trace = _bind_owner(monkeypatch, web, fail, fail_before_owner=True)
    response = _asgi_call(web, kind)
    _assert_failure(response, kind, unknown=False, caplog=caplog)
    assert trace == {"bot_imports": 1, "owner_loads": 0}
    assert "ModuleNotFoundError" in caplog.text


@pytest.mark.parametrize("kind", ["settings", "directive", "nudges", "run"])
def test_callable_lookup_failure_stays_conservatively_unknown(monkeypatch, caplog, kind):
    from app import web
    lookups = []
    class Owner:
        def __getattr__(self, name):
            lookups.append(name)
            raise RuntimeError("private owner lookup token=hidden")
    trace = _bind_owner(monkeypatch, web, lambda: Owner())
    response = _asgi_call(web, kind)
    _assert_failure(response, kind, unknown=True, caplog=caplog)
    assert len(lookups) == 1
    assert trace == {"bot_imports": 1, "owner_loads": 1}

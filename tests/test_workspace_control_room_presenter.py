"""Signed Workspace/Control Room read presentation over the existing cache.

No new TCP listener, OAuth principal mint, surface-binding write or operation.
"""
import asyncio
import copy

import pytest

from control_plane.workspace_control_room_presenter import ExistingControlRoomPresenter
from tests.test_workspace_read_service import cache_fixture
from scripts import chairman_control_room as ccr


def principal(client="fixture-web"):
    return {"policy_id": "workspace-test", "issuer_digest": "a" * 64,
            "subject_digest": "b" * 64, "client_ref": client,
            "resource": "https://mcp.mastermind-x.com/workspace/read",
            "scopes": ["mastermind.workspace.read"]}


def owner(allowed):
    def authorize(p):
        return p.get("client_ref") in allowed
    authorize.binding_digest = lambda p: (
        "c" * 64 if p.get("client_ref") in allowed else None
    )
    return authorize


def read(presenter, p=None, operation="state"):
    return asyncio.run(presenter.read(principal() if p is None else p, operation))


def test_signed_state_uses_exact_published_cache_and_no_new_server(tmp_path, monkeypatch):
    owners, clock, cache = cache_fixture(tmp_path)
    monkeypatch.setattr(ccr.capability, "census", lambda **kw: {"test-only": True})
    presenter = ExistingControlRoomPresenter(cache, authorize=owner({"fixture-web"}))
    result = read(presenter)
    assert result["ok"] is True
    body = result["result"]
    assert body["control_room"] == owners[0].state_cache["doc"]
    assert body["capabilities"] == {"test-only": True}
    assert body["refresh_in_flight"] is False
    assert body["live_builds_active"] is False
    assert owners[0].state_published_seq == 1
    assert "state_refresh_error" in body and "source_validity" in body
    assert "_server" not in vars(presenter) and "_cache" in vars(presenter)


@pytest.mark.parametrize("operation", ["open", "bind", "unbind", "refresh-builds"])
def test_workspace_read_alone_never_dispatches_original_operator_actions(tmp_path, operation, monkeypatch):
    owners, _, cache = cache_fixture(tmp_path)
    monkeypatch.setattr(ccr, "_discover_document", lambda *_: pytest.fail("discovery must not run"))
    monkeypatch.setattr(ccr, "_ensure_capabilities_cached", lambda *_: pytest.fail("state must not run"))
    presenter = ExistingControlRoomPresenter(cache, authorize=owner({"fixture-web"}))
    result = read(presenter, operation=operation)
    assert result["status"] == 403 and result["error"]["code"] == "access_denied"
    assert owners[0].state_published_seq == 1


def test_rejects_unsigned_or_foreign_principal_before_any_source_access(tmp_path, monkeypatch):
    _, _, cache = cache_fixture(tmp_path)
    monkeypatch.setattr(ccr, "_ensure_capabilities_cached", lambda *_: pytest.fail("source read"))
    p = ExistingControlRoomPresenter(cache, authorize=owner({"fixture-web"}))
    for candidate in (principal("foreign-user"), {}, "admin@mastermind-x.com",
                      dict(principal(), raw_email="admin@mastermind-x.com"),
                      dict(principal(), scopes=["mastermind.workspace.control"])):
        result = read(p, candidate)
        assert result["status"] == 403
    assert read(p, operation="fake")["status"] == 400


def test_two_enrolled_accounts_use_same_cache_without_role_strings(tmp_path, monkeypatch):
    owners, _, cache = cache_fixture(tmp_path)
    monkeypatch.setattr(ccr.capability, "census", lambda **kw: {})
    p = ExistingControlRoomPresenter(cache, authorize=owner({"fixture-web", "fixture-mac"}))
    a, b = read(p, principal("fixture-web")), read(p, principal("fixture-mac"))
    assert a["ok"] and b["ok"]
    assert a["result"]["control_room"] == b["result"]["control_room"]
    assert owners[0].state_published_seq == 1


def test_candidate_discovery_requires_distinct_owner_action_grant(tmp_path, monkeypatch):
    owners, _, cache = cache_fixture(tmp_path)
    calls = []
    monkeypatch.setattr(ccr, "_discover_document", lambda conf: calls.append(conf) or {"candidates": []})
    user = owner({"fixture-web"})
    p = ExistingControlRoomPresenter(cache, authorize=user)
    assert read(p, operation="discover")["status"] == 403
    assert calls == []
    discovery = owner({"fixture-web"})
    p = ExistingControlRoomPresenter(cache, authorize=user, authorize_discovery=discovery)
    assert read(p, operation="discover") == {"ok": True, "result": {"candidates": []}}
    assert calls == [owners[0]]


def test_revocation_during_async_discovery_refuses_release(tmp_path, monkeypatch):
    _, _, cache = cache_fixture(tmp_path)
    allowed = {"fixture-web"}
    def revoke(conf):
        allowed.clear()
        return {"private": "never released"}
    monkeypatch.setattr(ccr, "_discover_document", revoke)
    p = ExistingControlRoomPresenter(cache, authorize=owner(allowed),
                                     authorize_discovery=owner(allowed))
    assert read(p, operation="discover")["status"] == 403
    assert "private" not in str(read(p, operation="discover"))


def test_publication_changed_mid_discovery_refuses_stale_source(tmp_path, monkeypatch):
    owners, _, cache = cache_fixture(tmp_path)
    def advance(_):
        owners[0].state_published_seq += 1
        return {"private": "never released"}
    monkeypatch.setattr(ccr, "_discover_document", advance)
    p = ExistingControlRoomPresenter(cache, authorize=owner({"fixture-web"}),
                                     authorize_discovery=owner({"fixture-web"}))
    result = read(p, operation="discover")
    assert result["status"] == 503 and "private" not in str(result)


def test_bounded_discovery_never_returns_unbounded_local_data(tmp_path, monkeypatch):
    _, _, cache = cache_fixture(tmp_path)
    monkeypatch.setattr(ccr, "_discover_document", lambda _: {"raw": "x" * 2_000_001})
    p = ExistingControlRoomPresenter(cache, authorize=owner({"fixture-web"}),
                                     authorize_discovery=owner({"fixture-web"}))
    result = read(p, operation="discover")
    assert result["status"] == 503 and "raw" not in str(result)

"""Direct owner operations on private fixtures; no server or native effect."""
import stat

import pytest

from control_plane import surface_bindings as sb
from scripts import chairman_control_room as publisher
from tests.test_control_room_binding_transactions import (
    FIRST, SECOND, VERIFIED, assert_provider_locks_released, bind_payload,
    binding, config, invoke, save,
)
from tests.test_chairman_control_room_server import (
    _b5_navigation_fixture, _b5_owed_request, _b5_sample,
)


def test_direct_operations_share_the_original_binding_file_without_a_server(tmp_path, monkeypatch):
    cfg = config(tmp_path)
    original = binding(FIRST)
    save(cfg, [original])

    def no_server(*args, **kwargs):
        pytest.fail("direct owner operations must not create a listener")

    monkeypatch.setattr(publisher, "ControlRoomServer", no_server)
    calls = []

    def provider(selected, runner, **kwargs):
        assert_provider_locks_released(cfg)
        assert selected == original
        with pytest.raises(TypeError):
            selected["locator"]["chat_id"] = "changed"
        calls.append(selected["binding_id"])
        return {"ok": True, "verified": True, "action": "fixture-open"}

    cfg.open_binding_fn = provider
    created = publisher.bind_surface(cfg, **bind_payload())
    assert created["ok"] is True
    result = publisher.open_surface(cfg, binding_id=FIRST)
    assert result.source_precondition_failed is False
    assert result.outcome == {"ok": True, "verified": True, "action": "fixture-open"}
    assert publisher.unbind_surface(cfg, binding_id=created["binding_id"]) == {"ok": True}
    doc, problems = sb.load_bindings(cfg.bindings_path)
    assert not problems
    assert doc["bindings"] == [dict(original, last_verified_at=VERIFIED)]
    assert stat.S_IMODE(cfg.bindings_path.stat().st_mode) == 0o600
    assert calls == [FIRST]


def test_direct_open_preserves_concurrent_legacy_bind_and_unbind(tmp_path):
    cfg = config(tmp_path)
    original = binding(FIRST)
    save(cfg, [original, binding(SECOND, target="sibling", work_ref="WS:SIBLING")])

    def provider(selected, runner, **kwargs):
        assert_provider_locks_released(cfg)
        assert invoke(cfg, "unbind", {"binding_id": SECOND}) == (200, {"ok": True})
        status, created = invoke(cfg, "bind", bind_payload())
        assert status == 200 and created["ok"]
        return {"ok": True, "verified": True}

    cfg.open_binding_fn = provider
    result = publisher.open_surface(cfg, binding_id=FIRST)
    assert result.outcome == {"ok": True, "verified": True}
    doc, problems = sb.load_bindings(cfg.bindings_path)
    assert not problems
    by_target = {row["locator"]["chat_id"]: row for row in doc["bindings"]}
    assert set(by_target) == {"original", "added"}
    assert by_target["original"] == dict(original, last_verified_at=VERIFIED)


@pytest.mark.parametrize("context", [None, {}, "ordinary-open-is-not-a-fallback"])
def test_explicit_invalid_owed_context_never_becomes_ordinary_open(tmp_path, context):
    cfg = config(tmp_path)
    save(cfg, [binding(FIRST)])
    before = cfg.bindings_path.read_bytes()
    calls = []
    cfg.open_binding_fn = lambda *a, **k: calls.append(a) or {"ok": True, "verified": True}
    result = publisher.open_surface(cfg, binding_id=FIRST, owed_context=context)
    assert result.source_precondition_failed is True
    assert result.outcome["next_action"] == "read_current_state"
    assert result.outcome["failure_kind"] == "source_precondition_failed"
    assert calls == [] and cfg.bindings_path.read_bytes() == before


@pytest.mark.parametrize("case", ["valid", "expired", "publication"])
def test_direct_owed_open_uses_the_current_owner_and_never_persists(tmp_path, monkeypatch, case):
    cfg, clock, original = _b5_navigation_fixture(tmp_path, monkeypatch)
    publisher._refresh_state_cache(
        cfg, timeout=240, generation=publisher._reserve_composition(cfg),
        include_capabilities=False,
    )
    snapshot = publisher._cached_state_snapshot(cfg)
    request = _b5_owed_request({
        "control_room": snapshot["doc"], "source_validity": snapshot["source_validity"],
    })
    if case == "expired":
        clock[:] = _b5_sample(1984)
    elif case == "publication":
        request["owed_context"]["publication_seq"] += 1
    before = cfg.bindings_path.read_bytes()
    calls, saves = [], []

    def provider(selected, runner, **kwargs):
        assert_provider_locks_released(cfg)
        assert selected == original
        calls.append(selected["binding_id"])
        return {"ok": True, "verified": True, "action": "fixture-only"}

    cfg.open_binding_fn = provider
    monkeypatch.setattr(sb, "save_bindings", lambda *a, **k: saves.append(a))
    result = publisher.open_surface(cfg, **request)
    assert result.source_precondition_failed is (case != "valid")
    assert calls == ([original["binding_id"]] if case == "valid" else [])
    assert saves == [] and cfg.bindings_path.read_bytes() == before


def test_provider_failure_kind_cannot_masquerade_as_an_owner_precondition_refusal(tmp_path):
    cfg = config(tmp_path)
    save(cfg, [binding(FIRST)])
    outcome = {"ok": False, "verified": False, "failure_kind": "source_precondition_failed"}
    calls = []
    cfg.open_binding_fn = lambda *a, **k: calls.append(a) or outcome
    result = publisher.open_surface(cfg, binding_id=FIRST)
    assert result.source_precondition_failed is False
    assert result.outcome == outcome
    assert invoke(cfg, "open", {"binding_id": FIRST}) == (200, outcome)
    assert len(calls) == 2


def test_provider_exception_after_dispatch_is_not_reclassified_as_a_precondition_refusal(tmp_path):
    cfg = config(tmp_path)
    save(cfg, [binding(FIRST)])
    calls = []

    def provider(*args, **kwargs):
        calls.append(True)
        raise ValueError("fixture provider may already have acted")

    cfg.open_binding_fn = provider
    with pytest.raises(ValueError, match="may already have acted"):
        publisher.open_surface(cfg, binding_id=FIRST)
    assert calls == [True]


@pytest.mark.parametrize("failure_stage", ["before_write", "after_replace"])
def test_direct_open_preserves_navigation_when_timestamp_persistence_is_uncertain(
    tmp_path, monkeypatch, failure_stage,
):
    cfg = config(tmp_path)
    original = binding(FIRST)
    save(cfg, [original])
    real_save = sb.save_bindings
    outcome = {"ok": True, "verified": True, "detail": "fixture navigation completed"}
    calls = []
    cfg.open_binding_fn = lambda *a, **k: calls.append(a) or outcome

    def failed_save(doc, path):
        if failure_stage == "after_replace":
            real_save(doc, path)
        raise OSError("fixture private locator")

    monkeypatch.setattr(sb, "save_bindings", failed_save)
    result = publisher.open_surface(cfg, binding_id=FIRST)
    assert result.source_precondition_failed is False
    assert result.outcome["ok"] and result.outcome["verified"]
    assert result.outcome["detail"] == (
        "Open completed; the verification timestamp update could not be confirmed. "
        "Do not repeat Open solely to update this timestamp."
    )
    assert outcome["detail"] == "fixture navigation completed" and len(calls) == 1
    doc, problems = sb.load_bindings(cfg.bindings_path)
    assert not problems
    assert doc["bindings"] == [dict(
        original, last_verified_at=VERIFIED if failure_stage == "after_replace" else None,
    )]


@pytest.mark.parametrize("action,kwargs", [
    ("open_surface", {"binding_id": ""}),
    ("open_surface", {"binding_id": FIRST, "target_surface": "unknown"}),
    ("bind_surface", dict(bind_payload(), role=None)),
    ("bind_surface", dict(bind_payload(), locator=[])),
    ("bind_surface", dict(bind_payload(), seat_ref=True)),
    ("unbind_surface", {"binding_id": None}),
])
def test_direct_owner_operations_reject_invalid_primitives_before_effect(tmp_path, action, kwargs):
    cfg = config(tmp_path)
    save(cfg, [binding(FIRST)])
    before = cfg.bindings_path.read_bytes()
    calls = []
    cfg.open_binding_fn = lambda *a, **k: calls.append(a)
    with pytest.raises(ValueError):
        getattr(publisher, action)(cfg, **kwargs)
    assert calls == [] and cfg.bindings_path.read_bytes() == before

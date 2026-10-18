"""Admission callbacks use actual first-effect edges, with inert fixture owners."""
import json

import pytest

from control_plane import surface_bindings as sb
from scripts import chairman_control_room as publisher
from tests.test_control_room_binding_transactions import (
    FIRST, VERIFIED, assert_provider_locks_released, bind_payload, binding, config, save,
)
from tests.test_control_room_refresh_publication import compiler_fixture, document


@pytest.mark.parametrize("operation", ["open", "bind", "unbind"])
def test_guard_rechecks_after_the_canonical_binding_read_and_before_any_effect(
    tmp_path, monkeypatch, operation,
):
    cfg = config(tmp_path)
    save(cfg, [binding(FIRST)])
    before = cfg.bindings_path.read_bytes()
    read = sb.load_bindings
    reads, guards, effects = [], [], []

    def moved_owner(path):
        value = read(path)
        reads.append(True)  # Admission may have expired or been revoked during this read.
        return value

    def refuse():
        assert reads, "admission was checked before the potentially blocking source read"
        guards.append(True)
        raise RuntimeError("fixture admission expired")

    monkeypatch.setattr(sb, "load_bindings", moved_owner)
    monkeypatch.setattr(sb, "save_bindings", lambda *a, **k: effects.append("write"))
    cfg.open_binding_fn = lambda *a, **k: effects.append("provider")
    kwargs = bind_payload() if operation == "bind" else {"binding_id": FIRST}
    with pytest.raises(RuntimeError, match="admission expired"):
        getattr(publisher, operation + "_surface")(cfg, before_effect=refuse, **kwargs)
    assert guards == [True] and effects == []
    assert cfg.bindings_path.read_bytes() == before


def test_open_admission_is_once_before_provider_and_not_repeated_for_owned_metadata(tmp_path):
    cfg = config(tmp_path)
    original = binding(FIRST)
    save(cfg, [original])
    order = []

    def admit():
        assert_provider_locks_released(cfg)
        order.append("admitted")

    def provider(*args, **kwargs):
        assert order == ["admitted"]
        order.append("provider")
        return {"ok": True, "verified": True}

    cfg.open_binding_fn = provider
    result = publisher.open_surface(cfg, binding_id=FIRST, before_effect=admit)
    assert result.outcome == {"ok": True, "verified": True}
    assert order == ["admitted", "provider"]
    doc, problems = sb.load_bindings(cfg.bindings_path)
    assert not problems and doc["bindings"] == [dict(original, last_verified_at=VERIFIED)]


@pytest.mark.parametrize("operation", ["bind", "unbind"])
def test_binding_guard_keeps_the_original_complete_transaction_lock(tmp_path, operation):
    cfg = config(tmp_path)
    save(cfg, [binding(FIRST)])
    calls = []

    def admit():
        acquired = cfg.bindings_lock.acquire(blocking=False)
        if acquired:
            cfg.bindings_lock.release()
        assert not acquired, "admission split the original binding transaction"
        assert cfg.state_lock.acquire(blocking=False)
        cfg.state_lock.release()
        calls.append(True)

    kwargs = bind_payload() if operation == "bind" else {"binding_id": FIRST}
    result = getattr(publisher, operation + "_surface")(cfg, before_effect=admit, **kwargs)
    assert result["ok"] is True and calls == [True]


def test_refresh_guard_precedes_compiler_and_does_not_abandon_admitted_publication(tmp_path, monkeypatch):
    cfg, snapshot = compiler_fixture(
        tmp_path, monkeypatch,
        source=lambda now, *, active_builds_snapshot: document(active_builds_snapshot),
    )
    order = []

    def admit():
        assert_provider_locks_released(cfg)
        assert not order
        order.append("admitted")

    def runner(*args, **kwargs):
        assert order == ["admitted"]
        order.append("compiler")
        return {"code": 0, "timed_out": False, "stdout": json.dumps(snapshot), "stderr": ""}

    cfg.runner = runner
    result = publisher.refresh_builds(cfg, before_effect=admit)
    assert order == ["admitted", "compiler"]
    assert result == {"ok": True, "collected_at": snapshot["collected_at"]}
    assert cfg.live_cache["active_builds"] == snapshot
    assert cfg.state_published_seq == 1


def test_refresh_refused_at_effect_edge_never_invokes_compiler_or_reserves(tmp_path, monkeypatch):
    cfg, _ = compiler_fixture(
        tmp_path, monkeypatch,
        source=lambda *a, **k: pytest.fail("refused refresh reached composition"),
        runner=lambda *a, **k: pytest.fail("refused refresh reached compiler"),
    )

    def refuse():
        raise RuntimeError("fixture owner retired")

    with pytest.raises(RuntimeError, match="owner retired"):
        publisher.refresh_builds(cfg, before_effect=refuse)
    assert cfg.state_compose_seq == cfg.state_explicit_floor == 0
    assert cfg.state_refreshes_in_flight == 0
    assert cfg.live_cache == cfg.state_cache == {}

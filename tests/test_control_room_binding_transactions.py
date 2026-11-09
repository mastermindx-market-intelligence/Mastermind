"""Fixture-only binding transactions; no HTTP listener or native provider calls."""
from __future__ import annotations

import json
import stat
import threading
from types import SimpleNamespace

import pytest

from control_plane import surface_bindings as sb
from scripts import chairman_control_room as publisher

OBSERVED = "2026-10-18T00:00:00Z"
VERIFIED = "2026-10-18T01:00:00Z"
LATER_VERIFIED = "2026-10-18T02:00:00Z"
FIRST = "11111111-1111-4111-8111-111111111111"
SECOND = "22222222-2222-4222-8222-222222222222"


def binding(binding_id, *, target="original", work_ref="WS:BINDING-RACE"):
    return sb.new_binding(
        work_ref=work_ref, role="worker", provider="cursor_agent",
        locator_kind="cursor_agent_thread",
        locator={"chat_id": target, "workspace_dir": None},
        observed_at=OBSERVED, binding_id=binding_id,
    )


def config(tmp_path):
    def no_runner(*args, **kwargs):
        pytest.fail("a binding transaction must not invoke a native runner")

    return publisher.ServerConfig(
        repo_root=tmp_path, macro_root=None,
        bindings_path=tmp_path / "bindings.json",
        token="fixture", origin="http://127.0.0.1:0", port=0,
        now_fn=lambda: VERIFIED, runner=no_runner,
    )


def save(cfg, rows):
    sb.save_bindings({"schema": sb.SCHEMA, "bindings": rows}, cfg.bindings_path)


def invoke(cfg, action, data):
    handler = object.__new__(publisher.ChairmanControlRoomHandler)
    handler.server = SimpleNamespace(config=cfg)
    handler._read_json_body = lambda: (data, None)
    responses = []
    handler._send_json = lambda status, payload, **kwargs: responses.append((status, payload))
    getattr(handler, "_handle_" + action)()
    assert len(responses) == 1
    return responses[0]


def bind_payload(*, target="added", work_ref="WS:ADDED"):
    return {
        "work_ref": work_ref, "role": "worker", "provider": "cursor_agent",
        "locator": {"chat_id": target, "workspace_dir": None},
    }


def assert_provider_locks_released(cfg):
    for lock in (getattr(cfg, "bindings_lock", None), cfg.state_lock):
        if lock is not None:
            assert lock.acquire(blocking=False), "owner lock spans provider work"
            lock.release()


@pytest.mark.parametrize("movement", [
    "bind_sibling", "unbind_selected", "unbind_sibling", "replace_selected",
    "restamp_selected", "invalid_document", "missing_document", "switch_path",
])
def test_verified_open_merges_only_unchanged_original_into_current_bindings(tmp_path, movement):
    cfg = config(tmp_path)
    original, sibling = binding(FIRST), binding(SECOND, target="sibling", work_ref="WS:SIBLING")
    save(cfg, [original, sibling])
    original_path = cfg.bindings_path
    original_bytes = original_path.read_bytes()
    expected = {}
    calls = []

    def provider(selected, runner, **kwargs):
        assert selected == original
        calls.append(json.loads(json.dumps(selected)))
        assert_provider_locks_released(cfg)
        if movement == "bind_sibling":
            status, result = invoke(cfg, "bind", bind_payload())
            assert status == 200 and result["ok"] is True
        elif movement in {"unbind_selected", "unbind_sibling"}:
            remove = FIRST if movement == "unbind_selected" else SECOND
            status, result = invoke(cfg, "unbind", {"binding_id": remove})
            assert status == 200 and result == {"ok": True}
        elif movement == "replace_selected":
            replacement = binding(FIRST, target="replacement")
            save(cfg, [replacement, sibling])
        elif movement == "restamp_selected":
            save(cfg, [dict(original, last_verified_at=LATER_VERIFIED), sibling])
        elif movement == "invalid_document":
            original_path.write_bytes(b"invalid fixture document")
        elif movement == "missing_document":
            original_path.unlink()
        elif movement == "switch_path":
            cfg.bindings_path = tmp_path / "other-bindings.json"
            save(cfg, [sibling])
        if cfg.bindings_path.exists():
            expected["bytes"] = cfg.bindings_path.read_bytes()
        if movement in {"bind_sibling", "unbind_sibling"}:
            expected_doc, problems = sb.load_bindings(cfg.bindings_path)
            assert not problems
            for row in expected_doc["bindings"]:
                if row["binding_id"] == FIRST:
                    row["last_verified_at"] = VERIFIED
            expected["doc"] = expected_doc
        return {"ok": True, "verified": True, "action": "fixture-only"}

    cfg.open_binding_fn = provider
    status, outcome = invoke(cfg, "open", {"binding_id": FIRST})
    assert status == 200 and outcome == {
        "ok": True, "verified": True, "action": "fixture-only",
    }
    assert calls == [original]
    if movement == "missing_document":
        assert not original_path.exists(), "late verification recreated a deleted binding document"
    elif "doc" in expected:
        actual, problems = sb.load_bindings(cfg.bindings_path)
        assert not problems and actual == expected["doc"]
        assert stat.S_IMODE(cfg.bindings_path.stat().st_mode) == 0o600
    else:
        assert cfg.bindings_path.read_bytes() == expected["bytes"]
    if movement == "switch_path":
        assert original_path.read_bytes() == original_bytes


@pytest.mark.parametrize("second_action", ["bind", "unbind"])
def test_same_owner_serializes_complete_binding_transactions(tmp_path, monkeypatch, second_action):
    cfg = config(tmp_path)
    original = binding(FIRST)
    save(cfg, [original])
    load = sb.load_bindings
    first_read = threading.Event()
    release_first = threading.Event()
    second_started = threading.Event()
    second_read = threading.Event()
    results, errors = {}, []

    def delayed_load(path):
        result = load(path)
        if threading.current_thread().name == "binding-first":
            first_read.set()
            assert release_first.wait(3), "fixture did not release the first read"
        elif threading.current_thread().name == "binding-second":
            second_read.set()
        return result

    monkeypatch.setattr(sb, "load_bindings", delayed_load)

    def run(name, action, payload):
        try:
            if name == "second":
                second_started.set()
            results[name] = invoke(cfg, action, payload)
        except BaseException as exc:
            errors.append(exc)

    first = threading.Thread(
        target=run, name="binding-first",
        args=("first", "bind", bind_payload(target="first", work_ref="WS:FIRST")),
        daemon=True,
    )
    second_payload = (bind_payload(target="second", work_ref="WS:SECOND")
                      if second_action == "bind" else {"binding_id": FIRST})
    second = threading.Thread(
        target=run, name="binding-second",
        args=("second", second_action, second_payload), daemon=True,
    )
    first.start()
    try:
        assert first_read.wait(2)
        second.start()
        assert second_started.wait(2)
        second_read_before_first_completed = second_read.wait(0.2)
    finally:
        release_first.set()
        first.join(3)
        if second.ident is not None:
            second.join(3)
    assert not first.is_alive() and not second.is_alive()
    assert not errors, errors
    assert not second_read_before_first_completed, "two owner transactions read the same stale document"
    assert all(status == 200 and outcome["ok"] is True for status, outcome in results.values())
    doc, problems = load(cfg.bindings_path)
    assert not problems
    targets = {row["locator"]["chat_id"] for row in doc["bindings"]}
    assert targets == ({"original", "first", "second"} if second_action == "bind" else {"first"})
    assert stat.S_IMODE(cfg.bindings_path.stat().st_mode) == 0o600


def test_provider_and_response_run_outside_binding_and_state_locks(tmp_path):
    cfg = config(tmp_path)
    save(cfg, [binding(FIRST)])
    assert hasattr(cfg, "bindings_lock")
    calls = []

    def provider(selected, runner, **kwargs):
        assert_provider_locks_released(cfg)
        calls.append(selected["binding_id"])
        return {"ok": True, "verified": True}

    cfg.open_binding_fn = provider
    handler = object.__new__(publisher.ChairmanControlRoomHandler)
    handler.server = SimpleNamespace(config=cfg)
    handler._read_json_body = lambda: ({"binding_id": FIRST}, None)
    responses = []

    def respond(status, payload, **kwargs):
        assert_provider_locks_released(cfg)
        responses.append((status, payload))

    handler._send_json = respond
    handler._handle_open()
    assert calls == [FIRST] and responses == [(200, {"ok": True, "verified": True})]


def test_normal_open_preserves_immutable_checked_target(tmp_path):
    cfg = config(tmp_path)
    original = binding(FIRST)
    save(cfg, [original])
    calls = []

    def provider(selected, runner, **kwargs):
        assert_provider_locks_released(cfg)
        assert selected == original
        with pytest.raises(TypeError):
            selected["role"] = "observer"
        with pytest.raises(TypeError):
            selected["locator"]["chat_id"] = "different-target"
        calls.append(selected["binding_id"])
        return {"ok": True, "verified": True}

    cfg.open_binding_fn = provider
    assert invoke(cfg, "open", {"binding_id": FIRST}) == (200, {"ok": True, "verified": True})
    doc, problems = sb.load_bindings(cfg.bindings_path)
    assert not problems
    assert doc["bindings"] == [dict(original, last_verified_at=VERIFIED)]
    assert calls == [FIRST]


@pytest.mark.parametrize("failure_stage", ["before_write", "after_replace"])
def test_timestamp_persistence_failure_preserves_actual_navigation_result(tmp_path, monkeypatch, failure_stage):
    cfg = config(tmp_path)
    original = binding(FIRST)
    save(cfg, [original])
    real_save = sb.save_bindings
    calls, saves = [], []
    provider_outcome = {
        "ok": True, "verified": True, "provider": "cursor_agent",
        "binding_id": FIRST, "action": "fixture-open", "detail": "Fixture navigation completed",
    }

    def provider(selected, runner, **kwargs):
        assert_provider_locks_released(cfg)
        calls.append(selected["binding_id"])
        return provider_outcome

    def failed_save(doc, path):
        saves.append(path)
        if failure_stage == "after_replace":
            real_save(doc, path)
        raise OSError("private fixture locator must not reach the response")

    cfg.open_binding_fn = provider
    monkeypatch.setattr(sb, "save_bindings", failed_save)
    status, outcome = invoke(cfg, "open", {"binding_id": FIRST})
    assert status == 200
    assert {key: outcome[key] for key in provider_outcome if key != "detail"} == {
        key: value for key, value in provider_outcome.items() if key != "detail"
    }
    assert outcome["detail"] == (
        "Open completed; the verification timestamp update could not be confirmed. "
        "Do not repeat Open solely to update this timestamp."
    )
    assert provider_outcome["detail"] == "Fixture navigation completed"
    assert calls == [FIRST] and saves == [cfg.bindings_path]
    doc, problems = sb.load_bindings(cfg.bindings_path)
    assert not problems
    expected_stamp = VERIFIED if failure_stage == "after_replace" else None
    assert doc["bindings"] == [dict(original, last_verified_at=expected_stamp)]

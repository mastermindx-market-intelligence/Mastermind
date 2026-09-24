"""scripts.chairman_control_room — Chairman Control Room P0 Wave C server tests.

Falsifiers for the loopback-only local HTTP server: security gates (loopback/
Host/token/Origin), the closed static-asset allowlist, the binding-mutation
endpoints (``/api/open``/``/api/bind``/``/api/unbind``), the process-memory
live-active-builds cache (``/api/refresh-builds``, restart-forgets proof), the
zero-ownership discovery endpoint (``/api/discover``), and response headers
(CSP/no-store/nosniff).

Hermetic: the server always runs in-process on an OS-assigned ephemeral port
(``127.0.0.1:0``) against a throwaway ``tmp_path`` repo/macro root and a
throwaway bindings file. Every subprocess call the server itself dispatches
via ``config.runner`` is intercepted by an injected ``FakeRunner`` — no real
``osascript``/Chrome/``open``/build-map subprocess is ever spawned by this
suite through that seam. The one documented exception: the chatgpt discovery
endpoint's local ``ps`` liveness probe (``integrations.chairman_surfaces.
chatgpt._default_process_args_reader``, Sol architecture correction,
MAS-113, 2026-08-22) is a bounded, read-only, harmless local process-list
read with no seam threaded through ``ServerConfig`` (frozen spec scope); it
never matches this suite's fixture UUIDs, so its result is always
deterministic here.
"""
from __future__ import annotations

import contextlib
import http.client
import json
import shutil
import stat
import threading
import time
from pathlib import Path

import pytest

from control_plane import surface_bindings as sb
from integrations.chairman_surfaces import claude as claude_surface
from scripts import chairman_control_room as server_mod


# ---------------------------------------------------------------------------
# fake runner
# ---------------------------------------------------------------------------


class FakeRunner:
    """Records every call; returns canned responses in order, then a default."""

    def __init__(self, responses=None, default=None):
        self.calls: list[dict] = []
        self._responses = list(responses or [])
        self._default = default or {"code": 0, "stdout": "", "stderr": "", "timed_out": False}

    def __call__(self, argv, *, timeout: float = 20.0, cwd=None, max_bytes=None):
        self.calls.append({"argv": list(argv), "timeout": timeout, "cwd": cwd, "max_bytes": max_bytes})
        if self._responses:
            return self._responses.pop(0)
        return dict(self._default)


def _fixed_now(value: str):
    def _now() -> str:
        return value
    return _now


def _b5_server_doc(stamp="2026-09-05T00:00:00Z"):
    return server_mod.ccr.compose_control_room(
        inbox=None, boot_packet=None, active_builds=None, bindings=None,
        runtime_jobs=None, binding_problems=(), generated_at=stamp,
        agent_os_state={"schema": "agent_os_state.v1", "generated_at": "2026-09-03T00:00:01Z",
                        "workstreams": [{"key": "B5", "title": "Bounded source",
                                         "owner": "ceo-sol", "status": "active"}]},
    )


def _b5_sample(elapsed, *, wall_offset=0):
    # Exact fixture epoch for the reference above; no real host clock change.
    wall = 1788566400000 + elapsed - 1000 + wall_offset
    return [elapsed, wall, elapsed, wall]


def test_b5_cache_debits_gather_and_residence_without_changing_source_document(tmp_path, monkeypatch):
    config = _make_config(tmp_path)
    clock = _b5_sample(1000)
    config.validity_sample_fn = lambda: tuple(clock)
    original = _b5_server_doc()
    original_bytes = json.dumps(original, sort_keys=True)
    calls = []

    def compose(*args, **kwargs):
        calls.append("gather")
        clock[:] = _b5_sample(1200)
        return original

    monkeypatch.setattr(server_mod, "_compose_state_doc", compose)
    generation = server_mod._reserve_composition(config)
    server_mod._refresh_state_cache(config, timeout=240, generation=generation, include_capabilities=False)
    clock[:] = _b5_sample(1300)
    snapshot = server_mod._cached_state_snapshot(config)
    validity = snapshot.get("source_validity", {})
    assert validity.get("publication_seq") == generation
    assert validity["browser_qualification"] is None
    component = validity["cards"][0]["components"]["card"]
    assert component["remaining_ms"] == 684  #1000 - gather200 - residence100 - U16
    clock[:] = _b5_sample(1984)
    expired = server_mod._cached_state_snapshot(config)["source_validity"]["cards"][0]["components"]["card"]
    assert expired["remaining_ms"] == 0
    assert json.dumps(original, sort_keys=True) == original_bytes
    assert calls == ["gather"]


def test_b5_cached_publication_cannot_renew_same_proof_after_reference_rollback(tmp_path, monkeypatch):
    config = _make_config(tmp_path)
    clock = _b5_sample(1000)
    config.validity_sample_fn = lambda: tuple(clock)
    monkeypatch.setattr(server_mod, "_compose_state_doc", lambda *a, **k: _b5_server_doc())
    server_mod._refresh_state_cache(config, timeout=240, generation=server_mod._reserve_composition(config),
                                    include_capabilities=False)
    clock[:] = _b5_sample(2000)
    first = server_mod._cached_state_snapshot(config)
    assert first.get("source_validity", {}).get("cards")
    monkeypatch.setattr(server_mod, "_compose_state_doc", lambda *a, **k: _b5_server_doc("2026-09-04T23:59:50Z"))
    server_mod._refresh_state_cache(config, timeout=240, generation=server_mod._reserve_composition(config),
                                    include_capabilities=False)
    second = server_mod._cached_state_snapshot(config)
    assert second["source_validity"]["publication_seq"] > first["source_validity"]["publication_seq"]
    assert second["source_validity"]["cards"][0]["components"]["card"]["remaining_ms"] in (None, 0)


@pytest.mark.parametrize("elapsed, wall_offset, remaining", [
    (0, 0, 984), (983, 0, 1), (984, 0, 0), (1000, 0, 0),
    (100, 8, 884), (100, 9, None), (100, -8, 884), (100, -9, None),
    (1000, 60000, None), (61000, 0, 0),
])
def test_b5_paired_clock_contract_pays_full_reserve(tmp_path, elapsed, wall_offset, remaining):
    config = _make_config(tmp_path)
    anchor = tuple(_b5_sample(1000))
    bound = {"budget": 1000, "anchor": anchor, "previous": anchor,
             "clock_id": id(config.validity_sample_fn)}
    sample = tuple(_b5_sample(1000 + elapsed, wall_offset=wall_offset))
    assert server_mod._source_remaining(bound, sample, config) == remaining


@pytest.mark.parametrize("sample", [None, (0, 0, 2, 0), (0, 0, 0, 2),
    (True, 0, 1, 0), (0.0, 0, 0, 0), (0, "0", 0, 0),
    (0, 0, float("nan"), 0), (0, 0, float("inf"), 0),
    (-1, 0, 0, 0), (2**53, 0, 2**53, 0), (1, 0, 0, 0), (0, 1, 0, 0)])
def test_b5_invalid_clock_samples_refuse_without_coercion(sample):
    assert server_mod._valid_clock_sample(sample) is False


def test_b5_cumulative_discrepancy_and_poisoned_same_proof_do_not_reset(tmp_path):
    config = _make_config(tmp_path)
    anchor = tuple(_b5_sample(1000))
    bound = {"budget": 100000, "anchor": anchor, "previous": anchor,
             "clock_id": id(config.validity_sample_fn)}
    assert server_mod._source_remaining(bound, _b5_sample(1100, wall_offset=4), config) == 99884
    assert server_mod._source_remaining(bound, _b5_sample(1200, wall_offset=8), config) == 99784
    assert server_mod._source_remaining(bound, _b5_sample(1300, wall_offset=12), config) is None
    assert server_mod._source_remaining(bound, _b5_sample(1400), config) is None


def test_b5_legacy_cache_and_unsupported_server_clock_cannot_claim_currency(tmp_path, monkeypatch):
    config = _make_config(tmp_path)
    config.state_cache["doc"] = _b5_server_doc()
    assert server_mod._cached_state_snapshot(config)["source_validity"]["cards"] == []
    config.validity_sample_fn = lambda: None
    monkeypatch.setattr(server_mod, "_compose_state_doc", lambda *a, **k: _b5_server_doc())
    server_mod._refresh_state_cache(config, timeout=240, generation=server_mod._reserve_composition(config),
                                    include_capabilities=False)
    components = server_mod._cached_state_snapshot(config)["source_validity"]["cards"][0]["components"]
    assert all(c["remaining_ms"] is None for c in components.values())


def test_b5_contradictory_qualification_reference_is_unqualified(tmp_path, monkeypatch):
    config = _make_config(tmp_path)
    config.validity_sample_fn = lambda: tuple(_b5_sample(1000))
    monkeypatch.setattr(server_mod, "_compose_state_doc", lambda *a, **k: _b5_server_doc("2026-09-04T23:59:59Z"))
    server_mod._refresh_state_cache(config, timeout=240, generation=server_mod._reserve_composition(config),
                                    include_capabilities=False)
    components = server_mod._cached_state_snapshot(config)["source_validity"]["cards"][0]["components"]
    assert all(c["remaining_ms"] is None for c in components.values())


def _b5_navigation_fixture(tmp_path, monkeypatch):
    config = _make_config(tmp_path, now_value="2026-09-05T00:00:00Z")
    clock = _b5_sample(1000)
    config.validity_sample_fn = lambda: tuple(clock)
    binding = sb.new_binding(work_ref="WS:B5", role="ceo", provider="cursor_agent",
        locator_kind="cursor_agent_thread", locator={"chat_id": "b5-fake-only", "workspace_dir": None},
        observed_at="2026-09-05T00:00:00Z", last_verified_at=None,
        binding_id="55555555-5555-4555-8555-555555555555")
    bindings = {"schema": sb.SCHEMA, "bindings": [binding]}
    sb.save_bindings(bindings, config.bindings_path)
    doc = server_mod.ccr.compose_control_room(
        inbox={"schema": server_mod.ccr.EXECUTIVE_INBOX_SCHEMA, "generated_at": "2026-09-05T00:00:00Z",
               "attention": [{"attention_id": "ATTENTION-B5", "kind": "decision", "target": "ceo",
                              "reason": "Review the harmless fixture", "workstream": "WS:B5"}]},
        boot_packet=None, active_builds=None, bindings=bindings, binding_problems=(),
        runtime_jobs=[{"job_id": "JOB-B5", "root_job_id": "JOB-B5", "workstream": "WS:B5"}],
        generated_at="2026-09-05T00:00:00Z", agent_os_state={"schema": "agent_os_state.v1",
            "generated_at": "2026-09-03T00:00:01Z", "workstreams": [{"key": "B5", "title": "Bounded fixture",
                "owner": "ceo-sol", "status": "active"}]},
        dispatch_evidence=[{"responsibility_ref": "WS:B5", "root_job_id": "JOB-B5",
            "runtime_root_state": "RESOLVED", "carrier_state": "OWNER_HELD", "w3c_state": "RESOLVED",
            "w3c_terminal_state": "APPLIED", "w3c_wake_state": "TARGET_ACKNOWLEDGED",
            "w3c_terminal_applied": "true", "w3c_source_observed_at": "2026-09-05T00:00:00Z",
            "w3c_source_freshness": "SOURCE_EVIDENCE_TIME", "w3c_snapshot_digest": "a" * 64,
            "w3c_terminal_source_owner": "executive_terminal_return", "w3c_wake_source_owner": "wake_ledger"}],
    )
    owed = doc["autonomy"]["responsibilities"][0]["validity"]["owed_open_age"]
    assert owed["valid_for_ms"] == 1000  # actual mapper, no fabricated optimistic envelope
    monkeypatch.setattr(server_mod, "_compose_state_doc", lambda *a, **k: doc)
    return config, clock, binding


def _b5_owed_request(envelope):
    card = envelope["control_room"]["autonomy"]["responsibilities"][0]
    owed = card["validity"]["owed_open_age"]
    return {"binding_id": owed["binding_id"], "owed_context": {
        "schema": "mastermind.owed_navigation.v1", "publication_seq": envelope["source_validity"]["publication_seq"],
        "responsibility_ref": card["responsibility_ref"], "root_job_id": card["root_job_id"],
        "proof_ref": owed["proof_ref"], "binding_fingerprint": owed["binding_fingerprint"],
        "owed_seat": owed["owed_seat"]}}


@pytest.mark.parametrize("case", ["valid", "expired", "publication", "root", "proof", "binding", "seat", "missing"])
def test_b5_owed_handoff_requires_exact_current_context_and_never_persists(tmp_path, monkeypatch, case):
    config, clock, binding = _b5_navigation_fixture(tmp_path, monkeypatch)
    providers, saves = [], []
    def provider(checked, runner, **kwargs):
        providers.append(checked)
        assert checked == binding
        return {"ok": True, "verified": True, "action": "fake-only"}
    config.open_binding_fn = provider
    monkeypatch.setattr(sb, "save_bindings", lambda *a, **k: saves.append(a))
    with _running_server(config) as (_httpd, port):
        status, _, body = _get(port, "/api/state", headers=_auth_headers(config))
        assert status == 200
        request = _b5_owed_request(json.loads(body))
        if case == "expired": clock[:] = _b5_sample(1984)
        elif case == "publication": request["owed_context"]["publication_seq"] += 1
        elif case == "root": request["owed_context"]["root_job_id"] = "JOB-OTHER"
        elif case == "proof": request["owed_context"]["proof_ref"] = "b" * 64
        elif case == "binding": request["owed_context"]["binding_fingerprint"] = "c" * 64
        elif case == "seat": request["owed_context"]["owed_seat"] = "worker"
        elif case == "missing": del request["owed_context"]["proof_ref"]
        status, _, body = _post(port, "/api/open", request, headers=_auth_headers(config))
    assert status == (200 if case == "valid" else 409)
    assert len(providers) == (1 if case == "valid" else 0)
    assert saves == []


@pytest.mark.parametrize("movement", ["binding", "second_candidate", "expiry_during_read", "publication_during_read"])
def test_b5_final_handoff_rechecks_after_canonical_binding_read(tmp_path, monkeypatch, movement):
    config, clock, binding = _b5_navigation_fixture(tmp_path, monkeypatch)
    providers = []
    config.open_binding_fn = lambda *a, **k: providers.append(a) or {"ok": True, "verified": True}
    with _running_server(config) as (_httpd, port):
        _, _, body = _get(port, "/api/state", headers=_auth_headers(config))
        request = _b5_owed_request(json.loads(body))
        if movement == "second_candidate":
            sibling = dict(binding, binding_id="66666666-6666-4666-8666-666666666666",
                           locator={"chat_id": "second-target", "workspace_dir": None})
            sb.save_bindings({"schema": sb.SCHEMA, "bindings": [binding, sibling]}, config.bindings_path)
        elif movement == "binding":
            changed = dict(binding, locator={"chat_id": "different-target", "workspace_dir": None})
            sb.save_bindings({"schema": sb.SCHEMA, "bindings": [changed]}, config.bindings_path)
        else:
            original_read = sb.load_bindings
            def read(*args, **kwargs):
                result = original_read(*args, **kwargs)
                if movement == "expiry_during_read": clock[:] = _b5_sample(1984)
                else:
                    with config.state_lock: config.state_published_seq += 1
                return result
            monkeypatch.setattr(sb, "load_bindings", read)
        before = config.bindings_path.read_bytes()
        status, _, body = _post(port, "/api/open", request, headers=_auth_headers(config))
    assert status == 409
    assert providers == []
    assert config.bindings_path.read_bytes() == before


def test_b5_checked_target_is_immutable_and_verified_result_cannot_overwrite_new_binding(tmp_path, monkeypatch):
    config, clock, binding = _b5_navigation_fixture(tmp_path, monkeypatch)
    providers = []
    changed = dict(binding, locator={"chat_id": "concurrent-target", "workspace_dir": None})
    def provider(checked, runner, **kwargs):
        providers.append(checked)
        assert checked == binding
        with pytest.raises(TypeError): checked["role"] = "worker"
        with pytest.raises(TypeError): checked["locator"]["chat_id"] = "mutated"
        # No composition lock spans provider work.
        assert config.state_lock.acquire(blocking=False)
        config.state_lock.release()
        sb.save_bindings({"schema": sb.SCHEMA, "bindings": [changed]}, config.bindings_path)
        return {"ok": True, "verified": True, "action": "fake-only"}
    config.open_binding_fn = provider
    with _running_server(config) as (_httpd, port):
        _, _, body = _get(port, "/api/state", headers=_auth_headers(config))
        status, _, body = _post(port, "/api/open", _b5_owed_request(json.loads(body)), headers=_auth_headers(config))
    assert status == 200 and len(providers) == 1
    after, errors = sb.load_bindings(config.bindings_path)
    assert not errors and after["bindings"] == [changed]



@pytest.mark.parametrize("failure", ["expired", "clock_poison"])
@pytest.mark.parametrize("intervening", ["omitted", "different_proof"])
def test_b5_same_proof_never_renews_across_successful_publications(tmp_path, failure, intervening):
    config = _make_config(tmp_path)
    clock = _b5_sample(1000)
    config.validity_sample_fn = lambda: tuple(clock)
    original = _b5_server_doc()
    # Exercise the real cache owner with real mapper metadata. The rollback
    # is a deterministic fixture; neither host clock nor source files change.
    def publish(doc):
        server_mod._publish_source_validity(config, doc, tuple(clock), tuple(clock))
        config.state_cache["doc"] = doc
    publish(original)
    clock[:] = _b5_sample(2000, wall_offset=9 if failure == "clock_poison" else 0)
    first = server_mod._source_validity_snapshot(config, tuple(clock))["cards"][0]["components"]["card"]
    assert first["remaining_ms"] == (None if failure == "clock_poison" else 0)
    changed = json.loads(json.dumps(original))
    if intervening == "omitted":
        changed["autonomy"] = None
    else:
        for meta in changed["autonomy"]["responsibilities"][0]["validity"].values():
            meta["proof_ref"] = "b" * 64
    publish(changed)
    if intervening == "omitted":
        assert server_mod._source_validity_snapshot(config, tuple(clock))["cards"] == []
    clock[:] = _b5_sample(1000)
    publish(original)
    final = server_mod._source_validity_snapshot(config, tuple(clock))["cards"][0]["components"]["card"]
    assert final["proof_ref"] == first["proof_ref"]
    assert final["remaining_ms"] in (None, 0)


def test_b5_server_boots_with_optional_projection_absent():
    import os
    import subprocess
    import sys
    program = r"""
import importlib.abc, importlib.util, sys
blocked = "control_plane.autonomy_control_room_projection"
original = importlib.util.find_spec
importlib.util.find_spec = lambda name, *a, **k: None if name == blocked else original(name, *a, **k)
class Absent(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        if fullname == blocked:
            raise ModuleNotFoundError(fullname, name=fullname)
sys.meta_path.insert(0, Absent())
from scripts import chairman_control_room as server
assert server.ccr.autonomy_control_room_projection is None
config = server.ServerConfig(repo_root=server._REPO_ROOT, macro_root=server._REPO_ROOT,
                             bindings_path=server._REPO_ROOT / "absent-fixture.json", token="fixture",
                             origin="http://127.0.0.1:0", port=0)
server._publish_source_validity(config, {"autonomy": None}, None, None)
assert server._source_validity_snapshot(config, None)["cards"] == []
print("OPTIONAL_OWNER_UNAVAILABLE")
"""
    result = subprocess.run([sys.executable, "-c", program], cwd=server_mod._REPO_ROOT,
                            env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    assert "OPTIONAL_OWNER_UNAVAILABLE" in result.stdout

# ---------------------------------------------------------------------------
# server harness
# ---------------------------------------------------------------------------


def _make_config(
    tmp_path: Path,
    *,
    runner=None,
    now_value: str = "2026-08-22T00:00:00Z",
    live_cache=None,
    claude_projects_dir=None,
    codex_sessions_dir=None,
    mlx_profiles_root=None,
    gologin_profiles_root=None,
) -> "server_mod.ServerConfig":
    repo_root = tmp_path / "mastermind_repo"
    repo_root.mkdir(exist_ok=True)
    macro_root = tmp_path / "macro_repo"
    macro_root.mkdir(exist_ok=True)
    static_dir = tmp_path / "static"
    static_dir.mkdir(exist_ok=True)
    shutil.copy(
        Path(server_mod.DEFAULT_STATIC_DIR) / "index.html", static_dir / "index.html"
    )
    (static_dir / "control_room.js").write_text("/* test */", encoding="utf-8")
    (static_dir / "control_room.css").write_text("/* test */", encoding="utf-8")

    bindings_path = tmp_path / "bindings" / "surface_bindings.json"

    return server_mod.ServerConfig(
        repo_root=repo_root,
        macro_root=str(macro_root),
        bindings_path=bindings_path,
        token="test-token-abc123",
        origin="http://127.0.0.1:0",  # patched to the real bound port by _running_server
        port=0,
        static_dir=static_dir,
        runner=runner or FakeRunner(),
        now_fn=_fixed_now(now_value),
        live_cache=live_cache if live_cache is not None else {},
        claude_projects_dir=claude_projects_dir,
        codex_sessions_dir=codex_sessions_dir,
        mlx_profiles_root=mlx_profiles_root if mlx_profiles_root is not None else str(tmp_path / "empty_mlx"),
        gologin_profiles_root=gologin_profiles_root if gologin_profiles_root is not None else str(tmp_path / "empty_gologin"),
    )


@contextlib.contextmanager
def _running_server(config: "server_mod.ServerConfig"):
    httpd = server_mod.ControlRoomServer(("127.0.0.1", 0), server_mod.ChairmanControlRoomHandler, config)
    port = httpd.server_address[1]
    config.port = port
    config.origin = f"http://127.0.0.1:{port}"
    thread = threading.Thread(target=httpd.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    thread.start()
    try:
        yield httpd, port
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=10)


def _request(port: int, method: str, path: str, *, headers=None, body: bytes | None = None, host: str | None = None):
    # R3 (H0 hardening, 2026-08-22): 5 -> 30s. Measured server-suite socket
    # flake, 2/2 full-suite runs on the real host, different victim each
    # time, 0/2 in isolation — an environment-level accept/scheduling stall
    # across the suite's many short-lived ThreadingHTTPServer instances, not
    # a pinned slow code path. A cost-free cap when healthy; if a 30s cap
    # still trips, that is a real accept-stall product signal, not a flake.
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
    try:
        if host is not None:
            conn.putrequest(method, path, skip_host=True)
            conn.putheader("Host", host)
            for key, value in (headers or {}).items():
                conn.putheader(key, value)
            if body is not None:
                conn.putheader("Content-Length", str(len(body)))
            conn.endheaders(message_body=body)
        else:
            conn.request(method, path, body=body, headers=headers or {})
        resp = conn.getresponse()
        raw = resp.read()
        return resp.status, dict(resp.getheaders()), raw
    finally:
        conn.close()


def _get(port, path, **kw):
    return _request(port, "GET", path, **kw)


def _post(port, path, json_body=None, headers=None, **kw):
    data = json.dumps(json_body if json_body is not None else {}).encode("utf-8")
    hdrs = dict(headers or {})
    hdrs.setdefault("Content-Type", "application/json")
    return _request(port, "POST", path, headers=hdrs, body=data, **kw)


def _auth_headers(config, extra=None):
    headers = {"X-CCR-Token": config.token}
    if extra:
        headers.update(extra)
    return headers


def test_browser_resource_cannot_be_started_from_control_room_presentation_process(tmp_path):
    """Removing the OHF boundary must not recreate a Control Room launch API."""

    config = _make_config(tmp_path)
    with _running_server(config) as (_httpd, port):
        post_status, _headers, _body = _post(
            port, "/api/browser-review", {}, headers=_auth_headers(config)
        )
        get_status, _headers, _body = _get(
            port, "/api/browser-review", headers=_auth_headers(config)
        )

    assert post_status == 404
    assert get_status == 404


# ---------------------------------------------------------------------------
# 1. token / origin gates on POST
# ---------------------------------------------------------------------------


def test_post_open_without_token_is_403(tmp_path):
    config = _make_config(tmp_path)
    with _running_server(config) as (_httpd, port):
        status, _headers, body = _post(port, "/api/open", {"binding_id": "x"})
    assert status == 403
    assert json.loads(body)["error"] == "forbidden"


def test_post_open_with_wrong_token_is_403(tmp_path):
    config = _make_config(tmp_path)
    with _running_server(config) as (_httpd, port):
        status, _headers, _body = _post(port, "/api/open", {"binding_id": "x"}, headers={"X-CCR-Token": "not-the-token"})
    assert status == 403


def test_post_open_with_foreign_origin_and_correct_token_is_403(tmp_path):
    config = _make_config(tmp_path)
    with _running_server(config) as (_httpd, port):
        status, _headers, _body = _post(
            port, "/api/open", {"binding_id": "x"},
            headers=_auth_headers(config, {"Origin": "https://evil.example"}),
        )
    assert status == 403


def test_post_open_with_correct_token_and_matching_origin_is_not_forbidden(tmp_path):
    config = _make_config(tmp_path)
    with _running_server(config) as (_httpd, port):
        status, _headers, _body = _post(
            port, "/api/open", {"binding_id": "does-not-exist"},
            headers=_auth_headers(config, {"Origin": config.origin}),
        )
    # Reaches the handler (not a 403) — a missing binding is a 200 ok:false.
    assert status == 200


def test_token_is_a_browser_origin_nonce_not_local_process_auth(tmp_path):
    """H1 repair, Sol review 5000983751 Blocker 1: X-CCR-Token is a
    per-process browser-origin capability nonce (cross-site/CSRF defense),
    NOT local-process authentication. GET / is itself unauthenticated and
    is what delivers the nonce to the browser, so a same-user local process
    can retrieve it the same way — that adversary is deliberately outside
    this nonce's threat boundary. What it actually stops: a browser cannot
    forge the custom header cross-site, and this server offers no
    CORS/preflight path for a browser to ever be granted permission to.
    """
    config = _make_config(tmp_path)
    with _running_server(config) as (_httpd, port):
        status_root, headers_root, body_root = _get(port, "/")  # no token
        status_no_token, headers_no_token, _b1 = _get(port, "/api/state")  # no token
        status_wrong_origin, headers_wrong_origin, _b2 = _get(
            port, "/api/state", headers=_auth_headers(config, {"Origin": "http://evil.example"})
        )
        status_ok, headers_ok, body_ok = _get(port, "/api/state", headers=_auth_headers(config))

    # GET / is deliberately unauthenticated — a same-user local process CAN
    # retrieve the nonce this way, exactly as the browser does.
    assert status_root == 200
    assert config.token in body_root.decode("utf-8")

    # /api/state still enforces the nonce + Origin gate.
    assert status_no_token == 403
    assert status_wrong_origin == 403
    assert status_ok == 200

    # No CORS path exists anywhere on this server — not on the bootstrap
    # page, not on a forbidden response, not on an authenticated one.
    for headers in (headers_root, headers_no_token, headers_wrong_origin, headers_ok):
        assert not any(name.lower().startswith("access-control-") for name in headers), headers

    # The nonce is delivered only via the index page substitution — never
    # echoed back through an API response body.
    assert config.token not in body_ok.decode("utf-8")


# ---------------------------------------------------------------------------
# 2. Host header allowlist
# ---------------------------------------------------------------------------


def test_bad_host_header_is_403_even_on_get_root(tmp_path):
    config = _make_config(tmp_path)
    with _running_server(config) as (_httpd, port):
        status, _headers, _body = _get(port, "/", host="example.com")
    assert status == 403


def test_bad_host_header_with_port_mismatch_is_403(tmp_path):
    config = _make_config(tmp_path)
    with _running_server(config) as (_httpd, port):
        status, _headers, _body = _get(port, "/", host=f"127.0.0.1:{port + 1}")
    assert status == 403


def test_localhost_host_header_is_allowed(tmp_path):
    config = _make_config(tmp_path)
    with _running_server(config) as (_httpd, port):
        status, _headers, _body = _get(port, "/", host="localhost")
    assert status == 200


# ---------------------------------------------------------------------------
# 3. static allowlist / path traversal
# ---------------------------------------------------------------------------


def test_path_traversal_and_unknown_static_are_404(tmp_path):
    config = _make_config(tmp_path)
    # Sentinel file that exists on disk under static_dir but is NOT in the
    # closed asset map — proves the allowlist, not just a traversal probe.
    (config.static_dir / "secret.txt").write_text("TOP-SECRET-SENTINEL", encoding="utf-8")
    with _running_server(config) as (_httpd, port):
        status1, _h1, body1 = _get(port, "/static/../../etc/passwd")
        status2, _h2, _b2 = _get(port, "/static/unknown.js")
        status3, _h3, body3 = _get(port, "/static/secret.txt")
    assert status1 == 404
    assert b"root:" not in body1
    assert status2 == 404
    assert status3 == 404
    assert b"TOP-SECRET-SENTINEL" not in body3


def test_static_map_is_closed_and_literal():
    # Unit-level proof the allowlist is a fixed dict, not built from input.
    assert set(server_mod._STATIC_NAME_BY_PATH.values()) == {"index.html", "control_room.js", "control_room.css"}
    assert set(server_mod._STATIC_NAME_BY_PATH.keys()) == {"/", "/static/control_room.js", "/static/control_room.css"}


# ---------------------------------------------------------------------------
# 4. /api/open accepts ONLY binding_id
# ---------------------------------------------------------------------------


def test_open_rejects_unknown_top_level_keys(tmp_path):
    config = _make_config(tmp_path)
    with _running_server(config) as (_httpd, port):
        status, _headers, body = _post(
            port, "/api/open", {"binding_id": "x", "url": "https://evil.example"},
            headers=_auth_headers(config),
        )
    assert status == 400
    payload = json.loads(body)
    assert "url" in payload["detail"]


@pytest.mark.parametrize("bad_body", [{"binding_id": "x", "argv": ["rm", "-rf"]}, {"binding_id": "x", "path": "/etc"}])
def test_open_rejects_argv_and_path_keys(tmp_path, bad_body):
    config = _make_config(tmp_path)
    with _running_server(config) as (_httpd, port):
        status, _headers, _body = _post(port, "/api/open", bad_body, headers=_auth_headers(config))
    assert status == 400


# ---------------------------------------------------------------------------
# 5. unknown binding_id / tampered stored file
# ---------------------------------------------------------------------------


def test_open_unknown_binding_id_is_not_found(tmp_path):
    config = _make_config(tmp_path)
    with _running_server(config) as (_httpd, port):
        status, _headers, body = _post(port, "/api/open", {"binding_id": "nope"}, headers=_auth_headers(config))
    assert status == 200
    outcome = json.loads(body)
    assert outcome["ok"] is False
    assert outcome["failure_kind"] == "not_found"


def test_open_against_tampered_bindings_file_is_invalid_binding(tmp_path):
    config = _make_config(tmp_path)
    config.bindings_path.parent.mkdir(parents=True, exist_ok=True)
    tampered = {
        "schema": sb.SCHEMA,
        "bindings": [
            {
                "binding_id": "11111111-1111-4111-8111-111111111111",
                "work_ref": "WS:X",
                "role": "worker",
                "seat_ref": None,
                "provider": "codex",
                "locator_kind": "codex_session",
                "locator": {"session_id": "abc123"},
                "observed_at": "2026-08-22T00:00:00Z",
                "last_verified_at": None,
                "status": "done",  # forbidden lifecycle key smuggled in
            }
        ],
    }
    config.bindings_path.write_text(json.dumps(tampered), encoding="utf-8")

    with _running_server(config) as (_httpd, port):
        status, _headers, body = _post(
            port, "/api/open", {"binding_id": "11111111-1111-4111-8111-111111111111"},
            headers=_auth_headers(config),
        )
    assert status == 200
    outcome = json.loads(body)
    assert outcome["ok"] is False
    assert outcome["failure_kind"] == "invalid_binding"


# ---------------------------------------------------------------------------
# 6. /api/bind + /api/unbind
# ---------------------------------------------------------------------------


def test_bind_with_lifecycle_key_in_locator_is_rejected_with_named_problems(tmp_path):
    config = _make_config(tmp_path)
    body = {
        "work_ref": "WS:LIFECYCLE-TEST",
        "role": "worker",
        "provider": "codex",
        "locator": {"session_id": "sess-abc-123", "status": "done"},
    }
    with _running_server(config) as (_httpd, port):
        status, _headers, resp_body = _post(port, "/api/bind", body, headers=_auth_headers(config))
    assert status == 200
    payload = json.loads(resp_body)
    assert payload["ok"] is False
    assert any("status" in p and "forbidden" in p for p in payload["problems"])
    assert not config.bindings_path.exists()


def test_valid_bind_then_unbind_roundtrip(tmp_path):
    config = _make_config(tmp_path)
    body = {
        "work_ref": "WS:BIND-TEST",
        "role": "worker",
        "provider": "codex",
        "locator": {"session_id": "sess-abc-123"},
    }
    with _running_server(config) as (_httpd, port):
        status, _headers, resp_body = _post(port, "/api/bind", body, headers=_auth_headers(config))
        assert status == 200
        payload = json.loads(resp_body)
        assert payload["ok"] is True
        binding_id = payload["binding_id"]

        # file exists, mode 0600, parent mode 0700
        assert config.bindings_path.is_file()
        file_mode = stat.S_IMODE(config.bindings_path.stat().st_mode)
        assert file_mode == 0o600
        parent_mode = stat.S_IMODE(config.bindings_path.parent.stat().st_mode)
        assert parent_mode == 0o700

        # content is deterministic canonical form (round-trips byte-identically)
        raw = config.bindings_path.read_bytes()
        loaded = json.loads(raw)
        expected = (json.dumps(loaded, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")
        assert raw == expected

        status2, _headers2, unbind_body = _post(port, "/api/unbind", {"binding_id": binding_id}, headers=_auth_headers(config))
        assert status2 == 200
        assert json.loads(unbind_body)["ok"] is True

        doc, _problems = sb.load_bindings(config.bindings_path)
        assert doc["bindings"] == []


def test_chatgpt_bind_via_managed_env_fields_round_trips(tmp_path):
    """Sol architecture correction (MAS-113, 2026-08-22): a chatgpt bind body
    built from the new env_manager/folder_id/profile_id/url fields (the
    client-side form's shape) round-trips through the store, and the old
    ``browser_profile``/``chatgpt_url`` form is refused by schema validation."""
    config = _make_config(tmp_path)
    body = {
        "work_ref": "WS:CHATGPT-BIND-TEST",
        "role": "chairman",
        "provider": "chatgpt",
        "seat_ref": "chatgpt-seat-1",
        "locator": {
            "env_manager": "multilogin",
            "folder_id": "11111111-1111-4111-8111-111111111111",
            "profile_id": "22222222-2222-4222-8222-222222222222",
            "url": "https://chatgpt.com/c/abc123",
        },
    }
    with _running_server(config) as (_httpd, port):
        status, _headers, resp_body = _post(port, "/api/bind", body, headers=_auth_headers(config))
        assert status == 200
        payload = json.loads(resp_body)
        assert payload["ok"] is True

        doc, problems = sb.load_bindings(config.bindings_path)
        assert problems == []
        bound = doc["bindings"][0]
        assert bound["provider"] == "chatgpt"
        assert bound["locator_kind"] == "chatgpt_managed_env"
        assert bound["locator"] == body["locator"]


def test_chatgpt_bind_old_browser_profile_form_rejected(tmp_path):
    config = _make_config(tmp_path)
    body = {
        "work_ref": "WS:CHATGPT-OLD-FORM",
        "role": "worker",
        "provider": "chatgpt",
        "seat_ref": "chatgpt-seat-1",
        "locator": {"browser_profile": "Default", "url": "https://chatgpt.com/c/abc123"},
    }
    with _running_server(config) as (_httpd, port):
        status, _headers, resp_body = _post(port, "/api/bind", body, headers=_auth_headers(config))
    assert status == 200
    payload = json.loads(resp_body)
    assert payload["ok"] is False
    assert any("browser_profile" in p for p in payload["problems"])
    assert not config.bindings_path.exists()


def test_unbind_unknown_binding_id_is_ok_false(tmp_path):
    config = _make_config(tmp_path)
    with _running_server(config) as (_httpd, port):
        status, _headers, body = _post(port, "/api/unbind", {"binding_id": "nope"}, headers=_auth_headers(config))
    assert status == 200
    assert json.loads(body)["ok"] is False


# ---------------------------------------------------------------------------
# 7. GET /api/state — zero writes, schema, capabilities
# ---------------------------------------------------------------------------


def _snapshot_tree(root: Path) -> set:
    if not root.exists():
        return set()
    return {str(p) for p in root.rglob("*")}


def test_get_state_performs_zero_filesystem_writes(tmp_path):
    config = _make_config(tmp_path)
    before_repo = _snapshot_tree(config.repo_root)
    before_macro = _snapshot_tree(Path(config.macro_root))
    before_bindings = _snapshot_tree(config.bindings_path.parent.parent)

    with _running_server(config) as (_httpd, port):
        status, headers, body = _get(port, "/api/state", headers=_auth_headers(config))

    after_repo = _snapshot_tree(config.repo_root)
    after_macro = _snapshot_tree(Path(config.macro_root))
    after_bindings = _snapshot_tree(config.bindings_path.parent.parent)

    assert status == 200
    assert before_repo == after_repo
    assert before_macro == after_macro
    assert before_bindings == after_bindings

    payload = json.loads(body)
    assert payload["control_room"]["schema"] == "mastermind.chairman_control_room.v1"
    assert "capabilities" in payload
    assert set(payload["capabilities"].keys()) >= {"chatgpt", "claude_code", "claude_desktop", "cursor_agent", "codex", "aionui"}
    assert payload["live_builds_active"] is False


# ---------------------------------------------------------------------------
# 8 / 9. /api/refresh-builds — live cache + restart-forgets + failure path
# ---------------------------------------------------------------------------


_STUB_FIXTURE_DOC = {
    "schema": "project_active_builds.v1",
    "collected_at": "2026-08-22T01:23:00Z",
    "repositories": [],
}


def _write_stub_build_script(macro_root: Path) -> None:
    scripts_dir = macro_root / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    # Content is irrelevant to these tests — the FakeRunner intercepts the
    # actual execution — but the file must EXIST for the endpoint's
    # script_path.is_file() gate to proceed past the "seam not present" refusal.
    (scripts_dir / "build_project_active_build_map.py").write_text(
        "# stub for tests; never actually executed (FakeRunner intercepts)\n",
        encoding="utf-8",
    )


def _build_large_active_builds_doc(min_bytes: int) -> dict:
    """A synthetic ``project_active_builds.v1`` doc padded past ``min_bytes``.

    Regression fixture for the Wave D live-proof defect: the real document
    was measured at 112,569 bytes (well over the old fixed 64 KiB runner
    cap). Padded with many synthetic PR rows rather than one huge field, so
    it exercises the same shape real repositories/open_prs data has.
    """
    pr_rows: list[dict] = []
    i = 0
    while True:
        doc = {
            "schema": "project_active_builds.v1",
            "collected_at": "2026-08-22T02:00:00Z",
            "repositories": [
                {"repo": "example-org/synthetic-repo", "open_prs": pr_rows}
            ],
        }
        if len(json.dumps(doc).encode("utf-8")) >= min_bytes:
            return doc
        pr_rows.append({
            "repo": "example-org/synthetic-repo",
            "number": 6000 + i,
            "url": f"https://github.com/example-org/synthetic-repo/pull/{6000 + i}",
            "title": f"padding row {i} " + ("x" * 80),
            "branch": f"branch-{i}",
            "draft": False,
            "merge_state": "clean",
        })
        i += 1


def _write_large_doc_build_script(macro_root: Path, doc: dict) -> None:
    """A REAL stub script (actually executed, not intercepted by a fake
    runner) that prints ``doc`` to stdout on ``--json-stdout`` — the exact
    shape of the real Wave D defect (subprocess stdout, not a canned dict).
    """
    scripts_dir = macro_root / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(doc)
    (scripts_dir / "build_project_active_build_map.py").write_text(
        "import sys\n"
        f"DOC = {payload!r}\n"
        "if '--json-stdout' in sys.argv:\n"
        "    sys.stdout.write(DOC)\n"
        "    sys.exit(0)\n"
        "sys.exit(2)\n",
        encoding="utf-8",
    )


def test_default_runner_cwd_branch_does_not_truncate_below_max_bytes(tmp_path):
    """Unit-level proof of the fix: the REAL subprocess path (not a fake)
    must not truncate a >64 KiB document when max_bytes widens the cap.
    """
    big_doc = _build_large_active_builds_doc(70_000)
    assert len(json.dumps(big_doc).encode("utf-8")) > 65536

    macro_root = tmp_path / "macro_big_unit"
    _write_large_doc_build_script(macro_root, big_doc)

    argv = [server_mod.sys.executable, str(macro_root / "scripts" / "build_project_active_build_map.py"), "--json-stdout"]
    result = server_mod.default_runner(
        argv, timeout=30, cwd=str(macro_root), max_bytes=server_mod._REFRESH_BUILDS_MAX_OUTPUT_BYTES
    )

    assert result["code"] == 0
    assert result["timed_out"] is False
    parsed = json.loads(result["stdout"])
    assert parsed["schema"] == "project_active_builds.v1"
    assert len(parsed["repositories"][0]["open_prs"]) == len(big_doc["repositories"][0]["open_prs"])


def test_default_runner_cwd_branch_still_honors_an_explicit_smaller_cap(tmp_path):
    # Proves the cap is a real, honored parameter — not just "big enough now".
    macro_root = tmp_path / "macro_tiny_cap"
    scripts_dir = macro_root / "scripts"
    scripts_dir.mkdir(parents=True)
    (scripts_dir / "build_project_active_build_map.py").write_text(
        "import sys\nsys.stdout.write('A' * 1000)\nsys.exit(0)\n", encoding="utf-8",
    )
    argv = [server_mod.sys.executable, str(scripts_dir / "build_project_active_build_map.py"), "--json-stdout"]
    result = server_mod.default_runner(argv, timeout=10, cwd=str(macro_root), max_bytes=100)
    assert len(result["stdout"].encode("utf-8")) <= 100


def test_refresh_builds_end_to_end_large_document_is_not_truncated(tmp_path):
    """Full HTTP round trip through the REAL subprocess runner (default_runner,
    not FakeRunner) reproducing the exact Wave D live-proof defect shape:
    a >64 KiB ``project_active_builds.v1`` document on a real subprocess's
    stdout must reach /api/state intact, not fail with "stdout was not
    valid JSON".
    """
    big_doc = _build_large_active_builds_doc(70_000)
    config = _make_config(tmp_path, runner=server_mod.default_runner)
    _write_large_doc_build_script(Path(config.macro_root), big_doc)

    with _running_server(config) as (_httpd, port):
        status, _headers, body = _post(port, "/api/refresh-builds", {}, headers=_auth_headers(config))
        assert status == 200
        payload = json.loads(body)
        assert payload["ok"] is True
        assert payload["collected_at"] == big_doc["collected_at"]

        status2, _headers2, body2 = _get(port, "/api/state", headers=_auth_headers(config))
    state_payload = json.loads(body2)
    assert state_payload["live_builds_active"] is True
    assert state_payload["control_room"]["sources"]["active_builds_collected_at"] == big_doc["collected_at"]


def test_refresh_builds_truncated_or_invalid_stdout_fails_closed(tmp_path):
    """A truncated/invalid stdout (code 0, but not parseable JSON — what the
    OLD 64 KiB cap silently produced from a real 112,569-byte document) must
    still refuse closed with ok:false, never crash, never poison the cache.
    """
    truncated = json.dumps(_STUB_FIXTURE_DOC)[:20]  # deliberately cut mid-object
    runner = FakeRunner(responses=[{"code": 0, "stdout": truncated, "stderr": "", "timed_out": False}])
    config = _make_config(tmp_path, runner=runner)
    _write_stub_build_script(Path(config.macro_root))

    with _running_server(config) as (_httpd, port):
        status, _headers, body = _post(port, "/api/refresh-builds", {}, headers=_auth_headers(config))
    assert status == 200
    payload = json.loads(body)
    assert payload["ok"] is False
    assert "not valid JSON" in payload["detail"]
    assert config.live_cache.get("active_builds") is None


def test_refresh_builds_happy_path_sets_live_cache_and_restart_forgets_it(tmp_path):
    runner = FakeRunner(responses=[
        {"code": 0, "stdout": json.dumps(_STUB_FIXTURE_DOC), "stderr": "", "timed_out": False},
    ])
    config = _make_config(tmp_path, runner=runner)
    _write_stub_build_script(Path(config.macro_root))

    with _running_server(config) as (_httpd, port):
        status, _headers, body = _post(port, "/api/refresh-builds", {}, headers=_auth_headers(config))
        assert status == 200
        payload = json.loads(body)
        assert payload["ok"] is True
        assert payload["collected_at"] == "2026-08-22T01:23:00Z"

        # the argv/cwd contract from the frozen spec
        call = runner.calls[0]
        assert call["argv"][0] == server_mod.sys.executable
        assert call["argv"][-1] == "--json-stdout"
        assert call["cwd"] == config.macro_root
        assert call["timeout"] == server_mod._REFRESH_BUILDS_TIMEOUT
        assert call["max_bytes"] == server_mod._REFRESH_BUILDS_MAX_OUTPUT_BYTES

        status2, _headers2, body2 = _get(port, "/api/state", headers=_auth_headers(config))
        payload2 = json.loads(body2)
        assert payload2["live_builds_active"] is True
        assert payload2["control_room"]["sources"]["active_builds_collected_at"] == "2026-08-22T01:23:00Z"

    # NEW server instance (fresh ServerConfig -> fresh process-memory live_cache)
    fresh_config = _make_config(tmp_path, runner=FakeRunner())
    with _running_server(fresh_config) as (_httpd2, port2):
        status3, _headers3, body3 = _get(port2, "/api/state", headers=_auth_headers(fresh_config))
    payload3 = json.loads(body3)
    assert payload3["live_builds_active"] is False


def test_refresh_builds_failure_reports_stderr_tail_never_stdout_and_leaves_state_unchanged(tmp_path):
    runner = FakeRunner(responses=[
        {"code": 2, "stdout": "SECRET-STDOUT-SHOULD-NEVER-APPEAR", "stderr": "boom: compiler exploded", "timed_out": False},
    ])
    config = _make_config(tmp_path, runner=runner)
    _write_stub_build_script(Path(config.macro_root))

    with _running_server(config) as (_httpd, port):
        status, _headers, body = _post(port, "/api/refresh-builds", {}, headers=_auth_headers(config))
        assert status == 200
        payload = json.loads(body)
        assert payload["ok"] is False
        assert "boom: compiler exploded" in payload["detail"]
        assert "SECRET-STDOUT-SHOULD-NEVER-APPEAR" not in payload["detail"]

        status2, _headers2, body2 = _get(port, "/api/state", headers=_auth_headers(config))
        payload2 = json.loads(body2)
        assert payload2["live_builds_active"] is False


def test_refresh_builds_failure_after_success_does_not_clear_existing_live_cache(tmp_path):
    runner = FakeRunner(responses=[
        {"code": 0, "stdout": json.dumps(_STUB_FIXTURE_DOC), "stderr": "", "timed_out": False},
        {"code": 1, "stdout": "", "stderr": "second attempt failed", "timed_out": False},
    ])
    config = _make_config(tmp_path, runner=runner)
    _write_stub_build_script(Path(config.macro_root))

    with _running_server(config) as (_httpd, port):
        status1, _h1, _b1 = _post(port, "/api/refresh-builds", {}, headers=_auth_headers(config))
        assert status1 == 200
        status2, _h2, body2 = _post(port, "/api/refresh-builds", {}, headers=_auth_headers(config))
        assert status2 == 200
        assert json.loads(body2)["ok"] is False

        assert config.live_cache["active_builds"]["collected_at"] == "2026-08-22T01:23:00Z"


def test_refresh_builds_missing_seam_reports_named_detail(tmp_path):
    config = _make_config(tmp_path)  # no stub script written
    with _running_server(config) as (_httpd, port):
        status, _headers, body = _post(port, "/api/refresh-builds", {}, headers=_auth_headers(config))
    assert status == 200
    payload = json.loads(body)
    assert payload["ok"] is False
    assert "seam not present" in payload["detail"]


def test_refresh_builds_rejects_unknown_body_keys(tmp_path):
    config = _make_config(tmp_path)
    with _running_server(config) as (_httpd, port):
        status, _headers, _body = _post(port, "/api/refresh-builds", {"force": True}, headers=_auth_headers(config))
    assert status == 400


# ---------------------------------------------------------------------------
# 10. /api/discover — chatgpt managed-environment identities, zero writes,
#     cursor unsupported (Sol architecture correction, MAS-113, 2026-08-22)
# ---------------------------------------------------------------------------


def test_discover_reports_chatgpt_environments_from_injected_roots_and_writes_nothing(tmp_path):
    gologin_id = "aaaaaaaaaaaaaaaaaaaaaaaa"
    workspace_id = "99999999-9999-4999-8999-999999999999"
    folder_id = "11111111-1111-4111-8111-111111111111"
    profile_id = "22222222-2222-4222-8222-222222222222"

    mlx_root = tmp_path / "mlx"
    gologin_root = tmp_path / "gologin"
    (mlx_root / workspace_id / folder_id / profile_id).mkdir(parents=True)
    (gologin_root / gologin_id).mkdir(parents=True)

    runner = FakeRunner(responses=[{"code": 0, "stdout": "", "stderr": "", "timed_out": False}])
    config = _make_config(tmp_path, runner=runner, mlx_profiles_root=str(mlx_root), gologin_profiles_root=str(gologin_root))

    before = _snapshot_tree(tmp_path)
    with _running_server(config) as (_httpd, port):
        status, _headers, body = _get(port, "/api/discover", headers=_auth_headers(config))
    after = _snapshot_tree(tmp_path)

    assert status == 200
    payload = json.loads(body)
    envs = payload["chatgpt_environments"]
    assert envs["gologin"] == [{"profile_id": gologin_id, "running": False}]
    assert envs["multilogin"] == [
        {"workspace_id": workspace_id, "folder_id": folder_id, "profile_id": profile_id, "running": False}
    ]
    assert payload["cursor"] == {"supported": False, "note": payload["cursor"]["note"]}
    assert payload["cursor"]["supported"] is False
    assert isinstance(payload["claude_code_sessions"], list)
    assert isinstance(payload["codex_sessions"], list)
    # bindings-file writes excluded (never touched by discover); repo/macro/
    # mlx/gologin trees must be byte-for-byte unchanged (read-only stat only).
    assert before == after


def test_discover_no_chatgpt_key_carries_chrome_vocabulary(tmp_path):
    config = _make_config(tmp_path)
    with _running_server(config) as (_httpd, port):
        status, _headers, body = _get(port, "/api/discover", headers=_auth_headers(config))
    assert status == 200
    payload = json.loads(body)
    assert "chatgpt_tabs" not in payload
    assert "chatgpt_profiles" not in payload
    assert set(payload["chatgpt_environments"].keys()) == {"multilogin", "gologin"}
    assert payload["chatgpt_environments"] == {"multilogin": [], "gologin": []}


# ---------------------------------------------------------------------------
# 11. last_verified_at / VERIFIED_OPENABLE law (Sol review 5000169412,
#     blocker 2): the stamp advances ONLY on ok=True AND verified=True.
# ---------------------------------------------------------------------------


def test_open_ok_but_unverified_leaves_bindings_file_byte_unchanged(tmp_path):
    """(a) ok=True, verified=False (cursor_agent — no proven local store) ->
    the bindings file on disk is byte-for-byte unchanged; last_verified_at
    stays None."""
    binding_id = "22222222-2222-4222-8222-222222222222"
    doc = {
        "schema": sb.SCHEMA,
        "bindings": [
            sb.new_binding(
                work_ref="WS:OPEN-TEST",
                role="worker",
                provider="cursor_agent",
                locator_kind="cursor_agent_thread",
                locator={"chat_id": "chat-abc123", "workspace_dir": None},
                observed_at="2026-08-22T00:00:00Z",
                last_verified_at=None,
                binding_id=binding_id,
            )
        ],
    }
    config = _make_config(tmp_path, now_value="2026-08-22T05:00:00Z")
    sb.save_bindings(doc, config.bindings_path)
    before_bytes = config.bindings_path.read_bytes()

    runner = FakeRunner(responses=[{"code": 0, "stdout": "", "stderr": "", "timed_out": False}])
    config.runner = runner

    with _running_server(config) as (_httpd, port):
        status, _headers, body = _post(port, "/api/open", {"binding_id": binding_id}, headers=_auth_headers(config))
    assert status == 200
    outcome = json.loads(body)
    assert outcome["ok"] is True
    assert outcome["verified"] is False

    after_bytes = config.bindings_path.read_bytes()
    assert after_bytes == before_bytes, "an unverified open must never write the bindings file"

    after_doc, _problems = sb.load_bindings(config.bindings_path)
    assert after_doc["bindings"][0]["last_verified_at"] is None


def test_open_ok_and_verified_advances_last_verified_at(tmp_path):
    """(b) ok=True, verified=True (claude_code with a fixture transcript
    present in a tmp claude_projects_dir) -> the stamp advances to the
    injected now_fn value; every other field is unchanged."""
    binding_id = "33333333-3333-4333-8333-333333333333"
    project_dir = str(tmp_path / "project")
    Path(project_dir).mkdir()
    session_id = "44444444-4444-4444-8444-444444444444"
    claude_projects_dir = tmp_path / "claude_store"
    project_slug = claude_surface._slugify_project_dir(project_dir)
    (claude_projects_dir / project_slug).mkdir(parents=True)
    (claude_projects_dir / project_slug / f"{session_id}.jsonl").write_text("", encoding="utf-8")

    doc = {
        "schema": sb.SCHEMA,
        "bindings": [
            sb.new_binding(
                work_ref="WS:OPEN-TEST",
                role="worker",
                provider="claude_code",
                locator_kind="claude_code_session",
                locator={"project_dir": project_dir, "session_id": session_id},
                observed_at="2026-08-22T00:00:00Z",
                last_verified_at=None,
                binding_id=binding_id,
            )
        ],
    }
    config = _make_config(
        tmp_path, now_value="2026-08-22T05:00:00Z", claude_projects_dir=str(claude_projects_dir),
    )
    sb.save_bindings(doc, config.bindings_path)
    before_doc, _problems = sb.load_bindings(config.bindings_path)
    before_binding = before_doc["bindings"][0]

    runner = FakeRunner(responses=[{"code": 0, "stdout": "", "stderr": "", "timed_out": False}])
    config.runner = runner

    with _running_server(config) as (_httpd, port):
        status, _headers, body = _post(port, "/api/open", {"binding_id": binding_id}, headers=_auth_headers(config))
    assert status == 200
    outcome = json.loads(body)
    assert outcome["ok"] is True
    assert outcome["verified"] is True

    after_doc, _problems2 = sb.load_bindings(config.bindings_path)
    after_binding = after_doc["bindings"][0]

    assert after_binding["last_verified_at"] == "2026-08-22T05:00:00Z"
    for key in before_binding:
        if key == "last_verified_at":
            continue
        assert after_binding[key] == before_binding[key], key


def test_open_valid_shaped_nonexistent_codex_session_not_found_file_unchanged(tmp_path):
    """(c) a valid-shaped but nonexistent codex session id -> 200,
    ok:false, failure_kind not_found; the bindings file is byte-unchanged."""
    binding_id = "55555555-5555-4555-8555-555555555555"
    doc = {
        "schema": sb.SCHEMA,
        "bindings": [
            sb.new_binding(
                work_ref="WS:OPEN-TEST",
                role="worker",
                provider="codex",
                locator_kind="codex_session",
                locator={"session_id": "well-formed-but-absent", "cwd": None},
                observed_at="2026-08-22T00:00:00Z",
                last_verified_at=None,
                binding_id=binding_id,
            )
        ],
    }
    codex_sessions_dir = tmp_path / "codex_store"
    codex_sessions_dir.mkdir()  # store exists, but no matching transcript
    config = _make_config(
        tmp_path, now_value="2026-08-22T05:00:00Z", codex_sessions_dir=str(codex_sessions_dir),
    )
    sb.save_bindings(doc, config.bindings_path)
    before_bytes = config.bindings_path.read_bytes()

    # Even a runner primed to ACK the Terminal launch must never be reached.
    runner = FakeRunner(responses=[{"code": 0, "stdout": "", "stderr": "", "timed_out": False}])
    config.runner = runner

    with _running_server(config) as (_httpd, port):
        status, _headers, body = _post(port, "/api/open", {"binding_id": binding_id}, headers=_auth_headers(config))
    assert status == 200
    outcome = json.loads(body)
    assert outcome["ok"] is False
    assert outcome["failure_kind"] == "not_found"
    assert runner.calls == []

    after_bytes = config.bindings_path.read_bytes()
    assert after_bytes == before_bytes


def test_open_chatgpt_binding_returns_refusal_and_leaves_bindings_file_byte_identical(tmp_path):
    """(d) Sol architecture correction (MAS-113, 2026-08-22): a chatgpt
    binding's managed environment is absent from the injected (empty) local
    stores -> 200, ok:false, failure_kind not_found, verified:false; the
    bindings file is byte-unchanged (the ``last_verified_at`` stamp law) and
    the navigation runner is never invoked."""
    binding_id = "66666666-6666-4666-8666-666666666666"
    doc = {
        "schema": sb.SCHEMA,
        "bindings": [
            sb.new_binding(
                work_ref="WS:OPEN-TEST",
                role="worker",
                provider="chatgpt",
                locator_kind="chatgpt_managed_env",
                locator={
                    "env_manager": "gologin",
                    "profile_id": "aaaaaaaaaaaaaaaaaaaaaaaa",
                    "url": "https://chatgpt.com/c/abc123",
                },
                observed_at="2026-08-22T00:00:00Z",
                last_verified_at=None,
                seat_ref="chatgpt-seat-1",
                binding_id=binding_id,
            )
        ],
    }
    # _make_config's default mlx_profiles_root/gologin_profiles_root point at
    # empty tmp directories, so env_exists is False and env_running (the one
    # path that would probe /bin/ps) is never even reached.
    config = _make_config(tmp_path, now_value="2026-08-22T05:00:00Z")
    sb.save_bindings(doc, config.bindings_path)
    before_bytes = config.bindings_path.read_bytes()

    runner = FakeRunner(responses=[{"code": 0, "stdout": "", "stderr": "", "timed_out": False}])
    config.runner = runner

    with _running_server(config) as (_httpd, port):
        status, _headers, body = _post(port, "/api/open", {"binding_id": binding_id}, headers=_auth_headers(config))
    assert status == 200
    outcome = json.loads(body)
    assert outcome["ok"] is False
    assert outcome["failure_kind"] == "not_found"
    assert outcome["verified"] is False
    assert runner.calls == []

    after_bytes = config.bindings_path.read_bytes()
    assert after_bytes == before_bytes


# ---------------------------------------------------------------------------
# 12. CSP + no-store + nosniff headers
# ---------------------------------------------------------------------------


def test_headers_on_root_and_state(tmp_path):
    config = _make_config(tmp_path)
    with _running_server(config) as (_httpd, port):
        status_root, headers_root, _b1 = _get(port, "/")
        status_state, headers_state, _b2 = _get(port, "/api/state", headers=_auth_headers(config))

    assert status_root == 200
    assert headers_root.get("Content-Security-Policy") == server_mod._CSP
    assert headers_root.get("X-Content-Type-Options") == "nosniff"

    assert status_state == 200
    assert headers_state.get("Cache-Control") == "no-store"
    assert headers_state.get("X-Content-Type-Options") == "nosniff"


def test_index_html_injects_token_and_removes_placeholder(tmp_path):
    config = _make_config(tmp_path)
    with _running_server(config) as (_httpd, port):
        status, _headers, body = _get(port, "/")
    assert status == 200
    text = body.decode("utf-8")
    assert "__CCR_TOKEN__" not in text
    assert config.token in text


# ---------------------------------------------------------------------------
# 13. H0 hardening (2026-08-22) — cached, single-flight state composition
#     (R1/R2), token-gated read GETs (R5), compose-timeout threading (R2),
#     and the R6 max_bytes seam-hygiene fix.
#
#     capability.census is deliberately excluded from the mandatory
#     constructor-time pre-compose (see _ensure_capabilities_cached's
#     docstring) — it is the only composition step touching config.runner,
#     and every _running_server-based test in this suite (whether or not it
#     ever calls /api/state) constructs a server. These new tests therefore
#     assert against the DOC composer (_compose_state_doc), not against
#     capability.census, unless a test is specifically about capabilities.
# ---------------------------------------------------------------------------


def test_state_served_from_cache_two_gets_within_ttl_invoke_composition_once(tmp_path, monkeypatch):
    calls: list[float] = []

    def fake_compose(config, *, timeout=60.0):
        calls.append(timeout)
        return {"marker": "cached-doc"}

    monkeypatch.setattr(server_mod, "_compose_state_doc", fake_compose)
    config = _make_config(tmp_path, now_value="2026-08-22T00:00:00Z")

    with _running_server(config) as (_httpd, port):
        assert len(calls) == 1  # startup pre-compose only, before any request
        status1, _h1, body1 = _get(port, "/api/state", headers=_auth_headers(config))
        status2, _h2, body2 = _get(port, "/api/state", headers=_auth_headers(config))

    assert status1 == 200 and status2 == 200
    assert len(calls) == 1  # neither GET (well within the default 120s TTL) recomposed
    payload1 = json.loads(body1)
    payload2 = json.loads(body2)
    assert payload1["control_room"]["marker"] == "cached-doc"
    assert payload1["composed_at"] == payload2["composed_at"] == "2026-08-22T00:00:00Z"


def test_single_flight_background_refresh_serves_stale_doc_promptly(tmp_path, monkeypatch):
    monkeypatch.setattr(server_mod.capability, "census", lambda **_kw: {})
    call_count = {"n": 0}
    count_lock = threading.Lock()
    entered_slow_call = threading.Event()
    release_slow_call = threading.Event()

    def fake_compose(config, *, timeout=60.0):
        with count_lock:
            call_count["n"] += 1
            n = call_count["n"]
        if n == 1:
            return {"marker": "startup-doc"}
        # The ONE single-flight background recompose the stale (TTL=0)
        # cache should trigger — deliberately slow, released by the test.
        entered_slow_call.set()
        release_slow_call.wait(timeout=5)
        return {"marker": "refreshed-doc"}

    monkeypatch.setattr(server_mod, "_compose_state_doc", fake_compose)
    config = _make_config(tmp_path)
    config.state_ttl = 0.0  # cache is stale the instant it is read

    with _running_server(config) as (_httpd, port):
        results: list[tuple[int, dict, bytes]] = []
        results_lock = threading.Lock()

        def do_get() -> None:
            r = _get(port, "/api/state", headers=_auth_headers(config))
            with results_lock:
                results.append(r)

        threads = [threading.Thread(target=do_get) for _ in range(6)]
        for t in threads:
            t.start()

        assert entered_slow_call.wait(timeout=5), "background recompose never started"
        # Every concurrent request must return promptly with the OLD doc
        # while the one recompose is still in flight — none of them block
        # on the slow composer themselves.
        for t in threads:
            t.join(timeout=5)
            assert not t.is_alive()

        for status, _headers, body in results:
            assert status == 200
            payload = json.loads(body)
            assert payload["control_room"]["marker"] == "startup-doc"
            assert payload["refresh_in_flight"] is True

        release_slow_call.set()
        # Poll the CONFIG directly (no further HTTP requests) — with TTL=0
        # every GET is itself a stale read that would kick ANOTHER
        # background refresh, which would make "exactly one recompose ran"
        # unobservable from outside. Reading the bookkeeping fields directly
        # has no such side effect.
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and config.state_refreshes_in_flight:
            time.sleep(0.02)

    assert config.state_refreshes_in_flight == 0
    assert config.state_cache.get("doc") == {"marker": "refreshed-doc"}
    # Exactly one background recompose ran, no matter how many concurrent
    # stale GETs asked for one (single-flight — F5).
    assert call_count["n"] == 2


def test_failed_background_refresh_keeps_last_good_doc_then_a_later_success_clears_the_error(tmp_path, monkeypatch):
    monkeypatch.setattr(server_mod.capability, "census", lambda **_kw: {})
    calls = {"n": 0}
    # Gates recompose #3 (the recovery attempt) so the "failed once, not yet
    # retried" state can be observed deterministically before it clears —
    # with TTL=0 every GET is itself a stale read that kicks another
    # background refresh, so an ungated recovery call can land before the
    # test ever gets to assert the intermediate state.
    allow_recovery = threading.Event()

    def fake_compose(config, *, timeout=60.0):
        calls["n"] += 1
        n = calls["n"]
        if n == 1:
            return {"marker": "doc-1"}
        if n == 2:
            raise RuntimeError("synthetic recompose failure")
        allow_recovery.wait(timeout=5)
        return {"marker": "doc-3"}

    monkeypatch.setattr(server_mod, "_compose_state_doc", fake_compose)
    config = _make_config(tmp_path)
    config.state_ttl = 0.0  # every GET below is against a stale cache

    with _running_server(config) as (_httpd, port):
        # Served from the startup doc (doc-1, call #1); kicks the first
        # (failing) background recompose (call #2).
        status1, _h1, body1 = _get(port, "/api/state", headers=_auth_headers(config))
        assert status1 == 200
        assert json.loads(body1)["control_room"]["marker"] == "doc-1"

        # Poll the CONFIG directly (no HTTP — see the single-flight test's
        # comment for why) until that background recompose concludes.
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and config.state_refreshes_in_flight:
            time.sleep(0.02)
        assert config.state_refreshes_in_flight == 0
        assert calls["n"] == 2

        # This GET observes the failure (last good doc preserved, static
        # error named) and kicks recompose #3 — which is gated, so this
        # state is stable until the test releases it.
        status2, _h2, body2 = _get(port, "/api/state", headers=_auth_headers(config))
        payload2 = json.loads(body2)
        assert payload2["control_room"]["marker"] == "doc-1"
        assert payload2["state_refresh_error"] == "state refresh failed; serving last good composition"
        assert payload2["refresh_in_flight"] is True

        allow_recovery.set()
        deadline2 = time.monotonic() + 5
        while time.monotonic() < deadline2 and config.state_refreshes_in_flight:
            time.sleep(0.02)

    assert config.state_refreshes_in_flight == 0
    assert config.state_cache.get("doc") == {"marker": "doc-3"}
    assert config.state_refresh_error is None


def test_superseded_background_refresh_never_overwrites_newer_explicit_recomposition(tmp_path, monkeypatch):
    """H1 repair, Sol review 5000983751 Blocker 2 — Sol's exact required
    regression: a stale-GET background composition (A) that starts before
    an explicit ``POST /api/refresh-builds`` recomposition (B) but FINISHES
    after B has already published must never overwrite B's result. B's
    generation raises ``state_explicit_floor``, which makes A's later,
    lower-generation publish a no-op (discarded entirely — no cache write,
    no composed_at/composed_monotonic touch).
    """
    monkeypatch.setattr(server_mod.capability, "census", lambda **_kw: {})
    calls = {"n": 0}
    entered_A = threading.Event()
    release_A = threading.Event()

    def fake_compose(config, *, timeout=60.0):
        calls["n"] += 1
        n = calls["n"]
        if n == 1:
            return {"marker": "startup-doc"}
        if n == 2:
            entered_A.set()
            release_A.wait(timeout=5)
            return {"marker": "old-background-doc"}
        return {"marker": "explicit-doc"}

    monkeypatch.setattr(server_mod, "_compose_state_doc", fake_compose)

    runner = FakeRunner(responses=[
        {"code": 0, "stdout": json.dumps(_STUB_FIXTURE_DOC), "stderr": "", "timed_out": False},
    ])
    config = _make_config(tmp_path, runner=runner)
    config.state_ttl = 0.0  # every GET below is against a stale cache
    _write_stub_build_script(Path(config.macro_root))

    with _running_server(config) as (_httpd, port):
        # Startup pre-compose already ran (call #1). This GET is against a
        # stale (TTL=0) cache, so it kicks background recompose A (call #2)
        # while itself still returning the last good (startup) doc.
        status1, _h1, body1 = _get(port, "/api/state", headers=_auth_headers(config))
        assert status1 == 200
        assert json.loads(body1)["control_room"]["marker"] == "startup-doc"

        assert entered_A.wait(timeout=5), "background recompose A never started"

        # Explicit recompose B: reserves a HIGHER generation, raises
        # state_explicit_floor, and — because fake_compose call #3 returns
        # immediately, unlike gated A — publishes before A does.
        status_post, _hp, body_post = _post(
            port, "/api/refresh-builds", {}, headers=_auth_headers(config)
        )
        assert status_post == 200
        assert json.loads(body_post)["ok"] is True

        # Poll the CONFIG directly (no further HTTP — a GET here would
        # itself be a stale read with TTL=0 and kick yet another
        # background refresh) to confirm B's doc is already published.
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and config.state_cache.get("doc") != {"marker": "explicit-doc"}:
            time.sleep(0.02)
        assert config.state_cache.get("doc") == {"marker": "explicit-doc"}
        composed_at_after_b = config.state_cache.get("composed_at")
        composed_monotonic_after_b = config.state_cache.get("composed_monotonic")

        # Release the gated background composition A — its result (an
        # OLDER generation than B) must be discarded entirely, not
        # overwrite B's already-published doc.
        release_A.set()
        deadline2 = time.monotonic() + 5
        while time.monotonic() < deadline2 and config.state_refreshes_in_flight:
            time.sleep(0.02)

    assert config.state_refreshes_in_flight == 0
    assert config.state_cache.get("doc") == {"marker": "explicit-doc"}
    assert config.state_refresh_error is None
    assert config.state_cache.get("composed_at") == composed_at_after_b
    assert config.state_cache.get("composed_monotonic") == composed_monotonic_after_b
    assert calls["n"] == 3


def test_superseded_background_failure_does_not_mask_newer_explicit_success(tmp_path, monkeypatch):
    """H1 repair, Sol review 5000983751 Blocker 2 — the same race as the
    superseded-success regression above, but the gated background
    composition A RAISES (instead of returning a doc) after it is
    released. A superseded FAILURE must be discarded exactly like a
    superseded success: it must never record state_refresh_error over a
    newer explicit recomposition's clean success, and the published doc
    must stay B's.
    """
    monkeypatch.setattr(server_mod.capability, "census", lambda **_kw: {})
    calls = {"n": 0}
    entered_A = threading.Event()
    release_A = threading.Event()

    def fake_compose(config, *, timeout=60.0):
        calls["n"] += 1
        n = calls["n"]
        if n == 1:
            return {"marker": "startup-doc"}
        if n == 2:
            entered_A.set()
            release_A.wait(timeout=5)
            raise RuntimeError("synthetic superseded background failure")
        return {"marker": "explicit-doc"}

    monkeypatch.setattr(server_mod, "_compose_state_doc", fake_compose)

    runner = FakeRunner(responses=[
        {"code": 0, "stdout": json.dumps(_STUB_FIXTURE_DOC), "stderr": "", "timed_out": False},
    ])
    config = _make_config(tmp_path, runner=runner)
    config.state_ttl = 0.0
    _write_stub_build_script(Path(config.macro_root))

    with _running_server(config) as (_httpd, port):
        status1, _h1, body1 = _get(port, "/api/state", headers=_auth_headers(config))
        assert status1 == 200
        assert json.loads(body1)["control_room"]["marker"] == "startup-doc"

        assert entered_A.wait(timeout=5), "background recompose A never started"

        status_post, _hp, body_post = _post(
            port, "/api/refresh-builds", {}, headers=_auth_headers(config)
        )
        assert status_post == 200
        assert json.loads(body_post)["ok"] is True

        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and config.state_cache.get("doc") != {"marker": "explicit-doc"}:
            time.sleep(0.02)
        assert config.state_cache.get("doc") == {"marker": "explicit-doc"}
        assert config.state_refresh_error is None

        release_A.set()
        deadline2 = time.monotonic() + 5
        while time.monotonic() < deadline2 and config.state_refreshes_in_flight:
            time.sleep(0.02)

    assert config.state_refreshes_in_flight == 0
    assert config.state_refresh_error is None
    assert config.state_cache.get("doc") == {"marker": "explicit-doc"}
    assert calls["n"] == 3


def test_startup_precompose_first_get_served_from_cache_not_recomposed(tmp_path, monkeypatch):
    calls: list[float] = []

    def fake_compose(config, *, timeout=60.0):
        calls.append(timeout)
        return {"marker": "startup-doc"}

    monkeypatch.setattr(server_mod, "_compose_state_doc", fake_compose)
    config = _make_config(tmp_path)

    with _running_server(config) as (_httpd, port):
        # The composer already ran once, synchronously, during server
        # construction — before this line issues any request at all.
        assert calls == [server_mod.ServerConfig.compose_timeout]
        status, _headers, body = _get(port, "/api/state", headers=_auth_headers(config))

    assert status == 200
    assert json.loads(body)["control_room"]["marker"] == "startup-doc"
    assert len(calls) == 1  # the GET was served from cache, not recomposed


def test_state_envelope_carries_composed_at_and_refresh_fields_with_unchanged_shapes(tmp_path):
    config = _make_config(tmp_path, now_value="2026-08-22T03:00:00Z")
    with _running_server(config) as (_httpd, port):
        status, _headers, body = _get(port, "/api/state", headers=_auth_headers(config))
    assert status == 200
    payload = json.loads(body)

    assert payload["composed_at"] == "2026-08-22T03:00:00Z"
    assert isinstance(payload["refresh_in_flight"], bool)
    assert payload["state_refresh_error"] is None

    assert set(payload["capabilities"].keys()) >= {
        "chatgpt", "claude_code", "claude_desktop", "cursor_agent", "codex", "aionui",
    }
    assert payload["live_builds_active"] is False


def test_get_state_and_discover_require_token_and_do_zero_work_when_forbidden(tmp_path, monkeypatch):
    compose_calls: list[int] = []

    def fake_compose(config, *, timeout=60.0):
        compose_calls.append(1)
        return {"marker": "doc"}

    monkeypatch.setattr(server_mod, "_compose_state_doc", fake_compose)

    discover_calls: list[int] = []
    real_discover = server_mod._discover_document

    def fake_discover(config):
        discover_calls.append(1)
        return real_discover(config)

    monkeypatch.setattr(server_mod, "_discover_document", fake_discover)

    config = _make_config(tmp_path)
    with _running_server(config) as (_httpd, port):
        assert compose_calls == [1]  # startup pre-compose only

        status1, _h1, body1 = _get(port, "/api/state")  # no token
        assert status1 == 403
        assert json.loads(body1)["error"] == "forbidden"
        assert compose_calls == [1]  # the forbidden GET did zero composition work

        status2, _h2, _b2 = _get(port, "/api/discover")  # no token
        assert status2 == 403
        assert discover_calls == []  # the forbidden GET did zero discovery work

        status3, _h3, _b3 = _get(port, "/api/state", headers=_auth_headers(config))
        assert status3 == 200

        status4, _h4, _b4 = _get(port, "/api/discover", headers=_auth_headers(config))
        assert status4 == 200
        assert discover_calls == [1]


def test_compose_timeout_and_state_ttl_cli_flags_reach_server_config():
    args_default = server_mod._parser().parse_args([])
    config_default = server_mod._build_config(args_default)
    assert config_default.compose_timeout == 240.0
    assert config_default.state_ttl == 120.0

    args_custom = server_mod._parser().parse_args(["--compose-timeout", "99", "--state-ttl", "7"])
    config_custom = server_mod._build_config(args_custom)
    assert config_custom.compose_timeout == 99.0
    assert config_custom.state_ttl == 7.0


def test_startup_precompose_threads_compose_timeout_into_build_control_room(tmp_path, monkeypatch):
    recorded: dict = {}

    def fake_build_control_room(**kwargs):
        recorded.update(kwargs)
        return {"marker": "doc"}

    monkeypatch.setattr(server_mod.ccr, "build_control_room", fake_build_control_room)
    config = _make_config(tmp_path)

    with _running_server(config):
        pass

    assert recorded.get("timeout") == 240.0


def test_default_runner_no_cwd_branch_passes_max_bytes_through(monkeypatch):
    """R6: the ``cwd is None`` branch of ``default_runner`` used to silently
    drop ``max_bytes`` — ``run_argv`` has carried that parameter since
    98c8834. Regression-proves the seam forwards it (including ``None``,
    which is a real, meaningful value: "use run_argv's own default")."""
    recorded: dict = {}

    def fake_run_argv(argv, *, timeout=20.0, max_bytes=None):
        recorded["timeout"] = timeout
        recorded["max_bytes"] = max_bytes
        return {"code": 0, "stdout": "", "stderr": "", "timed_out": False}

    monkeypatch.setattr(server_mod.surfaces_runner, "run_argv", fake_run_argv)

    server_mod.default_runner(["true"], timeout=12.0, max_bytes=999)
    assert recorded == {"timeout": 12.0, "max_bytes": 999}

    recorded.clear()
    server_mod.default_runner(["true"], timeout=5.0)
    assert recorded == {"timeout": 5.0, "max_bytes": None}


# ---------------------------------------------------------------------------
# security: non-loopback client rejection (unit-level; the harness only
# offers loopback connections, so this exercises _client_is_loopback directly)
# ---------------------------------------------------------------------------


def test_client_is_loopback_helper():
    assert server_mod._client_is_loopback("127.0.0.1") is True
    assert server_mod._client_is_loopback("127.5.5.5") is True
    assert server_mod._client_is_loopback("::1") is True
    assert server_mod._client_is_loopback("10.0.0.5") is False
    assert server_mod._client_is_loopback("not-an-ip") is False


def test_host_allowed_helper():
    assert server_mod._host_allowed("127.0.0.1:8787", 8787) is True
    assert server_mod._host_allowed("127.0.0.1", 8787) is True
    assert server_mod._host_allowed("localhost:8787", 8787) is True
    assert server_mod._host_allowed("127.0.0.1:9999", 8787) is False
    assert server_mod._host_allowed("evil.example", 8787) is False
    assert server_mod._host_allowed(None, 8787) is False


# ---------------------------------------------------------------------------
# unknown routes -> 404
# ---------------------------------------------------------------------------


def test_unknown_get_route_is_404(tmp_path):
    config = _make_config(tmp_path)
    with _running_server(config) as (_httpd, port):
        status, _headers, _body = _get(port, "/api/nope")
    assert status == 404


def test_unknown_post_route_is_404(tmp_path):
    config = _make_config(tmp_path)
    with _running_server(config) as (_httpd, port):
        status, _headers, _body = _post(port, "/api/nope", {}, headers=_auth_headers(config))
    assert status == 404


def test_favicon_is_204(tmp_path):
    config = _make_config(tmp_path)
    with _running_server(config) as (_httpd, port):
        status, _headers, body = _get(port, "/favicon.ico")
    assert status == 204
    assert body == b""


def test_b5_handoff_cannot_select_historical_proof_under_current_publication(tmp_path, monkeypatch):
    config, clock, binding = _b5_navigation_fixture(tmp_path, monkeypatch)
    providers = []
    config.open_binding_fn = lambda *a, **k: providers.append(a) or {"ok": True, "verified": True}
    with _running_server(config) as (_httpd, port):
        _, _, body = _get(port, "/api/state", headers=_auth_headers(config))
        request = _b5_owed_request(json.loads(body))
        current = json.loads(json.dumps(config.state_cache["doc"]))
        card = current["autonomy"]["responsibilities"][0]
        card["dispatch"]["dispatch_state"] = "EFFECT_UNKNOWN"
        card["validity"]["owed_open_age"].update(proof_ref="b" * 64, valid_for_ms=None)
        with config.state_lock:
            server_mod._publish_source_validity(config, current, tuple(clock), tuple(clock))
            config.state_cache["doc"] = current
            config.state_published_seq += 1
            request["owed_context"]["publication_seq"] = config.state_published_seq
        before = config.bindings_path.read_bytes()
        status, _, _ = _post(port, "/api/open", request, headers=_auth_headers(config))
    assert status == 409 and providers == []
    assert config.bindings_path.read_bytes() == before


def test_b5_proof_accounting_capacity_refuses_instead_of_forgetting(tmp_path, monkeypatch):
    config = _make_config(tmp_path)
    clock = tuple(_b5_sample(1000))
    config.validity_sample_fn = lambda: clock
    monkeypatch.setattr(server_mod, "_VALIDITY_MAX_PROOFS", 4, raising=False)
    doc = _b5_server_doc()
    server_mod._publish_source_validity(config, doc, clock, clock)
    config.state_cache["doc"] = doc
    assert server_mod._source_validity_snapshot(config, clock)["cards"][0]["components"]["card"]["remaining_ms"] == 984
    changed = json.loads(json.dumps(doc))
    changed["autonomy"]["responsibilities"][0]["validity"]["card"]["proof_ref"] = "b" * 64
    server_mod._publish_source_validity(config, changed, clock, clock)
    server_mod._publish_source_validity(config, doc, clock, clock)
    assert len(config.state_cache["source_validity_bounds"]) <= 4
    assert server_mod._source_validity_snapshot(config, clock)["cards"][0]["components"]["card"]["remaining_ms"] is None

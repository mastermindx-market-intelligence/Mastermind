"""scripts.chairman_control_room — Chairman Control Room P0 Wave C server tests.

Falsifiers for the loopback-only local HTTP server: security gates (loopback/
Host/token/Origin), the closed static-asset allowlist, the binding-mutation
endpoints (``/api/open``/``/api/bind``/``/api/unbind``), the process-memory
live-active-builds cache (``/api/refresh-builds``, restart-forgets proof), the
zero-ownership discovery endpoint (``/api/discover``), and response headers
(CSP/no-store/nosniff).

Hermetic: the server always runs in-process on an OS-assigned ephemeral port
(``127.0.0.1:0``) against a throwaway ``tmp_path`` repo/macro root and a
throwaway bindings file. Every subprocess call is intercepted by an injected
``FakeRunner`` — no real ``osascript``/Chrome/``open``/build-map subprocess is
ever spawned by this suite.
"""
from __future__ import annotations

import contextlib
import http.client
import json
import shutil
import stat
import threading
from pathlib import Path

import pytest

from control_plane import surface_bindings as sb
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


# ---------------------------------------------------------------------------
# server harness
# ---------------------------------------------------------------------------


def _make_config(tmp_path: Path, *, runner=None, now_value: str = "2026-08-22T00:00:00Z", live_cache=None) -> "server_mod.ServerConfig":
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
        thread.join(timeout=5)


def _request(port: int, method: str, path: str, *, headers=None, body: bytes | None = None, host: str | None = None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
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
                {"repo": "mastermindx-market-intelligence/macro", "open_prs": pr_rows}
            ],
        }
        if len(json.dumps(doc).encode("utf-8")) >= min_bytes:
            return doc
        pr_rows.append({
            "repo": "mastermindx-market-intelligence/macro",
            "number": 6000 + i,
            "url": f"https://github.com/mastermindx-market-intelligence/macro/pull/{6000 + i}",
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
# 10. /api/discover — chatgpt-host filtering, zero writes, cursor unsupported
# ---------------------------------------------------------------------------


def test_discover_filters_to_chatgpt_hosts_only_and_writes_nothing(tmp_path):
    mixed_stdout = "\n".join([
        "https://chatgpt.com/c/aaa\tFirst Chat",
        "https://example.com/not-chatgpt\tSomething Else",
        "https://chat.openai.com/c/bbb\tSecond Chat",
        "https://evil.example/chatgpt.com.phish\tPhish",
    ])
    runner = FakeRunner(responses=[{"code": 0, "stdout": mixed_stdout, "stderr": "", "timed_out": False}])
    config = _make_config(tmp_path, runner=runner)

    before = _snapshot_tree(tmp_path)
    with _running_server(config) as (_httpd, port):
        status, _headers, body = _get(port, "/api/discover", headers=_auth_headers(config))
    after = _snapshot_tree(tmp_path)

    assert status == 200
    payload = json.loads(body)
    urls = {tab["url"] for tab in payload["chatgpt_tabs"]}
    assert urls == {"https://chatgpt.com/c/aaa", "https://chat.openai.com/c/bbb"}
    assert all(tab["profile"] is None for tab in payload["chatgpt_tabs"])
    assert payload["cursor"] == {"supported": False, "note": payload["cursor"]["note"]}
    assert payload["cursor"]["supported"] is False
    assert isinstance(payload["claude_code_sessions"], list)
    assert isinstance(payload["codex_sessions"], list)
    # bindings-file writes excluded (never touched by discover); repo/macro
    # trees must be byte-for-byte unchanged.
    assert before == after


def test_discover_chrome_not_running_returns_empty_tabs(tmp_path):
    runner = FakeRunner(responses=[{"code": 0, "stdout": "", "stderr": "", "timed_out": False}])
    config = _make_config(tmp_path, runner=runner)
    with _running_server(config) as (_httpd, port):
        status, _headers, body = _get(port, "/api/discover", headers=_auth_headers(config))
    assert status == 200
    assert json.loads(body)["chatgpt_tabs"] == []


# ---------------------------------------------------------------------------
# AppleScript byte-stability + server-side filtering unit test
# ---------------------------------------------------------------------------


def test_discover_tabs_applescript_is_byte_stable():
    expected = (
        'on run argv\n'
        '    if application "Google Chrome" is not running then\n'
        '        return ""\n'
        '    end if\n'
        '    set outputLines to {}\n'
        '    tell application "Google Chrome"\n'
        '        repeat with w in windows\n'
        '            repeat with t in tabs of w\n'
        '                set end of outputLines to ((URL of t as string) & tab & (title of t as string))\n'
        '            end repeat\n'
        '        end repeat\n'
        '    end tell\n'
        '    set AppleScript\'s text item delimiters to linefeed\n'
        '    set outputText to outputLines as string\n'
        '    set AppleScript\'s text item delimiters to ""\n'
        '    return outputText\n'
        'end run\n'
    )
    assert server_mod.DISCOVER_TABS_APPLESCRIPT == expected


def test_discover_url_filter_is_server_side_not_in_the_script():
    # The AppleScript itself performs no host filtering — that happens in
    # Python (_chatgpt_tabs) after the argv/subprocess boundary.
    assert "chatgpt" not in server_mod.DISCOVER_TABS_APPLESCRIPT.lower()

    runner = FakeRunner(responses=[{"code": 0, "stdout": "https://not-chatgpt.example/x\tTitle", "stderr": "", "timed_out": False}])
    config = server_mod.ServerConfig(
        repo_root=Path("/tmp"), macro_root=None, bindings_path=None, token="t", origin="http://127.0.0.1:0",
        port=0, runner=runner,
    )
    tabs = server_mod._chatgpt_tabs(config)
    assert tabs == []


# ---------------------------------------------------------------------------
# 11. successful /api/open updates ONLY last_verified_at
# ---------------------------------------------------------------------------


def test_successful_open_updates_only_last_verified_at(tmp_path):
    binding_id = "22222222-2222-4222-8222-222222222222"
    doc = {
        "schema": sb.SCHEMA,
        "bindings": [
            sb.new_binding(
                work_ref="WS:OPEN-TEST",
                role="worker",
                provider="claude_desktop",
                locator_kind="claude_desktop_url",
                locator={"url": "https://claude.ai/chat/abc123"},
                observed_at="2026-08-22T00:00:00Z",
                last_verified_at=None,
                binding_id=binding_id,
            )
        ],
    }
    config = _make_config(tmp_path, now_value="2026-08-22T05:00:00Z")
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

    after_doc, _problems2 = sb.load_bindings(config.bindings_path)
    after_binding = after_doc["bindings"][0]

    assert after_binding["last_verified_at"] == "2026-08-22T05:00:00Z"
    for key in before_binding:
        if key == "last_verified_at":
            continue
        assert after_binding[key] == before_binding[key], key


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

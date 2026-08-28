"""Fail-closed contracts for the remote read-only Chairman Control Room."""
from __future__ import annotations

import copy
import contextlib
import http.client
import json
import os
import shutil
import socket
import stat
import tempfile
import threading
from pathlib import Path

import pytest

from control_plane import chairman_control_room as ccr
from control_plane import chairman_control_room_remote as remote
from scripts import chairman_control_room_remote as server


FIXTURES = Path(__file__).parent / "fixtures" / "chairman_control_room"
NOW = "2026-08-28T20:00:00Z"
IDENTITY = remote.BuildIdentity(
    commit="a" * 40,
    tree="b" * 40,
    artifact_digest="sha256:" + "c" * 64,
)
FRESHNESS = {
    remote.SOURCE_AGENT_OS_BRIEF: remote.SourceFreshness("fresh", NOW, NOW, None),
    remote.SOURCE_AGENT_OS_STATE: remote.SourceFreshness("fresh", NOW, NOW, None),
    remote.SOURCE_ACTIVE_BUILDS: remote.SourceFreshness("fresh", NOW, NOW, None),
    remote.SOURCE_EXECUTIVE_RUNTIME: remote.SourceFreshness("fresh", NOW, NOW, None),
}


def _load(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture
def canonical_doc():
    return ccr.compose_control_room(
        inbox=_load("executive_inbox_v2.json"),
        boot_packet=_load("boot_packet_v1.json"),
        active_builds=_load("active_builds_v1.json"),
        agent_os_state=_load("agent_os_state_v1.json"),
        runtime_jobs=_load("runtime_jobs_v1.json"),
        bindings=_load("bindings_v1.json"),
        binding_problems=(),
        generated_at=NOW,
    )


def _project(doc):
    return remote.project_remote_document(
        doc, observed_at=NOW, freshness=FRESHNESS, build_identity=IDENTITY
    )


def test_remote_projection_is_closed_and_omits_local_authority(canonical_doc):
    projected = _project(canonical_doc)
    assert projected["schema"] == "mastermind.chairman_control_room_remote.v1"
    assert set(projected) == {
        "schema", "observed_at", "code_identity", "source_freshness",
        "degraded", "attention", "work", "unjoined_open_prs",
    }
    assert set(projected["code_identity"]) == {"commit", "tree", "artifact_digest"}
    assert set(projected["source_freshness"]) == remote.COLLECTOR_SOURCES
    assert all(
        set(row) == {"state", "observed_at", "source_time", "reason"}
        for row in projected["source_freshness"].values()
    )
    assert set(projected["attention"]) == {"chairman", "ceo", "coo"}
    assert all(
        set(item) == {
            "attention_id", "kind", "title", "summary", "workstream",
            "state", "reason_code",
        }
        for bucket in projected["attention"].values()
        for item in bucket
    )
    assert all(
        set(card) == {
            "work_ref", "agent_os", "executive", "github",
            "attention_ids", "disagreements",
        }
        for card in projected["work"]
    )
    assert all(
        card["agent_os"] is None or set(card["agent_os"]) == {
            "workstream", "title", "status", "program", "next_action",
            "state", "reason_code", "reason", "depends_on",
            "unmet_dependencies",
        }
        for card in projected["work"]
    )
    assert all(set(card["executive"]) == {"jobs", "joined_by"} for card in projected["work"])
    assert all(
        set(job) == {"job_id", "status", "workstream"}
        for card in projected["work"] for job in card["executive"]["jobs"]
    )
    assert all(set(card["github"]) == {"prs"} for card in projected["work"])
    assert all(
        set(pr) == {"repo", "number", "url", "title", "branch", "draft", "merge_state"}
        for card in projected["work"] for pr in card["github"]["prs"]
    )
    assert all(
        set(pr) == {"repo", "number", "url", "title", "branch", "draft", "merge_state"}
        for pr in projected["unjoined_open_prs"]
    )
    encoded = json.dumps(projected, sort_keys=True)
    for forbidden in (
        "macro_root", "bindings", "binding_conflicts", "unbound_surfaces",
        "locator", "seat_ref", "argv", "traceback", "/Users/", "/opt/",
        "X-CCR-Token", "@example.com",
    ):
        assert forbidden not in encoded


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        (lambda d: d.__setitem__("future", True), "unexpected_keys"),
        (lambda d: d["work"][0].__setitem__("future", True), "unexpected_keys"),
        (lambda d: d.__setitem__("schema", "mastermind.future.v9"), "schema_mismatch"),
        (lambda d: d.__setitem__("work", {}), "invalid_type"),
        (lambda d: d["work"][0].__setitem__("attention_ids", "not-a-list"), "invalid_type"),
        (lambda d: d["work"][0]["executive"]["jobs"][0].__setitem__("status", float("nan")), "non_finite_number"),
        (lambda d: d["work"][0]["executive"]["jobs"][0].__setitem__("status", float("inf")), "non_finite_number"),
        (lambda d: d["work"][0].__setitem__("disagreements", ["host.local"]), "sensitive_value"),
        (lambda d: d["work"][0].__setitem__("disagreements", ["/opt/private/file"]), "sensitive_value"),
        (lambda d: d["work"][0].__setitem__("disagreements", ["person@example.com"]), "sensitive_value"),
        (lambda d: d["work"][0].__setitem__("disagreements", ["provider_session_id=raw-123"]), "sensitive_value"),
    ],
)
def test_remote_projection_rejects_adversarial_canonical_documents(canonical_doc, mutation, code):
    bad = copy.deepcopy(canonical_doc)
    mutation(bad)
    with pytest.raises(remote.RemoteProjectionError) as exc:
        _project(bad)
    assert exc.value.code == code


def test_remote_projection_rejects_bad_freshness_and_identity(canonical_doc):
    with pytest.raises(remote.RemoteProjectionError) as exc:
        remote.project_remote_document(
            canonical_doc,
            observed_at=NOW,
            freshness={remote.SOURCE_AGENT_OS_BRIEF: FRESHNESS[remote.SOURCE_AGENT_OS_BRIEF]},
            build_identity=IDENTITY,
        )
    assert exc.value.code == "freshness_sources_mismatch"

    with pytest.raises(remote.RemoteProjectionError) as exc:
        remote.project_remote_document(
            canonical_doc,
            observed_at=NOW,
            freshness=FRESHNESS,
            build_identity=remote.BuildIdentity("HEAD", "b" * 40, "sha256:" + "c" * 64),
        )
    assert exc.value.code == "invalid_build_identity"


def test_remote_projection_is_deterministic_and_does_not_mutate_input(canonical_doc):
    before = copy.deepcopy(canonical_doc)
    first = _project(canonical_doc)
    second = _project(canonical_doc)
    assert canonical_doc == before
    assert json.dumps(first, sort_keys=True, separators=(",", ":")) == json.dumps(
        second, sort_keys=True, separators=(",", ":")
    )


class RecordingRunner:
    def __init__(self, stdout: str, *, code: int = 0, stderr: str = ""):
        self.stdout = stdout
        self.code = code
        self.stderr = stderr
        self.calls = []

    def __call__(self, argv, *, cwd, timeout, max_bytes):
        self.calls.append({
            "argv": list(argv), "cwd": cwd, "timeout": timeout, "max_bytes": max_bytes,
        })
        return {
            "code": self.code, "stdout": self.stdout, "stderr": self.stderr,
            "timed_out": False,
        }


@pytest.fixture
def collector_config(tmp_path):
    macro = tmp_path / "macro"
    (macro / "scripts").mkdir(parents=True)
    (macro / "scripts" / "build_project_active_build_map.py").write_text("# fixture\n")
    active = _load("active_builds_v1.json")
    return remote.CollectorConfig(
        repo_root=tmp_path / "mastermind",
        macro_root=macro,
        timeout_seconds=12.0,
        max_output_bytes=4096,
        runner=RecordingRunner(json.dumps(active)),
        environ={},
    )


def _patch_collectors(monkeypatch, canonical_doc):
    packet = _load("boot_packet_v1.json")
    inbox = _load("executive_inbox_v2.json")
    agent_state = _load("agent_os_state_v1.json")
    runtime_jobs = _load("runtime_jobs_v1.json")
    packet_calls = []
    inbox_calls = []

    def fake_packet(**kwargs):
        packet_calls.append(kwargs)
        return packet

    def fake_inbox(**kwargs):
        inbox_calls.append(kwargs)
        assert kwargs["boot_packet"] is packet
        return inbox

    monkeypatch.setattr(remote.ceo_boot_packet, "build_packet", fake_packet)
    monkeypatch.setattr(remote.executive_inbox, "build_inbox", fake_inbox)
    monkeypatch.setattr(remote.ccr, "_read_agent_os_state", lambda _: (agent_state, None))
    monkeypatch.setattr(remote.ccr, "_read_runtime_jobs", lambda _: (runtime_jobs, None))
    return packet_calls, inbox_calls


def test_collector_injects_fresh_json_stdout_document_into_pure_compositor(
    monkeypatch, collector_config, canonical_doc
):
    packet_calls, inbox_calls = _patch_collectors(monkeypatch, canonical_doc)
    compose_calls = []
    monkeypatch.setattr(remote.ccr, "build_control_room", lambda **_: pytest.fail("forbidden"))
    monkeypatch.setattr(
        remote.ccr,
        "_read_active_builds",
        lambda *_: pytest.fail("stale active-build file must not be read"),
    )
    monkeypatch.setattr(
        remote.ccr,
        "compose_control_room",
        lambda **kwargs: compose_calls.append(kwargs) or canonical_doc,
    )

    inputs = remote.collect_once(collector_config, now=NOW)
    projected = remote.compose_collected(inputs, IDENTITY)

    assert len(packet_calls) == len(inbox_calls) == 1
    assert len(collector_config.runner.calls) == 1
    call = collector_config.runner.calls[0]
    assert call["argv"][-1] == "--json-stdout"
    assert call["cwd"] == collector_config.macro_root
    assert call["timeout"] == 12.0
    assert call["max_bytes"] == 4096
    assert len(compose_calls) == 1
    assert compose_calls[0]["active_builds"] == _load("active_builds_v1.json")
    assert compose_calls[0]["bindings"] is None
    assert compose_calls[0]["binding_problems"] == ()
    assert projected["schema"] == remote.REMOTE_SCHEMA


@pytest.mark.parametrize(
    ("stdout", "code"),
    [
        ("not-json", "invalid_json"),
        ('{"schema":"project_active_builds.v1","schema":"duplicate"}', "duplicate_json_key"),
        ('{"schema":"project_active_builds.v1","collected_at":"x","projects":[],"n":NaN}', "non_finite_number"),
        ('{"schema":"wrong","collected_at":"x","projects":[]}', "active_builds_schema_mismatch"),
    ],
)
def test_collector_rejects_invalid_active_build_stdout(
    monkeypatch, collector_config, canonical_doc, stdout, code
):
    _patch_collectors(monkeypatch, canonical_doc)
    collector_config.runner = RecordingRunner(stdout)
    with pytest.raises(remote.RemoteProjectionError) as exc:
        remote.collect_once(collector_config, now=NOW)
    assert exc.value.code == code


def test_collector_refuses_over_limit_and_failed_or_timed_out_runner(
    monkeypatch, collector_config, canonical_doc
):
    _patch_collectors(monkeypatch, canonical_doc)
    collector_config.max_output_bytes = 8
    with pytest.raises(remote.RemoteProjectionError) as exc:
        remote.collect_once(collector_config, now=NOW)
    assert exc.value.code == "collector_output_too_large"

    collector_config.max_output_bytes = 4096
    collector_config.runner = RecordingRunner("{}", code=9, stderr="secret details")
    with pytest.raises(remote.RemoteProjectionError) as exc:
        remote.collect_once(collector_config, now=NOW)
    assert exc.value.code == "active_builds_command_failed"
    assert "secret" not in str(exc.value)


def test_absent_runtime_database_is_degraded_and_never_created(
    monkeypatch, collector_config, canonical_doc
):
    packet = _load("boot_packet_v1.json")
    inbox = _load("executive_inbox_v2.json")
    monkeypatch.setattr(remote.ceo_boot_packet, "build_packet", lambda **_: packet)
    monkeypatch.setattr(remote.executive_inbox, "build_inbox", lambda **_: inbox)
    monkeypatch.setattr(remote.ccr, "_read_agent_os_state", lambda _: (None, "missing"))
    db = collector_config.repo_root / remote.executive_inbox.DB_RELATIVE_PATH
    assert not db.exists()
    inputs = remote.collect_once(collector_config, now=NOW)
    assert not db.exists()
    assert inputs.runtime_jobs is None
    assert inputs.freshness[remote.SOURCE_EXECUTIVE_RUNTIME].state == "unavailable"


def test_cache_starts_empty_single_flights_and_expires_last_good(monkeypatch, collector_config):
    assert collector_config.interval_seconds == 300.0
    assert collector_config.stale_after_seconds == 900.0
    entered = threading.Event()
    release = threading.Event()
    calls = []
    monotonic = [100.0]
    document = {"schema": remote.REMOTE_SCHEMA, "value": "accepted"}

    def collect(_config, *, now):
        calls.append(now)
        entered.set()
        release.wait(timeout=5)
        return object()

    monkeypatch.setattr(remote, "collect_once", collect)
    monkeypatch.setattr(remote, "compose_collected", lambda *_: document)
    cache = remote.RemoteStateCache(
        collector_config,
        IDENTITY,
        monotonic_fn=lambda: monotonic[0],
        now_fn=lambda: NOW,
    )
    assert cache.snapshot() is None
    thread = threading.Thread(target=cache.refresh)
    thread.start()
    assert entered.wait(timeout=5)
    assert cache.refresh() is False
    release.set()
    thread.join(timeout=5)
    assert not thread.is_alive()
    assert len(calls) == 1
    assert cache.snapshot() == document

    monotonic[0] = 1000.0
    assert cache.snapshot() == document
    monotonic[0] = 1000.0001
    assert cache.snapshot() is None
    assert remote.RemoteStateCache(collector_config, IDENTITY).snapshot() is None


def test_refresh_failure_preserves_only_bounded_last_good(monkeypatch, collector_config):
    monotonic = [10.0]
    outcomes = [object(), remote.RemoteProjectionError("refresh_failed")]
    monkeypatch.setattr(
        remote,
        "collect_once",
        lambda *_args, **_kwargs: (
            (_ for _ in ()).throw(outcomes.pop(0))
            if isinstance(outcomes[0], Exception)
            else outcomes.pop(0)
        ),
    )
    monkeypatch.setattr(remote, "compose_collected", lambda *_: {"ok": "last-good"})
    cache = remote.RemoteStateCache(
        collector_config, IDENTITY, monotonic_fn=lambda: monotonic[0], now_fn=lambda: NOW
    )
    assert cache.refresh() is True
    monotonic[0] = 20.0
    assert cache.refresh() is False
    assert cache.last_error == "refresh_failed"
    assert cache.snapshot() == {"ok": "last-good"}
    monotonic[0] = 911.0
    assert cache.snapshot() is None


def test_snapshot_is_memory_only(monkeypatch, collector_config):
    cache = remote.RemoteStateCache(collector_config, IDENTITY)
    monkeypatch.setattr(Path, "read_bytes", lambda *_: pytest.fail("no filesystem reads"))
    monkeypatch.setattr(remote.subprocess, "run", lambda *_a, **_k: pytest.fail("no subprocess"))
    assert cache.snapshot() is None


class StaticCache:
    def __init__(self, document=None):
        self.document = document
        self.snapshot_calls = 0

    def snapshot(self):
        self.snapshot_calls += 1
        return copy.deepcopy(self.document)


class UnixHTTPConnection(http.client.HTTPConnection):
    def __init__(self, socket_path: Path):
        super().__init__("localhost", timeout=5)
        self.socket_path = socket_path

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(os.fspath(self.socket_path))


@contextlib.contextmanager
def _running_remote_server(tmp_path, *, document=None):
    static = tmp_path / "static"
    static.mkdir()
    (static / "remote.html").write_text("<html>remote</html>", encoding="utf-8")
    (static / "control_room.css").write_text("body{}", encoding="utf-8")
    (static / "control_room.js").write_text("/* remote */", encoding="utf-8")
    # Darwin's AF_UNIX pathname ceiling is shorter than pytest's nested tmp
    # fixture path. Keep only the socket seam in a separately owned short dir.
    socket_root = Path(tempfile.mkdtemp(prefix="ccr-remote-", dir="/tmp"))
    socket_path = socket_root / "remote.sock"
    cache = StaticCache(document)
    config = server.RemoteServerConfig(
        socket_path=socket_path,
        static_dir=static,
        cache=cache,
        caddy_gid=os.getgid(),
        service_uid=os.getuid(),
    )
    httpd = server.ControlRoomUnixServer(
        socket_path, server.RemoteControlRoomHandler, config
    )
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield httpd, socket_path, cache
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)
        shutil.rmtree(socket_root)


def _unix_request(socket_path, method, path, headers=None):
    conn = UnixHTTPConnection(socket_path)
    try:
        conn.request(method, path, headers=headers or {})
        response = conn.getresponse()
        return response.status, dict(response.getheaders()), response.read()
    finally:
        conn.close()


def test_remote_cli_has_no_tcp_or_socket_override():
    parser = server.build_parser()
    args = parser.parse_args([
        "--repo-root", "/release", "--macro-root", "/macro",
        "--expected-commit", "a" * 40, "--build-metadata", "/release/build.json",
        "--interval-seconds", "300", "--stale-after-seconds", "900",
        "--timeout-seconds", "10", "--max-output-bytes", "4096",
    ])
    assert args.expected_commit == "a" * 40
    for option in ("--host", "--port", "--bind", "--socket"):
        with pytest.raises(SystemExit) as exc:
            parser.parse_args([option, "value"])
        assert exc.value.code == 2


def test_remote_server_is_unix_only_with_restricted_metadata(tmp_path):
    with _running_remote_server(tmp_path) as (httpd, socket_path, _cache):
        assert httpd.address_family == socket.AF_UNIX
        assert stat.S_IMODE(socket_path.parent.stat().st_mode) == 0o750
        assert stat.S_IMODE(socket_path.stat().st_mode) == 0o660
        assert socket_path.stat().st_gid == os.getgid()
    assert not socket_path.exists()


def test_fixed_get_head_health_and_state_routes(tmp_path):
    document = {"schema": remote.REMOTE_SCHEMA, "observed_at": NOW}
    with _running_remote_server(tmp_path, document=document) as (_httpd, sock, cache):
        for path in ("/", "/static/control_room.css", "/static/control_room.js"):
            get_status, get_headers, get_body = _unix_request(sock, "GET", path)
            head_status, head_headers, head_body = _unix_request(sock, "HEAD", path)
            assert get_status == head_status == 200
            assert get_headers["Content-Length"] == head_headers["Content-Length"]
            assert get_body
            assert head_body == b""

        status, headers, body = _unix_request(sock, "GET", "/healthz")
        assert status == 200
        assert headers["Content-Type"] == "text/plain; charset=utf-8"
        assert body == b"ok\n"
        assert cache.snapshot_calls == 0

        status, _headers, body = _unix_request(sock, "GET", "/api/state")
        assert status == 200
        assert json.loads(body) == {"ok": True, "control_room": document}


def test_state_is_typed_unavailable_before_first_success(tmp_path):
    with _running_remote_server(tmp_path) as (_httpd, sock, _cache):
        status, _headers, body = _unix_request(sock, "GET", "/api/state")
    assert status == 503
    assert json.loads(body) == {"ok": False, "error": {"code": "state_unavailable"}}


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_mutation_methods_are_closed_before_cache(method, tmp_path):
    with _running_remote_server(tmp_path, document={"secret": "must-not-read"}) as (
        _httpd, sock, cache
    ):
        status, headers, _body = _unix_request(sock, method, "/api/state")
    assert status == 405
    assert headers["Allow"] == "GET, HEAD"
    assert cache.snapshot_calls == 0


@pytest.mark.parametrize(
    "path",
    [
        "/api/open", "/api/bind", "/api/unbind", "/api/refresh-builds",
        "/api/state?x=1", "//api/state", "/x/../api/state", "/%2e%2e/api/state",
        "/static%2fcontrol_room.js", "/static%252fcontrol_room.js", "/x%00",
        "/static\\control_room.js", "/bad%zz", "/wild/*",
    ],
)
def test_unexpected_or_ambiguous_read_paths_fail_before_cache(path, tmp_path):
    with _running_remote_server(tmp_path, document={"ok": "hidden"}) as (
        _httpd, sock, cache
    ):
        status, _headers, _body = _unix_request(sock, "GET", path)
    assert status in (400, 404)
    assert cache.snapshot_calls == 0


def test_browser_credentials_and_forged_headers_change_no_decision_or_log(tmp_path):
    document = {"schema": remote.REMOTE_SCHEMA}
    with _running_remote_server(tmp_path, document=document) as (httpd, sock, _cache):
        baseline = _unix_request(sock, "GET", "/api/state")
        forged = _unix_request(
            sock,
            "GET",
            "/api/state",
            headers={
                "X-CCR-Token": "secret-nonce", "Cookie": "secret-cookie",
                "Authorization": "Bearer secret", "Host": "evil.example",
                "Origin": "https://evil.example", "X-Forwarded-User": "admin",
            },
        )
        events = list(httpd.config.events)
    assert forged == baseline
    encoded = json.dumps(events)
    for secret in ("secret-nonce", "secret-cookie", "Bearer secret", "evil.example", "admin"):
        assert secret not in encoded

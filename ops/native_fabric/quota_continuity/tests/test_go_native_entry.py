"""Actual immutable entry, original owners, B startup and A/SQLite composition."""
from contextlib import ExitStack
import hashlib
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import socket
import sqlite3
import sys
import threading
import time
from types import ModuleType
from unittest import mock

import pytest

from test_go_native_stage import builds, native_stage, published, loaded_entry


def inspect(entry, published):
    return entry.inspect(verified_root=published.release, verified_metadata=published.meta)


def arguments(published, startup):
    service = startup.handler.ApplicationServiceBinding(
        "macro", "vps", "site_interactive", "MACRO_APPLICATION_TOKEN",
        "fixture-application-service-credential-0123456789")
    return dict(verified_root=published.release, verified_metadata=published.meta,
        application_services=(service,), application_host="fixture-native",
        application_account_path=published.profile)


def clean_environment(monkeypatch, published):
    for name in list(os.environ):
        if name.startswith(("GO_", "POOL_")) or name == "REMOTE_SUB_HERE":
            monkeypatch.delenv(name)
    monkeypatch.setenv("GO_ACCOUNTS_PATH", str(published.profile))
    monkeypatch.setenv("GO_STATE_DIR", str(published.ext / "go_shim"))


def test_import_and_inspection_have_no_database_network_secret_or_service_effect(published):
    before = {str(p): p.read_bytes() for p in (published.profile,
        published.ext / "broker/leases.sqlite", published.ext / "go_shim/.token")}
    with loaded_entry(published) as entry, \
            mock.patch.object(sqlite3, "connect", side_effect=AssertionError("inspection opened database")), \
            mock.patch.object(socket.socket, "connect", side_effect=AssertionError("inspection connected")), \
            mock.patch.object(socket.socket, "bind", side_effect=AssertionError("inspection listened")):
        startup = inspect(entry, published)
        assert Path(startup.handler.__file__) == published.release / "ext/go_application_handler.py"
        assert Path(startup.broker_module.__file__) == published.release / "ext/lease_broker.py"
        codec = sys.modules["go_lease_capability"]
        assert codec is entry._LOADED_MODULES["go_lease_capability"]
        assert Path(codec.__file__) == published.release / "ext/go_lease_capability.py"
        assert startup.paths["db_path"] == published.ext / "broker/leases.sqlite"
        assert startup.paths["accounts_path"] == published.ext.parent / "orch/fabric/accounts.yaml"
        assert startup.paths["helper"] == published.ext / "glm_shim/glm_shim.py"
        assert sys.path[0] == str(published.release / "ext")
        with mock.patch.object(startup.broker_module, "Broker", side_effect=AssertionError("inspection constructed broker")), \
                mock.patch.object(startup.handler, "Router", side_effect=AssertionError("inspection constructed router")):
            assert inspect(entry, published).handler is startup.handler
            assert sys.modules["go_lease_capability"] is codec
            assert entry._LOADED_MODULES["go_lease_capability"] is codec
    assert before == {str(Path(p)): Path(p).read_bytes() for p in before}
    assert not (published.ext / "go_shim/shim.pid").exists()
    assert not (published.ext / "go_shim/shim.lock").exists()


@pytest.mark.parametrize("name", ["lease_broker", "go_lease_capability", "bailian_keys", "pool_ledger", "glm_shim"])
def test_matching_filename_foreign_module_is_not_adopted(published, name):
    with loaded_entry(published) as entry:
        foreign = ModuleType(name)
        foreign.__file__ = str(published.ext / "glm_shim/glm_shim.py" if name == "glm_shim"
                               else published.release / "ext" / (name + ".py"))
        sys.modules[name] = foreign
        with pytest.raises(ValueError, match="module conflict"):
            inspect(entry, published)


@pytest.mark.parametrize("value", [None, [], {}, False])
def test_only_exact_empty_tuple_means_no_enrollment(published, value):
    with loaded_entry(published) as entry, mock.patch.object(entry, "inspect", side_effect=AssertionError("invalid input reached imports")):
        with pytest.raises(ValueError, match="incomplete"):
            entry.main(verified_root=published.release, verified_metadata=published.meta, application_services=value)


def test_missing_enrollment_calls_original_B_main_without_broker(published, monkeypatch):
    clean_environment(monkeypatch, published)
    with loaded_entry(published) as entry:
        startup = inspect(entry, published)
        with mock.patch.object(startup.broker_module, "Broker", side_effect=AssertionError("legacy started broker")), \
                mock.patch.object(startup.handler, "main", return_value=19) as main:
            assert entry.main(verified_root=published.release, verified_metadata=published.meta) == 19
            main.assert_called_once_with()


@pytest.mark.parametrize("key,value", [
    ("GO_ACCOUNTS_PATH", "/other/profile/accounts.json"),
    ("GO_UPSTREAM_BASE", "http://127.0.0.1:1/v1"),
    ("GO_SHIM_PORT", "4149"),
    ("GO_WEIGHTS_PATH", "/other/weights.jsonl"),
    ("POOL_BROKER_DB", "/other/leases.sqlite"),
    ("POOL_BROKER_HOST", "other-native"),
])
def test_application_conflicting_owner_environment_refuses_before_broker(published, monkeypatch, key, value):
    clean_environment(monkeypatch, published)
    with loaded_entry(published) as entry:
        startup = inspect(entry, published)
        monkeypatch.setenv(key, value)
        with mock.patch.object(startup.broker_module, "Broker", side_effect=AssertionError("conflicting owner constructed broker")):
            with pytest.raises(ValueError, match="conflicts"):
                entry.main(**arguments(published, startup))


@pytest.mark.parametrize("fault", ["missing-db", "symlink-db", "hardlink-db", "account-symlink"])
def test_missing_or_aliased_original_owners_never_create_shadow_database(published, monkeypatch, fault):
    clean_environment(monkeypatch, published)
    with loaded_entry(published) as entry:
        startup = inspect(entry, published)
        db = startup.paths["db_path"]
        if fault == "missing-db":
            db.unlink()
        elif fault == "symlink-db":
            db.rename(db.with_suffix(".real"))
            db.symlink_to(db.with_suffix(".real"))
        elif fault == "hardlink-db":
            os.link(db, db.with_suffix(".linked"))
        else:
            account = startup.paths["accounts_path"]
            account.rename(account.with_suffix(".real"))
            account.symlink_to(account.with_suffix(".real"))
        with mock.patch.object(startup.broker_module, "Broker", side_effect=AssertionError("bad owner constructed broker")):
            with pytest.raises((ValueError, OSError)):
                entry.main(**arguments(published, startup))
        if fault == "missing-db":
            assert not db.exists()


def test_foreign_yaml_is_refused_before_broker_and_not_removed(published, monkeypatch):
    clean_environment(monkeypatch, published)
    with loaded_entry(published, clean_yaml=True) as entry:
        startup = inspect(entry, published)
        foreign = ModuleType("yaml")
        sys.modules["yaml"] = foreign
        with mock.patch.object(startup.broker_module, "Broker", side_effect=AssertionError("foreign yaml constructed broker")):
            with pytest.raises(ValueError):
                entry.main(**arguments(published, startup))
        assert sys.modules["yaml"] is foreign


def test_actual_entry_B_server_and_same_A_broker_settle_one_application(published, monkeypatch):
    clean_environment(monkeypatch, published)
    original_connect = socket.socket.connect
    original_bind = socket.socket.bind
    def only_local(function):
        def call(sock, address):
            assert isinstance(address, tuple) and address[0] == "127.0.0.1", "fixture attempted non-loopback network"
            return function(sock, address)
        return call
    monkeypatch.setattr(socket.socket, "connect", only_local(original_connect))
    monkeypatch.setattr(socket.socket, "bind", only_local(original_bind))
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        monkeypatch.setenv(name, "")
    monkeypatch.setenv("NO_PROXY", "127.0.0.1")
    posts = []
    class Upstream(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def respond(self, document):
            raw = json.dumps(document).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
        def do_GET(self):
            self.respond({"usage": {w: {"status": "ok", "percent": 1} for w in ("rolling", "weekly", "monthly")}})
        def do_POST(self):
            posts.append((self.path, self.rfile.read(int(self.headers["Content-Length"])), self.headers["Authorization"]))
            self.respond({"id": "native-entry-fixture", "model": "fixture-model",
                "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": "Native entry fixture answer."}}],
                "usage": {"prompt_tokens": 11, "completion_tokens": 7}})
    upstream = ThreadingHTTPServer(("127.0.0.1", 0), Upstream)
    upstream_thread = threading.Thread(target=lambda: upstream.serve_forever(poll_interval=0.01), daemon=True)
    upstream_thread.start()
    try:
        with loaded_entry(published, clean_yaml=True) as entry:
            startup = inspect(entry, published)
            go = startup.handler
            grant = dict(grant_id="macro-app", purpose="APPLICATION", enabled=True,
                principal_id="macro", credential_ref="MACRO_APPLICATION_TOKEN", admission_root="service:macro",
                caller_hosts=["vps"], workloads=["site_interactive"], pool="go", accounts=["account-a"],
                models=["fixture-model"], route="/v1/chat/completions", stream=False,
                expires_at=time.time()+120, max_turn_seconds=60, max_steps=2,
                qualification_ref="fixture:entry-composition", application_permission_ref="fixture:ordinary-inference")
            startup.paths["accounts_path"].write_text(json.dumps({"schema": "mastermind.provider_accounts.v1",
                "providers": {"go": {"enabled": True, "accounts": [{"name": "account-a", "per_account_cap": 2}]}},
                "application_grants": [grant]}))
            kwargs = arguments(published, startup)
            service = kwargs["application_services"][0]
            actual_router, actual_server = go.Router, go.make_server
            observed = {}
            def router(*args, **kw):
                result = actual_router(*args, **kw)
                # The only provider substitution: synthetic loopback upstream.
                result.upstream_base = "http://127.0.0.1:" + str(upstream.server_port) + "/v1"
                return result
            def server(router, port, **kw):
                broker = kw["lease_gateway"]._application_broker
                assert type(broker) is startup.broker_module.Broker
                assert Path(broker.db_path) == startup.paths["db_path"]
                assert broker.this_host == "fixture-native"
                assert kw["worker_capabilities_enabled"] is False
                assert kw["application_services"] == (service,)
                assert sys.modules["yaml"].safe_load("x: 1") == {"x": 1}
                result = actual_server(router, 0, **kw)
                def exercise():
                    thread = threading.Thread(target=lambda: ThreadingHTTPServer.serve_forever(result, poll_interval=0.01), daemon=True)
                    thread.start()
                    def request(path, body, headers):
                        connection = http.client.HTTPConnection("127.0.0.1", result.server_port, timeout=5)
                        try:
                            connection.request("POST", path, json.dumps(body), {
                                "Authorization": "Bearer " + service.credential,
                                "Content-Type": "application/json", **headers})
                            response = connection.getresponse()
                            return response.status, json.loads(response.read())
                        finally:
                            connection.close()
                    try:
                        status, answer = request("/v1/chat/completions",
                            {"model": "fixture-model", "messages": [{"role": "user", "content": "fixture"}], "stream": False},
                            {"X-MM-Application-Turn-ID": "entry-turn", "Idempotency-Key": "entry-step"})
                        assert status == 200, answer
                        assert answer["choices"][0]["message"]["content"] == "Native entry fixture answer."
                        status, close = request("/application-turns/close", {"turn_id": "entry-turn"}, {})
                        assert status == 200 and close["application"]["disposition"] == "closed"
                        observed["success"] = True
                    finally:
                        result.shutdown()
                        thread.join(2)
                        result.server_close()
                result.serve_forever = exercise
                return result
            helper = sys.modules["glm_shim"]
            try:
                with mock.patch.object(go, "Router", side_effect=router), \
                        mock.patch.object(go, "make_server", side_effect=server), \
                        mock.patch.object(sys.modules["pool_status"], "build_status", return_value={"pools": {}}):
                    assert entry.main(**kwargs) == 0
            finally:
                if helper._FILE_LOCK_FD is not None:
                    os.close(helper._FILE_LOCK_FD)
                    helper._FILE_LOCK_FD = None
            assert observed == {"success": True} and len(posts) == 1
            assert posts[0][2] == "Bearer fixture-provider-a"
            with sqlite3.connect(startup.paths["db_path"]) as db:
                assert db.execute("SELECT state FROM leases").fetchall() == [("released",)]
                assert db.execute("SELECT turn_id,request_id,state FROM application_requests").fetchall() == [("entry-turn", "entry-step", "terminal")]
            assert int((published.ext / "go_shim/shim.pid").read_text()) == os.getpid()
            assert "yaml" not in sys.modules
    finally:
        upstream.shutdown()
        upstream_thread.join(2)
        upstream.server_close()

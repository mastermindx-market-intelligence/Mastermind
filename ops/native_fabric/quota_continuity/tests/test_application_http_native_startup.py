"""Actual sealed generation, finite enrollment and B/A/H application ingress.

All state is disposable and all credentials are synthetic. The outbound
transport alone substitutes a numeric-loopback URL; source identity, original
enrollment, private loader, H compilation, B authentication and A settlement
remain real. These tests confer no provider application permission.
"""
import builtins
from dataclasses import replace
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
from types import SimpleNamespace
from unittest import mock

import pytest

from test_go_native_stage import builds, published, loaded_entry, ROOT, builder, g, installer
from test_go_native_install import go_owner
from test_native_launcher_successor_transition import source_owners, owner, historical
from test_go_service_enrollment import service_owner, prepare, unchanged_ingress
from test_go_service_startup import environment, inspect, boot


@pytest.fixture(scope="module")
def native_stage(builds):
    return builds.http


@pytest.fixture
def http_service_owner(service_owner, monkeypatch):
    case = service_owner
    home = case.root / "synthetic-home"
    home.mkdir(mode=0o700)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("LANE_LEASED", raising=False)
    monkeypatch.delenv("POOL_ACCOUNT", raising=False)
    case.provider_profile = home / ".bailian/config.json"
    case.provider_profile.parent.mkdir(mode=0o700)
    case.provider_profile.write_text(json.dumps({"token-plan": {"api_keys": [
        {"name": "account-a", "api_key": "fixture-bailian-a"}]}}))
    case.provider_profile.chmod(0o600)
    # Keep the real account eligibility owner enabled. A missing slots owner
    # or policy correctly refuses admission, even for a synthetic credential.
    (case.ext / "slots/bailian").mkdir(parents=True, mode=0o700)
    (case.ext / "bailian_policy.json").write_text(json.dumps({
        "per_key_cap": 2, "onpeak_per_key_cap": 2,
        "offpeak_window": {"start": "00:00", "end": "00:00", "tz": "UTC"}}))
    case.document["providers"]["bailian"] = {"enabled": True,
        "accounts": [{"name": "account-a", "per_account_cap": 2}]}
    case.accounts.write_text(json.dumps(case.document))
    case.specification["schema"] = installer.SERVICE_HTTP_SPEC_SCHEMA
    case.specification["scope"]["workload"] = "site_interactive"
    case.specification["grant"].update(pool="bailian", models=["qwen3.8-flash"], workloads=["site_interactive"])
    with loaded_entry(case.published, clean_yaml=True) as entry:
        startup = inspect(entry, case)
        recipe = entry.application_http_recipe(startup, "qwen3.8-flash")
        _, digest = startup.broker_module._application_http_recipe(recipe, pool="bailian", model="qwen3.8-flash")
    case.specification["application_recipe"] = recipe
    case.specification["grant"]["recipe_digest"] = digest
    return case


def test_http_v2_rejects_selected_purpose_before_enrollment(http_service_owner):
    case = http_service_owner
    assert case.specification["schema"] == installer.SERVICE_HTTP_SPEC_SCHEMA
    case.specification["scope"]["selection_purpose"] = {
        "purpose_id": "fixture-admin-text", "source_ref": "fixture:qualified-purpose",
        "task": {"task_class": "mechanical", "route_key": "fixture-admin-text",
                 "task_complexity": "C1_ROUTINE_BOUNDED", "needs": []}}
    with pytest.raises(ValueError, match="invalid service enrollment scope"):
        prepare(case)
    assert not case.service_bundle.exists()
    assert not case.intent.exists() and not case.binding.exists() and not case.service_receipt.exists()
    unchanged_ingress(case)


def test_http_build_adds_only_closed_three_and_keeps_historical_evidence_inert(builds):
    default = json.loads((builds.default / "native-manifest.json").read_bytes())
    # This fixture executes the canonical109 component, not the separate118
    # profile. Restore its exact accepted107 parent before historical checks.
    assert len(default) == 109
    parent = builder.before_memory_owner_integrity(default)
    assert len(parent) == 107
    assert set(default) - set(parent) == set(builder.MEMORY_OWNER_ADDITIONS) == {
        "ext/fabric_memory_view.py", "ext/protected_memory_economic.py"}
    assert {key for key in parent if parent[key] != default[key]} == set(builder.MEMORY_OWNER_DIGESTS)
    assert {key: default[key] for key in builder.MEMORY_OWNER_ADDITIONS} == builder.MEMORY_OWNER_ADDITIONS
    assert {key: default[key] for key in builder.MEMORY_OWNER_DIGESTS} == builder.MEMORY_OWNER_DIGESTS
    assert g.digest((json.dumps(parent, sort_keys=True, indent=2) + "\n").encode()) == builder.MEMORY_OWNER_PARENT_MANIFEST_SHA256
    baseline = json.loads((builds.application / "native-manifest.json").read_bytes())
    assert len(baseline) == 111
    assert {key: baseline[key] for key in default} == default
    assert set(baseline) - set(default) == {g.GO_ENTRY, g.GO_HANDLER}
    manifest = json.loads((builds.http / "native-manifest.json").read_bytes())
    assert len(manifest) == 114 and {key: manifest[key] for key in baseline} == baseline
    assert set(manifest) - set(baseline) == builder.HTTP_GENERATION_MEMBERS == g.HTTP_REQUIRED
    assert all(not path.endswith(".preimage") for path in manifest)
    sources = builder.application_http_sources(ROOT)
    for relative, (raw, source) in sources.items():
        assert (builds.http / "native-code-stage" / relative).read_bytes() == raw
        assert manifest[relative] == g.digest(raw)
    historical = (ROOT / "source/application_http_transports.py.preimage").read_bytes()
    assert hashlib.sha1(b"blob %d\0" % len(historical) + historical).hexdigest() == "a116d8c671594552dd5c14f46f91981cd7c15f43"
    assert g.digest(historical) != manifest["ext/application_http_transports.py"]
    realm_preimage = (ROOT / "source/codex_provider_realm.py.preimage").read_bytes()
    assert hashlib.sha1(b"blob %d\0" % len(realm_preimage) + realm_preimage).hexdigest() == "eeea4c0fafc7e6df5c534c731cb6046bbe4d3f37"
    document = json.loads(sources["ext/application_http_realms.v1.json"][0])
    assert [row["realm_id"] for row in document["drivers"]] == [
        "alibaba-token-plan-sg", "minimax-token-plan"]
    assert g._entrypoints_for(manifest) == g._entrypoints_for(baseline)


@pytest.mark.parametrize("member", sorted(g.HTTP_REQUIRED))
def test_partial_http_group_never_becomes_valid_generation(builds, member):
    manifest = json.loads((builds.http / "native-manifest.json").read_bytes())
    del manifest[member]
    with pytest.raises(ValueError, match="HTTP closure"):
        g.manifest_files(manifest)


def test_arbitrary_metadata_or_runtime_preimage_is_not_admitted():
    for relative in ("ext/application_http_realms.other.json", "ext/application_http_transports.py.preimage",
                     "ext/codex_provider_realm.py.preimage"):
        with pytest.raises(ValueError):
            g.file_name(relative)


def test_builder_uses_pinned_realm_evidence_and_rejects_tampering(monkeypatch):
    expected = builder.application_http_sources(ROOT)
    original_read = Path.read_bytes
    current_realm = ROOT.parents[2] / "control_plane/codex_provider_realm.py"
    historical_realm = ROOT / "source/codex_provider_realm.py.preimage"

    def guard_current(path):
        assert path != current_realm, "historical projection read mutable current realm"
        return original_read(path)

    monkeypatch.setattr(Path, "read_bytes", guard_current)
    assert builder.application_http_sources(ROOT) == expected

    def tamper_historical(path):
        raw = guard_current(path)
        return raw + b"\n# altered evidence\n" if path == historical_realm else raw

    monkeypatch.setattr(Path, "read_bytes", tamper_historical)
    with pytest.raises(ValueError, match="source_blob_mismatch"):
        builder.application_http_sources(ROOT)


def test_builder_executes_exact_captured_reader_not_cached_same_path_object(monkeypatch):
    expected = builder.application_http_sources(ROOT)
    poisoned = SimpleNamespace(__file__=str(ROOT / "rollout/application_http_realm_projection.py"),
        compile_projection_bytes=lambda _: pytest.fail("used foreign cached compiler"))
    monkeypatch.setitem(sys.modules, "application_http_realm_projection", poisoned)
    assert builder.application_http_sources(ROOT) == expected


@pytest.mark.parametrize("fault", ["fourth-hash", "missing", "extra", "captured-a3"])
def test_base_validator_accepts_only_exact_captured_three(builds, fault):
    manifest = json.loads((builds.default / "native-manifest.json").read_bytes())
    dependencies = {name: manifest["ext/" + name] for name in builder.GO_APPLICATION_DEPENDENCIES}
    if fault == "fourth-hash":
        manifest["ext/remote_sub.sh"] = "1" * 64
    elif fault == "missing":
        del manifest["ext/remote_sub.sh"]
    elif fault == "extra":
        manifest["ext/extra.py"] = "1" * 64
    else:
        dependencies["lease_broker.py"] = "1" * 64
    with pytest.raises(ValueError):
        builder.validate_go_base_manifest(manifest, dependencies)


def test_flat_inspection_uses_sealed_metadata_without_repository_or_private_effects(published):
    original_import = builtins.__import__
    def no_repository(name, *args, **kwargs):
        assert not name.startswith("control_plane"), "flat runtime imported repository owner"
        return original_import(name, *args, **kwargs)
    with loaded_entry(published, clean_yaml=True) as entry, \
            mock.patch.object(builtins, "__import__", side_effect=no_repository), \
            mock.patch.object(sqlite3, "connect", side_effect=AssertionError("inspection opened database")), \
            mock.patch.object(socket.socket, "connect", side_effect=AssertionError("inspection connected")), \
            mock.patch.object(socket.socket, "bind", side_effect=AssertionError("inspection listened")):
        startup = entry.inspect(verified_root=published.release, verified_metadata=published.meta)
        assert startup.http_projection_sha256 == published.manifest["ext/application_http_realms.v1.json"]
        assert len(startup.http_recipes) == 2
        assert startup.bailian_keys.__file__ == str(published.release / "ext/bailian_keys.py")
        with mock.patch.object(startup.bailian_keys, "_codex_key_value", side_effect=AssertionError("inspection loaded key")), \
                mock.patch.object(startup.http_transports, "_shared_realm", side_effect=AssertionError("dynamic fallback")):
            again = entry.inspect(verified_root=published.release, verified_metadata=published.meta)
            assert again.http_projection == startup.http_projection
            for kind in (startup.http_transports.BailianResponsesDriver, startup.http_transports.MiniMaxResponsesDriver):
                driver = kind(transport=lambda _: pytest.fail("pure constructor sent"),
                    realm_projection=startup.http_projection, projection_sha256=startup.http_projection_sha256)
                assert driver.identity.realm_id in {"alibaba-token-plan-sg", "minimax-token-plan"}
                for args in ({"realm_projection": startup.http_projection},
                             {"projection_sha256": startup.http_projection_sha256},
                             {"realm_projection": startup.http_projection + b" ", "projection_sha256": startup.http_projection_sha256}):
                    with pytest.raises(startup.http_transports.TransportRefused, match="sealed_realm_refused"):
                        kind(transport=lambda _: pytest.fail("refusal sent"), **args)


def test_sealed_projection_tamper_refuses_at_generation_and_startup(published):
    path = published.release / "ext/application_http_realms.v1.json"
    original = path.read_bytes()
    path.chmod(0o755)
    path.write_bytes(original + b" ")
    path.chmod(0o555)
    with pytest.raises(ValueError):
        g.verify(published.store, published.release.name)
    with loaded_entry(published) as entry, pytest.raises(ValueError, match="source identity"):
        entry.inspect(verified_root=published.release, verified_metadata=published.meta)


def test_http_enrollment_uses_original_finite_owner_and_never_reads_key(http_service_owner):
    case = http_service_owner
    with mock.patch.object(sqlite3, "connect", side_effect=AssertionError("prepare opened database")):
        plan = prepare(case)
    assert plan["schema"] == "native-go-service-enrollment.v2"
    assert plan["application_recipe"] == case.specification["application_recipe"]
    with mock.patch.object(installer.secrets, "token_urlsafe", return_value="fixture-service-token-" + "x" * 48) as mint:
        receipt = installer.apply_go_service_enrollment(case.service_bundle)
        assert mint.call_count == 1
        assert installer.apply_go_service_enrollment(case.service_bundle) == receipt
        assert mint.call_count == 1
    assert receipt["schema"] == "native-go-service-enrollment-completed.v2"
    assert receipt["application_recipe_digest"] == case.specification["grant"]["recipe_digest"]
    assert receipt["source_projection_sha256"] == plan["application_recipe"]["source_projection_sha256"]
    unchanged_ingress(case)


def test_historical_auth_is_independent_of_new_projection_and_removed_model(http_service_owner):
    case = http_service_owner
    prepare(case)
    installer.apply_go_service_enrollment(case.service_bundle)
    with loaded_entry(case.published, clean_yaml=True) as entry:
        startup = inspect(entry, case)
        old = entry.load_completed_application_startup(startup)
        # A future valid source artifact can have a different byte commitment.
        # This fixture supplies that already-verified metadata boundary; it
        # does not claim the current deterministic builder emits these bytes.
        raw = startup.http_projection + b"\n"
        digest = g.digest(raw)
        recipes = tuple(startup.broker_module._application_json(dict(json.loads(row),
            source_projection_sha256=digest)) for row in startup.http_recipes)
        current = replace(startup, http_projection=raw, http_projection_sha256=digest, http_recipes=recipes)
        with mock.patch.object(entry, "application_http_recipe", side_effect=AssertionError("historical auth consulted current catalogue")):
            assert entry.load_completed_application_startup(current) == old
            document = json.loads(case.binding.read_bytes())
            document["application_recipe"]["model"] = "historically-retired-model"
            # Shape-only historical parsing accepts a removed model; the REAL
            # completed reader still checks the unchanged signed-off receipt.
            assert entry.validate_application_service_document(current, document)[0] == old[0]
        with mock.patch.object(current.bailian_keys, "_codex_key_value", side_effect=AssertionError("binding loaded credential")):
            binding = entry._application_http_binding(current, old[3])
            assert binding.source_projection_sha256 == digest
            assert binding.recipe("qwen3.8-flash") != json.loads(old[3].recipe_json)
        document = json.loads(case.binding.read_bytes())
        document["application_recipe"]["source_projection_sha256"] = "0" * 64
        case.binding.write_text(json.dumps(document))
        with pytest.raises(ValueError, match="receipt"):
            entry.load_completed_application_startup(current)


@pytest.mark.parametrize("boundary", ["private", "binding", "accounts", "receipt"])
def test_interrupted_http_enrollment_keeps_one_original_credential(http_service_owner, boundary):
    case = http_service_owner
    prepare(case)
    original, original_replace, hit = g.atomic_bytes, installer.os.replace, []
    def interrupted(path, raw, mode):
        original(path, raw, mode)
        path = Path(path)
        kind = ("private" if path.name == installer._SERVICE_PRIVATE else
                "receipt" if path == case.service_receipt else None)
        if kind == boundary and not hit:
            hit.append(True)
            raise OSError("fixture after " + boundary)
    def interrupted_replace(source, destination, *args, **kwargs):
        original_replace(source, destination, *args, **kwargs)
        kind = "binding" if Path(destination) == case.binding else "accounts" if Path(destination) == case.accounts else None
        if kind == boundary and not hit:
            hit.append(True)
            raise OSError("fixture after original target rename " + boundary)
    with mock.patch.object(g, "atomic_bytes", side_effect=interrupted), \
            mock.patch.object(installer.os, "replace", side_effect=interrupted_replace), \
            mock.patch.object(installer.secrets, "token_urlsafe", return_value="fixture-http-token-" + "y" * 48) as mint:
        with pytest.raises(OSError, match="fixture"):
            installer.apply_go_service_enrollment(case.service_bundle)
        assert mint.call_count == 1
    with mock.patch.object(installer.secrets, "token_urlsafe", side_effect=AssertionError("reminted")):
        if boundary == "private":
            with pytest.raises(ValueError, match="commitment"):
                installer.apply_go_service_enrollment(case.service_bundle)
        else:
            receipt = installer.apply_go_service_enrollment(case.service_bundle)
            assert receipt["application_recipe_digest"] == case.specification["grant"]["recipe_digest"]
    assert hit


def test_actual_entry_enrollment_loader_http_and_same_broker_complete_once(http_service_owner, monkeypatch):
    case = http_service_owner
    prepare(case)
    installer.apply_go_service_enrollment(case.service_bundle)
    environment(monkeypatch, case)
    with historical.numeric_loopback_network() as loopback:
        original_connect, original_bind = socket.socket.connect, socket.socket.bind
        def local_only(function):
            def call(sock, address):
                assert isinstance(address, tuple) and address[0] == "127.0.0.1"
                return function(sock, address)
            return call
        monkeypatch.setattr(socket.socket, "connect", local_only(original_connect))
        monkeypatch.setattr(socket.socket, "bind", local_only(original_bind))
        def numeric_name(address):
            assert address == "127.0.0.1"
            return "fixture-loopback"
        monkeypatch.setattr(socket, "getfqdn", numeric_name)
        posts, reads = [], []
        class Upstream(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_POST(self):
                posts.append((self.path, self.rfile.read(int(self.headers["Content-Length"])), self.headers["Authorization"]))
                with sqlite3.connect(case.ext / "broker/leases.sqlite") as db:
                    assert db.execute("SELECT state FROM application_requests").fetchall() == [("pending",)]
                raw = json.dumps({"id": "fixture-http", "model": "qwen3.8-flash", "status": "completed",
                    "output": [{"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Native HTTP fixture answer."}]}],
                    "usage": {"input_tokens": 11, "output_tokens": 7}}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
        upstream = ThreadingHTTPServer(("127.0.0.1", 0), Upstream)
        loopback["ports"].add(upstream.server_port)
        loopback["post_urls"].add("http://127.0.0.1:" + str(upstream.server_port) + "/v1/responses")
        thread = threading.Thread(target=lambda: upstream.serve_forever(poll_interval=0.01), daemon=True)
        thread.start()
        try:
            with loaded_entry(case.published, clean_yaml=True) as entry:
                startup = inspect(entry, case)
                go = startup.handler
                original_transport, original_server = go.application_http_transport, go.make_server
                original_key = startup.bailian_keys._codex_key_value
                def credential(account):
                    reads.append(account)
                    return original_key(account)
                def transport(request):
                    observed = original_transport(replace(request, url="http://127.0.0.1:" + str(upstream.server_port) + "/v1/responses"))
                    return replace(observed, final_url=request.url)
                observed = []
                def server(router, port, **kwargs):
                    assert Path(kwargs["lease_gateway"]._application_broker.db_path) == startup.paths["db_path"]
                    broker = kwargs["lease_gateway"]._application_broker
                    assert broker.external_gates is True
                    assert [row["name"] for row in broker.grantable_accounts("bailian")] == ["account-a"]
                    assert kwargs["application_http_binding"].driver.identity.endpoint.endswith("/responses")
                    service = kwargs["application_services"][0]
                    result = original_server(router, 0, **kwargs)
                    loopback["ports"].add(result.server_port)
                    def exercise():
                        serving = threading.Thread(target=lambda: ThreadingHTTPServer.serve_forever(result, poll_interval=0.01), daemon=True)
                        serving.start()
                        def request(path, body, headers):
                            client = http.client.HTTPConnection("127.0.0.1", result.server_port, timeout=5)
                            try:
                                client.request("POST", path, json.dumps(body), {"Authorization": "Bearer " + service.credential,
                                    "Content-Type": "application/json", **headers})
                                response = client.getresponse()
                                return response.status, json.loads(response.read())
                            finally:
                                client.close()
                        try:
                            headers = {"X-MM-Application-Turn-ID": "http-entry-turn", "Idempotency-Key": "http-entry-step",
                                "X-MM-Application-Recipe-Digest": case.specification["grant"]["recipe_digest"]}
                            payload = {"model": "qwen3.8-flash", "messages": [{"role": "system", "content": "Fixture system."},
                                {"role": "user", "content": "Fixture question."}], "max_tokens": 128, "stream": False}
                            status, body = request("/v1/chat/completions", payload, headers)
                            assert status == 200, body
                            assert body["model"] == "qwen3.8-flash"
                            assert body["choices"][0]["message"]["content"] == "Native HTTP fixture answer."
                            assert body["usage"] == {"prompt_tokens": 11, "completion_tokens": 7}
                            # Original recovery must precede current grant and key.
                            document = json.loads(case.accounts.read_bytes())
                            document["application_grants"][0]["enabled"] = False
                            case.accounts.write_text(json.dumps(document))
                            case.provider_profile.unlink()
                            status, body = request("/v1/chat/completions", payload, headers)
                            assert status == 409 and body["application"]["disposition"] == "terminal_receipt_only"
                            status, body = request("/application-turns/close", {"turn_id": "http-entry-turn"}, {})
                            assert status == 200 and body["application"]["disposition"] == "closed"
                            observed.append(True)
                        finally:
                            result.shutdown()
                            serving.join(2)
                            result.server_close()
                    result.serve_forever = exercise
                    return result
                helper = sys.modules["glm_shim"]
                try:
                    with mock.patch.object(go, "application_http_transport", side_effect=transport), \
                            mock.patch.object(go, "make_server", side_effect=server), \
                            mock.patch.object(startup.bailian_keys, "_codex_key_value", side_effect=credential), \
                            mock.patch.object(go.Router, "reserve_application_account", side_effect=AssertionError("Go quota used")), \
                            mock.patch.object(go.Router, "_usage_row", side_effect=AssertionError("Go ledger used")), \
                            mock.patch.object(sys.modules["pool_status"], "build_status", return_value={"pools": {}}):
                        assert boot(entry, case) == 0
                finally:
                    if helper._FILE_LOCK_FD is not None:
                        os.close(helper._FILE_LOCK_FD)
                        helper._FILE_LOCK_FD = None
                assert observed == [True] and len(posts) == 1 and reads == ["account-a", "account-a"]
                assert posts[0][2] == "Bearer fixture-bailian-a"
                assert json.loads(posts[0][1])["max_output_tokens"] == 128
                with sqlite3.connect(case.ext / "broker/leases.sqlite") as db:
                    assert db.execute("SELECT state FROM leases").fetchall() == [("released",)]
                    assert db.execute("SELECT state FROM application_requests").fetchall() == [("terminal",)]
                # A later startup still authenticates recovery after key removal.
                with mock.patch.object(go, "main", return_value=31) as main:
                    assert boot(entry, case) == 31
                    assert main.call_args.kwargs["application_http_binding"] is not None
        finally:
            upstream.shutdown()
            thread.join(2)
            upstream.server_close()


def test_loopback_fixture_exception_keeps_installer_guards(service_owner):
    assert historical._active
    with historical.numeric_loopback_network() as allowed:
        allowed["ports"].add(12345)
        allowed["post_urls"].add("http://127.0.0.1:12345/v1/responses")
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            historical._audit("socket.bind", (sock, ("127.0.0.1", 0)))
            historical._audit("socket.connect", (sock, ("127.0.0.1", 12345)))
            historical._audit("socket.getaddrinfo", ("127.0.0.1", 12345, 0, socket.SOCK_STREAM, 0))
            historical._audit("urllib.Request", ("http://127.0.0.1:12345/v1/responses", b"", {}, "POST"))
            denied = [
                ("socket.__new__", (None, socket.AF_INET6, socket.SOCK_STREAM, 0)),
                ("socket.__new__", (None, socket.AF_INET, socket.SOCK_DGRAM, 0)),
                ("socket.bind", (sock, ("0.0.0.0", 0))),
                ("socket.connect", (sock, ("192.0.2.1", 12345))),
                ("socket.connect", (sock, ("127.0.0.1", 12346))),
                ("socket.getaddrinfo", ("localhost", 12345, 0, socket.SOCK_STREAM, 0)),
                ("socket.gethostbyaddr", ("127.0.0.1",)),
                ("urllib.Request", ("http://127.0.0.1:12345/other", b"", {}, "POST")),
                ("urllib.Request", ("http://127.0.0.1:12345/v1/responses", None, {}, "GET")),
                ("subprocess.Popen", ("fixture", ["fixture"], None, None)),
                ("open", (historical._private[0] + "/fixture", "r", 0)),
            ]
            with mock.patch.object(historical, "_expected", True):
                for event, args in denied:
                    with pytest.raises(historical.FixtureBoundaryError):
                        historical._audit(event, args)
    with mock.patch.object(historical, "_expected", True), pytest.raises(historical.FixtureBoundaryError):
        socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    assert historical._loopback_network is None and historical._active

"""Two explicit roles through the same finite E and actual Go B/A."""
import copy
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import time
from pathlib import Path
import socket
import sqlite3
import sys
import threading
from unittest import mock

import pytest

from test_go_native_stage import builds, native_stage, loaded_entry, installer, ROOT, g
from test_go_native_install import go_owner
from test_native_launcher_successor_transition import source_owners, owner, historical
from test_go_service_enrollment import service_owner, set_specification, prepare_set, reseal_modified_entry_for_disposable_fixtures
from test_go_service_startup import environment, inspect, boot

# The changed E is sealed by the enrollment fixture; historical source guard
# accepts that generated manifest during this process only, never on disk.

def admin_predecessor(case, schema):
    role = copy.deepcopy(case.specification)
    purpose = {"purpose_id": "fixture-admin", "source_ref": "fixture:admin",
        "task": {"task_class": "mechanical", "route_key": "fixture-admin",
                 "task_complexity": "C1_ROUTINE_BOUNDED", "needs": []}}
    if schema != "v1":
        role["schema"] = installer.SERVICE_SELECTED_SPEC_SCHEMA
        role["scope"]["selection_purpose"] = purpose
    if schema == "v4":
        role["schema"] = installer.SERVICE_ADMIN_SPEC_SCHEMA
        role["scope"]["admin_pool_view"] = True
    installer.apply_go_service_enrollment(installer.prepare_go_service_enrollment(
        case.go_bundle, role, case.service_bundle)["digest"] and case.service_bundle)
    return role


@pytest.mark.parametrize("schema", ["v1", "v3", "v4"])
def test_completed_admin_successor(service_owner, monkeypatch, schema):
    sys.path.insert(0, str(ROOT / "tests"))
    case = service_owner
    role = admin_predecessor(case, schema)
    predecessor = json.loads(case.binding.read_bytes())
    case.service_bundle.rename(case.root / "completed-admin")
    case.service_bundle = case.root / "service-set-review"
    set_specification(case, successor=True)
    case.service_set["admin"] = role
    plan = prepare_set(case)
    assert plan["predecessor"] is True and plan["scopes"] == [role["scope"], case.service_set["text"]["scope"]]
    receipt = installer.apply_go_service_enrollment(case.service_bundle)
    document = json.loads(case.binding.read_bytes())
    assert document["credentials"][0] == predecessor["credential"]
    assert document["scopes"][0] == predecessor["scope"] == receipt["scopes"][0]
    accounts = json.loads(case.accounts.read_bytes())
    assert role["grant"] in accounts["application_grants"]
    assert case.service_set["text"]["grant"] in accounts["application_grants"]
    assert len(accounts["application_grants"]) == 2
    assert installer.reconcile_go_service_enrollment(case.service_bundle) == receipt
    environment(monkeypatch, case)
    with loaded_entry(case.published, clean_yaml=True) as entry:
        startup = inspect(entry, case)
        services, host, profile = entry.load_completed_application_startup(startup)
        assert len(services) == 2 and host == "fixture-native" and profile == case.profile
        with mock.patch.object(startup.handler, "main", return_value=47) as main:
            assert boot(entry, case) == 47
            kwargs = main.call_args.kwargs
            assert kwargs["application_services"] == services
            assert Path(kwargs["application_broker"].db_path) == startup.paths["db_path"]
            assert Path(kwargs["application_broker"].lock_path) == startup.paths["lock_path"]
            assert Path(kwargs["application_broker"].accounts_path) == startup.paths["accounts_path"]


@pytest.mark.parametrize("schema", ["v4"])
def test_same_listener_recovery_admission_close(service_owner, monkeypatch, schema):
    """Recover pre-transition Admin effects and admit Text through actual E/B/A."""
    sys.path.insert(0, str(ROOT / "tests"))
    case = service_owner
    role = admin_predecessor(case, schema)
    old_credential = json.loads(case.binding.read_bytes())["credential"]
    environment(monkeypatch, case)
    policy = {"routing": {"execute_order": ["minimax", "glm-flash", "bailian", "grok", "cursor", "go"],
                          "judgment_order": ["glm-5.3", "grok", "cursor", "fable", "go"],
                          "acceptance_floor": "0.6 over last 20"},
              "pools": {"go": {"enabled": True, "task_classes": ["mechanical", "review", "build"],
                                "worker_models": ["fixture-model"], "default_model": "fixture-model"},
                        "glm": {"enabled": True, "models": {"executor": "glm-5.3-flash"}},
                        "grok": {"enabled": True, "windows": {"weekly": {}}},
                        "minimax": {"enabled": True}, "bailian": {"enabled": True}, "cursor": {"enabled": True}}}
    case.accounts.parent.joinpath("pools.yaml").write_text(json.dumps(policy))
    case.accounts.parent.joinpath("ledger.jsonl").write_text("")
    payload = {"model": "fixture-model", "messages": [{"role": "user", "content": "fixture"}], "stream": False}
    db = case.ext / "broker/leases.sqlite"
    lock = case.ext / "broker/leases.lock"
    owner_inodes = (db.stat().st_ino, lock.stat().st_ino)
    usage_path = case.ext / "go_shim/usage.jsonl"
    def rows(table, principal=None):
        with sqlite3.connect(db) as connection:
            connection.row_factory = sqlite3.Row
            if principal is None:
                found = connection.execute("SELECT * FROM " + table + " ORDER BY rowid").fetchall()
            else:
                found = connection.execute("SELECT * FROM " + table + " WHERE principal_id=? ORDER BY rowid",
                    (principal,)).fetchall()
            return [dict(row) for row in found]
    def usage():
        return [json.loads(line) for line in usage_path.read_text().splitlines()] if usage_path.exists() else []

    with historical.numeric_loopback_network() as loopback:
        original_connect, original_bind = socket.socket.connect, socket.socket.bind
        def local_only(function):
            def call(sock, address):
                assert isinstance(address, tuple) and address[0] == "127.0.0.1"
                return function(sock, address)
            return call
        monkeypatch.setattr(socket.socket, "connect", local_only(original_connect))
        monkeypatch.setattr(socket.socket, "bind", local_only(original_bind))
        monkeypatch.setattr(socket, "getfqdn", lambda address: "fixture-loopback")
        posts = []
        class Upstream(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_POST(self):
                posts.append(self.rfile.read(int(self.headers["Content-Length"])))
                raw = json.dumps({"id": "set-proof", "model": "fixture-model",
                    "choices": [{"message": {"role": "assistant", "content": "one admitted text effect"}}],
                    "usage": {"prompt_tokens": 3, "completion_tokens": 2}}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
        upstream = ThreadingHTTPServer(("127.0.0.1", 0), Upstream)
        loopback["ports"].add(upstream.server_port)
        loopback["post_urls"].add("http://127.0.0.1:" + str(upstream.server_port) + "/fixture-model")
        serving = threading.Thread(target=lambda: upstream.serve_forever(poll_interval=0.01), daemon=True)
        serving.start()

        def run_listener(exercise):
            with loaded_entry(case.published, clean_yaml=True) as entry:
                startup = inspect(entry, case)
                go = startup.handler
                original_server, original_exchange = go.make_server, go.Router._application_exchange
                def exchange(router, request, **kwargs):
                    request.full_url = "http://127.0.0.1:" + str(upstream.server_port) + "/" + json.loads(request.data)["model"]
                    return original_exchange(router, request, **kwargs)
                def refresh(router, account, force=False, require_fresh=False):
                    snapshot = {window: {"status": "ok", "percent": 0.0} for window in go.WINDOWS}
                    router.snapshots[account] = snapshot
                    router.snapshot_at[account] = router.now()
                    return snapshot
                observed = []
                def server(router, port, **kwargs):
                    result = original_server(router, 0, **kwargs)
                    loopback["ports"].add(result.server_port)
                    assert Path(router.usage_path) == usage_path
                    assert (db.stat().st_ino, lock.stat().st_ino) == owner_inodes
                    def serve():
                        thread = threading.Thread(target=lambda: ThreadingHTTPServer.serve_forever(
                            result, poll_interval=0.01), daemon=True)
                        thread.start()
                        def request(service, path, body, turn=None, request_id="step1"):
                            headers = {"Authorization": "Bearer " + service.credential, "Content-Type": "application/json"}
                            if turn is not None:
                                headers.update({"X-MM-Application-Turn-ID": turn, "Idempotency-Key": request_id})
                            client = http.client.HTTPConnection("127.0.0.1", result.server_port, timeout=5)
                            try:
                                client.request("POST", path, json.dumps(body), headers)
                                response = client.getresponse()
                                return response.status, json.loads(response.read())
                            finally:
                                client.close()
                        try:
                            exercise(kwargs["application_services"], kwargs["lease_gateway"], request)
                            observed.append(True)
                        finally:
                            result.shutdown()
                            thread.join(2)
                            result.server_close()
                    result.serve_forever = serve
                    return result
                try:
                    with mock.patch.object(go, "make_server", side_effect=server), \
                            mock.patch.object(go.Router, "_application_exchange", exchange), \
                            mock.patch.object(go.Router, "refresh", refresh):
                        assert boot(entry, case) == 0
                    assert observed == [True]
                finally:
                    helper = sys.modules["glm_shim"]
                    if helper._FILE_LOCK_FD is not None:
                        os.close(helper._FILE_LOCK_FD)
                        helper._FILE_LOCK_FD = None

        def before_transition(services, gateway, request):
            assert len(services) == 1 and services[0].credential == old_credential
            admin = services[0]
            status, body = request(admin, "/v1/chat/completions", payload, "shared-terminal")
            assert status == 200, body
            assert len(posts) == len(usage()) == 1
            # Actual B/A admission and durable preparation model a process exit
            # immediately before the provider handoff. No direct SQLite writes.
            scope = {"workload": admin.workload, "turn_id": "admin-pending", "pool": "go", "model": "fixture-model"}
            binding = gateway.begin_application(scope, principal_id=admin.principal_id, host=admin.host,
                expected_credential_ref=admin.credential_ref)
            assert binding["ok"] and binding["disposition"] == "admitted"
            permit = gateway.prepare_application(binding["token"], principal_id=admin.principal_id,
                host=admin.host, turn_id="admin-pending", request_id="step1",
                path="/v1/chat/completions", payload=payload)
            assert permit["dispatch_permitted"] is True
            assert {row["state"] for row in rows("application_requests", admin.principal_id)} == {"pending", "terminal"}
            assert len(posts) == len(usage()) == 1

        try:
            run_listener(before_transition)
            old_admin_rows = rows("application_requests", role["scope"]["principal_id"])
            usage_before = usage_path.read_bytes()
            old_bundle = case.service_bundle
            case.service_bundle = case.root / "service-set-review"
            set_specification(case, successor=True)
            case.service_set["admin"] = role
            accounts = json.loads(case.accounts.read_bytes())
            accounts["application_grants"][0]["enabled"] = False
            case.accounts.write_text(json.dumps(accounts))
            retained_grant = copy.deepcopy(accounts["application_grants"][0])
            prepare_set(case)
            installer.apply_go_service_enrollment(case.service_bundle)
            assert json.loads(case.accounts.read_bytes())["application_grants"][0] == retained_grant
            with mock.patch.object(g, "atomic_bytes", side_effect=AssertionError("stale Admin bundle wrote")), pytest.raises(ValueError):
                installer.apply_go_service_enrollment(old_bundle)

            def after_transition(services, gateway, request):
                assert len(services) == 2
                admin, text = services
                assert admin.credential == old_credential and text.credential != old_credential
                status, body = request(admin, "/v1/chat/completions", payload, "shared-terminal")
                assert status == 409 and body["application"]["disposition"] == "terminal_receipt_only"
                status, body = request(admin, "/v1/chat/completions", payload, "admin-pending")
                assert status == 409 and body["application"]["disposition"] == "pending"
                assert rows("application_requests", admin.principal_id) == old_admin_rows
                assert usage_path.read_bytes() == usage_before and len(posts) == 1
                status, body = request(admin, "/application-turns/close", {"turn_id": "shared-terminal"})
                assert status == 200 and body["application"]["disposition"] == "closed"
                # Equal turn/request IDs belong to distinct authenticated roles.
                status, body = request(text, "/v1/chat/completions", payload, "shared-terminal")
                assert status == 200, body
                assert body["choices"][0]["message"]["content"] == "one admitted text effect"
                assert len(posts) == len(usage()) == 2
                assert all(row["model"] == "fixture-model" and row["input"] == 3 and row["output"] == 2
                    and row["usage_state"] == "known" and row["est_usd"] is None for row in usage())
                unchanged = (rows("application_turns", admin.principal_id), rows("application_requests", admin.principal_id),
                    rows("leases"), usage_path.read_bytes(), len(posts))
                request(text, "/application-turns/close", {"turn_id": "admin-pending"})
                assert (rows("application_turns", admin.principal_id), rows("application_requests", admin.principal_id),
                    rows("leases"), usage_path.read_bytes(), len(posts)) == unchanged
                status, body = request(admin, "/v1/chat/completions", payload, "admin-fresh-refused")
                assert status == 409 and body["application"]["disposition"] == "refused"
                status, body = request(text, "/v1/chat/completions", payload, "shared-terminal")
                assert status == 409 and body["application"]["disposition"] == "terminal_receipt_only"
                status, body = request(text, "/application-turns/close", {"turn_id": "shared-terminal"})
                assert status == 200 and body["application"]["disposition"] == "closed"
                status, body = request(admin, "/application-turns/close", {"turn_id": "admin-pending"})
                assert status == 409 and body["application"]["disposition"] in {"pending", "effect_unknown"}
                assert rows("application_requests", admin.principal_id) == old_admin_rows
                assert len(posts) == len(usage()) == 2
            run_listener(after_transition)
        finally:
            upstream.shutdown()
            serving.join(2)
            upstream.server_close()



def test_initial_set_mints_two_stable_nonoverlapping_grant_tokens_once(service_owner):
    case = service_owner
    set_specification(case)
    plan = prepare_set(case)
    assert plan["predecessor"] is False
    with mock.patch.object(installer.secrets, "token_urlsafe", wraps=installer.secrets.token_urlsafe) as minted:
        receipt = installer.apply_go_service_enrollment(case.service_bundle)
        assert minted.call_count == 2
    first = json.loads(case.binding.read_bytes())
    account_before = json.loads(case.accounts.read_bytes())
    assert first["credentials"][0] != first["credentials"][1]
    assert first["scopes"][0]["credential_ref"] != first["scopes"][1]["credential_ref"]
    assert {tuple(scope[key] for key in ("principal_id", "caller_host", "workload"))
            for scope in first["scopes"]} == {
        ("macro-admin", "fixture-vps", "admin-site-interactive"),
        ("mastermind-text", "m2studio", "mastermind-site-batch")}
    assert account_before["application_grants"] == [case.service_set["admin"]["grant"],
                                                    case.service_set["text"]["grant"]]
    with mock.patch.object(installer.secrets, "token_urlsafe", side_effect=AssertionError("replay reminted")), \
            mock.patch.object(g, "atomic_bytes", side_effect=AssertionError("completed set rewrote")):
        assert installer.apply_go_service_enrollment(case.service_bundle) == receipt
        assert installer.reconcile_go_service_enrollment(case.service_bundle) == receipt
    assert json.loads(case.binding.read_bytes()) == first
    assert json.loads(case.accounts.read_bytes()) == account_before


def test_initial_set_is_exactly_two_roles_and_never_infers_fields(service_owner, fault="caller"):
    case = service_owner
    set_specification(case)
    case.service_set["text"]["scope"]["caller_host"] = case.service_set["admin"]["scope"]["caller_host"]
    with pytest.raises(ValueError, match="invalid service enrollment scope|service enrollment mapping differs"):
        prepare_set(case)
    assert not case.binding.exists() and not case.intent.exists()

def prepare_transition(case, predecessor):
    old_bundle = None
    old_credential = None
    if predecessor:
        role = admin_predecessor(case, "v4")
        old_bundle = case.service_bundle
        old_credential = json.loads(case.binding.read_bytes())["credential"]
        case.service_bundle = case.root / "service-set-review"
        set_specification(case, successor=True)
        case.service_set["admin"] = role
    else:
        set_specification(case)
    return prepare_set(case), old_bundle, old_credential


@pytest.mark.parametrize("predecessor", [False, True])
@pytest.mark.parametrize("boundary", ["private", "private-progress", "intent-prepare", "intent", "intent-progress",
    "binding-prepare", "binding", "binding-progress", "accounts-prepare", "accounts", "accounts-progress",
    "receipt-prepare", "receipt", "receipt-progress"])
def test_service_set_original_interruption_custody(service_owner, predecessor, boundary):
    case = service_owner
    plan, _, old_credential = prepare_transition(case, predecessor)
    paths = {"intent": case.intent, "binding": case.binding, "accounts": case.accounts, "receipt": case.service_receipt}
    targets = dict(paths, private=case.service_bundle / installer._SERVICE_PRIVATE)
    targets["private-progress"] = case.store / "bootstrap" / (plan["digest"] + ".service-private.json")
    for name in paths:
        targets[name + "-prepare"] = case.store / "bootstrap" / (plan["digest"] + ".service-" + name + "-prepared.json")
        targets[name + "-progress"] = case.store / "bootstrap" / (plan["digest"] + ".service-" + name + ".json")
    originals = {name: (path.read_bytes(), path.stat().st_ino) if path.exists() else None for name, path in paths.items()}
    original_write, original_replace = g.atomic_bytes, os.replace
    hit = []
    def written(path, raw, mode):
        original_write(path, raw, mode)
        if Path(path) == targets[boundary] and boundary not in paths and not hit:
            hit.append(boundary)
            raise OSError("fixture original write acknowledgement lost")
    def renamed(source, target):
        original_replace(source, target)
        if boundary in paths and Path(target) == targets[boundary] and not hit:
            hit.append(boundary)
            raise OSError("fixture original rename acknowledgement lost")
    with mock.patch.object(g, "atomic_bytes", side_effect=written), \
            mock.patch.object(os, "replace", side_effect=renamed), \
            mock.patch.object(installer.secrets, "token_urlsafe", wraps=installer.secrets.token_urlsafe) as minted, \
            pytest.raises(OSError, match="fixture original"):
        installer.apply_go_service_enrollment(case.service_bundle)
    assert hit == [boundary] and minted.call_count == (1 if predecessor else 2)
    with mock.patch.object(installer.secrets, "token_urlsafe", side_effect=AssertionError("original reminted")):
        if boundary == "private":
            for action in (installer.apply_go_service_enrollment, installer.reconcile_go_service_enrollment):
                with mock.patch.object(g, "atomic_bytes", side_effect=AssertionError("uncommitted private adopted")), \
                        pytest.raises(ValueError, match="adoption refused"):
                    action(case.service_bundle)
            assert {name: (path.read_bytes(), path.stat().st_ino) if path.exists() else None
                    for name, path in paths.items()} == originals
            return
        # Reconciliation may settle only observed effects and the completion
        # receipt; it cannot publish the missing intent/binding/accounts targets.
        def reconcile_rename(source, target):
            assert Path(target) not in {case.intent, case.binding, case.accounts}
            return original_replace(source, target)
        with mock.patch.object(os, "replace", side_effect=reconcile_rename):
            reconciled = installer.reconcile_go_service_enrollment(case.service_bundle)
        if "disposition" in reconciled:
            assert reconciled["disposition"] in {"prepared", "staged", "partial"}
            receipt = installer.apply_go_service_enrollment(case.service_bundle)
        else:
            receipt = reconciled
        current = json.loads(case.binding.read_bytes())
        if predecessor:
            assert current["credentials"][0] == old_credential
        with mock.patch.object(g, "atomic_bytes", side_effect=AssertionError("completed enrollment rewrote")):
            assert installer.apply_go_service_enrollment(case.service_bundle) == receipt
            assert installer.reconcile_go_service_enrollment(case.service_bundle) == receipt


@pytest.mark.parametrize("target", ["binding", "intent", "receipt", "predecessor"])
@pytest.mark.parametrize("fault", ["missing", "replacement"])
def test_predecessor_identity_must_survive_until_original_intent(service_owner, target, fault):
    case = service_owner
    prepare_transition(case, True)
    path = {"binding": case.binding, "intent": case.intent, "receipt": case.service_receipt,
            "predecessor": case.service_bundle / installer._SERVICE_PREDECESSOR}[target]
    if fault == "missing":
        path.unlink()
    else:
        g.atomic_bytes(path, path.read_bytes(), 0o600)
    accounts_before = case.accounts.read_bytes()
    with mock.patch.object(installer.secrets, "token_urlsafe", side_effect=AssertionError("invalid predecessor minted")), \
            mock.patch.object(g, "atomic_bytes", side_effect=AssertionError("invalid predecessor wrote")), \
            pytest.raises((ValueError, OSError)):
        installer.apply_go_service_enrollment(case.service_bundle)
    assert case.accounts.read_bytes() == accounts_before


@pytest.mark.parametrize("target", ["intent", "receipt"])
@pytest.mark.parametrize("lost_ack", [False, True])
def test_service_set_identical_replacement_is_not_original_effect(service_owner, target, lost_ack):
    case = service_owner
    plan, _, _ = prepare_transition(case, True)
    path = case.intent if target == "intent" else case.service_receipt
    if lost_ack:
        original = os.replace
        def interrupted(source, destination):
            original(source, destination)
            if Path(destination) == path:
                raise OSError("fixture renamed original")
        with mock.patch.object(os, "replace", side_effect=interrupted), pytest.raises(OSError):
            installer.apply_go_service_enrollment(case.service_bundle)
    else:
        installer.apply_go_service_enrollment(case.service_bundle)
    g.atomic_bytes(path, path.read_bytes(), 0o600)
    for action in (installer.apply_go_service_enrollment, installer.reconcile_go_service_enrollment):
        with mock.patch.object(g, "atomic_bytes", side_effect=AssertionError("replacement adopted")), \
                mock.patch.object(installer.secrets, "token_urlsafe", side_effect=AssertionError("replacement minted")), \
                pytest.raises(ValueError):
            action(case.service_bundle)


@pytest.mark.parametrize("state", ["disabled", "expired", "narrowed", "removed"])
def test_text_enrollment_preserves_retained_admin_grant_state(service_owner, state):
    case = service_owner
    role = admin_predecessor(case, "v4")
    old_bundle = case.service_bundle
    secret = json.loads(case.binding.read_bytes())["credential"]
    document = json.loads(case.accounts.read_bytes())
    grant = document["application_grants"][0]
    if state == "disabled":
        grant["enabled"] = False
    elif state == "expired":
        grant["expires_at"] = time.time() - 10
    elif state == "narrowed":
        grant["max_steps"] = 1
    else:
        document["application_grants"] = []
    if state != "removed":
        role["grant"] = copy.deepcopy(grant)
    case.accounts.write_text(json.dumps(document))
    case.service_bundle = case.root / "service-set-review"
    set_specification(case, successor=True)
    case.service_set["admin"] = role
    prepare_set(case)
    receipt = installer.apply_go_service_enrollment(case.service_bundle)
    current = json.loads(case.accounts.read_bytes())
    assert current == dict(document, application_grants=[*document["application_grants"], case.service_set["text"]["grant"]])
    assert json.loads(case.binding.read_bytes())["credentials"][0] == secret
    with mock.patch.object(g, "atomic_bytes", side_effect=AssertionError("stale original restored Admin")), pytest.raises(ValueError):
        installer.apply_go_service_enrollment(old_bundle)
    assert installer.reconcile_go_service_enrollment(case.service_bundle) == receipt


@pytest.mark.parametrize("role", ["admin", "text"])
def test_initial_set_checks_each_new_grant_expiry(service_owner, role):
    case = service_owner
    set_specification(case)
    case.service_set[role]["grant"]["expires_at"] = time.time() - 10
    with mock.patch.object(installer.secrets, "token_urlsafe", side_effect=AssertionError("expired role minted")), \
            pytest.raises(ValueError, match="expired"):
        prepare_set(case)
    assert not case.intent.exists() and not case.binding.exists() and not case.service_receipt.exists()


@pytest.mark.parametrize("boundary", ["private-progress", "intent"])
def test_original_intent_distinguishes_elapsed_new_authority(service_owner, boundary):
    case = service_owner
    plan, _, _ = prepare_transition(case, True)
    target = (case.store / "bootstrap" / (plan["digest"] + ".service-private.json")
              if boundary == "private-progress" else case.intent)
    original_write, original_replace = g.atomic_bytes, os.replace
    def written(path, raw, mode):
        original_write(path, raw, mode)
        if boundary == "private-progress" and Path(path) == target:
            raise OSError("fixture authority boundary")
    def renamed(source, destination):
        original_replace(source, destination)
        if boundary == "intent" and Path(destination) == target:
            raise OSError("fixture authority boundary")
    with mock.patch.object(g, "atomic_bytes", side_effect=written), \
            mock.patch.object(os, "replace", side_effect=renamed), pytest.raises(OSError):
        installer.apply_go_service_enrollment(case.service_bundle)
    future = case.service_set["text"]["grant"]["expires_at"] + 1
    with mock.patch.object(installer.time, "time", return_value=future), \
            mock.patch.object(installer.secrets, "token_urlsafe", side_effect=AssertionError("elapsed original reminted")):
        if boundary == "private-progress":
            with pytest.raises(ValueError, match="expired"):
                installer.apply_go_service_enrollment(case.service_bundle)
        else:
            assert installer.apply_go_service_enrollment(case.service_bundle)["plan_digest"] == plan["digest"]


def test_service_set_cli_and_public_receipts_never_expose_credentials(service_owner, capsys):
    case = service_owner
    role = admin_predecessor(case, "v4")
    old_secret = json.loads(case.binding.read_bytes())["credential"]
    case.service_bundle = case.root / "service-set-review"
    set_specification(case, successor=True)
    case.service_set["admin"] = role
    spec = case.root / "service-set-specification.json"
    spec.write_text(json.dumps(case.service_set))
    spec.chmod(0o600)
    with mock.patch.object(sys, "argv", ["native_install.py", "prepare-go-service",
            "--go-ingress-bundle", str(case.go_bundle), "--specification", str(spec), "--output", str(case.service_bundle)]):
        installer.main()
    plan_output = capsys.readouterr().out
    plan = json.loads(plan_output)
    assert old_secret not in plan_output and all("bytes" not in value for value in plan["predecessor_custody"].values())
    with mock.patch.object(sys, "argv", ["native_install.py", "apply-go-service", "--bundle", str(case.service_bundle)]):
        installer.main()
    receipt_output = capsys.readouterr().out
    secrets = json.loads(case.binding.read_bytes())["credentials"]
    assert all(secret not in plan_output + receipt_output for secret in secrets)
    assert all(secret not in (case.service_bundle / "PLAN.json").read_text() for secret in secrets)
    assert (case.service_bundle / installer._SERVICE_PREDECESSOR).stat().st_mode & 0o777 == 0o600

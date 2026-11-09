"""Closed five-role E enrollment through the original private transaction."""
import copy
import json
import os
import time
from pathlib import Path
from unittest import mock

import pytest

from test_go_native_stage import builds, native_stage, loaded_entry, installer, ROOT, g
from test_go_native_install import go_owner
from test_native_launcher_successor_transition import source_owners, owner, historical
from test_go_service_enrollment import (
    service_owner, set_specification, prepare_set,
    reseal_modified_entry_for_disposable_fixtures, unchanged_ingress,
)
from test_go_service_set_composition import admin_predecessor
from test_go_service_startup import environment, inspect, boot

NAMES = ("admin", "text", "chat", "brain", "ask")
ROLES = (
    ("admin", "admin-orchestrator", "site_interactive", "MACRO_FABRIC_APPLICATION_TOKEN"),
    ("text", "mastermind-text", "site_batch", "MASTERMIND_FABRIC_APPLICATION_TOKEN"),
    ("chat", "mastermind-chat", "site_interactive", "MASTERMIND_FABRIC_CHAT_TOKEN"),
    ("brain", "brain", "site_interactive", "MACRO_BRAIN_FABRIC_APPLICATION_TOKEN"),
    ("ask", "ask-brain", "site_interactive", "MACRO_ASK_FABRIC_APPLICATION_TOKEN"),
)


def completed_predecessor(case, schema):
    if schema is None:
        return None
    if schema == "v5":
        set_specification(case)
        prepare_set(case)
        installer.apply_go_service_enrollment(case.service_bundle)
    else:
        admin_predecessor(case, schema)
    document = json.loads(case.binding.read_bytes())
    case.previous_bundle = case.service_bundle
    case.service_bundle = case.root / "service-family-review"
    return document


def family_specification(case, previous=None):
    defaults = set_specification(case)
    specification = {"schema": installer.SERVICE_FAMILY_SPEC_SCHEMA,
                     "operation_id": "fixture-service-family"}
    for name, lane, profile, reference in ROLES:
        if name in ("admin", "text"):
            source = defaults[name]
        else:
            source = copy.deepcopy(case.specification)
            source["scope"].update(principal_id="service-" + name, caller_host="fixture-vps",
                workload=name + "-site-interactive", capability_lane=lane,
                workload_profile=profile, credential_ref=reference)
            source["grant"].update(grant_id="fixture-" + name, principal_id="service-" + name,
                admission_root="service:" + name, credential_ref=reference,
                caller_hosts=["fixture-vps"], workloads=[name + "-site-interactive"])
        specification[name] = {key: copy.deepcopy(source[key]) for key in ("scope", "grant")}
    if previous is not None:
        scopes = previous["scopes"] if previous["schema"].endswith(".v5") else [previous["scope"]]
        for name, scope in zip(NAMES, scopes):
            specification[name] = {"scope": copy.deepcopy(scope)}
    case.family = specification
    return specification


def prepare_family(case):
    return installer.prepare_go_service_enrollment(case.go_bundle, case.family, case.service_bundle)


@pytest.mark.parametrize("schema,retained", [(None, 0), ("v1", 1), ("v3", 1), ("v4", 1), ("v5", 2)])
def test_five_role_transition_preserves_original_authentication_and_replay(service_owner, monkeypatch, schema, retained):
    case = service_owner
    previous = completed_predecessor(case, schema)
    family_specification(case, previous)
    with mock.patch.object(installer.secrets, "token_urlsafe", side_effect=AssertionError("prepare minted")):
        plan = prepare_family(case)
        assert installer.reconcile_go_service_enrollment(case.service_bundle)["disposition"] == "prepared"
    assert plan["schema"] == "native-go-service-enrollment.v6"
    assert plan["predecessor_schema"] == (previous["schema"] if previous else None)
    with mock.patch.object(installer.secrets, "token_urlsafe", wraps=installer.secrets.token_urlsafe) as minted:
        receipt = installer.apply_go_service_enrollment(case.service_bundle)
    assert minted.call_count == 5 - retained
    current = json.loads(case.binding.read_bytes())
    assert current["schema"] == "mastermind.native_go_application_service.v6"
    assert len(current["credentials"]) == len(set(current["credentials"])) == 5
    assert current["scopes"] == [case.family[name]["scope"] for name in NAMES] == receipt["scopes"]
    if previous:
        old_credentials = previous["credentials"] if retained == 2 else [previous["credential"]]
        old_scopes = previous["scopes"] if retained == 2 else [previous["scope"]]
        assert current["credentials"][:retained] == old_credentials
        assert current["scopes"][:retained] == old_scopes
    account_data = json.loads(case.accounts.read_bytes())
    assert len(account_data["application_grants"]) == 5
    assert account_data["operator_note"] == case.document["operator_note"]
    assert all(value not in json.dumps(plan) + json.dumps(receipt) for value in current["credentials"])
    with mock.patch.object(g, "atomic_bytes", side_effect=AssertionError("completed replay wrote")), \
            mock.patch.object(installer.secrets, "token_urlsafe", side_effect=AssertionError("completed replay minted")):
        assert installer.apply_go_service_enrollment(case.service_bundle) == receipt
        assert installer.reconcile_go_service_enrollment(case.service_bundle) == receipt
    environment(monkeypatch, case)
    with loaded_entry(case.published, clean_yaml=True) as entry:
        startup = inspect(entry, case)
        services, host, profile = entry.load_completed_application_startup(startup)
        assert len(services) == 5 and host == "fixture-native" and profile == case.profile
        assert [service.credential_ref for service in services] == [role[3] for role in ROLES]
        with mock.patch.object(startup.handler, "main", return_value=47) as main:
            assert boot(entry, case) == 47
            assert main.call_args.kwargs["application_services"] == services
            assert Path(main.call_args.kwargs["application_broker"].db_path) == case.ext / "broker/leases.sqlite"
    with pytest.raises(ValueError, match="predecessor schema"):
        installer.prepare_go_service_enrollment(case.go_bundle, case.family, case.root / "duplicate-family")
    unchanged_ingress(case)


@pytest.mark.parametrize("name", ["admin", "text"])
@pytest.mark.parametrize("state", ["disabled", "expired", "narrowed", "removed"])
def test_two_retained_roles_never_recreate_or_renew_current_grants(service_owner, name, state):
    case = service_owner
    previous = completed_predecessor(case, "v5")
    family_specification(case, previous)
    accounts = json.loads(case.accounts.read_bytes())
    original = accounts["application_grants"][NAMES.index(name)]
    if state == "disabled":
        original["enabled"] = False
    elif state == "expired":
        original["expires_at"] = time.time() - 20
    elif state == "narrowed":
        original["models"] = ["other-original-model"]
    else:
        accounts["application_grants"].remove(original)
    case.accounts.write_text(json.dumps(accounts))
    retained = copy.deepcopy(accounts["application_grants"])
    prepare_family(case)
    installer.apply_go_service_enrollment(case.service_bundle)
    after = json.loads(case.accounts.read_bytes())["application_grants"]
    assert after[:len(retained)] == retained
    assert after[len(retained):] == [case.family[role]["grant"] for role in ("chat", "brain", "ask")]
    assert json.loads(case.binding.read_bytes())["credentials"][:2] == previous["credentials"]


@pytest.mark.parametrize("fault", ["missing-role", "extra-role", "missing-new-grant", "retained-grant",
    "wrong-reference", "wrong-lane", "wrong-profile", "child-admin-view", "duplicate-identity",
    "missing-text-purpose", "scope-not-object"])
def test_family_grammar_refuses_implicit_or_invented_authority(service_owner, fault):
    case = service_owner
    previous = completed_predecessor(case, "v5") if fault == "retained-grant" else None
    family_specification(case, previous)
    s = case.family
    if fault == "missing-role":
        del s["ask"]
    elif fault == "extra-role":
        s["terminal"] = copy.deepcopy(s["ask"])
    elif fault == "missing-new-grant":
        del s["chat"]["grant"]
    elif fault == "retained-grant":
        s["text"]["grant"] = copy.deepcopy(case.service_set["text"]["grant"])
    elif fault == "wrong-reference":
        s["chat"]["scope"]["credential_ref"] = s["admin"]["scope"]["credential_ref"]
    elif fault == "wrong-lane":
        s["chat"]["scope"]["capability_lane"] = "brain"
    elif fault == "wrong-profile":
        s["text"]["scope"]["workload_profile"] = "site_interactive"
    elif fault == "child-admin-view":
        s["ask"]["scope"]["admin_pool_view"] = True
    elif fault == "duplicate-identity":
        for key in ("principal_id", "caller_host", "workload"):
            s["chat"]["scope"][key] = s["brain"]["scope"][key]
        s["chat"]["grant"].update(principal_id=s["chat"]["scope"]["principal_id"],
            caller_hosts=[s["chat"]["scope"]["caller_host"]], workloads=[s["chat"]["scope"]["workload"]])
    elif fault == "missing-text-purpose":
        del s["text"]["scope"]["selection_purpose"]
    else:
        s["chat"]["scope"] = None
    before = {path: path.read_bytes() if path.exists() else None
              for path in (case.binding, case.intent, case.service_receipt, case.accounts)}
    with mock.patch.object(installer.secrets, "token_urlsafe", side_effect=AssertionError("invalid specification minted")), \
            pytest.raises(ValueError):
        prepare_family(case)
    assert {path: path.read_bytes() if path.exists() else None for path in before} == before


def test_v5_and_v6_private_document_grammars_remain_closed(service_owner):
    case = service_owner
    family_specification(case)
    prepare_family(case)
    installer.apply_go_service_enrollment(case.service_bundle)
    original = json.loads(case.binding.read_bytes())
    with loaded_entry(case.published, clean_yaml=True) as entry:
        startup = inspect(entry, case)
        for fault in ("v5", "missing", "extra", "reorder", "duplicate-token", "extra-scope-field"):
            document = copy.deepcopy(original)
            if fault == "v5":
                document["schema"] = entry.SERVICE_SET_SCHEMA
            elif fault == "missing":
                document["scopes"].pop();document["credentials"].pop()
            elif fault == "extra":
                document["scopes"].append(copy.deepcopy(document["scopes"][-1]))
                document["credentials"].append("fixture-extra-" + "x" * 40)
            elif fault == "reorder":
                document["scopes"][2], document["scopes"][3] = document["scopes"][3], document["scopes"][2]
            elif fault == "duplicate-token":
                document["credentials"][4] = document["credentials"][0]
            else:
                document["scopes"][4]["admin_pool_view"] = False
            with pytest.raises(ValueError):
                entry.validate_application_service_document(startup, document)
        intent = json.loads(case.intent.read_bytes())
        intent["schema"] = entry.SERVICE_SET_ENROLLMENT_SCHEMA
        with pytest.raises(ValueError, match="receipt"):
            entry.validate_completed_application_records(startup, case.binding.read_bytes(),
                entry.application_file_identity(case.binding), json.dumps(intent).encode(),
                case.service_receipt.read_bytes())


@pytest.mark.parametrize("schema", [None, "v1", "v5"])
@pytest.mark.parametrize("boundary", ["private", "private-progress", "intent", "binding", "accounts", "receipt"])
def test_family_original_interruption_custody_never_remints_or_adopts(service_owner, schema, boundary):
    case = service_owner
    previous = completed_predecessor(case, schema)
    family_specification(case, previous)
    plan = prepare_family(case)
    retained = 0 if previous is None else 2 if schema == "v5" else 1
    paths = {"intent": case.intent, "binding": case.binding, "accounts": case.accounts,
             "receipt": case.service_receipt}
    targets = dict(paths, private=case.service_bundle / installer._SERVICE_PRIVATE)
    targets["private-progress"] = case.store / "bootstrap" / (plan["digest"] + ".service-private.json")
    original_bytes = {name: (path.read_bytes(), path.stat().st_ino) if path.exists() else None
                      for name, path in paths.items()}
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
    assert hit == [boundary] and minted.call_count == 5 - retained
    with mock.patch.object(installer.secrets, "token_urlsafe", side_effect=AssertionError("original reminted")):
        if boundary == "private":
            for action in (installer.apply_go_service_enrollment, installer.reconcile_go_service_enrollment):
                with mock.patch.object(g, "atomic_bytes", side_effect=AssertionError("uncommitted private adopted")), \
                        pytest.raises(ValueError, match="adoption refused"):
                    action(case.service_bundle)
            assert {name: (path.read_bytes(), path.stat().st_ino) if path.exists() else None
                    for name, path in paths.items()} == original_bytes
            return
        def reconcile_rename(source, target):
            assert Path(target) not in {case.intent, case.binding, case.accounts}
            return original_replace(source, target)
        with mock.patch.object(os, "replace", side_effect=reconcile_rename):
            result = installer.reconcile_go_service_enrollment(case.service_bundle)
        receipt = installer.apply_go_service_enrollment(case.service_bundle) if "disposition" in result else result
        current = json.loads(case.binding.read_bytes())
        if previous:
            assert current["credentials"][:retained] == (
                previous["credentials"] if retained == 2 else [previous["credential"]])
        with mock.patch.object(g, "atomic_bytes", side_effect=AssertionError("completed replay wrote")):
            assert installer.apply_go_service_enrollment(case.service_bundle) == receipt
            assert installer.reconcile_go_service_enrollment(case.service_bundle) == receipt


@pytest.mark.parametrize("target", ["binding", "intent", "receipt", "predecessor"])
def test_two_role_predecessor_replacement_refuses_before_any_new_effect(service_owner, target):
    case = service_owner
    previous = completed_predecessor(case, "v5")
    family_specification(case, previous)
    prepare_family(case)
    path = {"binding": case.binding, "intent": case.intent, "receipt": case.service_receipt,
            "predecessor": case.service_bundle / installer._SERVICE_PREDECESSOR}[target]
    g.atomic_bytes(path, path.read_bytes(), 0o600)
    before = case.accounts.read_bytes()
    with mock.patch.object(installer.secrets, "token_urlsafe", side_effect=AssertionError("foreign predecessor minted")), \
            mock.patch.object(g, "atomic_bytes", side_effect=AssertionError("foreign predecessor wrote")), \
            pytest.raises((ValueError, OSError)):
        installer.apply_go_service_enrollment(case.service_bundle)
    assert case.accounts.read_bytes() == before


@pytest.mark.parametrize("key,value", [("caller_host", "different-vps"), ("workload", "different-workload"),
                                      ("selection_purpose", {"purpose_id": "altered"})])
def test_retained_text_scope_cannot_be_replaced(service_owner, key, value):
    case = service_owner
    previous = completed_predecessor(case, "v5")
    family_specification(case, previous)
    case.family["text"]["scope"][key] = value
    before = {path: path.read_bytes() for path in (case.binding, case.intent, case.service_receipt, case.accounts)}
    with pytest.raises(ValueError):
        prepare_family(case)
    assert {path: path.read_bytes() for path in before} == before


@pytest.mark.parametrize("schema", ["mastermind.native_go_application_service.v2",
    "mastermind.native_go_application_service.v6", "foreign", {}, True])
def test_family_predecessor_version_discriminator_is_closed(schema):
    with pytest.raises(ValueError, match="predecessor schema"):
        installer._service_family_retained(schema)


@pytest.mark.parametrize("name", NAMES)
def test_every_new_family_grant_must_be_current_before_original_intent(service_owner, name):
    case = service_owner
    family_specification(case)
    case.family[name]["grant"]["expires_at"] = time.time() - 5
    before = case.accounts.read_bytes()
    with mock.patch.object(installer.secrets, "token_urlsafe", side_effect=AssertionError("expired grant minted")), \
            pytest.raises(ValueError, match="expired"):
        prepare_family(case)
    assert case.accounts.read_bytes() == before
    assert not case.binding.exists() and not case.intent.exists()


def test_family_elapsed_new_authority_keeps_original_intent_recoverable(service_owner):
    case = service_owner
    previous = completed_predecessor(case, "v5")
    family_specification(case, previous)
    plan = prepare_family(case)
    original = os.replace
    def renamed(source, target):
        original(source, target)
        if Path(target) == case.intent:
            raise OSError("fixture committed intent acknowledgement lost")
    with mock.patch.object(os, "replace", side_effect=renamed), pytest.raises(OSError):
        installer.apply_go_service_enrollment(case.service_bundle)
    private = (case.service_bundle / installer._SERVICE_PRIVATE).read_bytes()
    future = max(case.family[name]["grant"]["expires_at"] for name in ("chat", "brain", "ask")) + 1
    with mock.patch.object(installer.time, "time", return_value=future), \
            mock.patch.object(installer.secrets, "token_urlsafe", side_effect=AssertionError("elapsed original reminted")):
        receipt = installer.apply_go_service_enrollment(case.service_bundle)
    assert case.binding.read_bytes() == private
    assert receipt["schema"] == "native-go-service-enrollment-completed.v6"


def test_five_services_recover_two_originals_and_share_physical_capacity(service_owner, monkeypatch):
    import http.client
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    import socket
    import sqlite3
    import sys
    import threading
    sys.path.insert(0, str(ROOT / "tests"))
    case = service_owner
    previous = completed_predecessor(case, "v5")
    old_credentials = previous["credentials"]
    accounts = json.loads(case.accounts.read_bytes())
    accounts["providers"]["go"]["accounts"][0]["per_account_cap"] = 3
    case.accounts.write_text(json.dumps(accounts))
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
            assert len(services) == 2
            for index, service in enumerate(services):
                assert service.credential == old_credentials[index]
                status, body = request(service, "/v1/chat/completions", payload, "shared-terminal")
                assert status == 200, body
                status, body = request(service, "/application-turns/close", {"turn_id": "shared-terminal"})
                assert status == 200 and body["application"]["disposition"] == "closed"
                scope = {"workload": service.workload, "turn_id": "shared-pending", "pool": "go", "model": "fixture-model"}
                binding = gateway.begin_application(scope, principal_id=service.principal_id, host=service.host,
                    expected_credential_ref=service.credential_ref)
                assert binding["ok"] and binding["disposition"] == "admitted"
                permit = gateway.prepare_application(binding["token"], principal_id=service.principal_id,
                    host=service.host, turn_id="shared-pending", request_id="step1",
                    path="/v1/chat/completions", payload=payload)
                assert permit["dispatch_permitted"] is True
                assert {row["state"] for row in rows("application_requests", service.principal_id)} == {"pending", "terminal"}
            assert len(posts) == len(usage()) == 2

        try:
            run_listener(before_transition)
            principals = [scope["principal_id"] for scope in previous["scopes"]]
            original_rows = {principal: rows("application_requests", principal) for principal in principals}
            usage_before = usage_path.read_bytes()
            family_specification(case, previous)
            accounts = json.loads(case.accounts.read_bytes())
            for grant in accounts["application_grants"]:
                grant["enabled"] = False
            case.accounts.write_text(json.dumps(accounts))
            retained_grants = copy.deepcopy(accounts["application_grants"])
            prepare_family(case)
            installer.apply_go_service_enrollment(case.service_bundle)
            assert json.loads(case.accounts.read_bytes())["application_grants"][:2] == retained_grants
            with mock.patch.object(g, "atomic_bytes", side_effect=AssertionError("stale v5 bundle wrote")), pytest.raises(ValueError):
                installer.apply_go_service_enrollment(case.previous_bundle)

            def after_transition(services, gateway, request):
                assert len(services) == 5
                admin, text, chat, brain, ask = services
                assert [admin.credential, text.credential] == old_credentials
                for service in (admin, text):
                    status, body = request(service, "/v1/chat/completions", payload, "shared-terminal")
                    assert status == 409 and body["application"]["disposition"] == "terminal_receipt_only"
                    status, body = request(service, "/v1/chat/completions", payload, "shared-pending")
                    assert status == 409 and body["application"]["disposition"] == "pending"
                    assert rows("application_requests", service.principal_id) == original_rows[service.principal_id]
                    status, body = request(service, "/v1/chat/completions", payload, "revoked-fresh")
                    assert status == 409 and body["application"]["disposition"] == "refused"
                assert usage_path.read_bytes() == usage_before and len(posts) == 2

                status, body = request(chat, "/v1/chat/completions", payload, "shared-child")
                assert status == 200, body
                before_capacity = (rows("leases"), rows("application_turns"), rows("application_requests"),
                                   usage_path.read_bytes(), len(posts))
                status, body = request(brain, "/v1/chat/completions", payload, "capacity-full")
                assert status == 429 and body["application"]["disposition"] == "refused"
                after_capacity = (rows("leases"), rows("application_turns"), rows("application_requests"),
                                  usage_path.read_bytes(), len(posts))
                assert after_capacity[1:] == before_capacity[1:]
                assert len(after_capacity[0]) == len(before_capacity[0])
                # The incumbent fairness owner may mark one surplus original
                # nonrenewable. It does not free pending work or grant a fourth slot.
                changed = 0
                for old, current in zip(before_capacity[0], after_capacity[0]):
                    if old != current:
                        changed += 1
                        assert old["orchestrator_id"] == case.specification["grant"]["admission_root"]
                        assert old["state"] == "held" and old["renewable"] == 1
                        assert current == dict(old, state="rented", renewable=0)
                assert changed == 1
                assert sum(row["state"] in {"held", "rented"} for row in after_capacity[0]) == 3
                status, body = request(chat, "/application-turns/close", {"turn_id": "shared-child"})
                assert status == 200 and body["application"]["disposition"] == "closed"

                for service in (brain, ask):
                    status, body = request(service, "/v1/chat/completions", payload, "shared-child")
                    assert status == 200, body
                    status, body = request(service, "/application-turns/close", {"turn_id": "shared-child"})
                    assert status == 200 and body["application"]["disposition"] == "closed"
                assert len(posts) == len(usage()) == 5
                assert all(row["model"] == "fixture-model" and row["input"] == 3 and row["output"] == 2
                           and row["usage_state"] == "known" and row["est_usd"] is None for row in usage())
                unchanged = (rows("leases"), rows("application_requests"), usage_path.read_bytes(), len(posts))
                request(ask, "/application-turns/close", {"turn_id": "shared-pending"})
                assert (rows("leases"), rows("application_requests"), usage_path.read_bytes(), len(posts)) == unchanged
                for service in (admin, text):
                    status, body = request(service, "/application-turns/close", {"turn_id": "shared-pending"})
                    assert status == 409 and body["application"]["disposition"] in {"pending", "effect_unknown"}
                    assert rows("application_requests", service.principal_id) == original_rows[service.principal_id]
                for service in (chat, brain, ask):
                    status, body = request(service, "/v1/chat/completions", payload, "shared-child")
                    assert status == 409 and body["application"]["disposition"] == "terminal_receipt_only"
                assert len(posts) == len(usage()) == 5
                assert (db.stat().st_ino, lock.stat().st_ino) == owner_inodes
            run_listener(after_transition)
        finally:
            upstream.shutdown()
            serving.join(2)
            upstream.server_close()


@pytest.mark.parametrize("fault", ["one-role", "absent", "hash-count", "hash-value"])
def test_original_predecessor_discriminator_and_hash_vector_cannot_be_reinterpreted(service_owner, fault):
    case = service_owner
    previous = completed_predecessor(case, "v5")
    family_specification(case, previous)
    plan = prepare_family(case)
    if fault == "one-role":
        plan["predecessor_schema"] = "mastermind.native_go_application_service.v1"
    elif fault == "absent":
        plan["predecessor_schema"] = None
    elif fault == "hash-count":
        plan["predecessor_credential_sha256s"].pop()
    else:
        plan["predecessor_credential_sha256s"][1] = "a" * 64
    plan["digest"] = g.digest(g.canonical({key: value for key, value in plan.items() if key != "digest"}))
    (case.service_bundle / "PLAN.json").write_bytes(g.canonical(plan) + b"\n")
    before = {path: path.read_bytes() for path in (case.binding, case.intent, case.service_receipt, case.accounts)}
    with mock.patch.object(g, "atomic_bytes", side_effect=AssertionError("forged predecessor wrote")), \
            mock.patch.object(installer.secrets, "token_urlsafe", side_effect=AssertionError("forged predecessor minted")), \
            pytest.raises(ValueError):
        installer.apply_go_service_enrollment(case.service_bundle)
    assert {path: path.read_bytes() for path in before} == before

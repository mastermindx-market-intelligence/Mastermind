"""V7 to V8 adds three native workload identities without replacing the family."""
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
from test_go_service_enrollment import service_owner, unchanged_ingress
from test_go_service_family_composition import NAMES, family_specification, prepare_family
from test_go_service_routed_composition import complete_v6, routed_specification, prepare_routed, targets
from test_go_service_startup import environment, inspect, boot

ADDITIONS = (
    ("batch", "site_batch", "MACRO_BATCH_FABRIC_APPLICATION_TOKEN"),
    ("analysis", "lobe_analysis", "MACRO_ANALYSIS_FABRIC_APPLICATION_TOKEN"),
    ("portfolio", "portfolio_analysis", "MACRO_PORTFOLIO_FABRIC_APPLICATION_TOKEN"),
)
ALL_NAMES = NAMES + tuple(row[0] for row in ADDITIONS)


def complete_v7(case):
    previous = complete_v6(case)
    routed_specification(case, previous)
    prepare_routed(case)
    installer.apply_go_service_enrollment(case.service_bundle)
    previous = json.loads(case.binding.read_bytes())
    case.routed_bundle = case.service_bundle
    case.service_bundle = case.root / "service-workload-review"
    return previous


def workload_specification(case, previous):
    specification = {"schema": installer.SERVICE_WORKLOAD_SPEC_SCHEMA,
                     "operation_id": "fixture-workload-eight"}
    for name, scope in zip(NAMES, previous["scopes"]):
        specification[name] = {"scope": copy.deepcopy(scope)}
    for name, profile, reference in ADDITIONS:
        scope = copy.deepcopy(previous["scopes"][1])
        scope.update(principal_id="service-" + name, workload=profile,
                     workload_profile=profile, capability_lane=None, credential_ref=reference)
        scope["selection_purpose"].update(purpose_id="fixture-" + name,
            source_ref="fixture:explicit-" + name + "-workload-contract")
        scope["route_scope"] = {"schema": "mastermind.application_route_scope.v1", "pools": ["go"]}
        grant = copy.deepcopy(case.family["text"]["grant"])
        grant.update(grant_id="fixture-workload-" + name, principal_id=scope["principal_id"],
            admission_root="service:" + name, credential_ref=reference,
            caller_hosts=[scope["caller_host"]], workloads=[profile])
        specification[name] = {"scope": scope, "new_grants": [grant]}
    case.workloads = specification
    return specification


def prepare_workloads(case):
    return installer.prepare_go_service_enrollment(case.go_bundle, case.workloads, case.service_bundle)


def test_eight_role_transition_mints_only_three_and_keeps_original_startup(service_owner, monkeypatch):
    case = service_owner
    previous = complete_v7(case)
    workload_specification(case, previous)
    before = json.loads(case.accounts.read_bytes())
    with mock.patch.object(installer.secrets, "token_urlsafe", side_effect=AssertionError("prepare minted")):
        plan = prepare_workloads(case)
        assert installer.reconcile_go_service_enrollment(case.service_bundle)["disposition"] == "prepared"
    with mock.patch.object(installer.secrets, "token_urlsafe", wraps=installer.secrets.token_urlsafe) as minted:
        receipt = installer.apply_go_service_enrollment(case.service_bundle)
    assert minted.call_count == 3
    current = json.loads(case.binding.read_bytes())
    assert plan["schema"] == "native-go-service-enrollment.v8"
    assert current["schema"] == "mastermind.native_go_application_service.v8"
    assert receipt["schema"] == "native-go-service-enrollment-completed.v8"
    assert len(plan["predecessor_credential_sha256s"]) == 5
    assert len(current["credentials"]) == len(set(current["credentials"])) == 8
    assert current["credentials"][:5] == previous["credentials"]
    assert current["scopes"][:5] == previous["scopes"]
    assert current["scopes"] == receipt["scopes"] == [case.workloads[name]["scope"] for name in ALL_NAMES]
    after = json.loads(case.accounts.read_bytes())
    assert after["application_grants"] == before["application_grants"] + [
        case.workloads[name]["new_grants"][0] for name, _, _ in ADDITIONS]
    assert after["operator_note"] == before["operator_note"]
    assert all(token not in json.dumps(plan) + json.dumps(receipt) for token in current["credentials"])
    with mock.patch.object(g, "atomic_bytes", side_effect=AssertionError("completed replay wrote")), \
            mock.patch.object(installer.secrets, "token_urlsafe", side_effect=AssertionError("completed replay minted")):
        assert installer.apply_go_service_enrollment(case.service_bundle) == receipt
        assert installer.reconcile_go_service_enrollment(case.service_bundle) == receipt
    environment(monkeypatch, case)
    with loaded_entry(case.published, clean_yaml=True) as entry:
        startup = inspect(entry, case)
        services, host, profile = entry.load_completed_application_startup(startup)
        assert len(services) == 8 and host == "fixture-native" and profile == case.profile
        assert [s.credential for s in services] == current["credentials"]
        for service, (name, workload, reference) in zip(services[5:], ADDITIONS):
            assert service.workload == workload and service.credential_ref == reference
            assert service.selection_purpose.document == case.workloads[name]["scope"]["selection_purpose"]
            assert not service.admin_pool_view
        with mock.patch.object(startup.handler, "main", return_value=83) as main:
            assert boot(entry, case) == 83
            assert main.call_args.kwargs["application_services"] == services
    # A previously completed family/routed bundle cannot overwrite the successor.
    snapshot = targets(case)
    for old in (case.previous_bundle, case.routed_bundle):
        with pytest.raises(ValueError):
            installer.apply_go_service_enrollment(old)
        assert targets(case) == snapshot
    unchanged_ingress(case)


def test_workload_closed_grammar_refuses_authority_substitution_before_effect(service_owner):
    case = service_owner
    previous = complete_v7(case)
    original = workload_specification(case, previous)
    before = targets(case)
    faults = ("missing-role", "extra-role", "retained-grant", "retained-purpose", "retained-route",
              "missing-purpose", "missing-route", "admin-metadata", "string-null-lane", "wrong-profile",
              "wrong-workload", "wrong-reference", "account-owner", "implicit-grant", "wrong-principal",
              "outside-pool", "unknown-grant-field", "expired", "overlap")
    for index, fault in enumerate(faults):
        spec = copy.deepcopy(original)
        scope = spec["analysis"]["scope"]
        grant = spec["analysis"]["new_grants"][0]
        if fault == "missing-role":
            del spec["portfolio"]
        elif fault == "extra-role":
            spec["terminal"] = copy.deepcopy(spec["analysis"])
        elif fault == "retained-grant":
            spec["text"]["new_grants"] = []
        elif fault == "retained-purpose":
            spec["text"]["scope"]["selection_purpose"]["source_ref"] = "fixture:replacement"
        elif fault == "retained-route":
            spec["text"]["scope"]["route_scope"]["pools"] = ["go"]
        elif fault == "missing-purpose":
            del scope["selection_purpose"]
        elif fault == "missing-route":
            del scope["route_scope"]
        elif fault == "admin-metadata":
            scope["admin_pool_view"] = True
        elif fault == "string-null-lane":
            scope["capability_lane"] = "null"
        elif fault == "wrong-profile":
            scope["workload_profile"] = "site_interactive"
        elif fault == "wrong-workload":
            scope["workload"] = "another-analysis"
            grant["workloads"] = ["another-analysis"]
        elif fault == "wrong-reference":
            scope["credential_ref"] = spec["admin"]["scope"]["credential_ref"]
            grant["credential_ref"] = scope["credential_ref"]
        elif fault == "account-owner":
            scope["account_profile"] = "/tmp/another-owner"
        elif fault == "implicit-grant":
            spec["analysis"]["grant"] = spec["analysis"].pop("new_grants")[0]
        elif fault == "wrong-principal":
            grant["principal_id"] = "unrelated-principal"
        elif fault == "outside-pool":
            grant["pool"] = "bailian"
        elif fault == "unknown-grant-field":
            grant["token"] = "not-authority"
        elif fault == "expired":
            grant["expires_at"] = time.time() - 1
        else:
            spec["analysis"]["new_grants"].append(dict(grant, grant_id="duplicate-authority"))
        case.workloads = spec
        case.service_bundle = case.root / ("invalid-workload-" + str(index))
        with mock.patch.object(installer.secrets, "token_urlsafe", side_effect=AssertionError("invalid minted")), \
                pytest.raises(ValueError):
            prepare_workloads(case)
        assert targets(case) == before, fault


def test_workload_requires_completed_v7_predecessor(service_owner):
    case = service_owner
    previous = complete_v6(case)
    routed_specification(case, previous)
    # A spec is not evidence that its proposed routed predecessor was installed.
    scopes = [case.routed[name]["scope"] for name in NAMES]
    workload_specification(case, {"scopes": scopes})
    before = targets(case)
    with pytest.raises(ValueError, match="completed v7 predecessor"):
        prepare_workloads(case)
    assert targets(case) == before


def test_workload_preserves_revoked_expired_narrowed_and_removed_grants(service_owner):
    case = service_owner
    previous = complete_v7(case)
    workload_specification(case, previous)
    data = json.loads(case.accounts.read_bytes())
    rows = data["application_grants"]
    rows[0]["enabled"] = False
    rows[1]["expires_at"] = time.time() - 10
    rows[2]["models"] = ["narrowed-original-model"]
    removed = rows.pop(3)
    case.accounts.write_text(json.dumps(data))
    retained = copy.deepcopy(rows)
    prepare_workloads(case)
    installer.apply_go_service_enrollment(case.service_bundle)
    after = json.loads(case.accounts.read_bytes())
    assert after["application_grants"][:len(retained)] == retained
    assert removed not in after["application_grants"]
    assert json.loads(case.binding.read_bytes())["credentials"][:5] == previous["credentials"]


def test_workload_private_versions_cardinality_and_role_order_remain_closed(service_owner, monkeypatch):
    case = service_owner
    previous = complete_v7(case)
    workload_specification(case, previous)
    plan = prepare_workloads(case)
    installer.apply_go_service_enrollment(case.service_bundle)
    document = json.loads(case.binding.read_bytes())
    assert installer._service_set_credentials_match(plan, previous["credentials"], predecessor=True)
    assert installer._service_set_credentials_match(plan, document["credentials"])
    assert not installer._service_set_credentials_match(plan, previous["credentials"])
    assert not installer._service_set_credentials_match(plan, document["credentials"], predecessor=True)
    for values in (document["credentials"][:-1], document["credentials"] + ["extra"],
                   [previous["credentials"]] + document["credentials"][5:],
                   ["changed"] + document["credentials"][1:]):
        assert not installer._service_set_credentials_match(plan, values)
    environment(monkeypatch, case)
    with loaded_entry(case.published, clean_yaml=True) as entry:
        startup = inspect(entry, case)
        for fault in ("v6", "v7", "short-scopes", "extra-credentials", "duplicate-credentials", "reordered"):
            bad = copy.deepcopy(document)
            if fault in ("v6", "v7"):
                bad["schema"] = "mastermind.native_go_application_service." + fault
            elif fault == "short-scopes":
                bad["scopes"].pop()
            elif fault == "extra-credentials":
                bad["credentials"].append("extra-" + "x" * 40)
            elif fault == "duplicate-credentials":
                bad["credentials"][-1] = bad["credentials"][0]
            else:
                bad["scopes"][5], bad["scopes"][6] = bad["scopes"][6], bad["scopes"][5]
            with pytest.raises(ValueError):
                entry.validate_application_service_document(startup, bad)


@pytest.mark.parametrize("boundary", ["private", "private-progress", "intent", "binding", "accounts", "receipt"])
def test_workload_interruption_preserves_three_original_mints(service_owner, boundary):
    case = service_owner
    previous = complete_v7(case)
    workload_specification(case, previous)
    plan = prepare_workloads(case)
    paths = {"intent": case.intent, "binding": case.binding, "accounts": case.accounts,
             "receipt": case.service_receipt}
    named = dict(paths, private=case.service_bundle / installer._SERVICE_PRIVATE)
    named["private-progress"] = case.store / "bootstrap" / (plan["digest"] + ".service-private.json")
    before = targets(case)
    original_write, original_replace = g.atomic_bytes, os.replace
    hit = []
    def written(path, raw, mode):
        original_write(path, raw, mode)
        if Path(path) == named[boundary] and boundary not in paths and not hit:
            hit.append(boundary)
            raise OSError("fixture workload ACK lost")
    def renamed(source, target):
        original_replace(source, target)
        if boundary in paths and Path(target) == named[boundary] and not hit:
            hit.append(boundary)
            raise OSError("fixture workload ACK lost")
    with mock.patch.object(installer.secrets, "token_urlsafe", wraps=installer.secrets.token_urlsafe) as minted, \
            mock.patch.object(g, "atomic_bytes", side_effect=written), \
            mock.patch.object(os, "replace", side_effect=renamed), pytest.raises(OSError, match="workload ACK"):
        installer.apply_go_service_enrollment(case.service_bundle)
    assert hit == [boundary] and minted.call_count == 3
    private = json.loads((case.service_bundle / installer._SERVICE_PRIVATE).read_bytes())
    with mock.patch.object(installer.secrets, "token_urlsafe", side_effect=AssertionError("workload reminted")):
        if boundary == "private":
            for action in (installer.apply_go_service_enrollment, installer.reconcile_go_service_enrollment):
                with mock.patch.object(g, "atomic_bytes", side_effect=AssertionError("uncommitted adopted")), \
                        pytest.raises(ValueError, match="adoption refused"):
                    action(case.service_bundle)
            assert targets(case) == before
            return
        result = installer.reconcile_go_service_enrollment(case.service_bundle)
        receipt = installer.apply_go_service_enrollment(case.service_bundle) if "disposition" in result else result
        assert receipt["schema"] == "native-go-service-enrollment-completed.v8"
        current = json.loads(case.binding.read_bytes())
        assert current["credentials"] == private["credentials"]
        assert current["credentials"][:5] == previous["credentials"]
        with mock.patch.object(g, "atomic_bytes", side_effect=AssertionError("completed replay wrote")):
            assert installer.apply_go_service_enrollment(case.service_bundle) == receipt


@pytest.mark.parametrize("target", ["binding", "intent", "receipt", "predecessor", "accounts"])
def test_workload_prepared_transition_requires_original_inodes(service_owner, target):
    case = service_owner
    previous = complete_v7(case)
    workload_specification(case, previous)
    prepare_workloads(case)
    path = {"binding": case.binding, "intent": case.intent, "receipt": case.service_receipt,
            "predecessor": case.service_bundle / installer._SERVICE_PREDECESSOR,
            "accounts": case.accounts}[target]
    g.atomic_bytes(path, path.read_bytes(), 0o600)
    before = targets(case)
    with mock.patch.object(installer.secrets, "token_urlsafe", side_effect=AssertionError("replacement minted")), \
            mock.patch.object(g, "atomic_bytes", side_effect=AssertionError("replacement wrote")), \
            pytest.raises(ValueError):
        installer.apply_go_service_enrollment(case.service_bundle)
    assert targets(case) == before


@pytest.mark.parametrize("committed", [False, True])
def test_workload_new_expiry_only_blocks_before_original_intent(service_owner, committed):
    case = service_owner
    previous = complete_v7(case)
    workload_specification(case, previous)
    prepare_workloads(case)
    if committed:
        original = os.replace
        def renamed(source, target):
            original(source, target)
            if Path(target) == case.intent:
                raise OSError("fixture workload intent ACK lost")
        with mock.patch.object(os, "replace", side_effect=renamed), pytest.raises(OSError):
            installer.apply_go_service_enrollment(case.service_bundle)
    future = max(case.workloads[name]["new_grants"][0]["expires_at"] for name, _, _ in ADDITIONS) + 1
    with mock.patch.object(installer.time, "time", return_value=future), \
            mock.patch.object(installer.secrets, "token_urlsafe", side_effect=AssertionError("elapsed minted")):
        if committed:
            assert installer.apply_go_service_enrollment(case.service_bundle)["schema"] == "native-go-service-enrollment-completed.v8"
        else:
            with pytest.raises(ValueError, match="expired before"):
                installer.apply_go_service_enrollment(case.service_bundle)
    assert json.loads(case.binding.read_bytes())["credentials"][:5] == previous["credentials"]


def test_workload_checks_every_retained_hash_before_effect(service_owner):
    case = service_owner
    previous = complete_v7(case)
    workload_specification(case, previous)
    plan = prepare_workloads(case)
    before = targets(case)
    for index in range(5):
        bad = copy.deepcopy(plan)
        bad["predecessor_credential_sha256s"][index] = "a" * 64
        bad["digest"] = g.digest(g.canonical({key: value for key, value in bad.items() if key != "digest"}))
        (case.service_bundle / "PLAN.json").write_bytes(g.canonical(bad) + b"\n")
        with mock.patch.object(g, "atomic_bytes", side_effect=AssertionError("forged hash wrote")), \
                mock.patch.object(installer.secrets, "token_urlsafe", side_effect=AssertionError("forged hash minted")), \
                pytest.raises(ValueError):
            installer.apply_go_service_enrollment(case.service_bundle)
        assert targets(case) == before


def test_three_enrolled_workloads_reach_actual_startup_http_and_original_broker(service_owner, monkeypatch):
    import http.client
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    import socket
    import sqlite3
    import sys
    import threading

    case = service_owner
    previous = complete_v7(case)
    workload_specification(case, previous)
    prepare_workloads(case)
    installer.apply_go_service_enrollment(case.service_bundle)
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
    db, lock = case.ext / "broker/leases.sqlite", case.ext / "broker/leases.lock"
    inodes = db.stat().st_ino, lock.stat().st_ino
    posts, observed, upstream_auth = [], [], []

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
        class Upstream(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_POST(self):
                upstream_auth.append(self.headers.get("Authorization"))
                posts.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
                raw = json.dumps({"id": "workload-proof", "model": "fixture-model",
                    "choices": [{"message": {"role": "assistant", "content": "one workload effect"}}],
                    "usage": {"prompt_tokens": 3, "completion_tokens": 2}}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
        upstream = ThreadingHTTPServer(("127.0.0.1", 0), Upstream)
        loopback["ports"].add(upstream.server_port)
        loopback["post_urls"].add("http://127.0.0.1:" + str(upstream.server_port) + "/fixture-model")
        thread = threading.Thread(target=lambda: upstream.serve_forever(poll_interval=0.01), daemon=True)
        thread.start()
        try:
            with loaded_entry(case.published, clean_yaml=True) as entry:
                startup = inspect(entry, case)
                services, _, _ = entry.load_completed_application_startup(startup)
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
                def server(router, port, **kwargs):
                    result = original_server(router, 0, **kwargs)
                    loopback["ports"].add(result.server_port)
                    assert kwargs["application_services"] == services
                    assert (db.stat().st_ino, lock.stat().st_ino) == inodes
                    def serve():
                        listener = threading.Thread(target=lambda: ThreadingHTTPServer.serve_forever(
                            result, poll_interval=0.01), daemon=True)
                        listener.start()
                        def request(service, endpoint, body, turn=None):
                            headers = {"Authorization": "Bearer " + service.credential,
                                "Content-Type": "application/json"}
                            if turn is not None:
                                headers.update({"X-MM-Application-Turn-ID": turn, "Idempotency-Key": "step1",
                                    "X-MM-Application-Route-Scope-Digest": g.digest(g.canonical(service.route_scope.document))})
                            client = http.client.HTTPConnection("127.0.0.1", result.server_port, timeout=5)
                            try:
                                client.request("POST", endpoint, json.dumps(body), headers)
                                response = client.getresponse()
                                return response.status, json.loads(response.read())
                            finally:
                                client.close()
                        try:
                            for service, (name, workload, _) in zip(services[5:], ADDITIONS):
                                turn = "enrolled-" + name
                                payload = {"model": None, "max_tokens": 128, "stream": False,
                                    "messages": [{"role": "user", "content": "synthetic workload"}]}
                                status, body = request(service, "/v1/chat/completions", payload, turn)
                                assert status == 200, body
                                route = body["application"]["routing"]
                                assert body["application"]["schema"] == "mastermind.fabric_application.v2"
                                assert route["requested_model"] is None
                                assert route["selected_model"] == "fixture-model" and route["pool"] == "go"
                                assert body["application"]["usage"] == {"input_tokens": 3, "output_tokens": 2}
                                status, body = request(service, "/application-turns/close", {"turn_id": turn})
                                assert status == 200 and body["application"]["disposition"] == "closed"
                                observed.append((service.principal_id, workload, turn))
                        finally:
                            result.shutdown()
                            listener.join(2)
                            result.server_close()
                    result.serve_forever = serve
                    return result
                try:
                    with mock.patch.object(go, "make_server", side_effect=server), \
                            mock.patch.object(go.Router, "_application_exchange", exchange), \
                            mock.patch.object(go.Router, "refresh", refresh):
                        assert boot(entry, case) == 0
                finally:
                    helper = sys.modules["glm_shim"]
                    if helper._FILE_LOCK_FD is not None:
                        os.close(helper._FILE_LOCK_FD)
                        helper._FILE_LOCK_FD = None
        finally:
            upstream.shutdown()
            thread.join(2)
            upstream.server_close()
    assert len(posts) == len(observed) == 3
    assert upstream_auth == ["Bearer fixture-provider-only"] * 3
    assert all(body["model"] == "fixture-model" for body in posts)
    with sqlite3.connect(db) as connection:
        connection.row_factory = sqlite3.Row
        turns = [dict(row) for row in connection.execute("SELECT * FROM application_turns ORDER BY rowid")]
        leases = [dict(row) for row in connection.execute("SELECT * FROM leases ORDER BY rowid")]
    assert [(row["principal_id"], row["workload"], row["turn_id"]) for row in turns] == observed
    assert all(row["state"] == "released" for row in leases)
    assert {row["account"] for row in leases} == {"account-a"}
    assert (db.stat().st_ino, lock.stat().st_ino) == inodes
    unchanged_ingress(case)

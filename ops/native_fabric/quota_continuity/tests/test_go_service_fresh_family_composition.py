"""Fresh eight-role routed enrollment through the existing sealed transaction."""
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
    service_owner, unchanged_ingress, reseal_modified_entry_for_disposable_fixtures,
)
from test_go_service_family_composition import (
    NAMES, family_specification, completed_predecessor,
)
from test_go_service_routed_composition import complete_v6, targets
from test_go_service_workload_composition import (
    ADDITIONS, ALL_NAMES, complete_v7, workload_specification, prepare_workloads,
)
from test_go_service_startup import environment, inspect, boot
from test_hermes_primary_application_enrollment import isolated_native_service_imports


def fresh_specification(case, previous=None, *, additions=False):
    if additions:
        document = json.loads(case.accounts.read_bytes())
        document["providers"].setdefault("codex-native", copy.deepcopy(document["providers"]["go"]))
        case.accounts.write_bytes(g.canonical(document) + b"\n")
    base = family_specification(case)
    purpose = copy.deepcopy(base["text"]["scope"]["selection_purpose"])
    result = {"schema": installer.SERVICE_FRESH_FAMILY_SPEC_SCHEMA,
              "operation_id": "fixture-fresh-family"}
    for name in NAMES:
        scope = copy.deepcopy(base[name]["scope"])
        scope.setdefault("selection_purpose", copy.deepcopy(purpose))
        result[name] = {"scope": scope, "new_grants": []}
    for name, profile, reference in ADDITIONS:
        scope = copy.deepcopy(base["text"]["scope"])
        scope.update(principal_id="service-" + name, workload=profile,
                     workload_profile=profile, capability_lane=None, credential_ref=reference)
        result[name] = {"scope": scope, "new_grants": []}
    if previous:
        scopes = previous.get("scopes", [previous.get("scope")])
        for name, scope in zip(ALL_NAMES, scopes):
            result[name]["scope"] = copy.deepcopy(scope)
    for name in ALL_NAMES:
        scope = result[name]["scope"]
        scope.setdefault("selection_purpose", copy.deepcopy(purpose))
        scope.setdefault("route_scope", {"schema": "mastermind.application_route_scope.v1",
                                        "pools": ["codex-native"]})
        if additions:
            grant = copy.deepcopy(case.specification["grant"])
            grant.update(grant_id="fixture-fresh-" + name, pool="codex-native",
                         principal_id=scope["principal_id"], credential_ref=scope["credential_ref"],
                         admission_root="service:" + name, caller_hosts=[scope["caller_host"]],
                         workloads=[scope["workload"]], transport_kind="native_cli_operation_v1",
                         recipe_digest="a" * 64, output_limit_mode="hard_maximum",
                         usage_policy="nullable_operation")
            result[name]["new_grants"] = [grant]
    case.fresh = result
    return result


def prepare_fresh(case):
    return installer.prepare_go_service_enrollment(case.go_bundle, case.fresh, case.service_bundle)


def prior_family(case, version):
    if version is None:
        return None
    if version in ("v1", "v3", "v4", "v5"):
        return completed_predecessor(case, version)
    if version == "v6":
        return complete_v6(case)
    if version == "v7":
        return complete_v7(case)
    if version == "v8":
        previous = complete_v7(case)
        workload_specification(case, previous)
        prepare_workloads(case)
    else:
        assert version == "v10"
        fresh_specification(case)
        prepare_fresh(case)
    installer.apply_go_service_enrollment(case.service_bundle)
    previous = json.loads(case.binding.read_bytes())
    case.previous_bundle = case.service_bundle
    case.service_bundle = case.root / ("service-fresh-after-" + version)
    return previous


@pytest.mark.parametrize("additions", [False, True])
def test_fresh_eight_roles_need_no_go_grant_and_keep_the_original_owner(service_owner, monkeypatch, additions):
    case = service_owner
    fresh_specification(case, additions=additions)
    before = case.accounts.read_bytes()
    with mock.patch.object(installer.secrets, "token_urlsafe", side_effect=AssertionError("prepare minted")):
        plan = prepare_fresh(case)
        assert installer.reconcile_go_service_enrollment(case.service_bundle)["disposition"] == "prepared"
    assert plan["predecessor_schema"] is None
    with mock.patch.object(installer.secrets, "token_urlsafe", wraps=installer.secrets.token_urlsafe) as minted:
        receipt = installer.apply_go_service_enrollment(case.service_bundle)
    assert minted.call_count == 8
    current = json.loads(case.binding.read_bytes())
    assert current["schema"] == "mastermind.native_go_application_service.v10"
    assert receipt["schema"] == "native-go-service-enrollment-completed.v10"
    assert len(current["credentials"]) == len(set(current["credentials"])) == 8
    assert current["scopes"] == receipt["scopes"] == [case.fresh[name]["scope"] for name in ALL_NAMES]
    if additions:
        grants = json.loads(case.accounts.read_bytes())["application_grants"]
        assert len(grants) == 8 and {grant["pool"] for grant in grants} == {"codex-native"}
    else:
        assert case.accounts.read_bytes() == before
        assert installer._service_set_expiry(case.fresh) is None
    assert all(token not in json.dumps(plan) + json.dumps(receipt) for token in current["credentials"])
    with mock.patch.object(g, "atomic_bytes", side_effect=AssertionError("completed replay wrote")), \
            mock.patch.object(installer.secrets, "token_urlsafe", side_effect=AssertionError("completed replay minted")):
        assert installer.apply_go_service_enrollment(case.service_bundle) == receipt
        assert installer.reconcile_go_service_enrollment(case.service_bundle) == receipt
    environment(monkeypatch, case)
    with loaded_entry(case.published, clean_yaml=True) as entry:
        startup = inspect(entry, case)
        services, host, profile = entry.load_all_completed_application_startup(startup)
        assert len(services) == 8 and host == "fixture-native" and profile == case.profile
        assert [service.credential for service in services] == current["credentials"]
        assert all(service.route_scope.document["pools"] == ["codex-native"] for service in services)
        assert all(service.selection_purpose is not None for service in services)
    unchanged_ingress(case)


@pytest.mark.parametrize("version,count", [
    ("v1", 1), ("v3", 1), ("v4", 1), ("v5", 2), ("v6", 5), ("v7", 5), ("v8", 8), ("v10", 8),
])
def test_every_completed_family_preserves_tokens_and_current_grants(service_owner, version, count):
    case = service_owner
    previous = prior_family(case, version)
    old_bundle = case.previous_bundle if hasattr(case, "previous_bundle") else None
    fresh_specification(case, previous)
    before = case.accounts.read_bytes()
    plan = prepare_fresh(case)
    assert len(plan["predecessor_credential_sha256s"]) == count
    with mock.patch.object(installer.secrets, "token_urlsafe", wraps=installer.secrets.token_urlsafe) as minted:
        receipt = installer.apply_go_service_enrollment(case.service_bundle)
    assert minted.call_count == 8 - count
    current = json.loads(case.binding.read_bytes())
    old_tokens = previous.get("credentials", [previous.get("credential")])
    old_scopes = previous.get("scopes", [previous.get("scope")])
    assert current["credentials"][:count] == old_tokens
    for old, new in zip(old_scopes, current["scopes"][:count]):
        assert all(new[key] == value for key, value in old.items())
    assert case.accounts.read_bytes() == before
    with mock.patch.object(g, "atomic_bytes", side_effect=AssertionError("completed replay wrote")), \
            mock.patch.object(installer.secrets, "token_urlsafe", side_effect=AssertionError("completed replay minted")):
        assert installer.apply_go_service_enrollment(case.service_bundle) == receipt
        assert installer.reconcile_go_service_enrollment(case.service_bundle) == receipt
    if old_bundle:
        snapshot = targets(case)
        with pytest.raises(ValueError):
            installer.apply_go_service_enrollment(old_bundle)
        assert targets(case) == snapshot
    unchanged_ingress(case)


def test_fresh_family_rejects_authority_substitution_before_runtime_effects(service_owner):
    case = service_owner
    original = fresh_specification(case, additions=True)
    before = targets(case)
    faults = ("missing-role", "extra-role", "missing-purpose", "missing-route", "wrong-lane",
              "wrong-profile", "wrong-reference", "wrong-owner", "outside-pool", "wrong-principal",
              "worker-purpose", "streaming", "unknown-grant-field", "expired", "overlap")
    for index, fault in enumerate(faults):
        spec = copy.deepcopy(original)
        scope, grant = spec["analysis"]["scope"], spec["analysis"]["new_grants"][0]
        if fault == "missing-role": del spec["portfolio"]
        elif fault == "extra-role": spec["terminal"] = copy.deepcopy(spec["analysis"])
        elif fault == "missing-purpose": del scope["selection_purpose"]
        elif fault == "missing-route": del scope["route_scope"]
        elif fault == "wrong-lane": scope["capability_lane"] = "cortex"
        elif fault == "wrong-profile": scope["workload_profile"] = "site_interactive"
        elif fault == "wrong-reference": scope["credential_ref"] = "OTHER_TOKEN"
        elif fault == "wrong-owner": scope["native_host"] = "other-host"
        elif fault == "outside-pool": grant["pool"] = "go"
        elif fault == "wrong-principal": grant["principal_id"] = "other-principal"
        elif fault == "worker-purpose": grant["purpose"] = "WORKER"
        elif fault == "streaming": grant["stream"] = True
        elif fault == "unknown-grant-field": grant["inferred_permission"] = True
        elif fault == "expired": grant["expires_at"] = time.time() - 1
        elif fault == "overlap": spec["analysis"]["new_grants"].append(copy.deepcopy(grant))
        output = case.root / ("fresh-refused-" + str(index))
        with mock.patch.object(installer.secrets, "token_urlsafe", side_effect=AssertionError("refused mint")), \
                pytest.raises(ValueError):
            installer.prepare_go_service_enrollment(case.go_bundle, spec, output)
        assert targets(case) == before


def test_all_eight_retained_hashes_are_authoritative_before_any_new_effect(service_owner):
    case = service_owner
    previous = prior_family(case, "v10")
    fresh_specification(case, previous)
    plan = prepare_fresh(case)
    before = targets(case)
    for index in range(8):
        bad = copy.deepcopy(plan)
        bad["predecessor_credential_sha256s"][index] = "a" * 64
        bad["digest"] = g.digest(g.canonical({key: value for key, value in bad.items() if key != "digest"}))
        (case.service_bundle / "PLAN.json").write_bytes(g.canonical(bad) + b"\n")
        with mock.patch.object(g, "atomic_bytes", side_effect=AssertionError("forged hash wrote")), \
                mock.patch.object(installer.secrets, "token_urlsafe", side_effect=AssertionError("forged hash minted")), \
                pytest.raises(ValueError):
            installer.apply_go_service_enrollment(case.service_bundle)
        assert targets(case) == before


@pytest.mark.parametrize("state", ["empty", "disabled", "expired", "narrowed", "deleted"])
def test_fresh_successor_never_recreates_or_renews_existing_grants(service_owner, state):
    case = service_owner
    previous = prior_family(case, "v8")
    document = json.loads(case.accounts.read_bytes())
    grants = document["application_grants"]
    if state == "empty":
        document["application_grants"] = []
    elif state == "disabled":
        grants[0]["enabled"] = False
    elif state == "expired":
        grants[0]["expires_at"] = time.time() - 1
    elif state == "narrowed":
        grants[0]["accounts"] = ["account-a"]
        grants[0]["max_steps"] = 1
    else:
        grants.pop(0)
    case.accounts.write_bytes(g.canonical(document) + b"\n")
    before = case.accounts.read_bytes()
    fresh_specification(case, previous)
    prepare_fresh(case)
    installer.apply_go_service_enrollment(case.service_bundle)
    assert case.accounts.read_bytes() == before
    assert json.loads(case.binding.read_bytes())["credentials"] == previous["credentials"]


def test_identity_only_does_not_relax_existing_grant_parser(service_owner):
    case = service_owner
    fresh_specification(case)
    original = json.loads(case.accounts.read_bytes())
    for index, invalid in enumerate((None, {}, [{"malformed": True}])):
        case.accounts.write_bytes(g.canonical({**original, "application_grants": invalid}) + b"\n")
        before = targets(case)
        output = case.root / ("invalid-existing-grants-" + str(index))
        with mock.patch.object(installer.secrets, "token_urlsafe", side_effect=AssertionError("invalid mint")), \
                pytest.raises(ValueError):
            installer.prepare_go_service_enrollment(case.go_bundle, case.fresh, output)
        assert targets(case) == before


def test_fresh_successor_preserves_existing_scope_authority(service_owner):
    case = service_owner
    previous = prior_family(case, "v10")
    original = fresh_specification(case, previous)
    before = targets(case)
    for index, fault in enumerate(("route", "purpose", "principal", "workload", "metadata")):
        spec = copy.deepcopy(original)
        scope = spec["admin"]["scope"]
        if fault == "route": scope["route_scope"]["pools"] = ["go"]
        elif fault == "purpose": scope["selection_purpose"]["source_ref"] = "fixture:substituted"
        elif fault == "principal": scope["principal_id"] = "substituted-principal"
        elif fault == "workload": scope["workload"] = "substituted-workload"
        else: scope["admin_pool_view"] = not scope["admin_pool_view"]
        with pytest.raises(ValueError):
            installer.prepare_go_service_enrollment(
                case.go_bundle, spec, case.root / ("invalid-scope-" + str(index)))
        assert targets(case) == before


@pytest.mark.parametrize("boundary", ["private", "private-progress", "intent", "binding", "accounts", "receipt"])
def test_fresh_interruption_keeps_eight_original_mints(service_owner, boundary):
    case = service_owner
    fresh_specification(case, additions=True)
    plan = prepare_fresh(case)
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
            raise OSError("fixture fresh ACK lost")
    def renamed(source, target):
        original_replace(source, target)
        if boundary in paths and Path(target) == named[boundary] and not hit:
            hit.append(boundary)
            raise OSError("fixture fresh ACK lost")
    with mock.patch.object(installer.secrets, "token_urlsafe", wraps=installer.secrets.token_urlsafe) as minted, \
            mock.patch.object(g, "atomic_bytes", side_effect=written), \
            mock.patch.object(os, "replace", side_effect=renamed), pytest.raises(OSError, match="fresh ACK"):
        installer.apply_go_service_enrollment(case.service_bundle)
    assert hit == [boundary] and minted.call_count == 8
    private = json.loads((case.service_bundle / installer._SERVICE_PRIVATE).read_bytes())
    with mock.patch.object(installer.secrets, "token_urlsafe", side_effect=AssertionError("fresh reminted")):
        if boundary == "private":
            for action in (installer.apply_go_service_enrollment, installer.reconcile_go_service_enrollment):
                with mock.patch.object(g, "atomic_bytes", side_effect=AssertionError("uncommitted adopted")), \
                        pytest.raises(ValueError, match="adoption refused"):
                    action(case.service_bundle)
            assert targets(case) == before
            return
        result = installer.reconcile_go_service_enrollment(case.service_bundle)
        receipt = installer.apply_go_service_enrollment(case.service_bundle) if "disposition" in result else result
        assert receipt["schema"] == "native-go-service-enrollment-completed.v10"
        assert json.loads(case.binding.read_bytes())["credentials"] == private["credentials"]
        with mock.patch.object(g, "atomic_bytes", side_effect=AssertionError("completed replay wrote")):
            assert installer.apply_go_service_enrollment(case.service_bundle) == receipt


@pytest.mark.parametrize("target", ["binding", "intent", "receipt", "predecessor", "accounts"])
def test_fresh_successor_requires_original_predecessor_inodes(service_owner, target):
    case = service_owner
    previous = prior_family(case, "v10")
    fresh_specification(case, previous)
    prepare_fresh(case)
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


def completed_sibling(case):
    import importlib.util
    path = Path(__file__).resolve().parents[4] / "tests/test_hermes_primary_application_enrollment.py"
    spec = importlib.util.spec_from_file_location("fresh_family_role_fixture", path)
    role_fixture = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(role_fixture)
    names = ("specification", "service_bundle", "binding", "intent", "service_receipt")
    saved = {name: getattr(case, name) for name in names}
    try:
        role_fixture.routed_role(case, "hermes-secretary")
        installer.prepare_go_service_enrollment(case.go_bundle, case.specification, case.service_bundle)
        installer.apply_go_service_enrollment(case.service_bundle)
        return {name: getattr(case, name) for name in names}
    finally:
        for name, value in saved.items():
            setattr(case, name, value)


@pytest.mark.parametrize("fault", [None, "partial", "principal", "physical-owner"])
def test_fresh_family_respects_existing_hermes_sibling(service_owner, monkeypatch, fault):
    case = service_owner
    sibling = completed_sibling(case)
    raw = sibling["binding"].read_bytes()
    fresh_specification(case)
    if fault == "partial":
        sibling["service_receipt"].unlink()
    elif fault == "principal":
        case.fresh["admin"]["scope"]["principal_id"] = "hermes-secretary"
    elif fault == "physical-owner":
        for name in ALL_NAMES:
            case.fresh[name]["scope"]["native_host"] = "other-physical-host"
    before = targets(case)
    if fault is not None:
        with mock.patch.object(installer.secrets, "token_urlsafe", side_effect=AssertionError("sibling minted")), \
                pytest.raises(ValueError):
            prepare_fresh(case)
        assert targets(case) == before
    else:
        prepare_fresh(case)
        installer.apply_go_service_enrollment(case.service_bundle)
        environment(monkeypatch, case)
        with loaded_entry(case.published, clean_yaml=True) as entry:
            services, _, profile = entry.load_all_completed_application_startup(inspect(entry, case))
            assert len(services) == 9 and profile == case.profile
            assert len({service.principal_id for service in services}) == 9
        assert sibling["binding"].read_bytes() == raw


@pytest.mark.parametrize("empty_go_profile", [False, True])
def test_fresh_non_go_identities_reach_real_listener_without_go_upstream(service_owner, monkeypatch, empty_go_profile):
    import http.client
    from http.server import ThreadingHTTPServer
    import socket
    import sys
    import threading
    import urllib.request

    case = service_owner
    if empty_go_profile:
        case.profile.write_text("{}")
    fresh_specification(case)
    prepare_fresh(case)
    installer.apply_go_service_enrollment(case.service_bundle)
    environment(monkeypatch, case)
    attempts, replies = [], []
    with historical.numeric_loopback_network() as loopback:
        original_connect, original_bind = socket.socket.connect, socket.socket.bind
        def guarded(function):
            def call(sock, address):
                if not isinstance(address, tuple) or address[0] != "127.0.0.1":
                    attempts.append(("socket", str(address)))
                    raise AssertionError("unexpected upstream connection")
                return function(sock, address)
            return call
        monkeypatch.setattr(socket.socket, "connect", guarded(original_connect))
        monkeypatch.setattr(socket.socket, "bind", guarded(original_bind))
        monkeypatch.setattr(socket, "getfqdn", lambda address: "fixture-loopback")
        def forbidden_request(request, *args, **kwargs):
            attempts.append(("urlopen", str(getattr(request, "full_url", request))))
            raise AssertionError("unexpected upstream request")
        monkeypatch.setattr(urllib.request, "urlopen", forbidden_request)
        with loaded_entry(case.published, clean_yaml=True) as entry:
            startup = inspect(entry, case)
            services, _, _ = entry.load_all_completed_application_startup(startup)
            go = startup.handler
            original_server = go.make_server
            def server(router, port, **kwargs):
                result = original_server(router, 0, **kwargs)
                loopback["ports"].add(result.server_port)
                assert kwargs["application_services"] == services
                def serve():
                    listener = threading.Thread(target=lambda: ThreadingHTTPServer.serve_forever(
                        result, poll_interval=0.01), daemon=True)
                    listener.start()
                    try:
                        for index, service in enumerate(services):
                            client = http.client.HTTPConnection("127.0.0.1", result.server_port, timeout=5)
                            try:
                                headers = {"Authorization": "Bearer " + service.credential,
                                    "Content-Type": "application/json",
                                    "X-MM-Application-Turn-ID": "fresh-no-go-" + str(index),
                                    "Idempotency-Key": "step1",
                                    "X-MM-Application-Route-Scope-Digest": g.digest(
                                        g.canonical(service.route_scope.document))}
                                payload = {"model": None, "max_tokens": 128, "stream": False,
                                    "messages": [{"role": "user", "content": "synthetic no-Go request"}]}
                                client.request("POST", "/v1/chat/completions", json.dumps(payload), headers)
                                response = client.getresponse()
                                body = json.loads(response.read())
                                replies.append((service.principal_id, response.status, body))
                                assert response.status == 409, body
                                assert body["application"]["disposition"] == "refused"
                                assert body["error"]["type"] == "application_selection_refused"
                            finally:
                                client.close()
                    finally:
                        result.shutdown()
                        listener.join(2)
                        result.server_close()
                result.serve_forever = serve
                return result
            try:
                with mock.patch.object(go, "make_server", side_effect=server):
                    assert boot(entry, case) == 0
            finally:
                helper = sys.modules["glm_shim"]
                if helper._FILE_LOCK_FD is not None:
                    os.close(helper._FILE_LOCK_FD)
                    helper._FILE_LOCK_FD = None
    assert attempts == []
    assert len(replies) == 8
    unchanged_ingress(case)


@pytest.mark.parametrize("boundary", ["intent", "binding"])
def test_prepared_hermes_role_cannot_publish_over_partial_fresh_family(service_owner, boundary):
    import importlib.util
    case = service_owner
    path = Path(__file__).resolve().parents[4] / "tests/test_hermes_primary_application_enrollment.py"
    module_spec = importlib.util.spec_from_file_location("fresh_family_delayed_role_fixture", path)
    fixture = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(fixture)
    names = ("specification", "service_bundle", "binding", "intent", "service_receipt")
    family = {name: getattr(case, name) for name in names}
    fixture.routed_role(case, "hermes-secretary")
    installer.prepare_go_service_enrollment(case.go_bundle, case.specification, case.service_bundle)
    role = {name: getattr(case, name) for name in names}
    for name, value in family.items():
        setattr(case, name, value)
    fresh_specification(case)
    prepare_fresh(case)
    original = os.replace
    def interrupted(source, target):
        original(source, target)
        if Path(target) == getattr(case, boundary):
            raise OSError("fixture family partial publication")
    with mock.patch.object(os, "replace", side_effect=interrupted), pytest.raises(OSError):
        installer.apply_go_service_enrollment(case.service_bundle)
    before = targets(case)
    with mock.patch.object(installer.secrets, "token_urlsafe", side_effect=AssertionError("competing role mint")), \
            pytest.raises(ValueError):
        installer.apply_go_service_enrollment(role["service_bundle"])
    assert targets(case) == before
    assert not any(role[name].exists() for name in ("intent", "binding", "service_receipt"))
    with mock.patch.object(installer.secrets, "token_urlsafe", side_effect=AssertionError("original family remint")):
        receipt = installer.apply_go_service_enrollment(case.service_bundle)
    assert receipt["schema"] == "native-go-service-enrollment-completed.v10"

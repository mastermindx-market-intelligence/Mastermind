"""Installed owner wiring; all source records and transports here are synthetic."""
from __future__ import annotations

import copy
import dataclasses
import hashlib
import importlib
import json
import os
from pathlib import Path

import pytest

from integrations.session_bridge.installed import validate_private_frame, principal_frame
from tests.test_session_bridge_installed import PRINCIPAL


def test_private_census_is_closed_read_only():
    from common.session_bridge_private_contract import SESSION_TOOLS, MODIFYING_TOOLS, PRIVATE_SCHEMA
    assert "session_web_census" in SESSION_TOOLS
    assert "session_web_census" not in MODIFYING_TOOLS
    frame = {"schema": PRIVATE_SCHEMA, "tool": "session_web_census",
             "principal": principal_frame(PRINCIPAL), "arguments": {}}
    assert validate_private_frame(frame)[0] == "session_web_census"
    from integrations.session_bridge.schemas import BridgeError
    for injected in ({"binding_id": "other"}, {"grants": []}, {"profile_owner_uid": os.getuid()},
                     {"socket_path": "/tmp/other"}, {"adapter_instance_id": "a" * 64},
                     {"expected_revision": "b" * 64}):
        with pytest.raises(BridgeError):
            validate_private_frame(dict(frame, arguments=injected))


def test_owner_module_has_no_default_source():
    module = importlib.import_module("integrations.session_bridge.installed_web_observation")
    with pytest.raises(TypeError):
        module.ObservationPermissionReader()


def test_installed_entry_has_explicit_optional_composition():
    from ops.executive_os import executive_mcp_entry as entry
    assert entry.installed_web_observation_owner(
        Path("/not-an-install"), Path("/not-a-release"), expected_uid=os.geteuid(),
        initial={}) is None


import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

from common.session_bridge_private_contract import BridgeError, PRIVATE_SCHEMA
from integrations.business_mcp_auth.contracts import VerifiedPrincipal, client_ref_digest
from integrations.business_mcp_auth.principal_projection import principal_projection
from integrations.chairman_surfaces import web_sol_instance
from integrations.session_bridge import installed_web_observation as observation
from integrations.session_bridge.web_observation_tools import OBSERVE_TOOL
from tests import test_mastermind_executive_app_asgi as auth
from tests.test_web_sol_fleet_transport import managed_binding
from tests.test_session_web_observation import receipt


def bundle(*, clock=None):
    policy = auth._read_policy()
    binding = managed_binding()
    adapter = web_sol_instance.adapter_instance_id(binding)
    uid = os.getuid() if os.getuid() > 0 else 501
    block = {"schema": observation.CONFIG_SCHEMA, "source": {
        "binding_id": binding["binding_id"], "adapter_instance_id": adapter,
        "profile_owner_uid": uid}, "permissions": {"generation": "a" * 64,
        "principals": [{"policy_id": policy.policy_id, "resource": policy.resource,
            "issuer_digest": hashlib.sha256(policy.issuer.encode()).hexdigest(),
            "subject_digest": policy.allowed_subject_digests[0],
            "client_ref": client_ref_digest(issuer=policy.issuer, client_id="e1-test-client"),
            "adapter_instance_id": adapter}]}}
    principal = VerifiedPrincipal(policy.policy_id, policy.issuer,
        hashlib.sha256(policy.issuer.encode()).hexdigest(), policy.resource,
        policy.allowed_subject_digests[0], block["permissions"]["principals"][0]["client_ref"],
        policy.required_scopes, auth.NOW, auth.NOW + 300, None)
    state = [observation.observation_state(block, (policy,), "d" * 64)]
    now = [datetime.fromtimestamp(auth.NOW + 1, timezone.utc)]
    owner = observation.ObservationPermissionReader(load_state=lambda: state[0],
        clock=clock or (lambda: now[0]))
    return SimpleNamespace(block=block, policy=policy, binding=binding, adapter=adapter,
        principal=principal, projected=principal_projection(principal),
        state=state, now=now, owner=owner)


def installation_document(block):
    from ops.executive_os import executive_mcp_entry as entry
    return {"schema": entry.CONFIG_SCHEMA, "release_sha": "a" * 40,
        "service_uid": 458, "ceo_ingress_socket_path": "/var/run/mastermind-executive/ceo-ingress.sock",
        "port": 8443, "audit_root": "/var/log/mastermind-executive/mcp-auth",
        "policies": json.loads(json.dumps({"read": dataclasses.asdict(auth._read_policy()),
                                          "submit": dataclasses.asdict(auth._submit_policy())})),
        "executive_mcp_profile": "web_ceo_v3", "session_web_observation": copy.deepcopy(block)}


def configured_owner(tmp_path, monkeypatch, *, clock=None):
    from ops.executive_os import executive_mcp_entry as entry
    from control_plane import fs_security
    b = bundle(clock=clock)
    raw = installation_document(b.block)
    source = tmp_path / raw["release_sha"]
    source.mkdir()
    path = tmp_path / "installed.json"
    path.write_text(json.dumps(raw))
    path.chmod(0o600)
    # Test-only substitute for root provisioning; real validators, file instance,
    # fixed policy/source comparisons and before/after reads are retained.
    monkeypatch.setattr(entry, "require_sealed_path", lambda *a, **k: None)
    monkeypatch.setattr(fs_security, "has_macos_acl", lambda *a, **k: False)
    b.owner = entry.installed_web_observation_owner(path, source,
        expected_uid=os.geteuid(), clock=clock or (lambda: b.now[0]))
    b.raw, b.path, b.source = raw, path, source
    return b


@pytest.mark.parametrize("mutation", [
    "unknown_block", "schema", "source_extra", "root_uid", "bool_uid", "negative_uid",
    "owner_string", "binding_id", "adapter_id", "permissions_extra", "generation",
    "principal_not_list", "too_many", "duplicate", "role", "group", "foreign_policy",
    "foreign_resource", "foreign_subject", "foreign_issuer", "missing_client",
    "foreign_adapter", "unknown_grant",
])
def test_closed_owner_projection_refuses_unknown_or_unenrolled_grants(mutation):
    b = bundle()
    value = copy.deepcopy(b.block)
    source, permissions = value["source"], value["permissions"]
    grant = permissions["principals"][0]
    if mutation == "unknown_block": value["collector"] = "new"
    elif mutation == "schema": value["schema"] = "unknown"
    elif mutation == "source_extra": source["socket"] = "/tmp/other"
    elif mutation == "root_uid": source["profile_owner_uid"] = 0
    elif mutation == "bool_uid": source["profile_owner_uid"] = True
    elif mutation == "negative_uid": source["profile_owner_uid"] = -1
    elif mutation == "owner_string": source["profile_owner_uid"] = "501"
    elif mutation == "binding_id": source["binding_id"] = "not-a-uuid"
    elif mutation == "adapter_id": source["adapter_instance_id"] = "not-a-digest"
    elif mutation == "permissions_extra": permissions["enabled"] = True
    elif mutation == "generation": permissions["generation"] = ""
    elif mutation == "principal_not_list": permissions["principals"] = {}
    elif mutation == "too_many": permissions["principals"] *= 17
    elif mutation == "duplicate": permissions["principals"] *= 2
    elif mutation in {"role", "group"}: grant[mutation] = "Meta-CEO"
    elif mutation == "foreign_policy": grant["policy_id"] = "other"
    elif mutation == "foreign_resource": grant["resource"] = "https://foreign.test/mcp"
    elif mutation == "foreign_subject": grant["subject_digest"] = "f" * 64
    elif mutation == "foreign_issuer": grant["issuer_digest"] = "f" * 64
    elif mutation == "missing_client": grant["client_ref"] = "oauth-client-unavailable"
    elif mutation == "foreign_adapter": grant["adapter_instance_id"] = "f" * 64
    elif mutation == "unknown_grant": grant["all_sessions"] = True
    with pytest.raises(ValueError, match="installed observation configuration is invalid"):
        observation.parse_configuration(value, (b.policy,))


@pytest.mark.parametrize("profile", ["legacy", "personal_read", "web_ceo_v2", "web_ceo_sessions_v1"])
def test_owner_requires_explicit_v3_profile(profile):
    from ops.executive_os import executive_mcp_entry as entry
    raw = installation_document(bundle().block)
    raw["executive_mcp_profile"] = profile
    with pytest.raises(ValueError):
        entry.validate_document(raw)


@pytest.mark.parametrize("field,value", [
    ("policy_id", "other"), ("resource", "https://other.test/mcp"),
    ("subject_digest", "e" * 64), ("client_ref", "e" * 64),
    ("scopes", ("mastermind.executive.read", "foreign.read")),
])
def test_exact_principal_identity_cannot_inherit_a_profile_grant(field, value):
    b = bundle()
    other = dataclasses.replace(b.principal, **{field: value})
    assert b.owner.public_scope(other).adapter_instance_ids == ()
    with pytest.raises(BridgeError, match="authorized profile-local observation"):
        b.owner.select(principal_projection(other), required=True)


@pytest.mark.parametrize("change", [
    {"issued_at": auth.NOW + 10}, {"expires_at": auth.NOW}, {"issued_at": True},
    {"expires_at": False}, {"expires_at": auth.NOW + 901},
    {"client_ref": "oauth-client-unavailable"}, {"issuer_digest": "e" * 64},
    {"jti_digest": "bad"}, {"scopes": ()},
])
def test_invalid_or_stale_private_principal_is_refused(change):
    b = bundle()
    changed = dataclasses.replace(b.projected, **change)
    with pytest.raises(BridgeError):
        b.owner.select(changed, required=True)


def test_exact_issuer_and_client_are_not_reconstructed_from_role_or_subject():
    b = bundle()
    foreign_issuer = "https://other-auth.test/"
    principal = dataclasses.replace(b.principal, issuer=foreign_issuer,
        issuer_digest=hashlib.sha256(foreign_issuer.encode()).hexdigest())
    assert b.owner.public_scope(principal).adapter_instance_ids == ()
    with pytest.raises(Exception):
        b.owner.public_scope(dataclasses.asdict(b.principal))
    assert b.owner.public_scope(b.principal).workstreams == ()


def test_empty_grants_do_not_contact_any_private_or_browser_owner():
    b = bundle()
    empty = copy.deepcopy(b.block)
    empty["permissions"]["principals"] = []
    b.state[0] = observation.observation_state(empty, (b.policy,), "c" * 64)
    class Client:
        async def web_census(self, principal):
            pytest.fail("no grant may contact the private owner")
    result = asyncio.run(b.owner.network_tools(Client()).handle(b.principal, OBSERVE_TOOL, {}))
    assert result["ok"] is True
    assert result["data"]["sources"] == []


@pytest.mark.parametrize("fault", ["none", "revoke", "generation", "expired", "guard", "binding", "too_large"])
def test_private_collector_rechecks_after_the_original_read(monkeypatch, fault):
    b = bundle()
    reads, sources, guards = [], [], [True]
    def current(source):
        sources.append(source)
        return copy.deepcopy(b.binding), ("changed" if fault == "binding" and reads else "original",)
    monkeypatch.setattr(observation, "_current_source", current)
    from integrations.chairman_surfaces import web_sol_client
    def collect(binding, **request):
        reads.append(request)
        assert set(request) == {"operation_key", "nonce", "issued_at", "expires_at"}
        assert len(request["nonce"]) == 32
        window = (datetime.fromisoformat(request["expires_at"].replace("Z", "+00:00"))
                  - datetime.fromisoformat(request["issued_at"].replace("Z", "+00:00"))).total_seconds()
        assert 0 < window <= 8
        if fault == "revoke":
            b.state[0] = dataclasses.replace(b.state[0], grants=())
        elif fault == "generation":
            b.state[0] = dataclasses.replace(b.state[0], revision="f" * 64)
        elif fault == "expired":
            b.now[0] = datetime.fromtimestamp(auth.NOW + 300, timezone.utc)
        elif fault == "guard":
            guards[0] = False
        if fault == "too_large": return {"synthetic_size": "x" * 40000}
        return receipt(adapter=b.adapter)
    monkeypatch.setattr(web_sol_client, "census_via_extension", collect)
    collector = observation.InstalledProfileCensus(b.owner, current_guard=lambda: guards[0])
    if fault == "none":
        result = asyncio.run(collector(b.projected, {}))
        assert result["owner_revision"] == b.state[0].revision
        assert result["receipt"]["adapter_instance_id"] == b.adapter
    else:
        with pytest.raises(BridgeError):
            asyncio.run(collector(b.projected, {}))
    assert len(reads) == 1


@pytest.mark.parametrize("fault", ["root", "different_uid", "effective_uid", "real_uid"])
def test_unowned_profile_refuses_before_any_profile_io(monkeypatch, fault):
    b = bundle()
    source = b.state[0].source
    owner_uid = source.profile_owner_uid
    monkeypatch.setattr(observation, "_profile_home", lambda uid: pytest.fail("unowned profile I/O"))
    if fault == "root":
        source = dataclasses.replace(source, profile_owner_uid=0)
        monkeypatch.setattr(observation.os, "getuid", lambda: 0)
        monkeypatch.setattr(observation.os, "geteuid", lambda: 0)
    elif fault == "different_uid":
        monkeypatch.setattr(observation.os, "getuid", lambda: owner_uid + 1)
        monkeypatch.setattr(observation.os, "geteuid", lambda: owner_uid + 1)
    elif fault == "effective_uid":
        monkeypatch.setattr(observation.os, "geteuid", lambda: owner_uid + 1)
    else:
        monkeypatch.setattr(observation.os, "getuid", lambda: owner_uid + 1)
    with pytest.raises(BridgeError):
        observation._current_source(source)


@pytest.mark.parametrize("fault", ["symlink", "permissive_file", "permissive_parent", "moving",
                                   "warning", "duplicate", "adapter"])
def test_profile_binding_has_outer_custody_and_exact_join(tmp_path, monkeypatch, fault):
    b = bundle()
    home = tmp_path / "profile"
    path = home / "Library/Application Support/Mastermind/control-room/surface_bindings.json"
    path.parent.mkdir(parents=True, mode=0o700)
    for parent in (home, path.parent): parent.chmod(0o700)
    from control_plane import surface_bindings, fs_security
    document = {"schema": surface_bindings.SCHEMA, "bindings": [b.binding]}
    path.write_text(json.dumps(document)); path.chmod(0o600)
    monkeypatch.setattr(observation, "_profile_home", lambda uid: home)
    monkeypatch.setattr(fs_security, "has_macos_acl", lambda *a, **k: False)
    if fault == "symlink":
        other = path.with_name("other.json"); path.rename(other); path.symlink_to(other)
    elif fault == "permissive_file": path.chmod(0o644)
    elif fault == "permissive_parent": path.parent.chmod(0o755)
    elif fault == "moving":
        original = surface_bindings.load_bindings
        def moving(selected):
            result = original(selected)
            selected.write_text(selected.read_text() + " ")
            return result
        monkeypatch.setattr(surface_bindings, "load_bindings", moving)
    elif fault == "warning":
        monkeypatch.setattr(surface_bindings, "load_bindings", lambda selected: (document, ["private path"]))
    elif fault == "duplicate":
        monkeypatch.setattr(surface_bindings, "load_bindings",
                            lambda selected: ({**document, "bindings": [b.binding, b.binding]}, []))
    elif fault == "adapter":
        source = dataclasses.replace(b.state[0].source, adapter_instance_id="f" * 64)
        b.state[0] = dataclasses.replace(b.state[0], source=source)
    monkeypatch.setattr(web_sol_instance, "socket_path", lambda *a, **k: pytest.fail("invalid binding reached socket"))
    with pytest.raises(BridgeError):
        observation._current_source(b.state[0].source)


@pytest.mark.parametrize("fault", ["none", "revision", "adapter", "unknown_field", "revoked", "oversize"])
def test_network_read_uses_one_private_frame_and_withholds_mismatches(fault):
    b = bundle()
    calls = []
    class Client:
        async def web_census(self, principal):
            calls.append(principal)
            if fault == "oversize": raise BridgeError("output_too_large", "PRIVATE-SENTINEL")
            result = {"schema": observation.RESULT_SCHEMA, "owner_revision": b.state[0].revision,
                      "receipt": receipt(adapter=b.adapter)}
            if fault == "revision": result["owner_revision"] = "f" * 64
            elif fault == "adapter": result["receipt"] = receipt(adapter="f" * 64)
            elif fault == "unknown_field": result["secret"] = "PRIVATE-SENTINEL"
            elif fault == "revoked": b.state[0] = dataclasses.replace(b.state[0], grants=())
            return result
    result = asyncio.run(b.owner.network_tools(Client()).handle(b.principal, OBSERVE_TOOL, {}))
    assert len(calls) == 1
    assert result["ok"] is (fault == "none")
    if fault != "none": assert result["data"] is None
    if fault == "oversize": assert result["error"]["code"] == "output_too_large"
    assert "PRIVATE-SENTINEL" not in json.dumps(result)


@pytest.mark.parametrize("fault", ["generation", "same_contents_replace", "revoke", "source",
                                   "policy", "block_removed", "other_config"])
def test_sealed_installation_rotates_only_permission_projection(tmp_path, monkeypatch, fault):
    b = configured_owner(tmp_path, monkeypatch)
    before = b.owner.public_scope(b.principal)
    raw = copy.deepcopy(b.raw)
    if fault == "generation": raw["session_web_observation"]["permissions"]["generation"] = "e" * 64
    elif fault == "same_contents_replace": pass
    elif fault == "revoke": raw["session_web_observation"]["permissions"]["principals"] = []
    elif fault == "source": raw["session_web_observation"]["source"]["profile_owner_uid"] += 1
    elif fault == "policy": raw["policies"]["read"]["max_token_lifetime_seconds"] = 899
    elif fault == "block_removed": del raw["session_web_observation"]
    elif fault == "other_config": raw["port"] += 1
    replacement = b.path.with_name("replacement.json")
    replacement.write_text(json.dumps(raw)); replacement.chmod(0o600)
    replacement.replace(b.path)
    if fault in {"generation", "same_contents_replace", "revoke"}:
        after = b.owner.public_scope(b.principal)
        assert before.revision != after.revision
        assert bool(after.adapter_instance_ids) is (fault != "revoke")
    else:
        with pytest.raises(ValueError):
            b.owner.public_scope(b.principal)


def test_sealed_file_mutation_during_read_fails_closed(tmp_path, monkeypatch):
    from ops.executive_os import executive_mcp_entry as entry
    b = configured_owner(tmp_path, monkeypatch)
    original = entry.validate_document
    def mutate(raw):
        result = original(raw)
        b.path.write_text(b.path.read_text() + " ")
        return result
    monkeypatch.setattr(entry, "validate_document", mutate)
    with pytest.raises(ValueError):
        b.owner.public_scope(b.principal)


def test_unconfigured_private_operation_never_falls_into_summon():
    from integrations.session_bridge.installed import InstalledSessionBridgeProvider
    def forbidden(*args): pytest.fail("read entered a modifying owner")
    provider = InstalledSessionBridgeProvider(target_projector=forbidden,
        reply_handler=forbidden, summon_handler=forbidden)
    frame = {"schema": PRIVATE_SCHEMA, "tool": observation.PRIVATE_TOOL,
             "principal": principal_frame(PRINCIPAL), "arguments": {}}
    result = asyncio.run(provider.handle_frame(frame))
    assert result["ok"] is False
    assert result["error"]["code"] == "backend_unavailable"


def test_private_client_has_one_empty_read_frame_and_no_retry():
    from integrations.session_bridge.installed import InstalledSessionBridgeClient
    from integrations.mastermind_executive_app.gateway import CeoIngressResponse, TRANSPORT_SENT_UNKNOWN
    calls = []
    class Peer:
        async def send_frame(self, path, frame):
            calls.append(frame)
            return CeoIngressResponse(transport=TRANSPORT_SENT_UNKNOWN)
    client = InstalledSessionBridgeClient("/tmp/synthetic.sock", client=Peer())
    with pytest.raises(BridgeError) as exc:
        asyncio.run(client.web_census(PRINCIPAL))
    assert exc.value.code == "backend_unavailable"
    assert len(calls) == 1 and calls[0]["arguments"] == {}
    assert calls[0]["tool"] == observation.PRIVATE_TOOL


def test_principal_expiry_during_permission_load_withholds_state():
    b = bundle()
    def load():
        b.now[0] = datetime.fromtimestamp(auth.NOW + 300, timezone.utc)
        return b.state[0]
    owner = observation.ObservationPermissionReader(load_state=load, clock=lambda: b.now[0])
    with pytest.raises(BridgeError):
        owner.select(b.projected, required=True)


def test_private_revocation_during_post_read_binding_check_is_withheld(monkeypatch):
    b = bundle()
    inspections = []
    def source(_):
        inspections.append(True)
        if len(inspections) == 2:
            b.state[0] = dataclasses.replace(b.state[0], grants=())
        return b.binding, ("same",)
    monkeypatch.setattr(observation, "_current_source", source)
    monkeypatch.setattr("integrations.chairman_surfaces.web_sol_client.census_via_extension",
                        lambda *a, **kw: receipt(adapter=b.adapter))
    with pytest.raises(BridgeError):
        asyncio.run(observation.InstalledProfileCensus(b.owner, current_guard=lambda: True)(
            b.projected, {}))
    assert len(inspections) == 2


def test_ungranted_private_principal_never_reaches_runtime_or_profile(monkeypatch):
    b = bundle()
    b.state[0] = dataclasses.replace(b.state[0], grants=())
    monkeypatch.setattr(observation, "_current_source", lambda *a: pytest.fail("profile reached"))
    def guard(): pytest.fail("ungranted read reached Runtime guard")
    with pytest.raises(BridgeError):
        asyncio.run(observation.InstalledProfileCensus(b.owner, current_guard=guard)(
            b.projected, {}))


def test_profile_home_is_not_rebound_from_another_home_environment(monkeypatch):
    monkeypatch.setattr(observation.Path, "home", lambda: Path("/not-the-process-home"))
    with pytest.raises(BridgeError):
        observation._profile_home(os.getuid())


def test_same_file_same_grants_rewrite_cannot_restore_old_scope_revision(tmp_path, monkeypatch):
    b = configured_owner(tmp_path, monkeypatch)
    old = b.owner.public_scope(b.principal)
    info = b.path.stat()
    contents = b.path.read_text()
    b.path.write_text(contents)
    os.utime(b.path, ns=(info.st_atime_ns, info.st_mtime_ns))
    after = b.owner.public_scope(b.principal)
    assert old.adapter_instance_ids == after.adapter_instance_ids
    assert old.revision != after.revision, "ctime fences an in-place ABA despite restored mtime"


def test_root_seal_acl_failure_never_returns_permissions(tmp_path, monkeypatch):
    from control_plane import fs_security
    b = configured_owner(tmp_path, monkeypatch)
    monkeypatch.setattr(fs_security, "has_macos_acl", lambda *a, **kw: True)
    with pytest.raises(ValueError):
        b.owner.public_scope(b.principal)


@pytest.mark.parametrize("elapsed", [3.0, 8.1])
def test_custody_spends_original_deadline_without_renewing_native_window(monkeypatch, elapsed):
    b = bundle()
    ticks, reads = [100.0], []
    monkeypatch.setattr(observation, "monotonic", lambda: ticks[0])
    def source(_):
        ticks[0] = 100.0 + elapsed
        return b.binding, ("same",)
    monkeypatch.setattr(observation, "_current_source", source)
    def census(binding, **request):
        reads.append(request)
        delta = (datetime.fromisoformat(request["expires_at"].replace("Z", "+00:00"))
                 - datetime.fromisoformat(request["issued_at"].replace("Z", "+00:00"))).total_seconds()
        assert 0 < delta <= 5.0, "preflight must not restart an eight-second window"
        return receipt(adapter=b.adapter)
    monkeypatch.setattr("integrations.chairman_surfaces.web_sol_client.census_via_extension", census)
    collector = observation.InstalledProfileCensus(b.owner, current_guard=lambda: True)
    if elapsed > 8:
        with pytest.raises(BridgeError):
            asyncio.run(collector(b.projected, {}))
        assert reads == []
    else:
        assert asyncio.run(collector(b.projected, {}))["receipt"]
        assert len(reads) == 1


def test_cancelled_preflight_cannot_start_browser_read_after_caller_leaves(monkeypatch):
    from threading import Event
    b = bundle()
    entered, release, finished = Event(), Event(), Event()
    reads = []
    def source(_):
        entered.set()
        assert release.wait(2), "fixture did not release preflight"
        return b.binding, ("same",)
    monkeypatch.setattr(observation, "_current_source", source)
    monkeypatch.setattr("integrations.chairman_surfaces.web_sol_client.census_via_extension",
                        lambda *a, **kw: reads.append(True))
    collector = observation.InstalledProfileCensus(b.owner, current_guard=lambda: True)
    original = collector._read
    def tracked(*args, **kwargs):
        try:
            return original(*args, **kwargs)
        finally:
            finished.set()
    monkeypatch.setattr(collector, "_read", tracked)
    async def run():
        task = asyncio.create_task(collector(b.projected, {}))
        try:
            assert await asyncio.to_thread(entered.wait, 1)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        finally:
            release.set()
        assert await asyncio.to_thread(finished.wait, 1)
        assert reads == [], "cancelled custody must not initiate a fresh browser read"
    asyncio.run(run())

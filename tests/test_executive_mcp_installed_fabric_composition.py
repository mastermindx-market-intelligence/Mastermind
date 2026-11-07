"""Installed C779 explicit profile selector: factory wiring, mismatch, signed path."""
from __future__ import annotations

import asyncio
import dataclasses
import importlib
import json
import os
import socket
import sys
import threading
from contextlib import asynccontextmanager
from pathlib import Path
import httpx
import pytest

sys.path.insert(0, str(Path(__file__).parent))
try:
    import test_mastermind_executive_app_asgi as fixture
    import test_executive_mcp_app_composition as mcp
finally:
    sys.path.pop(0)

from control_plane import executive_runtime as er
from control_plane.executive_service import (
    CEO_APP_READ_SCHEMA,
    CEO_WEB_CEO_V2_READ_SCHEMA,
    _canonical_json,
)
from integrations.executive_mcp import schemas as legacy
from integrations.executive_mcp import server as transport
from integrations.executive_mcp import web_ceo as web
from integrations.executive_mcp.installed import InstalledExecutiveReaders
from tests.test_executive_ceo_ingress import _raw_ceo_request
from tests.test_executive_runtime_bounded_role_result import complete_maximum_chain
from tests.test_runtime_namespace_custody import writer_result

rsa_key = fixture.rsa_key
short_socket_root = fixture.short_socket_root


@pytest.fixture
def settings(rsa_key, tmp_path, short_socket_root):
    mastermind = tmp_path / "mastermind"
    macro = tmp_path / "macro"
    fixture._git_repo(mastermind)
    (macro / "scripts").mkdir(parents=True)
    (macro / "scripts" / "agentos.py").write_text("")
    (macro / "agentos").mkdir()
    (macro / "agentos" / ".keep").write_text("")
    fixture._git_repo(macro)
    return fixture._real_app_settings(
        rsa_key, mastermind_root=mastermind, macro_root=macro,
        ceo_ingress_socket_path=short_socket_root / "ceo-ingress.sock",
    )

INVALID_PROFILES = (
    None, False, True, 0, 1, 3.14, [], {}, "", " ", "\t", "legacy ", " legacy",
    "Legacy", "LEGACY", "web_ceo_v1", "web_ceo_v2 ", "WEB_CEO_V2",
    "mastermind.executive_ceo_ingress_app_read.v1",
    "mastermind.executive_ceo_ingress_app_read.v3",
    "unknown",
)


class _NoExecutionSupervisor:
    def reconcile_restart(self, *, requeue_lost: bool = False):
        return []


def test_validate_installed_mcp_profile_is_pure_closed_enum():
    assert web.validate_installed_mcp_profile() == "legacy"
    assert web.validate_installed_mcp_profile("legacy") == "legacy"
    assert web.validate_installed_mcp_profile("web_ceo_v2") == web.WEB_CEO_V2_PROFILE
    for value in INVALID_PROFILES:
        with pytest.raises(ValueError, match="installed Executive MCP profile is invalid"):
            web.validate_installed_mcp_profile(value)
    assert web.web_ceo_v2_schema_snapshot_sha256() == web.WEB_CEO_V2_SCHEMA_SNAPSHOT_SHA256
    assert legacy.schema_snapshot_sha256() == (
        "546b4345e30c24363a02ae3d4fc873e17559ffd569cde188a533fb628b284232"
    )


def _listening(path: Path) -> socket.socket:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.unlink()
    except FileNotFoundError:
        pass
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.bind(os.fspath(path))
    sock.listen(16)
    os.chmod(path, 0o600)
    return sock


def _raw_for_factory(tmp_path: Path, socket_root: Path, *, profile=None) -> dict[str, object]:
    euid = os.geteuid()
    mastermind = tmp_path / "proof-source"
    macro = tmp_path / "control-macro"
    sha = fixture._git_repo(mastermind, content="control-source")
    fixture._git_repo(macro, content="macro-source")
    (macro / "scripts").mkdir(exist_ok=True)
    (macro / "scripts" / "agentos.py").write_text("")
    (macro / "agentos").mkdir(exist_ok=True)
    (macro / "agentos" / ".keep").write_text("")
    raw: dict[str, object] = {
        "schema_version": "mastermind.executive_control_config/v1",
        "runtime_root": tmp_path / "runtime",
        "control_socket_path": socket_root / "operator.sock",
        "launchd_socket_name": "Operator",
        "ceo_ingress_socket_path": socket_root / "ceo-ingress.sock",
        "ceo_ingress_launchd_socket_name": "CeoIngress",
        "ceo_ingress_peer_uid": euid + 1000,
        "ceo_ingress_app_peer_uid": euid,
        "ceo_ingress_app_armed": True,
        "ceo_ingress_app_macro_root": macro,
        "worker_broker_socket_path": tmp_path / "worker-broker.sock",
        "worker_provider_home": tmp_path / "worker-home",
        "worker_runs_root": tmp_path / "worker-runs",
        "receipts_root": tmp_path / "receipts",
        "proof_source_repository": mastermind,
        "proof_workspace_root": tmp_path / "workspaces",
        "proof_base_sha": sha,
        "backup_root": tmp_path / "backups",
        "control_uid": euid + 20,
        "worker_uid": euid + 1,
        "worker_gid": euid + 1,
        "worker_user": "_mastermind_worker_fixture",
        "shared_run_gid": euid + 2,
        "allowed_peer_uids": (euid + 20,),
        "secret_canary_receipt_path": tmp_path / "canary.json",
        "control_environment_attestation_path": tmp_path / "attestation.json",
        "shutdown_grace_seconds": 2.0,
    }
    if profile is not None:
        raw["executive_mcp_profile"] = profile
    return raw


def _patch_composition(monkeypatch, sockets: dict[str, socket.socket]):
    module = importlib.import_module("scripts.executive_os_phase1c")
    broker = importlib.import_module("control_plane.executive_worker_broker")
    monkeypatch.setattr(broker, "WorkerBrokerClient", lambda *a, **k: object())
    monkeypatch.setattr(
        broker, "RemoteCodexWorkerAdapter", lambda *a, **k: object()
    )
    monkeypatch.setattr(
        "control_plane.executive_supervisor.ExecutiveSupervisor",
        lambda *a, **k: _NoExecutionSupervisor(),
    )
    monkeypatch.setattr(
        module, "activate_launchd_socket", lambda name: sockets[name]
    )
    return module


@asynccontextmanager
async def factory_service(tmp_path, socket_root, monkeypatch, *, profile=None, chain=False):
    raw = _raw_for_factory(tmp_path, socket_root, profile=profile)
    runtime_root = Path(raw["runtime_root"])
    chain_result = None
    if chain:
        chain_result = complete_maximum_chain(runtime_root)
    sockets = {
        "Operator": _listening(Path(raw["control_socket_path"])),
        "CeoIngress": _listening(Path(raw["ceo_ingress_socket_path"])),
    }
    module = _patch_composition(monkeypatch, sockets)
    service = None
    try:
        service = module._service_from_config(raw)
        yield service, raw, chain_result
    finally:
        if service is not None:
            await service.close()
        for sock in sockets.values():
            try:
                sock.close()
            except OSError:
                pass


def _selected_builder(profile: str | None):
    value = web.validate_installed_mcp_profile(
        "legacy" if profile is None else profile
    )
    if value == web.WEB_CEO_V2_PROFILE:
        return transport.build_web_ceo_v2_mcp_app
    return transport.build_executive_mcp_app


def headers(token: str) -> dict[str, str]:
    return mcp.headers(token)


async def rpc(client, token, method, params=None):
    request = {"jsonrpc": "2.0", "id": 1, "method": method}
    if params is not None:
        request["params"] = params
    response = await client.post("/mcp", headers=headers(token), json=request)
    assert response.status_code == 200, response.text
    body = response.json()
    assert "error" not in body, response.text
    return body["result"]


async def call(client, token, name, arguments):
    result = await rpc(client, token, "tools/call", {"name": name, "arguments": arguments})
    return result, json.loads(result["content"][0]["text"])


def test_parser_and_both_documents_share_get_default(tmp_path):
    from ops.executive_os import executive_mcp_entry as entry
    from tests.test_c1_ceo_ingress_composition import _module, _write_config, _app_raw

    assert web.validate_installed_mcp_profile.__defaults__ == ("legacy",)
    module = _module()
    raw_control = _app_raw(tmp_path)
    raw_control.pop("ceo_ingress_app_boot_python", None)
    loaded = module.load_control_config(_write_config(tmp_path, raw_control))
    assert "executive_mcp_profile" not in loaded
    raw = {
        "schema": entry.CONFIG_SCHEMA,
        "release_sha": "1" * 40,
        "service_uid": 458,
        "port": 8443,
        "ceo_ingress_socket_path": "/var/run/mastermind-executive/ceo-ingress.sock",
        "audit_root": "/var/log/mastermind-executive/mcp-auth",
        "policies": {},
    }
    assert entry.validate_document(raw) == raw
    present = dict(raw, executive_mcp_profile="web_ceo_v2")
    assert entry.validate_document(present)["executive_mcp_profile"] == "web_ceo_v2"


@pytest.mark.parametrize("profile", [None, "legacy"])
def test_factory_legacy_has_no_fabric_bind(tmp_path, short_socket_root, monkeypatch, profile):
    async def run():
        async with factory_service(
            tmp_path, short_socket_root, monkeypatch, profile=profile
        ) as (service, raw, _):
            binding = service._ceo_ingress_app_binding
            assert type(binding.read_provider) is InstalledExecutiveReaders
            assert binding.read_schema == CEO_APP_READ_SCHEMA
            assert binding.read_provider._fabric_source_binding is None
            assert service._ceo_ingress_armed is False
            assert service.config.ceo_submit_armed is False
    asyncio.run(run())


def test_factory_v2_bind_is_inert_until_started(tmp_path, short_socket_root, monkeypatch):
    async def run():
        async with factory_service(
            tmp_path, short_socket_root, monkeypatch, profile="web_ceo_v2"
        ) as (service, raw, _):
            binding = service._ceo_ingress_app_binding
            readers = binding.read_provider
            assert type(readers) is web.WebCeoV2InstalledExecutiveReaders
            assert binding.read_schema == CEO_WEB_CEO_V2_READ_SCHEMA
            getter, armed, identity = readers._fabric_source_binding
            assert identity == {"root": None, "db_present": True, "identity": None}
            assert armed["source"] == "control.json"
            with pytest.raises(Exception):
                getter()
            await service.start()
            facade = getter()
            assert facade.store.root == service._require_runtime().store.root
            await service.close()
            with pytest.raises(Exception):
                getter()
    asyncio.run(run())


@pytest.mark.parametrize(
    "control_profile,network_profile,control_schema,network_schema",
    [
        ("web_ceo_v2", "legacy", CEO_WEB_CEO_V2_READ_SCHEMA, CEO_APP_READ_SCHEMA),
        ("legacy", "web_ceo_v2", CEO_APP_READ_SCHEMA, CEO_WEB_CEO_V2_READ_SCHEMA),
    ],
)
def test_network_control_mismatch_shared_read_is_opaque(
    tmp_path, short_socket_root, monkeypatch, settings, rsa_key,
    control_profile, network_profile, control_schema, network_schema,
):
    async def run():
        async with factory_service(
            tmp_path, short_socket_root, monkeypatch, profile=control_profile
        ) as (service, raw, _):
            provider = service._ceo_ingress_app_binding.read_provider
            calls: list[tuple[str, object]] = []
            original = provider.call

            async def tracked(name, arguments):
                calls.append((name, arguments))
                return await original(name, arguments)

            provider.call = tracked
            getter_calls: list[int] = []
            binding = getattr(provider, "_fabric_source_binding", None)
            if binding is not None:
                real_getter, armed, identity = binding

                def counted():
                    getter_calls.append(1)
                    return real_getter()

                provider._fabric_source_binding = (counted, armed, identity)
            await service.start()
            unix = await _raw_ceo_request(
                Path(raw["ceo_ingress_socket_path"]),
                (json.dumps({
                    "schema": network_schema,
                    "tool": "executive_job",
                    "arguments": {"job_id": "JOB-001"},
                }) + "\n").encode(),
            )
            assert unix["ok"] is False, unix
            assert unix["error"]["code"] == "peer_denied"
            assert calls == []
            assert getter_calls == []
            bound = dataclasses.replace(
                settings,
                read_from_ceo_ingress=True,
                mastermind_root=tmp_path / "no-network-checkout",
                macro_root_flag=None,
                ceo_ingress_socket_path=str(raw["ceo_ingress_socket_path"]),
            )
            app = _selected_builder(network_profile)(bound, audit_sink=mcp.Sink())
            async with app._app.router.lifespan_context(app._app):
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1"
                ) as client:
                    result, body = await call(
                        client, fixture._read_token(rsa_key),
                        "executive_job", {"job_id": "JOB-001"},
                    )
            assert body["ok"] is False, body
            assert body["error"]["code"] == "backend_unavailable"
            assert calls == []
            assert getter_calls == []
            assert "data" not in body or body.get("data") is None
    asyncio.run(run())


def test_signed_v2_factory_path_reads_retained_result(
    tmp_path, short_socket_root, monkeypatch, settings, rsa_key,
):
    async def run():
        async with factory_service(
            tmp_path, short_socket_root, monkeypatch, profile="web_ceo_v2", chain=True
        ) as (service, raw, chain):
            runtime, root, nodes = chain
            job, attempt, _ = nodes[-1]
            expected = runtime.validated_role_completion(
                job, expected_attempt_id=attempt
            )
            readers = service._ceo_ingress_app_binding.read_provider
            getter, armed, identity = readers._fabric_source_binding
            getter_calls: list[int] = []

            def counted():
                getter_calls.append(1)
                return getter()

            readers._fabric_source_binding = (counted, armed, identity)
            await service.start()
            bound = dataclasses.replace(
                settings,
                read_from_ceo_ingress=True,
                mastermind_root=tmp_path / "no-network-checkout",
                macro_root_flag=None,
                ceo_ingress_socket_path=str(raw["ceo_ingress_socket_path"]),
            )
            app = _selected_builder("web_ceo_v2")(bound, audit_sink=mcp.Sink())
            async with app._app.router.lifespan_context(app._app):
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1"
                ) as client:
                    listed = await rpc(client, fixture._read_token(rsa_key), "tools/list")
                    names = {tool["name"] for tool in listed["tools"]}
                    assert names == {
                        "executive_state", "executive_inbox", "executive_job",
                        "executive_fabric", "ceo_intent_status", "submit_ceo_intent",
                    }
                    _, job_body = await call(
                        client, fixture._read_token(rsa_key),
                        "executive_job", {"job_id": root.job_id},
                    )
                    assert job_body["ok"] is True, job_body
                    args = dict(
                        view="result",
                        root_job_id=root.job_id,
                        job_id=job,
                        attempt_id=attempt,
                        result_envelope_digest=expected.result_digest,
                    )
                    result, body = await call(
                        client, fixture._read_token(rsa_key), "executive_fabric", args
                    )
                    assert body["ok"] is True, body
                    assert body["server_version"] == "1.2.0"
                    assert body["data"]["generation"]["state"] == "SAME"
                    assert body["data"]["content"]["role_result"] == (
                        expected.result_envelope["role_result"]
                    )
                    wrapper = _canonical_json({"ok": True, "result": body})
                    assert len(wrapper) <= 16384
                    assert getter_calls
                    assert str(raw["runtime_root"]) not in json.dumps(body)
                    submit, submit_body = await call(
                        client, fixture._read_token(rsa_key),
                        "submit_ceo_intent", mcp.PAYLOAD,
                    )
                    assert submit["isError"] is True
                    assert submit_body["error"]["code"] == "scope_refused"
    asyncio.run(run())


def test_signed_legacy_factory_path_keeps_five_tools(
    tmp_path, short_socket_root, monkeypatch, settings, rsa_key,
):
    async def run():
        async with factory_service(
            tmp_path, short_socket_root, monkeypatch, profile="legacy", chain=True
        ) as (service, raw, chain):
            runtime, root, nodes = chain
            await service.start()
            bound = dataclasses.replace(
                settings,
                read_from_ceo_ingress=True,
                mastermind_root=tmp_path / "no-network-checkout",
                macro_root_flag=None,
                ceo_ingress_socket_path=str(raw["ceo_ingress_socket_path"]),
            )
            app = _selected_builder("legacy")(bound, audit_sink=mcp.Sink())
            async with app._app.router.lifespan_context(app._app):
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1"
                ) as client:
                    listed = await rpc(client, fixture._read_token(rsa_key), "tools/list")
                    assert {tool["name"] for tool in listed["tools"]} == {
                        "executive_state", "executive_inbox", "executive_job",
                        "ceo_intent_status", "submit_ceo_intent",
                    }
                    _, body = await call(
                        client, fixture._read_token(rsa_key),
                        "executive_job", {"job_id": root.job_id},
                    )
                    assert body["ok"] is True, body
                    assert body["server_version"] == "1.0.0"
    asyncio.run(run())


@pytest.mark.parametrize("case", ["invalid", "wrong_audience", "expiry_after_read", "changed_principal"])
def test_v2_factory_auth_refuses_before_or_after_acquisition(
    tmp_path, short_socket_root, monkeypatch, settings, rsa_key, case,
):
    async def run():
        async with factory_service(
            tmp_path, short_socket_root, monkeypatch, profile="web_ceo_v2", chain=True
        ) as (service, raw, chain):
            runtime, root, nodes = chain
            job, attempt, _ = nodes[-1]
            expected = runtime.validated_role_completion(
                job, expected_attempt_id=attempt
            )
            readers = service._ceo_ingress_app_binding.read_provider
            getter, armed, identity = readers._fabric_source_binding
            getter_calls: list[int] = []

            def counted():
                getter_calls.append(1)
                return getter()

            readers._fabric_source_binding = (counted, armed, identity)
            now = [fixture.NOW]
            original_call = readers.call

            async def observed(name, arguments):
                response = await original_call(name, arguments)
                if case == "expiry_after_read":
                    now[0] += 10000
                return response

            readers.call = observed
            bound = dataclasses.replace(
                settings,
                read_from_ceo_ingress=True,
                mastermind_root=tmp_path / "no-network-checkout",
                macro_root_flag=None,
                ceo_ingress_socket_path=str(raw["ceo_ingress_socket_path"]),
                clock=lambda: now[0],
            )
            if case == "changed_principal":
                from integrations.mastermind_executive_app import app as appmod
                original_verify = appmod.JwtAuthenticator.verify_authorization_header
                seen: list[int] = []

                async def changed(auth, *args, **kwargs):
                    principal = await original_verify(auth, *args, **kwargs)
                    seen.append(1)
                    if len(seen) == 2:
                        return dataclasses.replace(principal, subject_digest="f" * 64)
                    return principal

                monkeypatch.setattr(
                    appmod.JwtAuthenticator, "verify_authorization_header", changed
                )
            await service.start()
            app = _selected_builder("web_ceo_v2")(bound, audit_sink=mcp.Sink())
            async with app._app.router.lifespan_context(app._app):
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1"
                ) as client:
                    token = fixture._read_token(rsa_key)
                    if case == "invalid":
                        token = "invalid"
                    elif case == "wrong_audience":
                        token = fixture._read_token(rsa_key, aud="https://other.example")
                    args = dict(
                        view="result",
                        root_job_id=root.job_id,
                        job_id=job,
                        attempt_id=attempt,
                        result_envelope_digest=expected.result_digest,
                    )
                    response = await client.post(
                        "/mcp",
                        headers=headers(token),
                        json={
                            "jsonrpc": "2.0",
                            "id": 1,
                            "method": "tools/call",
                            "params": {"name": "executive_fabric", "arguments": args},
                        },
                    )
                    assert response.status_code in (200, 401), response.text
                    if case in ("invalid", "wrong_audience"):
                        assert getter_calls == []
                    else:
                        assert getter_calls
                        payload = response.json()
                        if "result" in payload:
                            body = json.loads(payload["result"]["content"][0]["text"])
                            assert body.get("ok") is not True
                        assert "counts" not in response.text
    asyncio.run(run())


def test_v2_factory_cancellation_drains_before_namespace_close(
    tmp_path, short_socket_root, monkeypatch,
):
    from integrations.executive_mcp import adapter

    async def run():
        async with factory_service(
            tmp_path, short_socket_root, monkeypatch, profile="web_ceo_v2", chain=True
        ) as (service, raw, chain):
            runtime, root, nodes = chain
            job, attempt, _ = nodes[-1]
            expected = runtime.validated_role_completion(
                job, expected_attempt_id=attempt
            )
            readers = service._ceo_ingress_app_binding.read_provider
            await service.start()
            args = dict(
                view="result",
                root_job_id=root.job_id,
                job_id=job,
                attempt_id=attempt,
                result_envelope_digest=expected.result_digest,
            )
            entered = threading.Event()
            release = threading.Event()
            original = er.BoundedRuntimeReadObservation.read_role_result_bounded

            def blocked(observation, *a, **kw):
                value = original(observation, *a, **kw)
                entered.set()
                assert release.wait(10)
                return value

            monkeypatch.setattr(
                er.BoundedRuntimeReadObservation, "read_role_result_bounded", blocked
            )
            monkeypatch.setattr(adapter, "_CLOSE_TIMEOUT_SECONDS", 0.03)
            task = asyncio.create_task(readers.call("executive_fabric", args))
            try:
                for _ in range(1000):
                    if entered.is_set():
                        break
                    await asyncio.sleep(0.001)
                assert entered.is_set()
                task.cancel()
                await asyncio.sleep(0)
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
                assert writer_result(service._require_runtime()) == "BLOCKED"
                with pytest.raises(legacy.GatewayError) as failure:
                    await readers.aclose()
                assert failure.value.code == "timeout"
                assert writer_result(service._require_runtime()) == "BLOCKED"
            finally:
                release.set()
                for _ in range(1000):
                    if not readers._read_attempts:
                        break
                    await asyncio.sleep(0.001)
                try:
                    await readers.aclose()
                except Exception:
                    pass
            assert writer_result(service._require_runtime()) == "RESERVED"
    asyncio.run(run())


def test_v2_factory_wrapper_budget_and_mcp_cap(
    tmp_path, short_socket_root, monkeypatch, settings, rsa_key,
):
    from control_plane import fabric_result_projection as projection

    async def run():
        async with factory_service(
            tmp_path, short_socket_root, monkeypatch, profile="web_ceo_v2", chain=True
        ) as (service, raw, chain):
            runtime, root, nodes = chain
            job, attempt, _ = nodes[-1]
            expected = runtime.validated_role_completion(
                job, expected_attempt_id=attempt
            )
            readers = service._ceo_ingress_app_binding.read_provider
            await service.start()
            args = dict(
                view="result",
                root_job_id=root.job_id,
                job_id=job,
                attempt_id=attempt,
                result_envelope_digest=expected.result_digest,
            )
            document, ground, degraded = readers._executive_fabric(args)

            def envelope(doc):
                value = legacy.result_envelope(
                    "executive_fabric",
                    mode=readers.config.mode,
                    generated_at="2026-09-21T17:00:00Z",
                    data=doc,
                    grounding=ground,
                    degraded=degraded,
                )
                value["server_version"] = "1.2.0"
                return value

            base = json.loads(json.dumps(document.complete))
            pad = 16384 - len(_canonical_json({"ok": True, "result": envelope(base)}))
            assert pad > 0
            base["content"]["summary"] = (base["content"].get("summary") or "") + ("a" * pad)
            monkeypatch.setattr(
                readers,
                "_executive_fabric",
                lambda a: (
                    projection.FabricRoleResultProjection(
                        base, document.content_over_budget
                    ),
                    ground,
                    degraded,
                ),
            )
            exact = readers._read_fabric_result(
                "executive_fabric", args, "2026-09-21T17:00:00Z"
            )
            assert len(_canonical_json({"ok": True, "result": exact})) == 16384
            bound = dataclasses.replace(
                settings,
                read_from_ceo_ingress=True,
                mastermind_root=tmp_path / "no-network-checkout",
                macro_root_flag=None,
                ceo_ingress_socket_path=str(raw["ceo_ingress_socket_path"]),
            )
            from starlette.applications import Starlette
            from starlette.responses import JSONResponse
            from starlette.routing import Route
            from integrations.mastermind_executive_app import app as appmod

            text = '\\"\n漢' * 16000
            overflow = legacy.result_envelope(
                "executive_fabric",
                mode=legacy.ServerMode.READONLY,
                generated_at="2026-09-21T17:00:00Z",
                data={"payload": text},
            )
            overflow["server_version"] = "1.2.0"

            async def fixed(_request):
                return JSONResponse(overflow)

            monkeypatch.setattr(
                appmod,
                "create_web_ceo_v2_app",
                lambda _: Starlette(
                    routes=[Route("/v1/tools/executive_fabric", fixed, methods=["POST"])]
                ),
            )
            app = transport.build_web_ceo_v2_mcp_app(bound, audit_sink=mcp.Sink())
            async with app._app.router.lifespan_context(app._app):
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1"
                ) as client:
                    response = await client.post(
                        "/mcp",
                        headers=headers(fixture._read_token(rsa_key)),
                        json={
                            "jsonrpc": "2.0",
                            "id": "r" * 60000,
                            "method": "tools/call",
                            "params": {
                                "name": "executive_fabric",
                                "arguments": {"view": "roots"},
                            },
                        },
                    )
                    assert response.status_code == 200, response.text
                    assert len(response.content) <= legacy.MAX_RESPONSE_BYTES
                    out = json.loads(response.json()["result"]["content"][0]["text"])
                    assert out["ok"] is False
                    assert out["error"]["code"] == "output_too_large"
    asyncio.run(run())

"""Finite private native history: real Runtime and owned socket-pair contracts.

The optional DSH_SOURCE case also runs the actual donor Gateway/JSONL services
in a separate Node process. Its fixture principal is not installed OAuth proof.
"""
from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import time
from types import SimpleNamespace

import pytest

from control_plane.executive_runtime import Runtime
from control_plane.executive_ceo_ingress import MAX_RESPONSE_BYTES
from integrations.business_mcp_auth.contracts import VerifiedPrincipal
from integrations.business_mcp_auth.principal_projection import principal_projection
from integrations.deepseek_harness.native_read_port import (
    NativeReadUnavailable, OwnedNativeReadPort, RESPONSE_SCHEMA, canonical,
)
from integrations.session_bridge.deepseek_native import (
    DeepSeekNativeAssociation, DeepSeekNativeReadSource, DeepSeekNativeSession,
    principal_namespace, validate_native_read_arguments,
)
from integrations.session_bridge.installed import (
    PRIVATE_SCHEMA, build_runtime_session_bridge, principal_frame,
)
from integrations.session_bridge.schemas import BridgeError

WORK = "WS:Company-native-read"
REPO = Path(__file__).resolve().parents[1]


def composition(tmp_path):
    runtime = Runtime.at(tmp_path / "runtime")
    job = runtime.jobs.create_job("Read original native history",
                                  provenance={"workstream": WORK})
    now = int(time.time())
    issuer = "https://native-read-fixture.test/"
    principal = VerifiedPrincipal(
        policy_id="native-read-fixture", issuer=issuer,
        issuer_digest=hashlib.sha256(issuer.encode()).hexdigest(),
        resource="https://executive-fixture.test/mcp",
        subject_digest="1"*64, client_ref="2"*64,
        scopes=("mastermind.executive.read",), issued_at=now-1,
        expires_at=now+600, jti_digest=None)
    association = DeepSeekNativeAssociation(
        work_ref=WORK, root_job_id=job.job_id, native_session_id="company-bound-original",
        owner_principal_scope=principal_namespace(principal_projection(principal)),
        composition_sha256="3"*64, native_package_sha256="4"*64)
    left, right = socket.socketpair()
    port = OwnedNativeReadPort(left, association_sha256=association.digest)
    live = {"source": True, "app": True}
    def guard(name):
        if not live[name]:
            raise BridgeError("binding_unavailable", "fixture original owner retired")
    source = DeepSeekNativeReadSource(association, port, require_current=lambda: guard("source"))
    native = DeepSeekNativeSession(source, read_guard=lambda: guard("app"))
    owner = build_runtime_session_bridge(
        runtime, dialogue_socket_path=tmp_path / "unused-dialogue.sock", deepseek_session=native)
    args = {"selection": {"work_ref": WORK, "root_job_id": job.job_id}, "read": {"kind": "snapshot"}}
    def frame(*, who=principal, arguments=None):
        return {"schema": PRIVATE_SCHEMA, "tool": "session_native_read",
                "principal": principal_frame(who), "arguments": args if arguments is None else arguments}
    return SimpleNamespace(runtime=runtime, job=job, principal=principal, association=association,
                           port=port, peer=right, source=source, native=native, owner=owner,
                           args=args, frame=frame, live=live)


@pytest.fixture
def h(tmp_path):
    value = composition(tmp_path)
    try:
        yield value
    finally:
        value.port.retire()
        value.peer.close()


async def receive(peer):
    peer.setblocking(False)
    loop = asyncio.get_running_loop()
    raw = b""
    async with asyncio.timeout(5):
        while b"\n" not in raw:
            item = await loop.sock_recv(peer, 4096)
            if not item:
                raise EOFError("test peer closed")
            raw += item
    assert raw.endswith(b"\n")
    return json.loads(raw), raw


async def respond(peer, *, data=None, transform=None, on_frame=None):
    frame, _ = await receive(peer)
    if on_frame:
        on_frame()
    value = {"schema": RESPONSE_SCHEMA, "request_id": frame["request_id"],
             "association_sha256": frame["association_sha256"], "status": "READ",
             "data": data if data is not None else {"projections": {"kind": "sequenced", "asOfSeq": 5},
                                                    "page": {"records": [], "fixture": True}}}
    raw = canonical(value)+b"\n"
    if transform:
        raw = transform(value, raw)
    await asyncio.get_running_loop().sock_sendall(peer, raw)
    return frame, raw


async def roundtrip(h, **kwargs):
    peer = asyncio.create_task(respond(h.peer, **kwargs))
    result = await h.owner.handle_frame(h.frame())
    sent = await peer
    return result, sent


def assert_no_frame(h):
    h.peer.setblocking(False)
    with pytest.raises(BlockingIOError):
        h.peer.recv(1)


def test_actual_private_owner_reads_exact_runtime_root_with_optional_jti(h):
    before = [event.to_dict() for event in h.runtime.events.list_events(job_id=h.job.job_id)]
    result, (wire, _) = asyncio.run(roundtrip(h))
    assert result["ok"] is True
    data = result["data"]
    assert data["selection"] == h.args["selection"]
    assert data["native_session_id"] == h.association.native_session_id
    assert data["association_sha256"] == h.association.digest
    assert data["root_event_id"] == h.runtime.store.unique_root_created_event(h.job.job_id).event_id
    assert data["observational_only"] is True
    assert data["can_send"] is False and data["parent_consumed"] is False
    assert wire["principal"]["principal_scope"] == h.association.owner_principal_scope
    assert wire["read"] == {"kind": "snapshot"}
    assert not any(field in wire for field in ("session_id", "fd", "socket", "token", "authGeneration"))
    assert [event.to_dict() for event in h.runtime.events.list_events(job_id=h.job.job_id)] == before


@pytest.mark.parametrize("fault", ["principal", "expired", "future", "scope", "work", "root", "app", "source"])
def test_authority_or_selection_refusal_enters_no_native_port(h, fault):
    principal, args = h.principal, json.loads(json.dumps(h.args))
    if fault == "principal":
        principal = dataclasses.replace(principal, client_ref="9"*64)
    elif fault == "expired":
        principal = dataclasses.replace(principal, issued_at=1, expires_at=2)
    elif fault == "future":
        principal = dataclasses.replace(principal, issued_at=principal.expires_at+1,
                                        expires_at=principal.expires_at+100)
    elif fault == "scope":
        principal = dataclasses.replace(principal, scopes=())
    elif fault == "work":
        args["selection"]["work_ref"] = "WS:Foreign"
    elif fault == "root":
        args["selection"]["root_job_id"] = "JOB-999"
    else:
        h.live[fault] = False
    result = asyncio.run(h.owner.handle_frame(h.frame(who=principal, arguments=args)))
    assert result["ok"] is False and result["data"] is None
    assert_no_frame(h)


@pytest.mark.parametrize("fault", ["native_selector", "identity", "callback", "fractional", "bool", "large_cursor", "before_start"])
def test_closed_selection_and_cursor_cannot_supply_native_authority(h, fault):
    args = json.loads(json.dumps(h.args))
    if fault in {"native_selector", "identity", "callback"}:
        args[{"native_selector": "native_session_id", "identity": "principal_scope",
              "callback": "require_current"}[fault]] = "caller-controlled"
    else:
        args["read"] = {"kind": "page", "through_seq": 5, "before_seq": None, "max_messages": 8}
        args["read"]["through_seq"] = {"fractional": 1.5, "bool": True, "large_cursor": 2**53, "before_start": -2}[fault]
    with pytest.raises(BridgeError, match="native history"):
        validate_native_read_arguments(args)
    assert_no_frame(h)


@pytest.mark.parametrize("fault", ["app", "source", "root"])
def test_late_native_data_is_withheld_if_original_authority_or_root_changes(h, fault, monkeypatch):
    original = h.runtime.store.unique_root_created_event(h.job.job_id)
    def change():
        if fault == "root":
            # Fault-inject a changed observation, not a writable canonical Event:
            # the actual Runtime correctly refuses mutation of immutable events.
            monkeypatch.setattr(h.runtime.store, "unique_root_created_event",
                lambda *_args, **_kwargs: dataclasses.replace(original, event_id=original.event_id+1))
        else:
            h.live[fault] = False
    result, _ = asyncio.run(roundtrip(h, on_frame=change))
    assert result["ok"] is False and result["data"] is None


def test_private_outer_wrapper_budget_refuses_a_complete_utf8_page(h):
    async def run():
        empty, _ = await roundtrip(h, data={"projections": None, "page": {"text": ""}})
        assert empty["ok"] is True
        overhead = len(canonical({"ok": True, "result": empty}))+1
        native = {"projections": None, "page": {"text": "界"*((MAX_RESPONSE_BYTES-overhead)//3+1)}}
        result, (_, raw) = await roundtrip(h, data=native)
        assert len(raw) <= MAX_RESPONSE_BYTES  # Native frame fits; final wrapper does not.
        assert result["ok"] is False and result["data"] is None
        assert result["error"]["code"] == "response_too_large"
    asyncio.run(run())


@pytest.mark.parametrize("fault", ["duplicate", "wrong_id", "extra_frame", "invalid_utf8", "oversized"])
def test_native_protocol_corruption_retires_original_endpoint_without_replay(h, fault):
    def corrupt(value, raw):
        if fault == "duplicate":
            return raw.replace(b'"status":', b'"status":"READ","status":', 1)
        if fault == "wrong_id":
            value["request_id"] = "0"*64
            return canonical(value)+b"\n"
        if fault == "extra_frame":
            return raw+b"{}\n"
        if fault == "invalid_utf8":
            return b"\xff\n"
        return b" "*MAX_RESPONSE_BYTES+b"\n"
    result, _ = asyncio.run(roundtrip(h, transform=corrupt))
    assert result["ok"] is False and result["data"] is None
    with pytest.raises(NativeReadUnavailable):
        h.port.require_current()


def test_cancellation_retires_original_port_and_never_sends_a_second_frame(h):
    async def run():
        pending = asyncio.create_task(h.owner.handle_frame(h.frame()))
        await receive(h.peer)
        pending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pending
        with pytest.raises(NativeReadUnavailable):
            h.port.require_current()
        assert await asyncio.get_running_loop().sock_recv(h.peer, 4096) == b""
    asyncio.run(run())


def test_concurrent_read_is_refused_without_cancelling_original_initiator(h):
    async def run():
        first = asyncio.create_task(h.owner.handle_frame(h.frame()))
        frame, _ = await receive(h.peer)
        second = await h.owner.handle_frame(h.frame())
        assert second["ok"] is False
        value = {"schema": RESPONSE_SCHEMA, "request_id": frame["request_id"],
                 "association_sha256": frame["association_sha256"], "status": "READ",
                 "data": {"projections": None, "page": None}}
        await asyncio.get_running_loop().sock_sendall(h.peer, canonical(value)+b"\n")
        assert (await first)["ok"] is True
        h.port.require_current()
    asyncio.run(run())


def test_builder_default_keeps_native_read_unavailable(h, tmp_path):
    owner = build_runtime_session_bridge(h.runtime, dialogue_socket_path=tmp_path / "unused.sock")
    result = asyncio.run(owner.handle_frame(h.frame()))
    assert result["ok"] is False and result["error"]["code"] == "backend_unavailable"
    assert_no_frame(h)


def test_no_descriptor_or_json_association_can_create_the_nominal_capability(h):
    with pytest.raises(TypeError):
        OwnedNativeReadPort(h.peer.fileno(), association_sha256=h.association.digest)
    with pytest.raises(TypeError):
        DeepSeekNativeReadSource(h.association.document(), h.port, require_current=lambda: None)


def test_async_before_write_guard_is_refused_without_running_or_leaking_it(h):
    ran = []
    async def invalid():
        ran.append(True)
    async def run():
        with pytest.raises(NativeReadUnavailable):
            await h.port.read(principal_scope=h.association.owner_principal_scope,
                              issued_at=h.principal.issued_at, expires_at=h.principal.expires_at,
                              request={"kind": "snapshot"}, before_write=invalid)
    asyncio.run(run())
    assert ran == []
    with pytest.raises(NativeReadUnavailable):
        h.port.require_current()


@pytest.mark.skipif(not os.environ.get("DSH_SOURCE"), reason="exact clean native donor is required")
def test_real_runtime_private_bridge_to_native_process_preserves_original_history(h, tmp_path):
    donor = Path(os.environ["DSH_SOURCE"]).resolve(strict=True)
    node = os.environ.get("DSH_NODE") or shutil.which("node")
    assert node, "Native Node runtime is required"
    plugin = REPO / "integrations/deepseek_harness/company_plugin"
    ready, report = tmp_path / "native-ready.json", tmp_path / "native-report.json"
    spec = tmp_path / "native-fixture.json"
    spec.write_text(json.dumps({"fd": h.peer.fileno(), "association": h.association.document(),
                               "ready": str(ready), "report": str(report)}))
    log = tmp_path / "native-process.log"
    environment = dict(os.environ, DSH_SOURCE=str(donor), MMX_DSH_NATIVE_READ_FIXTURE=str(spec))
    with log.open("wb") as output:
        process = subprocess.Popen([
            node, str(donor / "node_modules/vitest/vitest.mjs"), "run", "--pool", "threads",
            "--config", "vitest.host.config.mts", "native.executive.fixture.test.ts",
        ], cwd=plugin, env=environment, pass_fds=(h.peer.fileno(),), stdout=output, stderr=subprocess.STDOUT)
    h.peer.close()  # Only the original child retains the other socket-pair endpoint.
    try:
        deadline = time.monotonic()+40
        while not ready.exists() and process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.03)
        assert ready.exists(), log.read_text(errors="replace")[-6000:]
        before = [event.to_dict() for event in h.runtime.events.list_events(job_id=h.job.job_id)]
        async def journey():
            first = await h.owner.handle_frame(h.frame())
            assert first["ok"] is True, first
            result = first["data"]
            page = result["native"]["page"]
            assert [row["event"]["seq"] for row in page["records"]] == [0,1,2,3,4,5]
            rendered = json.dumps(page, ensure_ascii=False)
            assert "原始问题" in rendered and "Native answer retained" in rendered
            assert '"texts": ["Native answer", " retained", " — 原样保留"]' in rendered
            repeat = await h.owner.handle_frame(h.frame())
            assert repeat == first
            args = {"selection": h.args["selection"], "read": {
                "kind": "page", "through_seq": result["native"]["projections"]["asOfSeq"],
                "before_seq": None, "max_messages": 8}}
            paged = await h.owner.handle_frame(h.frame(arguments=args))
            assert paged["ok"] is True and paged["data"]["native"]["page"] == page
            args["read"].update(through_seq=-1, before_seq=0)
            empty = await h.owner.handle_frame(h.frame(arguments=args))
            assert empty["ok"] is True and empty["data"]["native"]["page"]["records"] == []
            foreign = dataclasses.replace(h.principal, client_ref="9"*64)
            refused = await h.owner.handle_frame(h.frame(who=foreign))
            assert refused["ok"] is False and refused["data"] is None
        asyncio.run(journey())
        assert [event.to_dict() for event in h.runtime.events.list_events(job_id=h.job.job_id)] == before
        h.port.retire()
        assert process.wait(timeout=40) == 0, log.read_text(errors="replace")[-6000:]
        evidence = json.loads(report.read_text())
        assert evidence["native_files_before"] == evidence["native_files_after"]
        assert evidence["original_writer_held"] and evidence["port_closed"]
        assert evidence["native_read_calls"] >= 1  # Original native projection cache may serve later reads.
        assert evidence["gateway_methods"] == ["projections", "page", "projections", "page", "page", "page"]
        assert evidence["agent_create_calls"] == evidence["agent_resume_calls"] == evidence["provider_calls"] == 0
        assert evidence["native_session_promoted"] is False and evidence["installed"] is False
        print("NATIVE_RUNTIME_PROCESS_PROOF "+json.dumps(evidence, sort_keys=True))
    finally:
        h.port.retire()
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=10)


@pytest.mark.parametrize("native_enabled,census_enabled", [(True, True), (True, False), (False, True)])
def test_original_bridge_keeps_native_history_and_profile_census_independent(h, tmp_path, native_enabled, census_enabled):
    calls = []
    def census(principal, arguments):
        assert principal == principal_projection(h.principal)
        assert arguments == {}
        calls.append("census")
        return {"fixture_profile_census": True}
    def forbidden(*args):
        pytest.fail("read entered a modifying owner")
    h.owner = build_runtime_session_bridge(
        h.runtime, dialogue_socket_path=tmp_path / "unused-coexistence.sock",
        deepseek_session=h.native if native_enabled else None,
        web_census_handler=census if census_enabled else None,
        summon_handler=forbidden, attention_requester=forbidden)
    frame = {**h.frame(), "tool": "session_web_census", "arguments": {}}
    before = [event.to_dict() for event in h.runtime.events.list_events(job_id=h.job.job_id)]
    async def exercise():
        observed = await h.owner.handle_frame(frame)
        assert observed["ok"] is census_enabled
        if census_enabled:
            assert observed["data"] == {"fixture_profile_census": True}
        else:
            assert observed["error"]["code"] == "backend_unavailable"
        assert_no_frame(h)
        prior_calls = list(calls)
        if native_enabled:
            result, (wire, _) = await roundtrip(h)
            assert result["ok"] is True
            assert result["data"]["native_session_id"] == h.association.native_session_id
            assert wire["read"] == {"kind": "snapshot"}
        else:
            result = await h.owner.handle_frame(h.frame())
            assert result["ok"] is False and result["data"] is None
            assert_no_frame(h)
        assert calls == prior_calls
        with pytest.raises(ValueError, match="native read guard requires"):
            await h.owner.handle_frame(frame, native_read_guard=forbidden)
        assert calls == prior_calls
        h.live["source"] = False
        observed = await h.owner.handle_frame(frame)
        assert observed["ok"] is census_enabled
        assert calls == (["census", "census"] if census_enabled else [])
        assert_no_frame(h)
    asyncio.run(exercise())
    assert [event.to_dict() for event in h.runtime.events.list_events(job_id=h.job.job_id)] == before

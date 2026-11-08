"""Original receipt custody and finite physical reads; all provider/session effects are inert."""
import asyncio
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import socket
import time
from types import SimpleNamespace

import pytest
from control_plane.codex_worker import ProcessInspector, ProcessIdentityError
from control_plane.executive_orchestration_principal import OperatorPrincipalObservation
from control_plane.executive_worker_broker import BrokerStateError
from control_plane.native_conversation_read_contract import (
    NativeReadUnavailable, NativeReadPhysicalUnknown, canonical, native_read_frame,
)
from control_plane.operator_harness_wire import to_wire
from integrations.deepseek_harness import native_history as module
from tests.test_dsh_native_broker import configured, request, launch_payload, close

DONOR = "687f282e8625c6b8d11ff58211a90524be2e4317"


def no_answer(frame):
    read = frame["read"]
    return dict(schema="mastermind.dsh.native_read_result.v1", request_id=frame["request_id"],
        association_sha256=frame["association_sha256"], status="READ",
        data=dict(kind="result", state="NO_ANSWER", claim=read["claim"], terminal=read["terminal"],
                  turn_start_seq=0, turn_end_seq=1, user_message_seq=None,
                  assistant_message_seqs=[], content=None))


async def history_case(tmp_path, monkeypatch):
    f = await configured(tmp_path, monkeypatch)
    # Match the incumbent enrolled native realm (private home with worker uid/gid).
    os.chown(f.broker.policy.provider_home, -1, f.broker.policy.worker_gid)
    await request(f, "ohf-start", launch_payload(f))
    receipt = f.broker._operator_run.materialization_receipt
    await close(f)
    assert f.broker._operator_run is None
    home = f.broker.policy.provider_home
    observed = OperatorPrincipalObservation(
        attempt_id=receipt.attempt_id, worker_id=receipt.worker_id,
        process_generation_id=receipt.process_generation_id,
        provider_session_id=receipt.provider_session_id, process_identity=receipt.process_identity,
        os_principal_name=receipt.process_credentials["os_principal_name"],
        os_principal_uid=receipt.process_credentials["os_principal_uid"],
        provider_home_identity=receipt.provider_home_identity, observed_at_ms=int(time.time()*1000))
    payload = dict(epoch=to_wire(f.epoch), generation=to_wire(f.generation),
        history=dict(principal_observation=observed.to_dict(),
            requested_profile_digest=receipt.requested_profile_digest,
            observed_attestation_digest=hashlib.sha256(canonical(receipt.observed_attestation)).hexdigest()))
    source = {"current":True}
    def current():
        if not source["current"]: raise NativeReadUnavailable()
    entry = tmp_path/"finite_history_fixture.py"
    entry.write_text(
        "import os,socket,json,sys\n"
        "assert sys.argv[1:]==['--read-history']\n"
        "sock=socket.socket(fileno=int(os.environ['MMX_NATIVE_COMPANY_FD']))\n"
        "stream=sock.makefile('rb');frame=json.loads(stream.readline());read=frame['read']\n"
        "value=dict(schema='mastermind.dsh.native_read_result.v1',request_id=frame['request_id'],"
        "association_sha256=frame['association_sha256'],status='READ',"
        "data=dict(kind='result',state='NO_ANSWER',claim=read['claim'],terminal=read['terminal'],"
        "turn_start_seq=0,turn_end_seq=1,user_message_seq=None,assistant_message_seqs=[],content=None))\n"
        "sock.sendall((json.dumps(value)+'\\n').encode());stream.read();stream.close();sock.close()\n")
    installed = SimpleNamespace(binary=f.adapter.binding.binary, entrypoint=entry,
        package_manifest_sha256="3"*64, donor_sha=DONOR, require_current=current)
    class Inspector(ProcessInspector):
        def boot_session_id(self): return receipt.process_identity["boot_id"]
    reader = module.NativeHistoryReader(policy=f.broker.policy, installed=installed,
        require_source=current, inspector=Inspector())
    original_group_exists = module._process_group_exists
    physical = {"present":False}
    def group_exists(pgid):
        if pgid == receipt.process_identity["pgid"]: return physical["present"]
        return original_group_exists(pgid)
    monkeypatch.setattr(module, "_process_group_exists", group_exists)
    f.broker._native_history_binding = (reader, f.broker._native_read_binding)
    f.reader, f.history_payload, f.receipt, f.history_source = reader, payload, receipt, source
    f.physical, f.entry = physical, entry
    return f


async def content_payload(f):
    assert f.reader._receipt(f.history_payload, content=False, current=lambda:None)[0] == f.receipt
    bound = (await request(f, "ohf-native-read-binding", f.history_payload))["native_read"]
    assert bound["materialization_receipt_sha256"] == f.receipt.receipt_digest
    association = dict(schema="mastermind.dsh.native_read_association.v1", work_ref="WS:Original-read",
        root_job_id="JOB-001", native_session_id=f.receipt.provider_session_id, owner_principal_scope="1"*64,
        composition_sha256="2"*64, native_package_sha256=bound["binding"]["native_package_sha256"], donor_sha=DONOR)
    claim = dict(schema="mastermind.dsh.native_prompt_claim.v1", operationId="original-closed",
        requestId=1, sessionId=f.receipt.provider_session_id, messageId="original-message", nativeTurn=1, throughSeq=0)
    terminal = dict(schema="mastermind.dsh.native_prompt_terminal.v1", operationId=claim["operationId"],
        requestId=1, claim=claim, throughSeq=1, observedLastTurn=1, observedTurnCount=1)
    frame = native_read_frame(association_sha256=hashlib.sha256(canonical(association)).hexdigest(),
        principal_scope="1"*64, issued_at=int(time.time())-1, expires_at=int(time.time())+120,
        request=dict(kind="result", claim=claim, terminal=terminal, offset_bytes=0, expected_sha256=None))
    return {**f.history_payload, "history":{**f.history_payload["history"],
            "materialization_receipt_sha256":bound["materialization_receipt_sha256"]},
            "association":association, "request":frame}


def test_original_receipt_drives_one_finite_physical_reader_without_session_or_sweep(tmp_path, monkeypatch):
    async def run():
        f = await history_case(tmp_path, monkeypatch)
        payload = await content_payload(f)
        factories, sweeps = list(f.factories), list(f.sweeper.calls)
        original = f.adapter.native
        value = await request(f, "ohf-native-read", payload)
        assert value == {"native_read":no_answer(payload["request"])}
        assert f.reader.resource is None and f.reader.capture is None
        assert f.broker._native_history_task is None and not f.broker._native_history_unknown
        assert f.factories == factories and f.sweeper.calls == sweeps
        assert f.adapter.native is original and original.prompt_calls == 0
        assert not list(f.broker.policy.run_root.glob("native-history-*"))
    asyncio.run(run())


@pytest.mark.parametrize("fault", ["active-group", "permission", "profile", "home", "receipt-digest"])
def test_closed_reader_refuses_original_identity_drift_before_child(tmp_path, monkeypatch, fault):
    async def run():
        f = await history_case(tmp_path, monkeypatch)
        payload = await content_payload(f)
        async def forbidden(**kwargs): pytest.fail("unqualified historical read spawned")
        monkeypatch.setattr(module.NativeProcessResource, "open", forbidden)
        if fault == "active-group": f.physical["present"] = True
        elif fault == "permission":
            def denied(pgid): raise ProcessIdentityError("fixture absence unknown")
            monkeypatch.setattr(module, "_process_group_exists", denied)
        elif fault == "profile": payload["history"]["requested_profile_digest"] = "f"*64
        elif fault == "home": f.broker.policy.provider_home.chmod(0o750)
        else: payload["history"]["materialization_receipt_sha256"] = "f"*64
        assert await request(f, "ohf-native-read", payload) == {"native_read":None}
        assert f.reader.resource is None and f.reader.capture is None
        assert not f.broker._native_history_unknown
    asyncio.run(run())


def test_equal_boot_uuid_spellings_still_require_original_group_absence(tmp_path, monkeypatch):
    async def run():
        f = await history_case(tmp_path, monkeypatch)
        # Keep all secure receipt joins real; change only the inspector branch
        # comparison input through the existing immutable receipt read seam.
        import uuid
        original = f.receipt
        boot = str(uuid.uuid4())
        changed = replace(original, process_identity={**original.process_identity, "boot_id":boot},
            process_credentials={**original.process_credentials,
                "process_identity":{**original.process_credentials["process_identity"], "boot_id":boot}})
        payload = json.loads(canonical(f.history_payload))
        payload["history"]["principal_observation"]["process_identity"]["boot_id"] = boot
        monkeypatch.setattr(module, "read_operator_materialization_receipt", lambda *a, **k: changed)
        f.reader.inspector = SimpleNamespace(boot_session_id=lambda:"{"+boot.upper()+"}")
        f.physical["present"] = True
        with pytest.raises(NativeReadUnavailable):
            f.reader._receipt(payload, content=False, current=lambda:None)
    asyncio.run(run())


@pytest.mark.parametrize("cancel_reader", [False, True])
def test_broker_owns_finite_history_lock_until_read_and_cleanup_finish(tmp_path, monkeypatch, cancel_reader):
    async def run():
        f = await history_case(tmp_path, monkeypatch)
        payload = await content_payload(f)
        entered, release, settled = asyncio.Event(), asyncio.Event(), asyncio.Event()
        async def owned(payload, *, content, current):
            current(); entered.set(); await release.wait(); current()
            await asyncio.sleep(0); settled.set()
            return no_answer(payload["request"])
        f.broker._native_history_binding = (owned, f.broker._native_read_binding)
        pending = asyncio.create_task(request(f, "ohf-native-read", payload))
        await asyncio.wait_for(entered.wait(), 2)
        task = f.broker._native_history_task
        if cancel_reader:
            pending.cancel()
            with pytest.raises(asyncio.CancelledError): await pending
        shutdown = asyncio.create_task(f.broker.shutdown())
        await asyncio.sleep(0)
        assert not shutdown.done() and not task.done() and not settled.is_set()
        release.set()
        result = await asyncio.wait_for(task, 2)
        assert result["native_read"]["status"] == "READ" and settled.is_set()
        if not cancel_reader: assert await pending == result
        await asyncio.wait_for(shutdown, 2)
        assert f.broker._native_history_shutdown
        assert await request(f, "ohf-native-read", payload) == {"native_read":None}
    asyncio.run(run())


def test_unknown_reader_preserves_original_custody_and_refuses_all_sweeps_and_admission(tmp_path, monkeypatch):
    async def run():
        f = await history_case(tmp_path, monkeypatch)
        payload = await content_payload(f)
        async def unknown(payload, *, content, current):
            current(); raise NativeReadPhysicalUnknown()
        f.broker._native_history_binding = (unknown, f.broker._native_read_binding)
        assert await request(f, "ohf-native-read", payload) == {"native_read":None}
        assert f.broker._native_history_unknown and f.broker._quarantined_reason is not None
        sweeps, factories = list(f.sweeper.calls), list(f.factories)
        for operation, data in [
            ("ohf-validate", {"requested":to_wire(f.requested)}),
            ("ohf-start", launch_payload(f)),
            ("autonomy-canary", {"control_environment_attestation":{}}),
            ("ohf-reconcile-absence", {"generation":to_wire(f.generation),
                "provider_session_id":f.receipt.provider_session_id,
                "process":f.receipt.process_identity,
                "config_digest":f.receipt.observed_attestation["effective_config_digest"] or "c"*64}),
        ]:
            with pytest.raises(BrokerStateError): await request(f, operation, data)
        with pytest.raises(BrokerStateError): await f.broker.shutdown()
        assert f.sweeper.calls == sweeps and f.factories == factories
        assert await request(f, "ohf-native-read", payload) == {"native_read":None}
    asyncio.run(run())


@pytest.mark.parametrize("fault", ["settlement", "capture-cleanup"])
def test_physical_cleanup_classification_retains_original_reader_without_replay(tmp_path, monkeypatch, fault):
    async def run():
        f = await history_case(tmp_path, monkeypatch)
        payload = await content_payload(f)
        opened = []
        original_open = module.NativeProcessResource.open
        async def open_once(**kwargs):
            resource = await original_open(**kwargs); opened.append(resource); return resource
        monkeypatch.setattr(module.NativeProcessResource, "open", open_once)
        if fault == "settlement":
            original_finish = module.NativeProcessResource.finish
            async def finish(self, reason):
                actual = await original_finish(self, reason)
                assert actual.settled
                return SimpleNamespace(settled=False, exit_code=actual.exit_code)
            monkeypatch.setattr(module.NativeProcessResource, "finish", finish)
        else:
            def failed_cleanup(path): raise OSError("fixture capture retained")
            monkeypatch.setattr(module.shutil, "rmtree", failed_cleanup)
        assert await request(f, "ohf-native-read", payload) == {"native_read":None}
        assert len(opened) == 1 and opened[0].process.returncode == 0
        assert f.reader.capture is not None and f.reader.capture.is_dir()
        assert f.broker._native_history_unknown is (fault == "settlement")
        assert (f.reader.resource is opened[0]) is (fault == "settlement")
        assert await request(f, "ohf-native-read", payload) == {"native_read":None}
        assert len(opened) == 1
    asyncio.run(run())


def test_unknown_history_fences_original_flat_sweep_and_validation(tmp_path):
    from tests.test_executive_worker_broker import _fixture, _request
    async def run():
        broker, adapter, sweeper, peer, spec = _fixture(tmp_path)
        adapter.finished.set()
        await broker.execute(_request("start", {"launch_spec":spec,
            "validation_commands":[["/usr/bin/true"]]}), peer=peer)
        await broker.execute(_request("collect", {"run_id":spec["run_id"]}), peer=peer)
        broker._native_history_unknown = True
        broker._quarantined_reason = "original native history resource unresolved"
        before = list(sweeper.calls)
        for operation, payload in [
            ("status", {"fresh_uid_sweep":True}),
            ("validate", {"run_id":spec["run_id"], "argv":["/usr/bin/true"], "timeout_seconds":10}),
        ]:
            with pytest.raises(BrokerStateError):
                await broker.execute(_request(operation, payload), peer=peer)
        assert sweeper.calls == before and not broker._validation_busy
    asyncio.run(run())

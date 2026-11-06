"""Persisted denial is rejoined to original Job/Event; no live host effects."""
import asyncio
import copy
from contextlib import contextmanager
import dataclasses
import json

import pytest

from control_plane.executive_runtime import Runtime, StateConflict
from control_plane.executive_service import ExecutiveControlService
from control_plane.fresh_conversation_admission import (
    TASK_KIND, read_creation_restriction, require_original_creation_request,
    require_initial_native_claim,
)
from tests.test_fresh_conversation import case, preview, create, cleanup


async def interrupted(tmp_path, monkeypatch, *, before_child=True):
    service, runtime, owner, principal, request, adapters = case(tmp_path)
    prepared = await preview(owner, principal, request)
    if before_child:
        async def no_first_cycle(root):
            raise OSError("fixture interrupted before child claim")
        monkeypatch.setattr(service, "_run_coo_cycle", no_first_cycle)
    else:
        async def no_first_claim(job_id, **kwargs):
            raise OSError("fixture interrupted before native claim")
        monkeypatch.setattr(service.operator_supervisor, "start_retained_native_job", no_first_claim)
    # The actual ingress admitted the original root before its continuation
    # became unknown. This fixture never asserts that an unknown effect is clear.
    try:
        await create(owner, principal, request, prepared)
    except Exception:
        pass
    roots = [j for j in runtime.jobs.list_jobs() if j.parent_job_id is None]
    assert len(roots) == 1 and not runtime.attempts.list_attempts() and not adapters
    await cleanup(service)
    return service, runtime, roots[0]


def test_closed_request_restart_autotick_and_native_claim_refuse(tmp_path, monkeypatch):
    async def run():
        service, runtime, root = await interrupted(tmp_path, monkeypatch, before_child=False)
        material = read_creation_restriction(runtime, root)
        assert material and root.constraints["task_kind"] == TASK_KIND
        reopened = Runtime.at(service.config.runtime_root)
        restarted = ExecutiveControlService(service.config, autonomy_guard=lambda: None)
        restarted.runtime = reopened
        assert restarted._next_bound_coo_root() is None
        with pytest.raises((StateConflict, ValueError)):
            restarted._require_foreground_only_source(root.job_id, cycle_entry=True)
        with pytest.raises((StateConflict, ValueError)):
            reopened.jobs.create_interactive_operator(root.job_id,
                command_id=f"coo-cycle:{root.job_id}:create-interactive:0")
        with pytest.raises((StateConflict, ValueError)):
            require_original_creation_request(reopened, root, None)
        child = next(j for j in reopened.jobs.list_jobs() if j.parent_job_id == root.job_id)
        with pytest.raises((StateConflict, ValueError)):
            require_initial_native_claim(reopened.store, root_job_id=root.job_id,
                role="plan", profile=child.constraints["execution_profile_id"])
        with pytest.raises((StateConflict, ValueError)):
            reopened.attempts.dispatch_cycle_job(child.job_id, command_id="refused-fresh-claim", lease_owner="fixture")
        assert not reopened.attempts.list_attempts()
    asyncio.run(run())


def test_removed_tampered_and_copied_receipts_never_become_autonomous(tmp_path, monkeypatch):
    async def run():
        service, runtime, root = await interrupted(tmp_path, monkeypatch)
        with runtime.store.read() as conn:
            row = conn.execute("SELECT event_id,command_id,payload_json FROM events WHERE event_type='JOB_CREATED' AND job_id=?", (root.job_id,)).fetchone()
            constraints = conn.execute("SELECT constraints_json FROM jobs WHERE job_id=?", (root.job_id,)).fetchone()[0]
        payload = json.loads(row["payload_json"])
        assert read_creation_restriction(runtime, root)
        cases = []
        changed = copy.deepcopy(payload); del changed["fresh_conversation_admission"]
        cases.append((changed, constraints))
        changed = copy.deepcopy(payload); changed["provenance"].pop("fresh_conversation")
        cases.append((changed, constraints))
        changed = copy.deepcopy(payload); changed["provenance"]["fresh_conversation_digest"] = "0" * 64
        cases.append((changed, constraints))
        changed = copy.deepcopy(payload); changed["provenance"]["fresh_conversation"]["command_id"] = "ceo-intent:foreign"
        cases.append((changed, constraints))
        changed_constraints = json.loads(constraints); changed_constraints.pop("task_kind")
        cases.append((payload, json.dumps(changed_constraints)))
        # Actual immutable Event triggers reject an attempted edit. To test
        # corrupted/restored-storage reads without disabling that protection,
        # project ONLY the selected SQL read row; all other reads/writes stay real.
        with pytest.raises(StateConflict):
            with runtime.store.transaction() as conn:
                conn.execute("UPDATE events SET payload_json='{}' WHERE event_id=?", (row["event_id"],))
        original_read, original_get = runtime.store.read, runtime.jobs.get_job
        for body, current in cases + [(None, constraints)]:
            changed_root = dataclasses.replace(root, constraints=json.loads(current))
            class Projection:
                def __init__(self, conn): self.conn = conn
                def execute(self, sql, args=()):
                    if sql.startswith("SELECT command_id,payload_json FROM events WHERE event_type='JOB_CREATED'") and args == (root.job_id,):
                        class Rows:
                            def fetchall(self):
                                return [] if body is None else [{"command_id": row["command_id"], "payload_json": json.dumps(body)}]
                        return Rows()
                    return self.conn.execute(sql, args)
            @contextmanager
            def corrupted_read():
                with original_read() as conn: yield Projection(conn)
            with monkeypatch.context() as m:
                m.setattr(runtime.store, "read", corrupted_read)
                m.setattr(runtime.jobs, "get_job", lambda key: changed_root if key == root.job_id else original_get(key))
                with pytest.raises(StateConflict): read_creation_restriction(runtime, changed_root)
                refusals = {}
                assert service._next_bound_coo_root(prestart_refusals=refusals) is None
                assert root.job_id in refusals
                with pytest.raises((StateConflict, ValueError)):
                    runtime.jobs.create_interactive_operator(root.job_id,
                        command_id=f"coo-cycle:{root.job_id}:create-interactive:0")
                assert not runtime.attempts.list_attempts()
        assert not runtime.attempts.list_attempts() and len(runtime.jobs.list_jobs()) == 1
    asyncio.run(run())


def test_public_metadata_cannot_mint_private_creation_source(tmp_path):
    service, runtime, owner, principal, request, adapters = case(tmp_path)
    before = runtime.events.list_events()
    for fields in ({"constraints": {"task_kind": TASK_KIND}},
                   {"provenance": {"fresh_conversation": {}, "fresh_conversation_digest": "0" * 64}}):
        with pytest.raises(StateConflict):
            runtime.jobs.create_job("public marker forgery", command_id="forged-creation", **fields)
    assert not runtime.jobs.list_jobs() and runtime.events.list_events() == before


def test_nominal_creation_copy_and_changed_intent_rejected_before_insert(tmp_path, monkeypatch):
    async def run():
        service, runtime, owner, principal, request, adapters = case(tmp_path)
        prepared = await preview(owner, principal, request)
        original = runtime.jobs.create_v2_orchestration_root
        evidence = []
        def inspect(intent, **kwargs):
            source = kwargs["_fresh_conversation_source"]
            assert source.check() is None
            for forged in (copy.copy(source), dataclasses.replace(source),
                           dataclasses.replace(source, _material=source._material.replace(b'WS:ONE', b'WS:TWO'))):
                with pytest.raises(ValueError): forged.check()
                evidence.append("copied-refused")
            changed = copy.deepcopy(intent); changed["workstream"] = "WS:TWO"
            with pytest.raises(ValueError): source.check_intent(changed)
            assert not runtime.jobs.list_jobs()
            return original(intent, **kwargs)
        monkeypatch.setattr(runtime.jobs, "create_v2_orchestration_root", inspect)
        try:
            result = await create(owner, principal, request, prepared)
            assert result["state"] == "CREATED" and len(evidence) == 3
        finally:
            await cleanup(service)
    asyncio.run(run())


def test_fresh_route_never_adopts_unmarked_generic_namespace_lookalike(tmp_path, monkeypatch):
    async def run():
        from control_plane.fresh_conversation import ConversationRefusal
        service, runtime, owner, principal, request, adapters = case(tmp_path)
        prepared = await preview(owner, principal, request)
        original = runtime.jobs.create_v2_orchestration_root
        # Deliberately create an ordinary strict-v2 root through its real
        # incumbent producer, with the computed command namespace and matching
        # prompt data, but WITHOUT the private fresh creation source.
        def generic(intent, **kwargs):
            kwargs.pop("_fresh_conversation_source")
            return original(intent, **kwargs)
        monkeypatch.setattr(runtime.jobs, "create_v2_orchestration_root", generic)
        with pytest.raises(ConversationRefusal):
            await create(owner, principal, request, prepared)
        root, = runtime.jobs.list_jobs()
        assert read_creation_restriction(runtime, root) is None
        assert not runtime.attempts.list_attempts() and not adapters
        before = runtime.events.list_events()
        monkeypatch.setattr(runtime.jobs, "create_v2_orchestration_root", original)
        selected = {key: request[key] for key in ("work_ref", "operation_key")}
        for operation in (owner.status, owner.read):
            with pytest.raises(ConversationRefusal, match="original_operation_mismatch"):
                await operation(principal, selected)
        with pytest.raises(ConversationRefusal):
            await create(owner, principal, request, prepared)
        assert runtime.events.list_events() == before
        assert len(runtime.jobs.list_jobs()) == 1 and not runtime.attempts.list_attempts() and not adapters
        await cleanup(service)
    asyncio.run(run())

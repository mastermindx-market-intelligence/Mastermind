"""Production factory joins the real canonical sink, with fixture grounding/host admission."""
import asyncio
from pathlib import Path

import pytest

from control_plane.executive_service import _ForegroundExecution, _canonical_json
from control_plane import executive_ceo_ingress as ingress, foreground_operation as scope
from integrations.executive_mcp.web_ceo_sessions import WEB_CEO_SESSIONS_PROFILE
from tests.test_executive_mcp_installed_fabric_composition import factory_service
from tests.test_foreground_operation import frame
from tests import test_foreground_fresh_admission as fresh


@pytest.mark.parametrize("edge", ["fresh", "legacy", "before_commit", "after_commit", "drive", "duplicate", "drive_failure"])
def test_actual_factory_fresh_source_and_committed_error_classification(tmp_path, short_socket_root, monkeypatch, edge):
    async def run():
        state = {"live": True}
        def host():
            if not state["live"]: raise ValueError("closed fixture host")
        async with factory_service(tmp_path, short_socket_root, monkeypatch,
                profile=WEB_CEO_SESSIONS_PROFILE) as (service, raw, _):
            await service.start()
            runtime = service._require_runtime()
            drives = []
            if edge in {"fresh", "drive", "duplicate", "drive_failure"}:
                # Wrapper-only fixture: actual host eligibility and the real
                # driver are exercised separately in the eligibility tests.
                snapshot = _ForegroundExecution("ORDINARY_OPERATOR", _canonical_json(service._require_current_coo_binding()))
                monkeypatch.setattr(service, "_foreground_execution_state", lambda **kw: snapshot)
                monkeypatch.setattr(service, "_require_foreground_execution", lambda expected: None if expected == snapshot else pytest.fail("foreign fixture snapshot"))
                assert service.config.coo_attended_work_placements == ()
                async def drive(op, root):
                    op.require_root(root)
                    assert service._foreground_cycle_owner == (asyncio.current_task(), op)
                    assert asyncio.current_task() in service._coo_action_tasks
                    drives.append(root)
                    if edge == "drive_failure": raise RuntimeError("private failure")
                    return {"state": "NO_ACTION", "root_job_id": root, "delivery": "INCOMPLETE"}
                monkeypatch.setattr(service, "_drive_foreground_cycle", drive)
            fresh.phase1fc._register_placement_union(runtime)
            owner = service._ceo_ingress_app_binding.session_bridge_provider_factory(runtime)
            original_observe, original_submit = ingress._observe_trusted_grounding, ingress.handle_frame
            seen = []
            async def observed(_):
                result = await original_observe(fresh.hooks.pr_a._FakeGrounding())
                if edge == "before_commit": state["live"] = False
                return result
            async def submit(parsed, **kw):
                assert kw["strict_v2_admission"] is True and kw["runtime"] is runtime
                seen.append(kw["fresh_admission_observer"])
                # Existing host binding and grounding providers are explicit
                # fixture boundaries; root/event/observer/guard use actual code.
                return await original_submit(parsed, runtime=runtime,
                    grounding_provider=fresh.hooks.pr_a._FakeGrounding(),
                    workspace_root=Path(raw["proof_workspace_root"]),
                    service_state="READY", ceo_ingress_armed=True, strict_v2_admission=True,
                    execution_binding_provider=lambda: (kw["execution_binding_provider"](), fresh.phase1fc._v3_execution_binding())[1],
                    dialogue_source_provider=lambda *_: fresh.hooks._dialogue_source(),
                    admission_guard=kw["admission_guard"], fresh_admission_observer=kw["fresh_admission_observer"])
            monkeypatch.setattr(ingress, "_observe_trusted_grounding", observed)
            monkeypatch.setattr(ingress, "handle_frame", submit)
            if edge == "after_commit":
                original_bind = scope.ForegroundOperation._bind_admitted_root
                def lost_after_commit(self, root_id, command_id):
                    state["live"] = False
                    original_bind(self, root_id, command_id)
                monkeypatch.setattr(scope.ForegroundOperation, "_bind_admitted_root", lost_after_commit)
            f = frame()
            if edge == "legacy":
                result = await owner.handle_frame(f)
                assert seen == [None]
            else:
                async with scope._session_bridge_foreground_dispatch(runtime, f, host) as op:
                    result = await owner.handle_frame(f)
                    if edge in {"fresh", "drive", "duplicate"}: assert op._root == result["data"]["job_id"]
                if edge == "duplicate":
                    async with scope._session_bridge_foreground_dispatch(runtime, f, host) as replay_op:
                        replay = await owner.handle_frame(f)
                        assert replay["ok"] and replay["data"]["duplicate"]
                        assert "foreground_completion" not in replay["data"] and replay_op._root is None
                if edge in {"fresh", "drive", "duplicate"}:
                    assert drives == [result["data"]["job_id"]]
                    assert result["data"]["foreground_completion"]["delivery"] == "INCOMPLETE"
            if edge in {"fresh", "legacy", "drive", "duplicate"}:
                assert result["ok"] and result["data"]["dispatched"] is False
                assert len(runtime.jobs.list_jobs()) == 1
            elif edge == "before_commit":
                assert not result["ok"] and result["error"]["code"] == "host_not_current"
                assert runtime.jobs.list_jobs() == [] and seen == []
            else:
                assert not result["ok"] and result["error"]["code"] == "effect_unknown"
                assert len(runtime.jobs.list_jobs()) == 1
            assert runtime.attempts.list_attempts() == []
            assert service._foreground_cycle_owner is None and not service._coo_action_tasks
    asyncio.run(run())

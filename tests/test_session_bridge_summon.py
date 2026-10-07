"""Installed Session Bridge SUMMON reuses canonical Executive admission."""
from __future__ import annotations

import asyncio
import copy
import dataclasses
import json
from pathlib import Path

import pytest

from integrations.session_bridge.installed import PRIVATE_SCHEMA
from integrations.session_bridge.schemas import BridgeError, validate_tool_arguments, summon_input_schema
from integrations.executive_mcp import schemas as executive
from tests.test_session_bridge_installed import principal_frame
from tests.test_executive_ceo_ingress import _raw_ceo_request
from tests.test_executive_mcp_installed_fabric_composition import factory_service, short_socket_root
from tests import test_executive_ceo_ingress as ingress_fixture
from tests import test_executive_ceo_ingress_admission_hook as hook_fixture
from tests import test_executive_os_phase1fc as host_fixture


def request():
    return {
        "operation_key": "session-installed-summon-001",
        "objective": "Inspect one bounded contract and return its falsifier.",
        "execution_profile": "research_only",
        "department": "executive-infrastructure", "priority": 0,
        "workstream": hook_fixture.WORKSTREAM, "attempt_limit": 1,
    }


@pytest.mark.parametrize("profile", ["research_only", "bounded_code_change"])
def test_summon_schema_and_normalization_reuse_executive_contract(profile):
    args = request()
    args["execution_profile"] = profile
    if profile == "bounded_code_change":
        args.update(allowed_write_paths=["tests", "tests"],
                    validation={"pytest_targets": ["tests/test_session_bridge_summon.py"],
                                "git_diff_check": False})
    assert validate_tool_arguments("session_summon", args) == executive.validate_tool_arguments(
        executive.MODIFYING_TOOL, args)
    standard = copy.deepcopy(executive.tool_spec(executive.MODIFYING_TOOL).input_schema)
    standard["required"].append("workstream")
    assert summon_input_schema() == standard


@pytest.mark.parametrize("field", [
    "provider", "model", "host", "account", "credential", "commission_ref",
    "requested_authorities", "validation_commands", "actor", "branch", "worktree",
])
def test_summon_cannot_supply_privileged_fields(field):
    with pytest.raises(BridgeError) as exc:
        validate_tool_arguments("session_summon", {**request(), field: "caller-value"})
    assert exc.value.code == "invalid_input"


def test_summon_requires_workstream_before_owner_entry():
    args = request()
    del args["workstream"]
    with pytest.raises(BridgeError) as exc:
        validate_tool_arguments("session_summon", args)
    assert exc.value.code == "invalid_input"


@pytest.mark.parametrize("fault,expected", [
    (None, None),
    ("missing_scope", "authority_refused"),
    ("source_absent", "backend_unavailable"),
    ("source_moved", "operation_conflict"),
    ("grounding_moved", "grounding_changed"),
    ("binding_moved", "effect_unknown"),
])
def test_installed_summon_uses_existing_strict_admission(tmp_path, short_socket_root, monkeypatch, fault, expected):
    from integrations.executive_mcp.web_ceo_sessions import WEB_CEO_SESSIONS_PROFILE
    from integrations.mastermind_executive_app import web_commission_source
    from control_plane import executive_ceo_ingress

    source_calls = []
    def source(intent_id, work_ref):
        source_calls.append((intent_id, work_ref))
        if fault == "source_absent":
            return None
        return hook_fixture._dialogue_source(
            "e" * 40 if fault == "source_moved" and len(source_calls) > 1 else "c" * 40)
    constructions = []
    def source_factory():
        constructions.append(1)
        return source
    monkeypatch.setattr(web_commission_source, "GitHubWebCommissionSourceProvider", source_factory)

    async def run():
        async with factory_service(
            tmp_path, short_socket_root, monkeypatch, profile=WEB_CEO_SESSIONS_PROFILE
        ) as (service, raw, _):
            assert service._ceo_ingress_dialogue_source_provider is source
            assert constructions == [1]
            await service.start()
            runtime = service._require_runtime()
            host_fixture._register_placement_union(runtime)
            monkeypatch.setattr(service, "_require_current_coo_binding", host_fixture._v3_execution_binding)
            observations = []
            def observe():
                observations.append(1)
                value = dict(ingress_fixture.GROUNDING_A)
                if fault == "grounding_moved" and len(observations) >= 3:
                    value["mastermind_sha"] = "f" * 40
                return value
            monkeypatch.setattr(service._ceo_ingress_app_binding.grounding_provider, "observe", observe)
            if fault == "binding_moved":
                original = executive_ceo_ingress.handle_frame
                async def moved(*args, **kwargs):
                    result = await original(*args, **kwargs)
                    service._ceo_ingress_app_binding = dataclasses.replace(service._ceo_ingress_app_binding)
                    return result
                monkeypatch.setattr(executive_ceo_ingress, "handle_frame", moved)
            principal = principal_frame()
            if fault == "missing_scope":
                principal["scopes"] = ["mastermind.executive.read"]
            async def call(args):
                frame = {"schema": PRIVATE_SCHEMA, "tool": "session_summon",
                         "principal": principal, "arguments": args}
                outer = await _raw_ceo_request(Path(raw["ceo_ingress_socket_path"]),
                                              (json.dumps(frame) + "\n").encode())
                assert outer["ok"] is True
                return outer["result"]

            result = await call(request())
            jobs = runtime.jobs.list_jobs()
            if expected is not None:
                assert result["ok"] is False
                assert result["error"]["code"] == expected, result
                assert len(jobs) == (1 if fault == "binding_moved" else 0)
                if fault == "missing_scope":
                    assert observations == source_calls == []
                return

            assert result["ok"] is True, result
            receipt = result["data"]
            assert receipt["dispatched"] is False
            assert len(jobs) == 1
            assert jobs[0].job_id == receipt["job_id"]
            assert jobs[0].status.value == "QUEUED"
            assert jobs[0].requested_authorities == ["READ", "RESEARCH"]
            assert len(source_calls) == 2
            assert all(item[1] == request()["workstream"] for item in source_calls)
            with runtime.store.read() as connection:
                from control_plane.executive_runtime import _dialogue_source_from_root_creation
                admitted = _dialogue_source_from_root_creation(connection, root_job_id=receipt["job_id"])
            assert admitted.to_dict() == hook_fixture._dialogue_source()
            duplicate = await call(request())
            assert duplicate["data"] == {**receipt, "duplicate": True}
            assert len(runtime.jobs.list_jobs()) == 1
            changed = await call({**request(), "objective": "A different bounded objective."})
            assert changed["ok"] is False
            assert changed["error"]["code"] == "operation_conflict"
            assert len(runtime.jobs.list_jobs()) == 1
            assert runtime.attempts.list_attempts() == []

    asyncio.run(run())

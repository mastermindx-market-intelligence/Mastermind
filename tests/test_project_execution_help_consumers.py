"""Reached signed API and packaged Hermes consumers of original-input help v2.

The real existing native lifecycle/source registration and signed-resource App
owners are reused. Their documented source-seal, native PluginManager and
same-process private-hop fixture boundaries remain explicit. No provider model,
installed profile or Unix service is exercised by this file.
"""
import asyncio
import json
import time

import pytest

from common import coo_project_help_contract as wire
from integrations.hermes_harness.tests import test_native_project_help as native_help
from integrations.hermes_runtime.tests.test_native_request_observation import native
from tests import test_t3_project_help_api as api
from tests.test_project_execution_help_read import (
    execution_help, execution_project, qualified_help, full_joined, owner,
    env, isolated_git_env, identity, rsa_key,
)


def test_actual_signed_t3_api_reads_the_original_execution_help_witness(execution_help, rsa_key, tmp_path):
    f = execution_help
    signed = api.signed_help.__wrapped__(f, rsa_key, tmp_path)
    before = api._events(f)
    async def run():
        async with api._session(signed) as (session, _):
            listed = await session.list_tools()
            assert wire.TOOL in {tool.name for tool in listed.tools}
            value = await session.call_tool(wire.TOOL, {"work_ref": f.work})
            payload = api._payload(value)
            assert value.isError is False and payload["ok"] is True, (payload, signed.failures)
            return payload["data"]
    result = asyncio.run(run())
    assert result["schema"] == wire.EXECUTION_RESULT_SCHEMA and result["scope"] == f.scope
    assert result["original_execution"]["original_source_plan"] == f.source_plan
    assert result["observation"]["mission"]["mission_read_state"] == "PARTIAL"
    assert result["execution_authority"] is False and result["native_origin_attested"] is False
    assert len(signed.reads) == 2 and api._events(f) == before
    assert signed.token not in json.dumps(result) and signed.second not in json.dumps(result)


def test_actual_packaged_hermes_context_and_memory_deliver_original_input_witness(
        execution_help, rsa_key, native, monkeypatch, tmp_path):
    signed = native_help.hermes_signed.__wrapped__(execution_help, rsa_key, tmp_path, monkeypatch)
    lifecycle = native_help.lifecycle.__wrapped__(native, signed, monkeypatch, tmp_path)
    value = next(lifecycle)
    before = api._events(execution_help)
    observed = {}
    timings = []
    original_help = execution_help.provider.read_project_help
    async def timed_help(*args, **kwargs):
        started = time.monotonic()
        try:
            result = await original_help(*args, **kwargs)
        except Exception as error:
            timings.append((round(time.monotonic() - started, 3), type(error).__name__))
            raise
        timings.append((round(time.monotonic() - started, 3), result["schema"]))
        return result
    monkeypatch.setattr(execution_help.provider, "read_project_help", timed_help)
    try:
        def reached(agent):
            result = json.loads(value.source_tool({}, session_id=agent.session_id))
            assert result["ok"] is True, result
            observed["tool"] = result["context"]["project_help"]
            assert observed["tool"].get("schema") == wire.EXECUTION_RESULT_SCHEMA, {
                "state": observed["tool"].get("state"), "reason": observed["tool"].get("reason"),
                "read_timings": timings, "attempts": len(signed.attempts), "completed_reads": len(signed.reads),
                "source_failures": signed.failures[-2:]}
        result = native_help.native_memory.exercise(value, before_prefetch=reached)
        assert observed["tool"]["schema"] == wire.EXECUTION_RESULT_SCHEMA
        assert observed["tool"]["scope"] == execution_help.scope
        assert observed["tool"]["original_execution"]["original_source_plan"] == execution_help.source_plan
        assert wire.EXECUTION_RESULT_SCHEMA in result["context"]
        assert result["context"] in result["built"][0][-1]["content"]
        delivery = result["live_readback"]["context"]["last_delivery"]
        assert delivery["project_help"]["state"] == "AVAILABLE"
        assert delivery["prompt"]["boundary"] == "build_api_messages"
        assert value.stores == [] and value.slot.startup is None and value.slot.registration is None
        assert all(arguments == {"work_ref": execution_help.work} for _, arguments in value.session.calls)
        assert api._events(execution_help) == before
    finally:
        with pytest.raises(StopIteration):
            next(lifecycle)

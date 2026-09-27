"""Actual Codex machinery with scripted loopback responses; no real inference."""
import importlib.util
import os
from pathlib import Path

import pytest

CODEX = os.environ.get("MASTERMIND_CODEX_NATIVE_PROBE")


@pytest.mark.skipif(not CODEX, reason="explicit native Codex binary required")
def test_native_fixture_completes_and_exposes_spawn_schema(tmp_path):
    name = "tests.codex_orchestrator_native_fixture"
    assert importlib.util.find_spec(name) is not None, "native scripted fixture is absent"
    from tests.codex_orchestrator_native_fixture import run_native_fixture
    result = run_native_fixture(Path(CODEX), tmp_path)
    assert result["parent_status"] == "completed"
    assert result["request_count"] == 1
    assert result["spawn_schema"] is not None
    assert result["parent_sandbox"] == {"type": "readOnly", "networkAccess": False}
    assert result["real_credentials_used"] is False
    assert result["served_model_attested"] is False
    assert result["process_settled"] is True


@pytest.mark.skipif(not CODEX, reason="explicit native Codex binary required")
@pytest.mark.parametrize("role,model", [("l2_sol_ceo", "gpt-5.6-sol"), ("l2_astra_ceo", "gpt-6-astra")])
def test_native_named_child_uses_role_model_but_retains_spawn_tool(tmp_path, role, model):
    from tests.codex_orchestrator_native_fixture import run_native_fixture
    import inspect
    assert "role" in inspect.signature(run_native_fixture).parameters, "native spawn scenario is absent"
    result = run_native_fixture(Path(CODEX), tmp_path, role=role)
    assert result["parent_status"] == "completed"
    assert len(result["children"]) == 1, result
    child = result["children"][0]
    assert child["parentThreadId"] == result["parent_id"]
    assert child["agentRole"] == role
    assert child["model"] == model
    assert child["reasoningEffort"] == "high"
    assert result["child_request_model"] == model
    # Native 0.154.0 ignores role-local agents.enabled=false for this tool.
    # The separate invocation-level negative below is the actual confinement proof.
    assert result["child_spawn_tool_present"] is True
    assert result["child_read_only_instructions"] is True
    assert result["child_own_role_instructions"] is True
    assert result["process_settled"] is True
    assert result["served_model_attested"] is False


@pytest.mark.skipif(not CODEX, reason="explicit native Codex binary required")
def test_native_coordinator_grandchild_attempt_is_rejected(tmp_path):
    from tests.codex_orchestrator_native_fixture import run_native_fixture
    import inspect
    assert "attempt_grandchild" in inspect.signature(run_native_fixture).parameters, "descendant negative is absent"
    result = run_native_fixture(Path(CODEX), tmp_path, role="l2_sol_ceo", attempt_grandchild=True)
    assert result["grandchildren"] == []
    assert result["grandchild_call_outputs"], result
    assert result["completed_thread_count"] == 2
    assert result["process_settled"] is True


@pytest.mark.skipif(not CODEX, reason="explicit native Codex binary required")
def test_role_flag_and_depth_setting_do_not_replace_single_child_cap(tmp_path, monkeypatch):
    import tests.codex_orchestrator_native_fixture as fixture
    original = fixture.configuration_overrides
    def expanded_test_only(*args, **kwargs):
        values = original(*args, **kwargs)
        return tuple(v.replace("agents.max_concurrent_threads_per_session=1",
                               "agents.max_concurrent_threads_per_session=2") for v in values) + ("agents.max_depth=1",)
    monkeypatch.setattr(fixture, "configuration_overrides", expanded_test_only)
    result = fixture.run_native_fixture(Path(CODEX), tmp_path, role="l2_sol_ceo", attempt_grandchild=True)
    assert len(result["grandchildren"]) == 1
    assert result["grandchildren"][0]["parentThreadId"] == result["children"][0]["id"]
    assert result["process_settled"] is True


@pytest.mark.skipif(not CODEX, reason="explicit native Codex binary required")
def test_native_child_cannot_write_project_marker(tmp_path):
    from tests.codex_orchestrator_native_fixture import run_native_fixture
    import inspect
    assert "attempt_write" in inspect.signature(run_native_fixture).parameters, "native sandbox negative is absent"
    result = run_native_fixture(Path(CODEX), tmp_path, role="l2_sol_ceo", attempt_write=True)
    assert result["write_call_outputs"], result
    import json
    observed = json.dumps(result["write_call_outputs"]).lower()
    assert "operation not permitted" in observed or "permission denied" in observed
    assert "exit_code" in observed
    assert result["project_marker_exists"] is False
    assert result["completed_thread_count"] == 2
    assert result["process_settled"] is True


@pytest.mark.skipif(not CODEX, reason="explicit native Codex binary required")
def test_native_child_result_reaches_exact_parent_provider_request(tmp_path):
    from tests.codex_orchestrator_native_fixture import run_native_fixture
    result = run_native_fixture(Path(CODEX), tmp_path, role="l2_sol_ceo")
    assert result.get("parent_received_child_completion") is True, "exact parent has not consumed native child return"
    assert result["completed_thread_count"] == 2
    assert result["process_settled"] is True
    assert result["served_model_attested"] is False



def test_scripted_fixture_closes_listener_after_source_preflight_failure(tmp_path, monkeypatch):
    import tests.codex_orchestrator_native_fixture as fixture
    servers = []
    original = fixture.ThreadingHTTPServer
    def recording_server(*args, **kwargs):
        server = original(*args, **kwargs)
        servers.append(server)
        return server
    def fail_inspection(*args, **kwargs):
        raise ValueError("source preflight refused")
    monkeypatch.setattr(fixture, "ThreadingHTTPServer", recording_server)
    monkeypatch.setattr(fixture, "inspect_bundle", fail_inspection)
    try:
        with pytest.raises(ValueError, match="source preflight refused"):
            fixture.run_native_fixture(Path("/not-invoked"), tmp_path)
        assert servers[0].fileno() == -1, "fixture leaked its listener after setup failure"
    finally:
        for server in servers:
            if server.fileno() >= 0:
                server.shutdown()
                server.server_close()

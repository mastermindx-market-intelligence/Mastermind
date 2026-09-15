from __future__ import annotations

import ast
import asyncio
import json
from pathlib import Path
from unittest import mock

import pytest

from control_plane import executive_ceo_ingress
from scripts import chairman_submit_ceo_intent_v2 as launcher


FORBIDDEN_HOST_OWNED_NAMES = (
    "provider", "provider_home", "credential_home", "uid", "gid",
    "worker_id", "session_id", "authority", "execution_binding",
    "dialogue_source",
)


def _frame(**extra: object) -> dict[str, object]:
    value: dict[str, object] = {
        "schema": executive_ceo_ingress.SUBMIT_SCHEMA_V2,
        "request_ref": "W1H2-REQUEST-1",
        "observed_grounding": {"mastermind_sha": "a" * 40, "macro_sha": "b" * 40, "boot_packet_schema": executive_ceo_ingress.BOOT_PACKET_SCHEMA},
        "request": {"objective": "test", "workstream": "WS-1"},
    }
    value.update(extra)
    return value


def test_d1_v2_admission_refuses_unarmed_and_degraded_before_shape_or_sink() -> None:
    runtime = mock.Mock()
    runtime.jobs.list_jobs.return_value = []
    jobs_before = runtime.jobs.list_jobs()
    with mock.patch.object(executive_ceo_ingress.ceo_intent, "submit_intent") as sink:
        for state, armed in (("READY", False), ("DEGRADED", True)):
            with pytest.raises(executive_ceo_ingress.CeoIngressError) as error:
                asyncio.run(executive_ceo_ingress.handle_frame(
                    {"schema": executive_ceo_ingress.SUBMIT_SCHEMA_V2},
                    runtime=runtime, grounding_provider=object(), workspace_root="/tmp",
                    service_state=state, ceo_ingress_armed=armed,
                ))
            assert error.value.code == "ingress_unavailable"
        sink.assert_not_called()
    assert jobs_before == []
    assert runtime.jobs.list_jobs() == []
    assert runtime.jobs.list_jobs.call_count >= 2


def test_d2_wrong_peer_is_refused_before_body_read() -> None:
    service = object.__new__(__import__("control_plane.executive_service", fromlist=["ExecutiveControlService"]).ExecutiveControlService)
    service._ceo_ingress_tasks = set()
    service._ceo_ingress_peer_uid = 452
    service._ceo_ingress_app_binding = None
    service._ceo_ingress_ready = True
    reader = mock.Mock()
    reader.readuntil = mock.AsyncMock()
    writer = mock.Mock()
    writer.get_extra_info.return_value = object()
    writer.write = mock.Mock()
    writer.drain = mock.AsyncMock()
    writer.wait_closed = mock.AsyncMock()
    with mock.patch("control_plane.executive_service._peer_uid", return_value=501):
        asyncio.run(service._handle_ceo_ingress_connection(reader, writer))
    reader.readuntil.assert_not_called()


def test_d3_launcher_is_strict_v2_and_has_no_host_owned_fields() -> None:
    frame = launcher.build_frame("W1H2-REQUEST-1", {"objective": "test", "workstream": "WS-1"}, {"mastermind_sha": "a" * 40, "macro_sha": "b" * 40, "boot_packet_schema": executive_ceo_ingress.BOOT_PACKET_SCHEMA})
    assert frame["schema"] is executive_ceo_ingress.SUBMIT_SCHEMA_V2
    assert set(frame) == {"schema", "request_ref", "observed_grounding", "request"}
    encoded = json.dumps(frame)
    for forbidden in ("execution_binding", "dialogue_source"):
        assert forbidden not in encoded


def test_d3_v2_submit_uses_host_providers_and_refuses_missing_binding() -> None:
    frame = _frame(request_ref="req-host-provider-1", request={
        "objective": "test", "workstream": "WS:HOST-PROVIDER",
        "department": "executive-infrastructure", "priority": 10,
        "execution_profile": "research_only",
    })
    binding = {"provider": "host-provider", "model": "host-model"}
    source = {
        "schema_version": "mastermind.executive_dialogue_source/v1",
        "work_ref": "WS:HOST-PROVIDER",
        "commission_ref": {
            "repository": "mastermindx-market-intelligence/Mastermind",
            "path": "research/commission.md",
            "commit": "c" * 40,
            "content_sha256": "d" * 64,
        },
        "watch_mode": None,
    }
    runtime = mock.Mock()
    runtime.store.find_event_by_command_id.return_value = None
    grounding = mock.Mock()
    grounding.observe.return_value = frame["observed_grounding"]
    binding_provider = mock.Mock(return_value=binding)
    source_provider = mock.Mock(return_value=source)
    sink_receipt = {"dispatched": False, "intent_id": "auto-test"}

    async def exercise() -> dict[str, object]:
        with mock.patch.object(executive_ceo_ingress, "_submit", new=mock.AsyncMock(return_value=sink_receipt)) as sink:
            result = await executive_ceo_ingress.handle_frame(
                frame, runtime=runtime, grounding_provider=grounding,
                workspace_root="/tmp", service_state="READY", ceo_ingress_armed=True,
                strict_v2_admission=True,
                execution_binding_provider=binding_provider,
                dialogue_source_provider=source_provider,
            )
            assert sink.await_count == 1
            kwargs = sink.await_args.kwargs
            assert kwargs["execution_binding"] == binding
            observed_source = kwargs["dialogue_source"]
            assert observed_source.to_dict() == source_provider.return_value
            return result

    result = asyncio.run(exercise())
    assert result == sink_receipt
    binding_provider.assert_called_once_with()
    source_provider.assert_called()
    assert "execution_binding" not in frame
    assert "dialogue_source" not in frame

    with pytest.raises(executive_ceo_ingress.CeoIngressError) as error:
        asyncio.run(executive_ceo_ingress.handle_frame(
            frame, runtime=runtime, grounding_provider=grounding,
            workspace_root="/tmp", service_state="READY", ceo_ingress_armed=True,
            strict_v2_admission=True, execution_binding_provider=None,
            dialogue_source_provider=source_provider,
        ))
    assert error.value.code == "backend_unavailable"


@pytest.mark.parametrize("name", FORBIDDEN_HOST_OWNED_NAMES)
def test_d4_v2_rejects_forbidden_top_level_authority(name: str) -> None:
    frame = _frame(**{name: "forbidden"})
    with pytest.raises(executive_ceo_ingress.CeoIngressError):
        executive_ceo_ingress._exact_top_keys(frame, "submit v2 frame", frozenset({"schema", "request_ref", "observed_grounding", "request"}))
    with pytest.raises(executive_ceo_ingress.CeoIngressError) as error:
        asyncio.run(executive_ceo_ingress.handle_frame(frame, runtime=object(), grounding_provider=object(), workspace_root="/tmp", service_state="READY", ceo_ingress_armed=True))
    assert error.value.code == "invalid_input"


def test_d4_launcher_parser_has_no_forbidden_options() -> None:
    parser = launcher._parser()
    options = {option for action in parser._actions for option in action.option_strings}
    normalized = {option.lstrip("-").replace("-", "_") for option in options}
    assert normalized.isdisjoint(FORBIDDEN_HOST_OWNED_NAMES)


def test_d7_ast_fence_and_dry_run_does_not_connect() -> None:
    sources = (
        Path(__file__).parents[1] / "scripts" / "chairman_submit_ceo_intent_v2.py",
        Path(__file__).parents[1] / "ops" / "executive_os" / "submit_arm_receipt.py",
    )
    banned_imports = {
        "subprocess", "control_plane.executive_worker_broker",
        "control_plane.worker_adapter", "control_plane.codex_worker",
        "control_plane.codex_provider_realm", "control_plane.executive_supervisor",
        "urllib", "http", "requests", "socket",
    }
    banned_calls = {"Popen", "claim_job", "dispatch", "spawn"}
    for source in sources:
        tree = ast.parse(source.read_text(encoding="utf-8"))
        imports = {
            alias.name for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        }
        assert not any(name == banned or name.startswith(banned + ".") for name in imports for banned in banned_imports)
        assert not any(
            isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id in banned_calls for node in ast.walk(tree)
        )
    with mock.patch.object(launcher.asyncio, "open_unix_connection") as connect:
        assert launcher.main(["--socket", "/tmp/ingress.sock", "--request-ref", "W1H2-REQUEST-1", "--objective", "test", "--workstream", "WS-1", "--dry-run"]) == 0
        connect.assert_not_called()


def test_d8_template_topology_and_ingress_socket_only(tmp_path: Path) -> None:
    template = Path(__file__).parents[1] / "ops" / "executive_os" / "control.json.template"
    value = json.loads(template.read_text(encoding="utf-8"))
    assert value["allowed_peer_uids"] == [450, 501]
    assert value["ceo_ingress_peer_uid"] == 452
    assert value["ceo_ingress_app_peer_uid"] == 458
    config = tmp_path / "control.json"
    config.write_text(json.dumps({"ceo_ingress_socket_path": "/tmp/ingress.sock", "control_socket_path": "/tmp/operator.sock"}), encoding="utf-8")
    try:
        assert launcher._socket_path(mock.Mock(socket=None, config=config)) == Path("/tmp/ingress.sock")
        with pytest.raises(ValueError, match="Operator control socket"):
            launcher._socket_path(mock.Mock(socket=Path("/var/run/mastermind-executive/control.sock"), config=None))
        config.write_text(json.dumps({"ceo_ingress_socket_path": "/tmp/operator.sock", "control_socket_path": "/tmp/operator.sock"}), encoding="utf-8")
        with pytest.raises(ValueError, match="must differ"):
            launcher._socket_path(mock.Mock(socket=None, config=config))
    finally:
        config.unlink(missing_ok=True)

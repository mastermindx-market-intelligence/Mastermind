from __future__ import annotations

import ast
import asyncio
import json
from pathlib import Path
from unittest import mock

import pytest

from control_plane import executive_ceo_ingress
from scripts import chairman_submit_ceo_intent_v2 as launcher


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
    with mock.patch.object(executive_ceo_ingress.ceo_intent, "submit_intent") as sink:
        for state, armed in (("READY", False), ("DEGRADED", True)):
            with pytest.raises(executive_ceo_ingress.CeoIngressError) as error:
                asyncio.run(executive_ceo_ingress.handle_frame(
                    {"schema": executive_ceo_ingress.SUBMIT_SCHEMA_V2},
                    runtime=object(), grounding_provider=object(), workspace_root="/tmp",
                    service_state=state, ceo_ingress_armed=armed,
                ))
            assert error.value.code == "ingress_unavailable"
        sink.assert_not_called()


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


@pytest.mark.parametrize("name", ("provider", "provider_home", "credential_home", "uid", "gid", "worker_id", "session_id", "authority", "execution_binding", "dialogue_source"))
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
    assert not any(option.lstrip("-") in {"provider", "credential_home", "uid", "gid", "authority"} for option in options)


def test_d7_ast_fence_and_dry_run_does_not_connect() -> None:
    source = Path(__file__).parents[1] / "scripts" / "chairman_submit_ceo_intent_v2.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    imports = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    assert "subprocess" not in imports and "socket" not in imports
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
    finally:
        config.unlink(missing_ok=True)

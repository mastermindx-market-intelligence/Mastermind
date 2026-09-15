from __future__ import annotations

import asyncio
from unittest import mock
from pathlib import Path

import pytest

from control_plane import executive_service
from control_plane.executive_service import ExecutiveControlService, ServiceConfig


def _service(tmp_path: Path, socket_path: Path, *, armed: bool) -> ExecutiveControlService:
    return ExecutiveControlService(
        ServiceConfig(
            runtime_root=tmp_path / "runtime",
            socket_path=socket_path,
            proof_source_repository=tmp_path / "source",
            proof_workspace_root=tmp_path / "workspaces",
            proof_base_sha="a" * 40,
            ceo_submit_armed=armed,
        )
    )


def _request() -> dict[str, object]:
    return {
        "version": executive_service.CONTROL_PROTOCOL_VERSION,
        "command": "submit-ceo-intent",
        "args": {"intent": {"intent_id": "test-intent"}},
    }


def test_d1_production_submit_refused_unarmed_and_sink_not_called(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = _service(
        tmp_path,
        executive_service._PRODUCTION_CONTROL_SOCKET,
        armed=False,
    )
    service.runtime = object()
    with mock.patch.object(executive_service.ceo_intent, "submit_intent") as sink:
        with pytest.raises(executive_service._CeoSubmitUnarmedError) as raised:
            asyncio.run(service._dispatch_request(_request()))

        sink.assert_not_called()

    assert raised.value.code == "ceo_submit_unarmed"
    assert str(raised.value) == "CEO intent submission is not armed"


def test_d2_production_submit_reaches_existing_handler_when_armed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = _service(
        tmp_path,
        executive_service._PRODUCTION_CONTROL_SOCKET,
        armed=True,
    )
    service.runtime = object()
    with mock.patch.object(service, "_submit_service_intent", return_value={"accepted": True}) as handler:
        result = asyncio.run(service._dispatch_request(_request()))
        handler.assert_called_once_with({"intent_id": "test-intent"})

    assert result == {"accepted": True}


def test_d3_nonproduction_submit_is_unchanged_when_unarmed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = _service(tmp_path, tmp_path / "temporary.sock", armed=False)
    service.runtime = object()
    with mock.patch.object(service, "_submit_service_intent", return_value={"accepted": True}) as handler:
        result = asyncio.run(service._dispatch_request(_request()))
        handler.assert_called_once_with({"intent_id": "test-intent"})

    assert result == {"accepted": True}


def test_production_socket_predicate_resolves_both_sides(tmp_path: Path) -> None:
    service = _service(
        tmp_path,
        executive_service._PRODUCTION_CONTROL_SOCKET,
        armed=False,
    )
    assert service._is_production_control_socket() is True
    other = _service(tmp_path, tmp_path / "temporary.sock", armed=False)
    assert other._is_production_control_socket() is False

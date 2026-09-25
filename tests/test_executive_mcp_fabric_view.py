"""Executive MCP composition for the canonical Fabric job view."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from control_plane import fabric_job_view
from integrations.executive_mcp.adapter import ExecutiveMcpGateway, GatewayConfig

from integrations.executive_mcp.schemas import (
    SCHEMA_SNAPSHOT_SHA256,
    GatewayError,
    ServerMode,
    schema_snapshot_sha256,
    tool_names,
)
from integrations.executive_mcp.web_ceo import (
    WEB_CEO_SCHEMA_SNAPSHOT_SHA256,
    WebCeoExecutiveMcpGateway,
    validate_web_ceo_tool_arguments,
    web_ceo_schema_snapshot_sha256,
    web_ceo_tool_names,
    web_ceo_tool_spec,
)


def test_executive_fabric_is_read_only_and_advertised() -> None:
    spec = web_ceo_tool_spec("executive_fabric")

    assert spec.read_only is True
    assert "executive_fabric" not in tool_names()
    assert "executive_fabric" in web_ceo_tool_names()
    assert spec.input_schema["additionalProperties"] is False
    assert spec.input_schema["required"] == ["view"]


def test_executive_fabric_validates_closed_modes() -> None:
    assert validate_web_ceo_tool_arguments("executive_fabric", {"view": "roots"}) == {
        "view": "roots",
        "limit": 50,
    }
    assert validate_web_ceo_tool_arguments(
        "executive_fabric", {"view": "roots", "limit": 7}
    ) == {"view": "roots", "limit": 7}
    assert validate_web_ceo_tool_arguments(
        "executive_fabric", {"view": "root", "root_job_id": "JOB-7"}
    ) == {"view": "root", "root_job_id": "JOB-7"}


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"view": "roots", "root_job_id": "JOB-1"},
        {"view": "root"},
        {"view": "root", "root_job_id": "JOB-1", "limit": 5},
        {"view": "roots", "limit": 0},
        {"view": "roots", "limit": 51},
        {"view": "roots", "limit": True},
        {"view": "other"},
        {"view": "root", "root_job_id": "job-1"},
    ],
)
def test_executive_fabric_rejects_ambiguous_or_unbounded_inputs(
    payload: dict[str, object],
) -> None:
    with pytest.raises(GatewayError) as exc:
        validate_web_ceo_tool_arguments("executive_fabric", payload)

    assert exc.value.code == "invalid_input"


_FROZEN_NOW = "2026-09-17T22:00:00Z"


def _gateway(tmp_path: Path) -> tuple[WebCeoExecutiveMcpGateway, Path]:
    repo_root = tmp_path / "repo"
    runtime_root = tmp_path / "runtime"
    repo_root.mkdir()
    runtime_root.mkdir()
    gateway = WebCeoExecutiveMcpGateway(
        GatewayConfig(
            mode=ServerMode.READONLY,
            repo_root=repo_root,
            read_runtime_root=runtime_root,
            now=_FROZEN_NOW,
        ),
        clock=lambda: _FROZEN_NOW,
    )
    return gateway, runtime_root.resolve()


def _call(
    gateway: WebCeoExecutiveMcpGateway,
    arguments: dict[str, object],
) -> dict[str, Any]:
    return asyncio.run(gateway.call("executive_fabric", arguments))


def test_executive_fabric_lists_roots_through_canonical_projector(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    gateway, runtime_root = _gateway(tmp_path)
    calls: list[tuple[Path, int, object]] = []

    def fake_list_roots(
        observed_root: str | Path,
        *,
        limit: int,
        control_config_path: str | Path | None = None,
    ) -> dict[str, Any]:
        calls.append((Path(observed_root), limit, control_config_path))
        return {
            "schema": fabric_job_view.ROOT_LIST_SCHEMA,
            "generated_at": _FROZEN_NOW,
            "runtime": {
                "root": str(runtime_root),
                "db_present": True,
                "identity": None,
            },
            "roots": [
                {
                    "job_id": "JOB-1",
                    "status": "QUEUED",
                    "depth": 0,
                    "parent_job_id": None,
                    "orchestration_role": "root",
                }
            ],
            "count": 1,
            "total": 1,
            "truncated": False,
            "degraded": [f"observer read {runtime_root}/data/control_plane/executive.sqlite3"],
        }

    monkeypatch.setattr(fabric_job_view, "list_roots", fake_list_roots)

    envelope = _call(gateway, {"view": "roots", "limit": 7})

    assert envelope["ok"] is True
    assert envelope["data"]["schema"] == fabric_job_view.ROOT_LIST_SCHEMA
    assert envelope["data"]["roots"][0]["job_id"] == "JOB-1"
    assert envelope["data"]["runtime"]["root"] == "readonly:runtime"
    assert calls == [(runtime_root, 7, None)]
    serialized = json.dumps(envelope, sort_keys=True)
    assert str(runtime_root) not in serialized
    assert "readonly:runtime" in serialized


def test_executive_fabric_reads_one_root_through_canonical_projector(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    gateway, runtime_root = _gateway(tmp_path)
    calls: list[tuple[Path, str, object]] = []

    def fake_read_fabric_view(
        observed_root: str | Path,
        root_job_id: str,
        *,
        control_config_path: str | Path | None = None,
    ) -> dict[str, Any]:
        calls.append((Path(observed_root), root_job_id, control_config_path))
        return {
            "schema": fabric_job_view.SCHEMA,
            "generated_at": _FROZEN_NOW,
            "runtime": {
                "root": str(runtime_root),
                "db_present": True,
                "identity": None,
            },
            "armed": {},
            "root": {"job_id": root_job_id, "status": "RUNNING"},
            "children": [
                {
                    "job_id": "JOB-2",
                    "review": {"required": True, "verdict": "NOT_YET"},
                    "result": {"state": "NOT_STARTED", "summary": None},
                }
            ],
            "unjoined_job_count": 0,
            "unjoined_job_ids": [],
            "degraded": [f"runtime source {runtime_root}"],
            "missingness": [],
            "capability": {
                "state": "PARTIAL",
                "installed": False,
                "version": "v1",
                "detail": "fixture",
            },
        }

    monkeypatch.setattr(fabric_job_view, "read_fabric_view", fake_read_fabric_view)

    envelope = _call(gateway, {"view": "root", "root_job_id": "JOB-1"})

    assert envelope["ok"] is True
    assert envelope["data"]["schema"] == fabric_job_view.SCHEMA
    assert envelope["data"]["root"]["job_id"] == "JOB-1"
    assert envelope["data"]["children"][0]["review"]["verdict"] == "NOT_YET"
    assert envelope["data"]["children"][0]["result"]["state"] == "NOT_STARTED"
    assert calls == [(runtime_root, "JOB-1", None)]
    assert str(runtime_root) not in json.dumps(envelope, sort_keys=True)


def test_executive_fabric_projector_failure_is_typed_and_path_safe(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    gateway, runtime_root = _gateway(tmp_path)
    calls = 0

    def fail_list_roots(*_args: object, **_kwargs: object) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        raise OSError(f"cannot open {runtime_root}/data/control_plane/executive.sqlite3")

    monkeypatch.setattr(fabric_job_view, "list_roots", fail_list_roots)

    envelope = _call(gateway, {"view": "roots"})

    assert envelope["ok"] is False
    assert envelope["error"]["code"] == "backend_unavailable"
    assert calls == 1
    serialized = json.dumps(envelope, sort_keys=True)
    assert str(runtime_root) not in serialized
    assert "traceback" not in serialized.lower()


def test_legacy_and_web_ceo_schema_surfaces_are_both_pinned() -> None:
    assert tool_names() == (
        "executive_state",
        "executive_inbox",
        "executive_job",
        "ceo_intent_status",
        "submit_ceo_intent",
    )
    assert web_ceo_tool_names() == (
        "executive_state",
        "executive_inbox",
        "executive_job",
        "executive_fabric",
        "ceo_intent_status",
        "submit_ceo_intent",
    )
    assert schema_snapshot_sha256() == SCHEMA_SNAPSHOT_SHA256
    assert SCHEMA_SNAPSHOT_SHA256 == (
        "546b4345e30c24363a02ae3d4fc873e17559ffd569cde188a533fb628b284232"
    )
    assert web_ceo_schema_snapshot_sha256() == WEB_CEO_SCHEMA_SNAPSHOT_SHA256
    assert WEB_CEO_SCHEMA_SNAPSHOT_SHA256 == (
        "17e052ed734c2c4606094c49b0e9c057382a193fc181d595fc084da10809a5cd"
    )


def test_legacy_gateway_refuses_fabric_while_web_profile_serves_it(tmp_path: Path) -> None:
    repo = tmp_path / "legacy-repo"
    repo.mkdir()
    legacy = ExecutiveMcpGateway(
        GatewayConfig(mode=ServerMode.READONLY, repo_root=repo),
        clock=lambda: _FROZEN_NOW,
    )
    envelope = asyncio.run(legacy.call("executive_fabric", {"view": "roots"}))
    assert envelope["ok"] is False
    assert envelope["error"]["code"] == "not_found"
    assert envelope["server_version"] == "1.0.0"


def test_sdk_advertises_fabric_only_on_web_ceo_profile() -> None:
    pytest.importorskip("mcp")
    from integrations.executive_mcp.server import build_tools, build_web_ceo_tools

    legacy_tools = {tool.name: tool for tool in build_tools()}
    web_tools = {tool.name: tool for tool in build_web_ceo_tools()}
    assert "executive_fabric" not in legacy_tools
    tool = web_tools["executive_fabric"]
    assert set(web_tools) == set(web_ceo_tool_names())
    assert tool.annotations is not None
    assert tool.annotations.readOnlyHint is True
    assert tool.annotations.destructiveHint is False
    assert tool.inputSchema == web_ceo_tool_spec("executive_fabric").input_schema

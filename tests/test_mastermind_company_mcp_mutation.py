"""Adversarial change detectors for the bounded WP-2 authority surface."""
from __future__ import annotations

import ast
import asyncio
import copy
import hashlib
import json
from pathlib import Path

import pytest

from integrations.mastermind_company_mcp.adapter import (
    CompanyDialogueGateway,
    DialogueBinding,
)
from integrations.mastermind_company_mcp.schemas import (
    SCHEMA_SNAPSHOT_SHA256,
    TOOL_SPECS,
    GatewayError,
    canonical_json,
    schema_snapshot,
    validate_tool_arguments,
)

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "integrations" / "mastermind_company_mcp"


def _digest(value) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value["tools"].append(copy.deepcopy(value["tools"][0])),
        lambda value: value["tools"][0]["input_schema"]["properties"].update(
            job_id={"type": "string"}
        ),
        lambda value: value["tools"][1]["annotations"].update(
            destructiveHint=True
        ),
        lambda value: value["tools"][1].update(name="generic_slack_post"),
    ],
)
def test_schema_digest_kills_tool_authority_widening(mutation):
    value = schema_snapshot()
    assert _digest(value) == SCHEMA_SNAPSHOT_SHA256
    mutation(value)
    assert _digest(value) != SCHEMA_SNAPSHOT_SHA256


@pytest.mark.parametrize(
    "field",
    [
        "job_id",
        "attempt_id",
        "worker_id",
        "thread_ts",
        "channel",
        "display_name",
        "actor_ref",
        "seat",
        "operation_key",
        "watch_mode",
    ],
)
def test_model_identity_target_or_authority_mutations_are_refused(field):
    with pytest.raises(GatewayError) as exc_info:
        validate_tool_arguments("progress", {
            "stage": "testing",
            "completed": "Bounded check.",
            "next": "Continue.",
            field: "attacker-controlled",
        })
    assert exc_info.value.code == "INVALID_REQUEST"


def test_generic_slack_tool_mutation_is_not_dispatchable():
    assert [spec.name for spec in TOOL_SPECS] == [
        "read_thread",
        "ack",
        "progress",
        "blocked",
        "request_decision",
        "result",
    ]
    with pytest.raises(GatewayError) as exc_info:
        validate_tool_arguments("generic_slack_post", {})
    assert exc_info.value.code == "INVALID_REQUEST"


def test_worker_binding_cannot_widen_itself_to_ruling_or_lifecycle_messages():
    binding = DialogueBinding(
        actor_ref={
            "kind": "worker_attempt",
            "job_id": "JOB-001",
            "attempt_id": "ATT-001",
            "worker_id": "W-001",
        },
        work_ref="WS:CHAIRMAN-CONTROL-ROOM",
        commission_ref={
            "repository": "mastermindx-market-intelligence/Mastermind",
            "commit": "1" * 40,
            "path": "docs/superpowers/plans/company-dialogue-wp2.md",
            "content_sha256": "2" * 64,
        },
        session_ref="asd-session-wp2bounded01",
        operation_key="worker-presence-dialogue-wp2-20260829",
        watch_mode=None,
        applies_to={
            "kind": "executive_attempt",
            "job_id": "JOB-001",
            "attempt_id": "ATT-001",
            "worker_id": "W-001",
        },
        thread_ts="1787896128.625239",
        allowed_message_types=("RULING",),
    )

    class Resolver:
        def resolve(self):
            return binding

    calls = []

    async def service(*args):
        calls.append(args)
        return {"ok": True, "result": {}}

    gateway = CompanyDialogueGateway(
        Resolver(),
        socket_path=Path("/private/tmp/mastermind-agent-dialogue.sock"),
        service_call=service,
    )

    response = asyncio.run(gateway.call("ack", {}))

    assert response["error"]["code"] == "BINDING_UNAVAILABLE"
    assert calls == []


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    result: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            result.add(node.module)
    return result


def test_package_cannot_gain_persistence_credentials_processes_or_direct_slack():
    imports = {path.name: _imports(path) for path in PACKAGE.glob("*.py")}
    forbidden = {
        "sqlite3",
        "subprocess",
        "keyring",
        "slack_sdk",
        "requests",
        "httpx",
        "control_plane.executive_runtime",
        "control_plane.turn_watcher",
        "control_plane.wake",
    }
    for filename, modules in imports.items():
        assert not (modules & forbidden), filename
        mcp_modules = {name for name in modules if name == "mcp" or name.startswith("mcp.")}
        assert bool(mcp_modules) is (filename == "server.py")

    server_source = (PACKAGE / "server.py").read_text(encoding="utf-8")
    for widening in (
        "add_tool(",
        "remove_tool(",
        "register_tool(",
        "list_resources(",
        "read_resource(",
        "list_prompts(",
        "get_prompt(",
        "create_message(",
        "list_roots(",
    ):
        assert widening not in server_source


def test_production_policy_remains_free_of_fake_company_dialogue_binding():
    raw = json.loads(
        (ROOT / "config" / "executive_agent_capabilities.json").read_text(
            encoding="utf-8"
        )
    )
    rendered = json.dumps(raw, sort_keys=True)
    assert raw["production_armed"] is False
    assert "mastermind-company-dialogue" not in rendered
    assert "mastermindCompanyDialogue" not in rendered
    assert "company-dialogue.test.invalid" not in rendered

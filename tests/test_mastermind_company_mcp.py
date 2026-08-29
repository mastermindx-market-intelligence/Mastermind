from __future__ import annotations

import asyncio
import ast
import copy
import json
import subprocess
import sys
from pathlib import Path
from uuid import UUID

import pytest

from integrations.mastermind_company_mcp.adapter import (
    CompanyDialogueGateway,
    DialogueBinding,
)
from integrations.mastermind_company_mcp.schemas import (
    ERROR_CODES,
    RESULT_SCHEMA,
    SCHEMA_SNAPSHOT_SHA256,
    SERVER_NAME,
    SERVER_VERSION,
    TOOL_SCHEMA_DIGEST,
    TOOL_SPECS,
    GatewayError,
    error_envelope,
    schema_snapshot_sha256,
    tool_schema_digest,
    validate_tool_arguments,
)
from integrations.slack_agent_dialogue.service import DialogueServiceError


EXPECTED_TOOL_NAMES = [
    "read_thread",
    "ack",
    "progress",
    "blocked",
    "request_decision",
    "result",
]

EXPECTED_INPUT_KEYS = {
    "read_thread": set(),
    "ack": {"evidence_refs"},
    "progress": {"stage", "completed", "next", "evidence_refs"},
    "blocked": {
        "blocker_code",
        "reason",
        "needed_from",
        "work_paused",
        "evidence_refs",
    },
    "request_decision": {
        "question",
        "outcome_impact",
        "options",
        "recommendation",
        "work_paused",
        "evidence_refs",
    },
    "result": {"status", "result", "evidence_refs"},
}

FORBIDDEN_INPUT_NAMES = {
    "job_id",
    "attempt_id",
    "worker_id",
    "seat",
    "actor_ref",
    "work_ref",
    "workstream",
    "commission_ref",
    "session_ref",
    "channel",
    "channel_id",
    "thread",
    "thread_ts",
    "username",
    "display_name",
    "authority_class",
    "provider",
    "account",
    "host",
    "runtime_binding",
    "operation_key",
    "watch_mode",
    "token",
    "secret",
}


def _walk_schema(value):
    if isinstance(value, dict):
        yield value
        for nested in value.values():
            yield from _walk_schema(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _walk_schema(nested)


def test_tool_census_and_annotations_are_exact():
    assert SERVER_NAME == "mastermind-company-dialogue"
    assert SERVER_VERSION == "1.0.0"
    assert [spec.name for spec in TOOL_SPECS] == EXPECTED_TOOL_NAMES
    assert [spec.read_only for spec in TOOL_SPECS] == [True, False, False, False, False, False]
    for spec in TOOL_SPECS:
        assert spec.annotations["destructiveHint"] is False
        assert spec.annotations["openWorldHint"] is False
        assert spec.annotations["readOnlyHint"] is spec.read_only
        assert "Slack" not in spec.name


def test_tool_inputs_are_closed_and_contain_no_privileged_binding_fields():
    for spec in TOOL_SPECS:
        schema = spec.input_schema
        assert schema["type"] == "object"
        assert schema["additionalProperties"] is False
        assert set(schema["properties"]) == EXPECTED_INPUT_KEYS[spec.name]
        for node in _walk_schema(schema):
            assert node.get("additionalProperties") is not True
            assert not (set(node) & FORBIDDEN_INPUT_NAMES)
            properties = node.get("properties")
            if isinstance(properties, dict):
                assert not (set(properties) & FORBIDDEN_INPUT_NAMES)


@pytest.mark.parametrize(
    ("tool", "arguments", "expected"),
    [
        ("read_thread", {}, {}),
        ("ack", {}, {"evidence_refs": []}),
        (
            "progress",
            {"stage": "implementation", "completed": "Schema frozen.", "next": "Build adapter."},
            {
                "stage": "implementation",
                "completed": "Schema frozen.",
                "next": "Build adapter.",
                "evidence_refs": [],
            },
        ),
        (
            "blocked",
            {
                "blocker_code": "AUTHORITY_REQUIRED",
                "reason": "A bounded ruling is required.",
                "needed_from": "sol",
                "work_paused": True,
            },
            {
                "blocker_code": "AUTHORITY_REQUIRED",
                "reason": "A bounded ruling is required.",
                "needed_from": "sol",
                "work_paused": True,
                "evidence_refs": [],
            },
        ),
        (
            "request_decision",
            {
                "question": "Which bounded option should proceed?",
                "outcome_impact": "The implementation remains paused.",
                "options": [
                    {
                        "id": "opt-proceed",
                        "summary": "Proceed within scope.",
                        "consequence": "Complete the bounded carrier.",
                        "disposition": "CONTINUE",
                        "authority_effect": "NONE",
                    }
                ],
                "recommendation": "opt-proceed",
                "work_paused": True,
            },
            {
                "question": "Which bounded option should proceed?",
                "outcome_impact": "The implementation remains paused.",
                "options": [
                    {
                        "id": "opt-proceed",
                        "summary": "Proceed within scope.",
                        "consequence": "Complete the bounded carrier.",
                        "disposition": "CONTINUE",
                        "authority_effect": "NONE",
                    }
                ],
                "recommendation": "opt-proceed",
                "work_paused": True,
                "evidence_refs": [],
            },
        ),
        ("result", {"status": "PASS", "result": "Bounded outcome returned."}, {"status": "PASS", "result": "Bounded outcome returned.", "evidence_refs": []}),
    ],
)
def test_tool_argument_validation_normalizes_only_semantic_inputs(tool, arguments, expected):
    assert validate_tool_arguments(tool, arguments) == expected


@pytest.mark.parametrize("field", sorted(FORBIDDEN_INPUT_NAMES))
def test_caller_cannot_supply_binding_or_authority_fields(field):
    with pytest.raises(GatewayError) as exc_info:
        validate_tool_arguments("ack", {field: "attacker-controlled"})
    assert exc_info.value.code == "INVALID_REQUEST"


def test_schema_snapshot_is_literal_and_drift_sensitive():
    assert SCHEMA_SNAPSHOT_SHA256 == schema_snapshot_sha256()
    assert TOOL_SCHEMA_DIGEST == tool_schema_digest()
    assert SCHEMA_SNAPSHOT_SHA256 != "0" * 64
    snapshot = {
        "server_name": SERVER_NAME,
        "server_version": SERVER_VERSION,
        "result_schema": RESULT_SCHEMA,
        "errors": sorted(ERROR_CODES),
        "tools": [
            {
                "name": spec.name,
                "description": spec.description,
                "input_schema": copy.deepcopy(spec.input_schema),
                "output_description": spec.output_description,
                "annotations": spec.annotations,
                "read_only": spec.read_only,
            }
            for spec in TOOL_SPECS
        ],
    }
    snapshot["tools"][0]["input_schema"]["additionalProperties"] = True
    altered = __import__("hashlib").sha256(
        json.dumps(snapshot, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()
    assert altered != SCHEMA_SNAPSHOT_SHA256


def test_error_envelope_is_fixed_bounded_and_never_echoes_secret_shaped_text():
    envelope = error_envelope(
        "ack",
        code="SERVICE_UNAVAILABLE",
        message="upstream xoxb-not-a-real-token-but-secret-shaped-value failed " + "x" * 2000,
        detail_code="SERVICE_UNAVAILABLE",
    )
    rendered = json.dumps(envelope, sort_keys=True)
    assert envelope == {
        "schema": RESULT_SCHEMA,
        "tool": "ack",
        "ok": False,
        "server_version": SERVER_VERSION,
        "data": None,
        "error": {
            "code": "SERVICE_UNAVAILABLE",
            "message": "SERVICE_UNAVAILABLE",
            "detail_code": "SERVICE_UNAVAILABLE",
        },
    }
    assert "xoxb-" not in rendered
    assert len(rendered.encode()) < 1024


class _StaticResolver:
    def __init__(self, binding: DialogueBinding) -> None:
        self.binding = binding
        self.calls = 0

    def resolve(self) -> DialogueBinding:
        self.calls += 1
        return self.binding


class _FailingResolver:
    def __init__(self, message: str = "binding xoxb-not-a-real-secret-shaped-token missing") -> None:
        self.message = message
        self.calls = 0

    def resolve(self) -> DialogueBinding:
        self.calls += 1
        raise RuntimeError(self.message)


class _RecordingService:
    def __init__(self, response=None, *, error: Exception | None = None) -> None:
        self.response = response or {"ok": True, "result": {"messages": []}}
        self.error = error
        self.calls: list[tuple[Path, dict]] = []

    async def __call__(self, socket_path: Path, request: dict) -> dict:
        self.calls.append((socket_path, copy.deepcopy(request)))
        if self.error is not None:
            raise self.error
        return copy.deepcopy(self.response)


def _binding(**overrides) -> DialogueBinding:
    values = {
        "actor_ref": {
            "kind": "worker_attempt",
            "job_id": "JOB-001",
            "attempt_id": "ATT-001",
            "worker_id": "W-001",
        },
        "work_ref": "WS:CHAIRMAN-CONTROL-ROOM",
        "commission_ref": {
            "repository": "mastermindx-market-intelligence/Mastermind",
            "commit": "1" * 40,
            "path": "docs/superpowers/plans/company-dialogue-wp2.md",
            "content_sha256": "2" * 64,
        },
        "session_ref": "asd-session-wp2bounded01",
        "operation_key": "worker-presence-dialogue-wp2-20260829",
        "watch_mode": None,
        "applies_to": {
            "kind": "executive_attempt",
            "job_id": "JOB-001",
            "attempt_id": "ATT-001",
            "worker_id": "W-001",
        },
        "thread_ts": "1787896128.625239",
        "allowed_message_types": (
            "ACK",
            "PROGRESS",
            "BLOCKED",
            "DECISION_REQUEST",
            "RESULT",
        ),
    }
    values.update(overrides)
    return DialogueBinding(**values)


def _gateway(binding: DialogueBinding | None = None, *, service=None, resolver=None):
    recording = service or _RecordingService()
    binding_resolver = resolver or _StaticResolver(binding or _binding())
    gateway = CompanyDialogueGateway(
        binding_resolver,
        socket_path=Path("/private/tmp/mastermind-agent-dialogue.sock"),
        service_call=recording,
        uuid_source=lambda: UUID("00000000-0000-4000-8000-000000000001"),
        utc_now=lambda: "2026-08-29T01:00:00Z",
    )
    return gateway, binding_resolver, recording


def _run(coroutine):
    return asyncio.run(coroutine)


def test_read_thread_propagates_exact_resolver_owned_context_including_wp1_parent_fields():
    binding = _binding(operation_key="trusted-operation-key-20260829", watch_mode="turn_watch_v1")
    gateway, resolver, service = _gateway(binding)

    response = _run(gateway.call("read_thread", {}))

    assert response["ok"] is True
    assert resolver.calls == 1
    assert len(service.calls) == 1
    socket_path, request = service.calls[0]
    assert socket_path == Path("/private/tmp/mastermind-agent-dialogue.sock")
    assert request == {
        "version": "mastermind.agent_dialogue_control.v2",
        "operation": "read_thread",
        "args": {
            "context": {
                "work_ref": binding.work_ref,
                "commission_ref": binding.commission_ref,
                "session_ref": binding.session_ref,
                "operation_key": "trusted-operation-key-20260829",
                "watch_mode": "turn_watch_v1",
                "actor_ref": binding.actor_ref,
                "applies_to": binding.applies_to,
            },
            "thread_ts": binding.thread_ts,
        },
    }


def test_semantic_payload_cannot_change_resolver_owned_identity_or_thread():
    binding = _binding()
    gateway, _resolver, service = _gateway(binding)

    response = _run(gateway.call(
        "progress",
        {
            "stage": "implementation",
            "completed": "Caller text mentions another thread 1777777777.111111.",
            "next": "Continue only the trusted operation.",
        },
    ))

    assert response["ok"] is True
    assert len(service.calls) == 1
    request = service.calls[0][1]
    assert request["args"]["thread_ts"] == binding.thread_ts
    assert request["args"]["context"]["actor_ref"] == binding.actor_ref
    assert request["args"]["context"]["operation_key"] == binding.operation_key
    message = request["args"]["message"]
    assert message["message_type"] == "PROGRESS"
    assert message["actor_ref"] == binding.actor_ref
    assert message["work_ref"] == binding.work_ref
    assert message["session_ref"] == binding.session_ref


@pytest.mark.parametrize(
    ("tool", "arguments", "message_type", "requires_response", "summary"),
    [
        ("ack", {}, "ACK", False, "Bounded dialogue context acknowledged."),
        (
            "progress",
            {"stage": "testing", "completed": "Focused checks pass.", "next": "Verify scope."},
            "PROGRESS",
            False,
            "Progress: testing.",
        ),
        (
            "blocked",
            {
                "blocker_code": "AUTHORITY_REQUIRED",
                "reason": "A bounded decision is required.",
                "needed_from": "sol",
                "work_paused": True,
            },
            "BLOCKED",
            True,
            "Blocked: AUTHORITY_REQUIRED.",
        ),
        (
            "request_decision",
            {
                "question": "Which bounded option should proceed?",
                "outcome_impact": "The implementation remains paused.",
                "options": [
                    {
                        "id": "opt-proceed",
                        "summary": "Proceed within scope.",
                        "consequence": "Complete the bounded carrier.",
                        "disposition": "CONTINUE",
                        "authority_effect": "NONE",
                    }
                ],
                "recommendation": "opt-proceed",
                "work_paused": True,
            },
            "DECISION_REQUEST",
            True,
            "Decision requested.",
        ),
        (
            "result",
            {"status": "PASS", "result": "Bounded result returned."},
            "RESULT",
            False,
            "Result: PASS.",
        ),
    ],
)
def test_each_emitting_tool_builds_one_valid_wp1_message(
    tool, arguments, message_type, requires_response, summary
):
    gateway, _resolver, service = _gateway()

    response = _run(gateway.call(tool, arguments))

    assert response["ok"] is True
    assert len(service.calls) == 1
    request = service.calls[0][1]
    assert request["operation"] == "send_message"
    assert request["args"]["message"]["message_type"] == message_type
    assert request["args"]["message"]["requires_response"] is requires_response
    assert request["args"]["message"]["summary"] == summary
    assert request["args"]["message"]["message_key"] == "asd-mcp-00000000000040008000000000000001"
    assert request["args"]["message"]["created_at"] == "2026-08-29T01:00:00Z"


def test_unavailable_or_malformed_binding_fails_closed_without_transport_call():
    resolver = _FailingResolver()
    gateway, _resolver, service = _gateway(resolver=resolver)

    unavailable = _run(gateway.call("ack", {}))

    assert unavailable["error"] == {
        "code": "BINDING_UNAVAILABLE",
        "message": "BINDING_UNAVAILABLE",
        "detail_code": "BINDING_UNAVAILABLE",
    }
    assert service.calls == []
    malformed_gateway, _resolver, malformed_service = _gateway(
        _binding(operation_key="bad")
    )
    malformed = _run(malformed_gateway.call("ack", {}))
    assert malformed["error"]["code"] == "BINDING_UNAVAILABLE"
    assert malformed_service.calls == []


def test_disallowed_message_type_fails_closed_without_transport_call():
    gateway, _resolver, service = _gateway(_binding(allowed_message_types=("PROGRESS",)))

    response = _run(gateway.call("ack", {}))

    assert response["error"]["code"] == "DIALOGUE_REFUSED"
    assert response["error"]["detail_code"] == "MESSAGE_TYPE_DENIED"
    assert service.calls == []


def test_send_effect_unknown_is_returned_once_without_retry():
    service = _RecordingService(
        response={"ok": False, "error": {"code": "SEND_EFFECT_UNKNOWN"}}
    )
    gateway, _resolver, service = _gateway(service=service)

    response = _run(gateway.call("ack", {}))

    assert response["error"] == {
        "code": "DIALOGUE_REFUSED",
        "message": "DIALOGUE_REFUSED",
        "detail_code": "SEND_EFFECT_UNKNOWN",
    }
    assert response["data"] == {
        "message_key": "asd-mcp-00000000000040008000000000000001"
    }
    assert len(service.calls) == 1


def test_raised_send_effect_unknown_preserves_message_key_without_retry():
    service = _RecordingService(error=DialogueServiceError("SEND_EFFECT_UNKNOWN"))
    gateway, _resolver, service = _gateway(service=service)

    response = _run(gateway.call("ack", {}))

    assert response["error"] == {
        "code": "DIALOGUE_REFUSED",
        "message": "DIALOGUE_REFUSED",
        "detail_code": "SEND_EFFECT_UNKNOWN",
    }
    assert response["data"] == {
        "message_key": "asd-mcp-00000000000040008000000000000001"
    }
    assert len(service.calls) == 1


def test_unrecognized_downstream_error_code_is_not_reflected_to_caller():
    service = _RecordingService(
        response={"ok": False, "error": {"code": "ROOT_ACCESS_GRANTED"}}
    )
    gateway, _resolver, service = _gateway(service=service)

    response = _run(gateway.call("ack", {}))

    assert response["error"]["code"] == "INTERNAL_ERROR"
    assert response["error"]["message"] == "INTERNAL_ERROR"
    assert "ROOT_ACCESS_GRANTED" not in json.dumps(response)
    assert len(service.calls) == 1


def test_exact_executive_surface_binding_is_resolver_owned_and_supported():
    actor_ref = {
        "kind": "executive_surface",
        "seat": "ceo",
        "reasoning_surface": "codex",
    }
    applies_to = {
        "kind": "repository",
        "repository": "mastermindx-market-intelligence/Mastermind",
        "head_sha": "3" * 40,
        "pr": "mastermindx-market-intelligence/Mastermind#201",
    }
    binding = _binding(actor_ref=actor_ref, applies_to=applies_to)
    gateway, _resolver, service = _gateway(binding)

    response = _run(gateway.call("result", {"status": "PASS", "result": "Reviewed."}))

    assert response["ok"] is True
    assert len(service.calls) == 1
    request = service.calls[0][1]
    assert request["args"]["context"]["actor_ref"] == actor_ref
    assert request["args"]["context"]["applies_to"] == applies_to
    assert request["args"]["message"]["actor_ref"] == actor_ref


def test_transport_exception_is_bounded_secret_safe_and_never_retried():
    service = _RecordingService(error=RuntimeError("failed bearer secretshapedvalue1234567890"))
    gateway, _resolver, service = _gateway(service=service)

    response = _run(gateway.call("read_thread", {}))

    assert response["error"] == {
        "code": "SERVICE_UNAVAILABLE",
        "message": "SERVICE_UNAVAILABLE",
        "detail_code": "SERVICE_UNAVAILABLE",
    }
    assert "secretshaped" not in json.dumps(response)
    assert len(service.calls) == 1


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def test_sdk_and_runtime_dependency_boundaries_are_exact():
    root = Path(__file__).resolve().parent.parent
    package = root / "integrations" / "mastermind_company_mcp"
    imports = {path.name: _imported_modules(path) for path in sorted(package.glob("*.py"))}
    assert set(imports) == {"__init__.py", "adapter.py", "schemas.py", "server.py"}
    for filename, modules in imports.items():
        mcp_imports = {module for module in modules if module == "mcp" or module.startswith("mcp.")}
        assert bool(mcp_imports) is (filename == "server.py")
    adapter_imports = imports["adapter.py"]
    forbidden_roots = {
        "slack_sdk",
        "sqlite3",
        "subprocess",
        "keyring",
        "control_plane.executive_runtime",
        "control_plane.turn_watcher",
        "control_plane.wake",
    }
    assert not (adapter_imports & forbidden_roots)
    for path in sorted((root / "control_plane").glob("*.py")):
        assert not any(
            module.startswith("integrations.mastermind_company_mcp")
            for module in _imported_modules(path)
        )


def test_schemas_and_adapter_import_when_mcp_sdk_is_blocked():
    root = Path(__file__).resolve().parent.parent
    script = """
import builtins

original_import = builtins.__import__

def guarded_import(name, *args, **kwargs):
    if name == "mcp" or name.startswith("mcp."):
        raise ImportError("mcp blocked by WP-2 isolation probe")
    return original_import(name, *args, **kwargs)

builtins.__import__ = guarded_import
import integrations.mastermind_company_mcp.schemas
import integrations.mastermind_company_mcp.adapter
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr


def test_mcp_server_advertises_only_the_frozen_six_tools():
    pytest.importorskip("mcp")
    from mcp.server.lowlevel import NotificationOptions

    from integrations.mastermind_company_mcp.server import build_mcp_server, build_tools

    tools = build_tools()
    assert [tool.name for tool in tools] == EXPECTED_TOOL_NAMES
    for tool, spec in zip(tools, TOOL_SPECS, strict=True):
        assert tool.description == spec.description
        assert tool.inputSchema == spec.input_schema
        assert tool.annotations.readOnlyHint is spec.read_only
        assert tool.annotations.destructiveHint is False
        assert tool.annotations.openWorldHint is False

    gateway, _resolver, _service = _gateway()
    server = build_mcp_server(gateway)
    capabilities = server.get_capabilities(
        notification_options=NotificationOptions(), experimental_capabilities={}
    )
    assert capabilities.tools is not None
    assert capabilities.resources is None
    assert capabilities.prompts is None
    assert capabilities.completions is None
    assert {handler.__name__ for handler in server.request_handlers} == {
        "PingRequest",
        "ListToolsRequest",
        "CallToolRequest",
    }
    assert server.notification_handlers == {}


def test_mcp_server_calls_gateway_exactly_once_and_returns_one_bounded_text_result():
    pytest.importorskip("mcp")
    from mcp import types as mcp_types

    from integrations.mastermind_company_mcp.server import build_mcp_server

    class Gateway:
        def __init__(self) -> None:
            self.calls = []

        async def call(self, name, arguments):
            self.calls.append((name, copy.deepcopy(arguments)))
            return {"schema": RESULT_SCHEMA, "tool": name, "ok": True}

    gateway = Gateway()
    server = build_mcp_server(gateway)
    handler = server.request_handlers[mcp_types.CallToolRequest]
    request = mcp_types.CallToolRequest(
        params=mcp_types.CallToolRequestParams(
            name="ack",
            arguments={"evidence_refs": []},
        )
    )

    response = _run(handler(request))

    assert gateway.calls == [("ack", {"evidence_refs": []})]
    document = response.model_dump(mode="json", by_alias=True)
    content = document["content"]
    assert len(content) == 1
    assert content[0]["type"] == "text"
    assert json.loads(content[0]["text"]) == {
        "ok": True,
        "schema": RESULT_SCHEMA,
        "tool": "ack",
    }

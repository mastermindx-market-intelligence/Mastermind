from __future__ import annotations

import ast
import asyncio
import copy
import inspect
from pathlib import Path

import pytest

from integrations.mastermind_company_mcp.adapter import DialogueBinding
from integrations.mastermind_company_mcp.principal_adapter import (
    PrincipalCommitFenceReceipt,
    PrincipalCommitIntent,
    PrincipalCompanyDialogueGateway,
)
from integrations.mastermind_company_mcp.principal_schemas import (
    ERROR_CODES,
    PRINCIPAL_RESULT_SCHEMA,
    PRINCIPAL_SCHEMA_SNAPSHOT_SHA256,
    PRINCIPAL_SERVER_IDENTITY,
    PRINCIPAL_SERVER_NAME,
    PRINCIPAL_SERVER_VERSION,
    PRINCIPAL_TOOL_SCHEMA_DIGEST,
    PRINCIPAL_TOOL_SPECS,
    PrincipalGatewayError,
    principal_schema_snapshot_sha256,
    principal_tool_schema_digest,
    validate_principal_tool_arguments,
)
from integrations.mastermind_company_mcp.schemas import (
    SCHEMA_SNAPSHOT_SHA256 as WORKER_SCHEMA_DIGEST,
    TOOL_SCHEMA_DIGEST as WORKER_TOOL_DIGEST,
    schema_snapshot_sha256 as worker_schema_digest,
    tool_schema_digest as worker_tool_digest,
)
from integrations.slack_agent_dialogue.contract import DialogueContractError
from integrations.slack_agent_dialogue.contract_v2 import build_message_v2
from integrations.slack_agent_dialogue.engine_v2 import (
    DialogueContextV2,
    DialogueEngineError,
    _adjudicate_reply_v2,
)
from integrations.slack_agent_dialogue.service import (
    EXACT_SEND_PROTOCOL,
    DialogueServiceError,
)


ROOT = Path(__file__).resolve().parents[1]
THREAD_TS = "1788000000.123456"
REPLY_KEY = "asd-result-12345678"
WORK_REF = "WS:CLAUDE-CAPABILITY-HARDENING"
SESSION_REF = "asd-session-claudeprincipal0001"
OPERATION_KEY = "claude-capability-hardening-h6-b1"
D0 = "0" * 64
D1 = "1" * 64
D2 = "2" * 64

EXPECTED_TOOLS = ["read_thread", "ruling", "continue", "stop"]
FORBIDDEN_INPUTS = {
    "actor_ref",
    "applies_to",
    "attempt_id",
    "authority_generation_digest",
    "canonical_ref",
    "capability_profile_digest",
    "channel",
    "channel_id",
    "job_id",
    "mission_authority_ref",
    "operation_key",
    "principal_binding_digest",
    "provider",
    "account",
    "host",
    "reasoning_surface",
    "reply_to_message_key",
    "root_job_id",
    "session_ref",
    "thread",
    "thread_ts",
    "worker_id",
    "work_ref",
}


def commission() -> dict[str, str]:
    return {
        "repository": "mastermindx-market-intelligence/Mastermind",
        "commit": "a" * 40,
        "path": "docs/CLAUDE_CAPABILITY_HARDENING_BUILD_HANDOFFS_2026-10-04.md",
        "content_sha256": "b" * 64,
    }


def principal_actor() -> dict[str, str]:
    return {
        "kind": "executive_principal",
        "seat": "coo",
        "reasoning_surface": "claude-agent-sdk",
        "principal_binding_digest": D0,
        "mission_authority_ref": "authority:claude-coo-current",
        "authority_generation_digest": D1,
        "capability_profile_digest": D2,
        "root_job_id": "JOB-100",
    }


def worker_actor() -> dict[str, str]:
    return {
        "kind": "worker_attempt",
        "job_id": "JOB-200",
        "attempt_id": "ATT-0123456789abcdef0123456789abcdef",
        "worker_id": "codex-worker-01",
    }


def applies_to() -> dict[str, str]:
    return {
        "kind": "executive_attempt",
        "job_id": "JOB-200",
        "attempt_id": "ATT-0123456789abcdef0123456789abcdef",
        "worker_id": "codex-worker-01",
    }


def binding(**changes) -> DialogueBinding:
    value = DialogueBinding(
        actor_ref=principal_actor(),
        work_ref=WORK_REF,
        commission_ref=commission(),
        session_ref=SESSION_REF,
        operation_key=OPERATION_KEY,
        watch_mode="turn_watch_v1",
        applies_to=applies_to(),
        thread_ts=THREAD_TS,
        allowed_message_types=("RULING", "CONTINUE", "STOP"),
        reply_to_message_key=REPLY_KEY,
    )
    return __import__("dataclasses").replace(value, **changes) if changes else value


class Resolver:
    def __init__(self, value: DialogueBinding | None = None):
        self.value = value or binding()

    def resolve(self) -> DialogueBinding:
        return self.value


class ExactService:
    """Small exact-send semantic fake; not a second transport implementation."""

    def __init__(self, *, effect_unknown: bool = False):
        self.effect_unknown = effect_unknown
        self.messages: dict[str, dict] = {}
        self.calls: list[dict] = []
        self.before_write_calls = 0

    async def __call__(self, path, request, **kwargs):
        self.calls.append(copy.deepcopy(request))
        if request["operation"] == "read_thread":
            assert kwargs == {}
            return {
                "ok": True,
                "result": {
                    "thread_ts": request["args"]["thread_ts"],
                    "messages": [],
                    "mutated_count": 0,
                },
            }

        assert request["operation"] == "send_message"
        assert request["args"]["send_protocol"] == EXACT_SEND_PROTOCOL
        message = request["args"]["message"]
        key = message["message_key"]
        existing = self.messages.get(key)
        if existing is not None:
            if existing["fingerprint"] != message["fingerprint"]:
                return {"ok": False, "error": {"code": "MESSAGE_KEY_CONFLICT"}}
            return {
                "ok": True,
                "result": {
                    "action": "DUPLICATE",
                    "message_key": key,
                    "fingerprint": message["fingerprint"],
                },
            }

        before_write = kwargs.get("before_write")
        assert callable(before_write)
        self.before_write_calls += 1
        marked = before_write()
        if inspect.isawaitable(marked):
            await marked
        if self.effect_unknown:
            raise DialogueServiceError("SEND_EFFECT_UNKNOWN")
        self.messages[key] = copy.deepcopy(message)
        return {
            "ok": True,
            "result": {
                "action": "CREATED",
                "message_key": key,
                "fingerprint": message["fingerprint"],
            },
        }


def gateway(
    service: ExactService,
    fences: list[PrincipalCommitIntent],
    *,
    resolver: Resolver | None = None,
    fence_error: bool = False,
) -> PrincipalCompanyDialogueGateway:
    async def before_commit(intent: PrincipalCommitIntent):
        fences.append(intent)
        if fence_error:
            raise RuntimeError("synthetic durable owner refusal")
        return PrincipalCommitFenceReceipt.for_intent(
            intent,
            durable_ref=f"event:{len(fences)}",
        )

    return PrincipalCompanyDialogueGateway(
        resolver or Resolver(),
        socket_path=Path("/private/tmp/mastermind-agent-dialogue.sock"),
        before_commit=before_commit,
        service_call=service,
        utc_now=lambda: "2026-10-05T06:00:00Z",
    )


def run(value):
    return asyncio.run(value)


def test_principal_schema_is_distinct_exact_and_worker_schema_does_not_rotate() -> None:
    assert PRINCIPAL_SERVER_NAME == "mastermind-company-dialogue-principal"
    assert PRINCIPAL_SERVER_IDENTITY == "mastermind-company-dialogue-principal-mcp"
    assert PRINCIPAL_SERVER_VERSION == "0.1.0"
    assert [spec.name for spec in PRINCIPAL_TOOL_SPECS] == EXPECTED_TOOLS
    assert [spec.read_only for spec in PRINCIPAL_TOOL_SPECS] == [
        True,
        False,
        False,
        False,
    ]
    assert PRINCIPAL_SCHEMA_SNAPSHOT_SHA256 == principal_schema_snapshot_sha256()
    assert PRINCIPAL_TOOL_SCHEMA_DIGEST == principal_tool_schema_digest()
    assert worker_schema_digest() == WORKER_SCHEMA_DIGEST
    assert worker_tool_digest() == WORKER_TOOL_DIGEST


def test_principal_inputs_are_closed_and_have_no_binding_or_placement_selectors() -> None:
    for spec in PRINCIPAL_TOOL_SPECS:
        schema = spec.input_schema
        assert schema["additionalProperties"] is False
        assert not (set(schema["properties"]) & FORBIDDEN_INPUTS)
    for field in sorted(FORBIDDEN_INPUTS):
        with pytest.raises(PrincipalGatewayError):
            validate_principal_tool_arguments("continue", {
                "instruction": "Continue the accepted bounded work.",
                "stop_condition": "Return one result.",
                field: "caller-controlled",
            })


def test_principal_tool_normalization_reuses_existing_dialogue_bodies() -> None:
    assert validate_principal_tool_arguments("read_thread", {}) == {}
    assert validate_principal_tool_arguments(
        "continue",
        {
            "instruction": "Continue the accepted bounded work.",
            "stop_condition": "Return one canonical result.",
        },
    ) == {
        "instruction": "Continue the accepted bounded work.",
        "stop_condition": "Return one canonical result.",
        "scope_change": False,
        "evidence_refs": [],
    }
    assert validate_principal_tool_arguments(
        "stop", {"reason": "Accepted terminal result.", "next_authority": "sol"}
    ) == {
        "reason": "Accepted terminal result.",
        "next_authority": "sol",
        "evidence_refs": [],
    }
    ruling = validate_principal_tool_arguments(
        "ruling",
        {
            "authority_class": "WITHIN_COMMISSION",
            "selected_option": "opt-proceed",
            "decision": "Proceed.",
            "rationale": "The option remains within the accepted commission.",
        },
    )
    assert ruling["canonical_ref"] is None
    assert ruling["selected_option"] == "opt-proceed"


@pytest.mark.parametrize(
    "tool",
    ["ack", "progress", "blocked", "request_decision", "result", "generic_post"],
)
def test_worker_style_or_generic_tools_are_absent_from_principal_surface(tool: str) -> None:
    with pytest.raises(PrincipalGatewayError):
        validate_principal_tool_arguments(tool, {})


def test_neutral_contract_accepts_exact_principal_reply_but_not_worker_message_family() -> None:
    principal = principal_actor()
    message = build_message_v2(
        {
            "schema": "mastermind.agent_dialogue.v2",
            "message_key": "asd-principal-contract-0001",
            "message_type": "CONTINUE",
            "work_ref": WORK_REF,
            "commission_ref": commission(),
            "session_ref": SESSION_REF,
            "actor_ref": principal,
            "reply_to_message_key": REPLY_KEY,
            "applies_to": applies_to(),
            "summary": "COO continuation returned.",
            "body": {
                "instruction": "Continue.",
                "stop_condition": "Return.",
                "scope_change": False,
            },
            "evidence_refs": [],
            "requires_response": False,
            "created_at": "2026-10-05T06:00:00Z",
        }
    )
    assert message["actor_ref"] == principal

    hostile = dict(message)
    hostile.pop("fingerprint")
    hostile["message_key"] = "asd-principal-contract-0002"
    hostile["message_type"] = "ACK"
    hostile["reply_to_message_key"] = None
    hostile["body"] = {"acknowledged": True}
    with pytest.raises(DialogueContractError):
        build_message_v2(hostile)

    higher_seat = dict(message)
    higher_seat.pop("fingerprint")
    higher_seat["message_key"] = "asd-principal-contract-0003"
    higher_seat["message_type"] = "RULING"
    higher_seat["body"] = {
        "authority_class": "CHAIRMAN_REQUIRED",
        "selected_option": "opt-escalate",
        "decision": "Escalate.",
        "rationale": "Reserved boundary.",
        "canonical_ref": None,
    }
    with pytest.raises(DialogueContractError):
        build_message_v2(higher_seat)


class AuthorityPolicy:
    def minimum_authority(self, *, request, option):
        return "WITHIN_COMMISSION"

    def allows_continuation(self, *, request, reply):
        return True


def worker_message(
    message_type: str,
    *,
    key: str,
    body: dict,
    requires_response: bool,
) -> dict:
    return build_message_v2(
        {
            "schema": "mastermind.agent_dialogue.v2",
            "message_key": key,
            "message_type": message_type,
            "work_ref": WORK_REF,
            "commission_ref": commission(),
            "session_ref": SESSION_REF,
            "actor_ref": worker_actor(),
            "reply_to_message_key": None,
            "applies_to": applies_to(),
            "summary": "Worker return.",
            "body": body,
            "evidence_refs": [],
            "requires_response": requires_response,
            "created_at": "2026-10-05T05:59:00Z",
        }
    )


def principal_reply(message_type: str, request: dict, body: dict) -> dict:
    return build_message_v2(
        {
            "schema": "mastermind.agent_dialogue.v2",
            "message_key": "asd-principal-adjudication-0001",
            "message_type": message_type,
            "work_ref": WORK_REF,
            "commission_ref": commission(),
            "session_ref": SESSION_REF,
            "actor_ref": principal_actor(),
            "reply_to_message_key": request["message_key"],
            "applies_to": applies_to(),
            "summary": "COO reply.",
            "body": body,
            "evidence_refs": [],
            "requires_response": False,
            "created_at": "2026-10-05T06:00:00Z",
        }
    )


def test_engine_adjudicates_coo_principal_ruling_and_continuation_for_worker_only() -> None:
    request = worker_message(
        "DECISION_REQUEST",
        key=REPLY_KEY,
        body={
            "question": "Proceed?",
            "outcome_impact": "Work is paused.",
            "options": [
                {
                    "id": "opt-proceed",
                    "summary": "Proceed.",
                    "consequence": "Continue bounded work.",
                    "disposition": "CONTINUE",
                    "authority_effect": "NONE",
                }
            ],
            "recommendation": "opt-proceed",
            "work_paused": True,
        },
        requires_response=True,
    )
    ruling = principal_reply(
        "RULING",
        request,
        {
            "authority_class": "WITHIN_COMMISSION",
            "selected_option": "opt-proceed",
            "decision": "Proceed.",
            "rationale": "Inside the accepted commission.",
            "canonical_ref": None,
        },
    )
    assert _adjudicate_reply_v2(
        request, ruling, authority_policy=AuthorityPolicy()
    )["disposition"] == "CONTINUE"

    result = worker_message(
        "RESULT",
        key="asd-result-87654321",
        body={"status": "PARTIAL", "result": "One bounded phase complete."},
        requires_response=False,
    )
    continuation = principal_reply(
        "CONTINUE",
        result,
        {
            "instruction": "Continue the next bounded phase.",
            "stop_condition": "Return the next result.",
            "scope_change": False,
        },
    )
    assert _adjudicate_reply_v2(
        result, continuation, authority_policy=AuthorityPolicy()
    )["disposition"] == "CONTINUE"


def test_principal_cannot_reply_as_higher_seat_or_to_an_executive_request() -> None:
    executive_request = build_message_v2(
        {
            "schema": "mastermind.agent_dialogue.v2",
            "message_key": "asd-decision-executive-0001",
            "message_type": "DECISION_REQUEST",
            "work_ref": WORK_REF,
            "commission_ref": commission(),
            "session_ref": SESSION_REF,
            "actor_ref": {
                "kind": "executive_surface",
                "seat": "coo",
                "reasoning_surface": "claude",
            },
            "reply_to_message_key": None,
            "applies_to": applies_to(),
            "summary": "COO decision request.",
            "body": {
                "question": "Escalate?",
                "outcome_impact": "A higher-seat decision is required.",
                "options": [
                    {
                        "id": "opt-escalate",
                        "summary": "Escalate.",
                        "consequence": "Reserve the higher-seat turn.",
                        "disposition": "STOP",
                        "authority_effect": "CHAIRMAN_REQUIRED",
                    }
                ],
                "recommendation": "opt-escalate",
                "work_paused": True,
            },
            "evidence_refs": [],
            "requires_response": True,
            "created_at": "2026-10-05T05:59:00Z",
        }
    )
    reply = principal_reply(
        "RULING",
        executive_request,
        {
            "authority_class": "WITHIN_COMMISSION",
            "selected_option": "opt-escalate",
            "decision": "Escalate.",
            "rationale": "Reserved boundary.",
            "canonical_ref": None,
        },
    )
    with pytest.raises(DialogueEngineError):
        _adjudicate_reply_v2(
            executive_request,
            reply,
            authority_policy=AuthorityPolicy(),
        )


def test_read_thread_is_bound_and_does_not_invoke_commit_fence() -> None:
    service, fences = ExactService(), []
    response = run(gateway(service, fences).call("read_thread", {}))
    assert response["ok"] is True
    assert response["schema"] == PRINCIPAL_RESULT_SCHEMA
    assert fences == []
    assert service.before_write_calls == 0
    assert service.calls[0]["operation"] == "read_thread"


def test_exact_continue_invokes_durable_fence_before_first_commit() -> None:
    service, fences = ExactService(), []
    response = run(
        gateway(service, fences).call(
            "continue",
            {
                "instruction": "Continue the next bounded phase.",
                "stop_condition": "Return one canonical result.",
            },
        )
    )
    assert response["ok"] is True
    assert len(fences) == 1
    intent = fences[0]
    assert intent.schema == "mastermind.company_dialogue_principal_commit_intent.v1"
    assert intent.message_type == "CONTINUE"
    assert intent.reply_to_message_key == REPLY_KEY
    assert intent.child_job_id == "JOB-200"
    assert intent.principal_binding_digest == D0
    assert service.before_write_calls == 1
    sent = service.calls[0]
    assert sent["args"]["send_protocol"] == EXACT_SEND_PROTOCOL
    assert sent["args"]["message"]["message_key"] == intent.message_key
    assert sent["args"]["message"]["fingerprint"] == intent.message_fingerprint


def test_identical_retry_reuses_same_edge_without_second_commit_fence() -> None:
    service, fences = ExactService(), []
    subject = gateway(service, fences)
    args = {
        "instruction": "Continue the next bounded phase.",
        "stop_condition": "Return one canonical result.",
    }
    first = run(subject.call("continue", args))
    second = run(subject.call("continue", args))
    assert first["ok"] is True and second["ok"] is True
    assert len(fences) == 1
    assert service.before_write_calls == 1
    assert first["data"]["message_key"] == second["data"]["message_key"]
    assert second["data"]["action"] == "DUPLICATE"


def test_changed_semantics_or_edge_kind_conflicts_on_same_child_return() -> None:
    service, fences = ExactService(), []
    subject = gateway(service, fences)
    first = run(
        subject.call(
            "continue",
            {
                "instruction": "Continue A.",
                "stop_condition": "Return A.",
            },
        )
    )
    changed = run(
        subject.call(
            "continue",
            {
                "instruction": "Continue B.",
                "stop_condition": "Return B.",
            },
        )
    )
    stopped = run(
        subject.call(
            "stop",
            {"reason": "Stop instead.", "next_authority": "sol"},
        )
    )
    assert first["ok"] is True
    assert changed["ok"] is False
    assert stopped["ok"] is False
    assert changed["error"]["detail_code"] == "MESSAGE_KEY_CONFLICT"
    assert stopped["error"]["detail_code"] == "MESSAGE_KEY_CONFLICT"
    assert changed["data"]["message_key"] == first["data"]["message_key"]
    assert stopped["data"]["message_key"] == first["data"]["message_key"]
    assert len(fences) == 1


def test_durable_fence_refusal_stops_before_commit_and_returns_reconciliation_key() -> None:
    service, fences = ExactService(), []
    response = run(
        gateway(service, fences, fence_error=True).call(
            "continue",
            {
                "instruction": "Continue.",
                "stop_condition": "Return.",
            },
        )
    )
    assert response["ok"] is False
    assert response["error"]["code"] == "EFFECT_FENCE_UNAVAILABLE"
    assert response["data"]["message_key"].startswith("asd-principal-")
    assert len(fences) == 1
    assert service.messages == {}


def test_noop_or_mismatched_fence_receipt_refuses_before_commit() -> None:
    service = ExactService()

    def noop_fence(intent: PrincipalCommitIntent):
        return None

    subject = PrincipalCompanyDialogueGateway(
        Resolver(),
        socket_path=Path("/private/tmp/mastermind-agent-dialogue.sock"),
        before_commit=noop_fence,
        service_call=service,
        utc_now=lambda: "2026-10-05T06:00:00Z",
    )
    response = run(
        subject.call(
            "continue",
            {"instruction": "Continue.", "stop_condition": "Return."},
        )
    )
    assert response["ok"] is False
    assert response["error"]["code"] == "EFFECT_FENCE_UNAVAILABLE"
    assert service.messages == {}

    def wrong_fence(intent: PrincipalCommitIntent):
        return PrincipalCommitFenceReceipt(
            schema="mastermind.company_dialogue_principal_commit_fence_receipt.v1",
            intent_sha256="f" * 64,
            durable_ref="event:wrong",
        )

    service2 = ExactService()
    response2 = run(
        PrincipalCompanyDialogueGateway(
            Resolver(),
            socket_path=Path("/private/tmp/mastermind-agent-dialogue.sock"),
            before_commit=wrong_fence,
            service_call=service2,
            utc_now=lambda: "2026-10-05T06:00:00Z",
        ).call(
            "continue",
            {"instruction": "Continue.", "stop_condition": "Return."},
        )
    )
    assert response2["ok"] is False
    assert response2["error"]["code"] == "EFFECT_FENCE_UNAVAILABLE"
    assert service2.messages == {}


def test_lost_response_after_fence_is_effect_unknown_with_same_reconciliation_key() -> None:
    service, fences = ExactService(effect_unknown=True), []
    response = run(
        gateway(service, fences).call(
            "continue",
            {
                "instruction": "Continue.",
                "stop_condition": "Return.",
            },
        )
    )
    assert response["ok"] is False
    assert response["error"]["code"] == "EFFECT_UNKNOWN"
    assert response["error"]["detail_code"] == "SEND_EFFECT_UNKNOWN"
    assert response["data"]["message_key"] == fences[0].message_key
    assert len(fences) == 1


def test_effect_unknown_replay_requires_durable_owner_to_refuse_second_commit() -> None:
    service = ExactService(effect_unknown=True)
    intents: list[PrincipalCommitIntent] = []
    admitted_digest: str | None = None

    async def one_shot_fence(intent: PrincipalCommitIntent):
        nonlocal admitted_digest
        intents.append(intent)
        digest = intent.digest()
        if admitted_digest is not None:
            assert digest == admitted_digest
            raise RuntimeError("original COMMIT outcome requires reconciliation")
        admitted_digest = digest
        return PrincipalCommitFenceReceipt.for_intent(
            intent,
            durable_ref="event:principal-commit-started",
        )

    subject = PrincipalCompanyDialogueGateway(
        Resolver(),
        socket_path=Path("/private/tmp/mastermind-agent-dialogue.sock"),
        before_commit=one_shot_fence,
        service_call=service,
        utc_now=lambda: "2026-10-05T06:00:00Z",
    )
    args = {
        "instruction": "Continue.",
        "stop_condition": "Return.",
    }

    first = run(subject.call("continue", args))
    second = run(subject.call("continue", args))

    assert first["ok"] is False
    assert first["error"]["code"] == "EFFECT_UNKNOWN"
    assert second["ok"] is False
    assert second["error"]["code"] == "EFFECT_FENCE_UNAVAILABLE"
    assert first["data"]["message_key"] == second["data"]["message_key"]
    assert len(intents) == 2
    assert intents[0].digest() == intents[1].digest()
    assert service.messages == {}


def test_principal_gateway_refuses_worker_binding_and_requires_commit_owner() -> None:
    worker_binding = __import__("dataclasses").replace(
        binding(),
        actor_ref=worker_actor(),
        allowed_message_types=("ACK", "BLOCKED", "DECISION_REQUEST", "PROGRESS", "RESULT"),
        reply_to_message_key=None,
    )
    service, fences = ExactService(), []
    response = run(
        gateway(service, fences, resolver=Resolver(worker_binding)).call(
            "read_thread", {}
        )
    )
    assert response["ok"] is False
    assert response["error"]["code"] == "BINDING_UNAVAILABLE"
    assert service.calls == []

    with pytest.raises(TypeError):
        PrincipalCompanyDialogueGateway(
            Resolver(),
            socket_path=Path("/private/tmp/mastermind-agent-dialogue.sock"),
            before_commit=None,  # type: ignore[arg-type]
            service_call=service,
        )


def test_principal_source_modules_add_no_persistence_runtime_or_transport_owner() -> None:
    package = ROOT / "integrations" / "mastermind_company_mcp"
    for name in ("principal_schemas.py", "principal_adapter.py"):
        tree = ast.parse((package / name).read_text(encoding="utf-8"))
        imports = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        imports |= {
            node.module or ""
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
        }
        roots = {item.split(".")[0] for item in imports}
        assert roots.isdisjoint(
            {"sqlite3", "subprocess", "requests", "httpx", "slack_sdk", "mcp"}
        )
        assert not any(item.startswith("control_plane") for item in imports)


def test_existing_server_declares_separate_principal_builders_without_dynamic_tools() -> None:
    source = (ROOT / "integrations" / "mastermind_company_mcp" / "server.py").read_text()
    assert "def build_principal_tools()" in source
    assert "def build_principal_mcp_server(" in source
    assert "def run_principal_stdio(" in source
    for forbidden in (
        "add_tool(",
        "remove_tool(",
        "register_tool(",
        "list_resources(",
        "read_resource(",
        "list_prompts(",
        "get_prompt(",
    ):
        assert forbidden not in source


def test_principal_facet_is_not_admitted_by_current_capability_policy() -> None:
    policy_text = (
        ROOT / "config" / "executive_agent_capabilities.json"
    ).read_text(encoding="utf-8")
    capability_source = (
        ROOT / "control_plane" / "executive_agent_capabilities.py"
    ).read_text(encoding="utf-8")
    for marker in (
        PRINCIPAL_SERVER_IDENTITY,
        PRINCIPAL_SERVER_NAME,
    ):
        assert marker not in policy_text
        assert marker not in capability_source


def test_principal_test_is_in_existing_ci_gate() -> None:
    from scripts.ci_pytest import resolve_gate

    gate = resolve_gate(ROOT)
    assert "tests/test_company_dialogue_principal_mcp.py" in gate["included"]

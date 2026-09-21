"""Hermetic contracts for sealed self-returning Workspace Agent trigger packages."""
from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from integrations.mastermind_company_mcp.adapter import DialogueBinding
from integrations.workspace_agent_activation_trigger import (
    PACKAGE_SCHEMA,
    PROMPT_SCHEMA,
    WorkspaceActivationTriggerError,
    build_self_returning_trigger_package,
)
from integrations.workspace_agent_profiles import (
    ECONOMIC_SCHEMA,
    OVERFLOW_POLICY,
    build_activation_binding,
)
from integrations.workspace_agent_return import (
    MAX_TICKET_TTL_MS,
    WorkspaceReturnTicketCodec,
    binding_digest,
)


ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "config" / "workspace_agents" / "profile_catalog.v1.json"
MODULE = ROOT / "integrations" / "workspace_agent_activation_trigger.py"
NOW = 1790000000000
EVENT_ISSUED = NOW - 1_000
SUBJECT = "a" * 64
OPERATION = "exec-job-200"
EVENT = "workspace-event-0001"
KEY = b"k" * 32


def catalog() -> dict:
    return json.loads(CATALOG.read_text(encoding="utf-8"))


def economic_envelope(**changes) -> dict:
    value = {
        "schema": ECONOMIC_SCHEMA,
        "authority_ref": "chairman:workspace-canary",
        "accounting_source_ref": "billing:workspace-seat",
        "billing_currency": "USD",
        "incremental_spend_cap_minor_units": 0,
        "usage_unit": "trigger",
        "usage_cap_quantity": 1,
        "max_trigger_count": 1,
        "overflow_policy": OVERFLOW_POLICY,
        "issued_at_ms": NOW - 60_000,
        "expires_at_ms": NOW + 60 * 60 * 1000,
    }
    value.update(changes)
    return value


def activation(**changes) -> dict:
    value = build_activation_binding(
        catalog=catalog(),
        profile_id="program-continuity-adviser",
        provider_channel_ref="agtch_synthetic",
        agent_version_ref="agent-version-20260921-01",
        return_subject_digest=SUBJECT,
        economic_envelope=economic_envelope(),
    )
    value.update(changes)
    return value


def binding(**changes) -> DialogueBinding:
    value = {
        "actor_ref": {
            "kind": "worker_attempt",
            "job_id": "JOB-200",
            "attempt_id": "ATT-200",
            "worker_id": "worker-200",
        },
        "work_ref": "WS:WORKSPACE-AGENT-PROGRAM",
        "commission_ref": {
            "repository": "mastermindx-market-intelligence/Mastermind",
            "commit": "1" * 40,
            "path": "research/WORKSPACE_AGENT_SUPERVISION_INTEGRATION_2026-09-13.md",
            "content_sha256": "2" * 64,
        },
        "session_ref": "asd-session-exec-job-200",
        "operation_key": OPERATION,
        "watch_mode": None,
        "applies_to": {
            "kind": "executive_attempt",
            "job_id": "JOB-200",
            "attempt_id": "ATT-200",
            "worker_id": "worker-200",
        },
        "thread_ts": "1790000000.123456",
        "allowed_message_types": ("RESULT",),
        "reply_to_message_key": None,
    }
    value.update(changes)
    return DialogueBinding(**value)


def package(**changes):
    codec = changes.pop("ticket_codec", WorkspaceReturnTicketCodec(KEY))
    arguments = {
        "catalog": catalog(),
        "activation_binding": activation(),
        "expected_return_subject_digest": SUBJECT,
        "current_binding": binding(),
        "operation_key": OPERATION,
        "event_ref": EVENT,
        "event_issued_at_ms": EVENT_ISSUED,
        "now_ms": NOW,
        "task_input": "Review the current responsibility and return one bounded next-action candidate.",
        "ticket_codec": codec,
    }
    arguments.update(changes)
    return codec, build_self_returning_trigger_package(**arguments)


def trigger_prompt(value) -> tuple[dict, str]:
    body = json.loads(value.trigger_plan._body)
    return json.loads(body["input"]), body["conversation_key"]


def test_package_is_deterministic_across_later_observation_time() -> None:
    codec = WorkspaceReturnTicketCodec(KEY)
    _, first = package(ticket_codec=codec, now_ms=NOW)
    _, second = package(ticket_codec=codec, now_ms=NOW + 100)

    assert first == second
    assert first.schema == PACKAGE_SCHEMA
    assert first.trigger_plan.channel_id == "agtch_synthetic"
    assert first.trigger_plan.operation_key == OPERATION
    assert first.ticket_expires_at_ms == EVENT_ISSUED + MAX_TICKET_TTL_MS
    assert first.binding_digest == binding_digest(binding())


def test_prompt_carries_exact_return_ref_without_leaking_it_from_manifest_repr() -> None:
    codec, value = package()
    prompt, conversation_key = trigger_prompt(value)

    assert prompt["schema"] == PROMPT_SCHEMA
    assert prompt["activation_digest"] == value.activation_digest
    assert prompt["event_digest"] == value.event_digest
    assert prompt["profile"] == {
        "profile_id": value.profile_id,
        "profile_revision": value.profile_revision,
        "profile_digest": activation()["profile_digest"],
        "agent_version_ref": value.agent_version_ref,
    }
    assert prompt["return_contract"]["tool"] == "submit_candidate"
    assert prompt["return_contract"]["candidate_only"] is True
    return_ref = prompt["return_contract"]["return_ref"]
    ticket = codec.decode(return_ref, now_ms=NOW)
    assert ticket.ticket_id == value.ticket_id
    assert ticket.operation_key == OPERATION
    assert ticket.binding_digest == value.binding_digest
    assert ticket.issued_at_ms == EVENT_ISSUED
    assert ticket.expires_at_ms == value.ticket_expires_at_ms
    assert value.return_ref_sha256 != return_ref
    assert return_ref not in repr(value)
    assert prompt["task_input"] not in repr(value)
    assert conversation_key == value.conversation_key
    assert SUBJECT not in json.dumps(prompt, sort_keys=True)
    assert "chairman:workspace-canary" not in json.dumps(prompt, sort_keys=True)


def test_new_event_changes_return_capability_and_same_event_task_change_keeps_ticket() -> None:
    _, original = package()
    original_prompt, _ = trigger_prompt(original)

    _, new_event = package(event_ref="workspace-event-0002")
    new_event_prompt, _ = trigger_prompt(new_event)

    _, changed_task = package(
        task_input="Review only the exact current evidence and return a bounded candidate."
    )
    changed_task_prompt, _ = trigger_prompt(changed_task)

    assert new_event.event_digest != original.event_digest
    assert new_event.ticket_id != original.ticket_id
    assert (
        new_event_prompt["return_contract"]["return_ref"]
        != original_prompt["return_contract"]["return_ref"]
    )
    assert new_event.trigger_plan.idempotency_key != original.trigger_plan.idempotency_key

    assert changed_task.event_digest == original.event_digest
    assert changed_task.ticket_id == original.ticket_id
    assert changed_task.return_ref_sha256 == original.return_ref_sha256
    assert (
        changed_task_prompt["return_contract"]["return_ref"]
        == original_prompt["return_contract"]["return_ref"]
    )
    assert changed_task.trigger_plan.idempotency_key != original.trigger_plan.idempotency_key


def test_activation_current_subject_and_event_window_fail_closed() -> None:
    with pytest.raises(WorkspaceActivationTriggerError, match="ACTIVATION_REFUSED"):
        package(expected_return_subject_digest="b" * 64)

    with pytest.raises(WorkspaceActivationTriggerError, match="EVENT_OUTSIDE_ACTIVATION"):
        package(
            event_issued_at_ms=NOW - 120_000,
            activation_binding=build_activation_binding(
                catalog=catalog(),
                profile_id="program-continuity-adviser",
                provider_channel_ref="agtch_synthetic",
                agent_version_ref="agent-version-20260921-01",
                return_subject_digest=SUBJECT,
                economic_envelope=economic_envelope(issued_at_ms=NOW - 60_000),
            ),
        )

    with pytest.raises(WorkspaceActivationTriggerError, match="RETURN_WINDOW_EXPIRED"):
        package(now_ms=EVENT_ISSUED + MAX_TICKET_TTL_MS + 1)

    with pytest.raises(WorkspaceActivationTriggerError, match="ACTIVATION_REFUSED"):
        package(
            now_ms=NOW + 2 * 60 * 60 * 1000,
            activation_binding=build_activation_binding(
                catalog=catalog(),
                profile_id="program-continuity-adviser",
                provider_channel_ref="agtch_synthetic",
                agent_version_ref="agent-version-20260921-01",
                return_subject_digest=SUBJECT,
                economic_envelope=economic_envelope(expires_at_ms=NOW + 60 * 60 * 1000),
            ),
        )


def test_operation_binding_and_input_shape_refuse_before_plan() -> None:
    with pytest.raises(WorkspaceActivationTriggerError, match="CURRENT_BINDING_REFUSED"):
        package(operation_key="exec-job-201")

    with pytest.raises(WorkspaceActivationTriggerError, match="INVALID_EVENT"):
        package(event_ref="bad")

    with pytest.raises(WorkspaceActivationTriggerError, match="INVALID_TASK_INPUT"):
        package(task_input="bad\x00task")

    with pytest.raises(WorkspaceActivationTriggerError, match="INVALID_EVENT"):
        package(event_issued_at_ms=NOW + 1)


def test_source_is_pure_pre_effect_composition_only() -> None:
    tree = ast.parse(MODULE.read_text(encoding="utf-8"))
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)

    forbidden_imports = {
        "http.client",
        "httpx",
        "requests",
        "socket",
        "sqlite3",
        "subprocess",
        "keyring",
        "control_plane.executive_runtime",
    }
    assert not (imports & forbidden_imports)

    source = MODULE.read_text(encoding="utf-8")
    for forbidden_text in (
        "trigger_once(",
        "Runtime.at(",
        "CREATE TABLE",
        "INSERT INTO",
        "UPDATE ",
        "DELETE FROM",
        "publish_agent",
        "create_workspace_agent",
    ):
        assert forbidden_text not in source

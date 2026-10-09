from __future__ import annotations

import asyncio

import pytest

from integrations.mastermind_browser_plugin.workbench_client import (
    WorkbenchBrowserClientError,
    WorkbenchBrowserMcpEffectPort,
)


class Caller:
    pass


class ToolCaller:
    def __init__(self):
        self.calls = []
        self.fail = None

    async def __call__(self, name, arguments):
        self.calls.append((name, dict(arguments)))
        if self.fail is not None:
            raise self.fail
        if name == "browser_snapshot":
            return {
                "content": [{"type": "text", "text": "synthetic"}],
                "structuredContent": {"kind": "snapshot"},
                "isError": False,
            }
        if name == "prepare_browser_click":
            return {
                "content": [],
                "structuredContent": {
                    "status": "PREPARED",
                    "action_ref": "owner-action-ref",
                },
                "isError": False,
            }
        if name == "run_browser_action":
            return {
                "content": [],
                "structuredContent": {
                    "status": "OK",
                    "effect_state": "APPLIED",
                    "observed_sha256": "a" * 64,
                    "reconciled": False,
                },
                "isError": False,
            }
        if name == "reconcile_browser_action":
            return {
                "content": [],
                "structuredContent": {
                    "status": "OK",
                    "effect_state": "EFFECT_UNKNOWN",
                    "observed_sha256": None,
                    "reconciled": True,
                },
                "isError": False,
            }
        raise AssertionError(name)


def port():
    caller = ToolCaller()
    return WorkbenchBrowserMcpEffectPort(call_tool=caller), caller


def test_read_delegates_exact_native_tool_with_browser_ref():
    effect, calls = port()
    result = asyncio.run(
        effect.call_read_tool(
            Caller(),
            "browser-resource-ref",
            "browser_snapshot",
            {"page": 7},
        )
    )
    assert result["structuredContent"]["kind"] == "snapshot"
    assert calls.calls == [
        (
            "browser_snapshot",
            {"browser_ref": "browser-resource-ref", "page": 7},
        )
    ]


def test_prepare_uses_existing_prepare_tool_and_returns_only_action_ref():
    effect, calls = port()
    result = asyncio.run(
        effect.prepare_action(
            Caller(),
            "browser-resource-ref",
            "browser_click",
            {"element": "a"},
        )
    )
    assert result == "owner-action-ref"
    assert calls.calls == [
        (
            "prepare_browser_click",
            {
                "browser_ref": "browser-resource-ref",
                "element": "a",
            },
        )
    ]


def test_run_and_reconcile_preserve_existing_effect_receipt_shape():
    effect, calls = port()
    run = asyncio.run(
        effect.run_action(Caller(), "browser-resource-ref", "owner-action-ref")
    )
    reconcile = asyncio.run(
        effect.reconcile_action(
            Caller(), "browser-resource-ref", "owner-action-ref"
        )
    )
    assert run["effect_state"] == "APPLIED"
    assert reconcile["effect_state"] == "EFFECT_UNKNOWN"
    assert [row[0] for row in calls.calls] == [
        "run_browser_action",
        "reconcile_browser_action",
    ]
    assert all(
        row[1]
        == {
            "browser_ref": "browser-resource-ref",
            "action_ref": "owner-action-ref",
        }
        for row in calls.calls
    )


@pytest.mark.parametrize(
    "tool",
    [
        "browser_close",
        "browser_console_messages",
        "browser_network_requests",
        "browser_hover",
        "browser_fill_form",
        "browser_press_key",
        "browser_select_option",
        "browser_tabs",
        "shell",
        "evaluate",
    ],
)
def test_adapter_only_accepts_high_level_projector_tool_subset(tool):
    effect, _ = port()
    with pytest.raises(WorkbenchBrowserClientError, match="TOOL_NOT_ALLOWED"):
        asyncio.run(
            effect.call_read_tool(
                Caller(), "browser-resource-ref", tool, {}
            )
        )


def test_prepare_rejects_read_tool_and_unknown_tool_before_transport():
    effect, calls = port()
    for tool in ("browser_snapshot", "browser_take_screenshot", "shell"):
        with pytest.raises(WorkbenchBrowserClientError):
            asyncio.run(
                effect.prepare_action(
                    Caller(), "browser-resource-ref", tool, {}
                )
            )
    assert calls.calls == []


def test_transport_exception_is_not_retried_or_downgraded():
    effect, calls = port()
    calls.fail = RuntimeError("lost response")
    with pytest.raises(WorkbenchBrowserClientError, match="TRANSPORT_UNCERTAIN"):
        asyncio.run(
            effect.run_action(
                Caller(), "browser-resource-ref", "owner-action-ref"
            )
        )
    assert len(calls.calls) == 1


def test_invalid_structured_results_fail_closed_without_secret_echo():
    effect, calls = port()

    async def malformed(_name, _arguments):
        return {
            "content": [{"type": "text", "text": "credential-do-not-echo"}],
            "structuredContent": {"status": "OK"},
            "isError": False,
        }

    effect = WorkbenchBrowserMcpEffectPort(call_tool=malformed)
    with pytest.raises(WorkbenchBrowserClientError) as exc:
        asyncio.run(
            effect.run_action(
                Caller(), "browser-resource-ref", "owner-action-ref"
            )
        )
    assert "credential-do-not-echo" not in str(exc.value)


def test_caller_identity_is_not_serialized_into_low_level_mcp_arguments():
    effect, calls = port()
    caller = object()
    asyncio.run(
        effect.call_read_tool(
            caller,
            "browser-resource-ref",
            "browser_snapshot",
            {},
        )
    )
    rendered = repr(calls.calls)
    assert "caller" not in rendered
    assert "actor" not in rendered

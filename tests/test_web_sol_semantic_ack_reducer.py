"""Provider-local Web-Sol completed-turn semantic ACK reduction."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "integrations/chairman_surfaces/web_sol_extension/semantic_ack_core.js"
OID_A = "WAKE-" + "a" * 32
OID_B = "WAKE-" + "b" * 32
NUDGE = "NUDGE-" + "c" * 32
SET_DIGEST = "d" * 64


def _message(
    role: str,
    message_id: str,
    text: str = "",
    *,
    status: str | None = "finished_successfully",
    end_turn: bool | None = True,
) -> dict[str, object]:
    return {
        "id": message_id,
        "author": {"role": role},
        "status": status,
        "end_turn": end_turn,
        "content": {"content_type": "text", "parts": [text]},
    }


def _node(
    message_id: str,
    parent: str | None,
    message: dict[str, object] | None,
    *,
    children: list[str] | None = None,
) -> dict[str, object]:
    return {
        "id": message_id,
        "parent": parent,
        "children": list(children or []),
        "message": message,
    }


def _nudge_text() -> str:
    return "\n".join(
        [
            "SOL CONTINUE",
            f"- {OID_A}",
            f"- {OID_B}",
            f"MASTERMIND_WAKE_NUDGE {NUDGE}",
            f"MASTERMIND_WAKE_SET {SET_DIGEST}",
        ]
    )


def _ack_text(*, prose: str = "Canonical state consumed.") -> str:
    return "\n".join(
        [prose, f"MASTERMIND_WAKE_ACK {OID_B}", f"MASTERMIND_WAKE_ACK {OID_A}"]
    )


def _linear_snapshot(
    assistant_text: str,
    *,
    assistant_status: str | None = "finished_successfully",
    assistant_end_turn: bool | None = True,
) -> dict[str, object]:
    user_id = "user-turn-current-001"
    assistant_id = "assistant-turn-current-001"
    return {
        "current_node": assistant_id,
        "mapping": {
            user_id: _node(
                user_id,
                None,
                _message("user", user_id, _nudge_text(), end_turn=False),
                children=[assistant_id],
            ),
            assistant_id: _node(
                assistant_id,
                user_id,
                _message(
                    "assistant",
                    assistant_id,
                    assistant_text,
                    status=assistant_status,
                    end_turn=assistant_end_turn,
                ),
            ),
        },
    }


def _run(snapshot: dict[str, object]) -> dict[str, object]:
    node = shutil.which("node")
    assert node is not None
    harness = r"""
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(process.argv[1], 'utf8');
const input = JSON.parse(process.argv[2]);
const context = vm.createContext({globalThis: null, Object, Array, Set, RegExp, JSON, String, Number, Boolean});
context.globalThis = context;
vm.runInContext(source, context, {filename: 'semantic_ack_core.js'});
const result = context.MMXWebSolSemanticAck.reduceConversation(input.snapshot, input.request);
process.stdout.write(JSON.stringify(result));
"""
    payload = {
        "snapshot": snapshot,
        "request": {
            "nudge_id": NUDGE,
            "wake_obligation_ids": [OID_A, OID_B],
            "wake_obligation_digest": SET_DIGEST,
        },
    }
    completed = subprocess.run(
        [node, "-e", harness, str(CORE), json.dumps(payload, separators=(",", ":"))],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    return json.loads(completed.stdout)


def test_exact_current_completed_provider_turn_emits_closed_projection() -> None:
    result = _run(_linear_snapshot(_ack_text()))
    assert result == {
        "status": "ACKNOWLEDGED",
        "provider_native_turn_id": "assistant-turn-current-001",
        "obligation_ids": [OID_A, OID_B],
        "terminal_ack_trailer": True,
    }
    rendered = json.dumps(result, sort_keys=True)
    assert "Canonical state" not in rendered
    assert "content" not in rendered


@pytest.mark.parametrize(
    ("status", "end_turn"),
    [
        ("in_progress", False),
        ("finished_successfully", False),
        ("pending", None),
    ],
)
def test_marker_without_provider_terminal_completion_stays_pending(
    status: str, end_turn: bool | None
) -> None:
    result = _run(
        _linear_snapshot(
            _ack_text(), assistant_status=status, assistant_end_turn=end_turn
        )
    )
    assert result["status"] == "PENDING"
    assert result["provider_native_turn_id"] is None


def test_visible_completed_turn_without_terminal_ack_stays_pending() -> None:
    result = _run(_linear_snapshot("I saw the return but have not consumed it."))
    assert result["status"] == "PENDING"


@pytest.mark.parametrize(
    "assistant_text",
    [
        f"> MASTERMIND_WAKE_ACK {OID_A}\n> MASTERMIND_WAKE_ACK {OID_B}",
        f"```text\nMASTERMIND_WAKE_ACK {OID_A}\nMASTERMIND_WAKE_ACK {OID_B}\n```",
    ],
)
def test_quoted_or_fenced_marker_echo_without_a_terminal_trailer_stays_pending(
    assistant_text: str,
) -> None:
    result = _run(_linear_snapshot(assistant_text))
    assert result["status"] == "PENDING"
    assert result["obligation_ids"] == []


@pytest.mark.parametrize(
    "assistant_text",
    [
        f"MASTERMIND_WAKE_ACK {OID_A}\nMASTERMIND_WAKE_ACK {OID_B}\nnonterminal prose",
        f"MASTERMIND_WAKE_ACK {OID_A}",
        f"MASTERMIND_WAKE_ACK {OID_A}\nMASTERMIND_WAKE_ACK {OID_A}\nMASTERMIND_WAKE_ACK {OID_B}",
        f"MASTERMIND_WAKE_ACK {OID_A}\nMASTERMIND_WAKE_ACK WAKE-{'f' * 32}",
        f" MASTERMIND_WAKE_ACK {OID_A}\n MASTERMIND_WAKE_ACK {OID_B}",
        f"MASTERMIND_WAKE_ACK {OID_A} \nMASTERMIND_WAKE_ACK {OID_B} ",
    ],
)
def test_nonterminal_partial_duplicate_wrong_or_inexact_terminal_trailer_refuses(
    assistant_text: str,
) -> None:
    result = _run(_linear_snapshot(assistant_text))
    assert result["status"] == "REFUSED"
    assert result["obligation_ids"] == []


@pytest.mark.parametrize(
    "echo",
    [
        f"> MASTERMIND_WAKE_ACK {OID_A}",
        f"```text\nMASTERMIND_WAKE_ACK {'WAKE-' + 'f' * 32}\n```",
    ],
)
def test_non_authoritative_older_echo_does_not_block_one_exact_final_trailer(
    echo: str,
) -> None:
    text = "\n".join(
        [
            echo,
            "Canonical state consumed.",
            f"MASTERMIND_WAKE_ACK {OID_B}",
            f"MASTERMIND_WAKE_ACK {OID_A}",
        ]
    )
    result = _run(_linear_snapshot(text))
    assert result["status"] == "ACKNOWLEDGED"
    assert result["obligation_ids"] == [OID_A, OID_B]


@pytest.mark.parametrize("status", ["failed", "cancelled", "interrupted"])
def test_provider_failure_terminal_refuses(status: str) -> None:
    assert _run(_linear_snapshot(_ack_text(), assistant_status=status))["status"] == "REFUSED"


def test_stale_ack_on_noncurrent_branch_cannot_satisfy_current_turn() -> None:
    user_id = "user-turn-current-001"
    stale_id = "assistant-turn-stale-001"
    current_id = "assistant-turn-current-001"
    snapshot = {
        "current_node": current_id,
        "mapping": {
            user_id: _node(
                user_id,
                None,
                _message("user", user_id, _nudge_text(), end_turn=False),
                children=[stale_id, current_id],
            ),
            stale_id: _node(
                stale_id,
                user_id,
                _message("assistant", stale_id, _ack_text()),
            ),
            current_id: _node(
                current_id,
                user_id,
                _message("assistant", current_id, "No terminal marker yet."),
            ),
        },
    }
    assert _run(snapshot)["status"] == "PENDING"


def test_tool_call_intermediary_can_precede_one_exact_final_turn() -> None:
    user_id = "user-turn-current-001"
    tool_call_id = "assistant-tool-call-001"
    tool_id = "tool-result-001"
    final_id = "assistant-turn-current-001"
    snapshot = {
        "current_node": final_id,
        "mapping": {
            user_id: _node(
                user_id,
                None,
                _message("user", user_id, _nudge_text(), end_turn=False),
                children=[tool_call_id],
            ),
            tool_call_id: _node(
                tool_call_id,
                user_id,
                _message(
                    "assistant",
                    tool_call_id,
                    "",
                    status="finished_successfully",
                    end_turn=False,
                ),
                children=[tool_id],
            ),
            tool_id: _node(
                tool_id,
                tool_call_id,
                _message("tool", tool_id, "", end_turn=False),
                children=[final_id],
            ),
            final_id: _node(
                final_id,
                tool_id,
                _message("assistant", final_id, _ack_text()),
            ),
        },
    }
    snapshot["mapping"][tool_call_id]["message"]["content"]["parts"] = [
        {"tool_call": "opaque-provider-local-structure"}
    ]
    result = _run(snapshot)
    assert result["status"] == "ACKNOWLEDGED"
    assert result["provider_native_turn_id"] == final_id


def test_second_completed_assistant_or_later_user_refuses() -> None:
    first = "assistant-turn-first-001"
    second = "assistant-turn-second-001"
    user = "user-turn-current-001"
    snapshot = {
        "current_node": second,
        "mapping": {
            user: _node(
                user,
                None,
                _message("user", user, _nudge_text(), end_turn=False),
                children=[first],
            ),
            first: _node(
                first,
                user,
                _message("assistant", first, _ack_text()),
                children=[second],
            ),
            second: _node(
                second,
                first,
                _message("assistant", second, _ack_text()),
            ),
        },
    }
    assert _run(snapshot)["status"] == "REFUSED"


def test_malformed_or_cyclic_provider_graph_refuses() -> None:
    snapshot = _linear_snapshot(_ack_text())
    snapshot["mapping"]["user-turn-current-001"]["parent"] = "assistant-turn-current-001"
    assert _run(snapshot)["status"] == "REFUSED"

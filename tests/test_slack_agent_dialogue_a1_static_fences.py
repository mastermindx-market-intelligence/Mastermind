from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "integrations" / "slack_agent_dialogue"
A1_FILES = (
    PACKAGE / "contract.py",
    PACKAGE / "engine.py",
    PACKAGE / "fake_slack.py",
    PACKAGE / "service.py",
    ROOT / "scripts" / "agent_dialogue_client.py",
)


def combined_text() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in A1_FILES)


def test_a1_has_no_lifecycle_store_or_executive_crossover() -> None:
    lowered = combined_text().lower()
    forbidden = (
        "sqlite",
        "create table",
        "control_plane",
        "ceo_ingress",
        "sol_state",
        "executive_runtime",
        "apscheduler",
        "launchd",
        "redis",
        "postgres",
        "sqlalchemy",
        "shelve",
        "pickle",
    )
    assert all(fragment not in lowered for fragment in forbidden)


def test_a1_has_no_real_slack_sdk_or_generic_http_client() -> None:
    lowered = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            PACKAGE / "contract.py",
            PACKAGE / "engine.py",
            PACKAGE / "fake_slack.py",
            PACKAGE / "service.py",
        )
    ).lower()
    forbidden = (
        "slack_sdk",
        "urllib.request",
        "requests.",
        "httpx.",
        "aiohttp",
        "websocket",
        "socket mode",
        "conversations.history",
        "conversations.replies",
        "chat.postmessage",
    )
    assert all(fragment not in lowered for fragment in forbidden)


def test_injected_slack_seam_is_exactly_three_methods() -> None:
    tree = ast.parse((PACKAGE / "engine.py").read_text(encoding="utf-8"))
    protocol = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "SlackDialogueClient"
    )
    methods = {
        node.name
        for node in protocol.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert methods == {"fetch_channel_history", "fetch_thread", "post_reply"}


def test_local_service_exposes_only_five_operations() -> None:
    text = (PACKAGE / "service.py").read_text(encoding="utf-8")
    operations = {
        "status",
        "bind_or_verify_thread",
        "send_message",
        "read_thread",
        "wait_for_reply",
    }
    for operation in operations:
        assert f'operation == "{operation}"' in text
    forbidden = (
        "arbitrary_channel",
        "file_upload",
        "workspace_search",
        "user_admin",
        "execute_command",
        "dispatch_job",
        "merge_pull",
        "deploy",
    )
    lowered = text.lower()
    assert all(fragment not in lowered for fragment in forbidden)


def test_model_side_client_contains_no_token_or_credential_path() -> None:
    text = (ROOT / "scripts" / "agent_dialogue_client.py").read_text(
        encoding="utf-8"
    ).lower()
    assert "token" not in text
    assert "credential" not in text
    assert "environment" not in text
    assert "--channel" not in text
    assert "--workspace" not in text


def test_only_service_socket_path_is_written_or_unlinked() -> None:
    tree = ast.parse((PACKAGE / "service.py").read_text(encoding="utf-8"))
    attribute_calls = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            attribute_calls.append(node.func.attr)
    assert "write_text" not in attribute_calls
    assert "write_bytes" not in attribute_calls
    assert "open" not in attribute_calls
    # unlink is present only for the owner-checked AF_UNIX socket path.
    assert "unlink" in attribute_calls

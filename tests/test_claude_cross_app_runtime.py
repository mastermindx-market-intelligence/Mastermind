from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.claude_cross_app_runtime import (
    MODERN_RUNTIME,
    PROFILE_ROOTS,
    build_launch_argv,
    launch_profile,
    profile_status_from_process_rows,
    safe_status_document,
)


def test_profile_set_is_closed_to_the_four_active_accounts():
    assert tuple(PROFILE_ROOTS) == ("claude-2", "claude-3", "claude-5", "claude-6")
    assert PROFILE_ROOTS["claude-2"].endswith("/Parall/Claude 2")
    assert PROFILE_ROOTS["claude-6"].endswith("/Parall/Claude 6")


def test_launch_reuses_modern_runtime_and_preserves_isolated_user_data():
    argv = build_launch_argv("claude-3")
    assert argv == (
        "/usr/bin/open",
        "-na",
        MODERN_RUNTIME,
        "--args",
        "--user-data-dir=/Users/chriswong/Library/Application Support/Parall/Claude 3",
    )


@pytest.mark.parametrize("profile", ["claude-1", "Claude 3", "../claude-3", ""])
def test_unknown_or_unclosed_profile_is_refused(profile):
    with pytest.raises(ValueError, match="unsupported profile"):
        build_launch_argv(profile)


def test_status_detects_existing_profile_process_and_sendmessage_gate():
    rows = [
        (
            100,
            "/Applications/Claude Runtimes/Claude 3/Claude.app/Contents/MacOS/Claude "
            "--user-data-dir=/Users/chriswong/Library/Application Support/Parall/Claude 3",
        ),
        (
            101,
            "/Users/chriswong/Library/Application Support/Parall/Claude 3/"
            "claude-code/2.1.260/claude.app/Contents/MacOS/claude "
            "--disallowedTools SendMessage",
        ),
    ]
    status = profile_status_from_process_rows("claude-3", rows)
    assert status.running_pids == (100, 101)
    assert status.send_message_denied is True


def test_status_does_not_cross_match_other_profiles():
    rows = [
        (
            200,
            "/Users/chriswong/Library/Application Support/Parall/Claude 5/"
            "claude-code/2.1.260/claude.app/Contents/MacOS/claude "
            "--disallowedTools SendMessage",
        )
    ]
    status = profile_status_from_process_rows("claude-3", rows)
    assert status.running_pids == ()
    assert status.send_message_denied is False


def test_safe_status_document_contains_no_command_lines_or_account_identity():
    rows = [
        (
            300,
            "/Users/chriswong/Library/Application Support/Parall/Claude 2/"
            "claude-code/2.1.280/claude.app/Contents/MacOS/claude "
            "--disallowedTools SubscribePR",
        )
    ]
    doc = safe_status_document("claude-2", rows, desktop_version="2.7032.0")
    assert doc == {
        "profile": "claude-2",
        "profile_root": PROFILE_ROOTS["claude-2"],
        "desktop_version": "2.7032.0",
        "running_count": 1,
        "send_message_denied": False,
        "launch_allowed_now": False,
    }
    encoded = json.dumps(doc)
    assert "SubscribePR" not in encoded
    assert "--disallowedTools" not in encoded
    assert "token" not in encoded.lower()


def test_launch_refuses_profile_that_is_already_open():
    calls = []
    rows = [
        (
            400,
            "/Applications/Claude Runtimes/Claude 3/Claude.app/Contents/MacOS/Claude "
            "--user-data-dir=/Users/chriswong/Library/Application Support/Parall/Claude 3",
        )
    ]
    with pytest.raises(RuntimeError, match="PROFILE_ALREADY_RUNNING"):
        launch_profile(
            "claude-3",
            rows,
            runner=lambda argv: calls.append(tuple(argv)),
            runtime_exists=True,
        )
    assert calls == []


def test_launch_refuses_when_modern_runtime_is_missing():
    calls = []
    with pytest.raises(RuntimeError, match="MODERN_RUNTIME_UNAVAILABLE"):
        launch_profile(
            "claude-5",
            [],
            runner=lambda argv: calls.append(tuple(argv)),
            runtime_exists=False,
        )
    assert calls == []


def test_launch_calls_only_the_closed_modern_runtime_command():
    calls = []
    result = launch_profile(
        "claude-6",
        [],
        runner=lambda argv: calls.append(tuple(argv)),
        runtime_exists=True,
    )
    assert calls == [build_launch_argv("claude-6")]
    assert result == {
        "profile": "claude-6",
        "effect": "LAUNCH_REQUESTED",
        "launch_allowed_now": True,
    }

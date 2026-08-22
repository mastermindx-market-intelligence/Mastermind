"""integrations.chairman_surfaces.cursor — Cursor agent thread.

Resumes a ``cursor_agent`` thread by launching ``cursor-agent --resume
<chat_id>`` in a Terminal tab, optionally ``cd``-ing into the bound
workspace first. Same shell-string discipline as ``claude.py``'s
``claude_code`` path: every token is charset-gated before it is
``shlex.quote``-d into the one command string this module ever builds.

Unlike ``claude_code``/``codex`` (see those modules' native existence
gates, Sol review 5000169412 blocker 2), Cursor has no proven local
session/thread store this surface can read — so a launch here can only ever
report ``verified=False`` (``BOUND_UNVERIFIED``): the Terminal launch is
still attempted, but existence of the underlying thread is not provable on
the installed surface.
"""
from __future__ import annotations

import os
import shlex

from . import contract


def open_surface(binding: dict, runner) -> dict:
    locator = binding.get("locator") if isinstance(binding, dict) else None
    locator = locator if isinstance(locator, dict) else {}
    binding_id = binding.get("binding_id") if isinstance(binding, dict) else None
    binding_id = binding_id if isinstance(binding_id, str) else None

    chat_id = locator.get("chat_id")
    workspace_dir = locator.get("workspace_dir")

    if not isinstance(chat_id, str) or not contract.SAFE_ID_RE.match(chat_id):
        return contract.refused("cursor_agent", binding_id, "unsafe_token", "the bound chat id failed the safety check")

    if workspace_dir is not None:
        if not contract.safe_abs_dir(workspace_dir):
            return contract.refused("cursor_agent", binding_id, "unsafe_token", "the bound workspace directory failed the safety check")
        if not os.path.isdir(workspace_dir):
            return contract.refused("cursor_agent", binding_id, "not_found", "the bound workspace directory does not exist")
        command = "cd " + shlex.quote(workspace_dir) + " && " + "cursor-agent --resume " + shlex.quote(chat_id)
    else:
        command = "cursor-agent --resume " + shlex.quote(chat_id)

    result = runner(contract.terminal_launch_argv(command))
    if not isinstance(result, dict) or result.get("timed_out") or result.get("code") != 0:
        return contract.refused("cursor_agent", binding_id, "runner_error", "the terminal launch failed")

    return contract.succeeded(
        "cursor_agent", binding_id, "launched",
        "launched a Terminal session for the bound chat; existence of the underlying session is not provable on the installed surface",
        verified=False,
    )

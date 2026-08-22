"""integrations.chairman_surfaces.claude — Claude Code + Claude desktop.

Two unrelated providers share this module because they share almost nothing
except a name: ``claude_code`` resumes a terminal session, ``claude_desktop``
opens a URL/deep-link in the native app.
"""
from __future__ import annotations

import os
import re
import shlex

from . import contract

#: Strict UUID gate for a ``claude_code`` binding's ``session_id``. Matches
#: ``control_plane.surface_bindings``'s own ``_UUID_RE`` (that module
#: already enforces this at write time); this module re-checks it at open
#: time so a binding crafted or mutated outside ``save_bindings`` cannot
#: reach the shell-string builder below with an unsafe value.
SESSION_ID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE
)


def open_claude_code(binding: dict, runner) -> dict:
    """Resume a ``claude_code`` session by launching it in a Terminal tab.

    Shell-string construction law: the ONE sanctioned shell-string site in
    this package is the ``command`` line built below. It is assembled ONLY
    from two triple-gated tokens — ``project_dir`` (charset via
    :func:`contract.safe_abs_dir`, no ``..`` segment, then existence via
    ``os.path.isdir``) and ``session_id`` (charset via :data:`SESSION_ID_RE`)
    — each individually ``shlex.quote``-d before joining. No other string in
    this package is ever built by concatenation into something a shell will
    interpret.
    """
    locator = binding.get("locator") if isinstance(binding, dict) else None
    locator = locator if isinstance(locator, dict) else {}
    binding_id = binding.get("binding_id") if isinstance(binding, dict) else None
    binding_id = binding_id if isinstance(binding_id, str) else None

    session_id = locator.get("session_id")
    project_dir = locator.get("project_dir")

    if not isinstance(session_id, str) or not SESSION_ID_RE.match(session_id):
        return contract.refused("claude_code", binding_id, "unsafe_token", "the bound session id failed the safety check")

    if not contract.safe_abs_dir(project_dir):
        return contract.refused("claude_code", binding_id, "unsafe_token", "the bound project directory failed the safety check")

    if not os.path.isdir(project_dir):
        return contract.refused("claude_code", binding_id, "not_found", "the bound project directory does not exist")

    command = "cd " + shlex.quote(project_dir) + " && " + "claude --resume " + shlex.quote(session_id)
    result = runner(contract.terminal_launch_argv(command))
    if not isinstance(result, dict) or result.get("timed_out") or result.get("code") != 0:
        return contract.refused("claude_code", binding_id, "runner_error", "the terminal launch failed")

    return contract.succeeded("claude_code", binding_id, "launched", "launched a Terminal session for the bound session")


def open_claude_desktop(binding: dict, runner) -> dict:
    """Open a ``claude_desktop`` binding's URL with the OS default handler.

    The locator's URL was already re-validated (https on ``claude.ai``, or
    the ``claude://`` scheme) by ``control_plane.surface_bindings`` before
    this function is ever reached (see ``contract.open_binding``), so no
    further gate is needed here beyond confirming it is present.
    """
    locator = binding.get("locator") if isinstance(binding, dict) else None
    locator = locator if isinstance(locator, dict) else {}
    binding_id = binding.get("binding_id") if isinstance(binding, dict) else None
    binding_id = binding_id if isinstance(binding_id, str) else None

    url = locator.get("url")
    if not isinstance(url, str) or not url:
        return contract.refused("claude_desktop", binding_id, "invalid_binding", "the bound URL is missing")

    result = runner(["/usr/bin/open", url])
    if not isinstance(result, dict) or result.get("timed_out") or result.get("code") != 0:
        return contract.refused("claude_desktop", binding_id, "runner_error", "opening the bound URL failed")

    return contract.succeeded("claude_desktop", binding_id, "opened", "opened the bound URL")

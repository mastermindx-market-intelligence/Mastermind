"""integrations.chairman_surfaces.codex — Codex session.

Resumes a ``codex`` session by launching ``codex resume <session_id>`` in a
Terminal tab, optionally ``cd``-ing into the bound working directory first.
Same shell-string discipline as ``claude.py``/``cursor.py``: every token is
charset-gated before it is ``shlex.quote``-d into the one command string
this module ever builds.
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

    session_id = locator.get("session_id")
    cwd = locator.get("cwd")

    if not isinstance(session_id, str) or not contract.SAFE_ID_RE.match(session_id):
        return contract.refused("codex", binding_id, "unsafe_token", "the bound session id failed the safety check")

    if cwd is not None:
        if not contract.safe_abs_dir(cwd):
            return contract.refused("codex", binding_id, "unsafe_token", "the bound working directory failed the safety check")
        if not os.path.isdir(cwd):
            return contract.refused("codex", binding_id, "not_found", "the bound working directory does not exist")
        command = "cd " + shlex.quote(cwd) + " && " + "codex resume " + shlex.quote(session_id)
    else:
        command = "codex resume " + shlex.quote(session_id)

    result = runner(contract.terminal_launch_argv(command))
    if not isinstance(result, dict) or result.get("timed_out") or result.get("code") != 0:
        return contract.refused("codex", binding_id, "runner_error", "the terminal launch failed")

    return contract.succeeded("codex", binding_id, "launched", "launched a Terminal session for the bound session")

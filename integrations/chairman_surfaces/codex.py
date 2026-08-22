"""integrations.chairman_surfaces.codex — Codex session.

Resumes a ``codex`` session by launching ``codex resume <session_id>`` in a
Terminal tab, optionally ``cd``-ing into the bound working directory first.
Same shell-string discipline as ``claude.py``/``cursor.py``: every token is
charset-gated before it is ``shlex.quote``-d into the one command string
this module ever builds.

Native existence gate (Sol review 5000169412, blocker 2)
-----------------------------------------------------------
``osascript`` returning ``0`` only proves Terminal accepted the shell line,
never that ``codex resume`` found a real session. So :func:`open_surface`
proves the bound session's transcript file — ``*<session_id>.jsonl`` —
actually exists somewhere under the local Codex sessions store BEFORE ever
launching Terminal; a valid-shaped but nonexistent session id refuses
``not_found`` and the runner is never called. Only a proven-existing session
may report ``verified=True``.
"""
from __future__ import annotations

import os
import shlex
from pathlib import Path

from . import contract

#: Default on-disk root of Codex's session transcripts.
DEFAULT_CODEX_SESSIONS_DIR = "~/.codex/sessions"

#: Bounds on :func:`_codex_session_exists`'s recursive search — a plain
#: unbounded ``Path.rglob`` could hang or scan without limit against a
#: pathological, very large, or symlink-cyclical sessions directory. Depth
#: is capped, symlinked directories are never followed, and the total number
#: of directory entries examined is capped; hitting either bound reports
#: "not found" rather than raising.
_SESSION_SEARCH_MAX_DEPTH = 6
_SESSION_SEARCH_MAX_ENTRIES = 20000


def _codex_session_exists(codex_sessions_dir: str | None, session_id: str) -> bool:
    """Bounded recursive search for ``*<session_id>.jsonl`` under the store."""
    root = Path(codex_sessions_dir).expanduser() if codex_sessions_dir else Path(DEFAULT_CODEX_SESSIONS_DIR).expanduser()
    if not root.is_dir():
        return False

    suffix = f"{session_id}.jsonl"
    stack: list[tuple[Path, int]] = [(root, 0)]
    examined = 0
    while stack:
        current, depth = stack.pop()
        try:
            entries = list(os.scandir(current))
        except OSError:
            continue
        for entry in entries:
            examined += 1
            if examined > _SESSION_SEARCH_MAX_ENTRIES:
                return False
            if entry.is_dir(follow_symlinks=False):
                if depth < _SESSION_SEARCH_MAX_DEPTH:
                    stack.append((Path(entry.path), depth + 1))
                continue
            if entry.name.endswith(suffix):
                return True
    return False


def open_surface(binding: dict, runner, *, codex_sessions_dir: str | None = None) -> dict:
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

    if not _codex_session_exists(codex_sessions_dir, session_id):
        return contract.refused(
            "codex", binding_id, "not_found",
            "the bound session was not found in the local Codex session store",
        )

    result = runner(contract.terminal_launch_argv(command))
    if not isinstance(result, dict) or result.get("timed_out") or result.get("code") != 0:
        return contract.refused("codex", binding_id, "runner_error", "the terminal launch failed")

    return contract.succeeded(
        "codex", binding_id, "launched",
        "launched a Terminal session for the bound session", verified=True,
    )

"""integrations.chairman_surfaces.claude — Claude Code + Claude desktop.

Two unrelated providers share this module because they share almost nothing
except a name: ``claude_code`` resumes a terminal session, ``claude_desktop``
opens a URL/deep-link in the native app.

Native existence gate (Sol review 5000169412, blocker 2)
-----------------------------------------------------------
A ``claude --resume <id>`` command line handed to Terminal.app executes
asynchronously: ``osascript`` returning ``0`` only proves Terminal accepted
the shell line, never that ``claude`` itself found a real session. So
``open_claude_code`` proves the bound session actually exists in the local
Claude Code session store — ``<claude_projects_dir>/<slug>/<session_id>.jsonl``
— BEFORE ever launching Terminal; a valid-shaped but nonexistent session id
refuses ``not_found`` and the runner is never called. Only a proven-existing
session may report ``verified=True``.

The ``<slug>`` mapping was pinned empirically (2026-08-22) from a read-only
listing of a real ``~/.claude/projects`` directory against known real
project paths — see :func:`_slugify_project_dir`.
"""
from __future__ import annotations

import os
import re
import shlex
from pathlib import Path

from . import contract

#: Strict UUID gate for a ``claude_code`` binding's ``session_id``. Matches
#: ``control_plane.surface_bindings``'s own ``_UUID_RE`` (that module
#: already enforces this at write time); this module re-checks it at open
#: time so a binding crafted or mutated outside ``save_bindings`` cannot
#: reach the shell-string builder below with an unsafe value.
SESSION_ID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE
)

#: Default on-disk root of Claude Code's per-project session transcripts.
DEFAULT_CLAUDE_PROJECTS_DIR = "~/.claude/projects"

#: Any character outside this set is folded to ``-`` by
#: :func:`_slugify_project_dir` — see that function's docstring for the
#: empirical evidence.
_SLUG_FOLD_RE = re.compile(r"[^A-Za-z0-9-]")


def _slugify_project_dir(project_dir: str) -> str:
    """Map an absolute project directory to Claude Code's on-disk slug.

    Empirically pinned (2026-08-22) from a read-only ``ls`` of a real
    ``~/.claude/projects`` directory against known real project paths on
    this machine (directory names only — no file contents were read):

      - ``/Users/chriswong/Documents/Cluade/macro-main``
        -> ``-Users-chriswong-Documents-Cluade-macro-main``
      - ``/Users/chriswong/Documents/Cluade/Macro Dashboard/.claude/worktrees/<x>``
        -> ``-Users-chriswong-Documents-Cluade-Macro-Dashboard--claude-worktrees-<x>``
      - ``/Users/chriswong/.openclaw-crestodian-workspace``
        -> ``-Users-chriswong--openclaw-crestodian-workspace``

    Rule: every character OUTSIDE ``[A-Za-z0-9-]`` — path separators, dots,
    spaces — is replaced 1:1 with ``-``; alphanumerics and existing hyphens
    pass through unchanged. This is a 1:1 fold, not a de-duplicating one,
    which is exactly why a leading ``/`` immediately followed by a dotfile's
    leading ``.`` (``/.claude``, ``/.openclaw-...``) produces the doubled
    ``--`` seen in both worktree and dotfile examples above: the ``/`` folds
    to one ``-`` and the ``.`` folds to a second, adjacent ``-``.
    """
    return _SLUG_FOLD_RE.sub("-", project_dir)


def _claude_code_session_exists(claude_projects_dir: str | None, project_dir: str, session_id: str) -> bool:
    """True iff the bound session's transcript file is present on disk."""
    root = Path(claude_projects_dir).expanduser() if claude_projects_dir else Path(DEFAULT_CLAUDE_PROJECTS_DIR).expanduser()
    transcript = root / _slugify_project_dir(project_dir) / f"{session_id}.jsonl"
    return transcript.is_file()


def open_claude_code(binding: dict, runner, *, claude_projects_dir: str | None = None) -> dict:
    """Resume a ``claude_code`` session by launching it in a Terminal tab.

    Shell-string construction law: the ONE sanctioned shell-string site in
    this package is the ``command`` line built below. It is assembled ONLY
    from two triple-gated tokens — ``project_dir`` (charset via
    :func:`contract.safe_abs_dir`, no ``..`` segment, then existence via
    ``os.path.isdir``) and ``session_id`` (charset via :data:`SESSION_ID_RE`)
    — each individually ``shlex.quote``-d before joining. No other string in
    this package is ever built by concatenation into something a shell will
    interpret.

    ``claude_projects_dir`` overrides the local session-store root the
    native existence gate reads (module docstring); ``None`` means the real
    ``~/.claude/projects`` default. The existence check runs BEFORE the
    Terminal launch — a missing transcript refuses ``not_found`` and
    ``runner`` is never invoked.
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

    if not _claude_code_session_exists(claude_projects_dir, project_dir, session_id):
        return contract.refused(
            "claude_code", binding_id, "not_found",
            "the bound session was not found in the local Claude Code session store",
        )

    command = "cd " + shlex.quote(project_dir) + " && " + "claude --resume " + shlex.quote(session_id)
    result = runner(contract.terminal_launch_argv(command))
    if not isinstance(result, dict) or result.get("timed_out") or result.get("code") != 0:
        return contract.refused("claude_code", binding_id, "runner_error", "the terminal launch failed")

    return contract.succeeded(
        "claude_code", binding_id, "launched",
        "launched a Terminal session for the bound session", verified=True,
    )


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

    return contract.succeeded(
        "claude_desktop", binding_id, "opened",
        "the OS was asked to open the bound URL; conversation-level verification is not provable on the installed surface",
        verified=False,
    )

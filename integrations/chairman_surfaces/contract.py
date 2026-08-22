"""integrations.chairman_surfaces.contract — shared vocabulary + dispatch.

Every adapter module (``chatgpt.py``, ``claude.py``, ``cursor.py``,
``codex.py``) imports this module for: the closed-vocabulary capability
states, the ``OpenOutcome`` shape, the token/path safety gates, and the
shared Terminal.app launch mechanism. :func:`open_binding` is the single
public entry point a caller (Wave C UI, tests) uses to navigate to a
binding — it re-validates the binding through
:mod:`control_plane.surface_bindings` (the canonical schema owner) before
ever dispatching to a provider adapter, so a binding that was valid when
written but has since drifted (or was crafted directly, bypassing
``save_bindings``) is still refused-closed here.

Privacy law (frozen by the architecture doc)
---------------------------------------------
No ``OpenOutcome.detail`` string may ever contain a locator value — a URL,
session id, or chat id. Refer to them only as "the bound URL" / "the bound
session" / "the bound chat". This module and every adapter built on it
follow that law; ``tests/test_chairman_surfaces.py`` asserts it against
every outcome the suite produces.
"""
from __future__ import annotations

import re

from control_plane import surface_bindings as _surface_bindings

# ---------------------------------------------------------------------------
# capability / confidence vocabularies
# ---------------------------------------------------------------------------

#: Installed-capability states (:mod:`capability`'s per-provider census).
PROVEN = "PROVEN"
PARTIAL = "PARTIAL"
UNSUPPORTED = "UNSUPPORTED"
NOT_INSTALLED = "NOT_INSTALLED"

CAPABILITY_STATES = (PROVEN, PARTIAL, UNSUPPORTED, NOT_INSTALLED)

#: Per-binding navigation-confidence vocabulary. ``control_plane.
#: surface_bindings`` deliberately carries no state/confidence field of its
#: own (it is a pure navigation cache — see its ``FORBIDDEN_SEMANTIC_KEYS``),
#: so this vocabulary is minted here for this wave's own outcome reporting
#: rather than re-exported.
VERIFIED_OPENABLE = "VERIFIED_OPENABLE"
BOUND_UNVERIFIED = "BOUND_UNVERIFIED"
UNBOUND = "UNBOUND"
STALE = "STALE"
# UNSUPPORTED is shared with the capability vocabulary above (one string).

NAV_CONFIDENCE = (VERIFIED_OPENABLE, BOUND_UNVERIFIED, UNBOUND, STALE, UNSUPPORTED)

# ---------------------------------------------------------------------------
# token / path safety gates (module-level, reused by every adapter)
# ---------------------------------------------------------------------------

#: General-purpose id gate for a session/chat id that is not itself a UUID
#: (cursor_agent ``chat_id``, codex ``session_id``). ``claude_code``'s
#: ``session_id`` uses its own stricter UUID regex, defined in ``claude.py``.
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")

#: Chrome profile directory name gate (e.g. ``"Default"``, ``"Profile 3"``).
SAFE_PROFILE_RE = re.compile(r"^[A-Za-z0-9 ._-]{1,64}$")

_SAFE_ABS_DIR_CHARSET_RE = re.compile(r"^[A-Za-z0-9 ._/-]+$")


def safe_abs_dir(path: object) -> bool:
    """True iff ``path`` is safe to use as an absolute directory string.

    Charset-gated and ``..``-segment-gated only — this never touches the
    filesystem. Callers that also require the directory to actually exist
    combine this with ``os.path.isdir`` themselves (adapters do, so a
    missing-but-otherwise-safe directory reports ``not_found`` rather than
    ``unsafe_token``).
    """
    if not isinstance(path, str) or not path:
        return False
    if len(path) > 512:
        return False
    if not path.startswith("/"):
        return False
    if ".." in path.split("/"):
        return False
    if not _SAFE_ABS_DIR_CHARSET_RE.match(path):
        return False
    return True


# ---------------------------------------------------------------------------
# OpenOutcome
# ---------------------------------------------------------------------------

#: Closed vocabulary of OpenOutcome failure kinds.
FAILURE_KINDS = frozenset({
    "invalid_binding", "unsafe_token", "disallowed_target", "not_installed",
    "not_running", "not_found", "ambiguous", "runner_error", "refused",
})


def _outcome(
    *,
    ok: bool,
    action: str | None,
    provider: str,
    binding_id: str | None,
    detail: str,
    failure_kind: str | None,
) -> dict:
    if failure_kind is not None and failure_kind not in FAILURE_KINDS:
        raise ValueError(f"unknown failure_kind: {failure_kind!r}")
    if ok and failure_kind is not None:
        raise ValueError("a successful outcome must not carry a failure_kind")
    if not ok and action is not None:
        raise ValueError("a refused/failed outcome must not carry an action")
    return {
        "ok": ok,
        "action": action,
        "provider": provider,
        "binding_id": binding_id,
        "detail": detail,
        "failure_kind": failure_kind,
    }


def refused(provider: str, binding_id: str | None, failure_kind: str, detail: str) -> dict:
    """Build a refusal :class:`OpenOutcome`. Never invokes the runner."""
    return _outcome(
        ok=False, action=None, provider=provider, binding_id=binding_id,
        detail=detail, failure_kind=failure_kind,
    )


def succeeded(provider: str, binding_id: str | None, action: str, detail: str) -> dict:
    """Build a successful :class:`OpenOutcome`."""
    return _outcome(
        ok=True, action=action, provider=provider, binding_id=binding_id,
        detail=detail, failure_kind=None,
    )


# ---------------------------------------------------------------------------
# shared Terminal.app launch mechanism (claude_code, cursor_agent, codex)
# ---------------------------------------------------------------------------

#: Fixed AppleScript source shared by every adapter that resumes a session
#: inside a Terminal.app window. The command line it runs is passed in as
#: ``item 1 of argv`` — never interpolated into this constant — so the
#: script text is byte-identical no matter which binding produced the
#: command.
TERMINAL_LAUNCH_APPLESCRIPT = """\
on run argv
    tell application "Terminal"
        activate
        do script (item 1 of argv)
    end tell
end run
"""


def terminal_launch_argv(command: str) -> list[str]:
    """Build the ``osascript`` argv that runs ``command`` in a new Terminal tab.

    ``command`` is appended as the ONLY varying element; every ``-e`` line
    before it comes straight from :data:`TERMINAL_LAUNCH_APPLESCRIPT` and is
    therefore identical across every binding.
    """
    argv = ["osascript"]
    for line in TERMINAL_LAUNCH_APPLESCRIPT.splitlines():
        argv.append("-e")
        argv.append(line)
    argv.append(command)
    return argv


# ---------------------------------------------------------------------------
# dispatch
# ---------------------------------------------------------------------------

#: Provider -> the locator_kind ``control_plane.surface_bindings`` requires
#: for it. This mirrors that module's own (private) provider/locator_kind
#: pairing — duplicated here, rather than reached into as a private
#: attribute, because it is part of the frozen ``v1`` schema and this
#: module's own gate (unknown provider/locator_kind -> ``refused``) must run
#: BEFORE the full document re-validation below (which instead reports
#: ``invalid_binding`` for a known provider carrying a malformed binding).
_EXPECTED_LOCATOR_KIND = {
    "chatgpt": "chatgpt_url",
    "claude_code": "claude_code_session",
    "claude_desktop": "claude_desktop_url",
    "cursor_agent": "cursor_agent_thread",
    "codex": "codex_session",
}


def _revalidate(binding: dict) -> list[str]:
    """Re-validate ``binding`` by wrapping it in a one-binding document."""
    doc = {"schema": _surface_bindings.SCHEMA, "bindings": [binding]}
    return _surface_bindings.validate_bindings_document(doc)


def open_binding(binding: dict, runner) -> dict:
    """Re-validate ``binding`` then dispatch to the owning provider adapter.

    ``runner`` is any callable matching :func:`integrations.chairman_
    surfaces.runner.run_argv`'s signature — always inject a fake in tests,
    never the real one.

    Dispatch order (every step refuses closed, never touching ``runner``,
    before the one that follows it runs):

    1. ``binding`` is not a dict -> ``invalid_binding``.
    2. ``provider`` is not one of the five known providers, or
       ``locator_kind`` does not match what that provider requires ->
       ``refused`` (this is the "unknown provider/locator_kind" case).
    3. The binding fails full re-validation against
       ``control_plane.surface_bindings`` (bad URL host, a smuggled
       lifecycle/authority key, a malformed locator, ...) -> ``invalid_binding``.
    4. Only past all three does the owning adapter ever see the binding or
       the runner.
    """
    if not isinstance(binding, dict):
        return refused("unknown", None, "invalid_binding", "the binding must be an object")

    provider = binding.get("provider")
    binding_id = binding.get("binding_id")
    binding_id = binding_id if isinstance(binding_id, str) else None
    provider_label = provider if isinstance(provider, str) else "unknown"

    expected_kind = _EXPECTED_LOCATOR_KIND.get(provider) if isinstance(provider, str) else None
    if expected_kind is None or binding.get("locator_kind") != expected_kind:
        return refused(provider_label, binding_id, "refused", "unknown provider or locator_kind")

    problems = _revalidate(binding)
    if problems:
        return refused(provider_label, binding_id, "invalid_binding", "the binding failed re-validation")

    # Deferred import: the adapter modules import this module at their own
    # top level (for the gates/outcome helpers above), so importing them
    # back at contract.py's module scope would be circular. Importing here,
    # inside the function body, resolves after all five modules are loaded.
    from . import chatgpt as _chatgpt
    from . import claude as _claude
    from . import codex as _codex
    from . import cursor as _cursor

    if provider == "chatgpt":
        return _chatgpt.open_surface(binding, runner)
    if provider == "claude_code":
        return _claude.open_claude_code(binding, runner)
    if provider == "claude_desktop":
        return _claude.open_claude_desktop(binding, runner)
    if provider == "cursor_agent":
        return _cursor.open_surface(binding, runner)
    if provider == "codex":
        return _codex.open_surface(binding, runner)

    # Unreachable: _EXPECTED_LOCATOR_KIND only contains these five keys, so
    # the `expected_kind is None` check above already caught anything else.
    return refused(provider_label, binding_id, "refused", "unknown provider or locator_kind")

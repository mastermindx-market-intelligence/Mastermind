"""integrations.chairman_surfaces.capability — installed-capability census.

Answers "is this provider even installed here" for the Chairman Control
Room's navigation affordances — a purely local, read-only inspection
(``which``, app-bundle existence, an optional bounded ``--version`` probe).
It never opens, focuses, or launches anything, and it never claims
:data:`contract.PROVEN` — that state means a live navigation action already
succeeded, which is exactly the Wave D concern this module does not touch.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from . import chatgpt as _chatgpt
from . import contract

#: Bounded timeout for the optional ``--version`` probe.
_VERSION_TIMEOUT = 5.0


def _default_app_exists(path: str) -> bool:
    try:
        return Path(path).exists()
    except OSError:
        return False


def _capture_version(runner, argv: list[str]) -> str | None:
    """Best-effort ``--version`` capture. Never raises; ``None`` on any failure."""
    if runner is None:
        return None
    try:
        result = runner(argv, timeout=_VERSION_TIMEOUT)
    except Exception:
        return None
    if not isinstance(result, dict) or result.get("timed_out") or result.get("code") != 0:
        return None
    stdout = (result.get("stdout") or "").strip()
    return stdout or None


def _binary_provider(name: str, binary: str, *, runner, which) -> dict:
    found = which(binary)
    installed = bool(found)
    if not installed:
        return {
            "installed": False,
            "version": None,
            "state": contract.NOT_INSTALLED,
            "detail": f"{binary!r} was not found on PATH",
        }
    version = _capture_version(runner, [found, "--version"])
    return {
        "installed": True,
        "version": version,
        # Census alone never proves a live open/focus/resume succeeded, so
        # an installed binary is PARTIAL, never PROVEN, until a Wave D live
        # navigation action actually verifies it.
        "state": contract.PARTIAL,
        "detail": f"{binary!r} found on PATH; live navigation proof pending Wave D",
    }


def _app_provider(name: str, app_path: str, *, app_exists, detail_installed: str, detail_missing: str) -> dict:
    installed = bool(app_exists(app_path))
    if not installed:
        return {"installed": False, "version": None, "state": contract.NOT_INSTALLED, "detail": detail_missing}
    return {"installed": True, "version": None, "state": contract.PARTIAL, "detail": detail_installed}


def census(runner=None, *, which=shutil.which, app_exists=_default_app_exists) -> dict:
    """Return ``{provider: {installed, version, state, detail}}`` for every
    provider this package knows about, plus ``aionui`` (always
    :data:`contract.UNSUPPORTED` — see below).

    ``runner`` (a callable matching :func:`integrations.chairman_surfaces.
    runner.run_argv`'s signature, or ``None``) is used ONLY for the optional
    ``--version`` probe of a binary that ``which`` already found — an absent
    binary/app never reaches ``runner`` at all, and any probe failure
    (exception, non-zero exit, timeout) degrades ``version`` to ``None``
    rather than raising or changing ``state``.
    """
    result: dict[str, dict] = {}

    # Sol architecture correction (MAS-113, 2026-08-22): chatgpt seats live in
    # managed-browser (GoLogin/Multilogin) environments, never a Chrome
    # profile — "installed" here means "a local managed-browser profile
    # store is present", not "Chrome.app exists". Census alone still never
    # proves PROVEN (integrations.chairman_surfaces.chatgpt.open_surface
    # refuses closed on every path by design; see that module's docstring).
    mlx_root = str(Path(_chatgpt.MLX_PROFILES_ROOT).expanduser())
    gologin_root = str(Path(_chatgpt.GOLOGIN_PROFILES_ROOT).expanduser())
    mlx_present = bool(app_exists(mlx_root))
    gologin_present = bool(app_exists(gologin_root))
    if not mlx_present and not gologin_present:
        result["chatgpt"] = {
            "installed": False,
            "version": None,
            "state": contract.NOT_INSTALLED,
            "detail": "no local GoLogin/Multilogin managed-browser profile store was found",
        }
    else:
        result["chatgpt"] = {
            "installed": True,
            "version": None,
            "state": contract.PARTIAL,
            "detail": (
                "a local managed-browser profile store is present; navigation is refused — "
                "see integrations.chairman_surfaces.chatgpt's managed-environment seat law"
            ),
        }

    result["claude_code"] = _binary_provider("claude_code", "claude", runner=runner, which=which)

    result["claude_desktop"] = _app_provider(
        "claude_desktop", "/Applications/Claude.app", app_exists=app_exists,
        detail_installed="Claude.app is installed; live open proof pending Wave D",
        detail_missing="Claude.app was not found",
    )

    result["cursor_agent"] = _binary_provider("cursor_agent", "cursor-agent", runner=runner, which=which)
    result["codex"] = _binary_provider("codex", "codex", runner=runner, which=which)

    aionui_installed = bool(app_exists("/Applications/AionUi.app"))
    result["aionui"] = {
        "installed": aionui_installed,
        "version": None,
        "state": contract.UNSUPPORTED,
        "detail": (
            "AionUi has no locator_kind in mastermind.surface_bindings.v1 and is "
            "never a navigation target (architecture §6.5, fail-closed by design) "
            "— reported here for visibility only, independent of installation state"
        ),
    }

    return result

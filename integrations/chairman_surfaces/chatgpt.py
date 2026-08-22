"""integrations.chairman_surfaces.chatgpt — ChatGPT (Chrome, named profile).

Seat-exact navigation law (Sol review 5000169412, blocker 1)
--------------------------------------------------------------
The installed Chrome AppleScript automation surface enumerates tabs/windows
by URL only — it has no way to prove which browser PROFILE an already-open
tab belongs to. Focusing "whichever Chrome profile [the URL] happens to be
open in" (the pre-review behavior) can therefore cross the bound seat: the
same exact chat URL open in the WRONG profile, or duplicated across two
profiles, would satisfy the URL match and get treated as the bound seat's
tab regardless of whose profile it actually is.

Because this surface cannot prove tab-level profile identity,
:func:`open_surface` NEVER attempts to focus an existing tab. It always
opens the bound URL through the exact bound Chrome profile via ``open -na
"Google Chrome" --args --profile-directory=<bound profile>`` — the one
navigation primitive this surface CAN prove targets the right seat. macOS's
``open -na`` either raises the existing window for that profile (if Chrome/
that profile is already running) or launches it fresh, so Chrome-running and
Chrome-not-running are the same code path; there is no separate "focus
first, fall back to open" branch to take.

:data:`APPLESCRIPT_FOCUS` and :func:`focus_exact_tab` remain in this module
as the seam a FUTURE surface that CAN prove per-tab profile identity (e.g. a
Chrome extension bridge) would use. :func:`open_surface` never references
either of them; :func:`focus_exact_tab` itself refuses closed today because
no such profile-identity prover exists yet on the installed surface.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import contract

#: Default on-disk location of Chrome's "Local State" file (macOS), which
#: carries the local profile-directory -> display-name map this module reads
#: to validate a bound ``browser_profile`` against real installed profiles.
CHROME_LOCAL_STATE = "~/Library/Application Support/Google/Chrome/Local State"

#: Fixed AppleScript source. Compares each open tab's URL against
#: ``item 1 of argv`` (the bound URL, passed only as a trailing osascript
#: argument — never interpolated into this text) for EXACT string equality.
#: Returns one of: ``"NOT_RUNNING"`` (Chrome isn't running — returned before
#: any ``tell application "Google Chrome"`` block runs, so this script never
#: launches Chrome), ``"NOT_FOUND"`` (Chrome is running, no tab matches), or
#: ``"FOCUSED <n>"`` (the first matching tab, in window/tab order, was
#: focused; ``<n>`` is the number of matches found).
APPLESCRIPT_FOCUS = """\
on run argv
    set targetURL to item 1 of argv
    if application "Google Chrome" is not running then
        return "NOT_RUNNING"
    end if
    tell application "Google Chrome"
        set matchCount to 0
        set matchWindowIndex to -1
        set matchTabIndex to -1
        set winIndex to 0
        repeat with w in windows
            set winIndex to winIndex + 1
            set tabIndex to 0
            repeat with t in tabs of w
                set tabIndex to tabIndex + 1
                if (URL of t as string) is equal to targetURL then
                    set matchCount to matchCount + 1
                    if matchCount is 1 then
                        set matchWindowIndex to winIndex
                        set matchTabIndex to tabIndex
                    end if
                end if
            end repeat
        end repeat
        if matchCount is 0 then
            return "NOT_FOUND"
        end if
        set active tab index of window matchWindowIndex to matchTabIndex
        set index of window matchWindowIndex to 1
        activate
        return "FOCUSED " & matchCount
    end tell
end run
"""


def _focus_argv(url: str) -> list[str]:
    """Build the osascript argv for :data:`APPLESCRIPT_FOCUS`.

    Every ``-e`` line before the trailing ``url`` element comes straight
    from the fixed script text, so this argv is identical across every
    binding except for its last element.
    """
    argv = ["osascript"]
    for line in APPLESCRIPT_FOCUS.splitlines():
        argv.append("-e")
        argv.append(line)
    argv.append(url)
    return argv


def list_profiles(path: str | Path | None = None) -> dict[str, str]:
    """Read Chrome's ``Local State`` and return ``{dir_name: display_name}``.

    Read-only, tolerant of a missing/unreadable/malformed file (returns
    ``{}`` rather than raising) — this is a best-effort local enumeration,
    never a source of canonical identity.
    """
    target = Path(path) if path is not None else Path(CHROME_LOCAL_STATE).expanduser()
    try:
        raw = target.read_text(encoding="utf-8")
    except OSError:
        return {}
    try:
        doc = json.loads(raw)
    except ValueError:
        return {}
    if not isinstance(doc, dict):
        return {}
    profile = doc.get("profile")
    cache = profile.get("info_cache") if isinstance(profile, dict) else None
    if not isinstance(cache, dict):
        return {}

    result: dict[str, str] = {}
    for dir_name, info in cache.items():
        if not isinstance(dir_name, str):
            continue
        display = info.get("name") if isinstance(info, dict) else None
        result[dir_name] = display if isinstance(display, str) and display else dir_name
    return result


def open_in_profile(profile_dir: str, url: str, runner, *, profiles: dict | None = None, binding_id: str | None = None) -> dict:
    """Launch ``url`` in the named Chrome profile via ``open -na ...``.

    ``profile_dir`` must pass :data:`contract.SAFE_PROFILE_RE` AND be
    present in a fresh :func:`list_profiles` enumeration (or the injected
    ``profiles`` mapping, for tests) — both checked BEFORE ``runner`` is
    ever called.
    """
    if not isinstance(profile_dir, str) or not contract.SAFE_PROFILE_RE.match(profile_dir):
        return contract.refused("chatgpt", binding_id, "unsafe_token", "the bound profile directory failed the safety check")

    known_profiles = profiles if profiles is not None else list_profiles()
    if profile_dir not in known_profiles:
        return contract.refused("chatgpt", binding_id, "disallowed_target", "the bound profile directory is not a known Chrome profile")

    if not isinstance(url, str) or not url:
        return contract.refused("chatgpt", binding_id, "invalid_binding", "the bound URL is missing")

    argv = ["/usr/bin/open", "-na", "Google Chrome", "--args", "--profile-directory=" + profile_dir, url]
    result = runner(argv)
    if not isinstance(result, dict) or result.get("timed_out") or result.get("code") != 0:
        return contract.refused("chatgpt", binding_id, "runner_error", "opening the bound URL in the bound profile failed")

    return contract.succeeded(
        "chatgpt", binding_id, "opened",
        "opened via the exact bound profile; focus-by-URL is disabled: the "
        "installed automation surface cannot prove a tab's profile identity",
        verified=False,
    )


def open_surface(binding: dict, runner, *, profiles: dict | None = None) -> dict:
    """Open the bound URL through the exact bound Chrome profile.

    Never attempts to focus an existing tab (see the module docstring's
    seat-exact navigation law) — always dispatches straight to
    :func:`open_in_profile`, whether Chrome (or that profile) is already
    running or not, so the same one primitive covers both cases.

    ``profiles`` is accepted (and passed through to :func:`open_in_profile`)
    purely so tests can inject a fixed profile enumeration instead of
    reading the real ``Local State`` file.
    """
    locator = binding.get("locator") if isinstance(binding, dict) else None
    locator = locator if isinstance(locator, dict) else {}
    binding_id = binding.get("binding_id") if isinstance(binding, dict) else None
    binding_id = binding_id if isinstance(binding_id, str) else None

    profile_dir = locator.get("browser_profile")
    url = locator.get("url")

    if not isinstance(profile_dir, str) or not contract.SAFE_PROFILE_RE.match(profile_dir):
        return contract.refused("chatgpt", binding_id, "unsafe_token", "the bound profile directory failed the safety check")

    known_profiles = profiles if profiles is not None else list_profiles()
    if profile_dir not in known_profiles:
        return contract.refused("chatgpt", binding_id, "disallowed_target", "the bound profile directory is not a known Chrome profile")

    if not isinstance(url, str) or not url:
        return contract.refused("chatgpt", binding_id, "invalid_binding", "the bound URL is missing")

    return open_in_profile(profile_dir, url, runner, profiles=known_profiles, binding_id=binding_id)


def focus_exact_tab(binding: dict, runner, *, profile_prover) -> dict:
    """Focus the bound URL's existing tab — ONLY when its profile is proven.

    ``profile_prover`` is a REQUIRED keyword argument: a callable that, given
    the raw focus-probe result, proves the focused tab belongs to the bound
    ``browser_profile`` — or ``None`` when no such prover exists on the
    installed surface (the current P0 state, always). When
    ``profile_prover`` is ``None`` this refuses closed WITHOUT ever invoking
    ``runner``: focusing an unproven tab is exactly the cross-seat failure
    Sol's review blocked, so the capability is gated off entirely rather than
    left to a caller's discretion. :func:`open_surface` never calls this
    function.
    """
    locator = binding.get("locator") if isinstance(binding, dict) else None
    locator = locator if isinstance(locator, dict) else {}
    binding_id = binding.get("binding_id") if isinstance(binding, dict) else None
    binding_id = binding_id if isinstance(binding_id, str) else None

    if profile_prover is None:
        return contract.refused(
            "chatgpt", binding_id, "refused",
            "focusing an existing tab requires a profile-identity prover "
            "the installed automation surface does not offer",
        )

    profile_dir = locator.get("browser_profile")
    url = locator.get("url")

    if not isinstance(profile_dir, str) or not contract.SAFE_PROFILE_RE.match(profile_dir):
        return contract.refused("chatgpt", binding_id, "unsafe_token", "the bound profile directory failed the safety check")
    if not isinstance(url, str) or not url:
        return contract.refused("chatgpt", binding_id, "invalid_binding", "the bound URL is missing")

    result = runner(_focus_argv(url))
    if not isinstance(result, dict) or result.get("timed_out"):
        return contract.refused("chatgpt", binding_id, "runner_error", "the focus check failed")

    output = (result.get("stdout") or "").strip()
    if not output.startswith("FOCUSED"):
        return contract.refused("chatgpt", binding_id, "not_found", "no matching tab was found to focus")

    if not profile_prover(result):
        return contract.refused(
            "chatgpt", binding_id, "disallowed_target",
            "the focused tab's profile identity could not be proven to match the bound profile",
        )

    return contract.succeeded(
        "chatgpt", binding_id, "focused",
        "focused the bound URL's tab in the proven bound profile",
        verified=True,
    )

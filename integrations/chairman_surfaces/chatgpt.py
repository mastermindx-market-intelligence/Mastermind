"""integrations.chairman_surfaces.chatgpt — ChatGPT (Chrome, named profile).

Navigation strategy: try to focus an already-open tab whose URL exactly
matches the bound URL, in whichever Chrome profile it happens to be open
in; only if Chrome is not running or no matching tab exists do we open the
URL in the specific bound profile with ``open -na ... --profile-directory=``
(never letting AppleScript's ``activate`` launch a default-profile Chrome
window first — see :data:`APPLESCRIPT_FOCUS`, which returns before ever
telling Chrome to do anything when it is not already running).
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

    return contract.succeeded("chatgpt", binding_id, "opened", "opened the bound URL in the bound Chrome profile")


def open_surface(binding: dict, runner, *, profiles: dict | None = None) -> dict:
    """Focus the bound URL's tab if one is open; otherwise open it fresh.

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

    result = runner(_focus_argv(url))
    if not isinstance(result, dict):
        return contract.refused("chatgpt", binding_id, "runner_error", "the focus check returned an unexpected result")
    if result.get("timed_out"):
        return contract.refused("chatgpt", binding_id, "runner_error", "the focus check timed out")

    output = (result.get("stdout") or "").strip()

    if output == "NOT_RUNNING" or output == "NOT_FOUND":
        return open_in_profile(profile_dir, url, runner, profiles=known_profiles, binding_id=binding_id)

    if output.startswith("FOCUSED"):
        parts = output.split()
        count = parts[1] if len(parts) > 1 and parts[1].isdigit() else "1"
        if count != "1":
            detail = f"focused first of {count} duplicate tabs"
        else:
            detail = "focused the bound URL's tab"
        return contract.succeeded("chatgpt", binding_id, "focused", detail)

    return contract.refused("chatgpt", binding_id, "runner_error", "the focus check returned an unexpected result")

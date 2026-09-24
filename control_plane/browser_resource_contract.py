"""Owner-bound browser resource contract for Mastermind browser-capable hosts.

This module is deliberately not a lifecycle, browser-session registry, scheduler,
credential store, or network service. It projects one already-authorized owner
context into one Playwright MCP process and defines when that owned process may
be retired. Existing Executive/Capacity/Workbench/Operator Harness owners remain
authoritative for admission, placement, lease state, effect reconciliation and
process custody.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import PurePosixPath
import re


PLAYWRIGHT_MCP_VERSION = "0.0.79"

ALLOWED_BROWSER_TOOLS = frozenset(
    {
        "browser_click",
        "browser_close",
        "browser_console_messages",
        "browser_fill_form",
        "browser_hover",
        "browser_navigate",
        "browser_network_requests",
        "browser_press_key",
        "browser_select_option",
        "browser_snapshot",
        "browser_tabs",
        "browser_take_screenshot",
        "browser_type",
        "browser_wait_for",
    }
)

_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,127}$")


class BrowserResourceError(ValueError):
    """The requested browser resource cannot be projected safely."""


class BrowserMode(str, Enum):
    ISOLATED = "isolated"
    PERSISTENT = "persistent"


class BrowserCleanupAction(str, Enum):
    KEEP = "keep"
    TERMINATE_OWNED_PROCESS = "terminate_owned_process"
    BLOCK_EFFECT_UNKNOWN = "block_effect_unknown"


@dataclass(frozen=True)
class BrowserResourcePlan:
    lease_ref: str
    owner_context_ref: str
    host_ref: str
    boot_generation: str
    principal_ref: str
    mode: BrowserMode
    profile_ref: str | None
    profile_dir: str | None
    requires_exclusive_profile: bool
    command: str
    argv: tuple[str, ...]
    allowed_tools: frozenset[str]
    playwright_mcp_version: str
    delete_profile_on_release: bool = False


@dataclass(frozen=True)
class BrowserCleanupDecision:
    action: BrowserCleanupAction
    delete_persistent_profile: bool = False


def _safe_ref(value: str, field: str) -> str:
    if not isinstance(value, str) or not _REF.fullmatch(value):
        raise BrowserResourceError(f"{field} is invalid")
    return value


def _absolute_path(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.startswith("/") or "\x00" in value:
        raise BrowserResourceError(f"{field} must be an absolute path")
    path = PurePosixPath(value)
    if ".." in path.parts or str(path) != value.rstrip("/"):
        raise BrowserResourceError(f"{field} is not normalized")
    return value


def build_browser_resource_plan(
    *,
    lease_ref: str,
    owner_context_ref: str,
    host_ref: str,
    boot_generation: str,
    principal_ref: str,
    node_executable: str,
    mcp_cli_path: str,
    chrome_executable: str,
    output_dir: str,
    mode: BrowserMode,
    headed: bool,
    profile_ref: str | None = None,
    profile_dir: str | None = None,
) -> BrowserResourcePlan:
    """Project one owner-issued browser lease into one Playwright MCP process.

    The caller must already own the host/process reservation and, for a persistent
    profile, the exclusive profile reservation. This function accepts no port,
    CDP endpoint, browser-extension attachment, shared browser context, credential,
    proxy, or arbitrary Playwright-code input.
    """
    if not isinstance(mode, BrowserMode):
        raise BrowserResourceError("mode must be a BrowserMode")
    if type(headed) is not bool:
        raise BrowserResourceError("headed must be boolean")

    lease_ref = _safe_ref(lease_ref, "lease_ref")
    owner_context_ref = _safe_ref(owner_context_ref, "owner_context_ref")
    host_ref = _safe_ref(host_ref, "host_ref")
    boot_generation = _safe_ref(boot_generation, "boot_generation")
    principal_ref = _safe_ref(principal_ref, "principal_ref")

    node_executable = _absolute_path(node_executable, "node_executable")
    mcp_cli_path = _absolute_path(mcp_cli_path, "mcp_cli_path")
    chrome_executable = _absolute_path(chrome_executable, "chrome_executable")
    output_dir = _absolute_path(output_dir, "output_dir")

    if not mcp_cli_path.endswith("/node_modules/@playwright/mcp/cli.js"):
        raise BrowserResourceError("mcp_cli_path is not the pinned Playwright MCP entrypoint")

    if mode is BrowserMode.ISOLATED:
        if profile_ref is not None or profile_dir is not None:
            raise BrowserResourceError("isolated resources cannot bind a persistent profile")
        requires_exclusive_profile = False
    else:
        if profile_ref is None or profile_dir is None:
            raise BrowserResourceError("persistent resources require an owner-selected profile")
        profile_ref = _safe_ref(profile_ref, "profile_ref")
        profile_dir = _absolute_path(profile_dir, "profile_dir")
        requires_exclusive_profile = True

    argv = [
        mcp_cli_path,
        "--browser",
        "chrome",
        "--executable-path",
        chrome_executable,
        "--output-dir",
        output_dir,
    ]
    if not headed:
        argv.append("--headless")
    if mode is BrowserMode.ISOLATED:
        argv.append("--isolated")
    else:
        argv.extend(("--user-data-dir", profile_dir))

    forbidden = {
        "--shared-browser-context",
        "--cdp-endpoint",
        "--extension",
        "--allow-unrestricted-file-access",
    }
    if forbidden.intersection(argv):
        raise BrowserResourceError("unsafe browser sharing or attachment requested")

    return BrowserResourcePlan(
        lease_ref=lease_ref,
        owner_context_ref=owner_context_ref,
        host_ref=host_ref,
        boot_generation=boot_generation,
        principal_ref=principal_ref,
        mode=mode,
        profile_ref=profile_ref,
        profile_dir=profile_dir,
        requires_exclusive_profile=requires_exclusive_profile,
        command=node_executable,
        argv=tuple(argv),
        allowed_tools=ALLOWED_BROWSER_TOOLS,
        playwright_mcp_version=PLAYWRIGHT_MCP_VERSION,
    )


def decide_browser_cleanup(
    *,
    owner_state: str,
    effect_state: str,
    tool_call_inflight: bool,
    process_owned: bool,
) -> BrowserCleanupDecision:
    """Return the only lawful local cleanup action for one owned browser process.

    Age, tab count, low CPU, or a missing Web chat are deliberately absent from
    this API. The existing lease/lifecycle owner must first classify the resource
    as released or expired. EFFECT_UNKNOWN remains sticky because destroying the
    browser can erase the best same-carrier reconciliation surface.
    """
    if owner_state not in {"active", "released", "expired"}:
        raise BrowserResourceError("owner_state is invalid")
    if effect_state not in {"NOT_APPLIED", "APPLIED", "EFFECT_UNKNOWN"}:
        raise BrowserResourceError("effect_state is invalid")
    if type(tool_call_inflight) is not bool or type(process_owned) is not bool:
        raise BrowserResourceError("cleanup booleans are invalid")

    if effect_state == "EFFECT_UNKNOWN":
        return BrowserCleanupDecision(BrowserCleanupAction.BLOCK_EFFECT_UNKNOWN)
    if tool_call_inflight or owner_state == "active" or not process_owned:
        return BrowserCleanupDecision(BrowserCleanupAction.KEEP)
    return BrowserCleanupDecision(BrowserCleanupAction.TERMINATE_OWNED_PROCESS)

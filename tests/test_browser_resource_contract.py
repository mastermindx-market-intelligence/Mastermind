from __future__ import annotations

import pytest

from control_plane.browser_resource_contract import (
    ALLOWED_BROWSER_TOOLS,
    BrowserCleanupAction,
    BrowserMode,
    BrowserResourceError,
    build_browser_resource_plan,
    decide_browser_cleanup,
)


def _base(**overrides):
    values = {
        "lease_ref": "lease-0123456789abcdef",
        "owner_context_ref": "workbench-context-0123456789abcdef",
        "host_ref": "mini2",
        "boot_generation": "boot-0123456789abcdef",
        "principal_ref": "worker-0123456789abcdef",
        "node_executable": "/opt/homebrew/bin/node",
        "mcp_cli_path": "/Users/mini2/.local/share/mastermind-browser-control/mcp-runtime/node_modules/@playwright/mcp/cli.js",
        "chrome_executable": "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "output_dir": "/Users/mini2/.local/state/mastermind-browser/output/lease-0123456789abcdef",
        "mode": BrowserMode.ISOLATED,
        "headed": False,
    }
    values.update(overrides)
    return values


def test_isolated_plan_is_one_process_per_lease_and_never_shared():
    plan = build_browser_resource_plan(**_base())
    assert plan.mode is BrowserMode.ISOLATED
    assert plan.requires_exclusive_profile is False
    assert plan.profile_dir is None
    assert "--isolated" in plan.argv
    assert "--shared-browser-context" not in plan.argv
    assert "--cdp-endpoint" not in plan.argv
    assert "--extension" not in plan.argv
    assert "--headless" in plan.argv
    assert plan.command == "/opt/homebrew/bin/node"
    assert plan.argv[0].endswith("/@playwright/mcp/cli.js")
    assert plan.lease_ref == "lease-0123456789abcdef"


def test_persistent_plan_requires_one_owner_selected_profile_and_no_shared_context():
    plan = build_browser_resource_plan(
        **_base(
            mode=BrowserMode.PERSISTENT,
            profile_ref="web-identity-research-01",
            profile_dir="/Users/mini2/.local/share/mastermind-browser-profiles/web-identity-research-01",
        )
    )
    assert plan.requires_exclusive_profile is True
    assert plan.profile_ref == "web-identity-research-01"
    assert plan.profile_dir.endswith("/web-identity-research-01")
    assert "--isolated" not in plan.argv
    assert "--shared-browser-context" not in plan.argv
    assert "--user-data-dir" in plan.argv
    assert plan.argv[plan.argv.index("--user-data-dir") + 1] == plan.profile_dir


@pytest.mark.parametrize(
    "kwargs",
    [
        {"mode": BrowserMode.PERSISTENT},
        {
            "mode": BrowserMode.ISOLATED,
            "profile_ref": "should-not-exist",
            "profile_dir": "/tmp/should-not-exist",
        },
        {"headed": "yes"},
        {"node_executable": "node"},
        {"mcp_cli_path": "cli.js"},
        {"output_dir": "../escape"},
    ],
)
def test_plan_refuses_ambiguous_or_unsafe_inputs(kwargs):
    with pytest.raises(BrowserResourceError):
        build_browser_resource_plan(**_base(**kwargs))


def test_safe_tool_contract_is_granular_but_excludes_rce_and_secret_state():
    expected = {
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
    assert ALLOWED_BROWSER_TOOLS == frozenset(expected)
    forbidden_fragments = ("run_code", "evaluate", "storage_state", "file_upload", "network_state_set")
    assert not any(fragment in tool for fragment in forbidden_fragments for tool in ALLOWED_BROWSER_TOOLS)


def test_release_or_owner_expiry_terminates_owned_browser_process_only():
    for owner_state in ("released", "expired"):
        decision = decide_browser_cleanup(
            owner_state=owner_state,
            effect_state="APPLIED",
            tool_call_inflight=False,
            process_owned=True,
        )
        assert decision.action is BrowserCleanupAction.TERMINATE_OWNED_PROCESS
        assert decision.delete_persistent_profile is False


def test_active_or_inflight_resource_is_not_reaped():
    active = decide_browser_cleanup(
        owner_state="active",
        effect_state="APPLIED",
        tool_call_inflight=False,
        process_owned=True,
    )
    inflight = decide_browser_cleanup(
        owner_state="released",
        effect_state="APPLIED",
        tool_call_inflight=True,
        process_owned=True,
    )
    assert active.action is BrowserCleanupAction.KEEP
    assert inflight.action is BrowserCleanupAction.KEEP


def test_effect_unknown_blocks_cleanup_even_after_expiry():
    decision = decide_browser_cleanup(
        owner_state="expired",
        effect_state="EFFECT_UNKNOWN",
        tool_call_inflight=False,
        process_owned=True,
    )
    assert decision.action is BrowserCleanupAction.BLOCK_EFFECT_UNKNOWN


def test_cleanup_never_kills_an_unowned_chrome_process():
    decision = decide_browser_cleanup(
        owner_state="released",
        effect_state="NOT_APPLIED",
        tool_call_inflight=False,
        process_owned=False,
    )
    assert decision.action is BrowserCleanupAction.KEEP

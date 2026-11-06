"""Shared synthetic optional-policy preparation for gateway owner tests."""
from __future__ import annotations

import json
import stat

from ops.executive_os import autonomy_control as control
from tests import test_os_gateway_publication_owner as incumbent


def replace_fixture(path, raw, mode=None):
    """Synthetic fixture preparation or an explicit modeled outside mutation."""
    selected_mode = stat.S_IMODE(path.stat().st_mode) if mode is None else mode
    path.chmod(0o600)
    path.write_bytes(raw)
    path.chmod(selected_mode)


def add_existing_mounts(s):
    from integrations.business_mcp_auth.contracts import load_resource_policy
    from ops.executive_os.workspace_owner_enrollment import compile_control_room_action_bindings
    from integrations.mastermind_workspace_app.contract import CONTROL_ROOM_ACTIONS

    value = json.loads(s.mcp_bytes)
    workspace = value["workspace"]
    workspace["bindings"] = compile_control_room_action_bindings(
        load_resource_policy(workspace["policy"]), workspace["bindings"], {
            name: {action: (b"TESTDATA action: " + action.encode() if slot["enabled"] else None)
                   for action in CONTROL_ROOM_ACTIONS}
            for name, slot in workspace["bindings"]["profiles"].items()
        },
    )
    subjects = workspace["policy"]["allowed_subject_digests"]
    value["steward"] = {
        "policy": incumbent._policy(policy_id="steward-dormant", subjects=subjects,
            resource="https://mcp.mastermind-x.com/mcp/steward/v1", scopes=["mastermind.steward.read"]),
        "content_policy": incumbent._policy(policy_id="content", subjects=subjects,
            resource="https://mcp.mastermind-x.com/workspace/window/current",
            scopes=["mastermind.workspace.content.read"]),
        "content_profiles": {"schema": "mastermind.executive_content_profiles.v1", "profiles": {
            "web": {"enabled": False, "profile": None}, "mac": {"enabled": False, "profile": None}}},
        "allowed_origin": "https://mcp.mastermind-x.com",
    }
    s.mcp_bytes = control._encoded_json(value)
    replace_fixture(control.OS_GATEWAY_MCP_CONFIG, s.mcp_bytes)

"""Finite, model-free qualification of the original Hermes MCP client owners.

Run only in the separately pinned Hermes SDK process. The sole input is a
disposable test fixture; no model, live Paperclip run, plugin grant or native
origin is manufactured. This module does not import the Mastermind App.
"""
from __future__ import annotations

import asyncio
import hashlib
from importlib.metadata import version
import json
import logging
import os
from pathlib import Path
import sys
import time
from urllib.parse import urlsplit


NATIVE_REF = "ba4ddf9945a213ede9dda016602a86591ed634f9"
ALIAS = "mastermindExecutiveCoo"
PINS = {
    "tools/tool_search.py": "bcaf4ed695a5493fdda421f7c969db5a6fd9cf06d8ad92a8cb546c3326f52866",
    "tools/tool_search_validation.py": "97d327a0c122a66023b570919ab9cdf968e4737fa16652283811ce8278079cc0",
    "hermes_cli/tools_config.py": "c35d87a2abe61c12e065a9aa1126cae0e948b7c6d3f93c8cf1541efd9630ccc0",
    "toolsets.py": "9aed91987f1403b02df22997491b90fedcf2516756a0f7ab9b6c245d5f769159",
    "model_tools.py": "24850d5ce74f7bcf17e58638fc787d6b955bfb89f4980e74b361d7927de74581",
    "hermes_cli/mcp_startup.py": "1d36dc9ff5ba0d8f7a51b366aa7799a94316fc04c486a9252315ff5d4d034be6",
    "tools/mcp_tool.py": "19059b5aadcaee0ac1ec8fbbfbaf30d090397dfdc92cf729e755e2221363d60e",
    "tools/mcp_tool_scope.py": "da50fa6b9704f535f296657604ff41679ef9e0d0e85154beb7a30a2da63eaac5",
    "tools/mcp_tool_config.py": "02d05318c60b5f203610185e9ca152ec15276420d3d11060cbbef206cd651797",
    "tools/mcp_tool_transport.py": "4d2fc8bb580e9a292ee9314da9cc13a7b929b583f83f751dfd97e543688426cb",
    "tools/mcp_tool_server_run.py": "fc05e142e0dedc888e9dfe78c8044cfe4a55de874799c31ffd17d47b4c5fb712",
    "tools/mcp_tool_lifecycle.py": "c73b3c7de2e69a70ddbfc88681678cc30ec14de86a4b93203bc3203b99672bf1",
    "tools/mcp_tool_discovery.py": "8e9efe1680968c5ee121a576a8cc3548d64a3e47da8e51c72632a8c353de6bb1",
    "tools/mcp_tool_handlers.py": "f29475bde493fb93f55ca16ca53a845b703f87b851ba85770a90f3b5369c58b7",
    "tools/mcp_oauth_manager.py": "5574bca545ba6507e3b30ead7c89a37962a1e87adaf04040d141eeb592ec1bea",
    "tools/mcp_oauth.py": "b25655d6a2ca717b3697f2fe98b5f817da5605c203ebdce8823da55398a8b99f",
}


def checked_inputs(path):
    value = json.loads(path.read_bytes())
    assert set(value) == {"url", "home", "source", "token", "issuer", "scopes", "work_ref",
                          "command", "root_job_id", "job_id", "ack_action", "boundary", "report"}
    url = urlsplit(value["url"])
    assert url.scheme == "http" and url.hostname == "127.0.0.1" and url.port
    assert url.path == "/mcp/coo" and not (url.query or url.fragment or url.username or url.password)
    home, source = Path(value["home"]).resolve(strict=True), Path(value["source"]).resolve(strict=True)
    assert Path(os.environ["HERMES_HOME"]).resolve(strict=True) == home
    assert value["boundary"] in {"normal", "lost_response"}
    for name, digest in PINS.items():
        assert hashlib.sha256((source / name).read_bytes()).hexdigest() == digest, name
    assert version("mcp") == "2.3.0"
    assert version("httpx2") == version("httpcore2") == "2.15.1"
    assert "integrations.mastermind_executive_app.coo" not in sys.modules
    return value, home, source


def main():
    value, home, source = checked_inputs(Path(sys.argv[1]))
    from hermes_constants import set_hermes_home_override, reset_hermes_home_override
    from hermes_cli.mcp_startup import ensure_mcp_discovery_before_agent_build
    from tools import mcp_tool
    from tools.mcp_tool_lifecycle import shutdown_mcp_servers
    from tools.mcp_oauth import HermesTokenStorage, OAuthNonInteractiveError, suppress_interactive_oauth
    from tools.mcp_oauth_manager import get_manager
    from tools.mcp_tool_scope import _resolve_server_key
    from tools.registry import registry
    from model_tools import handle_function_call, get_tool_definitions
    from hermes_cli.tools_config import _get_platform_tools
    from toolsets import session_disabled_toolsets, resolve_toolset
    from mcp.shared.auth import OAuthMetadata, OAuthToken

    assert Path(sys.modules["tools.mcp_tool"].__file__).resolve() == source / "tools/mcp_tool.py"
    assert Path(sys.modules["model_tools"].__file__).resolve() == source / "model_tools.py"
    assert not mcp_tool._servers
    config = {"platform_toolsets": {"cli": [ALIAS]}, "mcp_servers": {ALIAS: {"url": value["url"], "auth": "oauth", "oauth": {"client_id": "inert-client"},
        "trust": "full"}}}
    (home / "config.yaml").write_text(json.dumps(config))
    storage = HermesTokenStorage(ALIAS, hermes_home=home)
    storage.bind_issuer(value["issuer"])
    asyncio.run(storage.set_tokens(OAuthToken(access_token=value["token"], token_type="Bearer",
        expires_in=3600, scope=" ".join(value["scopes"]))))
    # This is the original owner's cached metadata path. The disposable
    # bearer is current, so this proof neither refreshes nor opens a login.
    issuer = value["issuer"].rstrip("/")
    storage.save_oauth_metadata(OAuthMetadata(issuer=value["issuer"],
        authorization_endpoint=issuer + "/authorize", token_endpoint=issuer + "/token",
        response_types_supported=["code"], grant_types_supported=["authorization_code", "refresh_token"],
        code_challenge_methods_supported=["S256"]))
    calls = []

    def invoke(name, arguments):
        calls.append({"tool": name, "action": arguments.get("action")})
        # This is the ordinary model-visible dispatcher. Keep all native
        # pre/post hooks and request/execution middleware enabled.
        rendered = handle_function_call("tool_call",
            {"calls": [{"name": name, "arguments": arguments}]},
            enabled_toolsets=enabled_toolsets, disabled_toolsets=disabled_toolsets)
        rendered = json.loads(rendered) if type(rendered) is str else rendered
        assert type(rendered) is dict
        if "error" in rendered:
            return rendered
        assert type(rendered.get("result")) is str
        return json.loads(rendered["result"])

    try:
        # The ordinary chat -q/one-shot pre-agent call site, unchanged.
        ensure_mcp_discovery_before_agent_build(logger=logging.getLogger(__name__), single_query=True)
        key = _resolve_server_key(ALIAS)
        current = mcp_tool._servers.get(key)
        assert current is not None and current.session is not None, "original native discovery did not connect"
        assert current._auth_type == "oauth", "original OAuth owner was not selected"
        names = tuple(current._registered_tool_names)
        assert len(names) == 9, "joint catalogue did not reach native registry"
        helper = next(name for name in names if name.endswith("executive_project_help"))
        requester = next(name for name in names if name.endswith("mmx_delegate"))
        assert value["ack_action"] in repr(registry.get_entry(requester).schema)
        # The exact discovered server toolset reaches the normal model schema
        # compiler; no hand-built catalogue or direct registry-only path.
        enabled_toolsets = sorted(_get_platform_tools(config, "cli"))
        disabled_toolsets = session_disabled_toolsets(None, "cli", oneshot=True)
        assert requester in {name for toolset in enabled_toolsets for name in resolve_toolset(toolset)}
        definitions = get_tool_definitions(enabled_toolsets=enabled_toolsets,
            disabled_toolsets=disabled_toolsets, quiet_mode=True)
        model_names = [item["function"]["name"] for item in definitions]
        assert {"tool_search", "tool_describe", "tool_call"} <= set(model_names)
        assert requester not in model_names and helper not in model_names
        described = json.loads(handle_function_call("tool_describe",
            {"names": [requester, helper]}, enabled_toolsets=enabled_toolsets,
            disabled_toolsets=disabled_toolsets))
        assert set(described["tools"]) == {requester, helper}
        for name in (requester, helper):
            assert described["tools"][name]["parameters"] == registry.get_entry(name).schema["parameters"]
        assert value["ack_action"] in repr(described["tools"][requester]["parameters"])
        for relative in PINS:
            module = sys.modules.get(relative[:-3].replace("/", "."))
            assert module is not None and Path(module.__file__).resolve() == source / relative, relative
        assert mcp_tool._tool_read_only_hints[key]["mmx_delegate"] is False
        original = get_manager().get_or_build_provider(ALIAS, value["url"], {"client_id": "inert-client"})
        assert original._hermes_home == str(home)
        assert asyncio.run(storage.get_tokens()).access_token == value["token"]

        missing = invoke(helper, {"work_ref": value["work_ref"]})
        assert "error" in missing and "authority_refused" in str(missing), "help accepted missing Workspace authority"

        # The same process's real routed-profile owner must not lend either
        # its cached credential or its already-connected same-alias session.
        sibling = home.parent / "ungranted-sibling-profile"
        sibling.mkdir(mode=0o700)
        (sibling / "config.yaml").write_text(json.dumps(config))
        token = set_hermes_home_override(sibling)
        try:
            assert asyncio.run(HermesTokenStorage(ALIAS, hermes_home=sibling).get_tokens()) is None
            with suppress_interactive_oauth():
                try:
                    get_manager().get_or_build_provider(ALIAS, value["url"], {"client_id": "inert-client"})
                except OAuthNonInteractiveError:
                    pass
                else:
                    raise AssertionError("ungranted sibling borrowed OAuth custody")
            assert _resolve_server_key(ALIAS) not in mcp_tool._servers
            sibling_result = invoke(requester, {"action": "selected_child_status", "command": value["command"]})
            assert "error" in sibling_result
        finally:
            reset_hermes_home_override(token)
        assert get_manager().get_or_build_provider(ALIAS, value["url"], {"client_id": "inert-client"}) is original

        submitted = invoke(requester, {"action": "selected_child_submit", "command": value["command"]})
        assert submitted.get("state") in {"ACTIVE", "COMPLETED"}, "original submit did not qualify"
        until = time.monotonic() + 10.0
        while True:
            observed = invoke(requester, {"action": "selected_child_status", "command": value["command"]})
            if observed.get("state") == "COMPLETED":
                break
            assert observed.get("state") == "ACTIVE" and time.monotonic() < until, "original result did not settle"
            time.sleep(0.05)
        descriptor = observed["requester_return"]
        assert descriptor["consumption"] is None
        assert descriptor["root_job_id"] == value["root_job_id"] and descriptor["job_id"] == value["job_id"]
        assert descriptor["command_id"] == value["command"]
        # Explicit test invocation after reviewing the original descriptor.
        acknowledged = invoke(requester, {"action": value["ack_action"],
            "command": value["command"], "result": descriptor})
        expected = "EFFECT_UNKNOWN" if value["boundary"] == "lost_response" else "COMPLETED"
        assert acknowledged.get("state") == expected, "acknowledgment classifier changed"
        # Reconcile only the original command; never resend the write after
        # response loss. Native readOnlyHint=False must preserve that fence.
        final = invoke(requester, {"action": "selected_child_status", "command": value["command"]})
        assert final.get("state") == "COMPLETED" and final["requester_return"]["consumption"] is not None
        assert len([call for call in calls if call["action"] == "selected_child_submit"]) == 1
        assert len([call for call in calls if call["action"] == value["ack_action"]]) == 1
        report = {"native_ref": NATIVE_REF, "native_sdk": version("mcp"), "native_httpx": version("httpx2"),
            "native_tool_timeout": current.tool_timeout,
            "entry": "ensure_mcp_discovery_before_agent_build(single_query=True)",
            "dispatch": "model_tools.handle_function_call(tool_call; default guards and middleware)",
            "toolset_selection": "hermes_cli.tools_config._get_platform_tools + session_disabled_toolsets(oneshot=True)",
            "enabled_toolsets": enabled_toolsets, "disabled_toolsets": disabled_toolsets,
            "described_tools": sorted(described["tools"]),
            "native_schema_source_patch": {"path": "tools/tool_search.py",
                "base_sha256": "87e06c029304dae1ff1f592fa97f238165a04f1406cbdab68a2e3a0c3fd489a5",
                "post_sha256": PINS["tools/tool_search.py"], "installed": False},
            "registered_tools": list(names), "model_visible_tools": model_names,
            "missing_workspace_refused": True, "sibling_profile_refused": True,
            "submit": submitted, "reviewed_descriptor": descriptor, "acknowledgment": acknowledged,
            "final": final, "explicit_calls": calls, "native_origin_attested": False}
    finally:
        shutdown_mcp_servers(timeout=5.0)
    report["original_native_owner_closed"] = not mcp_tool._servers
    assert report["original_native_owner_closed"]
    Path(value["report"]).write_text(json.dumps(report, sort_keys=True, indent=2) + "\n")
    print(json.dumps({"native_ref": NATIVE_REF, "native_sdk": version("mcp"),
        "acknowledgment_state": report["acknowledgment"]["state"], "native_owner_closed": True}), flush=True)


if __name__ == "__main__":
    main()

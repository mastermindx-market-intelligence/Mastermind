#!/usr/bin/env python3
"""Exercise actual MCP SDK/stdio and existing native read-only tool owners.

Disposable synthetic thread attribution is explicitly NOT a live T3 agent.
No provider inference, application controls, permission grants or profile edits.
"""
from __future__ import annotations
import argparse
import asyncio
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from integrations.t3_harness.runtime import SCHEMA, SOURCE_FILES, encode
from integrations.t3_harness.native_launch import executable_digest
from integrations.session_bridge.project_task_context import parse_plan, contract_digest


def body(result):
    if type(result.structured_content) is dict:
        return result.structured_content
    for item in result.content:
        if getattr(item, "type", None) == "text":
            try:
                value = json.loads(item.text)
                if type(value) is dict:
                    return value
            except ValueError:
                pass
    return {}


async def qualify(args):
    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client
    checks, observations = [], {}
    descriptor = Path(args.browser_descriptor)
    source_hashes = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in SOURCE_FILES}
    plan_path = "docs/plans/2026-11-09-claude-t3-long-horizon.md"
    plan = parse_plan((ROOT / plan_path).read_bytes())
    sid = "qualification-t3-mcp-not-a-live-model-thread"
    config = {"schema": SCHEMA, "source_root": str(ROOT), "source_files": source_hashes,
              "browser_descriptor": str(descriptor), "browser_descriptor_sha256": hashlib.sha256(descriptor.read_bytes()).hexdigest(),
              "namespace": "t3:qualification", "local_browser_only": True, "session_bindings": {
                  sid: {"workspace_root": str(ROOT), "plan_path": plan_path, "workstream": plan["workstream"],
                        "plan_contract_sha256": contract_digest(plan)}}}
    if args.peekaboo:
        selected = Path(args.peekaboo).resolve(strict=True)
        config["peekaboo"] = {"executable": str(selected), "executable_sha256": executable_digest(selected),
                              "bridge_socket": args.bridge_socket}
    with tempfile.TemporaryDirectory(prefix="mmx-t3-mcp-qualification-") as scratch:
        path = Path(scratch) / "runtime.json"; raw = encode(config);path.write_bytes(raw)
        params = StdioServerParameters(command=sys.executable, args=["-I", "-B", str(ROOT / "integrations/t3_harness/native_launch.py"), "browser",
            "--config", str(path), "--expected-config-sha256", hashlib.sha256(raw).hexdigest()],
            env={"HOME": str(Path.home()), "PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "T3CODE_THREAD_ID": sid})
        async with asyncio.timeout(90):
            async with stdio_client(params) as (reader, writer):
                async with ClientSession(reader, writer) as session:
                    init = await session.initialize();catalog = await session.list_tools()
                    assert init.server_info.name == "mastermind-t3-harness"
                    assert {t.name for t in catalog.tools} == {"mmx_browser", "mmx_project_context"}
                    checks.append("real_mcp_sdk_initialize_and_closed_tool_discovery")
                    context = await session.call_tool("mmx_project_context", {})
                    projected = body(context)
                    assert not context.is_error and projected["state"] == "OBSERVED"
                    assert projected["project"]["requirements"] == plan["requirements"]
                    assert projected["native_action"] == "NONE" and projected["mission_accepted"] is False
                    checks.append("real_stdio_round_trip_retains_all_bound_requirements")
                    inventory = await session.call_tool("mmx_browser", {"action": "browsers"})
                    value = body(inventory);assert not inventory.is_error and value["state"] == "OBSERVED"
                    observations["enrolled_browser_count_not_live_count"] = len(value["browsers"])
                    checks.append("incumbent_browser_inventory_through_actual_mcp_process")
                    if args.browser_id:
                        status = await session.call_tool("mmx_browser", {"action": "status", "browser_id": args.browser_id,
                                                                       "host_ref": args.browser_host})
                        value = body(status);receipt = value.get("receipt") or {};data = receipt.get("data") or {}
                        observations["selected_browser"] = {"state": value.get("state"), "reason": value.get("reason"),
                            "receipt_status": receipt.get("status"), "connection_observed": bool(data.get("connection_id")),
                            "controls_enabled": data.get("control_enabled"), "screenshot_enabled": data.get("screenshot_enabled"),
                            "version": data.get("package_version")}
                        if value.get("state") == "RECEIPT" and receipt.get("status") == "OK":
                            checks.append("selected_existing_chrome_extension_connection_observed")
                            if args.exercise_browser:
                                from scripts.t3_browser_journey import exercise
                                journey = await exercise(session, {"browser_id": args.browser_id,
                                    "host_ref": args.browser_host}, data, Path(args.operation_log))
                                observations["owned_browser_journey"] = journey
                                checks.extend(journey["checks"])
                    if args.peekaboo:
                        peek_params = StdioServerParameters(command=sys.executable,
                            args=["-I", "-B", str(ROOT / "integrations/t3_harness/native_launch.py"), "peekaboo",
                                  "--config", str(path), "--expected-config-sha256", hashlib.sha256(raw).hexdigest()],
                            env={"HOME": str(Path.home()), "PATH": "/usr/bin:/bin", "T3CODE_THREAD_ID": sid,
                                 "ANTHROPIC_API_KEY": "fixture-must-not-be-forwarded"})
                        async with stdio_client(peek_params) as (pr, pw):
                            async with ClientSession(pr, pw) as ps:
                                pi = await ps.initialize(); pc = await ps.list_tools()
                                assert pi.server_info.name == "peekaboo-mcp"
                                assert {"see", "analyze", "permissions"} <= {t.name for t in pc.tools}
                                assert (await ps.call_tool("permissions", {})).is_error is not True
                                checks.append("fixed_peekaboo_launcher_real_mcp_round_trip")
                    # Revocation of the original descriptor, not a new project assignment.
                    path.write_bytes(raw + b"\n")
                    revoked = await session.call_tool("mmx_project_context", {})
                    assert revoked.is_error and body(revoked)["reason"] == "INSTALL_BINDING_CHANGED"
                    checks.append("native_mcp_read_observes_config_revocation")
    if args.peekaboo:
        assert args.bridge_socket and Path(args.bridge_socket).is_socket()
        params = StdioServerParameters(command=args.peekaboo, args=["mcp", "serve", "--bridge-socket", args.bridge_socket],
            env={"HOME": str(Path.home()), "PATH": "/opt/homebrew/bin:/usr/bin:/bin"})
        async with asyncio.timeout(45):
            async with stdio_client(params) as (reader, writer):
                async with ClientSession(reader, writer) as session:
                    init = await session.initialize();catalog = await session.list_tools()
                    names = {t.name for t in catalog.tools}
                    assert init.server_info.name == "peekaboo-mcp" and {"see", "image", "click", "type", "permissions", "analyze"} <= names
                    observations["peekaboo"] = {"version": init.server_info.version, "tool_count": len(names),
                        "catalog_sha256": hashlib.sha256(encode({"tools": [t.model_dump(mode="json", by_alias=True) for t in catalog.tools]})).hexdigest()}
                    checks.append("real_peekaboo_mcp_discovery_on_original_bridge_owner")
                    permissions = await session.call_tool("permissions", {})
                    assert permissions.is_error is not True
                    checks.append("native_peekaboo_permissions_read_round_trip")
                    if args.t3_bundle_id:
                        windows = await session.call_tool("window", {"action": "list", "app": args.t3_bundle_id})
                        assert windows.is_error is not True
                        checks.append("native_peekaboo_targeted_t3_window_read")
    assert source_hashes == {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in SOURCE_FILES}
    status = "PASS" if not args.exercise_browser or observations.get("owned_browser_journey", {}).get("state") == "PASS" else "PARTIAL"
    return {"schema": "mastermind.t3_harness_mcp_qualification.v1", "status": status,
            "scope": "REAL_MCP_PROTOCOL_AND_NATIVE_READ_ONLY_OWNERS_WITH_DISPOSABLE_THREAD_ATTRIBUTION",
            "mcp_sdk_version": importlib.metadata.version("mcp"), "source_sha256": source_hashes,
            "browser_descriptor_sha256": config["browser_descriptor_sha256"], "checks": checks,
            "observations": observations, "provider_calls": 0, "live_t3_agent_consumption": "UNPROVEN",
            "production_provider_configuration_changed": False, "browser_or_desktop_mutations": "OWNED_FIXTURE_TAB_ONLY" if args.exercise_browser else 0,
            "mission_accepted": False}


def main():
    if not __debug__:
        raise SystemExit("Qualification requires enabled assertions")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--browser-descriptor", required=True)
    parser.add_argument("--browser-id")
    parser.add_argument("--browser-host", default="m2")
    parser.add_argument("--peekaboo")
    parser.add_argument("--bridge-socket")
    parser.add_argument("--t3-bundle-id")
    parser.add_argument("--exercise-browser", action="store_true")
    parser.add_argument("--operation-log")
    args = parser.parse_args()
    if args.exercise_browser and (not args.browser_id or not args.operation_log):
        parser.error("Browser journey requires exact selected browser and new operation log")
    print(json.dumps(asyncio.run(qualify(args)), sort_keys=True))


if __name__ == "__main__":
    main()

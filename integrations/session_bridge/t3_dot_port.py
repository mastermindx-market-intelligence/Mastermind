"""Fixed stdin/stdout entrypoint selected by the installed Studio account owner.

Not a general shell, MCP server, background service or worker-submission shim.
Only the closed T3DotTools catalog is exposed, over the existing native owner.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import signal
import sys

from .t3_cli_transport import _decode
from .t3_dot_native_owner import NativeDotFleetOwner, read_profile
from .t3_native_client import Unavailable, Rejected
from .t3_dot_tools import T3DotTools, TOOLS, MAX_BYTES


def emit(value):
    raw = json.dumps(value, ensure_ascii=True, allow_nan=False, separators=(",", ":"))
    if len(raw.encode()) > MAX_BYTES:
        raise ValueError("Result exceeds typed port limit")
    print(raw, flush=True)


async def execute(profile_path: str, profile_sha256: str, frame: dict) -> dict:
    if (type(frame) is not dict or set(frame) != {"schema", "principal_key", "tool", "arguments"}
            or frame["schema"] != "mastermind.t3_dot_call.v1" or type(frame["principal_key"]) is not str
            or type(frame["tool"]) is not str or type(frame["arguments"]) is not dict):
        return T3DotTools._failure("INVALID_ARGUMENT", "CLOSED_PORT_FRAME_REQUIRED")
    profile = read_profile(profile_path, profile_sha256)
    owner = NativeDotFleetOwner(profile,
        current_profile=lambda: read_profile(profile_path, profile_sha256))
    try:
        result = await T3DotTools(owner).call(frame["principal_key"], frame["tool"], frame["arguments"])
    except asyncio.CancelledError:
        modifying = any(tool["name"] == frame["tool"] and not tool["annotations"]["readOnlyHint"] for tool in TOOLS)
        status = "EFFECT_UNKNOWN" if modifying and owner.runner.last_effect is not None else "UNAVAILABLE"
        result = T3DotTools._failure(status, "OWNED_PORT_CANCELLED", operation=frame["tool"],
            operation_id=frame["arguments"].get("operation_id"), environment_id=frame["arguments"].get("environment_id"),
            project_id=frame["arguments"].get("project_id"), thread_id=frame["arguments"].get("thread_id"))
    if result["status"] == "EFFECT_UNKNOWN":
        result["native_helper"] = owner.runner.last_effect
        result["original_connection_id"] = profile["connection_id"]
        result["local_environment_id"] = profile["local_environment_id"]
    return result


async def execute_with_shutdown(profile_path, profile_sha256, frame):
    """Cancel this invocation on SIGTERM so its existing runner cleans its helper.

    Native run termination is NOT inferred from helper cancellation. The fixed
    gateway still retains effect uncertainty if this process cannot return.
    """
    loop = asyncio.get_running_loop()
    task = asyncio.create_task(execute(profile_path, profile_sha256, frame))
    installed = False
    try:
        try:
            loop.add_signal_handler(signal.SIGTERM, task.cancel)
            installed = True
        except (NotImplementedError, RuntimeError):
            pass
        return await task
    finally:
        if installed:
            loop.remove_signal_handler(signal.SIGTERM)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile")
    parser.add_argument("--profile-sha256")
    parser.add_argument("--catalog", action="store_true")
    args = parser.parse_args(argv)
    if args.catalog:
        if args.profile or args.profile_sha256:
            parser.error("Catalog export accepts no runtime profile")
        emit({"tools": TOOLS})
        return 0
    if not args.profile or not args.profile_sha256:
        parser.error("An installed exact profile is required")
    try:
        raw = sys.stdin.buffer.read(MAX_BYTES + 1)
        frame = _decode(raw.decode("utf-8"), MAX_BYTES)
        result = asyncio.run(execute_with_shutdown(args.profile, args.profile_sha256, frame))
    except (ValueError, TypeError, OSError, UnicodeError, Unavailable, Rejected):
        # Input/profile failures happen before execute dispatches a native action.
        result = T3DotTools._failure("UNAVAILABLE", "INSTALLED_PROFILE_OR_INPUT_UNAVAILABLE")
    emit(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

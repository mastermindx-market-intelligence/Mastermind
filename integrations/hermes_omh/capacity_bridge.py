#!/usr/bin/env python3
"""Hermes read-only MCP view of the existing Mastermind Fabric Capacity owner.

No credential access, model inference, admission, requests, reservations or retries.
Fabric remains the sole router, lifecycle and quota owner.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

import yaml

ROOT = (Path.home() / ".claude/projects/-Users-chriswong-Documents-Cluade-Macro-Dashboard"
        / "handoff_kits/meta-ceo-b-2026-09-08")
POOLS = ROOT / "orch/fabric/pools.yaml"
FABRIC = ROOT / "ext/fabric_task.py"
REPO_ROOT = Path(__file__).resolve().parents[2]
#: Shared routing-law lane per canonical complexity (the stdio caller states
#: a fabric task class/complexity; the law's option ladder is derived from
#: the complexity, per the OQ-10 re-point of this tool onto route_preview).
ROUTE_OPTION_BY_COMPLEXITY = {
    "C0_MECHANICAL": "mechanical", "C1_ROUTINE_BOUNDED": "routine",
    "C2_COMPLEX_BOUNDED": "hard", "C3_FRONTIER_JUDGMENT": "frontier",
}
CLASSES = frozenset(("execute", "fix_build", "mechanical", "review", "census",
                     "audit", "verify", "build", "high_level", "architecture",
                     "integration", "domain_orchestration", "orchestration"))
COMPLEXITIES = frozenset(("C0_MECHANICAL", "C1_ROUTINE_BOUNDED",
                          "C2_COMPLEX_BOUNDED", "C3_FRONTIER_JUDGMENT"))
FIELDS = frozenset(("pool", "model", "mode", "host", "state", "reason",
                    "reserved", "selection_rechecked_at_request"))


def catalog() -> dict:
    if not POOLS.is_file() or POOLS.stat().st_size > 65536:
        raise ValueError("FABRIC_POLICY_UNAVAILABLE")
    data = yaml.safe_load(POOLS.read_text(encoding="utf-8"))
    pools = data.get("pools") if isinstance(data, dict) else None
    if not isinstance(pools, dict):
        raise ValueError("FABRIC_POLICY_INVALID")
    found = []
    for name, entry in sorted(pools.items()):
        if not isinstance(name, str) or not re.fullmatch(r"[a-z0-9_-]{1,32}", name):
            continue
        if not isinstance(entry, dict):
            continue
        models = []
        for field in ("models", "worker_models", "default_model", "review_model"):
            value = entry.get(field)
            if isinstance(value, str):
                models.append(value)
            elif isinstance(value, dict):
                for slot, obj in value.items():
                    if isinstance(obj, str):
                        models.append(obj)
                    elif isinstance(obj, dict):
                        item = obj.get("model") or obj.get("id") or obj.get("name")
                        if isinstance(item, str):
                            models.append(item)
            elif isinstance(value, list):
                for obj in value:
                    if isinstance(obj, str):
                        models.append(obj)
                    elif isinstance(obj, dict):
                        item = obj.get("model") or obj.get("id") or obj.get("name")
                        if isinstance(item, str):
                            models.append(item)
        models = sorted({v for v in models if re.fullmatch(r"[A-Za-z0-9._:/-]{1,100}", v)})
        found.append({"pool": name, "models": models[:24]})
    return {"source": "existing Mastermind Fabric pools.yaml",
            "status": "CONFIGURED_NOT_AVAILABILITY_PROOF",
            "pools": found, "count": len(found),
            "safety": "Read-only; admission, quota and jobs remain with Fabric"}


# Only classify the incumbent owner's closed diagnostic. Raw stderr never
# crosses the native MCP boundary and cannot become model-visible prose.
_HOST_BLOCKERS = frozenset(("automatic-qualification", "cpu", "disk",
    "lane-ceiling", "load", "memory", "pressure", "reachable", "thermal", "tools"))
_NO_HOST_PREFIX = "NONE reason=no eligible remote mode on requested host blockers="


def _preview_refusal_code(returncode: int, diagnostic: str) -> str:
    generic = "FABRIC_PREVIEW_REFUSED"
    if returncode != 75 or not isinstance(diagnostic, str) or len(diagnostic) > 8192:
        return generic
    line = diagnostic.strip()
    if not line.startswith(_NO_HOST_PREFIX):
        return generic
    blocks = line[len(_NO_HOST_PREFIX):].split(",")
    if not 1 <= len(blocks) <= 64:
        return generic
    for block in blocks:
        host, separator, reasons = block.partition(":")
        values = reasons.split("+")
        if (not separator or not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", host)
                or not values or len(values) != len(set(values))
                or any(value not in _HOST_BLOCKERS for value in values)):
            return generic
    return "FABRIC_PREVIEW_NO_ELIGIBLE_REMOTE_HOST"


def shared_route_preview(task: str, complexity: str) -> dict:
    """The shared Mastermind routing-law preview (WO-07 ``route_preview``).

    Re-pointed per OQ-10: this stdio tool's routing answer now comes from the
    Executive host's read-only ``route_preview`` composition, not from a
    second independent preview. Still no reservation, dispatch or spend; if
    the shared law is unavailable or refuses, the whole preview refuses.
    """
    root = str(REPO_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)
    try:
        from integrations.executive_mcp.route_preview import compose
        return compose({"route_option": ROUTE_OPTION_BY_COMPLEXITY[complexity],
                        "goal": task})
    except Exception:
        raise ValueError("ROUTE_PREVIEW_SOURCE_UNAVAILABLE") from None


def preview(arguments: dict) -> dict:
    task = arguments.get("task_class")
    complexity = arguments.get("complexity", "C1_ROUTINE_BOUNDED")
    pool = arguments.get("pool")
    if task not in CLASSES or complexity not in COMPLEXITIES:
        raise ValueError("FABRIC_PREVIEW_ARGUMENTS_INVALID")
    composition = shared_route_preview(task, complexity)
    effective_complexity = composition.get("effective_complexity") if isinstance(composition, dict) else None
    if not isinstance(effective_complexity, str) or effective_complexity not in COMPLEXITIES:
        raise ValueError("FABRIC_PREVIEW_EFFECTIVE_COMPLEXITY_INVALID")
    allowed = {row["pool"] for row in catalog()["pools"]}
    if pool is not None and pool not in allowed:
        raise ValueError("FABRIC_PREVIEW_POOL_NOT_CONFIGURED")
    if not FABRIC.is_file():
        raise ValueError("FABRIC_OWNER_UNAVAILABLE")
    args = ["/opt/homebrew/bin/python3", str(FABRIC), "preview",
            "--id", "hermes-ro-" + uuid.uuid4().hex,
            "--class", task, "--task-complexity", effective_complexity]
    if pool is not None:
        args += ["--pool", pool]
    try:
        # Keep stderr anonymous and bounded when reading; never retain or emit it.
        with tempfile.TemporaryFile(mode="w+t", encoding="utf-8", errors="replace") as errors:
            proc = subprocess.run(args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                  stderr=errors, text=True, timeout=15)
            errors.seek(0)
            diagnostic = errors.read(8193)
    except (OSError, subprocess.TimeoutExpired):
        raise ValueError("FABRIC_PREVIEW_UNAVAILABLE") from None
    if proc.returncode != 0:
        raise ValueError(_preview_refusal_code(proc.returncode, diagnostic))
    line = proc.stdout.strip().splitlines()[-1:] or [""]
    try:
        result = json.loads(line[0])
    except (ValueError, TypeError):
        return {"state": "NO_ELIGIBLE_ROUTE", "reason": "Fabric returned no selectable route",
                "reserved": False}
    if not isinstance(result, dict):
        raise ValueError("FABRIC_PREVIEW_INVALID_RESPONSE")
    result = {key: val for key, val in result.items() if key in FIELDS
              and isinstance(val, (str, int, bool, float, type(None)))}
    result = {**result, "proof": "PREVIEW_ONLY_NO_RESERVATION_OR_DISPATCH",
              # OQ-10 re-point: the routing answer is the shared law's
              # RoutePreview.v1; the owner's placement columns stay the
              # existing Fabric owner's.
              "authority": composition["authority"],
              "route_preview": composition}
    return result


TOOLS = [
    {"name": "fabric_capacity_catalog",
     "description": "Read-only metadata of Mastermind Subagent Fabric pools and model names. Does not establish live availability, authenticate models or start work.",
     "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"name": "fabric_route_preview",
     "description": "Ask the shared Mastermind routing law (route_preview) and the existing Subagent Fabric owner for one NON-RESERVING route/capacity preview; never submits, dispatches or spends.",
     "inputSchema": {"type": "object", "properties": {
         "task_class": {"type": "string", "enum": sorted(CLASSES)},
         "complexity": {"type": "string", "enum": sorted(COMPLEXITIES),
                        "default": "C1_ROUTINE_BOUNDED"},
         "pool": {"type": "string", "description": "Optional exact known Fabric pool"},
         }, "required": ["task_class"], "additionalProperties": False}},
]


def reply(identity, result=None, error=None):
    response = {"jsonrpc": "2.0", "id": identity}
    if error is not None:
        response["error"] = {"code": -32601, "message": error}
    else:
        response["result"] = result
    sys.stdout.write(json.dumps(response, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def handle(message):
    if not isinstance(message, dict) or "id" not in message:
        return
    method = message.get("method")
    identity = message["id"]
    params = message.get("params") or {}
    if method == "initialize":
        req_version = params.get("protocolVersion", "2025-03-26")
        version = req_version if req_version in (
            "2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25") else "2025-03-26"
        return reply(identity, {"protocolVersion": version,
                                "capabilities": {"tools": {"listChanged": False}},
                                "serverInfo": {"name": "mmx-fabric-capacity-readonly",
                                               "version": "1.1.0"}})
    if method == "ping":
        return reply(identity, {})
    if method == "tools/list":
        return reply(identity, {"tools": TOOLS})
    if method == "tools/call":
        if not isinstance(params, dict):
            return reply(identity, {"isError": True,
                                    "content": [{"type": "text", "text": "INVALID_CALL"}]})
        name = params.get("name")
        args = params.get("arguments") or {}
        try:
            if not isinstance(args, dict):
                raise ValueError("INVALID_ARGUMENTS")
            if name == "fabric_capacity_catalog":
                output = catalog()
            elif name == "fabric_route_preview":
                output = preview(args)
            else:
                raise ValueError("UNKNOWN_READ_ONLY_TOOL")
            result = {"isError": False,
                      "content": [{"type": "text", "text": json.dumps(output, sort_keys=True)}]}
        except Exception as exc:
            code = str(exc) if isinstance(exc, ValueError) else "READ_ONLY_OWNER_UNAVAILABLE"
            result = {"isError": True, "content": [{"type": "text", "text": code}]}
        return reply(identity, result)
    return reply(identity, error="METHOD_NOT_SUPPORTED")


if __name__ == "__main__":
    for raw_line in sys.stdin:
        if len(raw_line) > 16384:
            continue
        try:
            handle(json.loads(raw_line))
        except (ValueError, TypeError):
            continue

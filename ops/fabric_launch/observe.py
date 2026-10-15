"""Bounded read-only probes; no credential copying, installation or inference.

The result describes only this process/host and the exact successful read. It is
not the future worker's effective tool census, authorization or an admission token.
"""
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import urllib.error
import urllib.request

from ops.fabric_launch.context import OBSERVATION_SCHEMA, digest, text, TOOLS, parse as parse_json

ENDPOINTS = {
    "openai-docs": "https://developers.openai.com/mcp",
    "studio-read": "https://m2studio.taila6eca1.ts.net/studio-fabric",
}
MAX_RESPONSE = 256 * 1024


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError("PROBE_REDIRECT_REFUSED")


class ReadOnlyMcpProbe:
    """A transient probe of two fixed existing services, never a tool gateway."""
    def __init__(self, service):
        self.url = ENDPOINTS[service]
        self.headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
        self.opener = urllib.request.build_opener(NoRedirect())

    def call(self, method, params, identifier):
        request = urllib.request.Request(self.url, data=json.dumps({
            "jsonrpc": "2.0", "id": identifier, "method": method, "params": params,
        }).encode(), headers=self.headers, method="POST")
        with self.opener.open(request, timeout=10) as response:
            body = response.read(MAX_RESPONSE + 1)
            session = response.headers.get("Mcp-Session-Id")
        if len(body) > MAX_RESPONSE:
            raise ValueError("PROBE_RESPONSE_TOO_LARGE")
        if session:
            self.headers["Mcp-Session-Id"] = session
        raw = body.decode("utf-8")
        if raw.startswith("event:") or raw.startswith("data:"):
            raw = next(line[6:] for line in raw.splitlines() if line.startswith("data: "))
        value = parse_json(raw.encode("utf-8"), MAX_RESPONSE)
        # A response for another request, malformed JSON-RPC envelope or primitive
        # result is not evidence that this exact read succeeded. No retry follows.
        if (value.get("jsonrpc") != "2.0"
                or type(value.get("id")) is not int
                or value["id"] != identifier
                or "error" in value
                or type(value.get("result")) is not dict):
            raise ValueError("PROBE_PROTOCOL_ERROR")
        return value["result"]

    def observe(self):
        initialized = self.call("initialize", {
            "protocolVersion": "2025-03-26", "capabilities": {},
            "clientInfo": {"name": "mastermind-worker-readiness", "version": "1.0.0"},
        }, 1)
        result = self.call("tools/list", {}, 2)
        tools = result.get("tools", [])
        if not isinstance(tools, list) or len(tools) > 100:
            raise ValueError("PROBE_TOOL_LIST_INVALID")
        return initialized, tools


def observe(mission_ref, workspace, *, repository=None, services=()):
    """Report exact local evidence; unavailable remote/privileged tools stay unknown."""
    text(mission_ref, 192)
    cwd = Path(workspace).resolve(strict=True)
    if not cwd.is_dir():
        raise ValueError("WORKSPACE_NOT_DIRECTORY")
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    scope_ref = "local:" + socket.gethostname() + ":" + str(cwd)
    rows = {}
    def add(name, state, evidence):
        rows[name] = {"tool": name, "state": state, "observed_at": now,
                      "evidence_ref": evidence}
    def run(name, argv):
        try:
            p = subprocess.run(argv, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               timeout=10, check=False)
            if len(p.stdout) + len(p.stderr) > MAX_RESPONSE:
                add(name, "UNKNOWN", "local-probe:output-bound")
            elif p.returncode == 0:
                add(name, "CALLABLE", "local-read-probe:" + digest(p.stdout + p.stderr))
            else:
                add(name, "UNKNOWN", "local-read-probe:nonzero:" + str(p.returncode))
        except FileNotFoundError:
            add(name, "MISSING", "local-read-probe:executable-missing")
        except (OSError, subprocess.TimeoutExpired):
            add(name, "UNKNOWN", "local-read-probe:unavailable")
    try:
        with os.scandir(cwd) as stream:
            next(stream, None)
        add("workspace.read", "CALLABLE", "local-read-probe:workspace-directory")
    except OSError:
        add("workspace.read", "UNKNOWN", "local-read-probe:workspace-unreadable")
    run("python.run", [sys.executable, "-I", "-S", "-c", "import sys;print(sys.version_info[:3])"])
    run("git.read", ["git", "rev-parse", "HEAD"])
    if shutil.which("node"):
        run("node.run", ["node", "--version"])
    else:
        add("node.run", "MISSING", "local-read-probe:node-missing")
    if repository is not None:
        import re
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
            raise ValueError("REPOSITORY_INVALID")
        run("github.read", ["gh", "api", "repos/" + repository, "--jq", ".full_name"])
    for service in services:
        if service not in ENDPOINTS:
            raise ValueError("SERVICE_NOT_REGISTERED")
        target = "docs.search" if service == "openai-docs" else "studio.read"
        try:
            probe = ReadOnlyMcpProbe(service)
            initialized, tools = probe.observe()
            names = {row.get("name") for row in tools}
            # This probes the advertised *read* action, not merely server reachability.
            action = "search_openai_docs" if service == "openai-docs" else "studio_ping"
            if action not in names:
                add(target, "MISSING", "mcp-read-probe:required-tool-absent")
                continue
            args = {"query": "skills"} if service == "openai-docs" else {}
            result = probe.call("tools/call", {"name": action, "arguments": args}, 3)
            if result.get("isError") is True:
                add(target, "UNKNOWN", "mcp-read-probe:tool-error")
                continue
            encoded = json.dumps(result, sort_keys=True).encode()
            add(target, "CALLABLE", "mcp-read-probe:" + action + ":" + digest(encoded))
        except urllib.error.HTTPError as exc:
            state = "AUTH_REQUIRED" if exc.code == 401 else "DENIED" if exc.code == 403 else "UNKNOWN"
            add(target, state, "mcp-read-probe:http:" + str(exc.code))
        except (ValueError, OSError, StopIteration, KeyError, TypeError):
            add(target, "UNKNOWN", "mcp-read-probe:unavailable")
    # Never manufacture write, auth, browser, child-dispatch or memory privileges.
    for name in sorted(TOOLS - rows.keys()):
        add(name, "UNKNOWN", "not-probed:requires-exact-owner-evidence")
    return {"schema": OBSERVATION_SCHEMA, "mission_ref": mission_ref,
            "scope_ref": scope_ref, "items": list(rows.values())}

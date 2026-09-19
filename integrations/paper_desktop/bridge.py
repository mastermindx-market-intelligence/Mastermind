"""Bounded Paper Desktop client. No credentials, listener, queue or retry owner.

The CLI is dependency-free (Python 3.9+); the MCP projection uses the official SDK.
Paper itself owns documents. Executive/approved interactive clients own authorization.
"""
from __future__ import annotations

import argparse
import base64
import contextlib
import fcntl
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import stat
import sys
import time
from typing import Any

VERSION = "0.1.0"
ENDPOINT = "http://127.0.0.1:29979/mcp"
MAX_BYTES = 16 * 1024 * 1024
MAX_REQUEST = 512 * 1024
READ_TOOLS = frozenset({
    "get_basic_info", "get_selection", "get_node_info", "get_children",
    "get_tree_summary", "get_screenshot", "get_jsx", "get_computed_styles",
    "get_fill_image", "get_font_family_info", "get_guide", "list_files",
    "find_nodes", "get_tokens", "list_comment_threads", "get_comment_thread",
    "list_comment_thread_authors",
})
EDIT_TOOLS = frozenset({
    "create_artboard", "write_html", "set_text_content", "rename_nodes",
    "duplicate_nodes", "move_nodes", "update_styles", "finish_working_on_nodes",
    "create_page", "create_tokens", "set_tokens", "set_comment_thread_status",
})
# Native export can write arbitrary host paths; delete can destroy a whole document.
# Neither is exposed. Screenshots/JSX use explicit private artifact saving instead.


class Refusal(RuntimeError):
    def __init__(self, code: str, detail: str = "") -> None:
        self.code, self.detail = code, detail
        super().__init__(code)


def encode(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(encode(value)).hexdigest()


def load_json(value: str | bytes) -> Any:
    def unique(pairs):
        result = {}
        for key, item in pairs:
            if key in result:
                raise Refusal("DUPLICATE_JSON_KEY")
            result[key] = item
        return result
    try:
        return json.loads(value, object_pairs_hook=unique,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise Refusal("INVALID_JSON") from exc


def private_dir(path: Path) -> Path:
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise Refusal("PRIVATE_DIRECTORY_REQUIRED")
    return path


def state_root() -> Path:
    # Fixed per OS principal, not per workspace, so separate clients share the mutex.
    return private_dir(Path.home() / ".local" / "state" / "mastermind-paper")


@contextlib.contextmanager
def desktop_lock(root: Path | None = None):
    root = private_dir(root) if root else state_root()
    fd = os.open(root / "desktop.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1 or info.st_mode & 0o077:
            raise Refusal("UNSAFE_LOCK_FILE")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise Refusal("DESKTOP_BUSY", "Another bridge call owns this desktop; no call sent.") from exc
        yield
    finally:
        os.close(fd)


class PaperClient:
    """Fixed loopback transport; handles JSON and bounded SSE, never follows redirects.

    No proxy environment, cookies, caller URL, automatic retries or event reconnection.
    Tests inject a transport; production cannot select another host or port.
    """
    def __init__(self, timeout: float = 20.0):
        self.timeout = max(1.0, min(float(timeout), 60.0))
        self.session_id = None
        self.protocol = None
        self.counter = 0
        self.server = None

    def rpc(self, method: str, params: dict | None = None, *, notification=False) -> dict:
        self.counter += 1
        request = {"jsonrpc": "2.0", "method": method, "params": params or {}}
        if not notification:
            request["id"] = self.counter
        body = encode(request)
        if len(body) > MAX_REQUEST:
            raise Refusal("REQUEST_TOO_LARGE")
        headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        if self.protocol:
            headers["MCP-Protocol-Version"] = self.protocol
        connection = http.client.HTTPConnection("127.0.0.1", 29979, timeout=self.timeout)
        deadline = time.monotonic() + self.timeout
        try:
            connection.request("POST", "/mcp", body=body, headers=headers)
            response = connection.getresponse()
            if response.status != 200 and not (notification and response.status == 202):
                code = {401: "UPSTREAM_AUTH_REQUIRED", 403: "UPSTREAM_FORBIDDEN", 429: "UPSTREAM_RATE_LIMITED"}.get(response.status, "UPSTREAM_HTTP_ERROR")
                raise Refusal(code, "HTTP %d; no redirect or retry performed." % response.status)
            session_id = response.getheader("Mcp-Session-Id")
            if session_id:
                if not re.fullmatch(r"[\x21-\x7e]{1,256}", session_id):
                    raise Refusal("INVALID_SESSION_HEADER")
                if self.session_id and session_id != self.session_id:
                    raise Refusal("SESSION_CHANGED")
                self.session_id = session_id
            if notification:
                return {}
            content_type = response.getheader("Content-Type", "").split(";")[0].strip()
            if content_type == "text/event-stream":
                payload = self._sse(response, request["id"], deadline)
            elif content_type == "application/json":
                raw = bytearray()
                while True:
                    if time.monotonic() >= deadline:
                        raise Refusal("RESPONSE_DEADLINE")
                    chunk = response.read1(min(65536, MAX_BYTES - len(raw) + 1))
                    if not chunk:
                        break
                    raw.extend(chunk)
                    if len(raw) > MAX_BYTES:
                        raise Refusal("RESPONSE_TOO_LARGE")
                payload = load_json(bytes(raw))
            else:
                raise Refusal("UNSUPPORTED_CONTENT_TYPE")
            if not isinstance(payload, dict) or payload.get("jsonrpc") != "2.0" or payload.get("id") != request["id"]:
                raise Refusal("INVALID_RPC_RESPONSE")
            if "error" in payload:
                raise Refusal("UPSTREAM_RPC_ERROR", "Inspect Paper; upstream error text is not authority.")
            result = payload.get("result")
            if not isinstance(result, dict):
                raise Refusal("INVALID_RPC_RESULT")
            return result
        except (OSError, http.client.HTTPException) as exc:
            raise Refusal("UPSTREAM_UNAVAILABLE", "Paper must be running with a file open. Login state is unknown.") from exc
        finally:
            connection.close()

    def _sse(self, response, request_id, deadline):
        size, parts, buffer = 0, [], b""
        while time.monotonic() < deadline:
            chunk = response.read1(min(65536, MAX_BYTES - size + 1))
            size += len(chunk)
            if size > MAX_BYTES:
                raise Refusal("RESPONSE_TOO_LARGE")
            if not chunk:
                break
            buffer += chunk
            while b"\n" in buffer:
                line, buffer = buffer.split(b"\n", 1)
                if line.strip() == b"":
                    if parts:
                        item = load_json(b"\n".join(parts))
                        parts = []
                        if isinstance(item, dict) and item.get("id") == request_id:
                            return item
                elif line.startswith(b"data:"):
                    parts.append(line[5:].lstrip(b" ").rstrip(b"\r"))
        raise Refusal("INCOMPLETE_SSE_RESPONSE")

    def initialize(self):
        result = self.rpc("initialize", {"protocolVersion": "2025-03-26", "capabilities": {},
            "clientInfo": {"name": "mastermind-paper", "version": VERSION}})
        self.protocol = result.get("protocolVersion")
        if self.protocol not in {"2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25", "2026-07-28"}:
            raise Refusal("UNSUPPORTED_PROTOCOL")
        self.server = result.get("serverInfo")
        self.rpc("notifications/initialized", notification=True)
        return result

    def catalog(self):
        tools, cursor, seen = [], None, set()
        for _ in range(8):
            page = self.rpc("tools/list", {"cursor": cursor} if cursor else {})
            chunk = page.get("tools")
            if not isinstance(chunk, list):
                raise Refusal("INVALID_CATALOG")
            tools.extend(chunk)
            if len(tools) > 128:
                raise Refusal("CATALOG_TOO_LARGE")
            cursor = page.get("nextCursor")
            if not cursor:
                break
            if not isinstance(cursor, str) or cursor in seen:
                raise Refusal("CATALOG_CURSOR_INVALID")
            seen.add(cursor)
        else:
            raise Refusal("CATALOG_TOO_LARGE")
        result = {}
        for tool in tools:
            if not isinstance(tool, dict) or not isinstance(tool.get("name"), str) or tool["name"] in result:
                raise Refusal("INVALID_CATALOG")
            result[tool["name"]] = tool
        return result

    def call(self, name, arguments):
        return self.rpc("tools/call", {"name": name, "arguments": arguments})


def _basic_candidates(result):
    values = []
    structured = result.get("structuredContent")
    if isinstance(structured, dict):
        values.append(structured)
    for block in result.get("content", []):
        if not isinstance(block, dict) or block.get("type") != "text":
            continue
        try:
            value = load_json(block.get("text", ""))
        except Refusal:
            continue
        if isinstance(value, dict):
            values.append(value)
    return values


def _stable_file(value):
    file_id = value.get("fileId") or value.get("documentId")
    file_name = value.get("fileName")
    nested = value.get("file")
    if not file_id and isinstance(nested, dict):
        file_id = nested.get("id")
        if not file_name:
            file_name = nested.get("name")
    if isinstance(file_id, str) and file_id:
        return file_id, file_name if isinstance(file_name, str) and file_name else None
    return None


def basic_object(result):
    if result.get("isError"):
        raise Refusal("DOCUMENT_UNAVAILABLE")
    values = _basic_candidates(result)
    if not values:
        raise Refusal("DOCUMENT_SCHEMA_UNVERIFIED", "get_basic_info must return a JSON object; do not guess fields.")
    stable = [item for item in (_stable_file(value) for value in values) if item]
    file_ids = {item[0] for item in stable}
    if len(file_ids) > 1:
        raise Refusal("DOCUMENT_SCHEMA_UNVERIFIED", "get_basic_info returned conflicting file identities.")
    file_id = next(iter(file_ids), None)
    details = [value for value in values
               if isinstance(value.get("fileName"), str) and value.get("fileName")
               and isinstance(value.get("pageName"), str) and value.get("pageName")
               and isinstance(value.get("artboards"), list)]
    if details:
        names = {value["fileName"] for value in details}
        pages = {(value.get("pageId"), value["pageName"]) for value in details}
        if len(names) != 1 or len(pages) != 1:
            raise Refusal("DOCUMENT_SCHEMA_UNVERIFIED", "get_basic_info returned conflicting document detail.")
        info = dict(max(details, key=lambda value: len(value)))
        stable_names = {name for _, name in stable if name}
        if stable_names and (len(stable_names) != 1 or info["fileName"] not in stable_names):
            raise Refusal("DOCUMENT_SCHEMA_UNVERIFIED", "File header and document detail disagree.")
        if file_id:
            info["fileId"] = file_id
        hashes = [value.get("contentHash") for value in values if isinstance(value.get("contentHash"), dict)]
        if hashes:
            encoded = {encode(value) for value in hashes}
            if len(encoded) != 1:
                raise Refusal("DOCUMENT_SCHEMA_UNVERIFIED", "get_basic_info returned conflicting content hashes.")
            info["contentHash"] = hashes[0]
        return info
    if file_id:
        info = dict(values[0])
        info["fileId"] = file_id
        if stable[0][1] and not info.get("fileName"):
            info["fileName"] = stable[0][1]
        return info
    raise Refusal("DOCUMENT_SCHEMA_UNVERIFIED", "get_basic_info returned no supported document identity.")


def document_identity(info):
    file_id = info.get("fileId") or info.get("documentId")
    nested = info.get("file")
    if not file_id and isinstance(nested, dict):
        file_id = nested.get("id")
    if isinstance(file_id, str) and file_id:
        return {"kind": "file-id", "id": file_id}
    name, page, boards = info.get("fileName"), info.get("pageName"), info.get("artboards")
    if not isinstance(name, str) or not name or not isinstance(page, str) or not isinstance(boards, list):
        raise Refusal("DOCUMENT_SCHEMA_UNVERIFIED")
    ids = sorted(b["id"] for b in boards if isinstance(b, dict) and isinstance(b.get("id"), str) and b["id"])
    if not ids:
        raise Refusal("DOCUMENT_ANCHOR_REQUIRED", "Create one starter artboard in the intended Paper file, then inspect again.")
    return {"kind": "artboard-anchor", "file": name, "page": page, "anchor": ids[0]}


def snapshot(client):
    info = basic_object(client.call("get_basic_info", {}))
    try:
        identity = document_identity(info)
        bind_error = None
    except Refusal as exc:
        identity, bind_error = None, exc.code
    return {"basic_info": info, "identity": identity, "snapshot_sha256": digest(info),
            "write_binding_ready": identity is not None, "binding_error": bind_error}


def same_document(identity, info):
    if identity["kind"] == "file-id":
        try:
            current = document_identity(info)
        except Refusal:
            return False
        return current.get("kind") == "file-id" and current.get("id") == identity["id"]
    return (info.get("fileName") == identity["file"] and info.get("pageName") == identity["page"]
            and any(isinstance(b, dict) and b.get("id") == identity["anchor"] for b in info.get("artboards", [])))


def execute(action: str, *, tool: str | None = None, arguments: dict | None = None,
            expected_snapshot: str | None = None, operation_id: str | None = None,
            allow_write=False, client=None, lock_root=None):
    """One serialized operation. Snapshot hash is a drift guard, NOT authorization.

    Local edits outside this adapter can race; no transaction/isolation claim is made.
    No persistent duplicate/retry ledger is introduced. Caller owns effect reconciliation.
    """
    if action not in {"status", "catalog", "read", "edit"}:
        raise Refusal("UNKNOWN_ACTION")
    if arguments is None:
        arguments = {}
    if not isinstance(arguments, dict) or len(encode(arguments)) > MAX_REQUEST - 1024:
        raise Refusal("INVALID_ARGUMENTS")
    editing = action == "edit"
    if editing:
        if not allow_write:
            raise Refusal("WRITE_DISABLED")
        if tool not in EDIT_TOOLS:
            raise Refusal("TOOL_NOT_ALLOWED")
        if not isinstance(operation_id, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,120}", operation_id):
            raise Refusal("OPERATION_ID_REQUIRED")
        if not isinstance(expected_snapshot, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_snapshot):
            raise Refusal("SNAPSHOT_REQUIRED")
    elif action == "read" and tool not in READ_TOOLS:
        raise Refusal("TOOL_NOT_ALLOWED")
    client = client or PaperClient()
    with desktop_lock(lock_root):
        client.initialize()
        if action == "status":
            return {"state": "CONNECTED", "server": client.server, "endpoint": ENDPOINT,
                    "document": snapshot(client), "quota_remaining": None, "plan": "UNKNOWN"}
        catalog = client.catalog()
        if action == "catalog":
            return {"server": client.server, "tools": [dict(catalog[n], bridge_access=("read" if n in READ_TOOLS else "edit"))
                    for n in sorted(catalog) if n in READ_TOOLS | EDIT_TOOLS],
                    "blocked_tools": sorted(set(catalog) - READ_TOOLS - EDIT_TOOLS),
                    "catalog_sha256": digest(catalog)}
        if tool not in catalog:
            raise Refusal("TOOL_NOT_AVAILABLE")
        before = snapshot(client) if editing or expected_snapshot else None
        if before and before["snapshot_sha256"] != expected_snapshot:
            raise Refusal("DOCUMENT_CHANGED", "Read the current document before deciding on a new edit.")
        if editing and not before["write_binding_ready"]:
            raise Refusal(before["binding_error"] or "DOCUMENT_BINDING_REQUIRED")
        if editing and before["identity"]["kind"] == "file-id":
            supplied_file = arguments.get("fileId")
            if supplied_file is None:
                raise Refusal("FILE_ID_REQUIRED", "Pass the exact inspected Paper file ID for every edit.")
            if supplied_file != before["identity"]["id"]:
                raise Refusal("FILE_ID_MISMATCH", "Edit target does not match the inspected Paper file.")
        if editing and tool == "set_tokens":
            updates = arguments.get("tokens")
            if isinstance(updates, list) and any(isinstance(item, dict) and item.get("delete") is True for item in updates):
                raise Refusal("TOKEN_DELETE_NOT_ALLOWED", "Delete tokens only through an explicitly reviewed destructive workflow.")
        # Paper validates its current input schema. A dispatched tool error may be partial.
        try:
            result = client.call(tool, arguments)
        except Exception as exc:
            if editing:
                return {"state": "EFFECT_UNKNOWN", "operation_id": operation_id, "tool": tool,
                        "before": before, "retry_allowed": False, "reason": "RESPONSE_NOT_OBSERVED"}
            raise
        if not editing:
            return {"state": "TOOL_ERROR" if result.get("isError") else "OBSERVED", "result": result}
        if result.get("isError"):
            return {"state": "EFFECT_UNKNOWN", "operation_id": operation_id, "tool": tool,
                    "result": result, "before": before, "retry_allowed": False, "reason": "UPSTREAM_TOOL_ERROR_MAY_BE_PARTIAL"}
        try:
            after = snapshot(client)
            matched = same_document(before["identity"], after["basic_info"])
        except Exception:
            after, matched = None, False
        return {"state": "APPLIED_RESPONSE_OBSERVED" if matched else "EFFECT_UNKNOWN",
                "operation_id": operation_id, "tool": tool, "result": result,
                "before": before, "after": after, "retry_allowed": False,
                "production_acceptance": False}


def save_artifacts(value: dict, directory: Path):
    """Save only returned PNG/JPEG images and JSON; no server-selected host paths."""
    directory = private_dir(directory)
    copied = json.loads(json.dumps(value))
    paths = []
    result = copied.get("result", {})
    for block in result.get("content", []):
        if block.get("type") != "image":
            continue
        suffix = {"image/png": "png", "image/jpeg": "jpg"}.get(block.get("mimeType"))
        if not suffix:
            raise Refusal("UNSUPPORTED_IMAGE_TYPE")
        try:
            raw = base64.b64decode(block["data"], validate=True)
        except (KeyError, ValueError) as exc:
            raise Refusal("INVALID_IMAGE") from exc
        if len(raw) > MAX_BYTES or not (raw.startswith(b"\x89PNG\r\n\x1a\n") if suffix == "png" else raw.startswith(b"\xff\xd8\xff")):
            raise Refusal("INVALID_IMAGE")
        name = hashlib.sha256(raw).hexdigest() + "." + suffix
        target = directory / name
        try:
            fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        except FileExistsError:
            raise Refusal("ARTIFACT_EXISTS", "Reuse the existing artifact; never overwrite it.")
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
        block.pop("data")
        block["artifact_path"] = str(target)
        paths.append(str(target))
    copied["artifact_paths"] = paths
    return copied


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["status", "catalog", "read", "edit"])
    parser.add_argument("--tool")
    parser.add_argument("--arguments", default="{}", help="JSON object; @file reads a bounded local JSON file")
    parser.add_argument("--expected-snapshot")
    parser.add_argument("--operation-id")
    parser.add_argument("--allow-write", action="store_true")
    parser.add_argument("--artifact-dir", type=Path)
    args = parser.parse_args()
    try:
        raw = args.arguments
        if raw.startswith("@"):
            with open(raw[1:], "rb") as stream:
                raw = stream.read(MAX_REQUEST + 1)
        if len(raw) > MAX_REQUEST:
            raise Refusal("REQUEST_TOO_LARGE")
        result = execute(args.action, tool=args.tool, arguments=load_json(raw),
                         expected_snapshot=args.expected_snapshot, operation_id=args.operation_id,
                         allow_write=args.allow_write)
        if args.artifact_dir:
            result = save_artifacts(result, args.artifact_dir)
        print(json.dumps(result, indent=2))
        return 2 if result.get("state") in {"EFFECT_UNKNOWN", "TOOL_ERROR"} else 0
    except Refusal as exc:
        print(json.dumps({"state": exc.code, "detail": exc.detail, "retry_allowed": False}))
        return 2
    except Exception:
        print(json.dumps({"state": "LOCAL_FAILURE", "retry_allowed": False}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

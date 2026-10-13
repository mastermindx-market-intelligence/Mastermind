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

VERSION = "0.1.6"
ENDPOINT = "http://127.0.0.1:29979/mcp"
MAX_BYTES = 16 * 1024 * 1024
MAX_REQUEST = 1 << 19
PRIVATE_DIR_MODE = 0o700
DESKTOP_LOCK_WAIT_SECONDS = 30.0
DESKTOP_LOCK_POLL_SECONDS = 0.05
SUPPORTED_SERVER = ("paper-desktop", None)
SUPPORTED_CATALOG_SHA256 = "48b2587455d839a57b4b78f5cfdb2e75df8d530ad8059a3ad6af303c0d37224f"
READ_TOOLS = frozenset({
    "get_basic_info", "get_selection", "get_node_info", "get_children",
    "get_tree_summary", "get_screenshot", "get_jsx", "get_computed_styles",
    "get_fill_image", "get_font_family_info", "get_guide",
    "find_nodes", "get_tokens", "list_comment_threads", "get_comment_thread",
    "list_comment_thread_authors",
})
EDIT_TOOLS = frozenset({
    "create_artboard", "write_html", "set_text_content", "rename_nodes",
    "duplicate_nodes", "move_nodes", "update_styles", "finish_working_on_nodes",
    "create_page", "create_tokens", "set_tokens", "set_comment_thread_status",
})
# Both digests below are independently reviewed complete upstream catalogs.
# A changed tool schema is NOT admitted based on a subset or similarity check.
PREVIOUSLY_REVIEWED_CATALOG_SHA256 = frozenset({
    "ac18857df0aa6323646333368e5798e7c28de7b4d5f5dc3cb320276e3535daa9",
})
# The diagnostic profile never grants write permission. It lets operators
# rapidly distinguish likely read-description-only churn from actual schema
# changes without exposing raw vendor content, adding a watcher or new auth.
DIAGNOSTIC_READ_DESCRIPTION_TOOLS = READ_TOOLS - {"get_basic_info"}
DIAGNOSTIC_DESCRIPTION_LIMIT = 8192
REVIEWED_DESCRIPTION_PROFILE_SHA256 = "210fa4e8801986b07fec879b8f734c653a04d369e3e79227a09c583e6ee6978a"
REVIEWED_TOOL_SHA256 = {
    "create_artboard": "69397924c5de8dd93f2159d09ec12f69afda9666a83660091a43b2880c8f85a4",
    "create_file": "635cad7f83390cf94f967247a2f0996b32efac54a93b9bbb4dd0472ee4ecb4a8",
    "create_page": "054d9ab984702a91b72af029b4e11e8bdfaed324dfb6ecb4d6f2d9d1d72306e4",
    "create_tokens": "8935e10a54416875f2ecb5bc562333a6d046b89070786f3165529db2b95ba0a1",
    "delete_nodes": "7993f27f0fe74ce6de51a9c60a0570669e13b5c32eb6ece3ed9c3c71cf00e823",
    "duplicate_nodes": "f618a6647a141868a1ef00a92b25916fd085afe81b4083f195a36ba2a1b49bc9",
    "export": "3ffe106644541a86b702c63eba87670513d87999eff8ff0e1af0ba5a91233d1d",
    "export_combined_pdf": "1b3e2c8486af5d0b9919ad52cc63b6fbc5ada4ecfbcd3374d2183fb82210c34f",
    "find_nodes": "d93cca1f909f66211316310dc085aa299cdba1de5a267db271d3e43c29b94049",
    "finish_working_on_nodes": "279ad91a4ffc42758f107927638224745692d6c8dc94bbe7c95e01ee8d66ee6e",
    "get_basic_info": "c810bf741bda4053d6d6793e65cc5b69eb18c45e1e82783bca7efb9a09ce6228",
    "get_children": "cc8f62d18bf67ec88f1536a7e7185ff2984ae0de67a1c79b4512e5f780f5f365",
    "get_comment_thread": "c5b9755ce9d4b496145eb23c40944a685decf697aab4b21df1d7441b18bc2db4",
    "get_computed_styles": "2eb2c85f219c545d593f10c00f5b44b10efdb91c66377df9b4b26a7d6a00fba7",
    "get_fill_image": "d02d30ff64edde2de5f4d89e91098d7677baf3c98f36607de1fa3d1c16275d28",
    "get_font_family_info": "cf7f00cbd5b489e41eb0bcba83c8bcce7f0fd4f16fb96f6c2841eb04ef7a77c1",
    "get_guide": "56622d114b2430cde45782040422332f7ffacc9ac5b874b96a33dee5b9560d46",
    "get_jsx": "d5268ea27e6c98d86109c44eca48622c9544395ac45b09215ee59d987032a6d1",
    "get_node_info": "b0f86ff1419f1ca53dba5102dee4c970855015c1ae290b98c498f9a343f4c4c1",
    "get_screenshot": "6e3dc2037a50c5cd7393ab9aa6f887d31dceb67e3d21e14e6dc4893df09a7fee",
    "get_selection": "f06282fa36cb710c36c11aec7475a7a2e0fc29fe529c0abe3e1a242f9994207c",
    "get_tokens": "67eac1dba9442cdf80b9fead63e4c53a329894cdf00810b06443704e18114bbe",
    "get_tree_summary": "7c0af8c9e411b1660d2bfd787d4d7cc418cb8483b0b461b5243065df0cc18f7d",
    "list_comment_thread_authors": "91f063cc884546d9e7f1020d1a8b7a58f089242e309034062b0eff80fdbd3a4a",
    "list_comment_threads": "f73cdeeecc5acfd4dae14ab5c00d263aea4210f51f8cc961f040c5d8c74dfd8e",
    "list_resources": "47e74048dcaac66cb7a8a7b2b4f84cf612183665aae06ac2a26d45189619043b",
    "move_nodes": "0286050634b4097a5a4aa3e575b580a33d207fc505a1e502de21d5538944a9d5",
    "open_file": "fc257403c5b7b6199016b44d9e17b17a512e0dfe9aeb3c5813db3edeab61e717",
    "rename_nodes": "f27d608b51f8dcc1cdeab3abaf631771c5a22bed4fe8e1b1f452711f7a843c40",
    "rename_pages": "53a6446843a4c8c8cc30ff3c02973e6c3a1f00b02c003700c2482c70507dfe83",
    "rename_resource": "5ed7d160d1c517a78be52939cceeb00e18e4a8d14128914ce5f4cecc19f31850",
    "set_comment_thread_status": "a5f2a87bed89041feb8e3718dd3893d80bfa3b58ca60f54bd6c62cb6637f3329",
    "set_text_content": "613762a015d7be7feb5e5c53ca5562b16962886d865db0d564c1ff1961c672d8",
    "set_tokens": "e88c1558fb71f4fd989bb3d8f4c0af229221c4fb62f4642363a2a80c5804277b",
    "update_styles": "406531e52e53eded14589371dea58a3f6d327ac423630a9c562382a546c6b5de",
    "write_html": "c85ea2476c5f29c562901c79dbcb00742c10d45a81af29e5f5373029e1b4c781",
}

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
    path.mkdir(mode=PRIVATE_DIR_MODE, parents=True, exist_ok=True)
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise Refusal("PRIVATE_DIRECTORY_REQUIRED")
    return path


def state_root() -> Path:
    # Fixed per OS principal, not per workspace, so separate clients share the mutex.
    return private_dir(Path.home() / ".local" / "state" / "mastermind-paper")


@contextlib.contextmanager
def desktop_lock(root: Path | None = None, *, wait_seconds: float | None = None):
    """Serialize one host's Paper calls while absorbing ordinary session overlap.

    Waiting is only for the local OS lock before any upstream call is sent. It is
    not an effect retry, queue, lease, or exactly-once mechanism. A bounded
    timeout still fails closed with DESKTOP_BUSY and no Paper call dispatched.
    """
    root = private_dir(root) if root else state_root()
    fd = os.open(root / "desktop.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1 or info.st_mode & 0o077:
            raise Refusal("UNSAFE_LOCK_FILE")
        limit = DESKTOP_LOCK_WAIT_SECONDS if wait_seconds is None else max(0.0, float(wait_seconds))
        deadline = time.monotonic() + limit
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError as exc:
                if time.monotonic() >= deadline:
                    raise Refusal(
                        "DESKTOP_BUSY",
                        f"Another bridge call held this desktop for more than {limit:g}s; no Paper call sent.",
                    ) from exc
                time.sleep(min(DESKTOP_LOCK_POLL_SECONDS, max(0.0, deadline - time.monotonic())))
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
        detail_variants = {encode(value) for value in details}
        if len(names) != 1 or len(pages) != 1 or len(detail_variants) != 1:
            raise Refusal("DOCUMENT_SCHEMA_UNVERIFIED", "get_basic_info returned conflicting document detail.")
        info = dict(details[0])
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


def validate_execution_binding(value):
    """Validate installed provenance, never caller permission or a host registry.

    The host ref must come from the existing fleet owner at deployment. This
    function validates its shape, not physical-host attestation. Legacy unbound
    runtimes retain their original snapshot contract.
    """
    if value is None:
        return None
    fields = {"schema", "host_ref", "service_ref", "runtime_revision", "bridge_sha256"}
    if type(value) is not dict or set(value) != fields:
        raise Refusal("EXECUTION_BINDING_INVALID")
    if value.get("schema") != "mastermind.paper_execution_binding.v1":
        raise Refusal("EXECUTION_BINDING_INVALID")
    for key, pattern in (("host_ref", r"host-[0-9a-f]{64}"),
                         ("service_ref", r"[0-9a-f]{64}"),
                         ("runtime_revision", r"[0-9a-f]{40}"),
                         ("bridge_sha256", r"[0-9a-f]{64}")):
        if type(value[key]) is not str or not re.fullmatch(pattern, value[key]):
            raise Refusal("EXECUTION_BINDING_INVALID")
    return dict(value)


def snapshot(client, file_id: str | None = None, *, execution_binding=None):
    execution_binding = validate_execution_binding(execution_binding)
    if file_id is not None and (not isinstance(file_id, str) or not file_id):
        raise Refusal("FILE_ID_REQUIRED")
    arguments = {} if file_id is None else {"fileId": file_id}
    info = basic_object(client.call("get_basic_info", arguments))
    try:
        identity = document_identity(info)
        bind_error = None
    except Refusal as exc:
        identity, bind_error = None, exc.code
    if identity is not None and identity.get("kind") != "file-id":
        bind_error = "FILE_ID_REQUIRED"
    if file_id is not None and (identity is None or identity.get("kind") != "file-id"
                                or identity.get("id") != file_id):
        raise Refusal("FILE_ID_MISMATCH", "Paper target read did not return the requested file.")
    guarded_info = info if execution_binding is None else {
        "document": info, "execution_binding": execution_binding}
    result = {"basic_info": info, "identity": identity, "snapshot_sha256": digest(guarded_info),
              "write_binding_ready": identity is not None and identity.get("kind") == "file-id",
              "binding_error": bind_error}
    if execution_binding is not None:
        result["execution_binding"] = execution_binding
    return result


def same_document(identity, info):
    if identity["kind"] == "file-id":
        try:
            current = document_identity(info)
        except Refusal:
            return False
        return current.get("kind") == "file-id" and current.get("id") == identity["id"]
    return (info.get("fileName") == identity["file"] and info.get("pageName") == identity["page"]
            and any(isinstance(b, dict) and b.get("id") == identity["anchor"] for b in info.get("artboards", [])))

def description_drift_profile(catalog):
    """Diagnostic only; never a catalog write-admission shortcut."""
    if type(catalog) is not dict:
        return None
    candidate = {}
    for name, descriptor in catalog.items():
        if name in DIAGNOSTIC_READ_DESCRIPTION_TOOLS:
            if (type(descriptor) is not dict
                    or type(descriptor.get("description")) is not str
                    or not 0 < len(descriptor["description"]) <= DIAGNOSTIC_DESCRIPTION_LIMIT):
                return None
            candidate[name] = {**descriptor, "description": ""}
        else:
            candidate[name] = descriptor
    return candidate


def catalog_drift_names(catalog):
    """Compact bounded evidence; never echo untrusted descriptor prose."""
    reviewed_names = set(REVIEWED_TOOL_SHA256)
    observed_names = set(catalog)
    changed = sorted(name for name in (reviewed_names & observed_names)
                     if digest(catalog[name]) != REVIEWED_TOOL_SHA256[name])
    bound = lambda names: [n[:80] for n in names[:32]]
    return {"added": bound(sorted(observed_names - reviewed_names)),
            "removed": bound(sorted(reviewed_names - observed_names)),
            "changed": bound(changed),
            "added_count": len(observed_names - reviewed_names),
            "removed_count": len(reviewed_names - observed_names),
            "changed_count": len(changed)}


def schema_receipt(client, catalog, *, server_pin=SUPPORTED_SERVER,
                   catalog_pin=SUPPORTED_CATALOG_SHA256):
    server = client.server if isinstance(client.server, dict) else {}
    actual = {"server_name": server.get("name"), "server_version": server.get("version"),
              "catalog_sha256": digest(catalog)}
    expected_name = server_pin[0] if server_pin else None
    expected_version = server_pin[1] if server_pin and len(server_pin) > 1 else None
    server_name_ok = expected_name is None or actual["server_name"] == expected_name
    # Version strings are observational. Only EXACT complete reviewed catalogs
    # qualify writes. Diagnostics never grant write permission for unknown drift.
    server_version_ok = expected_version is None or actual["server_version"] == expected_version
    exact_current = catalog_pin is None or actual["catalog_sha256"] == catalog_pin
    # An explicitly injected/overridden pin never inherits this registry.
    exact_prior = (catalog_pin == SUPPORTED_CATALOG_SHA256
                   and actual["catalog_sha256"] in PREVIOUSLY_REVIEWED_CATALOG_SHA256)
    catalog_ok = exact_current or exact_prior
    result = {**actual, "accepted_for_write": bool(server_name_ok and server_version_ok and catalog_ok),
              "expected_server": [expected_name, expected_version] if server_pin else None,
              "server_name_compatible": server_name_ok,
              "server_version_compatible": server_version_ok,
              "server_version_policy": "EXACT" if expected_version is not None else "OBSERVED_NOT_PINNED",
              "catalog_compatible": catalog_ok,
              "catalog_exact_match": exact_current,
              "catalog_admission_mode": ("EXACT_CURRENT" if exact_current
                                         else "EXACT_PREVIOUSLY_REVIEWED" if exact_prior
                                         else "UNREVIEWED"),
              "expected_catalog_sha256": catalog_pin}
    if not exact_current:
        result["catalog_drift"] = catalog_drift_names(catalog)
        if not exact_prior:
            profile = description_drift_profile(catalog)
            result["drift_triage"] = (
                "READ_DESCRIPTION_ONLY_REQUIRES_REVIEW"
                if profile is not None and digest(profile) == REVIEWED_DESCRIPTION_PROFILE_SHA256
                else "UNKNOWN_OR_MATERIAL_CHANGE_REQUIRES_REVIEW")
    return result


def execute(action: str, *, tool: str | None = None, arguments: dict | None = None,
            expected_snapshot: str | None = None, operation_id: str | None = None,
            allow_write=False, client=None, lock_root=None, execution_binding=None,
            _server_pin=SUPPORTED_SERVER, _catalog_pin=SUPPORTED_CATALOG_SHA256):
    """One serialized operation. Snapshot hash is a drift guard, NOT authorization.

    Local edits outside this adapter can race; no transaction/isolation claim is made.
    No persistent duplicate/retry ledger is introduced. Caller owns effect reconciliation.
    """
    execution_binding = validate_execution_binding(execution_binding)
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
            # Readiness includes catalog qualification, not just Paper liveness.
            # A catalog failure must never be reported as write_ready.
            document = snapshot(client, execution_binding=execution_binding)
            try:
                inspection_catalog = client.catalog()
                inspection_schema = schema_receipt(client, inspection_catalog,
                                                  server_pin=_server_pin, catalog_pin=_catalog_pin)
            except (Refusal, OSError, TypeError, ValueError):
                inspection_schema = {"accepted_for_write": False,
                                     "catalog_admission_mode": "CATALOG_UNAVAILABLE"}
            return {"state": "CONNECTED", "server": client.server, "endpoint": ENDPOINT,
                    "document": document, "write_schema": inspection_schema,
                    "quota_remaining": None, "plan": "UNKNOWN"}
        catalog = client.catalog()
        schema = schema_receipt(client, catalog, server_pin=_server_pin, catalog_pin=_catalog_pin)
        if action == "catalog":
            return {"server": client.server, "tools": [dict(catalog[n], bridge_access=("read" if n in READ_TOOLS else "edit"))
                    for n in sorted(catalog) if n in READ_TOOLS | EDIT_TOOLS],
                    "blocked_tools": sorted(set(catalog) - READ_TOOLS - EDIT_TOOLS),
                    "catalog_sha256": schema["catalog_sha256"], "write_schema": schema}
        if editing and not schema["accepted_for_write"]:
            raise Refusal("UPSTREAM_SCHEMA_UNREVIEWED", "Paper server identity or catalog schema changed; inspect read-only and review compatibility before editing.")
        if tool not in catalog:
            raise Refusal("TOOL_NOT_AVAILABLE")
        supplied_file = arguments.get("fileId")
        if editing and (not isinstance(supplied_file, str) or not supplied_file):
            raise Refusal("FILE_ID_REQUIRED", "Pass the exact inspected Paper file ID for every edit.")
        # A guarded background-file read must inspect that same explicit target,
        # not the unrelated user-active document. Host scope remains out of band.
        before = (snapshot(client, supplied_file, execution_binding=execution_binding)
                  if editing or expected_snapshot else None)
        if before and before["snapshot_sha256"] != expected_snapshot:
            raise Refusal("DOCUMENT_CHANGED", "Read the exact target file before deciding on a new edit.")
        if editing and not before["write_binding_ready"]:
            raise Refusal(before["binding_error"] or "DOCUMENT_BINDING_REQUIRED")
        if editing and supplied_file != before["identity"]["id"]:
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
            observed = {"state": "TOOL_ERROR" if result.get("isError") else "OBSERVED", "result": result}
            if tool == "get_basic_info" and supplied_file is not None and not result.get("isError"):
                # Bootstrap through the existing read schema when Paper has no
                # default active-file context. Never infer a target from a name.
                if not same_document({"kind": "file-id", "id": supplied_file}, basic_object(result)):
                    raise Refusal("FILE_ID_MISMATCH", "Paper target read did not return the requested file.")
                # Keep page-specific content in result, but obtain the guard
                # from the same file-only snapshot constructor used by edits.
                # Installed host/runtime provenance and the mutex are retained.
                observed["document"] = snapshot(client, supplied_file, execution_binding=execution_binding)
                observed["write_schema"] = schema
            return observed
        if result.get("isError"):
            return {"state": "EFFECT_UNKNOWN", "operation_id": operation_id, "tool": tool,
                    "result": result, "before": before, "retry_allowed": False, "reason": "UPSTREAM_TOOL_ERROR_MAY_BE_PARTIAL"}
        try:
            after = snapshot(client, supplied_file, execution_binding=execution_binding)
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

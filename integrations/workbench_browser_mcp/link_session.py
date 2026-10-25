"""Exact-tab native session borrowed by the incumbent Workbench browser relay.

The session owns transport interlocks only. Workbench owns the original durable
claim, effect classification, process, profile grant, and lease. No native
request is retried, and a new Chrome connection never inherits old tab consent.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
import secrets
import select
import socket
import threading
import time
from typing import Any, Mapping

from control_plane.codex_worker import ProcessInspector
from integrations.mastermind_browser_link.native_bridge import require_peer_uid
from integrations.mastermind_browser_link.endpoint_evidence import capture_native_endpoint
from integrations.mastermind_browser_link.native_channel import (
    COMMAND_SCHEMA, INVENTORY_SCHEMA, OBSERVE_SCHEMA, READY_SCHEMA,
    Deadline, LinkEnrollment, LinkProtocolError, MAX_LIFETIME_MS, NativeHostError,
    close_private_server, open_private_server, read_frame, write_frame,
    record, reference, integer, snapshot, validate_command, validate_hello,
    validate_extension_message, validate_target,
)
from integrations.mastermind_browser_link.tool_contract import (
    ACTION_TOOL, INVENTORY_TOOL, READ_TOOL, LINK_TOOLS, LINK_READ_TOOLS,
    LINK_TOOL_SCHEMA_DIGEST, OWNER_CONNECTION_SCHEMA, OWNER_INVENTORY_SCHEMA, OWNER_RESULT_SCHEMA,
)
from .relay import (
    BrowserRelayError, BrowserRequestRefused, BrowserSession, McpSessionReceipt,
    _unix_peer_pid,
)


@dataclass
class _Pending:
    kind: str
    tab_id: int | None
    event: threading.Event = field(default_factory=threading.Event)
    result: dict | None = None
    failed: bool = False


@dataclass
class _Connection:
    socket: socket.socket
    channel: Any
    generation: str
    peer_pid: int
    peer_identity: Any
    pending: dict[str, _Pending] = field(default_factory=dict)
    used: set[str] = field(default_factory=set)
    busy_tabs: set[int] = field(default_factory=set)
    next_fence: int = 0
    write_gate: threading.Lock = field(default_factory=threading.Lock)


class BrowserLinkSession(BrowserSession):
    max_parallel_calls = 16
    read_only_tools = LINK_READ_TOOLS

    def __init__(
        self, *, enrollment: LinkEnrollment, chrome_pid: int,
        chrome_start_identity: str, holder_ref: str, inspector=None,
        clock_ms=None, timeout_seconds: float = 25.0,
    ):
        if type(enrollment) is not LinkEnrollment:
            raise BrowserRelayError("Link enrollment is invalid")
        enrollment.__post_init__()
        if type(chrome_pid) is not int or chrome_pid <= 1:
            raise BrowserRelayError("Link Chrome identity is invalid")
        if type(chrome_start_identity) is not str or not chrome_start_identity or len(chrome_start_identity) > 128:
            raise BrowserRelayError("Link Chrome identity is invalid")
        reference(holder_ref)
        if type(timeout_seconds) not in {int, float} or not 0 < timeout_seconds <= 30:
            raise BrowserRelayError("Link timeout is invalid")
        self.enrollment = enrollment
        self._chrome_pid, self._chrome_start = chrome_pid, chrome_start_identity
        self._holder = holder_ref
        self._inspector = inspector or ProcessInspector()
        self._clock_ms = clock_ms or (lambda: int(time.time() * 1000))
        self._timeout = float(timeout_seconds)
        self._gate = threading.RLock()
        self._slot = threading.BoundedSemaphore(1)
        self._stop = threading.Event()
        self._server = None
        self._accept_thread = self._reader_thread = None
        self._active: _Connection | None = None
        self._receipt = None
        self._endpoint = None
        self._uncertain_tabs: set[int] = set()

    def _chrome_current(self):
        chrome = self._inspector.inspect(self._chrome_pid)
        if (chrome.start_identity != self._chrome_start
                or chrome.effective_uid != os.geteuid() or chrome.real_uid != os.getuid()):
            raise BrowserRelayError("Link Chrome process changed")
        return chrome

    def _peer_current(self, connection, peer_pid=None, prior=None):
        require_peer_uid(connection, os.geteuid())
        pid = _unix_peer_pid(connection)
        if peer_pid is not None and pid != peer_pid:
            raise BrowserRelayError("Link native peer changed")
        chrome = self._chrome_current()
        peer = self._inspector.inspect(pid)
        if (peer.parent_pid != self._chrome_pid or peer.effective_uid != os.geteuid()
                or peer.real_uid != os.getuid() or (prior is not None and peer != prior)):
            raise BrowserRelayError("Link native lineage changed")
        if self._inspector.inspect(pid) != peer or self._chrome_current() != chrome:
            raise BrowserRelayError("Link native lineage changed")
        return pid, peer

    @property
    def connection_status(self):
        # Advisory channel discovery. No tab, consent or browser permission is
        # issued here; chosen tabs still require a correlated native observe.
        with self._gate:
            selected = self._active
            if selected is not None:
                try:
                    self._peer_current(selected.socket, selected.peer_pid, selected.peer_identity)
                except Exception:
                    self._retire(selected)
                    selected = None
            return {"schema": OWNER_CONNECTION_SCHEMA,
                    "instance_id": self.enrollment.instance_id,
                    "connected": selected is not None,
                    **({"connection_generation": selected.generation} if selected is not None else {})}

    @property
    def native_endpoint(self):
        with self._gate:
            if self._server is None or self._endpoint is None:
                raise BrowserRelayError("Link endpoint is not started")
            self._endpoint.qualify(self.enrollment.socket_path)
            return self._endpoint.document()

    @property
    def receipt(self):
        if self._receipt is None:
            raise BrowserRelayError("Link session is not started")
        return self._receipt

    def start(self):
        with self._gate:
            if self._server is not None or self._stop.is_set():
                raise BrowserRelayError("Link session cannot be restarted")
            self._chrome_current()
            parent = self.enrollment.socket_path.parent.lstat()
            parent_identity = (parent.st_dev, parent.st_ino)
            self._server = open_private_server(self.enrollment.socket_path, owner_uid=os.geteuid())
            try:
                self._endpoint = capture_native_endpoint(self._server, self.enrollment.socket_path,
                                                         parent_identity=parent_identity)
            except BaseException:
                close_private_server(self._server, self.enrollment.socket_path, owner_uid=os.geteuid())
                self._server = None
                raise
            self._server.settimeout(0.2)
            self._receipt = McpSessionReceipt(
                child_pid=os.getpid(), tool_schema_digest=LINK_TOOL_SCHEMA_DIGEST,
                allowed_tools=tuple(sorted(LINK_TOOLS)),
            )
            self._accept_thread = threading.Thread(target=self._accept, name="browser-link-accept", daemon=True)
            try:
                self._accept_thread.start()
            except BaseException:
                close_private_server(self._server, self.enrollment.socket_path, owner_uid=os.geteuid())
                self._server = self._receipt = self._accept_thread = self._endpoint = None
                raise
            return self._receipt

    def _accept(self):
        while not self._stop.is_set():
            try:
                connection, _ = self._server.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            # A second local process cannot preempt a live or handshaking peer.
            if not self._slot.acquire(blocking=False):
                connection.close()
                continue
            self._reader_thread = threading.Thread(
                target=self._read_native, args=(connection,), name="browser-link-native", daemon=True
            )
            try:
                self._reader_thread.start()
            except RuntimeError:
                connection.close()
                self._slot.release()

    def _read_native(self, connection):
        selected = None
        try:
            connection.settimeout(5.0)
            peer_pid, peer_identity = self._peer_current(connection)
            with connection.makefile("rwb", buffering=0) as channel:
                hello = validate_hello(read_frame(channel, deadline=Deadline(time.monotonic() + 5.0)), self.enrollment)
                self._peer_current(connection, peer_pid, peer_identity)
                selected = _Connection(connection, channel, hello["connection_generation"], peer_pid, peer_identity)
                with self._gate:
                    if self._stop.is_set() or self._active is not None:
                        return
                    write_frame(channel, {"schema": READY_SCHEMA, "connection_generation": selected.generation},
                                deadline=Deadline(time.monotonic() + 5.0))
                    self._active = selected
                while not self._stop.is_set():
                    readable, _, _ = select.select([channel], [], [], 0.2)
                    if not readable:
                        continue
                    self._peer_current(connection, peer_pid, peer_identity)
                    data = validate_extension_message(
                        read_frame(channel, deadline=Deadline(time.monotonic() + 5.0)), selected.generation
                    )
                    request_id = data.get("request_id")
                    if request_id is None:
                        # Push inventory is advisory. Every owner observation
                        # requests a correlated live inventory before using it.
                        continue
                    with self._gate:
                        pending = selected.pending.get(request_id)
                        if pending is None:
                            continue  # late receipt never causes redispatch
                        if pending.kind == "inventory":
                            if data["schema"] != INVENTORY_SCHEMA:
                                raise LinkProtocolError("LINK_RESPONSE_KIND_CHANGED")
                        elif data["schema"] == INVENTORY_SCHEMA:
                            raise LinkProtocolError("LINK_RESPONSE_KIND_CHANGED")
                        elif pending.kind == "read" and data["effect"] != "NOT_APPLIED":
                            raise LinkProtocolError("LINK_READ_EFFECT_INVALID")
                        elif pending.kind == "write":
                            if ((data["status"] == "completed") != (data["effect"] == "APPLIED")
                                    or (data["status"] == "pending" and data["effect"] != "EFFECT_UNKNOWN")):
                                raise LinkProtocolError("LINK_WRITE_EFFECT_INVALID")
                        if pending.result is not None:
                            if pending.result != data:
                                raise LinkProtocolError("LINK_RESPONSE_CONFLICT")
                            continue
                        pending.result = data
                        pending.event.set()
        except Exception:
            pass  # a rejected native peer never kills the resource owner
        finally:
            if selected is not None:
                self._retire(selected)
            connection.close()
            self._slot.release()

    def _retire(self, selected):
        with self._gate:
            if self._active is selected:
                self._active = None
            for pending in selected.pending.values():
                if pending.kind == "write" and (pending.result is None
                        or pending.result.get("effect") == "EFFECT_UNKNOWN"
                        or "original_effect" in pending.result):
                    self._uncertain_tabs.add(pending.tab_id)
                if pending.result is None:
                    pending.failed = True
                pending.event.set()
            try:
                selected.socket.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

    def _request(self, request_id, tool, arguments):
        try:
            reference(request_id)
            args = snapshot(arguments)
            if tool == INVENTORY_TOOL:
                record(args, set())
                target = None
                kind = "inventory"
            elif tool in {READ_TOOL, ACTION_TOOL}:
                record(args, {"target", "command", "args", "expires_at_ms"})
                target = validate_target(args["target"])
                integer(args["expires_at_ms"])
                kind = "read" if tool == READ_TOOL else "write"
                if (tool == READ_TOOL) != (args["command"] in {"snapshot", "screenshot"}):
                    raise LinkProtocolError("LINK_TOOL_KIND_CHANGED")
            else:
                raise LinkProtocolError("LINK_TOOL_NOT_GRANTED")
        except (ValueError, TypeError, UnicodeError) as exc:
            raise BrowserRequestRefused("Link arguments refused") from exc
        with self._gate:
            selected = self._active
            if selected is None or self._stop.is_set():
                raise BrowserRequestRefused("Link is disconnected")
        pending = _Pending(kind, None if target is None else target["tab_id"])
        with selected.write_gate:
            with self._gate:
                if selected is not self._active or self._stop.is_set():
                    raise BrowserRequestRefused("Link generation changed")
                try:
                    self._peer_current(selected.socket, selected.peer_pid, selected.peer_identity)
                except Exception as exc:
                    self._retire(selected)
                    raise BrowserRequestRefused("Link peer disappeared before dispatch") from exc
                if request_id in selected.pending or request_id in selected.used:
                    raise BrowserRelayError("Link original request may already have applied")
                if len(selected.pending) >= 16 or (kind != "inventory" and len(selected.used) >= 4096):
                    raise BrowserRequestRefused("Link call capacity exhausted")
                if target is None:
                    command = {"schema": OBSERVE_SCHEMA, "request_id": request_id,
                               "connection_generation": selected.generation}
                else:
                    if target["connection_generation"] != selected.generation:
                        raise BrowserRequestRefused("Link generation changed")
                    if kind == "write" and (target["tab_id"] in self._uncertain_tabs or target["tab_id"] in selected.busy_tabs):
                        raise BrowserRequestRefused("Link target is busy or unresolved")
                    now = self._clock_ms()
                    command = {"schema": COMMAND_SCHEMA, "request_id": request_id, **target,
                               "expires_at_ms": min(args["expires_at_ms"], now + MAX_LIFETIME_MS),
                               "command": args["command"], "args": args["args"]}
                    if kind == "write":
                        selected.next_fence += 1
                        command["writer"] = {"holder_ref": self._holder, "fence": selected.next_fence}
                    try:
                        command = validate_command(command, now_ms=now)
                    except (ValueError, TypeError) as exc:
                        raise BrowserRequestRefused("Link command refused") from exc
                selected.pending[request_id] = pending
                if kind != "inventory":
                    selected.used.add(request_id)
                if kind == "write":
                    selected.busy_tabs.add(target["tab_id"])
            try:
                write_frame(selected.channel, command, deadline=Deadline(time.monotonic() + 5.0))
            except (NativeHostError, OSError):
                # A partial frame poisons the generation, not just this call.
                self._retire(selected)
        pending.event.wait(min(self._timeout, 2.0) if kind == "inventory" else self._timeout)
        with self._gate:
            selected.pending.pop(request_id, None)
            if kind == "write":
                selected.busy_tabs.discard(target["tab_id"])
            result = pending.result
            if pending.failed or result is None:
                if kind == "write":
                    self._uncertain_tabs.add(target["tab_id"])
                raise BrowserRelayError("Link response unavailable after dispatch")
            if kind == "write" and (result.get("effect") == "EFFECT_UNKNOWN" or "original_effect" in result):
                self._uncertain_tabs.add(target["tab_id"])
            if "original_effect" in result:
                raise BrowserRelayError("Link original effect requires reconciliation")
            if kind == "inventory":
                result = snapshot(result)
                for row in result["shared_tabs"]:
                    if row["tab_id"] in self._uncertain_tabs and row["state"] == "shared":
                        row["state"] = "effect_unresolved"
            return snapshot(result)

    def call(self, tool: str, arguments: Mapping[str, Any]):
        return self.call_with_identity(secrets.token_hex(16), tool, arguments)

    def call_with_identity(self, request_id, tool, arguments):
        result = self._request(request_id, tool, arguments)
        if tool == INVENTORY_TOOL:
            return {"isError": False, "content": [{"type": "text", "text": "Current Browser Link inventory"}],
                    "structuredContent": {"schema": OWNER_INVENTORY_SCHEMA,
                        "instance_id": self.enrollment.instance_id,
                        "connection_generation": result["connection_generation"],
                        "shared_tabs": result["shared_tabs"]}}
        output = result.get("output")
        metadata = {"schema": OWNER_RESULT_SCHEMA, "effect_state": result["effect"],
                    "status": result["status"], "request_id": result["request_id"]}
        for name in ("code", "document_revision"):
            if name in result:
                metadata[name] = result[name]
        content = []
        if type(output) is dict and output.get("kind") == "viewport_screenshot":
            image = dict(output)
            data = image.pop("data", None)
            mime = image.pop("mime_type", None)
            if type(data) is not str or mime not in {"image/jpeg", "image/png"}:
                raise BrowserRelayError("Link image result is invalid")
            content.append({"type": "image", "mimeType": mime, "data": data})
            output = image
        content.insert(0, {"type": "text", "text": json.dumps(
            {**metadata, **({"output": output} if output is not None else {})},
            separators=(",", ":"), ensure_ascii=False, allow_nan=False)})
        return {"isError": result["status"] != "completed", "content": content, "structuredContent": metadata}

    def close(self):
        self._stop.set()
        with self._gate:
            selected, server = self._active, self._server
            self._active = None
            self._receipt = None
            if selected is not None:
                for pending in selected.pending.values():
                    if pending.result is None:
                        pending.failed = True
                    pending.event.set()
                try:
                    selected.socket.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
        if server is not None:
            close_private_server(server, self.enrollment.socket_path, owner_uid=os.geteuid())
        for thread in (self._accept_thread, self._reader_thread):
            if thread is not None and thread.ident is not None and thread is not threading.current_thread():
                thread.join(timeout=6.0)
        self._server = None

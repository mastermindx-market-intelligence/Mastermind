"""The one production composition of the t3-native worker adapter.

Closes audit item #14 (AUDIT_T3_DURABLE_ADAPTER_OPUS_20261109; re-audits A3/A4
gap 4): before this module NO runtime composed the SQLite adapter-state store,
``T3McpToolPort`` and a real producer of the pre-ACK recovery binding.  This
module is a pure factory over the existing owners — it adds no queue,
registry, lifecycle or database of its own:

* **Store placement** — the adapter state file is placed by the SAME rule the
  Executive runtime uses for its own database: a sibling file
  (``t3_adapter_state.sqlite3``) in the Executive's actual data directory
  (``<runtime root>/data/control_plane``), NEVER ``executive.sqlite3`` itself
  (the runtime pins its whole-file schema digest).  When no installed layout
  is configured the per-checkout module-relative default is used AND that
  fact is disclosed in the typed ``basis`` field (the per-checkout default is
  exactly what makes the re-audit R1 no-row recovery window reachable, so a
  production composition must say when it is on it).
* **Endpoint** — reuses :class:`control_plane.t3_environment_projection.\
T3EnvironmentProjection` as the endpoint carrier (``server_endpoint``), with
  the local default ``http://127.0.0.1:3773/mcp`` when no projection carries
  one.  No second endpoint store is created.
* **Credential** — the MCP access token is READ FROM A PATH (environment
  variable or explicit path), never embedded here, never logged, never
  echoed in errors or results.  An absent token file is a typed
  ``T3_NOT_ENROLLED`` composition result, never an exception at import or
  composition time: the t3-native route stays unselected until it is
  enrolled.
* **Port + transport** — ``T3McpToolPort.from_access_token`` over a minimal
  stdlib streamable-HTTP MCP transport defined in this module (control_plane
  must not import the ``integrations`` package; the donor client stays a
  live-proof tool).  The port attests its upstream namespace from the SAME
  token the transport sends — the composition precondition (re-check M2).
* **Adapter** — constructed through the reviewed instantiation path
  (:func:`construct_reviewed_adapter` + :func:`bind_reviewed_adapter`),
  bound to the supervisor's binding source (the Runtime's per-attempt
  ``ExecutionBinding``) and inspector, over the SQLite store at the resolved
  placement.
* **Supervisor owner** — :func:`compose_t3_native_supervisor_owners` builds
  the per-worker :class:`ExecutiveSupervisor` owners that plug into the
  existing :class:`MixedExecutionOwnerSupervisor` owners map.  The
  supervisor's own launch path is the real producer of the pre-ACK recovery
  binding: ``_launch_metadata`` binds ``WorkerRecoveryBinding`` and
  ``record_process`` persists it BEFORE the RUNNING transition, so a crash
  before the ACK leaves a durable binding ``T3ExecutionAdapter.reattach``
  consumes with zero native launches.

This module performs no I/O at import and grants no authority the composed
owners do not already hold.
"""
from __future__ import annotations

import asyncio
import json
import os
import socket
import urllib.error
import urllib.request
from dataclasses import dataclass, replace as dataclass_replace
from pathlib import Path
from typing import Any, Callable, Mapping

from control_plane.t3_execution_adapter import (
    T3ExecutionAdapter,
    T3_NATIVE_ADAPTER_ID,
    T3McpToolPort,
    T3McpTransportError,
    SQLiteT3AdapterStateStore,
    default_t3_adapter_state_path,
)

#: Environment variable naming the FILE that holds the MCP access token.
#: The token itself is never an environment variable value (it would land in
#: process listings and crash reports); only its path is configuration.
T3_MCP_ACCESS_TOKEN_FILE_ENV = "MASTERMIND_T3_MCP_ACCESS_TOKEN_FILE"

#: Local default MCP endpoint (host:port form for the projection carrier).
T3_MCP_DEFAULT_ENDPOINT = "127.0.0.1:3773"
T3_MCP_DEFAULT_URL = f"http://{T3_MCP_DEFAULT_ENDPOINT}/mcp"

#: The adapter's own SQLite file name (sibling of the Executive database).
T3_ADAPTER_STATE_FILENAME = "t3_adapter_state.sqlite3"

#: Typed store-placement bases (disclosed, never inferred from silence).
STORE_BASIS_EXECUTIVE_DATA_DIR = "EXECUTIVE_DATA_DIR"
STORE_BASIS_CHECKOUT_DEFAULT = "CHECKOUT_DEFAULT"

#: Typed composition statuses.
COMPOSITION_COMPOSED = "COMPOSED"
COMPOSITION_NOT_ENROLLED = "T3_NOT_ENROLLED"


class T3NativeCompositionError(Exception):
    """Typed, fail-closed composition refusal (never a bare OSError here)."""


@dataclass(frozen=True)
class T3AdapterStorePlacement:
    """Where the adapter's SQLite store lives and WHY (typed disclosure)."""

    path: Path
    basis: str

    def __post_init__(self) -> None:
        if self.basis not in (STORE_BASIS_EXECUTIVE_DATA_DIR,
                              STORE_BASIS_CHECKOUT_DEFAULT):
            raise T3NativeCompositionError(
                f"unknown store placement basis {self.basis!r}"
            )


def resolve_t3_adapter_store_placement(
    runtime: Any = None,
    *,
    runtime_root: str | Path | None = None,
) -> T3AdapterStorePlacement:
    """Place the adapter store by the Executive's own database rule.

    With a live ``runtime`` (or an explicit installed-layout ``runtime_root``)
    the placement is a SIBLING of the Executive's actual database — same data
    directory, the adapter's own file — so the installed layout governs both
    files identically.  Without either, the per-checkout module-relative
    default is returned with basis ``CHECKOUT_DEFAULT``: that default is what
    makes the re-audit R1 no-row recovery window reachable, so a composition
    on it must say so instead of implying an installed placement.
    """
    executive_db: Path | None = None
    if runtime is not None:
        store = getattr(runtime, "store", None)
        path = getattr(store, "path", None) if store is not None else None
        if path is not None:
            executive_db = Path(path)
    if executive_db is None and runtime_root is not None:
        executive_db = (
            Path(runtime_root) / "data" / "control_plane" / "executive.sqlite3"
        )
    if executive_db is not None:
        placement = T3AdapterStorePlacement(
            path=executive_db.parent / T3_ADAPTER_STATE_FILENAME,
            basis=STORE_BASIS_EXECUTIVE_DATA_DIR,
        )
    else:
        placement = T3AdapterStorePlacement(
            path=default_t3_adapter_state_path(),
            basis=STORE_BASIS_CHECKOUT_DEFAULT,
        )
    if placement.path.name == "executive.sqlite3" or (
        executive_db is not None and placement.path == executive_db
    ):
        raise T3NativeCompositionError(
            "t3 adapter state must never be the Executive runtime database"
        )
    return placement


def resolve_t3_access_token_file(
    token_file: str | Path | None = None,
    *,
    environ: Mapping[str, str] | None = None,
) -> Path | None:
    """Resolve the access-token FILE path; ``None`` means not enrolled.

    An explicit path wins; otherwise the environment variable names it.  This
    reads only the path, never the secret.
    """
    if token_file is not None:
        return Path(token_file)
    env = os.environ if environ is None else environ
    value = env.get(T3_MCP_ACCESS_TOKEN_FILE_ENV, "").strip()
    return Path(value) if value else None


def _read_access_token(token_file: Path) -> str:
    """Read the bearer token from its file.  The value is never logged."""
    try:
        raw = token_file.read_text(encoding="utf-8")
    except OSError as exc:
        raise T3NativeCompositionError(
            f"t3 access token file {token_file} is unreadable: "
            f"{type(exc).__name__}"
        ) from exc
    token = raw.strip()
    if not token:
        raise T3NativeCompositionError(
            f"t3 access token file {token_file} is empty"
        )
    return token


def _endpoint_url(
    endpoint: str | None,
    projection: Any = None,
) -> str:
    """Reuse the existing projection carrier; do not duplicate endpoint state."""
    carrier = endpoint
    if carrier is None and projection is not None:
        projected = getattr(projection, "server_endpoint", None)
        if isinstance(projected, str) and projected.strip():
            carrier = projected.strip()
    host_port = (carrier or T3_MCP_DEFAULT_ENDPOINT).strip()
    if "://" in host_port:
        return host_port
    return f"http://{host_port}/mcp"


class T3McpHttpTransport:
    """Minimal stdlib streamable-HTTP MCP client for the t3-native adapter.

    A control_plane resident equivalent of the live-proof donor client: Bearer
    authorization from the SAME token the port attests, ``Mcp-Session-Id``
    retention, SSE data-frame parsing, and every failure classified into
    :class:`T3McpTransportError` with the phase the adapter's lost-reply
    classifier depends on (pre-send failures vs everything after send).  The
    token is kept only in the authorization header it sends; it is never
    stored on an error, repr, or log line.
    """

    def __init__(self, url: str, access_token: str, *,
                 timeout_seconds: float = 60.0) -> None:
        self._url = str(url)
        self._token = str(access_token)
        self._session_id: str | None = None
        self._next_id = 0
        self._timeout = float(timeout_seconds)
        self.protocol_version = "2025-03-26"

    # -- plumbing -------------------------------------------------------------

    def _post(self, payload: Mapping[str, Any], *,
              expect_reply: bool = True) -> Mapping[str, Any] | None:
        body = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "Authorization": f"Bearer {self._token}",
        }
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id
        request = urllib.request.Request(
            self._url, data=body, headers=headers, method="POST"
        )
        after = T3McpTransportError.AFTER_SEND
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as resp:
                sid = resp.headers.get("Mcp-Session-Id") or resp.headers.get(
                    "mcp-session-id"
                )
                if sid:
                    self._session_id = sid
                ctype = resp.headers.get("Content-Type", "")
                raw = resp.read().decode("utf-8", "replace")
                status = resp.status
        except urllib.error.HTTPError as exc:
            # An explicit upstream HTTP answer (the status is the evidence).
            detail = exc.read().decode("utf-8", "replace")[:500]
            raise T3McpTransportError(
                f"HTTP {exc.code}: {detail}", phase=after, http_status=exc.code
            ) from exc
        except urllib.error.URLError as exc:
            # Connection refused / name resolution: nothing was delivered.
            # Timeouts and resets may have been delivered: after-send.
            pre = isinstance(exc.reason, (ConnectionRefusedError, socket.gaierror))
            raise T3McpTransportError(
                f"transport failure: {exc.reason}",
                phase=T3McpTransportError.PRE_SEND if pre else after,
            ) from exc
        except (TimeoutError, ConnectionError, OSError) as exc:
            raise T3McpTransportError(
                f"transport failure: {exc}", phase=after
            ) from exc
        if not expect_reply:
            return None
        if status != 200:
            raise T3McpTransportError(
                f"HTTP {status} {ctype}: {raw[:300]}", phase=after,
                http_status=status,
            )
        try:
            if "text/event-stream" in ctype:
                data = None
                for line in raw.splitlines():
                    if line.startswith("data:"):
                        data = line[5:].strip()
                if data is None:
                    raise ValueError("SSE response carried no data frame")
                return json.loads(data)
            return json.loads(raw)
        except ValueError as exc:
            raise T3McpTransportError(
                f"unparsable reply: {exc}", phase=after
            ) from exc

    def _rpc_id(self) -> int:
        self._next_id += 1
        return self._next_id

    # -- MCP surface ----------------------------------------------------------

    def initialize(self) -> Mapping[str, Any]:
        """Open the MCP session (initialize + initialized notification)."""
        resp = self._post({
            "jsonrpc": "2.0",
            "id": self._rpc_id(),
            "method": "initialize",
            "params": {
                "protocolVersion": self.protocol_version,
                "capabilities": {},
                "clientInfo": {
                    "name": "mastermind-executive-t3-native",
                    "version": "1.0.0",
                },
            },
        })
        assert resp is not None
        result = resp.get("result") or {}
        server_pv = result.get("protocolVersion")
        if server_pv and server_pv != self.protocol_version:
            self.protocol_version = server_pv
        if resp.get("error"):
            raise T3McpTransportError(
                f"initialize failed: {resp['error']}", phase=T3McpTransportError.AFTER_SEND,
            )
        self._post(
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            expect_reply=False,
        )
        return result

    def call_tool(self, name: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
        """The transport callable ``T3McpToolPort`` requires."""
        resp = self._post({
            "jsonrpc": "2.0",
            "id": self._rpc_id(),
            "method": "tools/call",
            "params": {"name": name, "arguments": dict(arguments)},
        })
        assert resp is not None
        after = T3McpTransportError.AFTER_SEND
        if resp.get("error"):
            error = resp["error"] if isinstance(resp["error"], dict) else {}
            code = error.get("code")
            raise T3McpTransportError(
                f"tools/call {name} JSON-RPC error: {resp['error']}",
                phase=after, rpc_code=code if isinstance(code, int) else None,
            )
        result = resp.get("result") or {}
        if result.get("isError"):
            text = ""
            for item in result.get("content") or []:
                if isinstance(item, dict) and item.get("type") == "text":
                    text = str(item.get("text", ""))
            if not text and isinstance(result.get("structuredContent"), dict):
                text = json.dumps(result["structuredContent"].get("error"))
            from control_plane.t3_execution_adapter import t3_mcp_tool_error_code
            raise T3McpTransportError(
                f"tool {name} returned failure: {text[:400]}",
                phase=after, tool_error=True,
                tool_error_code=t3_mcp_tool_error_code(result),
            )
        structured = result.get("structuredContent")
        if isinstance(structured, dict):
            return structured
        for item in result.get("content") or []:
            if item.get("type") == "text":
                try:
                    parsed = json.loads(item.get("text", ""))
                except (ValueError, TypeError):
                    continue
                if isinstance(parsed, dict):
                    return parsed
        raise T3McpTransportError(
            f"tool {name} returned no parsable payload", phase=after
        )


@dataclass(frozen=True)
class T3NativeComposition:
    """Typed composition result — composed, or typed-not-enrolled.  Never a
    bare exception: an unenrolled host is a normal state, not a fault."""

    status: str
    store_placement: T3AdapterStorePlacement
    endpoint_url: str
    adapter: T3ExecutionAdapter | None = None
    upstream_namespace: str | None = None
    reason: str = ""

    @property
    def composed(self) -> bool:
        return self.status == COMPOSITION_COMPOSED and self.adapter is not None


def _runtime_binding_source(runtime: Any) -> Callable[[Any], Any]:
    """The supervisor's binding source: the Runtime's per-attempt binding."""

    def binding_source(spec: Any):
        raw = runtime.attempts.execution_binding(spec.run_id)
        if raw is None:
            return None
        from control_plane.child_execution_contracts import ExecutionBinding
        return ExecutionBinding.from_dict(raw)

    return binding_source


def compose_t3_native_adapter(
    runtime: Any,
    *,
    inspector: Any = None,
    token_file: str | Path | None = None,
    endpoint: str | None = None,
    projection: Any = None,
    clock: Any = None,
    state_store: Any = None,
    store_placement: T3AdapterStorePlacement | None = None,
    port_factory: Callable[[str], Any] | None = None,
    transport_factory: Callable[[str, str], Any] | None = None,
    environ: Mapping[str, str] | None = None,
) -> T3NativeComposition:
    """Compose the reviewed t3-native adapter over real production inputs.

    Fail-closed and typed: an absent token file yields
    ``T3_NOT_ENROLLED`` (the route stays unselected); a present token builds
    the port over the SAME token the transport sends and constructs the
    adapter through the reviewed instantiation path.
    """
    placement = store_placement or resolve_t3_adapter_store_placement(runtime)
    url = _endpoint_url(endpoint, projection)
    resolved_file = resolve_t3_access_token_file(token_file, environ=environ)
    if resolved_file is None:
        return T3NativeComposition(
            status=COMPOSITION_NOT_ENROLLED,
            store_placement=placement,
            endpoint_url=url,
            reason=(
                f"no access token file configured "
                f"({T3_MCP_ACCESS_TOKEN_FILE_ENV} or token_file)"
            ),
        )
    try:
        token = _read_access_token(resolved_file)
    except T3NativeCompositionError as exc:
        return T3NativeComposition(
            status=COMPOSITION_NOT_ENROLLED,
            store_placement=placement,
            endpoint_url=url,
            reason=str(exc),
        )
    if port_factory is not None:
        # A test-injected port over the same token (no real transport).
        port = port_factory(token)
    else:
        transport = (
            transport_factory(url, token)
            if transport_factory is not None
            else T3McpHttpTransport(url, token)
        )
        # COMPOSITION PRECONDITION (re-check M2): attestation and transport
        # are built from the SAME token, right here, with nothing between.
        port = T3McpToolPort.from_access_token(transport.call_tool, token)
    if inspector is None:
        from control_plane.codex_worker import ProcessInspector
        inspector = ProcessInspector()
    store = state_store if state_store is not None else SQLiteT3AdapterStateStore(
        placement.path
    )
    from control_plane.worker_adapter import (
        bind_reviewed_adapter,
        construct_reviewed_adapter,
    )
    adapter = construct_reviewed_adapter(
        "t3-native",
        port,
        _runtime_binding_source(runtime),
        inspector,
        clock=clock,
        state_store=store,
    )
    bind_reviewed_adapter(adapter, "t3-native")
    return T3NativeComposition(
        status=COMPOSITION_COMPOSED,
        store_placement=placement,
        endpoint_url=url,
        adapter=adapter,
        upstream_namespace=port.authenticated_namespace(),
    )


class T3NativeProcessController:
    """Presence law for adapter-owned remote-native executions.

    A t3-native attempt has no local PID; its lifecycle is owned by the
    adapter through its port.  An attempt carrying this adapter's durable
    ``worker_recovery_binding`` reports ``TERMINAL_OWNED`` (the reconcile
    path adopts it through ``reattach``); anything else is ``UNKNOWN`` —
    never signalled, never assumed absent.  ``terminate`` stays refused: a
    remote thread is interrupted only through the adapter's own cancel seam.
    """

    def presence(self, attempt: Any):
        from control_plane.executive_supervisor import ProcessPresence
        raw = getattr(attempt, "launch_metadata", {}).get(
            "worker_recovery_binding"
        )
        if isinstance(raw, Mapping) and raw.get("adapter_id") == "t3-native":
            return ProcessPresence.TERMINAL_OWNED
        return ProcessPresence.UNKNOWN

    def absence_verified(self, attempt: Any) -> bool:
        # The adapter owns absence knowledge; the controller never claims it.
        return False

    def terminate(self, attempt: Any) -> None:
        from control_plane.executive_supervisor import SupervisorError
        raise SupervisorError(
            "remote-native t3 execution is interrupted only through its adapter"
        )


class SupervisorBoundaryT3Adapter:
    """Supervisor-boundary projection of the reviewed T3ExecutionAdapter.

    WHY this projection exists: the supervisor's single ``record_process``
    call site (protected ``executive_supervisor.py``) passes the process
    ref's pid/pgid verbatim, and the Runtime accepts either a POSITIVE
    local pid or the all-``None`` provider-managed shape
    (``provider_session_id`` only).  The T3 durable ref contract pins
    ``pid=0``/``pgid=0`` — a remote thread is not a local process, and the
    retained ref's determinism is what reattach verifies — so this
    projection translates ONLY the four local-process identity fields
    (pid, pgid, process_start_identity, boot_session_id) to the runtime's
    provider-managed recording shape at the supervisor boundary.  The
    mapping is a pure projection and its exact inverse; every durable T3
    fact (launch nonce, thread id, paths, base shas, receipts, the SQLite
    store) is unchanged, and the execution owner stays the adapter built
    through :func:`construct_reviewed_adapter` + :func:`bind_reviewed_adapter`.

    Every translation is fail-closed: a ref that is not the exact twin of
    the adapter's retained original ref is refused typed, never guessed.
    """

    #: Read by ``_implementation_adapter_id`` from the CLASS attribute: the
    #: projection claims exactly the reviewed adapter's identity.
    adapter_id = T3_NATIVE_ADAPTER_ID

    def __init__(self, inner: T3ExecutionAdapter) -> None:
        self._inner = inner

    # --- the twin projection (pure, reversible) ---------------------------

    @staticmethod
    def _twin(ref: Any) -> Any:
        return dataclass_replace(
            ref,
            pid=None,
            pgid=None,
            process_start_identity=None,
            boot_session_id=None,
        )

    def _retained(self, ref: Any) -> Any:
        """The durable neutral ref a supervisor-boundary twin must equal."""
        retained = self._inner.retained_original_ref(ref.run_id)
        if retained is None:
            raise T3NativeCompositionError(
                "supervisor boundary ref has no durable retained original "
                f"ref for run {ref.run_id!r}; refusing to translate"
            )
        if self._twin(retained) != ref:
            raise T3NativeCompositionError(
                "supervisor boundary ref is not the twin of the durable "
                f"retained ref for run {ref.run_id!r}; refusing to translate"
            )
        return retained

    # --- adapter surface (supervisor entry points) ------------------------

    async def start(self, spec: Any) -> Any:
        return self._twin(await self._inner.start(spec))

    def launch_attestation(self, process_ref: Any) -> dict[str, Any]:
        retained = self._retained(process_ref)
        attestation = dict(self._inner.launch_attestation(retained))
        # The identity the recovery binding compares is the TWIN's (the
        # provider-managed recording shape), so the attestation must carry
        # exactly that shape — all local-process identity fields None.
        attestation["process_identity"] = {
            "pid": None,
            "pgid": None,
            "session_id": None,
            "start_identity": None,
            "boot_id": None,
            "effective_uid": None,
            "effective_gid": None,
            "real_uid": None,
            "real_gid": None,
        }
        return attestation

    def reattach(self, spec: Any, binding: Any) -> Any:
        # The supervisor calls non-paid reattach SYNCHRONOUSLY and stores the
        # returned ref; the reviewed adapter's reattach is async.  Bridge on
        # a private one-shot loop (the retained-ref recovery path is a pure
        # durable-store read; the replay path's native calls run equally
        # well on it).  Must not be entered from a running event loop.
        retained = self._inner.retained_original_ref(spec.run_id)
        if retained is None:
            # A supervisor-issued binding always follows a completed ACK,
            # which always persisted the receipt + original ref first.  No
            # retained ref means this binding did not come from that path.
            raise T3NativeCompositionError(
                "recovery binding has no durable retained ref for run "
                f"{spec.run_id!r}; refusing to translate"
            )
        neutral_binding = dataclass_replace(binding, process_ref=retained)
        return self._twin(
            asyncio.run(self._inner.reattach(spec, neutral_binding))
        )

    async def status(self, ref: Any) -> Any:
        return await self._inner.status(self._retained(ref))

    async def collect_result(self, ref: Any) -> Any:
        return await self._inner.collect_result(self._retained(ref))

    async def cancel(self, ref: Any, reason: str) -> Any:
        return await self._inner.cancel(self._retained(ref), reason)

    async def interrupt_run(self, ref: Any, reason: str) -> Any:
        return await self._inner.interrupt_run(self._retained(ref), reason)

    async def run_validation_argv(self, spec: Any, argv: Any, **kwargs: Any) -> Any:
        return await self._inner.run_validation_argv(spec, argv, **kwargs)

    def __getattr__(self, name: str) -> Any:
        # Read-only delegation to the reviewed adapter (inspector, durable
        # accessors, anything the supervisor feature-detects).  Attributes
        # the inner adapter does not expose stay absent here too.
        return getattr(self._inner, name)


def compose_t3_native_supervisor(
    primary: Any,
    composition: T3NativeComposition,
    *,
    runs_root: str | Path,
    isolation_roots: tuple[str | Path, ...],
    receipts_root: str | Path | None = None,
    worker_user: str | None = None,
    worker_uid: int | None = None,
    worker_gid: int | None = None,
    process_controller: Any = None,
) -> Any:
    """Build ONE t3-native ExecutiveSupervisor owner for the mixed map.

    The owner shares the primary's Runtime and service instance and uses the
    composed adapter; launch attestation stays legacy-partial (the t3 adapter
    attests through its durable receipts, not a local binary attestation),
    and the process controller is the remote-native one unless a caller with
    its own controller injects it.
    """
    if not composition.composed:
        raise T3NativeCompositionError(
            "supervisor composition requires a composed t3-native adapter"
        )
    from control_plane.executive_supervisor import ExecutiveSupervisor
    runtime = primary.runtime
    return ExecutiveSupervisor(
        runtime,
        SupervisorBoundaryT3Adapter(composition.adapter),
        runs_root=runs_root,
        isolation_roots=isolation_roots,
        receipts_root=receipts_root,
        worker_user=worker_user,
        worker_uid=worker_uid,
        worker_gid=worker_gid,
        shared_run_gid=None,
        secret_canary_verdict=None,
        require_complete_launch_attestation=False,
        process_controller=(
            process_controller or T3NativeProcessController()
        ),
        instance_id=primary.instance_id,
        project_input_owner=primary,
    )


def compose_t3_native_supervisor_owners(
    primary: Any,
    composition: T3NativeComposition,
    *,
    runs_root: str | Path,
    isolation_roots: tuple[str | Path, ...],
    receipts_root: str | Path | None = None,
    worker_user: str | None = None,
    worker_uid: int | None = None,
    worker_gid: int | None = None,
) -> dict[str, Any]:
    """Per-worker t3-native owners for the existing mixed owners map.

    Every worker REGISTERED in the shared Runtime with ``worker_type``
    ``t3-native`` gets one owner over the single composed adapter (the
    paid/fabric precedent: one adapter, one owner per physical worker).
    Unenrolled or no registered t3 workers yields an empty mapping — the
    existing composition stays byte-identical.
    """
    if not composition.composed:
        return {}
    owners: dict[str, Any] = {}
    for worker in primary.runtime.workers.list_workers():
        if worker.worker_type != "t3-native":
            continue
        owners[worker.worker_id] = compose_t3_native_supervisor(
            primary,
            composition,
            runs_root=runs_root,
            isolation_roots=isolation_roots,
            receipts_root=receipts_root,
            worker_user=worker_user,
            worker_uid=worker_uid,
            worker_gid=worker_gid,
        )
    return owners


def compose_t3_native_owners_for_service(
    primary: Any,
    runtime: Any,
    *,
    runs_root: str | Path,
    isolation_roots: tuple[str | Path, ...],
    receipts_root: str | Path | None = None,
    worker_user: str | None = None,
    worker_uid: int | None = None,
    worker_gid: int | None = None,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """The Executive service seam: compose once, return per-worker owners.

    An unenrolled host (no token file) or one with no registered t3-native
    workers composes NOTHING — the existing supervisor composition stays
    byte-identical.  A configured-but-broken enrollment surfaces as its typed
    composition error instead of a silent capability gap.
    """
    composition = compose_t3_native_adapter(
        runtime, inspector=primary.inspector, environ=environ
    )
    if not composition.composed:
        return {}
    return compose_t3_native_supervisor_owners(
        primary,
        composition,
        runs_root=runs_root,
        isolation_roots=isolation_roots,
        receipts_root=receipts_root,
        worker_user=worker_user,
        worker_uid=worker_uid,
        worker_gid=worker_gid,
    )

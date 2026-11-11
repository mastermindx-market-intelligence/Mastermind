"""Rev5 T3 lane LIVE PROOF: one real thread launch + read through T3ExecutionAdapter.

Runs against M2's real T3 server (127.0.0.1:3773) with a short-TTL scoped
bearer session (token from env T3_PROOF_TOKEN; never committed).
Proves: adapter.start -> real t3_thread_launch (clientRequestId idempotency
key persisted BEFORE the native call), adapter.status -> real t3_thread_read
with incremental cursor, adapter.collect_result -> result ledgered before
the CollectionReceipt. Records a secret-free receipt JSON.

A3 audit rework (2026-11-09): the port is the adapter's reference
``T3McpToolPort`` bound to this file's ``McpHttp`` — the namespace is
attested from the bearer token's session claim (``client:<sid>``, never a
guess), ``McpHttp`` raises typed ``T3McpTransportError`` so lost replies are
UNKNOWN outcomes (not clean refusals), interrupts carry ``threadId`` + the
native ``runId``, and the result is read by a dedicated terminal read.  The
recorded receipt (``t3_live_proof_receipt.json``) predates this rework and
is left untouched.
"""
from __future__ import annotations

import asyncio
import base64
import datetime as dt
import hashlib
import json
import os
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

# Import THIS repository's adapter (the old lane worktree path predates the
# A3 rework and would shadow the reworked port/transport API).
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)
))))
sys.path.insert(0, REPO)

from control_plane.child_execution_contracts import (  # noqa: E402
    C1_ROUTINE_BOUNDED,
    ExecutionBinding,
)
from control_plane.t3_execution_adapter import (  # noqa: E402
    InMemoryT3AdapterStateStore,
    T3ExecutionAdapter,
    T3McpToolPort,
    T3McpTransportError,
    T3ThreadLaunchEnvelope,
    T3ThreadLaunchReceipt,
    derive_t3_client_request_id,
    t3_mcp_tool_error_code,
    t3_mcp_upstream_namespace,
)
from control_plane.worker_execution_contract import (  # noqa: E402
    ProcessInspector,
    WorkerLaunchSpec,
)
from pathlib import Path  # noqa: E402

# Finding 8 (R4b review): the LIVE app (3773) is never an implicit target.
# The mint path takes its base explicitly (required argument below); the
# module-level BASE only reflects an explicitly-set env and has NO default.
BASE = os.environ.get("T3_PROOF_BASE_URL")
MCP = (BASE + "/mcp") if BASE else None
OUT = os.environ.get(
    "T3_PROOF_RECEIPT",
    "/Users/chriswong/.hermes/profiles/engineering/cache/scratch/t3_live_proof_receipt.json",
)


def _http_json(url: str, payload: dict | None, *, form: dict | None = None,
               method: str = "POST") -> tuple[int, dict]:
    if form is not None:
        body = urllib.parse.urlencode(form).encode()
        ctype = "application/x-www-form-urlencoded"
    else:
        body = json.dumps(payload or {}).encode()
        ctype = "application/json"
    req = urllib.request.Request(
        url, data=body, method=method,
        headers={"Content-Type": ctype, "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8", "replace") or "{}")
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read().decode("utf-8", "replace") or "{}")
        except ValueError:
            return exc.code, {}


def _pkce() -> tuple[str, str]:
    verifier = base64.urlsafe_b64encode(os.urandom(32)).rstrip(b"=").decode()
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).rstrip(b"=").decode()
    return verifier, challenge


DEFAULT_TOKEN_PATH = (
    "/Users/chriswong/.hermes/profiles/engineering/cache/scratch/t3_proof_token.txt"
)

# The live T3 app's ports are NEVER a mint target for this helper (finding 8:
# 14 pairing codes were minted on the Chairman's own app on 2026-11-10 by a
# helper whose CLI leg fell back to them).  A caller naming one of these
# explicitly is refused, not trusted.
FORBIDDEN_MINT_PORTS = frozenset({3773, 3774})


def _pinned_pairing_target(base_url: str, home_dir: str) -> tuple[str, int]:
    """Resolve and PIN the pairing target, or refuse the mint.

    The ``t3 auth pairing create`` CLI discovers its server from the T3 home
    (``<home>/userdata/server-runtime.json``, pid checked, origin probed) and
    falls back to other homes — including the live app — for a stale or wrong
    home.  So the mint is refused unless the PINNED home's OWN runtime state
    names exactly the pinned base's port with a live pid and a matching
    origin.  Returns ``(base, port)`` with the base normalized (no trailing
    slash); never dials anything."""
    parsed = urllib.parse.urlsplit(base_url or "")
    if parsed.scheme != "http" or parsed.hostname not in ("127.0.0.1",
                                                          "localhost"):
        raise RuntimeError(
            f"pairing target must be a loopback http base, got {base_url!r}")
    port = parsed.port
    if port is None:
        raise RuntimeError(
            f"pairing target must name an explicit port, got {base_url!r}")
    if port in FORBIDDEN_MINT_PORTS:
        raise RuntimeError(
            f"port {port} is the live T3 app; it is never a pairing target")
    home = Path(home_dir)
    state_path = home / "userdata" / "server-runtime.json"
    try:
        raw = state_path.read_text(encoding="utf-8")
        state = json.loads(raw)
    except FileNotFoundError as exc:
        raise RuntimeError(
            f"the pinned home has no server runtime state "
            f"({state_path}); no server provably runs there — refusing to "
            "mint a pairing code") from exc
    except (OSError, ValueError) as exc:
        raise RuntimeError(
            f"the pinned home's server runtime state is unreadable "
            f"({state_path}: {type(exc).__name__}); refusing to mint") from exc
    if not isinstance(state, dict):
        raise RuntimeError(
            f"server runtime state is not an object ({state_path})")
    state_port = state.get("port")
    if state_port != port:
        raise RuntimeError(
            f"the pinned home's server runtime state names port "
            f"{state_port!r}, not the pinned port {port}; refusing to mint")
    pid = state.get("pid")
    if type(pid) is not int or pid <= 0:
        raise RuntimeError(
            f"server runtime state names no live pid ({state_path})")
    try:
        os.kill(pid, 0)
    except (ProcessLookupError, PermissionError) as exc:
        raise RuntimeError(
            f"the home's server (pid {pid} in {state_path}) is not alive; "
            "refusing to mint") from exc
    origin = state.get("origin")
    if isinstance(origin, str):
        origin_parsed = urllib.parse.urlsplit(origin)
        if (origin_parsed.hostname, origin_parsed.port) != (
                parsed.hostname, port):
            raise RuntimeError(
                f"server runtime state origin {origin!r} disagrees with the "
                f"pinned base {base_url!r}; refusing to mint")
    return (f"{parsed.scheme}://{parsed.hostname}:{port}", port)


def obtain_mcp_access_token(
    token_path: str = DEFAULT_TOKEN_PATH,
    label: str = "mastermind-rev5-t3-lane-proof",
    *,
    base_url: str,
    home_dir: str,
) -> tuple[str, dict]:
    """Outside-agent OAuth: register loopback client, approve with a fresh
    short-TTL pairing code via /oauth/mcp/decision, exchange for a token.

    ``base_url`` and ``home_dir`` are REQUIRED and name the exact server this
    mint runs against (finding 8): the pairing CLI is executed only after the
    home's own runtime state is proven to name the pinned port (see
    ``_pinned_pairing_target``), with the CLI's environment pinned to the same
    home and port, and every HTTP leg goes to ``base_url`` — there is no
    default target and never a fallback to the live app (3773).

    The token is cached in scratch so a RERUN reuses the SAME OAuth client
    identity: the authenticated request namespace is part of T3's launch
    idempotency identity (namespace+key -> commandId), so the same client +
    same clientRequestId replays the SAME thread instead of minting a new
    one (live-verified: two different clients, same key -> two threads).
    Never committed; scratch only.  ``token_path`` selects the cache (one file
    per OAuth client identity — the A4 canary's second client uses its own
    file); ``label`` names the pairing and the registered client.  The token
    and the pairing code are never printed or logged."""
    import subprocess

    if os.path.exists(token_path):
        cached = open(token_path).read().strip()
        if cached:
            _log("oauth.token.reused", note="same client identity -> replay-safe namespace")
            return cached, {"client_id": "cached"}

    base, port = _pinned_pairing_target(base_url, home_dir)
    home = str(Path(home_dir))

    proc = subprocess.run(
        ["/Users/chriswong/.t3/bin/t3", "auth", "pairing", "create",
         "--ttl", "15m", "--label", label, "--json"],
        capture_output=True, text=True, timeout=60,
        # Pinned env: the CLI leg must see exactly the pinned home and port,
        # never an ambient T3CODE_HOME/T3CODE_PORT from another server.
        env={**os.environ, "T3CODE_HOME": home, "T3CODE_PORT": str(port)},
    )
    if proc.returncode != 0:
        raise RuntimeError(f"pairing create failed: {proc.stderr[:300]}")
    pairing = json.loads(proc.stdout)
    code = pairing.get("token") or pairing.get("credential") or pairing.get("code")
    if not code:
        raise RuntimeError(f"pairing create returned no code: {proc.stdout[:300]}")
    _log("pairing.create.ok", ttl="15m", label=label)

    redirect_uri = "http://localhost:51234/callback"
    status, reg = _http_json(
        base + "/oauth/mcp/register",
        {
            "client_name": label,
            "redirect_uris": [redirect_uri],
            "grant_types": ["authorization_code", "refresh_token"],
            "token_endpoint_auth_method": "none",
        },
    )
    if status != 201:
        raise RuntimeError(f"oauth register failed {status}: {reg}")
    client_id = reg["client_id"]

    verifier, challenge = _pkce()
    auth_params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": "t3-proof-state-1",
        "resource": MCP,
    }
    status, decision = _http_json(
        base + "/oauth/mcp/decision",
        {
            "authorization": auth_params,
            "decision": {"_tag": "pairing-code", "access": "auto", "code": code},
        },
    )
    if status != 200 or not decision.get("redirectTo"):
        raise RuntimeError(f"oauth decision failed {status}: {decision}")
    callback = urllib.parse.urlparse(decision["redirectTo"])
    grant_code = urllib.parse.parse_qs(callback.query).get("code", [""])[0]
    if not grant_code:
        raise RuntimeError(f"decision redirectTo lacks code: {decision}")

    status, token = _http_json(
        base + "/oauth/mcp/token",
        None,
        form={
            "grant_type": "authorization_code",
            "code": grant_code,
            "redirect_uri": redirect_uri,
            "client_id": client_id,
            "code_verifier": verifier,
            "resource": MCP,
        },
    )
    if status != 200 or not token.get("access_token"):
        raise RuntimeError(f"oauth token failed {status}: {token}")
    fd = os.open(token_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as fh:
        fh.write(token["access_token"])
    _log("oauth.token.ok", scope=token.get("scope"))
    return token["access_token"], reg


TOKEN = None  # obtained inside main()
_hex64 = lambda n: n  # noqa: E731

PROOF_LOG: dict = {"events": []}


def _log(event: str, **facts) -> None:
    entry = {"t": dt.datetime.now(dt.timezone.utc).isoformat(), "event": event}
    entry.update(facts)
    PROOF_LOG["events"].append(entry)
    print(f"[proof] {event} {facts if facts else ''}", flush=True)


class McpHttp:
    """Minimal streamable-HTTP MCP client (stdlib only)."""

    def __init__(self, token: str, mcp_url: str | None = None) -> None:
        self._token = token
        # Finding 8 (R4b review): the target is named EXPLICITLY (or by an
        # explicitly-set T3_PROOF_BASE_URL at import); there is no implicit
        # target and never a fallback to the live app (3773).
        self._mcp_url = mcp_url or MCP
        self._session_id: str | None = None
        self._next_id = 0
        self.protocol_version = "2025-03-26"

    def _post(self, payload: dict, *, expect_reply: bool = True) -> dict | None:
        if not self._mcp_url:
            raise RuntimeError(
                "the MCP target must be named explicitly (mcp_url=... or "
                "T3_PROOF_BASE_URL); no implicit target exists")
        body = json.dumps(payload).encode()
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "Authorization": f"Bearer {self._token}",
        }
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id
        req = urllib.request.Request(self._mcp_url, data=body, headers=headers, method="POST")
        after = T3McpTransportError.AFTER_SEND
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                sid = resp.headers.get("Mcp-Session-Id") or resp.headers.get(
                    "mcp-session-id"
                )
                if sid:
                    self._session_id = sid
                ctype = resp.headers.get("Content-Type", "")
                raw = resp.read().decode("utf-8", "replace")
                status = resp.status
        except urllib.error.HTTPError as exc:
            # An explicit upstream HTTP answer: the port classifies 4xx as a
            # refusal and 408/5xx as an unknown outcome.
            detail = exc.read().decode("utf-8", "replace")[:500]
            raise T3McpTransportError(
                f"HTTP {exc.code}: {detail}", phase=after, http_status=exc.code
            ) from exc
        except urllib.error.URLError as exc:
            # Connection refused / name resolution: nothing was delivered.
            # Anything else (timeout, reset) may have been delivered.
            pre = isinstance(exc.reason, (ConnectionRefusedError, socket.gaierror))
            raise T3McpTransportError(
                f"transport failure: {exc.reason}",
                phase=T3McpTransportError.PRE_SEND if pre else after,
            ) from exc
        except (TimeoutError, ConnectionError, OSError) as exc:
            # Timeout or reset while sending/reading: the reply was lost.
            raise T3McpTransportError(f"transport failure: {exc}", phase=after) from exc
        if not expect_reply:
            return None
        if status != 200:
            raise T3McpTransportError(
                f"HTTP {status} {ctype}: {raw[:300]}", phase=after, http_status=status
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

    def initialize(self) -> dict:
        resp = self._post(
            {
                "jsonrpc": "2.0",
                "id": self._rpc_id(),
                "method": "initialize",
                "params": {
                    "protocolVersion": self.protocol_version,
                    "capabilities": {},
                    "clientInfo": {
                        "name": "mastermind-rev5-t3-lane-proof",
                        "version": "1.0.0",
                    },
                },
            }
        )
        result = resp.get("result") or {}
        server_pv = result.get("protocolVersion")
        if server_pv and server_pv != self.protocol_version:
            self.protocol_version = server_pv
        if resp.get("error"):
            raise RuntimeError(f"initialize failed: {resp['error']}")
        self._post(
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            expect_reply=False,
        )
        return result

    def _rpc_id(self) -> int:
        self._next_id += 1
        return self._next_id

    def call_tool(self, name: str, arguments: dict) -> dict:
        resp = self._post(
            {
                "jsonrpc": "2.0",
                "id": self._rpc_id(),
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments},
            }
        )
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
            # A4 / re-audit N1: carry the donor's declared-failure code (if
            # the body has the exact donor shape) so the port can tell a
            # proven pre-dispatch refusal from a post-commit failure; a
            # codeless isError (defect, internal error) stays UNKNOWN.
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


class LiveT3McpPort(T3McpToolPort):
    """Real T3NativeClientPort over the authenticated MCP HTTP transport.

    The adapter's reference :class:`T3McpToolPort` bound to ``McpHttp``: the
    upstream namespace is attested from the bearer token's session claim
    (``client:<sid>`` — the identity T3 scopes launch idempotency by), the
    receipt echoes come only from the upstream thread id, every lost reply
    is an unknown outcome, interrupts are exact-run, and the result is read
    by a dedicated terminal read.  The token is used for attestation only
    and is not stored on the port.
    """

    def __init__(self, mcp: McpHttp, token: str) -> None:
        super().__init__(
            mcp.call_tool,
            upstream_namespace=t3_mcp_upstream_namespace(token),
            launch_arguments={"scratch": True},
        )
        self._mcp = mcp

    def _launch(self, envelope: T3ThreadLaunchEnvelope, op: str) -> T3ThreadLaunchReceipt:
        _log(f"port.{op}", clientRequestId=envelope.client_request_id)
        receipt = super()._launch(envelope, op)
        _log(
            f"port.{op}.ok",
            threadId=receipt.thread_id,
            runId=receipt.run_id,
            status=receipt.status,
            link=receipt.link,
            upstream_echo_proven=bool(receipt.client_request_id),
        )
        return receipt


class ProofInspector(ProcessInspector):
    def boot_session_id(self) -> str:
        return "proof-boot-1"

    def identity(self, pid: int) -> tuple[str, int]:
        return (f"proof-identity-{pid}", pid)

    def inspect(self, pid: int) -> object:
        return {"pid": pid, "proof": True}


async def main() -> None:
    if not BASE or not MCP:
        raise SystemExit(
            "T3_PROOF_BASE_URL is required (no default; the live app on 3773 "
            "is never an implicit target)")
    home = os.environ.get("T3_PROOF_HOME")
    if not home:
        raise SystemExit(
            "T3_PROOF_HOME is required: it names the pinned server's home "
            "whose runtime state must name the base's port")
    token, oauth_client = obtain_mcp_access_token(
        base_url=BASE, home_dir=home)
    mcp = McpHttp(token)
    init = mcp.initialize()
    _log(
        "mcp.initialize.ok",
        server=init.get("serverInfo", {}),
        protocolVersion=init.get("protocolVersion"),
        session=bool(mcp._session_id),
    )
    env = mcp.call_tool("t3_environment_read", {})
    _log(
        "t3_environment_read",
        environmentId=env.get("environmentId"),
        label=env.get("label"),
        serverVersion=env.get("serverVersion"),
        platform=env.get("platform"),
    )

    now = dt.datetime.now(dt.timezone.utc)
    binding = ExecutionBinding(
        root_run_ref="roots/rev5-t3-lane-proof",
        immediate_parent_run_ref="parents/fable-ceo",
        logical_child_key="t3-live-proof-2026-11-08",
        request_digest="9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08",
        effective_complexity=C1_ROUTINE_BOUNDED,
        adapter_id="t3-native",
        worker_id="workers/t3-proof-1",
        host_id="m2-studio",
        lease_expiry=(now + dt.timedelta(minutes=30)).isoformat(),
    )
    spec = WorkerLaunchSpec(
        run_id="runs/t3-live-proof-1",
        job_id="jobs/rev5-t3-lane-proof",
        worker_id="workers/t3-proof-1",
        workspace_path=Path("/Users/chriswong/.hermes/profiles/engineering/cache/scratch/t3-proof-ws"),
        run_dir=Path("/Users/chriswong/.hermes/profiles/engineering/cache/scratch/t3-proof-run"),
        prompt=(
            "This is a one-shot Mastermind Executive integration proof of the "
            "T3 native execution lane. Do not use any tools. Reply with "
            "exactly this line and nothing else: T3-PROOF-OK"
        ),
        result_schema_path=Path("/Users/chriswong/.hermes/profiles/engineering/cache/scratch/t3-proof-result.json"),
        model=json.dumps(
            {
                "instanceId": "GLM2",
                "model": "glm-5.3-flash",
            }
        ),  # the environment's configured ZAI GLM2 instance; glm-5.3-flash is
        # its cheapest model (the free OpenCode lane was listed in the catalog
        # but stalled in delivery -- catalog visibility is not readiness)
    )
    port = LiveT3McpPort(mcp, token)
    state_store = InMemoryT3AdapterStateStore()
    adapter = T3ExecutionAdapter(
        port,
        binding_source=lambda s: binding,
        inspector=ProofInspector(),
        state_store=state_store,
    )

    # Verify intent-before-native-call ordering LIVE: the port checks the
    # intent store is already populated when launch_thread is entered.
    original_launch = port.launch_thread

    async def checked_launch(envelope):
        assert adapter.launch_intent(envelope.run_id) is not None, (
            "intent must be persisted before native call"
        )
        return await original_launch(envelope)

    port.launch_thread = checked_launch  # type: ignore[method-assign]

    t0 = time.monotonic()
    ref = await adapter.start(spec)
    _log(
        "adapter.start.ok",
        run_id=ref.run_id,
        pid=ref.pid,
        receipt_before_ack=True,
        elapsed_s=round(time.monotonic() - t0, 2),
    )
    receipt = adapter.launch_receipt(spec.run_id)
    _log(
        "launch.receipt",
        threadId=receipt.thread_id,
        nativeRunId=receipt.run_id,
        clientRequestId=receipt.client_request_id,
        derived_key_matches=derive_t3_client_request_id(binding)
        == receipt.client_request_id,
        link=receipt.link,
    )

    statuses = []
    deadline = time.monotonic() + 420
    terminal = False
    while time.monotonic() < deadline:
        st = await adapter.status(ref)
        statuses.append(st.value)
        _log("adapter.status", state=st.value)
        from control_plane.worker_execution_contract import WorkerRunStatus

        if st in (
            WorkerRunStatus.SUCCEEDED,
            WorkerRunStatus.FAILED,
            WorkerRunStatus.CANCELLED,
            WorkerRunStatus.TIMED_OUT,
            WorkerRunStatus.INVALID_RESULT,
        ):
            terminal = True
            break
        await asyncio.sleep(10)

    collected = None
    collect_error = None
    try:
        collected = await adapter.collect_result(ref)
    except Exception as exc:
        collect_error = str(exc)
    result_ledger_entry = adapter.result_ledger_entry(spec.run_id)
    ledger_before_receipt = result_ledger_entry is not None
    _log(
        "adapter.collect_result",
        ok=collected is not None,
        error=collect_error,
        ledgered_before_receipt=ledger_before_receipt,
        collection_status=collected.result.status.value if collected else None,
        exit_code=collected.result.exit_code if collected else None,
        result_sha256=(collected.result_sha256 or "")[:16] if collected else None,
    )

    proof = {
        "schema": "mastermind.t3_live_proof_receipt/v1",
        "recorded_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "environment": {
            "environmentId": env.get("environmentId"),
            "label": env.get("label"),
            "serverVersion": env.get("serverVersion"),
            "platform": env.get("platform"),
            "endpoint": MCP,
        },
        "company": {
            "run_id": spec.run_id,
            "job_id": spec.job_id,
            "worker_id": spec.worker_id,
            "binding_adapter": binding.adapter_id,
            "binding_host": binding.host_id,
            "client_request_id": receipt.client_request_id,
            "request_namespace": receipt.request_namespace,
        },
        "native": {
            "thread_id": receipt.thread_id,
            "run_id": receipt.run_id,
            "project_id": receipt.project_id,
            "link": receipt.link,
            "launch_status": receipt.status,
        },
        "observed": {
            "status_sequence": statuses,
            "reached_terminal": terminal,
            "result_ledgered_before_receipt": ledger_before_receipt,
            "intent_persisted_before_native_call": True,
            "port_call_sequence": port.calls,
            "collection_result_digest": collected.result_digest
            if hasattr(collected, "result_digest")
            else None,
        },
        "result_excerpt": (
            result_ledger_entry.result_ref[:200]
            if result_ledger_entry is not None
            else None
        ),
        "result_payload_excerpt": None,
        "events": PROOF_LOG["events"],
    }
    # Capture the exact run's final text through the dedicated terminal read.
    try:
        last = await port.read_result(receipt.thread_id, receipt.run_id)
        proof["result_payload_excerpt"] = (
            str(last.result_payload.get("text", ""))[-300:] or None
        )
    except Exception as exc:  # non-fatal for the receipt
        proof["result_payload_excerpt"] = f"read-back skipped: {exc}"

    with open(OUT, "w") as fh:
        json.dump(proof, fh, indent=2)
    _log("proof.receipt.written", path=OUT, terminal=terminal)
    print(json.dumps({k: v for k, v in proof.items() if k != "events"}, indent=2))


if __name__ == "__main__":
    asyncio.run(main())

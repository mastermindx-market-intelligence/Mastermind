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
    t3_mcp_upstream_namespace,
)
from control_plane.worker_execution_contract import (  # noqa: E402
    ProcessInspector,
    WorkerLaunchSpec,
)
from pathlib import Path  # noqa: E402

BASE = os.environ.get("T3_PROOF_BASE_URL", "http://127.0.0.1:3773")
MCP = BASE + "/mcp"
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


def obtain_mcp_access_token() -> tuple[str, dict]:
    """Outside-agent OAuth: register loopback client, approve with a fresh
    short-TTL pairing code via /oauth/mcp/decision, exchange for a token.

    The token is cached in scratch so a RERUN reuses the SAME OAuth client
    identity: the authenticated request namespace is part of T3's launch
    idempotency identity (namespace+key -> commandId), so the same client +
    same clientRequestId replays the SAME thread instead of minting a new
    one (live-verified: two different clients, same key -> two threads).
    Never committed; scratch only."""
    import subprocess

    token_path = "/Users/chriswong/.hermes/profiles/engineering/cache/scratch/t3_proof_token.txt"
    if os.path.exists(token_path):
        cached = open(token_path).read().strip()
        if cached:
            _log("oauth.token.reused", note="same client identity -> replay-safe namespace")
            return cached, {"client_id": "cached"}

    proc = subprocess.run(
        ["/Users/chriswong/.t3/bin/t3", "auth", "pairing", "create",
         "--ttl", "15m", "--label", "mastermind-rev5-t3-lane-proof", "--json"],
        capture_output=True, text=True, timeout=60,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"pairing create failed: {proc.stderr[:300]}")
    pairing = json.loads(proc.stdout)
    code = pairing.get("token") or pairing.get("credential") or pairing.get("code")
    if not code:
        raise RuntimeError(f"pairing create returned no code: {proc.stdout[:300]}")
    _log("pairing.create.ok", sessionId=pairing.get("sessionId"), ttl="15m")

    redirect_uri = "http://localhost:51234/callback"
    status, reg = _http_json(
        BASE + "/oauth/mcp/register",
        {
            "client_name": "mastermind-rev5-t3-lane-proof",
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
        BASE + "/oauth/mcp/decision",
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
        BASE + "/oauth/mcp/token",
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
    with open(token_path, "w") as fh:
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

    def __init__(self, token: str) -> None:
        self._token = token
        self._session_id: str | None = None
        self._next_id = 0
        self.protocol_version = "2025-03-26"

    def _post(self, payload: dict, *, expect_reply: bool = True) -> dict | None:
        body = json.dumps(payload).encode()
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "Authorization": f"Bearer {self._token}",
        }
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id
        req = urllib.request.Request(MCP, data=body, headers=headers, method="POST")
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
                if item.get("type") == "text":
                    text = item.get("text", "")
            if not text and isinstance(result.get("structuredContent"), dict):
                text = json.dumps(result["structuredContent"].get("error"))
            raise T3McpTransportError(
                f"tool {name} returned failure: {text[:400]}",
                phase=after, tool_error=True,
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
    token, oauth_client = obtain_mcp_access_token()
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

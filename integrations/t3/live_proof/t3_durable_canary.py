"""Rev5 T3 lane — LIVE DURABLE CANARY (Director A2).

Turns the fake-port cold-restart proof (tests/test_t3_adapter_durability.py)
into a REAL-PATH proof against the live T3 server on this Mac
(http://127.0.0.1:3773, environment m2studio): the crash points move from a
counting fake port to deterministic ``os._exit`` hooks in HARNESS wrappers
(never in the adapter), the recovery processes are SEPARATE OS PROCESSES
sharing one ``SQLiteT3AdapterStateStore`` on disk, and every launch/replay is
a real authenticated ``t3_thread_launch`` under the cheapest ENABLED model
``orchestrator_capabilities`` reports at run time.

Scenarios (thread budget: AT MOST 3 real threads, all labeled MMOS durable
canary; T3 owns their lifecycle — nothing is deleted or archived here):

* S1 crash-after-receipt — P1 persists intent -> REAL launch -> persists
  receipt -> ``os._exit`` BEFORE the start ACK.  P2 (fresh process, fresh
  adapter, same store, same cached OAuth token = same authenticated
  namespace) reattaches R1 and must get the retained original ref with ZERO
  native launch/replay calls, then reads to terminal and collects.
* S2 crash-after-launch-before-receipt — P1's port wrapper crashes AFTER the
  native launch returned but BEFORE the receipt is persisted.  P2 replays the
  SAME clientRequestId + namespace (upstream idempotency MUST return the
  ORIGINAL thread), asserts the thread id equals P1's side-file record and
  that the thread shows exactly one run.
* S3 foreign namespace — an adapter whose port REPORTS a different
  authenticated principal (stubbed ``authenticated_namespace``; no second
  OAuth client is created) must REFUSE reattach of R1/R2 locally with zero
  native calls.
* S4 exact-run interrupt honesty (3rd thread) — start, interrupt through the
  adapter, assert the requested-vs-settled ledger NEVER claims a settle
  without a terminal observation.  LIVE FINDING (m2studio, T3 0.1.7): T3
  reclaims interrupted scratch threads from the exact-run read path, so the
  settle observation legitimately comes from the project-scoped thread row
  (status "interrupted", upstream settled=false) — recorded as observed,
  never inferred.

Read-only verification roles (``--role s1-verify`` / ``s2-verify`` /
``s4-verify``) cold-reattach a TERMINAL run and re-observe it with ZERO
launch/replay calls; ``--assemble`` rebuilds the receipt from the current
batch's side files + role logs without spawning anything.  These exist
because the terminal status polls advance the persisted read cursor PAST
the final assistant reply, which can leave ``collect_result``'s page empty
(the reply text is then re-observed by a verification head read and merged
into the receipt as ``verification`` — the ORIGINAL process's launch/replay
counts are never overwritten).

Auth reuses the existing PROVEN_LIVE harness ``t3_live_proof.py``: the same
outside-agent OAuth pairing flow and the SAME scratch token cache, so every
process in one canary run shares ONE OAuth client identity (the live-proof
finding-1 rule: the authenticated principal is part of launch idempotency,
so P2 must replay under P1's identity, never a fresh one).  The token itself
is never printed, logged, or written to any side file — only its sha256
prefix (the principal projection) is recorded.

Receipt: secret-free JSON written next to this file
(``t3_durable_canary_receipt.json``), pinned by
``tests/test_t3_durable_canary_receipt.py``.

Run:  env -u PYTHONPATH /opt/homebrew/bin/python3.12 \
          integrations/t3/live_proof/t3_durable_canary.py
"""
from __future__ import annotations

import argparse
import asyncio
import dataclasses
import datetime as dt
import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]  # .../integrations/t3/live_proof -> repo root
sys.path.insert(0, str(REPO))

# Import every control_plane module BEFORE importing the proof harness: the
# harness inserts the OLD lane worktree at sys.path[0] at import time, and
# this canary must run against THIS worktree's adapter code.
from control_plane.child_execution_contracts import (  # noqa: E402
    C1_ROUTINE_BOUNDED,
    ExecutionBinding,
)
from control_plane.t3_execution_adapter import (  # noqa: E402
    _T3_REMOTE_BINARY_PLACEHOLDER,
    SQLiteT3AdapterStateStore,
    T3ExecutionAdapter,
    T3ExecutionAdapterError,
    T3InterruptOutcome,
    T3ThreadLaunchEnvelope,
    T3ThreadLaunchReceipt,
    T3ThreadReadResult,
    t3_request_namespace,
)
from control_plane.worker_execution_contract import (  # noqa: E402
    ProcessInspector,
    WorkerLaunchSpec,
    WorkerProcessRef,
    WorkerRecoveryBinding,
    WorkerRunStatus,
)

sys.path.insert(0, str(REPO / "integrations" / "t3" / "live_proof"))
import t3_live_proof as _harness  # noqa: E402  (attribution: auth flow reused)

for _mod_name in (
    "control_plane.t3_execution_adapter",
    "control_plane.worker_execution_contract",
    "control_plane.child_execution_contracts",
):
    _mod_file = str(sys.modules[_mod_name].__file__)
    assert _mod_file.startswith(str(REPO)), (
        f"{_mod_name} must resolve from THIS worktree, got {_mod_file}"
    )

obtain_mcp_access_token = _harness.obtain_mcp_access_token
TOKEN_CACHE = Path(
    "/Users/chriswong/.hermes/profiles/engineering/cache/scratch/t3_proof_token.txt"
)

BASE = os.environ.get("T3_PROOF_BASE_URL", "http://127.0.0.1:3773")
MCP = BASE + "/mcp"
SCRATCH_ROOT = Path(
    os.environ.get(
        "T3_CANARY_ROOT",
        "/Users/chriswong/.hermes/profiles/engineering/cache/scratch/t3_durable_canary",
    )
)
RECEIPT_OUT = REPO / "integrations" / "t3" / "live_proof" / "t3_durable_canary_receipt.json"

CANARY_LABEL = "MMOS durable canary"
JOB_ID = "jobs/mmos-rev5-durable-canary"
WORKER_ID = "workers/t3-canary-1"
HOST_ID = "m2-studio"
PREFERRED_MODEL = "glm-5.3-flash"  # expected cheapest ENABLED; verified live in prep

CRASH_EXIT_AFTER_RECEIPT = 90  # S1-P1 expected process exit code
CRASH_EXIT_AFTER_LAUNCH = 91  # S2-P1 expected process exit code

SCENARIOS = {
    "s1": {"run_id": "runs/t3-durable-canary/s1-r1", "nonce": "durable-s1"},
    "s2": {"run_id": "runs/t3-durable-canary/s2-r2", "nonce": "durable-s2"},
    "s4": {"run_id": "runs/t3-durable-canary/s4-r3", "nonce": "durable-s4"},
}

_LAST_TOKEN: list[str] = [""]  # for error redaction only; never recorded


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _log(events: list, event: str, **facts) -> None:
    entry = {"t": _now(), "event": event}
    entry.update(facts)
    events.append(entry)
    print(f"[canary] {event} {facts if facts else ''}", file=sys.stderr, flush=True)


def _redact(text: object) -> str:
    value = str(text)
    if _LAST_TOKEN[0]:
        value = value.replace(_LAST_TOKEN[0], "<redacted-token>")
    return value[:500]


def _write_side(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2, default=str) + "\n")
    tmp.replace(path)


def _side_path(role: str) -> Path:
    return SCRATCH_ROOT / "batch" / "side" / f"{role}.json"


def _load_side(name: str) -> dict:
    path = _side_path(name)
    return json.loads(path.read_text()) if path.exists() else {}


# ---------------------------------------------------------------------------
# Company-side fixtures (proof-scope binding + spec per scenario run)
# ---------------------------------------------------------------------------


def make_binding(run_key: str) -> ExecutionBinding:
    digest = hashlib.sha256(f"mmos-rev5-durable-canary/{run_key}".encode()).hexdigest()
    lease = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=45)).isoformat()
    return ExecutionBinding(
        root_run_ref="roots/mmos-rev5-durable-canary",
        immediate_parent_run_ref="parents/fable-director-a2",
        logical_child_key=f"t3-durable-canary-{run_key}",
        request_digest=digest,
        effective_complexity=C1_ROUTINE_BOUNDED,
        adapter_id="t3-native",
        worker_id=WORKER_ID,
        host_id=HOST_ID,
        lease_expiry=lease,
    )


def make_spec(scenario: str, model_selection: str) -> WorkerLaunchSpec:
    """Build the P1-side spec AND its durable run dir + prompt file."""
    conf = SCENARIOS[scenario]
    run_dir = SCRATCH_ROOT / "batch" / "runs" / scenario
    (run_dir / "input").mkdir(parents=True, exist_ok=True)
    prompt = (
        f"{CANARY_LABEL} — scenario {scenario.upper()} (cold-restart durability "
        f"proof, run {conf['run_id']}). Do not use any tools. Reply with "
        f"exactly this line and nothing else: T3-CANARY-OK {conf['nonce']}"
    )
    prompt_path = run_dir / "input" / "prompt.txt"
    prompt_path.write_text(prompt)
    os.chmod(prompt_path, 0o600)
    return WorkerLaunchSpec(
        run_id=conf["run_id"],
        job_id=JOB_ID,
        worker_id=WORKER_ID,
        workspace_path=SCRATCH_ROOT / "batch" / "runs" / f"{scenario}-ws",
        run_dir=run_dir,
        prompt=prompt,
        result_schema_path=run_dir / "input" / "schema.json",
        model=model_selection,
    )


class CanaryInspector(ProcessInspector):
    def boot_session_id(self) -> str:
        return "t3-durable-canary-boot-1"

    def identity(self, pid: int) -> tuple[str, int]:
        return (f"canary-identity-{pid}", pid)

    def inspect(self, pid: int) -> object:
        return {"pid": pid, "canary": True}


def binding_source_for(spec: WorkerLaunchSpec) -> ExecutionBinding | None:
    for key in SCENARIOS:
        if SCENARIOS[key]["run_id"] == spec.run_id:
            return make_binding(key)
    return None


# ---------------------------------------------------------------------------
# Live MCP client (verbatim from t3_live_proof.McpHttp) and the canary port
# wrapper (call counting + crash hook + principal projection/stub).
# ---------------------------------------------------------------------------


class McpHttp:
    """Minimal streamable-HTTP MCP client — verbatim from t3_live_proof.py."""

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
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                sid = resp.headers.get("Mcp-Session-Id") or resp.headers.get(
                    "mcp-session-id"
                )
                if sid:
                    self._session_id = sid
                ctype = resp.headers.get("Content-Type", "")
                raw = resp.read().decode("utf-8", "replace")
                status = resp.status
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:500]
            raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc
        if not expect_reply:
            return None
        if status != 200:
            raise RuntimeError(f"HTTP {status} {ctype}: {raw[:300]}")
        if "text/event-stream" in ctype:
            data = None
            for line in raw.splitlines():
                if line.startswith("data:"):
                    data = line[5:].strip()
            if data is None:
                raise RuntimeError("SSE response carried no data frame")
            return json.loads(data)
        return json.loads(raw)

    def initialize(self) -> dict:
        resp = self._post(
            {
                "jsonrpc": "2.0",
                "id": self._rpc_id(),
                "method": "initialize",
                "params": {
                    "protocolVersion": self.protocol_version,
                    "capabilities": {},
                    "clientInfo": {"name": "mmos-t3-durable-canary", "version": "1.0.0"},
                },
            }
        )
        result = resp.get("result") or {}
        if resp.get("error"):
            raise RuntimeError(f"initialize failed: {resp['error']}")
        server_pv = result.get("protocolVersion")
        if server_pv:
            self.protocol_version = server_pv
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
        if resp.get("error"):
            raise RuntimeError(f"tools/call {name} JSON-RPC error: {resp['error']}")
        result = resp.get("result") or {}
        if result.get("isError"):
            text = ""
            for item in result.get("content") or []:
                if item.get("type") == "text":
                    text = item.get("text", "")
            raise RuntimeError(f"tool {name} returned failure: {text[:400]}")
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
        raise RuntimeError(f"tool {name} returned no parsable payload")


class CanaryLivePort:
    """Real T3NativeClientPort over the authenticated MCP transport.

    Same seam as t3_live_proof.LiveT3McpPort (attribution), plus: per-op call
    COUNTING; an optional crash hook AFTER the native launch returned (S2's
    crash point — between port.launch_thread and the adapter's receipt
    write); an honest ``authenticated_namespace`` (sha256 prefix of the
    access token — the cached token IS the OAuth client identity projection;
    two tokens are two principals, live finding 1); a CORRECT exact-run
    interrupt (the donor tool wants ``threadId``, taken from the retained
    ref's provider_session_id); and run-count capture from every read
    (``recentRuns``) for the exactly-one-run assertion.
    """

    def __init__(
        self,
        mcp: McpHttp,
        *,
        token: str = "",
        crash_after_launch: bool = False,
        crash_side_path: Path | None = None,
        namespace_override: str | None = None,
        events: list | None = None,
    ) -> None:
        self._mcp = mcp
        self._token = token
        self._crash_after_launch = crash_after_launch
        self._crash_side_path = crash_side_path
        self._namespace_override = namespace_override
        self._events = events if events is not None else []
        self.calls: list[dict] = []
        self.runs_observed: list[list[dict]] = []

    # -- principal -----------------------------------------------------------
    def authenticated_namespace(self) -> str:
        if self._namespace_override is not None:
            return self._namespace_override
        return hashlib.sha256(self._token.encode()).hexdigest()[:16]

    def _counts(self) -> dict:
        return {
            "launch": sum(1 for c in self.calls if c["op"] == "launch"),
            "replay": sum(1 for c in self.calls if c["op"] == "replay"),
            "read": sum(1 for c in self.calls if c["op"] == "read"),
            "interrupt": sum(1 for c in self.calls if c["op"] == "interrupt"),
        }

    def counts(self) -> dict:
        return self._counts()

    # -- port surface ----------------------------------------------------------
    async def launch_thread(self, envelope: T3ThreadLaunchEnvelope) -> T3ThreadLaunchReceipt:
        args = {
            "title": envelope.title,
            "message": envelope.message,
            "scratch": True,
            "clientRequestId": envelope.client_request_id,
        }
        if envelope.model_selection:
            if envelope.model_selection.strip().startswith("{"):
                args["modelSelection"] = json.loads(envelope.model_selection)
            else:
                args["modelSelection"] = {"instanceId": envelope.model_selection}
        self.calls.append({"op": "launch", "clientRequestId": envelope.client_request_id})
        _log(self._events, "port.launch_thread", clientRequestId=envelope.client_request_id)
        payload = self._mcp.call_tool("t3_thread_launch", args)
        receipt = T3ThreadLaunchReceipt(
            thread_id=str(payload.get("threadId") or ""),
            run_id=str(payload.get("runId") or ""),
            project_id=str(payload.get("projectId") or ""),
            status=str(payload.get("status") or ""),
            link=str(payload.get("link") or ""),
            request_namespace=envelope.request_namespace,
            client_request_id=envelope.client_request_id,
            created_at=_now(),
        )
        _log(
            self._events, "port.launch_thread.ok",
            threadId=receipt.thread_id, runId=receipt.run_id, status=receipt.status,
        )
        if self._crash_after_launch:
            # S2 crash point: the native launch TOOK EFFECT upstream; the
            # adapter never sees the receipt.  Record what P1 knew, then
            # hard-exit (no atexit, no cleanup, no ACK).
            assert self._crash_side_path is not None
            _write_side(
                self._crash_side_path,
                {
                    "role": os.environ.get("T3_CANARY_ROLE", "?"),
                    "pid": os.getpid(),
                    "crash_point": "after_launch_before_receipt_persist",
                    "client_request_id": envelope.client_request_id,
                    "request_namespace": envelope.request_namespace,
                    "native": {
                        "thread_id": receipt.thread_id,
                        "run_id": receipt.run_id,
                        "project_id": receipt.project_id,
                        "launch_status": receipt.status,
                    },
                    "port_counts": self._counts(),
                    "crashed_at": _now(),
                },
            )
            _log(self._events, "crash.after_launch", threadId=receipt.thread_id)
            sys.stderr.flush()
            sys.stdout.flush()
            os._exit(CRASH_EXIT_AFTER_LAUNCH)
        return receipt

    async def replay_launch(self, envelope: T3ThreadLaunchEnvelope) -> T3ThreadLaunchReceipt:
        # Upstream idempotency: same authenticated session + same
        # clientRequestId returns the ORIGINAL thread (never a fresh mint).
        self.calls.append({"op": "replay", "clientRequestId": envelope.client_request_id})
        _log(self._events, "port.replay_launch", clientRequestId=envelope.client_request_id)
        saved = self._crash_after_launch
        self._crash_after_launch = False  # the replay never carries the hook
        try:
            receipt = await self.launch_thread(envelope)
        finally:
            self._crash_after_launch = saved
        # calls now carries BOTH the replay op and its underlying launch call
        # (the replay IS the same upstream launch command, re-issued).
        return receipt

    async def read_thread(
        self, thread_id: str, run_id: str, cursor: str
    ) -> T3ThreadReadResult:
        args = {
            "threadId": thread_id,
            "view": "messages",
            "limit": 20,
            "maxCharsPerItem": 4000,
            "runLimit": 10,
        }
        if cursor:
            args["afterPosition"] = int(cursor)
        self.calls.append({"op": "read", "threadId": thread_id, "cursor": cursor})
        payload = self._mcp.call_tool("t3_thread_read", args)
        thread = payload.get("thread") if isinstance(payload.get("thread"), dict) else {}
        native_status = str(thread.get("status") or payload.get("status") or "")
        runs_slim = [
            {
                "id": str(r.get("id") or ""),
                "ordinal": r.get("ordinal"),
                "status": str(r.get("status") or ""),
            }
            for r in (payload.get("recentRuns") or [])
            if isinstance(r, dict)
        ]
        self.runs_observed.append(runs_slim)
        items = payload.get("items") or []
        next_pos = payload.get("nextPosition")
        last_text = ""
        for item in items:
            if item.get("text"):
                last_text = str(item["text"])
            for part in item.get("parts") or []:
                if isinstance(part, dict) and part.get("text"):
                    last_text = str(part["text"])
        return T3ThreadReadResult(
            thread_id=thread_id,
            run_id=str(thread.get("latestRunId") or run_id or ""),
            native_status=native_status,
            cursor=cursor,
            next_cursor=str(next_pos) if next_pos is not None else cursor,
            result_ref=str(payload.get("link") or thread.get("link") or thread_id),
            result_payload={
                "last_text": last_text[-1000:],
                "item_count": len(items),
                "runs_count": len(runs_slim),
            },
            started_at="",
            finished_at="",
        )

    async def read_items(self, thread_id: str) -> list[dict]:
        """Head read returning per-item ``(role, text)`` for verification
        scans — counted as a native read like every other read.

        The canary's nonce reply is not always the LAST item: after the run,
        a human can legitimately append messages to the thread through the
        T3 desktop app (observed live on S2: a manual "test" message added a
        second run), so verification must SCAN the items instead of trusting
        the tail.
        """
        self.calls.append({"op": "read", "threadId": thread_id, "cursor": ""})
        payload = self._mcp.call_tool("t3_thread_read", {
            "threadId": thread_id, "view": "messages", "limit": 20,
            "maxCharsPerItem": 4000, "runLimit": 10,
        })
        runs_slim = [
            {
                "id": str(r.get("id") or ""),
                "ordinal": r.get("ordinal"),
                "status": str(r.get("status") or ""),
            }
            for r in (payload.get("recentRuns") or [])
            if isinstance(r, dict)
        ]
        self.runs_observed.append(runs_slim)
        items: list[dict] = []
        for it in payload.get("items") or []:
            text = str(it.get("text") or "")
            for part in it.get("parts") or []:
                if isinstance(part, dict) and part.get("text"):
                    text += "\n" + str(part["text"])
            items.append({
                "role": str(it.get("role") or it.get("type") or ""),
                "text": text,
            })
        return items

    async def interrupt_run(self, ref: WorkerProcessRef, reason: str) -> T3InterruptOutcome:
        self.calls.append({"op": "interrupt", "thread_id": ref.provider_session_id})
        payload = self._mcp.call_tool(
            "t3_thread_interrupt", {"threadId": ref.provider_session_id}
        )
        status = str(payload.get("status") or "")
        _log(self._events, "port.interrupt_run.ok", status=status)
        return T3InterruptOutcome(
            requested=True,
            settled=False,
            already_exited=status == "no_active_run",
            observed_native_status=status,
            finished_at=_now(),
        )


class CrashHookStore:
    """HARNESS-side wrapper around the durable store (never the adapter).

    S1's deterministic crash point: AFTER ``put_launch_receipt`` has COMMITTED
    the receipt + adopted ref and BEFORE ``adapter.start`` returns the ACK.
    The side file records what the durable state now proves (the thread id),
    then the process hard-exits — a coordinator that died between the durable
    write and the acknowledgment.
    """

    def __init__(self, inner: SQLiteT3AdapterStateStore, side_path: Path, events: list):
        self._inner = inner
        self._side_path = side_path
        self._events = events

    def put_launch_receipt(
        self,
        run_id: str,
        *,
        receipt: T3ThreadLaunchReceipt,
        original_ref: WorkerProcessRef,
        cursor: str = "",
        spec: WorkerLaunchSpec | None = None,
        claim_token: str | None = None,
    ) -> None:
        # A3 rework: the receipt write is conditional on the launch claim
        # token; the wrapper forwards it unchanged (crash point unchanged).
        self._inner.put_launch_receipt(
            run_id, receipt=receipt, original_ref=original_ref, cursor=cursor,
            spec=spec, claim_token=claim_token,
        )
        if os.environ.get("T3_CANARY_CRASH_MODE") == "after_receipt":
            _write_side(
                self._side_path,
                {
                    "role": os.environ.get("T3_CANARY_ROLE", "?"),
                    "pid": os.getpid(),
                    "crash_point": "after_receipt_persist_before_ack",
                    "client_request_id": receipt.client_request_id,
                    "request_namespace": receipt.request_namespace,
                    "native": {
                        "thread_id": receipt.thread_id,
                        "run_id": receipt.run_id,
                        "project_id": receipt.project_id,
                        "launch_status": receipt.status,
                    },
                    "durable_state": "intent+receipt+original_ref COMMITTED",
                    "crashed_at": _now(),
                },
            )
            _log(
                self._events, "crash.after_receipt",
                run_id=run_id, threadId=receipt.thread_id,
            )
            sys.stderr.flush()
            sys.stdout.flush()
            os._exit(CRASH_EXIT_AFTER_RECEIPT)

    def __getattr__(self, name):  # every other op delegates to the real store
        return getattr(self._inner, name)


# ---------------------------------------------------------------------------
# Shared role plumbing
# ---------------------------------------------------------------------------


def _state_store() -> SQLiteT3AdapterStateStore:
    return SQLiteT3AdapterStateStore(SCRATCH_ROOT / "batch" / "state.sqlite3")


def _load_model_selection() -> str:
    """The launch envelope's model_selection JSON (wire shape: instanceId)."""
    prep = _load_side("prep")
    if prep.get("outcome") != "OK":
        raise RuntimeError(f"prep outcome is {prep.get('outcome')!r}; cannot launch")
    provider = prep["provider"]
    return json.dumps(
        {"instanceId": provider["providerInstanceId"], "model": provider["model"]}
    )


def _live_context(
    role: str,
    events: list,
    *,
    crash_after_launch: bool = False,
    crash_side_path: Path | None = None,
    namespace_override: str | None = None,
) -> tuple[McpHttp, CanaryLivePort]:
    token, _reg = obtain_mcp_access_token()
    _LAST_TOKEN[0] = token
    mcp = McpHttp(token)
    init = mcp.initialize()
    _log(events, "mcp.initialize.ok", server=init.get("serverInfo", {}), role=role)
    port = CanaryLivePort(
        mcp, token=token, crash_after_launch=crash_after_launch,
        crash_side_path=crash_side_path, namespace_override=namespace_override,
        events=events,
    )
    return mcp, port


_TERMINAL = frozenset({
    WorkerRunStatus.SUCCEEDED, WorkerRunStatus.FAILED,
    WorkerRunStatus.INVALID_RESULT, WorkerRunStatus.CANCELLED,
    WorkerRunStatus.TIMED_OUT,
})


async def _wait_terminal(
    adapter: T3ExecutionAdapter, ref: WorkerProcessRef, events: list,
    deadline_s: float = 420.0,
) -> tuple[list[str], WorkerRunStatus]:
    statuses: list[str] = []
    st = WorkerRunStatus.STARTING
    deadline = time.monotonic() + deadline_s
    while time.monotonic() < deadline:
        st = await adapter.status(ref)
        statuses.append(st.value)
        if st in _TERMINAL:
            return statuses, st
        await asyncio.sleep(5)
    return statuses, st


def _recovery_binding(
    spec: WorkerLaunchSpec, process_ref: WorkerProcessRef
) -> WorkerRecoveryBinding:
    return WorkerRecoveryBinding.bind(
        adapter_id="t3-native", spec=spec, process_ref=process_ref,
        prompt_path=spec.run_dir / "input" / "prompt.txt",
    )


async def _reply_excerpt(
    adapter: T3ExecutionAdapter,
    port: CanaryLivePort,
    ref: WorkerProcessRef,
    nonce: str,
) -> tuple[str, str, bool]:
    """(excerpt_tail, source, nonce_present) for a terminal run.

    ``collect_result`` reads from the persisted cursor, and the terminal
    status polls have already advanced that cursor PAST the final assistant
    reply, so the collect page can legitimately come back empty.  When the
    nonce is missing, re-read the thread from the head (cursor reset — the
    shape the PROVEN_LIVE harness uses) and take the last item text.
    """
    collected = await adapter.collect_result(ref)
    text = (collected.result.structured_output or {}).get("last_text", "")
    source = "collect_result"
    if nonce not in text:
        # Scan ASSISTANT item texts only, not the tail and not the prompt
        # (the prompt itself quotes the nonce as the instruction): a human
        # may also have appended messages to the thread after the run
        # (observed live on S2).
        items = await port.read_items(ref.provider_session_id)
        hit = next(
            (
                i["text"] for i in items
                if "assistant" in i["role"] and nonce in i["text"]
            ),
            "",
        )
        if hit:
            text = hit
        else:
            text = next(
                (i["text"] for i in reversed(items) if "assistant" in i["role"]), ""
            )
        source = "post_collect_head_read"
    return text[-200:], source, nonce in text


async def _observe_settle(
    mcp: McpHttp,
    port: CanaryLivePort,
    store: SQLiteT3AdapterStateStore,
    run_id: str,
    final: WorkerRunStatus,
) -> dict:
    """Observe the settle WITHOUT ever inferring it.

    Live finding (m2studio, T3 0.1.7): T3 reclaims interrupted scratch
    threads from the exact-run read path (``t3_thread_read`` ->
    thread_not_found), so a cancelled run's terminal state can become
    unobservable there.  Fall back to the project-scoped thread row and
    record exactly what upstream itself reports — including upstream's own
    ``settled`` flag.  Never a guess, never a settle claim.
    """
    observation: dict = {"observed_at": _now()}
    if final in _TERMINAL:
        observation["exact_run_read"] = "terminal_observed_before_deadline"
        return observation
    run = store.load_run(run_id)
    receipt = run.receipt if run is not None else None
    thread_id = receipt.thread_id if receipt is not None else ""
    try:
        head = await port.read_thread(thread_id, "", "")
        observation["exact_run_read"] = "ok"
        observation["native_status"] = head.native_status
    except Exception as exc:  # noqa: BLE001 — record the refusal, then probe
        text = str(exc)
        code = ""
        for marker in ('"code":"', "'code':'"):
            at = text.find(marker)
            if at != -1:
                code = text[at + len(marker):].split('"')[0].split("'")[0]
                break
        observation["exact_run_read"] = "thread_no_longer_available"
        observation["exact_run_error_code"] = code or "unknown"
    # The project-scoped thread row carries upstream's OWN settled flag —
    # fetched on BOTH paths (readable and reclaimed) as settle evidence.
    project_id = receipt.project_id if receipt is not None else ""
    if project_id:
        try:
            listing = mcp.call_tool(
                "t3_thread_list", {"limit": 50, "projectId": project_id}
            )
            rows = listing.get("threads") or listing.get("items") or []
            row = next(
                (
                    r for r in rows
                    if isinstance(r, dict)
                    and str(r.get("threadId") or "") == thread_id
                ),
                None,
            )
            if row is not None:
                observation["project_row"] = {
                    "status": str(row.get("status") or ""),
                    "settled": bool(row.get("settled")),
                    "settled_at": row.get("settledAt"),
                    "item_count": row.get("itemCount"),
                }
        except Exception as exc:  # noqa: BLE001
            observation["project_row_error"] = f"{type(exc).__name__}"
    return observation


# ---------------------------------------------------------------------------
# Roles
# ---------------------------------------------------------------------------


async def role_prep(events: list) -> dict:
    token, _reg = obtain_mcp_access_token()
    _LAST_TOKEN[0] = token
    mcp = McpHttp(token)
    try:
        init = mcp.initialize()
    except Exception as exc:
        # Cached token no longer authenticates: mint ONE fresh client (same
        # cache path — every later role shares the new identity).  Never a
        # silent retry loop; a second failure blocks the canary.
        _log(events, "prep.token.stale", error=_redact(exc))
        TOKEN_CACHE.unlink(missing_ok=True)
        token, _reg = obtain_mcp_access_token()
        _LAST_TOKEN[0] = token
        mcp = McpHttp(token)
        init = mcp.initialize()
    env = mcp.call_tool("t3_environment_read", {})
    caps = mcp.call_tool("orchestrator_capabilities", {})
    providers = caps.get("providers") or []
    enabled = [p for p in providers if isinstance(p, dict) and not p.get("constraints")]
    disabled = [
        {"id": p.get("providerInstanceId"), "constraints": p.get("constraints")}
        for p in providers
        if isinstance(p, dict) and p.get("constraints")
    ]
    choice, rule = None, ""
    for p in sorted(enabled, key=lambda item: str(item.get("providerInstanceId"))):
        for m in p.get("models") or []:
            if isinstance(m, dict) and m.get("id") == PREFERRED_MODEL:
                choice = {"providerInstanceId": p["providerInstanceId"], "model": m["id"]}
                rule = (
                    "cheapest ENABLED flash-tier model named by "
                    f"orchestrator_capabilities (exact id {PREFERRED_MODEL!r})"
                )
                break
        if choice:
            break
    if choice is None:  # documented fallback, still cheapest-tier-first
        flash = sorted(
            (p["providerInstanceId"], m["id"])
            for p in enabled
            for m in (p.get("models") or [])
            if isinstance(m, dict) and "flash" in str(m.get("id") or "")
        )
        if flash:
            choice = {"providerInstanceId": flash[0][0], "model": flash[0][1]}
            rule = "preferred id not ENABLED; first *flash* model on an ENABLED provider"
    if choice is None:
        raise RuntimeError(
            "no ENABLED provider lists any model; enabled="
            f"{[p.get('providerInstanceId') for p in enabled]}"
        )
    principal = hashlib.sha256(token.encode()).hexdigest()[:16]
    _log(
        events, "prep.ready",
        provider=choice["providerInstanceId"], model=choice["model"],
        enabled_providers=[p.get("providerInstanceId") for p in enabled],
    )
    return {
        "role": "prep",
        "outcome": "OK",
        "environment": {
            "environmentId": env.get("environmentId"),
            "label": env.get("label"),
            "serverVersion": env.get("serverVersion"),
            "platform": env.get("platform"),
            "endpoint": MCP,
            "mcp_server": init.get("serverInfo", {}),
        },
        "authenticated_namespace": {
            "principal_projection": (
                "sha256(oauth token)[:16] — the cached OAuth client identity"
            ),
            "principal": principal,
            "qualified_namespace": t3_request_namespace(principal),
        },
        "provider": {**choice, "selection_rule": rule},
        "providers_enabled": [p.get("providerInstanceId") for p in enabled],
        "providers_disabled": disabled,
        "prepared_at": _now(),
    }


async def role_s1_p1(events: list) -> dict:
    assert os.environ.get("T3_CANARY_CRASH_MODE") == "after_receipt"
    provider = _load_model_selection()
    _mcp, port = _live_context("s1-p1", events)
    store = CrashHookStore(_state_store(), _side_path("s1-p1"), events)
    adapter = T3ExecutionAdapter(
        port, binding_source_for, CanaryInspector(), state_store=store
    )
    spec = make_spec("s1", provider)
    ref = await adapter.start(spec)  # never returns: the crash hook fires first
    raise AssertionError(f"S1-P1 should have crashed before the ACK, got {ref!r}")


async def role_s1_p2(events: list) -> dict:
    _mcp, port = _live_context("s1-p2", events)
    store = _state_store()
    run = store.load_run(SCENARIOS["s1"]["run_id"])
    assert run is not None and run.spec is not None, "no durable run state for S1"
    assert run.receipt is not None and run.original_ref is not None, (
        "S1-P1 must have persisted the receipt before crashing"
    )
    assert run.intent is not None
    adapter = T3ExecutionAdapter(
        port, binding_source_for, CanaryInspector(), state_store=store
    )
    binding = _recovery_binding(run.spec, run.original_ref)
    t0 = time.monotonic()
    ref = await adapter.reattach(run.spec, binding)
    counts_after_reattach = port.counts()
    assert ref == run.original_ref, "reattach must return the retained original ref"
    assert counts_after_reattach["launch"] == 0 and counts_after_reattach["replay"] == 0, (
        f"S1-P2 reattach must make ZERO native launch/replay calls, saw {counts_after_reattach}"
    )
    p1 = _load_side("s1-p1")
    assert ref.provider_session_id == p1["native"]["thread_id"], (
        "reattached thread id must equal P1's side-file record"
    )
    # A second start on the recovered run stays refused (no replacement).
    start_refused = False
    try:
        await adapter.start(run.spec)
    except T3ExecutionAdapterError:
        start_refused = True
    assert start_refused, "second start must be refused after recovery"
    statuses, final = await _wait_terminal(adapter, ref, events)
    excerpt, excerpt_source, nonce_present = await _reply_excerpt(
        adapter, port, ref, SCENARIOS["s1"]["nonce"]
    )
    single_run = bool(port.runs_observed) and all(
        len(r) == 1 for r in port.runs_observed
    )
    return {
        "role": "s1-p2",
        "outcome": "OK",
        "reattach": {
            "returned_retained_ref": True,
            "zero_native_launch_or_replay": True,
            "counts_after_reattach": counts_after_reattach,
            "elapsed_s": round(time.monotonic() - t0, 2),
            "second_start_refused": start_refused,
        },
        "thread_id": ref.provider_session_id,
        "thread_matches_p1_side_file": True,
        "status_sequence": statuses,
        "final_state": final.value,
        "single_run_observed": single_run,
        "result_excerpt": excerpt,
        "result_excerpt_source": excerpt_source,
        "result_nonce_present": nonce_present,
        "result_ledgered": adapter.result_ledger_entry(run.spec.run_id) is not None,
        "port_counts_final": port.counts(),
        "finished_at": _now(),
    }


async def role_s2_p1(events: list) -> dict:
    assert os.environ.get("T3_CANARY_CRASH_MODE") == "after_launch"
    provider = _load_model_selection()
    _mcp, port = _live_context(
        "s2-p1", events, crash_after_launch=True, crash_side_path=_side_path("s2-p1")
    )
    adapter = T3ExecutionAdapter(
        port, binding_source_for, CanaryInspector(), state_store=_state_store()
    )
    spec = make_spec("s2", provider)
    ref = await adapter.start(spec)  # never returns: the port crash hook fires first
    raise AssertionError(f"S2-P1 should have crashed after launch, got {ref!r}")


async def role_s2_p2(events: list) -> dict:
    _mcp, port = _live_context("s2-p2", events)
    store = _state_store()
    run = store.load_run(SCENARIOS["s2"]["run_id"])
    assert run is not None and run.spec is not None, "no durable run state for S2"
    assert run.intent is not None, "S2-P1 must have persisted the intent"
    assert run.receipt is None, "S2-P1 must NOT have persisted a receipt (crash point)"
    intent = run.intent
    adapter = T3ExecutionAdapter(
        port, binding_source_for, CanaryInspector(), state_store=store
    )
    # The supervisor's pre-ACK ref: the durable intent's key; thread unknown.
    pre_ack_ref = WorkerProcessRef(
        run_id=run.spec.run_id, pid=0, pgid=0,
        process_start_identity="", boot_session_id="",
        launch_nonce=intent.client_request_id, provider_session_id=None,
        stdout_path="", stderr_path="", result_path="",
        started_at="", binary=_T3_REMOTE_BINARY_PLACEHOLDER, base_sha="",
    )
    binding = _recovery_binding(run.spec, pre_ack_ref)
    t0 = time.monotonic()
    ref = await adapter.reattach(run.spec, binding)
    counts_after_reattach = port.counts()
    assert counts_after_reattach["replay"] == 1, (
        f"S2-P2 must recover through exactly one replay, saw {counts_after_reattach}"
    )
    assert counts_after_reattach["launch"] == 1, (
        "the replay executes as the SAME upstream launch command (the port "
        "records the underlying launch call alongside the replay op)"
    )
    assert counts_after_reattach["read"] == 0
    p1 = _load_side("s2-p1")
    assert ref.provider_session_id == p1["native"]["thread_id"], (
        "upstream idempotent replay must return P1's ORIGINAL thread"
    )
    assert ref.launch_nonce == intent.client_request_id
    statuses, final = await _wait_terminal(adapter, ref, events)
    excerpt, excerpt_source, nonce_present = await _reply_excerpt(
        adapter, port, ref, SCENARIOS["s2"]["nonce"]
    )
    single_run = bool(port.runs_observed) and all(
        len(r) == 1 for r in port.runs_observed
    )
    return {
        "role": "s2-p2",
        "outcome": "OK",
        "recovery": {
            "path": "replay_launch(same clientRequestId + namespace)",
            "counts_after_reattach": counts_after_reattach,
            "elapsed_s": round(time.monotonic() - t0, 2),
            "client_request_id": intent.client_request_id,
            "request_namespace": intent.request_namespace,
        },
        "thread_id": ref.provider_session_id,
        "thread_equals_p1_side_file": True,
        "native_replays_original_thread": True,
        "status_sequence": statuses,
        "final_state": final.value,
        "single_run_observed": single_run,
        "runs_last_observed": port.runs_observed[-1] if port.runs_observed else [],
        "result_excerpt": excerpt,
        "result_excerpt_source": excerpt_source,
        "result_nonce_present": nonce_present,
        "result_ledgered": adapter.result_ledger_entry(run.spec.run_id) is not None,
        "port_counts_final": port.counts(),
        "finished_at": _now(),
    }


async def role_s3(events: list) -> dict:
    _mcp, port = _live_context(
        "s3", events, namespace_override="foreign-oauth-client-s3-stub"
    )
    store = _state_store()
    adapter = T3ExecutionAdapter(
        port, binding_source_for, CanaryInspector(), state_store=store
    )
    attempts = []
    for key in ("s1", "s2"):
        run = store.load_run(SCENARIOS[key]["run_id"])
        assert (
            run is not None and run.spec is not None and run.original_ref is not None
        ), f"S3 needs S1/S2's adopted durable refs (missing {key})"
        binding = _recovery_binding(run.spec, run.original_ref)
        try:
            await adapter.reattach(run.spec, binding)
            attempts.append({"scenario": key, "refused": False})
        except T3ExecutionAdapterError as exc:
            attempts.append({
                "scenario": key,
                "refused": True,
                "namespace_message": "authenticated namespace" in str(exc),
                "error_excerpt": str(exc)[:100],
            })
    assert all(a["refused"] and a.get("namespace_message") for a in attempts), attempts
    counts = port.counts()
    assert not port.calls, (
        f"foreign-namespace reattach must make ZERO native calls: {counts}"
    )
    return {
        "role": "s3",
        "outcome": "OK",
        "stub_principal": "foreign-oauth-client-s3-stub",
        "attempts": attempts,
        "port_counts": counts,
        "finished_at": _now(),
    }


async def role_s4(events: list) -> dict:
    provider = _load_model_selection()
    _mcp, port = _live_context("s4", events)
    store = _state_store()
    adapter = T3ExecutionAdapter(
        port, binding_source_for, CanaryInspector(), state_store=store
    )
    spec = make_spec("s4", provider)
    ref = await adapter.start(spec)
    # Record the minted thread id IMMEDIATELY: a later failure in this role
    # must never hide a minted thread from the budget accounting.
    _write_side(
        _side_path("s4"),
        {"role": "s4", "outcome": "PENDING", "thread_id": ref.provider_session_id,
         "at": _now()},
    )
    # Wait until the run is live (RUNNING) so the interrupt has a target; if
    # it reaches terminal first, record that honestly.
    pre_interrupt: list[str] = []
    deadline = time.monotonic() + 90
    st = WorkerRunStatus.STARTING
    while time.monotonic() < deadline:
        st = await adapter.status(ref)
        pre_interrupt.append(st.value)
        if st == WorkerRunStatus.RUNNING or st in _TERMINAL:
            break
        await asyncio.sleep(2)
    was_live = st == WorkerRunStatus.RUNNING
    cancel_receipt = await adapter.cancel(
        ref, "MMOS durable canary S4 interrupt honesty check"
    )
    report_after_cancel = dataclasses.asdict(adapter.cancel_report(spec.run_id))
    statuses, final = await _wait_terminal(adapter, ref, events)
    report_settled = dataclasses.asdict(adapter.cancel_report(spec.run_id))
    excerpt = ""
    try:
        collected = await adapter.collect_result(ref)
        excerpt = (collected.result.structured_output or {}).get("last_text", "")
    except T3ExecutionAdapterError as exc:
        excerpt = f"collect refused: {exc}"[:200]
    settle = await _observe_settle(_mcp, port, store, spec.run_id, final)
    honesty = {
        "signal_sent": bool(cancel_receipt.signal_sent),
        "requested_before_settle": bool(
            report_after_cancel["requested"] and not report_after_cancel["settled"]
        ),
        # The honesty invariant: a settle is NEVER claimed without a terminal
        # observation.  Unobserved-at-deadline is honest; inferred is not.
        "settle_claimed_without_terminal_observation": bool(
            report_settled["settled"] and final not in _TERMINAL
        ),
        "settled_state": report_settled["settled_state"],
        "final_state": final.value,
    }
    return {
        "role": "s4",
        "outcome": "OK",
        "thread_id": ref.provider_session_id,
        "was_live_at_interrupt": was_live,
        "pre_interrupt_states": pre_interrupt,
        "cancel": honesty,
        "settle_observation": settle,
        "status_sequence": statuses,
        "final_state": final.value,
        "result_excerpt": excerpt[-200:],
        "port_counts": port.counts(),
        "finished_at": _now(),
    }


async def _verify_common(scenario: str, events: list) -> dict:
    """READ-ONLY post-run verification of an existing canary thread.

    A fresh OS process cold-reattaches the TERMINAL run (retained ref —
    ZERO native launch/replay calls by construction) and re-reads the thread
    from the head.  This is the repair path for a P2 process whose collect
    page came back empty because the terminal status polls had already
    advanced the persisted cursor past the final reply: the durability facts
    (launch/replay counts, thread ids) stay the ORIGINAL process's; only the
    reply text is re-observed here and merged into the receipt as
    ``verification``.
    """
    conf = SCENARIOS[scenario]
    _mcp, port = _live_context(f"{scenario}-verify", events)
    store = _state_store()
    run = store.load_run(conf["run_id"])
    assert run is not None and run.spec is not None, f"no durable run for {scenario}"
    assert run.original_ref is not None, "verify needs the adopted durable ref"
    adapter = T3ExecutionAdapter(
        port, binding_source_for, CanaryInspector(), state_store=store
    )
    t0 = time.monotonic()
    ref = await adapter.reattach(run.spec, _recovery_binding(run.spec, run.original_ref))
    counts_after_reattach = port.counts()
    assert counts_after_reattach["launch"] == 0 and counts_after_reattach["replay"] == 0, (
        f"{scenario}-verify must make ZERO native launch/replay calls, "
        f"saw {counts_after_reattach}"
    )
    head = await port.read_thread(ref.provider_session_id, "", "")
    items = await port.read_items(ref.provider_session_id)
    nonce_line = next(
        (
            i["text"] for i in items
            if "assistant" in i["role"] and conf["nonce"] in i["text"]
        ),
        "",
    )
    runs_now = port.runs_observed[-1] if port.runs_observed else []
    return {
        "role": f"{scenario}-verify",
        "outcome": "OK",
        "purpose": (
            "read-only post-run verification (zero launch/replay; "
            "assistant-item nonce scan)"
        ),
        "thread_id": ref.provider_session_id,
        "reattach": {
            "returned_retained_ref": True,
            "counts_after_reattach": counts_after_reattach,
            "elapsed_s": round(time.monotonic() - t0, 2),
        },
        "native_status": head.native_status,
        "runs_observed": runs_now,
        "canary_run_status": next(
            (str(r.get("status") or "") for r in runs_now if str(r.get("ordinal")) == "1"),
            "",
        ),
        "post_canary_activity": any(
            str(r.get("ordinal")) not in {"1", "None", ""} for r in runs_now
        ),
        "result_excerpt": nonce_line[-200:] or next(
            (i["text"][-200:] for i in reversed(items) if "assistant" in i["role"]),
            "",
        ),
        "result_nonce_present": bool(nonce_line),
        "port_counts_final": port.counts(),
        "finished_at": _now(),
    }


async def role_s1_verify(events: list) -> dict:
    return await _verify_common("s1", events)


async def role_s2_verify(events: list) -> dict:
    return await _verify_common("s2", events)


async def role_s4_verify(events: list) -> dict:
    """READ-ONLY settle observation for the interrupted S4 thread.

    Zero launch/replay (reattach returns the retained ref).  The exact-run
    read path is expected to report the reclaimed thread (live finding);
    the project-scoped thread row then records upstream's own status and
    settled flags.  Nothing is inferred and nothing is settled here.
    """
    conf = SCENARIOS["s4"]
    _mcp, port = _live_context("s4-verify", events)
    store = _state_store()
    run = store.load_run(conf["run_id"])
    assert run is not None and run.receipt is not None, "no durable S4 run"
    assert run.original_ref is not None, "s4-verify needs the adopted durable ref"
    adapter = T3ExecutionAdapter(
        port, binding_source_for, CanaryInspector(), state_store=store
    )
    ref = await adapter.reattach(run.spec, _recovery_binding(run.spec, run.original_ref))
    counts_after_reattach = port.counts()
    assert counts_after_reattach["launch"] == 0 and counts_after_reattach["replay"] == 0, (
        f"s4-verify must make ZERO native launch/replay calls, saw {counts_after_reattach}"
    )
    # final=CANCELLING routes _observe_settle past the deadline branch into
    # the exact-run read + project-row fallback; nothing about `final` is
    # recorded as an observation of the thread.
    settle = await _observe_settle(
        _mcp, port, store, conf["run_id"], WorkerRunStatus.CANCELLING
    )
    return {
        "role": "s4-verify",
        "outcome": "OK",
        "purpose": (
            "read-only settle observation for the interrupted S4 thread "
            "(zero launch/replay)"
        ),
        "thread_id": ref.provider_session_id,
        "reattach": {
            "returned_retained_ref": True,
            "counts_after_reattach": counts_after_reattach,
        },
        "settle_observation": settle,
        "port_counts_final": port.counts(),
        "finished_at": _now(),
    }


ROLES = {
    "prep": role_prep,
    "s1-p1": role_s1_p1,
    "s1-p2": role_s1_p2,
    "s2-p1": role_s2_p1,
    "s2-p2": role_s2_p2,
    "s3": role_s3,
    "s4": role_s4,
    "s1-verify": role_s1_verify,
    "s2-verify": role_s2_verify,
    "s4-verify": role_s4_verify,
}


async def run_role(role: str) -> int:
    events: list = []
    try:
        payload = await ROLES[role](events)
        _write_side(_side_path(role), payload)
        return 0
    except BaseException as exc:  # record honestly, never hide the failure
        _write_side(
            _side_path(role),
            {
                "role": role,
                "outcome": "ERROR",
                "error": f"{type(exc).__name__}: {_redact(exc)}",
                "at": _now(),
            },
        )
        print(f"[canary] role {role} FAILED: {exc}", file=sys.stderr, flush=True)
        return 3


# ---------------------------------------------------------------------------
# Driver: spawns each role as a SEPARATE OS PROCESS, then writes the receipt.
# ---------------------------------------------------------------------------


def _spawn(role: str, crash_mode: str | None) -> dict:
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env["T3_CANARY_ROLE"] = role
    if crash_mode:
        env["T3_CANARY_CRASH_MODE"] = crash_mode
    try:
        proc = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), "--role", role],
            capture_output=True, text=True, env=env, timeout=900,
        )
        rc, err, out = proc.returncode, proc.stderr, proc.stdout
    except subprocess.TimeoutExpired as exc:
        rc, err, out = None, str(exc.timeout) + "s timeout", str(exc.stdout or "")
    log_path = SCRATCH_ROOT / "batch" / "logs" / f"{role}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(f"=== exit {rc} ===\n--- stderr ---\n{err}\n--- stdout ---\n{out}\n")
    return {"role": role, "returncode": rc}


def _assemble_receipt(results: list[dict], started_at: str, blocked_gate: str | None) -> dict:
    prep = _load_side("prep")
    state_path = SCRATCH_ROOT / "batch" / "state.sqlite3"
    state_sha = (
        hashlib.sha256(state_path.read_bytes()).hexdigest() if state_path.exists() else None
    )
    scenarios: dict[str, dict] = {}

    s1_p1, s1_p2 = _load_side("s1-p1"), _load_side("s1-p2")
    s1_verify = _load_side("s1-verify")
    if s1_verify.get("outcome") == "OK":
        # The ORIGINAL process's durability facts stay untouched; only the
        # reply text is re-observed by the read-only verification pass.
        s1_p2["verification"] = s1_verify
        if s1_verify.get("result_nonce_present"):
            s1_p2["result_excerpt"] = s1_verify["result_excerpt"]
            s1_p2["result_nonce_present"] = True
            s1_p2["result_excerpt_source"] = (
                "post-run verification head read (see verification record)"
            )
    s1_ok = bool(
        s1_p1.get("crash_point") == "after_receipt_persist_before_ack"
        and s1_p2.get("outcome") == "OK"
        and s1_p2.get("reattach", {}).get("zero_native_launch_or_replay")
        and s1_p2.get("thread_matches_p1_side_file")
        and s1_p2.get("reattach", {}).get("second_start_refused")
        and s1_p2.get("final_state") == "SUCCEEDED"
        and s1_p2.get("result_nonce_present")
    )
    scenarios["s1"] = {
        "name": "crash-after-receipt cold restart",
        "outcome": "PASS" if s1_ok else "FAIL",
        "thread_id": s1_p2.get("thread_id") or s1_p1.get("native", {}).get("thread_id"),
        "processes": {"p1": s1_p1, "p2": s1_p2},
    }

    s2_p1, s2_p2 = _load_side("s2-p1"), _load_side("s2-p2")
    s2_verify = _load_side("s2-verify")
    if s2_verify.get("outcome") == "OK":
        s2_p2["verification"] = s2_verify
        if s2_verify.get("result_nonce_present"):
            s2_p2["result_excerpt"] = s2_verify["result_excerpt"]
            s2_p2["result_nonce_present"] = True
            s2_p2["result_excerpt_source"] = (
                "post-run verification head read (see verification record)"
            )
    s2_ok = bool(
        s2_p1.get("crash_point") == "after_launch_before_receipt_persist"
        and s2_p2.get("outcome") == "OK"
        and s2_p2.get("recovery", {}).get("counts_after_reattach", {}).get("replay") == 1
        and s2_p2.get("thread_equals_p1_side_file")
        and s2_p2.get("single_run_observed")
        and s2_p2.get("final_state") == "SUCCEEDED"
        and s2_p2.get("result_nonce_present")
    )
    scenarios["s2"] = {
        "name": "crash-after-launch-before-receipt idempotent replay",
        "outcome": "PASS" if s2_ok else "FAIL",
        "thread_id": s2_p2.get("thread_id") or s2_p1.get("native", {}).get("thread_id"),
        "processes": {"p1": s2_p1, "p2": s2_p2},
    }

    s3 = _load_side("s3")
    s3_ok = bool(
        s3.get("outcome") == "OK" and not any(s3.get("port_counts", {}).values())
    )
    scenarios["s3"] = {
        "name": "foreign authenticated namespace refused locally",
        "outcome": "PASS" if s3_ok else "FAIL",
        "processes": {"p": s3},
    }

    s4 = _load_side("s4")
    s4_verify = _load_side("s4-verify")
    if s4_verify.get("outcome") == "OK":
        s4["post_run_verification"] = s4_verify
        settle_verify = s4_verify.get("settle_observation") or {}
        # Prefer the LATER observation; the original process's own record is
        # preserved inside post_run_verification.
        if settle_verify.get("observed_at", "") >= s4.get(
            "settle_observation", {}
        ).get("observed_at", ""):
            s4["settle_observation"] = settle_verify
    s4_cancel = s4.get("cancel") if isinstance(s4.get("cancel"), dict) else {}
    if s4_cancel and "settle_claimed_without_terminal_observation" not in s4_cancel:
        # Derived from the run's own recorded facts (a pre-merge run-B
        # payload lacks the key): a settle was CLAIMED only if settled_state
        # is non-null, and it would have been an INFERENCE if the exact-run
        # status sequence never reached a terminal state.  Run B recorded
        # settled_state null — no settle was ever claimed.
        _terminal_values = {s.value for s in _TERMINAL}
        _last_status = (s4.get("status_sequence") or [None])[-1]
        s4_cancel["settle_claimed_without_terminal_observation"] = bool(
            s4_cancel.get("settled_state")
            and _last_status not in _terminal_values
        )
    s4_settle = (
        s4.get("settle_observation")
        if isinstance(s4.get("settle_observation"), dict)
        else {}
    )
    s4_row = (
        s4_settle.get("project_row")
        if isinstance(s4_settle.get("project_row"), dict)
        else {}
    )
    if s4.get("outcome") == "SKIPPED":
        s4_ok = False
        s4_outcome = "SKIPPED"
    else:
        # PASS = the requested-vs-settled ledger stayed honest AND the settle
        # is evidenced one of three ways: a terminal state was observed on
        # the exact-run path before the deadline; the exact-run path still
        # reads the thread and reports a thread-TERMINAL status ("completed"
        # / "interrupted" / "failed"); or (observed live at 09:33Z, later
        # transient) the exact-run path lost the reclaimed scratch thread and
        # the project row shows the interrupt landed with upstream NOT
        # settled.  A settle is never inferred from absence alone.
        s4_ok = bool(
            s4.get("outcome") == "OK"
            and s4_cancel.get("signal_sent")
            and s4_cancel.get("requested_before_settle")
            and not s4_cancel.get("settle_claimed_without_terminal_observation")
            and (
                s4_settle.get("exact_run_read") == "terminal_observed_before_deadline"
                or (
                    s4_settle.get("exact_run_read") == "ok"
                    and s4_settle.get("native_status")
                    in {"completed", "interrupted", "failed"}
                )
                or (
                    s4_settle.get("exact_run_read") == "thread_no_longer_available"
                    and s4_row.get("status") == "interrupted"
                    and s4_row.get("settled") is False
                )
            )
        )
        s4_outcome = "PASS" if s4_ok else "FAIL"
    scenarios["s4"] = {
        "name": "exact-run interrupt requested-vs-settled honesty",
        "outcome": s4_outcome,
        "thread_id": s4.get("thread_id"),
        "processes": {"p": s4},
    }

    core = [scenarios[k]["outcome"] for k in ("s1", "s2", "s3")]
    outcome = (
        "BLOCKED" if blocked_gate
        else "DONE" if all(o == "PASS" for o in core)
        and scenarios["s4"]["outcome"] in {"PASS", "SKIPPED"}
        else "PARTIAL"
    )
    threads = [
        scenarios[k].get("thread_id")
        for k in ("s1", "s2", "s4")
        if scenarios[k].get("thread_id")
    ]
    return {
        "schema": "mastermind.t3_durable_canary_receipt/v1",
        "recorded_at": _now(),
        "started_at": started_at,
        "outcome": outcome,
        "blocked_gate": blocked_gate,
        "label": CANARY_LABEL,
        "environment": prep.get("environment", {}),
        "authenticated_namespace": prep.get("authenticated_namespace", {}),
        "provider": prep.get("provider", {}),
        "providers_enabled": prep.get("providers_enabled", []),
        "providers_disabled": prep.get("providers_disabled", []),
        "store": {
            "path": str(state_path),
            "sha256": state_sha,
            "implementation": "SQLiteT3AdapterStateStore",
            "note": (
                "scratch proof store under the harness's authorized scratch "
                "root; NOT data/control_plane (the Executive file is pinned)"
            ),
        },
        "scenarios": scenarios,
        "processes": results,
        "threads_minted_ids": threads,
        "threads_minted": len(threads),
        "thread_budget": 3,
    }


def drive() -> int:
    started_at = _now()
    SCRATCH_ROOT.mkdir(parents=True, exist_ok=True)
    batch = SCRATCH_ROOT / "batch"
    if batch.exists():
        batch.rename(SCRATCH_ROOT / f"batch-{time.strftime('%Y%m%dT%H%M%S')}")
    batch.mkdir(parents=True)

    def run_step(role: str, expected_rc: int, crash_mode: str | None, results: list) -> bool:
        res = _spawn(role, crash_mode)
        res["expected_returncode"] = expected_rc
        res["ok"] = res["returncode"] == expected_rc
        results.append(res)
        return bool(res["ok"])

    def skip_step(role: str, reason: str, results: list) -> None:
        _write_side(
            _side_path(role),
            {"role": role, "outcome": "SKIPPED", "reason": reason},
        )
        results.append({"role": role, "returncode": None, "skipped": True})

    results: list[dict] = []
    blocked_gate: str | None = None

    # prep gates everything (auth + server + provider/model availability).
    if not run_step("prep", 0, None, results):
        payload = _load_side("prep")
        blocked_gate = f"prep failed: {payload.get('error', '?')}"
        for role in ("s1-p1", "s1-p2", "s2-p1", "s2-p2", "s3", "s4"):
            skip_step(role, f"blocked: {blocked_gate}", results)
    else:
        # S1 and S2 are independent scenarios; S3 needs BOTH adopted refs;
        # S4 needs only prep.  A failure blocks its own dependents, never
        # the independent lanes.
        s1_p1_ok = run_step("s1-p1", CRASH_EXIT_AFTER_RECEIPT, "after_receipt", results)
        if s1_p1_ok:
            run_step("s1-p2", 0, None, results)
        else:
            skip_step("s1-p2", "s1-p1 did not crash at its deterministic point", results)
        s2_p1_ok = run_step("s2-p1", CRASH_EXIT_AFTER_LAUNCH, "after_launch", results)
        if s2_p1_ok:
            run_step("s2-p2", 0, None, results)
        else:
            skip_step("s2-p2", "s2-p1 did not crash at its deterministic point", results)
        if s1_p1_ok and s2_p1_ok:
            run_step("s3", 0, None, results)
        else:
            skip_step("s3", "needs S1 and S2 durable adopted refs", results)
        run_step("s4", 0, None, results)  # optional lane; failure recorded only

    # Persist the driving process's records so a later ``--assemble`` can
    # rebuild the receipt without re-running anything.
    (SCRATCH_ROOT / "batch" / "drive.json").write_text(
        json.dumps(
            {"started_at": started_at, "blocked_gate": blocked_gate,
             "processes": results},
            indent=2, default=str,
        )
        + "\n"
    )

    receipt = _assemble_receipt(results, started_at, blocked_gate)
    RECEIPT_OUT.write_text(json.dumps(receipt, indent=2, default=str) + "\n")
    print(
        f"[canary] receipt -> {RECEIPT_OUT}\n[canary] outcome: {receipt['outcome']}"
        f"  blocked_gate: {blocked_gate}",
        file=sys.stderr, flush=True,
    )
    return 0 if receipt["outcome"] in {"DONE", "PARTIAL"} else 2


_EXPECTED_RC = {
    "prep": 0,
    "s1-p1": CRASH_EXIT_AFTER_RECEIPT,
    "s1-p2": 0,
    "s2-p1": CRASH_EXIT_AFTER_LAUNCH,
    "s2-p2": 0,
    "s3": 0,
    "s4": 0,
    "s1-verify": 0,
    "s2-verify": 0,
    "s4-verify": 0,
}


def assemble_only() -> int:
    """Rebuild the receipt from the CURRENT batch's side files + role logs.

    No role is spawned and nothing is launched: this is the repair path after
    read-only verification roles (``--role s1-verify`` … ``s4-verify``)
    updated side files in place.  Process records come from
    ``batch/drive.json`` when the driving process wrote one; otherwise each
    role's persisted log (``=== exit N ===``) is matched against the
    expected-returncode map, and standalone verify-role side files are
    appended with their recorded outcome.
    """
    drive_rec_path = SCRATCH_ROOT / "batch" / "drive.json"
    results: list[dict] = []
    started_at: str | None = None
    blocked_gate: str | None = None
    if drive_rec_path.exists():
        rec = json.loads(drive_rec_path.read_text())
        results = rec.get("processes", [])
        started_at = rec.get("started_at")
        blocked_gate = rec.get("blocked_gate")
    known = {p.get("role") for p in results}
    logs_dir = SCRATCH_ROOT / "batch" / "logs"
    if logs_dir.exists():
        for log in sorted(logs_dir.glob("*.log")):
            role = log.stem
            if role in known or role not in _EXPECTED_RC:
                continue
            first = log.read_text().splitlines()[0] if log.stat().st_size else ""
            rc = None
            if first.startswith("=== exit ") and first.endswith(" ==="):
                try:
                    rc = int(first[len("=== exit "):-len(" ===")])
                except ValueError:
                    rc = None
            results.append({
                "role": role,
                "returncode": rc,
                "expected_returncode": _EXPECTED_RC[role],
                "ok": rc == _EXPECTED_RC[role],
                "reconstructed_from": "role log",
            })
            known.add(role)
    for verify_role in ("s1-verify", "s2-verify", "s4-verify"):
        if verify_role in known:
            continue
        side = _load_side(verify_role)
        if not side:
            continue
        ok = side.get("outcome") == "OK"
        results.append({
            "role": verify_role,
            "returncode": 0 if ok else 3,
            "expected_returncode": 0,
            "ok": ok,
            "reconstructed_from": "standalone role side file",
        })
    if started_at is None:
        # Preserve the true batch start recorded by the driving process.
        if RECEIPT_OUT.exists():
            started_at = json.loads(RECEIPT_OUT.read_text()).get("started_at") or _now()
        else:
            started_at = _now()
    receipt = _assemble_receipt(results, started_at, blocked_gate)
    receipt["assembled_from"] = (
        "post-run verification pass (no roles spawned, nothing launched)"
    )
    RECEIPT_OUT.write_text(json.dumps(receipt, indent=2, default=str) + "\n")
    print(
        f"[canary] receipt -> {RECEIPT_OUT}\n[canary] outcome: {receipt['outcome']}"
        f"  blocked_gate: {blocked_gate}",
        file=sys.stderr, flush=True,
    )
    return 0 if receipt["outcome"] in {"DONE", "PARTIAL"} else 2


def main() -> int:
    parser = argparse.ArgumentParser(description="MMOS durable canary (T3 live)")
    parser.add_argument("--role", choices=sorted(ROLES), default=None)
    parser.add_argument(
        "--assemble",
        action="store_true",
        help="rebuild the receipt from the current batch's side files + logs "
        "(no roles spawned, nothing launched)",
    )
    args = parser.parse_args()
    if args.assemble:
        return assemble_only()
    if args.role:
        return asyncio.run(run_role(args.role))
    return drive()


if __name__ == "__main__":
    raise SystemExit(main())

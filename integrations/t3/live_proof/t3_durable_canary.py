"""Rev5 T3 lane — LIVE DURABLE CANARY r2 (Director A4; r1 by Director A2).

Turns the fake-port cold-restart proofs (``tests/test_t3_adapter_durability.py``,
``tests/test_t3_execution_adapter.py``) into REAL-PATH proofs against the live
T3 desktop server on this Mac (``http://127.0.0.1:3773/mcp``, environment
m2studio).  Every role is a SEPARATE OS PROCESS; P1/P2 of a scenario share ONE
on-disk ``SQLiteT3AdapterStateStore``; crash points are deterministic
``os._exit`` hooks in HARNESS wrappers (a store wrapper after
``put_launch_receipt`` commits; a port subclass after the native launch
returned) — never in the adapter.

A4 harness swap (r2): the port is the adapter's REFERENCE live port
:class:`~control_plane.t3_execution_adapter.T3McpToolPort` over the typed
``McpHttp`` transport of ``t3_live_proof.py`` — it attests ``client:<sid>``
from the bearer token's claims (upstream's real ``requestNamespace``), proves
every launch/replay receipt by ``t3_expected_launch_thread_id`` (echo fields
come ONLY from that upstream evidence, never from the request), reads the
exact run's status from ``recentRuns[].runId`` (the donor field; r1's harness
read ``.id``), classifies lost replies with the re-audit N1 allowlist, sends
exact-run interrupts and reads the result by a dedicated terminal read.  The
r1 ``CanaryLivePort`` (token-hash principal, copied echoes) is gone.  r2 runs
on a FRESH state file under its own scratch root (r1 rows were persisted under
a token-hash principal, which ``T3McpToolPort`` can never attest).

Scenarios (HARD thread budget: at most 5 new real threads, reserved in a
durable budget file BEFORE each minting role starts; nothing is ever retried,
deleted or archived — T3 owns lifecycle):

* S1 crash-after-receipt — P1 claims -> REAL launch -> receipt COMMITTED ->
  ``os._exit(90)`` before the ACK.  P2 reattaches with ZERO native calls
  (retained ref), a second ``start`` is refused with ZERO native calls, the run
  is read to terminal and ``collect_result`` names the run's FINAL assistant
  item (re-audit N2, cross-checked by a full head read).
* S2 crash-after-launch-before-receipt — P1's port subclass hard-exits (91)
  after the native launch returned.  P2 replays under the SAME OAuth client:
  the port logs ``upstream_echo_proven=true``, the thread equals P1's, the
  thread has exactly one run (one launch upstream).
* S3 foreign principal (REAL second OAuth client) — a second pairing (own
  token cache) attests a DIFFERENT ``client:<sid>``; reattach of S1/S2 is
  refused ``PRINCIPAL_MISMATCH`` and ``start`` is refused, all with ZERO
  native calls.  Then ONE direct ``t3_thread_launch`` with S1's SAME
  clientRequestId (no message: no model turn) from the second client proves
  upstream mints a DIFFERENT thread (namespace = OAuth client), whose id is
  exactly the second client's derivation.
* S4 exact-run interrupt — a RUNNING run is interrupted through the adapter
  (``threadId`` + native ``runId``, upstream echo verified); the ledger
  records requested vs settled honestly (``CANCELLING`` may outlast the
  polls — recorded, never inferred).
* S5 lost reply — a HARNESS transport wrapper lets the real launch COMMIT and
  then raises the donor's own post-commit failure shape (``isError`` with
  ``orchestration_error``, "The operation could not be completed.").  The
  adapter keeps the intent (UNKNOWN, never a clean refusal); a fresh process
  replays and adopts the ORIGINAL thread (still one run upstream).

Receipt: ``t3_durable_canary_receipt_r2.json`` next to this file (r1's
receipt is immutable evidence and is never touched), schema
``mastermind.t3_durable_canary_receipt/v1`` + ``harness_port`` +
``adapter_commit_sha``; secret-free (sha256 projections only, user-home
paths redacted as ``~``); pinned by ``tests/test_t3_durable_canary_receipt_r2.py``.

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
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[3]  # .../integrations/t3/live_proof -> repo root
sys.path.insert(0, str(REPO))

from control_plane.child_execution_contracts import (  # noqa: E402
    C1_ROUTINE_BOUNDED,
    ExecutionBinding,
)
from control_plane.t3_execution_adapter import (  # noqa: E402
    _T3_REMOTE_BINARY_PLACEHOLDER,
    SQLiteT3AdapterStateStore,
    T3ExecutionAdapter,
    T3ExecutionAdapterError,
    T3LaunchClaimConflictError,
    T3LaunchEffectUnknownError,
    T3McpToolPort,
    T3McpTransportError,
    T3NamespaceAttestationError,
    T3ThreadLaunchEnvelope,
    T3ThreadLaunchReceipt,
    t3_expected_launch_thread_id,
    t3_mcp_failure_is_definitive_refusal,
    t3_mcp_upstream_namespace,
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
import t3_live_proof as _harness  # noqa: E402  (typed McpHttp + OAuth flow reused)

for _mod_name in (
    "control_plane.t3_execution_adapter",
    "control_plane.worker_execution_contract",
    "control_plane.child_execution_contracts",
):
    _mod_file = str(sys.modules[_mod_name].__file__)
    assert _mod_file.startswith(str(REPO)), (
        f"{_mod_name} must resolve from THIS worktree, got {_mod_file}"
    )

McpHttp = _harness.McpHttp  # typed transport errors (T3McpTransportError)

HOME = str(Path.home())
SCRATCH_BASE = Path(HOME) / ".hermes" / "profiles" / "engineering" / "cache" / "scratch"
SCRATCH_ROOT = Path(os.environ.get("T3_CANARY_ROOT", str(SCRATCH_BASE / "t3_durable_canary_r2")))
TOKEN_CACHE_A = Path(
    os.environ.get("T3_CANARY_TOKEN_A", str(SCRATCH_BASE / "t3_canary_r2_client_a_token.txt"))
)
TOKEN_CACHE_B = Path(
    os.environ.get("T3_CANARY_TOKEN_B", str(SCRATCH_BASE / "t3_canary_r2_client_b_token.txt"))
)
RECEIPT_OUT = Path(
    os.environ.get(
        "T3_CANARY_RECEIPT_OUT",
        str(REPO / "integrations" / "t3" / "live_proof" / "t3_durable_canary_receipt_r2.json"),
    )
)
#: Dry-run only (never in a live run): synthesize session tokens for a fake
#: local MCP server instead of pairing.  The live run leaves this unset.
DRY_RUN_TOKENS = os.environ.get("T3_CANARY_DRY_RUN_TOKENS") == "1"

CANARY_LABEL = "MMOS durable canary r2"
JOB_ID = "jobs/mmos-rev5-durable-canary-r2"
WORKER_ID = "workers/t3-canary-r2"
HOST_ID = "m2-studio"
PREFERRED_PROVIDER = "capacity_fabric"
PREFERRED_MODEL = "glm-5.3-flash"
THREAD_BUDGET = 5

CRASH_EXIT_AFTER_RECEIPT = 90  # S1-P1
CRASH_EXIT_AFTER_LAUNCH = 91  # S2-P1

SCENARIOS = {
    "s1": {"run_id": "runs/t3-durable-canary-r2/s1", "nonce": "r2-s1"},
    "s2": {"run_id": "runs/t3-durable-canary-r2/s2", "nonce": "r2-s2"},
    "s4": {"run_id": "runs/t3-durable-canary-r2/s4", "nonce": "r2-s4"},
    "s5": {"run_id": "runs/t3-durable-canary-r2/s5", "nonce": "r2-s5"},
}

_SECRETS: list[str] = []  # tokens seen by this process (redaction only)


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _redact(text: object) -> str:
    value = str(text)
    for secret in _SECRETS:
        if secret:
            value = value.replace(secret, "<redacted-token>")
    return value.replace(HOME, "~")[:600]


def _log(events: list, event: str, **facts) -> None:
    entry = {"t": _now(), "event": event}
    entry.update(facts)
    events.append(entry)
    print(f"[canary] {event} {_redact(facts) if facts else ''}", file=sys.stderr, flush=True)


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
# Thread budget (durable; reserved BEFORE a minting role may start)
# ---------------------------------------------------------------------------


def _budget_path() -> Path:
    return SCRATCH_ROOT / "batch" / "budget.json"


def _budget() -> dict:
    path = _budget_path()
    return json.loads(path.read_text()) if path.exists() else {"limit": THREAD_BUDGET, "reserved": []}


def _reserve_thread(role: str) -> bool:
    """Reserve one thread for ``role``; False when the hard budget is spent."""
    budget = _budget()
    if role in budget["reserved"]:
        return True
    if len(budget["reserved"]) >= THREAD_BUDGET:
        return False
    budget["reserved"].append(role)
    _write_side(_budget_path(), budget)
    return True


# ---------------------------------------------------------------------------
# Company-side fixtures
# ---------------------------------------------------------------------------


def make_binding(run_key: str) -> ExecutionBinding:
    digest = _sha(f"mmos-rev5-durable-canary-r2/{run_key}")
    lease = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=45)).isoformat()
    return ExecutionBinding(
        root_run_ref="roots/mmos-rev5-durable-canary-r2",
        immediate_parent_run_ref="parents/fable-director-a4",
        logical_child_key=f"t3-durable-canary-r2-{run_key}",
        request_digest=digest,
        effective_complexity=C1_ROUTINE_BOUNDED,
        adapter_id="t3-native",
        worker_id=WORKER_ID,
        host_id=HOST_ID,
        lease_expiry=lease,
    )


def _prompt(scenario: str) -> str:
    conf = SCENARIOS[scenario]
    if scenario == "s4":
        return (
            f"{CANARY_LABEL} — scenario S4 (exact-run interrupt check, run "
            f"{conf['run_id']}). Do not use any tools. First write the line "
            f"T3-CANARY-OK {conf['nonce']} and then count from 1 to 600, one "
            "number per line, with no other text."
        )
    return (
        f"{CANARY_LABEL} — scenario {scenario.upper()} (durability proof, run "
        f"{conf['run_id']}). Do not use any tools. Reply with exactly this line "
        f"and nothing else: T3-CANARY-OK {conf['nonce']}"
    )


def make_spec(scenario: str, model_selection: str) -> WorkerLaunchSpec:
    """Build the P1-side spec AND its durable run dir + private prompt file."""
    conf = SCENARIOS[scenario]
    run_dir = SCRATCH_ROOT / "batch" / "runs" / scenario
    (run_dir / "input").mkdir(parents=True, exist_ok=True)
    prompt = _prompt(scenario)
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
        return "t3-durable-canary-r2-boot-1"

    def identity(self, pid: int) -> tuple[str, int]:
        return (f"canary-identity-{pid}", pid)

    def inspect(self, pid: int) -> object:
        return {"pid": pid, "canary": True}


def binding_source_for(spec: WorkerLaunchSpec) -> ExecutionBinding | None:
    for key, conf in SCENARIOS.items():
        if conf["run_id"] == spec.run_id:
            return make_binding(key)
    return None


# ---------------------------------------------------------------------------
# Auth + the REAL reference port (T3McpToolPort) with harness-only hooks
# ---------------------------------------------------------------------------


def _dry_run_token(sid: str) -> str:
    import base64

    claims = {"v": 1, "kind": "session", "sid": sid, "sub": "mcp-client",
              "method": "bearer-access-token", "scopes": ["orchestration:operate"]}
    body = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=").decode()
    return body + ".dry-run-signature"


def obtain_token(client: str) -> str:
    """Client "a" (primary) or "b" (S3's second OAuth client); never printed."""
    if DRY_RUN_TOKENS:
        token = _dry_run_token(f"dry-run-client-{client}")
    else:
        path = TOKEN_CACHE_A if client == "a" else TOKEN_CACHE_B
        label = f"mmos-durable-canary-r2-client-{client}"
        token, _reg = _harness.obtain_mcp_access_token(str(path), label)
    _SECRETS.append(token)
    return token


class CanaryToolPort(T3McpToolPort):
    """The adapter's REFERENCE port, plus harness-only call accounting and the
    S2 crash hook (after the native launch RETURNED, before the adapter can
    persist the receipt).  Echo proof, attestation, classification, reads and
    interrupts are ALL the real ``T3McpToolPort`` code (``super()``)."""

    def __init__(self, call_tool, token: str, *, events: list,
                 crash_after_launch: bool = False, crash_side_path: Path | None = None):
        super().__init__(
            call_tool, upstream_namespace=t3_mcp_upstream_namespace(token),
            launch_arguments={"scratch": True},
        )
        self._events = events
        self._crash_after_launch = crash_after_launch
        self._crash_side_path = crash_side_path

    def counts(self) -> dict:
        ops = [c.get("op") for c in self.calls]
        return {
            "launch": ops.count("launch"),
            "replay": ops.count("replay"),
            "read": sum(ops.count(op) for op in ("read", "read_result", "run_lookup", "read_launch")),
            "interrupt": ops.count("interrupt"),
        }

    def _launch(self, envelope: T3ThreadLaunchEnvelope, op: str) -> T3ThreadLaunchReceipt:
        _log(self._events, f"port.{op}", clientRequestId=envelope.client_request_id)
        receipt = super()._launch(envelope, op)
        _log(
            self._events, f"port.{op}.ok", threadId=receipt.thread_id, runId=receipt.run_id,
            status=receipt.status,
            upstream_echo_proven=bool(receipt.client_request_id)
            and receipt.client_request_id == envelope.client_request_id
            and receipt.request_namespace == envelope.request_namespace,
        )
        if op == "launch" and self._crash_after_launch:
            assert self._crash_side_path is not None
            _write_side(self._crash_side_path, {
                "role": os.environ.get("T3_CANARY_ROLE", "?"),
                "pid": os.getpid(),
                "crash_point": "after_launch_before_receipt_persist",
                "client_request_id": envelope.client_request_id,
                "native": {"thread_id": receipt.thread_id, "run_id": receipt.run_id,
                           "project_id": receipt.project_id, "launch_status": receipt.status},
                "upstream_echo_proven": bool(receipt.client_request_id),
                "port_counts": self.counts(),
                "crashed_at": _now(),
            })
            _log(self._events, "crash.after_launch", threadId=receipt.thread_id)
            sys.stderr.flush()
            sys.stdout.flush()
            os._exit(CRASH_EXIT_AFTER_LAUNCH)
        return receipt


class LostReplyTransport:
    """S5 HARNESS wrapper around the real transport: the FIRST
    ``t3_thread_launch`` is really sent and COMMITS upstream; its real reply is
    recorded for verification only and then replaced by the donor's own
    post-commit failure shape (``isError`` + ``orchestration_error``, the
    message of ``threadAccess.unavailable()``)."""

    def __init__(self, inner, events: list) -> None:
        self._inner = inner
        self._events = events
        self.injected = False
        self.observed_reply: dict = {}

    def __call__(self, tool: str, arguments):
        reply = self._inner(tool, arguments)
        if tool == "t3_thread_launch" and not self.injected:
            self.injected = True
            self.observed_reply = {
                "thread_id": str(reply.get("threadId") or ""),
                "run_id": str(reply.get("runId") or ""),
            }
            failure = T3McpTransportError(
                "tool t3_thread_launch returned failure: "
                '{"_tag":"OrchestratorMcpFailure","code":"orchestration_error",'
                '"message":"The operation could not be completed."}',
                phase=T3McpTransportError.AFTER_SEND, tool_error=True,
                tool_error_code="orchestration_error",
            )
            _log(self._events, "inject.lost_reply_after_commit",
                 committed_thread=self.observed_reply["thread_id"],
                 classifier_definitive_refusal=t3_mcp_failure_is_definitive_refusal(
                     failure, tool="t3_thread_launch"))
            raise failure
        return reply


class CrashHookStore:
    """HARNESS-side wrapper around the durable store (never the adapter).

    S1's deterministic crash point: AFTER ``put_launch_receipt`` COMMITTED the
    receipt + original ref and BEFORE ``adapter.start`` returns the ACK."""

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
        self._inner.put_launch_receipt(
            run_id, receipt=receipt, original_ref=original_ref, cursor=cursor,
            spec=spec, claim_token=claim_token,
        )
        if os.environ.get("T3_CANARY_CRASH_MODE") == "after_receipt":
            _write_side(self._side_path, {
                "role": os.environ.get("T3_CANARY_ROLE", "?"),
                "pid": os.getpid(),
                "crash_point": "after_receipt_persist_before_ack",
                "client_request_id": receipt.client_request_id,
                "upstream_echo_proven": bool(receipt.client_request_id),
                "native": {"thread_id": receipt.thread_id, "run_id": receipt.run_id,
                           "project_id": receipt.project_id, "launch_status": receipt.status},
                "durable_state": "intent+receipt+original_ref COMMITTED",
                "crashed_at": _now(),
            })
            _log(self._events, "crash.after_receipt", run_id=run_id, threadId=receipt.thread_id)
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
    prep = _load_side("prep")
    if prep.get("outcome") != "OK":
        raise RuntimeError(f"prep outcome is {prep.get('outcome')!r}; cannot launch")
    provider = prep["provider"]
    return json.dumps({"instanceId": provider["providerInstanceId"], "model": provider["model"]})


def _live_context(role: str, events: list, *, client: str = "a", transport_wrapper=None,
                  crash_after_launch: bool = False, crash_side_path: Path | None = None
                  ) -> tuple[Any, CanaryToolPort, str]:
    token = obtain_token(client)
    mcp = McpHttp(token)
    init = mcp.initialize()
    _log(events, "mcp.initialize.ok", server=init.get("serverInfo", {}), role=role, client=client)
    call_tool = transport_wrapper(mcp.call_tool) if transport_wrapper else mcp.call_tool
    port = CanaryToolPort(call_tool, token, events=events,
                          crash_after_launch=crash_after_launch,
                          crash_side_path=crash_side_path)
    return mcp, port, port.authenticated_namespace()


_TERMINAL = frozenset({
    WorkerRunStatus.SUCCEEDED, WorkerRunStatus.FAILED,
    WorkerRunStatus.INVALID_RESULT, WorkerRunStatus.CANCELLED,
    WorkerRunStatus.TIMED_OUT,
})


async def _wait_terminal(adapter: T3ExecutionAdapter, ref: WorkerProcessRef,
                         deadline_s: float = 420.0, interval_s: float = 5.0
                         ) -> tuple[list[str], WorkerRunStatus]:
    statuses: list[str] = []
    st = WorkerRunStatus.STARTING
    deadline = time.monotonic() + deadline_s
    while time.monotonic() < deadline:
        st = await adapter.status(ref)
        if not statuses or statuses[-1] != st.value:
            statuses.append(st.value)
        if st in _TERMINAL:
            return statuses, st
        await asyncio.sleep(interval_s)
    return statuses, st


def _recovery_binding(spec: WorkerLaunchSpec, process_ref: WorkerProcessRef) -> WorkerRecoveryBinding:
    return WorkerRecoveryBinding.bind(
        adapter_id="t3-native", spec=spec, process_ref=process_ref,
        prompt_path=spec.run_dir / "input" / "prompt.txt",
    )


def _pre_ack_ref(spec: WorkerLaunchSpec, key: str) -> WorkerProcessRef:
    """The supervisor's pre-ACK ref: the durable intent's key; thread unknown."""
    return WorkerProcessRef(
        run_id=spec.run_id, pid=0, pgid=0,
        process_start_identity="", boot_session_id="",
        launch_nonce=key, provider_session_id=None,
        stdout_path="", stderr_path="", result_path="",
        started_at="", binary=_T3_REMOTE_BINARY_PLACEHOLDER, base_sha="",
    )


def _head_items(port: CanaryToolPort, thread_id: str) -> tuple[list[dict], dict]:
    """Full head read for VERIFICATION (counted as reads): every item + the
    thread row; ``runId`` is the donor's run field."""
    items: list[dict] = []
    position = None
    payload: dict = {}
    for _ in range(40):
        arguments = {"threadId": thread_id, "view": "messages", "limit": 50,
                     "maxCharsPerItem": 2000, "runLimit": 50}
        if position is not None:
            arguments["afterPosition"] = position
        port.calls.append({"op": "read", "threadId": thread_id, "verification": True})
        payload = dict(port._call_tool("t3_thread_read", arguments))
        items.extend(i for i in payload.get("items") or [] if isinstance(i, dict))
        if payload.get("hasMore") is not True or not isinstance(payload.get("nextPosition"), int):
            break
        position = payload["nextPosition"]
    return items, payload


def _runs_slim(payload: dict) -> list[dict]:
    return [
        {"run_id": str(r.get("runId") or ""), "ordinal": r.get("ordinal"),
         "status": str(r.get("status") or "")}
        for r in (payload.get("recentRuns") or []) if isinstance(r, dict)
    ]


async def _collect_and_verify(adapter: T3ExecutionAdapter, port: CanaryToolPort,
                              ref: WorkerProcessRef, run_id: str, nonce: str) -> dict:
    """``collect_result`` (terminal read) + an independent head-read check that
    the ledgered reference names the run's FINAL assistant item (N2)."""
    out: dict = {}
    try:
        collected = await adapter.collect_result(ref)
        output = dict(collected.result.structured_output or {})
        out["collect_ok"] = True
        out["collected_status"] = collected.result.status.value
        out["result_text_tail"] = str(output.get("text", ""))[-200:]
    except T3ExecutionAdapterError as exc:
        out["collect_ok"] = False
        out["collect_error"] = _redact(exc)[:300]
        output = {}
    entry = adapter.result_ledger_entry(run_id)
    out["result_ledgered"] = entry is not None
    out["result_ref"] = entry.result_ref if entry is not None else ""
    receipt = adapter.launch_receipt(run_id)
    items, payload = _head_items(port, ref.provider_session_id or "")
    run_items = [i for i in items if str(i.get("runId") or "") == receipt.run_id]
    assistants = [i for i in run_items if i.get("type") == "assistant_message" and i.get("text")]
    final = assistants[-1] if assistants else {}
    out["head_read_item_count"] = len(items)
    out["run_assistant_items"] = len(assistants)
    out["final_assistant_item_id"] = str(final.get("itemId") or "")
    out["ledger_names_final_assistant_item"] = bool(final) and out["result_ref"].endswith(
        f"/item/{final.get('itemId')}"
    )
    out["nonce_in_collected_text"] = f"T3-CANARY-OK {nonce}" in out.get("result_text_tail", "")
    out["nonce_in_final_item"] = f"T3-CANARY-OK {nonce}" in str(final.get("text") or "")
    out["thread_run_count"] = (payload.get("thread") or {}).get("runCount")
    out["runs_observed"] = _runs_slim(payload)
    return out


def _derivation_check(namespace: str, key: str, thread_id: str) -> bool:
    return bool(thread_id) and thread_id == t3_expected_launch_thread_id(namespace, key)


# ---------------------------------------------------------------------------
# Roles
# ---------------------------------------------------------------------------


async def role_prep(events: list) -> dict:
    mcp, port, namespace = _live_context("prep", events, client="a")
    env = mcp.call_tool("t3_environment_read", {})
    caps = mcp.call_tool("orchestrator_capabilities", {})
    providers = caps.get("providers") or []
    enabled = [p for p in providers if isinstance(p, dict) and not p.get("constraints")]
    disabled = [
        {"id": p.get("providerInstanceId"), "constraints": p.get("constraints")}
        for p in providers if isinstance(p, dict) and p.get("constraints")
    ]
    choice = None
    for p in enabled:
        if p.get("providerInstanceId") != PREFERRED_PROVIDER:
            continue
        for m in p.get("models") or []:
            if isinstance(m, dict) and m.get("id") == PREFERRED_MODEL:
                choice = {"providerInstanceId": PREFERRED_PROVIDER, "model": PREFERRED_MODEL}
    if choice is None:
        raise RuntimeError(
            f"{PREFERRED_PROVIDER}/{PREFERRED_MODEL} is not ENABLED; enabled="
            f"{[p.get('providerInstanceId') for p in enabled]} — no fallback in r2"
        )
    _log(events, "prep.ready", **choice)
    return {
        "role": "prep",
        "outcome": "OK",
        "environment": {
            "environmentId": env.get("environmentId"),
            "label": env.get("label"),
            "serverVersion": env.get("serverVersion"),
            "platform": env.get("platform"),
            "endpoint": _harness.MCP,
        },
        "authenticated_namespace": {
            "attestation": "T3McpToolPort.from token claims: client:<auth session id>",
            "client_a_upstream_namespace_sha256": _sha(namespace),
            "client_a_qualified_namespace_sha256": _sha(t3_request_namespace(namespace)),
        },
        "provider": {**choice, "selection_rule": "fixed by the A4 brief (no fallback)"},
        "providers_enabled": [p.get("providerInstanceId") for p in enabled],
        "providers_disabled": disabled,
        "prepared_at": _now(),
    }


async def role_s1_p1(events: list) -> dict:
    assert os.environ.get("T3_CANARY_CRASH_MODE") == "after_receipt"
    provider = _load_model_selection()
    _mcp, port, _ns = _live_context("s1-p1", events)
    store = CrashHookStore(_state_store(), _side_path("s1-p1"), events)
    adapter = T3ExecutionAdapter(port, binding_source_for, CanaryInspector(), state_store=store)
    ref = await adapter.start(make_spec("s1", provider))  # never returns: crash hook
    raise AssertionError(f"S1-P1 should have crashed before the ACK, got {ref!r}")


async def role_s1_p2(events: list) -> dict:
    _mcp, port, namespace = _live_context("s1-p2", events)
    store = _state_store()
    conf = SCENARIOS["s1"]
    run = store.load_run(conf["run_id"])
    assert run is not None and run.spec is not None and run.intent is not None
    assert run.receipt is not None and run.original_ref is not None, (
        "S1-P1 must have persisted the receipt before crashing"
    )
    adapter = T3ExecutionAdapter(port, binding_source_for, CanaryInspector(), state_store=store)
    t0 = time.monotonic()
    ref = await adapter.reattach(run.spec, _recovery_binding(run.spec, run.original_ref))
    counts_after_reattach = port.counts()
    assert ref == run.original_ref
    assert not port.calls, f"S1-P2 reattach must make ZERO native calls: {port.calls}"
    p1 = _load_side("s1-p1")
    assert ref.provider_session_id == p1["native"]["thread_id"]
    start_refusal = ""
    try:
        await adapter.start(run.spec)
    except T3LaunchClaimConflictError:
        start_refusal = "T3LaunchClaimConflictError"
    except T3ExecutionAdapterError as exc:
        start_refusal = type(exc).__name__
    counts_after_second_start = port.counts()
    assert start_refusal and not port.calls, "second start must be refused with zero native calls"
    statuses, final = await _wait_terminal(adapter, ref)
    collected = await _collect_and_verify(adapter, port, ref, conf["run_id"], conf["nonce"])
    return {
        "role": "s1-p2",
        "outcome": "OK",
        "reattach": {
            "returned_retained_ref": True,
            "native_calls": 0,
            "counts_after_reattach": counts_after_reattach,
            "elapsed_s": round(time.monotonic() - t0, 3),
        },
        "second_start": {"refused": bool(start_refusal), "error": start_refusal,
                         "counts_after": counts_after_second_start},
        "thread_id": ref.provider_session_id,
        "thread_matches_p1_side_file": True,
        "thread_id_matches_client_a_derivation": _derivation_check(
            namespace, run.intent.client_request_id, ref.provider_session_id or ""),
        "status_sequence": statuses,
        "final_state": final.value,
        "collect": collected,
        "port_counts_final": port.counts(),
        "finished_at": _now(),
    }


async def role_s2_p1(events: list) -> dict:
    assert os.environ.get("T3_CANARY_CRASH_MODE") == "after_launch"
    provider = _load_model_selection()
    _mcp, port, _ns = _live_context(
        "s2-p1", events, crash_after_launch=True, crash_side_path=_side_path("s2-p1"))
    adapter = T3ExecutionAdapter(port, binding_source_for, CanaryInspector(), state_store=_state_store())
    ref = await adapter.start(make_spec("s2", provider))  # never returns: crash hook
    raise AssertionError(f"S2-P1 should have crashed after launch, got {ref!r}")


async def role_s2_p2(events: list) -> dict:
    _mcp, port, namespace = _live_context("s2-p2", events)
    store = _state_store()
    conf = SCENARIOS["s2"]
    run = store.load_run(conf["run_id"])
    assert run is not None and run.spec is not None and run.intent is not None
    assert run.receipt is None, "S2-P1 must NOT have persisted a receipt (crash point)"
    intent = run.intent
    adapter = T3ExecutionAdapter(port, binding_source_for, CanaryInspector(), state_store=store)
    t0 = time.monotonic()
    ref = await adapter.reattach(run.spec, _recovery_binding(run.spec, _pre_ack_ref(run.spec, intent.client_request_id)))
    counts_after_reattach = port.counts()
    assert counts_after_reattach["replay"] == 1 and counts_after_reattach["launch"] == 0, counts_after_reattach
    p1 = _load_side("s2-p1")
    assert ref.provider_session_id == p1["native"]["thread_id"], "replay must return P1's ORIGINAL thread"
    receipt = adapter.launch_receipt(conf["run_id"])
    echo_proven = (receipt.client_request_id == intent.client_request_id
                   and receipt.request_namespace == intent.request_namespace)
    statuses, final = await _wait_terminal(adapter, ref)
    collected = await _collect_and_verify(adapter, port, ref, conf["run_id"], conf["nonce"])
    return {
        "role": "s2-p2",
        "outcome": "OK",
        "recovery": {
            "path": "reattach -> replay_launch (same OAuth client, same clientRequestId)",
            "counts_after_reattach": counts_after_reattach,
            "elapsed_s": round(time.monotonic() - t0, 3),
            "client_request_id": intent.client_request_id,
            "request_namespace_sha256": _sha(intent.request_namespace),
            "upstream_echo_proven": echo_proven,
        },
        "native_launch_calls_total": int(p1.get("port_counts", {}).get("launch", 0))
        + counts_after_reattach["launch"],
        "thread_id": ref.provider_session_id,
        "thread_equals_p1_side_file": True,
        "thread_id_matches_client_a_derivation": _derivation_check(
            namespace, intent.client_request_id, ref.provider_session_id or ""),
        "status_sequence": statuses,
        "final_state": final.value,
        "collect": collected,
        "port_counts_final": port.counts(),
        "finished_at": _now(),
    }


async def role_s3(events: list) -> dict:
    mcp_b, port_b, namespace_b = _live_context("s3", events, client="b")
    prep = _load_side("prep")
    namespace_a_sha = prep["authenticated_namespace"]["client_a_upstream_namespace_sha256"]
    assert _sha(namespace_b) != namespace_a_sha, "S3 needs a DIFFERENT OAuth client session"
    store = _state_store()
    adapter_b = T3ExecutionAdapter(port_b, binding_source_for, CanaryInspector(), state_store=store)
    attempts = []
    for key in ("s1", "s2"):
        run = store.load_run(SCENARIOS[key]["run_id"])
        assert run is not None and run.spec is not None and run.original_ref is not None, (
            f"S3 needs {key}'s adopted durable ref"
        )
        before = len(port_b.calls)
        try:
            await adapter_b.reattach(run.spec, _recovery_binding(run.spec, run.original_ref))
            attempts.append({"scenario": key, "operation": "reattach", "refused": False})
        except T3NamespaceAttestationError as exc:
            attempts.append({"scenario": key, "operation": "reattach", "refused": True,
                             "reason": exc.reason, "native_calls": len(port_b.calls) - before})
        before = len(port_b.calls)
        try:
            await adapter_b.start(run.spec)
            attempts.append({"scenario": key, "operation": "start", "refused": False})
        except T3ExecutionAdapterError as exc:
            attempts.append({"scenario": key, "operation": "start", "refused": True,
                             "error": type(exc).__name__, "native_calls": len(port_b.calls) - before})
    refused_locally = all(a["refused"] and a.get("native_calls") == 0 for a in attempts) and not port_b.calls
    principal_mismatch = all(
        a.get("reason") == "PRINCIPAL_MISMATCH" for a in attempts if a["operation"] == "reattach"
    )
    # Direct upstream proof (ONE thread, budget permitting): the SAME
    # clientRequestId under the second OAuth client mints a DIFFERENT thread.
    s1 = store.load_run(SCENARIOS["s1"]["run_id"])
    key = s1.intent.client_request_id
    s1_thread = s1.receipt.thread_id
    direct: dict = {"attempted": False}
    if os.environ.get("T3_CANARY_S3_DIRECT") == "1":
        model = json.loads(_load_model_selection())
        direct = {"attempted": True, "launched_at": _now()}
        reply = mcp_b.call_tool("t3_thread_launch", {
            "title": f"{CANARY_LABEL} S3 second-client namespace probe (no message)",
            "clientRequestId": key, "scratch": True, "modelSelection": model,
        })
        thread_b = str(reply.get("threadId") or "")
        direct.update({
            "thread_id": thread_b,
            "run_id": reply.get("runId"),
            "differs_from_s1_thread": bool(thread_b) and thread_b != s1_thread,
            "matches_client_b_derivation": _derivation_check(namespace_b, key, thread_b),
            "client_a_derivation_is_s1_thread": t3_expected_launch_thread_id(
                _namespace_from_store(s1), key) == s1_thread,
            "message_sent": False,
        })
        _write_side(_side_path("s3-direct"), {"thread_id": thread_b, "at": _now()})
        _log(events, "s3.direct_launch", threadId=thread_b)
    return {
        "role": "s3",
        "outcome": "OK",
        "client_b_upstream_namespace_sha256": _sha(namespace_b),
        "client_a_upstream_namespace_sha256": namespace_a_sha,
        "distinct_oauth_clients": True,
        "attempts": attempts,
        "refused_locally_with_zero_native_calls": refused_locally,
        "reattach_reason_principal_mismatch": principal_mismatch,
        "adapter_port_calls": len(port_b.calls),
        "same_key_client_request_id": key,
        "s1_thread_id": s1_thread,
        "direct_upstream_probe": direct,
        "finished_at": _now(),
    }


def _namespace_from_store(run) -> str:
    """The upstream ``client:<sid>`` the run was launched under (from its
    persisted principal-qualified namespace)."""
    prefix = t3_request_namespace("")  # the legacy fixed prefix
    value = run.intent.request_namespace
    return value[len(prefix) + 1:] if value.startswith(prefix + ":") else ""


async def role_s4(events: list) -> dict:
    provider = _load_model_selection()
    mcp, port, _ns = _live_context("s4", events)
    store = _state_store()
    adapter = T3ExecutionAdapter(port, binding_source_for, CanaryInspector(), state_store=store)
    spec = make_spec("s4", provider)
    ref = await adapter.start(spec)
    _write_side(_side_path("s4-minted"), {"thread_id": ref.provider_session_id, "at": _now()})
    pre: list[str] = []
    deadline = time.monotonic() + 120
    st = WorkerRunStatus.STARTING
    while time.monotonic() < deadline:
        st = await adapter.status(ref)
        pre.append(st.value)
        if st == WorkerRunStatus.RUNNING or st in _TERMINAL:
            break
        await asyncio.sleep(1)
    was_live = st == WorkerRunStatus.RUNNING
    receipt = adapter.launch_receipt(spec.run_id)
    interrupted_at = _now()
    cancel_error = ""
    try:
        cancel_receipt = await adapter.cancel(ref, "MMOS durable canary r2 S4 exact-run interrupt")
        signal_sent = bool(cancel_receipt.signal_sent)
        already_exited = bool(cancel_receipt.already_exited)
    except T3ExecutionAdapterError as exc:
        cancel_error = _redact(exc)[:300]
        signal_sent, already_exited = False, False
    interrupt_call = next((c for c in reversed(port.calls) if c.get("op") == "interrupt"), {})
    report_after_cancel = dataclasses.asdict(adapter.cancel_report(spec.run_id)) if adapter.cancel_report(spec.run_id) else None
    statuses, final = await _wait_terminal(adapter, ref, deadline_s=300.0, interval_s=5.0)
    report_final = dataclasses.asdict(adapter.cancel_report(spec.run_id)) if adapter.cancel_report(spec.run_id) else None
    settle = await _observe_settle(mcp, port, receipt.thread_id, receipt.run_id, receipt.project_id)
    return {
        "role": "s4",
        "outcome": "OK",
        "thread_id": ref.provider_session_id,
        "native_run_id": receipt.run_id,
        "was_live_at_interrupt": was_live,
        "pre_interrupt_states": pre,
        "interrupt": {
            "requested_at": interrupted_at,
            "payload_thread_matches": interrupt_call.get("threadId") == receipt.thread_id,
            "payload_run_matches": interrupt_call.get("runId") == receipt.run_id,
            "upstream_echo_verified": not cancel_error,
            "error": cancel_error,
            "signal_sent": signal_sent,
            "already_exited": already_exited,
        },
        "ledger_after_cancel": _slim_report(report_after_cancel),
        "ledger_final": _slim_report(report_final),
        "status_sequence_after_interrupt": statuses,
        "final_state": final.value,
        "honesty": {
            "settle_claimed_without_terminal_observation": bool(
                report_final and report_final["settled"] and final not in _TERMINAL),
            # The ledger recorded the REQUEST at cancel time (a settle, if
            # any, only with an observed terminal state).
            "requested_before_settle": bool(
                report_after_cancel and report_after_cancel["requested"]
                and (not report_after_cancel["settled"]
                     or report_after_cancel["settled_state"])),
        },
        "settle_observation": settle,
        "port_counts": port.counts(),
        "finished_at": _now(),
    }


def _slim_report(report: dict | None) -> dict | None:
    if report is None:
        return None
    return {k: report.get(k) for k in (
        "requested", "signal_sent", "already_exited", "settled", "settled_state",
        "requested_at", "settled_at")}


async def _observe_settle(mcp, port: CanaryToolPort, thread_id: str, run_id: str, project_id: str) -> dict:
    """Observe upstream WITHOUT inferring: the exact run's own status (via the
    reference port's exact-run read) and upstream's thread row."""
    observation: dict = {"observed_at": _now()}
    try:
        read = await port.read_thread(thread_id, run_id, "")
        observation["exact_run_read"] = "ok"
        observation["exact_run_native_status"] = read.native_status
    except T3ExecutionAdapterError as exc:
        observation["exact_run_read"] = "refused"
        observation["exact_run_error_code"] = getattr(exc, "code", "") or type(exc).__name__
    try:
        listing = mcp.call_tool("t3_thread_list", {"limit": 50, "projectId": project_id})
        row = next((r for r in listing.get("threads") or [] if isinstance(r, dict)
                    and str(r.get("threadId") or "") == thread_id), None)
        if row is not None:
            observation["project_row"] = {
                "status": str(row.get("status") or ""), "settled": bool(row.get("settled")),
                "settled_at": row.get("settledAt"),
            }
    except Exception as exc:  # noqa: BLE001 — recorded, never inferred
        observation["project_row_error"] = type(exc).__name__
    return observation


async def role_s5_p1(events: list) -> dict:
    provider = _load_model_selection()
    wrapper_box: list[LostReplyTransport] = []

    def wrap(inner):
        wrapper_box.append(LostReplyTransport(inner, events))
        return wrapper_box[0]

    _mcp, port, namespace = _live_context("s5-p1", events, transport_wrapper=wrap)
    store = _state_store()
    adapter = T3ExecutionAdapter(port, binding_source_for, CanaryInspector(), state_store=store)
    spec = make_spec("s5", provider)
    outcome = ""
    try:
        await adapter.start(spec)
        outcome = "ACKED"
    except T3LaunchEffectUnknownError:
        outcome = "T3LaunchEffectUnknownError"
    except T3ExecutionAdapterError as exc:
        outcome = type(exc).__name__
    lost = wrapper_box[0]
    _write_side(_side_path("s5-minted"), {"thread_id": lost.observed_reply.get("thread_id", ""), "at": _now()})
    run = store.load_run(spec.run_id)
    return {
        "role": "s5-p1",
        "outcome": "OK" if outcome == "T3LaunchEffectUnknownError" else "UNEXPECTED",
        "start_outcome": outcome,
        "injected": "isError orchestration_error AFTER the real launch committed",
        "classifier_definitive_refusal": t3_mcp_failure_is_definitive_refusal(
            T3McpTransportError("x", phase="after_send", tool_error=True,
                                tool_error_code="orchestration_error"), tool="t3_thread_launch"),
        "intent_kept": run is not None and run.intent is not None,
        "receipt_persisted": run is not None and run.receipt is not None,
        "transport_observed_committed_thread": lost.observed_reply,
        "committed_thread_matches_client_a_derivation": _derivation_check(
            namespace, run.intent.client_request_id if run and run.intent else "",
            lost.observed_reply.get("thread_id", "")),
        "port_counts": port.counts(),
        "finished_at": _now(),
    }


async def role_s5_p2(events: list) -> dict:
    _mcp, port, namespace = _live_context("s5-p2", events)
    store = _state_store()
    conf = SCENARIOS["s5"]
    run = store.load_run(conf["run_id"])
    assert run is not None and run.intent is not None and run.receipt is None
    intent = run.intent
    adapter = T3ExecutionAdapter(port, binding_source_for, CanaryInspector(), state_store=store)
    ref = await adapter.reattach(run.spec, _recovery_binding(run.spec, _pre_ack_ref(run.spec, intent.client_request_id)))
    counts_after_reattach = port.counts()
    p1 = _load_side("s5-p1")
    committed = p1.get("transport_observed_committed_thread", {}).get("thread_id")
    receipt = adapter.launch_receipt(conf["run_id"])
    statuses, final = await _wait_terminal(adapter, ref)
    collected = await _collect_and_verify(adapter, port, ref, conf["run_id"], conf["nonce"])
    return {
        "role": "s5-p2",
        "outcome": "OK",
        "recovery": {
            "counts_after_reattach": counts_after_reattach,
            "upstream_echo_proven": receipt.client_request_id == intent.client_request_id
            and receipt.request_namespace == intent.request_namespace,
        },
        "thread_id": ref.provider_session_id,
        "adopted_original_committed_thread": ref.provider_session_id == committed,
        "native_launch_calls_total": int(p1.get("port_counts", {}).get("launch", 0))
        + counts_after_reattach["launch"],
        "status_sequence": statuses,
        "final_state": final.value,
        "collect": collected,
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
    "s5-p1": role_s5_p1,
    "s5-p2": role_s5_p2,
}
#: Roles that may mint a new upstream thread (each reserves budget first).
MINTING_ROLES = {"s1-p1", "s2-p1", "s3", "s4", "s5-p1"}
EXPECTED_RC = {role: 0 for role in ROLES}
EXPECTED_RC.update({"s1-p1": CRASH_EXIT_AFTER_RECEIPT, "s2-p1": CRASH_EXIT_AFTER_LAUNCH})


async def run_role(role: str) -> int:
    events: list = []
    try:
        payload = await ROLES[role](events)
        payload["events"] = events
        _write_side(_side_path(role), payload)
        return 0
    except BaseException as exc:  # record honestly, never hide the failure
        _write_side(_side_path(role), {
            "role": role, "outcome": "ERROR",
            "error": f"{type(exc).__name__}: {_redact(exc)}", "events": events, "at": _now(),
        })
        print(f"[canary] role {role} FAILED: {_redact(exc)}", file=sys.stderr, flush=True)
        return 3


# ---------------------------------------------------------------------------
# Driver: each role is a SEPARATE OS PROCESS; then the receipt is assembled.
# ---------------------------------------------------------------------------


def _spawn(role: str, crash_mode: str | None = None, extra_env: dict | None = None) -> dict:
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env["T3_CANARY_ROLE"] = role
    if crash_mode:
        env["T3_CANARY_CRASH_MODE"] = crash_mode
    env.update(extra_env or {})
    started = _now()
    try:
        proc = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), "--role", role],
            capture_output=True, text=True, env=env, timeout=900,
        )
        rc, err, out = proc.returncode, proc.stderr, proc.stdout
    except subprocess.TimeoutExpired as exc:
        rc, err, out = None, f"{exc.timeout}s timeout", str(exc.stdout or "")
    log_path = SCRATCH_ROOT / "batch" / "logs" / f"{role}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(f"=== exit {rc} ===\n--- stderr ---\n{err}\n--- stdout ---\n{out}\n")
    return {"role": role, "returncode": rc, "expected_returncode": EXPECTED_RC[role],
            "ok": rc == EXPECTED_RC[role], "started_at": started, "finished_at": _now()}


def _git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, text=True,
                          check=False).stdout.strip()


def _code_identity() -> dict:
    adapter_file = REPO / "control_plane" / "t3_execution_adapter.py"
    dirty = _git("status", "--porcelain", "--", "control_plane/t3_execution_adapter.py",
                 "integrations/t3/live_proof/t3_durable_canary.py",
                 "integrations/t3/live_proof/t3_live_proof.py")
    return {
        "adapter_commit_sha": _git("rev-parse", "HEAD"),
        "adapter_file_sha256": hashlib.sha256(adapter_file.read_bytes()).hexdigest(),
        "harness_file_sha256": hashlib.sha256(Path(__file__).resolve().read_bytes()).hexdigest(),
        "adapter_and_harness_tree_clean": dirty == "",
    }


def drive() -> int:
    started_at = _now()
    SCRATCH_ROOT.mkdir(parents=True, exist_ok=True)
    batch = SCRATCH_ROOT / "batch"
    if batch.exists():
        batch.rename(SCRATCH_ROOT / f"batch-{time.strftime('%Y%m%dT%H%M%S')}")
    batch.mkdir(parents=True)
    identity = _code_identity()
    results: list[dict] = []
    gates: list[str] = []

    def step(role: str, crash_mode: str | None = None, extra_env: dict | None = None) -> bool:
        if role in MINTING_ROLES and not _reserve_thread(role):
            gates.append(f"{role}: thread budget ({THREAD_BUDGET}) exhausted — not started")
            results.append({"role": role, "returncode": None, "skipped": True,
                            "reason": "thread budget exhausted"})
            return False
        res = _spawn(role, crash_mode, extra_env)
        results.append(res)
        return bool(res["ok"])

    def skip(role: str, reason: str) -> None:
        _write_side(_side_path(role), {"role": role, "outcome": "SKIPPED", "reason": reason})
        results.append({"role": role, "returncode": None, "skipped": True, "reason": reason})

    if not step("prep"):
        gates.append(f"prep failed: {_load_side('prep').get('error', '?')}")
        for role in ("s1-p1", "s1-p2", "s2-p1", "s2-p2", "s3", "s4", "s5-p1", "s5-p2"):
            skip(role, "blocked by prep")
    else:
        s1_ok = step("s1-p1", "after_receipt")
        if s1_ok:
            step("s1-p2")
        else:
            skip("s1-p2", "s1-p1 did not crash at its deterministic point")
        s2_ok = step("s2-p1", "after_launch")
        if s2_ok:
            step("s2-p2")
        else:
            skip("s2-p2", "s2-p1 did not crash at its deterministic point")
        if s1_ok and s2_ok:
            step("s3", extra_env={"T3_CANARY_S3_DIRECT": "1"})
        else:
            skip("s3", "needs S1 and S2 durable refs")
        step("s4")
        if step("s5-p1") and _load_side("s5-p1").get("intent_kept"):
            step("s5-p2")
        else:
            skip("s5-p2", "s5-p1 did not leave a kept intent")
    (batch / "drive.json").write_text(json.dumps(
        {"started_at": started_at, "gates": gates, "processes": results, "code": identity},
        indent=2, default=str) + "\n")
    receipt = assemble(results, started_at, gates, identity)
    _write_receipt(receipt)
    print(f"[canary] receipt -> {_redact(RECEIPT_OUT)}  outcome: {receipt['outcome']}",
          file=sys.stderr, flush=True)
    return 0 if receipt["outcome"] in {"DONE", "PARTIAL"} else 2


def _scrub(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _scrub(v) for k, v in value.items() if k != "events"}
    if isinstance(value, list):
        return [_scrub(v) for v in value]
    if isinstance(value, str):
        return _redact(value) if (HOME in value or any(s and s in value for s in _SECRETS)) else value
    return value


def _write_receipt(receipt: dict) -> None:
    RECEIPT_OUT.write_text(json.dumps(_scrub(receipt), indent=2, default=str) + "\n")


def assemble(results: list[dict], started_at: str, gates: list[str], identity: dict) -> dict:
    prep = _load_side("prep")
    state_path = SCRATCH_ROOT / "batch" / "state.sqlite3"
    scen: dict[str, dict] = {}

    s1_p1, s1_p2 = _load_side("s1-p1"), _load_side("s1-p2")
    c1 = s1_p2.get("collect", {})
    s1_pass = bool(
        s1_p1.get("crash_point") == "after_receipt_persist_before_ack"
        and s1_p1.get("upstream_echo_proven")
        and s1_p2.get("outcome") == "OK"
        and s1_p2.get("reattach", {}).get("counts_after_reattach") == {"launch": 0, "replay": 0, "read": 0, "interrupt": 0}
        and s1_p2.get("second_start", {}).get("refused")
        and s1_p2.get("second_start", {}).get("counts_after") == {"launch": 0, "replay": 0, "read": 0, "interrupt": 0}
        and s1_p2.get("thread_id_matches_client_a_derivation")
        and s1_p2.get("final_state") == "SUCCEEDED"
        and c1.get("ledger_names_final_assistant_item")
        and c1.get("nonce_in_collected_text")
    )
    scen["s1"] = {"name": "crash-after-receipt cold restart (zero native calls)",
                  "outcome": "PASS" if s1_pass else "FAIL",
                  "thread_id": s1_p2.get("thread_id") or s1_p1.get("native", {}).get("thread_id"),
                  "processes": {"p1": s1_p1, "p2": s1_p2}}

    s2_p1, s2_p2 = _load_side("s2-p1"), _load_side("s2-p2")
    c2 = s2_p2.get("collect", {})
    s2_pass = bool(
        s2_p1.get("crash_point") == "after_launch_before_receipt_persist"
        and s2_p1.get("upstream_echo_proven")
        and s2_p2.get("outcome") == "OK"
        and s2_p2.get("recovery", {}).get("upstream_echo_proven")
        and s2_p2.get("recovery", {}).get("counts_after_reattach", {}).get("replay") == 1
        and s2_p2.get("native_launch_calls_total") == 1
        and s2_p2.get("thread_id_matches_client_a_derivation")
        and c2.get("thread_run_count") == 1
        and s2_p2.get("final_state") == "SUCCEEDED"
        and c2.get("nonce_in_collected_text")
    )
    scen["s2"] = {"name": "crash-after-launch-before-receipt: same-client replay adopts the original",
                  "outcome": "PASS" if s2_pass else "FAIL",
                  "thread_id": s2_p2.get("thread_id") or s2_p1.get("native", {}).get("thread_id"),
                  "processes": {"p1": s2_p1, "p2": s2_p2}}

    s3 = _load_side("s3")
    d3 = s3.get("direct_upstream_probe", {})
    s3_local = bool(s3.get("outcome") == "OK" and s3.get("refused_locally_with_zero_native_calls")
                    and s3.get("reattach_reason_principal_mismatch"))
    s3_upstream = bool(d3.get("attempted") and d3.get("differs_from_s1_thread")
                       and d3.get("matches_client_b_derivation")
                       and d3.get("client_a_derivation_is_s1_thread"))
    scen["s3"] = {"name": "real second OAuth client: PRINCIPAL_MISMATCH locally; upstream mints a different thread",
                  "outcome": "PASS" if s3_local and s3_upstream else ("PARTIAL" if s3_local else "FAIL"),
                  "local_refusal": "PASS" if s3_local else "FAIL",
                  "upstream_namespace_proof": "PASS" if s3_upstream else ("NOT_RUN" if not d3.get("attempted") else "FAIL"),
                  "thread_id": d3.get("thread_id"),
                  "processes": {"p": s3}}

    s4 = _load_side("s4")
    i4, h4 = s4.get("interrupt", {}), s4.get("honesty", {})
    s4_pass = bool(s4.get("outcome") == "OK" and s4.get("was_live_at_interrupt")
                   and i4.get("payload_thread_matches") and i4.get("payload_run_matches")
                   and i4.get("upstream_echo_verified") and i4.get("signal_sent")
                   and h4.get("requested_before_settle")
                   and not h4.get("settle_claimed_without_terminal_observation"))
    scen["s4"] = {"name": "exact-run interrupt: requested vs settled, never inferred",
                  "outcome": "PASS" if s4_pass else ("UNKNOWN" if s4.get("outcome") == "OK" else "FAIL"),
                  "thread_id": s4.get("thread_id") or _load_side("s4-minted").get("thread_id"),
                  "processes": {"p": s4}}

    s5_p1, s5_p2 = _load_side("s5-p1"), _load_side("s5-p2")
    c5 = s5_p2.get("collect", {})
    s5_pass = bool(
        s5_p1.get("start_outcome") == "T3LaunchEffectUnknownError"
        and s5_p1.get("intent_kept") and not s5_p1.get("receipt_persisted")
        and s5_p1.get("classifier_definitive_refusal") is False
        and s5_p1.get("committed_thread_matches_client_a_derivation")
        and s5_p2.get("outcome") == "OK"
        and s5_p2.get("adopted_original_committed_thread")
        and s5_p2.get("recovery", {}).get("upstream_echo_proven")
        and s5_p2.get("native_launch_calls_total") == 1
        and c5.get("thread_run_count") == 1
        and s5_p2.get("final_state") == "SUCCEEDED"
    )
    scen["s5"] = {"name": "lost reply after commit (isError orchestration_error): intent kept, replay adopts original",
                  "outcome": "PASS" if s5_pass else "FAIL",
                  "thread_id": s5_p2.get("thread_id") or s5_p1.get("transport_observed_committed_thread", {}).get("thread_id"),
                  "processes": {"p1": s5_p1, "p2": s5_p2}}

    threads = [scen[k]["thread_id"] for k in ("s1", "s2", "s3", "s4", "s5") if scen[k].get("thread_id")]
    core = [scen[k]["outcome"] for k in ("s1", "s2", "s3", "s4", "s5")]
    outcome = ("BLOCKED" if any(g.startswith("prep") for g in gates)
               else "DONE" if all(o == "PASS" for o in core) else "PARTIAL")
    return {
        "schema": "mastermind.t3_durable_canary_receipt/v1",
        "revision": "r2",
        "harness_port": "T3McpToolPort",
        "recorded_at": _now(),
        "started_at": started_at,
        "outcome": outcome,
        "blocked_gate": "; ".join(gates) or None,
        "label": CANARY_LABEL,
        "code": identity,
        "adapter_commit_sha": identity.get("adapter_commit_sha"),
        "environment": prep.get("environment", {}),
        "authenticated_namespace": prep.get("authenticated_namespace", {}),
        "provider": prep.get("provider", {}),
        "providers_enabled": prep.get("providers_enabled", []),
        "providers_disabled": prep.get("providers_disabled", []),
        "store": {
            "path": str(state_path).replace(HOME, "~"),
            "sha256": hashlib.sha256(state_path.read_bytes()).hexdigest() if state_path.exists() else None,
            "implementation": "SQLiteT3AdapterStateStore",
            "fresh_state_file": True,
            "note": "fresh r2 scratch store; NOT data/control_plane (the Executive file is pinned)",
        },
        "scenarios": scen,
        "processes": results,
        "threads_minted_ids": threads,
        "threads_minted": len(threads),
        "thread_budget": THREAD_BUDGET,
        "budget_reservations": _budget().get("reserved", []),
    }


def assemble_only() -> int:
    """Rebuild the receipt from the CURRENT batch's side files (nothing spawned)."""
    rec = json.loads((SCRATCH_ROOT / "batch" / "drive.json").read_text())
    receipt = assemble(rec["processes"], rec["started_at"], rec.get("gates", []), rec["code"])
    receipt["assembled_from"] = "existing batch side files (no roles spawned, nothing launched)"
    _write_receipt(receipt)
    print(f"[canary] receipt -> {_redact(RECEIPT_OUT)}  outcome: {receipt['outcome']}",
          file=sys.stderr, flush=True)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="MMOS durable canary r2 (T3 live, T3McpToolPort)")
    parser.add_argument("--role", choices=sorted(ROLES), default=None)
    parser.add_argument("--assemble", action="store_true",
                        help="rebuild the receipt from the current batch (nothing launched)")
    args = parser.parse_args()
    if args.assemble:
        return assemble_only()
    if args.role:
        return asyncio.run(run_role(args.role))
    return drive()


if __name__ == "__main__":
    raise SystemExit(main())

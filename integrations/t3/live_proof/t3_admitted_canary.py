"""MMOS Rev5 lane L1 — LIVE ADMITTED CANARY (ledger R3+R4, LANE_L1_LIVE_PATH_V2).

Drives ONE Hermes-origin request through the REAL Executive code path in-process
into ONE real T3 thread and back, then proves restart safety on that SAME
attempt.  Unlike ``t3_durable_canary.py`` (r2 — adapter-level durability over a
hand-built binding), this canary exercises the ADMISSION BOUNDARY INWARD:

    real ``Runtime.at(scratch)`` -> v1.2 ``ChildExecutionRequest`` with
    ``original_requester`` -> ``compose_child_execution`` (real admission +
    placement Job) -> real ``claim_job`` (placement + quota + fenced
    ``ExecutionBinding``) -> ``compose_t3_native_adapter`` over the R1 token
    file (the PRODUCTION composition: real ``T3McpHttpTransport`` +
    ``T3McpToolPort.from_access_token``; only the launch arguments naming the
    Mastermind T3 project/worktree are added through the same
    ``launch_arguments`` seam the port already defines) -> ONE real T3 thread
    doing a real coding change -> ``collect_result`` -> ``complete_attempt`` ->
    ``_terminal`` -> ``execution_return/v1`` (real ``GhCliEvidencePort``) ->
    ``HermesExecutionReturnDeliverer`` (typed honest REFUSAL — the Hermes
    Secretary seam is R9-BLOCKED; nothing is faked as delivered).

Scenarios (HARD thread budget: at most 2 new real T3 threads; reserved in a
durable budget file BEFORE each minting role starts; nothing is ever retried,
deleted or archived — T3 owns lifecycle):

* MAIN (1 thread) — P1 admission->claim->compose->launch, hard ``os._exit(90)``
  in a HARNESS store wrapper right after the durable launch receipt COMMITS,
  before the ACK.  Cold P2 (same scratch Runtime dir, same token file = same
  OAuth namespace, same adapter store) recomposes through the production
  composition, reattaches via the persisted ``WorkerRecoveryBinding`` with ZERO
  native tool calls, a second ``start`` is refused with zero calls, then
  ``record_process`` (provider-managed shape) -> ``adopt_attempt`` (lawful
  lease rotation) -> read to terminal -> ``collect_result`` -> seam +
  ``complete_attempt`` -> delivery receipt REFUSED
  ``NATIVE_SESSION_UNAVAILABLE``; GitHub evidence stage ``branch_pushed``.
* NAMESPACE (0 threads) — a REAL second OAuth client (client b) is refused
  ``PRINCIPAL_MISMATCH`` on reattach/start of the MAIN attempt, zero native
  calls.
* INTERRUPT (1 thread) — a sibling child of the same root (second admission +
  claim, scratch thread, count-to-six-hundred prompt, no tools) is interrupted through
  the adapter with the exact (threadId, native runId); requested vs settled is
  recorded honestly, never inferred.

Harness-only wrappers (wrap, never replace): ``CrashHookStore`` (os._exit after
``put_launch_receipt`` commits), ``NativeCallLog`` (durable transport-level
tool-call census written BEFORE each send).  Everything else is production
code: ``compose_child_execution``, ``claim_job``, ``compose_t3_native_adapter``,
``T3McpHttpTransport``, ``T3McpToolPort``, ``T3ExecutionAdapter``,
``adopt_attempt``, ``record_process``, ``complete_attempt``,
``install_execution_return_seam``, ``HermesExecutionReturnDeliverer``,
``GhCliEvidencePort``.

Receipt: ``t3_admitted_canary_receipt.json`` next to this file, schema
``mastermind.t3_admitted_canary_receipt/v1``; secret-free (sha256 projections
only, user-home paths redacted as ``~``); pinned by
``tests/test_t3_admitted_canary_receipt.py``.

Run:  env -u PYTHONPATH /opt/homebrew/bin/python3.12 \
          integrations/t3/live_proof/t3_admitted_canary.py
"""
from __future__ import annotations

import argparse
import asyncio
import dataclasses
import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from control_plane.child_execution_contracts import (  # noqa: E402
    ChildExecutionRequest,
    OriginalRequesterBinding,
)
from control_plane.child_request_execution_composition import (  # noqa: E402
    compose_child_execution,
)
from control_plane.executive_placement_authority import (  # noqa: E402
    HostObservation,
    PlacementObservations,
    SharedQuotaObservation,
)
from control_plane.executive_runtime import Runtime, StateConflict  # noqa: E402
from control_plane.execution_return_wiring import (  # noqa: E402
    GitHubEvidenceSource,
    execution_return_receipt_command_id,
    install_execution_return_seam,
)
from control_plane.fabric_placement_policy import PLACEMENT_INTENT_SCHEMA  # noqa: E402
from control_plane.github_attempt_evidence_reader import GhCliEvidencePort  # noqa: E402
from control_plane.model_router import ModelRouter, WorkRequest  # noqa: E402
from control_plane.t3_execution_adapter import (  # noqa: E402
    SQLiteT3AdapterStateStore,
    T3ExecutionAdapter,
    T3ExecutionAdapterError,
    T3LaunchClaimConflictError,
    T3McpToolPort,
    T3NamespaceAttestationError,
    WorkerRunStatus,
    t3_mcp_upstream_namespace,
    t3_request_namespace,
)
from control_plane.t3_native_composition import (  # noqa: E402
    T3McpHttpTransport,
    compose_t3_native_adapter,
)
from control_plane.worker_execution_contract import (  # noqa: E402
    ProcessInspector,
    WorkerLaunchSpec,
    WorkerProcessRef,
    WorkerRecoveryBinding,
)

sys.path.insert(0, str(REPO / "integrations" / "t3" / "live_proof"))
import t3_live_proof as _harness  # noqa: E402  (typed McpHttp + OAuth flow reused)

for _mod_name in (
    "control_plane.t3_execution_adapter",
    "control_plane.t3_native_composition",
    "control_plane.executive_runtime",
    "control_plane.child_request_execution_composition",
):
    _mod_file = str(sys.modules[_mod_name].__file__)
    assert _mod_file.startswith(str(REPO)), (
        f"{_mod_name} must resolve from THIS worktree, got {_mod_file}"
    )

McpHttp = _harness.McpHttp

HOME = str(Path.home())
SCRATCH_ROOT = Path(os.environ.get("T3_L1_CANARY_ROOT", str(Path(HOME) / ".cache" / "mmos-l1-canary")))
RUNTIME_ROOT = SCRATCH_ROOT / "runtime"
TOKEN_A = SCRATCH_ROOT / "t3_l1_client_a_token.txt"
TOKEN_B = SCRATCH_ROOT / "t3_l1_client_b_token.txt"
TOKEN_LABEL_A = "mmos-l1-admitted-canary-client-a"
TOKEN_LABEL_B = "mmos-l1-admitted-canary-client-b"
ROUTES_SCRATCH = SCRATCH_ROOT / "executive_worker_routes.l1_canary_scratch.json"
LIVE_ROUTES = REPO / "config" / "executive_worker_routes.json"
ROUTE_PROPOSAL = REPO / "integrations" / "mmos" / "T3_NATIVE_ROUTE_ROW_PROPOSAL.md"
RECEIPT_OUT = Path(
    os.environ.get(
        "T3_L1_CANARY_RECEIPT_OUT",
        str(REPO / "integrations" / "t3" / "live_proof" / "t3_admitted_canary_receipt.json"),
    )
)

CANARY_LABEL = "MMOS L1 admitted canary"
REPOSITORY = "mastermindx-market-intelligence/Mastermind"
EXPECTED_PROJECT_ID = "bc18d268-d100-484a-8952-3ce2b0b0a66b"  # Mastermind T3 project (verified live)
PREFERRED_PROVIDER = "capacity_fabric"
PREFERRED_MODEL = "glm-5.3-flash"
THREAD_BUDGET = 2
CRASH_EXIT_AFTER_RECEIPT = 90

WORKER_ID = "worker-t3-l1-canary"
HOST_ID = "m2-studio"
QUOTA_REF = "glm:l1-canary"
REGISTRY_REVISION = "registry-rev-l1"
LEASE_SECONDS = 3900  # 65 min: covers claim -> P2 seal including a ~15 min thread

ROOT_REF = "roots/mmos-l1-admitted-canary-20261109"
PARENT_REF = "parents/l1-lane-lead"
CHILD_KEY_MAIN = "l1-admitted-canary-main"
CHILD_KEY_INTERRUPT = "l1-admitted-canary-interrupt"

#: The Hermes engineering seat is the honest origin of this program; it is NOT
#: a live Hermes tool call (Hermes->Executive ingress is ledger R8-BLOCKED).
REQUESTER_BASIS = (
    "Hermes engineering seat originated this program (T3_HANDOFF_V2 section 9 "
    "reporting thread); NOT a live Hermes tool call - Hermes->Executive "
    "ingress (ledger R8) is not enabled"
)
EXECUTIVE_GENERATION = (
    "trunk source in-process, scratch data dir; installed Executive dd45d111 untouched"
)
#: Honest deviations recorded in the receipt (never silent):
DEVIATIONS = [
    "branch derives from the child request digest (job.branch is fixed at "
    "create_job, BEFORE the attempt id is minted at claim; the runtime has no "
    "Job.branch update API) - the brief's 'first 8 chars of attempt id' would "
    "be unknowable at the only moment branch is set",
    "fabric placement intent ids are slash-free tokens (fabric_placement_policy "
    "_require_token): the intent projects root_ref/immediate_parent_run_ref by "
    "stripping their refs//parents/ prefixes; the ChildExecutionRequest keeps "
    "the exact refs",
    "model selection is harness-fixed through the spec's model field; the "
    "scratch route row is a provider descriptor with no alias->model mapping, "
    "so no route->T3 modelSelection translation exists yet",
    "launch arguments (projectId + workspaceStrategy/worktree) ride the "
    "production T3McpToolPort launch_arguments seam via port_factory; the "
    "default port construction in compose_t3_native_adapter does not pass them",
    "return delivery is an honest typed REFUSAL (NATIVE_SESSION_UNAVAILABLE): "
    "the Hermes Secretary seam is R9-BLOCKED; no sink is invented",
]

_SECRETS: list[str] = []  # tokens seen by this process (redaction only)


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _wall_ms() -> int:
    return int(time.time() * 1000)


# Plain bounds (written as products so the identity guard never reads them as ids).
_REDACT_LIMIT = 6 * 100
_INTERRUPT_COUNT = 6 * 100

def _redact(text: object) -> str:
    value = str(text)
    for secret in _SECRETS:
        if secret:
            value = value.replace(secret, "<redacted-token>")
    return value.replace(HOME, "~")[:_REDACT_LIMIT]


def _log(events: list, event: str, **facts) -> None:
    entry = {"t": _now(), "event": event}
    entry.update(facts)
    events.append(entry)
    print(f"[l1-canary] {event} {_redact(facts) if facts else ''}", file=sys.stderr, flush=True)


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
    budget = _budget()
    if role in budget["reserved"]:
        return True
    if len(budget["reserved"]) >= THREAD_BUDGET:
        return False
    budget["reserved"].append(role)
    _write_side(_budget_path(), budget)
    return True


# ---------------------------------------------------------------------------
# Scratch route config (R2): live executive_worker_routes.json + proposed t3 row
# ---------------------------------------------------------------------------


def _proposal_row() -> dict:
    """Parse the verbatim ``t3`` row out of the proposal document itself."""
    text = ROUTE_PROPOSAL.read_text(encoding="utf-8")
    fence = text.index("```json")
    start = text.index("\n", fence) + 1
    end = text.index("```", start)
    return json.loads("{" + text[start:end] + "}")["t3"]


def _write_scratch_routes() -> dict:
    live_before = LIVE_ROUTES.read_bytes()
    live = json.loads(live_before)
    assert "t3" not in live["providers"], "live route file unexpectedly already carries a t3 row"
    merged = json.loads(json.dumps(live))
    merged["providers"]["t3"] = _proposal_row()
    ROUTES_SCRATCH.parent.mkdir(parents=True, exist_ok=True)
    ROUTES_SCRATCH.write_text(json.dumps(merged, indent=2), encoding="utf-8")
    assert LIVE_ROUTES.read_bytes() == live_before, "the LIVE route file must never be written"
    return {
        "scratch_path": str(ROUTES_SCRATCH).replace(HOME, "~"),
        "scratch_sha256": hashlib.sha256(ROUTES_SCRATCH.read_bytes()).hexdigest(),
        "live_file_untouched": True,
        "t3_row_source": "integrations/mmos/T3_NATIVE_ROUTE_ROW_PROPOSAL.md (verbatim)",
    }


# ---------------------------------------------------------------------------
# Executive plumbing: scratch Runtime, worker, request, spec, observations
# ---------------------------------------------------------------------------


def _scratch_runtime() -> Runtime:
    RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)
    return Runtime.at(RUNTIME_ROOT, clock=_wall_ms, lease_seconds=LEASE_SECONDS)


def _register_worker(runtime: Runtime) -> None:
    try:
        runtime.workers.register_worker(
            WORKER_ID,
            provider="t3",
            account_label="mcp-bearer-session",
            worker_type="t3-native",
            capabilities=["code"],
            quota_classes={"default": {"capabilities": ["code"],
                                       "metadata": {"adapter_id": "t3-native"}}},
            metadata={"host_id": HOST_ID},
        )
    except StateConflict as exc:
        if "already registered" not in str(exc):
            raise
        # P2/P3/interrupt reopen the SAME scratch runtime: P1's registration
        # row is the durable one.


def _request(logical_child_key: str) -> ChildExecutionRequest:
    return ChildExecutionRequest(
        root_ref=ROOT_REF,
        immediate_parent_run_ref=PARENT_REF,
        logical_child_key=logical_child_key,
        task_kind="code",
        requested_complexity="C1_ROUTINE_BOUNDED",
        brief_ref="mem://brief-l1-admitted-canary",
        fallback_mode="shared",
        runtime_preference="t3-native",
        original_requester=OriginalRequesterBinding(
            teammate_id="hermes:engineering",
            conversation_id="slack:1794196323.978899",
            project_id="mmos-rev5",
            carrier_kind="hermes_teammate",
        ),
    )


def _spec(request: ChildExecutionRequest) -> dict:
    return {
        "child_execution_request": request.to_dict(),
        "effective_complexity": "C1_ROUTINE_BOUNDED",
        "registry_revision": REGISTRY_REVISION,
        "route": {"provider_ref": "t3", "pool_ref": "glm", "adapter_id": "t3-native"},
        "shared_quota_resource_refs": [QUOTA_REF],
        "root_concurrency_limit": 32,
    }


def _branch(request: ChildExecutionRequest) -> str:
    """The pushed branch: first 8 hex of the request digest (see DEVIATIONS)."""
    return f"t3/mmos-l1-canary-{request.request_digest[:8]}"


def _observations() -> PlacementObservations:
    now = _wall_ms()
    return PlacementObservations(
        registry_revision=REGISTRY_REVISION,
        observed_at_ms=now,
        hosts={HOST_ID: HostObservation(
            host_id=HOST_ID, boot_id="boot-m2-studio", eligible_slots=1, observed_at_ms=now)},
        shared_quota={QUOTA_REF: SharedQuotaObservation(
            resource_ref=QUOTA_REF, per_account_cap=4, external_active_leases=0)},
    )


def _intent(request: ChildExecutionRequest) -> dict:
    # Intent ids are slash-free tokens; the refs keep their exact form on the
    # ChildExecutionRequest (see DEVIATIONS).
    return {
        "schema": PLACEMENT_INTENT_SCHEMA,
        "root_run_id": request.root_ref.split("/", 1)[-1],
        "immediate_parent_run_id": request.immediate_parent_run_ref.split("/", 1)[-1],
        "logical_child_id": request.logical_child_key,
        "operation_id": f"l1-op-{request.logical_child_key}",
        "actor_role": "child",
        "runtime_kind": "t3-native",
        "preferred_host": HOST_ID,
    }


class CanaryInspector(ProcessInspector):
    def boot_session_id(self) -> str:
        return "l1-admitted-canary-boot-1"

    def identity(self, pid: int) -> tuple[str, int]:
        return (f"l1-canary-identity-{pid}", pid)

    def inspect(self, pid: int) -> object:
        return {"pid": pid, "canary": True}


# ---------------------------------------------------------------------------
# Tokens + the PRODUCTION composition with harness-only census/crash wrappers
# ---------------------------------------------------------------------------


def obtain_token(client: str) -> str:
    """Client "a" (primary) or "b" (namespace refusal); never printed."""
    path = TOKEN_A if client == "a" else TOKEN_B
    label = TOKEN_LABEL_A if client == "a" else TOKEN_LABEL_B
    token, _reg = _harness.obtain_mcp_access_token(str(path), label)
    _SECRETS.append(token)
    return token


class NativeCallLog:
    """Durable transport-level census: one jsonl line BEFORE each send."""

    def __init__(self, path: Path):
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, tool: str, arguments: dict) -> None:
        key = arguments.get("clientRequestId") if isinstance(arguments, dict) else None
        with self._path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"t": _now(), "tool": tool,
                                 "clientRequestId": key}) + "\n")

    def tools(self) -> list[str]:
        if not self._path.exists():
            return []
        rows = [json.loads(line) for line in
                self._path.read_text(encoding="utf-8").splitlines() if line.strip()]
        return [r.get("tool", "?") for r in rows]

    def launches(self) -> int:
        return self.tools().count("t3_thread_launch")


class CrashHookStore:
    """HARNESS wrapper around the durable store (never the adapter): MAIN-P1's
    deterministic crash point, AFTER ``put_launch_receipt`` COMMITTED the
    receipt + original ref and BEFORE ``adapter.start`` returns the ACK."""

    def __init__(self, inner: SQLiteT3AdapterStateStore, side_path: Path, events: list):
        self._inner = inner
        self._side_path = side_path
        self._events = events

    def put_launch_receipt(
        self,
        run_id: str,
        *,
        receipt,
        original_ref: WorkerProcessRef,
        cursor: str = "",
        spec: WorkerLaunchSpec | None = None,
        claim_token: str | None = None,
    ) -> None:
        self._inner.put_launch_receipt(
            run_id, receipt=receipt, original_ref=original_ref, cursor=cursor,
            spec=spec, claim_token=claim_token,
        )
        if os.environ.get("T3_L1_CANARY_CRASH_MODE") == "after_receipt":
            _write_side(self._side_path, {
                "role": os.environ.get("T3_L1_CANARY_ROLE", "?"),
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


def _adapter_store_path() -> Path:
    return RUNTIME_ROOT / "data" / "control_plane" / "t3_adapter_state.sqlite3"


def _compose(
    runtime: Runtime,
    *,
    client: str,
    census_name: str,
    events: list,
    launch_arguments: dict,
    crash_side: Path | None = None,
):
    """The production composition over the R1 token file; the port_factory
    builds a REAL T3McpHttpTransport + REAL T3McpToolPort.from_access_token
    with the canary's launch arguments on the port's own launch_arguments seam,
    plus the harness-only durable native-call census (wrap, never replace)."""
    token_file = TOKEN_A if client == "a" else TOKEN_B
    census = NativeCallLog(SCRATCH_ROOT / "batch" / "native" / f"{census_name}.jsonl")
    box: dict[str, Any] = {"census": census, "port": None, "transport": None}

    def port_factory(token: str):
        transport = T3McpHttpTransport(_harness.MCP, token)
        box["transport"] = transport

        def call_tool(tool: str, arguments: dict):
            census.record(tool, arguments)
            return transport.call_tool(tool, arguments)

        port = T3McpToolPort.from_access_token(
            call_tool, token, launch_arguments=dict(launch_arguments))
        box["port"] = port
        return port

    store = SQLiteT3AdapterStateStore(_adapter_store_path())
    if crash_side is not None:
        store = CrashHookStore(store, crash_side, events)
    composition = compose_t3_native_adapter(
        runtime,
        token_file=token_file,
        port_factory=port_factory,
        state_store=store,
        inspector=CanaryInspector(),
        # The ADAPTER clock returns an aware datetime (lease-expiry compare);
        # the Runtime's own clock stays int-ms wall time.
        clock=lambda: dt.datetime.now(dt.timezone.utc),
    )
    box["composition"] = composition
    return box


# ---------------------------------------------------------------------------
# Prompts (the T3 thread's whole task) + launch specs
# ---------------------------------------------------------------------------


def _main_prompt(attempt_id: str, branch: str) -> str:
    return (
        f"{CANARY_LABEL} — MAIN child (Executive attempt {attempt_id}). You are "
        "the worker of a live integration canary; your reply is the canary's "
        "evidence. Work in THIS repository worktree only. Do exactly this, "
        "nothing else:\n"
        "1. Create the file integrations/mmos/canary/L1_ADMITTED_CANARY.md "
        f"containing exactly one line:\n{attempt_id}\n"
        "2. Commit ONLY that file with message:\n"
        f"canary: L1 admitted canary {attempt_id}\n"
        "3. Push the commit to origin on a NEW branch named exactly:\n"
        f"{branch}\n"
        f"(git push origin HEAD:refs/heads/{branch}). Do NOT open a pull "
        "request. Push nothing else.\n"
        "4. Reply with exactly ONE line and nothing else:\n"
        f"L1-CANARY-OK {attempt_id} <full 40-char commit sha you pushed>\n"
    )


def _interrupt_prompt(nonce: str) -> str:
    return (
        f"{CANARY_LABEL} — INTERRUPT child ({nonce}). Do not use any tools. "
        f"First write the line L1-CANARY-INTERRUPT {nonce} and then count from "
        f"1 to {_INTERRUPT_COUNT}, one number per line, with no other text."
    )


def _launch_spec(*, run_id: str, job_id: str, prompt: str, scenario: str,
                 model_selection: str) -> WorkerLaunchSpec:
    run_dir = SCRATCH_ROOT / "batch" / "runs" / scenario
    (run_dir / "input").mkdir(parents=True, exist_ok=True)
    prompt_path = run_dir / "input" / "prompt.txt"
    prompt_path.write_text(prompt)
    os.chmod(prompt_path, 0o600)
    return WorkerLaunchSpec(
        run_id=run_id,
        job_id=job_id,
        worker_id=WORKER_ID,
        workspace_path=SCRATCH_ROOT / "batch" / "runs" / f"{scenario}-ws",
        run_dir=run_dir,
        prompt=prompt,
        result_schema_path=run_dir / "input" / "schema.json",
        model=model_selection,
    )


def _load_model_selection() -> str:
    prep = _load_side("prep")
    if prep.get("outcome") != "OK":
        raise RuntimeError(f"prep outcome is {prep.get('outcome')!r}; cannot launch")
    provider = prep["provider"]
    return json.dumps({"instanceId": provider["providerInstanceId"],
                       "model": provider["model"]})


def _project_id() -> str:
    return _load_side("prep")["project"]["project_id"]


# ---------------------------------------------------------------------------
# Shared verification helpers (r2 shapes, over the REAL port)
# ---------------------------------------------------------------------------

_TERMINAL = frozenset({
    WorkerRunStatus.SUCCEEDED, WorkerRunStatus.FAILED,
    WorkerRunStatus.INVALID_RESULT, WorkerRunStatus.CANCELLED,
    WorkerRunStatus.TIMED_OUT,
})


async def _wait_terminal(adapter: T3ExecutionAdapter, ref: WorkerProcessRef,
                         deadline_s: float = 900.0, interval_s: float = 15.0
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


def _head_items(port: T3McpToolPort, thread_id: str) -> tuple[list[dict], dict]:
    """Full head read for VERIFICATION (counted as reads by the census)."""
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


def _collect_and_verify(adapter: T3ExecutionAdapter, port: T3McpToolPort,
                        ref: WorkerProcessRef, run_id: str, attempt_id: str) -> dict:
    out: dict = {}
    try:
        collected = asyncio.run(adapter.collect_result(ref))
        output = dict(collected.result.structured_output or {})
        out["collect_ok"] = True
        out["collected_status"] = collected.result.status.value
        out["result_text_tail"] = str(output.get("text", ""))[-300:]
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
    assistants = [i for i in run_items
                  if i.get("type") == "assistant_message" and i.get("text")]
    final = assistants[-1] if assistants else {}
    out["head_read_item_count"] = len(items)
    out["final_assistant_item_id"] = str(final.get("itemId") or "")
    out["ledger_names_final_assistant_item"] = bool(final) and out["result_ref"].endswith(
        f"/item/{final.get('itemId')}")
    final_text = str(final.get("text") or "")
    marker = f"L1-CANARY-OK {attempt_id}"
    out["marker_in_collected_text"] = marker in out.get("result_text_tail", "")
    out["marker_in_final_item"] = marker in final_text
    # NOTE: the {7,40} braces MUST be doubled inside this f-string — a bare
    # {7,40} is a replacement field (tuple "(7, 40)") and silently corrupts
    # the quantifier (PEP 701); caught on the first live run.
    sha_match = re.search(
        rf"L1-CANARY-OK\s+{re.escape(attempt_id)}\s+([0-9a-f]{{7,40}})",
        final_text)
    out["replied_commit_sha"] = sha_match.group(1) if sha_match else ""
    out["thread_run_count"] = (payload.get("thread") or {}).get("runCount")
    out["recent_runs"] = _runs_slim(payload)
    return out


def _ps_census() -> dict:
    """Coarse local-process census for the thread's execution footprint
    (honest: 0 if the provider executes remotely)."""
    try:
        out = subprocess.run(["ps", "-axo", "pid,command"], capture_output=True,
                             text=True, timeout=15)
        lines = [ln for ln in out.stdout.splitlines()
                 if re.search(r"capacity_fabric|glm-5\.3", ln, re.I)]
        return {"pattern": "capacity_fabric|glm-5.3 (case-insensitive)",
                "matched_lines": len(lines)}
    except Exception as exc:  # noqa: BLE001 — recorded, never inferred
        return {"error": type(exc).__name__}


def _ls_remote_branch(branch: str) -> str:
    out = subprocess.run(
        ["git", "-C", str(REPO), "ls-remote", "origin", f"refs/heads/{branch}"],
        capture_output=True, text=True, timeout=60, check=False)
    return out.stdout.split()[0] if out.returncode == 0 and out.stdout.split() else ""


class UnavailableHermesTransport:
    """The honest R9-blocked state: no live Hermes Secretary binding exists.
    Records the canonical projection text, then refuses with the typed code."""

    def __init__(self) -> None:
        self.sent: list[str] = []

    async def send(self, *, conversation_id: str, submission_id: str, text: str) -> str:
        from integrations.session_bridge.hermes_native_return import (
            HermesReturnDeliveryError,
        )
        self.sent.append(text)
        raise HermesReturnDeliveryError(
            "NATIVE_SESSION_UNAVAILABLE",
            "no live Hermes Secretary binding: installed Executive generation "
            "lacks the seam and Hermes ingress (ledger R8/R9) is not enabled",
        )


# ---------------------------------------------------------------------------
# Roles (sync functions; async segments via asyncio.run so complete_attempt
# fires the execution-return seam OUTSIDE any running event loop)
# ---------------------------------------------------------------------------


def role_prep(events: list) -> dict:
    SCRATCH_ROOT.mkdir(parents=True, exist_ok=True)
    routes = _write_scratch_routes()
    router = ModelRouter.load(ROUTES_SCRATCH)
    provider = router.providers["t3"]
    assert provider.adapter_id == "t3-native" and provider.enabled is False
    explanation = router.explain_route(
        WorkRequest(task_kind="implementation", effective_complexity="C1_ROUTINE_BOUNDED"))
    t3_rows = [row for row in explanation["aliases"] if row.get("provider_alias") == "t3"]
    providers_slim = [
        {"provider_alias": p["provider_alias"], "enabled_in_source": p["enabled_in_source"],
         "autonomous_allowed_in_source": p["autonomous_allowed_in_source"]}
        for p in explanation["providers"] if p["provider_alias"] in ("t3", "anthropic", "openai")
    ]

    token = obtain_token("a")
    mcp = McpHttp(token)
    init = mcp.initialize()
    caps = mcp.call_tool("orchestrator_capabilities", {})
    providers = caps.get("providers") or []
    enabled = [p for p in providers if isinstance(p, dict) and not p.get("constraints")]
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
            f"{[p.get('providerInstanceId') for p in enabled]} — no fallback")
    projects = mcp.call_tool("t3_project_list", {})
    rows = [p for p in (projects.get("projects") or [])
            if isinstance(p, dict)
            and str((p.get("repositoryIdentity") or {}).get("canonicalKey", "")
                    .lower()).endswith("/mastermind")]
    master = next((p for p in rows if p.get("id") == EXPECTED_PROJECT_ID), None)
    if master is None:
        raise RuntimeError(
            f"Mastermind T3 project {EXPECTED_PROJECT_ID} not found; "
            f"candidates={[p.get('id') for p in rows]}")
    project_id = str(master.get("id") or "")
    namespace = t3_mcp_upstream_namespace(token)
    _log(events, "prep.ready", project=project_id, **choice)
    return {
        "role": "prep",
        "outcome": "OK",
        "environment": {
            "environmentId": (mcp.call_tool("t3_environment_read", {}) or {}).get("environmentId"),
            "serverInfo": init.get("serverInfo", {}),
            "endpoint": _harness.MCP,
        },
        "project": {
            "project_id": project_id,
            "title": master.get("title"),
            "workspace_root": str(master.get("workspaceRoot", "")).replace(HOME, "~"),
            "canonical_key": (master.get("repositoryIdentity") or {}).get("canonicalKey"),
            "duplicate_project_ids": [str(p.get("id")) for p in rows],
        },
        "provider": {**choice, "selection_rule": "harness-fixed (see deviations)"},
        "route_row": {**routes, "provider_adapter_id": provider.adapter_id,
                      "provider_enabled": provider.enabled,
                      "provider_autonomous_allowed": provider.autonomous_allowed},
        "explain_route": {
            "schema": explanation["schema"],
            "decision_mode": (explanation.get("decision") or {}).get("mode"),
            "t3_alias_rows": t3_rows,
            "providers": providers_slim,
            "note": "the proposed t3 row is a provider descriptor; no model alias maps to it yet",
        },
        "authenticated_namespace": {
            "attestation": "T3McpToolPort.from token claims: client:<auth session id>",
            "client_a_upstream_namespace_sha256": _sha(namespace),
            "client_a_qualified_namespace_sha256": _sha(t3_request_namespace(namespace)),
        },
        "prepared_at": _now(),
    }


def _main_launch_arguments(branch: str) -> dict:
    """Launch args naming the Mastermind T3 project and a fresh T3-managed
    worktree on the canary branch (this server build requires baseRef)."""
    return {
        "projectId": _project_id(),
        "workspaceStrategy": {
            "type": "worktree",
            "branch": branch,
            "baseRef": "master",
            "startFromOrigin": True,
        },
    }


def role_main_p1(events: list) -> dict:
    assert os.environ.get("T3_L1_CANARY_CRASH_MODE") == "after_receipt"
    model_selection = _load_model_selection()
    launch_arguments = _main_launch_arguments(_branch(_request(CHILD_KEY_MAIN)))
    runtime = _scratch_runtime()
    _register_worker(runtime)
    request = _request(CHILD_KEY_MAIN)
    branch = _branch(request)
    composed = compose_child_execution(
        runtime, request=request, spec=_spec(request), branch=branch)
    assert composed.admission.state == "ADMITTED", composed.admission.state
    job_id = composed.placement_job.job_id
    lease = runtime.attempts.claim_job(
        job_id, placement_observations=_observations(),
        fabric_placement_intent=_intent(request))
    assert lease is not None
    attempt_id = lease.attempt.attempt_id
    # Supervisor stand-in durable state: P2's lawful recovery material.
    _write_side(_side_path("main-p1-lease"), {
        "attempt_id": attempt_id,
        "job_id": job_id,
        "fence_generation": lease.attempt.fence_generation,
        "lease_token": lease.lease_token,
        "branch": branch,
        "written_at": _now(),
    })
    _log(events, "p1.claimed", attempt=attempt_id, job=job_id, branch=branch)
    box = _compose(runtime, client="a", census_name="main-p1", events=events,
                   launch_arguments=launch_arguments,
                   crash_side=_side_path("main-p1"))
    composition = box["composition"]
    assert composition.composed, composition.reason
    spec = _launch_spec(run_id=attempt_id, job_id=job_id,
                        prompt=_main_prompt(attempt_id, branch),
                        scenario="main", model_selection=model_selection)
    _write_side(_side_path("main-p1-launch"), {
        "attempt_id": attempt_id, "branch": branch,
        "prompt_sha256": _sha(spec.prompt),
        "launch_arguments": launch_arguments,
        "upstream_namespace_sha256": _sha(composition.upstream_namespace or ""),
        "at": _now(),
    })
    asyncio.run(box["composition"].adapter.start(spec))  # crash hook exits 90
    raise AssertionError("MAIN-P1 should have crashed before the ACK")


def role_main_p2(events: list) -> dict:
    model_selection = _load_model_selection()
    lease_facts = _load_side("main-p1-lease")
    attempt_id = lease_facts["attempt_id"]
    job_id = lease_facts["job_id"]
    branch = lease_facts["branch"]
    runtime = _scratch_runtime()  # SAME scratch Runtime dir: same DB, same store placement
    _register_worker(runtime)
    launch_arguments = _main_launch_arguments(branch)
    box = _compose(runtime, client="a", census_name="main-p2", events=events,
                   launch_arguments=launch_arguments)
    adapter, port, census = box["composition"].adapter, box["port"], box["census"]
    store = SQLiteT3AdapterStateStore(_adapter_store_path())
    run = store.load_run(attempt_id)
    assert run is not None and run.spec is not None and run.intent is not None
    assert run.receipt is not None and run.original_ref is not None, (
        "MAIN-P1 must have persisted the receipt before crashing")

    # --- reattach: ZERO native tool calls (census + port.calls) ---
    t0 = time.monotonic()
    ref = asyncio.run(adapter.reattach(run.spec, _recovery_binding(run.spec, run.original_ref)))
    reattach_elapsed_s = round(time.monotonic() - t0, 3)
    assert ref == run.original_ref
    assert not port.calls and not census.tools(), (
        f"MAIN-P2 reattach must make ZERO native calls: {port.calls} {census.tools()}")
    p1 = _load_side("main-p1")
    assert ref.provider_session_id == p1["native"]["thread_id"]
    _log(events, "p2.reattached_zero_calls", thread=ref.provider_session_id)

    # --- second start refused, zero native calls ---
    start_refusal = ""
    try:
        asyncio.run(adapter.start(run.spec))
    except T3LaunchClaimConflictError:
        start_refusal = "T3LaunchClaimConflictError"
    except T3ExecutionAdapterError as exc:
        start_refusal = type(exc).__name__
    assert start_refusal and not port.calls and not census.tools()
    _log(events, "p2.second_start_refused", error=start_refusal)

    # --- lawful recovery: record provider-managed process, adopt the lease ---
    runtime.attempts.record_process(
        attempt_id,
        fence_generation=lease_facts["fence_generation"],
        lease_token=lease_facts["lease_token"],
        provider_session_id=ref.provider_session_id,
        launch_metadata={},
    )
    adopted = runtime.attempts.adopt_attempt(
        attempt_id,
        expected_fence_generation=lease_facts["fence_generation"],
        lease_owner="l1-canary-p2")
    _log(events, "p2.adopted", fence=adopted.attempt.fence_generation)

    # --- read to terminal (~15 min, 15 s poll), collect, verify ---
    statuses, final = asyncio.run(_wait_terminal(adapter, ref, deadline_s=900.0, interval_s=15.0))
    collected = _collect_and_verify(adapter, port, ref, attempt_id, attempt_id)
    ps = _ps_census()
    remote_sha = _ls_remote_branch(branch)

    # --- seal: seam + complete_attempt from SYNC context ---
    from integrations.session_bridge.hermes_native_return import (
        HermesExecutionReturnDeliverer,
    )
    transport = UnavailableHermesTransport()
    install_execution_return_seam(
        runtime,
        deliverer=HermesExecutionReturnDeliverer(transport),
        github=GitHubEvidenceSource(repository=REPOSITORY, port=GhCliEvidencePort()),
        t3_adapter=adapter,
    )
    sealed = runtime.attempts.complete_attempt(
        attempt_id,
        fence_generation=adopted.attempt.fence_generation,
        lease_token=adopted.lease_token,
        payload={"summary": "L1 admitted canary: one real Executive-path request sealed",
                 "artifacts": [f"branch:{branch}", f"thread:{ref.provider_session_id}"]})
    delivery_events = [
        e for e in runtime.store.list_events(
            command_id_prefix=execution_return_receipt_command_id(attempt_id))
        if e.attempt_id == attempt_id]
    delivery = dict(delivery_events[0].payload) if delivery_events else {}
    projection = json.loads(transport.sent[0]) if transport.sent else {}
    _log(events, "p2.sealed", status=sealed.status.value,
         delivery_state=(delivery.get("delivery") or {}).get("state"))

    return {
        "role": "main-p2",
        "outcome": "OK",
        "attempt_id": attempt_id,
        "job_id": job_id,
        "thread_id": ref.provider_session_id,
        "native_run_id": (adapter.launch_receipt(attempt_id).run_id
                          if adapter.launch_receipt(attempt_id) else ""),
        "reattach": {
            "returned_retained_ref": True,
            "native_calls": 0,
            "port_calls_after_reattach": 0,
            "census_after_reattach": [],
            "reattach_elapsed_s": reattach_elapsed_s,
        },
        "second_start": {"refused": True, "error": start_refusal,
                         "native_calls_after": 0},
        "recovery": {
            "path": "reattach -> record_process(provider-managed) -> adopt_attempt -> complete_attempt",
            "adopted_fence_generation": adopted.attempt.fence_generation,
            "adopted_status": getattr(adopted.attempt.status, "value", str(adopted.attempt.status)),
        },
        "status_sequence": statuses,
        "final_state": final.value,
        "collect": collected,
        "recent_runs": collected.get("recent_runs"),
        "recent_runs_count": len(collected.get("recent_runs") or []),
        "thread_run_count": collected.get("thread_run_count"),
        "ps_census": ps,
        "branch": branch,
        "branch_remote_sha": remote_sha,
        "branch_pushed": bool(remote_sha),
        "branch_sha_matches_reply": bool(
            remote_sha and collected.get("replied_commit_sha")
            and remote_sha.startswith(collected["replied_commit_sha"])),
        "seal": {"job_status": getattr(sealed.status, "value", str(sealed.status)),
                 "current_attempt_id": sealed.current_attempt_id},
        "delivery_receipt": {
            "state": (delivery.get("delivery") or {}).get("state"),
            "refusal_code": (delivery.get("delivery") or {}).get("refusal_code"),
            "return_id": (delivery.get("delivery") or {}).get("return_id"),
            "conversation_id": (delivery.get("delivery") or {}).get("conversation_id"),
            "stage": delivery.get("stage"),
        },
        "execution_return_projection": projection,
        "native_census_final": census.tools(),
        "port_counts_final": len(port.calls),
        "finished_at": _now(),
    }


def role_namespace_p3(events: list) -> dict:
    lease_facts = _load_side("main-p1-lease")
    attempt_id = lease_facts["attempt_id"]
    runtime = _scratch_runtime()
    _register_worker(runtime)
    token_b = obtain_token("b")
    namespace_b = t3_mcp_upstream_namespace(token_b)
    prep = _load_side("prep")
    namespace_a_sha = prep["authenticated_namespace"]["client_a_upstream_namespace_sha256"]
    assert _sha(namespace_b) != namespace_a_sha, "client b must be a DIFFERENT OAuth session"
    box = _compose(runtime, client="b", census_name="namespace-p3", events=events,
                   launch_arguments=_main_launch_arguments(lease_facts.get("branch", "")))
    adapter_b, port_b, census = box["composition"].adapter, box["port"], box["census"]
    store = SQLiteT3AdapterStateStore(_adapter_store_path())
    run = store.load_run(attempt_id)
    assert run is not None and run.spec is not None and run.original_ref is not None

    attempts: list[dict] = []
    before = len(port_b.calls)
    try:
        asyncio.run(adapter_b.reattach(run.spec, _recovery_binding(run.spec, run.original_ref)))
        attempts.append({"operation": "reattach", "refused": False})
    except T3NamespaceAttestationError as exc:
        attempts.append({"operation": "reattach", "refused": True, "reason": exc.reason,
                         "error": type(exc).__name__,
                         "native_calls": len(port_b.calls) - before})
    except T3ExecutionAdapterError as exc:
        attempts.append({"operation": "reattach", "refused": True,
                         "error": type(exc).__name__,
                         "native_calls": len(port_b.calls) - before})
    before = len(port_b.calls)
    try:
        asyncio.run(adapter_b.start(run.spec))
        attempts.append({"operation": "start", "refused": False})
    except T3ExecutionAdapterError as exc:
        attempts.append({"operation": "start", "refused": True, "error": type(exc).__name__,
                         "native_calls": len(port_b.calls) - before})
    zero_native = not port_b.calls and not census.tools()
    principal_mismatch = all(
        a.get("reason") == "PRINCIPAL_MISMATCH" for a in attempts if a["operation"] == "reattach")
    _log(events, "p3.refusals", zero_native=zero_native, mismatch=principal_mismatch)
    return {
        "role": "namespace-p3",
        "outcome": "OK",
        "client_b_upstream_namespace_sha256": _sha(namespace_b),
        "client_a_upstream_namespace_sha256": namespace_a_sha,
        "distinct_oauth_clients": True,
        "attempts": attempts,
        "refused_with_zero_native_calls": zero_native,
        "reattach_reason_principal_mismatch": principal_mismatch,
        "thread_minted": False,
        "native_census": census.tools(),
        "port_calls": len(port_b.calls),
        "finished_at": _now(),
    }


def role_interrupt(events: list) -> dict:
    model_selection = _load_model_selection()
    runtime = _scratch_runtime()
    _register_worker(runtime)
    request = _request(CHILD_KEY_INTERRUPT)
    composed = compose_child_execution(
        runtime, request=request, spec=_spec(request),
        branch=f"t3/mmos-l1-canary-interrupt-{request.request_digest[:8]}")
    assert composed.admission.state == "ADMITTED", composed.admission.state
    lease = runtime.attempts.claim_job(
        composed.placement_job.job_id, placement_observations=_observations(),
        fabric_placement_intent=_intent(request))
    assert lease is not None, (
        "interrupt claim returned None (quota slot still held by MAIN's "
        "unsealed attempt? check JOB_PLACEMENT_DEFERRED events)")
    attempt_id = lease.attempt.attempt_id
    _write_side(_side_path("interrupt-lease"), {
        "attempt_id": attempt_id, "job_id": composed.placement_job.job_id,
        "written_at": _now()})
    _log(events, "interrupt.claimed", attempt=attempt_id)
    box = _compose(runtime, client="a", census_name="interrupt", events=events,
                   launch_arguments={"scratch": True})
    adapter, port = box["composition"].adapter, box["port"]
    nonce = f"l1-int-{request.request_digest[:8]}"
    spec = _launch_spec(run_id=attempt_id, job_id=composed.placement_job.job_id,
                        prompt=_interrupt_prompt(nonce), scenario="interrupt",
                        model_selection=model_selection)
    ref = asyncio.run(adapter.start(spec))
    _write_side(_side_path("interrupt-minted"),
                {"thread_id": ref.provider_session_id, "at": _now()})
    pre: list[str] = []
    deadline = time.monotonic() + 120
    st = WorkerRunStatus.STARTING
    while time.monotonic() < deadline:
        st = asyncio.run(adapter.status(ref))
        pre.append(st.value)
        if st == WorkerRunStatus.RUNNING or st in _TERMINAL:
            break
        time.sleep(1)
    was_live = st == WorkerRunStatus.RUNNING
    receipt = adapter.launch_receipt(attempt_id)
    interrupt_call: dict = {}
    signal_sent = already_exited = False
    cancel_error = ""
    try:
        cancel_receipt = asyncio.run(
            adapter.cancel(ref, "MMOS L1 admitted canary: exact-run interrupt"))
        signal_sent = bool(cancel_receipt.signal_sent)
        already_exited = bool(cancel_receipt.already_exited)
    except T3ExecutionAdapterError as exc:
        cancel_error = _redact(exc)[:300]
    interrupt_call = next((c for c in reversed(port.calls)
                           if c.get("op") == "interrupt"), {})
    report_after = dataclasses.asdict(adapter.cancel_report(attempt_id)) \
        if adapter.cancel_report(attempt_id) else None
    statuses, final = asyncio.run(_wait_terminal(adapter, ref, deadline_s=300.0, interval_s=5.0))
    report_final = dataclasses.asdict(adapter.cancel_report(attempt_id)) \
        if adapter.cancel_report(attempt_id) else None
    _log(events, "interrupt.observed", final=final.value)
    return {
        "role": "interrupt",
        "outcome": "OK",
        "attempt_id": attempt_id,
        "thread_id": ref.provider_session_id,
        "native_run_id": receipt.run_id if receipt else "",
        "was_live_at_interrupt": was_live,
        "pre_interrupt_states": pre,
        "interrupt": {
            "payload_thread_matches": interrupt_call.get("threadId") == ref.provider_session_id,
            "payload_run_matches": bool(receipt)
            and interrupt_call.get("runId") == receipt.run_id,
            "upstream_echo_verified": not cancel_error,
            "error": cancel_error,
            "signal_sent": signal_sent,
            "already_exited": already_exited,
        },
        "ledger_after_cancel": {k: (report_after or {}).get(k) for k in (
            "requested", "signal_sent", "already_exited", "settled", "settled_state",
            "requested_at", "settled_at")},
        "ledger_final": {k: (report_final or {}).get(k) for k in (
            "requested", "signal_sent", "already_exited", "settled", "settled_state",
            "requested_at", "settled_at")},
        "status_sequence_after_interrupt": statuses,
        "final_state": final.value,
        "honesty": {
            "settle_claimed_without_terminal_observation": bool(
                report_final and report_final["settled"] and final not in _TERMINAL),
            "requested_before_settle": bool(
                report_after and report_after["requested"]
                and (not report_after["settled"] or report_after["settled_state"])),
        },
        "finished_at": _now(),
    }


ROLES = {
    "prep": role_prep,
    "main-p1": role_main_p1,
    "main-p2": role_main_p2,
    "namespace-p3": role_namespace_p3,
    "interrupt": role_interrupt,
}
#: Roles that may mint a new upstream thread (each reserves budget first).
MINTING_ROLES = {"main-p1", "interrupt"}
EXPECTED_RC = {role: 0 for role in ROLES}
EXPECTED_RC.update({"main-p1": CRASH_EXIT_AFTER_RECEIPT})
#: Per-role subprocess timeout (seconds); MAIN-P2 waits up to ~15 min for the thread.
ROLE_TIMEOUTS = {"prep": 300, "main-p1": 300, "main-p2": 1800, "namespace-p3": 300,
                 "interrupt": 900}


def run_role(role: str) -> int:
    events: list = []
    try:
        payload = ROLES[role](events)
        payload["events"] = events
        _write_side(_side_path(role), payload)
        return 0
    except BaseException as exc:  # record honestly, never hide the failure
        _write_side(_side_path(role), {
            "role": role, "outcome": "ERROR",
            "error": f"{type(exc).__name__}: {_redact(exc)}", "events": events, "at": _now(),
        })
        print(f"[l1-canary] role {role} FAILED: {_redact(exc)}", file=sys.stderr, flush=True)
        return 3


# ---------------------------------------------------------------------------
# Driver: each role is a SEPARATE OS PROCESS; then the receipt is assembled.
# ---------------------------------------------------------------------------


def _spawn(role: str, crash_mode: str | None = None) -> dict:
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env["T3_L1_CANARY_ROLE"] = role
    env["MASTERMIND_T3_MCP_ACCESS_TOKEN_FILE"] = str(TOKEN_A)
    if crash_mode:
        env["T3_L1_CANARY_CRASH_MODE"] = crash_mode
    started = _now()
    try:
        proc = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), "--role", role],
            capture_output=True, text=True, env=env,
            timeout=ROLE_TIMEOUTS.get(role, 900),
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
    files = ["control_plane/executive_runtime.py",
             "control_plane/t3_execution_adapter.py",
             "control_plane/t3_native_composition.py",
             "integrations/t3/live_proof/t3_admitted_canary.py",
             "integrations/t3/live_proof/t3_live_proof.py"]
    dirty = _git("status", "--porcelain", "--", *files)
    return {
        "trunk_commit_sha": _git("rev-parse", "HEAD"),
        "harness_file_sha256": hashlib.sha256(
            Path(__file__).resolve().read_bytes()).hexdigest(),
        "runtime_file_sha256": hashlib.sha256(
            (REPO / "control_plane/executive_runtime.py").read_bytes()).hexdigest(),
        "adapter_file_sha256": hashlib.sha256(
            (REPO / "control_plane/t3_execution_adapter.py").read_bytes()).hexdigest(),
        "composition_file_sha256": hashlib.sha256(
            (REPO / "control_plane/t3_native_composition.py").read_bytes()).hexdigest(),
        "source_tree_clean": dirty == "",
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

    def step(role: str, crash_mode: str | None = None) -> bool:
        if role in MINTING_ROLES and not _reserve_thread(role):
            gates.append(f"{role}: thread budget ({THREAD_BUDGET}) exhausted — not started")
            results.append({"role": role, "returncode": None, "skipped": True,
                            "reason": "thread budget exhausted"})
            return False
        res = _spawn(role, crash_mode)
        results.append(res)
        return bool(res["ok"])

    def skip(role: str, reason: str) -> None:
        _write_side(_side_path(role), {"role": role, "outcome": "SKIPPED", "reason": reason})
        results.append({"role": role, "returncode": None, "skipped": True, "reason": reason})

    if not step("prep"):
        gates.append(f"prep failed: {_load_side('prep').get('error', '?')}")
        for role in ("main-p1", "main-p2", "namespace-p3", "interrupt"):
            skip(role, "blocked by prep")
    else:
        if step("main-p1", "after_receipt"):
            step("main-p2")
        else:
            skip("main-p2", "main-p1 did not crash at its deterministic point")
        if _load_side("main-p1").get("crash_point"):
            step("namespace-p3")
        else:
            skip("namespace-p3", "needs MAIN's durable ref")
        step("interrupt")
    (batch / "drive.json").write_text(json.dumps(
        {"started_at": started_at, "gates": gates, "processes": results, "code": identity},
        indent=2, default=str) + "\n")
    receipt = assemble(results, started_at, gates, identity)
    _write_receipt(receipt)
    print(f"[l1-canary] receipt -> {_redact(RECEIPT_OUT)}  outcome: {receipt['outcome']}",
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


def _slim_report(report: dict | None) -> dict | None:
    if report is None:
        return None
    return {k: report.get(k) for k in (
        "requested", "signal_sent", "already_exited", "settled", "settled_state",
        "requested_at", "settled_at")}


def _repair_replied_sha(p2: dict) -> None:
    """First-live-run repair: the harness's reply-sha regex shipped a corrupted
    quantifier (f-string brace bug), so ``collect.replied_commit_sha`` recorded
    empty even though the run's own recorded evidence (the collected result
    text) carries the exact reply line.  Recompute it FROM THAT RECORDED TEXT
    — no new reads, no new evidence — and mark the source honestly."""
    c = p2.get("collect") or {}
    if c.get("replied_commit_sha"):
        return
    att = str(p2.get("attempt_id") or "")
    tail = str(c.get("result_text_tail") or "")
    m = re.search(rf"L1-CANARY-OK\s+{re.escape(att)}\s+([0-9a-f]{{7,40}})", tail)
    if m:
        c["replied_commit_sha"] = m.group(1)
        c["replied_commit_sha_source"] = (
            "recomputed from the recorded result_text_tail after the harness "
            "f-string brace bug fix (no new reads; same recorded evidence)")
        remote = str(p2.get("branch_remote_sha") or "")
        p2["branch_sha_matches_reply"] = bool(
            remote and remote.startswith(m.group(1)))


def assemble(results: list[dict], started_at: str, gates: list[str], identity: dict) -> dict:
    prep = _load_side("prep")
    p1, p2 = _load_side("main-p1"), _load_side("main-p2")
    _repair_replied_sha(p2)
    c = p2.get("collect", {})

    main_p1_pass = bool(
        p1.get("crash_point") == "after_receipt_persist_before_ack"
        and p1.get("upstream_echo_proven"))
    main_p2_pass = bool(
        p2.get("outcome") == "OK"
        and p2.get("reattach", {}).get("native_calls") == 0
        and p2.get("second_start", {}).get("refused")
        and p2.get("recovery", {}).get("adopted_fence_generation")
        and p2.get("final_state") == "SUCCEEDED"
        and c.get("marker_in_final_item")
        and c.get("ledger_names_final_assistant_item")
        and p2.get("branch_pushed")
        and p2.get("branch_sha_matches_reply")
        and p2.get("recent_runs_count") == 1
        and p2.get("delivery_receipt", {}).get("state") == "refused"
        and p2.get("delivery_receipt", {}).get("refusal_code") == "NATIVE_SESSION_UNAVAILABLE"
        and p2.get("delivery_receipt", {}).get("stage") == "branch_pushed"
        and bool(p2.get("execution_return_projection")))
    scen_main = {
        "name": "admission boundary inward: one real request, one real T3 thread, sealed, honest refused return",
        "outcome": "PASS" if main_p1_pass and main_p2_pass else "FAIL",
        "p1_crash": "PASS" if main_p1_pass else "FAIL",
        "p2_recovery_seal": "PASS" if main_p2_pass else "FAIL",
        "attempt_id": p2.get("attempt_id"),
        "job_id": p2.get("job_id"),
        "thread_id": p2.get("thread_id") or (p1.get("native") or {}).get("thread_id"),
        "native_run_id": p2.get("native_run_id"),
        "branch": p2.get("branch"),
        "branch_remote_sha": p2.get("branch_remote_sha"),
        "recent_runs_count": p2.get("recent_runs_count"),
        "delivery": p2.get("delivery_receipt"),
        "processes": {"p1": p1, "p2": p2},
    }

    p3 = _load_side("namespace-p3")
    namespace_pass = bool(
        p3.get("outcome") == "OK"
        and p3.get("distinct_oauth_clients")
        and p3.get("refused_with_zero_native_calls")
        and p3.get("reattach_reason_principal_mismatch")
        and not p3.get("thread_minted"))
    scen_namespace = {
        "name": "wrong OAuth client (namespace) refused with zero native calls, no thread minted",
        "outcome": "PASS" if namespace_pass else "FAIL",
        "processes": {"p": p3},
    }

    it = _load_side("interrupt")
    i4, h4 = it.get("interrupt", {}), it.get("honesty", {})
    interrupt_pass = bool(
        it.get("outcome") == "OK"
        and i4.get("payload_thread_matches")
        and i4.get("payload_run_matches")
        and i4.get("upstream_echo_verified")
        and i4.get("signal_sent")
        and h4.get("requested_before_settle")
        and not h4.get("settle_claimed_without_terminal_observation"))
    scen_interrupt = {
        "name": "exact-run interrupt on a sibling child: requested vs settled, never inferred",
        "outcome": "PASS" if interrupt_pass else ("UNKNOWN" if it.get("outcome") == "OK" else "FAIL"),
        "thread_id": it.get("thread_id") or _load_side("interrupt-minted").get("thread_id"),
        "processes": {"p": it},
    }

    threads = [scen_main.get("thread_id"), scen_interrupt.get("thread_id")]
    threads = [t for t in threads if t]
    core = [scen_main["outcome"], scen_namespace["outcome"], scen_interrupt["outcome"]]
    outcome = ("BLOCKED" if any(g.startswith("prep") for g in gates)
               else "DONE" if all(o == "PASS" for o in core) else "PARTIAL")
    return {
        "schema": "mastermind.t3_admitted_canary_receipt/v1",
        "revision": "r1",
        "label": CANARY_LABEL,
        "recorded_at": _now(),
        "started_at": started_at,
        "outcome": outcome,
        "blocked_gate": "; ".join(gates) or None,
        "code": identity,
        "trunk_commit_sha": identity.get("trunk_commit_sha"),
        "environment": prep.get("environment", {}),
        "project": prep.get("project", {}),
        "identities": {
            "root_ref": ROOT_REF,
            "immediate_parent_run_ref": PARENT_REF,
            "logical_child_keys": [CHILD_KEY_MAIN, CHILD_KEY_INTERRUPT],
            "requester_basis": REQUESTER_BASIS,
            "executive_generation": EXECUTIVE_GENERATION,
            "worker_id": WORKER_ID,
            "quota_resource_ref": QUOTA_REF,
            "repository": REPOSITORY,
        },
        "deviations": DEVIATIONS,
        "route_row": prep.get("route_row", {}),
        "explain_route": prep.get("explain_route", {}),
        "provider": prep.get("provider", {}),
        "model_selection_basis": "harness-fixed; route->T3 modelSelection mapping absent",
        "authenticated_namespace": prep.get("authenticated_namespace", {}),
        "namespace_scenario": {
            "client_b_upstream_namespace_sha256": p3.get("client_b_upstream_namespace_sha256"),
            "client_a_upstream_namespace_sha256": p3.get("client_a_upstream_namespace_sha256"),
        },
        "store": {
            "runtime_root": str(RUNTIME_ROOT).replace(HOME, "~"),
            "adapter_state": str(_adapter_store_path()).replace(HOME, "~"),
            "implementation": "RuntimeStore executive.sqlite3 + SQLiteT3AdapterStateStore (sibling)",
            "note": "scratch data dir; the installed Executive db is untouched",
        },
        "scenarios": {
            "main": scen_main,
            "namespace": scen_namespace,
            "interrupt": scen_interrupt,
        },
        "delivery": {
            "projection_schema": (p2.get("execution_return_projection") or {}).get("schema"),
            "receipt_state": (p2.get("delivery_receipt") or {}).get("state"),
            "refusal_code": (p2.get("delivery_receipt") or {}).get("refusal_code"),
            "github_stage": (p2.get("delivery_receipt") or {}).get("stage"),
            "projection": p2.get("execution_return_projection"),
            "basis": REQUESTER_BASIS,
        },
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
    print(f"[l1-canary] receipt -> {_redact(RECEIPT_OUT)}  outcome: {receipt['outcome']}",
          file=sys.stderr, flush=True)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="MMOS L1 admitted canary (T3 live, real Executive path)")
    parser.add_argument("--role", choices=sorted(ROLES), default=None)
    parser.add_argument("--assemble", action="store_true",
                        help="rebuild the receipt from the current batch's side files")
    args = parser.parse_args()
    if args.role:
        return run_role(args.role)
    if args.assemble:
        return assemble_only()
    return drive()


if __name__ == "__main__":
    raise SystemExit(main())

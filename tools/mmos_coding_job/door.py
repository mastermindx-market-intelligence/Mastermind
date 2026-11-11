#!/usr/bin/env python3
"""T4b dev Executive door — joins one Paperclip task to one governed coding job.

One process, on a SCRATCH root only, composes existing pieces:

- the real ``ExecutiveControlService`` with the CEO-ingress Unix socket and
  the selected-child App binding (the ingress tests' composition), holding
  the host-frozen ``child_request_material`` — one envelope per dev
  Paperclip issue, frozen at intake (registration, never admission);
- the real L4 ``LocalOperatorListener`` on ``local-operator.sock`` (kernel
  peer uid, no bearer, no TCP) serving the carrier's two coding-job routes;
- the executor: for each admitted job, the L1 canary's engine chain on the
  DEV T3 server — placement composition, fenced claim, the real
  ``compose_t3_native_adapter``, ONE native launch, collect, seal through
  the execution-return seam with the ``paperclip_task`` transport
  registered, so the verified result lands on the task it came from.

Paperclip stays passive (plan V3 §8a): the wake carrier's single admit call
names a COMMAND; the envelope never travels through the caller.  The
per-run Paperclip token never enters this process.  Production Executive,
installed Paperclip (3100), the Chairman's T3 app (3773/3774) and Hermes are
never read for state and never written.

Run: ``python3 tools/mmos_coding_job/door.py --config door.json serve``
"""
from __future__ import annotations

import argparse
import asyncio
import dataclasses
import datetime as dt
import json
import os
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from control_plane.child_execution_contracts import ChildExecutionRequest  # noqa: E402
from control_plane.child_request_execution_composition import (  # noqa: E402
    compose_child_execution,
)
from control_plane.executive_runtime import Runtime  # noqa: E402
from control_plane.executive_service import (  # noqa: E402
    SELECTED_CHILD_FRAME_SCHEMA,
    CeoIngressAppBinding,
    ExecutiveControlService,
    ServiceConfig,
)
from control_plane.execution_return_wiring import (  # noqa: E402
    GitHubEvidenceSource,
    execution_return_receipt_command_id,
    install_execution_return_seam,
)
from control_plane.result_delivery import ResultDeliveryRegistry  # noqa: E402
from control_plane.github_attempt_evidence_reader import (  # noqa: E402
    GhCliEvidencePort,
)
from integrations.hermes_delegate.executive import (  # noqa: E402
    ExecutiveChildSelection,
    ExecutiveSelectedChild,
    ExecutiveSelectedChildTarget,
)
from tools.mmos_coding_job.envelope import (  # noqa: E402
    CARRIER_KIND,
    DEFAULT_JOB_KEY,
    build_task_request,
    task_command,
)

WORK_REF = "WS:EXECUTIVE-CAPACITY-FABRIC"
HOST_ID = "host-t4b-door"
WORKER_ID = "worker-t4b-door"
# provider:account shape (the placement authority rejects any ref without a
# colon as "not unique provider:account refs"); the canary uses "glm:l1-canary"
QUOTA_REF = "t3:t4b-door"
REGISTRY_REVISION = "rev-t4b-door-1"
THREAD_BUDGET = 2
LEASE_SECONDS = 900
REPOSITORY = "mastermindx-market-intelligence/Mastermind"
# F3/F13 (R4b review): the attempt statuses after which the door owes
# bookkeeping only — never an adoption (F3) — and after which a held
# launch-uncertain thread slot returns (F13).
TERMINAL_ATTEMPT_STATUSES = frozenset(
    {"COMPLETED", "FAILED", "LOST", "CANCELLED"})


def _log(message: str) -> None:
    print(f"[t4b-door] {message}", flush=True)  # secrets never logged


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def loopback_only(url: str, what: str) -> str:
    """The dev boundary law: only a loopback http base, ever.

    F9 (R4b review): the URL is PARSED, never string-prefix-matched —
    ``http://127.0.0.1:80@example.com`` has userinfo and the real host
    ``example.com``, and must refuse.  No userinfo, no query, no fragment,
    no path (a bare base), http only.
    """
    parts = urllib.parse.urlsplit(url)
    if parts.scheme != "http":
        raise ValueError(f"{what} must be an http url, got {url!r}")
    if parts.username is not None or parts.password is not None:
        raise ValueError(f"{what} must carry no userinfo, got {url!r}")
    if parts.query or parts.fragment:
        raise ValueError(f"{what} must be a bare base url, got {url!r}")
    host = (parts.hostname or "").lower()
    if host not in ("127.0.0.1", "localhost", "::1"):
        raise ValueError(f"{what} must be a loopback http url, got {url!r}")
    if parts.path not in ("", "/"):
        raise ValueError(f"{what} must be a bare base url, got {url!r}")
    return url.rstrip("/")


# The dev T3 server's port range (tools/mmos_dev/t3_dev.sh).  The live T3
# app (3773/3774), the team server (3780) and installed Paperclip (3100)
# are never legal targets for this door.  The pairing helper's CLI leg
# selects its server by T3CODE_HOME/T3CODE_PORT, NOT by the base URL —
# so those must be configured, required, and provably the SAME server as
# the HTTP base, or the CLI would silently mint against the live app.
DEV_T3_PORT_FIRST = 3790
DEV_T3_PORT_LAST = 3810

# F9 (R4b review): reserved neighbour ports that are NEVER a legal
# Paperclip target for this door, even if a config lists them — the
# installed Paperclip (3100, 3179), the live T3 app (3773/3774) and the
# team server (3780).
RESERVED_NEIGHBOUR_PORTS = frozenset({3100, 3179, 3773, 3774, 3780})

DEV_T3_PORT_FIRST = 3790
DEV_T3_PORT_LAST = 3810


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


class DoorConfig:
    """The door's JSON config; every boundary enforced at load."""

    def __init__(self, values: dict):
        self.scratch_root = Path(values["scratch_root"]).expanduser()
        self.paperclip_base = loopback_only(
            values["paperclip_base_url"], "paperclip_base_url")
        # F9 (R4b review): the Paperclip base must match an EXPLICIT
        # host:port allowlist from the config — parsing the URL and
        # comparing (host, port) never accepts a lookalike, and the
        # reserved neighbour ports are refused even when listed.
        allowed = values.get("paperclip_allowed")
        if not isinstance(allowed, list) or not allowed:
            raise ValueError(
                "paperclip_allowed is required: an explicit list of the "
                "legal host:port Paperclip targets for this door")
        allowed_targets: set[tuple[str, int]] = set()
        for item in allowed:
            if type(item) is not str:
                raise ValueError(f"paperclip_allowed entries are strings, "
                                 f"got {item!r}")
            parsed = urllib.parse.urlsplit(f"http://{item.strip()}")
            try:
                port = parsed.port
            except ValueError as exc:
                raise ValueError(f"paperclip_allowed entry is not a "
                                 f"host:port pair: {item!r}") from exc
            if not parsed.hostname or port is None:
                raise ValueError(f"paperclip_allowed entry is not a "
                                 f"host:port pair: {item!r}")
            if port in RESERVED_NEIGHBOUR_PORTS:
                raise ValueError(
                    f"paperclip_allowed names reserved port {port} "
                    f"(installed Paperclip / live T3 app / team server): "
                    "never a legal target for this door")
            allowed_targets.add((parsed.hostname.lower(), port))
        base = urllib.parse.urlsplit(self.paperclip_base)
        if (base.hostname or "").lower() in ("::1",):
            base_target = ("::1", base.port)
        else:
            base_target = ((base.hostname or "").lower(), base.port)
        if base_target not in allowed_targets:
            raise ValueError(
                f"paperclip_base_url target {base_target[0]}:{base_target[1]} "
                "is not in the paperclip_allowed allowlist "
                f"{sorted(allowed_targets)}")
        self.paperclip_company_id = str(values["paperclip_company_id"])
        self.paperclip_headers = dict(values.get("paperclip_headers") or {})
        # F10 (R4b review): the enrolled-teammate roster — the door freezes
        # only issues assigned to one of these agents, and admits only when
        # the task itself shows the request from the assignee.
        self.teammates = frozenset(
            str(agent) for agent in (values.get("teammates") or ()))
        self.repository = str(values.get("repository") or REPOSITORY)
        self.t3_proof_base = loopback_only(
            values["t3"]["proof_base_url"], "t3.proof_base_url")
        # Required, no defaults: without these the pairing helper's CLI leg
        # would fall back to the live T3 app (the recorded incident).
        for field in ("home_dir", "port"):
            if not values["t3"].get(field):
                raise ValueError(
                    f"t3.{field} is required (the dev server pin); "
                    "refusing to run the pairing CLI against a default")
        self.t3_home_dir = str(values["t3"]["home_dir"])
        self.t3_port = int(values["t3"]["port"])
        if not (DEV_T3_PORT_FIRST <= self.t3_port <= DEV_T3_PORT_LAST):
            raise ValueError(
                f"t3.port must be a dev-server port "
                f"({DEV_T3_PORT_FIRST}-{DEV_T3_PORT_LAST}), "
                f"got {self.t3_port}")
        base_port = urllib.parse.urlsplit(self.t3_proof_base).port
        if base_port != self.t3_port:
            raise ValueError(
                "t3.proof_base_url must point at the same dev server as "
                f"t3.port ({self.t3_port}), got base port {base_port}")
        self.t3_token_path = Path(values["t3"]["token_path"]).expanduser()
        self.t3_token_label = str(values["t3"].get("token_label")
                                  or "t4b-door-worker")
        self.t3_project_id = str(values["t3"]["project_id"])
        self.t3_model_selection = str(values["t3"]["model_selection"])
        self.register_transport = bool(values.get("register_transport", True))
        self.crash_mode = values.get("crash_mode") or None
        self.intake_poll_seconds = float(values.get("intake_poll_seconds", 2.0))
        # F12 (R4b review): a WAIT is retried by the door itself once this
        # many seconds have passed since the last ask — the same command,
        # so still one admission (the engine's command-id law arbitrates).
        self.wait_retry_seconds = float(values.get("wait_retry_seconds", 30.0))
        # F15 (R4b review) + attack F8: the composed supervisor's
        # reconcile cadence — run at start, then at least this often.
        self.reconcile_interval_seconds = float(
            values.get("reconcile_interval_seconds", 30.0))
        # The claim/adoption lease window the door's Runtime instances use
        # (scenarios shorten it to prove the door-down-longer-than-lease
        # recovery).
        self.lease_seconds = int(values.get("lease_seconds", LEASE_SECONDS))
        self.ready_limit = values.get("child_root_ready_limit")
        self.fleet_limit = values.get("child_fleet_ready_limit")

    @classmethod
    def load(cls, path: str) -> "DoorConfig":
        with open(path, "r", encoding="utf-8") as fh:
            return cls(json.load(fh))


# ---------------------------------------------------------------------------
# Dev Paperclip client (loopback, the dev instance's local-trusted surface)
# ---------------------------------------------------------------------------


class PaperclipLoopbackClient:
    """The DOOR's reader/writer against the dev Paperclip (stdlib urllib).

    This is the Executive-side writer of results and blockers — the dev
    stand-in for a production instance-scoped service credential, never the
    carrier's per-run token (which this process never sees).
    """

    def __init__(self, config: DoorConfig, timeout: int = 20):
        self._config = config
        self._timeout = timeout

    def _request(self, method: str, path: str, body=None):
        url = f"{self._config.paperclip_base}{path}"
        data = json.dumps(body).encode() if body is not None else None
        headers = dict(self._config.paperclip_headers)
        if data is not None:
            headers["content-type"] = "application/json"
        req = urllib.request.Request(url, data=data, method=method,
                                     headers=headers)
        with urllib.request.urlopen(req, timeout=self._timeout) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else {}

    def issue(self, issue_id):
        return self._request("GET", f"/api/issues/{issue_id}")

    def comments(self, issue_id):
        return self._request("GET", f"/api/issues/{issue_id}/comments")

    def company_issues(self):
        rows = self._request(
            "GET", f"/api/companies/{self._config.paperclip_company_id}"
                   "/issues?limit=100")
        if isinstance(rows, dict):
            rows = rows.get("issues") or rows.get("rows") or []
        return rows

    def add_comment(self, issue_id, body: str):
        # clientRequestId must be a UUID (the API answers invalid_format
        # otherwise — the exact 400 the first live run hit)
        return self._request(
            "POST", f"/api/issues/{issue_id}/comments",
            {"clientRequestId": str(uuid.uuid4()),
             "body": body})


# ---------------------------------------------------------------------------
# Scratch proof-source repository (the service fixture's shape, pytest-free)
# ---------------------------------------------------------------------------


def make_proof_source(root: Path) -> tuple[Path, str]:
    source = root / "proof-source"
    if not (source / ".git").is_dir():
        source.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "init", "-q", str(source)], check=True)
        subprocess.run(["git", "-C", str(source), "config", "user.name",
                        "T4B Door Fixture"], check=True)
        subprocess.run(["git", "-C", str(source), "config", "user.email",
                        "t4b-door@example.invalid"], check=True)
        (source / "README.md").write_text("# T4b door proof base\n",
                                          encoding="utf-8")
        subprocess.run(["git", "-C", str(source), "add", "."], check=True)
        subprocess.run(["git", "-C", str(source), "commit", "-qm", "base"],
                       check=True)
    sha = subprocess.run(["git", "-C", str(source), "rev-parse", "HEAD"],
                         capture_output=True, text=True, check=True)
    return source, sha.stdout.strip()


# ---------------------------------------------------------------------------
# Installed host facts (the COO host fixture's shape, pytest-free)
# ---------------------------------------------------------------------------


def build_host_facts(root: Path):
    """A real CooHostProvider over an installed-facts-shaped source.

    The mission names a synthetic root job — lawful for the ADMIT lane,
    where the selected-child lookup is skipped and only the work-ref
    currentness proof runs (the ingress lane's own law).
    """
    from ops.executive_os.coo_principal_host import CooInstalledSource
    from control_plane.executive_agent_capabilities import (
        ExecutionCapabilityRegistry,
    )
    from control_plane.workspace_read_service import WorkspaceReadService
    from control_plane.coo_principal_host import CooHostProvider
    from integrations.mastermind_executive_app.coo_binding import _digest

    sys.path.insert(0, str(REPO_ROOT / "tests"))
    try:
        from test_executive_coo_host import registry_file, PRINCIPAL_PROFILE
        from test_coo_principal_mandate import mission_doc
    finally:
        sys.path.pop(0)

    path = registry_file(root)
    registry = ExecutionCapabilityRegistry.load(path, source_root=REPO_ROOT)
    sys.path.insert(0, str(REPO_ROOT / "tests"))
    try:
        import test_executive_coo_install_binding as install
    finally:
        sys.path.pop(0)
    coo = install.coo_block()
    coo["missions"] = [dict(
        enabled=True, work_ref=WORK_REF,
        principal_binding_digest=_digest(coo["binding"]["binding"]),
        mission_authority_ref="authority:coo-t4b",
        outcome_ref="outcome:coo-t4b",
        proof_contract_ref="proof:coo-t4b",
        capability_profile_id=PRINCIPAL_PROFILE,
        capability_profile_digest=(
            registry.profiles[PRINCIPAL_PROFILE].profile_digest),
        execution_profiles=["research_only"], allowed_write_paths=[])]
    source = CooInstalledSource(
        lambda: json.loads(json.dumps(coo)),
        lambda: ExecutionCapabilityRegistry.load(path, source_root=REPO_ROOT))
    workspace = WorkspaceReadService(
        cache=None, runtime=None, authorize=None, armed={},
        runtime_identity={})
    host = CooHostProvider(source, workspace)
    document = json.loads(json.dumps(mission_doc()))
    host.workspace.read_mission_for_work_ref = (
        lambda work_ref: document)  # dev harness patch, admission lane only
    return host


# ---------------------------------------------------------------------------
# The frozen selected-child target (synthetic coordinates; the admit lane
# never resolves children)
# ---------------------------------------------------------------------------


def build_target() -> ExecutiveSelectedChildTarget:
    return ExecutiveSelectedChildTarget(
        work_ref=WORK_REF,
        children=(ExecutiveSelectedChild(
            selection=ExecutiveChildSelection(
                root_job_id="JOB-T4B-ROOT", parent_job_id="JOB-T4B-ROOT",
                job_id="JOB-T4B-WORK", plan_attempt_id="attempt-t4b-plan",
                plan_digest="b" * 64, plan_step_id="STEP-T4B",
                repair_round=0, expected_current_attempt_id=None),
            attempt_ordinal=1),),
        currentness_guard=lambda: None,
    )


# ---------------------------------------------------------------------------
# The crash hook store (the canary's MAIN-P1 window, verbatim discipline)
# ---------------------------------------------------------------------------


class CrashAfterReceiptStore:
    """Exit 90 AFTER ``put_launch_receipt`` commits, BEFORE the ACK returns —
    the L1B3-5 crash window: durable receipt, no process record."""

    def __init__(self, inner, side_path: Path):
        self._inner = inner
        self._side = side_path

    def put_launch_receipt(self, run_id: str, *args, **kwargs):
        # *args/**kwargs: the engine's receipt-store signature has grown
        # (cursor=) since this hook was written; forward everything so the
        # crash lands in the intended window, never as a TypeError
        self._inner.put_launch_receipt(run_id, *args, **kwargs)
        self._side.write_text(json.dumps({"crashed": _now(),
                                          "run_id": run_id}), encoding="utf-8")
        os._exit(90)  # noqa: PLW0160 - the deterministic crash point

    def __getattr__(self, name):
        return getattr(self._inner, name)


# ---------------------------------------------------------------------------
# The door
# ---------------------------------------------------------------------------


class CodingJobDoor:
    def __init__(self, config: DoorConfig):
        self.config = config
        self.root = config.scratch_root
        run_dir = self.root / "run"
        run_dir.mkdir(parents=True, exist_ok=True)
        # F11 (R4b review): frozen.json carries the lease token — its
        # directory is owner-only, as is every file written beneath it.
        os.chmod(run_dir, 0o700)
        self.paperclip = PaperclipLoopbackClient(config)
        self.frozen_path = self.root / "run" / "frozen.json"
        # F6 (R4b review): ONE lock around every structural change and
        # every save of the frozen record — intake and the executor are
        # two threads in one process.
        self._frozen_lock = threading.RLock()
        # command -> {"issue": {...issue fields...}, "envelope": {...}}
        self.frozen: dict[str, dict] = self._load_frozen()
        self.service: ExecutiveControlService | None = None
        self.host = None
        self.target = build_target()
        self.operator_listener = None
        self._stopping = threading.Event()
        self._executor_thread: threading.Thread | None = None
        self._wake = threading.Event()
        # F15 (R4b review) + attack F8: the composed t3-native supervisor
        # that owns recovery on the EXECUTOR thread (the service composes
        # its own over the service runtime in start()), the recovered
        # ActiveRuns it handed back, and the reconcile cadence clock.
        self._supervisor = None
        self._recovered: dict[str, Any] = {}
        self._last_reconcile = 0.0
        self.launch_census = self.root / "run" / "native-census.jsonl"
        self._budget = self.root / "run" / "thread-budget.json"

    # ------------------------------------------------------------- durable

    def _load_frozen(self) -> dict:
        if self.frozen_path.exists():
            return json.loads(self.frozen_path.read_text(encoding="utf-8"))
        return {}

    def _save_frozen(self) -> None:
        """F5 + F6 + F11: one locked, atomic, private write.

        F5 (attack review): write-temp-then-rename — a crash mid-write must
        never leave a truncated frozen.json.  F6 (R4b review): a UNIQUE
        temp name per writer, fsync of file and directory, and the lock so
        concurrent savers serialize instead of colliding.  F11: 0600 —
        the record carries the lease token.
        """
        with self._frozen_lock:
            payload = json.dumps(self.frozen, indent=2, sort_keys=True)
            tmp = self.frozen_path.with_name(
                f"frozen.json.{os.getpid()}.{threading.get_ident()}.tmp")
            try:
                fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
                             0o600)
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    fh.write(payload)
                    fh.flush()
                    os.fsync(fh.fileno())
                os.replace(tmp, self.frozen_path)
            except BaseException:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
                raise
            dir_fd = os.open(self.frozen_path.parent, os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)

    @staticmethod
    def _write_private(path: Path, text: str) -> None:
        """F11: every durable file this door writes is owner-only."""
        path.parent.mkdir(parents=True, exist_ok=True)
        os.chmod(path.parent, 0o700)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)

    def _reserve_thread(self, role: str) -> bool:
        budget = (json.loads(self._budget.read_text())
                  if self._budget.exists()
                  else {"limit": THREAD_BUDGET, "reserved": []})
        if role in budget["reserved"]:
            return True
        if len(budget["reserved"]) >= budget["limit"]:
            return False
        budget["reserved"].append(role)
        self._write_private(self._budget, json.dumps(budget))
        return True

    def _release_thread(self, role: str) -> None:
        """F7 (attack review): the budget bounds CONCURRENT jobs; a job that
        reached a terminal phase gives its slot back (idempotent)."""
        if not self._budget.exists():
            return
        budget = json.loads(self._budget.read_text())
        reserved = budget.get("reserved") or []
        if role in reserved:
            budget["reserved"] = [r for r in reserved if r != role]
            self._write_private(self._budget, json.dumps(budget))

    # ------------------------------------------------------- service setup

    def _t3_port_factory(self, branch: str):
        """A REAL census-recording port factory for a door-owned supervisor
        composition.  The service-side supervisor may finish a run it
        recovered at startup, so its port must be real; its launch
        arguments name a door-owned branch that is only ever used if that
        supervisor (which never launches) somehow tried to."""
        from control_plane.t3_native_composition import (
            T3McpHttpTransport,
            T3McpToolPort,
        )
        launch_arguments = {
            "projectId": self.config.t3_project_id,
            "workspaceStrategy": {"type": "worktree", "branch": branch,
                                  "baseRef": "master", "startFromOrigin": True},
        }

        def factory(token_value: str):
            transport = T3McpHttpTransport(
                self.config.t3_proof_base + "/mcp", token_value)

            def call_tool(tool: str, arguments: dict):
                self._record_census(tool, arguments)
                return transport.call_tool(tool, arguments)

            return T3McpToolPort.from_access_token(
                call_tool, token_value,
                launch_arguments=dict(launch_arguments))

        return factory

    @staticmethod
    def _reconcile_only_port_factory(token_value: str):
        """The executor's supervisor RECONCILES; it never launches.  A port
        request on that composition is a bug to surface, not a silent
        wrong-branch launch (the per-job launch port is composed
        separately in ``_compose_adapter``)."""
        raise RuntimeError(
            "the door's reconcile-only supervisor composition requested a "
            "launch port; recovery must never launch")

    def _compose_supervisor(self, runtime, *, port_factory):
        """F15 (R4b review) + attack F8: compose the REAL t3-native
        supervisor over the shared adapter state store.

        One recovery owner — the engine.  The composition shares the door's
        durable adapter receipts (``SQLiteT3AdapterStateStore`` over the
        door's own store path), so the wired ``provider_receipt_reader``
        sees exactly the receipts the crashed door's adapter persisted,
        and ``reconcile_restart`` adopts an identity-less claim through the
        boundary seam.  ``runs_root`` is the door's run/jobs tree so the
        recomputed launch metadata and the recovery prompt land where the
        door's launcher put them.

        Not enrolled (no token file yet — the dev server was down at start):
        the PLAIN primary supervisor is returned.  That composition can
        reconcile nothing it would need the t3 owner for, and a fresh
        un-tokened scratch holds no claim rows at all; the executor's mint
        loop composes the full owner once a token exists."""
        from control_plane.executive_supervisor import ExecutiveSupervisor
        from control_plane.t3_execution_adapter import SQLiteT3AdapterStateStore
        from control_plane.t3_native_composition import (
            T3NativeProcessController,
            compose_t3_native_adapter,
            compose_t3_native_supervisor,
        )
        composition = compose_t3_native_adapter(
            runtime,
            token_file=self.config.t3_token_path,
            port_factory=port_factory,
            state_store=SQLiteT3AdapterStateStore(self._adapter_store_path()),
            inspector=_DoorInspector(),
            clock=lambda: dt.datetime.now(dt.timezone.utc))
        runs_root = self.root / "run" / "jobs"
        isolation_roots = (self.root / "workspaces", runs_root)
        primary = ExecutiveSupervisor(
            runtime, composition.adapter,
            runs_root=runs_root,
            isolation_roots=isolation_roots,
            require_complete_launch_attestation=False,
            inspector=_DoorInspector(),
            process_controller=T3NativeProcessController())
        if not composition.composed:
            _log(f"t3 adapter not enrolled ({composition.status}: "
                 f"{composition.reason}); service-side reconciliation runs "
                 "on the plain supervisor until the worker token exists")
            return primary
        return compose_t3_native_supervisor(
            primary, composition,
            runs_root=runs_root,
            isolation_roots=isolation_roots)

    async def _ensure_worker_token(self) -> None:
        """Mint/verify the door's worker token (never printed) ONCE, before
        the service composes — the composed adapter reads the token file
        eagerly.  Never blocks door startup on a down dev server: the door
        must still serve its operator socket (the degrade-honestly law), the
        executor's own mint loop owns the retry, and without a token the
        service-side supervisor composes plain and reconciles nothing it
        cannot own.  The pairing CLI selects its server by the home's
        runtime state and FALLS BACK TO THE LIVE APP for an unknown home —
        no port flag exists — so the CLI runs only when the configured dev
        server provably answers; a pairing code on the live app is never
        acceptable, even unused."""
        if not self._dev_server_ready():
            _log("dev T3 server not answering on "
                 f"{self.config.t3_proof_base}; pairing CLI withheld "
                 "(it would fall back to the live app); the executor's "
                 "mint loop retries and the service composes plain until "
                 "a token exists")
            return
        from integrations.t3.live_proof import t3_live_proof as proof

        try:
            # Finding 8 (R4b review): the target is REQUIRED and pinned
            # — the mint is refused unless the pinned home's own runtime
            # state names the pinned dev port.
            proof.obtain_mcp_access_token(
                str(self.config.t3_token_path),
                self.config.t3_token_label,
                base_url=self.config.t3_proof_base,
                home_dir=self.config.t3_home_dir)
        except Exception as exc:  # noqa: BLE001 - dev server may be down
            _log(f"worker token unavailable (dev T3 server down?): "
                 f"{type(exc).__name__}: {exc}")

    async def start(self) -> None:
        # The service's supervisor factory composes the REAL t3-native
        # owner, which reads the token file eagerly — mint first (F15).
        self._t3_env_backup = self._apply_t3_env()
        await self._ensure_worker_token()
        source, base_sha = make_proof_source(self.root)
        cfg = ServiceConfig(
            runtime_root=self.root / "runtime",
            socket_path=self.root / "run" / "executive.sock",
            proof_source_repository=source,
            proof_workspace_root=self.root / "workspaces",
            proof_base_sha=base_sha,
            proof_shared_gid=os.getegid(),
            backup_root=self.root / "backups",
            allowed_peer_uids=(os.geteuid(),),
            shutdown_grace_seconds=0.1,
            coo_autonomy_armed=True,
            coo_tick_interval_seconds=3600.0,
        )
        uid = os.geteuid()
        binding = CeoIngressAppBinding(
            peer_uid=uid, armed=False,
            grounding_provider=SimpleNamespace(observe=lambda: {}),
            principal_admission_armed=True,
            principal_admission_guard=lambda _value: None,
            child_request_material=dict(self.frozen),
        )
        self.service = ExecutiveControlService(
            cfg,
            # F15 (R4b review) + attack F8: the service's startup
            # reconciliation runs on the REAL composed t3-native supervisor
            # (its own composition over the service runtime; the door
            # executor composes a second instance over its own runtime —
            # one owner, one writer per thread).
            supervisor_factory=lambda runtime: self._compose_supervisor(
                runtime,
                port_factory=self._t3_port_factory(
                    "t3/mmos-t4b-door-service")),
            autonomy_guard=(lambda: None),
            ceo_ingress_socket_path=self.root / "run" / "selected-child.sock",
            # The App and C1 lanes must carry distinct peer uids; the door
            # process itself connects as the App peer (the ingress tests'
            # own composition: binding uid = ours, C1 uid = ours + 1).
            ceo_ingress_peer_uid=uid + 1,
            ceo_ingress_grounding_provider=SimpleNamespace(observe=lambda: {}),
            ceo_ingress_armed=False, ceo_ingress_app_binding=binding)
        await self.service.start()
        reply = await self._service_request("register-worker")
        if not reply.get("ok"):
            raise RuntimeError(f"register-worker refused: {reply}")
        self.host = build_host_facts(self.root)
        self.service._ceo_ingress_app_binding = dataclasses.replace(
            self.service._ceo_ingress_app_binding,
            principal_facts_factory=lambda runtime: self.host,
            selected_child_target=self.target)

        from integrations.executive_mcp.local_operator import (
            LocalOperatorConfig, LocalOperatorListener,
        )
        operator_config = LocalOperatorConfig(
            socket_path=self.root / "run" / "local-operator.sock",
            allowed_uids=(uid,), operator_subject="t4b-coding-job-door")
        self.operator_listener = LocalOperatorListener(
            operator_config, CodingJobDoorApp(self))
        self.operator_listener.bind()
        asyncio.get_running_loop().create_task(
            self.operator_listener.serve_forever())
        self._refreeze_binding()
        self._executor_thread = threading.Thread(
            target=self._executor_main, name="t4b-executor", daemon=True)
        self._executor_thread.start()
        _log(f"door up: scratch={self.root} "
             f"operator={operator_config.socket_path} "
             f"ingress={self.root / 'run' / 'selected-child.sock'}")

    async def _service_request(self, command: str, args=None):
        from control_plane.executive_service import send_control_request
        return await send_control_request(
            self.root / "run" / "executive.sock", command, args or {})

    def _refreeze_binding(self) -> None:
        if self.service is None:
            return  # not yet started (intake before serve; tests)
        self.service._ceo_ingress_app_binding = dataclasses.replace(
            self.service._ceo_ingress_app_binding,
            child_request_material={
                command: entry["envelope"]
                for command, entry in self.frozen.items()})

    # --------------------------------------------------------------- intake

    def freeze_issue(self, issue_row: dict) -> str | None:
        """Freeze one envelope for one task (registration, not admission).

        F10 (R4b review): only issues assigned to an ENROLLED teammate are
        frozen — the door never holds an envelope for a task outside the
        roster.  The structural insert rides the frozen lock (F6).
        """
        issue_id = str(issue_row.get("id") or "")
        if not issue_id:
            return None
        assignee = str(issue_row.get("assigneeAgentId") or "")
        if assignee not in self.config.teammates:
            return None  # not an enrolled teammate: never frozen
        request = build_task_request(
            issue_id=issue_id,
            agent_id=issue_row.get("assigneeAgentId") or "unknown-agent",
            company_id=self.config.paperclip_company_id,
            title=issue_row.get("title") or "",
            description=issue_row.get("description") or "",
            key=DEFAULT_JOB_KEY)
        command = task_command(request)
        with self._frozen_lock:
            if command in self.frozen:
                return None  # the digest is frozen at intake; edits never drift
            self.frozen[command] = {
                "issue": {"id": issue_id,
                          "identifier": issue_row.get("identifier"),
                          "title": issue_row.get("title"),
                          "assigneeAgentId": issue_row.get("assigneeAgentId")},
                "envelope": request.to_dict(),
                "command": command,  # the entry's own id (a person reads it on a blocker)
                "frozen_at": _now(),
            }
            self._save_frozen()
        self._refreeze_binding()
        _log(f"frozen {issue_row.get('identifier')} -> {command[:24]}…")
        self._wake.set()
        return command

    def intake_poll_once(self) -> None:
        try:
            rows = self.paperclip.company_issues()
        except Exception as exc:  # noqa: BLE001 - unreachable Paperclip is honest
            _log(f"intake poll failed (dev Paperclip unreachable): "
                 f"{type(exc).__name__}: {exc}")
            return
        for row in rows:
            try:
                self.freeze_issue(row)
            except Exception as exc:  # noqa: BLE001 - one bad row stops nothing
                _log(f"intake of {row.get('identifier')} failed: {exc}")

    # ------------------------------------------------------- the admit lane

    def _frame_context(self) -> dict:
        row, fact, authority = self.host.source.snapshot(WORK_REF)
        from control_plane.coo_principal_envelope import (
            PrincipalAdmissionContext,
        )
        return {
            "principal": {
                "policy_id": fact.policy_id, "issuer_digest": fact.issuer_digest,
                "subject_digest": fact.subject_digest,
                "client_ref": fact.client_ref, "resource": fact.resource_ref,
                "scopes": list(fact.scopes)},
            "principal_context": dataclasses.asdict(PrincipalAdmissionContext(
                row["work_ref"], fact.principal_binding_digest,
                authority.mission_authority_ref,
                authority.authority_generation_digest)),
            "capability_profile_digest": authority.capability_profile_digest,
            "target_digest": self.target.material_digest(),
        }

    async def admit(self, command: str) -> dict:
        """ONE admission call over the real CEO-ingress socket lane.

        The frame is built here from the door's own providers (the trusted
        host act); the caller named a command only.
        """
        if command not in self.frozen:
            return {"ok": False, "error": {
                "kind": "refused", "code": "invalid_input",
                "message": "coding-job command is not frozen for any task"}}
        entry = self.frozen[command]
        # F10 (R4b review): the FIRST admission of a command requires the
        # task itself to show the request — the assignee is enrolled and
        # its newest agent comment carries the job block for this entry's
        # key.  A same-uid caller can then not admit a task that never
        # asked for a job.  A recovery REPLAY (the request already durable,
        # F3's crash window) skips the gate: it re-asks the same command,
        # never a new authorization.
        if not entry.get("admit_requested_at"):
            gate_error = self._task_request_error(command, entry)
            if gate_error is not None:
                return {"ok": False, "error": {
                    "kind": "refused", "code": gate_error[0],
                    "message": gate_error[1]}}
        # F3 (attack review): the request (the carrier's ONE call) is durable
        # BEFORE the engine is asked, so a crash mid-call is recoverable.
        # Freezing at intake is REGISTRATION, never a request — the door
        # must not admit a task nobody asked for (the live default-journey
        # re-run caught exactly that inversion).
        entry["admit_requested_at"] = (
            entry.get("admit_requested_at") or _now())
        entry["admit_last_ask"] = _now()  # F12: ages the WAIT retry
        self._save_frozen()
        context = self._frame_context()
        frame = {
            "schema": SELECTED_CHILD_FRAME_SCHEMA,
            "request": {"action": "selected_child_admit", "command": command},
            "target_digest": context["target_digest"],
            "principal": context["principal"],
            "principal_context": context["principal_context"],
            "capability_profile_digest": context["capability_profile_digest"],
        }
        reader, writer = await asyncio.open_unix_connection(
            str(self.root / "run" / "selected-child.sock"))
        try:
            writer.write(json.dumps(frame).encode() + b"\n")
            await writer.drain()
            reply = json.loads(await reader.readline())
        finally:
            writer.close()
            await writer.wait_closed()
        # the outcome is durable even when it is a WAIT or a refusal, so the
        # executor never re-asks a question the engine already answered
        entry["admit_outcome"] = (
            (reply.get("result") or {}).get("state")
            or (reply.get("error") or {}).get("code") or "UNKNOWN")
        if reply.get("ok") and reply.get("result", {}).get("state") in (
                "ADMITTED", "REPLAY"):
            entry["job_id"] = reply["result"].get("job_id")
            entry["admitted_at"] = _now()
        self._save_frozen()
        if entry.get("job_id"):
            self._wake.set()
        return reply

    # ------------------------------------------------- the F10 request gate

    @staticmethod
    def _comment_rows_oldest_first(rows) -> list[dict]:
        """An issue's comments, oldest first (the carrier's own ordering:
        Paperclip lists newest first; rows without timestamps keep their
        arrival order)."""
        if isinstance(rows, dict):
            rows = (rows.get("comments") or rows.get("rows")
                    or rows.get("items") or [])
        rows = [row for row in rows if isinstance(row, dict)]
        if rows and all(row.get("createdAt") for row in rows):
            rows = sorted(rows, key=lambda row: str(row["createdAt"]))
        return rows

    def _task_request_error(self, command: str, entry: dict):
        """F10 (R4b review): ``None`` when the TASK shows the request —
        the live assignee is an enrolled teammate and its NEWEST agent
        comment carries the job block for this entry's key (the carrier's
        own parser discipline: the fenced block as the comment's own last
        word).  Otherwise a typed ``(code, message)`` refusal; nothing is
        persisted, so a later lawful admit is not burned."""
        issue = entry.get("issue") or {}
        issue_id = issue.get("id")
        if not issue_id:
            return ("invalid_input",
                    "the frozen entry names no issue to show a request")
        try:
            live = self.paperclip.issue(issue_id)
            rows = self.paperclip.comments(issue_id)
        except Exception as exc:  # noqa: BLE001 - unreadable is a refusal
            return ("TASK_STATE_UNREADABLE",
                    f"the task's assignee/comments could not be read "
                    f"({type(exc).__name__}); refusing to admit on a guess")
        assignee = str(
            (live or {}).get("assigneeAgentId")
            or issue.get("assigneeAgentId") or "")
        if assignee not in self.config.teammates:
            return ("ASSIGNEE_NOT_ENROLLED",
                    f"the task's assignee ({assignee or 'none'}) is not an "
                    "enrolled teammate of this door")
        agent_rows = [row for row in self._comment_rows_oldest_first(rows)
                      if row.get("authorType") == "agent"]
        if not agent_rows:
            return ("TASK_REQUEST_MISSING",
                    "no agent comment on the task carries the coding-job "
                    "request block")
        newest = agent_rows[-1]
        # the carrier's parser (byte-pinned by its own tests): the LAST
        # fenced paperclip-coding-job block, the comment's own last word
        from tools.mmos_teammate.wake_carrier import parse_coding_job_block
        block = parse_coding_job_block(newest.get("body") or "")
        key = str((entry.get("envelope") or {}).get("logical_child_key")
                  or DEFAULT_JOB_KEY)
        if block is None or block.get("key") != key:
            return ("TASK_REQUEST_MISSING",
                    f"the assignee's newest agent comment does not request "
                    f"a coding job for key {key}")
        return None

    def job_state(self, command: str) -> dict:
        entry = self.frozen.get(command) or {}
        return {
            "command": command,
            "issue": entry.get("issue"),
            "job_id": entry.get("job_id"),
            "attempt_id": entry.get("attempt_id"),
            "phase": entry.get("phase"),
            "delivery": entry.get("delivery"),
            "native_launches": self._native_launch_count(),
        }

    def _native_launch_count(self) -> int:
        if not self.launch_census.exists():
            return 0
        rows = self.launch_census.read_text(encoding="utf-8").splitlines()
        return sum(1 for line in rows if line.strip()
                   and json.loads(line).get("tool") == "t3_thread_launch")

    def _ensure_admitted(self, command: str, entry: dict) -> None:
        """F3 (attack review): a crash between the admission commit and the
        frozen save leaves the engine holding an admitted job this door
        cannot see — an admit was REQUESTED (durable) but its outcome is
        unknown.  Re-issuing the SAME command is an idempotent REPLAY — the
        engine's command_id unique law arbitrates — so the orphan is
        recovered, never doubled.  The reply's outcome is then durable; a
        WAIT or refusal was answered and stays with the carrier."""
        try:
            asyncio.run(self.admit(command))
        except Exception as exc:  # noqa: BLE001 - the service is in-process
            _log(f"re-admission of {command[:24]}… failed: "
                 f"{type(exc).__name__}: {exc}")
            return  # the outcome is still unknown; the next wake retries
        if entry.get("job_id"):
            self._save_frozen()  # idempotent with admit()'s own persist
            self._wake.set()
            return  # healed: the orphaned admission is visible to the door
        outcome = entry.get("admit_outcome") or "UNKNOWN"
        if outcome == "WAIT":
            return  # answered for now; F12 — this door itself re-asks the
            # same command once the retry interval elapses
        code = outcome if outcome != "UNKNOWN" else "ADMISSION_REFUSED"
        reason = (f"the Executive refused re-admission of the frozen job "
                  f"({outcome})")
        entry["phase"] = "admission-refused"
        entry["blocker"] = {"code": code, "reason": reason[:200]}
        self._save_frozen()
        self._surface_blocker(entry, code, reason[:200])

    def _record_census(self, tool: str, arguments: dict) -> None:
        # F11: the census rides the owner-only run directory
        self.launch_census.parent.mkdir(parents=True, exist_ok=True)
        os.chmod(self.launch_census.parent, 0o700)
        fd = os.open(self.launch_census,
                     os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"t": _now(), "tool": tool,
                                 "clientRequestId":
                                     arguments.get("clientRequestId")}) + "\n")

    # ------------------------------------------------------------ executor

    def _adapter_store_path(self) -> Path:
        return (self.root / "runtime" / "data" / "control_plane"
                / "t3_adapter_state.sqlite3")

    def _apply_t3_env(self) -> dict:
        """Pin every T3-selection env to the configured DEV server.

        The pairing helper's CLI leg reads T3CODE_HOME/T3CODE_PORT (not the
        base URL); all three are set together so no leg can fall back to a
        default server.  Returns a backup for in-process callers (tests).
        """
        backup = {}
        for key, value in (
                ("T3_PROOF_BASE_URL", self.config.t3_proof_base),
                ("T3CODE_HOME", self.config.t3_home_dir),
                ("T3CODE_PORT", str(self.config.t3_port))):
            backup[key] = os.environ.get(key)
            os.environ[key] = value
        return backup

    def _restore_t3_env(self, backup: dict) -> None:
        for key, value in backup.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def _executor_main(self) -> None:
        """The canary's engine chain on the executor's own runtime instance
        (same scratch dir, same sqlite — the canary's one-writer-per-role
        discipline, here one dedicated thread; one job at a time)."""
        if getattr(self, "_t3_env_backup", None) is None:
            self._t3_env_backup = self._apply_t3_env()
        from integrations.t3.live_proof import t3_live_proof as proof

        runtime = Runtime.at(self.root / "runtime", clock=lambda: int(
            time.time() * 1000), lease_seconds=self.config.lease_seconds)
        self._register_worker(runtime)
        while not self._stopping.is_set():
            # The pairing CLI selects its server by the home's runtime state
            # and FALLS BACK TO THE LIVE APP for an unknown home — there is
            # no port flag.  So the CLI is run only once the configured dev
            # server provably answers on the configured base; otherwise the
            # executor waits.  A pairing code on the live app is never
            # acceptable, even unused.
            if not self._dev_server_ready():
                _log("dev T3 server not answering on "
                     f"{self.config.t3_proof_base}; pairing CLI withheld "
                     "(it would fall back to the live app); waiting")
                self._stopping.wait(timeout=10.0)
                continue
            try:
                # Mint/verify the door's worker token file (never printed).
                # start() mints it before the service; this loop only
                # re-verifies (idempotent).  Finding 8 (R4b review): the
                # target is REQUIRED and pinned — the mint is refused
                # unless the pinned home's own runtime state names the
                # pinned dev port, so the pairing CLI can never fall back
                # to the live app (3773).
                proof.obtain_mcp_access_token(
                    str(self.config.t3_token_path),
                    self.config.t3_token_label,
                    base_url=self.config.t3_proof_base,
                    home_dir=self.config.t3_home_dir)
                break
            except Exception as exc:  # noqa: BLE001 - dev server may be down
                _log(f"worker token unavailable (dev T3 server down?): "
                     f"{type(exc).__name__}: {exc}")
                self._stopping.wait(timeout=10.0)

        # F15 (R4b review) + attack F8: the EXECUTOR's recovery owner is
        # the real composed supervisor over this thread's runtime.  It
        # reconciles at start and on a cadence; the door never records a
        # process or adopts a lease itself.
        try:
            self._supervisor = self._compose_supervisor(
                runtime, port_factory=self._reconcile_only_port_factory)
            self._reconcile(runtime)
        except Exception as exc:  # noqa: BLE001 - honest lane failure
            _log(f"supervisor composition/reconcile failed: "
                 f"{type(exc).__name__}: {exc}")

        while not self._stopping.is_set():
            self._wake.wait(timeout=2.0)
            self._wake.clear()
            if (self._supervisor is not None
                    and time.monotonic() - self._last_reconcile
                    >= self.config.reconcile_interval_seconds):
                self._reconcile(runtime)
            for command, entry in list(self.frozen.items()):
                action = self._entry_action(entry)
                if action == "skip":
                    continue
                job_role = (f"job:{entry.get('job_id')}"
                            if entry.get("job_id") else None)
                if action == "admit":
                    # F3 (attack review): the engine may hold an admitted job
                    # whose job_id never reached frozen.json — re-admit the
                    # SAME command (idempotent REPLAY), never a second job.
                    self._ensure_admitted(command, entry)
                    continue
                if action == "finish-sealed":
                    # F6: the seam already fired inside complete_attempt; a
                    # crash before the bookkeeping read only owes this read.
                    self._finish_sealed(runtime, entry)
                    if job_role:
                        self._release_thread(job_role)
                    continue
                if action == "blocker":
                    # F6: execution is over (refused/failed/parked); only the
                    # blocker post may still be owed — never a re-execution.
                    if entry.get("phase") == "launch-uncertain":
                        # F13 (R4b review): an uncertain attempt HOLDS its
                        # thread slot until the attempt row is reconciled
                        # to a terminal state — only then does it return.
                        self._close_launch_uncertainty(runtime, entry)
                        if entry.get("uncertainty_closed"):
                            continue  # reconciled; the slot already returned
                        self._surface_blocker(entry, "LAUNCH_UNCERTAIN",
                                              (entry.get("blocker")
                                               or {}).get("reason", ""))
                        continue  # the slot stays held
                    if entry.get("phase") == "reconcile-quarantined":
                        # F15: the ENGINE quarantined the recovery; the
                        # receipt proved a live native execution, so the
                        # slot HOLDS until an operator reconciles it.
                        blocker = entry.get("blocker") or {}
                        self._surface_blocker(
                            entry, blocker.get("code") or "RECONCILE_QUARANTINED",
                            blocker.get("reason") or "")
                        continue  # the slot stays held
                    blocker = entry.get("blocker") or {}
                    self._surface_blocker(
                        entry, blocker.get("code") or "EXECUTOR_FAILED",
                        blocker.get("reason") or entry.get("error") or "")
                    if job_role:
                        self._release_thread(job_role)
                    continue
                try:
                    self._execute(runtime, command, entry)
                except Exception as exc:  # noqa: BLE001 - honest per-task lane
                    _log(f"execute {command[:24]}… failed: "
                         f"{type(exc).__name__}: {exc}")
                    entry["phase"] = "execute-failed"
                    entry["error"] = f"{type(exc).__name__}: {exc}"[:300]
                    entry["blocker"] = {
                        "code": "EXECUTOR_FAILED",
                        "reason": f"{type(exc).__name__}: {exc}"[:200]}
                    self._save_frozen()
                    self._surface_blocker(entry, "EXECUTOR_FAILED",
                                          f"{type(exc).__name__}: {exc}"[:200])
                    if job_role:
                        self._release_thread(job_role)

    # execution phases after which _execute must never run again: the
    # refusal/failure is the job's recorded result (F6, attack review)
    PARKED_PHASES = ("delivery-refused", "execute-failed", "launch-uncertain",
                     "admission-refused", "reconcile-quarantined")

    def _wait_retry_due(self, entry: dict) -> bool:
        """F12 (R4b review): True when a WAIT may be re-asked — the retry
        interval elapsed since the last ask.  A timestamp that cannot be
        aged honestly reads as due: the engine's command-id law makes the
        re-ask of the same command safe (one admission, idempotent)."""
        stamp = entry.get("admit_last_ask") or entry.get("admit_requested_at")
        if type(stamp) is not str or not stamp:
            return True
        try:
            asked = dt.datetime.fromisoformat(stamp)
        except ValueError:
            return True
        if asked.tzinfo is None:
            asked = asked.replace(tzinfo=dt.timezone.utc)
        age = (dt.datetime.now(dt.timezone.utc) - asked).total_seconds()
        return age >= self.config.wait_retry_seconds

    def _reconcile_retry_due(self, entry: dict) -> bool:
        """F15: True when a deferred recovery may drive reconcile again —
        the same cadence as the executor's periodic reconcile.  An
        unageable timestamp reads as due (reconcile is idempotent)."""
        stamp = entry.get("reconcile_last_ask")
        if type(stamp) is not str or not stamp:
            return True
        try:
            asked = dt.datetime.fromisoformat(stamp)
        except ValueError:
            return True
        if asked.tzinfo is None:
            asked = asked.replace(tzinfo=dt.timezone.utc)
        age = (dt.datetime.now(dt.timezone.utc) - asked).total_seconds()
        return age >= self.config.reconcile_interval_seconds

    def _reconcile(self, runtime, attempt_ids=None) -> list:
        """F15 (R4b review) + attack F8: ONE recovery owner — the engine.

        Drive the composed supervisor's ``reconcile_restart`` (at start and
        on a cadence), then keep the recovered ActiveRuns for the executor
        to finish through the door's delivery lane.  The door never records
        a process or adopts a lease itself; a quarantine is surfaced as the
        entry's typed blocker, a deferral is retried on the cadence."""
        if self._supervisor is None:
            return []
        try:
            outcomes = self._supervisor.reconcile_restart(
                requeue_lost=False,
                **({"attempt_ids": attempt_ids}
                   if attempt_ids is not None else {}))
            recovered = self._supervisor.take_recovered_runs()
        except Exception as exc:  # noqa: BLE001 - honest lane failure
            _log(f"reconcile failed: {type(exc).__name__}: {exc}")
            return []
        self._last_reconcile = time.monotonic()
        for run in recovered:
            attempt_id = run.lease.attempt.attempt_id
            self._recovered[attempt_id] = run
            # route the recovered lease to its frozen entry: the next
            # executor pass seals from the ENGINE-adopted lease
            for entry in self.frozen.values():
                if entry.get("attempt_id") == attempt_id:
                    entry["fence_generation"] = (
                        run.lease.attempt.fence_generation)
                    entry["lease_token"] = run.lease.lease_token
                    entry["provider_session_id"] = (
                        run.process_ref.provider_session_id)
                    entry["phase"] = "reattached"
            self._wake.set()
            self._save_frozen()
        for outcome in outcomes:
            status = getattr(outcome.status, "name", str(outcome.status))
            if status != "AWAITING_LEASE_EXPIRY":  # routine deferral
                _log(f"reconcile {outcome.attempt_id[:24]}… -> {status}"
                     + (f" ({(outcome.error or '')[:140]})"
                        if outcome.error else ""))
        return outcomes

    def _entry_action(self, entry: dict) -> str:
        """One bounded routing decision per frozen entry per wake (F6).

        Registration is not a request: a frozen entry nobody's carrier call
        named stays parked until its admit call arrives.  A refusal was
        answered (the carrier owns its retry); a WAIT is retried by THIS
        door once the retry interval elapses (F12) — same command, so
        still one admission."""
        phase = entry.get("phase")
        if phase == "delivered":
            return "skip"
        if phase == "launch-uncertain" and not entry.get("uncertainty_closed"):
            # F13: an uncertainty that has not closed keeps its wake — the
            # blocker branch polls the attempt row and returns the held
            # slot exactly when the row turns terminal
            return "blocker"
        if phase == "awaiting-lease-expiry":
            # F15: the engine deferred adoption until the crashed claimant's
            # lease expires; the periodic reconcile adopts when it finally
            # can and the entry resumes from the recovered run — within the
            # interval the deferral stands
            return "execute" if self._reconcile_retry_due(entry) else "skip"
        if phase == "engine-owned":
            # F15: an engine recovery already owns this run (the service's
            # startup reconcile or an earlier adoption); the door watches
            # for the terminal row and finishes the delivery read
            return "execute"
        if entry.get("blocker_surfaced"):
            # the blocker is the job's recorded result on the task; a
            # surfaced blocker is terminal for this executor
            return "skip"
        if entry.get("uncertainty_closed"):
            # F13: the uncertain attempt was reconciled; nothing more owed
            return "skip"
        if not entry.get("job_id"):
            if not entry.get("admit_requested_at"):
                return "skip"   # registered only; nobody asked for a job
            if entry.get("admit_outcome") == "WAIT":
                # F12: the door re-asks the SAME command when capacity may
                # have freed; within the interval the answer stands
                return "admit" if self._wait_retry_due(entry) else "skip"
            if entry.get("admit_outcome"):
                return "skip"   # answered (refusal); the carrier owns retry
            return "admit"      # the crash window: outcome unknown
        if phase == "sealed":
            return "finish-sealed"
        if phase in self.PARKED_PHASES:
            return "blocker"
        return "execute"

    def _dev_server_ready(self) -> bool:
        """The configured dev T3 server answers on the configured base."""
        try:
            with urllib.request.urlopen(
                    self.config.t3_proof_base + "/", timeout=5) as resp:
                return 200 <= resp.status < 300
        except Exception:  # noqa: BLE001 - not answering is the answer
            return False

    def _register_worker(self, runtime: Runtime) -> None:
        from control_plane.executive_runtime import StateConflict
        try:
            runtime.workers.register_worker(
                WORKER_ID, provider="t3", account_label="mcp-bearer-session",
                worker_type="t3-native", capabilities=["code"],
                quota_classes={"default": {"capabilities": ["code"],
                                           "metadata": {"adapter_id":
                                                        "t3-native"}}},
                metadata={"host_id": HOST_ID})
        except StateConflict as exc:
            if "already registered" not in str(exc):
                raise

    def _compose_adapter(self, request, branch: str, *, fresh: bool):
        """The canary's `_compose` per job: real transport + port with the
        job's own launch arguments, durable census wrapper, optional crash
        hook on the fresh launch only."""
        from control_plane.t3_execution_adapter import SQLiteT3AdapterStateStore
        from control_plane.t3_native_composition import (
            T3McpHttpTransport,
            T3McpToolPort,
            compose_t3_native_adapter,
        )
        launch_arguments = {
            "projectId": self.config.t3_project_id,
            "workspaceStrategy": {"type": "worktree", "branch": branch,
                                  "baseRef": "master", "startFromOrigin": True},
        }
        box: dict = {}

        def port_factory(token_value: str):
            transport = T3McpHttpTransport(
                self.config.t3_proof_base + "/mcp", token_value)

            def call_tool(tool: str, arguments: dict):
                self._record_census(tool, arguments)
                return transport.call_tool(tool, arguments)

            port = T3McpToolPort.from_access_token(
                call_tool, token_value,
                launch_arguments=dict(launch_arguments))
            box["port"] = port
            return port

        store = SQLiteT3AdapterStateStore(self._adapter_store_path())
        if fresh and self.config.crash_mode == "after_receipt":
            store = CrashAfterReceiptStore(store, self.root / "run" / "crash")
        composition = compose_t3_native_adapter(
            Runtime.at(self.root / "runtime", clock=lambda: int(
                time.time() * 1000), lease_seconds=self.config.lease_seconds),
            token_file=self.config.t3_token_path,
            port_factory=port_factory, state_store=store,
            inspector=_DoorInspector(),
            clock=lambda: dt.datetime.now(dt.timezone.utc))
        box["composition"] = composition
        return composition.adapter, box

    def _wait_terminal(self, adapter, ref, *, deadline_s: float = 1800.0,
                       interval_s: float = 15.0):
        from control_plane.worker_execution_contract import WorkerRunStatus
        terminal = frozenset({
            WorkerRunStatus.SUCCEEDED, WorkerRunStatus.FAILED,
            WorkerRunStatus.INVALID_RESULT, WorkerRunStatus.CANCELLED,
            WorkerRunStatus.TIMED_OUT})

        async def _run():
            statuses: list[str] = []
            status = WorkerRunStatus.STARTING
            deadline = time.monotonic() + deadline_s
            while time.monotonic() < deadline:
                status = await adapter.status(ref)
                if not statuses or statuses[-1] != status.value:
                    statuses.append(status.value)
                if status in terminal:
                    return statuses, status
                await asyncio.sleep(interval_s)
            return statuses, status

        return asyncio.run(_run())

    def _execute(self, runtime, command, entry):
        request = ChildExecutionRequest.from_dict(dict(entry["envelope"]))
        branch = f"t3/mmos-t4b-job-{request.request_digest[:8]}"
        job_id = entry.get("job_id")
        attempt_id = entry.get("attempt_id")

        if attempt_id is None:
            if not self._reserve_thread(f"job:{job_id}"):
                entry["phase"] = "budget-exhausted"
                self._save_frozen()
                self._surface_blocker(entry, "THREAD_BUDGET_EXHAUSTED",
                                      "no T3 thread budget left for this job")
                return
            # F15 (R4b review): the placement Job names its workspace —
            # restart reconciliation refuses (typed) to adopt an
            # identity-less claim whose Job cannot name where it ran.
            workspace = (self.root / "run" / "jobs"
                         / f"job-{request.request_digest[:8]}-ws")
            workspace.mkdir(parents=True, exist_ok=True)
            os.chmod(workspace, 0o700)
            composed = compose_child_execution(
                runtime, request=request, spec=self._spec(request),
                branch=branch, worktree=str(workspace))
            lease = runtime.attempts.claim_job(
                composed.placement_job.job_id,
                placement_observations=self._observations(),
                fabric_placement_intent=self._intent(request))
            if lease is None:
                raise RuntimeError("claim refused for the placement job")
            attempt_id = lease.attempt.attempt_id
            entry.update({"attempt_id": attempt_id,
                          "placement_job_id": composed.placement_job.job_id,
                          "fence_generation": lease.attempt.fence_generation,
                          "lease_token": lease.lease_token, "phase": "claimed"})
            self._save_frozen()
            _log(f"claimed {attempt_id} on placement "
                 f"{composed.placement_job.job_id}; branch {branch}")
            adapter, _box = self._compose_adapter(request, branch, fresh=True)
            spec = self._launch_spec(run_id=attempt_id, job_id=job_id,
                                     prompt=self._worker_prompt(attempt_id,
                                                                branch))
            entry["spec"] = {
                "run_id": spec.run_id, "job_id": spec.job_id,
                "worker_id": spec.worker_id,
                "workspace_path": str(spec.workspace_path),
                "run_dir": str(spec.run_dir),
                "prompt": spec.prompt, "model": spec.model}
            self._save_frozen()
            # F1 (attack review): durable proof of WHETHER adapter.start was
            # ever called for this attempt.  A crash before this flag and
            # without a receipt means the launch NEVER HAPPENED (the fresh
            # door may lawfully start it — still one launch); a crash AFTER
            # the flag without a receipt leaves the launch UNCERTAIN and the
            # attempt must be parked, never re-launched from this door.
            launch_flag = (self.root / "run" / "jobs" / attempt_id
                           / "launch-attempted")
            launch_flag.write_text(_now(), encoding="utf-8")
            ref = asyncio.run(adapter.start(spec))
            entry["provider_session_id"] = ref.provider_session_id
            entry["phase"] = "launched"
            self._save_frozen()
            _log(f"launched ONE native thread {ref.provider_session_id}")
        else:
            # F3 (R4b review): read the attempt's status FIRST.  A crash
            # after complete_attempt committed but before phase="sealed"
            # was saved leaves the entry "launched" over a TERMINAL
            # attempt; adopting it raises StateConflict and misreported a
            # succeeded job as EXECUTOR_FAILED.  A terminal attempt is
            # finished as sealed — and the seam is re-driven inside
            # _finish_sealed when its receipt event never landed (the
            # receipt command id and the comment marker make that
            # idempotent).
            row = runtime.attempts.get_attempt(attempt_id)
            row_status = getattr(row, "status", None) if row else None
            row_status_value = (getattr(row_status, "value", str(row_status))
                                if row_status is not None else "")
            if row_status_value in TERMINAL_ATTEMPT_STATUSES:
                entry["phase"] = "sealed"
                self._save_frozen()
                _log(f"attempt {attempt_id} is already terminal "
                     f"({row_status_value}); finishing as sealed")
                self._finish_sealed(runtime, entry)
                return
            # Recovery continuation.  The persisted adapter receipt decides
            # the lane: no receipt at all falls to the launch windows (F1
            # first launch / F13 uncertainty); a receipt hands the attempt
            # to the ENGINE's reconcile (F15) — the door never adopts.
            from control_plane.t3_execution_adapter import (
                SQLiteT3AdapterStateStore,
            )
            store = SQLiteT3AdapterStateStore(self._adapter_store_path())
            run = store.load_run(attempt_id)
            launch_flag = (self.root / "run" / "jobs" / attempt_id
                           / "launch-attempted")
            if run is None or run.spec is None or run.original_ref is None:
                if launch_flag.exists():
                    # the launch was ATTEMPTED but left no durable receipt:
                    # whether the native thread started is unknowable here.
                    # Park the attempt honestly; never guess, never re-launch.
                    # F13 (R4b review): the thread slot is NOT released —
                    # the native thread may still be running; it returns
                    # only when the attempt is reconciled terminal.
                    entry["phase"] = "launch-uncertain"
                    entry["blocker"] = {
                        "code": "LAUNCH_UNCERTAIN",
                        "reason": "the previous door died attempting the "
                                  "launch before its receipt was durable; "
                                  "whether the native thread started is "
                                  "unknown — the attempt is left to "
                                  "lease-expiry reconciliation, never "
                                  "re-launched from this door"}
                    self._save_frozen()
                    self._surface_blocker(entry, "LAUNCH_UNCERTAIN",
                                          entry["blocker"]["reason"])
                    return
                # F1: no receipt AND no launch was ever attempted — the
                # claim's lease is still held by this door's persisted
                # credentials, so START the claimed attempt now.  This is
                # the attempt's first and only launch.
                adapter, _box = self._compose_adapter(request, branch,
                                                      fresh=False)
                spec = self._launch_spec(
                    run_id=attempt_id, job_id=job_id,
                    prompt=self._worker_prompt(attempt_id, branch))
                launch_flag.write_text(_now(), encoding="utf-8")
                _log(f"launch of {attempt_id} was never attempted; starting "
                     "the claimed attempt now (its first launch)")
                ref = asyncio.run(adapter.start(spec))
                entry["provider_session_id"] = ref.provider_session_id
                entry["phase"] = "launched"
                self._save_frozen()
                _log(f"launched ONE native thread {ref.provider_session_id}")
                self._seal_and_deliver(runtime, entry, attempt_id, adapter,
                                       ref, branch)
                return
            # F15 (R4b review) + attack F8: the ENGINE is the one recovery
            # owner.  The door never reattaches, records or adopts itself;
            # it drives the composed supervisor's reconcile_restart for
            # THIS attempt and finishes from the recovered ActiveRun.
            run = self._recovered.pop(attempt_id, None)
            if run is None:
                current = runtime.attempts.get_attempt(attempt_id)
                if (getattr(current, "provider_session_id", None)
                        or "worker_recovery_binding" in (
                            getattr(current, "launch_metadata", None) or {})):
                    # an engine recovery already owns this run (the
                    # service's startup reconcile adopted it, or an earlier
                    # executor pass did): the door watches for the terminal
                    # row and finishes only the delivery read — re-driving
                    # reconcile here could fence that live finisher's lease
                    if entry.get("phase") != "engine-owned":
                        entry["phase"] = "engine-owned"
                        self._save_frozen()
                        _log(f"attempt {attempt_id} is owned by an engine "
                             "recovery; watching for the terminal row")
                    else:
                        entry["reconcile_last_ask"] = _now()
                        self._save_frozen()
                    return
                outcomes = self._reconcile(
                    runtime, frozenset({attempt_id}))
                run = self._recovered.pop(attempt_id, None)
            if run is None:
                outcome = next(
                    (o for o in outcomes
                     if getattr(o, "attempt_id", None) == attempt_id), None)
                status = (getattr(getattr(outcome, "status", None),
                                  "name", "") if outcome is not None else "")
                if outcome is None:
                    # reconcile never reported this attempt (composition
                    # unavailable or a transient failure): retry on the
                    # cadence with the entry's wake intact
                    entry["reconcile_last_ask"] = _now()
                    self._save_frozen()
                    return
                if status == "AWAITING_LEASE_EXPIRY":
                    # the crashed claimant's lease is still live: the
                    # engine's own proof discipline defers adoption; the
                    # periodic reconcile adopts at expiry and routes the
                    # recovered run back to this entry
                    if entry.get("phase") != "awaiting-lease-expiry":
                        entry["phase"] = "awaiting-lease-expiry"
                        _log(f"engine deferred {attempt_id} to lease expiry "
                             "(a live launcher may still record)")
                    entry["reconcile_last_ask"] = _now()
                    self._save_frozen()
                    return
                if status in ("RECEIPT_RECOVERED", "LIVE_RECOVERED",
                              "TERMINAL_RECOVERED", "ALREADY_RECOVERED"):
                    # recovered but the ActiveRun is not in hand (a second
                    # consumer or a fresh process): the row now carries the
                    # identity, so the engine-owned watch below takes over
                    entry["phase"] = "engine-owned"
                    entry["reconcile_last_ask"] = _now()
                    self._save_frozen()
                    return
                # a typed engine quarantine: the execution is preserved and
                # the blocker is the job's honest result (the slot holds —
                # the receipt proved a live native execution)
                entry["phase"] = "reconcile-quarantined"
                entry["blocker"] = {
                    "code": f"RECONCILE_{status}" if status
                            else "RECONCILE_REFUSED",
                    "reason": ((outcome.error or status or
                                "restart reconciliation refused this attempt")
                               [:400])}
                entry["reconcile_last_ask"] = _now()
                self._save_frozen()
                _log(f"engine quarantined {attempt_id}: {status}")
                self._surface_blocker(entry, entry["blocker"]["code"],
                                      entry["blocker"]["reason"])
                return
            # the engine adopted the SAME attempt under its receipt: seal
            # from the ENGINE's lease and the engine-reattached ref.
            entry["fence_generation"] = run.lease.attempt.fence_generation
            entry["lease_token"] = run.lease.lease_token
            entry["provider_session_id"] = run.process_ref.provider_session_id
            entry["phase"] = "reattached"
            self._save_frozen()
            _log(f"engine recovered {attempt_id} under fence "
                 f"{run.lease.attempt.fence_generation} "
                 f"({run.process_ref.provider_session_id})")
            adapter, _box = self._compose_adapter(request, branch, fresh=False)
            self._seal_and_deliver(runtime, entry, attempt_id, adapter,
                                   run.process_ref, branch)
            return

        self._seal_and_deliver(runtime, entry, attempt_id, adapter, ref,
                               branch)

    def _seal_and_deliver(self, runtime, entry, attempt_id, adapter, ref,
                          branch) -> None:
        """The shared tail: wait terminal, collect, seal through the
        execution-return seam, then read the delivery receipt honestly."""
        statuses, final = self._wait_terminal(adapter, ref)
        _log(f"attempt {attempt_id} terminal: {final.value} "
             f"({statuses})")

        collected = asyncio.run(adapter.collect_result(ref))
        output = dict(collected.result.structured_output or {})
        summary = str(output.get("text", ""))[:8000]
        artifacts = list(output.get("artifacts") or []) or [
            f"branch:{branch}", f"thread:{ref.provider_session_id}"]

        # --- the execution-return seam, installed per seal with THIS job's
        # adapter; the paperclip_task transport is registered unless the
        # undeliverable scenario deliberately withholds it.
        registry = ResultDeliveryRegistry()
        if self.config.register_transport:
            from control_plane.paperclip_result_delivery import (
                PaperclipResultDeliveryTransport,
            )
            registry.register(CARRIER_KIND, PaperclipResultDeliveryTransport(
                base_url=self.config.paperclip_base,
                headers=self.config.paperclip_headers,
                state_dir=self.root / "run" / "delivery"))
        install_execution_return_seam(
            runtime, registry=registry,
            github=GitHubEvidenceSource(
                repository=self.config.repository, port=GhCliEvidencePort()),
            t3_adapter=adapter)

        sealed = runtime.attempts.complete_attempt(
            attempt_id, fence_generation=entry["fence_generation"],
            lease_token=entry["lease_token"],
            payload={"summary": summary, "artifacts": artifacts})
        if self.config.crash_mode == "after_seal":
            # the second deterministic window (T4c): the seal is COMMITTED
            # in the engine, the frozen entry still says "launched" — a
            # FRESH door must finish it as sealed with the result comment
            # EXACTLY once (F3's terminal-row check + the seam's single
            # re-drive).  Same marker discipline as the after_receipt hook.
            (self.root / "run" / "crash").write_text(json.dumps(
                {"crashed": _now(), "window": "after_seal",
                 "attempt_id": attempt_id}), encoding="utf-8")
            os._exit(91)  # noqa: PLW0160 - the deterministic crash point
        entry["phase"] = "sealed"
        entry["final_status"] = getattr(sealed.status, "value",
                                        str(sealed.status))
        self._save_frozen()
        self._finish_sealed(runtime, entry)

    def _finish_sealed(self, runtime, entry) -> None:
        """Read the seam's delivery receipt and finish the entry (F6): the
        seam fired inside complete_attempt, so this is bookkeeping only —
        callable again after a crash between the seal and this read.

        F3 (R4b review): when the receipt event is MISSING (a crash inside
        the post-commit window), the seam is re-driven ONCE from the
        terminal rows — the receipt command id (events UNIQUE) and the
        comment marker make a second drive impossible to double-post."""
        attempt_id = entry.get("attempt_id")
        job_role = (f"job:{entry.get('job_id')}"
                    if entry.get("job_id") else None)
        events = [
            e for e in runtime.store.list_events(
                command_id_prefix=execution_return_receipt_command_id(
                    attempt_id))
            if e.attempt_id == attempt_id]
        if not events:
            self._redrive_return_seam(runtime, entry)
            events = [
                e for e in runtime.store.list_events(
                    command_id_prefix=execution_return_receipt_command_id(
                        attempt_id))
                if e.attempt_id == attempt_id]
        receipt = dict(events[0].payload) if events else {}
        delivery = dict(receipt.get("delivery") or {})
        entry["delivery"] = {
            "state": delivery.get("state"),
            "refusal_code": delivery.get("refusal_code"),
            "transport_ref": delivery.get("transport_ref"),
        }
        if delivery.get("state") == "delivered":
            entry["phase"] = "delivered"
        else:
            entry["phase"] = "delivery-refused"
            entry["blocker"] = {
                "code": delivery.get("refusal_code")
                or ("DELIVERY_RECEIPT_MISSING" if not events
                    else "DELIVERY_REFUSED"),
                "reason": f"return could not be delivered "
                          f"({delivery.get('refusal_code') or delivery.get('state') or 'no receipt'})"}
            self._surface_blocker(entry, entry["blocker"]["code"],
                                  entry["blocker"]["reason"])
        self._save_frozen()
        if job_role:
            self._release_thread(job_role)
        _log(f"sealed {attempt_id}: delivery "
             f"{entry['delivery'].get('state')}")

    def _redrive_return_seam(self, runtime, entry) -> None:
        """F3 (R4b review): re-install the execution-return seam with THIS
        job's transport and deliver once from the terminal rows.  Never
        raises; a seam that can do nothing honest records its own typed
        refusal receipt (or nothing, which _finish_sealed reports as
        DELIVERY_RECEIPT_MISSING — never as success)."""
        attempt_id = entry.get("attempt_id")
        if not attempt_id:
            return
        row = runtime.attempts.get_attempt(attempt_id)
        job = (runtime.jobs.get_job(row.job_id)
               if row is not None and row.job_id else None)
        if job is None:
            return
        _log(f"no delivery receipt for {attempt_id}; re-driving the seam "
             "once from the terminal rows")
        request = ChildExecutionRequest.from_dict(dict(entry["envelope"]))
        branch = f"t3/mmos-t4b-job-{request.request_digest[:8]}"
        adapter, _box = self._compose_adapter(request, branch, fresh=False)
        registry = ResultDeliveryRegistry()
        if self.config.register_transport:
            from control_plane.paperclip_result_delivery import (
                PaperclipResultDeliveryTransport,
            )
            registry.register(CARRIER_KIND, PaperclipResultDeliveryTransport(
                base_url=self.config.paperclip_base,
                headers=self.config.paperclip_headers,
                state_dir=self.root / "run" / "delivery"))
        wiring = install_execution_return_seam(
            runtime, registry=registry,
            github=GitHubEvidenceSource(
                repository=self.config.repository, port=GhCliEvidencePort()),
            t3_adapter=adapter)
        try:
            wiring.deliver(job=job, status=row.status)
        except Exception as exc:  # noqa: BLE001 - the seal is already durable
            _log(f"return-seam re-drive failed for {attempt_id}: "
                 f"{type(exc).__name__}: {exc}")

    def _close_launch_uncertainty(self, runtime, entry) -> None:
        """F13 (R4b review): a launch-uncertain attempt holds its thread
        slot until the attempt is reconciled.  The engine's recovery path
        owns that transition; the slot returns exactly when the attempt
        row reaches a terminal status (and only once)."""
        if entry.get("uncertainty_closed"):
            return
        attempt_id = entry.get("attempt_id")
        row = runtime.attempts.get_attempt(attempt_id) if attempt_id else None
        status = getattr(row, "status", None) if row is not None else None
        value = getattr(status, "value", str(status)) if status else ""
        if value not in TERMINAL_ATTEMPT_STATUSES:
            return  # still live or unknown: the slot stays held
        job_role = (f"job:{entry.get('job_id')}"
                    if entry.get("job_id") else None)
        entry["uncertainty_closed"] = _now()
        self._save_frozen()
        if job_role:
            self._release_thread(job_role)
        _log(f"launch-uncertain attempt {attempt_id} reconciled terminal "
             f"({value}); its thread slot returned")

    # ------------------------------------------- engine shapes (canary's)

    def _spec(self, request) -> dict:
        return {
            "child_execution_request": request.to_dict(),
            "effective_complexity": request.requested_complexity,
            "registry_revision": REGISTRY_REVISION,
            "route": {"provider_ref": "t3", "pool_ref": "glm",
                      "adapter_id": "t3-native"},
            "shared_quota_resource_refs": [QUOTA_REF],
            "root_concurrency_limit": 32,
        }

    def _observations(self):
        # same owner module the canary imports these from
        from control_plane.executive_placement_authority import (
            HostObservation, PlacementObservations, SharedQuotaObservation,
        )
        now = int(time.time() * 1000)
        return PlacementObservations(
            registry_revision=REGISTRY_REVISION, observed_at_ms=now,
            hosts={HOST_ID: HostObservation(
                host_id=HOST_ID, boot_id="boot-t4b-door",
                eligible_slots=1, observed_at_ms=now)},
            shared_quota={QUOTA_REF: SharedQuotaObservation(
                resource_ref=QUOTA_REF, per_account_cap=4,
                external_active_leases=0)})

    def _intent(self, request) -> dict:
        from control_plane.fabric_placement_policy import PLACEMENT_INTENT_SCHEMA
        return {
            "schema": PLACEMENT_INTENT_SCHEMA,
            "root_run_id": request.root_ref.split("/", 1)[-1],
            "immediate_parent_run_id":
                request.immediate_parent_run_ref.split("/", 1)[-1],
            "logical_child_id": request.logical_child_key,
            "operation_id": f"t4b-op-{request.logical_child_key}",
            "actor_role": "child", "runtime_kind": "t3-native",
            "preferred_host": HOST_ID,
        }

    def _launch_spec(self, *, run_id: str, job_id: str, prompt: str):
        from control_plane.worker_execution_contract import WorkerLaunchSpec
        run_dir = self.root / "run" / "jobs" / run_id
        (run_dir / "input").mkdir(parents=True, exist_ok=True)
        # F11: the run tree is owner-only
        os.chmod(self.root / "run" / "jobs", 0o700)
        os.chmod(run_dir, 0o700)
        os.chmod(run_dir / "input", 0o700)
        (run_dir / "input" / "prompt.txt").write_text(prompt, encoding="utf-8")
        os.chmod(run_dir / "input" / "prompt.txt", 0o600)
        # F15 (R4b review): the engine's receipt-recovery path re-verifies
        # the prompt bytes at this exact name when it rebuilds the recovery
        # binding for an identity-less claim (supervisor law), so the
        # canonical copy rides the engine's name too — same bytes.
        (run_dir / "input" / "worker-prompt.txt").write_text(
            prompt, encoding="utf-8")
        os.chmod(run_dir / "input" / "worker-prompt.txt", 0o600)
        return WorkerLaunchSpec(
            run_id=run_id, job_id=job_id, worker_id=WORKER_ID,
            workspace_path=self.root / "run" / "jobs" / f"{run_id}-ws",
            run_dir=run_dir, prompt=prompt,
            result_schema_path=run_dir / "input" / "schema.json",
            model=self.config.t3_model_selection)

    def _worker_prompt(self, attempt_id: str, branch: str) -> str:
        return (
            "T4B CODING JOB (Executive attempt "
            f"{attempt_id}). You are the worker of one governed coding job "
            "from a Paperclip task; your reply is the job's evidence. Work "
            "in THIS repository worktree only. Do exactly this:\n"
            f"1. Create the file integrations/mmos/canary/"
            f"T4B_JOB_{attempt_id}.md containing exactly one line:\n"
            f"{attempt_id}\n"
            "2. Commit ONLY that file with message:\n"
            f"t4b: coding job {attempt_id}\n"
            "3. Push the commit to origin on a NEW branch named exactly:\n"
            f"{branch}\n"
            f"(git push origin HEAD:refs/heads/{branch}). Do NOT open a "
            "pull request. Push nothing else.\n"
            "4. Reply with exactly ONE line and nothing else:\n"
            f"T4B-JOB-OK {attempt_id} <full 40-char commit sha you pushed>\n"
        )

    # ------------------------------------------------------ blocker surface

    def _surface_blocker(self, entry: dict, code: str, reason: str) -> None:
        """ONE blocker comment per code on the task (an Executive-side act).
        The payload is persisted before the post so a later wake can retry
        the POST alone (F6) — never a re-execution; if Paperclip stays
        unreachable the frozen record is the honest residue."""
        issue = entry.get("issue") or {}
        issue_id = issue.get("id")
        entry["blocker"] = {"code": code, "reason": str(reason)[:200]}
        if not issue_id:
            return
        if entry.get("blocker_surfaced") == code:
            return  # already on the task; the executor's retry must not spam
        # F4 (R4b review): every comment the door writes starts with the
        # line `[coding-job]` — the carrier (lane CQ) filters that prefix
        # from board notes, board feedback and answers, so door words can
        # never reach a teammate as the board's.
        body = (f"[coding-job] coding job blocked — {code}\n\n{reason}\n\n"
                f"frozen command: `{(entry.get('command') or '')[:80]}`\n"
                f"at {_now()}")
        try:
            self.paperclip.add_comment(issue_id, body)
            entry["blocker_surfaced"] = code
            _log(f"blocker {code} surfaced on {issue.get('identifier')}")
        except Exception as exc:  # noqa: BLE001 - unreachable task is honest
            _log(f"blocker surface failed for {issue.get('identifier')}: "
                 f"{type(exc).__name__}: {exc}")
        self._save_frozen()

    # ----------------------------------------------------------- shutdown

    async def stop(self) -> None:
        self._stopping.set()
        self._wake.set()
        if self._executor_thread is not None:
            self._executor_thread.join(timeout=5.0)
        if self.service is not None:
            await self.service.close()
        if self.operator_listener is not None:
            self.operator_listener.stop()
        backup = getattr(self, "_t3_env_backup", None)
        if backup is not None:
            self._restore_t3_env(backup)
            self._t3_env_backup = None


class _DoorInspector:
    """The canary's inert ProcessInspector shape for the door's adapter."""

    def boot_session_id(self) -> str:
        return "t4b-door-boot-1"

    def identity(self, pid: int) -> tuple[str, int]:
        return (f"t4b-door-identity-{pid}", pid)

    def inspect(self, pid: int) -> object:
        return {"pid": pid, "door": True}


# ---------------------------------------------------------------------------
# The operator-socket ASGI app (the carrier's one-call door)
# ---------------------------------------------------------------------------


class CodingJobDoorApp:
    """Socket-only ASGI app behind LocalOperatorListener (kernel peer uid).

    Routes (nothing else, no query strings):
      POST /paperclip/coding-job/admit   {"command": "..."}
      GET  /paperclip/coding-job/state/<command>
    """

    _MAX_BODY = 1 << 20

    def __init__(self, door: CodingJobDoor):
        self._door = door

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            return
        path, method = scope.get("path"), scope.get("method")
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] != "http.request":
                break
            body += message.get("body", b"")
            if len(body) > self._MAX_BODY or not message.get("more_body", False):
                break
        if scope.get("query_string"):
            await self._json(send, 404, {"ok": False, "error": "not_found"})
            return
        if path == "/paperclip/coding-job/admit" and method == "POST":
            try:
                payload = json.loads(bytes(body) or b"{}")
            except ValueError:
                await self._json(send, 400, {"ok": False, "error": {
                    "code": "invalid_input", "message": "body must be JSON"}})
                return
            command = payload.get("command")
            if not isinstance(command, str) or not command.strip():
                await self._json(send, 400, {"ok": False, "error": {
                    "code": "invalid_input",
                    "message": "a frozen coding-job command is required"}})
                return
            reply = await self._door.admit(command.strip())
            # F11 (attack review): the JSON body is this socket's contract
            # (ok/result/error); a refusal is a 200 with ok=false so the
            # carrier always gets the exact reason, never a bare status.
            await self._json(send, 200, reply)
            return
        if (path.startswith("/paperclip/coding-job/state/")
                and method == "GET" and len(path.rsplit("/", 1)) == 2):
            command = path.rsplit("/", 1)[1]
            await self._json(send, 200, self._door.job_state(command))
            return
        await self._json(send, 404, {"ok": False, "error": "not_found"})

    async def _json(self, send, status, payload):
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        await send({"type": "http.response.start", "status": status,
                    "headers": [(b"content-type", b"application/json"),
                                (b"cache-control", b"no-store"),
                                (b"content-length",
                                 str(len(raw)).encode("ascii"))]})
        await send({"type": "http.response.body", "body": raw})


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


async def _serve(config: DoorConfig) -> None:
    door = CodingJobDoor(config)
    await door.start()
    stop = asyncio.get_running_loop().create_future()

    def _sig(*_args):
        stop.set_result(None)

    import signal
    signal.signal(signal.SIGINT, _sig)
    signal.signal(signal.SIGTERM, _sig)
    try:
        while not stop.done():
            door.intake_poll_once()
            try:
                await asyncio.wait_for(
                    asyncio.shield(stop),
                    timeout=config.intake_poll_seconds)
            except asyncio.TimeoutError:
                continue
    finally:
        await door.stop()
        _log("door down")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("command", nargs="?", default="serve",
                        choices=("serve",))
    args = parser.parse_args(argv)
    config = DoorConfig.load(args.config)
    # The per-root cap can never bind this door (one job key per root); the
    # fleet cap is the queue-full case a busy dev Executive actually hits.
    if config.ready_limit is not None:
        os.environ["MMOS_CHILD_ROOT_READY_LIMIT"] = str(config.ready_limit)
    if config.fleet_limit is not None:
        os.environ["MMOS_CHILD_FLEET_READY_LIMIT"] = str(config.fleet_limit)
    asyncio.run(_serve(config))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

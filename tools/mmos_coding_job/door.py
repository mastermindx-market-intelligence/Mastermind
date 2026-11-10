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


def _log(message: str) -> None:
    print(f"[t4b-door] {message}", flush=True)  # secrets never logged


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def loopback_only(url: str, what: str) -> str:
    """The dev boundary law: only a loopback http base, ever."""
    if not url.startswith("http://127.0.0.1:") and not url.startswith(
            "http://localhost:"):
        raise ValueError(f"{what} must be a loopback http url, got {url!r}")
    return url.rstrip("/")


# The dev T3 server's port range (tools/mmos_dev/t3_dev.sh).  The live T3
# app (3773/3774), the team server (3780) and installed Paperclip (3100)
# are never legal targets for this door.  The pairing helper's CLI leg
# selects its server by T3CODE_HOME/T3CODE_PORT, NOT by the base URL —
# so those must be configured, required, and provably the SAME server as
# the HTTP base, or the CLI would silently mint against the live app.
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
        self.paperclip_company_id = str(values["paperclip_company_id"])
        self.paperclip_headers = dict(values.get("paperclip_headers") or {})
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


class DoorSupervisor:
    """The service's supervisor stand-in (the ingress fixture's shape)."""

    def __init__(self, runtime: Runtime):
        self.runtime = runtime

    def reconcile_restart(self, *, requeue_lost: bool = False):
        return []

    async def start_job(self, job_id: str):  # pragma: no cover - unused path
        raise RuntimeError("the door executor owns launches, not the service")


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
        (self.root / "run").mkdir(parents=True, exist_ok=True)
        self.paperclip = PaperclipLoopbackClient(config)
        self.frozen_path = self.root / "run" / "frozen.json"
        # command -> {"issue": {...issue fields...}, "envelope": {...}}
        self.frozen: dict[str, dict] = self._load_frozen()
        self.service: ExecutiveControlService | None = None
        self.host = None
        self.target = build_target()
        self.operator_listener = None
        self._stopping = threading.Event()
        self._executor_thread: threading.Thread | None = None
        self._wake = threading.Event()
        self.launch_census = self.root / "run" / "native-census.jsonl"
        self._budget = self.root / "run" / "thread-budget.json"

    # ------------------------------------------------------------- durable

    def _load_frozen(self) -> dict:
        if self.frozen_path.exists():
            return json.loads(self.frozen_path.read_text(encoding="utf-8"))
        return {}

    def _save_frozen(self) -> None:
        # F5 (attack review): write-temp-then-rename — a crash mid-write must
        # never leave a truncated frozen.json, or the next door cannot start
        # and every frozen job is lost with it.
        tmp = self.frozen_path.with_name("frozen.json.tmp")
        tmp.write_text(
            json.dumps(self.frozen, indent=2, sort_keys=True),
            encoding="utf-8")
        os.replace(tmp, self.frozen_path)

    def _reserve_thread(self, role: str) -> bool:
        budget = (json.loads(self._budget.read_text())
                  if self._budget.exists()
                  else {"limit": THREAD_BUDGET, "reserved": []})
        if role in budget["reserved"]:
            return True
        if len(budget["reserved"]) >= budget["limit"]:
            return False
        budget["reserved"].append(role)
        self._budget.write_text(json.dumps(budget), encoding="utf-8")
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
            self._budget.write_text(json.dumps(budget), encoding="utf-8")

    # ------------------------------------------------------- service setup

    async def start(self) -> None:
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
            cfg, supervisor_factory=lambda runtime: DoorSupervisor(runtime),
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
        """Freeze one envelope for one task (registration, not admission)."""
        issue_id = str(issue_row.get("id") or "")
        if not issue_id:
            return None
        request = build_task_request(
            issue_id=issue_id,
            agent_id=issue_row.get("assigneeAgentId") or "unknown-agent",
            company_id=self.config.paperclip_company_id,
            title=issue_row.get("title") or "",
            description=issue_row.get("description") or "",
            key=DEFAULT_JOB_KEY)
        command = task_command(request)
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
        # F3 (attack review): the request (the carrier's ONE call) is durable
        # BEFORE the engine is asked, so a crash mid-call is recoverable.
        # Freezing at intake is REGISTRATION, never a request — the door
        # must not admit a task nobody asked for (the live default-journey
        # re-run caught exactly that inversion).
        entry["admit_requested_at"] = _now()
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
            return  # answered; the carrier retries on its next wake
        code = outcome if outcome != "UNKNOWN" else "ADMISSION_REFUSED"
        reason = (f"the Executive refused re-admission of the frozen job "
                  f"({outcome})")
        entry["phase"] = "admission-refused"
        entry["blocker"] = {"code": code, "reason": reason[:200]}
        self._save_frozen()
        self._surface_blocker(entry, code, reason[:200])

    def _record_census(self, tool: str, arguments: dict) -> None:
        with self.launch_census.open("a", encoding="utf-8") as fh:
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
        self._t3_env_backup = self._apply_t3_env()
        from integrations.t3.live_proof import t3_live_proof as proof

        runtime = Runtime.at(self.root / "runtime", clock=lambda: int(
            time.time() * 1000), lease_seconds=LEASE_SECONDS)
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
                proof.obtain_mcp_access_token(
                    str(self.config.t3_token_path),
                    self.config.t3_token_label)
                break
            except Exception as exc:  # noqa: BLE001 - dev server may be down
                _log(f"worker token unavailable (dev T3 server down?): "
                     f"{type(exc).__name__}: {exc}")
                self._stopping.wait(timeout=10.0)

        while not self._stopping.is_set():
            self._wake.wait(timeout=2.0)
            self._wake.clear()
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
                     "admission-refused")

    def _entry_action(self, entry: dict) -> str:
        """One bounded routing decision per frozen entry per wake (F6).

        Registration is not a request: a frozen entry nobody's carrier call
        named stays parked until its admit call arrives (and a WAIT or a
        refusal was already answered — the carrier retries, not the door)."""
        phase = entry.get("phase")
        if phase == "delivered":
            return "skip"
        if entry.get("blocker_surfaced"):
            # the blocker is the job's recorded result on the task; a
            # surfaced blocker is terminal for this executor
            return "skip"
        if not entry.get("job_id"):
            if not entry.get("admit_requested_at"):
                return "skip"   # registered only; nobody asked for a job
            if entry.get("admit_outcome"):
                return "skip"   # answered (WAIT/refusal); the carrier owns retry
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
                time.time() * 1000), lease_seconds=LEASE_SECONDS),
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
            composed = compose_child_execution(
                runtime, request=request, spec=self._spec(request),
                branch=branch)
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
            # Recovery continuation.  The persisted adapter receipt proves
            # the launch took effect: reattach with the retained ref — ZERO
            # native calls — then record the provider-managed process (only
            # if the identity is not already durable, F2) and adopt the
            # lease under a new fence (the canary's MAIN-P2 path).
            from control_plane.worker_execution_contract import WorkerRecoveryBinding
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
                    self._release_thread(f"job:{job_id}")
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
            adapter, _box = self._compose_adapter(request, branch, fresh=False)
            ref = asyncio.run(adapter.reattach(
                run.spec, WorkerRecoveryBinding.bind(
                    adapter_id="t3-native", spec=run.spec,
                    process_ref=run.original_ref,
                    prompt_path=run.spec.run_dir / "input" / "prompt.txt")))
            _log(f"reattached {attempt_id} -> {ref.provider_session_id} "
                 "(zero native calls)")
            # F2 (attack review): a crash AFTER record_process left the
            # identity durable on the row; recording again is a hard
            # StateConflict that would misreport a succeeded job.  Only the
            # adoption is owed when the identity is already there.
            row = runtime.attempts.get_attempt(attempt_id)
            recorded_session = getattr(row, "provider_session_id", None)
            if not recorded_session and not getattr(row, "pid", None):
                runtime.attempts.record_process(
                    attempt_id,
                    fence_generation=entry["fence_generation"],
                    lease_token=entry["lease_token"],
                    provider_session_id=ref.provider_session_id,
                    launch_metadata={})
            elif (recorded_session is not None
                    and recorded_session != ref.provider_session_id):
                raise RuntimeError(
                    f"attempt {attempt_id} holds provider identity "
                    f"{recorded_session!r}, reattach read "
                    f"{ref.provider_session_id!r}; refusing to rewrite")
            adopted = runtime.attempts.adopt_attempt(
                attempt_id,
                expected_fence_generation=entry["fence_generation"],
                lease_owner="t4b-door-recovery")
            entry["fence_generation"] = adopted.attempt.fence_generation
            entry["lease_token"] = adopted.lease_token
            entry["phase"] = "reattached"
            self._save_frozen()
            _log(f"adopted {attempt_id} under fence "
                 f"{adopted.attempt.fence_generation}")

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
        entry["phase"] = "sealed"
        entry["final_status"] = getattr(sealed.status, "value",
                                        str(sealed.status))
        self._save_frozen()
        self._finish_sealed(runtime, entry)

    def _finish_sealed(self, runtime, entry) -> None:
        """Read the seam's delivery receipt and finish the entry (F6): the
        seam fired inside complete_attempt, so this is bookkeeping only —
        callable again after a crash between the seal and this read."""
        attempt_id = entry.get("attempt_id")
        job_role = (f"job:{entry.get('job_id')}"
                    if entry.get("job_id") else None)
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
                "code": delivery.get("refusal_code") or "DELIVERY_REFUSED",
                "reason": f"return could not be delivered "
                          f"({delivery.get('refusal_code') or delivery.get('state')})"}
            self._surface_blocker(entry, entry["blocker"]["code"],
                                  entry["blocker"]["reason"])
        self._save_frozen()
        if job_role:
            self._release_thread(job_role)
        _log(f"sealed {attempt_id}: delivery "
             f"{entry['delivery'].get('state')}")

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
        (run_dir / "input" / "prompt.txt").write_text(prompt, encoding="utf-8")
        os.chmod(run_dir / "input" / "prompt.txt", 0o600)
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
        body = (f"[t4b-door] coding job blocked — {code}\n\n{reason}\n\n"
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

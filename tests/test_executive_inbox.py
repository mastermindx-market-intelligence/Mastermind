"""Executive OS Phase 1F-A tests — the read-only Executive Inbox projection.

The fourteen safety proofs, each named at its own test:

  1. Zero runtime mutations — a full logical dump of every table (plus
     ``sqlite_master``) is identical before and after ``build_inbox``
  2. The database is logically unchanged including its event log — no row is
     appended, and the AUTOINCREMENT high-water mark does not move
  3. No lifecycle operation is reachable — with ``RuntimeStore.transaction``
     booby-trapped to raise, the inbox still builds its full attention list, which
     proves it travelled the ``read()`` path only
  4. Import fence — the module imports exactly ``executive_runtime`` and
     ``ceo_boot_packet`` from ``control_plane``, and names no supervisor, broker,
     service, codex worker, or worker runtime anywhere in its source
  5. Clean completions are SUPPRESSED but COUNTED — never silently dropped
  6. Non-disappearance — the exact expected job set surfaces, with the expected
     kinds, and the suppression arithmetic reconciles against the job total
  7. ``needs_ceo`` rows survive verbatim — workstream and question, unrewritten
  8. No label elevation — an executive-department, priority-100, CEO-provenance
     job is still COO attention, and nothing produces a chairman item
  9. Degraded honesty — a missing database, a bubbled boot-packet warning, and an
     uncollected boot packet each land as a named entry
 10. Determinism — same state plus same ``now`` is byte-identical
 11. Unknown status degrades VISIBLY — a corrupted status closes the jobs surface
     by name rather than quietly reclassifying the row as routine; an unknown boot
     packet schema is named and produces no CEO attention
 12. No new database, table, or queue — the fixture tree is unchanged by a CLI run
 13. Existing suites stay green — a RUN receipt, not a test in this file: the
     repository test gate in ``.github/workflows/ci.yml`` is the standing proof
 14. CI wiring self-check — this file is included by discovery, not a filename pack

Plus the post-review proofs: the read-only construction path (a 0-byte husk, a
foreign SQLite file, and a `delete`-mode database are all left exactly as found),
the boot packet whose `brief` is null, LOST cause wording, stale leases, schema
drift pins, and attention-id collisions.

Hermetic: no network, no real Macro checkout, no boot-packet subprocess, and **no
git subprocess** — every test that builds an inbox takes the ``frozen_git``
fixture, which pins the two ``git rev-parse`` probes.  It patches the PRIVATE
``_git_sha``/``_git_branch`` names, which is also the standing proof that
``ceo_boot_packet``'s public ``git_sha``/``git_branch`` are wrappers rather than
import-time aliases.  The runtime fixture is built through the runtime's OWN API
with a frozen clock, and the boot packet is injected as a dict.  Raw SQL appears
only through the fixture-only ``_raw`` helper, and only where a proof needs a state
the runtime API cannot produce — never to read, and never inside the projector.
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
import sqlite3
from pathlib import Path

import pytest

from control_plane import ceo_boot_packet
from control_plane import executive_inbox as mod
from control_plane.executive_inbox import (
    BOOT_PACKET_SCHEMA,
    BRIEF_SCHEMA,
    DB_RELATIVE_PATH,
    SCHEMA,
    TARGETS,
    attention_id,
    build_inbox,
    render_inbox,
)
from control_plane.executive_runtime import (
    JobPayload,
    JobStatus,
    Runtime,
    RuntimeStore,
    StateConflict,
    WorkerStatus,
)
from control_plane.executive_runtime import _DB_RELATIVE_PATH as _RUNTIME_DB_PATH
from scripts.executive_inbox import main as cli_main

_NOW = "2026-08-14T00:00:00Z"
_REPO = Path(__file__).resolve().parent.parent

#: Durable provenance of a CEO-submitted job, shaped exactly as
#: ``control_plane.ceo_intent._provenance`` records it.
_CEO_PROVENANCE = {
    "schema": "mastermind.ceo_intent.v1",
    "intent_id": "CEO-EXEC-OS-1F-1",
    "actor": "ceo-sol",
    "fingerprint": "a" * 64,
    "grounding": {"mastermind_sha": "b" * 40, "macro_sha": "c" * 40},
    "workstream": "WS:EXECUTIVE_OS",
}
_CEO_PROVENANCE_CLEAN = dict(_CEO_PROVENANCE, intent_id="CEO-EXEC-OS-1F-2")

_NEEDS_CEO = [
    {
        "workstream": "WS:PROPHET-FUSION",
        "question": "Authorize the conditional-fusion promotion gate?",
        "options": ["authorize", "defer"],
        "recommendation": "authorize",
        "by_when": "2026-08-16",
    },
    {
        "workstream": "WS:CN-LIMIT-ALPHA",
        "question": "Authorize the bulk limit-up backfill?",
        "options": ["authorize", "defer"],
        "recommendation": "defer",
    },
]

#: Exactly which jobs the inbox must surface from the fixture, and as what.
_EXPECTED_ATTENTION = {
    "JOB-009": "job_failed",             # FAILED at its attempt limit
    "JOB-010": "job_failed",             # FAILED below its attempt limit
    "JOB-011": "job_lost",
    "JOB-012": "job_rate_limited",
    "JOB-013": "cancel_requested",
    "JOB-014": "attempts_exhausted",     # QUEUED and permanently unclaimable
    "JOB-015": "completed_with_errors",
    "JOB-016": "unresolved_next_actions",
    "JOB-017": "malformed_result_evidence",      # unparseable result
    "JOB-018": "malformed_result_evidence",      # unparseable checkpoint
    "JOB-019": "job_failed",             # CEO-submitted, executive dept, priority 100
    "JOB-021": "job_lost",               # LOST by lease expiry, not verified absence
    "JOB-022": "stale_lease",            # RUNNING, lease expired, never swept
}
_EXPECTED_SUPPRESSED = {
    "clean_completed": 4,   # JOB-001..003 plus the clean CEO-submitted JOB-020
    "queued": 2,            # JOB-004, JOB-005
    "running": 1,           # JOB-006 (live lease); JOB-022 is attention, not routine
    "checkpointed": 1,      # JOB-007
    "cancelled": 1,         # JOB-008
}
_TOTAL_JOBS = 22
_TOTAL_ATTEMPTS = 18


# ---------------------------------------------------------------------------
# fixture: a rich mixed runtime built through the runtime's own API
# ---------------------------------------------------------------------------

#: Fixture epoch: one hour BEFORE `_NOW`, so the store's own 24h leases are still
#: live at `_NOW` while a deliberately short 60s lease has already expired.  That
#: gap is what makes the stale-lease rule testable in both directions.
_FIXTURE_EPOCH_MS = 1_786_665_600_000 - 3_600_000   # 2026-08-13T23:00:00Z
_LONG_LEASE_SECONDS = 86_400
_SHORT_LEASE_SECONDS = 60


class _Clock:
    """Monotonic millisecond counter — no wall clock anywhere in the fixture."""

    def __init__(self, start: int = _FIXTURE_EPOCH_MS, step: int = 1000) -> None:
        self.value = start
        self.step = step

    def __call__(self) -> int:
        self.value += self.step
        return self.value


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _payload(**kwargs) -> JobPayload:
    return JobPayload(
        summary=kwargs.get("summary", "done"),
        completed_steps=kwargs.get("completed_steps", ["read inputs"]),
        current_state=kwargs.get("current_state", "finished"),
        artifacts=kwargs.get("artifacts", []),
        next_actions=kwargs.get("next_actions", []),
        errors=kwargs.get("errors", []),
    )


def _create(runtime: Runtime, objective: str, quota_class: str, **kwargs) -> str:
    job = runtime.jobs.create_job(
        objective,
        constraints={"eligible_quota_classes": [quota_class]},
        **kwargs,
    )
    return job.job_id


def _claim(
    runtime: Runtime,
    job_id: str,
    worker_id: str,
    quota_class: str,
    *,
    lease_seconds: int | None = None,
):
    lease = runtime.attempts.claim_job(
        job_id,
        worker_id=worker_id,
        quota_class=quota_class,
        lease_seconds=lease_seconds,
    )
    assert lease is not None, f"fixture could not claim {job_id} on {quota_class}"
    return lease


def _raw(db_path: Path, sql: str, params=(), *, ignore_checks: bool = False) -> None:
    """Fixture-only raw write.  Never used to READ — the projector uses registries."""
    connection = sqlite3.connect(db_path)
    try:
        if ignore_checks:
            connection.execute("PRAGMA ignore_check_constraints=ON")
        connection.execute(sql, params)
        connection.commit()
    finally:
        connection.close()


def build_fixture_store(root: Path) -> Runtime:
    """A mixed durable runtime: 20 jobs across all nine JobStatus values.

    Every state is DERIVED through claim/checkpoint/complete/fail/cancel/rate-limit
    calls, so the rows carry the same invariants production rows carry.  The three
    exceptions go through ``_raw`` and are explained where they happen.
    """
    clock = _Clock()
    runtime = Runtime.at(root, clock=clock, lease_seconds=_LONG_LEASE_SECONDS)
    db_path = root / DB_RELATIVE_PATH

    runtime.workers.register_worker(
        "claude-01",
        provider="claude",
        account_label="claude-a",
        worker_type="mock",
        capabilities=["research", "code"],
        quota_classes={
            name: ["research", "code"]
            for name in ("c1", "c2", "c3", "c4", "c5", "c6", "c7")
        },
    )
    runtime.workers.register_worker(
        "codex-01",
        provider="codex",
        account_label="codex-a",
        worker_type="mock",
        capabilities=["research", "code"],
        quota_classes={name: ["research", "code"] for name in ("k1", "k2", "k3")},
    )
    runtime.workers.register_worker(
        "claude-02",
        provider="claude",
        account_label="claude-b",
        worker_type="mock",
        capabilities=["research"],
        quota_classes={"c9": ["research"]},
    )
    runtime.workers.set_worker_status("claude-02", WorkerStatus.OFFLINE)
    # A dead worker: it produces no failed jobs (nothing it cannot claim can
    # fail), so it is invisible in the attention list and must show in the counts.
    runtime.workers.register_worker(
        "codex-02",
        provider="codex",
        account_label="codex-b",
        worker_type="mock",
        capabilities=["research"],
        quota_classes={"k9": ["research"]},
    )
    runtime.workers.set_worker_status("codex-02", WorkerStatus.ERROR)

    # --- creation, in id order -------------------------------------------------
    assert _create(runtime, "Clean completion A", "c1") == "JOB-001"
    assert _create(runtime, "Clean completion B", "c1") == "JOB-002"
    assert _create(runtime, "Clean completion C", "c1") == "JOB-003"
    assert _create(runtime, "Healthy queued A", "c1") == "JOB-004"
    assert _create(runtime, "Healthy queued B", "c1") == "JOB-005"
    assert _create(runtime, "In flight", "c2") == "JOB-006"
    assert _create(runtime, "Checkpointed cleanly", "c3") == "JOB-007"
    assert _create(runtime, "Cancelled while queued", "c1") == "JOB-008"
    assert _create(runtime, "Failed at the limit", "k1", attempt_limit=1) == "JOB-009"
    assert _create(runtime, "Failed below the limit", "k1", attempt_limit=3) == "JOB-010"
    assert _create(runtime, "Lost invocation", "k2") == "JOB-011"
    assert _create(runtime, "Rate limited", "k3") == "JOB-012"
    assert _create(runtime, "Cancel requested", "c4") == "JOB-013"
    assert _create(runtime, "Wedged queued", "c1", attempt_limit=1) == "JOB-014"
    assert _create(runtime, "Completed with errors", "k1") == "JOB-015"
    assert _create(runtime, "Completed with next actions", "k1") == "JOB-016"
    assert _create(runtime, "Corrupt result payload", "k1") == "JOB-017"
    assert _create(runtime, "Corrupt checkpoint payload", "c5") == "JOB-018"
    # The label-elevation bait: the highest department, the highest priority, and
    # a CEO provenance record.  It must still come back as COO attention.
    assert _create(
        runtime,
        "CEO-submitted objective that failed",
        "k1",
        attempt_limit=3,
        department="executive",
        priority=100,
        command_id="ceo-intent:test-1",
        provenance=dict(_CEO_PROVENANCE),
    ) == "JOB-019"
    assert _create(
        runtime,
        "CEO-submitted objective that finished cleanly",
        "k1",
        department="executive",
        priority=100,
        command_id="ceo-intent:test-2",
        provenance=dict(_CEO_PROVENANCE_CLEAN),
    ) == "JOB-020"
    assert _create(runtime, "Lost to lease expiry", "c6") == "JOB-021"
    assert _create(runtime, "Claimed then abandoned", "c7") == "JOB-022"

    # --- clean completions -----------------------------------------------------
    for job_id in ("JOB-001", "JOB-002", "JOB-003"):
        _claim(runtime, job_id, "claude-01", "c1")
        runtime.jobs.complete_job(job_id, _payload())

    # --- RUNNING (a real launched invocation) ----------------------------------
    lease = _claim(runtime, "JOB-006", "claude-01", "c2")
    runtime.attempts.record_process(
        lease.attempt.attempt_id,
        fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token,
        pid=4242,
        pgid=4242,
        process_start_identity="start-006",
        boot_id="boot-1",
    )
    runtime.attempts.mark_running(
        lease.attempt.attempt_id,
        fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token,
    )

    # --- CHECKPOINTED, cleanly -------------------------------------------------
    _claim(runtime, "JOB-007", "claude-01", "c3")
    runtime.jobs.checkpoint_job(
        "JOB-007", _payload(current_state="halfway", next_actions=["resume synthesis"])
    )

    # --- CANCELLED from QUEUED -------------------------------------------------
    runtime.jobs.cancel_job("JOB-008")

    # --- FAILED at the attempt limit, with a recorded exit code ----------------
    lease = _claim(runtime, "JOB-009", "codex-01", "k1")
    runtime.attempts.record_process(
        lease.attempt.attempt_id,
        fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token,
        pid=4243,
        pgid=4243,
        process_start_identity="start-009",
        boot_id="boot-1",
    )
    runtime.attempts.mark_running(
        lease.attempt.attempt_id,
        fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token,
    )
    runtime.attempts.record_process_exit(
        lease.attempt.attempt_id,
        fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token,
        exit_code=1,
    )
    runtime.jobs.fail_job(
        "JOB-009",
        _payload(
            summary="worker aborted",
            errors=["provider returned a fatal error"],
            next_actions=["re-scope the objective before another attempt"],
        ),
    )

    # --- FAILED below the attempt limit ---------------------------------------
    _claim(runtime, "JOB-010", "codex-01", "k1")
    runtime.jobs.fail_job("JOB-010", _payload(summary="transient", errors=["timeout"]))

    # --- LOST (verified-absent provider invocation) ---------------------------
    lease = _claim(runtime, "JOB-011", "codex-01", "k2")
    runtime.attempts.record_process(
        lease.attempt.attempt_id,
        fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token,
        provider_session_id="prov-session-011",
    )
    runtime.attempts.mark_lost(
        lease.attempt.attempt_id,
        fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token,
        reason="provider session disappeared",
        verified_process_absent=True,
    )

    # --- RATE_LIMITED ----------------------------------------------------------
    lease = _claim(runtime, "JOB-012", "codex-01", "k3")
    runtime.attempts.rate_limit_attempt(
        lease.attempt.attempt_id,
        fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token,
    )

    # --- CANCEL_REQUESTED (cancel issued against a live attempt) --------------
    _claim(runtime, "JOB-013", "claude-01", "c4")
    runtime.jobs.cancel_job("JOB-013")

    # --- COMPLETED with errors / with next actions ----------------------------
    _claim(runtime, "JOB-015", "codex-01", "k1")
    runtime.jobs.complete_job(
        "JOB-015",
        _payload(summary="finished with damage", errors=["3 rows failed to reconcile"]),
    )
    _claim(runtime, "JOB-016", "codex-01", "k1")
    runtime.jobs.complete_job(
        "JOB-016",
        _payload(
            summary="finished, handoff pending",
            next_actions=["publish the reconciliation note", "close WS:DEMO"],
        ),
    )

    # --- the CEO-submitted pair ------------------------------------------------
    _claim(runtime, "JOB-019", "codex-01", "k1")
    runtime.jobs.fail_job(
        "JOB-019", _payload(summary="denied upstream", errors=["authority refused"])
    )
    _claim(runtime, "JOB-020", "codex-01", "k1")
    runtime.jobs.complete_job("JOB-020", _payload())

    # --- LOST the OTHER way: a lease that ran out with nobody heart-beating ----
    # A real API path, targeted at one attempt so the long-lease attempts that
    # must stay live are not swept along with it.
    lease = _claim(
        runtime, "JOB-021", "claude-01", "c6", lease_seconds=_SHORT_LEASE_SECONDS
    )
    runtime.attempts.reconcile_expired(
        now_ms=clock.value + 2 * _SHORT_LEASE_SECONDS * 1000,
        attempt_id=lease.attempt.attempt_id,
    )

    # --- the supervisor-death signature: claimed, lease expired, never swept ---
    _claim(runtime, "JOB-022", "claude-01", "c7", lease_seconds=_SHORT_LEASE_SECONDS)

    # --- corruptions the API cannot produce -----------------------------------
    _claim(runtime, "JOB-017", "codex-01", "k1")
    runtime.jobs.complete_job("JOB-017", _payload())
    # `next_actions` must be a list; the runtime's own validator rejects this.  The
    # JSON is still a valid object, so the column CHECK accepts it and `list_jobs`
    # decodes it — exactly the shape a hand-edited or restored row would take.
    _raw(
        db_path,
        "UPDATE jobs SET result_json=? WHERE job_id=?",
        (json.dumps({"summary": "ok", "next_actions": "publish the note"}), "JOB-017"),
    )

    _claim(runtime, "JOB-018", "claude-01", "c5")
    runtime.jobs.checkpoint_job("JOB-018", _payload(current_state="halfway"))
    _raw(
        db_path,
        "UPDATE jobs SET checkpoint_json=? WHERE job_id=?",
        (json.dumps({"summary": "ok", "errors": 7}), "JOB-018"),
    )

    # JOB-014: QUEUED with its attempts used up.  No sequence of runtime calls can
    # reach this state today — `requeue_job` refuses at the limit, so the row can
    # only arrive by operator edit, restore, or a future requeue path.  The
    # projector must still name it, because the durable row is the authority and
    # the job is permanently unclaimable (asserted directly in the wedge test).
    _raw(
        db_path,
        "UPDATE jobs SET attempt_count=attempt_limit WHERE job_id=?",
        ("JOB-014",),
    )

    return runtime


@pytest.fixture
def store(tmp_path) -> Path:
    build_fixture_store(tmp_path)
    return tmp_path


@pytest.fixture
def frozen_git(monkeypatch):
    """Pin the checkout probes so a non-repo tmp fixture cannot manufacture noise.

    Patches the PRIVATE names deliberately — that is the house idiom
    (``tests/test_ceo_boot_packet.py`` does the same), and it only works because
    ``git_sha``/``git_branch`` are wrappers rather than import-time aliases.  If
    someone turns them back into aliases, every assertion on ``eeee…`` reds.
    """
    monkeypatch.setattr(ceo_boot_packet, "_git_sha", lambda path: "e" * 40)
    monkeypatch.setattr(ceo_boot_packet, "_git_branch", lambda path: "master")


def packet(*, schema: str = BOOT_PACKET_SCHEMA, needs_ceo=None, degraded=None) -> dict:
    """An injected ``mastermind.ceo_boot_packet.v1`` document (no subprocess)."""
    return {
        "schema": schema,
        "generated_at": _NOW,
        "mastermind": {"root": "/fixture/mastermind", "sha": "f" * 40, "branch": "master"},
        "macro": {
            "root": "/fixture/macro",
            "sha": "9" * 40,
            "resolved_via": "flag",
            "candidates_tried": [],
        },
        "strategic_state": {"company_phase": "phase-1", "north_star": [], "p0": []},
        "brief": {
            "schema": "ceo_brief.v1",
            "generated_at": _NOW,
            "counts": {"total": 6},
            "needs_ceo": [
                dict(row) if isinstance(row, dict) else row
                for row in (_NEEDS_CEO if needs_ceo is None else needs_ceo)
            ],
            "blocked": [],
            "inputs": {"degraded": []},
        },
        "handoffs": [],
        "degraded": list(degraded or []),
        "next_recommended_act": "Rule on 2 pending CEO decision(s).",
    }


def inbox_for(root: Path, **kwargs) -> dict:
    kwargs.setdefault("boot_packet", packet())
    kwargs.setdefault("now", _NOW)
    return build_inbox(repo_root=root, environ={}, **kwargs)


def logical_dump(db_path: Path) -> dict:
    """Every user table plus ``sqlite_master`` — the whole logical database."""
    connection = sqlite3.connect(db_path)
    try:
        dump: dict[str, list] = {
            "sqlite_master": [
                tuple(row)
                for row in connection.execute(
                    "SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name"
                )
            ]
        }
        tables = [
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
        ]
        for table in tables:
            dump[table] = [
                tuple(row)
                for row in connection.execute(f"SELECT * FROM {table} ORDER BY rowid")
            ]
        return dump
    finally:
        connection.close()


def runtime_items(inbox: dict) -> list[dict]:
    return [item for item in inbox["attention"] if item["source"] == "runtime"]


# ---------------------------------------------------------------------------
# 1. zero runtime mutations
# ---------------------------------------------------------------------------

def test_1_build_inbox_mutates_no_runtime_row(store, frozen_git):
    db_path = store / DB_RELATIVE_PATH
    before = logical_dump(db_path)
    assert before["jobs"], "fixture is empty — the comparison would pass vacuously"
    assert len(before["jobs"]) == _TOTAL_JOBS

    inbox = inbox_for(store)
    assert inbox["attention"], "an empty projection would make this proof vacuous"

    after = logical_dump(db_path)
    assert after == before
    for table, rows in before.items():
        assert after[table] == rows, f"{table} moved"


# ---------------------------------------------------------------------------
# 2. the event log is untouched, including its high-water mark
# ---------------------------------------------------------------------------

def test_2_no_event_is_appended_and_the_sequence_does_not_advance(store, frozen_git):
    db_path = store / DB_RELATIVE_PATH

    def _event_state() -> tuple:
        connection = sqlite3.connect(db_path)
        try:
            count = connection.execute("SELECT COUNT(*) FROM events").fetchone()[0]
            high = connection.execute("SELECT MAX(event_id) FROM events").fetchone()[0]
            seq = connection.execute(
                "SELECT seq FROM sqlite_sequence WHERE name='events'"
            ).fetchone()
            return count, high, (seq[0] if seq else None)
        finally:
            connection.close()

    before = _event_state()
    assert before[0] > 0
    inbox = inbox_for(store)
    assert runtime_items(inbox)
    assert _event_state() == before


# ---------------------------------------------------------------------------
# 3. no lifecycle operation — the write path is booby-trapped
# ---------------------------------------------------------------------------

def test_3_inbox_never_opens_a_write_transaction(store, frozen_git, monkeypatch):
    def _trap(self):  # pragma: no cover - raising IS the assertion
        raise AssertionError("the inbox must never open a write transaction")

    monkeypatch.setattr(RuntimeStore, "transaction", _trap)

    inbox = inbox_for(store)

    # Not merely "did not raise": the whole projection must still be there.  A
    # build that swallowed the trap into `degraded` and returned an empty skeleton
    # would otherwise read as a pass.
    assert {item["job_id"] for item in runtime_items(inbox)} == set(_EXPECTED_ATTENTION)
    assert inbox["suppressed"] == _EXPECTED_SUPPRESSED
    assert inbox["degraded"] == []


# ---------------------------------------------------------------------------
# 4. import fence
# ---------------------------------------------------------------------------

def test_4_module_imports_only_the_runtime_and_the_boot_packet():
    source = Path(mod.__file__).read_text(encoding="utf-8")
    submodules: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("control_plane."):
                    submodules.add(alias.name.split(".", 1)[1].split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            if node.module == "control_plane":
                submodules.update(alias.name for alias in node.names)
            elif node.module.startswith("control_plane."):
                submodules.add(node.module.split(".", 1)[1].split(".")[0])

    assert submodules == {"executive_runtime", "ceo_boot_packet"}, sorted(submodules)

    forbidden = (
        "executive_supervisor",
        "executive_worker_broker",
        "executive_service",
        "codex_worker",
        "worker_runtime",
        "executive_canary",
        "executive_backup",
    )
    named = [name for name in forbidden if name in source]
    assert not named, f"projection must not reference {named}"


# ---------------------------------------------------------------------------
# 5. clean completions are suppressed but counted
# ---------------------------------------------------------------------------

def test_5_clean_completions_are_suppressed_but_counted(store, frozen_git):
    inbox = inbox_for(store)

    assert inbox["suppressed"] == _EXPECTED_SUPPRESSED
    assert inbox["suppressed"]["clean_completed"] == 4

    counts = inbox["runtime_counts"]
    assert counts["jobs"]["total"] == _TOTAL_JOBS
    assert counts["jobs"]["by_status"] == {
        "QUEUED": 3,
        "RUNNING": 2,
        "CHECKPOINTED": 2,
        "RATE_LIMITED": 1,
        "FAILED": 3,
        "LOST": 2,
        "CANCEL_REQUESTED": 1,
        "COMPLETED": 7,
        "CANCELLED": 1,
    }
    # Every enum member is present with a zero rather than absent.
    assert set(counts["attempts"]["by_status"]) == {s.value for s in mod.AttemptStatus}
    assert counts["attempts"]["by_status"]["CANCELLED"] == 0
    assert counts["attempts"]["total"] == _TOTAL_ATTEMPTS
    assert counts["workers"] == {
        "total": 4,
        "by_status": {
            "AVAILABLE": 2,
            "BUSY": 0,
            "DRAINING": 0,
            "RATE_LIMITED": 0,
            "OFFLINE": 1,
            "ERROR": 1,
        },
    }
    # Four clean completions exist in the ledger and none of them is listed.
    assert not {"JOB-001", "JOB-002", "JOB-003", "JOB-020"} & {
        item["job_id"] for item in runtime_items(inbox)
    }


# ---------------------------------------------------------------------------
# 6. non-disappearance
# ---------------------------------------------------------------------------

def test_6_every_exceptional_job_surfaces_exactly_once(store, frozen_git):
    inbox = inbox_for(store)
    items = runtime_items(inbox)

    assert items, "an empty attention list would make every other assertion vacuous"
    assert [item["job_id"] for item in items] == sorted(_EXPECTED_ATTENTION)
    assert {item["job_id"]: item["kind"] for item in items} == _EXPECTED_ATTENTION
    assert len(items) == len({item["attention_id"] for item in items})

    # The audit arithmetic: suppression + attention accounts for every job.
    assert sum(inbox["suppressed"].values()) + len(items) == _TOTAL_JOBS
    assert inbox["degraded"] == []

    by_id = {item["job_id"]: item for item in items}

    # The attempt-limit clause appears only where the limit is actually reached.
    assert "requeue is refused" in by_id["JOB-009"]["reason"]
    assert "attempts exhausted (1/1)" in by_id["JOB-009"]["reason"]
    assert "requeue is refused" not in by_id["JOB-010"]["reason"]

    # Evidence is canonical, not narrated.
    assert {"ref": "job:JOB-009", "field": "status", "value": "FAILED"} in by_id[
        "JOB-009"
    ]["evidence"]
    assert {"ref": "job:JOB-009", "field": "attempt_limit", "value": "1"} in by_id[
        "JOB-009"
    ]["evidence"]
    exit_codes = [
        entry
        for entry in by_id["JOB-009"]["evidence"]
        if entry["field"] == "exit_code"
    ]
    assert exit_codes and exit_codes[0]["value"] == "1"
    assert exit_codes[0]["ref"].startswith("attempt:ATT-")

    # next_actions travel verbatim off the stored payload — never authored here.
    assert by_id["JOB-016"]["existing_next_actions"] == [
        "publish the reconciliation note",
        "close WS:DEMO",
    ]
    assert by_id["JOB-009"]["existing_next_actions"] == [
        "re-scope the objective before another attempt"
    ]
    assert by_id["JOB-010"]["existing_next_actions"] == []

    # Both malformed branches: an unparseable result and an unparseable checkpoint.
    assert "result payload" in by_id["JOB-017"]["reason"]
    assert "checkpoint payload" in by_id["JOB-018"]["reason"]
    assert by_id["JOB-018"]["status"] == "CHECKPOINTED"


def test_6b_the_wedged_queued_job_is_really_unclaimable(store, frozen_git):
    """The `attempts_exhausted` reason is a fact, not a claim: prove the refusal."""
    inbox = inbox_for(store)
    wedge = next(
        item for item in inbox["attention"] if item["job_id"] == "JOB-014"
    )
    assert wedge["kind"] == "attempts_exhausted"
    assert wedge["status"] == "QUEUED"
    assert "permanently unclaimable" in wedge["reason"]

    runtime = Runtime.at(store)
    with pytest.raises(StateConflict, match="exhausted its attempt limit"):
        runtime.attempts.claim_job("JOB-014", worker_id="claude-01", quota_class="c1")
    with pytest.raises(StateConflict):
        runtime.jobs.requeue_job("JOB-014")


# ---------------------------------------------------------------------------
# 7. needs_ceo survives verbatim
# ---------------------------------------------------------------------------

def test_7_needs_ceo_rows_survive_verbatim(store, frozen_git):
    inbox = inbox_for(store)
    ceo = [item for item in inbox["attention"] if item["target"] == "ceo"]

    assert [item["workstream"] for item in ceo] == [
        "WS:CN-LIMIT-ALPHA",
        "WS:PROPHET-FUSION",
    ]
    assert {item["reason"] for item in ceo} == {
        row["question"] for row in _NEEDS_CEO
    }
    for item in ceo:
        assert item["kind"] == "ceo_decision_pending"
        assert item["source"] == "agent_os"
        assert item["job_id"] is None and item["status"] is None
        # The row's `recommendation` is NOT re-rendered as an executive action.
        assert item["existing_next_actions"] == []
        assert {
            "ref": "agentos:needs_ceo",
            "field": "workstream",
            "value": item["workstream"],
        } in item["evidence"]
        assert {
            "ref": "boot_packet",
            "field": "schema",
            "value": BOOT_PACKET_SCHEMA,
        } in item["evidence"]

    assert inbox["grounding"]["boot_packet_schema"] == BOOT_PACKET_SCHEMA
    assert inbox["grounding"]["macro"] == {"root": "/fixture/macro", "sha": "9" * 40}


def test_7b_a_question_free_row_says_so_rather_than_inventing_one(store, frozen_git):
    inbox = inbox_for(
        store, boot_packet=packet(needs_ceo=[{"workstream": "WS:QUIET"}])
    )
    ceo = [item for item in inbox["attention"] if item["target"] == "ceo"]
    assert [item["reason"] for item in ceo] == ["question not recorded"]


def test_7c_a_malformed_needs_ceo_row_degrades_instead_of_vanishing(store, frozen_git):
    inbox = inbox_for(
        store,
        boot_packet=packet(needs_ceo=[_NEEDS_CEO[0], "not-an-object", None]),
    )
    ceo = [item for item in inbox["attention"] if item["target"] == "ceo"]
    assert len(ceo) == 1
    named = [entry for entry in inbox["degraded"] if "needs_ceo[" in entry]
    assert len(named) == 2, inbox["degraded"]
    assert "needs_ceo[1]" in named[0] and "needs_ceo[2]" in named[1]


# ---------------------------------------------------------------------------
# 8. no label elevation
# ---------------------------------------------------------------------------

def test_8_titles_departments_and_priority_confer_no_authority(store, frozen_git):
    inbox = inbox_for(store)
    items = runtime_items(inbox)

    assert all(item["target"] == "coo" for item in items)
    assert not [item for item in inbox["attention"] if item["target"] == "chairman"]
    assert {item["target"] for item in inbox["attention"]} == {"ceo", "coo"}
    assert all(
        item["source"] == "agent_os"
        for item in inbox["attention"]
        if item["target"] == "ceo"
    )

    ceo_job = next(item for item in items if item["job_id"] == "JOB-019")
    assert ceo_job["target"] == "coo"          # executive department, priority 100
    assert ceo_job["kind"] == "job_failed"
    assert ceo_job["workstream"] == "WS:EXECUTIVE_OS"   # from provenance, not a column
    assert {
        "ref": "event:JOB-019:JOB_CREATED",
        "field": "provenance.actor",
        "value": "ceo-sol",
    } in ceo_job["evidence"]
    assert {
        "ref": "event:JOB-019:JOB_CREATED",
        "field": "provenance.intent_id",
        "value": "CEO-EXEC-OS-1F-1",
    } in ceo_job["evidence"]

    # A clean CEO-submitted job produces no attention at all.
    assert "JOB-020" not in {item["job_id"] for item in items}

    # And a plain job carries no provenance evidence.
    plain = next(item for item in items if item["job_id"] == "JOB-010")
    assert plain["workstream"] is None
    assert not [e for e in plain["evidence"] if e["field"].startswith("provenance.")]


def test_8b_a_command_id_prefix_alone_is_not_ceo_provenance(tmp_path, frozen_git):
    """The `ceo-intent:` namespace is not proof — only the provenance record is."""
    runtime = Runtime.at(tmp_path, clock=_Clock(), lease_seconds=_LONG_LEASE_SECONDS)
    runtime.workers.register_worker(
        "claude-01", provider="claude", account_label="a", worker_type="mock",
        capabilities=["code"], quota_classes={"c1": ["code"]},
    )
    runtime.jobs.create_job(
        "Impostor",
        constraints={"eligible_quota_classes": ["c1"]},
        command_id="ceo-intent:impostor",
        provenance={"schema": "some.other.v1", "actor": "not-the-ceo"},
    )
    _claim(runtime, "JOB-001", "claude-01", "c1")
    runtime.jobs.fail_job("JOB-001", _payload(errors=["boom"]))

    item = next(
        i for i in inbox_for(tmp_path)["attention"] if i["job_id"] == "JOB-001"
    )
    assert item["target"] == "coo"
    assert item["workstream"] is None
    assert not [e for e in item["evidence"] if e["field"].startswith("provenance.")]


# ---------------------------------------------------------------------------
# 9. degraded honesty
# ---------------------------------------------------------------------------

def test_9a_missing_database_degrades_and_nulls_the_runtime_sections(
    tmp_path, frozen_git
):
    empty = tmp_path / "no-runtime"
    empty.mkdir()

    inbox = build_inbox(
        repo_root=empty, boot_packet=packet(), environ={}, now=_NOW
    )

    assert inbox["runtime_counts"] is None
    assert inbox["suppressed"] is None
    assert not runtime_items(inbox)
    assert inbox["grounding"]["runtime_db"]["present"] is False
    assert inbox["grounding"]["runtime_db"]["path"].endswith(
        "data/control_plane/executive.sqlite3"
    )
    named = [entry for entry in inbox["degraded"] if "database missing" in entry]
    assert named and "runtime not projected" in named[0]
    # A reader must not be able to mistake this for a quiet company: the CEO rows
    # are still projected, so the document is visibly partial rather than empty.
    assert [item["target"] for item in inbox["attention"]] == ["ceo", "ceo"]
    # And nothing was created by asking.
    assert not (empty / "data").exists()


def test_9b_boot_packet_degraded_entries_bubble_with_a_prefix(store, frozen_git):
    inbox = inbox_for(
        store,
        boot_packet=packet(degraded=["macro git sha unreadable at /fixture/macro"]),
    )
    assert "boot_packet: macro git sha unreadable at /fixture/macro" in inbox["degraded"]


def test_9c_no_boot_packet_says_exactly_what_was_not_projected(store, frozen_git):
    inbox = build_inbox(
        repo_root=store,
        boot_packet=None,
        include_boot_packet=False,
        environ={},
        now=_NOW,
    )
    assert (
        "boot packet not collected (--no-boot-packet); CEO/Agent OS attention "
        "not projected" in inbox["degraded"]
    )
    assert inbox["grounding"]["boot_packet_schema"] is None
    assert inbox["grounding"]["macro"] == {"root": None, "sha": None}
    assert not [item for item in inbox["attention"] if item["target"] == "ceo"]
    # The runtime half is unaffected — a missing packet degrades one input, not all.
    assert {item["job_id"] for item in runtime_items(inbox)} == set(_EXPECTED_ATTENTION)


def test_9d_an_unreadable_boot_packet_file_degrades_and_continues(store, frozen_git):
    missing = store / "nowhere.json"
    inbox = build_inbox(
        repo_root=store, boot_packet_file=missing, environ={}, now=_NOW
    )
    assert [entry for entry in inbox["degraded"] if "boot packet file unreadable" in entry]
    assert {item["job_id"] for item in runtime_items(inbox)} == set(_EXPECTED_ATTENTION)

    junk = store / "junk.json"
    junk.write_text("{not json", encoding="utf-8")
    inbox = build_inbox(repo_root=store, boot_packet_file=junk, environ={}, now=_NOW)
    assert [entry for entry in inbox["degraded"] if "is not JSON" in entry]

    saved = store / "packet.json"
    saved.write_text(json.dumps(packet()), encoding="utf-8")
    inbox = build_inbox(repo_root=store, boot_packet_file=saved, environ={}, now=_NOW)
    assert inbox["degraded"] == []
    assert len([i for i in inbox["attention"] if i["target"] == "ceo"]) == 2


# ---------------------------------------------------------------------------
# 10. determinism
# ---------------------------------------------------------------------------

def test_10_two_builds_over_one_state_are_byte_identical(store, frozen_git):
    first = json.dumps(inbox_for(store), indent=2, sort_keys=True)
    second = json.dumps(inbox_for(store), indent=2, sort_keys=True)
    assert first == second
    assert json.loads(first)["generated_at"] == _NOW

    # The identity is content-addressed, not positional.  A runtime item is
    # reconstructible from its own projected fields alone — the documented
    # six-part join, with no ordinal.
    document = json.loads(first)
    sample = next(i for i in document["attention"] if i["source"] == "runtime")
    assert sample["attention_id"] == attention_id(
        target=sample["target"],
        kind=sample["kind"],
        source=sample["source"],
        job_id=sample["job_id"],
        workstream=sample["workstream"],
        reason=sample["reason"],
    )
    assert sample["attention_id"].startswith("eia-")
    assert len(sample["attention_id"]) == 16

    # An Agent OS item additionally carries its source row ordinal, so two
    # identical rows cannot collapse (see the collision test).
    row = document["attention"][0]
    assert row["source"] == "agent_os"
    assert row["attention_id"] == attention_id(
        target=row["target"], kind=row["kind"], source=row["source"],
        job_id=row["job_id"], workstream=row["workstream"], reason=row["reason"],
        ordinal=1,
    )

    # Sorted by (target rank, source, job_id or workstream, kind).
    ranks = [TARGETS.index(item["target"]) for item in json.loads(first)["attention"]]
    assert ranks == sorted(ranks)


# ---------------------------------------------------------------------------
# 11. unknown inputs degrade visibly
# ---------------------------------------------------------------------------

def test_11a_an_unknown_job_status_closes_the_jobs_surface_by_name(store, frozen_git):
    corrupt_root = store.parent / "corrupt"
    (corrupt_root / DB_RELATIVE_PATH.parent).mkdir(parents=True)
    (corrupt_root / DB_RELATIVE_PATH).write_bytes(
        (store / DB_RELATIVE_PATH).read_bytes()
    )
    _raw(
        corrupt_root / DB_RELATIVE_PATH,
        "UPDATE jobs SET status='PAUSED' WHERE job_id=?",
        ("JOB-004",),
        ignore_checks=True,
    )

    inbox = inbox_for(corrupt_root)

    named = [entry for entry in inbox["degraded"] if "jobs unreadable" in entry]
    assert named, inbox["degraded"]
    assert "PAUSED" in named[0]
    assert inbox["runtime_counts"]["jobs"] is None
    assert inbox["suppressed"] is None
    assert not runtime_items(inbox)
    # The unreadable row is NOT quietly routine: nothing claims a clean read.
    assert "PAUSED" not in json.dumps(inbox["attention"])
    # The registries that still decode keep answering.
    assert inbox["runtime_counts"]["attempts"]["total"] == _TOTAL_ATTEMPTS
    assert inbox["runtime_counts"]["workers"]["total"] == 4


def test_11b_an_unknown_boot_packet_schema_is_named_and_not_mapped(store, frozen_git):
    inbox = inbox_for(store, boot_packet=packet(schema="mastermind.ceo_boot_packet.v9"))

    named = [entry for entry in inbox["degraded"] if "boot packet schema" in entry]
    assert named, inbox["degraded"]
    assert "v9" in named[0] and "not projected" in named[0]
    assert not [item for item in inbox["attention"] if item["target"] == "ceo"]
    assert inbox["grounding"]["boot_packet_schema"] is None
    assert inbox["grounding"]["macro"] == {"root": None, "sha": None}
    # The runtime half is untouched by a foreign orientation document.
    assert {item["job_id"] for item in runtime_items(inbox)} == set(_EXPECTED_ATTENTION)


# ---------------------------------------------------------------------------
# 12. no new database, table, or queue
# ---------------------------------------------------------------------------

def test_12_a_cli_run_creates_no_new_state(store, frozen_git, capsys):
    db_path = store / DB_RELATIVE_PATH

    sqlite3.connect(db_path).close()

    def _tree() -> set[str]:
        return {
            path.relative_to(store).as_posix()
            for path in store.rglob("*")
            if not path.name.endswith(("-wal", "-shm"))
        }

    before_tree = _tree()
    before_master = logical_dump(db_path)["sqlite_master"]
    before_sha = _sha(db_path)
    assert before_tree

    assert cli_main(["--root", os.fspath(store), "--no-boot-packet", "--now", _NOW]) == 0
    capsys.readouterr()

    assert _tree() == before_tree
    assert logical_dump(db_path)["sqlite_master"] == before_master
    assert _sha(db_path) == before_sha
    # Nothing anywhere else, either: no sibling store, no queue file, no journal.
    assert sorted(before_tree & {"data/control_plane"}) == ["data/control_plane"]

    # WAL sidecars ACCOUNTED FOR, not merely excluded.  Reading a WAL database —
    # the mode this runtime uses — lets SQLite build its wal-index, so `-wal` and
    # `-shm` may appear even under `mode=ro`.  What must be true is that no
    # COMMITTED frame was written: the `-wal` is empty and the database file's
    # sha is unchanged (asserted above).  `test_b1c_*` proves the stricter form on
    # a `delete`-mode database, where nothing at all is created.
    for sidecar in db_path.parent.glob("*-wal"):
        assert sidecar.stat().st_size == 0, f"{sidecar.name} carries committed frames"
    assert not (db_path.parent / f"{db_path.name}-journal").exists()


# ---------------------------------------------------------------------------
# 14. CI wiring self-check  (13 is the RUN receipt — see the module docstring)
# ---------------------------------------------------------------------------

def test_14_this_suite_is_wired_into_the_hermetic_governance_gate():
    workflow = (_REPO / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "Run repository test gate" in workflow
    assert "scripts/ci_pytest.py" in workflow
    discovered = {
        path.relative_to(_REPO).as_posix()
        for path in (_REPO / "tests").rglob("test_*.py")
        if path.is_file()
    }
    assert "tests/test_executive_inbox.py" in discovered, (
        "a projection nobody runs is a projection nobody trusts"
    )


# ---------------------------------------------------------------------------
# the CLI and the text form
# ---------------------------------------------------------------------------

def test_cli_json_parses_and_exits_zero(store, frozen_git, capsys):
    argv = ["--root", os.fspath(store), "--json", "--no-boot-packet", "--now", _NOW]
    assert cli_main(argv) == 0
    first = capsys.readouterr().out
    emitted = json.loads(first)
    assert emitted["schema"] == SCHEMA
    assert set(emitted) == {
        "schema", "generated_at", "grounding", "attention", "runtime_counts",
        "suppressed", "degraded",
    }
    assert {item["job_id"] for item in runtime_items(emitted)} == set(_EXPECTED_ATTENTION)

    assert cli_main(argv) == 0
    assert capsys.readouterr().out == first


def test_cli_text_render_carries_the_counts_line(store, frozen_git, capsys):
    assert cli_main(["--root", os.fspath(store), "--now", _NOW, "--no-boot-packet"]) == 0
    text = capsys.readouterr().out

    assert f"EXECUTIVE INBOX — {_NOW}" in text
    assert "mastermind eeeeeeeeeeee (master)" in text
    assert "runtime db present" in text
    assert f"schema {SCHEMA}" in text
    assert "0 chairman · 0 CEO · 13 COO" in text
    assert (
        "suppressed: 4 clean completions · 2 queued · 2 running/checkpointed · "
        "1 cancelled" in text
    )
    assert "COO" in text and "CHAIRMAN" not in text
    assert "[job_failed] JOB-009 is FAILED" in text
    assert "evidence: status=FAILED" in text
    assert "attempt.exit_code=1" in text
    assert "next actions on file: re-scope the objective before another attempt" in text
    # DEGRADED is present because --no-boot-packet was passed, and never suppressed.
    assert "⚠ DEGRADED (1)" in text
    assert "boot packet not collected" in text


def test_render_never_suppresses_degraded_even_with_nothing_to_show(tmp_path, frozen_git):
    empty = tmp_path / "bare"
    empty.mkdir()
    inbox = build_inbox(
        repo_root=empty,
        boot_packet=None,
        include_boot_packet=False,
        environ={},
        now=_NOW,
    )
    text = render_inbox(inbox)
    assert "runtime db MISSING" in text
    assert "suppressed: runtime not projected" in text
    assert "0 chairman · 0 CEO · 0 COO" in text
    assert "⚠ DEGRADED (2)" in text
    assert "no attention items" in text


def test_cli_exits_zero_in_every_degraded_scenario(tmp_path, frozen_git, capsys):
    empty = tmp_path / "bare"
    empty.mkdir()
    assert cli_main(["--root", os.fspath(empty), "--no-boot-packet", "--now", _NOW]) == 0
    assert "DEGRADED" in capsys.readouterr().out
    assert cli_main(
        ["--root", os.fspath(empty), "--json", "--boot-packet-file",
         os.fspath(tmp_path / "missing.json"), "--now", _NOW]
    ) == 0
    assert json.loads(capsys.readouterr().out)["degraded"]


# ---------------------------------------------------------------------------
# BLOCKER 1 — the reader never creates, migrates, or re-modes a database
# ---------------------------------------------------------------------------

def _bare_root(tmp_path: Path, name: str) -> Path:
    root = tmp_path / name
    (root / DB_RELATIVE_PATH.parent).mkdir(parents=True)
    return root


def _table_names(db_path: Path) -> list[str]:
    connection = sqlite3.connect(f"{db_path.as_uri()}?mode=ro", uri=True)
    try:
        return [
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
        ]
    finally:
        connection.close()


def test_b1a_a_zero_byte_database_is_named_and_never_given_a_schema(
    tmp_path, frozen_git
):
    """Existence is not readiness: a husk must not be handed the whole schema."""
    root = _bare_root(tmp_path, "husk")
    db_path = root / DB_RELATIVE_PATH
    db_path.write_bytes(b"")
    before = _sha(db_path)

    inbox = build_inbox(repo_root=root, boot_packet=packet(), environ={}, now=_NOW)

    named = [e for e in inbox["degraded"] if "carries no Executive OS schema" in e]
    assert named, inbox["degraded"]
    assert "runtime not projected" in named[0]
    assert os.fspath(db_path) in named[0]
    assert inbox["runtime_counts"] is None and inbox["suppressed"] is None
    assert not runtime_items(inbox)

    assert db_path.stat().st_size == 0
    assert _sha(db_path) == before
    assert _table_names(db_path) == []
    # And the CEO lane still answers — a broken runtime is not a quiet company.
    assert [item["target"] for item in inbox["attention"]] == ["ceo", "ceo"]


def test_b1b_a_foreign_sqlite_file_is_named_and_left_alone(tmp_path, frozen_git):
    root = _bare_root(tmp_path, "foreign")
    db_path = root / DB_RELATIVE_PATH
    connection = sqlite3.connect(db_path)
    connection.execute("CREATE TABLE unrelated(x)")
    connection.execute("INSERT INTO unrelated VALUES(1)")
    connection.commit()
    connection.close()
    before = _sha(db_path)

    inbox = build_inbox(repo_root=root, boot_packet=packet(), environ={}, now=_NOW)

    assert [e for e in inbox["degraded"] if "Executive OS" in e], inbox["degraded"]
    assert inbox["runtime_counts"] is None and inbox["suppressed"] is None
    assert _sha(db_path) == before
    assert _table_names(db_path) == ["unrelated"]


def test_b1c_a_delete_mode_database_keeps_its_journal_mode_and_its_bytes(
    store, frozen_git
):
    """The reader sets no journal mode — and on `delete` it creates nothing at all."""
    root = _bare_root(store.parent, "delete_mode")
    db_path = root / DB_RELATIVE_PATH
    db_path.write_bytes((store / DB_RELATIVE_PATH).read_bytes())
    connection = sqlite3.connect(db_path, isolation_level=None)
    assert connection.execute("PRAGMA journal_mode=delete").fetchone()[0] == "delete"
    connection.close()
    before = _sha(db_path)

    inbox = inbox_for(root)
    assert {item["job_id"] for item in runtime_items(inbox)} == set(_EXPECTED_ATTENTION)

    assert _sha(db_path) == before
    probe = sqlite3.connect(f"{db_path.as_uri()}?mode=ro", uri=True)
    try:
        assert probe.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
    finally:
        probe.close()
    assert not list(db_path.parent.glob("*-wal"))
    assert not list(db_path.parent.glob("*-shm"))
    assert not list(db_path.parent.glob("*-journal"))


def test_b1d_a_read_only_store_refuses_every_lifecycle_mutation(store):
    read_only = RuntimeStore(store, create=False)
    assert read_only.create is False
    with pytest.raises(StateConflict, match="read-only store"):
        with read_only.transaction():
            pass  # pragma: no cover - the enter must raise

    # The read path is unaffected...
    assert len(Runtime.at(store, create=False).jobs.list_jobs()) == _TOTAL_JOBS
    # ...and the default stays exactly what every existing caller relies on.
    assert RuntimeStore(store).create is True


# ---------------------------------------------------------------------------
# BLOCKER 2 — a packet that carries no brief must not read as a quiet CEO lane
# ---------------------------------------------------------------------------

def test_b2a_a_packet_with_no_brief_says_the_ceo_lane_was_not_read(store, frozen_git):
    """`build_packet` emits brief: null whenever the Macro read fails."""
    empty = packet()
    empty["brief"] = None

    inbox = inbox_for(store, boot_packet=empty)

    assert (
        "boot packet carries no Agent OS brief; CEO attention not projected"
        in inbox["degraded"]
    )
    assert not [item for item in inbox["attention"] if item["target"] == "ceo"]
    # The render must not be able to show a healthy-looking "0 CEO" alone.
    text = render_inbox(inbox)
    assert "0 CEO" in text and "⚠ DEGRADED" in text
    assert "no Agent OS brief" in text
    # The runtime half is unaffected.
    assert {item["job_id"] for item in runtime_items(inbox)} == set(_EXPECTED_ATTENTION)


def test_b2b_a_non_list_packet_degraded_field_is_named_not_discarded(
    store, frozen_git
):
    malformed = packet()
    malformed["degraded"] = "macro git sha unreadable"

    inbox = inbox_for(store, boot_packet=malformed)

    named = [e for e in inbox["degraded"] if "degraded field is a str" in e]
    assert named, inbox["degraded"]
    # It must not have been iterated character by character either.
    assert not [e for e in inbox["degraded"] if e == "boot_packet: m"]


def test_b2c_a_foreign_brief_schema_is_named_and_not_read(store, frozen_git):
    foreign = packet()
    foreign["brief"]["schema"] = "ceo_brief.v9"

    inbox = inbox_for(store, boot_packet=foreign)

    named = [e for e in inbox["degraded"] if "brief schema" in e]
    assert named and "ceo_brief.v9" in named[0] and BRIEF_SCHEMA in named[0]
    assert not [item for item in inbox["attention"] if item["target"] == "ceo"]


# ---------------------------------------------------------------------------
# LOST cause, stale leases, schema drift, the fleet line, id collisions
# ---------------------------------------------------------------------------

def test_lost_wording_separates_lease_expiry_from_a_verified_absence(
    store, frozen_git
):
    items = {item["job_id"]: item for item in runtime_items(inbox_for(store))}

    assert "verified its invocation was absent" in items["JOB-011"]["reason"]
    assert "lease expired without a heartbeat" in items["JOB-021"]["reason"]
    assert items["JOB-011"]["reason"] != items["JOB-021"]["reason"]

    causes = [e for e in items["JOB-021"]["evidence"] if e["field"] == "error.reason"]
    assert causes and causes[0]["value"] == "lease_expired"
    assert causes[0]["ref"].startswith("attempt:ATT-")

    # And an unreadable attempt gets the neutral sentence, never an invented cause.
    assert mod._lost_cause(None) == ("the runtime marked it LOST", None)


def test_a_stale_lease_on_an_active_attempt_is_attention(store, frozen_git):
    inbox = inbox_for(store)
    items = {item["job_id"]: item for item in runtime_items(inbox)}

    stale = items["JOB-022"]
    assert stale["kind"] == "stale_lease"
    assert stale["status"] == "RUNNING"
    assert "lease expired at" in stale["reason"]
    assert "reconciliation has not swept it" in stale["reason"]
    fields = {e["field"] for e in stale["evidence"]}
    assert {"lease_expires_at", "heartbeat_at"} <= fields

    # The RUNNING job whose lease is still live stays routine.
    assert "JOB-006" not in items
    assert inbox["suppressed"]["running"] == 1


def test_stale_lease_is_arithmetic_not_inference(store, frozen_git):
    """Move `now` behind every lease and the same row is routine again."""
    inbox = inbox_for(store, now="2026-08-13T00:00:00Z")
    assert "JOB-022" not in {item["job_id"] for item in runtime_items(inbox)}
    assert inbox["suppressed"]["running"] == 2
    assert sum(inbox["suppressed"].values()) + len(runtime_items(inbox)) == _TOTAL_JOBS
    # ...and the SAME store at `_NOW` does surface it, so this cannot pass merely
    # because the rule is absent.
    assert "JOB-022" in {item["job_id"] for item in runtime_items(inbox_for(store))}


def test_an_unparseable_now_is_refused_rather_than_silently_replaced(store):
    with pytest.raises(ValueError):
        build_inbox(
            repo_root=store, boot_packet=packet(), environ={}, now="not-a-timestamp"
        )
    # The CLI rejects it at PARSE time — before the always-exit-0 contract begins.
    with pytest.raises(SystemExit) as excinfo:
        cli_main(["--root", os.fspath(store), "--now", "not-a-timestamp"])
    assert excinfo.value.code == 2
    assert mod.parse_now("2026-08-14T00:00:00Z") == mod.parse_now(
        "2026-08-14T00:00:00+00:00"
    )


def test_provenance_schema_is_pinned_to_the_intent_bridge():
    """Import ceo_intent in the TEST only — the module's import fence is unchanged."""
    from control_plane.ceo_intent import INTENT_SCHEMA

    assert mod.CEO_INTENT_PROVENANCE_SCHEMA == INTENT_SCHEMA
    assert INTENT_SCHEMA.startswith(mod.CEO_INTENT_SCHEMA_PREFIX)


def test_a_versioned_sibling_provenance_is_named_not_silently_dropped(
    tmp_path, frozen_git
):
    runtime = Runtime.at(tmp_path, clock=_Clock(), lease_seconds=_LONG_LEASE_SECONDS)
    runtime.workers.register_worker(
        "claude-01", provider="claude", account_label="a", worker_type="mock",
        capabilities=["code"], quota_classes={"c1": ["code"]},
    )
    runtime.jobs.create_job(
        "Submitted under a newer intent schema",
        constraints={"eligible_quota_classes": ["c1"]},
        command_id="ceo-intent:v2-1",
        provenance=dict(_CEO_PROVENANCE, schema="mastermind.ceo_intent.v2"),
    )
    _claim(runtime, "JOB-001", "claude-01", "c1")
    runtime.jobs.fail_job("JOB-001", _payload(errors=["boom"]))

    inbox = inbox_for(tmp_path)
    named = [e for e in inbox["degraded"] if "unrecognized" in e]
    assert named, inbox["degraded"]
    assert "mastermind.ceo_intent.v2" in named[0] and "JOB-001" in named[0]

    item = next(i for i in inbox["attention"] if i["job_id"] == "JOB-001")
    assert item["target"] == "coo" and item["workstream"] is None
    assert not [e for e in item["evidence"] if e["field"].startswith("provenance.")]


def test_the_fleet_line_makes_a_dead_worker_visible(store, frozen_git):
    text = render_inbox(inbox_for(store))
    assert (
        f"runtime: {_TOTAL_JOBS} jobs · {_TOTAL_ATTEMPTS} attempts · 4 workers "
        f"(2 AVAILABLE · 1 OFFLINE · 1 ERROR)" in text
    )


def test_two_identical_needs_ceo_rows_stay_two_items(store, frozen_git):
    row = dict(_NEEDS_CEO[0])
    twice = packet(needs_ceo=[dict(row), dict(row)])

    inbox = inbox_for(store, boot_packet=twice)
    ceo = [item for item in inbox["attention"] if item["target"] == "ceo"]
    assert len(ceo) == 2
    assert len({item["attention_id"] for item in ceo}) == 2
    assert {item["reason"] for item in ceo} == {row["question"]}

    # ...and the disambiguation is deterministic, not incidental.
    again = inbox_for(store, boot_packet=packet(needs_ceo=[dict(row), dict(row)]))
    assert [i["attention_id"] for i in again["attention"] if i["target"] == "ceo"] == [
        i["attention_id"] for i in ceo
    ]


# ---------------------------------------------------------------------------
# contract drift guards
# ---------------------------------------------------------------------------

def test_db_path_constant_matches_the_runtime(store):
    """The existence check is only safe while it names the runtime's own path."""
    assert DB_RELATIVE_PATH == _RUNTIME_DB_PATH
    assert (store / DB_RELATIVE_PATH).is_file()


def test_classification_covers_every_job_status():
    """Every JobStatus is either classified or suppressed — no status falls through."""
    classified = {
        JobStatus.FAILED, JobStatus.LOST, JobStatus.RATE_LIMITED,
        JobStatus.CANCEL_REQUESTED,
    }
    assert classified | set(mod._SUPPRESSION_BY_STATUS) == set(JobStatus)
    assert set(mod._SUPPRESSION_BY_STATUS.values()) == set(mod._SUPPRESSION_KEYS)

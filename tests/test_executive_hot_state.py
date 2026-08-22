from __future__ import annotations

import ast
import asyncio
import functools
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from control_plane import executive_hot_state as hot_state
from control_plane.executive_runtime import (
    AttemptStatus,
    JobStatus,
    Runtime,
    WorkerStatus,
)


def _sync_test(function):
    @functools.wraps(function)
    def wrapped(*args, **kwargs):
        return asyncio.run(function(*args, **kwargs))

    return wrapped


GROUNDING = {
    "mastermind_sha": "1" * 40,
    "macro_sha": "2" * 40,
    "boot_packet_schema": hot_state.BOOT_PACKET_SCHEMA,
}


class _Grounding:
    def __init__(self, value=GROUNDING, *, error: Exception | None = None):
        self.value = value
        self.error = error
        self.calls = 0

    def observe(self):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.value


def _now(second: int = 0) -> datetime:
    return datetime(2026, 8, 21, 12, 0, second, 999999, tzinfo=timezone.utc)


def test_r0_enum_vocabulary_is_literal_and_matches_accepted_runtime():
    assert hot_state.JOB_STATUS_VALUES == (
        "QUEUED",
        "RUNNING",
        "CHECKPOINTED",
        "RATE_LIMITED",
        "FAILED",
        "LOST",
        "CANCEL_REQUESTED",
        "COMPLETED",
        "CANCELLED",
    )
    assert hot_state.ATTEMPT_STATUS_VALUES == (
        "CLAIMED",
        "RUNNING",
        "CHECKPOINTED",
        "CANCEL_REQUESTED",
        "RATE_LIMITED",
        "FAILED",
        "LOST",
        "COMPLETED",
        "CANCELLED",
    )
    assert hot_state.WORKER_STATUS_VALUES == (
        "AVAILABLE",
        "BUSY",
        "DRAINING",
        "RATE_LIMITED",
        "OFFLINE",
        "ERROR",
    )
    assert tuple(item.value for item in JobStatus) == hot_state.JOB_STATUS_VALUES
    assert tuple(item.value for item in AttemptStatus) == hot_state.ATTEMPT_STATUS_VALUES
    assert tuple(item.value for item in WorkerStatus) == hot_state.WORKER_STATUS_VALUES


@_sync_test
async def test_exact_empty_enum_census_and_ready_truth(tmp_path):
    runtime = Runtime.at(tmp_path / "runtime")
    state = await hot_state.build_hot_state(
        runtime=runtime,
        grounding_provider=_Grounding(),
        service_state="AWAITING_CANARY",
        ceo_ingress_armed=True,
        generated_at=_now(),
    )

    assert set(state) == {
        "schema",
        "generated_at",
        "snapshot_hash",
        "grounding",
        "service",
        "generic_operator_mutations",
        "runtime",
        "degraded",
        "do_not_submit",
    }
    assert state["schema"] == hot_state.HOT_STATE_SCHEMA
    assert state["generated_at"] == "2026-08-21T12:00:00Z"
    assert state["grounding"] == GROUNDING
    assert state["service"] == {
        "service_state": "AWAITING_CANARY",
        "ceo_admission": "READY",
    }
    assert state["generic_operator_mutations"] == "BLOCKED_AWAITING_CANARY"
    assert state["runtime"] == {
        "projection_state": "OK",
        "jobs": {"total": 0, "by_status": {name: 0 for name in hot_state.JOB_STATUS_VALUES}},
        "attempts": {
            "total": 0,
            "by_status": {name: 0 for name in hot_state.ATTEMPT_STATUS_VALUES},
        },
        "workers": {
            "total": 0,
            "by_status": {name: 0 for name in hot_state.WORKER_STATUS_VALUES},
        },
    }
    assert state["degraded"] == []
    assert state["do_not_submit"] is False
    assert len(state["snapshot_hash"]) == 64
    semantic = dict(state)
    semantic.pop("generated_at")
    semantic.pop("snapshot_hash")
    assert state["snapshot_hash"] == hashlib.sha256(
        hot_state.canonical_json_bytes(semantic)
    ).hexdigest()
    assert len(hot_state.canonical_json_bytes(state)) <= hot_state.MAX_STATE_BYTES


@_sync_test
async def test_clock_only_change_keeps_hash_semantic_change_moves_hash(tmp_path):
    runtime = Runtime.at(tmp_path / "runtime")
    first = await hot_state.build_hot_state(
        runtime=runtime,
        grounding_provider=_Grounding(),
        service_state="READY",
        ceo_ingress_armed=True,
        generated_at=_now(0),
    )
    heartbeat = await hot_state.build_hot_state(
        runtime=runtime,
        grounding_provider=_Grounding(),
        service_state="READY",
        ceo_ingress_armed=True,
        generated_at=_now(30),
    )
    assert first["generated_at"] != heartbeat["generated_at"]
    assert first["snapshot_hash"] == heartbeat["snapshot_hash"]

    runtime.workers.register_worker(
        "worker-1",
        provider="fixture",
        account_label="fixture",
        worker_type="fixture",
    )
    changed = await hot_state.build_hot_state(
        runtime=runtime,
        grounding_provider=_Grounding(),
        service_state="READY",
        ceo_ingress_armed=True,
        generated_at=_now(30),
    )
    assert changed["runtime"]["workers"]["total"] == 1
    assert changed["snapshot_hash"] != heartbeat["snapshot_hash"]


@_sync_test
async def test_grounding_failure_is_opaque_degraded_and_preserves_runtime(tmp_path):
    runtime = Runtime.at(tmp_path / "runtime")
    state = await hot_state.build_hot_state(
        runtime=runtime,
        grounding_provider=_Grounding(
            error=RuntimeError("/Users/operator/private token=xoxb-secret")
        ),
        service_state="READY",
        ceo_ingress_armed=True,
        generated_at=_now(),
    )
    assert state["grounding"] == {
        "mastermind_sha": None,
        "macro_sha": None,
        "boot_packet_schema": None,
    }
    assert state["runtime"]["projection_state"] == "OK"
    assert state["degraded"] == ["GROUNDING_UNAVAILABLE"]
    assert state["do_not_submit"] is True
    encoded = hot_state.canonical_json_bytes(state)
    assert b"/Users/operator" not in encoded
    assert b"xoxb-secret" not in encoded


@_sync_test
async def test_service_normalization_unknown_quarantine_and_unarmed(tmp_path):
    runtime = Runtime.at(tmp_path / "runtime")
    quarantined = await hot_state.build_hot_state(
        runtime=runtime,
        grounding_provider=_Grounding(),
        service_state="QUARANTINED",
        ceo_ingress_armed=True,
        generated_at=_now(),
    )
    assert quarantined["service"] == {
        "service_state": "QUARANTINED",
        "ceo_admission": "BLOCKED_QUARANTINED",
    }
    assert quarantined["generic_operator_mutations"] == "BLOCKED_QUARANTINED"
    assert quarantined["degraded"] == []
    assert quarantined["do_not_submit"] is True

    unknown = await hot_state.build_hot_state(
        runtime=runtime,
        grounding_provider=_Grounding(),
        service_state="NEW_FUTURE_VALUE",
        ceo_ingress_armed=True,
        generated_at=_now(),
    )
    assert unknown["service"] == {
        "service_state": "UNKNOWN",
        "ceo_admission": "BLOCKED_UNSAFE_STATE",
    }
    assert unknown["generic_operator_mutations"] == "UNKNOWN"
    assert unknown["degraded"] == ["SERVICE_STATE_UNKNOWN"]

    unarmed = await hot_state.build_hot_state(
        runtime=runtime,
        grounding_provider=_Grounding(),
        service_state="READY",
        ceo_ingress_armed=False,
        generated_at=_now(),
    )
    assert unarmed["service"]["ceo_admission"] == "UNARMED"
    assert unarmed["do_not_submit"] is True


@_sync_test
async def test_one_registry_failure_is_null_not_zero_and_unknown_status_fails_closed(
    tmp_path, monkeypatch
):
    runtime = Runtime.at(tmp_path / "runtime")

    def unavailable():
        raise RuntimeError("SELECT secret FROM jobs at /var/db/executive.sqlite3")

    monkeypatch.setattr(runtime.jobs, "list_jobs", unavailable)
    state = await hot_state.build_hot_state(
        runtime=runtime,
        grounding_provider=_Grounding(),
        service_state="READY",
        ceo_ingress_armed=True,
        generated_at=_now(),
    )
    assert state["runtime"]["jobs"] is None
    assert state["runtime"]["attempts"]["total"] == 0
    assert state["runtime"]["workers"]["total"] == 0
    assert state["runtime"]["projection_state"] == "DEGRADED"
    assert state["degraded"] == ["RUNTIME_JOBS_UNAVAILABLE"]
    assert "SELECT secret" not in hot_state.canonical_json_bytes(state).decode()

    monkeypatch.setattr(
        runtime.jobs, "list_jobs", lambda: [SimpleNamespace(status="BLOCKED")]
    )
    unknown = await hot_state.build_hot_state(
        runtime=runtime,
        grounding_provider=_Grounding(),
        service_state="READY",
        ceo_ingress_armed=True,
        generated_at=_now(),
    )
    assert unknown["runtime"]["jobs"] is None
    assert "BLOCKED" not in hot_state.canonical_json_bytes(unknown).decode()


@_sync_test
async def test_current_registry_failure_never_reuses_prior_green_values(
    tmp_path, monkeypatch
):
    runtime = Runtime.at(tmp_path / "runtime")
    green = await hot_state.build_hot_state(
        runtime=runtime,
        grounding_provider=_Grounding(),
        service_state="READY",
        ceo_ingress_armed=True,
        generated_at=_now(),
    )
    assert green["runtime"]["jobs"] == {
        "total": 0,
        "by_status": {name: 0 for name in hot_state.JOB_STATUS_VALUES},
    }

    def unavailable():
        raise RuntimeError("current read failed")

    monkeypatch.setattr(runtime.jobs, "list_jobs", unavailable)
    current = await hot_state.build_hot_state(
        runtime=runtime,
        grounding_provider=_Grounding(),
        service_state="READY",
        ceo_ingress_armed=True,
        generated_at=_now(30),
    )
    assert current["runtime"]["jobs"] is None
    assert current["runtime"]["projection_state"] == "DEGRADED"
    assert current["snapshot_hash"] != green["snapshot_hash"]


@_sync_test
async def test_all_registry_failures_are_unavailable_with_closed_sorted_codes(
    tmp_path, monkeypatch
):
    runtime = Runtime.at(tmp_path / "runtime")

    def unavailable():
        raise RuntimeError("backend detail must remain opaque")

    monkeypatch.setattr(runtime.jobs, "list_jobs", unavailable)
    monkeypatch.setattr(runtime.attempts, "list_attempts", unavailable)
    monkeypatch.setattr(runtime.workers, "list_workers", unavailable)
    state = await hot_state.build_hot_state(
        runtime=runtime,
        grounding_provider=_Grounding(),
        service_state="READY",
        ceo_ingress_armed=True,
        generated_at=_now(),
    )
    assert state["runtime"] == {
        "projection_state": "UNAVAILABLE",
        "jobs": None,
        "attempts": None,
        "workers": None,
    }
    assert state["degraded"] == sorted(
        [
            "RUNTIME_JOBS_UNAVAILABLE",
            "RUNTIME_ATTEMPTS_UNAVAILABLE",
            "RUNTIME_WORKERS_UNAVAILABLE",
        ]
    )
    assert state["do_not_submit"] is True


@_sync_test
async def test_state_projection_causes_zero_runtime_mutation(tmp_path):
    runtime = Runtime.at(tmp_path / "runtime")
    before = {
        "jobs": runtime.jobs.list_jobs(),
        "attempts": runtime.attempts.list_attempts(),
        "workers": runtime.workers.list_workers(),
        "events": runtime.events.list_events(),
    }
    await hot_state.build_hot_state(
        runtime=runtime,
        grounding_provider=_Grounding(),
        service_state="READY",
        ceo_ingress_armed=True,
        generated_at=_now(),
    )
    after = {
        "jobs": runtime.jobs.list_jobs(),
        "attempts": runtime.attempts.list_attempts(),
        "workers": runtime.workers.list_workers(),
        "events": runtime.events.list_events(),
    }
    assert after == before


@_sync_test
async def test_oversize_state_refuses_without_truncation(tmp_path, monkeypatch):
    runtime = Runtime.at(tmp_path / "runtime")
    monkeypatch.setattr(hot_state, "MAX_STATE_BYTES", 1)
    with pytest.raises(hot_state.HotStateTooLarge):
        await hot_state.build_hot_state(
            runtime=runtime,
            grounding_provider=_Grounding(),
            service_state="READY",
            ceo_ingress_armed=True,
            generated_at=_now(),
        )


def test_hot_state_static_import_and_raw_sql_fences():
    path = Path(hot_state.__file__)
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = {
        node.names[0].name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
    } | {
        node.module or ""
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }
    assert "sqlite3" not in imports
    assert "subprocess" not in imports
    assert not any(name.startswith("integrations") for name in imports)
    assert "control_plane.ceo_boot_packet" not in imports
    assert "SELECT " not in source
    assert "PRAGMA " not in source
    assert "_database_health" not in source

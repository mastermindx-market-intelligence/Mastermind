"""Durable privileged families reject corrupted/reordered cross-operation evidence."""
from __future__ import annotations

import dataclasses
import hashlib

import pytest

from control_plane import executive_privileged_authority as authority
from control_plane.executive_privileged_action import REQUEST_SCHEMA, canonical_request_bytes, validate_request
from control_plane.executive_privileged_broker import RECEIPT_SCHEMA
from control_plane.executive_runtime import EventRegistry, RuntimeStore, Runtime


def binding(rows=None):
    if rows:
        return authority.ReadinessBinding(**rows[0].payload["binding"])
    return authority.ReadinessBinding(
        job_id="JOB-001", attempt_id="ATT-" + "1" * 32,
        worker_id="codex-01", quota_class="codex-native", fence_generation=1,
        authority_policy_hash="a" * 64, effective_grant_digest=None,
        release_sha="b" * 40, boot_id="00000000-0000-4000-8000-000000000001",
        slot_id="codex-01",
    )


def request(rows=None):
    value = binding(rows)
    return authority.ReadinessRequest(value.job_id, value.attempt_id, value.fence_generation)


def receipt(value, *, failed=False):
    payload = validate_request({"schema": REQUEST_SCHEMA, "request_id": value.operation_id,
                                "action": authority.FIXED_ACTION, "args": {"slot_id": value.slot_id}})
    return {
        "schema": RECEIPT_SCHEMA, "request_id": value.operation_id,
        "request_sha256": hashlib.sha256(canonical_request_bytes(payload)).hexdigest(),
        "action": authority.FIXED_ACTION, "effect_class": "CREDENTIAL_ADMIN_READINESS",
        "started_at": "2026-09-28T00:00:00Z", "finished_at": "2026-09-28T00:00:01Z",
        "exit_code": 65 if failed else 0, "outcome": "FAILED" if failed else "SUCCEEDED",
        "release_sha": value.release_sha, "broker_version": "1",
        "stdout_bytes": 0, "stdout_sha256": hashlib.sha256(b"").hexdigest(), "stdout_excerpt": "",
        "stderr_bytes": 0, "stderr_sha256": hashlib.sha256(b"").hexdigest(), "stderr_excerpt": "",
    }


def events(store, phase="TERMINAL", *, failed=False):
    runtime = Runtime.from_store(store)
    runtime.workers.register_worker(
        "codex-01", provider="codex", account_label="test", worker_type="codex-cli",
        capabilities=["research"], quota_classes={"codex-native": {"capabilities": ["research"],
            "model": "gpt-5.6-sol", "effort": "xhigh", "cost_class": "standard"}},
    )
    job = runtime.jobs.create_job("Bounded login status", requested_authorities=["READ"],
        constraints={"provider": "codex", "model": "gpt-5.6-sol", "effort": "xhigh",
                     "cost_class": "standard", "eligible_quota_classes": ["codex-native"],
                     "required_capabilities": ["research"]})
    lease = runtime.attempts.claim_job(job.job_id, worker_id="codex-01", quota_class="codex-native")
    assert lease is not None
    value = dataclasses.replace(binding(), job_id=job.job_id, attempt_id=lease.attempt.attempt_id)
    family = authority.ReadinessFamilyKey(value.job_id, value.attempt_id, value.fence_generation).family_id
    phases = ["INTENT", "ATTEMPTED"]
    if phase == "RECONCILED":
        phases += ["EFFECT_UNKNOWN", "RECONCILED"]
    elif phase != "ATTEMPTED":
        phases += [phase]
    with store.transaction() as connection:
        for name in phases:
            payload = {"binding": value.to_canonical_dict()}
            if name in ("TERMINAL", "RECONCILED"):
                payload["receipt"] = receipt(value, failed=failed)
            if name == "BROKER_REFUSED":
                payload["reason_code"] = "PEER_UNAUTHORIZED"
            store.append_event(
                connection, aggregate_type="privileged_readiness", aggregate_id=family,
                event_type="PRIVILEGED_READINESS_" + name,
                command_id=value.operation_id + ("" if name == "INTENT" else ":" + name.lower()),
                job_id=value.job_id, attempt_id=value.attempt_id,
                worker_id=value.worker_id, quota_class=value.quota_class,
                payload=payload,
            )
    return EventRegistry(store).list_events(aggregate_type="privileged_readiness", aggregate_id=family)


@pytest.mark.parametrize("phase,state", [
    ("ATTEMPTED", "EFFECT_UNKNOWN"), ("EFFECT_UNKNOWN", "EFFECT_UNKNOWN"),
    ("TERMINAL", "TERMINAL"), ("RECONCILED", "TERMINAL"), ("BROKER_REFUSED", "REFUSED"),
])
def test_recover_exact_family_from_real_runtime_events(tmp_path, phase, state):
    rows = events(RuntimeStore(tmp_path), phase, failed=True)
    result = authority.validate_event_family(rows, request(rows))
    assert result.binding == binding(rows)
    assert result.state.value == state
    assert result.phase.value == "PRIVILEGED_READINESS_" + phase
    if state == "TERMINAL":
        assert result.receipt["outcome"] == "FAILED"
        assert result.receipt["release_sha"] == "b" * 40
    else:
        assert result.receipt is None
    assert result.reason_code == ("PEER_UNAUTHORIZED" if state == "REFUSED" else None)


def test_empty_exact_family_allows_admission():
    assert authority.validate_event_family([], request()) is None


@pytest.mark.parametrize("mutation", [
    "intent_only", "missing_attempted", "reordered", "duplicated", "wrong_sequence",
    "wrong_family", "wrong_command", "wrong_job", "wrong_worker", "binding_drift",
    "extra_payload", "wrong_receipt_action", "wrong_receipt_digest", "wrong_receipt_release",
    "wrong_receipt_id", "extra_receipt", "unknown_reason", "terminal_after_unknown",
])
def test_corrupt_family_cannot_be_replayed_or_reauthorize(tmp_path, mutation):
    rows = events(RuntimeStore(tmp_path))
    if mutation == "intent_only": rows = rows[:1]
    elif mutation == "missing_attempted": del rows[1]
    elif mutation == "reordered": rows = rows[::-1]
    elif mutation == "duplicated": rows.append(rows[-1])
    elif mutation == "wrong_sequence": rows[1] = dataclasses.replace(rows[1], sequence=9)
    elif mutation == "wrong_family": rows[0] = dataclasses.replace(rows[0], aggregate_id="pvrf-" + "0" * 48)
    elif mutation == "wrong_command": rows[1] = dataclasses.replace(rows[1], command_id=binding(rows).operation_id)
    elif mutation == "wrong_job": rows[1] = dataclasses.replace(rows[1], job_id="JOB-002")
    elif mutation == "wrong_worker": rows[1] = dataclasses.replace(rows[1], worker_id="codex-pro-01")
    elif mutation == "binding_drift": rows[1].payload["binding"]["release_sha"] = "c" * 40
    elif mutation == "extra_payload": rows[-1].payload["ready"] = True
    elif mutation == "wrong_receipt_action": rows[-1].payload["receipt"]["action"] = "executive.services.start"
    elif mutation == "wrong_receipt_digest": rows[-1].payload["receipt"]["request_sha256"] = "d" * 64
    elif mutation == "wrong_receipt_release": rows[-1].payload["receipt"]["release_sha"] = "e" * 40
    elif mutation == "wrong_receipt_id": rows[-1].payload["receipt"]["request_id"] = "req-other"
    elif mutation == "extra_receipt": rows[-1].payload["receipt"]["ready"] = True
    elif mutation == "unknown_reason":
        rows[-1] = dataclasses.replace(rows[-1], event_type="PRIVILEGED_READINESS_BROKER_REFUSED",
            command_id=binding(rows).operation_id + ":broker_refused",
            payload={"binding": binding(rows).to_canonical_dict(), "reason_code": "NEW_REASON"})
    elif mutation == "terminal_after_unknown":
        rows.insert(2, dataclasses.replace(rows[1], sequence=3,
            event_type="PRIVILEGED_READINESS_EFFECT_UNKNOWN", command_id=binding(rows).operation_id + ":effect_unknown"))
        rows[-1] = dataclasses.replace(rows[-1], sequence=4)
    with pytest.raises(authority.PrivilegedReadinessError):
        authority.validate_event_family(rows, request(rows))


def test_old_family_cannot_answer_different_attempt_fence(tmp_path):
    rows = events(RuntimeStore(tmp_path))
    with pytest.raises(authority.PrivilegedReadinessError):
        authority.validate_event_family(rows, dataclasses.replace(request(rows), fence_generation=2))

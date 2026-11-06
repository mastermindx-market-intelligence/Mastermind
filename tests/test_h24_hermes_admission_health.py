"""H24-08 synthetic chaos fixtures. No host, credential, or provider acquisition.

Run with stdlib unittest (no installation needed) or the repository pytest job.
Positive vectors prove composition logic only, never available fleet capacity.
"""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import socket
import sqlite3
import subprocess
import threading
import time
import unittest
from unittest.mock import patch

from control_plane import executive_host_capacity as host
from control_plane import native_capacity_v2 as capacity
from control_plane.executive_capacity_observation_producer import (
    READINESS_FIELDS, SOURCE_CONFIG_SCHEMA, build_worker_capacity_observation,
    validate_worker_capacity_readiness, validate_worker_capacity_source_config,
    worker_capacity_source_config_digest,
)
from control_plane.hermes_admission_health import (
    HealthInputError, HealthPolicy, OWNERS, compose_admission_health,
)


NOW = 1_793_956_800_000
MONO = 50_000
GIB = 1 << 30
POLICY = HealthPolicy(15_000, 1000, 2 * GIB, 5 * GIB, 90_000, 20_000, 10_000, 20_000)


def stamp(ms, milliseconds=True):
    return datetime.fromtimestamp(ms / 1000, timezone.utc).isoformat(
        timespec="milliseconds" if milliseconds else "seconds").replace("+00:00", "Z")


def rehash(snapshot):
    snapshot["snapshot_hash"] = capacity.digest({k: v for k, v in snapshot.items() if k != "snapshot_hash"})


def healthy_fixture():
    """One fully synthetic owner-bound candidate; no source is acquired here."""
    binding = {"host_ref": "host-" + "a" * 64, "boot_ref": "boot-" + "b" * 64,
        "capacity_pool_ref": "capacity-pool-" + "c" * 64,
        "source_generation_sha256": "d" * 64, "execution_scope_sha256": "e" * 64,
        "namespace_sha256": "f" * 64, "ancestry_sha256": "0" * 64}
    config = {"schema_version": SOURCE_CONFIG_SCHEMA, "host_ref": binding["host_ref"],
        "capacity_capability_id": "native-lane-1", "broker_release_identity_digest": "1" * 64,
        "broker_operation_identity_digest": "2" * 64, "broker_generation": 7,
        "executive_peer_policy_digest": "3" * 64, "worker_realm_metadata_policy_digest": "4" * 64,
        "provider_binary_identity_digest": "5" * 64}
    source_config = validate_worker_capacity_source_config(config)
    join = {"schema": capacity.JOIN_SCHEMA, "provider_capacity_schema": capacity.SCHEMA,
        "host_ref": binding["host_ref"], "capacity_capability_id": "native-lane-1",
        "capability_generation": 3, "worker_source_config_digest": worker_capacity_source_config_digest(source_config)}
    provider_source = {"source_release_commit": "a" * 40, "previous_release_commit": "b" * 40,
        "material_source_digest": "6" * 64, "source_receipt_digest": "7" * 64,
        "registration_receipt_digest": "8" * 64}
    expected = {"root_job_id": "root-1", "job_id": "job-1", "worker_id": "worker-1",
        "quota_class": "standard", "provider": "minimax", "host_binding": binding,
        "capacity_join": join, "worker_source_config": config, "provider_source": provider_source,
        "producer_sha256": "9" * 64, "realm_generation": 2,
        "enrollment_receipt_digest": "a" * 64, "slot_id": "slot-1", "lane_id": "lane-1",
        "credential_scope_sha256": "b" * 64, "process_generation": "broker-instance-7",
        "process_identity_sha256": "c" * 64, "quota_fence_generation": 4,
        "original_attempt_id": None, "original_broker_operation": None, "original_request_sha256": None}
    values = {"host_usable_memory_bytes": 32 * GIB,
        "host_available_memory_estimate_bytes": 16 * GIB, "host_swap_total_bytes": 4 * GIB,
        "host_swap_used_bytes": 0, "host_cpu_busy_milli_pct": 20_000, "host_logical_cpu_count": 8,
        "effective_cpu_capacity_millicores": 4000, "effective_memory_headroom_estimate_bytes": 8 * GIB,
        "disk_usable_bytes": 100 * GIB, "pool_total_bytes": 200 * GIB,
        "pswpin_pages_delta": 0, "pswpout_pages_delta": 0}
    metrics = {k: {"value": v, "null_reason": None} for k, v in values.items()}
    for resource, kinds in (("cpu", ("some",)), ("memory", ("some", "full")), ("io", ("some", "full"))):
        for kind in kinds:
            for measure in ("avg10", "avg60", "avg300", "total"):
                metrics[f"{resource}_{kind}_{measure}"] = {"value": 0, "null_reason": None}
    for name in ("darwin_vm_counters", "darwin_fseventsd", "host_cpu_full_pressure"):
        metrics[name] = {"value": None, "null_reason": "NOT_APPLICABLE"}
    native_host = host.build_native_host_capacity_snapshot(metrics, binding=binding,
        observed_at_ms=NOW, sample_window_ms=1000, total_observation_window_ms=1000)
    worker_capacity = build_worker_capacity_observation(source_config=source_config,
        readiness=validate_worker_capacity_readiness({k: True for k in READINESS_FIELDS}),
        observed_at=stamp(NOW, False)).to_dict()
    row = {"host_ref": binding["host_ref"], "boot_ref": binding["boot_ref"],
        "capacity_capability_id": join["capacity_capability_id"], "capability_generation": 3,
        "realm_generation": 2, "enrollment_receipt_digest": expected["enrollment_receipt_digest"],
        "provider": "minimax", "provider_enabled": True,
        "worker_source_config_digest": join["worker_source_config_digest"], "observed_at": stamp(NOW),
        "realm_auth": {"state": "authenticated", "method": "subscription_api_key", "source_quality": "native_provider"},
        "provider_health": {"state": "healthy", "error_class": None, "scope": "capability_generation", "observed_at": stamp(NOW)},
        "cooling": {"active": False, "kind": None, "reset_at": None, "evidence": "native_provider", "scope": "capability_generation", "observed_at": stamp(NOW)},
        "quota_horizons": [{"name": "subscription", "remaining": 1, "limit": 10,
            "reset_at": stamp(NOW + 60_000), "scope": "capability_generation", "observed_at": stamp(NOW)}],
        "last_provider_outcome": {"class": "success", "scope": "capability_generation", "observed_at": stamp(NOW)}}
    provider = {"schema": capacity.SCHEMA, "generated_at_ms": NOW, "source": provider_source,
        "producer_sha256": expected["producer_sha256"], "slots": [row]}
    rehash(provider)
    runtime = {
        "root": {"job_id": "root-1", "root_job_id": "root-1", "status": "RUNNING", "current_attempt_id": "root-attempt"},
        "job": {"job_id": "job-1", "root_job_id": "root-1", "status": "QUEUED", "current_attempt_id": None},
        "worker": {"worker_id": "worker-1", "provider": "minimax", "status": "AVAILABLE", "last_seen_at": stamp(NOW), "active_job_id": None},
        "quota": {"worker_id": "worker-1", "provider": "minimax", "quota_class": "standard", "status": "AVAILABLE",
            "last_seen_at": stamp(NOW), "active_job_id": None, "active_attempt_id": None,
            "fence_generation": 4, "capacity_join": join},
        "attempt": None,
    }
    slot = {k: expected[k] for k in ("slot_id", "lane_id", "worker_id", "provider", "credential_scope_sha256",
                                     "process_generation", "process_identity_sha256")}
    slot.update(host_ref=binding["host_ref"], boot_ref=binding["boot_ref"], process_alive=True,
                state="free", owner_attempt_id=None, host_occupied=False, available_count=1)
    transport = {"host_ref": binding["host_ref"], "worker_id": "worker-1", "job_id": "job-1",
        "attempt_id": None, "phase": "PRE_SUBMIT", "outcome": "ready", "effect": "no_effect",
        "broker_operation": None, "request_sha256": None}
    raw = dict(host=native_host, worker_capacity=worker_capacity, provider=provider,
               runtime=runtime, slot=slot, transport=transport)
    observations = {key: {"owner": OWNERS[key], "source_verified": True,
        "reader_generation": "reader-instance-1", "observed_at_ms": NOW,
        "observed_monotonic_ms": MONO, "expires_at_ms": NOW + 15_000, "value": value}
        for key, value in raw.items()}
    # Trusted expected identities and observed bytes are independent acquisitions.
    return dict(expected=deepcopy(expected), observations=deepcopy(observations), now_ms=NOW,
        now_monotonic_ms=MONO, reader_generation="reader-instance-1", policy=POLICY)


def raw(fixture, key):
    return fixture["observations"][key]["value"]


def codes(decision):
    return {r.code for r in decision.blocking_reasons}


def original_attempt(fixture, status="CLAIMED"):
    e, runtime, transport = fixture["expected"], raw(fixture, "runtime"), raw(fixture, "transport")
    e["original_attempt_id"] = "attempt-1"
    e.update(original_broker_operation="start", original_request_sha256="6" * 64)
    runtime["job"]["current_attempt_id"] = "attempt-1"
    runtime["attempt"] = {"attempt_id": "attempt-1", "job_id": "job-1", "worker_id": "worker-1",
        "quota_class": "standard", "status": status, "fence_generation": 4}
    transport.update(attempt_id="attempt-1", phase="SUBMITTED", outcome="unknown", effect="effect_unknown",
                     broker_operation="start", request_sha256="6" * 64)


class HermesAdmissionHealthTests(unittest.TestCase):
    def assert_blocked(self, fixture, code):
        decision = compose_admission_health(**fixture)
        self.assertFalse(decision.eligible)
        self.assertIn(code, codes(decision))
        self.assertLessEqual(decision.expires_at_ms, fixture["now_ms"])
        self.assertLessEqual(decision.expires_monotonic_ms, fixture["now_monotonic_ms"])
        for field in ("admitted", "reserved", "worker_started", "retry_authorized"):
            self.assertIs(decision.to_dict()[field], False)
        return decision

    def test_verified_candidate_is_eligible_but_cannot_admit_or_start(self):
        decision = compose_admission_health(**healthy_fixture())
        self.assertTrue(decision.eligible)
        self.assertEqual(decision.status, "READY")
        self.assertEqual(decision.recovery_action, "NEW_CANDIDATE_ELIGIBLE")
        self.assertEqual(decision.expires_at_ms, NOW + 14_000)  # oldest host sample
        self.assertEqual(decision.expires_monotonic_ms, MONO + 14_000)
        self.assertEqual(decision.blocking_reasons, ())
        self.assertEqual(set(dict(decision.source_states).values()), {"COMPLETE"})
        self.assertEqual(set(dict(decision.evidence_sha256)), set(OWNERS))
        self.assertTrue(decision.to_dict()["requires_owner_reservation"])
        for key in ("admitted", "reserved", "worker_started", "retry_authorized"):
            self.assertFalse(decision.to_dict()[key])

    def test_decision_expires_at_shortest_owner_deadline(self):
        for source in OWNERS:
            with self.subTest(source=source):
                f = healthy_fixture()
                f["observations"][source]["expires_at_ms"] = NOW + 2000
                d = compose_admission_health(**f)
                self.assertTrue(d.eligible)
                self.assertEqual(d.expires_at_ms, NOW + 2000)
                self.assertEqual(d.expires_monotonic_ms, MONO + 2000)

    def test_raw_quota_reset_and_last_seen_shorten_expiry(self):
        f = healthy_fixture()
        raw(f, "provider")["slots"][0]["quota_horizons"][0]["reset_at"] = stamp(NOW + 1000)
        rehash(raw(f, "provider"))
        self.assertEqual(compose_admission_health(**f).expires_at_ms, NOW + 1000)
        f = healthy_fixture()
        raw(f, "runtime")["quota"]["last_seen_at"] = stamp(NOW - 14_000)
        self.assertEqual(compose_admission_health(**f).expires_at_ms, NOW + 1000)

    def test_expiry_boundary_is_exclusive(self):
        f = healthy_fixture()
        f.update(now_ms=NOW + 14_000, now_monotonic_ms=MONO + 14_000)
        self.assert_blocked(f, "OBSERVATION_EXPIRED_OR_FUTURE")

    def test_missing_all_sources_differs_from_partial(self):
        f = healthy_fixture()
        f["observations"]["host"] = None
        d = self.assert_blocked(f, "SOURCE_MISSING")
        self.assertEqual(d.status, "PARTIAL")
        self.assertEqual(dict(d.source_states)["host"], "UNAVAILABLE")
        f["observations"] = dict.fromkeys(OWNERS)
        self.assertEqual(compose_admission_health(**f).status, "UNAVAILABLE")

    def test_unknown_metric_is_never_zero(self):
        f = healthy_fixture()
        observation = raw(f, "host")
        observation["metrics"]["effective_memory_headroom_estimate_bytes"] = {"value": None, "null_reason": "MISSING"}
        observation["unknown_fields"] = ["effective_memory_headroom_estimate_bytes"]
        observation["telemetry_status"] = "PARTIAL"
        before = deepcopy(observation)
        d = self.assert_blocked(f, "HOST_METRICS_PARTIAL")
        self.assertEqual(d.status, "PARTIAL")
        self.assertNotIn("MEMORY_HEADROOM_LOW", codes(d))
        self.assertEqual(observation, before)

    def test_inapplicable_fields_preserve_nulls(self):
        f = healthy_fixture()
        self.assertTrue(compose_admission_health(**f).eligible)
        for key in ("darwin_vm_counters", "darwin_fseventsd", "host_cpu_full_pressure"):
            self.assertEqual(raw(f, "host")["metrics"][key], {"value": None, "null_reason": "NOT_APPLICABLE"})

    def test_controller_created_is_not_worker_start(self):
        f = healthy_fixture()
        original_attempt(f)
        raw(f, "transport").update(phase="CONTROLLER_CREATED", outcome="ok", effect=None)
        d = self.assert_blocked(f, "ORIGINAL_TRANSPORT_RECONCILE")
        self.assertEqual(d.recovery_action, "ORIGINAL_RECONCILE")
        self.assertEqual(d.original_attempt_id, "attempt-1")
        self.assertFalse(d.to_dict()["worker_started"])

    def test_unknown_after_submit_dominates_stale_or_missing_evidence(self):
        f = healthy_fixture()
        original_attempt(f)
        f["observations"]["provider"] = None
        f["observations"]["host"]["source_verified"] = False
        d = self.assert_blocked(f, "TRANSPORT_EFFECT_UNKNOWN")
        self.assertEqual(d.recovery_action, "ORIGINAL_RECONCILE")

    def test_terminal_and_lost_attempts_never_authorize_retry(self):
        for status in ("CLAIMED", "RUNNING", "LOST", "FAILED", "COMPLETED", "CANCELLED", "RATE_LIMITED"):
            with self.subTest(status=status):
                f = healthy_fixture()
                original_attempt(f, status)
                raw(f, "transport").update(outcome="error", effect="no_effect")
                d = self.assert_blocked(f, "ORIGINAL_ATTEMPT_PRESENT")
                self.assertEqual(d.recovery_action, "ORIGINAL_RECONCILE")

    def test_disappeared_original_attempt_requires_original_reconciliation(self):
        f = healthy_fixture()
        original_attempt(f)
        raw(f, "runtime")["attempt"] = None
        self.assertEqual(self.assert_blocked(f, "ORIGINAL_ATTEMPT_MISSING").recovery_action, "ORIGINAL_RECONCILE")

    def test_running_or_lost_job_without_attempt_is_not_new_work(self):
        for status in ("RUNNING", "CHECKPOINTED", "LOST", "COMPLETED"):
            with self.subTest(status=status):
                f = healthy_fixture()
                raw(f, "runtime")["job"]["status"] = status
                self.assertEqual(self.assert_blocked(f, "JOB_NOT_UNATTEMPTED").recovery_action, "ORIGINAL_RECONCILE")

    def test_invalid_binding_does_not_erase_original_attempt(self):
        f = healthy_fixture()
        original_attempt(f)
        f["expected"]["worker_source_config"]["broker_generation"] += 1
        d = self.assert_blocked(f, "SOURCE_CONFIG_MISMATCH")
        self.assertEqual(d.recovery_action, "ORIGINAL_RECONCILE")
        self.assertEqual(d.original_attempt_id, "attempt-1")

    def test_original_request_cannot_be_substituted_with_status_or_other_submit(self):
        for field, bad in (("broker_operation", "status"), ("request_sha256", "7" * 64)):
            with self.subTest(field=field):
                f = healthy_fixture()
                original_attempt(f)
                raw(f, "transport")[field] = bad
                d = self.assert_blocked(f, "TRANSPORT_REQUEST_IDENTITY_MISMATCH")
                self.assertEqual(d.recovery_action, "ORIGINAL_RECONCILE")
                self.assertEqual(d.original_request_sha256, "6" * 64)

    def test_original_request_survives_missing_attempt_and_source_change(self):
        f = healthy_fixture()
        f["expected"].update(original_broker_operation="start", original_request_sha256="6" * 64)
        f["expected"]["worker_source_config"]["broker_generation"] += 1
        d = self.assert_blocked(f, "SOURCE_CONFIG_MISMATCH")
        self.assertEqual(d.recovery_action, "ORIGINAL_RECONCILE")
        self.assertEqual(d.original_request_sha256, "6" * 64)

    def test_role_status_cannot_substitute_for_capacity(self):
        f = healthy_fixture()
        f["observations"]["worker_capacity"]["value"] = {
            "schema": "mastermind.hermes.role_status.v3", "state": "OBSERVED", "role": "worker"}
        self.assert_blocked(f, "CAPACITY_OBSERVE_SCHEMA_INVALID")

    def test_restart_source_aba_with_same_content_never_freshens_epoch(self):
        f = healthy_fixture()
        # Content A reappears after a restart, but owner generation is now B.
        f["reader_generation"] = "reader-instance-2"
        d = self.assert_blocked(f, "READER_GENERATION_CHANGED")
        self.assertEqual(d.status, "UNAVAILABLE")
        f = healthy_fixture()
        f["expected"]["process_generation"] = "broker-instance-8"
        self.assert_blocked(f, "SLOT_IDENTITY_MISMATCH")
        f = healthy_fixture()
        f["expected"]["host_binding"]["source_generation_sha256"] = "1" * 64
        self.assert_blocked(f, "NATIVE_BINDING_MISMATCH")

    def test_broker_generation_change_invalidates_config_digest(self):
        f = healthy_fixture()
        f["expected"]["worker_source_config"]["broker_generation"] += 1
        self.assert_blocked(f, "SOURCE_CONFIG_MISMATCH")

    def test_physical_credentials_cannot_be_interchanged(self):
        f = healthy_fixture()
        raw(f, "slot")["credential_scope_sha256"] = "d" * 64
        self.assert_blocked(f, "SLOT_IDENTITY_MISMATCH")

    def test_distinct_physical_realms_do_not_share_cooling(self):
        first, second = healthy_fixture(), healthy_fixture()
        second["expected"]["credential_scope_sha256"] = "d" * 64
        second["expected"]["realm_generation"] = 5
        second["expected"]["enrollment_receipt_digest"] = "e" * 64
        raw(second, "slot")["credential_scope_sha256"] = "d" * 64
        raw(second, "provider")["slots"][0].update(realm_generation=5, enrollment_receipt_digest="e" * 64)
        rehash(raw(second, "provider"))
        cooling = raw(first, "provider")["slots"][0]["cooling"]
        cooling.update(active=True, kind="rate_limit", reset_at=stamp(NOW + 60_000))
        rehash(raw(first, "provider"))
        self.assert_blocked(first, "PROVIDER_COOLING")
        self.assertTrue(compose_admission_health(**second).eligible)
        second["observations"]["provider"] = first["observations"]["provider"]
        self.assert_blocked(second, "PROVIDER_REALM_MISMATCH")

    def test_concurrent_reads_cannot_reserve_same_available_count(self):
        f = healthy_fixture()
        before = deepcopy(f)
        with ThreadPoolExecutor(max_workers=2) as workers:
            decisions = list(workers.map(lambda _: compose_admission_health(**f), range(2)))
        self.assertTrue(all(d.eligible for d in decisions))
        self.assertTrue(all(not d.to_dict()["reserved"] for d in decisions))
        self.assertEqual(f, before)
        # Test-only incumbent-owner simulator: exactly its atomic reservation,
        # not either health read, consumes the single capacity unit.
        lock, remaining = threading.Lock(), [1]
        def reserve_at_owner(_):
            with lock:
                if not remaining[0]:
                    return False
                remaining[0] -= 1
                return True
        with ThreadPoolExecutor(max_workers=2) as workers:
            self.assertEqual(sum(workers.map(reserve_at_owner, range(2))), 1)

    def test_no_api_host_filesystem_clock_or_runtime_mutation(self):
        f = healthy_fixture()
        before = deepcopy(f)
        with patch("builtins.open", side_effect=AssertionError("filesystem")), \
             patch("os.open", side_effect=AssertionError("filesystem")), \
             patch.object(socket, "socket", side_effect=AssertionError("network")), \
             patch.object(subprocess, "Popen", side_effect=AssertionError("process")), \
             patch.object(sqlite3, "connect", side_effect=AssertionError("runtime")), \
             patch.object(time, "time", side_effect=AssertionError("wall clock")), \
             patch.object(time, "monotonic", side_effect=AssertionError("monotonic clock")):
            self.assertTrue(compose_admission_health(**f).eligible)
        self.assertEqual(f, before)

    def test_closed_inputs_and_boolean_counts(self):
        for source in OWNERS:
            with self.subTest(source=source):
                f = healthy_fixture()
                f["observations"][source]["source_verified"] = 1
                self.assert_blocked(f, "INPUT_INVALID")
        for bad in (True, -1, "1", 1.5, None):
            f = healthy_fixture()
            raw(f, "slot")["available_count"] = bad
            self.assertFalse(compose_admission_health(**f).eligible)
        f = healthy_fixture()
        raw(f, "host")["ready"] = True
        self.assert_blocked(f, "NATIVE_FIELDS_INVALID")
        f = healthy_fixture()
        f["observations"]["extra"] = None
        self.assert_blocked(f, "OBSERVATIONS_INVALID")

    def test_wrong_provider_schema_does_not_receive_optimistic_fallback(self):
        f = healthy_fixture()
        raw(f, "provider")["schema"] = "mastermind.provider_capacity.v1"
        rehash(raw(f, "provider"))
        self.assert_blocked(f, "V2_SCHEMA_INVALID")

    def test_wrong_source_owner_is_unavailable(self):
        f = healthy_fixture()
        f["observations"]["host"]["owner"] = "hermes-role-status"
        self.assert_blocked(f, "SOURCE_OWNER_MISMATCH")

    def test_missing_provider_facts_remain_partial(self):
        for field in ("enabled", "health", "auth", "cooling", "quota"):
            with self.subTest(field=field):
                f = healthy_fixture()
                row = raw(f, "provider")["slots"][0]
                if field == "enabled": row["provider_enabled"] = None
                elif field == "health": row["provider_health"]["state"] = "unknown"
                elif field == "auth": row["realm_auth"]["state"] = "unknown"
                elif field == "cooling": row["cooling"]["active"] = None
                else: row["quota_horizons"] = []
                rehash(raw(f, "provider"))
                d = compose_admission_health(**f)
                self.assertFalse(d.eligible)
                self.assertEqual(d.status, "PARTIAL")

    def test_missing_quota_does_not_hide_known_provider_failure(self):
        for fault in ("disabled", "unauthenticated", "unhealthy", "auth_error", "transport"):
            with self.subTest(fault=fault):
                f = healthy_fixture()
                row = raw(f, "provider")["slots"][0]
                row["quota_horizons"] = []
                if fault == "disabled": row["provider_enabled"] = False
                elif fault == "unauthenticated": row["realm_auth"]["state"] = "unauthenticated"
                elif fault == "unhealthy": row["provider_health"]["state"] = "unhealthy"
                elif fault == "auth_error": row["provider_health"]["error_class"] = "auth"
                else: row["last_provider_outcome"]["class"] = "transport"
                rehash(raw(f, "provider"))
                d = compose_admission_health(**f)
                self.assertEqual(d.status, "BLOCKED")
                self.assertEqual(d.recovery_action, "NO_ELIGIBLE_CANDIDATE")

    def test_invalid_clocks_policy_are_rejected_without_read(self):
        for key, bad in (("now_ms", True), ("now_monotonic_ms", -1), ("reader_generation", "")):
            with self.subTest(key=key):
                f = healthy_fixture()
                f[key] = bad
                with self.assertRaises(HealthInputError): compose_admission_health(**f)
        with self.assertRaises(HealthInputError): HealthPolicy(60_000, 1, 1, 1, 1, 1, 1, 1)

    def test_monotonic_reset_and_wall_clock_jump_are_not_freshness(self):
        for wall, mono in ((NOW, MONO - 1), (NOW + 3000, MONO), (NOW, MONO + 3000)):
            f = healthy_fixture()
            f.update(now_ms=wall, now_monotonic_ms=mono)
            self.assert_blocked(f, "MONOTONIC_CLOCK_MISMATCH")

    def test_monotonic_expiry_cannot_be_extended_by_wall_clock(self):
        f = healthy_fixture()
        f.update(now_ms=NOW + 14_000, now_monotonic_ms=MONO + 15_000)
        d = self.assert_blocked(f, "MONOTONIC_OBSERVATION_EXPIRED")
        self.assertFalse(d.eligible)

    def test_rewrapped_stale_provider_quota_remains_stale(self):
        f = healthy_fixture()
        raw(f, "provider")["slots"][0]["quota_horizons"][0]["observed_at"] = stamp(NOW - 60_000)
        rehash(raw(f, "provider"))
        self.assert_blocked(f, "V2_OBSERVATION_STALE")

    def test_429_cooling_expiry_does_not_schedule_retry(self):
        f = healthy_fixture()
        row = raw(f, "provider")["slots"][0]
        row["cooling"].update(active=True, kind="rate_limit", reset_at=stamp(NOW + 1000))
        row["last_provider_outcome"]["class"] = "quota"
        rehash(raw(f, "provider"))
        d = self.assert_blocked(f, "PROVIDER_COOLING")
        self.assertEqual(d.recovery_action, "NO_ELIGIBLE_CANDIDATE")
        self.assertLessEqual(d.expires_at_ms, NOW)

    def test_no_partial_success_by_mixing_provider_rows(self):
        f = healthy_fixture()
        value = raw(f, "provider")
        other = deepcopy(value["slots"][0])
        other["capacity_capability_id"] = "other-capability"
        other["realm_generation"] = 5
        value["slots"][0]["quota_horizons"] = []
        value["slots"].append(other)
        rehash(value)
        self.assert_blocked(f, "V2_QUOTA_UNQUALIFIED")

    def test_closed_nested_inputs_have_no_unhandled_type_errors(self):
        baseline = healthy_fixture()
        paths = []
        def walk(value, path):
            pairs = value.items() if type(value) is dict else enumerate(value) if type(value) is list else ()
            for key, child in pairs:
                paths.append(path + (key,))
                walk(child, path + (key,))
        for key in ("expected", "observations"):
            walk(baseline[key], (key,))
        for path in paths:
            for malformed in (None, [], {}, True, "malformed"):
                with self.subTest(path=path, malformed=malformed):
                    f = deepcopy(baseline)
                    target = f
                    for key in path[:-1]: target = target[key]
                    target[path[-1]] = malformed
                    # Let provider semantic validation see malformed nested
                    # values without stopping first at the snapshot digest.
                    if path[:3] == ("observations", "provider", "value") and len(path) > 3:
                        rehash(raw(f, "provider"))
                    decision = compose_admission_health(**f)
                    self.assertIs(decision.to_dict()["reserved"], False)
                    self.assertIs(decision.to_dict()["retry_authorized"], False)


# Named, independently mutated failure-propagation vectors. Rehash provider
# documents to test semantic refusals, not merely tamper detection.
CHAOS_FIXTURE = (
    ("old_boot", "host", ("boot_ref",), "boot-" + "1" * 64, "NATIVE_BINDING_MISMATCH"),
    ("vanished_root", "runtime", ("root",), None, "ROOT_MISSING"),
    ("cancelled_root", "runtime", ("root", "status"), "CANCEL_REQUESTED", "ROOT_OR_JOB_NOT_ACTIVE"),
    ("stale_quota", "runtime", ("quota", "last_seen_at"), stamp(NOW - 60_000), "OBSERVATION_EXPIRED_OR_FUTURE"),
    ("wrong_realm", "provider", ("slots", 0, "realm_generation"), 3, "PROVIDER_REALM_MISMATCH"),
    ("source_missing", "provider", ("source",), None, "V2_FIELDS_INVALID"),
    ("memory_headroom", "host", ("metrics", "effective_memory_headroom_estimate_bytes", "value"), GIB, "MEMORY_HEADROOM_LOW"),
    ("memory_pressure", "host", ("metrics", "memory_some_avg10", "value"), 50_000, "MEMORY_PRESSURE"),
    ("cpu_pressure", "host", ("metrics", "host_cpu_busy_milli_pct", "value"), 99_000, "CPU_PRESSURE"),
    ("io_pressure", "host", ("metrics", "io_full_avg10", "value"), 50_000, "IO_PRESSURE"),
    ("disk_pressure", "host", ("metrics", "disk_usable_bytes", "value"), GIB, "DISK_HEADROOM_LOW"),
    ("slot_collision", "slot", ("state",), "held", "SLOT_NOT_FREE"),
    ("slot_other_attempt", "slot", ("owner_attempt_id",), "other-attempt", "SLOT_NOT_FREE"),
    ("worker_dead", "slot", ("process_alive",), False, "WORKER_PROCESS_DEAD"),
    ("host_occupied", "slot", ("host_occupied",), True, "HOST_OCCUPIED"),
    ("zero_capacity", "slot", ("available_count",), 0, "NO_AVAILABLE_CAPACITY"),
    ("unknown_capacity", "slot", ("available_count",), None, "AVAILABLE_COUNT_UNKNOWN"),
    ("worker_offline", "runtime", ("worker", "status"), "OFFLINE", "WORKER_NOT_AVAILABLE"),
    ("quota_busy", "runtime", ("quota", "status"), "BUSY", "QUOTA_NOT_AVAILABLE"),
    ("quota_exhausted", "provider", ("slots", 0, "quota_horizons", 0, "remaining"), 0, "PROVIDER_QUOTA_EXHAUSTED"),
    ("provider_unhealthy", "provider", ("slots", 0, "provider_health", "state"), "unhealthy", "V2_HEALTH_UNQUALIFIED"),
    ("failed_transport", "transport", ("outcome",), "error", "TRANSPORT_NOT_READY"),
    ("unknown_transport", "transport", ("outcome",), "unknown", "TRANSPORT_NOT_READY"),
    ("capacity_capability_changed", "runtime", ("quota", "capacity_join", "capability_generation"), 9, "QUOTA_BINDING_MISMATCH"),
    ("source_registration_changed", "provider", ("source", "registration_receipt_digest"), "f" * 64, "CAPACITY_SOURCE_MISMATCH"),
)


def _chaos_test(vector):
    name, source, path, value, code = vector
    def test(self):
        f = healthy_fixture()
        target = raw(f, source)
        for part in path[:-1]: target = target[part]
        target[path[-1]] = value
        if source == "provider": rehash(raw(f, "provider"))
        self.assert_blocked(f, code)
    test.__name__ = "test_chaos_" + name
    return test


for _vector in CHAOS_FIXTURE:
    setattr(HermesAdmissionHealthTests, "test_chaos_" + _vector[0], _chaos_test(_vector))


if __name__ == "__main__":
    unittest.main()

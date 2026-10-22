"""Original-operation retention in the incumbent Fabric lease database.

This module supplies no authentication, enrollment, route or CLI. Only the
existing owner may compose it after authenticating Control and verifying its
original Runtime request and fixed account mapping. Binding/receipt digests
are correlation evidence, never credentials or proof of cleanup by themselves.
Ordinary leases retain their existing behavior.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import re


_IDENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_IDENT_FIELDS = frozenset(("root_id", "parent_id", "job_id", "attempt_id",
                           "pool", "account", "model", "host", "task_class"))
_DIGEST_FIELDS = frozenset(("start_request_sha256", "configuration_sha256",
                            "realm_binding_sha256", "control_identity_sha256"))
_BINDING_KEYS = _IDENT_FIELDS | _DIGEST_FIELDS | {"schema", "fence", "owner_pid"}
_SETTLEMENT_KEYS = frozenset(("process_receipt_sha256", "cleanup_record_sha256",
                              "assignment_observation_sha256", "control_retention_sha256",
                              "physical_release_sha256"))


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False)


def _binding(value):
    if type(value) is not dict or set(value) != _BINDING_KEYS:
        raise ValueError("native_binding_shape")
    if value["schema"] != "mastermind.fabric_native_admission.v1":
        raise ValueError("native_binding_schema")
    for name, pattern in [(n, _IDENT) for n in _IDENT_FIELDS] + [(n, _SHA) for n in _DIGEST_FIELDS]:
        if type(value[name]) is not str or not pattern.fullmatch(value[name]):
            raise ValueError("native_binding_value")
    for name in ("fence", "owner_pid"):
        if type(value[name]) is not int or not 1 <= value[name] <= 2**63 - 1:
            raise ValueError("native_binding_value")
    # Runtime Job/Attempt are globally assigned identifiers. A changed root,
    # parent, fence, account or source must collide, not mint another admission.
    key = hashlib.sha256(_json([value["job_id"], value["attempt_id"]]).encode()).hexdigest()
    return key, _json(value)


def ensure_native_schema(conn):
    columns = {row[1] for row in conn.execute("PRAGMA table_info(leases)")}
    for name in ("native_key", "native_binding", "native_grant",
                 "native_settlement", "native_reconciliation"):
        if name not in columns:
            conn.execute(f"ALTER TABLE leases ADD COLUMN {name} TEXT")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS leases_native_original "
                 "ON leases(native_key) WHERE native_key IS NOT NULL")


def retain_native_grant(conn, lease_id, binding):
    """Runs in the original grant transaction, before its one commit."""
    if binding is None:
        return
    key, raw = _binding(binding)
    row = conn.execute("SELECT * FROM leases WHERE id=?", (lease_id,)).fetchone()
    expected = {"orchestrator_id": binding["root_id"], "pool": binding["pool"],
                "account": binding["account"], "model": binding["model"],
                "host": binding["host"], "pid": binding["owner_pid"],
                "task_class": binding["task_class"]}
    if row is None or any(row[k] != v for k, v in expected.items()):
        raise ValueError("native_grant_mapping_changed")
    grant = {"schema": "mastermind.fabric_native_grant.v1", "original_key": key,
             "binding_sha256": hashlib.sha256(raw.encode()).hexdigest(),
             "lease_id": lease_id, "account": row["account"], "pool": row["pool"],
             "granted_at": row["granted_at"], "ttl": row["ttl"]}
    conn.execute("UPDATE leases SET native_key=?,native_binding=?,native_grant=? WHERE id=?",
                 (key, raw, _json(grant), lease_id))


def hold_native_uncertain(conn, row):
    if row["native_key"] is None:
        return False
    conn.execute("UPDATE leases SET native_reconciliation=? WHERE id=?",
                 ("liveness_or_renewal_unconfirmed", row["id"]))
    return True


class NativeBrokerAdmissions:
    """Fixed data operations for an authenticated owner; not a public RPC API."""

    def _native_lookup(self, conn, binding, lease_id=None):
        key, raw = _binding(binding)
        row = conn.execute("SELECT * FROM leases WHERE native_key=?", (key,)).fetchone()
        if row is None:
            return None
        if row["native_binding"] != raw or (lease_id is not None and row["id"] != lease_id):
            raise ValueError("native_original_changed")
        return row

    @staticmethod
    def _native_view(row):
        return {"state": "SETTLED" if row["native_settlement"] else "RETAINED",
                "grant": json.loads(row["native_grant"]),
                "lease_state": row["state"],
                "reconciliation_required": row["native_reconciliation"] is not None,
                "settlement": json.loads(row["native_settlement"]) if row["native_settlement"] else None}

    def read_native_admission(self, binding):
        _binding(binding)
        lock = self._lock()
        try:
            conn = self._conn()
            try:
                row = self._native_lookup(conn, binding)
                return self._native_view(row) if row else {"state": "NOT_RETAINED"}
            finally:
                conn.close()
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)
            lock.close()

    def acquire_native_admission(self, binding):
        _binding(binding)
        # Freeze the caller's bytes before any wait or effect.
        binding = json.loads(_json(binding))
        lock = self._lock()
        try:
            conn = self._conn()
            try:
                old = self._native_lookup(conn, binding)
                if old is not None:
                    return self._native_view(old)
            finally:
                conn.close()
            if self.provider_name(binding["pool"]) != binding["pool"]:
                raise ValueError("native_canonical_pool_required")
            self._gc_locked()
            result, _, reason = self._try_acquire(
                binding["root_id"], binding["pool"], binding["account"],
                binding["task_class"], binding["host"], binding["owner_pid"],
                None, None, binding["model"], None, native_binding=binding)
            if not result.ok:
                return {"state": "DENIED", "reason": reason}
            conn = self._conn()
            try:
                row = self._native_lookup(conn, binding, result.lease_id)
                if row is None:
                    raise ValueError("native_admission_unconfirmed")
                return self._native_view(row)
            finally:
                conn.close()
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)
            lock.close()

    def heartbeat_native_admission(self, binding, lease_id):
        _binding(binding)
        lock = self._lock()
        try:
            conn = self._conn()
            try:
                if self._native_lookup(conn, binding, lease_id) is None:
                    raise ValueError("native_admission_not_retained")
            finally:
                conn.close()
            self._gc_locked()
            conn = self._conn()
            try:
                row = self._native_lookup(conn, binding, lease_id)
                if row is None:
                    raise ValueError("native_admission_not_retained")
                if (row["native_reconciliation"] or row["native_settlement"]
                        or row["state"] not in ("held", "rented")):
                    return {"ok": False, "reason": "native_reconciliation_or_settlement", **self._native_view(row)}
                conn.execute("UPDATE leases SET last_heartbeat=? WHERE id=?", (self.now(), lease_id))
                conn.commit()
                return {"ok": True, "reason": "held", **self._native_view(row)}
            finally:
                conn.close()
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)
            lock.close()

    def settle_native_admission(self, binding, lease_id, settlement):
        _binding(binding)
        if (type(settlement) is not dict or set(settlement) != _SETTLEMENT_KEYS
                or any(type(v) is not str or not _SHA.fullmatch(v) for v in settlement.values())):
            raise ValueError("native_exact_terminal_receipts_required")
        raw = _json(settlement)
        lock = self._lock()
        try:
            conn = self._conn()
            try:
                row = self._native_lookup(conn, binding, lease_id)
                if row is None:
                    raise ValueError("native_admission_not_retained")
                if row["native_settlement"] is not None:
                    if row["native_settlement"] != raw:
                        raise ValueError("native_settlement_changed")
                    return self._native_view(row)
                if row["state"] not in ("held", "rented"):
                    raise ValueError("native_lease_state_unconfirmed")
                # Actual proof/authentication is the fixed owner's prerequisite.
                # No ordinary release path may substitute for this retained join.
                conn.execute("UPDATE leases SET state='released',native_settlement=? WHERE id=?", (raw, lease_id))
                conn.commit()
                return self._native_view(self._native_lookup(conn, binding, lease_id))
            finally:
                conn.close()
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)
            lock.close()

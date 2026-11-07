#!/usr/bin/env python3
"""Cluster-wide agent-slot lease broker (R11–R16).

Single writer: SQLite at ext/broker/leases.sqlite behind a file lock.
No inbound listeners. Secret-free stdout (names only, never key values).

CLI:
  acquire --orchestrator-id ID --pool P [--account A] [--task-class C]
          [--host H] [--pid N] [--ttl S] [--wait S] [--poll S]
  heartbeat <lease-id>
  release <lease-id>
  plan --class C --need N [--orchestrator-id ID]
  status
  gc
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from contextvars import ContextVar
import fcntl
import hashlib
import json
import math
import os
import re
import socket
import sqlite3
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from commission_deadline import (CommissionDeadlineExpired, require_remaining,
                                 validate_deadline_ns)

# Only acquire sets this context. Independent threads/controllers and existing
# heartbeat/release/settlement operations never inherit another acquire's fuse.
_ACQUIRE_DEADLINE_NS = ContextVar("fabric_acquire_deadline_ns", default=None)
_APPLICATION_ACCOUNTS = ContextVar("fabric_application_accounts", default=None)


class ApplicationAdmissionError(ValueError):
    """A bounded refusal; never a provider or credential diagnostic."""

    def __init__(self, code):
        self.code = code
        super().__init__("application admission refused: " + code)


class ApplicationSelectionError(ApplicationAdmissionError):
    """A selection condition failed before allocation; no new turn was admitted."""


def _application_selection_purpose(value):
    """Validate the trusted enrollment projection, never an HTTP authority field."""
    if type(value) is not dict or set(value) != {"purpose_id", "source_ref", "task"}:
        raise ApplicationSelectionError("purpose_invalid")
    _application_id(value["purpose_id"])
    reference = value["source_ref"]
    if (type(reference) is not str or not reference.strip() or len(reference) > 512
            or any(ord(c) < 32 for c in reference)):
        raise ApplicationSelectionError("purpose_source_invalid")
    task = value["task"]
    required = {"task_class", "route_key"}
    optional = {"task_complexity", "needs", "subject_pool", "escalation_reason"}
    if type(task) is not dict or not required <= set(task) or set(task) - required - optional:
        raise ApplicationSelectionError("purpose_task_invalid")
    for key in required:
        _application_id(task[key])
    for key in ("task_complexity", "subject_pool"):
        if task.get(key) is not None:
            _application_id(task[key])
    if "needs" in task and (type(task["needs"]) is not list or len(task["needs"]) > 32
            or any(type(n) is not str or re.fullmatch(r"[a-z][a-z0-9_]{0,63}", n) is None
                   for n in task["needs"])):
        raise ApplicationSelectionError("purpose_needs_invalid")
    witness = task.get("escalation_reason")
    if witness is not None and (type(witness) is not str or len(witness) > 2048
            or any(ord(c) < 32 for c in witness)):
        raise ApplicationSelectionError("purpose_witness_invalid")
    encoded = _application_json(value)
    return encoded, hashlib.sha256(encoded.encode()).hexdigest()


def _application_id(value):
    if not isinstance(value, str) or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", value) is None:
        raise ApplicationAdmissionError("invalid_identity")
    return value


def _application_model(value):
    if not isinstance(value, str) or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_./:-]{0,127}", value) is None:
        raise ApplicationAdmissionError("invalid_model")
    return value


def _application_json(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError, OverflowError, RecursionError):
        raise ApplicationAdmissionError("invalid_document") from None


def _application_time(value):
    if type(value) not in (int, float):
        raise ApplicationAdmissionError("invalid_time")
    try:
        if not math.isfinite(value) or value <= 0:
            raise ApplicationAdmissionError("invalid_time")
    except (OverflowError, ValueError):
        raise ApplicationAdmissionError("invalid_time") from None
    return float(value)


_APPLICATION_HTTP_POOLS = frozenset({"bailian"})
_APPLICATION_HTTP_RECIPE_FIELDS = frozenset({
    "schema", "pool", "model", "driver_id", "realm_id", "provider", "protocol",
    "endpoint", "source_projection_sha256", "credential_owner",
})
_APPLICATION_HTTP_RECEIPT_FIELDS = frozenset({
    "terminal_kind", "recipe_digest", "logical_payload_digest", "wire_body_digest",
    "delivery_digest", "served_model",
})


def _application_digest(value):
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ApplicationAdmissionError("invalid_transport_commitment")
    return value


def _application_http_recipe(recipe, *, pool, model):
    """Commit an owner-projected recipe; the fresh grant supplies authority.

    This does not choose a realm or endpoint. The trusted handler compiles the
    exact sealed H identity, and the same transaction compares its complete
    digest with the canonical grant before any account can be admitted.
    """
    if (not isinstance(recipe, dict) or set(recipe) != _APPLICATION_HTTP_RECIPE_FIELDS
            or recipe["schema"] != "mastermind.application_http_recipe.v1"
            or not isinstance(pool, str) or pool not in _APPLICATION_HTTP_POOLS or recipe["pool"] != pool
            or recipe["model"] != model or recipe["protocol"] != "responses"
            or recipe["credential_owner"] != "bailian_keys._codex_key_value"):
        raise ApplicationAdmissionError("invalid_transport_recipe")
    for key in ("driver_id", "realm_id", "provider"):
        _application_id(recipe[key])
    _application_model(model)
    _application_digest(recipe["source_projection_sha256"])
    from urllib.parse import urlsplit
    endpoint = recipe["endpoint"]
    if not isinstance(endpoint, str) or len(endpoint) > 1024:
        raise ApplicationAdmissionError("invalid_transport_recipe")
    try:
        parsed = urlsplit(endpoint)
    except ValueError:
        raise ApplicationAdmissionError("invalid_transport_recipe") from None
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username is not None
            or parsed.password is not None or parsed.query or parsed.fragment
            or not parsed.path.endswith("/responses")
            or any(ord(c) < 33 or ord(c) > 126 for c in endpoint)):
        raise ApplicationAdmissionError("invalid_transport_recipe")
    encoded = _application_json(recipe)
    return encoded, hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _application_receipt(receipt):
    """Validate the original handler's final upstream response receipt."""
    fields = {"dispatch_id", "request_digest", "lease_id", "account", "model", "response_digest",
              "status_code", "completed_at", "usage"}
    if (not isinstance(receipt, dict)
            or set(receipt) not in (fields, fields | _APPLICATION_HTTP_RECEIPT_FIELDS)):
        raise ApplicationAdmissionError("invalid_terminal_receipt")
    if "terminal_kind" in receipt:
        if receipt["terminal_kind"] != "http_responses_v1":
            raise ApplicationAdmissionError("invalid_terminal_receipt")
        for key in ("recipe_digest", "logical_payload_digest", "wire_body_digest"):
            _application_digest(receipt[key])
        if receipt["delivery_digest"] is not None:
            _application_digest(receipt["delivery_digest"])
        if receipt["served_model"] is not None and (not isinstance(receipt["served_model"], str)
                or not 1 <= len(receipt["served_model"]) <= 256 or "\x00" in receipt["served_model"]):
            raise ApplicationAdmissionError("invalid_terminal_receipt")
    for key in ("dispatch_id", "lease_id", "account"):
        _application_id(receipt[key])
    _application_model(receipt["model"])
    for key in ("request_digest", "response_digest"):
        if not isinstance(receipt[key], str) or re.fullmatch(r"[0-9a-f]{64}", receipt[key]) is None:
            raise ApplicationAdmissionError("invalid_terminal_receipt")
    if type(receipt["status_code"]) is not int or not 200 <= receipt["status_code"] <= 599:
        raise ApplicationAdmissionError("invalid_terminal_receipt")
    _application_time(receipt["completed_at"])
    usage = receipt["usage"]
    if not isinstance(usage, dict) or set(usage) != {"input_tokens", "output_tokens"}:
        raise ApplicationAdmissionError("invalid_terminal_receipt")
    if any(value is not None and (type(value) is not int or not 0 <= value <= 10**12) for value in usage.values()):
        raise ApplicationAdmissionError("invalid_terminal_receipt")
    return _application_json(receipt)


def _application_stored_terminal(request, turn):
    """Positive settlement proof; corrupt or unfamiliar states retain custody."""
    if request["state"] != "terminal" or not isinstance(request["terminal_receipt"], str):
        return None
    try:
        receipt = json.loads(request["terminal_receipt"])
        encoded = _application_receipt(receipt)
        if (encoded != request["terminal_receipt"]
                or receipt["dispatch_id"] != request["dispatch_id"]
                or receipt["request_digest"] != request["request_digest"]
                or any(receipt[key] != turn[key] for key in ("lease_id", "account", "model"))
                or receipt["completed_at"] < request["created_at"]):
            return None
        if turn["pool"] in _APPLICATION_HTTP_POOLS:
            _, digest = _application_http_recipe(json.loads(turn["recipe_json"]),
                                                pool=turn["pool"], model=turn["model"])
            if (receipt.get("terminal_kind") != "http_responses_v1"
                    or digest != turn["recipe_digest"]
                    or receipt["recipe_digest"] != digest
                    or any(receipt[key] != request[key] for key in (
                        "recipe_digest", "logical_payload_digest", "wire_body_digest"))):
                return None
        elif "terminal_kind" in receipt:
            return None
        return receipt
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError):
        return None


_APPLICATION_GRANT_FIELDS = frozenset({
    "grant_id", "purpose", "enabled", "principal_id", "credential_ref", "admission_root",
    "caller_hosts", "workloads", "pool", "accounts", "models", "route", "stream",
    "expires_at", "max_turn_seconds", "max_steps", "qualification_ref", "application_permission_ref",
})


def _read_application_accounts(path):
    """Fresh owner document; no mtime fallback, duplicate keys or secret lookup."""
    try:
        import yaml

        class ClosedLoader(yaml.SafeLoader):
            pass

        def mapping(loader, node, deep=False):
            result = {}
            for key_node, value_node in node.value:
                key = loader.construct_object(key_node, deep=deep)
                if not isinstance(key, str) or key in result:
                    raise ApplicationAdmissionError("invalid_accounts_document")
                result[key] = loader.construct_object(value_node, deep=deep)
            return result

        ClosedLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, mapping)
        with open(path, "rb") as source:
            raw = source.read(2 * 1024 * 1024 + 1)
        if len(raw) > 2 * 1024 * 1024:
            raise ApplicationAdmissionError("invalid_accounts_document")
        document = yaml.load(raw.decode("utf-8"), Loader=ClosedLoader)
        if (not isinstance(document, dict)
                or document.get("schema") != "mastermind.provider_accounts.v1"
                or not isinstance(document.get("providers"), dict)
                or not isinstance(document.get("application_grants"), list)):
            raise ApplicationAdmissionError("invalid_accounts_document")
        _application_json(document)
        seen = set()
        for grant in document["application_grants"]:
            if not isinstance(grant, dict):
                raise ApplicationAdmissionError("invalid_application_grant")
            if not isinstance(grant.get("pool"), str):
                raise ApplicationAdmissionError("invalid_application_grant")
            expected_fields = (_APPLICATION_GRANT_FIELDS | {"recipe_digest"}
                               if grant.get("pool") in _APPLICATION_HTTP_POOLS
                               else _APPLICATION_GRANT_FIELDS)
            if set(grant) != expected_fields:
                raise ApplicationAdmissionError("invalid_application_grant")
            if "recipe_digest" in grant:
                _application_digest(grant["recipe_digest"])
            for key in ("grant_id", "principal_id", "credential_ref", "admission_root"):
                _application_id(grant[key])
            if grant["grant_id"] in seen:
                raise ApplicationAdmissionError("duplicate_application_grant")
            seen.add(grant["grant_id"])
            if (grant["purpose"] != "APPLICATION" or type(grant["enabled"]) is not bool
                    or grant["pool"] not in ({"go"} | _APPLICATION_HTTP_POOLS)
                    or grant["route"] != "/v1/chat/completions"
                    or grant["stream"] is not False):
                raise ApplicationAdmissionError("invalid_application_grant")
            _application_time(grant["expires_at"])
            for key, limit in (("max_turn_seconds", 900), ("max_steps", 64)):
                if type(grant[key]) is not int or not 1 <= grant[key] <= limit:
                    raise ApplicationAdmissionError("invalid_application_grant")
            for key in ("caller_hosts", "workloads", "accounts", "models"):
                values = grant[key]
                if not isinstance(values, list) or not 1 <= len(values) <= 128:
                    raise ApplicationAdmissionError("invalid_application_grant")
                for value in values:
                    (_application_model if key == "models" else _application_id)(value)
                if len(set(values)) != len(values):
                    raise ApplicationAdmissionError("invalid_application_grant")
            for key in ("qualification_ref", "application_permission_ref"):
                if (not isinstance(grant[key], str) or not grant[key].strip()
                        or len(grant[key]) > 512 or any(ord(c) < 32 for c in grant[key])):
                    raise ApplicationAdmissionError("invalid_application_grant")
            provider = document["providers"].get(grant["pool"])
            if (not isinstance(provider, dict) or type(provider.get("enabled")) is not bool
                    or not isinstance(provider.get("accounts"), list)):
                raise ApplicationAdmissionError("invalid_account_reference")
            for account in provider["accounts"]:
                _application_id(account["name"])
                if (type(account.get("per_account_cap")) is not int
                        or not 0 <= account["per_account_cap"] <= 4096
                        or ("enabled" in account and type(account["enabled"]) is not bool)):
                    raise ApplicationAdmissionError("invalid_account_reference")
            account_names = [a.get("name") for a in provider["accounts"] if isinstance(a, dict)]
            if (len(account_names) != len(provider["accounts"])
                    or any(not isinstance(name, str) for name in account_names)
                    or len(set(account_names)) != len(account_names)
                    or not set(grant["accounts"]).issubset(account_names)):
                raise ApplicationAdmissionError("invalid_account_reference")
        return document
    except ApplicationAdmissionError:
        raise
    except Exception:
        raise ApplicationAdmissionError("accounts_unavailable") from None


class _DeadlineConnection(sqlite3.Connection):
    """The incumbent SQLite owner, with waits narrowed before every statement."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.deadline_ns = _ACQUIRE_DEADLINE_NS.get()
        if self.deadline_ns is not None:
            self.set_progress_handler(
                lambda: int(time.monotonic_ns() >= self.deadline_ns), 1000)

    def _before_statement(self):
        if self.deadline_ns is not None:
            remaining = require_remaining(self.deadline_ns)
            # Recompute before each statement; successive SQLite lock waits
            # cannot each spend the same original remaining-time snapshot.
            super().execute("PRAGMA busy_timeout=" + str(min(30000, int(remaining * 1000))))

    def execute(self, *args, **kwargs):
        self._before_statement()
        return super().execute(*args, **kwargs)

    def commit(self):
        self._before_statement()
        return super().commit()


def _connect(path):
    deadline = _ACQUIRE_DEADLINE_NS.get()
    timeout = 30 if deadline is None else min(30, require_remaining(deadline))
    return sqlite3.connect(path, timeout=timeout,
                           factory=sqlite3.Connection if deadline is None else _DeadlineConnection)

HERE = os.path.dirname(os.path.abspath(__file__))
KIT = os.path.abspath(os.path.join(HERE, ".."))
DEFAULT_DB = os.path.join(HERE, "broker", "leases.sqlite")
DEFAULT_LOCK = os.path.join(HERE, "broker", "leases.lock")
DEFAULT_ACCOUNTS = os.path.join(KIT, "orch", "fabric", "accounts.yaml")
STATUS_JSON = os.path.join(KIT, "orch", "fabric", "status.json")
GROK_EXHAUSTED = os.path.join(HERE, "GROK_EXHAUSTED")
HOSTS_JSON = os.path.join(HERE, "hosts.json")

POOL_ALIASES = {"qwen": "bailian"}
HELD_STATES = ("held", "rented")
DEFAULT_TTL = 180
RENT_TTL = 90
WAITER_STALE_S = 90  # demand grace; live acquirers refresh last_heartbeat
CLASS_PRIORITY = {
    "application": 3,
    "heal": 0,
    "heals": 0,
    "fix_build": 1,
    "build": 1,
    "builds": 1,
    "fix": 1,
    "review": 2,
    "reviews": 2,
    "census": 3,
    "audit": 3,
    "mechanical": 3,
    "unknown": 4,
}


def _this_host() -> str:
    return (os.environ.get("POOL_BROKER_HOST") or socket.gethostname() or "studio").split()[0]


def _now_iso(ts: Optional[float] = None) -> str:
    return datetime.fromtimestamp(ts or time.time(), tz=timezone.utc).isoformat()


def _parse_iso(s: Optional[str]) -> Optional[float]:
    if not s:
        return None
    raw = str(s).strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(raw).timestamp()
    except ValueError:
        return None


def _load_yaml(path: str) -> Dict[str, Any]:
    with open(path, encoding="utf-8") as fh:
        try:
            import yaml  # type: ignore
        except ImportError:
            raise RuntimeError("PyYAML required to read accounts.yaml")
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise RuntimeError("accounts.yaml must be a mapping")
    return data


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _class_priority(task_class: str) -> int:
    return CLASS_PRIORITY.get((task_class or "unknown").lower(), 4)


@dataclass
class AcquireResult:
    ok: bool
    lease_id: str = ""
    account: str = ""
    state: str = ""
    reason: str = ""
    orchestrator_id: str = ""
    pool: str = ""
    quota_blockade: Optional[Dict[str, Any]] = None

    def line(self) -> str:
        if self.ok:
            return f"LEASE={self.lease_id} ACCOUNT={self.account}"
        return f"WAIT reason={self.reason or 'unavailable'}"


@dataclass(frozen=True)
class HeartbeatResult:
    ok: bool
    reason: str
    ttl: float | None = None

    def __bool__(self) -> bool:
        return self.ok


def _broker_controller_pid_observation(pid: object) -> str:
    """Advisory only: an OS PID is not a verified original worker return.

    Called only while viewing this broker's own live snapshot, for the
    controller-side PID passed by remote_sub.sh on original `acquire`.
    Never expire, release, change a lease, or interpret PID reuse as proof.
    """
    if type(pid) is not int or pid <= 0:
        return "UNVERIFIED"
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return "ABSENT"
    except OSError:  # Permission denied/unknown is not proof of process death.
        return "UNVERIFIED"
    return "PRESENT_UNVERIFIED"


class Broker:
    """Single-writer lease broker. All mutating methods take the file lock."""

    def __init__(
        self,
        db_path: str = DEFAULT_DB,
        lock_path: str = DEFAULT_LOCK,
        accounts_path: str = DEFAULT_ACCOUNTS,
        now_fn: Optional[Callable[[], float]] = None,
        check_pid: bool = True,
        external_gates: bool = True,
        grok_marker: Optional[str] = None,
        this_host: Optional[str] = None,
        status_json: Optional[str] = None,
        hosts_path: Optional[str] = None,
    ) -> None:
        self.hosts_path = hosts_path or HOSTS_JSON
        self.db_path = db_path
        self.lock_path = lock_path
        self.accounts_path = accounts_path
        self.now_fn = now_fn or time.time
        self.check_pid = check_pid
        self.external_gates = external_gates
        self.grok_marker = grok_marker or GROK_EXHAUSTED
        self.this_host = this_host or _this_host()
        self.status_json = status_json or STATUS_JSON
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        os.makedirs(os.path.dirname(self.lock_path) or ".", exist_ok=True)
        self._accounts_cache: Optional[Dict[str, Any]] = None
        self._accounts_mtime: Optional[float] = None
        self._init_db()

    def _init_db(self) -> None:
        conn = _connect(self.db_path)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(
                """CREATE TABLE IF NOT EXISTS leases (
                    id TEXT PRIMARY KEY,
                    orchestrator_id TEXT NOT NULL,
                    pool TEXT NOT NULL,
                    account TEXT NOT NULL,
                    task_class TEXT NOT NULL,
                    model TEXT NOT NULL DEFAULT '',
                    host TEXT NOT NULL,
                    pid INTEGER NOT NULL,
                    granted_at REAL NOT NULL,
                    ttl INTEGER NOT NULL,
                    last_heartbeat REAL NOT NULL,
                    state TEXT NOT NULL,
                    renewable INTEGER NOT NULL DEFAULT 1
                )"""
            )
            conn.execute(
                """CREATE TABLE IF NOT EXISTS waiters (
                    id TEXT PRIMARY KEY,
                    orchestrator_id TEXT NOT NULL,
                    pool TEXT NOT NULL,
                    account TEXT,
                    task_class TEXT NOT NULL,
                    host TEXT,
                    enqueued_at REAL NOT NULL,
                    priority INTEGER NOT NULL,
                    need INTEGER NOT NULL DEFAULT 1,
                    last_heartbeat REAL
                )"""
            )
            conn.execute("BEGIN IMMEDIATE")
            self._ensure_schema(conn)
            conn.commit()
        finally:
            conn.close()

    def _lock(self):
        fh = open(self.lock_path, "a+")
        deadline = _ACQUIRE_DEADLINE_NS.get()
        try:
            if deadline is None:
                fcntl.flock(fh, fcntl.LOCK_EX)
            else:
                while True:
                    remaining = require_remaining(deadline)
                    try:
                        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        break
                    except BlockingIOError:
                        time.sleep(min(0.05, remaining))
            return fh
        except BaseException:
            fh.close()
            raise

    def _conn(self) -> sqlite3.Connection:
        conn = _connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def now(self) -> float:
        return float(self.now_fn())

    def normalize_pool(self, pool: str) -> str:
        p = (pool or "").strip().lower()
        return POOL_ALIASES.get(p, p)

    def _ensure_schema(self, conn: sqlite3.Connection) -> None:
        import quota_circuit
        quota_circuit.init_schema(conn)
        lcols = {r[1] for r in conn.execute("PRAGMA table_info(leases)")}
        if "renewable" not in lcols:
            conn.execute(
                "ALTER TABLE leases ADD COLUMN renewable INTEGER NOT NULL DEFAULT 1"
            )
        if "model" not in lcols:
            conn.execute(
                "ALTER TABLE leases ADD COLUMN model TEXT NOT NULL DEFAULT ''"
            )
        if "purpose" not in lcols:
            conn.execute("ALTER TABLE leases ADD COLUMN purpose TEXT NOT NULL DEFAULT 'WORKER'")
        conn.execute("""CREATE TABLE IF NOT EXISTS application_turns (
            principal_id TEXT NOT NULL, turn_id TEXT NOT NULL,
            grant_id TEXT NOT NULL, grant_digest TEXT NOT NULL,
            caller_host TEXT NOT NULL, workload TEXT NOT NULL,
            admission_root TEXT NOT NULL, pool TEXT NOT NULL, account TEXT NOT NULL,
            model TEXT NOT NULL, lease_id TEXT NOT NULL UNIQUE,
            created_at REAL NOT NULL, expires_at REAL NOT NULL,
            max_steps INTEGER NOT NULL, state TEXT NOT NULL DEFAULT 'open',
            PRIMARY KEY (principal_id, turn_id))""")
        conn.execute("""CREATE TABLE IF NOT EXISTS application_requests (
            principal_id TEXT NOT NULL, turn_id TEXT NOT NULL, request_id TEXT NOT NULL,
            request_digest TEXT NOT NULL, dispatch_id TEXT NOT NULL UNIQUE,
            state TEXT NOT NULL CHECK (state IN ('pending','unknown','terminal')), created_at REAL NOT NULL,
            terminal_receipt TEXT, unknown_reason TEXT,
            CHECK ((state='terminal' AND terminal_receipt IS NOT NULL)
                   OR (state IN ('pending','unknown') AND terminal_receipt IS NULL)),
            PRIMARY KEY (principal_id, turn_id, request_id))""")
        # Add commitments to the existing owner rows in this same migration
        # transaction. Historical Go rows stay NULL and retain their v1 proof.
        for table, additions in (
                ("application_turns", ("recipe_json", "recipe_digest", "selection_json", "selection_digest")),
                ("application_requests", ("recipe_digest", "logical_payload_digest", "wire_body_digest"))):
            columns = {row[1] for row in conn.execute("PRAGMA table_info(" + table + ")")}
            for column in additions:
                if column not in columns:
                    conn.execute("ALTER TABLE " + table + " ADD COLUMN " + column + " TEXT")
        conn.execute("""CREATE TRIGGER IF NOT EXISTS application_selection_binding_v1
            BEFORE UPDATE ON application_turns WHEN
                NEW.selection_json IS NOT OLD.selection_json
                OR NEW.selection_digest IS NOT OLD.selection_digest
                OR (OLD.selection_digest IS NOT NULL AND (
                    NEW.principal_id IS NOT OLD.principal_id OR NEW.turn_id IS NOT OLD.turn_id
                    OR NEW.grant_id IS NOT OLD.grant_id OR NEW.grant_digest IS NOT OLD.grant_digest
                    OR NEW.caller_host IS NOT OLD.caller_host OR NEW.workload IS NOT OLD.workload
                    OR NEW.admission_root IS NOT OLD.admission_root OR NEW.pool IS NOT OLD.pool
                    OR NEW.account IS NOT OLD.account OR NEW.model IS NOT OLD.model
                    OR NEW.lease_id IS NOT OLD.lease_id OR NEW.created_at IS NOT OLD.created_at
                    OR NEW.expires_at IS NOT OLD.expires_at OR NEW.max_steps IS NOT OLD.max_steps))
            BEGIN SELECT RAISE(IGNORE); END""")
        conn.execute("""CREATE TRIGGER IF NOT EXISTS application_selection_delete_v1
            BEFORE DELETE ON application_turns WHEN OLD.selection_digest IS NOT NULL
            BEGIN SELECT RAISE(IGNORE); END""")
        conn.execute("""CREATE TRIGGER IF NOT EXISTS application_http_turn_binding_v1
            BEFORE UPDATE ON application_turns WHEN OLD.pool='bailian' AND (
                NEW.principal_id IS NOT OLD.principal_id OR NEW.turn_id IS NOT OLD.turn_id
                OR NEW.grant_id IS NOT OLD.grant_id OR NEW.grant_digest IS NOT OLD.grant_digest
                OR NEW.caller_host IS NOT OLD.caller_host OR NEW.workload IS NOT OLD.workload
                OR NEW.admission_root IS NOT OLD.admission_root OR NEW.pool IS NOT OLD.pool
                OR NEW.account IS NOT OLD.account OR NEW.model IS NOT OLD.model
                OR NEW.lease_id IS NOT OLD.lease_id OR NEW.created_at IS NOT OLD.created_at
                OR NEW.expires_at IS NOT OLD.expires_at OR NEW.max_steps IS NOT OLD.max_steps
                OR NEW.recipe_json IS NOT OLD.recipe_json OR NEW.recipe_digest IS NOT OLD.recipe_digest)
            BEGIN SELECT RAISE(IGNORE); END""")
        conn.execute("""CREATE TRIGGER IF NOT EXISTS application_http_request_binding_v1
            BEFORE UPDATE ON application_requests WHEN OLD.recipe_digest IS NOT NULL AND (
                NEW.principal_id IS NOT OLD.principal_id OR NEW.turn_id IS NOT OLD.turn_id
                OR NEW.request_id IS NOT OLD.request_id OR NEW.request_digest IS NOT OLD.request_digest
                OR NEW.dispatch_id IS NOT OLD.dispatch_id OR NEW.created_at IS NOT OLD.created_at
                OR NEW.recipe_digest IS NOT OLD.recipe_digest
                OR NEW.logical_payload_digest IS NOT OLD.logical_payload_digest
                OR NEW.wire_body_digest IS NOT OLD.wire_body_digest)
            BEGIN SELECT RAISE(IGNORE); END""")
        conn.execute("""CREATE TRIGGER IF NOT EXISTS application_http_turn_delete_v1
            BEFORE DELETE ON application_turns WHEN OLD.pool='bailian'
            BEGIN SELECT RAISE(IGNORE); END""")
        conn.execute("""CREATE TRIGGER IF NOT EXISTS application_http_request_delete_v1
            BEFORE DELETE ON application_requests WHEN OLD.recipe_digest IS NOT NULL
            BEGIN SELECT RAISE(IGNORE); END""")
        # Older immutable worker releases also run GC against this same DB.
        # Keep application custody in the canonical schema, where an old PID,
        # TTL or generic release path cannot erase it. IGNORE affects only the
        # incompatible row; ordinary worker updates continue in the same batch.
        conn.execute("""CREATE TRIGGER IF NOT EXISTS application_lease_binding_v1
            BEFORE UPDATE ON leases WHEN OLD.purpose='APPLICATION' AND (
                NEW.purpose IS NOT OLD.purpose OR NEW.id IS NOT OLD.id
                OR NEW.orchestrator_id IS NOT OLD.orchestrator_id OR NEW.pool IS NOT OLD.pool
                OR NEW.account IS NOT OLD.account OR NEW.model IS NOT OLD.model
                OR NEW.host IS NOT OLD.host OR NEW.pid IS NOT OLD.pid
                OR NEW.granted_at IS NOT OLD.granted_at OR NEW.ttl IS NOT OLD.ttl
                OR NEW.last_heartbeat IS NOT OLD.last_heartbeat
                OR NEW.renewable > OLD.renewable)
            BEGIN SELECT RAISE(IGNORE); END""")
        conn.execute("""CREATE TRIGGER IF NOT EXISTS application_lease_delete_v1
            BEFORE DELETE ON leases WHEN OLD.purpose='APPLICATION'
            BEGIN SELECT RAISE(IGNORE); END""")
        conn.execute("""CREATE TRIGGER IF NOT EXISTS application_lease_release_v1
            BEFORE UPDATE OF state ON leases WHEN OLD.purpose='APPLICATION'
            AND OLD.state IN ('held','rented') AND NEW.state NOT IN ('held','rented')
            AND NOT EXISTS (
                SELECT 1 FROM application_turns t WHERE t.lease_id=OLD.id AND t.state='closed'
                AND NOT EXISTS (
                    SELECT 1 FROM application_requests r
                    WHERE r.principal_id=t.principal_id AND r.turn_id=t.turn_id
                    AND CASE WHEN r.state='terminal' AND json_valid(r.terminal_receipt)=1 THEN
                        CASE WHEN json_type(r.terminal_receipt)='object'
                            AND json_extract(r.terminal_receipt,'$.dispatch_id')=r.dispatch_id
                            AND json_extract(r.terminal_receipt,'$.request_digest')=r.request_digest
                            AND json_extract(r.terminal_receipt,'$.lease_id')=t.lease_id
                            AND json_extract(r.terminal_receipt,'$.account')=t.account
                            AND json_extract(r.terminal_receipt,'$.model')=t.model
                            AND json_type(r.terminal_receipt,'$.response_digest')='text'
                            AND length(json_extract(r.terminal_receipt,'$.response_digest'))=64
                            AND json_extract(r.terminal_receipt,'$.response_digest') NOT GLOB '*[^0-9a-f]*'
                            AND json_type(r.terminal_receipt,'$.status_code')='integer'
                            AND json_extract(r.terminal_receipt,'$.status_code') BETWEEN 200 AND 599
                            AND json_type(r.terminal_receipt,'$.completed_at') IN ('integer','real')
                            AND json_extract(r.terminal_receipt,'$.completed_at')>=r.created_at
                            AND json_type(r.terminal_receipt,'$.usage')='object'
                            AND (json_type(r.terminal_receipt,'$.usage.input_tokens')='null'
                                 OR (json_type(r.terminal_receipt,'$.usage.input_tokens')='integer'
                                     AND json_extract(r.terminal_receipt,'$.usage.input_tokens') BETWEEN 0 AND 1000000000000))
                            AND (json_type(r.terminal_receipt,'$.usage.output_tokens')='null'
                                 OR (json_type(r.terminal_receipt,'$.usage.output_tokens')='integer'
                                     AND json_extract(r.terminal_receipt,'$.usage.output_tokens') BETWEEN 0 AND 1000000000000))
                        THEN 0 ELSE 1 END ELSE 1 END=1))
            BEGIN SELECT RAISE(IGNORE); END""")
        # The HTTP extension retains every v1 terminal condition and adds its
        # original recipe/wire binding. An old broker's release/GC cannot turn
        # a downgraded Go-shaped receipt into proof for a Bailian operation.
        conn.execute("""CREATE TRIGGER IF NOT EXISTS application_http_lease_release_v2
            BEFORE UPDATE OF state ON leases WHEN OLD.purpose='APPLICATION'
            AND OLD.pool='bailian' AND OLD.state IN ('held','rented')
            AND NEW.state NOT IN ('held','rented')
            AND NOT EXISTS (
                SELECT 1 FROM application_turns t WHERE t.lease_id=OLD.id
                AND t.pool=OLD.pool AND t.account=OLD.account AND t.model=OLD.model
                AND t.state='closed' AND json_valid(t.recipe_json)=1
                AND length(t.recipe_digest)=64
                AND t.recipe_digest NOT GLOB '*[^0-9a-f]*'
                AND NOT EXISTS (
                    SELECT 1 FROM application_requests r
                    WHERE r.principal_id=t.principal_id AND r.turn_id=t.turn_id
                    AND CASE WHEN r.state='terminal' AND json_valid(r.terminal_receipt)=1 THEN
                        CASE WHEN json_extract(r.terminal_receipt,'$.terminal_kind')='http_responses_v1'
                            AND (SELECT count(*) FROM json_each(r.terminal_receipt))=15
                            AND NOT EXISTS (SELECT 1 FROM json_each(r.terminal_receipt) j
                                WHERE j.key NOT IN ('dispatch_id','request_digest','lease_id','account','model',
                                    'response_digest','status_code','completed_at','usage','terminal_kind',
                                    'recipe_digest','logical_payload_digest','wire_body_digest','delivery_digest','served_model'))
                            AND (SELECT count(*) FROM json_each(r.terminal_receipt,'$.usage'))=2
                            AND NOT EXISTS (SELECT 1 FROM json_each(r.terminal_receipt,'$.usage') j
                                WHERE j.key NOT IN ('input_tokens','output_tokens'))
                            AND r.recipe_digest=t.recipe_digest
                            AND json_extract(r.terminal_receipt,'$.recipe_digest')=r.recipe_digest
                            AND length(r.logical_payload_digest)=64
                            AND r.logical_payload_digest NOT GLOB '*[^0-9a-f]*'
                            AND json_extract(r.terminal_receipt,'$.logical_payload_digest')=r.logical_payload_digest
                            AND length(r.wire_body_digest)=64
                            AND r.wire_body_digest NOT GLOB '*[^0-9a-f]*'
                            AND json_extract(r.terminal_receipt,'$.wire_body_digest')=r.wire_body_digest
                            AND (json_type(r.terminal_receipt,'$.delivery_digest')='null'
                                 OR (json_type(r.terminal_receipt,'$.delivery_digest')='text'
                                     AND length(json_extract(r.terminal_receipt,'$.delivery_digest'))=64
                                     AND json_extract(r.terminal_receipt,'$.delivery_digest') NOT GLOB '*[^0-9a-f]*'))
                            AND (json_type(r.terminal_receipt,'$.served_model')='null'
                                 OR (json_type(r.terminal_receipt,'$.served_model')='text'
                                     AND length(json_extract(r.terminal_receipt,'$.served_model')) BETWEEN 1 AND 256
                                     AND instr(json_extract(r.terminal_receipt,'$.served_model'),char(0))=0))
                        THEN 0 ELSE 1 END ELSE 1 END=1))
            BEGIN SELECT RAISE(IGNORE); END""")
        wcols = {r[1] for r in conn.execute("PRAGMA table_info(waiters)")}
        if "last_heartbeat" not in wcols:
            conn.execute("ALTER TABLE waiters ADD COLUMN last_heartbeat REAL")
            conn.execute(
                "UPDATE waiters SET last_heartbeat = enqueued_at "
                "WHERE last_heartbeat IS NULL"
            )

    def load_accounts_doc(self) -> Dict[str, Any]:
        selected = _APPLICATION_ACCOUNTS.get()
        if selected is not None:
            return selected
        try:
            mtime = os.path.getmtime(self.accounts_path)
        except OSError:
            if self._accounts_cache is not None:
                return self._accounts_cache
            raise
        if self._accounts_mtime == mtime and self._accounts_cache is not None:
            return self._accounts_cache
        try:
            doc = _load_yaml(self.accounts_path)
        except Exception:
            if self._accounts_cache is not None:
                return self._accounts_cache
            raise
        self._accounts_cache = doc
        self._accounts_mtime = mtime
        return doc

    def provider(self, pool: str) -> Dict[str, Any]:
        pool = self.normalize_pool(pool)
        doc = self.load_accounts_doc()
        providers = doc.get("providers") or {}
        # alias lookup
        if pool in providers:
            return dict(providers[pool] or {}, _name=pool)
        for name, spec in providers.items():
            aliases = [str(a).lower() for a in (spec or {}).get("pool_aliases") or []]
            if pool in aliases:
                return dict(spec or {}, _name=name)
        return {"_name": pool, "enabled": False, "accounts": []}

    def provider_name(self, pool: str) -> str:
        return str(self.provider(pool).get("_name") or self.normalize_pool(pool))

    # ── gates ────────────────────────────────────────────────────────────────

    def _parked(self, acct: Dict[str, Any], now: float) -> bool:
        until = _parse_iso(acct.get("parked_until"))
        return until is not None and until > now

    def _grok_exhausted(self) -> bool:
        return os.path.exists(self.grok_marker)

    def _bailian_effective_cap(self, name: str, base: int) -> Optional[int]:
        """None = not grantable (non-429 cooldown, or fresh known parked usage).
        Else effective cap."""
        if not self.external_gates:
            return base
        try:
            if HERE not in sys.path:
                sys.path.insert(0, HERE)
            import bailian_keys

            try:
                info = bailian_keys.read_usage_eligibility(name, now=self.now())
            except Exception:
                info = bailian_keys._usage_unknown()
            if info.get("state") == "CURRENT" and info.get("parked") is True:
                return None
            # A parked account is withheld even with healthy cooldown data;
            # untrusted/unsafe cooldowns cannot be granted by unknown usage.
            effective = int(bailian_keys._effective_cap_for_key(name))
            return min(base, effective) if effective > 0 else None
        except Exception:
            # Unavailable or corrupt source cannot establish provider room.
            return None

    def _host_lane_capacity(self, pool: str) -> int:
        """Physical fleet admission envelope, NOT a provider/account slot quota.

        Only explicitly qualified lane hosts count. The remote host picker and
        physical LaneLease still enforce live health, occupancy and resources.
        Missing/invalid registry fails closed, never becomes unlimited capacity.
        """
        if pool not in ("grok", "cursor"):
            return 0
        def reject_duplicate_keys(pairs):
            obj = {}
            for key, value in pairs:
                if key in obj:
                    raise ValueError("duplicate_host_registry_key")
                obj[key] = value
            return obj

        try:
            with open(self.hosts_path, encoding="utf-8") as handle:
                hosts = json.load(handle, object_pairs_hook=reject_duplicate_keys)
        except (OSError, ValueError, TypeError):
            return 0
        if not isinstance(hosts, dict):
            return 0
        total = 0
        for name, entry in hosts.items():
            # Registry metadata is not a physical host; it cannot create broker
            # capacity even when it accidentally contains host-shaped fields.
            if str(name).startswith("_") or not isinstance(entry, dict):
                continue
            roles = entry.get("roles")
            allowed = entry.get("allowed_modes")
            held = entry.get("qualification_only_modes", [])
            if (not isinstance(roles, list) or "lanes" not in roles
                    or not isinstance(allowed, list) or pool not in allowed
                    or not isinstance(held, list) or pool in held):
                continue
            maximum = entry.get("max_active")
            ceiling = entry.get("lane_ceiling")
            cores = entry.get("cores")
            if (any(type(v) is not int for v in (maximum, ceiling, cores))
                    or min(maximum, ceiling, cores) < 1
                    or maximum > 32 or ceiling > 32):
                continue
            total += min(maximum, ceiling, cores)
        return total

    def account_cap(self, pool: str, acct: Dict[str, Any], conn=None) -> Optional[int]:
        import quota_circuit
        base = self._base_account_cap(pool, acct)
        return (quota_circuit.account_cap(self, pool, acct, base) if conn is None
                else quota_circuit.account_cap(self, pool, acct, base, conn=conn))

    def _base_account_cap(self, pool: str, acct: Dict[str, Any]) -> Optional[int]:
        """Effective cap, or None if the account must not be granted."""
        now = self.now()
        if self._parked(acct, now):
            return None
        base = acct.get("per_account_cap")
        pname = self.provider_name(pool)
        if self.provider(pool).get("capacity_policy") == "host_admitted":
            # No provider seat count. Configuring both forms fails closed.
            if pname not in ("grok", "cursor") or base is not None:
                return None
            if pname == "grok" and self._grok_exhausted():
                return None
            return self._host_lane_capacity(pname) or None
        if base is None:
            return None
        base = int(base)
        name = str(acct.get("name") or "")
        if pname == "grok" and self._grok_exhausted():
            return None
        if pname == "bailian":
            return self._bailian_effective_cap(name, base)
        if pname == "glm" and self.external_gates:
            from quota_remote import cached_glm_account_parked
            if cached_glm_account_parked(name, now_ts=now):
                return None
        return base

    def account_model_cap(
        self, pool: str, acct: Dict[str, Any], model: str
    ) -> Optional[int]:
        """Per-model account cap when the provider declares one."""
        if self.provider_name(pool) != "glm":
            return None
        model_name = str(model or "").strip().lower()
        if not model_name:
            return None
        raw = acct.get("per_model_caps") or {}
        if not isinstance(raw, dict):
            return None
        value = raw.get(model_name)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        cap = int(value)
        return cap if cap >= 0 else None

    def _account_model_held(
        self, conn: sqlite3.Connection, pool: str, account: str, model: str
    ) -> int:
        """Held leases for one concrete model.

        During the migration, untagged legacy GLM leases count against full
        GLM conservatively; Flash keeps exact-model accounting because its
        declared model cap is no tighter than the generic account cap.
        """
        pool = self.provider_name(pool)
        model_name = str(model or "").strip().lower()
        if not model_name:
            return 0
        if pool == "glm" and model_name == "glm-5.3":
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM leases "
                "WHERE state IN ('held','rented') AND pool=? AND account=? "
                "AND (LOWER(model)=? OR model='')",
                (pool, account, model_name),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM leases "
                "WHERE state IN ('held','rented') AND pool=? AND account=? "
                "AND LOWER(model)=?",
                (pool, account, model_name),
            ).fetchone()
        return int(row["n"] if row else 0)

    def grantable_accounts(self, pool: str, conn=None) -> List[Dict[str, Any]]:
        spec = self.provider(pool)
        if spec.get("enabled") is False:
            return []
        out = []
        for acct in spec.get("accounts") or []:
            cap = self.account_cap(pool, acct) if conn is None else self.account_cap(pool, acct, conn=conn)
            if cap is None or cap <= 0:
                continue
            row = dict(acct)
            row["_eff_cap"] = cap
            out.append(row)
        return out

    def pool_cap(self, pool: str) -> int:
        grantable = self.grantable_accounts(pool)
        total = sum(int(a["_eff_cap"]) for a in grantable)
        if self.provider(pool).get("capacity_policy") == "host_admitted":
            # Multiple accounts must never multiply the physical fleet envelope.
            return min(total, self._host_lane_capacity(self.provider_name(pool)))
        return total

    # ── sql helpers ──────────────────────────────────────────────────────────

    def _active_leases(self, conn: sqlite3.Connection, pool: Optional[str] = None) -> List[sqlite3.Row]:
        if pool:
            pool = self.provider_name(pool)
            cur = conn.execute(
                "SELECT * FROM leases WHERE state IN ('held','rented') AND pool=?",
                (pool,),
            )
        else:
            cur = conn.execute("SELECT * FROM leases WHERE state IN ('held','rented')")
        return list(cur.fetchall())

    def _held_by(self, conn: sqlite3.Connection, orch: str, pool: str) -> List[sqlite3.Row]:
        pool = self.provider_name(pool)
        return list(
            conn.execute(
                "SELECT * FROM leases WHERE state IN ('held','rented') "
                "AND orchestrator_id=? AND pool=?",
                (orch, pool),
            ).fetchall()
        )

    def _account_held(self, conn: sqlite3.Connection, pool: str, account: str) -> int:
        pool = self.provider_name(pool)
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM leases WHERE state IN ('held','rented') "
            "AND pool=? AND account=?",
            (pool, account),
        ).fetchone()
        return int(row["n"] if row else 0)

    def _waiters(self, conn: sqlite3.Connection, pool: str) -> List[sqlite3.Row]:
        pool = self.provider_name(pool)
        return list(
            conn.execute(
                "SELECT * FROM waiters WHERE pool=? AND id NOT LIKE 'plan-%' "
                "ORDER BY priority ASC, enqueued_at ASC",
                (pool,),
            ).fetchall()
        )

    def _active_orchestrators(self, conn: sqlite3.Connection, pool: str) -> List[str]:
        pool = self.provider_name(pool)
        ids = set()
        for r in conn.execute(
            "SELECT DISTINCT orchestrator_id FROM leases "
            "WHERE state IN ('held','rented') AND pool=?",
            (pool,),
        ):
            ids.add(r["orchestrator_id"])
        for r in conn.execute(
            "SELECT DISTINCT orchestrator_id FROM waiters "
            "WHERE pool=? AND id NOT LIKE 'plan-%'",
            (pool,),
        ):
            ids.add(r["orchestrator_id"])
        return sorted(ids)

    def fair_share(self, conn: sqlite3.Connection, pool: str, extra: Optional[str] = None) -> int:
        cap = self.pool_cap(pool)
        orchs = set(self._active_orchestrators(conn, pool))
        if extra:
            orchs.add(extra)
        n = max(1, len(orchs))
        if cap <= 0:
            return 1
        return max(1, cap // n)

    def _below_share_waiters(
        self, conn: sqlite3.Connection, pool: str, except_orch: str, share: int
    ) -> List[sqlite3.Row]:
        out = []
        for w in self._waiters(conn, pool):
            if w["orchestrator_id"] == except_orch:
                continue
            held = len(self._held_by(conn, w["orchestrator_id"], pool))
            if held < share:
                out.append(w)
        return out

    def _mark_surplus_nonrenewable(
        self, conn: sqlite3.Connection, pool: str, share: int
    ) -> None:
        """When a below-share waiter exists, surplus leases drain at step boundaries."""
        # TTL stays the granted liveness window. Non-renewability is renewable=0
        # (blocks *new* acquires for this surplus); a heartbeat within TTL keeps
        # the current step alive. Never deletes a live lease.
        counts: Dict[str, List[sqlite3.Row]] = {}
        for row in self._active_leases(conn, pool):
            counts.setdefault(row["orchestrator_id"], []).append(row)
        for _orch, rows in counts.items():
            if len(rows) <= share:
                continue
            # keep the oldest `share` as held; mark the rest rented + non-renewable
            rows_sorted = sorted(rows, key=lambda r: r["granted_at"])
            for extra in rows_sorted[share:]:
                conn.execute(
                    "UPDATE leases SET state='rented', renewable=0 WHERE id=?",
                    (extra["id"],),
                )

    # ── gc ───────────────────────────────────────────────────────────────────

    def gc(self) -> int:
        lock = self._lock()
        try:
            return self._gc_locked()
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)
            lock.close()

    def _gc_locked(self) -> int:
        conn = self._conn()
        expired = 0
        try:
            now = self.now()
            for row in self._active_leases(conn):
                if row["purpose"] == "APPLICATION":
                    turn = conn.execute("SELECT * FROM application_turns WHERE lease_id=?", (row["id"],)).fetchone()
                    # Missing custody is not evidence that an application ended.
                    if turn is None or self._application_unsettled(conn, turn):
                        continue
                    if now >= min(float(turn["expires_at"]), float(row["granted_at"]) + float(row["ttl"])):
                        conn.execute("UPDATE application_turns SET state='closed' WHERE lease_id=?", (row["id"],))
                        conn.execute("UPDATE leases SET state='expired' WHERE id=?", (row["id"],))
                        expired += 1
                    continue  # Application liveness never depends on a fabricated PID.
                dead = False
                try:
                    renewable = int(row["renewable"])
                except (KeyError, IndexError, TypeError, ValueError):
                    renewable = 1
                if now - float(row["last_heartbeat"]) > float(row["ttl"]):
                    dead = True
                elif renewable == 0 and (now - float(row["granted_at"])) > float(row["ttl"]):
                    # surplus past its granted TTL is non-renewable: expire it
                    dead = True
                elif (
                    self.check_pid
                    and row["host"] == self.this_host
                    and not _pid_alive(int(row["pid"]))
                ):
                    dead = True
                if dead:
                    conn.execute(
                        "UPDATE leases SET state='expired' WHERE id=?", (row["id"],)
                    )
                    expired += 1
            # drop waiters whose demand heartbeat went stale (not absolute age)
            conn.execute(
                "DELETE FROM waiters WHERE COALESCE(last_heartbeat, enqueued_at) < ?",
                (now - WAITER_STALE_S,),
            )
            conn.commit()
        finally:
            conn.close()
        return expired

    # ── acquire / release / heartbeat ────────────────────────────────────────

    def acquire(
        self,
        orchestrator_id: str,
        pool: str,
        account: Optional[str] = None,
        task_class: str = "unknown",
        host: Optional[str] = None,
        pid: int = 0,
        ttl: Optional[int] = None,
        wait: float = 0,
        poll: float = 1.0,
        model: str = "",
        operator_child_id: Optional[str] = None,
        capacity_handoff: bool = False,
        deadline_ns: Optional[int] = None,
        not_before: Optional[str] = None,
    ) -> AcquireResult:
        if not_before is not None:
            from commission_deadline import require_not_before
            require_not_before(not_before)
        if deadline_ns is not None:
            deadline_ns = validate_deadline_ns(deadline_ns)
        token = _ACQUIRE_DEADLINE_NS.set(deadline_ns)
        try:
            return self._acquire(orchestrator_id, pool, account, task_class, host,
                pid, ttl, wait, poll, model, operator_child_id, capacity_handoff, not_before)
        except CommissionDeadlineExpired:
            return AcquireResult(ok=False, reason="commission_time_exhausted",
                orchestrator_id=orchestrator_id, pool=self.provider_name(pool))
        except sqlite3.OperationalError:
            # A refused/unknown database operation is never quota handoff proof.
            # In particular an interrupted grant cannot be declared lease-free.
            if deadline_ns is not None and time.monotonic_ns() >= deadline_ns:
                return AcquireResult(ok=False, reason="commission_time_exhausted",
                    orchestrator_id=orchestrator_id, pool=self.provider_name(pool))
            raise
        finally:
            _ACQUIRE_DEADLINE_NS.reset(token)

    def _acquire(self, orchestrator_id, pool, account, task_class, host,
                 pid, ttl, wait, poll, model, operator_child_id, capacity_handoff, not_before=None):
        pool = self.provider_name(pool)
        model = str(model or "").strip()
        host = host or self.this_host
        pid = int(pid or os.getpid())
        orchestrator_id = str(orchestrator_id or "").strip()
        if not orchestrator_id:
            return AcquireResult(ok=False, reason="missing_orchestrator_id", pool=pool)
        waiter_id: Optional[str] = None
        deadline = self.now() + max(0.0, float(wait))
        last_reason = "unavailable"
        # Failed/blocked acquire demand stays in waiters for WAITER_STALE_S so
        # lending and the starvation guard can fire (B5). plan() is read-only
        # for fair share (N1) and does not register competing demand.
        # Successful acquire deletes the waiter row inside _try_acquire.
        while True:
            if not_before is not None:
                from commission_deadline import require_not_before
                require_not_before(not_before)
            lock = self._lock()
            try:
                if not_before is not None:
                    require_not_before(not_before)
                self._gc_locked()
                result, waiter_id, last_reason = self._try_acquire(
                    orchestrator_id,
                    pool,
                    account,
                    task_class,
                    host,
                    pid,
                    ttl,
                    waiter_id,
                    model,
                    operator_child_id,
                    capacity_handoff,
                    not_before,
                )
                if result.ok or last_reason in ("operator_authorization_refused", "host_account_unavailable", "quota_cooldown"):
                    return result
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)
                lock.close()
            if self.now() >= deadline:
                break
            pause = min(max(0.05, float(poll)), max(0.0, deadline - self.now()))
            original = _ACQUIRE_DEADLINE_NS.get()
            if original is not None:
                pause = min(pause, require_remaining(original))
            time.sleep(pause)
        return AcquireResult(
            ok=False,
            reason=last_reason,
            orchestrator_id=orchestrator_id,
            pool=pool,
        )

    def _drop_waiter(self, waiter_id: str) -> None:
        lock = self._lock()
        try:
            conn = self._conn()
            try:
                conn.execute("DELETE FROM waiters WHERE id=?", (waiter_id,))
                conn.commit()
            finally:
                conn.close()
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)
            lock.close()

    def _enqueue_waiter(
        self,
        conn: sqlite3.Connection,
        waiter_id: Optional[str],
        orch: str,
        pool: str,
        account: Optional[str],
        task_class: str,
        host: str,
        need: int = 1,
    ) -> str:
        now = self.now()
        existing = conn.execute(
            "SELECT id FROM waiters WHERE orchestrator_id=? AND pool=?",
            (orch, pool),
        ).fetchone()
        if existing:
            wid = existing["id"]
            conn.execute(
                "UPDATE waiters SET last_heartbeat=?, task_class=?, priority=?, "
                "account=?, host=?, need=? WHERE id=?",
                (
                    now,
                    task_class,
                    _class_priority(task_class),
                    account,
                    host,
                    int(need),
                    wid,
                ),
            )
            return wid
        wid = waiter_id or uuid.uuid4().hex[:12]
        conn.execute(
            "INSERT OR REPLACE INTO waiters "
            "(id, orchestrator_id, pool, account, task_class, host, "
            "enqueued_at, priority, need, last_heartbeat) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                wid,
                orch,
                pool,
                account,
                task_class,
                host,
                now,
                _class_priority(task_class),
                int(need),
                now,
            ),
        )
        return wid

    def _register_demand(
        self,
        conn: sqlite3.Connection,
        waiter_id: Optional[str],
        orch: str,
        pool: str,
        account: Optional[str],
        task_class: str,
        host: str,
        need: int = 1,
    ) -> str:
        """Blocked/failed acquire: persist demand and drain surplus (B5 / N1)."""
        wid = self._enqueue_waiter(
            conn, waiter_id, orch, pool, account, task_class, host, need
        )
        share_now = self.fair_share(conn, pool)
        if self._below_share_waiters(conn, pool, "", share_now):
            self._mark_surplus_nonrenewable(conn, pool, share_now)
        return wid

    def _front_of_queue(
        self, conn: sqlite3.Connection, pool: str, orch: str, task_class: str
    ) -> bool:
        """True if this orch may take the next slot (priority + oldest-first)."""
        waiters = self._waiters(conn, pool)
        if not waiters:
            return True
        # A root already at its share cannot borrow while another root has
        # unsatisfied demand. Such a waiter must not block the eligible roots
        # behind it: _try_acquire refuses its own turn as lending_blocked.
        share = self.fair_share(conn, pool, extra=orch)
        below_share = {
            w["orchestrator_id"]
            for w in self._below_share_waiters(conn, pool, "", share)
        }
        # A first acquire has not registered a waiter yet. Its entitlement is
        # the same as on the next wait-loop iteration, without rewriting demand.
        if len(self._held_by(conn, orch, pool)) < share:
            below_share.add(orch)
        if below_share:
            waiters = [w for w in waiters if w["orchestrator_id"] in below_share]
        my_p = _class_priority(task_class)
        # higher-priority (lower number) waiter from someone else blocks us
        for w in waiters:
            if w["orchestrator_id"] == orch:
                return True
            if int(w["priority"]) < my_p:
                return False
            if int(w["priority"]) == my_p:
                # oldest at this class: if it's us, ok; if someone else, wait
                return w["orchestrator_id"] == orch
        return True

    def _pick_account(
        self,
        conn: sqlite3.Connection,
        pool: str,
        preferred: Optional[str],
        model: str = "",
        grantable_override: Optional[List[Dict[str, Any]]] = None,
    ) -> Optional[str]:
        grantable = self.grantable_accounts(pool) if grantable_override is None else grantable_override
        if not grantable:
            return None

        def has_model_room(acct: Dict[str, Any], name: str) -> bool:
            import quota_circuit
            if not quota_circuit.admission_room(self, conn, pool, acct):
                return False
            model_cap = self.account_model_cap(pool, acct, model)
            if model_cap is None:
                return True
            return self._account_model_held(conn, pool, name, model) < model_cap

        if preferred:
            for a in grantable:
                if a.get("name") == preferred:
                    # Existing exact pin is sticky; a *known* hard local
                    # denial is a refusal, never permission to substitute.
                    if self.external_gates and self.provider_name(pool) == "bailian":
                        try:
                            import bailian_keys
                            if bailian_keys.cooldown_rank_readonly(preferred) == 3:
                                return None
                        except Exception:
                            pass  # unknown remains subject to incumbent gates
                    if (
                        self._account_held(conn, pool, preferred) < int(a["_eff_cap"])
                        and has_model_room(a, preferred)
                    ):
                        return preferred
                    return None
            return None  # stickiness: requested account not grantable
        scored: List[Tuple[int, int, str]] = []
        for a in grantable:
            name = str(a["name"])
            held = self._account_held(conn, pool, name)
            cap = int(a["_eff_cap"])
            if held >= cap or not has_model_room(a, name):
                continue
            scored.append((held, cap, name))
        if not scored:
            return None
        if self.provider_name(pool) == "bailian":
            # The current tie breaker (alphabetical) silently reuses Chris
            # forever whenever workloads are sequential and held=0. Use the
            # incumbent broker's durable grant history instead. This creates
            # no new queue, cache, memory plane or provider operation.
            recent = {
                str(row["account"]): float(row["last_grant"])
                for row in conn.execute(
                    "SELECT account, MAX(granted_at) AS last_grant "
                    "FROM leases WHERE pool=? GROUP BY account",
                    (self.provider_name(pool),),
                )
                if row["last_grant"] is not None
            }
            # HTTP 429 soft caps preserve eligibility, but are a fallback for
            # unpinned *new* grants if another qualified account is healthy.
            # Exact-account pins above, model/host pairing, quota guards and
            # the prior held/cap/history order inside each tier are unchanged.
            # Host evidence is the already-verified, fresh account intersection.
            # No second read, quota authority or host-scanning side channel.
            host_rank = {
                str(a["name"]): a.get("_host_qwen_429_rank", 1)
                for a in grantable
            } if grantable_override is not None else {}

            local_ranks = {}
            if self.external_gates:
                try:
                    import bailian_keys
                    local_ranks = {
                        name: bailian_keys.cooldown_rank_readonly(name)
                        for _, _, name in scored
                    }
                except Exception:
                    local_ranks = {name: 1 for _, _, name in scored}
                # Known 401/403/402 hard denials must not be leased on an
                # unpinned path even if all configured accounts are parked.
                scored = [
                    row for row in scored
                    if local_ranks.get(row[2], 1) != 3
                ]
                if not scored:
                    return None

            def cooldown_priority(name: str) -> int:
                if not self.external_gates:
                    return 0
                local_rank = local_ranks.get(name, 1)
                if type(local_rank) is not int or local_rank not in (0, 1, 2, 3):
                    local_rank = 1
                observed = host_rank.get(
                    name, 1 if grantable_override is not None else 0
                )
                if type(observed) is not int or observed not in (0, 1, 2):
                    observed = 1
                return max(local_rank, observed)

            scored.sort(key=lambda t: (
                cooldown_priority(t[2]),
                t[0], -t[1], recent.get(t[2], float("-inf")), t[2]
            ))
        else:
            scored.sort(key=lambda t: (t[0], -t[1], t[2]))
        return scored[0][2]

    def _try_acquire(
        self,
        orch: str,
        pool: str,
        account: Optional[str],
        task_class: str,
        host: str,
        pid: int,
        ttl: Optional[int],
        waiter_id: Optional[str],
        model: str = "",
        operator_child_id: Optional[str] = None,
        capacity_handoff: bool = False,
        not_before: Optional[str] = None,
    ) -> Tuple[AcquireResult, Optional[str], str]:
        conn = self._conn()
        try:
            conn.execute("BEGIN IMMEDIATE")
            result = self._try_acquire_in_transaction(conn, orch, pool, account, task_class,
                host, pid, ttl, waiter_id, model, operator_child_id, capacity_handoff, not_before)
            conn.commit()
            return result
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _try_acquire_in_transaction(
        self,
        conn: sqlite3.Connection,
        orch: str,
        pool: str,
        account: Optional[str],
        task_class: str,
        host: str,
        pid: int,
        ttl: Optional[int],
        waiter_id: Optional[str],
        model: str = "",
        operator_child_id: Optional[str] = None,
        capacity_handoff: bool = False,
        not_before: Optional[str] = None,
        *, allowed_accounts=None, purpose="WORKER",
    ) -> Tuple[AcquireResult, Optional[str], str]:
        spec = self.provider(pool)
        if spec.get("enabled") is False:
            return (
                AcquireResult(ok=False, reason="provider_disabled", pool=pool, orchestrator_id=orch),
                waiter_id,
                "provider_disabled",
            )
        if pool == "grok" and self._grok_exhausted():
            return (
                AcquireResult(ok=False, reason="grok_exhausted", pool=pool, orchestrator_id=orch),
                waiter_id,
                "grok_exhausted",
            )
        if capacity_handoff and operator_child_id is None:
            import quota_circuit
            blockade = quota_circuit.capacity_blockade(self, conn, pool, account)
            if blockade is not None:
                if waiter_id is not None:
                    conn.execute("DELETE FROM waiters WHERE id=?", (waiter_id,))
                return (AcquireResult(ok=False, reason="quota_cooldown", pool=pool,
                    orchestrator_id=orch, quota_blockade=blockade), waiter_id, "quota_cooldown")
        compatible_accounts = None
        if (pool == "glm" and task_class == "remote-glm") or (
                self.provider_name(pool) == "bailian" and task_class == "remote-qwen"):
            # Pairing precedes capacity demand; no new waiter for an unavailable
            # host/account configuration. Model/held room stays inside selection.
            from glm_host_account_source import filter_observed_accounts
            compatible_accounts, _ = filter_observed_accounts(self.grantable_accounts(pool),
                host=host, model=model, now=self.now(), preferred=account,
                hosts_path=self.hosts_path, mode="glm" if pool == "glm" else "qwen")
            if not compatible_accounts:
                return (AcquireResult(ok=False, reason="host_account_unavailable", pool=pool,
                                      orchestrator_id=orch), waiter_id, "host_account_unavailable")
        if allowed_accounts is not None:
            available = self.grantable_accounts(pool) if compatible_accounts is None else compatible_accounts
            compatible_accounts = [a for a in available if a.get("name") in allowed_accounts
                                   and a.get("enabled", True) is not False]
        cap = self.pool_cap(pool)
        if cap <= 0:
            waiter_id = self._register_demand(
                conn, waiter_id, orch, pool, account, task_class, host
            )
            return (
                AcquireResult(ok=False, reason="no_grantable_account", pool=pool, orchestrator_id=orch),
                waiter_id,
                "no_grantable_account",
            )
        active = self._active_leases(conn, pool)
        share = self.fair_share(conn, pool, extra=orch)
        held_rows = self._held_by(conn, orch, pool)
        held_n = len(held_rows)
        below_any = self._below_share_waiters(conn, pool, "", share)
        below = self._below_share_waiters(conn, pool, orch, share)
        if below_any:
            self._mark_surplus_nonrenewable(conn, pool, share)
        else:
            conn.execute(
                "UPDATE leases SET state='held', renewable=1 "
                "WHERE state IN ('held','rented') AND pool=? AND purpose!='APPLICATION'",
                (pool,),
            )

        want_surplus = held_n >= share
        if want_surplus and below:
            waiter_id = self._register_demand(
                conn, waiter_id, orch, pool, account, task_class, host
            )
            return (
                AcquireResult(ok=False, reason="lending_blocked", pool=pool, orchestrator_id=orch),
                waiter_id,
                "lending_blocked",
            )
        if len(active) >= cap:
            waiter_id = self._register_demand(
                conn, waiter_id, orch, pool, account, task_class, host
            )
            return (
                AcquireResult(ok=False, reason="cap_full", pool=pool, orchestrator_id=orch),
                waiter_id,
                "cap_full",
            )
        if not self._front_of_queue(conn, pool, orch, task_class):
            waiter_id = self._register_demand(
                conn, waiter_id, orch, pool, account, task_class, host
            )
            return (
                AcquireResult(ok=False, reason="priority_wait", pool=pool, orchestrator_id=orch),
                waiter_id,
                "priority_wait",
            )

        picked = self._pick_account(conn, pool, account, model=model,
                                    grantable_override=compatible_accounts)
        if not picked:
            reason = "account_unavailable" if account else "accounts_at_cap"
            if account and any(self._parked(a, self.now()) for a in (spec.get("accounts") or []) if a.get("name") == account):
                reason = "account_parked"
            grantable_names = {a.get("name") for a in self.grantable_accounts(pool)}
            persist = reason not in ("account_parked",) and (
                not account or account in grantable_names or reason == "accounts_at_cap"
            )
            if persist:
                waiter_id = self._register_demand(
                    conn, waiter_id, orch, pool, account, task_class, host
                )
            return (
                AcquireResult(ok=False, reason=reason, pool=pool, orchestrator_id=orch),
                waiter_id,
                reason,
            )

        state = "rented" if want_surplus else "held"
        use_ttl = int(ttl if ttl is not None else (RENT_TTL if state == "rented" else DEFAULT_TTL))
        if purpose == "APPLICATION" and state == "rented":
            use_ttl = min(use_ttl, RENT_TTL)
        lid = uuid.uuid4().hex[:12]
        now = self.now()
        original_deadline = _ACQUIRE_DEADLINE_NS.get()
        if original_deadline is not None:
            require_remaining(original_deadline)
        if operator_child_id is not None:
            try:
                from fabric_operator_owner import validate_child_admission
                validate_child_admission(conn, operator_child_id, orch, now=now)
            except (ValueError, KeyError, TypeError, sqlite3.Error):
                return (AcquireResult(ok=False, reason="operator_authorization_refused",
                                      pool=pool, orchestrator_id=orch),
                        waiter_id, "operator_authorization_refused")
        if not_before is not None:
            from commission_deadline import require_not_before
            require_not_before(not_before)
        conn.execute(
            "INSERT INTO leases "
            "(id, orchestrator_id, pool, account, task_class, model, host, pid, "
            "granted_at, ttl, last_heartbeat, state, renewable, quota_scope, purpose) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (lid, orch, pool, picked, task_class, model, host, pid, now, use_ttl, now, state, 1,
             __import__("quota_circuit").scope_for(self, pool, picked), purpose),
        )
        if operator_child_id is not None:
            conn.execute("UPDATE operator_child_authorizations SET admitted_lease_id=? WHERE run_id=? AND root=? AND admitted_lease_id IS NULL",
                         (lid, operator_child_id, orch))
        conn.execute(
            "DELETE FROM waiters WHERE orchestrator_id=? AND pool=?",
            (orch, pool),
        )
        waiter_id = None
        return (
            AcquireResult(
                ok=True,
                lease_id=lid,
                account=picked,
                state=state,
                orchestrator_id=orch,
                pool=pool,
            ),
            None,
            "",
        )

    def heartbeat(self, lease_id: str) -> HeartbeatResult:
        lock = self._lock()
        try:
            # Preserve the typed surplus-drain reason before gc marks it expired.
            pre = self._conn()
            try:
                row = pre.execute("SELECT * FROM leases WHERE id=?", (lease_id,)).fetchone()
                if row and row["purpose"] == "APPLICATION":
                    return HeartbeatResult(False, "application_owned")
                if row and row["state"] in HELD_STATES:
                    now = self.now()
                    if int(row["renewable"]) == 0 and (now - float(row["granted_at"])) > float(row["ttl"]):
                        return HeartbeatResult(False, "nonrenewable", float(row["ttl"]))
            finally:
                pre.close()
            self._gc_locked()
            conn = self._conn()
            try:
                row = conn.execute(
                    "SELECT * FROM leases WHERE id=?", (lease_id,)
                ).fetchone()
                if not row or row["state"] not in HELD_STATES:
                    return HeartbeatResult(False, "not_held")
                now = self.now()
                try:
                    renewable = int(row["renewable"])
                except (KeyError, IndexError, TypeError, ValueError):
                    renewable = 1
                # renewable=0 past the granted TTL is non-renewable: refuse
                # heartbeat so gc expires the surplus step (W3-F).
                if renewable == 0 and (now - float(row["granted_at"])) > float(row["ttl"]):
                    return HeartbeatResult(False, "nonrenewable", float(row["ttl"]))
                conn.execute(
                    "UPDATE leases SET last_heartbeat=? WHERE id=?",
                    (now, lease_id),
                )
                # Heartbeat within the granted TTL keeps a live lease (B1).
                conn.commit()
                return HeartbeatResult(True, "held", float(row["ttl"]))
            finally:
                conn.close()
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)
            lock.close()

    def release(self, lease_id: str, orchestrator_id: Optional[str] = None) -> bool:
        oid = (orchestrator_id or "").strip()
        if not oid:
            return False
        lock = self._lock()
        try:
            conn = self._conn()
            try:
                row = conn.execute(
                    "SELECT * FROM leases WHERE id=?", (lease_id,)
                ).fetchone()
                if not row:
                    return False
                if row["purpose"] == "APPLICATION":
                    return False  # Only the application effect owner can settle it.
                if row["state"] not in HELD_STATES:
                    return False
                if row["orchestrator_id"] != oid:
                    return False
                conn.execute(
                    "UPDATE leases SET state='released' WHERE id=?", (lease_id,)
                )
                conn.commit()
                return True
            finally:
                conn.close()
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)
            lock.close()

    # ── application purpose, same admission/effect owner ─────────────────────

    @contextmanager
    def _application_transaction(self, *, deadline_ns=None, collect=False):
        deadline = validate_deadline_ns(deadline_ns) if deadline_ns is not None else None
        token = _ACQUIRE_DEADLINE_NS.set(deadline)
        lock = conn = None
        try:
            lock = self._lock()
            if collect:
                self._gc_locked()
            conn = self._conn()
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.commit()
        except BaseException:
            if conn is not None:
                conn.rollback()
            raise
        finally:
            if conn is not None:
                conn.close()
            if lock is not None:
                fcntl.flock(lock, fcntl.LOCK_UN)
                lock.close()
            _ACQUIRE_DEADLINE_NS.reset(token)

    def _application_grant(self, principal_id, caller_host, workload, pool, model,
                           expected_credential_ref=None, expected_recipe_digest=None):
        document = _read_application_accounts(self.accounts_path)
        return self._application_grant_from_document(document, principal_id, caller_host,
            workload, pool, model, expected_credential_ref, expected_recipe_digest)

    def _application_grant_from_document(self, document, principal_id, caller_host,
                                         workload, pool, model,
                                         expected_credential_ref=None, expected_recipe_digest=None):
        """Match one already validated owner reading; admission still reads fresh."""
        now = _application_time(self.now())
        matches = [g for g in document["application_grants"]
                   if g["enabled"] and g["expires_at"] > now
                   and g["principal_id"] == principal_id and g["pool"] == pool
                   and caller_host in g["caller_hosts"] and workload in g["workloads"]
                   and model in g["models"]]
        if len(matches) != 1:
            raise ApplicationAdmissionError("grant_unavailable" if not matches else "grant_ambiguous")
        grant = matches[0]
        # The HTTP owner supplies the reference of the service credential it
        # actually authenticated. Compare inside the same admission transaction;
        # a separate precheck could race a valid grant replacement.
        if (expected_credential_ref is not None
                and grant["credential_ref"] != expected_credential_ref):
            raise ApplicationAdmissionError("credential_ref_mismatch")
        if pool in _APPLICATION_HTTP_POOLS:
            _application_digest(expected_recipe_digest)
            if grant["recipe_digest"] != expected_recipe_digest:
                raise ApplicationAdmissionError("recipe_mismatch")
        elif expected_recipe_digest is not None:
            raise ApplicationAdmissionError("recipe_mismatch")
        digest = hashlib.sha256(_application_json(grant).encode()).hexdigest()
        return document, grant, digest

    def application_selection_facts(self, conn, *, principal_id, caller_host,
                                    workload, pool, model, credential_ref, transport_accounts):
        """Read existing Go ledger room; no admission, GC, secret or provider I/O.

        This is concurrency evidence, not a provider-quota observation. B keeps
        its existing post-admission quota/auth/frontier reservation unchanged.
        The supplied read-only snapshot also owns every cooldown lookup.
        """
        if pool != "go":
            raise ApplicationSelectionError("selection_transport_unqualified")
        document, grant, digest = self._application_grant(
            principal_id, caller_host, workload, pool, model, credential_ref)
        room = self._application_go_room(conn, document, grant, model, transport_accounts)
        return grant, digest, {"source": "broker-ledger-room", "observed_at": self.now(),
            "fresh_s": 5.0, "cooldown": False, "model_room": {model: room},
            "host": caller_host, "mode": "go"}

    def _application_go_room(self, conn, document, grant, model, transport_accounts):
        """The incumbent exact-model Go room calculation on one ledger snapshot."""
        pool = "go"
        allowed = frozenset(grant["accounts"]) & frozenset(transport_accounts)
        token = _APPLICATION_ACCOUNTS.set(document)
        try:
            import quota_circuit
            room = 0
            for account in self.grantable_accounts(pool, conn=conn):
                name = account["name"]
                if (name not in allowed or account.get("enabled") is False
                        or not quota_circuit.admission_room(self, conn, pool, account)):
                    continue
                available = max(0, account["_eff_cap"] - self._account_held(conn, pool, name))
                model_cap = self.account_model_cap(pool, account, model)
                if model_cap is not None:
                    available = min(available, max(0, model_cap - self._account_model_held(conn, pool, name, model)))
                room += available
        finally:
            _APPLICATION_ACCOUNTS.reset(token)
        return room

    def application_pool_view(self, conn, *, principal_id, caller_host, workload,
                              credential_ref, bound_pool, transports, source):
        """Bounded metadata over the retained owner, never snapshot()/GC/admission.

        The gateway supplies its read-only transaction and source-bound transport
        declarations. Unknown application effects remain counted as held. Only Go
        has a qualified no-effect room observer here; external quota, host lanes
        and provider health are deliberately not inferred from configured caps.
        """
        from pick import _APPLICATION_POOL_ORDER

        observed = _application_time(self.now())
        document = _read_application_accounts(self.accounts_path)
        providers = document["providers"]
        rows = []
        for pool in _APPLICATION_POOL_ORDER:
            spec = providers.get(pool)
            configured = enabled = configured_accounts = enabled_accounts = None
            basis, blockers = "unobserved", []
            if spec is None:
                blockers.append("account_inventory_unobserved")
            else:
                if (type(spec) is not dict or type(spec.get("enabled")) is not bool
                        or type(spec.get("accounts")) is not list or len(spec["accounts"]) > 1024):
                    raise ApplicationAdmissionError("admin_inventory_invalid")
                names = set()
                for account in spec["accounts"]:
                    if type(account) is not dict:
                        raise ApplicationAdmissionError("admin_inventory_invalid")
                    _application_id(account.get("name"))
                    if (account["name"] in names
                            or "enabled" in account and type(account["enabled"]) is not bool):
                        raise ApplicationAdmissionError("admin_inventory_invalid")
                    names.add(account["name"])
                    cap = account.get("per_account_cap")
                    if cap is not None and (type(cap) is not int or not 0 <= cap <= 4096):
                        raise ApplicationAdmissionError("admin_inventory_invalid")
                configured, enabled = True, spec["enabled"]
                configured_accounts = len(names)
                enabled_accounts = sum(a.get("enabled", True) is True for a in spec["accounts"])
                policy = spec.get("capacity_policy", "account")
                basis = {"account": "account_concurrency", "host_admitted": "host_admitted"}.get(policy, "unobserved")
                if not enabled:
                    blockers.append("pool_disabled")
                if not configured_accounts:
                    blockers.append("no_configured_accounts")
            held = conn.execute("SELECT COUNT(*) FROM leases WHERE pool=? AND state IN ('held','rented')",
                                (pool,)).fetchone()[0]
            models = []
            for declaration in transports.get(pool, ()):
                model = declaration["model"]
                state, model_blockers, room = "unqualified", [], None
                if declaration["qualified"] is not True:
                    model_blockers.append("application_transport_unqualified")
                elif pool != bound_pool:
                    state = "held"
                    model_blockers.append("service_pool_mismatch")
                elif spec is None:
                    state = "unobserved"
                    model_blockers.append("account_inventory_unobserved")
                elif not enabled or not enabled_accounts:
                    state = "held"
                    model_blockers.append("pool_disabled" if not enabled else "no_enabled_accounts")
                else:
                    try:
                        _, grant, _ = self._application_grant_from_document(document,
                            principal_id, caller_host, workload, pool, model, credential_ref,
                            declaration.get("recipe_digest"))
                        if not set(grant["accounts"]) & set(declaration["accounts"]):
                            raise ApplicationAdmissionError("transport_accounts_unavailable")
                        state = "configured"
                        if pool == "go":
                            room = self._application_go_room(conn, document, grant,
                                model, declaration["accounts"])
                    except ApplicationAdmissionError as exc:
                        state = "held"
                        model_blockers.append(exc.code if exc.code in {
                            "grant_unavailable", "grant_ambiguous", "credential_ref_mismatch",
                            "recipe_mismatch", "transport_accounts_unavailable"} else "application_grant_unavailable")
                if room == 0:
                    model_blockers.append("broker_room_exhausted")
                models.append({"model": model, "protocol": declaration["protocol"],
                    "capabilities": dict(declaration["capabilities"]),
                    "transport_state": "qualified" if declaration["qualified"] else "unqualified",
                    "application_state": state, "ledger_room": room,
                    "capacity_state": "broker_ledger_only" if room is not None else "unobserved",
                    "blockers": model_blockers})
            states = {m["application_state"] for m in models}
            if not models:
                blockers.append("application_transport_unqualified")
            application_state = ("configured" if "configured" in states
                else "held" if "held" in states else "unobserved" if "unobserved" in states else "unqualified")
            rows.append({"pool": pool, "configured": configured, "enabled": enabled,
                "configured_accounts": configured_accounts, "enabled_accounts": enabled_accounts,
                "capacity_basis": basis, "held_leases": held, "application_state": application_state,
                "models": models, "model_coverage": "bound_transport" if models else "unobserved",
                "blockers": blockers})
        provenance = dict(source)
        provenance["accounts_sha256"] = hashlib.sha256(_application_json(document).encode()).hexdigest()
        return {"schema": "mastermind.fabric_admin_pool_view.v1", "observed_at": observed,
            "stale_after": observed + 5.0, "execution_authorized": False,
            "requires_fresh_admission": True, "scope": {"workload": workload, "bound_pool": bound_pool},
            "coverage": {"inventory": "canonical_accounts", "ledger": "held_rows",
                         "transports": "application_gateway", "provider_quota": "unobserved"},
            "source": provenance, "pools": rows}

    def _application_check_selection(self, record, *, pool, model, caller_host, grant, grant_digest,
                                     expected_purpose, expected_profile, expected_task,
                                     existing=False):
        """Conditional admission in A's current transaction; never select again."""
        try:
            import pick
            fields = {"schema", "purpose", "purpose_digest", "profile", "profile_digest",
                      "identity", "commitments", "quality_records_sha256", "fresh_s"}
            if (type(record) is not dict or set(record) != fields
                    or record["schema"] != "mastermind.application_turn_selection.v1"
                    or pool != "go"):
                raise ValueError("invalid selection")
            encoded = _application_json(record)
            if len(encoded.encode()) > 32768:
                raise ValueError("selection exceeds bound")
            purpose_json, purpose_digest = _application_selection_purpose(expected_purpose)
            profile_json = _application_json(expected_profile)
            profile_digest = hashlib.sha256(profile_json.encode()).hexdigest()
            if (record["purpose_digest"] != purpose_digest
                    or _application_json(record["purpose"]) != purpose_json
                    or record["profile_digest"] != profile_digest
                    or _application_json(record["profile"]) != profile_json):
                raise ValueError("purpose or source changed")
            identity, commitments = record["identity"], record["commitments"]
            if type(identity) is not dict or type(commitments) is not dict:
                raise ValueError("selection identity unavailable")
            comparison_task = dict(expected_task)
            if existing:
                original_task = identity.get("task")
                if (type(original_task) is not dict or type(original_task.get("needs")) is not list
                        or not set(comparison_task["needs"]) <= set(original_task["needs"])):
                    raise ValueError("new step widens selected capability needs")
                # A follow-up may need less than its original turn. Preserve
                # that immutable commitment; never add a capability mid-turn.
                comparison_task["needs"] = original_task["needs"]
            expected = {"pool": pool, "model": model, "mode": expected_profile["mode"],
                "protocol": expected_profile["protocol"], "streaming": False,
                "driver": expected_profile["driver"], "profile": expected_profile["profile"],
                "source": expected_profile["source"], "capabilities": expected_profile["capabilities"],
                "grant_ref": {"grant_id": grant["grant_id"], "digest": grant_digest},
                "qualification_ref": grant["qualification_ref"],
                "application_permission_ref": grant["application_permission_ref"],
                "max_turn_seconds": grant["max_turn_seconds"], "max_steps": grant["max_steps"],
                "task": comparison_task, "host": caller_host, "observation_source": "broker-ledger-room"}
            if any(identity.get(key) != value for key, value in expected.items()):
                raise ValueError("selection binding changed")
            if commitments.get("task_digest") != hashlib.sha256(pick._diagnostic_json(comparison_task)).hexdigest():
                raise ValueError("selection task changed")
            policy = pick.read_application_policy()
            wanted = {"policy_bytes_sha256": policy.bytes_sha256,
                      "policy_text_sha256": policy.text_sha256,
                      "policy_parsed_sha256": policy.parsed_sha256,
                      "policy_critical_sha256": policy.critical_sha256}
            if (any(commitments.get(key) != value for key, value in wanted.items())
                    or identity.get("policy") != {"parsed_sha256": policy.parsed_sha256,
                                                   "critical_sha256": policy.critical_sha256}):
                raise ValueError("selection policy changed")
            _application_digest(record["quality_records_sha256"])
            if not existing:
                selected_at = _application_time(commitments["now_epoch"])
                if type(record["fresh_s"]) not in (int, float) or record["fresh_s"] != 5.0:
                    raise ValueError("selection freshness invalid")
                if not self.now() - record["fresh_s"] <= selected_at <= self.now():
                    raise ValueError("selection expired")
            return encoded, hashlib.sha256(encoded.encode()).hexdigest()
        except ApplicationSelectionError:
            raise
        except Exception:
            raise ApplicationSelectionError("selection_condition_changed") from None

    @staticmethod
    def _application_unsettled(conn, turn):
        requests = conn.execute("SELECT * FROM application_requests WHERE principal_id=? AND turn_id=?",
                                (turn["principal_id"], turn["turn_id"]))
        return any(_application_stored_terminal(request, turn) is None for request in requests)

    @staticmethod
    def _application_turn(conn, principal_id, turn_id):
        turn = conn.execute("SELECT * FROM application_turns WHERE principal_id=? AND turn_id=?",
                            (principal_id, turn_id)).fetchone()
        if turn is None:
            raise ApplicationAdmissionError("turn_unavailable")
        return turn

    def _application_binding(self, conn, turn, *, disposition=None):
        if disposition is None:
            requests = conn.execute("SELECT * FROM application_requests WHERE principal_id=? AND turn_id=?",
                                    (turn["principal_id"], turn["turn_id"]))
            unresolved = [row for row in requests if _application_stored_terminal(row, turn) is None]
            disposition = ("pending" if all(row["state"] == "pending" for row in unresolved)
                           else "effect_unknown") if unresolved else (
                "closed" if turn["state"] != "open" else "existing")
        result = {"ok": True, "disposition": disposition,
                **{key: turn[key] for key in ("principal_id", "turn_id", "grant_id", "grant_digest",
                    "caller_host", "workload", "admission_root", "pool", "account", "model",
                    "lease_id", "created_at", "expires_at", "max_steps", "state")}}
        if turn["pool"] in _APPLICATION_HTTP_POOLS:
            if disposition == "closed":
                lease = conn.execute("SELECT state FROM leases WHERE id=?", (turn["lease_id"],)).fetchone()
                if turn["state"] != "closed" or lease is None or lease["state"] not in {"released", "expired"}:
                    disposition = "effect_unknown"
                    result["disposition"] = disposition
            result.update(recipe_digest=turn["recipe_digest"], recipe_json=turn["recipe_json"])
        result.update(selection_json=turn["selection_json"], selection_digest=turn["selection_digest"])
        return result

    def begin_application_turn(self, *, principal_id, caller_host, workload, turn_id,
                               pool, model, deadline_ns=None, transport_accounts=None,
                               expected_credential_ref=None, application_recipe=None,
                               expected_recipe_digest=None, expected_selection=None,
                               selection_purpose=None, selection_profile=None, selection_task=None):
        for value in (principal_id, caller_host, workload, turn_id):
            _application_id(value)
        _application_model(model)
        if expected_credential_ref is not None:
            _application_id(expected_credential_ref)
        if not isinstance(pool, str) or pool not in ({"go"} | _APPLICATION_HTTP_POOLS):
            raise ApplicationAdmissionError("unsupported_application_pool")
        recipe_json = recipe_digest = None
        if pool in _APPLICATION_HTTP_POOLS:
            _application_id(expected_credential_ref)
            recipe_json, recipe_digest = _application_http_recipe(application_recipe, pool=pool, model=model)
            if _application_digest(expected_recipe_digest) != recipe_digest:
                raise ApplicationAdmissionError("recipe_mismatch")
        elif application_recipe is not None or expected_recipe_digest is not None:
            raise ApplicationAdmissionError("recipe_mismatch")
        if transport_accounts is not None:
            if not isinstance(transport_accounts, (set, frozenset, tuple, list)):
                raise ApplicationAdmissionError("invalid_transport_accounts")
            for account in transport_accounts:
                _application_id(account)
            transport_accounts = frozenset(transport_accounts)
        with self._application_transaction(deadline_ns=deadline_ns, collect=True) as conn:
            prior = conn.execute("SELECT * FROM application_turns WHERE principal_id=? AND turn_id=?",
                                 (principal_id, turn_id)).fetchone()
            if prior is not None:
                if any(prior[key] != value for key, value in (("caller_host", caller_host),
                        ("workload", workload), ("pool", pool), ("model", model))):
                    raise ApplicationAdmissionError("turn_conflict")
                recovered = self._application_binding(conn, prior)
                if recovered["disposition"] != "existing":
                    return recovered
            selected = expected_selection
            if prior is not None:
                if prior["selection_json"] is not None:
                    try:
                        if hashlib.sha256(prior["selection_json"].encode()).hexdigest() != prior["selection_digest"]:
                            raise ValueError("stored selection changed")
                        selected = json.loads(prior["selection_json"])
                    except Exception:
                        raise ApplicationSelectionError("stored_selection_invalid") from None
                elif expected_selection is not None or selection_purpose is not None:
                    raise ApplicationSelectionError("legacy_turn_purpose_changed")
            elif selection_purpose is not None and selected is None:
                raise ApplicationSelectionError("selection_required")
            try:
                document, grant, digest = self._application_grant(
                    principal_id, caller_host, workload, pool, model, expected_credential_ref,
                    expected_recipe_digest)
            except ApplicationAdmissionError:
                if selected is not None:
                    raise ApplicationSelectionError("selection_grant_unavailable") from None
                raise
            selection_json = selection_digest = None
            if selected is not None:
                selection_json, selection_digest = self._application_check_selection(selected,
                    pool=pool, model=model, caller_host=caller_host, grant=grant, grant_digest=digest,
                    expected_purpose=selection_purpose, expected_profile=selection_profile,
                    expected_task=selection_task, existing=prior is not None)
            if prior is not None:
                if prior["grant_digest"] != digest:
                    raise ApplicationAdmissionError("grant_changed")
                if (prior["recipe_digest"] != recipe_digest or prior["recipe_json"] != recipe_json):
                    raise ApplicationAdmissionError("recipe_changed")
                if transport_accounts is not None and prior["account"] not in transport_accounts:
                    raise ApplicationAdmissionError("account_unavailable")
                return self._application_binding(conn, prior)
            admitted_accounts = frozenset(grant["accounts"])
            if transport_accounts is not None:
                admitted_accounts &= transport_accounts
            accounts_token = _APPLICATION_ACCOUNTS.set(document)
            try:
                result, _, reason = self._try_acquire_in_transaction(
                    conn, grant["admission_root"], pool, None, "application", caller_host, 0,
                    grant["max_turn_seconds"], None, model,
                    allowed_accounts=admitted_accounts, purpose="APPLICATION")
            finally:
                _APPLICATION_ACCOUNTS.reset(accounts_token)
            if not result.ok:
                return {"ok": False, "disposition": "refused", "reason": reason}
            lease = conn.execute("SELECT * FROM leases WHERE id=?", (result.lease_id,)).fetchone()
            expires = min(grant["expires_at"], lease["granted_at"] + lease["ttl"])
            if _application_time(self.now()) >= expires:
                raise ApplicationAdmissionError("grant_expired")
            conn.execute("INSERT INTO application_turns (principal_id,turn_id,grant_id,grant_digest,"
                         "caller_host,workload,admission_root,pool,account,model,lease_id,created_at,"
                         "expires_at,max_steps,recipe_json,recipe_digest,selection_json,selection_digest,state) "
                         "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'open')",
                         (principal_id, turn_id, grant["grant_id"], digest, caller_host, workload,
                          grant["admission_root"], pool, result.account, model, result.lease_id,
                          lease["granted_at"], expires, grant["max_steps"], recipe_json, recipe_digest,
                          selection_json, selection_digest))
            return self._application_binding(conn, self._application_turn(conn, principal_id, turn_id),
                                             disposition="admitted")

    @staticmethod
    def _application_request_identity(principal_id, turn_id, request_id, request_digest):
        for value in (principal_id, turn_id, request_id):
            _application_id(value)
        if not isinstance(request_digest, str) or re.fullmatch(r"[0-9a-f]{64}", request_digest) is None:
            raise ApplicationAdmissionError("invalid_request_digest")

    @staticmethod
    def _application_prior_request(conn, turn, request_id, request_digest):
        prior = conn.execute("SELECT * FROM application_requests WHERE principal_id=? AND turn_id=? AND request_id=?",
                             (turn["principal_id"], turn["turn_id"], request_id)).fetchone()
        if prior is None:
            return None
        if prior["request_digest"] != request_digest:
            raise ApplicationAdmissionError("request_conflict")
        terminal = _application_stored_terminal(prior, turn)
        result = {"ok": True, "dispatch_permitted": False,
                  "disposition": "terminal" if terminal is not None else (
                      "pending" if prior["state"] == "pending" else "effect_unknown"),
                  "dispatch_id": prior["dispatch_id"]}
        if terminal is not None:
            result["terminal_receipt"] = terminal
        return result

    def recover_application_request(self, *, principal_id, turn_id, request_id, request_digest):
        """Original identity only; never admit a turn or grant another dispatch."""
        self._application_request_identity(principal_id, turn_id, request_id, request_digest)
        with self._application_transaction() as conn:
            turn = self._application_turn(conn, principal_id, turn_id)
            return self._application_prior_request(conn, turn, request_id, request_digest)

    def recover_application_context(self, *, principal_id, caller_host, workload, turn_id,
                                    model, request_id, request_digest, expected_recipe_digest, connection):
        """One owner snapshot distinguishes absence, replay and a new turn step."""
        self._application_request_identity(principal_id, turn_id, request_id, request_digest)
        _application_id(caller_host)
        _application_id(workload)
        _application_model(model)
        # The gateway supplies its existing mode=ro connection with BEGIN.
        # Original recovery does not wait for an admission flock or write data.
        turn = connection.execute("SELECT * FROM application_turns WHERE principal_id=? AND turn_id=?",
                                  (principal_id, turn_id)).fetchone()
        if turn is None:
            return {"kind": "turn_absent"}
        if (turn["caller_host"] != caller_host or turn["workload"] != workload
                or turn["model"] != model or turn["recipe_digest"] != expected_recipe_digest):
            raise ApplicationAdmissionError("recovery_context_conflict")
        request = self._application_prior_request(connection, turn, request_id, request_digest)
        binding = self._application_binding(connection, turn)
        if request is not None:
            return {"kind": "request_present", "turn": binding, "request": request}
        return {"kind": "turn_present_new_step", "turn": binding}

    def prepare_application_request(self, *, principal_id, turn_id, request_id, request_digest,
                                    transport_commitment=None):
        self._application_request_identity(principal_id, turn_id, request_id, request_digest)
        with self._application_transaction() as conn:
            turn = self._application_turn(conn, principal_id, turn_id)
            prior = self._application_prior_request(conn, turn, request_id, request_digest)
            if prior is not None:
                return prior
            commitment = {}
            if turn["pool"] in _APPLICATION_HTTP_POOLS:
                fields = {"recipe_digest", "logical_payload_digest", "wire_body_digest"}
                if not isinstance(transport_commitment, dict) or set(transport_commitment) != fields:
                    raise ApplicationAdmissionError("invalid_transport_commitment")
                commitment = {key: _application_digest(transport_commitment[key]) for key in fields}
                if commitment["recipe_digest"] != turn["recipe_digest"]:
                    raise ApplicationAdmissionError("recipe_changed")
                encoded, digest = _application_http_recipe(json.loads(turn["recipe_json"]),
                                                          pool=turn["pool"], model=turn["model"])
                if digest != turn["recipe_digest"] or encoded != turn["recipe_json"]:
                    raise ApplicationAdmissionError("recipe_changed")
            elif transport_commitment is not None:
                raise ApplicationAdmissionError("invalid_transport_commitment")
            document, grant, digest = self._application_grant(principal_id, turn["caller_host"],
                turn["workload"], turn["pool"], turn["model"],
                expected_recipe_digest=turn["recipe_digest"])
            if digest != turn["grant_digest"]:
                raise ApplicationAdmissionError("grant_changed")
            lease = conn.execute("SELECT * FROM leases WHERE id=?", (turn["lease_id"],)).fetchone()
            now = _application_time(self.now())
            if (turn["state"] != "open" or lease is None or lease["purpose"] != "APPLICATION"
                    or lease["state"] not in HELD_STATES
                    or now >= min(turn["expires_at"], lease["granted_at"] + lease["ttl"])):
                raise ApplicationAdmissionError("turn_closed")
            if self._application_unsettled(conn, turn):
                return {"ok": False, "dispatch_permitted": False, "disposition": "effect_unknown"}
            count = conn.execute("SELECT COUNT(*) FROM application_requests WHERE principal_id=? AND turn_id=?",
                                 (principal_id, turn_id)).fetchone()[0]
            if count >= turn["max_steps"]:
                raise ApplicationAdmissionError("step_limit")
            accounts_token = _APPLICATION_ACCOUNTS.set(document)
            try:
                if not any(a["name"] == turn["account"] and a.get("enabled", True) is not False
                           for a in self.grantable_accounts(turn["pool"])):
                    raise ApplicationAdmissionError("account_unavailable")
            finally:
                _APPLICATION_ACCOUNTS.reset(accounts_token)
            if any(lease[key] != turn[key] for key in ("account", "model", "pool")):
                raise ApplicationAdmissionError("lease_changed")
            now = _application_time(self.now())
            expires = min(grant["expires_at"], turn["expires_at"], lease["granted_at"] + lease["ttl"])
            if now >= expires:
                raise ApplicationAdmissionError("turn_closed")
            dispatch_id = uuid.uuid4().hex
            conn.execute("INSERT INTO application_requests (principal_id,turn_id,request_id,request_digest,dispatch_id,state,created_at,"
                         "recipe_digest,logical_payload_digest,wire_body_digest) "
                         "VALUES (?,?,?,?,?,'pending',?,?,?,?)", (principal_id, turn_id, request_id,
                          request_digest, dispatch_id, now, commitment.get("recipe_digest"),
                          commitment.get("logical_payload_digest"), commitment.get("wire_body_digest")))
            return {"ok": True, "dispatch_permitted": True, "disposition": "dispatch_permitted", **commitment,
                    "dispatch_id": dispatch_id, "request_digest": request_digest,
                    "expires_at": expires,
                    "lease_id": turn["lease_id"], "pool": turn["pool"], "account": turn["account"], "model": turn["model"]}

    def _application_release_if_finished(self, conn, turn):
        lease = conn.execute("SELECT * FROM leases WHERE id=?", (turn["lease_id"],)).fetchone()
        if lease is None or self._application_unsettled(conn, turn):
            return False
        expired = self.now() >= min(turn["expires_at"], lease["granted_at"] + lease["ttl"])
        if turn["state"] == "open" and not expired:
            return False
        conn.execute("UPDATE application_turns SET state='closed' WHERE principal_id=? AND turn_id=?",
                     (turn["principal_id"], turn["turn_id"]))
        conn.execute("UPDATE leases SET state='released' WHERE id=? AND purpose='APPLICATION' AND state IN ('held','rented')",
                     (turn["lease_id"],))
        return True

    def complete_application_request(self, *, dispatch_id, terminal_receipt):
        _application_id(dispatch_id)
        receipt = terminal_receipt
        encoded = _application_receipt(receipt)
        with self._application_transaction() as conn:
            request = conn.execute("SELECT * FROM application_requests WHERE dispatch_id=?", (dispatch_id,)).fetchone()
            if request is None:
                raise ApplicationAdmissionError("dispatch_unavailable")
            turn = self._application_turn(conn, request["principal_id"], request["turn_id"])
            if (receipt["dispatch_id"] != dispatch_id or receipt["request_digest"] != request["request_digest"]
                    or any(receipt[key] != turn[key] for key in ("lease_id", "account", "model"))
                    or not request["created_at"] <= receipt["completed_at"] <= self.now()):
                raise ApplicationAdmissionError("terminal_conflict")
            if turn["pool"] in _APPLICATION_HTTP_POOLS:
                if (receipt.get("terminal_kind") != "http_responses_v1"
                        or receipt["recipe_digest"] != turn["recipe_digest"]
                        or any(receipt[key] != request[key] for key in (
                            "recipe_digest", "logical_payload_digest", "wire_body_digest"))):
                    raise ApplicationAdmissionError("terminal_conflict")
            elif "terminal_kind" in receipt:
                raise ApplicationAdmissionError("terminal_conflict")
            if request["state"] == "terminal":
                if request["terminal_receipt"] != encoded:
                    raise ApplicationAdmissionError("terminal_conflict")
                return {"ok": True, "disposition": "terminal", "terminal_receipt": json.loads(encoded)}
            if request["state"] not in {"pending", "unknown"}:
                raise ApplicationAdmissionError("invalid_request_state")
            conn.execute("UPDATE application_requests SET state='terminal', terminal_receipt=?, unknown_reason=NULL WHERE dispatch_id=?",
                         (encoded, dispatch_id))
            self._application_release_if_finished(conn, turn)
            return {"ok": True, "disposition": "terminal", "terminal_receipt": json.loads(encoded)}

    def mark_application_request_unknown(self, *, dispatch_id, reason):
        _application_id(dispatch_id)
        if not isinstance(reason, str) or re.fullmatch(r"[a-z][a-z0-9_]{0,63}", reason) is None:
            raise ApplicationAdmissionError("invalid_unknown_reason")
        with self._application_transaction() as conn:
            request = conn.execute("SELECT * FROM application_requests WHERE dispatch_id=?", (dispatch_id,)).fetchone()
            if request is None:
                raise ApplicationAdmissionError("dispatch_unavailable")
            if request["state"] == "terminal":
                turn = self._application_turn(conn, request["principal_id"], request["turn_id"])
                return {"ok": True, "disposition": "terminal" if _application_stored_terminal(request, turn)
                        is not None else "effect_unknown"}
            if request["state"] not in {"pending", "unknown"}:
                raise ApplicationAdmissionError("invalid_request_state")
            conn.execute("UPDATE application_requests SET state='unknown', unknown_reason=? WHERE dispatch_id=?",
                         (reason, dispatch_id))
            return {"ok": True, "disposition": "effect_unknown"}

    def close_application_turn(self, *, principal_id, turn_id):
        _application_id(principal_id)
        _application_id(turn_id)
        with self._application_transaction() as conn:
            turn = self._application_turn(conn, principal_id, turn_id)
            conn.execute("UPDATE application_turns SET state='closing' WHERE principal_id=? AND turn_id=? AND state='open'",
                         (principal_id, turn_id))
            turn = self._application_turn(conn, principal_id, turn_id)
            self._application_release_if_finished(conn, turn)
            return self._application_binding(conn, self._application_turn(conn, principal_id, turn_id))

    # ── plan / status ────────────────────────────────────────────────────────

    def plan(
        self,
        task_class: str,
        need: int,
        orchestrator_id: str,
    ) -> List[Dict[str, Any]]:
        lock = self._lock()
        try:
            self._gc_locked()
            conn = self._conn()
            try:
                # N1: plan is visibility only for fair share. Drop leftover
                # plan-* waiters so they cannot inflate the denominator or
                # zero surplus_ok. Only a blocked/failed acquire competes.
                conn.execute("DELETE FROM waiters WHERE id LIKE 'plan-%'")
                conn.commit()
                out = []
                doc = self.load_accounts_doc()
                for name in (doc.get("providers") or {}):
                    out.append(self._plan_pool(conn, name, task_class, need, orchestrator_id))
                return out
            finally:
                conn.close()
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)
            lock.close()

    def _window_remaining(self, pool: str) -> str:
        try:
            if HERE not in sys.path:
                sys.path.insert(0, HERE)
            import pool_status

            return pool_status._window_remaining("bailian" if pool == "qwen" else pool)
        except Exception:
            pass
        spec = self.provider(pool)
        if spec.get("_name") == "grok" and self._grok_exhausted():
            return "EXHAUSTED"
        if spec.get("enabled") is False:
            return "disabled"
        wins = []
        for acct in spec.get("accounts") or []:
            for w in acct.get("windows") or []:
                if w.get("reset_anchor"):
                    wins.append(str(w["reset_anchor"]))
                elif w.get("reset_approx"):
                    wins.append(str(w["reset_approx"]))
                elif w.get("kind"):
                    wins.append(str(w["kind"]))
        return wins[0] if wins else "—"

    def _plan_pool(
        self,
        conn: sqlite3.Connection,
        pool: str,
        task_class: str,
        need: int,
        orch: str,
    ) -> Dict[str, Any]:
        pool = self.provider_name(pool)
        cap = self.pool_cap(pool)
        active = len(self._active_leases(conn, pool))
        held_by_me = len(self._held_by(conn, orch, pool)) if orch else 0
        # N1: plan is read-only for fair share — do not count the caller as
        # an extra orchestrator just because they asked for a plan.
        share = self.fair_share(conn, pool)
        below = self._below_share_waiters(conn, pool, orch or "", share)
        free = max(0, cap - active)
        entitled = max(0, share - held_by_me)
        surplus_ok = free - entitled if not below else 0
        grant_now = min(int(need), free, entitled + max(0, surplus_ok))
        if cap <= 0:
            grant_now = 0
        still = max(0, int(need) - grant_now)
        wait_est: Any = 0
        if still:
            if cap <= 0:
                wait_est = "unknown"
            else:
                active_rows = list(self._active_leases(conn, pool))
                surplus = []
                for r in active_rows:
                    try:
                        renew = int(r["renewable"])
                    except (KeyError, IndexError, TypeError, ValueError):
                        renew = 1
                    if r["state"] == "rented" or renew == 0:
                        surplus.append(r)
                cand = surplus if surplus else active_rows
                now = self.now()
                remain = []
                for r in cand:
                    rem = float(r["ttl"]) - (now - float(r["last_heartbeat"]))
                    remain.append(max(0.0, rem))
                wait_est = int(min(remain)) if remain else "unknown"
        # N1: do not enqueue plan-* demand and do not mark surplus from plan.
        # Recording competing demand is acquire's job.
        return {
            "pool": pool,
            "grant_now": grant_now,
            "wait_est": wait_est,
            "fair_share": share,
            "held_by_me": held_by_me,
            "cluster_active": active,
            "cap": cap,
            "window_remaining": self._window_remaining(pool),
            "task_class": task_class,
            "need": int(need),
        }

    def snapshot(self) -> Dict[str, Any]:
        lock = self._lock()
        try:
            self._gc_locked()
            conn = self._conn()
            try:
                return self._snapshot_locked(conn)
            finally:
                conn.close()
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)
            lock.close()

    def _snapshot_locked(self, conn: sqlite3.Connection) -> Dict[str, Any]:
        doc = self.load_accounts_doc()
        pools: Dict[str, Any] = {}
        leases_out: List[Dict[str, Any]] = []
        waiters_out: List[Dict[str, Any]] = []
        now = self.now()
        for name, spec in (doc.get("providers") or {}).items():
            cap = self.pool_cap(name)
            active_rows = self._active_leases(conn, name)
            accounts_out = []
            for acct in spec.get("accounts") or []:
                aname = str(acct.get("name") or "")
                eff = self.account_cap(name, acct)
                accounts_out.append(
                    {
                        "name": aname,
                        "cap": int(acct.get("per_account_cap") or 0)
                        if acct.get("per_account_cap") is not None
                        else None,
                        "effective_cap": eff,
                        "held": self._account_held(conn, name, aname),
                        "parked": self._parked(acct, now),
                        "parked_until": acct.get("parked_until"),
                        "quota_cooldown": __import__("quota_circuit").snapshot_cooldown(self, name, aname, conn),
                        "usage": acct.get("usage") or {},
                    }
                )
            orchs = self._active_orchestrators(conn, name)
            pools[name] = {
                "cap": cap,
                "cluster_active": len(active_rows),
                "remaining": max(0, cap - len(active_rows)),
                "fair_share": self.fair_share(conn, name),
                "window_remaining": self._window_remaining(name),
                "enabled": spec.get("enabled", True),
                "concurrency_cap": (None if spec.get("capacity_policy") == "host_admitted"
                                    else spec.get("concurrency_cap", cap if spec.get("enabled", True) else None)),
                "capacity_basis": spec.get("capacity_policy", "account"),
                "exhausted": bool(name == "grok" and self._grok_exhausted()),
                "accounts": accounts_out,
                "orchestrators_active": len(orchs),
            }
        for row in self._active_leases(conn):
            leases_out.append(
                {
                    "id": row["id"],
                    "orchestrator_id": row["orchestrator_id"],
                    "pool": row["pool"],
                    "account": row["account"],
                    "task_class": row["task_class"],
                    "model": row["model"] if "model" in row.keys() else "",
                    "host": row["host"],
                    "pid": row["pid"],
                    "granted_at": row["granted_at"],
                    "ttl": row["ttl"],
                    "last_heartbeat": row["last_heartbeat"],
                    "state": row["state"],
                    "renewable": int(row["renewable"]) if "renewable" in row.keys() else 1,
                    "age_s": int(now - float(row["granted_at"])),
                }
            )
        for row in conn.execute("SELECT * FROM waiters ORDER BY priority ASC, enqueued_at ASC"):
            waiters_out.append(
                {
                    "id": row["id"],
                    "orchestrator_id": row["orchestrator_id"],
                    "pool": row["pool"],
                    "task_class": row["task_class"],
                    "priority": row["priority"],
                    "enqueued_at": row["enqueued_at"],
                    "wait_s": int(now - float(row["enqueued_at"])),
                }
            )
        extra: Dict[str, Any] = {}
        try:
            if HERE not in sys.path:
                sys.path.insert(0, HERE)
            import pool_status

            extra = pool_status.build_status()
        except Exception:
            extra = {}
        # Merge local observations (offpeak, last 402, bailian key cooldown)
        # under pools without overwriting broker cap/active.
        for pname, local in (extra.get("pools") or {}).items():
            if pname not in pools:
                continue
            for k in ("last_402_429", "offpeak", "offpeak_window", "per_key_cap", "keys"):
                if k in local:
                    pools[pname][k] = local[k]
        return {
            "schema": "mastermind.provider_capacity.v1",
            "generated_at": int(now),
            "generated_at_human": _now_iso(now),
            "this_host": self.this_host,
            "orchestrators_active": len({r["orchestrator_id"] for r in leases_out}),
            "pools": pools,
            "leases": leases_out,
            "waiters": waiters_out,
            "offpeak": extra.get("offpeak"),
            "provenance": {
                "db_path": self.db_path,
                "broker_host": self.this_host,
                "coverage": "configured lease ledger only",
                "note": "counts reflect this configured lease ledger; execution host may differ",
            },
        }

    def write_status_json(self, snap: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        snap = snap if snap is not None else self.snapshot()
        os.makedirs(os.path.dirname(self.status_json), exist_ok=True)
        tmp = self.status_json + ".new"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(snap, fh, indent=2)
        os.replace(tmp, self.status_json)
        return snap

    def print_status(self, snap: Optional[Dict[str, Any]] = None) -> None:
        snap = snap if snap is not None else self.snapshot()
        cols = 88
        print()
        print("═" * cols)
        print("  AGENT POOL STATUS  (cluster lease broker)".center(cols))
        print("═" * cols)
        print(f"  schema={snap.get('schema')}  host={snap.get('this_host')}  orchs={snap.get('orchestrators_active')}")
        print(f"  generated={snap.get('generated_at_human')}  offpeak={snap.get('offpeak')}")
        provenance = snap.get("provenance") or {}
        print(
            f"  provenance: db={provenance.get('db_path', 'unverified')}  "
            f"broker_host={provenance.get('broker_host', 'unverified')}  "
            "coverage=configured lease ledger only (execution host may differ)"
        )
        print("─" * cols)
        print(
            f"  {'POOL':<10} {'CAP':>4} {'ACTIVE':>6} {'REM':>4} {'SHARE':>5} "
            f"{'ORCHS':>5} {'WAIT':>4} {'WINDOW':<22}"
        )
        for name, p in (snap.get("pools") or {}).items():
            wait_n = sum(1 for w in snap.get("waiters") or [] if w.get("pool") == name)
            win = str(p.get("window_remaining") or "—")[:22]
            if p.get("exhausted"):
                win = "EXHAUSTED"
            cap_s = ("HOST" if p.get("capacity_basis") == "host_admitted"
                     else "—" if p.get("concurrency_cap") is None and not p.get("enabled")
                     else str(p.get("cap", 0)))
            print(
                f"  {name:<10} {cap_s:>4} {p.get('cluster_active', 0):>6} "
                f"{p.get('remaining', 0):>4} {p.get('fair_share', 0):>5} "
                f"{p.get('orchestrators_active', 0):>5} {wait_n:>4} {win:<22}"
            )
        print("─" * cols)
        print("  ACCOUNTS")
        print(f"  {'POOL':<10} {'NAME':<12} {'CAP':>4} {'HELD':>4} {'PARKED':>8} {'UNTIL':<22}")
        for name, p in (snap.get("pools") or {}).items():
            for a in p.get("accounts") or []:
                parked = "YES" if a.get("parked") else "no"
                until = str(a.get("parked_until") or "—")[:22]
                cap = a.get("effective_cap")
                cap_s = ("HOST" if p.get("capacity_basis") == "host_admitted"
                         else "—" if cap is None else str(cap))
                print(
                    f"  {name:<10} {a.get('name','?'):<12} {cap_s:>4} "
                    f"{a.get('held', 0):>4} {parked:>8} {until:<22}"
                )
        print("─" * cols)
        print("  LEASES")
        print(
            f"  {'ID':<12} {'ORCH':<16} {'POOL':<8} {'ACCT':<10} {'HOST':<14} "
            f"{'PID':>6} {'AGE':>5} {'STATE':<8}"
        )
        for r in snap.get("leases") or []:
            print(
                f"  {str(r.get('id','')):<12} {str(r.get('orchestrator_id',''))[:16]:<16} "
                f"{str(r.get('pool','')):<8} {str(r.get('account','')):<10} "
                f"{str(r.get('host',''))[:14]:<14} {int(r.get('pid') or 0):>6} "
                f"{int(r.get('age_s') or 0):>5} {str(r.get('state','')):<8}"
            )
        if not snap.get("leases"):
            print("  (none)")
        # This is the existing broker's *read-only* operator view, not another
        # lease-reaper or completion authority. Remote shell acquires record
        # their launching broker-host PID even when execution host differs.
        # Only inspect PIDs when the snapshot is from our own PID namespace.
        if snap.get("this_host") == self.this_host:
            absent = []
            for row in snap.get("leases") or []:
                if (isinstance(row, dict)
                        and str(row.get("task_class") or "").startswith("remote-")
                        and row.get("state") in ("held", "rented")
                        and _broker_controller_pid_observation(row.get("pid")) == "ABSENT"):
                    absent.append(str(row.get("id") or ""))
            if absent:
                print(f"  CONTROLLER_PID_ABSENT count={len(absent)} (broker host only)")
                for lease_id in absent[:20]:
                    print(f"    lease={lease_id} remote_worker=UNKNOWN no_release_or_retry=1")
                if len(absent) > 20:
                    print(f"    additional_unlisted={len(absent) - 20}")
                print("  Original run/host result and lease effect must be reconciled before release.")
        print("─" * cols)
        print("  WAITERS")
        if snap.get("waiters"):
            for w in snap["waiters"]:
                print(
                    f"  id={w.get('id')} orch={w.get('orchestrator_id')} "
                    f"pool={w.get('pool')} class={w.get('task_class')} "
                    f"pri={w.get('priority')} wait_s={w.get('wait_s')}"
                )
        else:
            print("  (none)")
        print("═" * cols)
        print()


def default_broker() -> Broker:
    return Broker(
        db_path=os.environ.get("POOL_BROKER_DB") or DEFAULT_DB,
        lock_path=os.environ.get("POOL_BROKER_LOCK") or DEFAULT_LOCK,
        accounts_path=os.environ.get("POOL_ACCOUNTS_YAML") or DEFAULT_ACCOUNTS,
        grok_marker=os.environ.get("POOL_GROK_MARKER") or GROK_EXHAUSTED,
        this_host=os.environ.get("POOL_BROKER_HOST") or _this_host(),
        status_json=os.environ.get("POOL_STATUS_JSON") or STATUS_JSON,
    )


def resolve_orchestrator_id(explicit: Optional[str] = None) -> str:
    if explicit:
        return explicit.strip()
    for key in ("POOL_ORCHESTRATOR_ID", "CLAUDE_SESSION_ID"):
        val = (os.environ.get(key) or "").strip()
        if val:
            return val
    host = _this_host()
    return f"ppid-{host}-{os.getppid()}"


def _print_plan(rows: List[Dict[str, Any]]) -> None:
    for r in rows:
        we = r["wait_est"]
        we_s = f"{we}s" if isinstance(we, (int, float)) else str(we)
        print(
            f"POOL={r['pool']} grant_now={r['grant_now']} wait_est={we_s} "
            f"fair_share={r['fair_share']} held_by_me={r['held_by_me']} "
            f"cluster_active={r['cluster_active']}/{r['cap']} "
            f"window_remaining={r['window_remaining']}"
        )


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    p = argparse.ArgumentParser(description="cluster-wide agent-slot lease broker")
    sub = p.add_subparsers(dest="cmd", required=True)

    pa = sub.add_parser("acquire")
    pa.add_argument("--orchestrator-id", default=None)
    pa.add_argument("--pool", required=True)
    pa.add_argument("--account", default=None)
    pa.add_argument("--task-class", default="unknown")
    pa.add_argument("--model", default="")
    pa.add_argument("--operator-child-id", default=None)
    pa.add_argument("--host", default=None)
    pa.add_argument("--pid", type=int, default=0)
    pa.add_argument("--ttl", type=int, default=None)
    pa.add_argument("--wait", type=float, default=0)
    pa.add_argument("--poll", type=float, default=1.0)
    pa.add_argument("--deadline-ns", type=int, default=None)
    pa.add_argument("--not-before", default=None)
    pa.add_argument("--prelease-receipt", default=None)
    pa.add_argument("--run-id", default=None)
    pa.add_argument("--parent-run-id", default=None)
    pa.add_argument("--request-sha256", default=None)
    pa.add_argument("--launch-sha256", default=None)
    pa.add_argument("--controller-sha256", default=None)

    ph = sub.add_parser("heartbeat")
    ph.add_argument("lease_id")

    pr = sub.add_parser("release")
    pr.add_argument("lease_id")
    pr.add_argument("--orchestrator-id", default=None)

    po = sub.add_parser("observe-provider")
    for field in ("lease-id", "root-id", "run-id", "outcome", "process"):
        po.add_argument("--" + field, required=True)

    pp = sub.add_parser("plan")
    pp.add_argument("--class", dest="task_class", default=None)
    pp.add_argument("--task-class", dest="task_class_alt", default=None)
    pp.add_argument("--need", type=int, required=True)
    pp.add_argument("--orchestrator-id", default=None)

    sub.add_parser("status")
    sub.add_parser("gc")

    args = p.parse_args(argv)
    if args.cmd == "acquire" and args.not_before is not None:
        from commission_deadline import (require_not_before, CallerNotBeforePending, CallerNotBeforeInvalid)
        try:
            require_not_before(args.not_before)
        except CallerNotBeforePending as exc:
            print(str(exc))
            return 75
        except CallerNotBeforeInvalid as exc:
            print(str(exc))
            return 2
    deadline = None
    if args.cmd == "acquire" and args.deadline_ns is not None:
        deadline = validate_deadline_ns(args.deadline_ns)
    token = _ACQUIRE_DEADLINE_NS.set(deadline)
    try:
        br = default_broker()
    except (CommissionDeadlineExpired, sqlite3.OperationalError):
        if deadline is not None and time.monotonic_ns() >= deadline:
            print("WAIT reason=commission_time_exhausted")
            return 75
        raise
    finally:
        _ACQUIRE_DEADLINE_NS.reset(token)

    if args.cmd == "observe-provider":
        import quota_circuit
        lock = br._lock()
        try:
            conn = br._conn()
            try:
                result = quota_circuit.observe_locked(br, conn, args.lease_id,
                    args.root_id, args.run_id, args.outcome, args.process)
                print(json.dumps(result, sort_keys=True))
                return 0
            finally:
                conn.close()
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)
            lock.close()

    if args.cmd == "acquire":
        oid = resolve_orchestrator_id(args.orchestrator_id)
        handoff_fields = (args.prelease_receipt, args.run_id, args.parent_run_id,
            args.request_sha256, args.launch_sha256, args.controller_sha256)
        if any(value is not None for value in handoff_fields):
            import re
            if (not all(isinstance(value, str) and value for value in handoff_fields)
                    or args.operator_child_id is not None
                    or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", args.run_id)
                    or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", args.parent_run_id)
                    or any(re.fullmatch(r"[0-9a-f]{64}", value) is None for value in handoff_fields[3:])
                    or args.pid <= 0):
                p.error("invalid prelease handoff binding")
        res = br.acquire(
            orchestrator_id=oid,
            pool=args.pool,
            account=args.account,
            task_class=args.task_class,
            model=args.model,
            host=args.host,
            pid=args.pid or os.getpid(),
            ttl=args.ttl,
            wait=args.wait,
            poll=args.poll,
            operator_child_id=args.operator_child_id,
            capacity_handoff=args.prelease_receipt is not None,
            deadline_ns=deadline,
            not_before=args.not_before,
        )
        if (res.reason == "quota_cooldown" and res.quota_blockade is not None
                and not res.ok and not res.lease_id and args.prelease_receipt):
            import quota_circuit
            quota_circuit.write_prelease_refusal(args.prelease_receipt,
                run_id=args.run_id, root_id=oid, parent_run_id=args.parent_run_id,
                pool=res.pool, host=args.host, model=args.model, pid=args.pid,
                request_sha256=args.request_sha256, launch_sha256=args.launch_sha256,
                controller_sha256=args.controller_sha256, blockade=res.quota_blockade)
        print(res.line())
        return 0 if res.ok else 75

    if args.cmd == "heartbeat":
        answer = br.heartbeat(args.lease_id)
        ttl = f" ttl={answer.ttl:g}" if answer.ttl is not None else ""
        print(f"HEARTBEAT lease={args.lease_id} ok={'yes' if answer else 'no'} reason={answer.reason}{ttl}")
        return 0 if answer else 1

    if args.cmd == "release":
        oid = resolve_orchestrator_id(args.orchestrator_id)
        ok = br.release(args.lease_id, orchestrator_id=oid)
        print(f"RELEASE lease={args.lease_id} ok={'yes' if ok else 'no'}")
        return 0 if ok else 1

    if args.cmd == "plan":
        tc = args.task_class or args.task_class_alt or "unknown"
        oid = resolve_orchestrator_id(args.orchestrator_id)
        rows = br.plan(tc, args.need, oid)
        _print_plan(rows)
        return 0

    if args.cmd == "status":
        snap = br.write_status_json()
        br.print_status(snap)
        return 0

    if args.cmd == "gc":
        n = br.gc()
        print(f"GC expired={n}")
        return 0

    return 2


if __name__ == "__main__":
    sys.exit(main())

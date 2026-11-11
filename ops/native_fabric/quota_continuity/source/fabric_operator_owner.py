#!/usr/bin/env python3
"""Controller-local authorization for paid operator children.

Authorization reservations live in the existing broker database and take its
existing lock. They do not represent worker state. The installed adapter,
controller, lease broker and outcome ledger remain the only execution owners.
This module is never shipped to workers; its issue/authorize entrypoints are
local principal operations, not remotely exposed MCP tools.
"""
from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import secrets
import sqlite3
import stat
import subprocess
import sys
import time

from fabric_operator_contract import DelegationRefused, validate_launch

HERE = Path(__file__).resolve().parent
TOKEN = re.compile(r"^[a-f0-9]{64}$")
IDENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
CHILD_SUFFIX = "\n\nReturn a bounded final response of at most 12000 characters. Do not delegate further.\n"
CLASSES = ["mechanical", "extract", "fix_build", "census", "audit", "build"]


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(value).hexdigest()


def refuse(reason):
    raise DelegationRefused(reason)


def safe_id(value):
    if not isinstance(value, str) or not IDENT.fullmatch(value):
        refuse("invalid_identity")
    return value


def clean_child_environment(env):
    # Never lend the operator's outer lease, model, account or host to its child.
    return {k: v for k, v in env.items() if not k.startswith((
        "POOL_", "LANE_", "REMOTE_SUB_", "FABRIC_OPERATOR_", "CODEX_",
        "CLAUDE_", "ANTHROPIC_", "GROK_", "OPENAI_", "OPENCODE_",
        "STUDIO_MCP_", "SUPPORT_DIGEST", "NATIVE_LEASE_"))}


class OperatorOwner:
    def __init__(self, *, here=HERE, clock=time.time):
        self.here = Path(here)
        self.db = self.here / "broker/leases.sqlite"
        self.lock = self.here / "broker/leases.lock"
        self.clock = clock

    def original_delivery_binding(self, run_id, *, root):
        """Historical launch correlation only; no capability, renewal or lease authority.

        The caller's original commission/ancestry must be qualified separately.
        Read a bounded held broker snapshot, never the live mutating transaction.
        """
        import artifact_delivery
        import artifact_reader
        safe_id(run_id); safe_id(root)
        row = artifact_delivery._retained_broker_row(
            "SELECT operator_run,root,grant_json,launch_json FROM operator_grants "
            "WHERE operator_run=? AND root=?", (run_id, root), here=self.here)
        if row is None:
            refuse("original_operator_binding_unavailable")
        grant = artifact_reader.strict_json(row["grant_json"])
        launch = artifact_reader.strict_json(row["launch_json"])
        fields = ("root", "lease_id", "pool", "model", "account", "host",
                  "support_sha256", "packet_sha256")
        if (type(grant) is not dict or type(launch) is not dict
                or row["operator_run"] != run_id or row["root"] != root
                or grant.get("schema") != "mastermind.fabric_operator_grant.v1"
                or grant.get("operator_run") != run_id or launch.get("run_id") != run_id
                or grant.get("root") != root or launch.get("root") != root
                or launch.get("task_class") != "domain_orchestration"
                or any(type(grant.get(k)) is not str or grant[k] != launch.get(k) for k in fields)
                or any(not IDENT.fullmatch(grant[k]) for k in fields[:-2])
                or any(not re.fullmatch(r"[a-f0-9]{64}", grant[k]) for k in fields[-2:])):
            refuse("original_operator_binding_mismatch")
        return {"schema": "mastermind.original_operator_launch_binding.v1",
                "operator_run": run_id, **{k: grant[k] for k in fields},
                "parent_binding": "NOT_RECORDED_IN_OPERATOR_GRANT",
                "current_authority": False, "lease_settlement": "UNKNOWN",
                "children_settlement": "UNKNOWN"}

    @contextlib.contextmanager
    def transaction(self):
        # A missing existing broker is an error, never permission to create one.
        for p in (self.db, self.lock):
            st = p.lstat()
            if not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid():
                refuse("broker_owner_or_type")
        fd = os.open(self.lock, os.O_RDWR | os.O_NOFOLLOW)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            con = sqlite3.connect(self.db.as_uri() + "?mode=rw", uri=True, timeout=10)
            con.row_factory = sqlite3.Row
            try:
                con.execute("BEGIN IMMEDIATE")
                yield con
                con.commit()
            except BaseException:
                con.rollback()
                raise
            finally:
                con.close()
        finally:
            os.close(fd)

    @staticmethod
    def _schema(con):
        con.execute("""CREATE TABLE IF NOT EXISTS operator_root_grants (
          root TEXT PRIMARY KEY, child_limit INTEGER NOT NULL,
          issued REAL NOT NULL, expires REAL NOT NULL)""")
        con.execute("""CREATE TABLE IF NOT EXISTS operator_grants (
          operator_run TEXT PRIMARY KEY, root TEXT NOT NULL,
          token_digest TEXT NOT NULL UNIQUE, grant_json TEXT NOT NULL,
          launch_json TEXT NOT NULL)""")
        con.execute("""CREATE TABLE IF NOT EXISTS operator_child_authorizations (
          run_id TEXT PRIMARY KEY, operator_run TEXT NOT NULL, root TEXT NOT NULL,
          request_digest TEXT NOT NULL, authorized_at REAL NOT NULL,
          request_json TEXT NOT NULL, admitted_lease_id TEXT, acknowledged_sha256 TEXT)""")

    def authorize_root(self, root, child_limit, expires):
        safe_id(root)
        now = self.clock()
        if type(child_limit) is not int or not 1 <= child_limit <= 64:
            refuse("invalid_root_budget")
        if type(expires) not in (float, int) or not math.isfinite(expires) or not now < expires <= now + 7200:
            refuse("invalid_root_deadline")
        with self.transaction() as con:
            self._schema(con)
            # Immutable per mission authorization; no remote budget reset.
            if con.execute("SELECT 1 FROM operator_root_grants WHERE root=?", (root,)).fetchone():
                refuse("root_grant_exists")
            con.execute("INSERT INTO operator_root_grants VALUES (?,?,?,?)", (root, child_limit, now, expires))
        return {"root": root, "child_limit": child_limit, "expires_at": expires}

    @staticmethod
    def lease(con, lease_id):
        row = con.execute("SELECT * FROM leases WHERE id=?", (lease_id,)).fetchone()
        if row is None:
            refuse("operator_lease_unavailable")
        return dict(row)

    def issue(self, launch, child_budget):
        """Called only by the local controller after its actual lease acquisition."""
        now = self.clock()
        root, run = safe_id(launch.get("root")), safe_id(launch.get("run_id"))
        with self.transaction() as con:
            self._schema(con)
            root_grant = con.execute("SELECT * FROM operator_root_grants WHERE root=?", (root,)).fetchone()
            if root_grant is None or not now < root_grant["expires"]:
                refuse("root_grant_unavailable")
            if con.execute("SELECT 1 FROM operator_grants WHERE operator_run=?", (run,)).fetchone():
                refuse("operator_grant_exists")
            lease = self.lease(con, launch.get("lease_id"))
            launch = dict(launch)
            if launch.get("pool") != lease["pool"]:
                # Same declared provider, not another account/provider retry.
                # The broker's canonical persisted name owns capability binding.
                from lease_broker import _load_yaml, DEFAULT_ACCOUNTS
                providers = _load_yaml(DEFAULT_ACCOUNTS).get("providers", {})
                aliases = providers.get(lease["pool"], {}).get("pool_aliases", [])
                if launch.get("pool") not in aliases:
                    refuse("operator_pool_alias_unbound")
                launch["pool"] = lease["pool"]
            grant = {k: v for k, v in launch.items() if k not in ("run_id", "task_class")}
            grant.update(schema="mastermind.fabric_operator_grant.v1", operator_run=run,
                         issued_at=now, expires_at=root_grant["expires"],
                         child_budget=child_budget, allowed_classes=CLASSES)
            root_used = con.execute("SELECT COUNT(*) FROM operator_child_authorizations WHERE root=?", (root,)).fetchone()[0]
            # Exercise the complete contract with an inert prospective request.
            probe = dict(schema="mastermind.fabric_operator_child_request.v1", root=root,
                         parent=run, run_id=run[:100] + ":contract-check", task_class="mechanical",
                         task_complexity="C0_MECHANICAL", packet="contract validation only")
            validate_launch(grant, lease, launch, probe, now=now, used_children=0,
                            root_children_remaining=root_grant["child_limit"] - root_used)
            token = secrets.token_hex(32)
            con.execute("INSERT INTO operator_grants VALUES (?,?,?,?,?)",
                        (run, root, digest(token.encode()), canonical(grant), canonical(launch)))
        # Only the private transport capsule receives this bearer; logs do not.
        capsule = {k: grant[k] for k in ("root", "operator_run", "lease_id", "pool", "model",
                   "account", "host", "support_sha256", "packet_sha256", "expires_at", "child_budget")}
        return {"token": token, **capsule}

    def _authorized(self, con, token):
        if not isinstance(token, str) or not TOKEN.fullmatch(token):
            refuse("operator_capability_refused")
        row = con.execute("SELECT * FROM operator_grants WHERE token_digest=?", (digest(token.encode()),)).fetchone()
        if row is None:
            refuse("operator_capability_refused")
        grant, launch = json.loads(row["grant_json"]), json.loads(row["launch_json"])
        root_grant = con.execute("SELECT * FROM operator_root_grants WHERE root=?", (grant["root"],)).fetchone()
        if root_grant is None or not self.clock() < root_grant["expires"]:
            refuse("root_grant_expired")
        lease = self.lease(con, grant["lease_id"])
        # Read authorization remains available after the child budget is used,
        # but only while the operator's actual lease and grant remain valid.
        probe = dict(schema="mastermind.fabric_operator_child_request.v1", root=grant["root"],
                     parent=grant["operator_run"], run_id=grant["operator_run"][:100] + ":read-check",
                     task_class="mechanical", task_complexity="C0_MECHANICAL", packet="read validation only")
        validate_launch(grant, lease, launch, probe, now=self.clock(), used_children=0,
                        root_children_remaining=1)
        return grant, launch, lease, root_grant

    def describe(self, token):
        with self.transaction() as con:
            grant, _, _, root = self._authorized(con, token)
            used = con.execute("SELECT COUNT(*) FROM operator_child_authorizations WHERE operator_run=?", (grant["operator_run"],)).fetchone()[0]
            root_used = con.execute("SELECT COUNT(*) FROM operator_child_authorizations WHERE root=?", (grant["root"],)).fetchone()[0]
        return {"root": grant["root"], "operator_run": grant["operator_run"],
                "child_budget_remaining": max(0, min(grant["child_budget"] - used, root["child_limit"] - root_used)),
                "expires_at": grant["expires_at"], "allowed_classes": grant["allowed_classes"]}

    def reserve(self, token, request):
        with self.transaction() as con:
            grant, launch, lease, root = self._authorized(con, token)
            used = con.execute("SELECT COUNT(*) FROM operator_child_authorizations WHERE operator_run=?", (grant["operator_run"],)).fetchone()[0]
            root_used = con.execute("SELECT COUNT(*) FROM operator_child_authorizations WHERE root=?", (grant["root"],)).fetchone()[0]
            now = self.clock()
            validate_launch(grant, lease, launch, request, now=now, used_children=used,
                            root_children_remaining=root["child_limit"] - root_used)
            # Same 660s broker start window; refuse before consuming authorization.
            if root is None or min(root["expires"], grant["expires_at"]) - now < 660:
                refuse("operator_child_start_window_expired")
            rid = request["run_id"]
            if con.execute("SELECT 1 FROM operator_child_authorizations WHERE run_id=?", (rid,)).fetchone():
                refuse("RUN_EXISTS")
            for suffix in (".log", ".result"):
                p = self.here / "state/remote_sub" / (rid + suffix)
                if p.exists() or p.is_symlink():
                    refuse("RUN_EXISTS")
            con.execute("INSERT INTO operator_child_authorizations VALUES (?,?,?,?,?,?,NULL,NULL)",
                        (rid, grant["operator_run"], grant["root"], digest(canonical(request).encode()), self.clock(), canonical(request)))
        return grant

    def child_binding(self, token, rid):
        safe_id(rid)
        with self.transaction() as con:
            grant, _, _, _ = self._authorized(con, token)
            row = con.execute("SELECT * FROM operator_child_authorizations WHERE run_id=? AND operator_run=? AND root=?",
                              (rid, grant["operator_run"], grant["root"])).fetchone()
            if row is None:
                refuse("child_binding_refused")
        return grant

    def dispatch(self, token, request, *, popen=subprocess.Popen):
        grant = self.reserve(token, request)
        rid = request["run_id"]
        # These files capture the existing adapter transport only. No worker
        # status or lease decisions are stored here.
        base = self.here / "state/remote_sub"
        fds = []
        try:
            for suffix in (".operator-packet", ".operator-transport"):
                fds.append(os.open(base / (rid + suffix), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600))
            packet = request["packet"] + CHILD_SUFFIX
            pending = memoryview(packet.encode())
            while pending:
                written = os.write(fds[0], pending)
                if written <= 0: raise OSError("packet_write_incomplete")
                pending = pending[written:]
            os.fsync(fds[0])
            command = [sys.executable, str(self.here / "fabric_task.py"), "request", "--id", rid,
                       "--class", request["task_class"], "--task-complexity", request["task_complexity"],
                       "--packet", str(base / (rid + ".operator-packet")), "--cwd", "~",
                       "--root", grant["root"], "--parent", grant["operator_run"]]
            proc = popen(command, stdin=subprocess.DEVNULL, stdout=fds[1], stderr=fds[1],
                         env={**clean_child_environment(os.environ),
                              "FABRIC_OPERATOR_CHILD_ID": rid, "REMOTE_SUB_LEASE_WAIT": "60",
                              "REMOTE_SUB_CHILD_TIMEOUT": "600"},
                         start_new_session=True, close_fds=True)
            return {"state": "SUBMITTED_TO_EXISTING_ADAPTER", "run_id": rid,
                    "root": grant["root"], "parent": grant["operator_run"],
                    "controller_pid": proc.pid, "provider_start_proven": False, "retry_authorized": False}
        except Exception:
            # The immutable authorization remains consumed even if the reply is
            # lost. Never refund and replay an uncertain dispatch.
            return {"state": "DISPATCH_UNVERIFIED", "run_id": rid, "retry_authorized": False}
        finally:
            for fd in fds:
                os.close(fd)

    def observe(self, token, action, rid):
        grant = self.child_binding(token, rid)
        import fabric_task
        state = fabric_task.inspect_run(rid)
        if state.get("result_available"):
            if state.get("root_id") != grant["root"] or state.get("parent_run_id") != grant["operator_run"]:
                refuse("retained_result_binding_refused")
        if action == "status" or not state.get("result_available"):
            return state
        raw = fabric_task.read_result(rid, max_bytes=65536)
        again = fabric_task.inspect_run(rid)
        raw_again = fabric_task.read_result(rid, max_bytes=65536)
        if again != state or raw_again != raw:
            refuse("retained_result_changed")
        return {"run_id": rid, "root": grant["root"], "parent": grant["operator_run"],
                "sha256": digest(raw), "bytes": len(raw), "content": raw.decode("utf-8"),
                "untrusted_worker_content": True, "status": state}


    def returns(self, token):
        with self.transaction() as con:
            grant, _, _, _ = self._authorized(con, token)
            rows = con.execute("SELECT run_id,acknowledged_sha256 FROM operator_child_authorizations WHERE operator_run=? AND root=? ORDER BY authorized_at", (grant['operator_run'], grant['root'])).fetchall()
        import fabric_task
        states = []
        for row in rows:
            if row['acknowledged_sha256'] is not None:
                continue
            state = fabric_task.inspect_run(row['run_id'])
            item = {k: state.get(k) for k in ('run_id','state','rc','result_available')}
            if state.get('result_available'):
                # This method performs no content delivery or acceptance.
                if state.get('root_id') != grant['root'] or state.get('parent_run_id') != grant['operator_run']:
                    refuse('retained_result_binding_refused')
                raw = fabric_task.read_result(row['run_id'], max_bytes=65536)
                if fabric_task.inspect_run(row['run_id']) != state:
                    refuse('retained_result_changed')
                item.update(sha256=digest(raw),bytes=len(raw))
            states.append(item)
        return dict(root=grant['root'], parent=grant['operator_run'], children=states,
                    acceptance_recorded=False)

    def acknowledge(self, token, rid, sha256):
        # Acknowledges the operator's explicit consumption statement only.
        # Outcome acceptance remains exclusively in the incumbent ledger.
        result = self.observe(token, 'result', rid)
        if result.get('sha256') != sha256 or not re.fullmatch('[a-f0-9]{64}', sha256):
            refuse('consumption_digest_mismatch')
        with self.transaction() as con:
            grant, _, _, _ = self._authorized(con, token)
            old = con.execute("SELECT acknowledged_sha256 FROM operator_child_authorizations WHERE run_id=? AND operator_run=? AND root=?",(rid, grant['operator_run'],grant['root'])).fetchone()
            if old is None or old['acknowledged_sha256'] not in (None,sha256):
                refuse('consumption_binding_mismatch')
            con.execute("UPDATE operator_child_authorizations SET acknowledged_sha256=? WHERE run_id=?",(sha256,rid))
        return dict(run_id=rid,sha256=sha256,consumption_acknowledged=True,acceptance_recorded=False)

    def wait(self, token, rid, seconds):
        if type(seconds) is not int or not 1 <= seconds <= 30:
            refuse('wait_bound')
        deadline = time.monotonic() + seconds
        while True:
            value = self.observe(token,'status',rid)
            if value.get('result_available') or value.get('state') not in ('ACTIVE_OR_WAITING','NOT_FOUND') or time.monotonic() >= deadline:
                return value
            time.sleep(min(3,max(0,deadline-time.monotonic())))


def validate_child_admission(con, run_id, root, *, now, admitted_lease_id=None, start_binding=None, packet_sha256=None):
    """Called under the incumbent broker lock immediately before its grant.

    The optional controller start readback uses the already-created child lease;
    it cannot create/replay a grant or reset a consumed authorization.
    """
    safe_id(run_id)
    row = con.execute("SELECT * FROM operator_child_authorizations WHERE run_id=? AND root=?",
                      (run_id, root)).fetchone()
    if row is None:
        refuse("operator_child_authorization_missing")
    row = dict(row)
    if row['admitted_lease_id'] != admitted_lease_id:
        refuse("operator_child_already_admitted_or_mismatch")
    issued = con.execute("SELECT * FROM operator_grants WHERE operator_run=? AND root=?",
                         (row['operator_run'], root)).fetchone()
    if issued is None:
        refuse("operator_parent_grant_missing")
    grant, launch = json.loads(issued['grant_json']), json.loads(issued['launch_json'])
    root_grant = con.execute("SELECT * FROM operator_root_grants WHERE root=?", (root,)).fetchone()
    if root_grant is None or min(root_grant['expires'], grant['expires_at']) - now < 660:
        refuse("operator_child_start_window_expired")
    lease = OperatorOwner.lease(con, grant['lease_id'])
    request = json.loads(row['request_json'])
    if digest(canonical(request).encode()) != row['request_digest']:
        refuse("operator_child_authorization_changed")
    validate_launch(grant, lease, launch, request, now=now, used_children=0,
                    root_children_remaining=1)
    if admitted_lease_id is not None:
        child = OperatorOwner.lease(con, admitted_lease_id)
        if (child['orchestrator_id'] != root or child['state'] not in ('held', 'rented')
                or not child['last_heartbeat'] <= now < child['last_heartbeat'] + child['ttl']):
            refuse("operator_child_lease_unavailable")
        if packet_sha256 is not None and packet_sha256 != digest((request['packet'] + CHILD_SUFFIX).encode()):
            refuse('operator_child_packet_binding_mismatch')
        if start_binding is not None and (set(start_binding) != {'pool','model','account','host'} or any(child[k] != v for k,v in start_binding.items())):
            refuse('operator_child_launch_binding_mismatch')
    return grant



def refusal_payload(error):
    # Fixed public reason only; never disclose arbitrary exceptions or capability data.
    value = {"state": "OPERATOR_REQUEST_REFUSED", "retry_authorized": False}
    if isinstance(error, DelegationRefused) and str(error) == "operator_child_start_window_expired":
        value["reason"] = "operator_child_start_window_expired"
    return value


def main():
    # Remote callers can reach only these closed operations through the gateway.
    raw = sys.stdin.buffer.read(70001)
    if len(raw) > 70000:
        refuse("request_too_large")
    value = json.loads(raw)
    if type(value) is not dict or set(value) != {"action", "token", "arguments"}:
        refuse("request_shape")
    owner = OperatorOwner()
    action, args = value["action"], value["arguments"]
    if action == "describe" and args == {}:
        result = owner.describe(value["token"])
    elif action == "returns" and args == {}:
        result = owner.returns(value["token"])
    elif action == "acknowledge" and type(args) is dict and set(args) == {"run_id", "sha256"}:
        result = owner.acknowledge(value["token"], args["run_id"], args["sha256"])
    elif action == "wait" and type(args) is dict and set(args) == {"run_id", "seconds"}:
        result = owner.wait(value["token"], args["run_id"], args["seconds"])
    elif action == "request":
        result = owner.dispatch(value["token"], args)
    elif action in ("status", "result") and type(args) is dict and set(args) == {"run_id"}:
        result = owner.observe(value["token"], action, args["run_id"])
    else:
        refuse("operation_refused")
    print(canonical(result))


if __name__ == "__main__":
    try:
        main()
    except (DelegationRefused, ValueError, KeyError, TypeError, OSError, sqlite3.Error) as exc:
        print(canonical(refusal_payload(exc)))
        raise SystemExit(75)

"""Quota exclusions inside the existing lease broker database and lock.

No independent clock, queue, daemon, credentials, or capacity grants. Expiry
permits one existing broker lease to probe; only its qualified success clears
the exclusion. Every ordinary provider/account/economic gate still applies.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
import re

import provider_outcome


def init_schema(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS quota_cooldowns (
        scope TEXT PRIMARY KEY, observed_at REAL NOT NULL,
        until_ts REAL NOT NULL, failures INTEGER NOT NULL,
        kind TEXT NOT NULL, source_run TEXT NOT NULL,
        reset_source TEXT NOT NULL)""")
    cols = {r[1] for r in conn.execute("PRAGMA table_info(leases)")}
    if "quota_outcome_sha256" not in cols:
        conn.execute("ALTER TABLE leases ADD COLUMN quota_outcome_sha256 TEXT")
    if "quota_scope" not in cols:
        conn.execute("ALTER TABLE leases ADD COLUMN quota_scope TEXT")


def scope_for(br, pool, account):
    spec = br.provider(pool)
    if not isinstance(account, str) or not account:
        raise ValueError("quota_account_unqualified")
    rows = [a for a in spec.get("accounts", []) if a.get("name") == account]
    if len(rows) != 1:
        raise ValueError("quota_account_unqualified")
    # A declared scope may deliberately join different products/accounts that
    # consume one allowance. Model aliases always share the account default.
    explicit = rows[0].get("quota_scope", spec.get("quota_scope"))
    if explicit is not None:
        if not isinstance(explicit, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", explicit):
            raise ValueError("quota_scope_invalid")
        return "declared:" + explicit
    return br.provider_name(pool) + ":" + account


def cooldown(br, pool, account, conn=None):
    scope = scope_for(br, pool, account)
    own = conn is None
    conn = br._conn() if own else conn
    try:
        row = conn.execute("SELECT * FROM quota_cooldowns WHERE scope=?", (scope,)).fetchone()
        return dict(row) if row else None
    finally:
        if own:
            conn.close()


def account_cap(br, pool, acct, base):
    if base is None:
        return None
    try:
        row = cooldown(br, pool, acct.get("name"))
    except (ValueError, TypeError, KeyError):
        return None  # A malformed target account cannot close other pools.
    if row is None:
        return base
    if row["until_ts"] > br.now():
        return None
    return min(base, 1)  # half-open; admission_room enforces the shared scope.


def admission_room(br, conn, pool, acct):
    name = str(acct.get("name") or "")
    try:
        row = cooldown(br, pool, name, conn)
    except (ValueError, TypeError, KeyError):
        return False
    if row is None:
        return True
    if row["until_ts"] > br.now():
        return False
    wanted = row["scope"]
    # Other aliases/accounts/products in this allowance count too. The caller
    # holds the incumbent broker lock throughout this check and lease INSERT.
    for held in br._active_leases(conn):
        held_scope = held["quota_scope"]
        if held_scope is None:
            try:
                held_scope = scope_for(br, held["pool"], held["account"])
            except (ValueError, TypeError, KeyError):
                # Pre-upgrade leases have no captured allowance. An unknown
                # account in this provider withholds its probe; an unrelated
                # provider cannot wedge admission or status for every pool.
                if br.provider_name(held["pool"]) == br.provider_name(pool):
                    return False
                continue
        if held_scope == wanted:
            return False
    return True


def pool_blocked(br, pool):
    accounts = br.provider(pool).get("accounts") or []
    if not accounts:
        return False  # enrollment/ordinary policy remains its incumbent gate.
    def blocked(account):
        try:
            row = cooldown(br, pool, account.get("name"))
            return row is not None and row["until_ts"] > br.now()
        except (ValueError, TypeError, KeyError):
            return True
    return all(blocked(a) for a in accounts)


def snapshot_cooldown(br, pool, account, conn):
    try:
        return cooldown(br, pool, account, conn)
    except (ValueError, TypeError, KeyError):
        return {"state": "UNQUALIFIED", "reason": "quota_account_or_scope_invalid"}


def observe_locked(br, conn, lease_id, root_id, run_id, outcome_path, process_path):
    raw = provider_outcome.regular_bytes(Path(outcome_path), 16384)
    value = json.loads(raw)
    rows = provider_outcome.regular_bytes(Path(process_path), 1024 * 1024).splitlines()
    if not rows:
        raise ValueError("quota_process_receipt_missing")
    process = json.loads(rows[-1])
    provider_outcome.validate_receipt(value, process, run_id)
    lease = conn.execute("SELECT * FROM leases WHERE id=?", (lease_id,)).fetchone()
    if lease is None:
        raise ValueError("quota_original_lease_missing")
    for name, expected in {
        "lease_id": lease_id, "root_id": root_id, "account": lease["account"],
        "host": lease["host"], "model": lease["model"],
        "provider": br.provider_name(lease["pool"]),
    }.items():
        if not expected or value.get(name) != expected:
            raise ValueError("quota_original_lease_binding")
    if lease["orchestrator_id"] != root_id:
        raise ValueError("quota_original_root_binding")
    sha = provider_outcome.digest(raw)
    if lease["quota_outcome_sha256"]:
        if lease["quota_outcome_sha256"] != sha:
            raise ValueError("quota_terminal_observation_conflict")
        return {"kind": value["kind"], "recorded": True, "duplicate": True}
    stamp = value.get("observed_at")
    now = br.now()
    if (type(stamp) not in (int, float) or not math.isfinite(stamp)
            or not lease["granted_at"] <= stamp <= now + 5
            or now - stamp > 28800):
        raise ValueError("quota_observation_time_unqualified")
    scope = lease["quota_scope"] or scope_for(br, lease["pool"], lease["account"])
    prior_row = conn.execute("SELECT * FROM quota_cooldowns WHERE scope=?", (scope,)).fetchone()
    prior = dict(prior_row) if prior_row else None
    kind = value.get("kind")
    rc = value.get("command_rc")
    if kind in provider_outcome.CAPACITY and type(rc) is int and rc != 0:
        failures = min(20, prior["failures"] + 1) if prior else 1
        delay = min(3600, 60 * 2 ** min(failures - 1, 6))
        until, source = now + delay, "bounded_backoff"
        reset = value.get("reset_at")
        if (value.get("reset_source") == "provider_event"
                and type(reset) in (int, float) and math.isfinite(reset)
                and now < reset <= now + 32 * 86400):
            until, source = max(now + 1, reset), "provider_event"
        if prior:
            until = max(until, prior["until_ts"])
        conn.execute("""INSERT INTO quota_cooldowns
            (scope, observed_at, until_ts, failures, kind, source_run, reset_source)
            VALUES (?,?,?,?,?,?,?) ON CONFLICT(scope) DO UPDATE SET
            observed_at=excluded.observed_at, until_ts=excluded.until_ts,
            failures=excluded.failures, kind=excluded.kind,
            source_run=excluded.source_run, reset_source=excluded.reset_source""",
            (scope, now, until, failures, kind, run_id, source))
    elif (kind == "success" and rc == 0 and prior
          and lease["granted_at"] >= prior["observed_at"]
          and lease["granted_at"] >= prior["until_ts"]):
        # A late success from work started before exhaustion cannot reopen it.
        conn.execute("DELETE FROM quota_cooldowns WHERE scope=?", (scope,))
    conn.execute("UPDATE leases SET quota_outcome_sha256=? WHERE id=?", (sha, lease_id))
    conn.commit()
    return {"kind": kind, "recorded": True, "duplicate": False,
            "initial_rejection": value.get("initial_rejection") is True,
            "scope": scope}

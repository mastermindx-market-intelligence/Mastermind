"""Quota exclusions inside the existing lease broker database and lock.

No independent clock, queue, daemon, credentials, or capacity grants. Expiry
permits one existing broker lease to probe; only its qualified success clears
the exclusion. Every ordinary provider/account/economic gate still applies.

A qualified prospective Qwen adaptive-429 policy receipt is one bounded
exception to the generic CAPACITY branch: it records a distinct SOFT row in
the same quota_cooldowns table, keyed to the actual Bailian account, and only
lowers that exact account's ordinary concurrency cap for the policy window.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
import re

import provider_outcome

PRELEASE_SCHEMA = "mastermind.fabric_prelease_quota_refusal.v1"
PRELEASE_SOURCES = ("remote_sub.sh", "lease_broker.py", "quota_circuit.py")
PRELEASE_UNCERTAINTY_MARKERS = (
    "LEASE_PRESERVED effect_unknown=1", "REMOTE_EFFECT_UNKNOWN", "signal=effect_unknown",
    "CONTROLLER_PROCESS_UNPROVEN", "GO_EFFECT_UNKNOWN", "NATIVE_EFFECT_UNKNOWN",
    "EFFECT_UNKNOWN timeout ", "EFFECT_UNKNOWN_NONZERO", "GLM_CAPABILITY_TRANSFER_UNPROVEN",
)

# Qwen adaptive-429 soft mode. A wrapper-custody policy receipt never claims a
# provider HTTP status or usage and never enters the generic HARD branch: it
# records one SOFT row in the SAME quota_cooldowns table under a scope keyed to
# the ACTUAL account identity, separate from any declared shared HARD scope.
QWEN_FEEDBACK_FIELD = "qwen_policy_feedback"
QWEN_FEEDBACK_SCHEMA = "mastermind.qwen_adaptive429_feedback.v1"
QWEN_FEEDBACK_POLICY_SOURCE = "bailian_keys.adaptive_http_429"
QWEN_FEEDBACK_CLASSIFICATION = "429"
QWEN_FEEDBACK_DURATIONS = (120, 240, 480, 960, 1800)
QWEN_FEEDBACK_FIELDS = frozenset((
    "schema", "account", "classification_source", "classification",
    "policy_source", "observed_at", "until_ts", "duration_seconds",
    "soft_cap", "soft_cap_enabled"))
QWEN_WRAPPER_INFERENCE = "qwen_wrapper_inference"
QWEN_CODEX_ENUM = "codex_error_enum"
QWEN_FEEDBACK_MIN_CAP = 3
QWEN_FEEDBACK_MAX_CAP = 100000
QWEN_FEEDBACK_MAX_AGE = 28800
QWEN_FEEDBACK_SKEW = 5
SOFT_MODE = "SOFT"
SOFT_SCOPE_PREFIX = "bailian-adaptive429:"
SOFT_RESET_SOURCE = "local_adaptive_policy"


def capacity_blockade(br, conn, pool, preferred=None):
    """A locked capacity refusal, never an inference from missing accounts.

    Every relevant configured account must be otherwise enabled and excluded
    by an existing recorded capacity cooldown. Unknown, parked, malformed and
    ordinary resource states do not qualify this pre-lease handoff.
    """
    spec = br.provider(pool)
    if spec.get("enabled") is not True:
        return None
    accounts = spec.get("accounts")
    if not isinstance(accounts, list) or not accounts:
        return None
    names = [a.get("name") if isinstance(a, dict) else None for a in accounts]
    if (any(not isinstance(n, str) or not n for n in names)
            or len(set(names)) != len(names)):
        return None
    selected = [a for a in accounts if not preferred or a["name"] == preferred]
    if not selected:
        return None
    stamp = br.now()
    blocked = []
    for acct in selected:
        try:
            base = br._base_account_cap(pool, acct)
            row = cooldown(br, pool, acct["name"], conn)
            if (type(base) is not int or base <= 0 or row is None
                    or row.get("kind") not in provider_outcome.CAPACITY
                    or any(type(row.get(k)) not in (int, float)
                           or not math.isfinite(row[k]) for k in ("observed_at", "until_ts"))
                    or not row["observed_at"] <= stamp < row["until_ts"]
                    or not isinstance(row.get("source_run"), str)
                    or not provider_outcome.IDENT.fullmatch(row["source_run"])):
                return None
            blocked.append({"account": acct["name"], "scope": row["scope"],
                "kind": row["kind"], "observed_at": row["observed_at"],
                "until_ts": row["until_ts"], "source_run": row["source_run"]})
        except (ValueError, TypeError, KeyError):
            return None
    return {"observed_at": stamp, "accounts": blocked}


def write_prelease_refusal(path, *, run_id, root_id, parent_run_id,
                          pool, host, model, pid, request_sha256, launch_sha256,
                          controller_sha256, blockade):
    """Publish the exact acquire invocation's no-grant result after return.

    Only Broker.acquire's typed locked capacity branch calls this function.
    The caller's original subprocess return is a separate required witness.
    """
    for value in (run_id, root_id, parent_run_id):
        if not isinstance(value, str) or not provider_outcome.IDENT.fullmatch(value):
            raise ValueError("prelease_identity_invalid")
    for value in (request_sha256, launch_sha256, controller_sha256):
        if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
            raise ValueError("prelease_source_binding_invalid")
    if (type(pid) is not int or pid <= 0 or not isinstance(blockade, dict)
            or not all(isinstance(v, str) and v for v in (pool, host, model))):
        raise ValueError("prelease_invocation_invalid")
    here = Path(__file__).resolve().parent
    native_sources = {
        "remote_sub.sh": controller_sha256,
        "lease_broker.py": provider_outcome.digest(provider_outcome.regular_bytes(here / "lease_broker.py", 256 * 1024)),
        "quota_circuit.py": provider_outcome.digest(provider_outcome.regular_bytes(here / "quota_circuit.py", 256 * 1024)),
    }
    provider_outcome.write_new(Path(path), {
        "schema": PRELEASE_SCHEMA, "run_id": run_id, "root_id": root_id,
        "parent_run_id": parent_run_id, "pool": pool, "host": host, "model": model,
        "controller_pid": pid, "reason": "prelease_quota_cooldown", "rc": 75,
        "lease_granted": False, "task_cli_started": False,
        "request_sha256": request_sha256, "launch_sha256": launch_sha256,
        "native_sources": native_sources, "blockade": blockade,
    })


def validate_prelease_refusal(here, run, root, parent, *, packet_limit=8 * 1024 * 1024):
    """Read an original controller return; this cannot dispatch or resurrect.

    A source-bound broker refusal alone is insufficient: the adapter must have
    observed its exact one-shot controller return, after which that invocation
    cannot create a remote child. Missing or contradictory evidence fails closed.
    """
    if not all(isinstance(v, str) and provider_outcome.IDENT.fullmatch(v)
               for v in (run, root, parent)):
        raise ValueError("prelease_identity_invalid")
    directory = Path(here) / "state" / "remote_sub"
    def read(suffix, limit=32768):
        raw = provider_outcome.regular_bytes(directory / (run + suffix), limit)
        obj = json.loads(raw)
        if not isinstance(obj, dict):
            raise ValueError("prelease_artifact_invalid")
        return raw, obj
    request_raw, request = read(".request.json")
    launch_raw, launch = read(".request-launch.json")
    refusal_raw, refusal = read(".prelease-quota.json")
    returned_raw, returned = read(".request-return.json")
    schemas = ((request, "mastermind.fabric_request_artifact.v1"),
               (launch, "mastermind.fabric_request_launch.v1"),
               (refusal, PRELEASE_SCHEMA),
               (returned, "mastermind.fabric_request_return.v1"))
    for obj, schema in schemas:
        if (obj.get("schema") != schema or obj.get("run_id") != run
                or obj.get("root_id") != root or obj.get("parent_run_id") != parent):
            raise ValueError("prelease_artifact_identity")
    if (refusal.get("reason") != "prelease_quota_cooldown"
            or type(refusal.get("rc")) is not int or refusal["rc"] != 75
            or refusal.get("lease_granted") is not False
            or refusal.get("task_cli_started") is not False
            or type(refusal.get("controller_pid")) is not int or refusal["controller_pid"] <= 0
            or launch.get("state") != "LAUNCH_ATTEMPT_RESERVED"
            or launch.get("capacity_handoff") is not True
            or returned.get("state") != "NATIVE_CONTROLLER_RETURNED"
            or type(returned.get("controller_rc")) is not int or returned["controller_rc"] != 75
            or any(obj.get("request_sha256") != provider_outcome.digest(request_raw)
                   for obj in (launch, refusal, returned))
            or any(obj.get("launch_sha256") != provider_outcome.digest(launch_raw)
                   for obj in (refusal, returned))
            or returned.get("prelease_sha256") != provider_outcome.digest(refusal_raw)):
        raise ValueError("prelease_controller_return_unqualified")
    sources = launch.get("native_sources")
    if (not isinstance(sources, dict) or set(sources) != set(PRELEASE_SOURCES)
            or any(not isinstance(v, str) or re.fullmatch(r"[0-9a-f]{64}", v) is None
                   for v in sources.values())
            or refusal.get("native_sources") != sources):
        raise ValueError("prelease_source_changed")
    route = launch.get("route")
    if (not isinstance(route, dict)
            or any(refusal.get(k.lower()) != route.get(k) for k in ("POOL", "HOST", "MODEL"))):
        raise ValueError("prelease_route_changed")
    blockade = refusal.get("blockade")
    if (not isinstance(blockade, dict) or type(blockade.get("observed_at")) not in (int, float)
            or not math.isfinite(blockade["observed_at"])
            or not isinstance(blockade.get("accounts"), list) or not blockade["accounts"]):
        raise ValueError("prelease_capacity_evidence_invalid")
    names = set()
    for account in blockade["accounts"]:
        if (not isinstance(account, dict) or not isinstance(account.get("account"), str)
                or not account["account"] or account["account"] in names
                or account.get("kind") not in provider_outcome.CAPACITY
                or not isinstance(account.get("scope"), str) or not account["scope"]
                or not isinstance(account.get("source_run"), str)
                or not provider_outcome.IDENT.fullmatch(account["source_run"])
                or any(type(account.get(k)) not in (int, float) or not math.isfinite(account[k])
                       for k in ("observed_at", "until_ts"))
                or not account["observed_at"] <= blockade["observed_at"] < account["until_ts"]):
            raise ValueError("prelease_capacity_evidence_invalid")
        names.add(account["account"])
    log = provider_outcome.regular_bytes(directory / (run + ".log"), 8 * 1024 * 1024)
    if returned.get("log_sha256") != provider_outcome.digest(log):
        raise ValueError("prelease_controller_log_changed")
    text = log.decode("utf-8", errors="replace")
    if any(marker in text for marker in (*PRELEASE_UNCERTAINTY_MARKERS,
            "LEASE_OK pool=", "SUPPORT_VERSION_READY ", "LAUNCH stdout=", "REMOTE_DONE rc=", "DONE rc=")):
        raise ValueError("prelease_contradictory_execution_evidence")
    artifacts = [directory / (run + suffix) for suffix in (
        ".process.jsonl", ".provider.json", ".provider-observed.json", ".native-terminal.json",
        ".support.json", ".usage.json", ".go-run.json", ".session-created.json", ".session-retained.json")]
    artifacts.append(Path(here) / "lanes" / (run + ".remote.stdout"))
    for artifact in artifacts:
        if artifact.exists() or artifact.is_symlink():
            raise ValueError("prelease_contradictory_execution_artifact")
    if (request.get("packet") != run + ".request.packet"
            or launch.get("packet_sha256") != request.get("packet_sha256")
            or provider_outcome.digest(provider_outcome.regular_bytes(
                directory / (run + ".request.packet"), packet_limit)) != request.get("packet_sha256")):
        raise ValueError("prelease_packet_changed")
    return {"packet_sha256": request["packet_sha256"],
            "prelease_sha256": provider_outcome.digest(refusal_raw),
            "request_return_sha256": provider_outcome.digest(returned_raw),
            "kind": "prelease_quota_cooldown"}


def init_schema(conn):
    # Broker construction may race on the first upgraded invocation. Serialize
    # introspection and all ALTERs in its existing database transaction.
    if not conn.in_transaction:
        conn.execute("BEGIN IMMEDIATE")
    conn.execute("""CREATE TABLE IF NOT EXISTS quota_cooldowns (
        scope TEXT PRIMARY KEY, observed_at REAL NOT NULL,
        until_ts REAL NOT NULL, failures INTEGER NOT NULL,
        kind TEXT NOT NULL, source_run TEXT NOT NULL,
        reset_source TEXT NOT NULL, mode TEXT NOT NULL DEFAULT 'HARD',
        soft_cap INTEGER)""")
    cols = {r[1] for r in conn.execute("PRAGMA table_info(quota_cooldowns)")}
    # Idempotent migration; preexisting rows stay generic HARD cooldowns.
    if "mode" not in cols:
        conn.execute("ALTER TABLE quota_cooldowns ADD COLUMN mode TEXT NOT NULL DEFAULT 'HARD'")
    if "soft_cap" not in cols:
        conn.execute("ALTER TABLE quota_cooldowns ADD COLUMN soft_cap INTEGER")
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


def soft_cooldown(br, pool, account, conn=None):
    """The exact-account adaptive-429 SOFT row, or None.

    The scope key carries the actual account identity, never a declared shared
    allowance scope: pool aliases resolving to the same account see the same
    row; a different account never does. A soft row can never close or
    destabilize an account, so every unqualified lookup is just "no soft row".
    """
    try:
        if br.provider_name(pool) != "bailian":
            return None
    except (ValueError, TypeError, KeyError):
        return None
    if not isinstance(account, str) or not account:
        return None
    own = conn is None
    conn = br._conn() if own else conn
    try:
        row = conn.execute("SELECT * FROM quota_cooldowns WHERE scope=?",
                           (SOFT_SCOPE_PREFIX + account,)).fetchone()
        if row is None or row["mode"] != SOFT_MODE:
            return None
        return dict(row)
    finally:
        if own:
            conn.close()


def _qwen_int(value):
    return type(value) is int  # exact policy-clock integers; bool-as-int refuses


def validate_qwen_feedback(value, feedback, lease, provider, now):
    """Closed-shape gate for one adaptive-429 policy receipt.

    Raises before any database mutation. The wrapper's custody never claims a
    provider HTTP status or usage: api_status and reset_at/reset_source must
    stay unset, the classification stays "429", and the envelope kind must
    match the explicit classification source (wrapper inference stays
    kind=unknown; a typed CLI enum stays kind=rate_limit and is still not
    provider HTTP proof).
    """
    if provider != "bailian":
        raise ValueError("qwen_feedback_provider_unqualified")
    if (not isinstance(feedback, dict) or set(feedback) != QWEN_FEEDBACK_FIELDS
            or feedback["schema"] != QWEN_FEEDBACK_SCHEMA
            or feedback["policy_source"] != QWEN_FEEDBACK_POLICY_SOURCE
            or feedback["classification"] != QWEN_FEEDBACK_CLASSIFICATION):
        raise ValueError("qwen_feedback_shape_invalid")
    source = feedback["classification_source"]
    if source not in (QWEN_WRAPPER_INFERENCE, QWEN_CODEX_ENUM):
        raise ValueError("qwen_feedback_classification_invalid")
    kind = value.get("kind")
    rc = value.get("command_rc")
    if (value.get("api_status") is not None or value.get("reset_at") is not None
            or value.get("reset_source") is not None
            or type(rc) is not int or rc == 0
            or (source == QWEN_WRAPPER_INFERENCE
                and (kind != "unknown" or value.get("initial_rejection") is not False))
            or (source == QWEN_CODEX_ENUM and kind != "rate_limit")):
        raise ValueError("qwen_feedback_envelope_contradiction")
    if feedback["account"] != lease["account"]:
        raise ValueError("qwen_feedback_account_binding")
    observed, until, duration, cap = (feedback[name] for name in
        ("observed_at", "until_ts", "duration_seconds", "soft_cap"))
    if not all(_qwen_int(v) for v in (observed, until, duration, cap)):
        raise ValueError("qwen_feedback_shape_invalid")
    if (duration not in QWEN_FEEDBACK_DURATIONS or until != observed + duration
            or not QWEN_FEEDBACK_MIN_CAP <= cap <= QWEN_FEEDBACK_MAX_CAP
            or type(feedback["soft_cap_enabled"]) is not bool):
        raise ValueError("qwen_feedback_shape_invalid")
    stamp = value["observed_at"]  # already time-qualified above
    if (observed < lease["granted_at"] - 1  # integer policy clock, rounding <=1s
            or abs(observed - stamp) > QWEN_FEEDBACK_SKEW
            or observed > now + QWEN_FEEDBACK_SKEW
            or now - observed > QWEN_FEEDBACK_MAX_AGE):
        raise ValueError("qwen_feedback_time_unqualified")
    return {"account": feedback["account"], "observed_at": observed,
            "until_ts": until, "soft_cap": cap,
            "soft_cap_enabled": feedback["soft_cap_enabled"],
            "classification_source": source, "kind": kind}


def account_cap(br, pool, acct, base):
    if base is None:
        return None
    name = acct.get("name")
    try:
        row = cooldown(br, pool, name)
    except (ValueError, TypeError, KeyError):
        return None  # A malformed target account cannot close other pools.
    if row is not None and row["until_ts"] > br.now():
        return None
    cap = base if row is None else min(base, 1)  # half-open; admission_room enforces the shared scope.
    try:
        soft = soft_cooldown(br, pool, name)
    except (ValueError, TypeError, KeyError):
        soft = None  # An unqualified soft row never destabilizes admission.
    if (soft is not None and soft["until_ts"] > br.now()
            and type(soft.get("soft_cap")) is int
            and soft["soft_cap"] >= QWEN_FEEDBACK_MIN_CAP):
        # An active SOFT row only lowers this exact account's ordinary cap; an
        # expired one returns the ordinary base without the half-open throttle.
        # Rows exist only for policy-enabled observations: a soft_cap_enabled
        # false receipt stays purely diagnostic and records no row at all.
        cap = min(cap, soft["soft_cap"])
    return cap


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
        row = cooldown(br, pool, account, conn)
    except (ValueError, TypeError, KeyError):
        return {"state": "UNQUALIFIED", "reason": "quota_account_or_scope_invalid"}
    try:
        soft = soft_cooldown(br, pool, account, conn)
    except (ValueError, TypeError, KeyError):
        soft = None
    if soft is not None:
        row = dict(row) if row else {}
        row["soft"] = {"mode": soft["mode"], "observed_at": soft["observed_at"],
                       "until_ts": soft["until_ts"], "soft_cap": soft.get("soft_cap"),
                       "reset_source": soft.get("reset_source")}
    return row


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
    feedback = value.get(QWEN_FEEDBACK_FIELD)
    if QWEN_FEEDBACK_FIELD in value:
        # A qualified adaptive-429 policy observation takes the SOFT branch and
        # never the generic HARD CAPACITY branch, not even for a typed enum
        # kind. It never rewrites the declared HARD scope row above: a stronger
        # preexisting hold is preserved while this lease still binds its exact
        # terminal observation. Every refusal above happened before mutation.
        soft = validate_qwen_feedback(value, feedback, lease,
                                      br.provider_name(lease["pool"]), now)
        applied = None
        if soft["soft_cap_enabled"] and soft["until_ts"] > now:
            # An already-expired policy window records no cooldown at all.
            soft_scope = SOFT_SCOPE_PREFIX + soft["account"]
            row = conn.execute("SELECT * FROM quota_cooldowns WHERE scope=?",
                               (soft_scope,)).fetchone()
            prior_soft = dict(row) if row else None
            if prior_soft is not None and prior_soft.get("mode") != SOFT_MODE:
                raise ValueError("qwen_feedback_scope_collision")
            until, cap = soft["until_ts"], soft["soft_cap"]
            failures = 1 if prior_soft is None else min(20, prior_soft["failures"] + 1)
            if (prior_soft is not None and prior_soft["until_ts"] > now
                    and type(prior_soft.get("soft_cap")) is int
                    and prior_soft["soft_cap"] >= QWEN_FEEDBACK_MIN_CAP):
                # A later distinct observation merges conservatively: it may
                # keep the longer expiry and the lower cap; it never invents
                # policy or shortens an active window.
                until, cap = max(until, prior_soft["until_ts"]), min(cap, prior_soft["soft_cap"])
            conn.execute("""INSERT INTO quota_cooldowns
                (scope, observed_at, until_ts, failures, kind, source_run, reset_source, mode, soft_cap)
                VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(scope) DO UPDATE SET
                observed_at=excluded.observed_at, until_ts=excluded.until_ts,
                failures=excluded.failures, kind=excluded.kind,
                source_run=excluded.source_run, reset_source=excluded.reset_source,
                mode=excluded.mode, soft_cap=excluded.soft_cap""",
                (soft_scope, soft["observed_at"], until, failures, soft["kind"],
                 run_id, SOFT_RESET_SOURCE, SOFT_MODE, cap))
            applied = {"scope": soft_scope, "observed_at": soft["observed_at"],
                       "until_ts": until, "soft_cap": cap}
        conn.execute("UPDATE leases SET quota_outcome_sha256=? WHERE id=?", (sha, lease_id))
        conn.commit()
        return {"kind": kind, "recorded": True, "duplicate": False,
                "initial_rejection": value.get("initial_rejection") is True,
                "scope": scope, "soft": applied}
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

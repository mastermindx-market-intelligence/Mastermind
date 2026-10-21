#!/usr/bin/env python3
"""pool_ledger.py — append-only JSONL ledger for agent pool runs.

Schema: {"ts":<unix_epoch>,"pool":<name>,"key":<bailian_key_name or "-">,
         "window_id":<window>,"task_class":<class>,"rc":<int>,
         "tokens":<int|null>,"signal":<"402"|"429"|"ok"|"other"|"lease_lost">,
         "reason":<short typed reason|null>,
         "run_id":<id>,
         "accepted_by":<"deterministic"|"reviewer"|"none"|null>,
         "review_rejected":<bool>,"scope_violation":<bool>,
         "retries":<int>,"escalated":<bool>,"wall_s":<float|null>,
         "model":<name|null>,
         "input_tokens":<int|null>,"cached_tokens":<int|null>,
         "output_tokens":<int|null>            # R26 glm metering
         "credits":<float|null>,"credit_rate":<float|null>}   # glm rows only

Writes append under the existing ledger lock. Legacy calls are best-effort;
strict publication and outcome calls require durable acknowledgement and fail
closed when it cannot be confirmed. A failure does not imply no write occurred.
"""
from __future__ import annotations

import fcntl
import json
import math
import os
import re
import statistics
import stat
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
LEDGER_DIR = os.path.join(HERE, "..", "orch", "fabric")
# POOL_LEDGER_PATH (absolute path) redirects the ledger — tests use it so
# subprocess refusals never append to the production pool ledger. Default
# (unset or empty) stays orch/fabric/ledger.jsonl.
LEDGER_PATH = os.environ.get("POOL_LEDGER_PATH") or os.path.join(LEDGER_DIR, "ledger.jsonl")
POOLS_YAML = os.path.join(LEDGER_DIR, "pools.yaml")
SLOT_ROOT = os.path.join(HERE, "slots")

ACCEPTED_BY_OK = frozenset({"deterministic", "reviewer"})
ACCEPTED_BY_ALL = frozenset({"deterministic", "reviewer", "none"})
STRICT_OUTCOME_SOURCE_FIELDS = (
    "pool", "key", "window_id", "task_class", "job_class", "model",
    "tokens", "wall_s", "input_tokens", "cached_tokens", "output_tokens",
    "credits", "credit_rate", "usage_source", "credit_estimate_source",
)


def _load_usage() -> dict:
    usage_path = os.path.join(HERE, "bailian_usage.json")
    if os.path.exists(usage_path):
        try:
            with open(usage_path, encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            pass
    return {}


def _bailian_window_id(name: str) -> str:
    """Return window_id for a bailian key: 'offpeak', 'onpeak', or 'weekly_<name>'."""
    usage = _load_usage()
    keys = usage.get("keys", {})
    if name in keys:
        entry = keys[name]
        if entry.get("parked"):
            return f"parked_{entry.get('resets_at', 'unknown')}"
        pct = entry.get("pct_7d", 0)
        if pct >= 95:
            return f"high_{pct}"
    # Check off-peak status via bailian_keys
    try:
        sys.path.insert(0, HERE)
        import bailian_keys
        if bailian_keys.is_offpeak():
            return "offpeak"
        return "onpeak"
    except Exception:
        return "unknown"


def _grok_window_id() -> str:
    """Return window_id for grok: 'exhausted' if marker file present."""
    marker = os.path.join(HERE, "GROK_EXHAUSTED")
    if os.path.exists(marker):
        return "exhausted"
    return "weekly"


def _pool_window_id(pool: str, key: str = "-") -> str:
    if pool == "bailian":
        return _bailian_window_id(key)
    if pool == "grok":
        return _grok_window_id()
    if pool == "minimax":
        return "weekly"
    if pool == "cursor":
        return "monthly"
    if pool == "claude":
        return "5h"
    return "unknown"


def _strict_json(text: str) -> dict:
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result
    def constant(_value):
        raise ValueError("non-finite JSON value")
    value = json.loads(text, object_pairs_hook=pairs, parse_constant=constant)
    if not isinstance(value, dict):
        raise ValueError("invalid ledger row")
    # JSON exponent overflow (1e999) is not a parse_constant event.
    json.dumps(value, allow_nan=False)
    return value


def _outcomes_conflict(record: dict, outcomes: list[dict]) -> bool:
    # Review outcomes may predate graph metadata. Missing optional correlation
    # never overwrites the fully bound terminal row, while any explicit conflict
    # or uncertainty in execution facts invalidates publication/readback.
    for row in outcomes:
        for key in ("rc", "signal", "root_id", "parent_run_id"):
            if key in ("root_id", "parent_run_id") and key not in row:
                continue
            if (json.dumps(row.get(key), allow_nan=False)
                    != json.dumps(record.get(key), allow_nan=False)):
                return True
    return False


def _validate_outcome_source(terminal: dict, outcomes: list[dict]) -> None:
    """Strict acceptance binds the original execution, not outcome-overlaid facts."""
    if "kind" in terminal and terminal["kind"] != "terminal_publication":
        raise ValueError("unrecognized terminal record kind")
    if type(terminal.get("ts")) is not int:
        raise ValueError("terminal timestamp missing or malformed")
    for field in ("run_id", "root_id"):
        value = terminal.get(field)
        if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", value):
            raise ValueError("terminal operation/root identity missing or malformed")
    for field in ("pool", "key", "window_id", "task_class"):
        if not isinstance(terminal.get(field), str) or not terminal[field]:
            raise ValueError("terminal execution identity missing or malformed")
    for field in ("model", "job_class", "parent_run_id"):
        if terminal.get(field) is not None and not isinstance(terminal[field], str):
            raise ValueError("terminal optional identity malformed")
    parent = terminal.get("parent_run_id")
    if parent is not None and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", parent):
        raise ValueError("terminal parent identity malformed")
    if _outcomes_conflict(terminal, outcomes):
        raise ValueError("conflicting or uncertain later outcome")
    # Historical outcomes may omit metadata. Explicit changes are uncertainty,
    # even if a still later outcome restores the original value.
    for row in outcomes:
        for key in STRICT_OUTCOME_SOURCE_FIELDS:
            if key in row and json.dumps(row[key], allow_nan=False) != json.dumps(terminal.get(key), allow_nan=False):
                raise ValueError("outcome changed original execution facts")


def _strict_open(path: str, flags: int, mode: str):
    fd = os.open(path, flags | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    try:
        info = os.fstat(fd)
        retained = os.lstat(path)
        if (not stat.S_ISREG(info.st_mode) or not stat.S_ISREG(retained.st_mode)
                or info.st_uid != os.getuid() or info.st_mode & 0o022
                or (info.st_dev, info.st_ino) != (retained.st_dev, retained.st_ino)):
            raise ValueError("unsafe ledger or lock file")
        return os.fdopen(fd, mode, encoding="utf-8")
    except BaseException:
        os.close(fd)
        raise


def _strict_identity(handle, path: str) -> None:
    info = os.fstat(handle.fileno())
    retained = os.lstat(path)
    if (not stat.S_ISREG(retained.st_mode)
            or (info.st_dev, info.st_ino) != (retained.st_dev, retained.st_ino)):
        raise ValueError("ledger or lock replaced")



ACCEPTANCE_MAX_BYTES = 64 * 1024 * 1024
ACCEPTANCE_MAX_LINE_BYTES = 65536


def read_acceptance(run_id: str, *, expected_rc: int, expected_signal: str) -> dict:
    """Read strict rc0/ok acceptance; failures never become accepted outcomes."""
    return _read_terminal_projection(run_id, expected_rc=expected_rc,
                                     expected_signal=expected_signal, acceptance_only=True)


def read_execution_identity(run_id: str, *, expected_rc: int, expected_signal: str) -> dict:
    """Read retained terminal root/parent identity without adjudication or retry rights.

    Reuses the same bounded immutable-source/conflict checks as acceptance. This
    is local ledger provenance, not authenticated native parent or process proof.
    """
    return _read_terminal_projection(run_id, expected_rc=expected_rc,
                                     expected_signal=expected_signal, acceptance_only=False)


def _read_terminal_projection(run_id: str, *, expected_rc: int, expected_signal: str,
                              acceptance_only: bool) -> dict:
    """Observe acceptance from the owner's stable ledger snapshot, without effects.

    This is local provenance, not authenticated parent identity or a result hash
    attestation. The existing LEDGER_PATH configuration remains authoritative.
    Unknown evidence is distinct from a validated absence of parent acceptance.
    """
    unknown = {"accepted": None, "accepted_by": None,
               "acceptance_state": "UNVERIFIED", "acceptance_reason": "LEDGER_UNVERIFIED",
               "root_id": None, "parent_run_id": None}
    if not acceptance_only:
        unknown = {"root_id": None, "parent_run_id": None, "lineage_state": "UNVERIFIED"}
    def identity(info):
        return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns,
                info.st_ctime_ns, info.st_mode, info.st_uid)
    try:
        if (not isinstance(run_id, str)
                or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", run_id)
                or type(expected_rc) is not int or not 0 <= expected_rc <= 255
                or type(expected_signal) is not str
                or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", expected_signal)
                or expected_signal == "effect_unknown"
                or acceptance_only and (expected_rc != 0 or expected_signal != "ok")):
            raise ValueError("ineligible execution")
        # O_RDONLY never creates a ledger or its lock. _strict_open rejects
        # symlinks, special files, wrong ownership and unsafe write permissions.
        with _strict_open(LEDGER_PATH, os.O_RDONLY, "r") as handle:
            before = os.fstat(handle.fileno())
            if before.st_size > ACCEPTANCE_MAX_BYTES:
                raise ValueError("ledger exceeds bound")
            data = handle.buffer.read(ACCEPTANCE_MAX_BYTES + 1)
            if (len(data) != before.st_size or len(data) > ACCEPTANCE_MAX_BYTES
                    or (data and not data.endswith(b"\n"))):
                raise ValueError("incomplete ledger snapshot")
            matching = []
            for line in data.splitlines():
                if len(line) > ACCEPTANCE_MAX_LINE_BYTES:
                    raise ValueError("ledger row exceeds bound")
                if not line.strip():
                    continue
                row = _strict_json(line.decode("utf-8"))
                if row.get("run_id") == run_id:
                    matching.append(row)
            terminals = [r for r in matching if r.get("kind") != "outcome"]
            outcomes = [r for r in matching if r.get("kind") == "outcome"]
            if len(terminals) != 1 or matching[0] is not terminals[0]:
                raise ValueError("orphan, ambiguous or out-of-order terminal")
            terminal = terminals[0]
            _validate_outcome_source(terminal, outcomes)
            if (type(terminal.get("rc")) is not int or terminal["rc"] != expected_rc
                    or terminal.get("signal") != expected_signal):
                raise ValueError("execution facts disagree")
            for row in matching:
                role = row.get("accepted_by")
                if role is not None and (not isinstance(role, str) or role not in ACCEPTED_BY_ALL):
                    raise ValueError("malformed acceptance role")
                if any(row.get(k) is not None and type(row[k]) is not bool
                       for k in ("review_rejected", "scope_violation")):
                    raise ValueError("malformed outcome flag")
            for row in outcomes:
                if type(row.get("ts")) is not int or "accepted_by" not in row:
                    raise ValueError("incomplete outcome")
            # Validate original facts before folding. Append order is the owner
            # contract; outcome timestamps cannot reorder revocation/acceptance.
            current = merge_jobs(matching)[0]
            role = current.get("accepted_by") if outcomes else None
            accepted = bool(outcomes and role in ACCEPTED_BY_OK
                            and not current.get("review_rejected")
                            and not current.get("scope_violation"))
            retained = os.lstat(LEDGER_PATH)
            if (not stat.S_ISREG(retained.st_mode)
                    or identity(os.fstat(handle.fileno())) != identity(before)
                    or identity(retained) != identity(before)):
                raise ValueError("ledger changed during projection")
            if not acceptance_only:
                return {"root_id": terminal["root_id"],
                        "parent_run_id": terminal.get("parent_run_id"),
                        "lineage_state": "VERIFIED_TERMINAL"}
            return {"accepted": accepted, "accepted_by": role,
                    "acceptance_state": "ACCEPTED" if accepted else "NOT_ACCEPTED",
                    "acceptance_reason": ("VALIDATED_OUTCOME" if accepted else
                                          "OUTCOME_NOT_ACCEPTED" if outcomes else "NO_OUTCOME"),
                    "root_id": terminal["root_id"], "parent_run_id": terminal.get("parent_run_id")}
    except FileNotFoundError:
        return {**unknown, "acceptance_reason": "LEDGER_UNAVAILABLE"} if acceptance_only else unknown
    except (OSError, ValueError, TypeError, RecursionError):
        return unknown


def _write_record(record: dict, *, durable: bool = False, outcome: bool = False) -> None:
    """Append through the existing ledger lock; strict terminal writes reconcile.

    Strict mode makes publication and caller-adjudicated outcomes durable and
    idempotent. It cannot execute, settle effects, manufacture missing evidence,
    or adjudicate a worker result on the caller's behalf.
    """
    os.makedirs(LEDGER_DIR, exist_ok=True)
    lock_path = LEDGER_PATH + ".lock"
    if outcome and not durable:
        raise ValueError("outcome acknowledgement requires durable write")
    lock_handle = (_strict_open(lock_path, os.O_RDWR | os.O_CREAT, "r+")
                   if durable else open(lock_path, "w"))
    with lock_handle as lock_fh:
        fcntl.flock(lock_fh.fileno(), fcntl.LOCK_EX)
        try:
            if durable:
                _strict_identity(lock_fh, lock_path)
            ledger_handle = (_strict_open(LEDGER_PATH, os.O_RDWR | os.O_CREAT | os.O_APPEND, "a+")
                             if durable else open(LEDGER_PATH, "a", encoding="utf-8"))
            with ledger_handle as fh:
                if durable:
                    if os.fstat(fh.fileno()).st_size > 64 * 1024 * 1024:
                        raise ValueError("ledger exceeds strict reconciliation bound")
                    fh.seek(0)
                    matching = []
                    outcomes = []
                    run_records = []
                    while True:
                        retained = fh.readline(65537)
                        if not retained:
                            break
                        if len(retained) > 65536 or not retained.endswith("\n"):
                            raise ValueError("incomplete or oversized ledger row")
                        observed = _strict_json(retained)
                        if not isinstance(observed, dict):
                            raise ValueError("invalid ledger row")
                        guard = record.get("terminal_reconciliation", {}).get("legacy_collision_window")
                        if (guard and str(observed.get("run_id", "")).startswith("run-")
                                and observed.get("pool") == guard["pool"]
                                and guard["start_ts"] <= observed.get("ts", 0) <= guard["end_ts"]):
                            raise ValueError("ambiguous legacy publication identity")
                        if observed.get("run_id") == record.get("run_id"):
                            run_records.append(observed)
                            if observed.get("kind") == "outcome":
                                outcomes.append(observed)
                            else:
                                matching.append(observed)
                    # Timestamp is observation time; every substantive fact must
                    # match. A conflict is never authority to rewrite history.
                    def facts(row):
                        return json.dumps({k: v for k, v in row.items() if k != "ts"}, sort_keys=True, allow_nan=False)
                    if outcome:
                        if len(matching) != 1:
                            raise ValueError("outcome requires one unconflicted terminal publication")
                        _validate_outcome_source(matching[0], outcomes)
                        base = merge_jobs(run_records)[0]
                        if (record.get("accepted_by") in ACCEPTED_BY_OK
                                and (type(base.get("rc")) is not int or base["rc"] != 0
                                     or base.get("signal") != "ok")):
                            raise ValueError("positive outcome requires successful terminal publication")
                        # Build under the existing lock from the full bounded
                        # source snapshot, never an earlier/truncated recent view.
                        record = _outcome_record(base=base, **record)
                        # This path acknowledges an adjudication; it is not a
                        # measurement correction/backfill API. Missing optional
                        # historical fields may inherit, but explicit changes
                        # require a separately qualified owner reconciliation.
                        for key in STRICT_OUTCOME_SOURCE_FIELDS:
                            if (json.dumps(record.get(key), allow_nan=False)
                                    != json.dumps(matching[0].get(key), allow_nan=False)):
                                raise ValueError("strict outcome cannot change source facts")
                        if _outcomes_conflict(matching[0], [record]):
                            raise ValueError("outcome conflicts with terminal execution")
                        publish = (run_records[-1].get("kind") != "outcome"
                                   or facts(run_records[-1]) != facts(record))
                    else:
                        expected = facts(record)
                        if outcomes and not matching:
                            raise ValueError("orphan outcome blocks terminal publication")
                        if _outcomes_conflict(record, outcomes):
                            raise ValueError("conflicting or uncertain later outcome")
                        if len(matching) > 1 or (matching and facts(matching[0]) != expected):
                            raise ValueError("conflicting terminal publication")
                        publish = not matching
                    _strict_identity(lock_fh, lock_path)
                    _strict_identity(fh, LEDGER_PATH)
                    line = json.dumps(record, separators=(",", ":"), allow_nan=False) + "\n"
                    if publish:
                        offset = fh.tell()
                        fh.write(line)
                    fh.flush()
                    os.fsync(fh.fileno())
                    if publish:
                        fh.seek(offset)
                        if fh.read(len(line) + 1) != line:
                            raise ValueError("ledger append readback mismatch")
                    # A newly created ledger also needs its directory entry
                    # persisted before the controller may acknowledge DONE.
                    directory = os.open(os.path.dirname(os.path.abspath(LEDGER_PATH)), os.O_RDONLY)
                    try:
                        os.fsync(directory)
                    finally:
                        os.close(directory)
                    _strict_identity(lock_fh, lock_path)
                    _strict_identity(fh, LEDGER_PATH)
                else:
                    line = json.dumps(record, separators=(",", ":")) + "\n"
                    fh.write(line)
        finally:
            fcntl.flock(lock_fh.fileno(), fcntl.LOCK_UN)


def _glm_credits(model: Optional[str], input_tokens: Optional[int],
                 cached_tokens: Optional[int],
                 output_tokens: Optional[int]) -> tuple:
    """Credits + credit_rate for a glm run via glm_keys (R26).

    Returns (None, None) when glm_keys or the config is unavailable — the
    record is still appended, just unmetered.
    """
    try:
        if HERE not in sys.path:
            sys.path.insert(0, HERE)
        import glm_keys
        mdl = model or ""
        if not mdl:
            try:
                mdl = glm_keys.model()
            except Exception:
                mdl = "glm-5.3"  # conservative default (highest multipliers)
        credits = glm_keys.credits_for(
            mdl, input_tokens or 0, cached_tokens or 0, output_tokens or 0
        )
        return float(credits), float(glm_keys.credit_rate())
    except Exception:
        return None, None


def append(
    pool: str,
    key: str = "-",
    window_id: Optional[str] = None,
    task_class: str = "unknown",
    job_class: Optional[str] = None,
    rc: int = 0,
    tokens: Optional[int] = None,
    signal: str = "ok",
    run_id: Optional[str] = None,
    accepted_by: Optional[str] = None,
    review_rejected: Optional[bool] = None,
    scope_violation: Optional[bool] = None,
    retries: Optional[int] = None,
    escalated: Optional[bool] = None,
    wall_s: Optional[float] = None,
    model: Optional[str] = None,
    input_tokens: Optional[int] = None,
    cached_tokens: Optional[int] = None,
    output_tokens: Optional[int] = None,
    reason: Optional[str] = None,
    root_id: Optional[str] = None,
    parent_run_id: Optional[str] = None,
    escalation_reason: Optional[str] = None,
    usage_source: Optional[str] = None,
    strict: bool = False,
    reconciliation: Optional[dict] = None,
) -> bool:
    """Append one record; strict callers require durable publication success."""
    # Observational correlation inherited by older local launchers. Explicit
    # arguments, including empty strings, retain precedence; no identity invented.
    if root_id is None:
        root_id = os.environ.get("POOL_ORCHESTRATOR_ID", "").strip() or None
    if parent_run_id is None:
        parent_run_id = os.environ.get("POOL_PARENT_RUN_ID", "").strip() or None
    if job_class is None:
        job_class = os.environ.get("POOL_TASK_CLASS", "").strip() or None
    if escalation_reason is None:
        escalation_reason = os.environ.get("POOL_ESCALATION_REASON", "").strip() or None
    if window_id is None:
        window_id = _pool_window_id(pool, key)
    if not run_id:
        run_id = f"run-{int(time.time())}-{os.getpid()}"

    credits: Optional[float] = None
    credit_rate: Optional[float] = None
    if pool == "glm" and any(
        t is not None for t in (input_tokens, cached_tokens, output_tokens)
    ):
        credits, credit_rate = _glm_credits(
            model, input_tokens, cached_tokens, output_tokens
        )

    record: Dict[str, Any] = {
        "ts": int(time.time()),
        "pool": pool,
        "key": key,
        "window_id": window_id,
        "task_class": task_class,
        # job_class (R22, 2026-09-20): the REAL task class -- execute / review /
        # heal / audit / census. task_class keeps carrying the engine or variant
        # name because GLM credit accounting and pick's model+cap selection key
        # on it; overloading it would silently break those. Readers match EITHER
        # (see _class_matches). The key is omitted entirely when unset, so
        # `grep '"job_class": "' ledger.jsonl` is a truthful positive control for
        # "an instrumented writer actually ran" (MINOR 8).
        "rc": rc,
        "tokens": tokens,
        "signal": signal,
        "reason": reason,
        "escalation_reason": escalation_reason,
        "run_id": run_id,
        "accepted_by": accepted_by,
        "review_rejected": review_rejected,
        "scope_violation": scope_violation,
        "retries": retries,
        "escalated": escalated,
        "wall_s": wall_s,
        "model": model,
        "input_tokens": input_tokens,
        "cached_tokens": cached_tokens,
        "output_tokens": output_tokens,
        "credits": credits,
        "credit_rate": credit_rate,
    }
    if credits is not None:
        record["credit_estimate_source"] = "configured_model_credit_rates"
    if usage_source is not None:
        record["usage_source"] = usage_source
    if job_class is not None and str(job_class).strip():
        record["job_class"] = str(job_class).strip()
    # Caller-supplied graph correlation is observational, never admission.
    for name, value in (("root_id", root_id), ("parent_run_id", parent_run_id)):
        if value is not None and str(value).strip():
            record[name] = str(value).strip()

    if reconciliation is not None:
        if not strict:
            raise ValueError("reconciliation requires strict publication")
        record["kind"] = "terminal_publication"
        record["terminal_reconciliation"] = reconciliation
    try:
        if strict:
            _write_record(record, durable=True)
        else:
            _write_record(record)
        return True
    except Exception as exc:
        if strict:
            print(f"LEDGER_WRITE_FAILED: {exc}", file=sys.stderr)
            return False
        print(
            f"pool_ledger: append failed (best-effort, continuing): {exc}",
            file=sys.stderr,
        )


def _outcome_record(
    run_id: str,
    accepted_by: str = "none",
    review_rejected: bool = False,
    scope_violation: bool = False,
    retries: int = 0,
    escalated: bool = False,
    tokens: Optional[int] = None,
    wall_s: Optional[float] = None,
    pool: Optional[str] = None,
    task_class: Optional[str] = None,
    job_class: Optional[str] = None,
    model: Optional[str] = None,
    *, base: Dict[str, Any],
) -> dict:
    record: Dict[str, Any] = {
        "ts": int(time.time()),
        "kind": "outcome",
        "run_id": run_id,
        "pool": pool or base.get("pool") or "-",
        "key": base.get("key") or "-",
        "window_id": base.get("window_id") or "unknown",
        "task_class": task_class or base.get("task_class") or "unknown",
        "rc": base.get("rc", 0),
        "tokens": tokens if tokens is not None else base.get("tokens"),
        "signal": base.get("signal") or "ok",
        "model": model or base.get("model"),
        "accepted_by": accepted_by,
        "review_rejected": bool(review_rejected),
        "scope_violation": bool(scope_violation),
        "retries": int(retries),
        "escalated": bool(escalated),
        "wall_s": wall_s if wall_s is not None else base.get("wall_s"),
    }
    # Outcome joins preserve measured fields exactly. Current process environment
    # cannot re-parent an earlier run, and absent measurements stay absent.
    for field in (
        "root_id", "parent_run_id", "input_tokens", "cached_tokens", "output_tokens",
        "credits", "credit_rate", "usage_source", "credit_estimate_source",
        "escalation_reason",
    ):
        if field in base:
            record[field] = base[field]
    _jc = job_class or base.get("job_class")
    if _jc is not None and str(_jc).strip():
        record["job_class"] = str(_jc).strip()
    return record


def record_outcome(
    run_id: str, accepted_by: str = "none", review_rejected: bool = False,
    scope_violation: bool = False, retries: int = 0, escalated: bool = False,
    tokens: Optional[int] = None, wall_s: Optional[float] = None,
    pool: Optional[str] = None, task_class: Optional[str] = None,
    job_class: Optional[str] = None, model: Optional[str] = None,
    *, strict: bool = False,
) -> bool:
    """Record an outcome; strict callers require durable same-run acknowledgement.

    False means unconfirmed, not no effect. Reconcile retained ledger evidence
    after failure; this function never retries a write or worker operation.
    """
    try:
        if accepted_by not in ACCEPTED_BY_ALL:
            raise ValueError("accepted_by must be deterministic|reviewer|none")
        fields = dict(run_id=run_id, accepted_by=accepted_by,
                      review_rejected=review_rejected, scope_violation=scope_violation,
                      retries=retries, escalated=escalated, tokens=tokens,
                      wall_s=wall_s, pool=pool, task_class=task_class,
                      job_class=job_class, model=model)
        if strict:
            _write_record(fields, durable=True, outcome=True)
        else:
            base = {}
            for rec in read_recent(limit=10_000):
                if rec.get("run_id") == run_id:
                    base = rec
            _write_record(_outcome_record(base=base, **fields))
        return True
    except Exception as exc:
        label = "OUTCOME_WRITE_UNCONFIRMED" if strict else "outcome failed (best-effort, continuing)"
        print(f"pool_ledger: {label}: {exc}", file=sys.stderr)
        return False


def read_recent(pool: Optional[str] = None, limit: int = 100) -> list:
    """Return the last `limit` records, optionally filtered by pool."""
    records = []
    if not os.path.exists(LEDGER_PATH):
        return records
    try:
        with open(LEDGER_PATH, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if pool and rec.get("pool") != pool:
                    continue
                records.append(rec)
    except Exception:
        pass
    return records[-limit:]


# ── R26 GLM credit burn ───────────────────────────────────────────────────────

GLM_5H_CAP_DEFAULT = 28000.0
GLM_WEEK_CAP_DEFAULT = 140000.0


def _now_ts(now: Any) -> float:
    """Unix timestamp from None | epoch | datetime (naive → UTC)."""
    if now is None:
        return float(time.time())
    if isinstance(now, datetime):
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        return now.timestamp()
    return float(now)


SHIM_USAGE_PATH = os.path.join(HERE, "glm_shim", "usage.jsonl")
GLM_WINDOW_STATE_PATH = os.path.join(HERE, "glm_window_state.json")
_DEFAULT_LEDGER_DIR = os.path.abspath(os.path.join(HERE, "..", "orch", "fabric"))


def _parse_usage_ts(raw: Any) -> Optional[float]:
    """Parse a usage.jsonl ts → unix epoch float. Accepts ISO-8601 string
    (with optional 'Z' suffix) or numeric epoch. Returns None on failure."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        try:
            return float(raw)
        except (TypeError, ValueError):
            return None
    s = str(raw).strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        pass
    iso = s[:-1] if s.endswith("Z") else s
    try:
        dt = datetime.fromisoformat(iso)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def _include_shim_for(records: Optional[List[dict]]) -> bool:
    """True iff this glm_burn/compute_stats call should auto-include shim.

    Skipping rules (kept in sync with the legacy ledger-isolation tests):
      * caller passed synthetic `records` (caller controls the data),
      * LEDGER_DIR was redirected (test isolation via monkeypatch).
    """
    if records is not None:
        return False
    try:
        if os.path.abspath(LEDGER_DIR or "") != _DEFAULT_LEDGER_DIR:
            return False
    except Exception:
        return False
    return True


def _shim_known_models() -> Optional[set]:
    """Set of model names known to glm_keys.plan() (None on error)."""
    try:
        if HERE not in sys.path:
            sys.path.insert(0, HERE)
        import glm_keys
        mults = (glm_keys.plan().get("multipliers") or {})
        if not isinstance(mults, dict):
            return None
        return {m for m in mults.keys() if isinstance(m, str)}
    except Exception:
        return None


def _iso_utc(value: Any) -> str:
    if isinstance(value, datetime):
        dt = value.astimezone(timezone.utc)
    else:
        dt = datetime.fromtimestamp(float(value), tz=timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_utc_arg(raw: str) -> datetime:
    text = raw.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _load_glm_window_state(path: Optional[str] = None) -> Dict[str, Any]:
    state_path = path or GLM_WINDOW_STATE_PATH
    try:
        with open(state_path, encoding="utf-8") as fh:
            state = json.load(fh)
        return state if isinstance(state, dict) else {}
    except Exception:
        return {}


def _write_glm_window_state(state: Dict[str, Any],
                            path: Optional[str] = None) -> None:
    # A versioned code tree binds this file to the existing shared quota state.
    # Resolve before atomic replacement so the binding itself is never replaced.
    state_path = os.path.realpath(path or GLM_WINDOW_STATE_PATH)
    temp_path = state_path + ".new"
    os.makedirs(os.path.dirname(state_path) or ".", exist_ok=True)
    with open(temp_path, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2, sort_keys=True)
        fh.write("\n")
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(temp_path, state_path)


def _iter_usage_rows(records: Optional[List[dict]], five_start: float,
                     week_start: float) -> tuple:
    """Yield (timestamp, raw_credits, five, week) rows from both sources."""
    for rec in records or []:
        try:
            if rec.get("pool", "glm") != "glm":
                continue
            if rec.get("task_class") == "glm-codex":
                continue
            val = rec.get("credits")
            if val is None:
                continue
            ts = float(rec.get("ts") or 0)
            raw = float(val)
            yield ts, raw, ts > five_start, ts >= week_start
        except Exception:
            continue

    if not _include_shim_for(records):
        return
    path = SHIM_USAGE_PATH
    known = _shim_known_models()
    if not path or not os.path.exists(path):
        return
    try:
        import glm_keys
    except Exception:
        return
    calculate_credits = glm_keys.make_credit_calculator()
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                    if not isinstance(row, dict):
                        continue
                    model = row.get("model")
                    if not isinstance(model, str) or not model:
                        continue
                    if known is not None and model not in known:
                        continue
                    ts = _parse_usage_ts(row.get("ts"))
                    if ts is None:
                        continue
                    inp = int(row.get("input_tokens") or 0)
                    cached = int(row.get("cached_tokens") or 0)
                    out_tok = int(row.get("output_tokens") or 0)
                    row_dt = datetime.fromtimestamp(ts, tz=timezone.utc)
                    raw = float(calculate_credits(
                        model, inp, cached, out_tok, now=row_dt
                    ))
                    yield ts, raw, ts >= five_start, ts >= week_start
                except Exception:
                    continue
    except Exception:
        return


def _accumulate_shim(five_box, week_box,
                     five_start, week_start,
                     path=None):
    """Fold ext/glm_shim/usage.jsonl rows into five/week buckets. Returns
    (shim_rows, skipped). Credits are evaluated at the ROW's time, not now.
    Unknown models (per glm_keys.plan multipliers) are counted in `skipped`.
    Missing or unreadable file → (0, 0)."""
    if path is None:
        path = SHIM_USAGE_PATH  # lazy lookup so tests can monkeypatch
    shim_rows = 0
    skipped = 0
    if not path or not os.path.exists(path):
        return shim_rows, skipped
    try:
        import glm_keys
    except Exception:
        return shim_rows, skipped
    calculate_credits = glm_keys.make_credit_calculator()
    known = _shim_known_models()
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(row, dict):
                    continue
                shim_rows += 1
                model = row.get("model")
                if not isinstance(model, str) or not model:
                    skipped += 1
                    continue
                if known is not None and model not in known:
                    skipped += 1
                    continue
                ts = _parse_usage_ts(row.get("ts"))
                if ts is None:
                    skipped += 1
                    continue
                try:
                    inp = int(row.get("input_tokens") or 0)
                    cached = int(row.get("cached_tokens") or 0)
                    out_tok = int(row.get("output_tokens") or 0)
                    row_dt = datetime.fromtimestamp(ts, tz=timezone.utc)
                    credits = calculate_credits(
                        model, inp, cached, out_tok, now=row_dt
                    )
                except Exception:
                    skipped += 1
                    continue
                if ts > five_start:
                    five_box[0] += float(credits)
                if ts >= week_start:
                    week_box[0] += float(credits)
    except Exception:
        pass
    return shim_rows, skipped


def _shim_credit_totals_by_model(path=None):
    """Total credits per model from the shim file (no time-window filter).
    Used by compute_stats to fold shim credits into the glm provider's
    `credits_total`. Returns {} on error / missing file."""
    if path is None:
        path = SHIM_USAGE_PATH  # lazy lookup so tests can monkeypatch
    out_map = {}
    if not path or not os.path.exists(path):
        return out_map
    try:
        import glm_keys
    except Exception:
        return out_map
    calculate_credits = glm_keys.make_credit_calculator()
    known = _shim_known_models()
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(row, dict):
                    continue
                model = row.get("model")
                if not isinstance(model, str) or not model:
                    continue
                if known is not None and model not in known:
                    continue
                ts = _parse_usage_ts(row.get("ts"))
                if ts is None:
                    continue
                try:
                    inp = int(row.get("input_tokens") or 0)
                    cached = int(row.get("cached_tokens") or 0)
                    out_tok = int(row.get("output_tokens") or 0)
                    row_dt = datetime.fromtimestamp(ts, tz=timezone.utc)
                    credits = calculate_credits(
                        model, inp, cached, out_tok, now=row_dt
                    )
                except Exception:
                    continue
                out_map[model] = out_map.get(model, 0.0) + float(credits)
    except Exception:
        return out_map
    return out_map


def shim_model_share(limit: int = 5000, path: Optional[str] = None) -> dict:
    """Return bounded credit share from the last ``limit`` shim rows; ``lines_selected`` is the physical tail window while ``rows_scanned`` is the subset that parsed into a known model, and ``truncated`` refers to the physical window so ``rows_scanned`` may be below ``limit`` even when ``truncated`` is false."""
    if path is None:
        path = SHIM_USAGE_PATH  # lazy lookup so tests can monkeypatch
    empty = {
        "lines_selected": 0,
        "rows_scanned": 0,
        "limit": limit,
        "by_model": {},
        "total_credits": 0.0,
        "truncated": False,
    }
    try:
        if limit <= 0 or not path:
            return empty
        if not os.path.exists(path):
            return empty
        if HERE not in sys.path:
            sys.path.insert(0, HERE)
        import glm_keys
        calculate_credits = glm_keys.make_credit_calculator()

        known = _shim_known_models()
        with open(path, "rb") as file_handle:
            file_handle.seek(0, os.SEEK_END)
            file_size = file_handle.tell()
            position = file_size
            buffer = b""
            chunk_size = 64 * 1024
            while position > 0:
                read_size = min(chunk_size, position)
                position -= read_size
                file_handle.seek(position)
                buffer = file_handle.read(read_size) + buffer
                if buffer.count(b"\n") > limit:
                    break

        lines = buffer.splitlines()
        final_newline = file_size > 0 and buffer.endswith(b"\n")
        total_lines = len(lines)
        if file_size and not final_newline:
            total_lines += 1
        selected = lines[-limit:]
        by_model: Dict[str, Dict[str, float]] = {}
        total_credits = 0.0
        rows_scanned = 0
        for raw_line in selected:
            line = raw_line.strip()
            if not line:
                continue
            try:
                text_line = line.decode("utf-8")
            except UnicodeDecodeError:
                continue
            try:
                row = json.loads(text_line)
            except json.JSONDecodeError:
                continue
            if not isinstance(row, dict):
                continue
            model = row.get("model")
            if not isinstance(model, str) or not model:
                continue
            if known is not None and model not in known:
                continue
            ts = _parse_usage_ts(row.get("ts"))
            if ts is None:
                continue
            try:
                input_tokens = int(row.get("input_tokens") or 0)
                cached_tokens = int(row.get("cached_tokens") or 0)
                output_tokens = int(row.get("output_tokens") or 0)
                row_dt = datetime.fromtimestamp(ts, tz=timezone.utc)
                credits = float(
                    calculate_credits(
                        model,
                        input_tokens,
                        cached_tokens,
                        output_tokens,
                        now=row_dt,
                    )
                )
            except Exception:
                continue
            bucket = by_model.setdefault(model, {"credits": 0.0, "requests": 0})
            bucket["credits"] += credits
            bucket["requests"] += 1
            total_credits += credits
            rows_scanned += 1
        return {
            "lines_selected": len(selected),
            "rows_scanned": rows_scanned,
            "limit": limit,
            "by_model": by_model,
            "total_credits": total_credits,
            "truncated": total_lines > limit,
        }
    except Exception:
        return dict(empty)


# W4-G9: default account name for usage rows that pre-date the multi-account
# shim. Pre-W4-G9 rows have no "account" field; they all came from the
# legacy single-key path which the chair renamed ``chairman-max``.
_LEGACY_DEFAULT_ACCOUNT = "chairman-max"


def _shim_credit_totals_by_account(path=None):
    """Per-account credit totals from ext/glm_shim/usage.jsonl (W4-G9).

    Returns ``{account: {credits, rows}}`` where ``credits`` is the sum
    of ``glm_keys.credits_for`` evaluations for every valid row
    attributed to the account and ``rows`` is the row count. Rows without
    an ``account`` field are attributed to ``chairman-max`` (the pre-W4-G9
    single-key default). Missing / unreadable file → ``{}``.
    """
    if path is None:
        path = SHIM_USAGE_PATH  # lazy lookup so tests can monkeypatch
    out_map: Dict[str, Dict[str, float]] = {}
    if not path or not os.path.exists(path):
        return out_map
    try:
        import glm_keys
    except Exception:
        return out_map
    calculate_credits = glm_keys.make_credit_calculator()
    known = _shim_known_models()
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(row, dict):
                    continue
                model = row.get("model")
                if not isinstance(model, str) or not model:
                    continue
                if known is not None and model not in known:
                    continue
                ts = _parse_usage_ts(row.get("ts"))
                if ts is None:
                    continue
                account = row.get("account")
                if not isinstance(account, str) or not account:
                    account = _LEGACY_DEFAULT_ACCOUNT
                try:
                    inp = int(row.get("input_tokens") or 0)
                    cached = int(row.get("cached_tokens") or 0)
                    out_tok = int(row.get("output_tokens") or 0)
                    row_dt = datetime.fromtimestamp(ts, tz=timezone.utc)
                    credits = calculate_credits(
                        model, inp, cached, out_tok, now=row_dt
                    )
                except Exception:
                    continue
                bucket = out_map.setdefault(account, {
                    "credits": 0.0,
                    "rows": 0.0,
                })
                bucket["credits"] += float(credits)
                bucket["rows"] += 1
    except Exception:
        return out_map
    return out_map


def glm_burn(records: Optional[List[dict]] = None,
             now: Any = None) -> Dict[str, Any]:
    """GLM credit burn over anchored 5 h and weekly windows (R26/R29).

    state: FILL below the R29 pro-rata target, SPILL at ≥ 90 % of the
    5-hour cap, PARKED at ≥ 95 % weekly (PARKED wins); caps and the weekly
    boundary come from glm_keys.plan().
    """
    cap_5h = GLM_5H_CAP_DEFAULT
    cap_week = GLM_WEEK_CAP_DEFAULT
    week_start: Optional[float] = None
    try:
        if HERE not in sys.path:
            sys.path.insert(0, HERE)
        import glm_keys
        p = glm_keys.plan()
        cap_5h = float(p.get("credits_5h", cap_5h) or cap_5h)
        cap_week = float(p.get("credits_week", cap_week) or cap_week)
        reset = glm_keys.weekly_reset_utc(
            now if isinstance(now, datetime) else None
        )
        week_start = reset.timestamp() - 7 * 86400.0
    except Exception:
        week_start = None
    now_dt = now if isinstance(now, datetime) else None
    now_ts = _now_ts(now)
    window_state = _load_glm_window_state()
    state = window_state
    meter_state = ""
    five_reset: Optional[datetime] = None
    anchor_source = "rolling"
    calibration_factor = 1.0
    calibrated_at: Optional[datetime] = None
    try:
        five_reset = _parse_utc_arg(state["five_h_reset_utc"])
    except Exception:
        pass
    try:
        weekly_reset = _parse_utc_arg(state["weekly_reset_utc"])
        week_start = weekly_reset.timestamp() - 7 * 86400.0
    except Exception:
        pass
    try:
        calibrated_at = _parse_utc_arg(state["calibrated_at_utc"])
    except Exception:
        pass
    try:
        calibration_factor = float(state.get("calibration_factor", 1.0))
    except Exception:
        calibration_factor = 1.0

    include_shim = _include_shim_for(records)

    if five_reset is not None:
        anchor_ts = five_reset.timestamp() - 5 * 3600.0
        while now_ts >= five_reset.timestamp():
            first_post_reset: Optional[float] = None
            for row_ts, _raw, _in_five, _in_week in _iter_usage_rows(
                records, anchor_ts, week_start or anchor_ts
            ):
                if include_shim and row_ts > five_reset.timestamp():
                    first_post_reset = row_ts
                    break
            if first_post_reset is None:
                first_post_reset = now_ts
            anchor_ts = min(first_post_reset, now_ts)
            five_reset = datetime.fromtimestamp(
                anchor_ts + 5 * 3600.0, tz=timezone.utc
            )
            anchor_source = "inferred"
            if now_ts < five_reset.timestamp():
                window_state.update({
                    "five_h_anchor_utc": _iso_utc(anchor_ts),
                    "five_h_reset_utc": _iso_utc(five_reset),
                    "anchor_source": anchor_source,
                })
                _write_glm_window_state(window_state)
                break
        five_start = five_reset.timestamp() - 5 * 3600.0
        if anchor_source == "rolling":
            anchor_source = str(state.get("anchor_source") or "dashboard")
    else:
        five_start = now_ts - 5 * 3600.0
    if week_start is None:
        week_start = now_ts - 7 * 86400.0
    newest_ts = 0.0
    for rec_ts, _raw, in_five, _in_week in _iter_usage_rows(
        records, five_start, week_start
    ):
        if in_five and rec_ts <= now_ts:
            newest_ts = max(newest_ts, rec_ts)

    recs = records if records is not None else read_recent(pool="glm", limit=100_000)
    five = 0.0
    week = 0.0
    shim_rows = 0
    skipped = 0
    sources = "ledger"
    for rec in recs:
        if rec.get("pool", "glm") != "glm":
            continue
        # W4-K3 dedup: ext/glm_shim/usage.jsonl is the source of truth for
        # glm-codex spend; ledger rows with task_class "glm-codex" carry no
        # tokens (and credits==0) and must not be double-counted on top of
        # the shim contribution below.
        if rec.get("task_class") == "glm-codex":
            continue
        val = rec.get("credits")
        if val is None:
            continue
        try:
            val = float(val)
        except (TypeError, ValueError):
            continue
        ts = float(rec.get("ts") or 0)
        if ts >= five_start:
            five += val
        if ts >= week_start:
            week += val

    if include_shim:
        five_box = [five]
        week_box = [week]
        shim_rows, skipped = _accumulate_shim(
            five_box, week_box, five_start, week_start,
        )
        five = five_box[0]
        week = week_box[0]
        sources = "ledger+shim"
        # W4-G9: per-account credit totals (rows without "account" → chairman-max).
        credits_by_account = _shim_credit_totals_by_account()

    if five_reset is None:
        window_anchor = max(five_start, min(now_ts, newest_ts))
    else:
        window_anchor = five_start
    five_elapsed_s = min(5 * 3600.0, max(0.0, now_ts - window_anchor))
    pro_rata_target = cap_5h * five_elapsed_s / (5 * 3600.0)
    calibrated_five = five * calibration_factor
    pct_5h = 100.0 * calibrated_five / cap_5h if cap_5h else 0.0
    pct_week = 100.0 * week / cap_week if cap_week else 0.0
    remote_decision = None
    try:
        if records is not None or now is not None:
            raise RuntimeError("remote quota bypassed for deterministic estimate")
        import quota_remote
        remote_decision = quota_remote.glm_quota_decision(
            now_ts=now_ts,
            local_estimate=None,
            fallback_reader=lambda _now: {
                "state": (
                    "PARKED" if week * calibration_factor >= 0.95 * cap_week
                    else "SPILL" if calibrated_five >= 0.90 * cap_5h
                    else "FILL" if cap_5h and calibrated_five < 0.60 * pro_rata_target
                    else "OK"
                ),
                "pct_5h": pct_5h,
                "pct_week": pct_week,
                "observed_at": _iso_utc(now_ts),
            },
        )
    except Exception:
        remote_decision = None
    if remote_decision is not None and remote_decision.get("source") != "UNKNOWN":
        meter_state = remote_decision.get("state") or ""
        pct_5h = remote_decision.get("pct_5h", pct_5h)
        pct_week = remote_decision.get("pct_week", pct_week)
        if remote_decision.get("source") == "PROVIDER_AUTHORITATIVE":
            calibrated_five = remote_decision.get("used_5h", calibrated_five)
            week = remote_decision.get("used_week", week)
            cap_5h = remote_decision.get("cap_5h", cap_5h)
            cap_week = remote_decision.get("cap_week", cap_week)
    else:
        meter_state = (
            "PARKED" if week * calibration_factor >= 0.95 * cap_week
            else "SPILL" if calibrated_five >= 0.90 * cap_5h
            else "FILL" if cap_5h and calibrated_five < 0.60 * pro_rata_target
            else "OK"
        )
    out: Dict[str, Any] = {
        "five_h_credits": calibrated_five,
        "weekly_credits": week * calibration_factor,
        "cap_5h": int(cap_5h),
        "cap_week": int(cap_week),
        "pct_5h": pct_5h,
        "pct_week": pct_week,
        "state": meter_state,
        "five_h_window_start": five_start,
        "weekly_window_start": week_start,
        "pro_rata_target_5h": pro_rata_target,
        "raw_five_h_credits": five,
        "calibration_factor": calibration_factor,
        "calibration": "CALIBRATED" if calibrated_at is not None else "UNCALIBRATED",
        "calibrated_at": calibrated_at,
        "calibration_age_hours": (
            max(0.0, (datetime.now(timezone.utc) - calibrated_at).total_seconds() / 3600.0)
            if calibrated_at is not None else None
        ),
        "anchor_source": anchor_source,
        "quota_source": (
            remote_decision or {}
        ).get("source", "LOCAL_RECONSTRUCTION"),
        "quota_observed_at": (
            remote_decision or {}
        ).get("observed_at", _iso_utc(now_ts)),
        "quota_detail": (remote_decision or {}).get("detail"),
    }
    if now_dt is not None:
        out["five_h_reset"] = now_dt + timedelta(
            seconds=max(0.0, five_reset.timestamp() - now_ts)
        ) if five_reset is not None else now_dt + timedelta(
            seconds=5 * 3600.0 - five_elapsed_s
        )
        if "weekly_reset_utc" in state:
            try:
                out["weekly_reset"] = _parse_utc_arg(state["weekly_reset_utc"])
            except Exception:
                pass
        try:
            import glm_keys
            out["weekly_reset"] = glm_keys.weekly_reset_utc(now_dt)
        except Exception:
            pass
    else:
        if five_reset is not None:
            out["five_h_reset"] = five_reset
        else:
            try:
                out["five_h_reset"] = datetime.fromtimestamp(
                    now_ts + 5 * 3600.0 - five_elapsed_s, tz=timezone.utc
                )
            except Exception:
                pass
        try:
            import glm_keys
            out["weekly_reset"] = glm_keys.weekly_reset_utc()
        except Exception:
            pass
        if "weekly_reset_utc" in state:
            try:
                out["weekly_reset"] = _parse_utc_arg(state["weekly_reset_utc"])
            except Exception:
                pass
    if sources != "ledger":
        out["sources"] = sources
        out["shim_rows"] = shim_rows
        out["skipped"] = skipped
        out["credits_by_account"] = credits_by_account
    return out


def glm_calibrate(dashboard_5h: float, reset_5h: datetime,
                  observed_at: datetime,
                  dashboard_week: Optional[float] = None,
                  weekly_reset: Optional[datetime] = None) -> tuple:
    """Calibrate the D1-corrected estimate against the Z.ai dashboard."""
    if observed_at < reset_5h - timedelta(hours=5) or observed_at >= reset_5h:
        return 64, None, None
    anchor = reset_5h - timedelta(hours=5)
    now_dt = datetime.now(timezone.utc)
    burn = glm_burn(now=observed_at)
    estimate = float(burn["raw_five_h_credits"])
    if estimate <= 0:
        return 65, estimate, None
    factor = float(dashboard_5h) / estimate
    if estimate < 200.0 or not 0.5 <= factor <= 3.0:
        return 65, estimate, factor
    state: Dict[str, Any] = {
        "five_h_reset_utc": _iso_utc(reset_5h),
        "five_h_anchor_utc": _iso_utc(anchor),
        "calibration_factor": factor,
        "calibrated_at_utc": _iso_utc(now_dt),
        "dashboard_credits_5h": float(dashboard_5h),
        "estimate_at_calibration": estimate,
        "anchor_source": "dashboard",
    }
    if dashboard_week is not None:
        state["dashboard_credits_week"] = float(dashboard_week)
    if weekly_reset is not None:
        state["weekly_reset_utc"] = _iso_utc(weekly_reset)
    _write_glm_window_state(state)
    return 0, estimate, factor


def last_402_429(pool: Optional[str] = None) -> dict:
    """Return the most recent 402/429 record per pool (or one pool)."""
    records = read_recent(pool=pool, limit=10_000)
    result: dict = {}
    for rec in reversed(records):
        sig = rec.get("signal", "")
        if sig not in ("402", "429"):
            continue
        p = rec.get("pool")
        if p is None:
            continue
        if pool and p != pool:
            continue
        if p not in result:
            result[p] = rec
    return result


def merge_jobs(records: Iterable[dict]) -> List[dict]:
    """Fold outcome lines onto the run they name. Later fields win."""
    by_id: Dict[str, dict] = {}
    orphans: List[dict] = []
    for rec in records:
        rid = rec.get("run_id")
        if not rid:
            orphans.append(dict(rec))
            continue
        cur = by_id.get(rid, {})
        merged = dict(cur)
        merged.update(rec)
        by_id[rid] = merged
    return orphans + list(by_id.values())


def has_outcome(job: dict) -> bool:
    return job.get("accepted_by") is not None


def is_first_pass(job: dict) -> bool:
    """True iff the job succeeded clean on the first try (F2).

    Requires rc == 0 AND accepted_by in {"deterministic","reviewer"} AND
    not review_rejected AND not scope_violation AND retries == 0 AND
    not escalated. Anything else (including rc != 0, reviewer-labelled
    rows with scope_violation=True, etc.) is NOT a first-pass success;
    the stats column derives from this predicate.
    """
    if int(job.get("rc") or 0) != 0:
        return False
    if job.get("accepted_by") not in ACCEPTED_BY_OK:
        return False
    if job.get("review_rejected"):
        return False
    if job.get("scope_violation"):
        return False
    if int(job.get("retries") or 0) != 0:
        return False
    if job.get("escalated"):
        return False
    return True


def _class_matches(job: dict, wanted: str) -> bool:
    """A job matches a requested class on its job_class, else on task_class.

    Rows written before 2026-09-20 carry no job_class and their task_class holds
    an engine name, so they match only a literal engine-name query -- which is
    what keeps historical GLM/cursor reporting working unchanged.
    """
    want = (wanted or "").strip().lower()
    if not want:
        return True
    jc = (job.get("job_class") or "").strip().lower()
    tc = (job.get("task_class") or "").strip().lower()
    # MATCH EITHER, as the append comment says. Round 1 was exclusive on a present
    # job_class, which silently dropped a dual-field row
    # {task_class: glm-codex, job_class: execute} from a `glm-codex` query that the
    # pre-change reader would have kept. Parity on the real ledger was 0 diffs only
    # because no dual-field row existed yet; the first one written would have
    # regressed engine-name reporting. Found by independent review, MINOR 7.
    return want in (jc, tc)


def outcome_jobs(records: Iterable[dict], pool: Optional[str] = None,
                 task_class: Optional[str] = None) -> List[dict]:
    """Jobs that carry an accepted_by, filtered, chronological."""
    jobs = []
    for job in merge_jobs(records):
        if not has_outcome(job):
            continue
        if pool and job.get("pool") != pool:
            continue
        if task_class and not _class_matches(job, task_class):
            continue
        jobs.append(job)
    jobs.sort(key=lambda j: int(j.get("ts") or 0))
    return jobs


def below_acceptance_floor(jobs: List[dict], threshold: float = 0.6,
                           window: int = 20) -> bool:
    """True when the last `window` outcome jobs sit under the floor."""
    if len(jobs) < window:
        return False
    sample = jobs[-window:]
    rate = sum(1 for j in sample if is_first_pass(j)) / float(window)
    return rate < threshold


def _median(values: List[float]) -> Optional[float]:
    if not values:
        return None
    return float(statistics.median(values))


def load_cost_table(path: Optional[str] = None) -> Dict[str, float]:
    """Per-provider USD/Mtok placeholder estimates from pools.yaml.

    The dict only carries entries that are valid rates: bool, negative
    and nonfinite (NaN / inf) values are dropped so ``costs.get(...)``
    reports the rate as ``None`` (key absent) rather than implicitly 0.
    A genuine rate of ``0.0`` (e.g. ``ocfree``) IS legitimate and is
    preserved. Missing or unreadable YAML → empty dict.
    """
    target = path or POOLS_YAML
    try:
        import yaml  # type: ignore
        with open(target, encoding="utf-8") as fh:
            doc = yaml.safe_load(fh) or {}
        raw = ((doc.get("routing") or {}).get("cost_usd_per_mtok_estimates") or {})
        out: Dict[str, float] = {}
        for k, v in raw.items():
            if str(k).startswith("_"):
                continue
            rate = _valid_cost_rate(v)
            if rate is not None:
                out[str(k)] = rate
        return out
    except Exception:
        return {}


def _valid_cost_rate(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return None
    try:
        rate = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return rate if math.isfinite(rate) and rate >= 0 else None


def _is_known_token(value: Any) -> bool:
    """A token count is known only when ``type(value) is int`` and ``value >= 0``.

    Excludes bool (its own type, not int), floats, strings, None, and
    negative ints. Centralised so ``compute_stats`` can defend median
    and per-job cost columns against malformed usage in one place.
    """
    return type(value) is int and value >= 0


def _is_valid_model(value: Any) -> bool:
    """A model identifier is a str with at least one character."""
    return isinstance(value, str) and value != ""


def _is_review_rejected(job: dict) -> bool:
    """``review_rejected is True`` literally — not truthy, not a 1, not a string."""
    return job.get("review_rejected") is True


def _is_accepted_run(job: dict) -> bool:
    """Accepted for cost / credit per-job accounting.

    ``accepted_by in {deterministic, reviewer}`` AND not literal
    ``review_rejected``. No ``rc`` requirement: a reviewed partial
    source can be accepted even when its ``rc`` reflects a transport
    timeout, and the original ``accepted_by`` value is preserved.
    """
    return (
        job.get("accepted_by") in ACCEPTED_BY_OK
        and not _is_review_rejected(job)
    )


def _default_model(pool: str) -> str:
    MODELS = {
        "grok": "grok-4.6",
        "cursor": "cursor-pro",
        "bailian": "qwen3.8-flash",
        "minimax": "MiniMax-M2.7-highspeed",
        "claude": "claude-opus-5",
        "glm": "glm-placeholder",
    }
    return MODELS.get(pool, "-")


def _quality_verdict_available(job: dict) -> bool:
    """Explicit positive acceptance or rejection/scope finding.
    An accepted_by value of none alone is not a quality verdict."""
    return (job.get("accepted_by") in ACCEPTED_BY_OK
            or _is_review_rejected(job)
            or job.get("scope_violation") is True)


def compute_stats(records: Optional[List[dict]] = None,
                  task_class: Optional[str] = None) -> List[Dict[str, Any]]:
    """Per {provider, model, task_class} R22 metrics.

    Model grouping: missing / empty / non-str ``model`` values bucket
    as ``"(unknown)"`` rather than inferring a current default. Valid
    model strings are preserved verbatim.

    Token usage is known only when ``type(value) is int`` and
    ``value >= 0``; floats, bool, strings, negatives, and ``None`` are
    excluded from the median and from the cost basis. ``n_tokens_known``
    and ``n_tokens_unknown`` expose how many group members fell into
    each bucket. Invalid / missing usage does not raise.

    Per-provider USD/Mtok rates come from ``load_cost_table()``;
    absent or invalid rates stay unavailable (``None``) so the cost
    columns are never an implicit zero. ``effective_cost_per_accepted_job``
    is reported only when a valid rate exists, every contributing run has
    known usage, and at least one run is accepted.

    Accepted cost / credit denominator excludes rows whose
    ``review_rejected`` is literally ``True`` even when ``accepted_by``
    is ``reviewer`` or ``deterministic``. Existing ``accepted_by``
    values are preserved; no ``rc`` requirement is added. Shim usage
    has model-only provenance and is displayed once as unattributed,
    never multiplied across task classes.
    """
    recs = records if records is not None else read_recent(limit=10_000)
    jobs = merge_jobs(recs)
    groups: Dict[tuple, List[dict]] = {}
    for job in jobs:
        # R22's other half. Round 1 taught outcome_jobs about job_class but left
        # `pool stats --class execute|heal|review` filtering and grouping on
        # task_class alone, so it printed "# no jobs" for every real class while
        # the remote-lane change moved the real class into job_class. Independent
        # review, MAJOR 4. Filter and group on the same notion the floor uses.
        if task_class and not _class_matches(job, task_class):
            continue
        provider = job.get("pool") or "-"
        raw_model = job.get("model")
        if _is_valid_model(raw_model):
            model = raw_model  # preserve spelling
        else:
            model = "(unknown)"
        tc = job.get("job_class") or job.get("task_class") or "unknown"
        groups.setdefault((provider, model, tc), []).append(job)

    shim_by_model: Dict[str, float] = {}
    if _include_shim_for(records):
        shim_by_model = _shim_credit_totals_by_model()

    costs = load_cost_table()
    rows: List[Dict[str, Any]] = []
    for (provider, model, tc), group in sorted(groups.items()):
        n = len(group)
        with_out = [j for j in group if has_outcome(j)]
        n_out = len(with_out)
        def rate(pred) -> Optional[float]:
            if n_out == 0:
                return None
            return sum(1 for j in with_out if pred(j)) / float(n_out)

        # Legacy first-pass counts all outcomes; a distinct quality denominator
        # avoids mistaking unverified/none results for demonstrated model failures.
        quality_jobs = [j for j in with_out if _quality_verdict_available(j)]
        n_quality = len(quality_jobs)
        n_no_quality = n_out - n_quality
        evaluated_first_pass = (
            sum(1 for j in quality_jobs if is_first_pass(j)) / float(n_quality)
            if n_quality else None)
        quality_coverage = n_quality / float(n_out) if n_out else None
        successful_unaccepted = sum(
            1 for j in with_out
            if (j.get("rc") == 0 and j.get("signal") == "ok"
                and not _quality_verdict_available(j)))
        admission_refusals = sum(
            1 for j in group
            if j.get("rc") == 75 and j.get("signal") == "admission")
        first_pass = rate(is_first_pass)
        det = rate(lambda j: j.get("accepted_by") == "deterministic")
        rej = rate(lambda j: bool(j.get("review_rejected")))
        scope = rate(lambda j: bool(j.get("scope_violation")))
        retry = rate(lambda j: int(j.get("retries") or 0) > 0)
        esc = rate(lambda j: bool(j.get("escalated")))

        token_vals = [float(j["tokens"]) for j in group
                      if _is_known_token(j.get("tokens"))]
        n_tokens_known = len(token_vals)
        n_tokens_unknown = sum(
            1 for j in group if not _is_known_token(j.get("tokens"))
        )
        wall_vals = [float(j["wall_s"]) for j in group
                     if j.get("wall_s") is not None]
        accepted = [j for j in with_out if _is_accepted_run(j)]

        usd_per_m = _valid_cost_rate(costs.get(provider))
        # Failed attempts are part of the cost of accepted work. Partial
        # usage coverage cannot support a whole-group cost estimate.
        if usd_per_m is not None and accepted and n_tokens_unknown == 0:
            total_tok = sum(j["tokens"] for j in group)
            eff_cost: Optional[float] = (
                total_tok / 1_000_000.0 * usd_per_m / len(accepted)
            )
        else:
            eff_cost = None

        credit_vals = [float(j["credits"]) for j in group
                       if j.get("credits") is not None]
        credits_total: Optional[float] = sum(credit_vals) if credit_vals else None
        # Only row-level ledger credits have per-task-class provenance.
        # The model-only shim total is rendered separately below.
        if credits_total is not None and accepted:
            credits_per_job: Optional[float] = credits_total / float(len(accepted))
        else:
            credits_per_job = None

        rows.append({
            "provider": provider,
            "model": model,
            "task_class": tc,
            "n": n,
            "n_outcome": n_out,
            "n_quality_verdict": n_quality,
            "n_without_quality_verdict": n_no_quality,
            "quality_verdict_coverage": quality_coverage,
            "evaluated_first_pass_acceptance": evaluated_first_pass,
            "n_successful_without_quality_verdict": successful_unaccepted,
            "n_admission_refused": admission_refusals,
            "n_tokens_known": n_tokens_known,
            "n_tokens_unknown": n_tokens_unknown,
            "first_pass_acceptance": first_pass,
            "deterministic_verification_rate": det,
            "review_rejection_rate": rej,
            "scope_violation_rate": scope,
            "retry_rate": retry,
            "escalation_rate": esc,
            "median_tokens": _median(token_vals),
            "median_wall_time": _median(wall_vals),
            "effective_cost_per_accepted_job": eff_cost,
            "cost_usd_per_mtok_estimate": usd_per_m,
            "credits_total": credits_total,
            "credits_per_accepted_job": credits_per_job,
        })

    # GLM shim usage.jsonl has model/account/usage, but no run_id, job_class
    # or task_class. Charging its full model total to *every* model-class
    # row reports N x spend when N classes share a model. Keep one clearly
    # unattributed row per model instead of manufacturing job attribution.
    if shim_by_model and task_class in (None, "(shim-unattributed)"):
        for model, shim_total in sorted(
            shim_by_model.items(), key=lambda item: str(item[0])
        ):
            if not _is_valid_model(model):
                continue
            try:
                credit = float(shim_total)
            except (TypeError, ValueError):
                continue
            if not math.isfinite(credit) or credit < 0:
                continue
            rows.append({
                "provider": "glm", "model": model,
                "task_class": "(shim-unattributed)",
                "n": 0, "n_outcome": 0,
                "n_quality_verdict": 0,
                "n_without_quality_verdict": 0,
                "quality_verdict_coverage": None,
                "evaluated_first_pass_acceptance": None,
                "n_successful_without_quality_verdict": 0,
                "n_admission_refused": 0,
                "n_tokens_known": 0, "n_tokens_unknown": 0,
                "first_pass_acceptance": None,
                "deterministic_verification_rate": None,
                "review_rejection_rate": None,
                "scope_violation_rate": None,
                "retry_rate": None, "escalation_rate": None,
                "median_tokens": None, "median_wall_time": None,
                "effective_cost_per_accepted_job": None,
                "cost_usd_per_mtok_estimate": None,
                "credits_total": credit,
                "credits_per_accepted_job": None,
            })
    return rows


def _fmt(v: Optional[float], digits: int = 3) -> str:
    if v is None:
        return "n/a"
    return f"{v:.{digits}f}"


def _fmt_reset(value: Any) -> str:
    try:
        return value.isoformat()
    except AttributeError:
        return "unknown"


def _fmt_calibration(burn: Dict[str, Any]) -> str:
    if burn.get("calibration") != "CALIBRATED":
        return "UNCALIBRATED"
    factor = float(burn.get("calibration_factor", 1.0))
    age = burn.get("calibration_age_hours")
    age_s = "unknown" if age is None else f"{float(age):.1f}h"
    return f"CALIBRATED({factor:.6f}, age {age_s})"


def print_stats(task_class: Optional[str] = None) -> None:
    rows = compute_stats(task_class=task_class)
    print(
        "provider model task_class n n_outcome "
        "first_pass_acceptance deterministic_verification_rate "
        "review_rejection_rate scope_violation_rate retry_rate "
        "escalation_rate median_tokens median_wall_time "
        "effective_cost_per_accepted_job credits_total "
        "credits_per_accepted_job "
        "n_quality_verdict n_without_quality_verdict "
        "quality_verdict_coverage evaluated_first_pass_acceptance "
        "n_successful_without_quality_verdict n_admission_refused"
    )
    print("# legacy first_pass_acceptance includes all outcomes; inspect quality_verdict_coverage before judging model quality")
    print("# evaluated_first_pass_acceptance uses n_quality_verdict as denominator; small samples are inconclusive")
    print("# cost column uses PLACEHOLDER ESTIMATES $/Mtok from pools.yaml — not vendor quotes")
    if not rows:
        print("# no jobs")
        return
    for r in rows:
        print(
            f"{r['provider']} {r['model']} {r['task_class']} "
            f"{r['n']} {r['n_outcome']} "
            f"{_fmt(r['first_pass_acceptance'])} "
            f"{_fmt(r['deterministic_verification_rate'])} "
            f"{_fmt(r['review_rejection_rate'])} "
            f"{_fmt(r['scope_violation_rate'])} "
            f"{_fmt(r['retry_rate'])} "
            f"{_fmt(r['escalation_rate'])} "
            f"{_fmt(r['median_tokens'], 1)} "
            f"{_fmt(r['median_wall_time'], 1)} "
            f"{_fmt(r['effective_cost_per_accepted_job'], 4)} "
            f"{_fmt(r['credits_total'], 2)} "
            f"{_fmt(r['credits_per_accepted_job'], 4)} "
            f"{r['n_quality_verdict']} "
            f"{r['n_without_quality_verdict']} "
            f"{_fmt(r['quality_verdict_coverage'])} "
            f"{_fmt(r['evaluated_first_pass_acceptance'])} "
            f"{r['n_successful_without_quality_verdict']} "
            f"{r['n_admission_refused']}"
        )



# ---------------------------------------------------------------------------
# Candidate overlay: collected-source quality attestation sidecar (this owner).
#
# This ledger owner publishes ONE fixed metadata-only sidecar per original run
# at owner_path(state/remote_sub)/<run_id>.collection-quality.json under the
# existing ledger.jsonl.lock, using this owner's strict identity/flock
# primitives plus the incumbent artifact_delivery held-DirectoryChain,
# exclusive-create/fsync/link/readback mechanics.
#
# OWNER ENFORCEMENT: publication takes only original-operation inputs — the
# retained source binding path, the collection receipt path plus its expected
# SHA-256, the owned closed adjudication file path, and the original
# run/root/parent scope. The collector's original-caller guard runs BEFORE any
# input read or write, then — under the held ledger lock — this owner
# re-derives the qualified subject from the actual retained evidence through
# the collector's retained-descriptor qualification and reads the owned
# adjudication itself. Raw subject or adjudication dictionaries are never
# accepted and there is no optional verification callback: revalidation around
# the link is this owner's own retained-descriptor check. A facade (for
# example fabric_task) only forwards paths; it is never a trust boundary.
#
# Zero ledger.jsonl writes, zero terminal/result/stdout copies, no broker or
# lane change, no directory scans, discovery or second index, and no runtime
# acceptance field: the quality fields are named collected_source_quality and
# quality_by and grant no acceptance, release or retry right. The canonical
# path is derived only from the verified original operation namespace and is
# the cross-collection uniqueness anchor: an exact existing attestation with
# the same complete subject and adjudication is idempotent; any different
# receipt, binding, destination, bytes or verdict is an explicit conflict with
# no overwrite and no silent acceptance.
#
# FAIL-CLOSED PUBLICATION: the staged inode this call created stays open on a
# retained owned descriptor through stage-integrity, source revalidation,
# link, fsync, identity and readback verification. If any of those fail before
# an acknowledged durable result, that ONE inode is invalidated through the
# retained descriptor (truncate to zero + fsync) and the refusal re-raises —
# no fabricated attestation stays reachable under either name. The pending
# name is retained as the ambiguity marker, so a blind retry is refused and
# recovery stays with this fixed receipt owner. Deterministic refusals
# (existing or concurrently won conflicting attestations) keep the staged
# bytes exactly as written. A previously confirmed or concurrently replaced
# inode is never touched: invalidation only ever reaches the descriptor this
# call created and verified as its own, never a pathname.
#
# CLOSED READBACK: read_collection_quality enforces the original
# run/root/parent scope and the collector caller guard BEFORE any IO, then
# validates the complete canonical attestation strictly — exact field sets at
# every level (no accepted_by or other unknown field), the nested subject
# projection, and the retained complete explicit adjudication whose exact
# bytes must re-hash to the attested adjudication digest and crossbind the
# attested subject — and finally re-qualifies the attested collection right
# now from the canonical owned references (this owner's <run>.binding.json
# plus the attested receipt path and digest) before any delivery, worker or
# quality positive is projected. A schema-only, unknown-field, tampered or
# evidence-diverged row is reported UNQUALIFIED, never positive. Caller labels
# and file existence never self-authenticate, and a read never mutates the
# original operation or retries a publication.
#
# SERIALIZED READBACK: the whole inspection runs under the SAME incumbent
# ledger.jsonl.lock every publication holds exclusively — opened read-only
# WITHOUT O_CREAT through this owner's strict same-owner primitive and held
# LOCK_SH|LOCK_NB with bounded zero wait. A busy incumbent lock reports the
# explicit non-positive PUBLICATION_IN_PROGRESS with no sidecar IO, so a
# publication paused anywhere inside its qualification/link/readback window is
# never projected as positive; an absent lock is the precise non-positive
# NOT_RECORDED (a new confirmed record requires an existing publisher lock,
# and inspection never creates the lock, its directory or any state); a
# replaced, foreign-owned or unsafe lock is refused. The canonical link is
# additionally held open from its first strict read through the complete
# closed validation and evidence re-qualification and is re-proved to be the
# same inode with the same bytes, ownership, mode and link count afterwards
# through the incumbent DirectoryChain/read_local_at owners, so a canonical
# row replaced or invalidated while its evidence is re-qualified is reported
# UNQUALIFIED as changed, never a stale positive.
# ---------------------------------------------------------------------------

import hashlib

COLLECTION_QUALITY_SCHEMA = "mastermind.collection_quality_attestation.v1"
COLLECTION_QUALITY_SUBJECT_SCHEMA = "mastermind.collection_quality_subject.v1"
COLLECTION_QUALITY_ADJUDICATION_SCHEMA = "mastermind.collection_quality_adjudication.v1"
COLLECTION_QUALITY_SUFFIX = ".collection-quality.json"
COLLECTION_QUALITY_PENDING_SUFFIX = ".collection-quality.pending.json"
COLLECTION_QUALITY_MAX_BYTES = 262144
COLLECTION_QUALITY_MAX_FILES = 64
COLLECTION_QUALITY_MAX_ARTIFACTS = 8
COLLECTION_QUALITY_VERDICTS = ("PASS", "FAIL", "PARTIAL")
COLLECTION_QUALITY_BY_ROLES = ("deterministic", "reviewer")
COLLECTION_QUALITY_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z")
COLLECTION_QUALITY_TEXT = re.compile(r"[A-Za-z0-9][A-Za-z0-9 _.:/()+'-]{0,511}\Z")
COLLECTION_QUALITY_SHORT_TEXT = re.compile(r"[A-Za-z0-9][A-Za-z0-9 _.:/()+'-]{0,127}\Z")
COLLECTION_QUALITY_IDENTITY = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")
COLLECTION_QUALITY_MAX_ADJUDICATION = 65536


class CollectionQualityRefused(ValueError):
    """Typed sidecar refusal; never an invitation to retry."""


class CollectionQualityConflict(CollectionQualityRefused):
    """An existing immutable attestation disagrees; never overwritten."""


class CollectionQualityAmbiguous(CollectionQualityRefused):
    """A staged publication is retained; reconcile by readback, never retry blind."""


def _collection_quality_collector():
    import original_delivery_collector as collector
    return collector


def _collection_quality_state_dir():
    """The incumbent owner state directory of this exact installed owner."""
    import artifact_delivery as delivery
    here = os.path.dirname(os.path.abspath(__file__))
    return delivery.owner_path(os.path.join(here, "state", "remote_sub"), here)


def _collection_quality_scope(run_id, root, parent):
    """Typed original-operation scope; checked before any IO."""
    if (type(run_id) is not str or type(root) is not str or type(parent) is not str
            or any(COLLECTION_QUALITY_IDENTITY.fullmatch(value) is None
                   for value in (run_id, root, parent))):
        raise CollectionQualityRefused("collection_quality_scope_invalid")
    return run_id


def _collection_quality_digest(value):
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _collection_quality_identity(value):
    return (type(value) is str
            and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", value) is not None)


def _collection_quality_entries(items, shape, limit):
    if type(items) is not list or not 1 <= len(items) <= limit:
        raise CollectionQualityRefused("collection_quality_subject_files_invalid")
    for item in items:
        if type(item) is not dict or set(item) != {key for key, _ in shape}:
            raise CollectionQualityRefused("collection_quality_subject_files_invalid")
        for key, kind in shape:
            value = item[key]
            if kind == "int":
                if type(value) is not int or not 0 < value <= 16 * 1024 * 1024:
                    raise CollectionQualityRefused("collection_quality_subject_files_invalid")
            elif kind == "digest":
                if not _collection_quality_digest(value):
                    raise CollectionQualityRefused("collection_quality_subject_files_invalid")
            elif kind == "path":
                if (type(value) is not str or not value.startswith("/tmp/")
                        or len(value) > 270 or ".." in value.split("/")
                        or COLLECTION_QUALITY_NAME.fullmatch(value.rsplit("/", 1)[-1]) is None):
                    raise CollectionQualityRefused("collection_quality_subject_files_invalid")
            else:
                if (type(value) is not str
                        or COLLECTION_QUALITY_NAME.fullmatch(value) is None):
                    raise CollectionQualityRefused("collection_quality_subject_files_invalid")


def collection_quality_validate_subject(subject):
    """Strict bounded shape of one qualified collection subject (metadata only)."""
    fields = {"schema", "run_id", "root", "parent", "host", "mode", "requested_model",
              "destination", "receipt_name", "receipt_sha256", "binding_sha256",
              "request_sha256", "response_sha256", "packet_sha256", "body_sha256",
              "support_digest", "artifact_names", "stdout", "process_sha256",
              "returncode", "files", "artifacts", "artifact_manifest_sha256",
              "collection_files_sha256"}
    if (type(subject) is not dict or set(subject) != fields
            or subject["schema"] != COLLECTION_QUALITY_SUBJECT_SCHEMA):
        raise CollectionQualityRefused("collection_quality_subject_invalid")
    for key in ("run_id", "root", "parent", "host", "requested_model"):
        if not _collection_quality_identity(subject[key]):
            raise CollectionQualityRefused("collection_quality_subject_identity_invalid")
    if subject["mode"] not in ("glm", "qwen"):
        raise CollectionQualityRefused("collection_quality_subject_mode_invalid")
    for key in ("receipt_sha256", "binding_sha256", "request_sha256", "response_sha256",
                "packet_sha256", "body_sha256", "support_digest", "process_sha256",
                "artifact_manifest_sha256", "collection_files_sha256"):
        if not _collection_quality_digest(subject[key]):
            raise CollectionQualityRefused("collection_quality_subject_digest_invalid")
    destination = subject["destination"]
    if (type(destination) is not str or not destination.startswith("/")
            or ".." in destination.split("/") or len(destination) > 1024
            or type(subject["receipt_name"]) is not str
            or COLLECTION_QUALITY_NAME.fullmatch(subject["receipt_name"]) is None):
        raise CollectionQualityRefused("collection_quality_subject_destination_invalid")
    names = subject["artifact_names"]
    if (type(names) is not list or not 1 <= len(names) <= COLLECTION_QUALITY_MAX_ARTIFACTS
            or len(set(names)) != len(names)
            or any(type(name) is not str or COLLECTION_QUALITY_NAME.fullmatch(name) is None
                   for name in names)):
        raise CollectionQualityRefused("collection_quality_subject_names_invalid")
    stdout = subject["stdout"]
    if (type(stdout) is not dict or set(stdout) != {"sha256", "bytes", "chunks"}
            or not _collection_quality_digest(stdout["sha256"])
            or type(stdout["bytes"]) is not int or not 0 < stdout["bytes"] <= 8 * 1024 * 1024
            or type(stdout["chunks"]) is not int or not 1 <= stdout["chunks"] <= 64):
        raise CollectionQualityRefused("collection_quality_subject_stdout_invalid")
    if subject["returncode"] != 0:
        raise CollectionQualityRefused("collection_quality_subject_returncode_invalid")
    _collection_quality_entries(subject["files"],
                                (("local_name", "name"), ("bytes", "int"), ("sha256", "digest")),
                                COLLECTION_QUALITY_MAX_FILES)
    _collection_quality_entries(subject["artifacts"],
                                (("path", "path"), ("bytes", "int"), ("sha256", "digest"),
                                 ("local_name", "name")),
                                COLLECTION_QUALITY_MAX_ARTIFACTS)
    return subject


def collection_quality_validate_adjudication(adjudication):
    """Bounded shape of one normalized closed adjudication reference."""
    if (type(adjudication) is not dict
            or set(adjudication) != {"verdict", "by", "reason", "evidence",
                                     "adjudication_sha256"}):
        raise CollectionQualityRefused("collection_quality_adjudication_invalid")
    if adjudication["verdict"] not in COLLECTION_QUALITY_VERDICTS:
        raise CollectionQualityRefused("collection_quality_adjudication_verdict_invalid")
    if adjudication["by"] not in COLLECTION_QUALITY_BY_ROLES:
        raise CollectionQualityRefused("collection_quality_adjudication_role_invalid")
    if (type(adjudication["reason"]) is not str
            or COLLECTION_QUALITY_TEXT.fullmatch(adjudication["reason"]) is None):
        raise CollectionQualityRefused("collection_quality_adjudication_reason_invalid")
    if (type(adjudication["evidence"]) is not str
            or COLLECTION_QUALITY_SHORT_TEXT.fullmatch(adjudication["evidence"]) is None):
        raise CollectionQualityRefused("collection_quality_adjudication_evidence_invalid")
    if not _collection_quality_digest(adjudication["adjudication_sha256"]):
        raise CollectionQualityRefused("collection_quality_adjudication_digest_invalid")
    return adjudication


def _collection_quality_adjudication_record(row):
    """Verify the retained complete explicit adjudication and its crossbindings.

    The attestation retains the exact owned adjudication bytes so a readback
    can re-hash them to the attested digest — a normalized summary alone could
    never prove which closed input was adjudicated — and then crossbind the
    parsed record against the attested subject facts and attestation
    projections. Any drift in either direction refuses.
    """
    section = row.get("adjudication")
    if (type(section) is not dict
            or set(section) != {"verdict", "by", "adjudication_sha256", "record"}):
        raise CollectionQualityRefused("collection_quality_adjudication_section_invalid")
    record = section["record"]
    try:
        encoded = record.encode("utf-8")
    except (AttributeError, UnicodeError):
        raise CollectionQualityRefused("collection_quality_adjudication_unreadable")
    if (not 0 < len(encoded) <= COLLECTION_QUALITY_MAX_ADJUDICATION
            or hashlib.sha256(encoded).hexdigest() != section["adjudication_sha256"]):
        raise CollectionQualityRefused("collection_quality_adjudication_digest_mismatch")
    try:
        adjudication = _strict_json(record)
    except ValueError as error:
        raise CollectionQualityRefused("collection_quality_adjudication_unreadable") from error
    fields = {"schema", "run_id", "root", "parent", "verdict", "by", "reason",
              "evidence", "receipt_sha256", "stdout_sha256", "stdout_bytes",
              "files", "artifacts"}
    collection = row.get("collection") if type(row.get("collection")) is dict else {}
    stdout = collection.get("stdout") if type(collection.get("stdout")) is dict else {}
    if (type(adjudication) is not dict or set(adjudication) != fields
            or adjudication["schema"] != COLLECTION_QUALITY_ADJUDICATION_SCHEMA
            or adjudication["verdict"] not in COLLECTION_QUALITY_VERDICTS
            or adjudication["verdict"] != row.get("collected_source_quality")
            or adjudication["by"] not in COLLECTION_QUALITY_BY_ROLES
            or adjudication["by"] != row.get("quality_by")
            or type(adjudication["reason"]) is not str
            or COLLECTION_QUALITY_TEXT.fullmatch(adjudication["reason"]) is None
            or adjudication["reason"] != row.get("quality_reason")
            or type(adjudication["evidence"]) is not str
            or COLLECTION_QUALITY_SHORT_TEXT.fullmatch(adjudication["evidence"]) is None
            or adjudication["evidence"] != row.get("quality_evidence")
            or any(adjudication[key] != row.get(key) for key in ("run_id", "root", "parent"))
            or adjudication["receipt_sha256"] != collection.get("receipt_sha256")
            or adjudication["stdout_sha256"] != stdout.get("sha256")
            or adjudication["stdout_bytes"] != stdout.get("bytes")
            or adjudication["files"] != collection.get("files")
            or adjudication["artifacts"] != collection.get("artifacts")):
        raise CollectionQualityRefused("collection_quality_adjudication_crossbinding_invalid")
    return adjudication


def collection_quality_validate_attestation(row):
    """Strict closed shape of one canonical quality attestation.

    Exact field sets at every level: any unknown field — for example an
    accepted_by, acceptance or terminal field — refuses. This validates the
    canonical bytes only; it never projects a positive by itself, because a
    schema-shaped row is not a qualified collection.
    """
    fields = {"schema", "run_id", "root", "parent", "host", "mode",
              "requested_model", "collected_source_quality", "quality_by",
              "quality_reason", "quality_evidence", "source", "collection",
              "adjudication", "recorded_at"}
    if (type(row) is not dict or set(row) != fields
            or row["schema"] != COLLECTION_QUALITY_SCHEMA
            or any(not _collection_quality_identity(row[key])
                   for key in ("run_id", "root", "parent", "host", "requested_model"))
            or row["mode"] not in ("glm", "qwen")
            or row["collected_source_quality"] not in COLLECTION_QUALITY_VERDICTS
            or row["quality_by"] not in COLLECTION_QUALITY_BY_ROLES
            or type(row["quality_reason"]) is not str
            or COLLECTION_QUALITY_TEXT.fullmatch(row["quality_reason"]) is None
            or type(row["quality_evidence"]) is not str
            or COLLECTION_QUALITY_SHORT_TEXT.fullmatch(row["quality_evidence"]) is None
            or type(row["recorded_at"]) is not int or row["recorded_at"] < 0):
        raise CollectionQualityRefused("collection_quality_attestation_invalid")
    source = row["source"]
    if (type(source) is not dict
            or set(source) != {"binding_sha256", "request_sha256", "packet_sha256",
                               "body_sha256", "support_digest", "artifact_names"}
            or any(not _collection_quality_digest(source[key]) for key in
                   ("binding_sha256", "request_sha256", "packet_sha256",
                    "body_sha256", "support_digest"))
            or type(source["artifact_names"]) is not list
            or not 1 <= len(source["artifact_names"]) <= COLLECTION_QUALITY_MAX_ARTIFACTS
            or len(set(source["artifact_names"])) != len(source["artifact_names"])
            or any(type(name) is not str or COLLECTION_QUALITY_NAME.fullmatch(name) is None
                   for name in source["artifact_names"])):
        raise CollectionQualityRefused("collection_quality_source_section_invalid")
    collection = row["collection"]
    if (type(collection) is not dict
            or set(collection) != {"destination", "receipt_name", "receipt_sha256",
                                   "state", "delivery_verified", "worker_terminal_proof",
                                   "request_sha256", "response_sha256", "stdout",
                                   "process_sha256", "returncode",
                                   "artifact_manifest_sha256", "files", "artifacts",
                                   "collection_files_sha256"}
            or type(collection["destination"]) is not str
            or not collection["destination"].startswith("/")
            or ".." in collection["destination"].split("/")
            or len(collection["destination"]) > 1024
            or type(collection["receipt_name"]) is not str
            or COLLECTION_QUALITY_NAME.fullmatch(collection["receipt_name"]) is None
            or not _collection_quality_digest(collection["receipt_sha256"])
            or collection["state"] != "COMPLETE"
            or collection["delivery_verified"] is not True
            or collection["worker_terminal_proof"] is not True
            or not _collection_quality_digest(collection["request_sha256"])
            or not _collection_quality_digest(collection["response_sha256"])
            or not _collection_quality_digest(collection["process_sha256"])
            or not _collection_quality_digest(collection["artifact_manifest_sha256"])
            or not _collection_quality_digest(collection["collection_files_sha256"])
            or collection["returncode"] != 0):
        raise CollectionQualityRefused("collection_quality_collection_section_invalid")
    stdout = collection["stdout"]
    if (type(stdout) is not dict or set(stdout) != {"sha256", "bytes", "chunks"}
            or not _collection_quality_digest(stdout["sha256"])
            or type(stdout["bytes"]) is not int or not 0 < stdout["bytes"] <= 8 * 1024 * 1024
            or type(stdout["chunks"]) is not int or not 1 <= stdout["chunks"] <= 64):
        raise CollectionQualityRefused("collection_quality_stdout_section_invalid")
    _collection_quality_entries(collection["files"],
                                (("local_name", "name"), ("bytes", "int"), ("sha256", "digest")),
                                COLLECTION_QUALITY_MAX_FILES)
    _collection_quality_entries(collection["artifacts"],
                                (("path", "path"), ("bytes", "int"), ("sha256", "digest"),
                                 ("local_name", "name")),
                                COLLECTION_QUALITY_MAX_ARTIFACTS)
    _collection_quality_adjudication_record(row)
    return row


def collection_quality_subject_projection(row):
    """Rebuild the exact qualified subject from one validated attestation."""
    collection_quality_validate_attestation(row)
    source = row["source"]
    collection = row["collection"]
    subject = {
        "schema": COLLECTION_QUALITY_SUBJECT_SCHEMA,
        "run_id": row["run_id"],
        "root": row["root"],
        "parent": row["parent"],
        "host": row["host"],
        "mode": row["mode"],
        "requested_model": row["requested_model"],
        "destination": collection["destination"],
        "receipt_name": collection["receipt_name"],
        "receipt_sha256": collection["receipt_sha256"],
        "binding_sha256": source["binding_sha256"],
        "request_sha256": source["request_sha256"],
        "response_sha256": collection["response_sha256"],
        "packet_sha256": source["packet_sha256"],
        "body_sha256": source["body_sha256"],
        "support_digest": source["support_digest"],
        "artifact_names": list(source["artifact_names"]),
        "stdout": dict(collection["stdout"]),
        "process_sha256": collection["process_sha256"],
        "returncode": collection["returncode"],
        "files": [dict(item) for item in collection["files"]],
        "artifacts": [dict(item) for item in collection["artifacts"]],
        "artifact_manifest_sha256": collection["artifact_manifest_sha256"],
        "collection_files_sha256": collection["collection_files_sha256"],
    }
    collection_quality_validate_subject(subject)
    return subject


def collection_quality_attestation(*, run_id, root, parent, subject, adjudication,
                                   adjudication_record):
    """Owner-side construction of the immutable metadata-only attestation.

    Binds the original run, root, unchanged parent, host and mode, the exact
    source binding/transported packet/support, the collection receipt, stdout
    length+digest, and every artifact digest/length/name, plus the complete
    explicit adjudication retained verbatim so any readback can re-hash it to
    the attested digest. No raw result, command or secret content is ever
    copied: the adjudication input is the collector's closed metadata-only
    adjudication, not a success flag or free-form note.
    """
    if (type(run_id) is not str
            or COLLECTION_QUALITY_IDENTITY.fullmatch(run_id) is None):
        raise CollectionQualityRefused("collection_quality_run_invalid")
    collection_quality_validate_subject(subject)
    collection_quality_validate_adjudication(adjudication)
    if not isinstance(adjudication_record, (bytes, bytearray)):
        raise CollectionQualityRefused("collection_quality_adjudication_invalid")
    record = bytes(adjudication_record)
    if (not 0 < len(record) <= COLLECTION_QUALITY_MAX_ADJUDICATION
            or hashlib.sha256(record).hexdigest() != adjudication["adjudication_sha256"]):
        raise CollectionQualityRefused("collection_quality_adjudication_digest_mismatch")
    if subject["run_id"] != run_id or subject["root"] != root or subject["parent"] != parent:
        raise CollectionQualityRefused("collection_quality_scope_mismatch")
    row = {
        "schema": COLLECTION_QUALITY_SCHEMA,
        "run_id": run_id,
        "root": root,
        "parent": parent,
        "host": subject["host"],
        "mode": subject["mode"],
        "requested_model": subject["requested_model"],
        "collected_source_quality": adjudication["verdict"],
        "quality_by": adjudication["by"],
        "quality_reason": adjudication["reason"],
        "quality_evidence": adjudication["evidence"],
        "source": {
            "binding_sha256": subject["binding_sha256"],
            "request_sha256": subject["request_sha256"],
            "packet_sha256": subject["packet_sha256"],
            "body_sha256": subject["body_sha256"],
            "support_digest": subject["support_digest"],
            "artifact_names": list(subject["artifact_names"]),
        },
        "collection": {
            "destination": subject["destination"],
            "receipt_name": subject["receipt_name"],
            "receipt_sha256": subject["receipt_sha256"],
            "state": "COMPLETE",
            "delivery_verified": True,
            "worker_terminal_proof": True,
            "request_sha256": subject["request_sha256"],
            "response_sha256": subject["response_sha256"],
            "stdout": dict(subject["stdout"]),
            "process_sha256": subject["process_sha256"],
            "returncode": 0,
            "artifact_manifest_sha256": subject["artifact_manifest_sha256"],
            "collection_files_sha256": subject["collection_files_sha256"],
            "files": [dict(item) for item in subject["files"]],
            "artifacts": [dict(item) for item in subject["artifacts"]],
        },
        "adjudication": {
            "verdict": adjudication["verdict"],
            "by": adjudication["by"],
            "adjudication_sha256": adjudication["adjudication_sha256"],
            "record": record.decode("utf-8"),
        },
        "recorded_at": int(time.time()),
    }
    collection_quality_validate_attestation(row)
    return row


def _collection_quality_facts(row):
    """Every substantive fact; only the observation timestamp may differ."""
    return json.dumps({k: v for k, v in row.items() if k != "recorded_at"},
                      sort_keys=True, allow_nan=False)


def _collection_quality_raw(chain, name):
    """Bounded same-owner read of one sidecar link; None when absent."""
    import artifact_delivery as delivery
    try:
        return delivery.read_local_at(chain, name, COLLECTION_QUALITY_MAX_BYTES)
    except FileNotFoundError:
        return None


def _collection_quality_row(chain, name):
    """Parse one sidecar link; ("UNREADABLE"/"UNRELATED", raw) when not one."""
    raw = _collection_quality_raw(chain, name)
    if raw is None:
        return None
    try:
        row = _strict_json(raw.decode("utf-8"))
    except ValueError:
        return "UNREADABLE", raw
    if type(row) is not dict or row.get("schema") != COLLECTION_QUALITY_SCHEMA:
        return "UNRELATED", raw
    return row, raw


def _collection_quality_invalidate(handle):
    """Invalidate ONLY the inode this call created, through the retained FD.

    Truncation through the held descriptor reaches exactly the staged inode
    that was opened and identity-verified as our own creation — never a
    pathname, and never a confirmed or replaced inode that some other
    publication may own at either name.
    """
    if handle is None:
        return
    try:
        os.ftruncate(handle, 0)
        os.fsync(handle)
    except OSError:
        # The refused publication already fails closed; an invalidated inode
        # that could not be re-fsynced stays non-positive on any readback.
        pass


def _collection_quality_publish_locked(chain, name, pending, attestation, raw, reverify):
    """Publish under the held ledger lock through the incumbent link mechanics."""
    import artifact_delivery as delivery
    facts = _collection_quality_facts(attestation)
    existing = _collection_quality_row(chain, name)
    if existing is not None:
        row, _existing_raw = existing
        if type(row) is str:
            # The canonical name is occupied by bytes that are not a quality
            # attestation (unreadable or unrelated). It is never overwritten
            # and never fabricated into a positive; readback reports it.
            raise CollectionQualityConflict("collection_quality_unrelated_canonical_file")
        if _collection_quality_facts(row) == facts:
            return {"state": "RECORDED", "idempotent": True}
        raise CollectionQualityConflict("collection_quality_conflict_existing_attestation")
    if _collection_quality_raw(chain, pending) is not None:
        # A staged publication is retained evidence of an unconfirmed attempt.
        # It is never deleted, truncated, overwritten or blindly retried.
        raise CollectionQualityAmbiguous("collection_quality_staged_publication_retained")
    created = delivery.write_exclusive(chain.fd, pending, raw)
    handle = None
    owned = False
    try:
        handle = os.open(pending, os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=chain.fd)
        if delivery.inode(os.fstat(handle)) != created:
            raise ValueError("collection_quality_stage_substituted")
        owned = True
        if delivery.read_local_at(chain, pending, COLLECTION_QUALITY_MAX_BYTES) != raw:
            raise ValueError("collection_quality_stage_integrity")
        chain.verify()
        # Retained-descriptor revalidation of every qualified input BEFORE the
        # link; the same check runs again after the link and durable fsync.
        reverify()
        try:
            os.link(pending, name, src_dir_fd=chain.fd, dst_dir_fd=chain.fd,
                    follow_symlinks=False)
        except FileExistsError:
            # A concurrent publisher won this run's canonical name. Its exact
            # bytes decide; ours are never substituted or silently accepted,
            # and our own staged inode is retained exactly as written.
            winner = _collection_quality_row(chain, name)
            if (winner is not None and type(winner[0]) is dict
                    and _collection_quality_facts(winner[0]) == facts):
                return {"state": "RECORDED", "idempotent": True}
            raise CollectionQualityConflict(
                "collection_quality_conflict_concurrent_attestation")
        os.fsync(chain.fd)
        if (delivery.inode(os.stat(name, dir_fd=chain.fd, follow_symlinks=False)) != created
                or delivery.inode(os.stat(pending, dir_fd=chain.fd,
                                          follow_symlinks=False)) != created):
            raise ValueError("collection_quality_inode_changed")
        if delivery.read_local_at(chain, name, COLLECTION_QUALITY_MAX_BYTES) != raw:
            raise ValueError("collection_quality_readback_mismatch")
        reverify()
        chain.verify()
        if (delivery.inode(os.stat(name, dir_fd=chain.fd, follow_symlinks=False)) != created
                or delivery.inode(os.stat(pending, dir_fd=chain.fd,
                                          follow_symlinks=False)) != created):
            raise ValueError("collection_quality_inode_changed")
        if delivery.read_local_at(chain, name, COLLECTION_QUALITY_MAX_BYTES) != raw:
            raise ValueError("collection_quality_readback_mismatch")
        return {"state": "RECORDED", "idempotent": False}
    except CollectionQualityRefused:
        # Deterministic refusals (won/conflicting attestations) keep the
        # staged evidence exactly as written for same-owner reconciliation.
        raise
    except BaseException:
        # Any verification failure before an acknowledged durable result —
        # source revalidation, fsync, identity, readback — invalidates the one
        # inode this call created. The canonical positive can no longer be
        # fabricated from a failed publication, and the retained pending name
        # keeps refusing blind retries.
        _collection_quality_invalidate(handle if owned else None)
        raise
    finally:
        if handle is not None:
            os.close(handle)


def _collection_quality_publish_owner(collector, rid, root, parent, binding_path,
                                      receipt_path, receipt_sha256, adjudication_file):
    """Qualify, adjudicate, attest and link under the held ledger lock."""
    import artifact_delivery as delivery
    state_dir = _collection_quality_state_dir()
    name = rid + COLLECTION_QUALITY_SUFFIX
    pending = rid + COLLECTION_QUALITY_PENDING_SUFFIX
    with collector.retained_collection_quality(
            binding_path, collection_receipt=receipt_path,
            expected_sha256=receipt_sha256, run_id=rid, root=root, parent=parent,
            adjudication_path=adjudication_file) as qualified:
        subject = qualified.subject
        adjudication = collector.quality_adjudication(qualified.adjudication_raw,
                                                      subject=subject)
        attestation = collection_quality_attestation(
            run_id=rid, root=root, parent=parent, subject=subject,
            adjudication=adjudication, adjudication_record=qualified.adjudication_raw)
        raw = (json.dumps(attestation, sort_keys=True, separators=(",", ":"),
                          allow_nan=False) + "\n").encode("utf-8")
        if len(raw) > COLLECTION_QUALITY_MAX_BYTES:
            raise CollectionQualityRefused("collection_quality_attestation_limit")
        with delivery.DirectoryChain(state_dir) as chain:
            published = _collection_quality_publish_locked(
                chain, name, pending, attestation, raw, qualified.reverify)
    outcome = {"schema": COLLECTION_QUALITY_SCHEMA, "run_id": rid,
               "path": str(state_dir / name),
               "collected_source_quality": attestation["collected_source_quality"],
               "quality_by": attestation["quality_by"]}
    outcome.update(published)
    outcome["attestation_sha256"] = hashlib.sha256(raw).hexdigest()
    return outcome


def publish_collection_quality(*, run_id, root, parent, binding, collection,
                               receipt_sha256, adjudication_path):
    """Owner publication of one collected-source quality attestation sidecar.

    Owner API only: callers pass original-operation paths — the retained
    source binding, the collection receipt with its expected SHA-256, and the
    owned closed adjudication file — plus the original run/root/parent scope.
    The original-caller guard runs before any input read or write. Under the
    existing ledger.jsonl.lock this owner re-derives the qualified subject
    from the actual retained evidence, reads and closes the adjudication over
    it, builds the attestation, and publishes through the incumbent exclusive-
    create/fsync/link/readback mechanics. Raw subject or adjudication
    dictionaries and optional verification callbacks are refused: a
    shape-valid caller can never publish, and a facade only forwards paths.
    Publication is idempotent for an exact existing attestation and an
    explicit conflict for any differing subject. Zero ledger.jsonl writes: no
    terminal, outcome, acceptance or result row is ever produced here.
    """
    rid = _collection_quality_scope(run_id, root, parent)
    if (not isinstance(binding, (str, os.PathLike))
            or not isinstance(collection, (str, os.PathLike))
            or not isinstance(adjudication_path, (str, os.PathLike))
            or type(receipt_sha256) is not str
            or re.fullmatch(r"[0-9a-f]{64}", receipt_sha256) is None):
        raise CollectionQualityRefused("collection_quality_input_invalid")
    collector = _collection_quality_collector()
    # Original-caller agreement guard BEFORE any input read or write.
    collector.quality_caller_guard(root, parent)
    binding_path = os.fspath(binding)
    receipt_path = os.fspath(collection)
    adjudication_file = os.fspath(adjudication_path)
    os.makedirs(LEDGER_DIR, exist_ok=True)
    lock_path = LEDGER_PATH + ".lock"
    lock_handle = _strict_open(lock_path, os.O_RDWR | os.O_CREAT, "r+")
    with lock_handle as lock_fh:
        fcntl.flock(lock_fh.fileno(), fcntl.LOCK_EX)
        try:
            _strict_identity(lock_fh, lock_path)
            outcome = _collection_quality_publish_owner(
                collector, rid, root, parent, binding_path, receipt_path,
                receipt_sha256, adjudication_file)
            _strict_identity(lock_fh, lock_path)
        finally:
            fcntl.flock(lock_fh.fileno(), fcntl.LOCK_UN)
    return outcome


def _collection_quality_requalified(collector, rid, root, parent, subject):
    """Bind one validated attestation to the actual retained collection now.

    The only binding reference is the original collection's own ALREADY
    VERIFIED copy at <attested destination>/binding.json — the exact copy whose
    digest the collection receipt binds in its files list. No owner state path
    is invented and no caller path is trusted: a legitimate publication whose
    binding lived outside the owner state directory still re-qualifies, while
    a tampered copy, a tampered original source pin or a diverged subject
    leaves the row UNQUALIFIED — never a positive projection. The incumbent
    binding owner (load_binding with its original source pins and the
    full-hash-qualified producer validator) reproves the same original
    operation through that copy, and nothing here mutates the original
    operation or retries a publication.
    """
    destination = os.fspath(subject["destination"])
    if not destination.startswith("/") or ".." in destination.split("/"):
        return "UNQUALIFIED", "collection_quality_subject_destination_invalid"
    binding_path = os.path.join(destination, "binding.json")
    receipt_path = os.path.join(destination, subject["receipt_name"])
    try:
        with collector.retained_collection_quality(
                binding_path, collection_receipt=receipt_path,
                expected_sha256=subject["receipt_sha256"],
                run_id=rid, root=root, parent=parent) as qualified:
            if qualified.subject != subject:
                return "UNQUALIFIED", "collection_quality_subject_diverged"
    except (OSError, ValueError, TypeError, KeyError, RecursionError) as error:
        detail = getattr(error, "reason", None)
        if not (type(detail) is str
                and re.fullmatch(r"[a-z0-9_]{3,64}", detail) is not None):
            detail = type(error).__name__
        return "UNQUALIFIED", "collection_quality_evidence_" + detail
    return None, None


def _collection_quality_stat_identity(info):
    """Full held-inode identity, the fields the retained readers compare.

    Device, inode, size, both times, mode, owner and link count, so a
    same-bytes replacement, a truncation, a permission mutation or a path
    swap can never masquerade as the inode this readback opened.
    """
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns,
            info.st_ctime_ns, info.st_mode, info.st_uid, info.st_nlink)


def _collection_quality_inspection_lock():
    """Hold the SAME incumbent publisher lock shared and non-blocking.

    Every publication holds ledger.jsonl.lock exclusively from before any
    input read until its link, fsync, readback and revalidation are done, so
    a held shared hold proves the canonical names are stable for this whole
    inspection. The lock is opened read-only WITHOUT O_CREAT through the
    owner's strict same-owner primitive: inspection never creates the lock,
    its directory or any state, and never turns a missing lock into a new
    control plane. Acquisition is LOCK_SH|LOCK_NB with bounded zero wait — a
    busy incumbent lock raises BlockingIOError (a publication may be inside
    its window), a missing lock raises FileNotFoundError, and a replaced,
    foreign-owned or unsafe lock raises the owner's ValueError.
    """
    lock_path = LEDGER_PATH + ".lock"
    handle = _strict_open(lock_path, os.O_RDONLY, "r")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_SH | fcntl.LOCK_NB)
        _strict_identity(handle, lock_path)
    except BaseException:
        handle.close()
        raise
    return handle


def _collection_quality_retained_raw(chain, name):
    """Open-and-hold the canonical link, then read it through the owner reader.

    Returns (raw, holder) with the original descriptor held open, or
    (None, None) when the name is absent. The holder keeps the descriptor,
    its name, the held chain and the full identity captured before the owner
    read, so the visible path can be re-proved to be the SAME inode with the
    SAME bytes, ownership, mode and link count after qualification. The
    incumbent read_local_at stays the only byte reader.
    """
    import artifact_delivery as delivery
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                     dir_fd=chain.fd)
    except FileNotFoundError:
        return None, None
    try:
        held = os.fstat(fd)
        if (not stat.S_ISREG(held.st_mode) or held.st_uid != os.getuid()
                or held.st_mode & 0o022):
            raise ValueError("collection_quality_canonical_changed")
        identity = _collection_quality_stat_identity(held)
        if identity != _collection_quality_stat_identity(
                os.stat(name, dir_fd=chain.fd, follow_symlinks=False)):
            raise ValueError("collection_quality_canonical_changed")
        raw = delivery.read_local_at(chain, name, COLLECTION_QUALITY_MAX_BYTES)
        if identity != _collection_quality_stat_identity(os.fstat(fd)):
            raise ValueError("collection_quality_canonical_changed")
    except BaseException:
        os.close(fd)
        raise
    return raw, (fd, name, chain, identity)


def _collection_quality_retained_verify(holder, raw):
    """Re-prove the held canonical inode after qualification, before positive.

    The descriptor held since before validation must still carry its captured
    full identity — the canonical row cannot have been truncated, re-permis-
    sioned or rewritten in place — the visible canonical name must still
    resolve to that same inode through the held directory chain (a same-bytes
    replacement, a symlink or any path swap refuses), and the canonical bytes
    must read back identical through the incumbent owner reader.
    """
    import artifact_delivery as delivery
    fd, name, chain, identity = holder
    chain.verify()
    current = os.fstat(fd)
    if (_collection_quality_stat_identity(current) != identity
            or not stat.S_ISREG(current.st_mode) or current.st_uid != os.getuid()):
        raise ValueError("collection_quality_canonical_changed")
    if (_collection_quality_stat_identity(
            os.stat(name, dir_fd=chain.fd, follow_symlinks=False)) != identity):
        raise ValueError("collection_quality_canonical_changed")
    if delivery.read_local_at(chain, name, COLLECTION_QUALITY_MAX_BYTES) != raw:
        raise ValueError("collection_quality_canonical_changed")
    return True


def read_collection_quality(run_id, *, root, parent):
    """Guarded closed readback of one quality sidecar. Never mutates anything.

    Only a confirmed canonical link whose complete attestation validates
    closed AND whose attested collection still re-qualifies from the canonical
    owned references counts as RECORDED. A staged or ambiguous publication is
    reported exactly as retained; nothing is retried or cleaned.

    The whole inspection is serialized on the SAME incumbent ledger.jsonl.lock
    every publication holds exclusively: the caller guard runs before any IO,
    then the existing lock is opened read-only WITHOUT O_CREAT and held
    LOCK_SH|LOCK_NB with bounded zero wait. A busy lock reports the explicit
    non-positive PUBLICATION_IN_PROGRESS without reading a byte, so a
    publication paused anywhere inside its window is never projected positive;
    an absent lock is the precise non-positive NOT_RECORDED (a new confirmed
    record requires an existing publisher lock, and inspection never creates
    one); a replaced or unsafe lock is refused. The canonical link is held
    open from its first strict read through the complete closed validation and
    evidence re-qualification and is re-proved to be the same inode with the
    same bytes, ownership, mode and link count afterwards, so a canonical row
    replaced or invalidated while its evidence is re-qualified is reported
    UNQUALIFIED as changed, never a stale positive.
    """
    rid = _collection_quality_scope(run_id, root, parent)
    collector = _collection_quality_collector()
    # Guarded scope BEFORE any IO: a foreign, child or mismatched scope is
    # refused without reading a byte, and labels alone never authenticate.
    collector.quality_caller_guard(root, parent)
    import artifact_delivery as delivery
    state_dir = _collection_quality_state_dir()
    result = {"schema": COLLECTION_QUALITY_SCHEMA, "run_id": rid,
              "root": root, "parent": parent}
    lock = None
    chain = None
    holder = None
    try:
        try:
            lock = _collection_quality_inspection_lock()
        except BlockingIOError:
            # A publisher holds the incumbent lock: its link/readback window
            # is unconfirmed. Explicit non-positive, bounded zero wait, and
            # no sidecar IO at all — never a mid-flight positive.
            result["state"] = "PUBLICATION_IN_PROGRESS"
            result["reason"] = "collection_quality_publisher_lock_busy"
            return result
        except FileNotFoundError:
            # No publication ever created the incumbent lock for this ledger
            # configuration, so no record can be confirmed here. Reported
            # precisely; the lock is never created or substituted.
            result["state"] = "NOT_RECORDED"
            result["reason"] = "collection_quality_publisher_lock_absent"
            return result
        chain = delivery.DirectoryChain(state_dir)
        canonical_name = rid + COLLECTION_QUALITY_SUFFIX
        try:
            canonical_raw, holder = _collection_quality_retained_raw(
                chain, canonical_name)
        except ValueError as error:
            if not (error.args
                    and error.args[0] == "collection_quality_canonical_changed"):
                raise
            # The canonical link changed inside its own strict read window:
            # reported changed, never a positive, and never rewritten here.
            result["state"] = "UNQUALIFIED"
            result["reason"] = "collection_quality_canonical_changed"
            return result
        staged_raw = _collection_quality_raw(
            chain, rid + COLLECTION_QUALITY_PENDING_SUFFIX)
        if canonical_raw is None and staged_raw is None:
            result["state"] = "NOT_RECORDED"
            return result
        result["staged_retained"] = staged_raw is not None
        if canonical_raw is None:
            result["state"] = "STAGED_UNPUBLISHED"
            result["staged_sha256"] = hashlib.sha256(staged_raw).hexdigest()
            try:
                staged = _strict_json(staged_raw.decode("utf-8"))
                if (isinstance(staged, dict)
                        and staged.get("schema") == COLLECTION_QUALITY_SCHEMA):
                    result["staged_schema"] = COLLECTION_QUALITY_SCHEMA
            except ValueError:
                result["staged_schema"] = "UNREADABLE"
            return result
        result["attestation_sha256"] = hashlib.sha256(canonical_raw).hexdigest()
        try:
            row = _strict_json(canonical_raw.decode("utf-8"))
        except ValueError:
            result["state"] = "CANONICAL_UNREADABLE"
            return result
        if type(row) is not dict or row.get("schema") != COLLECTION_QUALITY_SCHEMA:
            result["state"] = "CANONICAL_UNRELATED"
            return result
        try:
            subject = collection_quality_subject_projection(row)
        except CollectionQualityRefused as error:
            result["state"] = "UNQUALIFIED"
            result["reason"] = (error.args[0] if error.args
                                else "collection_quality_attestation_invalid")
            return result
        if subject["run_id"] != rid or subject["root"] != root or subject["parent"] != parent:
            # The guarded caller scope must be the attested scope; a different
            # parent or root claim never projects another run's row as positive.
            result["state"] = "UNQUALIFIED"
            result["reason"] = "collection_quality_scope_mismatch"
            return result
        state, reason = _collection_quality_requalified(collector, rid, root, parent,
                                                        subject)
        if state is not None:
            result["state"] = state
            result["reason"] = reason
            return result
        try:
            _collection_quality_retained_verify(holder, canonical_raw)
        except ValueError as error:
            # The canonical row did not survive unchanged through its own
            # qualification: an explicit changed refusal — never the stale
            # positive read before the replacement.
            result["state"] = "UNQUALIFIED"
            result["reason"] = (error.args[0] if error.args
                                else "collection_quality_canonical_changed")
            return result
        result["state"] = "RECORDED"
        result["attestation"] = row
        result["collected_source_quality"] = row["collected_source_quality"]
        result["quality_by"] = row["quality_by"]
        return result
    finally:
        # Every handle and chain is closed on every path, including refusals.
        if holder is not None:
            os.close(holder[0])
            holder = None
        if chain is not None:
            chain.close()
            chain = None
        if lock is not None:
            lock.close()
            lock = None



if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="pool_ledger: append or query")
    sub = parser.add_subparsers(dest="cmd")

    p_append = sub.add_parser("append", help="append a record")
    p_append.add_argument("--strict", action="store_true",
                          help="require durable append; return 74 on storage failure")
    p_append.add_argument("--pool", required=True)
    p_append.add_argument("--key", default="-")
    p_append.add_argument("--window-id", default=None)
    p_append.add_argument("--task-class", default="unknown")
    p_append.add_argument("--job-class", default=None,
                          help="real task class: execute|review|heal|audit|census (R22)")
    p_append.add_argument("--rc", type=int, default=0)
    p_append.add_argument("--tokens", type=int, default=None)
    p_append.add_argument("--signal", default="ok")
    p_append.add_argument("--reason", default=None)
    p_append.add_argument("--run-id", default=None)
    p_append.add_argument("--accepted-by", default=None,
                          choices=["deterministic", "reviewer", "none"])
    p_append.add_argument("--review-rejected", action="store_true")
    p_append.add_argument("--scope-violation", action="store_true")
    p_append.add_argument("--retries", type=int, default=None)
    p_append.add_argument("--escalated", action="store_true")
    p_append.add_argument("--wall-s", type=float, default=None)
    p_append.add_argument("--model", default=None)
    p_append.add_argument("--root-id", default=None)
    p_append.add_argument("--parent-run-id", default=None)
    p_append.add_argument("--escalation-reason", default=None)
    p_append.add_argument("--input-tokens", type=int, default=None)
    p_append.add_argument("--cached-tokens", type=int, default=None)
    p_append.add_argument("--output-tokens", type=int, default=None)
    p_append.add_argument("--usage-source", default=None)

    sub.add_parser("last-402", help="show last 402/429 per pool")
    sub.add_parser("glm-burn", help="R26 GLM credit burn (5h + weekly + state)")
    p_cal = sub.add_parser("glm-calibrate", help="calibrate GLM burn to dashboard")
    p_cal.add_argument("--dashboard-5h", type=float, required=True)
    p_cal.add_argument("--reset-5h", required=True)
    p_cal.add_argument("--observed-at", required=True)
    p_cal.add_argument("--dashboard-week", type=float, default=None)
    p_cal.add_argument("--reset-week", default=None)

    p_recent = sub.add_parser("recent", help="show recent records")
    p_recent.add_argument("--pool", default=None)
    p_recent.add_argument("--limit", type=int, default=20)

    p_out = sub.add_parser("outcome", help="append after-the-fact outcome for a run_id")
    p_out.add_argument("--strict", action="store_true",
                       help="require durable same-run acknowledgement; failure may have written")
    p_out.add_argument("run_id")
    p_out.add_argument("--accepted-by", default="none",
                       choices=["deterministic", "reviewer", "none"])
    p_out.add_argument("--review-rejected", action="store_true")
    p_out.add_argument("--scope-violation", action="store_true")
    p_out.add_argument("--retries", type=int, default=0)
    p_out.add_argument("--escalated", action="store_true")
    p_out.add_argument("--tokens", type=int, default=None)
    p_out.add_argument("--wall-s", type=float, default=None)
    p_out.add_argument("--pool", default=None)
    p_out.add_argument("--task-class", default=None)
    p_out.add_argument("--job-class", default=None,
                       help="real task class: execute|review|heal|audit|census (R22)")
    p_out.add_argument("--model", default=None)

    p_stats = sub.add_parser("stats", help="R22 metrics per provider/model/class")
    p_stats.add_argument("--class", dest="task_class", default=None)

    args = parser.parse_args()

    if args.cmd == "append":
        published = append(
            pool=args.pool,
            key=args.key,
            window_id=args.window_id,
            task_class=args.task_class,
            job_class=args.job_class,
            rc=args.rc,
            tokens=args.tokens,
            signal=args.signal,
            reason=args.reason,
            root_id=args.root_id,
            parent_run_id=args.parent_run_id,
            escalation_reason=args.escalation_reason,
            run_id=args.run_id,
            accepted_by=args.accepted_by,
            review_rejected=args.review_rejected if args.accepted_by is not None else None,
            scope_violation=args.scope_violation if args.accepted_by is not None else None,
            retries=args.retries,
            escalated=args.escalated if args.accepted_by is not None else None,
            wall_s=args.wall_s,
            model=args.model,
            input_tokens=args.input_tokens,
            cached_tokens=args.cached_tokens,
            output_tokens=args.output_tokens,
            usage_source=args.usage_source,
            strict=args.strict,
        )
        if args.strict and not published:
            raise SystemExit(74)
    elif args.cmd == "last-402":
        for p, rec in last_402_429().items():
            print(f"{p}: {json.dumps(rec)}")
    elif args.cmd == "recent":
        for rec in read_recent(pool=args.pool, limit=args.limit):
            print(json.dumps(rec))
    elif args.cmd == "outcome":
        confirmed = record_outcome(
            run_id=args.run_id,
            accepted_by=args.accepted_by,
            review_rejected=args.review_rejected,
            scope_violation=args.scope_violation,
            retries=args.retries,
            escalated=args.escalated,
            tokens=args.tokens,
            wall_s=args.wall_s,
            pool=args.pool,
            task_class=args.task_class,
            job_class=args.job_class,
            model=args.model,
            strict=args.strict,
        )
        if args.strict and not confirmed:
            raise SystemExit(74)
    elif args.cmd == "stats":
        print_stats(task_class=args.task_class)
    elif args.cmd == "glm-burn":
        b = glm_burn()
        print(
            f"5h_credits={b['five_h_credits']:.2f} "
            f"5h_pro_rata_target={b.get('pro_rata_target_5h', 0):.2f} "
            f"weekly_credits={b['weekly_credits']:.2f} "
            f"cap_5h={b['cap_5h']} cap_week={b['cap_week']} "
            f"pct_5h={b['pct_5h']:.2f} pct_week={b['pct_week']:.2f} "
            f"source={b.get('quota_source', 'LOCAL_RECONSTRUCTION')} "
            f"observed_at={b.get('quota_observed_at', '-')} "
            f"state={b['state']} "
            f"raw_5h={b.get('raw_five_h_credits', 0):.2f} "
            f"calibration={_fmt_calibration(b)} "
            f"5h_reset={_fmt_reset(b.get('five_h_reset'))} "
            f"weekly_reset={_fmt_reset(b.get('weekly_reset'))}"
        )
    elif args.cmd == "glm-calibrate":
        try:
            reset = _parse_utc_arg(args.reset_5h)
            observed = _parse_utc_arg(args.observed_at)
            reset_week = (
                _parse_utc_arg(args.reset_week)
                if args.reset_week is not None else None
            )
        except ValueError:
            print("glm-calibrate: invalid ISO-8601 timestamp", file=sys.stderr)
            sys.exit(2)
        rc, estimate, factor = glm_calibrate(
            args.dashboard_5h, reset, observed,
            args.dashboard_week, reset_week,
        )
        if rc == 64:
            print(
                "glm-calibrate: observed-at must fall within [reset-5h, reset)",
                file=sys.stderr,
            )
            sys.exit(rc)
        if rc == 65:
            print(
                f"glm-calibrate: refused estimate={estimate:.2f} "
                f"factor={factor:.6f}",
                file=sys.stderr,
            )
            sys.exit(rc)
        state = _load_glm_window_state()
        print(
            f"estimate={estimate:.2f} dashboard={args.dashboard_5h:.2f} "
            f"factor={factor:.6f} "
            f"anchor={state.get('five_h_anchor_utc')} "
            f"reset={state.get('five_h_reset_utc')}"
        )
    else:
        parser.print_help()

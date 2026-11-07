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

"""Reconcile an original parent's prior rejection through the existing outcome owner.

This is not an attention writer, dispatcher or authentication service. The actual
assigned parent supplies authority and a previously qualified adjudication. Local
identity/proof checks narrow that authority; they do not authenticate a native user.
Sole-parent adjudication custody is required: the incumbent strict outcome writer
does not implement compare-and-set against the preceding status observation.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import importlib
import json
import os
from pathlib import Path
import re
import stat
import sys

ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")
SHA = re.compile(r"[0-9a-f]{64}\Z")


class ReconcileRefused(ValueError):
    pass


def owned_bytes(path, maximum=2 * 1024 * 1024):
    path = Path(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_uid != os.getuid()
                or before.st_mode & 0o022 or before.st_size > maximum):
            raise ReconcileRefused("unsafe evidence")
        data = b""
        while len(data) <= maximum:
            part = os.read(fd, min(65536, maximum + 1 - len(data)))
            if not part:
                break
            data += part
        after, visible = os.fstat(fd), path.lstat()
        identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mode,
                              s.st_uid, s.st_mtime_ns, s.st_ctime_ns)
        if (identity(before) != identity(after) or identity(after) != identity(visible)
                or len(data) != before.st_size):
            raise ReconcileRefused("evidence changed")
        return data
    finally:
        os.close(fd)


def validate_proof(proof, native_parent):
    fields = {"schema", "run_id", "root", "parent", "result_bytes", "result_sha256",
              "review_reason", "prior_adjudication_path", "prior_adjudication_sha256"}
    if (type(proof) is not dict or set(proof) != fields
            or proof["schema"] != "mastermind.fabric_prior_rejection.v1"
            or any(type(proof[k]) is not str or not ID.fullmatch(proof[k])
                   for k in ("run_id", "root", "parent"))
            or proof["root"] != proof["parent"] or proof["parent"] != native_parent
            or type(proof["result_bytes"]) is not int or not 0 < proof["result_bytes"] <= 1024*1024
            or any(type(proof[k]) is not str or not SHA.fullmatch(proof[k])
                   for k in ("result_sha256", "prior_adjudication_sha256"))
            or type(proof["review_reason"]) is not str or not 1 <= len(proof["review_reason"]) <= 2000
            or type(proof["prior_adjudication_path"]) is not str
            or not Path(proof["prior_adjudication_path"]).is_absolute()):
        raise ReconcileRefused("invalid original-parent adjudication")


def validate_history(document, proof):
    """Match actual adjudicated bytes, not merely an unrelated file's digest."""
    if (type(document) is not dict or document.get("root") != proof["root"]
            or document.get("parent") != proof["parent"]
            or type(document.get("outcomes")) is not list):
        raise ReconcileRefused("historical original parent mismatch")
    entries = [entry for entry in document["outcomes"]
               if type(entry) is dict and entry.get("run_id") == proof["run_id"]]
    if len(entries) != 1:
        raise ReconcileRefused("historical run missing or ambiguous")
    entry = entries[0]
    result = entry.get("result")
    if (entry.get("state") != "CONSUMED_NOT_ACCEPTED"
            or entry.get("accept_command_executed") is not False
            or entry.get("reason") != proof["review_reason"]
            or type(result) is not dict or type(result.get("bytes")) is not int
            or result["bytes"] != proof["result_bytes"]
            or result.get("sha256") != proof["result_sha256"]):
        raise ReconcileRefused("historical rejection does not match")


@contextmanager
def retained_receipt(path):
    """Hold the original directory through durable intent and outcome recording."""
    path = Path(path)
    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        original = os.fstat(directory)
        if (not stat.S_ISDIR(original.st_mode) or original.st_uid != os.getuid()
                or original.st_mode & 0o022):
            raise ReconcileRefused("unsafe receipt directory")
        def unchanged_directory():
            visible, held = path.parent.lstat(), os.fstat(directory)
            key = lambda s: (s.st_dev, s.st_ino, s.st_mode, s.st_uid)
            if key(original) != key(held) or key(held) != key(visible):
                raise ReconcileRefused("receipt directory changed")
        unchanged_directory()
        fd = os.open(path.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=directory)
        with os.fdopen(fd, "w") as receipt:
            original_file = os.fstat(receipt.fileno())
            def unchanged_receipt():
                held = os.fstat(receipt.fileno())
                visible = os.stat(path.name, dir_fd=directory, follow_symlinks=False)
                key = lambda s: (s.st_dev, s.st_ino, s.st_mode, s.st_uid, s.st_nlink)
                if (held.st_nlink != 1 or key(original_file) != key(held)
                        or key(held) != key(visible)):
                    raise ReconcileRefused("receipt file changed")
            def retain(value):
                unchanged_directory()
                unchanged_receipt()
                receipt.write(json.dumps(value, sort_keys=True) + "\n")
                receipt.flush()
                os.fsync(receipt.fileno())
                os.fsync(directory)
                unchanged_directory()
                unchanged_receipt()
            yield retain
    finally:
        os.close(directory)


def valid_status(status, proof, *, after=False):
    return (type(status) is dict
            and status.get("schema") == "mastermind.fabric_task_status.v1"
            and status.get("run_id") == proof["run_id"]
            and status.get("root_id") == proof["root"]
            and status.get("parent_run_id") == proof["parent"]
            and status.get("state") == "TERMINAL" and type(status.get("rc")) is int
            and status["rc"] == 0 and status.get("signal") == "ok"
            and status.get("result_available") is True
            and type(status.get("result_bytes")) is int
            and status["result_bytes"] == proof["result_bytes"]
            and status.get("accepted") is False
            and status.get("accepted_by") == ("none" if after else None)
            and status.get("acceptance_state") == "NOT_ACCEPTED"
            and status.get("acceptance_reason") == ("OUTCOME_NOT_ACCEPTED" if after else "NO_OUTCOME"))


def reconcile(proof, *, native_parent, status, write_outcome, record_intent):
    validate_proof(proof, native_parent)
    snapshots = [status(proof["run_id"]) for _ in range(2)]
    if snapshots[0] != snapshots[1] or not valid_status(snapshots[0], proof):
        raise ReconcileRefused("status is not the original unadjudicated terminal")
    record_intent({"state": "OUTCOME_WRITE_INTENT", "proof": proof, "status": snapshots[0]})
    acknowledged = write_outcome(proof["run_id"], accepted_by="none", review_rejected=True, strict=True)
    observed = status(proof["run_id"])
    confirmed = acknowledged is True and valid_status(observed, proof, after=True)
    return {"schema": "mastermind.fabric_rejection_reconcile_receipt.v1",
            "run_id": proof["run_id"], "root": proof["root"], "parent": proof["parent"],
            "state": "REJECTION_RECONCILED" if confirmed else "OUTCOME_ACKNOWLEDGEMENT_UNKNOWN",
            "strict_acknowledgement": acknowledged is True, "status": observed,
            "result_read": False, "attention_changed": False, "retry_authorized": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--proof", type=Path, required=True)
    parser.add_argument("--proof-sha256", required=True)
    parser.add_argument("--adapter", type=Path, required=True)
    parser.add_argument("--adapter-sha256", required=True)
    parser.add_argument("--ledger-sha256", required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args(argv)
    sha = lambda data: hashlib.sha256(data).hexdigest()
    raw = owned_bytes(args.proof)
    if sha(raw) != args.proof_sha256:
        raise ReconcileRefused("proof preimage changed")
    proof = json.loads(raw)
    validate_proof(proof, os.environ.get("CODEX_THREAD_ID"))
    if os.environ.get("POOL_ORCHESTRATOR_ID", proof["root"]) != proof["root"]:
        raise ReconcileRefused("inherited root mismatch")
    history = owned_bytes(proof["prior_adjudication_path"])
    if sha(history) != proof["prior_adjudication_sha256"]:
        raise ReconcileRefused("historical adjudication changed")
    validate_history(json.loads(history), proof)
    adapter = args.adapter.absolute()
    ledger = adapter.parent / "pool_ledger.py"
    if (adapter.name != "fabric_task.py" or sha(owned_bytes(adapter)) != args.adapter_sha256
            or sha(owned_bytes(ledger)) != args.ledger_sha256):
        raise ReconcileRefused("existing owner preimage changed")
    # An existing intent, including an interrupted write, prevents replay.
    with retained_receipt(args.receipt) as retain:
        retain({"state": "OWNER_PREFLIGHT", "proof_sha256": sha(raw)})
        sys.path.insert(0, str(adapter.parent))
        task = importlib.import_module("fabric_task")
        owner = importlib.import_module("pool_ledger")
        if (Path(task.__file__).absolute() != adapter or Path(owner.__file__).absolute() != ledger
                or sha(owned_bytes(adapter)) != args.adapter_sha256
                or sha(owned_bytes(ledger)) != args.ledger_sha256):
            raise ReconcileRefused("loaded owner changed")
        result = reconcile(proof, native_parent=os.environ.get("CODEX_THREAD_ID"),
                           status=task.inspect_run, write_outcome=owner.record_outcome,
                           record_intent=retain)
        retain(result)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["state"] == "REJECTION_RECONCILED" else 75


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"RECONCILIATION_REFUSED: {type(exc).__name__}", file=sys.stderr)
        raise SystemExit(75)

"""Read-only proof-gap audit for a bounded Mastermind mission snapshot.

Consumes selected, source-attributed observations already gathered from canonical
owners. The caller remains responsible for authenticating observations, freshness,
writer custody, and actual acceptance. This is NOT an Executive lifecycle, retry,
dispatch, credential, or finalization authority.

An optional ``lanes`` section additionally classifies the *claimed session exit*
against observed lane state: it separates lawful continuation after a lane-local
``WAITING_EXTERNAL`` from a mere status/checkpoint/CI-summary exit, and the lawful
all-lanes stop (or safety/effect-unknown fence) from a premature stop. These are
read-only classifications of supplied observations -- still no lifecycle, retry,
dispatch, credential, or finalization authority, and never served-model proof.

Run: python -m scripts.ohf.mission_exit_audit /path/to/snapshot.json
"""
from __future__ import annotations

import argparse
import json
import os
import re
import stat
import sys
from pathlib import Path
from typing import Any

from scripts.ohf.redaction import redact_evidence_text

SCHEMA = "mastermind.mission_exit_audit_input/v1"
OUTPUT_SCHEMA = "mastermind.mission_exit_audit_output/v1"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
PUBLIC_EFFECT_REF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,319}$")
MAX_SNAPSHOT_BYTES = 131072
REQUIREMENTS = (
    "accepted_worker_result",
    "source_implementation",
    "current_head_ci",
    "independent_source_review",
    "credential_owner_attestation",
    "governed_production_result",
)
OWNER = {
    "accepted_worker_result": "existing Fabric result/acceptance owner",
    "source_implementation": "existing source writer and GitHub",
    "current_head_ci": "GitHub Actions",
    "independent_source_review": "independent GitHub/Fabric reviewer",
    "credential_owner_attestation": "existing ProviderRealm credential owner",
    "governed_production_result": "Executive Job/Attempt and original parent",
}
ACTION = {
    "accepted_worker_result": "validate and accept the original immutable worker result",
    "source_implementation": "obtain lawful implementation and exact source readback",
    "current_head_ci": "run and inspect CI on the actual source head",
    "independent_source_review": "obtain a non-author review on the exact head",
    "credential_owner_attestation": "obtain private credential-owner issuer evidence",
    "governed_production_result": "observe an admitted Job/Attempt and parent-consumed result",
}
VALID_SCOPES = {"analysis", "implementation", "review", "none"}
VALID_RUN_STATES = {"NONE", "QUEUED", "STARTED", "TERMINAL", "UNKNOWN"}
VALID_EFFECTS = {"NONE", "SAFETY_DENIED", "PERMISSION_DENIED", "EFFECT_UNKNOWN"}
# Lane/exit-claim vocabulary (optional ``lanes`` snapshot section). States mirror
# the incumbent protected law: WAITING_EXTERNAL is lane-local (pending review,
# CI, capacity, or owner reply blocks only the dependent lane); SAFE_WORK_REMAINING
# marks an independent safe unblocked lane; BLOCKED_PROVEN requires exact current
# negative-capability evidence; FENCED is a safety-denied or effect-unknown hold
# that must be backed by this snapshot's held effect; DONE is verified/accepted.
VALID_LANE_STATES = {
    "DONE",
    "WAITING_EXTERNAL",
    "SAFE_WORK_REMAINING",
    "BLOCKED_PROVEN",
    "FENCED",
}
# CONTINUE keeps working the next safe unblocked lane in the same healthy turn.
# CHECKPOINT_SUMMARY_STOP claims a checkpoint/status/CI-summary exit; it is only
# lawful as a checkpointed continuation whose resume surface is a real accepted/
# started durable executor (a request, notification, delivery, or trigger is not
# that executor). WAIT_EXTERNAL_EXECUTOR claims ending solely to wait on such an
# executor. ALL_LANES_BLOCKED_STOP claims every scoped lane is proven blocked.
VALID_EXIT_CLAIMS = {
    "CONTINUE",
    "CHECKPOINT_SUMMARY_STOP",
    "WAIT_EXTERNAL_EXECUTOR",
    "ALL_LANES_BLOCKED_STOP",
}


class InvalidSnapshot(ValueError):
    """Invalid or incomplete evidence packet, not a proof of underlying failure."""


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise InvalidSnapshot(f"{label} must be an object")
    return value


def _bool(value: Any) -> bool:
    return type(value) is bool


def _sha(value: Any) -> bool:
    return isinstance(value, str) and SHA_RE.fullmatch(value) is not None


def _ref(value: Any) -> bool:
    return isinstance(value, str) and 1 <= len(value) <= 320 and "\n" not in value


def _public_effect_ref(value: Any) -> bool:
    """Only safe opaque identifiers may be reflected in output.

    This structural rule rejects private paths/control characters; the existing
    house sanitizer rejects credential-shaped values and exact env secrets.
    The source owner must supply an opaque ID, not a path, URL or secret.
    """
    return (
        _ref(value)
        and PUBLIC_EFFECT_REF_RE.fullmatch(value) is not None
        and any(c in value for c in (":", "-", "."))
        and all(len(part) <= 24 for part in re.split(r"[-.:]", value))
        and redact_evidence_text(value) == value
    )


def _true_and_ref(obj: dict[str, Any], flag: str, receipt: str) -> bool:
    return obj.get(flag) is True and _ref(obj.get(receipt))


def _audit_lanes(snapshot: dict[str, Any], effect_class: str) -> dict[str, Any]:
    """Classify the claimed session exit against observed lane state.

    Read-only discrimination over operator-collected observations, added 2026-11-02:
    a lane-local ``WAITING_EXTERNAL`` (pending review/CI/owner) never justifies a
    mission-wide stop while a safe independent lane remains; a checkpoint/status/
    CI-summary exit is not continuation unless its resume surface is a real
    accepted/started durable executor; an all-lanes stop is lawful only when every
    scoped lane carries proven blocks or a held safety/effect fence. Missing or
    malformed lane evidence fails closed. The returned flags never authorize any
    action and are never served-model behavioral proof.
    """
    lanes = _object(snapshot.get("lanes"), "lanes")
    items = lanes.get("items")
    if not isinstance(items, list) or not items or not all(isinstance(x, dict) for x in items):
        raise InvalidSnapshot("lanes.items must be a nonempty list of lane objects")
    states: list[str] = []
    seen_ids: set[str] = set()
    for item in items:
        lane_id = item.get("id")
        if not _ref(lane_id) or lane_id in seen_ids:
            raise InvalidSnapshot("lane ids must be unique bounded references")
        seen_ids.add(lane_id)
        state = item.get("state")
        if not isinstance(state, str) or state not in VALID_LANE_STATES:
            raise InvalidSnapshot("unknown lane state")
        if state == "FENCED" and effect_class == "NONE":
            raise InvalidSnapshot("fenced lane requires the snapshot's held effect")
        states.append(state)
    exit_claim = lanes.get("exit_claim")
    if not isinstance(exit_claim, str) or exit_claim not in VALID_EXIT_CLAIMS:
        raise InvalidSnapshot("unknown exit claim")
    durable_wait = False
    wait_executor = lanes.get("wait_executor")
    if wait_executor is not None:
        wait_executor = _object(wait_executor, "wait_executor")
        executor_ref = wait_executor.get("ref")
        if executor_ref is not None and not _ref(executor_ref):
            raise InvalidSnapshot("wait executor reference must be a bounded reference")
        started = wait_executor.get("started") is True
        if started and executor_ref is None:
            raise InvalidSnapshot("started wait executor requires a lawful return reference")
        durable_wait = started
    cycles = lanes.get("support_cycles_without_delta", 0)
    if type(cycles) is not int or cycles < 0:
        raise InvalidSnapshot("support_cycles_without_delta must be a nonnegative integer")

    waiting = states.count("WAITING_EXTERNAL") > 0
    safe_work = states.count("SAFE_WORK_REMAINING") > 0
    all_blocked = all(s in ("BLOCKED_PROVEN", "FENCED", "DONE") for s in states) and any(
        s in ("BLOCKED_PROVEN", "FENCED") for s in states
    )
    # Two support/status-only cycles without a capability delta or newly resolved
    # blocker are NO_DELTA_LOOP and force a changed tactic/lane plus a real
    # capability step before finalization. A truthful all-lanes-proven-blocked
    # state is the incumbent ALL_SCOPED_LANES_BLOCKED terminal, not a support loop.
    no_delta_loop = cycles >= 2 and not all_blocked
    stop_claim = exit_claim != "CONTINUE"
    checkpoint_continuation = durable_wait and not safe_work
    lawful_stop = (
        (exit_claim == "ALL_LANES_BLOCKED_STOP" and all_blocked)
        or (
            exit_claim in ("WAIT_EXTERNAL_EXECUTOR", "CHECKPOINT_SUMMARY_STOP")
            and checkpoint_continuation
        )
    )
    return {
        "lane_local_wait_blocks_only_its_lane": waiting and safe_work,
        "remaining_safe_work": safe_work,
        "all_lanes_proven_blocked": all_blocked,
        "no_delta_loop_forces_tactic_change": no_delta_loop,
        "status_summary_is_not_continuation": (
            exit_claim == "CHECKPOINT_SUMMARY_STOP" and not checkpoint_continuation
        ),
        "wait_requires_started_durable_executor": (
            exit_claim == "WAIT_EXTERNAL_EXECUTOR" and not durable_wait
        ),
        "premature_exit_detected": stop_claim and not lawful_stop,
    }


def audit(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Return bounded proof gaps, not permission to perform any action.

    Missing data fails closed. A success-shaped shell exit never suffices for an
    accepted result, source implementation, independent review, or production.
    """
    root = _object(snapshot, "snapshot")
    if root.get("schema") != SCHEMA:
        raise InvalidSnapshot("unsupported schema")
    mission = _object(root.get("mission"), "mission")
    worker = _object(root.get("worker"), "worker")
    source = _object(root.get("source"), "source")
    credential = _object(root.get("credential"), "credential")
    production = _object(root.get("production"), "production")
    effect = _object(root.get("effect"), "effect")
    req = mission.get("requires")
    if not isinstance(req, list) or not req or any(not isinstance(x, str) for x in req):
        raise InvalidSnapshot("mission.requires must be a nonempty list of known proof gates")
    if len(set(req)) != len(req) or any(x not in REQUIREMENTS for x in req):
        raise InvalidSnapshot("duplicate or unsupported proof requirement")
    worker_scope, worker_state = worker.get("scope"), worker.get("state")
    if (not isinstance(worker_scope, str) or worker_scope not in VALID_SCOPES
            or not isinstance(worker_state, str) or worker_state not in VALID_RUN_STATES):
        raise InvalidSnapshot("unknown worker scope/state")
    effect_class = effect.get("class")
    if not isinstance(effect_class, str) or effect_class not in VALID_EFFECTS:
        raise InvalidSnapshot("unknown effect class")
    if effect["class"] != "NONE":
        if not _public_effect_ref(effect.get("action_id")) or not _public_effect_ref(effect.get("carrier")):
            raise InvalidSnapshot("held action requires bounded exact action and carrier references")
        if effect.get("dispatched") is not None and not _bool(effect.get("dispatched")):
            raise InvalidSnapshot("effect.dispatched must be true, false or null")
    current_head = source.get("head")
    if not _sha(current_head):
        raise InvalidSnapshot("source.head must identify an exact commit")
    if worker.get("state") == "TERMINAL":
        if type(worker.get("exit_code")) is not int:
            raise InvalidSnapshot("terminal worker requires an integer exit code")
    elif worker.get("exit_code") is not None:
        raise InvalidSnapshot("nonterminal worker cannot claim exit code")

    checks = {
        "accepted_worker_result": (
            worker["state"] == "TERMINAL"
            and worker.get("exit_code") == 0
            and _true_and_ref(worker, "accepted", "acceptance_ref")
            and _ref(worker.get("result_ref"))
        ),
        "source_implementation": (
            _true_and_ref(source, "implementation_applied", "implementation_ref")
            and source.get("implementation_head") == current_head
            and source.get("implementation_scope_matched") is True
        ),
        "current_head_ci": (
            source.get("ci_conclusion") == "SUCCESS"
            and source.get("ci_head") == current_head
            and _ref(source.get("ci_run_ref"))
        ),
        "independent_source_review": (
            source.get("review_verdict") == "APPROVED"
            and source.get("review_head") == current_head
            and _ref(source.get("review_ref"))
            and _ref(source.get("author_id"))
            and _ref(source.get("reviewer_id"))
            and source.get("author_id") != source.get("reviewer_id")
        ),
        "credential_owner_attestation": (
            _true_and_ref(credential, "issuer_activation_verified", "issuer_evidence_ref")
            and _true_and_ref(credential, "owner_identified", "owner_ref")
        ),
        "governed_production_result": (
            _true_and_ref(production, "job_attempt_accepted", "job_attempt_ref")
            and _true_and_ref(production, "original_parent_consumed", "parent_consumption_ref")
            and _true_and_ref(production, "installed_generation_qualified", "generation_ref")
        ),
    }
    gaps = [
        {"requirement": key, "owner": OWNER[key], "next_proof": ACTION[key]}
        for key in REQUIREMENTS if key in req and not checks[key]
    ]
    held = []
    if effect["class"] != "NONE":
        held.append({
            "effect_class": effect["class"],
            "action_id": effect["action_id"],
            "carrier": effect["carrier"],
            "dispatched": effect.get("dispatched"),
            "instruction": (
                "reconcile only through original carrier; no replay or failover"
                if effect["class"] == "EFFECT_UNKNOWN" else
                "do not retry the denied action through any carrier"
            ),
        })
    # The caller must verify these observations against each canonical owner;
    # all green checks only mean the supplied packet is ready for adjudication.
    ready = not gaps and not held
    report = {
        "schema": OUTPUT_SCHEMA,
        "disposition": "READY_FOR_CANONICAL_ADJUDICATION" if ready else "INCOMPLETE",
        "checks_passed": [key for key in REQUIREMENTS if key in req and checks[key]],
        "gaps": gaps,
        "held_actions": held,
        "analysis_is_not_implementation": (
            worker["scope"] == "analysis" and not checks["source_implementation"]
        ),
        "terminal_exit_is_not_acceptance": (
            worker["state"] == "TERMINAL" and worker.get("exit_code") == 0
            and not checks["accepted_worker_result"]
        ),
        "source_write_authorized": False,
        "dispatch_authorized": False,
        "retry_authorized": False,
        "merge_authorized": False,
        "production_activation_authorized": False,
        "fresh_owner_readback_required": True,
    }
    # Exit-claim classification is additive: snapshots without a ``lanes`` section
    # keep the exact incumbent output contract (no lane flags ever appear).
    if root.get("lanes") is not None:
        report.update(_audit_lanes(root, effect["class"]))
    return report


def _read_snapshot(path: Path) -> str:
    """Bounded, identity-checked regular-file read; no FIFO/device/symlink open.

    Check file identity and metadata before/after a bounded read. These checks
    detect normal replacement/growth races; adversarial concurrent mutation of
    a privileged local filesystem remains outside this read-only tool's trust.
    """
    initial = path.lstat()
    if not stat.S_ISREG(initial.st_mode) or not 0 <= initial.st_size <= MAX_SNAPSHOT_BYTES:
        raise InvalidSnapshot("input is not a bounded regular file")
    nofollow = getattr(os, "O_NOFOLLOW", None)
    nonblock = getattr(os, "O_NONBLOCK", None)
    if nofollow is None or nonblock is None:
        raise InvalidSnapshot("safe input open unavailable")
    fd = os.open(path, os.O_RDONLY | nofollow | nonblock | getattr(os, "O_CLOEXEC", 0))
    try:
        opened = os.fstat(fd)
        if not stat.S_ISREG(opened.st_mode) or not 0 <= opened.st_size <= MAX_SNAPSHOT_BYTES:
            raise InvalidSnapshot("opened input is not a bounded regular file")
        if (initial.st_dev, initial.st_ino) != (opened.st_dev, opened.st_ino):
            raise InvalidSnapshot("input changed before open")
        chunks = []
        remaining = MAX_SNAPSHOT_BYTES + 1
        while remaining:
            chunk = os.read(fd, min(65536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        data = b"".join(chunks)
        after = os.fstat(fd)
        path_after = path.lstat()
        def identity(st):
            return st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns
        if (len(data) > MAX_SNAPSHOT_BYTES or len(data) != opened.st_size
                or identity(initial) != identity(opened)
                or identity(opened) != identity(after)
                or identity(after) != identity(path_after)):
            raise InvalidSnapshot("input changed during bounded read")
        return data.decode("utf-8")
    finally:
        os.close(fd)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only Mastermind mission-exit evidence audit")
    parser.add_argument("snapshot", type=Path, help="local JSON of canonical owner observations")
    args = parser.parse_args(argv)
    try:
        raw = _read_snapshot(args.snapshot)
        report = audit(json.loads(raw))
    except (OSError, ValueError, RecursionError):
        # Do not reflect error payloads or file paths, which could contain secrets.
        print(json.dumps({"schema": OUTPUT_SCHEMA, "disposition": "INPUT_UNVERIFIED", "error": "invalid_or_unreadable_snapshot"}))
        return 2
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0 if report["disposition"] == "READY_FOR_CANONICAL_ADJUDICATION" else 1


if __name__ == "__main__":
    sys.exit(main())

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
# Optional evidence-only lane classifier, NOT a new Executive lifecycle,
# admission, source authority, checkpoint registry, or retry controller.
VALID_LANE_STATES = {
    "DONE", "WAITING_EXTERNAL", "SAFE_WORK_REMAINING", "BLOCKED_PROVEN", "FENCED",
}
VALID_EXIT_CLAIMS = {
    "CONTINUE", "CHECKPOINT_SUMMARY_STOP", "CHECKPOINTED_CONTINUATION",
    "WAIT_EXTERNAL_EXECUTOR", "ALL_LANES_BLOCKED_STOP", "OWNER_HANDOFF_STOP",
}
VALID_CONTINUITY_REASONS = {
    "CONTEXT_PRESSURE", "SESSION_UNSTABLE", "SURFACE_TRANSITION",
    "NEXT_PHASE_EXCEEDS_LANDING_RESERVE",
}
# An old START receipt does not prove the executor remains live. These are
# read-only observations from the incumbent Job/Attempt or original carrier;
# only a currently observed STARTED/RUNNING state can support a worker-wait.
VALID_EXECUTOR_STATES = {
    "NONE", "QUEUED", "STARTED", "RUNNING",
    "TERMINAL", "FAILED", "CANCELED", "UNKNOWN",
}
ACTIVE_EXECUTOR_STATES = {"STARTED", "RUNNING"}



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


def _audit_lanes(snapshot: dict[str, Any], effect: dict[str, Any]) -> dict[str, Any]:
    """Evidence-bound diagnostic of a proposed session exit, never permission.

    WAITING_EXTERNAL blocks its own lane but not independent safe work. An
    actual verified checkpoint is distinct from a durable worker wait or a
    checkpoint/status summary. All-scoped-lanes-blocked requires source-linked
    evidence for every remaining lane. The canonical owners must still verify
    all supplied observations before acting.
    """
    lanes = _object(snapshot.get("lanes"), "lanes")
    items = lanes.get("items")
    if not isinstance(items, list) or not items or not all(isinstance(x, dict) for x in items):
        raise InvalidSnapshot("lanes.items must be a nonempty list of lane objects")
    states: list[str] = []
    seen_ids: set[str] = set()
    for item in items:
        lane_id = item.get("id")
        if not _public_effect_ref(lane_id) or lane_id in seen_ids:
            raise InvalidSnapshot("lane ids must be unique opaque source references")
        seen_ids.add(lane_id)
        state = item.get("state")
        if not isinstance(state, str) or state not in VALID_LANE_STATES:
            raise InvalidSnapshot("unknown lane state")
        if state in ("WAITING_EXTERNAL", "BLOCKED_PROVEN"):
            if (
                not _public_effect_ref(item.get("blocker_ref"))
                or not _public_effect_ref(item.get("blocker_owner_ref"))
                or item.get("blocker_observed") is not True
            ):
                raise InvalidSnapshot("blocked lane lacks attributed current evidence")
            if state == "BLOCKED_PROVEN" and item.get("negative_capability_verified") is not True:
                raise InvalidSnapshot("proven blocker lacks negative-capability evidence")
        elif state == "FENCED":
            if (
                effect.get("class") == "NONE"
                or item.get("effect_action_id") != effect.get("action_id")
                or item.get("effect_carrier") != effect.get("carrier")
            ):
                raise InvalidSnapshot("fenced lane is not bound to original held effect")
        elif state == "DONE":
            if not _public_effect_ref(item.get("completion_ref")):
                raise InvalidSnapshot("done lane lacks source acceptance reference")
        else:
            if not _public_effect_ref(item.get("next_action_ref")):
                raise InvalidSnapshot("ready lane lacks concrete next-action reference")
        states.append(state)

    exit_claim = lanes.get("exit_claim")
    if not isinstance(exit_claim, str) or exit_claim not in VALID_EXIT_CLAIMS:
        raise InvalidSnapshot("unknown exit claim")
    cycles = lanes.get("support_cycles_without_delta", 0)
    if type(cycles) is not int or cycles < 0:
        raise InvalidSnapshot("support cycles must be a nonnegative integer")

    # An owner name or requested reviewer is not a successor receipt. A
    # purported handoff without an actual current receiver/continuation is
    # always a premature exit, even when other lanes are waiting.
    owner_handoff_stop = exit_claim == "OWNER_HANDOFF_STOP"

    # A started worker is relevant only when bound to a specific waiting lane.
    # Canonical blocker/owner evidence is validated above; the caller still
    # authenticates that readback from the actual existing owner.
    waiting_lanes = {
        row["id"]: row for row in items if row["state"] == "WAITING_EXTERNAL"
    }
    # Started/running durable execution needs an exact original owner readback
    # and a real return/wake path. A request ID, delivery or watcher alone is
    # not proof of execution, and cannot legalize a checkpoint summary.
    wait_executor = lanes.get("wait_executor")
    durable_wait = False
    if wait_executor is not None:
        wait_executor = _object(wait_executor, "wait_executor")
        started = wait_executor.get("started", False)
        if type(started) is not bool:
            raise InvalidSnapshot("wait executor started must be boolean")
        if started:
            if (
                not _public_effect_ref(wait_executor.get("ref"))
                or not _public_effect_ref(wait_executor.get("return_path_ref"))
                or wait_executor.get("owner_observed") is not True
            ):
                raise InvalidSnapshot("started executor lacks original owner/return proof")
            lane_id = wait_executor.get("lane_id")
            if lane_id is not None and not _public_effect_ref(lane_id):
                raise InvalidSnapshot("wait executor lane ID is invalid")
            current_state = wait_executor.get("state")
            if current_state is not None and (
                type(current_state) is not str
                or current_state not in VALID_EXECUTOR_STATES
            ):
                raise InvalidSnapshot("unknown current executor state")
            live_state = current_state in ACTIVE_EXECUTOR_STATES
            if live_state and (
                not _public_effect_ref(wait_executor.get("state_ref"))
                or wait_executor.get("state_observed") is not True
            ):
                raise InvalidSnapshot("active executor state lacks current owner readback")
            waiting_lane = waiting_lanes.get(lane_id)
            if waiting_lane is not None:
                # Usually the blocker ref identifies the awaited run itself.
                # If it is a separate receipt, the lane must carry a bound
                # executor ref and its own source-attributed binding evidence.
                related_ref = waiting_lane.get("executor_ref")
                if related_ref is None:
                    related_ref = waiting_lane["blocker_ref"]
                elif (
                    not _public_effect_ref(related_ref)
                    or not _public_effect_ref(waiting_lane.get("executor_binding_ref"))
                    or waiting_lane.get("executor_binding_observed") is not True
                ):
                    raise InvalidSnapshot("waiting lane executor binding is unverified")
                durable_wait = live_state and wait_executor["ref"] == related_ref
            # A missing, terminal, queued, failed, foreign or unrelated run
            # is not an active executor for this mission, even if a historical
            # START and a valid return path are present.
        elif wait_executor.get("ref") is not None and not _public_effect_ref(wait_executor.get("ref")):
            raise InvalidSnapshot("invalid wait executor reference")

    # CHECKPOINTED_CONTINUATION requires genuinely observed risk, committed
    # cumulative source and coherent resume. It does NOT require a running
    # executor and can be valid with remaining safe work if context pressure
    # genuinely prevents a safe in-session next phase.
    checkpoint = lanes.get("checkpoint")
    checkpoint_proven = False
    if checkpoint is not None:
        checkpoint = _object(checkpoint, "checkpoint")
        revision = checkpoint.get("revision")
        reason = checkpoint.get("continuity_reason")
        checkpoint_proven = (
            checkpoint.get("persisted") is True
            and _public_effect_ref(checkpoint.get("receipt_ref"))
            and isinstance(revision, str)
            and re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", revision) is not None
            and isinstance(reason, str)
            and reason in VALID_CONTINUITY_REASONS
            and checkpoint.get("observed_continuity_risk") is True
            and _public_effect_ref(checkpoint.get("next_action_ref"))
            and _public_effect_ref(checkpoint.get("resume_surface_ref"))
            and checkpoint.get("effects_accounted") is True
            and checkpoint.get("custody_preserved") is True
            and checkpoint.get("mission_complete") is False
        )

    # A list of blocked entries cannot prove the absence of omitted ready
    # actions. Require an independently source-attributed, complete scoped
    # inventory before this read-only diagnostic accepts a mission-wide stop.
    # The caller still must authenticate this source against its canonical owner.
    scope_coverage = False
    scope = lanes.get("scope_evidence")
    if scope is not None:
        scope = _object(scope, "scope_evidence")
        revision = scope.get("source_revision")
        canonical_ids = scope.get("canonical_lane_ids")
        if (
            not _public_effect_ref(scope.get("source_ref"))
            or not _public_effect_ref(scope.get("owner_readback_ref"))
            or not isinstance(revision, str)
            or re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", revision) is None
            or scope.get("source_observed") is not True
            or scope.get("all_dependencies_checked") is not True
            or not isinstance(canonical_ids, list)
            or not canonical_ids
            or len(canonical_ids) > 128
            or any(not _public_effect_ref(i) for i in canonical_ids)
            or len(set(canonical_ids)) != len(canonical_ids)
        ):
            raise InvalidSnapshot("scope coverage lacks current canonical owner evidence")
        if set(canonical_ids) != seen_ids:
            raise InvalidSnapshot("enumerated lanes omit a canonical scoped action")
        scope_coverage = True
    waiting = "WAITING_EXTERNAL" in states
    safe_work = "SAFE_WORK_REMAINING" in states
    all_blocked = (
        scope_coverage
        and not safe_work
        and all(s in ("BLOCKED_PROVEN", "FENCED", "WAITING_EXTERNAL", "DONE") for s in states)
        and any(s != "DONE" for s in states)
    )
    external_waits_only = scope_coverage and waiting and all(s in ("WAITING_EXTERNAL", "DONE") for s in states)
    # No-delta is actionable when useful independent work remains; a proven
    # all-lanes block is a genuine terminal boundary, not an artificial loop.
    no_delta_loop = cycles >= 2 and not all_blocked
    lawful_stop = (
        (exit_claim == "ALL_LANES_BLOCKED_STOP" and all_blocked)
        or (exit_claim == "WAIT_EXTERNAL_EXECUTOR" and durable_wait and not safe_work
            and scope_coverage)
        or (exit_claim == "CHECKPOINTED_CONTINUATION" and checkpoint_proven)
    )
    return {
        "lane_local_wait_blocks_only_its_lane": waiting and safe_work,
        "remaining_safe_work": safe_work,
        "scope_evidence_structurally_bound": scope_coverage,
        "all_lanes_proven_blocked": all_blocked,
        "all_external_waits_proven_blocked": external_waits_only,
        "no_delta_loop_forces_tactic_change": no_delta_loop,
        "checkpoint_continuation_verified": checkpoint_proven,
        "wait_executor_verified": durable_wait,
        "status_summary_is_not_continuation": exit_claim == "CHECKPOINT_SUMMARY_STOP",
        "owner_only_handoff_is_not_continuation": owner_handoff_stop,
        "wait_requires_started_durable_executor": (
            exit_claim == "WAIT_EXTERNAL_EXECUTOR" and not durable_wait
        ),
        "premature_exit_detected": exit_claim != "CONTINUE" and not lawful_stop,
    }

def _next_proof(requirement: str, worker: dict[str, Any],
                source: dict[str, Any], current_head: str) -> str:
    """Describe the missing evidence without originating duplicate operations.

    These are fixed advisory strings, not scheduler actions. Supplied snapshots
    remain unverified until their existing owners confirm them; pending means
    neither execution nor acceptance. No source/ref/content is echoed here.
    """
    if requirement == "current_head_ci":
        state = source.get("ci_conclusion")
        bound = source.get("ci_head") == current_head and _ref(source.get("ci_run_ref"))
        if bound and isinstance(state, str):
            if state in {"QUEUED", "PENDING", "IN_PROGRESS", "WAITING", "REQUESTED"}:
                return (
                    "consume the existing current-head CI run through its original observation path; "
                    "do not rerun or push an empty change; advance independent permitted work"
                )
            # STALE, SKIPPED and NEUTRAL do not establish a failed check.
            # Reconcile identity and required status before any repair.
            if state in {"FAILURE", "CANCELLED", "TIMED_OUT", "ACTION_REQUIRED"}:
                return (
                    "inspect the original CI result and identify a permitted repair; "
                    "no blind retry or duplicate run"
                )
        return (
            "reconcile current-head CI identity and state with GitHub before any new run; "
            "missing evidence is not a failed build"
        )
    if requirement == "independent_source_review":
        verdict = source.get("review_verdict")
        bound = (
            source.get("review_head") == current_head
            and _ref(source.get("review_ref"))
            and _ref(source.get("author_id"))
            and _ref(source.get("reviewer_id"))
            and source.get("author_id") != source.get("reviewer_id")
        )
        if bound and isinstance(verdict, str):
            if verdict in {"REQUESTED", "PENDING"}:
                return (
                    "consume the existing current-head review request, confirm no active review "
                    "on its original carrier, then any eligible independent non-author may "
                    "return a real head-bound verdict; do not duplicate a started review "
                    "or change review identities; a request is not execution or approval"
                )
            if verdict == "IN_PROGRESS":
                return (
                    "consume the active current-head review on its original carrier; "
                    "do not duplicate or reroute a started review; "
                    "review execution is not approval"
                )
            if verdict == "CHANGES_REQUESTED":
                return (
                    "repair the existing findings on the original source carrier, then obtain "
                    "independent review of the stable changed head; do not repeat unchanged reviews"
                )
        return (
            "reconcile the original review and current source with the independent reviewer; "
            "obtain the missing head-bound verdict without duplicating an existing request"
        )
    if requirement == "accepted_worker_result":
        if worker["state"] in {"QUEUED", "STARTED", "UNKNOWN"}:
            return (
                "reconcile the original worker through the existing Fabric/Runtime owner; "
                "do not submit a replacement; queue or unknown state is not accepted execution"
            )
        if worker["state"] == "TERMINAL":
            if worker.get("exit_code") == 0:
                return (
                    "consume and verify the original terminal result; exit zero is not acceptance; "
                    "do not relaunch for missing result or acceptance evidence"
                )
            return (
                "inspect the original terminal failure and reconcile its effects; "
                "do not relaunch or fail over to obtain the same effect"
            )
    return ACTION[requirement]


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
        {"requirement": key, "owner": OWNER[key],
         "next_proof": _next_proof(key, worker, source, current_head)}
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
    # A proof-complete packet does not make a procedurally invalid session
    # exit ready for canonical adjudication. Audit the optional lane claim
    # before the CLI disposition so a ghost-owner/status-only stop fails
    # closed even when every separately enumerated proof gate passes.
    lane_audit = _audit_lanes(root, effect) if root.get("lanes") is not None else {}
    # The caller must verify these observations against each canonical owner;
    # all green checks only mean the supplied packet is ready for adjudication.
    ready = not gaps and not held and not lane_audit.get("premature_exit_detected", False)
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
    report.update(lane_audit)
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

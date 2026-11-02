"""Read-only proof-gap audit for a bounded Mastermind mission snapshot.

Consumes selected, source-attributed observations already gathered from canonical
owners. The caller remains responsible for authenticating observations, freshness,
writer custody, and actual acceptance. This is NOT an Executive lifecycle, retry,
dispatch, credential, or finalization authority.

Run: python -m scripts.ohf.mission_exit_audit /path/to/snapshot.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

SCHEMA = "mastermind.mission_exit_audit_input/v1"
OUTPUT_SCHEMA = "mastermind.mission_exit_audit_output/v1"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
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


def _true_and_ref(obj: dict[str, Any], flag: str, receipt: str) -> bool:
    return obj.get(flag) is True and _ref(obj.get(receipt))


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
    if worker.get("scope") not in VALID_SCOPES or worker.get("state") not in VALID_RUN_STATES:
        raise InvalidSnapshot("unknown worker scope/state")
    if effect.get("class") not in VALID_EFFECTS:
        raise InvalidSnapshot("unknown effect class")
    if effect["class"] != "NONE":
        if not _ref(effect.get("action_id")) or not _ref(effect.get("carrier")):
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
    return {
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only Mastermind mission-exit evidence audit")
    parser.add_argument("snapshot", type=Path, help="local JSON of canonical owner observations")
    args = parser.parse_args(argv)
    try:
        if args.snapshot.stat().st_size > 131072:
            raise InvalidSnapshot("snapshot too large")
        raw = args.snapshot.read_text(encoding="utf-8")
        report = audit(json.loads(raw))
    except (OSError, ValueError):
        # Do not reflect error payloads or file paths, which could contain secrets.
        print(json.dumps({"schema": OUTPUT_SCHEMA, "disposition": "INPUT_UNVERIFIED", "error": "invalid_or_unreadable_snapshot"}))
        return 2
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0 if report["disposition"] == "READY_FOR_CANONICAL_ADJUDICATION" else 1


if __name__ == "__main__":
    sys.exit(main())

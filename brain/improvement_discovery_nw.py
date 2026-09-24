"""Consume the existing NW reflection owner; no gatherer, store, ranker or dispatch.

Fresh reports expose an observed consumer-coverage limitation, not research quality,
causality or alpha. Legacy and incomplete populations cannot certify absence. Fixed
hypothesis scaffolds prepare Chairman Cognition; they are not model-generated ideas
or selected work. Only the counts projection may enter the public Agenda.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any

from brain import improvement_discovery as D

SCOPE = "open_theses_and_last_200_outcome_rows"
_INPUTS = {"context", "theses", "outcomes"}
_STATES = {"COMPLETE", "MISSING", "UNREADABLE", "MALFORMED", "UNAVAILABLE", "CHANGED_DURING_READ"}
_CODE_PATH = "brain/nw_reflection.py"
_REPO = "mastermindx-market-intelligence/Mastermind"
# Consume the existing deployer/health artifact, never a discovery-owned marker.
# A source-contract test binds this name to app.main's existing owner contract.
_DEPLOY_MARKER = ".deployed_git_sha"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _count(value: Any) -> int:
    if type(value) is not int or not 0 <= value <= 10_000_000:
        raise ValueError("invalid_owner_count")
    return value


def _coverage(value: Any) -> tuple[dict, str, bool, str]:
    if not isinstance(value, dict):
        raise ValueError("owner_coverage_required")
    new_keys = {"subjects_n", "sample_scope", "inputs_complete", "input_status"}
    if not (new_keys & value.keys()):
        return ({"subjects_n": None, "uncovered_subjects_n": None, "inputs_complete": False,
                 "sample_scope": "LEGACY_UNATTESTED"}, "UNKNOWN", False,
                "Legacy coverage omits its distinct-subject denominator and input completeness; do not infer a gap or full coverage.")
    if not new_keys <= value.keys() or value["sample_scope"] != SCOPE:
        raise ValueError("unsupported_owner_scope")
    statuses = value["input_status"]
    if not isinstance(statuses, dict) or set(statuses) != _INPUTS:
        raise ValueError("owner_input_status_required")
    if any(not isinstance(s, str) or s not in _STATES for s in statuses.values()):
        raise ValueError("invalid_owner_input_status")
    complete = value["inputs_complete"]
    if type(complete) is not bool or complete != all(s == "COMPLETE" for s in statuses.values()):
        raise ValueError("inconsistent_owner_completeness")
    n, covered, rows, opened, resolved = (_count(value[k]) for k in
        ("subjects_n", "with_context_row_n", "context_rows_n", "open_theses_n", "resolved_recent_n"))
    if covered > n or covered > rows or n > opened + resolved or resolved > 200:
        raise ValueError("inconsistent_owner_population")
    rate = value.get("coverage_rate")
    if n == 0:
        if rate is not None or covered != 0:
            raise ValueError("empty_population_rate_must_be_null")
    elif type(rate) not in (int, float) or not math.isfinite(rate) or abs(rate - covered / n) > 0.000501:
        raise ValueError("inconsistent_owner_rate")
    safe = {"subjects_n": n, "with_context_row_n": covered, "uncovered_subjects_n": n - covered,
            "coverage_rate": rate, "inputs_complete": complete, "sample_scope": SCOPE,
            "input_status": dict(statuses)}
    if not n:
        return safe, "UNKNOWN", False, "The declared sample has no observed decided subjects; no demand deficit can be inferred."
    state = "GAP" if covered < n else "SATISFIED"
    finding = (f"The owner observes context rows for {covered} of {n} distinct subjects in its bounded sample. "
               f"Input completeness is {'confirmed' if complete else 'not confirmed'}. "
               "This measures context-row coverage only, not semantic adequacy, predictive value or production eligibility.")
    return safe, state, complete, finding


def _hypotheses(diagnosis: str, *, covered: int | None, total: int | None) -> list[dict]:
    """Deterministic alternatives for a principal to investigate, never a decision."""
    if diagnosis in {"HELD_SOURCE", "CONFLICTING_OBSERVATIONS", "SATISFIED"}:
        return []
    if diagnosis in {"UNASSESSED", "UNVERIFIED_GAP"}:
        alternatives = [
            ("VERIFY_EVIDENCE", "Is the apparent limitation just an incomplete observation?",
             "Obtain the existing owner's current complete sample, denominator and input-status receipts; compare same-scope revisions.",
             "A complete current sample still shows the limitation."),
            ("HOLD", "Should this remain unassessed while evidence is unavailable?",
             "Preserve unknown inputs without commissioning replacement work or treating an absent read as zero demand.",
             "Current complete evidence establishes a decision-relevant shortfall."),
        ]
    else:
        alternatives = [
            ("REUSE_OR_CONNECT", "Does the needed context already exist behind a coverage or identity mismatch?",
             "Trace one uncovered subject through existing identity, source and publication owners; compare the same user task before and after a read-only reuse demonstration.",
             "The existing lawful sources genuinely do not supply the needed context."),
            ("BOUNDED_RESEARCH", "Would new evidence improve the user's actual question rather than merely fill a row?",
             "Only after reuse and duplicate checks, study one uncovered subject; preregister answer-quality, supported claims, correction behavior and a no-new-research baseline.",
             "Research does not improve the independently judged task over reuse or abstention."),
            ("HOLD_OR_NARROW", "Is this uncovered scope intentional or lower-value than the available alternatives?",
             "Compare a truthful limited-scope answer with expanded coverage on the same task, including research cost and false-confidence cost.",
             "The limited scope repeatedly prevents a priority user job that bounded evidence could solve."),
        ]
    return [{"kind": kind, "question": question, "discriminating_check": check,
             "falsifier": falsifier, "basis": {"covered_subjects": covered, "sample_subjects": total},
             "method": "DETERMINISTIC_HYPOTHESIS_SCAFFOLD", "effect_ceiling": "ADVISORY_ONLY",
             "existing_work_reconciliation_required": True, "execution_authority_granted": False}
            for kind, question, check, falsifier in alternatives]


def evaluate_owner_snapshot(snapshot: Any, *, source_revision: str,
                            contract_sha256: str, observed_at: str) -> dict:
    """Compose actual owner coverage into the existing discovery evaluator.

    source_revision binds the observer's checked-out contract, NOT a claimed report
    producer revision. The legacy owner wire has no producer attestation. Effect
    owners must independently revalidate source identity, currentness and authority.
    """
    from brain.neural_web_context import _STALE_DAYS
    if not isinstance(snapshot, dict) or snapshot.get("schema") != "nw_reflection.v1":
        raise ValueError("unsupported_owner_snapshot")
    serialized = json.dumps(snapshot, sort_keys=True, ensure_ascii=True, separators=(",", ":"), allow_nan=False)
    if len(serialized.encode()) > 2_000_000:
        raise ValueError("owner_snapshot_too_large")
    clock = D._time(observed_at)
    generated = D._time(snapshot.get("generated_at"))
    asof = date.fromisoformat(snapshot["asof"])
    if generated > clock or asof > clock.date() or asof > generated.date():
        raise ValueError("future_owner_snapshot")
    expiry = generated + timedelta(days=_STALE_DAYS)
    fresh = clock <= expiry and (clock.date() - asof).days <= _STALE_DAYS
    coverage, state, complete, finding = _coverage(snapshot.get("coverage"))
    contract_ref = f"https://github.com/{_REPO}/blob/{source_revision}/{_CODE_PATH}"
    receipt = {"revision": source_revision, "available_at": observed_at,
               "observed_at": observed_at, "valid_until": max(clock, expiry).isoformat()}
    sources = [
        {**receipt, "id": "nw-coverage-contract", "owner": "GITHUB", "ref": contract_ref,
         "content_sha256": contract_sha256, "state": "CURRENT"},
        {**receipt, "id": "nw-reflection-snapshot", "owner": "DOMAIN_OWNER",
         "ref": "brain.nw_reflection.latest:data/nw_reflection/latest.json",
         "content_sha256": "sha256:" + hashlib.sha256(serialized.encode()).hexdigest(),
         "state": "CURRENT" if fresh else "STALE"},
    ]
    bundle = {"schema": D.INPUT_SCHEMA, "case_id": "nw-coverage-" + asof.isoformat(),
        "origin": "PROSPECTIVE", "cutoff_at": None, "sources": sources,
        "expectations": [{"id": "nw-context-for-decided-subjects", "scope": SCOPE,
            "user_job": "Understand the available context for the subjects being researched or monitored.",
            "consumer": "Existing Neural Web context reader and Improvement Agenda",
            "requirement": "Disclose context coverage of the distinct decided-subject sample, its missing rows and input completeness; do not equate row coverage with useful understanding.",
            "expectation_source": "nw-coverage-contract"}],
        "observations": [{"expectation_id": "nw-context-for-decided-subjects", "scope": SCOPE,
            "source_refs": ["nw-reflection-snapshot"], "scope_complete": complete,
            "state": state, "finding": finding}], "existing_work": []}
    report = D.evaluate(bundle, now=observed_at)
    diagnosis = report["opportunities"][0]["diagnosis"]
    report["owner_coverage"] = coverage
    report["owner_generated_at"] = snapshot["generated_at"]
    report["owner_asof"] = snapshot["asof"]
    report["receipt_assurance"] = "CONTENT_IDENTIFIED_LOCAL_OWNER_SNAPSHOT_PRODUCER_REVISION_UNATTESTED"
    report["hypotheses"] = _hypotheses(diagnosis, covered=coverage.get("with_context_row_n"), total=coverage["subjects_n"])
    if coverage["subjects_n"] == 0 and coverage["inputs_complete"]:
        report["hypotheses"] = []  # no observed demand is not work to manufacture
    report["selection"] = None
    report["existing_agenda_identity_hints"] = []
    # This is a navigation pointer to the established nudge item, not a Job,
    # execution lease, accepted implementation or proof that no other work exists.
    nudges = snapshot.get("nudges")
    if isinstance(nudges, list) and any(isinstance(n, dict) and n.get("code") == "coverage_below_half" and n.get("severity") in ("high", "medium") for n in nudges):
        report["existing_agenda_identity_hints"] = ["nw:coverage_below_half"]
    report["digest"] = D._digest({key: value for key, value in report.items() if key != "digest"})
    return report


def render_owner_brief(report: dict) -> str:
    text = D.render_markdown(report)
    lines = [text, "", "## Competing hypotheses for Chairman Cognition", "",
             "Deterministic scaffolds, not selected work or proof of independent ideation.",
             "Producer revision is not attested by this legacy owner wire."]
    for row in report["hypotheses"]:
        lines += ["", "### " + row["kind"], row["question"],
                  "Discriminating evidence: " + row["discriminating_check"],
                  "Would reject this hypothesis: " + row["falsifier"]]
    if not report["hypotheses"]:
        lines += ["No transformation hypothesis is eligible from this observation. Preserve its source or no-work disposition."]
    return "\n".join(lines) + "\n"


def _source_identity(root: Path) -> tuple[str, str]:
    """Reuse health's release owner for archives; Git blobs for source checkouts.

    An archive marker names the installed release but is not a cryptographic file
    manifest. Record observed bytes separately and never promote this read into
    authenticated producer identity or execution authority. A valid deployed marker
    precedes retained stale Git metadata, exactly as the established health owner.
    """
    from control_plane import ceo_boot_packet
    path = root / _CODE_PATH
    marker = root / _DEPLOY_MARKER
    try:
        raw = path.read_bytes()
        if marker.is_file():
            marker_before = marker.read_bytes()
            declared = marker_before.decode("utf-8").strip().lower()
            if not re.fullmatch(r"[0-9a-f]{40}", declared):
                raise ValueError("source_revision_unavailable")
            # Do not import app.main: it boots the application's dependency graph.
            # This is a read consumer of its existing validated marker contract.
            revision = declared
            if marker.read_bytes() != marker_before or path.read_bytes() != raw:
                raise ValueError("source_revision_unavailable")
        else:
            revision = ceo_boot_packet.git_sha(root)
            expected = ceo_boot_packet._git(root, "rev-parse", f"{revision}:{_CODE_PATH}")
            # Git's ordinary blob identity over these exact observed bytes. SHA-1
            # is used only for Git object comparison, never as an authority token.
            blob = b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw
            actual = hashlib.sha1(blob, usedforsecurity=False).hexdigest()
            if not revision or not expected or actual != expected or ceo_boot_packet.git_sha(root) != revision:
                raise ValueError("source_revision_unavailable")
        return revision, "sha256:" + hashlib.sha256(raw).hexdigest()
    except (OSError, UnicodeError) as exc:
        raise ValueError("source_revision_unavailable") from exc


def latest_agenda_projection(*, root: Path, asof: date, now: str | None = None) -> dict:
    """Existing Agenda cadence consumes the existing persisted owner once; read only."""
    unavailable = D.optional_agenda_projection(None, now=None)
    try:
        from brain import nw_reflection
        snapshot = nw_reflection.latest()
        if not snapshot:
            return unavailable
        if date.fromisoformat(snapshot["asof"]) > asof:
            return {**unavailable, "reason_code": "POST_ASOF_OWNER_SNAPSHOT"}
        revision, digest = _source_identity(root)
        report = evaluate_owner_snapshot(snapshot, source_revision=revision,
            contract_sha256=digest, observed_at=now or _now())
        return D.agenda_projection(report)
    except Exception:  # noqa: BLE001 -- optional evidence must not suppress the existing agenda
        return {**unavailable, "reason_code": "OWNER_SNAPSHOT_UNAVAILABLE_OR_INVALID"}

"""Evidence-backed improvement discovery; advice, never a second work queue.

The caller supplies owner-attributed observations. This pure module neither gathers
sources nor authenticates receipts. Executive admission must independently re-read
source, custody, budget and effect state. No ranking, provider, scheduler or writes.
"""
from __future__ import annotations

import hashlib
import html
import json
import re
from collections import Counter
from datetime import datetime
from typing import Any

INPUT_SCHEMA = "mastermind.improvement_observations.v1"
REPORT_SCHEMA = "mastermind.improvement_discovery.v1"
PROJECTION_SCHEMA = "mastermind.improvement_discovery_summary.v1"
ORIGINS = {"CHAIRMAN_REVEALED", "PROSPECTIVE", "FROZEN_REPLAY"}
SOURCE_STATES = {"CURRENT", "STALE", "UNAVAILABLE", "CONFLICT", "RETRACTED"}
OWNERS = {"GITHUB", "AGENT_OS", "DOMAIN_OWNER", "CHAIRMAN"}
OBSERVATION_STATES = {"GAP", "SATISFIED", "UNKNOWN", "NOT_EXPOSED"}
MAX_ROWS = 256
MAX_TEXT = 2000


def _object(value: Any, keys: set[str]) -> dict:
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError("invalid_object_shape")
    return value


def _text(value: Any) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > MAX_TEXT:
        raise ValueError("invalid_text")
    if any(ord(c) < 32 and c not in "\n\t" for c in value):
        raise ValueError("invalid_control_character")
    return value


def _id(value: Any) -> str:
    value = _text(value)
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,119}", value):
        raise ValueError("invalid_id")
    return value


def _rows(value: Any) -> list:
    if not isinstance(value, list) or len(value) > MAX_ROWS:
        raise ValueError("invalid_rows")
    return value


def _time(value: Any) -> datetime:
    try:
        out = datetime.fromisoformat(_text(value).replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid_time") from exc
    if out.tzinfo is None:
        raise ValueError("timezone_required")
    return out


def _digest(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return "sha256:" + hashlib.sha256(raw.encode()).hexdigest()


def _source(row: Any, now: datetime, cutoff: datetime | None) -> tuple[str, dict, str]:
    row = _object(row, {"id", "owner", "ref", "revision", "content_sha256",
                        "available_at", "observed_at", "valid_until", "state"})
    key = _id(row["id"])
    if row["owner"] not in OWNERS or row["state"] not in SOURCE_STATES:
        raise ValueError("invalid_source_owner_or_state")
    _text(row["ref"])
    if not re.fullmatch(r"[0-9a-f]{40}", _text(row["revision"])):
        raise ValueError("immutable_revision_required")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", _text(row["content_sha256"])):
        raise ValueError("source_digest_required")
    available, observed, expires = (_time(row[k]) for k in
                                    ("available_at", "observed_at", "valid_until"))
    if available > observed or observed > now or expires < observed:
        raise ValueError("invalid_source_clocks")
    if cutoff is not None and available > cutoff:
        raise ValueError("post_cutoff_source")
    state = row["state"]
    if state == "CURRENT" and now > expires:
        state = "STALE"
    return key, {**row, "effective_state": state}, state


def evaluate(bundle: Any, *, now: str) -> dict:
    """Make reviewable opportunities; missing observation is UNKNOWN, not a gap.

    Source currentness is a supplied, content-identified observation, not a signature
    or a grant. A report is never evidence of independent model discovery or execution.
    """
    bundle = _object(bundle, {"schema", "case_id", "origin", "cutoff_at", "sources",
                              "expectations", "observations", "existing_work"})
    if bundle["schema"] != INPUT_SCHEMA or bundle["origin"] not in ORIGINS:
        raise ValueError("invalid_schema_or_origin")
    _id(bundle["case_id"])
    clock = _time(now)
    cutoff = _time(bundle["cutoff_at"]) if bundle["cutoff_at"] is not None else None
    if (bundle["origin"] == "FROZEN_REPLAY") != (cutoff is not None):
        raise ValueError("replay_cutoff_required_only_for_replay")
    if cutoff is not None and cutoff > clock:
        raise ValueError("future_cutoff")
    sources: dict[str, dict] = {}
    source_states: dict[str, str] = {}
    for raw in _rows(bundle["sources"]):
        key, receipt, state = _source(raw, clock, cutoff)
        if key in sources:
            raise ValueError("duplicate_source")
        sources[key], source_states[key] = receipt, state
    expectations: dict[str, dict] = {}
    for raw in _rows(bundle["expectations"]):
        row = _object(raw, {"id", "scope", "user_job", "consumer", "requirement",
                           "expectation_source"})
        key = _id(row["id"])
        for field in ("scope", "user_job", "consumer", "requirement"):
            _text(row[field])
        if key in expectations or row["expectation_source"] not in sources:
            raise ValueError("duplicate_expectation_or_missing_source")
        expectations[key] = dict(row)
    observations: dict[str, list[dict]] = {key: [] for key in expectations}
    for raw in _rows(bundle["observations"]):
        row = _object(raw, {"expectation_id", "scope", "source_refs", "scope_complete",
                           "state", "finding"})
        key = row["expectation_id"]
        if key not in expectations or row["scope"] != expectations[key]["scope"]:
            raise ValueError("observation_scope_mismatch")
        if type(row["scope_complete"]) is not bool or row["state"] not in OBSERVATION_STATES:
            raise ValueError("invalid_observation")
        _text(row["finding"])
        refs = _rows(row["source_refs"])
        if not refs or any(not isinstance(ref, str) or ref not in sources for ref in refs):
            raise ValueError("observation_evidence_required")
        if len(set(refs)) != len(refs):
            raise ValueError("duplicate_evidence_ref")
        observations[key].append({**row, "source_refs": sorted(refs)})
    work: dict[str, list[dict]] = {key: [] for key in expectations}
    for raw in _rows(bundle["existing_work"]):
        row = _object(raw, {"expectation_id", "source_ref", "disposition"})
        key, ref = row["expectation_id"], row["source_ref"]
        if key not in expectations or ref not in sources:
            raise ValueError("unknown_work_identity")
        if row["disposition"] not in {"OPEN_PROPOSAL", "ACCEPTED"}:
            raise ValueError("invalid_work_disposition")
        if sources[ref]["owner"] not in {"GITHUB", "AGENT_OS"}:
            raise ValueError("canonical_work_owner_required")
        if row in work[key]:
            raise ValueError("duplicate_work_ref")
        work[key].append(dict(row))
    entries = []
    for key, expected in sorted(expectations.items()):
        seen, known = observations[key], work[key]
        refs = {expected["expectation_source"]}
        refs.update(ref for row in seen for ref in row["source_refs"])
        refs.update(row["source_ref"] for row in known)
        bad = sorted({source_states[ref] for ref in refs if source_states[ref] != "CURRENT"})
        observed_states = {row["state"] for row in seen}
        complete = bool(seen) and all(row["scope_complete"] for row in seen)
        if bad:
            diagnosis = "HELD_SOURCE"
        elif len(observed_states - {"UNKNOWN"}) > 1:
            diagnosis = "CONFLICTING_OBSERVATIONS"
        elif not seen or observed_states == {"UNKNOWN"}:
            diagnosis = "UNASSESSED"
        elif not complete or "UNKNOWN" in observed_states:
            diagnosis = "UNVERIFIED_GAP" if "GAP" in observed_states or "NOT_EXPOSED" in observed_states else "UNASSESSED"
        elif observed_states == {"SATISFIED"}:
            diagnosis = "SATISFIED"
        elif observed_states == {"NOT_EXPOSED"}:
            diagnosis = "CONSUMER_GAP"
        else:
            diagnosis = "EVIDENCED_GAP"
        if bad or diagnosis == "CONFLICTING_OBSERVATIONS":
            disposition = "RECONCILE_EVIDENCE"
        elif any(row["disposition"] == "ACCEPTED" for row in known):
            disposition = "PRESERVE_ACCEPTED" if diagnosis == "SATISFIED" else "RECONCILE_ACCEPTED"
        elif diagnosis == "SATISFIED":
            disposition = "NO_WORK"
        elif known:
            disposition = "ATTACH_TO_EXISTING_PROPOSAL"
        else:
            disposition = "REVIEW_AND_DUPLICATE_CHECK"
        identity = _digest({"expectation_id": key, "scope": expected["scope"]})
        entries.append({
            "id": "opportunity:" + identity.split(":")[1][:24],
            "expectation": expected, "diagnosis": diagnosis,
            "disposition": disposition, "source_problems": bad,
            "observations": sorted(seen, key=lambda row: _digest(row)),
            "source_refs": sorted(refs),
            "existing_work": sorted(known, key=lambda row: (row["source_ref"], row["disposition"])),
            "next_evidence": _next_evidence(diagnosis, disposition),
            "alternatives": ["REUSE_OR_CONNECT_EXISTING", "BOUNDED_RESEARCH_OR_EVALUATION", "HOLD"],
            "execution_authority_granted": False,
        })
    report = {
        "schema": REPORT_SCHEMA, "case_id": bundle["case_id"], "as_of": now,
        "origin": bundle["origin"], "cutoff_at": bundle["cutoff_at"],
        "evaluation_use": "REVEALED_REGRESSION" if bundle["origin"] == "CHAIRMAN_REVEALED" else "UNPROVEN_CANDIDATE",
        "independent_discovery_proven": False,
        "execution_authority_granted": False, "jobs_created": 0,
        "receipt_assurance": "CALLER_SUPPLIED_OWNER_REVALIDATION_REQUIRED",
        "sources": [sources[key] for key in sorted(sources)], "opportunities": entries,
    }
    report["digest"] = _digest(report)
    return report


def _next_evidence(diagnosis: str, disposition: str) -> str:
    if disposition in {"PRESERVE_ACCEPTED", "NO_WORK"}:
        return "Do not redo accepted or satisfied work. Reopen only on a verified material invalidator."
    if disposition in {"RECONCILE_ACCEPTED", "RECONCILE_EVIDENCE"}:
        return "Resolve the exact conflicting, stale or accepted source through its existing owner before proposing effects."
    prefix = "Attach findings to the existing proposal; a draft PR is not a running worker. " if disposition == "ATTACH_TO_EXISTING_PROPOSAL" else "Check exact existing work and effects before originating any job. "
    if diagnosis == "CONSUMER_GAP":
        return prefix + "Determine whether knowledge already exists but is not exposed to this consumer. Test reuse before new research."
    if diagnosis in {"UNASSESSED", "UNVERIFIED_GAP"}:
        return prefix + "Run a bounded coverage audit. Establish completeness and evidence quality; do not infer absence from a partial search."
    return prefix + "Compare reuse, bounded research and hold. Specify an observable consumer improvement, null baseline, falsifier and evidence budget."


def agenda_projection(report: dict) -> dict:
    """Public-safe counts only: never mirror private findings, refs or prompts."""
    return {
        "schema": PROJECTION_SCHEMA, "state": "AVAILABLE", "as_of": report["as_of"],
        "diagnosis_counts": dict(sorted(Counter(row["diagnosis"] for row in report["opportunities"]).items())),
        "disposition_counts": dict(sorted(Counter(row["disposition"] for row in report["opportunities"]).items())),
        "n_expectations": len(report["opportunities"]),
        "independent_discovery_proven": False, "execution_authority_granted": False,
        "jobs_created": 0,
    }


def _md_text(value: str) -> str:
    value = html.escape(" ".join(value.split()))
    for char in "\\`*_{}[]()#+!|":
        value = value.replace(char, "\\" + char)
    return value


def render_markdown(report: dict) -> str:
    lines = ["# Improvement discovery - internal research brief", "",
             "Advisory only. No jobs created, ranking changed, or execution authority granted.",
             "Caller-supplied source receipts require independent owner revalidation.",
             "Independent discovery is NOT proven; revealed cases are regressions, not blind tests.",
             "", "Report: " + report["digest"], ""]
    for row in report["opportunities"]:
        e = row["expectation"]
        lines += ["## " + _md_text(e["id"]), "", "User job: " + _md_text(e["user_job"]),
                  "Consumer: " + _md_text(e["consumer"]),
                  "Expected capability: " + _md_text(e["requirement"]),
                  "Diagnosis: " + row["diagnosis"], "Disposition: " + row["disposition"],
                  "Next evidence: " + row["next_evidence"],
                  "Alternatives: reuse/connect; bounded research/evaluation; hold.", ""]
        for obs in row["observations"]:
            lines += ["Observed: " + _md_text(obs["finding"])]
        lines += ["Evidence references: " + ", ".join(row["source_refs"]), ""]
    return "\n".join(lines)


def optional_agenda_projection(bundle: Any, *, now: str | None) -> dict:
    """A degraded sensor must be visible without leaking its rejected contents."""
    unavailable = {"schema": PROJECTION_SCHEMA, "state": "UNAVAILABLE",
                   "independent_discovery_proven": False,
                   "execution_authority_granted": False, "jobs_created": 0}
    if bundle is None:
        return {**unavailable, "reason_code": "NOT_SUPPLIED"}
    if now is None:
        return {**unavailable, "reason_code": "EXPLICIT_CLOCK_REQUIRED"}
    try:
        return agenda_projection(evaluate(bundle, now=now))
    except (ValueError, TypeError, KeyError, OverflowError):
        return {**unavailable, "reason_code": "INVALID_INPUT"}


def render_public_summary(projection: Any) -> list[str]:
    """Fixed code/count rendering; never interpolate arbitrary snapshot prose."""
    if not isinstance(projection, dict) or projection.get("state") != "AVAILABLE":
        return ["## Improvement discovery (unranked)", "",
                "Input unavailable. This is not evidence of zero gaps.", ""]
    lines = ["## Improvement discovery (unranked)", "",
             "Advisory candidate evidence only. No work was dispatched; independent discovery is unproven."]
    allowed = {"HELD_SOURCE", "CONFLICTING_OBSERVATIONS", "UNASSESSED", "UNVERIFIED_GAP",
               "SATISFIED", "CONSUMER_GAP", "EVIDENCED_GAP"}
    counts = projection.get("diagnosis_counts")
    if not isinstance(counts, dict):
        return lines + ["Summary unavailable: malformed counts.", ""]
    for key in sorted(allowed):
        count = counts.get(key)
        if type(count) is int and 0 < count <= MAX_ROWS:
            lines.append(f"- {key}: {count}")
    return lines + [""]


def public_note(projection: dict) -> str:
    """Reuse the existing Agenda note renderer rather than fork a pending UI repair."""
    if projection.get("state") != "AVAILABLE":
        return " Improvement discovery input unavailable; zero gaps cannot be inferred."
    count = projection.get("n_expectations")
    count = count if type(count) is int and 0 <= count <= MAX_ROWS else 0
    diagnoses = projection.get("diagnosis_counts", {})
    parts = []
    for code in ("EVIDENCED_GAP", "CONSUMER_GAP", "UNVERIFIED_GAP", "UNASSESSED",
                 "HELD_SOURCE", "CONFLICTING_OBSERVATIONS", "SATISFIED"):
        value = diagnoses.get(code)
        if type(value) is int and 0 < value <= MAX_ROWS:
            parts.append(f"{code.lower().replace('_', ' ')}: {value}")
    return (f" Improvement discovery: {count} expectations reviewed (" + "; ".join(parts) +
            "). Unranked research evidence only; no jobs dispatched and independent discovery unproven.")


def observe_named_paths(*, expectation_id: str, scope: str, required_paths: list[str],
                        present_paths: list[str] | None, source_refs: list[str],
                        inventory_complete: bool) -> dict:
    """Derive an observation from an exact owner-supplied Git inventory.

    The expectation must concern these named source files only. Presence is not
    correctness or deployment; missing a named implementation is not proof no
    alternative capability exists. No filesystem scan or second search index.
    """
    from pathlib import PurePosixPath

    _id(expectation_id); _text(scope)
    required = _rows(required_paths)
    if not required or len(set(required)) != len(required):
        raise ValueError("unique_required_paths_needed")
    for path in required:
        _text(path)
        parsed = PurePosixPath(path)
        if parsed.is_absolute() or ".." in parsed.parts or str(parsed) != path:
            raise ValueError("relative_exact_paths_required")
    if type(inventory_complete) is not bool:
        raise ValueError("inventory_completeness_required")
    refs = _rows(source_refs)
    if not refs or len(set(refs)) != len(refs):
        raise ValueError("inventory_evidence_required")
    for ref in refs:
        _id(ref)
    if present_paths is None or not inventory_complete:
        state, complete = "UNKNOWN", False
        finding = "Exact named-path inventory is unavailable or incomplete; missing capability is not established."
    else:
        present = _rows(present_paths)
        if any(path not in required for path in present) or len(set(present)) != len(present):
            raise ValueError("inventory_outside_exact_scope")
        missing = sorted(set(required) - set(present))
        state, complete = ("GAP" if missing else "SATISFIED"), True
        finding = (f"Exact source inventory: {len(present)}/{len(required)} required named files present; "
                   f"{len(missing)} absent. This establishes source-path coverage only, not semantic quality, "
                   "alternative absence, deployment, or independent discovery.")
    return {"expectation_id": expectation_id, "scope": scope, "source_refs": sorted(refs),
            "scope_complete": complete, "state": state, "finding": finding}

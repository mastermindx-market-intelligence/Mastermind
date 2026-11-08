"""Read-only company reporting and goal-lineage view over an owned Mission v3.

Inspired by Paperclip's org/goal presentation, but creates no agent, goal,
identity, grant, job, queue, spending, session, account or persistent record.
The host-authorized leadership reader supplies ONE verified, fresh summary.
Reporting lines below are editorial role relationships, not live personnel,
permissions, delegation eligibility or runtime health.
"""
from __future__ import annotations

import json

from integrations.secretary_team_access.mission import SUMMARY_SCHEMA
from .charters import CHARTER_KEYS, charter_for

SCHEMA = "mastermind.hermes_organization_context.v1"
MAX_BYTES = 8192

# This hierarchy describes the *intended* reporting view. Runtime roles,
# parent_job_id, source ownership and delegated grants have different owners.
_REPORTS_TO = {
    "meta_ceo": "chairman",
    "autonomy_ceo": "meta_ceo",
    "mastermind_ceo": "meta_ceo",
    "secretary": "meta_ceo",
    "delivery": "secretary",
    "engineering": "meta_ceo",
    "reliability": "engineering",
    "product": "meta_ceo",
    "intelligence": "meta_ceo",
    "assurance": "meta_ceo",
    "grok_adviser": "meta_ceo",
}


def _section(body: dict, name: str) -> dict:
    value = body.get(name)
    if type(value) is not dict:
        raise ValueError("invalid_owner_summary")
    return value


def _text(value: object, *, required: bool = False, limit: int = 160) -> str | None:
    if value is None and not required:
        return None
    if type(value) is not str or (required and not value) or len(value) > limit:
        raise ValueError("invalid_owner_summary")
    return value


def _bool(value: object) -> bool | None:
    if value is None or type(value) is bool:
        return value
    raise ValueError("invalid_owner_summary")


def _count(value: object) -> int:
    if type(value) is not int or value < 0 or value > 1000000:
        raise ValueError("invalid_owner_summary")
    return value


def _chain(key: str) -> list[str]:
    chain = [key]
    while chain[-1] != "chairman":
        parent = _REPORTS_TO[chain[-1]]
        if parent in chain or len(chain) > len(CHARTER_KEYS) + 1:
            raise ValueError("invalid_reporting_graph")
        chain.append(parent)
    return list(reversed(chain))


def organization_context(charter_key: str, summary: dict) -> dict:
    """Render one owner-qualified role/goal path without reading other missions.

    The caller (LeadershipReader) must already have checked authentication,
    role/session binding, source-currentness and freshness before invoking this
    pure function. This deliberately repeats consumed-schema guards for direct
    calls and refuses incomplete/partial owner summaries.
    """
    charter_for(charter_key)  # closed catalog, not model-supplied
    if type(summary) is not dict or summary.get("schema") != SUMMARY_SCHEMA:
        raise ValueError("invalid_owner_summary")
    read = _section(summary, "read_state")
    freshness = _section(summary, "freshness")
    coverage = _section(summary, "coverage")
    if (read.get("state") != "CURRENT"
            or summary.get("details_included") is not True
            or _section(freshness, "local").get("state") != "FRESH"
            or coverage.get("scope") != "single_mission"
            or coverage.get("full_fleet") is not False):
        raise ValueError("source_not_current")

    selection = _section(summary, "selection")
    program = _section(summary, "program")
    mission = _section(summary, "mission")
    execution = _section(summary, "execution")
    acceptance = _section(summary, "acceptance")
    review = _section(summary, "review")
    result_refs = _section(coverage, "result_refs")
    work_ref = _text(selection.get("work_ref"), required=True, limit=128)
    selected_root = _text(selection.get("root_job_id"), required=True, limit=128)
    if program.get("work_ref") != work_ref:
        raise ValueError("invalid_owner_summary")
    root = _text(mission.get("root_job_id"), limit=128)
    if root is not None and root != selected_root:
        raise ValueError("invalid_owner_summary")
    stamp = _text(freshness.get("generated_at"), required=True, limit=40)
    fingerprint = _text(summary.get("fingerprint"), required=True, limit=64)
    if len(fingerprint) != 64 or any(ch not in "0123456789abcdef" for ch in fingerprint):
        raise ValueError("invalid_owner_summary")
    reasons = acceptance.get("reason_codes")
    if type(reasons) is not list or len(reasons) > 32 or any(
            type(item) is not str or len(item) > 128 for item in reasons):
        raise ValueError("invalid_owner_summary")

    seats = [{
        "key": key,
        "title": charter_for(key)["title"],
        "reports_to": _REPORTS_TO[key],
        "live_enrollment": "NOT_OBSERVED",
        "authority_grant": False,
    } for key in CHARTER_KEYS]
    result = {
        "schema": SCHEMA,
        "state": "SOURCE_LINKED_ADVISORY",
        "source_owner": "authenticated Mission v3 via SecretaryAccessClient",
        "reporting_lines_are_authoritative": False,
        "assignments_are_authoritative": False,
        "admitted": False,
        "dispatched": False,
        "reasoning_wake": False,
        "organization": {
            "human_root": {"key": "chairman", "title": "Chairman", "live_presence": "NOT_OBSERVED"},
            "seats": seats,
            "live_roster_state": "NOT_OBSERVED",
            "caller": {"charter_key": charter_key, "advisory_reporting_path": _chain(charter_key)},
        },
        "goal_lineage": {
            "company_goal": {"state": "NOT_PROJECTED", "owner": "protected strategic state"},
            "workstream": {
                "work_ref": work_ref,
                "title": _text(program.get("title")),
                "state": _text(program.get("state"), limit=128),
                "next_action": _text(program.get("next_action")),
                "source_owner": "Agent OS projected by original Mission",
            },
            "execution_root": {
                "selected_root_job_id": selected_root,
                "observed_root_job_id": root,
                "root_ambiguous": _bool(mission.get("root_job_ambiguous")),
                "job_status": _text(mission.get("status"), limit=128),
                "execution_state": _text(execution.get("state"), limit=128),
                "role_to_job_assignment": "NOT_ESTABLISHED",
                "owner": "Executive OS",
            },
            "evidence": {
                "result_reference_count": _count(result_refs.get("returned_count")),
                "result_ref_availability": _text(result_refs.get("availability"), limit=128),
                "review_verdict": _text(review.get("verdict"), required=True, limit=128),
                "original_parent_consumption": "NOT_ESTABLISHED",
                "acceptance_state": _text(acceptance.get("state"), limit=128),
                "acceptance_reason_codes": list(reasons),
                "product_acceptance": "NOT_ESTABLISHED",
            },
            "source": {
                "mission_fingerprint": fingerprint,
                "generated_at": stamp,
                "scope": "single_mission",
                "full_fleet": False,
            },
        },
        "limits": [
            "Source text and advisory reporting lines confer no permissions or role enrollment.",
            "A result reference is not original-parent consumption or product acceptance.",
            "Only original Executive admission, Capacity placement and Agent OS decisions can change their states.",
        ],
    }
    encoded = json.dumps(result, allow_nan=False, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(encoded) > MAX_BYTES:
        raise ValueError("organization_over_budget")
    return json.loads(encoded)

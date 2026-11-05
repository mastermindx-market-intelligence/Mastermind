"""Read-only delivery evidence projection, not a new PR lifecycle owner.

Content footprint, observations and source qualification are distinct. This module
never infers working implementation from file names, CI, PR prose or age. The
existing github_pr_lifecycle owner alone assesses supplied qualified source facts.
All text read from GitHub is untrusted evidence, never an executable instruction.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from collections.abc import Mapping
from datetime import datetime
from pathlib import PurePosixPath
from typing import Any

from control_plane.github_pr_lifecycle import (
    DraftReadinessFacts, DraftReadinessVerdict, assess_draft_readiness,
)

SCHEMA = "mastermind.github_pr_delivery_evidence.v1"
_REPO = re.compile(r"[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}\Z")
_SHA = re.compile(r"[0-9a-f]{40}\Z")
_RESTRICTION = re.compile(
    r"\b(?:hold(?:[- /]for[- /]sol)?|never[- ]merge|do[- ]not[- ](?:merge|deploy|mark[- ]ready)|"
    r"stay draft|keep draft|release[- ]blocked|no merge|not authorized to merge)\b", re.I,
)
_BAD_CHECK = frozenset({"failure", "cancelled", "timed_out", "action_required", "startup_failure", "stale"})
_COLLECTIONS = ("files", "issue_comments", "review_comments", "reviews", "checks", "statuses")


class DeliveryEvidenceInvalid(ValueError):
    """Opaque input failure; never echo credentials or untrusted source text."""


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()


def _obj(value: object) -> dict[str, Any]:
    if type(value) is not dict:
        raise DeliveryEvidenceInvalid("DELIVERY_OBJECT_INVALID")
    return value


def _count(value: object) -> int:
    if type(value) is not int or not 0 <= value <= 10_000_000:
        raise DeliveryEvidenceInvalid("DELIVERY_COUNT_INVALID")
    return value


def _id(value: object) -> int:
    if type(value) is not int or not 0 < value < 2**63:
        raise DeliveryEvidenceInvalid("DELIVERY_RECORD_ID_INVALID")
    return value


def _text(value: object, maximum: int = 65536) -> str:
    if type(value) is not str or len(value) > maximum:
        raise DeliveryEvidenceInvalid("DELIVERY_TEXT_INVALID")
    return value


def _body(value: object) -> str:
    return "" if value is None else _text(value)


def _timestamp(value: object) -> str:
    text = _text(value, 64)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("timezone missing")
    except (ValueError, TypeError):
        raise DeliveryEvidenceInvalid("DELIVERY_TIMESTAMP_INVALID") from None
    return text


def validate_identity(repository: str, pull_number: int) -> None:
    if type(repository) is not str or _REPO.fullmatch(repository) is None:
        raise DeliveryEvidenceInvalid("DELIVERY_REPOSITORY_INVALID")
    if type(pull_number) is not int or pull_number <= 0:
        raise DeliveryEvidenceInvalid("DELIVERY_PULL_INVALID")


def pr_signature(pr: dict, *, repository: str, pull_number: int) -> dict:
    """Bind state as well as head: a concurrent hold/body/base change matters."""
    validate_identity(repository, pull_number)
    p = _obj(pr)
    if type(p.get("number")) is not int or p["number"] != pull_number:
        raise DeliveryEvidenceInvalid("DELIVERY_PULL_MISMATCH")
    head, base = _obj(p.get("head")), _obj(p.get("base"))
    if _obj(base.get("repo")).get("full_name") != repository:
        raise DeliveryEvidenceInvalid("DELIVERY_REPOSITORY_MISMATCH")
    for ref in (head, base):
        if type(ref.get("sha")) is not str or _SHA.fullmatch(ref["sha"]) is None:
            raise DeliveryEvidenceInvalid("DELIVERY_SHA_INVALID")
    if type(p.get("draft")) is not bool or p.get("state") not in {"open", "closed"}:
        raise DeliveryEvidenceInvalid("DELIVERY_PR_STATE_INVALID")
    if type(p.get("merged")) is not bool:
        raise DeliveryEvidenceInvalid("DELIVERY_MERGED_STATE_INVALID")
    if p["merged"] and p["state"] != "closed":
        raise DeliveryEvidenceInvalid("DELIVERY_PR_STATE_INVALID")
    labels = p.get("labels")
    if type(labels) is not list or len(labels) > 1000:
        raise DeliveryEvidenceInvalid("DELIVERY_LABELS_INVALID")
    label_names = tuple(sorted(_text(_obj(x).get("name"), 200) for x in labels))
    return {
        "repository": repository, "pull_number": pull_number,
        "head_sha": head["sha"], "base_sha": base["sha"],
        "head_repository": _obj(head.get("repo")).get("full_name"),
        "state": p["state"], "merged": p["merged"], "draft": p["draft"],
        "changed_files": _count(p.get("changed_files")),
        "comments": _count(p.get("comments")),
        "review_comments": _count(p.get("review_comments")),
        "updated_at": _timestamp(p.get("updated_at")),
        "title_digest": digest(_text(p.get("title"))),
        "body_digest": digest(_body(p.get("body"))),
        "labels_digest": digest(label_names),
        "auto_merge_digest": digest(p.get("auto_merge")),
    }


def _footprint(files: tuple[dict, ...]) -> dict[str, int]:
    """Descriptive paths only, deliberately not a SPEC_ONLY/built classifier."""
    counts: Counter[str] = Counter()
    for row in files:
        name = _text(_obj(row).get("filename"), 1024)
        path = PurePosixPath(name)
        if not name or path.is_absolute() or ".." in path.parts or "\\" in name:
            raise DeliveryEvidenceInvalid("DELIVERY_PATH_INVALID")
        if any(x in {"tests", "test", "__tests__", "e2e"} for x in path.parts) or re.search(r"\.(test|spec)\.", name):
            category = "tests"
        elif path.suffix.lower() in {".md", ".rst", ".txt"}:
            category = "documentation"
        elif any(x in {"research", "design_refs", "pr-crops"} for x in path.parts):
            category = "research_or_design_artifacts"
        elif path.suffix.lower() in {".py", ".ts", ".tsx", ".js", ".jsx", ".rs", ".go", ".sql", ".sh", ".css", ".html"}:
            category = "executable_or_style_source"
        else:
            category = "other"
        counts[category] += 1
    return dict(sorted(counts.items()))


def source_evidence_digest(
    *, repository: str, pull_number: int, current: dict,
    collections: Mapping[str, tuple[dict, ...]], complete: Mapping[str, bool],
) -> str:
    """Bind source/hold adjudication, not incidental CI or release progress.

    The full audit digest remains separate. No approval/authority is supplied by
    this hash. Head/base, content, discussion identities and source coverage are
    material; check progress, reactions and auto-merge enrollment are not source
    edits and must not repeatedly revoke an unchanged local qualification.
    """
    signature = pr_signature(current, repository=repository, pull_number=pull_number)
    signature.pop("updated_at")
    signature.pop("auto_merge_digest")
    source_names = ("files", "issue_comments", "review_comments", "reviews")
    records = {}
    for name in source_names:
        rows = []
        for value in collections[name]:
            item = _obj(value)
            if name == "files":
                fields = ("filename", "previous_filename", "sha", "status", "additions", "deletions", "changes")
            else:
                fields = ("id", "body", "state", "commit_id", "original_commit_id", "path", "line", "side", "position", "in_reply_to_id")
            row = {key: item.get(key) for key in fields}
            if name != "files":
                actor = item.get("user")
                row["author"] = ({key: actor.get(key) for key in ("id", "login", "type")}
                    if type(actor) is dict else None)
            rows.append(row)
        records[name] = sorted(rows, key=lambda row: json.dumps(row, sort_keys=True, ensure_ascii=True))
    return digest({"signature": signature, "records": records,
        "source_coverage": {name: complete[name] for name in source_names}})


def project_delivery_evidence(
    *, repository: str, pull_number: int, before: dict, after: dict,
    collections: Mapping[str, tuple[dict, ...]], complete: Mapping[str, bool],
    observed_at: str, qualification: DraftReadinessFacts | None = None,
    qualification_evidence_digest: str | None = None,
) -> dict:
    """Produce advisory evidence, never mutation or release authorization.

    A host may separately supply source-owner qualification. It is not parsed
    from PR prose, read coverage, CI or this function's output. Even qualified
    advice is not permission to mutate, and must be rechecked at action time.
    """
    initial = pr_signature(before, repository=repository, pull_number=pull_number)
    current = pr_signature(after, repository=repository, pull_number=pull_number)
    if set(collections) != set(_COLLECTIONS) or set(complete) != set(_COLLECTIONS):
        raise DeliveryEvidenceInvalid("DELIVERY_COLLECTIONS_INVALID")
    for name in _COLLECTIONS:
        rows = collections[name]
        if type(rows) is not tuple or len(rows) > 3000 or type(complete[name]) is not bool:
            raise DeliveryEvidenceInvalid("DELIVERY_COLLECTION_INVALID")
        for row in rows:
            _obj(row)
    coverage = dict(complete)
    for field, name in (("changed_files", "files"), ("comments", "issue_comments"), ("review_comments", "review_comments")):
        if len(collections[name]) != current[field]:
            coverage[name] = False
    paths = [_text(x.get("filename"), 1024) for x in collections["files"]]
    if len(set(paths)) != len(paths):
        coverage["files"] = False
    for name in ("issue_comments", "review_comments", "reviews", "checks", "statuses"):
        identities = [row.get("id") for row in collections[name]]
        if any(type(x) is not int or x <= 0 for x in identities):
            raise DeliveryEvidenceInvalid("DELIVERY_RECORD_ID_INVALID")
        if len(set(identities)) != len(identities):
            coverage[name] = False
    stable = initial == current
    url = f"https://github.com/{repository}/pull/{pull_number}"
    restriction_refs = []
    if _RESTRICTION.search(_text(after.get("title")) + "\n" + _body(after.get("body"))):
        restriction_refs.append(url)
    if any(_RESTRICTION.search(_text(_obj(x).get("name"), 200)) for x in after["labels"]):
        restriction_refs.append(url + "#labels")
    for name in ("issue_comments", "review_comments", "reviews"):
        for item in collections[name]:
            body = _body(item.get("body"))
            identity = item.get("id")
            if type(identity) is not int or identity <= 0:
                raise DeliveryEvidenceInvalid("DELIVERY_COMMENT_ID_INVALID")
            if _RESTRICTION.search(body):
                prefix = {"issue_comments": "issuecomment-", "review_comments": "discussion_r", "reviews": "pullrequestreview-"}[name]
                restriction_refs.append(url + "#" + prefix + str(identity))
    # These are observed check runs, not a proof of required-check satisfaction.
    check_counts: Counter[str] = Counter()
    failures: list[dict] = []
    for item in collections["checks"]:
        if item.get("head_sha") != current["head_sha"]:
            coverage["checks"] = False
        status = _text(item.get("status"), 40)
        conclusion = item.get("conclusion")
        key = _text(conclusion, 40) if status == "completed" else status
        if status not in {"completed", "in_progress", "queued", "waiting", "pending", "requested"}:
            coverage["checks"] = False
            key = "unknown"
        if status == "completed" and key not in (_BAD_CHECK | {"success", "neutral", "skipped"}):
            coverage["checks"] = False
            key = "unknown"
        check_counts[key] += 1
        if key in _BAD_CHECK:
            failures.append({"id": _id(item.get("id")), "app_id": _id(_obj(item.get("app")).get("id"))})
    status_counts: Counter[str] = Counter()
    latest_statuses: dict[str, dict] = {}
    for item in collections["statuses"]:
        context = _text(item.get("context"), 512)
        identity = _id(item.get("id"))
        if context not in latest_statuses or identity > latest_statuses[context]["id"]:
            latest_statuses[context] = item
    for item in latest_statuses.values():
        state = _text(item.get("state"), 40)
        if state not in {"error", "failure", "pending", "success"}:
            coverage["statuses"] = False
            state = "unknown"
        status_counts[state] += 1
    current_reviews: Counter[str] = Counter()
    for item in collections["reviews"]:
        if item.get("commit_id") == current["head_sha"]:
            state = item.get("state")
            if state not in {"APPROVED", "CHANGES_REQUESTED", "COMMENTED", "DISMISSED", "PENDING"}:
                coverage["reviews"] = False
            else:
                current_reviews[state] += 1
    source_record_complete = stable and all(coverage[name] for name in (
        "files", "issue_comments", "review_comments", "reviews"))
    complete_metadata = source_record_complete and coverage["checks"] and coverage["statuses"]
    reasons = []
    if not stable:
        reasons.append("SOURCE_CHANGED_DURING_READ")
    if not all(coverage.values()):
        reasons.append("OBSERVATION_COVERAGE_INCOMPLETE")
    if current["head_repository"] != repository:
        reasons.append("FORK_SOURCE_REQUIRES_EXISTING_OWNER")
    if restriction_refs:
        reasons.append("POSSIBLE_RESTRICTION_REQUIRES_ADJUDICATION")
    if failures or status_counts.get("failure") or status_counts.get("error"):
        reasons.append("FAILED_CHECK_OBSERVED_NOT_REQUIRED_GATE_PROOF")
    mergeability = after.get("mergeable_state")
    if mergeability is not None and (type(mergeability) is not str or mergeability not in {
        "clean", "dirty", "unknown", "unstable", "blocked", "behind", "draft", "has_hooks"}):
        raise DeliveryEvidenceInvalid("DELIVERY_MERGEABILITY_INVALID")
    if mergeability in {"dirty", "behind", "blocked"}:
        reasons.append("INTEGRATION_OR_RELEASE_GATE_OBSERVED")
    observation_digest = digest({"before": before, "after": after, "collections": collections, "complete": coverage})
    qualification_digest = source_evidence_digest(repository=repository, pull_number=pull_number,
        current=after, collections=collections, complete=coverage)
    advice = None
    qualification_bound = False
    if qualification is not None:
        if type(qualification) is not DraftReadinessFacts:
            raise DeliveryEvidenceInvalid("DELIVERY_QUALIFICATION_INVALID")
        facts = qualification.lifecycle
        if (facts.repository != repository or facts.number != pull_number
                or qualification.current_head_sha != current["head_sha"]
                or facts.draft != current["draft"]
                or facts.merged != current["merged"]
                or facts.state.value.lower() != ("merged" if current["merged"] else current["state"])):
            raise DeliveryEvidenceInvalid("DELIVERY_QUALIFICATION_IDENTITY_MISMATCH")
        # A heuristic is never a new permanent hold. A trusted source owner
        # can adjudicate historical/released mentions only against these exact
        # observed bytes. This digest binds evidence; it authenticates nobody.
        qualification_bound = (type(qualification_evidence_digest) is str
            and qualification_evidence_digest == qualification_digest)
        if not qualification_bound:
            reasons.append("QUALIFICATION_OBSERVATION_UNBOUND")
        if source_record_complete and qualification_bound and current["head_repository"] == repository:
            assessed = assess_draft_readiness(qualification)
            advice = {"verdict": assessed.verdict.value, "issues": [x.value for x in assessed.issues]}
    if current["state"] != "open":
        next_action = "VERIFY_DELIVERED_CONSUMER" if current["merged"] else "NO_OPEN_PR_ACTION"
    elif not source_record_complete:
        next_action = "RECONCILE_OBSERVATION"
    elif restriction_refs and not (qualification_bound and qualification is not None
            and qualification.explicit_draft_hold is False):
        next_action = "ADJUDICATE_RECORDED_RESTRICTIONS"
    elif failures or status_counts.get("failure") or status_counts.get("error"):
        next_action = "INSPECT_FAILED_CHECKS_ON_ORIGINAL_CARRIER"
    elif not current["draft"] and mergeability in {"behind", "dirty"}:
        next_action = "RECONCILE_EXISTING_INTEGRATION_ROUTE"
    elif advice and advice["verdict"] == DraftReadinessVerdict.READY_CANDIDATE.value:
        next_action = "REVALIDATE_QUALIFIED_READY_TRANSITION"
    elif not current["draft"]:
        next_action = "VERIFY_EXISTING_PROTECTED_RELEASE_GATES"
    else:
        next_action = "VERIFY_SOURCE_COMPLETENESS_AND_CUSTODY"
    result = {
        "schema": SCHEMA, "repository": repository, "pull_number": pull_number,
        "head_sha": current["head_sha"], "base_sha": current["base_sha"],
        "observed_at": _timestamp(observed_at), "pr_url": url,
        "state": current["state"], "draft": current["draft"], "merged": current["merged"],
        "source_stable": stable, "metadata_coverage_complete": complete_metadata,
        "source_record_coverage_complete": source_record_complete,
        "ci_observation_coverage_complete": coverage["checks"] and coverage["statuses"],
        "coverage": coverage, "content_footprint": _footprint(collections["files"]),
        "source_maturity": "NOT_INFERRED", "source_review_coverage": "NOT_INFERRED",
        "possible_restriction_refs": sorted(set(restriction_refs)),
        "check_run_counts": dict(sorted(check_counts.items())),
        "commit_status_counts": dict(sorted(status_counts.items())),
        "failed_check_refs": failures, "required_checks_satisfied": None,
        "current_head_review_counts": dict(sorted(current_reviews.items())),
        "formal_approval_satisfied": None, "release_authorized": False,
        "auto_merge_observed": after.get("auto_merge") is not None,
        "mergeable_state_observed": mergeability, "qualification_advice": advice,
        "source_owner_qualification_bound": qualification_bound,
        "next_action": next_action, "reasons": reasons,
        "evidence_digest": observation_digest,
        "source_evidence_digest": qualification_digest,
    }
    return result

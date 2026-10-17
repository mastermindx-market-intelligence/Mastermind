"""Owner-native GitHub reads into the existing exact-candidate CI classifier.

The caller supplies its existing GET transport. This adapter owns no credentials,
scheduler, persistence, worker assignment, merge, deployment or wake delivery.
V1 supports same-repository candidates and unambiguous GitHub Actions check runs;
unsupported/partial evidence is an explicit error, never an inferred green.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from collections.abc import Callable
from urllib.parse import quote

from control_plane.github_release_assessment import (
    CI_OBSERVATION_INPUT_SCHEMA, CandidateCheckRun, CandidateCIObservation,
    CandidateCIObservationInput, CheckConclusion, CheckIdentity, CheckStatus,
    SourceOwner, SourceReference, SourceReferenceCoverage,
    assess_candidate_ci_observation,
)

_PAGE_SIZE = 100
_REPOSITORY = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*\Z")
_SHA = re.compile(r"[0-9a-f]{40}\Z")
_ACTIONS_APP = 15368
_ACTIVE_WORKFLOW_STATES = frozenset({"queued", "in_progress", "waiting", "pending", "requested"})


class CandidateReadError(ValueError):
    """The current observation cannot be safely constructed."""


def _digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _object(value: object, field: str) -> dict:
    if not isinstance(value, dict):
        raise CandidateReadError(f"invalid {field}")
    return value


def _positive(value: object, field: str) -> int:
    if type(value) is not int or value <= 0:
        raise CandidateReadError(f"invalid {field}")
    return value


class GitHubCandidateReader:
    """Stateless sampler using a bounded, already-authorized owner GET surface."""

    def __init__(self, *, read: Callable[[str], object], clock: Callable[[], float] = time.time, max_pages: int = 10):
        if not callable(read) or not callable(clock) or type(max_pages) is not int or not 1 <= max_pages <= 10:
            raise CandidateReadError("invalid reader configuration")
        self._read = read
        self._clock = clock
        self._max_pages = max_pages

    def _policy(self, prefix: str, branch: str) -> tuple[dict, tuple[CheckIdentity, ...]]:
        encoded = quote(branch, safe="")
        doc = _object(self._read(f"{prefix}/branches/{encoded}"), "branch")
        if doc.get("name") != branch or doc.get("protected") is not True:
            raise CandidateReadError("protected target branch not established")
        protection = _object(doc.get("protection"), "branch protection")
        required = protection.get("required_status_checks")
        rows: list[dict] = []
        if required is not None:
            required = _object(required, "required checks")
            checks = required.get("checks")
            contexts = required.get("contexts")
            if not isinstance(checks, list) or not isinstance(contexts, list):
                raise CandidateReadError("required-check policy coverage incomplete")
            if any(not isinstance(row, dict) for row in checks):
                raise CandidateReadError("invalid required-check policy")
            if set(contexts) != {row.get("context") for row in checks}:
                raise CandidateReadError("required-check policy coverage mismatch")
            rows.extend(checks)
        rules: list[dict] = []
        for page in range(1, self._max_pages + 1):
            part = self._read(f"{prefix}/rules/branches/{encoded}?per_page={_PAGE_SIZE}&page={page}")
            if not isinstance(part, list) or len(part) > _PAGE_SIZE or any(not isinstance(row, dict) for row in part):
                raise CandidateReadError("invalid ruleset coverage")
            rules.extend(part)
            if len(part) < _PAGE_SIZE:
                break
        else:
            raise CandidateReadError("ruleset coverage budget exhausted")
        for rule in rules:
            if rule.get("type") in {"workflows", "required_workflows"}:
                raise CandidateReadError("unsupported required-workflow policy")
            if rule.get("type") != "required_status_checks":
                continue
            parameters = _object(rule.get("parameters"), "ruleset parameters")
            checks = parameters.get("required_status_checks")
            if not isinstance(checks, list):
                raise CandidateReadError("invalid ruleset checks")
            for raw in checks:
                row = _object(raw, "ruleset check")
                rows.append({"context": row.get("context"), "app_id": row.get("integration_id")})
        keys: set[tuple[str, int]] = set()
        for row in rows:
            context, app = row.get("context"), row.get("app_id")
            if not isinstance(context, str) or not context or type(app) is not int or app != _ACTIONS_APP:
                raise CandidateReadError("unsupported required-check producer")
            keys.add((context, app))
        if not keys:
            raise CandidateReadError("no owner-native required checks")
        policy = {"branch": branch, "protected": True, "protection": protection, "rules": sorted(rules, key=_digest)}
        return policy, tuple(CheckIdentity(context, app) for context, app in sorted(keys))

    def _checks(self, prefix: str, head: str) -> list[dict]:
        rows: list[dict] = []
        total: int | None = None
        identifiers: set[int] = set()
        for page in range(1, self._max_pages + 1):
            doc = _object(self._read(f"{prefix}/commits/{head}/check-runs?filter=latest&per_page={_PAGE_SIZE}&page={page}"), "check runs")
            count, part = doc.get("total_count"), doc.get("check_runs")
            if type(count) is not int or count < 0 or not isinstance(part, list) or len(part) > _PAGE_SIZE:
                raise CandidateReadError("invalid check coverage")
            if total is not None and count != total:
                raise CandidateReadError("check coverage changed during pagination")
            total = count
            for raw in part:
                row = _object(raw, "check run")
                identifier = _positive(row.get("id"), "check run id")
                if identifier in identifiers or row.get("head_sha") != head:
                    raise CandidateReadError("duplicate or wrong-head check coverage")
                identifiers.add(identifier)
                rows.append(row)
            if len(rows) == total:
                return rows
            if len(rows) > total or len(part) < _PAGE_SIZE:
                raise CandidateReadError("check coverage incomplete")
        raise CandidateReadError("check coverage budget exhausted")

    def _jobs(self, prefix: str, head: str, workflow_id: int, attempt: int) -> tuple[list[dict], set[int]]:
        rows: list[dict] = []
        jobs: set[int] = set()
        checks: set[int] = set()
        total: int | None = None
        for page in range(1, self._max_pages + 1):
            endpoint = f"{prefix}/actions/runs/{workflow_id}/attempts/{attempt}/jobs?per_page={_PAGE_SIZE}&page={page}"
            doc = _object(self._read(endpoint), "workflow jobs")
            count, part = doc.get("total_count"), doc.get("jobs")
            if type(count) is not int or count < 0 or not isinstance(part, list) or len(part) > _PAGE_SIZE:
                raise CandidateReadError("invalid job coverage")
            if total is not None and count != total:
                raise CandidateReadError("job coverage changed during pagination")
            total = count
            for raw in part:
                job = _object(raw, "workflow job")
                job_id = _positive(job.get("id"), "job id")
                run_id = _positive(job.get("run_id"), "job workflow id")
                run_attempt = _positive(job.get("run_attempt"), "job attempt")
                if run_id != workflow_id or run_attempt != attempt or job.get("head_sha") != head:
                    raise CandidateReadError("job does not belong to current workflow attempt")
                url = job.get("check_run_url")
                match = re.fullmatch(rf"https://api\.github\.com/{re.escape(prefix)}/check-runs/([1-9][0-9]*)", url) if isinstance(url, str) else None
                if match is None:
                    raise CandidateReadError("job check identity is unbound")
                check_id = int(match.group(1))
                if job_id in jobs or check_id in checks:
                    raise CandidateReadError("duplicate job coverage")
                jobs.add(job_id)
                checks.add(check_id)
                rows.append(job)
            if len(rows) == total:
                return rows, checks
            if len(rows) > total or len(part) < _PAGE_SIZE:
                raise CandidateReadError("job coverage incomplete")
        raise CandidateReadError("job coverage budget exhausted")

    def sample(self, *, repository: str, pull_request_number: int, expected_head_sha: str) -> CandidateCIObservation:
        if not isinstance(repository, str) or not _REPOSITORY.fullmatch(repository):
            raise CandidateReadError("invalid repository")
        _positive(pull_request_number, "pull request number")
        if not isinstance(expected_head_sha, str) or not _SHA.fullmatch(expected_head_sha):
            raise CandidateReadError("invalid expected head")
        prefix = f"repos/{repository}"
        pull_path = f"{prefix}/pulls/{pull_request_number}"
        started_at = int(self._clock())
        pull = _object(self._read(pull_path), "pull request")
        if pull.get("number") != pull_request_number or pull.get("state") != "open":
            raise CandidateReadError("candidate pull request is not open")
        head = _object(pull.get("head"), "pull head")
        base = _object(pull.get("base"), "pull base")
        head_repo = _object(head.get("repo"), "head repository")
        base_repo = _object(base.get("repo"), "base repository")
        repository_id = _positive(base_repo.get("id"), "repository id")
        if head_repo.get("id") != repository_id or head_repo.get("full_name") != repository or base_repo.get("full_name") != repository:
            raise CandidateReadError("cross-repository candidate is unsupported")
        observed_head, candidate_ref, branch = head.get("sha"), head.get("ref"), base.get("ref")
        if not isinstance(observed_head, str) or not _SHA.fullmatch(observed_head):
            raise CandidateReadError("invalid observed head")
        if any(not isinstance(value, str) or not value or len(value) > 255 for value in (candidate_ref, branch)):
            raise CandidateReadError("invalid candidate or base ref")
        policy, required_checks = self._policy(prefix, branch)
        policy_revision = "github-ci-policy:" + _digest(policy)
        raw_checks = self._checks(prefix, observed_head)
        workflows: dict[int, dict] = {}
        workflow_jobs: dict[int, list[dict]] = {}
        workflow_checks: dict[int, set[int]] = {}
        pending_membership: set[int] = set()
        selected: list[tuple[CheckIdentity, dict, int, dict]] = []
        for identity in required_checks:
            matching = [row for row in raw_checks if row.get("name") == identity.context and _object(row.get("app"), "check producer").get("id") == identity.app_id]
            if len(matching) > 1:
                raise CandidateReadError("ambiguous latest required-check generation")
            if not matching:
                continue
            row = matching[0]
            url = row.get("details_url")
            pattern = rf"https://github\.com/{re.escape(repository)}/actions/runs/([1-9][0-9]*)(?:/job/[1-9][0-9]*)?\Z"
            match = re.fullmatch(pattern, url) if isinstance(url, str) else None
            if match is None:
                raise CandidateReadError("unbound workflow identity")
            workflow_id = int(match.group(1))
            if workflow_id not in workflows:
                workflows[workflow_id] = _object(self._read(f"{prefix}/actions/runs/{workflow_id}"), "workflow")
            workflow = workflows[workflow_id]
            suite = _object(row.get("check_suite"), "check suite")
            if workflow.get("id") != workflow_id or workflow.get("head_sha") != observed_head or workflow.get("check_suite_id") != suite.get("id"):
                raise CandidateReadError("workflow/check identity mismatch")
            attempt = _positive(workflow.get("run_attempt"), "workflow attempt")
            if workflow_id not in workflow_jobs:
                job_rows, check_ids = self._jobs(prefix, observed_head, workflow_id, attempt)
                workflow_jobs[workflow_id] = job_rows
                workflow_checks[workflow_id] = check_ids
            if row["id"] not in workflow_checks[workflow_id]:
                if workflow.get("status") in _ACTIVE_WORKFLOW_STATES:
                    # An active attempt may not have materialized its jobs yet.
                    # Omit the unqualified old check, not the required identity:
                    # the existing classifier then reports CHECK_MISSING/PENDING.
                    pending_membership.add(workflow_id)
                    continue
                raise CandidateReadError("check is not in current workflow attempt")
            selected.append((identity, row, workflow_id, workflow))
        # Revalidate candidate and policy after pagination, not just before it.
        after = _object(self._read(pull_path), "pull request revalidation")
        def candidate_identity(document: dict) -> tuple:
            candidate = _object(document.get("head"), "candidate head")
            target = _object(document.get("base"), "candidate base")
            candidate_repo = _object(candidate.get("repo"), "candidate repository")
            target_repo = _object(target.get("repo"), "target repository")
            return (
                document.get("number"), document.get("state"),
                candidate.get("sha"), candidate.get("ref"),
                candidate_repo.get("id"), candidate_repo.get("full_name"),
                target.get("ref"), target_repo.get("id"), target_repo.get("full_name"),
            )
        # The base commit and repository telemetry may advance independently.
        # Exact candidate/target identity and freshly reread policy are binding.
        if candidate_identity(after) != candidate_identity(pull):
            raise CandidateReadError("candidate changed during sample")
        final_policy, final_checks = self._policy(prefix, branch)
        if _digest(final_policy) != _digest(policy) or final_checks != required_checks:
            raise CandidateReadError("required-check policy changed during sample")
        for workflow_id, original in workflows.items():
            current = _object(self._read(f"{prefix}/actions/runs/{workflow_id}"), "workflow revalidation")
            if any(current.get(key) != original.get(key) for key in ("id", "head_sha", "check_suite_id", "run_attempt")):
                raise CandidateReadError("workflow generation changed during sample")
            if workflow_id in pending_membership and current.get("status") not in _ACTIVE_WORKFLOW_STATES:
                raise CandidateReadError("check is not in current workflow attempt")
        now = int(self._clock())

        def ref(kind: str, resource: str, revision: str, content: object) -> SourceReference:
            return SourceReference(
                source_kind="owner_native", owner=SourceOwner.GITHUB,
                repository=repository, resource_kind=kind, resource_id=resource,
                revision=revision, observed_at=started_at, valid_at=None,
                content_sha256=_digest(content), coverage=SourceReferenceCoverage.COMPLETE,
                truncated=False, continuation=None,
            )

        statuses = {
            "queued": CheckStatus.QUEUED, "waiting": CheckStatus.QUEUED,
            "pending": CheckStatus.QUEUED, "requested": CheckStatus.QUEUED,
            "in_progress": CheckStatus.IN_PROGRESS, "completed": CheckStatus.COMPLETED,
        }
        check_runs = []
        for identity, row, workflow_id, workflow in selected:
            raw_status, raw_conclusion = row.get("status"), row.get("conclusion")
            if not isinstance(raw_status, str) or raw_status not in statuses:
                raise CandidateReadError("unsupported native check status")
            try:
                conclusion = None if raw_conclusion is None else CheckConclusion(raw_conclusion.upper())
            except (AttributeError, ValueError):
                raise CandidateReadError("unsupported native check conclusion") from None
            check_runs.append(CandidateCheckRun(
                identity=identity, head_sha=observed_head, check_run_id=row["id"],
                workflow_run_id=workflow_id, attempt=workflow["run_attempt"],
                sequence=row["id"], status=statuses[raw_status], conclusion=conclusion,
                applicable=True, superseded=False,
                source_ref=ref("check_run", f"check-run:{row['id']}", observed_head, row),
            ))
        packet = CandidateCIObservationInput(
            schema=CI_OBSERVATION_INPUT_SCHEMA, observed_at=now, repository=repository,
            repository_id=repository_id, pull_request_number=pull_request_number,
            candidate_ref=candidate_ref, expected_head_sha=expected_head_sha,
            observed_head_sha=observed_head, policy_revision=policy_revision,
            required_checks=required_checks, allowed_non_success_checks=(),
            check_runs=tuple(check_runs), checks_complete=True,
            policy_source_ref=ref("required_checks_policy", policy_revision, policy_revision, final_policy),
            checks_source_ref=ref("commit_check_runs", observed_head, observed_head, {
                "pull": pull, "checks": raw_checks, "workflows": workflows,
                "attempt_jobs": workflow_jobs,
            }),
        )
        return assess_candidate_ci_observation(packet)

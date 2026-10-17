from __future__ import annotations

import inspect

import pytest

from control_plane.executive_runtime import (
    Attempt,
    AttemptStatus,
    Job,
    JobStatus,
    StateConflict,
    Worker,
    WorkerStatus,
)
from control_plane.operator_continuation import OperatorContinuationError, semantic_draft_digest
from control_plane.operator_continuation_sources import (
    ContinuationExternalRefs,
    build_current_continuation_draft,
)


SOURCE_ID = "ATT-0123456789abcdef0123456789abcdef"
TARGET_ID = "ATT-fedcba98765432100123456789abcdef"
GRANT_DIGEST = "a" * 64
SOURCE_SHA = "b" * 40


def _worker(worker_id: str, provider: str, account: str) -> Worker:
    return Worker(
        worker_id=worker_id,
        provider=provider,
        account_label=account,
        worker_type="fixture",
        status=WorkerStatus.AVAILABLE,
        capabilities=["operator"],
        active_job_id=None,
        last_seen_at="2026-09-15T00:00:00.000Z",
        metadata={},
        quota_classes={},
    )


def _attempt(
    attempt_id: str,
    *,
    worker_id: str,
    status: AttemptStatus,
    checkpoint=None,
    grant: bool = True,
) -> Attempt:
    return Attempt(
        attempt_id=attempt_id,
        job_id="JOB-002",
        attempt_number=1 if attempt_id == SOURCE_ID else 2,
        worker_id=worker_id,
        quota_class="default",
        status=status,
        fence_generation=1,
        lease_owner="fixture",
        lease_expires_at="2026-09-15T01:00:00.000Z",
        heartbeat_at="2026-09-15T00:00:00.000Z",
        checkpoint_sequence=1 if checkpoint else 0,
        checkpoint=checkpoint,
        result=None,
        error=None,
        started_at="2026-09-15T00:00:00.000Z",
        finished_at="2026-09-15T00:10:00.000Z" if status is AttemptStatus.RATE_LIMITED else "",
        version=1,
        authority_policy_hash="policy",
        pid=None,
        pgid=None,
        process_start_identity=None,
        boot_id=None,
        provider_session_id=None,
        stdout_path=None,
        stderr_path=None,
        result_path=None,
        exit_code=None,
        launch_metadata={},
        effective_grant={"schema_version": "mastermind.executive_effective_grant/v1"} if grant else None,
        effective_grant_digest=GRANT_DIGEST if grant else None,
    )


def _job(*, current_attempt_id: str = TARGET_ID) -> Job:
    return Job(
        job_id="JOB-002",
        objective="Continue durable orchestration",
        department="general",
        priority=0,
        status=JobStatus.RUNNING,
        assigned_worker_id="worker-b",
        assigned_quota_class="default",
        authority_level="A0",
        branch=None,
        worktree=None,
        checkpoint=None,
        result=None,
        created_at="2026-09-15T00:00:00.000Z",
        updated_at="2026-09-15T00:00:00.000Z",
        current_attempt_id=current_attempt_id,
        attempt_count=2,
        attempt_limit=3,
        root_job_id="JOB-001",
    )


class _Registry:
    def __init__(self, values):
        self.values = values

    def get_attempt(self, key):
        return self.values.get(key)

    def get_job(self, key):
        return self.values.get(key)

    def get_worker(self, key):
        return self.values.get(key)


class _Runtime:
    def __init__(self, source, target, job, workers):
        self.attempts = _Registry({source.attempt_id: source, target.attempt_id: target})
        self.jobs = _Registry({job.job_id: job})
        self.workers = _Registry(workers)


def _refs(**changes) -> ContinuationExternalRefs:
    values = dict(
        operation_key="operator-continuity-ocr3-sources-20260914",
        target_seat="coo",
        session_alias="COO-PRIMARY",
        source_authority_refs=("docs/authority.md",),
        agentos_refs=("WS:EXECUTIVE-CAPACITY-FABRIC",),
        github_state={"repository": "mastermindx-market-intelligence/Mastermind", "head_sha": SOURCE_SHA},
        slack_dialogue_ref=None,
        accepted_ruling_refs=("DEC:CONTINUITY",),
        source_revisions={"Mastermind": SOURCE_SHA},
    )
    values.update(changes)
    return ContinuationExternalRefs(**values)


def _runtime(*, source_status=AttemptStatus.RATE_LIMITED, target_status=AttemptStatus.CLAIMED, grant=True):
    checkpoint = {
        "summary": "handoff-ready",
        "current_state": "continuing",
        "next_actions": ["Resume the exact unfinished orchestration dependency."],
        "errors": ["provider capacity remains unknown"],
    }
    source = _attempt(SOURCE_ID, worker_id="worker-a", status=source_status, checkpoint=checkpoint)
    target = _attempt(TARGET_ID, worker_id="worker-b", status=target_status, grant=grant)
    return _Runtime(
        source,
        target,
        _job(),
        {
            "worker-a": _worker("worker-a", "anthropic", "realm-a"),
            "worker-b": _worker("worker-b", "openai-codex", "realm-b"),
        },
    )


def test_builder_has_no_timestamp_or_capsule_identity_parameter():
    params = inspect.signature(build_current_continuation_draft).parameters
    assert "generated_at" not in params
    assert "capsule_id" not in params


def test_builds_source_grounded_cross_realm_draft():
    draft = build_current_continuation_draft(
        _runtime(), source_attempt_id=SOURCE_ID, target_attempt_id=TARGET_ID, refs=_refs()
    )
    assert draft.root_job_id == "JOB-001"
    assert draft.job_id == "JOB-002"
    assert draft.effective_grant_digest == GRANT_DIGEST
    assert draft.prior_attempt_receipt["status"] == "RATE_LIMITED"
    assert draft.prior_attempt_receipt["terminal"] is True
    assert draft.checkpoint["summary"] == "handoff-ready"
    assert draft.next_action.startswith("Resume the exact unfinished")
    assert draft.known_unknowns == ("provider capacity remains unknown",)


def test_pre_prepare_source_movement_changes_semantic_digest():
    first = build_current_continuation_draft(
        _runtime(), source_attempt_id=SOURCE_ID, target_attempt_id=TARGET_ID, refs=_refs()
    )
    second = build_current_continuation_draft(
        _runtime(),
        source_attempt_id=SOURCE_ID,
        target_attempt_id=TARGET_ID,
        refs=_refs(source_revisions={"Mastermind": "c" * 40}),
    )
    assert semantic_draft_digest(first) != semantic_draft_digest(second)


@pytest.mark.parametrize("status", [AttemptStatus.CLAIMED, AttemptStatus.RUNNING, AttemptStatus.CHECKPOINTED])
def test_refuses_nonterminal_source(status):
    with pytest.raises(StateConflict, match="source attempt must be terminal"):
        build_current_continuation_draft(
            _runtime(source_status=status), source_attempt_id=SOURCE_ID, target_attempt_id=TARGET_ID, refs=_refs()
        )


def test_refuses_target_that_is_not_current():
    runtime = _runtime()
    runtime.jobs = _Registry({"JOB-002": _job(current_attempt_id=SOURCE_ID)})
    with pytest.raises(StateConflict, match="not the job's current attempt"):
        build_current_continuation_draft(
            runtime, source_attempt_id=SOURCE_ID, target_attempt_id=TARGET_ID, refs=_refs()
        )


def test_refuses_missing_effective_grant():
    with pytest.raises(StateConflict, match="lacks an effective grant"):
        build_current_continuation_draft(
            _runtime(grant=False), source_attempt_id=SOURCE_ID, target_attempt_id=TARGET_ID, refs=_refs()
        )


def test_refuses_same_realm_claim():
    runtime = _runtime()
    runtime.workers = _Registry(
        {
            "worker-a": _worker("worker-a", "anthropic", "realm-a"),
            "worker-b": _worker("worker-b", "anthropic", "realm-a"),
        }
    )
    # Same provider/account is enough to prove there was no realm change even if
    # an implementation materializes a different Worker identity.
    with pytest.raises(StateConflict, match="cross-realm claim"):
        build_current_continuation_draft(
            runtime, source_attempt_id=SOURCE_ID, target_attempt_id=TARGET_ID, refs=_refs()
        )


def test_external_refs_cannot_smuggle_provider_session_authority():
    with pytest.raises(OperatorContinuationError, match="provider/credential authority"):
        build_current_continuation_draft(
            _runtime(),
            source_attempt_id=SOURCE_ID,
            target_attempt_id=TARGET_ID,
            refs=_refs(github_state={"provider_session_id": "opaque-session"}),
        )

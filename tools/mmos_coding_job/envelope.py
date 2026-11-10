"""Task-origin ``ChildExecutionRequest`` builder for Paperclip coding jobs (T4b).

HOST-SIDE: this module imports control_plane and runs inside the Executive
door (the trusted host that freezes ``child_request_material``).  The wake
carrier never imports it — the carrier mirrors only ``admission_command_id``
in six stdlib lines (pinned byte-identical by
``tests/test_mmos_teammate_coding_job.py``).

Idempotency triple for one task's coding job:
``(roots/paperclip-<issueId>, parents/paperclip-<issueId>, <key>)`` — the
task IS the parent; one task admits one coding job per key (default
``coding-job-1``).  The task title+description is the brief; its digest is
frozen at intake, so a body edited afterwards does not drift the job (the
frozen material is authoritative, exactly like the ingress tests).
"""
from __future__ import annotations

import hashlib

from control_plane.child_execution_contracts import (
    C1_ROUTINE_BOUNDED,
    ChildExecutionRequest,
    OriginalRequesterBinding,
)
from control_plane.child_request_admission import admission_command_id

#: The origin kind this lane registers a transport for at the seam.
CARRIER_KIND = "paperclip_task"

#: The default logical child key of a task's coding job.
DEFAULT_JOB_KEY = "coding-job-1"


def root_ref_for(issue_id) -> str:
    return f"roots/paperclip-{issue_id}"


def parent_ref_for(issue_id) -> str:
    return f"parents/paperclip-{issue_id}"


def brief_digest(title: str, description: str) -> str:
    brief = f"{(title or '').strip()}\n{(description or '').strip()}"
    return hashlib.sha256(brief.encode("utf-8")).hexdigest()


def build_task_request(
    *,
    issue_id,
    agent_id,
    company_id,
    title: str,
    description: str,
    key: str = DEFAULT_JOB_KEY,
) -> ChildExecutionRequest:
    """One governed coding job for one Paperclip task.

    The requester block names where the sealed result must return:
    ``conversation_id`` carries the Paperclip issue (the transport's target),
    ``carrier_kind`` selects the ``paperclip_task`` delivery route.
    """
    return ChildExecutionRequest(
        root_ref=root_ref_for(issue_id),
        immediate_parent_run_ref=parent_ref_for(issue_id),
        logical_child_key=str(key),
        task_kind="code",
        requested_complexity=C1_ROUTINE_BOUNDED,
        brief_ref=f"paperclip-issue:{issue_id}",
        brief_digest=brief_digest(title, description),
        fallback_mode="shared",
        runtime_preference="t3-native",
        original_requester=OriginalRequesterBinding(
            teammate_id=f"paperclip-agent:{agent_id}",
            conversation_id=f"paperclip-issue:{issue_id}",
            project_id=f"paperclip-company:{company_id}",
            carrier_kind=CARRIER_KIND,
        ),
    )


def task_command(request: ChildExecutionRequest) -> str:
    """The command the carrier names; minted from the triple only."""
    return admission_command_id(request)

"""Initial-planning bounds in the incumbent authority-map and launch owners.

No ledger, token/currency limit, lease or provider is created here. The existing
command/Attempt rows enforce counts; WorkerLaunchSpec enforces wall time and
artifact bounds through the incumbent physical worker adapter.
"""
from dataclasses import dataclass
import hashlib
import re

from control_plane.ceo_boot_packet import bounded_subprocess_runner
from control_plane.executive_coo_policy import _extract_block, CooCyclePolicyError

COMMISSION_PATH = "research/executive_commissions/PROJECT_INITIAL_PLANNING.md"
EXPECTED = dict(schema_version=1,max_jobs_per_original_request=1,max_attempts_per_job=1,
    max_worker_seconds=300,max_artifacts=0,cancel_grace_seconds=10)


def read_protected_blob(root,base_sha,relative):
    if relative not in {"config/authority_map.yml",COMMISSION_PATH,"research/executive_commissions/PROJECT_EXECUTION.md"} or type(base_sha) is not str or re.fullmatch('[0-9a-f]{40}',base_sha) is None:
        raise ValueError("project planning protected source invalid")
    result=bounded_subprocess_runner(["git","--no-optional-locks","--no-replace-objects","-C",str(root),
        "show",base_sha+":"+relative],cwd=root,timeout=5,max_bytes=2*1024*1024)
    if (type(result) is not dict or result.get("code")!=0 or type(result.get("stdout")) is not str
            or any(result.get(key) is True for key in ("timed_out","limit_exceeded","invalid_utf8"))):
        raise ValueError("project planning protected source unavailable")
    return result["stdout"].encode('utf-8')


@dataclass(frozen=True,slots=True)
class PlanningPolicy:
    source_sha256:str
    max_jobs_per_original_request:int
    max_attempts_per_job:int
    max_worker_seconds:int
    max_artifacts:int
    cancel_grace_seconds:int

    @classmethod
    def load(cls,root,base_sha):
        raw=read_protected_blob(root,base_sha,"config/authority_map.yml")
        try: fields=_extract_block(raw,"project_initial_planning_policy")
        except CooCyclePolicyError:
            raise ValueError("project planning budget absent or unqualified") from None
        if fields!=EXPECTED:
            raise ValueError("project planning budget exhausted or changed")
        return cls(hashlib.sha256(raw).hexdigest(),**{key:fields[key] for key in fields if key!='schema_version'})


def launch_limits(runtime,job):
    """Rejoin immutable context/policy before the existing physical launch."""
    material=runtime.jobs.direct_native_provenance(job.job_id)
    if 'project_planning' not in material:
        return {}
    policy=PlanningPolicy.load(job.worktree,job.constraints.get('base_sha'))
    if (material['project_planning']['budget_ref']!='project-planning-policy:'+policy.source_sha256
            or job.attempt_limit!=policy.max_attempts_per_job):
        raise ValueError("project planning physical launch budget differs")
    return dict(timeout_seconds=policy.max_worker_seconds,max_artifacts=policy.max_artifacts,
        cancel_grace_seconds=policy.cancel_grace_seconds)

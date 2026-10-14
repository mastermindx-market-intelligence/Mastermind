"""Prepare the existing finite Attempt's workspace, without another lifecycle.

The owning Supervisor has already created this Attempt's schema and private
commission input in its dedicated run store. The canonical Job keeps its source
worktree. Only the immutable worker spec uses the new credentialless clone.
"""
from __future__ import annotations

import dataclasses
import os
from pathlib import Path
import re
import stat

from control_plane.executive_worker_broker import BrokerStateError
from control_plane.fabric_attended_canary import host_root


def prepare_assignment(spec, worker, job):
    from control_plane.executive_supervisor import ExecutiveSupervisor
    from control_plane.executive_workspace import prepare_credentialless_clone

    host_root(worker)
    roots = tuple(Path(worker[key]) for key in ('workspace_root', 'run_root'))
    source = Path(spec.workspace_path)
    run = Path(spec.run_dir)
    schema = Path(spec.result_schema_path)
    if (os.geteuid() != worker['control_uid']
            or worker['worker_gid'] not in set(os.getgroups()) | {os.getegid()}
            or spec.worker_id != worker['worker_id'] or spec.job_id != job.job_id
            or spec.expected_worker_uid != worker['worker_uid']
            or spec.expected_worker_gid != worker['worker_gid']
            or spec.shared_run_gid != worker['worker_gid']
            or source != Path(job.worktree).resolve(strict=True)
            or run.parent != roots[1] or run.name != spec.run_id
            or schema != run/'input/worker-result.schema.json'
            or not re.fullmatch(r'[0-9a-f]{40}', spec.expected_base_sha or '')
            or spec.expected_base_sha != job.constraints.get('base_sha')
            or spec.allowed_artifact_paths or tuple(spec.authorities) != ('READ',)):
        raise BrokerStateError('finite assignment differs from original read-only Job/Attempt')
    for root in roots:
        info = root.lstat()
        if (root.resolve(strict=True) != root or not stat.S_ISDIR(info.st_mode)
                or info.st_uid != worker['control_uid'] or info.st_gid != worker['worker_gid']
                or stat.S_IMODE(info.st_mode) & 0o027):
            raise BrokerStateError('finite assignment store is not the protected Control boundary')
    for path in (run, schema.parent, schema):
        info = path.lstat()
        if (path.resolve(strict=True) != path or info.st_uid != worker['control_uid']
                or info.st_gid != worker['worker_gid'] or stat.S_IMODE(info.st_mode) & 0o007
                or stat.S_ISLNK(info.st_mode)):
            raise BrokerStateError('finite original input is not Control-owned at the selected group')
    clone = prepare_credentialless_clone(source, roots[0], job_id=spec.run_id,
        base_sha=spec.expected_base_sha, branch=job.branch,
        shared_gid=worker['worker_gid'], shared_write_paths=())
    workspace = Path(clone.workspace_path)
    denied, manifest, digest = ExecutiveSupervisor._isolation_manifest(
        roots, workspace=workspace, run_dir=run)
    projected = dataclasses.replace(spec, workspace_path=workspace,
        isolation_roots=tuple(sorted(roots, key=str)), isolation_denied_paths=denied,
        isolation_manifest=manifest, isolation_manifest_sha256=digest)
    return projected, {'input_root': str(schema.parent), 'source_workspace': str(source)}

"""Concrete, bounded acquisition for the existing coordination host.

No new artifact store, lifecycle, permission service, or provider. The installed
host supplies its existing bound Runtime and configured workspace scope. Read
eligibility comes from canonical completed SEALED_WORKER evidence, not caller
Job objects, file names, a model's claim, or construction of this reader.
"""
from __future__ import annotations

import hashlib
import os
import re
import stat
from contextlib import ExitStack
from pathlib import Path, PurePosixPath
from typing import Any

from control_plane.chairman_coordination_work import _artifact_path
from control_plane.executive_runtime import Runtime, Job, Attempt, JobStatus, AttemptStatus
from control_plane.executive_supervisor import SupervisorError
from control_plane.fabric_result_projection import project_fabric_role_result

_MAX_ARTIFACT_BYTES = 128 * 1024
_MAX_PATH_DEPTH = 32
_SEALED_DIRECTORY_MODE = 0o700
_MAX_COMPILED_CONTEXT_BYTES = 524288


def _identity(info: os.stat_result) -> tuple[int, ...]:
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
            info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _namespace_anchor(info: os.stat_result) -> tuple[int, ...]:
    # The configured parent is shared by independent project workspaces. Its
    # entry-count/mtime may change without changing this exact selected child.
    # Device, inode, ownership and access mode remain fenced independently.
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid)


def _absolute(value: Any) -> Path:
    if not isinstance(value, (str, Path)):
        raise SupervisorError("configured workspace scope is invalid")
    text = str(value)
    path = PurePosixPath(text)
    if (not path.is_absolute() or str(path) != text or ".." in path.parts
            or len(path.parts) > _MAX_PATH_DEPTH or any(ord(c) < 32 for c in text)):
        raise SupervisorError("configured workspace scope is invalid")
    return Path(text)


class SealedCoordinationArtifactReader:
    """Read one configured artifact from an exact sealed coordination assignment.

    Compatible with the existing host artifact_reader callback. Construction is
    inert. Calls acquire canonical Runtime evidence afresh, close that observation,
    then read a bounded regular file through retained no-follow descriptors. The
    surrounding host independently checks the original result selector again.

    This is intentionally not a generic artifact reader. It supports local
    SEALED_WORKER completion with the existing terminal assignment seal and
    collected artifact manifest only; unsealed/OHF/foreign work is refused. The
    host owns read authorization and Runtime namespace acquisition. Hashes and
    caller-created dataclasses never authenticate those owners.
    """

    def __init__(self, *, runtime: Runtime, workspace_root: Path, project_ref: str,
                 job_id: str, artifact_path: str) -> None:
        if type(runtime) is not Runtime:
            raise SupervisorError("existing bound Runtime reader is required")
        if type(job_id) is not str or re.fullmatch(r"JOB-[0-9]{1,9}", job_id) is None:
            raise SupervisorError("exact coordination Job is required")
        if type(project_ref) is not str or re.fullmatch(r"WS:[A-Za-z0-9][A-Za-z0-9._-]{1,63}", project_ref) is None:
            raise SupervisorError("exact project reference is required")
        try:
            path = _artifact_path(artifact_path)
        except Exception as exc:
            raise SupervisorError("exact artifact configuration is invalid") from exc
        self._runtime = runtime
        self._root = _absolute(workspace_root)
        self._project = project_ref
        self._job_id = job_id
        self._artifact = path

    def __call__(self, job: Job, attempt: Attempt, artifact_path: str, *,
                 expected_sha256: str, max_bytes: int) -> bytes:
        try:
            return self._read(job, attempt, artifact_path, expected_sha256, max_bytes)
        except Exception as exc:
            # Bounded public error, not private workspace/source diagnostics.
            raise SupervisorError("sealed coordination artifact is unavailable") from exc

    def _read(self, job: Job, attempt: Attempt, path: str, digest: str, limit: int) -> bytes:
        if (type(job) is not Job or type(attempt) is not Attempt
                or job.job_id != self._job_id or attempt.job_id != job.job_id
                or job.current_attempt_id != attempt.attempt_id
                or job.status is not JobStatus.COMPLETED
                or attempt.status is not AttemptStatus.COMPLETED
                or path != self._artifact or _artifact_path(path) != path
                or type(digest) is not str or re.fullmatch(r"[0-9a-f]{64}", digest) is None
                or type(limit) is not int or not 0 < limit <= _MAX_ARTIFACT_BYTES):
            raise SupervisorError("artifact selection is not exact")
        selected = job.result.get("result_envelope_digest") if isinstance(job.result, dict) else None
        if type(selected) is not str or re.fullmatch(r"[0-9a-f]{64}", selected) is None:
            raise SupervisorError("completed result selector is missing")
        with self._runtime.observe_bounded_read() as observation:
            snapshot = observation.read_role_result_bounded(
                job.root_job_id, job.job_id, expected_attempt_id=attempt.attempt_id,
                expected_result_envelope_digest=selected)
        projected = project_fabric_role_result(snapshot, observation.receipt).complete
        current = snapshot.completion
        if (snapshot.root_metadata.work_ref != self._project or projected["role"] != "work"
                or current.execution_mode != "SEALED_WORKER"
                or current.job.to_dict() != job.to_dict() or current.attempt.to_dict() != attempt.to_dict()
                or current.result_envelope["errors"]):
            raise SupervisorError("artifact source is not the selected sealed work")
        grant = current.attempt.effective_grant
        if (not isinstance(grant, dict) or "WRITE_BRANCH" not in grant.get("authorities", [])
                or path not in grant.get("write_paths", [])):
            raise SupervisorError("artifact was not an exact granted write")
        evidence = current.terminal_receipt["result_evidence"]
        seal = evidence["assignment_seal_receipt"]
        sealed = seal["paths"]["workspace"]
        identity = sealed["after"]
        root = _absolute(current.job.worktree)
        relative_root = root.relative_to(self._root)
        if not relative_root.parts or len(relative_root.parts) > _MAX_PATH_DEPTH:
            raise SupervisorError("assignment is outside configured child scope")
        if (seal["passed"] is not True or sealed["worker_traversal_revoked"] is not True
                or seal["job_id"] != job.job_id or seal["attempt_id"] != attempt.attempt_id
                or identity["path"] != str(root) or identity["mode"] != _SEALED_DIRECTORY_MODE
                or seal["control_uid"] != os.geteuid()):
            raise SupervisorError("assignment seal is not current control-private evidence")
        manifest = evidence["collection_receipt"]["collection"]["result"]["artifact_manifest"]
        matches = [item for item in manifest if item["path"] == path]
        declared = [item for item in projected["content"]["role_result"]["artifacts"] if item["path"] == path]
        if (len(matches) != 1 or matches[0]["sha256"] != digest
                or type(matches[0]["size"]) is not int or not 0 < matches[0]["size"] <= limit
                or declared != [{"path": path, "digest": digest}]):
            raise SupervisorError("artifact collection evidence does not match selection")
        return self._file_bytes(relative_root.parts, PurePosixPath(path).parts,
                                identity, digest, matches[0]["size"], limit)

    def _file_bytes(self, workspace_parts: tuple[str, ...], artifact_parts: tuple[str, ...],
                    sealed: dict[str, Any], digest: str, size: int, limit: int) -> bytes:
        if (not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY")
                or not hasattr(os, "O_NONBLOCK") or len(artifact_parts) > _MAX_PATH_DEPTH):
            raise SupervisorError("required safe-file primitives are unavailable")
        directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
        file_flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | getattr(os, "O_CLOEXEC", 0)
        with ExitStack() as close:
            root_fd = os.open(self._root, directory_flags); close.callback(os.close, root_fd)
            root_info = os.fstat(root_fd)
            if not stat.S_ISDIR(root_info.st_mode) or root_info.st_uid != os.geteuid() or stat.S_IMODE(root_info.st_mode) & 0o022:
                raise SupervisorError("configured workspace root is not protected")
            retained = []
            parent_fd = root_fd
            for name in workspace_parts:
                child_fd = os.open(name, directory_flags, dir_fd=parent_fd); close.callback(os.close, child_fd)
                before = os.fstat(child_fd)
                if not stat.S_ISDIR(before.st_mode) or before.st_dev != root_info.st_dev:
                    raise SupervisorError("workspace traversal crossed its source")
                retained.append((parent_fd, name, child_fd, before)); parent_fd = child_fd
            actual = os.fstat(parent_fd)
            fields = {"device":actual.st_dev,"inode":actual.st_ino,"uid":actual.st_uid,
                      "gid":actual.st_gid,"mode":stat.S_IMODE(actual.st_mode)}
            if any(sealed[key] != value for key, value in fields.items()):
                raise SupervisorError("sealed workspace identity changed")
            for name in artifact_parts[:-1]:
                child_fd = os.open(name, directory_flags, dir_fd=parent_fd); close.callback(os.close, child_fd)
                before = os.fstat(child_fd)
                if not stat.S_ISDIR(before.st_mode) or before.st_dev != actual.st_dev or stat.S_IMODE(before.st_mode) & 0o002:
                    raise SupervisorError("artifact directory is unsafe")
                retained.append((parent_fd, name, child_fd, before)); parent_fd = child_fd
            fd = os.open(artifact_parts[-1], file_flags, dir_fd=parent_fd); close.callback(os.close, fd)
            before = os.fstat(fd)
            if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                    or before.st_dev != actual.st_dev or stat.S_IMODE(before.st_mode) & 0o002
                    or before.st_size != size or not 0 < before.st_size <= limit):
                raise SupervisorError("artifact is not the collected bounded regular file")
            retained.append((parent_fd, artifact_parts[-1], fd, before))
            chunks: list[bytes] = []; total = 0
            while total <= size:
                block = os.read(fd, min(64 * 1024, size + 1 - total))
                if not block: break
                total += len(block); chunks.append(block)
            data = b"".join(chunks)
            if total != size or hashlib.sha256(data).hexdigest() != digest:
                raise SupervisorError("artifact bytes changed")
            for parent, name, descriptor, original in reversed(retained):
                if (_identity(os.fstat(descriptor)) != _identity(original)
                        or _identity(os.stat(name, dir_fd=parent, follow_symlinks=False)) != _identity(original)):
                    raise SupervisorError("artifact namespace changed during reading")
            if (_namespace_anchor(os.fstat(root_fd)) != _namespace_anchor(root_info)
                    or _namespace_anchor(os.stat(self._root, follow_symlinks=False)) != _namespace_anchor(root_info)):
                raise SupervisorError("configured source namespace changed")
            return data



class CompiledAgentOSContext:
    """Immutable read observation over the existing compiler, not new memory."""

    def __init__(self, bundle: dict[str, Any], owner: "AgentOSCompileContextReader") -> None:
        import json
        self._json = json.dumps(bundle, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
        self._owner = owner

    @property
    def context_bundle(self) -> dict[str, Any]:
        import json
        return json.loads(self._json)

    @property
    def source_attestation(self) -> dict[str, Any]:
        """Project-scope observation, distinct from the company-wide brief digest.

        Evidence from this configured reader, not a credential or new authority.
        The existing source composer checks this alongside canonical repo identity.
        """
        from control_plane.wake_events import canonical_json_bytes
        bundle = self.context_bundle
        return {
            "schema": "mastermind.compiled_project_context_observation.v1",
            "project_ref": self._owner._project,
            "repository_revision": self._owner._revision,
            "compiler_sha256": self._owner._compiler_digest,
            "source_records_digest": bundle["source_records_digest"],
            "payload_digest": "sha256:" + hashlib.sha256(canonical_json_bytes(bundle)).hexdigest(),
            "observed_at": self._owner._as_of,
        }

    def revalidate(self) -> None:
        """Explicit bounded reread; never retry a failed read or refresh a claim."""
        current = self._owner.read()
        if current._json != self._json:
            raise SupervisorError("compiled project context changed")


class AgentOSCompileContextReader:
    """Call only the existing pinned Agent OS compile-context command.

    Concrete host configuration fixes the repository, compiler revision, Python
    executable, explicit project and as-of clock. Those values must be provided
    by the approved source/release owner; they are not authenticated by this
    class. Live use requires that owner's protected source namespace, not a
    model-selected executable or arbitrary repository. There is no fallback
    task search, record write, new compiler, daemon or provider invocation.

    The original collector owns subprocess/output/deadline/cleanup behavior.
    Every compile and revalidation carries the same explicit as-of clock;
    rereading never refreshes the returned record's timestamp. Degradation and
    omissions remain in the original bundle, not converted to completeness.
    """

    def __init__(self, *, macro_root: Path, expected_macro_sha: str,
                 expected_compiler_sha256: str, python_executable: Path,
                 project_ref: str, as_of: str, token_budget: int = 16384) -> None:
        from datetime import datetime, timedelta
        if (type(expected_macro_sha) is not str or re.fullmatch(r"[0-9a-f]{40}", expected_macro_sha) is None
                or type(expected_compiler_sha256) is not str or re.fullmatch(r"[0-9a-f]{64}", expected_compiler_sha256) is None
                or type(project_ref) is not str or re.fullmatch(r"WS:[A-Za-z0-9][A-Za-z0-9._-]{1,63}", project_ref) is None
                or type(token_budget) is not int or not 500 <= token_budget <= 32768):
            raise SupervisorError("compiled context configuration is invalid")
        try:
            if type(as_of) is not str or len(as_of) > 64:
                raise ValueError("invalid time")
            moment = datetime.fromisoformat(as_of.replace("Z", "+00:00"))
            if moment.tzinfo is None or moment.utcoffset() != timedelta(0):
                raise ValueError("not UTC")
        except (TypeError, ValueError) as exc:
            raise SupervisorError("compiled context requires explicit UTC time") from exc
        self._root = _absolute(macro_root)
        self._python = _absolute(python_executable)
        self._revision = expected_macro_sha
        self._compiler_digest = expected_compiler_sha256
        self._project = project_ref
        self._as_of = as_of
        self._moment = moment
        self._budget = token_budget

    def _source_snapshot(self) -> None:
        from control_plane import chairman_control_room_remote as collector
        result = collector.default_runner(["git", "--no-optional-locks", "-C", str(self._root),
            "rev-parse", "--verify", "HEAD"], cwd=self._root, timeout=10.0, max_bytes=4096)
        if (not isinstance(result, dict) or type(result.get("code")) is not int or result["code"] != 0
                or any(result.get(name) is not False for name in ("timed_out", "limit_exceeded", "invalid_utf8"))
                or not isinstance(result.get("stdout"), str) or result["stdout"].strip() != self._revision):
            raise SupervisorError("Agent OS repository revision changed")
        if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
            raise SupervisorError("source no-follow primitives are unavailable")
        flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
        with ExitStack() as close:
            root_fd = os.open(self._root, flags | os.O_DIRECTORY); close.callback(os.close, root_fd)
            scripts_fd = os.open("scripts", flags | os.O_DIRECTORY, dir_fd=root_fd); close.callback(os.close, scripts_fd)
            fd = os.open("agentos.py", flags | os.O_NONBLOCK, dir_fd=scripts_fd); close.callback(os.close, fd)
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or not 0 < before.st_size <= _MAX_COMPILED_CONTEXT_BYTES:
                raise SupervisorError("Agent OS compiler source is not bounded")
            chunks=[];total=0
            while total <= before.st_size:
                block=os.read(fd,min(64*1024,before.st_size+1-total))
                if not block:break
                chunks.append(block);total+=len(block)
            if (total != before.st_size or hashlib.sha256(b"".join(chunks)).hexdigest() != self._compiler_digest
                    or _identity(os.fstat(fd)) != _identity(before)
                    or _identity(os.stat("agentos.py", dir_fd=scripts_fd, follow_symlinks=False)) != _identity(before)):
                raise SupervisorError("Agent OS compiler source changed")

    def read(self) -> CompiledAgentOSContext:
        from datetime import datetime
        from control_plane import chairman_control_room_remote as collector
        try:
            self._source_snapshot()
            bundle = collector.run_json_document(collector.default_runner,
                [str(self._python), "-I", str(self._root / "scripts/agentos.py"),
                 "compile-context", "--workstream", self._project, "--json",
                 "--root", str(self._root / "agentos"), "--budget", str(self._budget), "--now", self._as_of],
                cwd=self._root, timeout=60.0, max_bytes=_MAX_COMPILED_CONTEXT_BYTES, expected_schema="context_bundle.v1")
            self._source_snapshot()
            target=bundle.get("target")
            if (not isinstance(target,dict) or target.get("workstream") != self._project or target.get("resolution") != "explicit"
                    or bundle.get("repo_sha") != self._revision
                    or type(bundle.get("source_records_digest")) is not str
                    or re.fullmatch(r"sha256:[0-9a-f]{64}",bundle["source_records_digest"]) is None
                    or type(bundle.get("token_budget")) is not int or bundle["token_budget"] != self._budget
                    or not all(type(bundle.get(key)) is list for key in ("sections","excluded","omitted_due_to_budget","degraded"))
                    or "no_answer_reason" not in bundle
                    or type(bundle.get("generated_at")) is not str
                    or datetime.fromisoformat(bundle["generated_at"].replace("Z","+00:00")) != self._moment):
                raise SupervisorError("compiled context does not match exact source selection")
            return CompiledAgentOSContext(bundle,self)
        except Exception as exc:
            raise SupervisorError("exact Agent OS context acquisition is unavailable") from exc



def bind_coordination_work_sources(
    *, source_bundle: Any, compiled_context: CompiledAgentOSContext,
    context_fields: Any, artifact_path: str, revalidate_source: Any,
):
    """Join actual compiled project data to the existing host source object.

    The approved host still supplies current Chairman/authority/target sources
    and their void-or-raise revalidator. This helper does not acquire those
    authorities or invent options. It derives revisions only from the unchanged
    source composer and never treats a complete Git revision as complete memory.
    No new registry, persistent snapshot, model/queue choice or dispatch occurs.
    """
    import copy
    from collections.abc import Mapping
    from control_plane.chairman_cognition_sources import compose_input, COMPILED_CONTEXT_SOURCE_REF
    from control_plane.chairman_coordination import _CONTEXT_KEYS, render_coordination_brief
    from control_plane.chairman_coordination_host import CoordinationWorkSources
    from control_plane.wake_events import canonical_json_bytes

    def fingerprint(value):
        return hashlib.sha256(canonical_json_bytes(value)).hexdigest()

    def assert_source():
        if revalidate_source() is not None:
            raise SupervisorError("source owner must revalidate or raise")

    try:
        if (type(compiled_context) is not CompiledAgentOSContext
                or not isinstance(source_bundle, Mapping) or not callable(revalidate_source)
                or not isinstance(context_fields, Mapping)
                or set(context_fields) != _CONTEXT_KEYS - {"source_revisions"}):
            raise SupervisorError("current source composition inputs are invalid")
        path = _artifact_path(artifact_path)
        assert_source()
        frozen_source = copy.deepcopy(dict(source_bundle))
        source_digest = fingerprint(frozen_source)
        acquired = compiled_context.context_bundle
        document = compose_input(frozen_source, compiled_context=acquired,
                                  compiled_context_attestation=compiled_context.source_attestation)
        fields = copy.deepcopy(dict(context_fields))
        if fields["project_ref"] != acquired["target"]["workstream"]:
            raise SupervisorError("compiled project differs from selected host responsibility")
        incomplete = bool(acquired["degraded"] or acquired["omitted_due_to_budget"]
                          or acquired["no_answer_reason"])
        if incomplete:
            if fields["coverage"] == "COMPLETE":
                fields["coverage"] = "PARTIAL"
            if not isinstance(fields["omissions"], list):
                raise SupervisorError("context omissions are invalid")
            fields["omissions"].append("Compiled context is incomplete; inspect its original omissions and degradation.")
        fields["source_revisions"] = {r["source_ref"]:r["revision"] for r in document["source_receipts"]}
        render_coordination_brief(document, context=fields, context_bundle=acquired,
                                  bundle_source_ref=COMPILED_CONTEXT_SOURCE_REF)
        assert_source()
        if fingerprint(source_bundle) != source_digest:
            raise SupervisorError("source changed during composition")
    except Exception as exc:
        raise SupervisorError("compiled coordination source binding is unavailable") from exc

    def revalidate():
        try:
            assert_source()
            if fingerprint(source_bundle) != source_digest:
                raise SupervisorError("original source bundle changed")
            compiled_context.revalidate()
            assert_source()
            if fingerprint(source_bundle) != source_digest:
                raise SupervisorError("source changed during revalidation")
        except Exception as exc:
            raise SupervisorError("compiled coordination sources are no longer current") from exc

    return CoordinationWorkSources(document, fields, acquired, COMPILED_CONTEXT_SOURCE_REF,
                                   path, revalidate)

"""Revision-bound candidate authoring for the existing native pool policy.

Only a new private candidate artifact may be written. Live policy, admission,
accounts, credentials, generations and publication remain their original owners.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat
import uuid
from typing import Any

from ops.native_fabric.quota_continuity import policy_change as policy

EDITS_SCHEMA = "mastermind.native_pool_policy_edits.v1"
RESULT_SCHEMA = "mastermind.native_pool_policy_candidate.v1"
MAX_EDITS_BYTES = 262144
MAX_EDIT_NODES = 10000
MAX_EDIT_DEPTH = 24


class CandidatePublicationUnknown(policy.PolicyChangeError):
    """The destination may exist; inspect that exact candidate, never restage."""

    def __init__(self, candidate_sha256: str) -> None:
        super().__init__("CANDIDATE_PUBLICATION_UNCERTAIN")
        self.candidate_sha256 = candidate_sha256


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise policy.PolicyChangeError("POLICY_EDITS_DUPLICATE_KEY")
        result[key] = value
    return result


def _nonfinite(_value):
    raise policy.PolicyChangeError("POLICY_EDITS_NONFINITE")


def parse_edits(raw: bytes) -> dict[str, Any]:
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_EDITS_BYTES:
        raise policy.PolicyChangeError("POLICY_EDITS_OVER_BUDGET")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs,
                           parse_constant=_nonfinite)
        stack, count = [(value, 0)], 0
        while stack:
            node, depth = stack.pop()
            count += 1
            if count > MAX_EDIT_NODES or depth > MAX_EDIT_DEPTH:
                raise policy.PolicyChangeError("POLICY_EDITS_GRAPH_OVER_BUDGET")
            if type(node) is dict:
                stack.extend((item, depth + 1) for item in node.values())
            elif type(node) is list:
                stack.extend((item, depth + 1) for item in node)
        if (type(value) is not dict or value.get("schema") != EDITS_SCHEMA
                or not set(value) <= {"schema", "pool_upserts", "pool_removals", "model_assignments", "routing"}):
            raise policy.PolicyChangeError("POLICY_EDITS_SHAPE_INVALID")
        upserts, removals = value.get("pool_upserts", {}), value.get("pool_removals", [])
        if (type(upserts) is not dict or type(removals) is not list
                or len(upserts) > policy.MAX_POOLS or len(removals) > policy.MAX_POOLS
                or any(type(key) is not str or policy._POOL_ID.fullmatch(key) is None
                       or type(row) is not dict for key, row in upserts.items())
                or any(type(key) is not str or policy._POOL_ID.fullmatch(key) is None for key in removals)
                or len(set(removals)) != len(removals)
                or set(upserts) & set(removals)
                or ("routing" in value and type(value["routing"]) is not dict)):
            raise policy.PolicyChangeError("POLICY_EDITS_SHAPE_INVALID")
        assignments = value.get("model_assignments", {})
        if (type(assignments) is not dict or len(assignments) > policy.MAX_POOLS
                or set(assignments) & (set(upserts) | set(removals))):
            raise policy.PolicyChangeError("POLICY_MODEL_ASSIGNMENT_INVALID")
        for pool_id, roles in assignments.items():
            if (type(pool_id) is not str or policy._POOL_ID.fullmatch(pool_id) is None
                    or type(roles) is not dict or not 1 <= len(roles) <= 32
                    or any(type(role) is not str or policy._POOL_ID.fullmatch(role) is None
                           or type(model) is not str or not 1 <= len(model) <= 128
                           for role, model in roles.items())):
                raise policy.PolicyChangeError("POLICY_MODEL_ASSIGNMENT_INVALID")
        # Encoding here also rejects overflowing floats and invalid Unicode.
        policy._canonical(value)
        return value
    except policy.PolicyChangeError:
        raise
    except Exception:
        raise policy.PolicyChangeError("POLICY_EDITS_INVALID") from None


def propose_edit(current: bytes, edits: bytes, *, expected_source_sha256: str) -> tuple[bytes, dict[str, Any]]:
    """Replace explicit complete rows only; never invent defaults or activation."""
    before = policy._checked_document(current)
    specification = parse_edits(edits)
    if (type(expected_source_sha256) is not str
            or policy._HEX.fullmatch(expected_source_sha256) is None):
        raise policy.PolicyChangeError("EXPECTED_SOURCE_DIGEST_INVALID")
    if hashlib.sha256(current).hexdigest() != expected_source_sha256:
        raise policy.PolicyChangeError("EXPECTED_SOURCE_REVISION_CHANGED")
    candidate = json.loads(policy._canonical(before))
    for name in specification.get("pool_removals", []):
        if name not in candidate["pools"]:
            raise policy.PolicyChangeError("POLICY_REMOVE_UNKNOWN_POOL")
        del candidate["pools"][name]
    for name, row in specification.get("pool_upserts", {}).items():
        candidate["pools"][name] = row
    for pool_id, roles in specification.get("model_assignments", {}).items():
        if pool_id not in candidate["pools"]:
            raise policy.PolicyChangeError("POLICY_MODEL_POOL_UNKNOWN")
        pool = candidate["pools"][pool_id]
        models, capabilities = pool.get("models"), pool.get("model_capabilities")
        if type(models) is not dict or type(capabilities) is not dict:
            raise policy.PolicyChangeError("POLICY_MODEL_MAP_UNAVAILABLE")
        for role, model in roles.items():
            if role not in models:
                raise policy.PolicyChangeError("POLICY_MODEL_ROLE_UNKNOWN")
            if model not in capabilities:
                raise policy.PolicyChangeError("POLICY_MODEL_CAPABILITY_UNKNOWN")
            models[role] = model
    if "routing" in specification:
        candidate["routing"] = specification["routing"]
    if policy._canonical(candidate) == policy._canonical(before):
        raise policy.PolicyChangeError("POLICY_EDITS_NO_CHANGE")
    raw = policy._canonical(candidate) + b"\n"
    # Candidate secrecy/bounds and native compatibility are checked BEFORE a
    # fingerprint or file is returned. A native-compatible document is not an
    # eligible model/account configuration and must never be described as one.
    preview = policy.preview_change(current, raw, expected_source_sha256=expected_source_sha256)
    return raw, preview


def _directory_identity(info: os.stat_result) -> tuple[int, ...]:
    return info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid


def _verify_directory(path: Path, descriptor: int, expected: tuple[int, ...]) -> None:
    if (_directory_identity(os.fstat(descriptor)) != expected
            or _directory_identity(path.lstat()) != expected
            or path.resolve(strict=True) != path):
        raise policy.PolicyChangeError("CANDIDATE_DIRECTORY_CHANGED")


def stage_edit(current_path: Path | str, edits_path: Path | str, output_path: Path | str, *,
               expected_source_sha256: str) -> dict[str, Any]:
    """Publish one no-replace artifact; never overwrite or modify live inputs.

    Once the final name is attempted, ambiguous failures retain it and expose
    its planned digest. Verification is read-only and cannot authorize replay.
    No journal, pointer, queue or account configuration is introduced.
    """
    current, changes = policy._read_source(current_path), policy._read_source(edits_path)
    raw, preview = propose_edit(current.raw, changes.raw, expected_source_sha256=expected_source_sha256)
    candidate_hash = hashlib.sha256(raw).hexdigest()
    directory_fd, temporary_fd, temporary_name = None, None, None
    temporary_identity = None
    attempted = False
    try:
        destination = Path(output_path).expanduser().absolute()
        parent = destination.parent
        if (destination.name in {"", ".", ".."}
                or parent.resolve(strict=True) != parent
                or parent == current.path.parent.resolve(strict=True)
                or destination in {current.path, changes.path}):
            raise policy.PolicyChangeError("CANDIDATE_DESTINATION_INVALID")
        directory_fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        info = os.fstat(directory_fd)
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid()
                or stat.S_IMODE(info.st_mode) & 0o077):
            raise policy.PolicyChangeError("CANDIDATE_DIRECTORY_NOT_PRIVATE")
        directory_identity = _directory_identity(info)
        _verify_directory(parent, directory_fd, directory_identity)
        if os.path.lexists(destination):
            raise policy.PolicyChangeError("CANDIDATE_DESTINATION_OCCUPIED")
        temporary_name = ".pool-candidate-" + uuid.uuid4().hex
        temporary_fd = os.open(temporary_name, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                               | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=directory_fd)
        temporary_identity = os.fstat(temporary_fd)
        view = memoryview(raw)
        while view:
            written = os.write(temporary_fd, view)
            if written <= 0:
                raise OSError("candidate write incomplete")
            view = view[written:]
        os.fsync(temporary_fd)
        held = os.fstat(temporary_fd)
        named = os.stat(temporary_name, dir_fd=directory_fd, follow_symlinks=False)
        if ((held.st_dev, held.st_ino) != (named.st_dev, named.st_ino)
                or held.st_size != len(raw) or held.st_nlink != 1
                or stat.S_IMODE(held.st_mode) != 0o600):
            raise policy.PolicyChangeError("CANDIDATE_STAGING_CHANGED")
        policy._require_current(current)
        policy._require_current(changes)
        _verify_directory(parent, directory_fd, directory_identity)
        # Same-directory link is atomic and refuses any existing final name.
        # Never use replace/rename-overwrite against operator source artifacts.
        attempted = True
        try:
            os.link(temporary_name, destination.name, src_dir_fd=directory_fd,
                    dst_dir_fd=directory_fd, follow_symlinks=False)
        except FileExistsError:
            attempted = False
            raise policy.PolicyChangeError("CANDIDATE_DESTINATION_OCCUPIED") from None
        os.unlink(temporary_name, dir_fd=directory_fd)
        temporary_name = None
        os.fsync(directory_fd)
        _verify_directory(parent, directory_fd, directory_identity)
        published = policy._read_source(destination)
        if (published.raw != raw or published.identity[:2] != (held.st_dev, held.st_ino)
                or published.identity[5] != 1):
            raise policy.PolicyChangeError("CANDIDATE_READBACK_CHANGED")
        policy._require_current(current)
        policy._require_current(changes)
        return {"schema": RESULT_SCHEMA, "state": "STAGED", "candidate_written": True,
                "candidate_source_sha256": candidate_hash,
                "parent_source_sha256": expected_source_sha256,
                "live_policy_changed": False, "activation_authorized": False,
                "original_operations_rebound": False, "replay_authorized": False,
                "preview": preview}
    except BaseException as exc:
        if attempted:
            raise CandidatePublicationUnknown(candidate_hash) from None
        if isinstance(exc, policy.PolicyChangeError):
            raise
        if not isinstance(exc, Exception):
            raise
        raise policy.PolicyChangeError("CANDIDATE_STAGE_REFUSED") from None
    finally:
        if temporary_name is not None and directory_fd is not None and temporary_identity is not None:
            # Remove only this invocation's own scratch inode, never its final
            # publication or any competing replacement at the scratch name.
            try:
                observed = os.stat(temporary_name, dir_fd=directory_fd, follow_symlinks=False)
                if ((observed.st_dev, observed.st_ino) == (temporary_identity.st_dev, temporary_identity.st_ino)
                        and stat.S_ISREG(observed.st_mode)):
                    os.unlink(temporary_name, dir_fd=directory_fd)
            except OSError:
                pass
        if temporary_fd is not None:
            os.close(temporary_fd)
        if directory_fd is not None:
            os.close(directory_fd)


def verify_candidate(path: Path | str, *, expected_candidate_sha256: str) -> dict[str, Any]:
    """Observe the exact original target after a lost reply; no write or replay."""
    if (type(expected_candidate_sha256) is not str
            or policy._HEX.fullmatch(expected_candidate_sha256) is None):
        raise policy.PolicyChangeError("EXPECTED_CANDIDATE_DIGEST_INVALID")
    source = policy._read_source(path)
    policy._checked_document(source.raw)
    if hashlib.sha256(source.raw).hexdigest() != expected_candidate_sha256:
        raise policy.PolicyChangeError("CANDIDATE_DIGEST_MISMATCH")
    policy._require_current(source)
    return {"schema": RESULT_SCHEMA, "state": "ARTIFACT_PRESENT_VERIFIED",
            "candidate_source_sha256": expected_candidate_sha256,
            "candidate_written": False, "original_stage_success_proven": False,
            "live_policy_changed": False, "activation_authorized": False,
            "replay_authorized": False}


def run_cli(args) -> int:
    """Share the existing operator CLI without exposing source/path exceptions."""
    try:
        if args.command == "stage":
            result = stage_edit(args.policy, args.edits, args.output,
                                expected_source_sha256=args.expected_source_sha256)
        else:
            result = verify_candidate(args.candidate,
                                      expected_candidate_sha256=args.expected_candidate_sha256)
    except CandidatePublicationUnknown as exc:
        print(json.dumps({"schema": RESULT_SCHEMA, "state": "EFFECT_UNKNOWN",
                          "code": "CANDIDATE_PUBLICATION_UNCERTAIN",
                          "candidate_source_sha256": exc.candidate_sha256,
                          "live_policy_changed": False, "activation_authorized": False,
                          "replay_authorized": False}, sort_keys=True))
        return 3
    except policy.PolicyChangeError as exc:
        print(json.dumps({"schema": RESULT_SCHEMA, "state": "REFUSED", "code": str(exc),
                          "candidate_written": False, "live_policy_changed": False,
                          "activation_authorized": False, "replay_authorized": False}, sort_keys=True))
        return 2
    print(policy._canonical(result).decode("utf-8"))
    return 0

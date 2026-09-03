#!/usr/bin/env python3
"""Read-only production adapter for deterministic Source Continuity V1 receipts.

This adapter observes one explicit local Git worktree plus authenticated GitHub
GET-only facts, then delegates all classification to the pure verifier in
``control_plane.source_continuity``. It intentionally owns no persistence,
lifecycle, retry/failover, watcher, receiver-transfer, release, merge, provider,
or runtime effect.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Callable, Mapping, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from control_plane.source_continuity import (  # noqa: E402
    BranchEffectDependency,
    CollisionState,
    ExternalEffectEvidence,
    ExternalEffectState,
    LocalGitFacts,
    ReceiptKind,
    RefusalCode,
    RemoteGitFacts,
    RemotePathEntry,
    SourceContinuityRefusal,
    SourceContinuityRequest,
    canonical_json,
    request_is_valid,
    verify_source_continuity,
)

_GIT = "/usr/bin/git"
_API_ROOT = "https://api.github.com"
_API_VERSION = "2022-11-28"
_COMMAND_TIMEOUT_SECONDS = 20.0
_HTTP_TIMEOUT_SECONDS = 20.0
_MAX_HTTP_BODY_BYTES = 5_000_000
_PAGE_SIZE = 100
_MAX_PAGES = 10
_MAX_COLLISION_PRS = 100
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_HOLD_LABELS = frozenset({"hold", "hold-for-sol", "hold_for_sol"})


class _SafeArgumentParser(argparse.ArgumentParser):
    def error(self, _message: str) -> None:
        raise ValueError("invalid arguments")


class _AuthProbeError(Exception):
    pass


class _RemoteProbeError(Exception):
    pass


@dataclass(frozen=True)
class _CommandResult:
    returncode: int
    stdout: str


Runner = Callable[..., object]
HTTPGet = Callable[..., object]
Clock = Callable[[], str]


def _utc_now_z() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _refusal(code: RefusalCode, exit_code: int) -> SourceContinuityRefusal:
    return SourceContinuityRefusal(code=code, exit_code=exit_code)


def _emit(result: object) -> int:
    if isinstance(result, SourceContinuityRefusal):
        print(canonical_json(result.to_dict()))
        return result.exit_code
    print(canonical_json(result.to_dict()))
    return 0


def _is_sha(value: object) -> bool:
    return isinstance(value, str) and _SHA_RE.fullmatch(value) is not None


def _invoke_git(
    runner: Runner,
    workspace: str,
    *arguments: str,
) -> _CommandResult | None:
    env = dict(os.environ)
    env.pop("GITHUB_TOKEN", None)
    env["GIT_OPTIONAL_LOCKS"] = "0"
    env["GIT_NO_LAZY_FETCH"] = "1"
    env["GIT_TERMINAL_PROMPT"] = "0"
    try:
        completed = runner(
            [_GIT, *arguments],
            cwd=workspace,
            env=env,
            text=True,
            capture_output=True,
            check=False,
            timeout=_COMMAND_TIMEOUT_SECONDS,
        )
        returncode = getattr(completed, "returncode")
        stdout = getattr(completed, "stdout")
    except Exception:
        return None
    if type(returncode) is not int or not isinstance(stdout, str):
        return None
    return _CommandResult(returncode=returncode, stdout=stdout)


def _stdlib_http_get(url: str, *, token: str, timeout: float) -> object:
    if not isinstance(url, str) or not url.startswith(_API_ROOT + "/"):
        raise _RemoteProbeError()
    if not isinstance(token, str) or not token:
        raise _AuthProbeError()
    request = Request(
        url,
        method="GET",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": _API_VERSION,
            "User-Agent": "mastermind-source-continuity-v1",
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed GitHub API root
            raw = response.read(_MAX_HTTP_BODY_BYTES + 1)
    except HTTPError as exc:
        if exc.code in {401, 403}:
            raise _AuthProbeError() from None
        raise _RemoteProbeError() from None
    except (URLError, TimeoutError, OSError):
        raise _RemoteProbeError() from None
    if len(raw) > _MAX_HTTP_BODY_BYTES:
        raise _RemoteProbeError()
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise _RemoteProbeError() from None


def _api(http_get: HTTPGet, token: str, endpoint: str) -> object:
    if not isinstance(endpoint, str) or endpoint.startswith(("http://", "https://")):
        raise _RemoteProbeError()
    return http_get(
        f"{_API_ROOT}/{endpoint}",
        token=token,
        timeout=_HTTP_TIMEOUT_SECONDS,
    )


def _branch_endpoint(repository: str, branch: str) -> str:
    return f"repos/{repository}/branches/{quote(branch, safe='')}"


def _pull_files_endpoint(repository: str, pr_number: int, page: int) -> str:
    return f"repos/{repository}/pulls/{pr_number}/files?per_page={_PAGE_SIZE}&page={page}"


def _paged_array(
    http_get: HTTPGet,
    token: str,
    endpoint_for_page: Callable[[int], str],
) -> tuple[list[object], bool]:
    items: list[object] = []
    for page in range(1, _MAX_PAGES + 1):
        payload = _api(http_get, token, endpoint_for_page(page))
        if not isinstance(payload, list):
            raise _RemoteProbeError()
        items.extend(payload)
        if len(payload) < _PAGE_SIZE:
            return items, True
    return items, False


def _hold_from_pr(pr: dict[str, object]) -> bool:
    if pr.get("draft") is True:
        return True
    labels = pr.get("labels")
    if not isinstance(labels, list):
        return False
    for label in labels:
        if not isinstance(label, dict):
            continue
        name = label.get("name")
        if isinstance(name, str) and name.strip().lower() in _HOLD_LABELS:
            return True
    return False


def _pr_identity(pr: object) -> tuple[object, ...] | None:
    if not isinstance(pr, dict):
        return None
    head = pr.get("head")
    base = pr.get("base")
    if not isinstance(head, dict) or not isinstance(base, dict):
        return None
    head_repo = head.get("repo")
    if not isinstance(head_repo, dict):
        return None
    return (
        pr.get("state"),
        _hold_from_pr(pr),
        head.get("ref"),
        head.get("sha"),
        head_repo.get("full_name"),
        base.get("ref"),
    )


def _changed_paths(
    http_get: HTTPGet,
    token: str,
    repository: str,
    pr_number: int,
) -> tuple[tuple[str, ...], bool]:
    raw_items, complete = _paged_array(
        http_get,
        token,
        lambda page: _pull_files_endpoint(repository, pr_number, page),
    )
    paths: list[str] = []
    for item in raw_items:
        if not isinstance(item, dict) or not isinstance(item.get("filename"), str):
            raise _RemoteProbeError()
        paths.append(item["filename"])
    return tuple(paths), complete


def _collision_census(
    http_get: HTTPGet,
    token: str,
    repository: str,
    target_pr: int,
    owned_paths: tuple[str, ...],
) -> tuple[CollisionState, tuple[int, ...], bool]:
    pulls: list[object] = []
    complete = False
    for page in range(1, _MAX_PAGES + 1):
        payload = _api(
            http_get,
            token,
            f"repos/{repository}/pulls?state=open&per_page={_PAGE_SIZE}&page={page}",
        )
        if not isinstance(payload, list):
            raise _RemoteProbeError()
        pulls.extend(payload)
        if len(pulls) > _MAX_COLLISION_PRS:
            return CollisionState.INCOMPLETE, (), False
        if len(payload) < _PAGE_SIZE:
            complete = True
            break
    if not complete:
        return CollisionState.INCOMPLETE, (), False

    owned = set(owned_paths)
    other_pr_count = 0
    colliding: list[int] = []
    for raw_pr in pulls:
        if not isinstance(raw_pr, dict):
            raise _RemoteProbeError()
        number = raw_pr.get("number")
        if type(number) is not int or number <= 0:
            raise _RemoteProbeError()
        if number == target_pr:
            continue
        other_pr_count += 1
        paths, paths_complete = _changed_paths(http_get, token, repository, number)
        if not paths_complete:
            return CollisionState.INCOMPLETE, (), False
        if owned.intersection(paths):
            colliding.append(number)

    if colliding:
        return CollisionState.OVERLAP, tuple(sorted(set(colliding))), True
    if other_pr_count:
        return CollisionState.DISJOINT, (), True
    return CollisionState.NONE, (), True


def _probe_remote_prefix(
    http_get: HTTPGet,
    token: str,
    request: SourceContinuityRequest,
) -> tuple[
    tuple[object, ...],
    str,
    str,
    str,
    str,
    str,
    tuple[str, ...],
    bool,
    CollisionState,
    tuple[int, ...],
    bool,
] | SourceContinuityRefusal:
    pr_endpoint = f"repos/{request.repository}/pulls/{request.pr_number}"
    first_pr = _api(http_get, token, pr_endpoint)
    first_identity = _pr_identity(first_pr)
    if first_identity is None:
        return _refusal(RefusalCode.REMOTE_PROBE_FAILED, 2)

    _, _, remote_branch, remote_head, remote_repo, remote_base = first_identity
    if not _is_sha(remote_head):
        return _refusal(RefusalCode.REMOTE_FACTS_INVALID, 2)

    branch_payload = _api(
        http_get,
        token,
        _branch_endpoint(request.repository, request.branch),
    )
    if not isinstance(branch_payload, dict):
        return _refusal(RefusalCode.REMOTE_PROBE_FAILED, 2)
    branch_commit = branch_payload.get("commit")
    if not isinstance(branch_commit, dict) or not _is_sha(branch_commit.get("sha")):
        return _refusal(RefusalCode.REMOTE_PROBE_FAILED, 2)
    if branch_commit["sha"] != remote_head:
        return _refusal(RefusalCode.REMOTE_PROOF_CHANGED, 1)

    commit_payload = _api(
        http_get,
        token,
        f"repos/{request.repository}/git/commits/{remote_head}",
    )
    if not isinstance(commit_payload, dict):
        return _refusal(RefusalCode.REMOTE_PROBE_FAILED, 2)
    tree = commit_payload.get("tree")
    if not isinstance(tree, dict) or not _is_sha(tree.get("sha")):
        return _refusal(RefusalCode.REMOTE_PROBE_FAILED, 2)
    remote_tree = tree["sha"]

    base_payload = _api(
        http_get,
        token,
        _branch_endpoint(request.repository, request.base_ref),
    )
    if not isinstance(base_payload, dict):
        return _refusal(RefusalCode.REMOTE_PROBE_FAILED, 2)
    base_commit = base_payload.get("commit")
    if not isinstance(base_commit, dict) or not _is_sha(base_commit.get("sha")):
        return _refusal(RefusalCode.REMOTE_PROBE_FAILED, 2)
    current_base_head = base_commit["sha"]

    compare_payload = _api(
        http_get,
        token,
        f"repos/{request.repository}/compare/{current_base_head}...{remote_head}",
    )
    if not isinstance(compare_payload, dict):
        return _refusal(RefusalCode.REMOTE_PROBE_FAILED, 2)
    merge_base = compare_payload.get("merge_base_commit")
    if not isinstance(merge_base, dict) or not _is_sha(merge_base.get("sha")):
        return _refusal(RefusalCode.REMOTE_PROBE_FAILED, 2)
    merge_base_sha = merge_base["sha"]

    changed_paths, files_complete = _changed_paths(
        http_get,
        token,
        request.repository,
        request.pr_number,
    )
    collision_state, colliding_pr_numbers, collisions_complete = _collision_census(
        http_get,
        token,
        request.repository,
        request.pr_number,
        request.owned_paths,
    )
    return (
        first_identity,
        str(remote_repo),
        str(remote_branch),
        str(remote_base),
        remote_head,
        remote_tree,
        merge_base_sha,
        current_base_head,
        changed_paths,
        files_complete,
        collision_state,
        colliding_pr_numbers,
        collisions_complete,
    )


def _parse_nul_paths(value: str) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(path for path in value.split("\0") if path)


def _same_duplicate_free_paths(left: tuple[str, ...], right: tuple[str, ...]) -> bool:
    return (
        len(left) == len(set(left))
        and len(right) == len(set(right))
        and set(left) == set(right)
    )


def _parse_ls_tree(value: str) -> tuple[RemotePathEntry, ...] | None:
    entries: list[RemotePathEntry] = []
    for record in (item for item in value.split("\0") if item):
        try:
            header, path = record.split("\t", 1)
            mode, object_type, object_sha, size_text = header.split()
            size = int(size_text)
        except (ValueError, TypeError):
            return None
        entries.append(
            RemotePathEntry(
                path=path,
                mode=mode,
                object_type=object_type,
                object_sha=object_sha,
                size=size,
            )
        )
    return tuple(entries)


def _probe_local_and_entries(
    runner: Runner,
    workspace: str,
    request: SourceContinuityRequest,
    remote_head: str,
    merge_base_sha: str,
    remote_changed_paths: tuple[str, ...],
) -> tuple[LocalGitFacts, tuple[RemotePathEntry, ...]] | SourceContinuityRefusal:
    root_result = _invoke_git(runner, workspace, "rev-parse", "--show-toplevel")
    if root_result is None or root_result.returncode != 0:
        return _refusal(RefusalCode.LOCAL_PROBE_FAILED, 2)
    if os.path.normpath(root_result.stdout.strip()) != os.path.normpath(workspace):
        return _refusal(RefusalCode.LOCAL_PROBE_FAILED, 2)

    branch_result = _invoke_git(runner, workspace, "symbolic-ref", "--short", "HEAD")
    if branch_result is None:
        return _refusal(RefusalCode.LOCAL_PROBE_FAILED, 2)
    if branch_result.returncode != 0:
        return _refusal(RefusalCode.LOCAL_BRANCH_MISMATCH, 1)
    branch = branch_result.stdout.strip()

    head_result = _invoke_git(runner, workspace, "rev-parse", "HEAD^{commit}")
    tree_result = _invoke_git(runner, workspace, "rev-parse", "HEAD^{tree}")
    if (
        head_result is None
        or tree_result is None
        or head_result.returncode != 0
        or tree_result.returncode != 0
    ):
        return _refusal(RefusalCode.LOCAL_PROBE_FAILED, 2)
    head_sha = head_result.stdout.strip()
    tree_sha = tree_result.stdout.strip()

    remote_object = _invoke_git(runner, workspace, "cat-file", "-e", f"{remote_head}^{{commit}}")
    if remote_object is None:
        return _refusal(RefusalCode.LOCAL_PROBE_FAILED, 2)
    if remote_object.returncode != 0:
        return _refusal(RefusalCode.REMOTE_HEAD_OBJECT_MISSING, 1)

    merge_base_object = _invoke_git(
        runner,
        workspace,
        "cat-file",
        "-e",
        f"{merge_base_sha}^{{commit}}",
    )
    if merge_base_object is None or merge_base_object.returncode != 0:
        return _refusal(RefusalCode.LOCAL_PROBE_FAILED, 2)

    ancestor_result = _invoke_git(
        runner,
        workspace,
        "merge-base",
        "--is-ancestor",
        remote_head,
        "HEAD",
    )
    if ancestor_result is None or ancestor_result.returncode not in {0, 1}:
        return _refusal(RefusalCode.LOCAL_PROBE_FAILED, 2)
    remote_head_is_ancestor = ancestor_result.returncode == 0

    unpushed_count = 0
    if remote_head_is_ancestor:
        count_result = _invoke_git(
            runner,
            workspace,
            "rev-list",
            "--count",
            f"{remote_head}..HEAD",
        )
        if count_result is None or count_result.returncode != 0:
            return _refusal(RefusalCode.LOCAL_PROBE_FAILED, 2)
        try:
            unpushed_count = int(count_result.stdout.strip())
        except ValueError:
            return _refusal(RefusalCode.LOCAL_PROBE_FAILED, 2)
        if unpushed_count < 0:
            return _refusal(RefusalCode.LOCAL_PROBE_FAILED, 2)

    unstaged = _invoke_git(runner, workspace, "diff", "--name-only", "-z", "HEAD")
    staged = _invoke_git(runner, workspace, "diff", "--cached", "--name-only", "-z")
    untracked = _invoke_git(runner, workspace, "ls-files", "--others", "--exclude-standard", "-z")
    if any(result is None or result.returncode != 0 for result in (unstaged, staged, untracked)):
        return _refusal(RefusalCode.LOCAL_PROBE_FAILED, 2)

    local_diff = _invoke_git(
        runner,
        workspace,
        "diff",
        "--name-only",
        "-z",
        f"{merge_base_sha}..{remote_head}",
    )
    if local_diff is None or local_diff.returncode != 0:
        return _refusal(RefusalCode.LOCAL_PROBE_FAILED, 2)
    local_changed_paths = _parse_nul_paths(local_diff.stdout)
    if not _same_duplicate_free_paths(local_changed_paths, remote_changed_paths):
        return _refusal(RefusalCode.REMOTE_PROOF_CHANGED, 1)

    tree_result = _invoke_git(
        runner,
        workspace,
        "ls-tree",
        "-z",
        "-l",
        remote_head,
        "--",
        *remote_changed_paths,
    )
    if tree_result is None or tree_result.returncode != 0:
        return _refusal(RefusalCode.LOCAL_PROBE_FAILED, 2)
    path_entries = _parse_ls_tree(tree_result.stdout)
    if path_entries is None:
        return _refusal(RefusalCode.LOCAL_PROBE_FAILED, 2)

    tracked_paths = set(_parse_nul_paths(unstaged.stdout)) | set(_parse_nul_paths(staged.stdout))
    untracked_paths = set(_parse_nul_paths(untracked.stdout))
    owned = set(request.owned_paths)
    local_facts = LocalGitFacts(
        branch=branch,
        head_sha=head_sha,
        tree_sha=tree_sha,
        remote_head_object_exists=True,
        remote_head_is_ancestor_of_local=remote_head_is_ancestor,
        unpushed_commit_count=unpushed_count,
        uncommitted_in_scope_count=len(tracked_paths & owned),
        untracked_in_scope_count=len(untracked_paths & owned),
        uncommitted_out_of_scope_count=len(tracked_paths - owned),
        untracked_out_of_scope_count=len(untracked_paths - owned),
    )
    return local_facts, path_entries


def _remote_still_matches(
    http_get: HTTPGet,
    token: str,
    request: SourceContinuityRequest,
    first_identity: tuple[object, ...],
    remote_head: str,
    current_base_head: str,
) -> bool:
    pr_endpoint = f"repos/{request.repository}/pulls/{request.pr_number}"
    second_pr = _api(http_get, token, pr_endpoint)
    second_identity = _pr_identity(second_pr)
    second_branch = _api(
        http_get,
        token,
        _branch_endpoint(request.repository, request.branch),
    )
    second_base = _api(
        http_get,
        token,
        _branch_endpoint(request.repository, request.base_ref),
    )
    if (
        second_identity is None
        or not isinstance(second_branch, dict)
        or not isinstance(second_base, dict)
    ):
        raise _RemoteProbeError()
    branch_commit = second_branch.get("commit")
    base_commit = second_base.get("commit")
    if not isinstance(branch_commit, dict) or not isinstance(base_commit, dict):
        raise _RemoteProbeError()
    return (
        second_identity == first_identity
        and branch_commit.get("sha") == remote_head
        and base_commit.get("sha") == current_base_head
    )


def _build_parser() -> _SafeArgumentParser:
    parser = _SafeArgumentParser(add_help=False)
    subparsers = parser.add_subparsers(dest="command", required=True)
    verify = subparsers.add_parser("verify", add_help=False)
    verify.add_argument("--kind", required=True, choices=("checkpoint", "remote-complete"))
    verify.add_argument("--operation-key", required=True)
    verify.add_argument("--workspace", required=True)
    verify.add_argument("--repository", required=True)
    verify.add_argument("--pr-number", required=True, type=int)
    verify.add_argument("--branch", required=True)
    verify.add_argument("--base-ref", required=True)
    verify.add_argument("--pinned-base-sha", required=True)
    verify.add_argument("--owned-path", required=True, action="append")
    verify.add_argument(
        "--external-effect-state",
        required=True,
        choices=tuple(item.value for item in ExternalEffectState),
    )
    verify.add_argument(
        "--branch-effect-dependency",
        required=True,
        choices=tuple(item.value for item in BranchEffectDependency),
    )
    verify.add_argument("--external-effect-evidence-fingerprint", required=True)
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    runner: Runner = subprocess.run,
    http_get: HTTPGet = _stdlib_http_get,
    environ: Mapping[str, str] = os.environ,
    clock: Clock = _utc_now_z,
) -> int:
    try:
        args = _build_parser().parse_args(list(argv) if argv is not None else None)
        workspace = args.workspace
        if not isinstance(workspace, str) or not Path(workspace).is_absolute():
            raise ValueError("invalid workspace")
        receipt_kind = {
            "checkpoint": ReceiptKind.CHECKPOINT_VERIFIED,
            "remote-complete": ReceiptKind.REMOTE_COMPLETE_VERIFIED,
        }[args.kind]
        request = SourceContinuityRequest(
            receipt_kind=receipt_kind,
            operation_key=args.operation_key,
            repository=args.repository,
            pr_number=args.pr_number,
            branch=args.branch,
            base_ref=args.base_ref,
            pinned_base_sha=args.pinned_base_sha,
            owned_paths=tuple(args.owned_path),
            verified_at=clock(),
        )
    except (Exception, SystemExit):
        return _emit(_refusal(RefusalCode.INVALID_REQUEST, 2))

    if not request_is_valid(request):
        return _emit(_refusal(RefusalCode.INVALID_REQUEST, 2))

    token = environ.get("GITHUB_TOKEN")
    if not isinstance(token, str) or not token:
        return _emit(_refusal(RefusalCode.AUTH_UNAVAILABLE, 2))

    try:
        remote_prefix = _probe_remote_prefix(http_get, token, request)
        if isinstance(remote_prefix, SourceContinuityRefusal):
            return _emit(remote_prefix)
        (
            first_identity,
            remote_repo,
            remote_branch,
            remote_base,
            remote_head,
            remote_tree,
            merge_base_sha,
            current_base_head,
            changed_paths,
            files_complete,
            collision_state,
            colliding_pr_numbers,
            collisions_complete,
        ) = remote_prefix

        local_probe = _probe_local_and_entries(
            runner,
            workspace,
            request,
            remote_head,
            merge_base_sha,
            changed_paths,
        )
        if isinstance(local_probe, SourceContinuityRefusal):
            return _emit(local_probe)
        local_facts, path_entries = local_probe

        if not _remote_still_matches(
            http_get,
            token,
            request,
            first_identity,
            remote_head,
            current_base_head,
        ):
            return _emit(_refusal(RefusalCode.REMOTE_PROOF_CHANGED, 1))

        remote_facts = RemoteGitFacts(
            repository=remote_repo,
            pr_number=request.pr_number,
            branch=remote_branch,
            base_ref=remote_base,
            pr_open=first_identity[0] == "open",
            pr_draft_or_hold=bool(first_identity[1]),
            head_sha=remote_head,
            tree_sha=remote_tree,
            merge_base_sha=merge_base_sha,
            current_base_head_sha=current_base_head,
            changed_paths=changed_paths,
            path_entries=path_entries,
            collision_state=collision_state,
            colliding_pr_numbers=colliding_pr_numbers,
            pagination_complete=files_complete and collisions_complete,
        )
        external = ExternalEffectEvidence(
            state=ExternalEffectState(args.external_effect_state),
            branch_dependency=BranchEffectDependency(args.branch_effect_dependency),
            evidence_fingerprint=args.external_effect_evidence_fingerprint,
        )
        result = verify_source_continuity(request, local_facts, remote_facts, external)
    except _AuthProbeError:
        result = _refusal(RefusalCode.AUTH_UNAVAILABLE, 2)
    except _RemoteProbeError:
        result = _refusal(RefusalCode.REMOTE_PROBE_FAILED, 2)
    except Exception:
        result = _refusal(RefusalCode.PROBE_INTERNAL_ERROR, 2)
    return _emit(result)


if __name__ == "__main__":
    raise SystemExit(main())

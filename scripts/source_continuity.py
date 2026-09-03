#!/usr/bin/env python3
"""Read-only adapter for deterministic Source Continuity V1 receipts.

The adapter observes local Git plus authenticated GitHub facts and delegates the
decision to control_plane.source_continuity. It never mutates Git, GitHub,
lifecycle, provider/runtime, watcher, release, or receiver state.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Callable, Iterable, Sequence
from urllib.parse import quote

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

_MAX_PAGES = 10
_PAGE_SIZE = 100
_COMMAND_TIMEOUT_SECONDS = 20
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_HOLD_LABELS = frozenset({"hold", "hold-for-sol", "hold_for_sol"})


class _SafeArgumentParser(argparse.ArgumentParser):
    def error(self, _message: str) -> None:
        raise ValueError("invalid arguments")


@dataclass(frozen=True)
class _CommandResult:
    returncode: int
    stdout: str


Runner = Callable[..., object]
Clock = Callable[[], str]


def _utc_now_z() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _invoke(
    runner: Runner,
    command: Sequence[str],
    *,
    cwd: str | None = None,
) -> _CommandResult | None:
    try:
        completed = runner(
            list(command),
            cwd=cwd,
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


def _api_json(
    runner: Runner,
    endpoint: str,
) -> object | None:
    completed = _invoke(runner, ("gh", "api", endpoint))
    if completed is None or completed.returncode != 0:
        return None
    try:
        return json.loads(completed.stdout)
    except (TypeError, ValueError):
        return None


def _git(
    runner: Runner,
    root: str | None,
    *arguments: str,
) -> _CommandResult | None:
    return _invoke(runner, ("git", *arguments), cwd=root)


def _branch_endpoint(repository: str, branch: str) -> str:
    return f"repos/{repository}/branches/{quote(branch, safe='')}"


def _pull_files_endpoint(repository: str, pr_number: int, page: int) -> str:
    return f"repos/{repository}/pulls/{pr_number}/files?per_page={_PAGE_SIZE}&page={page}"


def _paged_array(
    runner: Runner,
    endpoint_for_page: Callable[[int], str],
) -> tuple[list[object], bool] | None:
    items: list[object] = []
    for page in range(1, _MAX_PAGES + 1):
        payload = _api_json(runner, endpoint_for_page(page))
        if not isinstance(payload, list):
            return None
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
        if isinstance(label, dict):
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
    runner: Runner,
    repository: str,
    pr_number: int,
) -> tuple[tuple[str, ...], bool] | None:
    page = _paged_array(
        runner,
        lambda number: _pull_files_endpoint(repository, pr_number, number),
    )
    if page is None:
        return None
    raw_items, complete = page
    paths: list[str] = []
    for item in raw_items:
        if not isinstance(item, dict) or not isinstance(item.get("filename"), str):
            return None
        paths.append(item["filename"])
    return tuple(paths), complete


def _path_entries(
    runner: Runner,
    repository: str,
    tree_sha: str,
    changed_paths: Iterable[str],
) -> tuple[tuple[RemotePathEntry, ...], bool] | None:
    payload = _api_json(
        runner,
        f"repos/{repository}/git/trees/{tree_sha}?recursive=1",
    )
    if not isinstance(payload, dict):
        return None
    raw_tree = payload.get("tree")
    if not isinstance(raw_tree, list):
        return None
    truncated = payload.get("truncated")
    if type(truncated) is not bool:
        return None

    wanted = set(changed_paths)
    entries: list[RemotePathEntry] = []
    for item in raw_tree:
        if not isinstance(item, dict):
            return None
        path = item.get("path")
        if path not in wanted:
            continue
        entries.append(
            RemotePathEntry(
                path=path,
                mode=item.get("mode"),
                object_type=item.get("type"),
                object_sha=item.get("sha"),
                size=item.get("size"),
            )
        )
    return tuple(entries), not truncated


def _collision_census(
    runner: Runner,
    repository: str,
    target_pr: int,
    owned_paths: tuple[str, ...],
) -> tuple[CollisionState, tuple[int, ...], bool] | None:
    pull_page = _paged_array(
        runner,
        lambda page: f"repos/{repository}/pulls?state=open&per_page={_PAGE_SIZE}&page={page}",
    )
    if pull_page is None:
        return None
    pulls, pulls_complete = pull_page
    if not pulls_complete:
        return CollisionState.INCOMPLETE, (), False

    owned = set(owned_paths)
    other_prs = 0
    colliding: list[int] = []
    for raw_pr in pulls:
        if not isinstance(raw_pr, dict):
            return None
        number = raw_pr.get("number")
        if type(number) is not int or number <= 0:
            return None
        if number == target_pr:
            continue
        other_prs += 1
        files = _changed_paths(runner, repository, number)
        if files is None:
            return None
        paths, complete = files
        if not complete:
            return CollisionState.INCOMPLETE, (), False
        if owned.intersection(paths):
            colliding.append(number)

    if colliding:
        return CollisionState.OVERLAP, tuple(sorted(set(colliding))), True
    if other_prs:
        return CollisionState.DISJOINT, (), True
    return CollisionState.NONE, (), True


def _probe_remote(
    runner: Runner,
    request: SourceContinuityRequest,
) -> RemoteGitFacts | SourceContinuityRefusal:
    pr_endpoint = f"repos/{request.repository}/pulls/{request.pr_number}"
    first_pr = _api_json(runner, pr_endpoint)
    first_identity = _pr_identity(first_pr)
    if first_identity is None:
        return _refusal(RefusalCode.REMOTE_PROBE_FAILED, 2)

    _, pr_draft_or_hold, remote_branch, remote_head, remote_repo, remote_base = first_identity
    if not _is_sha(remote_head):
        return _refusal(RefusalCode.REMOTE_FACTS_INVALID, 2)

    branch_payload = _api_json(
        runner,
        _branch_endpoint(request.repository, request.branch),
    )
    if not isinstance(branch_payload, dict):
        return _refusal(RefusalCode.REMOTE_PROBE_FAILED, 2)
    branch_commit = branch_payload.get("commit")
    if not isinstance(branch_commit, dict) or not _is_sha(branch_commit.get("sha")):
        return _refusal(RefusalCode.REMOTE_PROBE_FAILED, 2)
    if branch_commit["sha"] != remote_head:
        return _refusal(RefusalCode.REMOTE_PROOF_CHANGED, 1)

    commit_payload = _api_json(
        runner,
        f"repos/{request.repository}/git/commits/{remote_head}",
    )
    if not isinstance(commit_payload, dict):
        return _refusal(RefusalCode.REMOTE_PROBE_FAILED, 2)
    tree = commit_payload.get("tree")
    if not isinstance(tree, dict) or not _is_sha(tree.get("sha")):
        return _refusal(RefusalCode.REMOTE_PROBE_FAILED, 2)
    remote_tree = tree["sha"]

    base_payload = _api_json(
        runner,
        _branch_endpoint(request.repository, request.base_ref),
    )
    if not isinstance(base_payload, dict):
        return _refusal(RefusalCode.REMOTE_PROBE_FAILED, 2)
    base_commit = base_payload.get("commit")
    if not isinstance(base_commit, dict) or not _is_sha(base_commit.get("sha")):
        return _refusal(RefusalCode.REMOTE_PROBE_FAILED, 2)
    current_base_head = base_commit["sha"]

    compare_payload = _api_json(
        runner,
        f"repos/{request.repository}/compare/{current_base_head}...{remote_head}",
    )
    if not isinstance(compare_payload, dict):
        return _refusal(RefusalCode.REMOTE_PROBE_FAILED, 2)
    merge_base = compare_payload.get("merge_base_commit")
    if not isinstance(merge_base, dict) or not _is_sha(merge_base.get("sha")):
        return _refusal(RefusalCode.REMOTE_PROBE_FAILED, 2)
    merge_base_sha = merge_base["sha"]

    changed = _changed_paths(runner, request.repository, request.pr_number)
    if changed is None:
        return _refusal(RefusalCode.REMOTE_PROBE_FAILED, 2)
    changed_paths, files_complete = changed

    entries = _path_entries(
        runner,
        request.repository,
        remote_tree,
        changed_paths,
    )
    if entries is None:
        return _refusal(RefusalCode.REMOTE_PROBE_FAILED, 2)
    path_entries, tree_complete = entries

    collision = _collision_census(
        runner,
        request.repository,
        request.pr_number,
        request.owned_paths,
    )
    if collision is None:
        return _refusal(RefusalCode.REMOTE_PROBE_FAILED, 2)
    collision_state, colliding_pr_numbers, collisions_complete = collision

    second_pr = _api_json(runner, pr_endpoint)
    second_identity = _pr_identity(second_pr)
    second_branch = _api_json(
        runner,
        _branch_endpoint(request.repository, request.branch),
    )
    second_base = _api_json(
        runner,
        _branch_endpoint(request.repository, request.base_ref),
    )
    if (
        second_identity is None
        or not isinstance(second_branch, dict)
        or not isinstance(second_base, dict)
    ):
        return _refusal(RefusalCode.REMOTE_PROBE_FAILED, 2)
    second_branch_commit = second_branch.get("commit")
    second_base_commit = second_base.get("commit")
    if (
        not isinstance(second_branch_commit, dict)
        or not isinstance(second_base_commit, dict)
    ):
        return _refusal(RefusalCode.REMOTE_PROBE_FAILED, 2)
    if (
        second_identity != first_identity
        or second_branch_commit.get("sha") != remote_head
        or second_base_commit.get("sha") != current_base_head
    ):
        return _refusal(RefusalCode.REMOTE_PROOF_CHANGED, 1)

    pagination_complete = files_complete and tree_complete and collisions_complete
    return RemoteGitFacts(
        repository=remote_repo,
        pr_number=request.pr_number,
        branch=remote_branch,
        base_ref=remote_base,
        pr_open=first_identity[0] == "open",
        pr_draft_or_hold=pr_draft_or_hold,
        head_sha=remote_head,
        tree_sha=remote_tree,
        merge_base_sha=merge_base_sha,
        current_base_head_sha=current_base_head,
        changed_paths=changed_paths,
        path_entries=path_entries,
        collision_state=collision_state,
        colliding_pr_numbers=colliding_pr_numbers,
        pagination_complete=pagination_complete,
    )


def _parse_nul_paths(value: str) -> set[str]:
    if not value:
        return set()
    return {path for path in value.split("\0") if path}


def _probe_local(
    runner: Runner,
    request: SourceContinuityRequest,
    remote: RemoteGitFacts,
) -> LocalGitFacts | SourceContinuityRefusal:
    root_result = _git(runner, None, "rev-parse", "--show-toplevel")
    if root_result is None or root_result.returncode != 0:
        return _refusal(RefusalCode.LOCAL_PROBE_FAILED, 2)
    root = root_result.stdout.strip()
    if not root:
        return _refusal(RefusalCode.LOCAL_PROBE_FAILED, 2)

    branch_result = _git(runner, root, "symbolic-ref", "--quiet", "--short", "HEAD")
    if branch_result is None:
        return _refusal(RefusalCode.LOCAL_PROBE_FAILED, 2)
    if branch_result.returncode != 0:
        return _refusal(RefusalCode.LOCAL_BRANCH_MISMATCH, 1)
    branch = branch_result.stdout.strip()

    head_result = _git(runner, root, "rev-parse", "HEAD")
    tree_result = _git(runner, root, "rev-parse", "HEAD^{tree}")
    if (
        head_result is None
        or tree_result is None
        or head_result.returncode != 0
        or tree_result.returncode != 0
    ):
        return _refusal(RefusalCode.LOCAL_PROBE_FAILED, 2)
    head_sha = head_result.stdout.strip()
    tree_sha = tree_result.stdout.strip()

    object_result = _git(runner, root, "cat-file", "-e", f"{remote.head_sha}^{{commit}}")
    if object_result is None:
        return _refusal(RefusalCode.LOCAL_PROBE_FAILED, 2)
    remote_head_object_exists = object_result.returncode == 0

    ancestor = False
    unpushed = 0
    if remote_head_object_exists:
        ancestor_result = _git(
            runner,
            root,
            "merge-base",
            "--is-ancestor",
            remote.head_sha,
            "HEAD",
        )
        if ancestor_result is None or ancestor_result.returncode not in {0, 1}:
            return _refusal(RefusalCode.LOCAL_PROBE_FAILED, 2)
        ancestor = ancestor_result.returncode == 0
        if ancestor:
            count_result = _git(
                runner,
                root,
                "rev-list",
                "--count",
                f"{remote.head_sha}..HEAD",
            )
            if count_result is None or count_result.returncode != 0:
                return _refusal(RefusalCode.LOCAL_PROBE_FAILED, 2)
            try:
                unpushed = int(count_result.stdout.strip())
            except ValueError:
                return _refusal(RefusalCode.LOCAL_PROBE_FAILED, 2)
            if unpushed < 0:
                return _refusal(RefusalCode.LOCAL_PROBE_FAILED, 2)

    unstaged = _git(runner, root, "diff", "--name-only", "-z", "HEAD")
    staged = _git(runner, root, "diff", "--cached", "--name-only", "-z")
    untracked = _git(runner, root, "ls-files", "--others", "--exclude-standard", "-z")
    if any(result is None or result.returncode != 0 for result in (unstaged, staged, untracked)):
        return _refusal(RefusalCode.LOCAL_PROBE_FAILED, 2)

    tracked_paths = _parse_nul_paths(unstaged.stdout) | _parse_nul_paths(staged.stdout)
    untracked_paths = _parse_nul_paths(untracked.stdout)
    owned = set(request.owned_paths)

    return LocalGitFacts(
        branch=branch,
        head_sha=head_sha,
        tree_sha=tree_sha,
        remote_head_object_exists=remote_head_object_exists,
        remote_head_is_ancestor_of_local=ancestor,
        unpushed_commit_count=unpushed,
        uncommitted_in_scope_count=len(tracked_paths & owned),
        untracked_in_scope_count=len(untracked_paths & owned),
        uncommitted_out_of_scope_count=len(tracked_paths - owned),
        untracked_out_of_scope_count=len(untracked_paths - owned),
    )


def _build_parser() -> _SafeArgumentParser:
    parser = _SafeArgumentParser(add_help=False)
    parser.add_argument("--receipt-kind", required=True, choices=[item.value for item in ReceiptKind])
    parser.add_argument("--operation-key", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--pr-number", required=True, type=int)
    parser.add_argument("--branch", required=True)
    parser.add_argument("--base-ref", required=True)
    parser.add_argument("--pinned-base-sha", required=True)
    parser.add_argument("--owned-path", required=True, action="append")
    parser.add_argument(
        "--external-effect-state",
        required=True,
        choices=[item.value for item in ExternalEffectState],
    )
    parser.add_argument(
        "--branch-effect-dependency",
        required=True,
        choices=[item.value for item in BranchEffectDependency],
    )
    parser.add_argument("--external-effect-evidence-fingerprint", required=True)
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    runner: Runner = subprocess.run,
    clock: Clock = _utc_now_z,
) -> int:
    try:
        args = _build_parser().parse_args(list(argv) if argv is not None else None)
        request = SourceContinuityRequest(
            receipt_kind=ReceiptKind(args.receipt_kind),
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

    auth = _invoke(runner, ("gh", "auth", "status", "--hostname", "github.com"))
    if auth is None or auth.returncode != 0:
        return _emit(_refusal(RefusalCode.AUTH_UNAVAILABLE, 2))

    try:
        remote = _probe_remote(runner, request)
        if isinstance(remote, SourceContinuityRefusal):
            return _emit(remote)
        local = _probe_local(runner, request, remote)
        if isinstance(local, SourceContinuityRefusal):
            return _emit(local)
        external = ExternalEffectEvidence(
            state=ExternalEffectState(args.external_effect_state),
            branch_dependency=BranchEffectDependency(args.branch_effect_dependency),
            evidence_fingerprint=args.external_effect_evidence_fingerprint,
        )
        result = verify_source_continuity(request, local, remote, external)
    except Exception:
        result = _refusal(RefusalCode.PROBE_INTERNAL_ERROR, 2)
    return _emit(result)


if __name__ == "__main__":
    raise SystemExit(main())

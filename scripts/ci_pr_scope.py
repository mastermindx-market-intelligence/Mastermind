"""Trusted-base PR CI scope, reusing the accepted review risk classifier.

The workflow MUST execute this file (and the imported risk policy) from the
protected PR base commit, not the PR checkout, or an untrusted PR could edit the
qualifier it is trying to pass. No review approval, protected-check waiver,
deployment, branch or runtime mutation is issued here.

FAST and STANDARD: quick PR checks, with the complete discovery-first suite
required on the exact native merge_group candidate before protected merge.
CRITICAL/HOLD/unverifiable: full PR tests as well as full merge_group tests.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from control_plane.github_review_risk_policy import (
    ReviewChangeFacts, ReviewFileStat, ReviewTier, assess_review_risk,
)
from scripts.ci_pr_smoke import SmokeUnqualified, _reviewed_registries, select_modules

_SHA = re.compile(r"^[0-9a-f]{40}$")
_VISUAL = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".ico", ".woff", ".woff2")
_MAX_OUTPUT_BYTES = 256_000
_MAX_EVENT_BYTES = 1_000_000


class CIScopeUnqualified(ValueError):
    """Exact diff, signed-event binding, or canonical policy was not proven."""


@dataclass(frozen=True)
class ScopeDecision:
    mode: str
    tier: str
    reason: str
    file_count: int = 0
    needs_node: bool = False
    source_base: str = field(default="", compare=False)
    source_head: str = field(default="", compare=False)

    @property
    def full(self) -> bool:
        return self.mode == "full"


def _git(root: Path, *args: str) -> bytes:
    try:
        output = subprocess.run(
            ["git", "-C", str(root), *args],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            check=True, timeout=12,
        ).stdout
    except (subprocess.SubprocessError, OSError):
        raise CIScopeUnqualified("GIT_DIFF_UNAVAILABLE") from None
    if len(output) > _MAX_OUTPUT_BYTES:
        raise CIScopeUnqualified("GIT_DIFF_OVER_BOUND")
    return output


def _path(value: bytes) -> str:
    try:
        name = value.decode("utf-8")
    except UnicodeError:
        raise CIScopeUnqualified("GIT_PATH_ENCODING_INVALID") from None
    if not name or "\x00" in name or "\n" in name or "\r" in name:
        raise CIScopeUnqualified("GIT_PATH_INVALID")
    return name


def _status_rows(raw: bytes) -> dict[str, str]:
    """Parse exact -z status records; refuse all delete/rename/copy/type moves."""
    tokens = raw.split(b"\x00")
    if tokens[-1] != b"":
        raise CIScopeUnqualified("GIT_STATUS_INCOMPLETE")
    tokens.pop()
    if len(tokens) % 2:
        raise CIScopeUnqualified("GIT_STATUS_MALFORMED")
    result = {}
    for i in range(0, len(tokens), 2):
        status, path = tokens[i], _path(tokens[i + 1])
        if status not in {b"M", b"A"}:
            raise CIScopeUnqualified("GIT_STATUS_NEEDS_FULL")
        if path in result:
            raise CIScopeUnqualified("GIT_PATH_DUPLICATED")
        result[path] = status.decode("ascii")
    return result


def _numstat_rows(raw: bytes) -> dict[str, tuple[int, int]]:
    tokens = raw.split(b"\x00")
    if tokens[-1] != b"":
        raise CIScopeUnqualified("GIT_NUMSTAT_INCOMPLETE")
    tokens.pop()
    result = {}
    for entry in tokens:
        fields = entry.split(b"\t", 2)
        if len(fields) != 3:
            raise CIScopeUnqualified("GIT_NUMSTAT_MALFORMED")
        a, d, path = fields
        name = _path(path)
        if name in result:
            raise CIScopeUnqualified("GIT_NUMSTAT_DUPLICATED")
        if a == b"-" and d == b"-" and name.lower().endswith(_VISUAL):
            # Git's binary diff has zero line metrics; trusted path/stat
            # coverage still holds, and the risk policy knows visual media.
            result[name] = (0, 0)
        elif a.isdigit() and d.isdigit():
            result[name] = (int(a), int(d))
        else:
            raise CIScopeUnqualified("GIT_NONVISUAL_BINARY_OR_METRIC_INVALID")
    return result


def classify(repo_path: Path, payload: dict, *, expected_repository: str) -> ScopeDecision:
    """Qualify the exact base...head Git source, never PR author text."""
    try:
        info = payload["pull_request"]
        number = info["number"]
        repo = payload["repository"]["full_name"]
        base = info["base"]["sha"]
        head = info["head"]["sha"]
        base_repo = info["base"]["repo"]["full_name"]
        head_repo = info["head"]["repo"]["full_name"]
    except (KeyError, TypeError, ValueError):
        raise CIScopeUnqualified("SIGNED_EVENT_INCOMPLETE") from None
    if (type(number) is not int or number <= 0 or type(repo) is not str
            or repo != expected_repository or type(base) is not str
            or type(head) is not str or _SHA.fullmatch(base) is None
            or _SHA.fullmatch(head) is None
            or base_repo != repo or head_repo != repo):
        raise CIScopeUnqualified("SIGNED_REPOSITORY_OR_HEAD_UNQUALIFIED")
    return _classify_verified_change(repo_path, base, head, number, expected_repository=expected_repository)


def _classify_verified_change(
    repo_path: Path, base: str, head: str, number: int, *,
    expected_repository: str,
    require_complete_smoke: bool = False,
) -> ScopeDecision:
    # The shared canonical risk assessor sees the complete verified source
    # diff, not event labels, user-authored text, or PR-only shortcuts.
    repo = expected_repository
    # The caller chooses the checkout directory, but never a remote, URL,
    # executable, ref, optional pipeline authority, or a shell command.
    root = repo_path.resolve(strict=True)
    if not (root / ".git").exists():
        raise CIScopeUnqualified("SOURCE_REPOSITORY_UNAVAILABLE")
    _git(root, "cat-file", "-e", f"{base}^{{commit}}")
    _git(root, "cat-file", "-e", f"{head}^{{commit}}")
    ancestor = _git(root, "merge-base", base, head).decode("ascii").strip()
    if _SHA.fullmatch(ancestor) is None:
        raise CIScopeUnqualified("MERGE_BASE_UNQUALIFIED")
    statuses = _status_rows(_git(
        root, "diff", "--name-status", "-z", "--find-renames", "--no-ext-diff",
        ancestor, head,
    ))
    metrics = _numstat_rows(_git(
        root, "diff", "--numstat", "-z", "--no-renames", "--no-ext-diff",
        ancestor, head,
    ))
    if not statuses or statuses.keys() != metrics.keys():
        raise CIScopeUnqualified("DIFF_FILE_COVERAGE_UNQUALIFIED")
    changed = tuple(sorted(statuses))
    # A benign-looking README symlink, changed executable mode or submodule
    # may be a new execution/data boundary. Source modes must be immutable,
    # exact regular Git blobs. One bounded ls-tree read covers every file.
    raw_tree = _git(root, "ls-tree", "-r", "-z", head, "--", *changed)
    if not raw_tree.endswith(b"\x00"):
        raise CIScopeUnqualified("GIT_TREE_INCOMPLETE")
    tree_paths = set()
    for record in raw_tree[:-1].split(b"\x00"):
        try:
            metadata, name = record.split(b"\t", 1)
            mode, kind, _ = metadata.split(b" ")
        except ValueError:
            raise CIScopeUnqualified("GIT_TREE_RECORD_MALFORMED") from None
        path = _path(name)
        if mode != b"100644" or kind != b"blob" or path in tree_paths:
            raise CIScopeUnqualified("GIT_EXECUTABLE_SYMLINK_OR_SUBMODULE")
        tree_paths.add(path)
    if tree_paths != set(changed):
        raise CIScopeUnqualified("GIT_TREE_FILE_COVERAGE_INVALID")
    entries = tuple(ReviewFileStat(
        path=path, additions=metrics[path][0], deletions=metrics[path][1],
    ) for path in changed)
    try:
        assessment = assess_review_risk(ReviewChangeFacts(
            repository=repo, pull_number=number, head_sha=head,
            changed_paths=changed,
            additions=sum(stat.additions for stat in entries),
            deletions=sum(stat.deletions for stat in entries),
            complete_source_verified=True,
            file_metrics=entries,
        ))
    except (ValueError, TypeError):
        raise CIScopeUnqualified("CANONICAL_RISK_SOURCE_UNQUALIFIED") from None
    if assessment.tier is ReviewTier.FAST:
        mode = "fast"
    elif assessment.tier is ReviewTier.STANDARD:
        mode = "smoke"
    else:
        mode = "full"
    reason = "SOURCE_VERIFIED"
    if mode == "smoke" and require_complete_smoke:
        try:
            select_modules(
                root, changed, identity_registries=_reviewed_registries(root, ancestor),
                require_complete=True,
            )
        except SmokeUnqualified as exc:
            # Coverage overflow is not a different risk tier. The existing
            # canonical full-suite path supplies the missing acceptance.
            mode, reason = "full", str(exc)
    needs_node = any(path.startswith("app/mastermind_os/") for path in changed)
    return ScopeDecision(mode, assessment.tier.value, reason, len(changed), needs_node,
                         source_base=ancestor, source_head=head)



def classify_merge_group(
    repo_path: Path, payload: dict, *,
    expected_repository: str, protected_base_sha: str,
) -> ScopeDecision:
    """Risk-scope the entire actual integrated candidate, not its latest PR only.

    The trusted code is loaded from the protected branch; the candidate must
    be a descendant of that exact protected head. A moving/non-ancestor
    base or ambiguous GitHub queue identity means full CI, not an escape.
    """
    try:
        group = payload["merge_group"]
        repo = payload["repository"]["full_name"]
        event_base, event_head = group["base_sha"], group["head_sha"]
        base_ref, head_ref = group["base_ref"], group["head_ref"]
    except (KeyError, TypeError):
        raise CIScopeUnqualified("SIGNED_MERGE_GROUP_INCOMPLETE") from None
    if (repo != expected_repository or type(event_base) is not str
            or type(event_head) is not str
            or _SHA.fullmatch(event_base) is None
            or _SHA.fullmatch(event_head) is None
            or type(protected_base_sha) is not str
            or _SHA.fullmatch(protected_base_sha) is None
            or base_ref != "refs/heads/master"
            or type(head_ref) is not str
            or not head_ref.startswith("refs/heads/gh-readonly-queue/master/")):
        raise CIScopeUnqualified("SIGNED_MERGE_GROUP_IDENTITY_UNQUALIFIED")
    root = repo_path.resolve(strict=True)
    if not (root / ".git").exists():
        raise CIScopeUnqualified("SOURCE_REPOSITORY_UNAVAILABLE")
    if (_git(root, "rev-parse", "HEAD").decode("ascii").strip() != event_head
            or _git(root, "rev-parse", "refs/remotes/origin/master").decode("ascii").strip()
            != protected_base_sha):
        raise CIScopeUnqualified("MERGE_GROUP_CHECKOUT_OR_PROTECTED_BASE_CHANGED")
    _git(root, "cat-file", "-e", f"{event_base}^{{commit}}")
    _git(root, "cat-file", "-e", f"{event_head}^{{commit}}")
    _git(root, "merge-base", "--is-ancestor", event_base, event_head)
    _git(root, "merge-base", "--is-ancestor", protected_base_sha, event_head)
    # The assessment identity is internal (not a PR, reviewer, merge command,
    # or GitHub receipt); release authority remains with the native queue.
    return _classify_verified_change(
        repo_path, protected_base_sha, event_head, 1,
        expected_repository=expected_repository,
        require_complete_smoke=True,
    )

def select_scope(repo_path: Path, event_path: Path, *, expected_repository: str,
                 event_type: str = 'pull_request',
                 protected_base_sha: str = '') -> ScopeDecision:
    try:
        if event_path.stat().st_size > _MAX_EVENT_BYTES:
            raise CIScopeUnqualified("EVENT_OVER_BOUND")
        payload = json.loads(event_path.read_text(encoding="utf-8"))
        if type(payload) is not dict:
            raise CIScopeUnqualified("EVENT_MALFORMED")
        if event_type == "merge_group":
            return classify_merge_group(
                repo_path, payload, expected_repository=expected_repository,
                protected_base_sha=protected_base_sha,
            )
        if event_type != "pull_request":
            raise CIScopeUnqualified("EVENT_TYPE_NOT_SCOPED")
        return classify(repo_path, payload, expected_repository=expected_repository)
    except CIScopeUnqualified as exc:
        return ScopeDecision("full", "HOLD", str(exc))
    except (OSError, UnicodeError, ValueError, TypeError):
        return ScopeDecision("full", "HOLD", "EVENT_OR_DIFF_UNAVAILABLE")


def main() -> int:
    parser = argparse.ArgumentParser(description="Trusted-base risk-tiered CI scope")
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--event", type=Path, required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--event-type", choices=("pull_request", "merge_group"),
                        default="pull_request")
    parser.add_argument("--protected-base", default="")
    args = parser.parse_args()
    decision = select_scope(
        args.repo, args.event, expected_repository=args.repository,
        event_type=args.event_type, protected_base_sha=args.protected_base,
    )
    # Output is closed vocabulary; no author-controlled path or text emitted.
    output = (f"mode={decision.mode}\ntier={decision.tier}\n"
              f"needs_node={str(decision.needs_node).lower()}\n"
              f"source_base={decision.source_base}\nsource_head={decision.source_head}\n")
    with args.output.open("a", encoding="ascii") as target:
        target.write(output)
    print(f"CI_SCOPE mode={decision.mode} tier={decision.tier} "
          f"changed_files={decision.file_count} reason={decision.reason}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

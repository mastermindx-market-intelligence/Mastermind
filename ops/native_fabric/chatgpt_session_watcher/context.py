"""Read-only project context. GitHub writes and Slack posts are not this worker's tools."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

SLACK_CHANNEL = "C0CBC6AEAQZ"

_GH_ALLOWED = frozenset({
    ("pr", "view"),
    ("pr", "checks"),
})
_GH_REFUSED = frozenset({
    "merge", "review", "comment", "edit", "ready", "label", "close", "create", "reopen", "approve",
})


class ContextRefusal(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass
class ProjectContext:
    ci: str | None = None  # green | red | pending
    review: str | None = None  # landed | pending | changes
    notes: list[str] = field(default_factory=list)

    def sentence(self, tail: str) -> str | None:
        text = tail or ""
        if self.ci == "green" and re.search(r"\bCI\b|checks are pending|waiting on CI", text):
            return "The CI you were waiting on finished green."
        if self.review == "landed" and re.search(r"review", text, re.I):
            return "The review landed."
        return None


class ReadOnlyGitHub:
    """gh pr view / gh pr checks only. Refuses merge, approve, label, enqueue, and Ready."""

    def __init__(self, runner=None):
        self._runner = runner

    def pr_snapshot(self, repo: str, number: int) -> ProjectContext:
        if self._runner is None:
            return ProjectContext()
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
            raise ContextRefusal("bad_repo")
        if not isinstance(number, int) or number < 1:
            raise ContextRefusal("bad_pr")
        view = self._run(["pr", "view", str(number), "--repo", repo, "--json",
                          "state,statusCheckRollup,reviews,title"])
        checks = self._run(["pr", "checks", str(number), "--repo", repo])
        return _interpret(view, checks)

    def _run(self, args: list[str]) -> str:
        if len(args) < 2 or (args[0], args[1]) not in _GH_ALLOWED:
            raise ContextRefusal("github_write_refused")
        if any(part in _GH_REFUSED for part in args):
            raise ContextRefusal("github_write_refused")
        if any(token in part for part in args for token in (";", "|", "&", "$", "\n", "`")):
            raise ContextRefusal("github_write_refused")
        return self._runner(["gh", *args])


def _interpret(view_text: str, checks_text: str) -> ProjectContext:
    ctx = ProjectContext()
    try:
        view = json.loads(view_text)
    except json.JSONDecodeError:
        return ctx
    rollup = view.get("statusCheckRollup") or []
    conclusions = []
    if isinstance(rollup, list):
        for item in rollup:
            if isinstance(item, dict):
                conclusions.append(str(item.get("conclusion") or item.get("state") or "").upper())
    blob = (checks_text or "") + " " + " ".join(conclusions)
    if conclusions and all(item in {"SUCCESS", "NEUTRAL", "SKIPPED"} for item in conclusions if item):
        ctx.ci = "green"
    elif "FAILURE" in blob.upper() or "fail" in blob.casefold():
        ctx.ci = "red"
    elif conclusions:
        ctx.ci = "pending"
    reviews = view.get("reviews") or []
    states = [str(item.get("state") or "").upper() for item in reviews if isinstance(item, dict)]
    if "APPROVED" in states or "COMMENTED" in states:
        ctx.review = "landed"
    elif "CHANGES_REQUESTED" in states:
        ctx.review = "changes"
    elif states:
        ctx.review = "pending"
    return ctx


class SlackReader:
    """Read #dotsandgroksecretary. This object has no send method."""

    def __init__(self, reader=None, channel: str = SLACK_CHANNEL):
        self.channel = channel
        self._reader = reader or (lambda _channel: [])

    def recent(self) -> list[str]:
        rows = self._reader(self.channel) or []
        return [str(row) for row in rows]


def context_for_tail(tail: str, github: ReadOnlyGitHub | None = None, slack: SlackReader | None = None) -> ProjectContext:
    ctx = ProjectContext()
    match = re.search(r"\b([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)?#(\d{1,6})\b", tail or "")
    if github and match and match.group(1):
        try:
            ctx = github.pr_snapshot(match.group(1), int(match.group(2)))
        except ContextRefusal:
            ctx = ProjectContext()
    if slack:
        for line in slack.recent():
            low = line.casefold()
            if "review" in low and any(word in low for word in ("landed", "approved", "commented")):
                ctx.review = ctx.review or "landed"
            if "ci" in low and "green" in low:
                ctx.ci = "green"
    return ctx

"""Trusted GitHub source provider for Web-CEO strict-v2 commission admission.

The public Executive App remains source-free.  A Web session publishes its complete
worker brief in the already-owned attended workspace branch ``sol/web-<operation_key>``.
This provider deterministically re-derives the automated Executive intent identity from
that branch suffix, snapshots one exact branch head, reads one fixed commission path at
that immutable commit, and returns the existing ``ExecutiveDialogueSource`` wire shape.

It owns no registry, database, queue, lifecycle, authority or retry plane.  Workstream
never selects a branch.  No caller chooses repository, remote, ref pattern, path, host,
credential or executable.
"""
from __future__ import annotations

import hashlib
import re
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from typing import Any

from control_plane import ceo_request
from control_plane.executive_runtime import (
    EXECUTIVE_DIALOGUE_SOURCE_SCHEMA,
    ExecutiveDialogueSource,
    StateConflict,
)


CANONICAL_REPOSITORY = "mastermindx-market-intelligence/Mastermind"
CANONICAL_REMOTE_URL = "https://github.com/mastermindx-market-intelligence/Mastermind.git"
WEB_BRANCH_PREFIX = "refs/heads/sol/web-"
COMMISSION_PATH = "research/executive_commissions/COMMISSION.md"
_RAW_HOST = "raw.githubusercontent.com"
_MAX_COMMISSION_BYTES = 1 << 19
_MAX_REMOTE_OUTPUT_BYTES = 1 << 18
_MAX_WEB_REFS = 1 << 9
_NETWORK_TIMEOUT_SECONDS = 10.0
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


class WebCommissionSourceError(RuntimeError):
    """The trusted Web commission source could not be resolved exactly."""


def _git_env() -> dict[str, str]:
    return {
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        "LANG": "C",
        "LC_ALL": "C",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_ASKPASS": "/usr/bin/false",
        "SSH_ASKPASS": "/usr/bin/false",
    }


def list_web_branch_refs() -> tuple[tuple[str, str], ...]:
    """Observe the bounded canonical remote branch namespace exactly once."""

    try:
        proc = subprocess.run(
            [
                "/usr/bin/git",
                "ls-remote",
                "--heads",
                CANONICAL_REMOTE_URL,
                f"{WEB_BRANCH_PREFIX}*",
            ],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=_NETWORK_TIMEOUT_SECONDS,
            env=_git_env(),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise WebCommissionSourceError("canonical Web branch observation is unavailable") from exc
    if proc.returncode != 0 or len(proc.stdout) > _MAX_REMOTE_OUTPUT_BYTES:
        raise WebCommissionSourceError("canonical Web branch observation is unavailable")

    refs: list[tuple[str, str]] = []
    for raw in proc.stdout.splitlines():
        parts = raw.split(b"\t")
        if len(parts) != 2:
            raise WebCommissionSourceError("canonical Web branch observation is malformed")
        try:
            sha = parts[0].decode("ascii", errors="strict")
            ref = parts[1].decode("ascii", errors="strict")
        except UnicodeDecodeError as exc:
            raise WebCommissionSourceError("canonical Web branch observation is malformed") from exc
        if _SHA_RE.fullmatch(sha) is None or not ref.startswith(WEB_BRANCH_PREFIX):
            raise WebCommissionSourceError("canonical Web branch observation is malformed")
        refs.append((sha, ref))
        if len(refs) > _MAX_WEB_REFS:
            raise WebCommissionSourceError("canonical Web branch census exceeds the reviewed bound")
    if len({ref for _sha, ref in refs}) != len(refs):
        raise WebCommissionSourceError("canonical Web branch observation contains duplicate refs")
    return tuple(refs)


def fetch_commission_blob(*, commit: str) -> bytes:
    """Fetch one fixed-path blob from one exact public GitHub commit, without auth."""

    if _SHA_RE.fullmatch(commit) is None:
        raise WebCommissionSourceError("commission commit is malformed")
    encoded_path = urllib.parse.quote(COMMISSION_PATH, safe="/")
    url = f"https://{_RAW_HOST}/{CANONICAL_REPOSITORY}/{commit}/{encoded_path}"
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/octet-stream",
            "User-Agent": "Mastermind-Web-Commission-Source/1",
        },
        method="GET",
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=_NETWORK_TIMEOUT_SECONDS) as response:
            final = urllib.parse.urlparse(response.geturl())
            if final.scheme != "https" or final.hostname != _RAW_HOST:
                raise WebCommissionSourceError("commission fetch escaped the canonical GitHub raw host")
            declared = response.headers.get("Content-Length")
            if declared is not None:
                try:
                    size = int(declared)
                except ValueError as exc:
                    raise WebCommissionSourceError("commission response length is malformed") from exc
                if size < 1 or size > _MAX_COMMISSION_BYTES:
                    raise WebCommissionSourceError("commission content is outside the reviewed size bound")
            content = response.read(_MAX_COMMISSION_BYTES + 1)
    except WebCommissionSourceError:
        raise
    except (OSError, urllib.error.URLError, ValueError) as exc:
        raise WebCommissionSourceError("commission blob is unavailable") from exc

    if not content or len(content) > _MAX_COMMISSION_BYTES:
        raise WebCommissionSourceError("commission content is outside the reviewed size bound")
    try:
        text = content.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise WebCommissionSourceError("commission content is not UTF-8") from exc
    if "\x00" in text:
        raise WebCommissionSourceError("commission content contains a NUL byte")
    return bytes(content)


class GitHubWebCommissionSourceProvider:
    """Resolve one immutable commission from the existing attended Web branch owner."""

    def __init__(
        self,
        *,
        list_refs: Callable[[], tuple[tuple[str, str], ...]] = list_web_branch_refs,
        fetch_blob: Callable[..., bytes] = fetch_commission_blob,
    ) -> None:
        if not callable(list_refs) or not callable(fetch_blob):
            raise TypeError("commission source dependencies must be callable")
        self._list_refs = list_refs
        self._fetch_blob = fetch_blob

    def __call__(self, intent_id: str, work_ref: str) -> dict[str, Any] | None:
        if not isinstance(intent_id, str) or not intent_id or len(intent_id) > 64:
            raise WebCommissionSourceError("Executive intent identity is malformed")
        if not isinstance(work_ref, str) or not work_ref or len(work_ref) > 72:
            raise WebCommissionSourceError("Executive work reference is malformed")

        observed_refs = self._list_refs()
        if not isinstance(observed_refs, tuple) or len(observed_refs) > _MAX_WEB_REFS:
            raise WebCommissionSourceError("canonical Web branch census exceeds the reviewed bound")
        matches: list[tuple[str, str]] = []
        seen_refs: set[str] = set()
        for head_sha, ref in observed_refs:
            if not isinstance(head_sha, str) or _SHA_RE.fullmatch(head_sha) is None:
                raise WebCommissionSourceError("canonical Web branch observation is malformed")
            if (
                not isinstance(ref, str)
                or not ref.startswith(WEB_BRANCH_PREFIX)
                or ref in seen_refs
            ):
                raise WebCommissionSourceError("canonical Web branch observation is malformed")
            seen_refs.add(ref)
            operation_key = ref[len(WEB_BRANCH_PREFIX) :]
            try:
                candidate = ceo_request.automated_intent_id(
                    ceo_request.app_request_ref(operation_key)
                )
            except ceo_request.CeoRequestError:
                continue
            if candidate == intent_id:
                matches.append((head_sha, operation_key))

        if not matches:
            return None
        if len(matches) != 1:
            raise WebCommissionSourceError("Executive intent maps to multiple Web commission branches")
        commit, _operation_key = matches[0]
        content = self._fetch_blob(commit=commit)
        if not isinstance(content, bytes):
            raise WebCommissionSourceError("commission blob resolver returned a non-byte payload")
        if not content or len(content) > _MAX_COMMISSION_BYTES:
            raise WebCommissionSourceError("commission content is outside the reviewed size bound")
        try:
            decoded = content.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise WebCommissionSourceError("commission content is not UTF-8") from exc
        if "\x00" in decoded:
            raise WebCommissionSourceError("commission content contains a NUL byte")
        try:
            return ExecutiveDialogueSource(
                schema_version=EXECUTIVE_DIALOGUE_SOURCE_SCHEMA,
                work_ref=work_ref,
                commission_ref={
                    "repository": CANONICAL_REPOSITORY,
                    "commit": commit,
                    "path": COMMISSION_PATH,
                    "content_sha256": hashlib.sha256(content).hexdigest(),
                },
                watch_mode=None,
            ).to_dict()
        except StateConflict as exc:
            raise WebCommissionSourceError("resolved commission source is not canonical") from exc


__all__ = [
    "CANONICAL_REPOSITORY",
    "CANONICAL_REMOTE_URL",
    "COMMISSION_PATH",
    "GitHubWebCommissionSourceProvider",
    "WebCommissionSourceError",
    "fetch_commission_blob",
    "list_web_branch_refs",
]

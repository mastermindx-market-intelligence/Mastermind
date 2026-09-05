"""Fixed GitHub API port for exact expected-head branch repair commits.

No model-visible input reaches an HTTP method, host, endpoint family, credential,
or request header. Repository, branch, and paths arrive only from the accepted
server-side authority resolver or an authenticated token-bound reconciliation
target. GitHub remains effect truth and this port contains no retry loop.
"""
from __future__ import annotations

import asyncio
import base64
import dataclasses
import hashlib
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping, Sequence
from typing import Protocol

from integrations.mastermind_github_app.models import (
    CommitFile,
    EffectObservation,
    EffectState,
    GithubBlob,
    NativeCommitError,
    NativeCommitResult,
    ResolvedPatchTarget,
)

REST_ROOT = "https://api.github.com"
GRAPHQL_ENDPOINT = "https://api.github.com/graphql"
API_VERSION = "2022-11-28"
USER_AGENT = "Mastermind-GitHub-Patch/0.3"
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
MAX_LIVE_BLOB_BYTES = 4 * 1024 * 1024
MAX_COMMIT_SCAN = 100

_REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}$")
_OID_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
_OPERATION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,191}$")

_CREATE_COMMIT_MUTATION = """
mutation CreateBoundedBranchPatch($input: CreateCommitOnBranchInput!) {
  createCommitOnBranch(input: $input) {
    commit { oid url }
  }
}
""".strip()


@dataclasses.dataclass(frozen=True)
class HttpResponse:
    status: int
    headers: Mapping[str, str]
    body: bytes


class HttpTransport(Protocol):
    async def request(
        self,
        *,
        method: str,
        url: str,
        headers: Mapping[str, str],
        body: bytes | None,
        timeout_seconds: float,
    ) -> HttpResponse: ...


class GithubTokenProvider(Protocol):
    async def installation_token(self) -> str: ...


class GithubReadError(RuntimeError):
    def __init__(self) -> None:
        super().__init__("github_read_error")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


class UrllibHttpTransport:
    async def request(
        self,
        *,
        method: str,
        url: str,
        headers: Mapping[str, str],
        body: bytes | None,
        timeout_seconds: float,
    ) -> HttpResponse:
        return await asyncio.to_thread(
            self._request_sync,
            method,
            url,
            dict(headers),
            body,
            timeout_seconds,
        )

    @staticmethod
    def _request_sync(
        method: str,
        url: str,
        headers: Mapping[str, str],
        body: bytes | None,
        timeout_seconds: float,
    ) -> HttpResponse:
        request = urllib.request.Request(url=url, data=body, headers=dict(headers), method=method)
        opener = urllib.request.build_opener(_NoRedirect())
        try:
            with opener.open(request, timeout=timeout_seconds) as response:
                raw = response.read(MAX_RESPONSE_BYTES + 1)
                if len(raw) > MAX_RESPONSE_BYTES:
                    raise GithubReadError()
                return HttpResponse(
                    status=int(response.status),
                    headers={key.lower(): value for key, value in response.headers.items()},
                    body=raw,
                )
        except urllib.error.HTTPError as exc:
            raw = exc.read(MAX_RESPONSE_BYTES + 1)
            if len(raw) > MAX_RESPONSE_BYTES:
                raise GithubReadError() from exc
            return HttpResponse(
                status=int(exc.code),
                headers={key.lower(): value for key, value in exc.headers.items()},
                body=raw,
            )
        except (OSError, urllib.error.URLError) as exc:
            raise GithubReadError() from exc


class GithubApiPatchPort:
    """Closed GitHub implementation of the GHP2 owner port."""

    def __init__(
        self,
        *,
        transport: HttpTransport,
        token_provider: GithubTokenProvider,
        timeout_seconds: float = 20.0,
    ) -> None:
        if timeout_seconds <= 0 or timeout_seconds > 60:
            raise ValueError("timeout must be within (0, 60]")
        self._transport = transport
        self._token_provider = token_provider
        self._timeout_seconds = float(timeout_seconds)

    async def read_branch_head(self, target: ResolvedPatchTarget) -> str:
        repository = self._repository(target.repository)
        branch = self._branch(target.branch)
        ref = urllib.parse.quote(f"heads/{branch}", safe="/")
        value, _ = await self._json_request(
            "GET",
            f"{REST_ROOT}/repos/{repository}/git/ref/{ref}",
            None,
        )
        try:
            oid = value["object"]["sha"]
        except (KeyError, TypeError) as exc:
            raise GithubReadError() from exc
        return self._oid(oid)

    async def read_blob(
        self,
        target: ResolvedPatchTarget,
        head_oid: str,
        path: str,
    ) -> GithubBlob:
        repository = self._repository(target.repository)
        head = self._oid(head_oid)
        parts = self._path_parts(path)
        commit, _ = await self._json_request(
            "GET",
            f"{REST_ROOT}/repos/{repository}/git/commits/{head}",
            None,
        )
        try:
            tree_oid = self._oid(commit["tree"]["sha"])
        except (KeyError, TypeError) as exc:
            raise GithubReadError() from exc

        entry: Mapping[str, object] | None = None
        for index, part in enumerate(parts):
            tree, _ = await self._json_request(
                "GET",
                f"{REST_ROOT}/repos/{repository}/git/trees/{tree_oid}",
                None,
            )
            rows = tree.get("tree") if isinstance(tree, Mapping) else None
            if not isinstance(rows, list):
                raise GithubReadError()
            matches = [row for row in rows if isinstance(row, Mapping) and row.get("path") == part]
            if len(matches) != 1:
                raise GithubReadError()
            entry = matches[0]
            final = index == len(parts) - 1
            if final:
                if entry.get("type") != "blob" or entry.get("mode") != "100644":
                    raise GithubReadError()
            else:
                if entry.get("type") != "tree" or entry.get("mode") != "040000":
                    raise GithubReadError()
                tree_oid = self._oid(entry.get("sha"))
        if entry is None:
            raise GithubReadError()

        blob_oid = self._oid(entry.get("sha"))
        blob, _ = await self._json_request(
            "GET",
            f"{REST_ROOT}/repos/{repository}/git/blobs/{blob_oid}",
            None,
        )
        if blob.get("encoding") != "base64" or blob.get("sha") != blob_oid:
            raise GithubReadError()
        encoded = blob.get("content")
        size = blob.get("size")
        if (
            not isinstance(encoded, str)
            or isinstance(size, bool)
            or not isinstance(size, int)
            or size < 0
            or size > MAX_LIVE_BLOB_BYTES
        ):
            raise GithubReadError()
        compact = "".join(encoded.split())
        try:
            raw = base64.b64decode(compact.encode("ascii"), validate=True)
            content = raw.decode("utf-8")
        except (ValueError, UnicodeError) as exc:
            raise GithubReadError() from exc
        if len(raw) != size or len(raw) > MAX_LIVE_BLOB_BYTES:
            raise GithubReadError()
        if self._git_blob_oid(raw, width=len(blob_oid)) != blob_oid:
            raise GithubReadError()
        return GithubBlob(
            path="/".join(parts),
            oid=blob_oid,
            content=content,
            object_kind="REGULAR_FILE",
            encoding="utf-8",
            truncated=False,
        )

    async def commit_branch_patch(
        self,
        target: ResolvedPatchTarget,
        expected_head_oid: str,
        operation_key: str,
        effect_digest: str,
        files: Sequence[CommitFile],
    ) -> NativeCommitResult:
        repository = self._repository(target.repository)
        branch = self._branch(target.branch)
        expected_head = self._oid(expected_head_oid)
        operation = self._operation(operation_key)
        effect = self._sha256(effect_digest)
        if not 1 <= len(files) <= 3:
            raise NativeCommitError(effect_possible=False)

        additions: list[dict[str, str]] = []
        after_lines: list[str] = []
        seen: set[str] = set()
        for item in sorted(files, key=lambda row: row.path):
            if not isinstance(item, CommitFile):
                raise NativeCommitError(effect_possible=False)
            path = "/".join(self._path_parts(item.path))
            if path in seen:
                raise NativeCommitError(effect_possible=False)
            seen.add(path)
            self._oid(item.expected_blob_oid)
            after_digest = self._sha256(item.after_sha256)
            try:
                raw = item.content.encode("utf-8")
            except UnicodeError as exc:
                raise NativeCommitError(effect_possible=False) from exc
            if len(raw) > MAX_LIVE_BLOB_BYTES or hashlib.sha256(raw).hexdigest() != after_digest:
                raise NativeCommitError(effect_possible=False)
            additions.append({"path": path, "contents": base64.b64encode(raw).decode("ascii")})
            after_lines.append(f"Mastermind-File: {path} {after_digest}")

        variables = {
            "input": {
                "branch": {
                    "repositoryNameWithOwner": repository,
                    "branchName": branch,
                },
                "message": {
                    "headline": f"fix(scf): apply bounded branch patch {effect[:12]}",
                    "body": "\n".join(
                        [
                            f"Mastermind-Operation: {operation}",
                            f"Mastermind-Effect: {effect}",
                            f"Mastermind-Expected-Head: {expected_head}",
                            *after_lines,
                        ]
                    ),
                },
                "fileChanges": {"additions": additions},
                "expectedHeadOid": expected_head,
            }
        }
        payload = json.dumps(
            {"query": _CREATE_COMMIT_MUTATION, "variables": variables},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        try:
            value, _ = await self._json_request("POST", GRAPHQL_ENDPOINT, payload)
        except GithubReadError as exc:
            raise NativeCommitError(effect_possible=True) from exc
        if not isinstance(value, Mapping) or value.get("errors"):
            raise NativeCommitError(effect_possible=True)
        try:
            oid = self._oid(value["data"]["createCommitOnBranch"]["commit"]["oid"])
        except (KeyError, TypeError) as exc:
            raise NativeCommitError(effect_possible=True) from exc
        return NativeCommitResult(request_sent=True, commit_oid=oid, definite_no_effect=False)

    async def reconcile_branch_patch(
        self,
        target: ResolvedPatchTarget,
        expected_head_oid: str,
        operation_key: str,
        effect_digest: str,
        expected_after_sha256: Mapping[str, str],
    ) -> EffectObservation:
        repository = self._repository(target.repository)
        branch = self._branch(target.branch)
        expected_head = self._oid(expected_head_oid)
        operation = self._operation(operation_key)
        effect = self._sha256(effect_digest)
        expected_after = {
            "/".join(self._path_parts(path)): self._sha256(digest)
            for path, digest in expected_after_sha256.items()
        }
        if not 1 <= len(expected_after) <= 3:
            raise GithubReadError()

        current_head = await self.read_branch_head(target)
        query = urllib.parse.urlencode({"sha": branch, "per_page": MAX_COMMIT_SCAN})
        commits, _ = await self._json_request(
            "GET",
            f"{REST_ROOT}/repos/{repository}/commits?{query}",
            None,
        )
        if not isinstance(commits, list):
            raise GithubReadError()
        marker = self._marker(operation, effect, expected_head, expected_after)
        candidates: list[str] = []
        observed_oids: list[str] = []
        for row in commits:
            if not isinstance(row, Mapping):
                raise GithubReadError()
            try:
                oid = self._oid(row["sha"])
                message = row["commit"]["message"]
            except (KeyError, TypeError) as exc:
                raise GithubReadError() from exc
            if not isinstance(message, str):
                raise GithubReadError()
            observed_oids.append(oid)
            if message == marker:
                candidates.append(oid)

        if len(candidates) > 1:
            return EffectObservation(EffectState.EFFECT_UNKNOWN, None, current_head, False)
        if len(candidates) == 1:
            candidate = candidates[0]
            valid = await self._verify_effect_commit(
                repository=repository,
                candidate_oid=candidate,
                expected_head_oid=expected_head,
                expected_after=expected_after,
                target=target,
            )
            return EffectObservation(
                EffectState.APPLIED if valid else EffectState.EFFECT_UNKNOWN,
                candidate if valid else None,
                current_head,
                valid,
            )

        # The exact createCommitOnBranch effect, if applied, must be a child of
        # expected_head and remain in the branch history. Seeing expected_head
        # in the complete scanned prefix proves no such child marker exists,
        # even when unrelated later commits advanced the branch.
        if current_head == expected_head or expected_head in observed_oids:
            return EffectObservation(EffectState.NOT_APPLIED, None, current_head, True)
        return EffectObservation(EffectState.EFFECT_UNKNOWN, None, current_head, False)

    async def _verify_effect_commit(
        self,
        *,
        repository: str,
        candidate_oid: str,
        expected_head_oid: str,
        expected_after: Mapping[str, str],
        target: ResolvedPatchTarget,
    ) -> bool:
        value, _ = await self._json_request(
            "GET",
            f"{REST_ROOT}/repos/{repository}/commits/{candidate_oid}",
            None,
        )
        parents = value.get("parents") if isinstance(value, Mapping) else None
        files = value.get("files") if isinstance(value, Mapping) else None
        actor = value.get("author") if isinstance(value, Mapping) else None
        if (
            not isinstance(actor, Mapping)
            or actor.get("login") != target.expected_actor_login
            or type(actor.get("id")) is not int
            or actor.get("id") != target.expected_actor_id
            or not isinstance(parents, list)
            or len(parents) != 1
            or not isinstance(parents[0], Mapping)
            or parents[0].get("sha") != expected_head_oid
            or not isinstance(files, list)
        ):
            return False
        actual_paths: set[str] = set()
        for row in files:
            if not isinstance(row, Mapping) or row.get("status") != "modified":
                return False
            path = row.get("filename")
            if not isinstance(path, str):
                return False
            actual_paths.add(path)
        if actual_paths != set(expected_after):
            return False
        for path, expected_digest in expected_after.items():
            blob = await self.read_blob(target, candidate_oid, path)
            if hashlib.sha256(blob.content.encode("utf-8")).hexdigest() != expected_digest:
                return False
        return True

    async def _json_request(
        self,
        method: str,
        url: str,
        body: bytes | None,
    ) -> tuple[object, Mapping[str, str]]:
        if method not in {"GET", "POST"}:
            raise GithubReadError()
        if not (url == GRAPHQL_ENDPOINT or url.startswith(f"{REST_ROOT}/repos/")):
            raise GithubReadError()
        try:
            token = await self._token_provider.installation_token()
        except Exception as exc:
            raise GithubReadError() from exc
        if (
            not isinstance(token, str)
            or not 20 <= len(token) <= 2_000
            or any(ord(char) <= 32 or ord(char) == 127 for char in token)
        ):
            raise GithubReadError()
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": API_VERSION,
            "User-Agent": USER_AGENT,
        }
        if body is not None:
            headers["Content-Type"] = "application/json"
        response = await self._transport.request(
            method=method,
            url=url,
            headers=headers,
            body=body,
            timeout_seconds=self._timeout_seconds,
        )
        if (
            not isinstance(response, HttpResponse)
            or not 200 <= response.status < 300
            or len(response.body) > MAX_RESPONSE_BYTES
        ):
            raise GithubReadError()
        try:
            value = json.loads(response.body.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise GithubReadError() from exc
        return value, {str(key).lower(): str(item) for key, item in response.headers.items()}

    @staticmethod
    def _git_blob_oid(content: bytes, *, width: int) -> str:
        framed = b"blob " + str(len(content)).encode("ascii") + b"\0" + content
        if width == 40:
            return hashlib.sha1(framed, usedforsecurity=False).hexdigest()
        if width == 64:
            return hashlib.sha256(framed).hexdigest()
        raise GithubReadError()

    @staticmethod
    def _marker(
        operation_key: str,
        effect_digest: str,
        expected_head_oid: str,
        expected_after: Mapping[str, str],
    ) -> str:
        lines = [
            f"fix(scf): apply bounded branch patch {effect_digest[:12]}",
            "",
            f"Mastermind-Operation: {operation_key}",
            f"Mastermind-Effect: {effect_digest}",
            f"Mastermind-Expected-Head: {expected_head_oid}",
        ]
        lines.extend(
            f"Mastermind-File: {path} {digest}"
            for path, digest in sorted(expected_after.items())
        )
        return "\n".join(lines)

    @staticmethod
    def _repository(value: object) -> str:
        if not isinstance(value, str) or _REPOSITORY_RE.fullmatch(value) is None:
            raise GithubReadError()
        return "/".join(urllib.parse.quote(part, safe="") for part in value.split("/"))

    @staticmethod
    def _branch(value: object) -> str:
        if (
            not isinstance(value, str)
            or not value
            or len(value) > 255
            or value == "HEAD"
            or value.startswith("refs/")
            or value.startswith("-")
            or value.endswith(".")
            or ".." in value
            or "//" in value
            or "@{" in value
            or value.endswith(".lock")
            or any(ord(char) <= 32 or ord(char) == 127 for char in value)
        ):
            raise GithubReadError()
        return value

    @staticmethod
    def _path_parts(value: object) -> tuple[str, ...]:
        if not isinstance(value, str) or not value or value.startswith("/") or "\\" in value:
            raise GithubReadError()
        parts = tuple(value.split("/"))
        if any(
            not part
            or part in {".", "..", ".git"}
            or any(ord(char) < 32 or ord(char) == 127 for char in part)
            for part in parts
        ):
            raise GithubReadError()
        if len(value.encode("utf-8")) > 512:
            raise GithubReadError()
        return parts

    @staticmethod
    def _oid(value: object) -> str:
        if not isinstance(value, str) or _OID_RE.fullmatch(value) is None:
            raise GithubReadError()
        return value

    @staticmethod
    def _sha256(value: object) -> str:
        if not isinstance(value, str) or _HEX64_RE.fullmatch(value) is None:
            raise GithubReadError()
        return value

    @staticmethod
    def _operation(value: object) -> str:
        if not isinstance(value, str) or _OPERATION_RE.fullmatch(value) is None:
            raise GithubReadError()
        return value


__all__ = [
    "API_VERSION",
    "GRAPHQL_ENDPOINT",
    "MAX_COMMIT_SCAN",
    "MAX_LIVE_BLOB_BYTES",
    "REST_ROOT",
    "GithubApiPatchPort",
    "GithubReadError",
    "GithubTokenProvider",
    "HttpResponse",
    "HttpTransport",
    "UrllibHttpTransport",
]

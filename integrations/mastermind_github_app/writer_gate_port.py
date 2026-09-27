"""Disarmed-by-default, read-only Source Continuity port for the existing app.

The service supplies principal, target authority and installation identity.
Model-visible requests contain only an operation key. Canonical Source
Continuity still acquires facts and owns all writer-gate classification.
No CLI subprocess, ambient environment credential, endpoint selector, mutation,
retry, credential store, or additional lifecycle is introduced here.
"""
from __future__ import annotations

import asyncio
import dataclasses
from datetime import datetime, timezone
import json
import re
from typing import Callable, Protocol
from urllib.parse import parse_qsl, urlsplit

from control_plane.source_continuity import (
    SourceContinuityRefusal, WriterGateReceipt, WriterGateRequest,
    verify_technical_writer_gate, writer_gate_request_is_valid,
)
from scripts import source_continuity as source
from .github_port import API_VERSION, REST_ROOT, GithubTokenProvider, HttpResponse, UrllibHttpTransport
from .models import AuthenticatedPrincipal, PrincipalProvider

WRITER_GATE_SCOPE = "mastermind.github.writer_gate.read"
WRITER_GATE_TOOL_SPEC = {
    "name": "source_continuity_writer_gate",
    "description": "Read canonical writer-gate evidence for one owner-bound operation. Grants no release authority.",
    "inputSchema": {"type": "object", "properties": {"operation_key": {"type": "string",
        "minLength": 1, "maxLength": 192, "pattern": "^[A-Za-z0-9][A-Za-z0-9._:-]*$"}},
        "required": ["operation_key"], "additionalProperties": False},
    "annotations": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True},
}
_OPERATION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,191}$")
_SHA = re.compile(r"^[0-9a-f]{40}$")
_PRINCIPAL = re.compile(r"^[0-9a-f]{64}$")
_CODES = frozenset({"PRODUCTION_DISARMED", "INPUT_REFUSED", "AUTHENTICATION_REFUSED",
    "SCOPE_REFUSED", "TARGET_UNRESOLVED", "AUTHORITY_EXPIRED", "AUTHORITY_CHANGED",
    "CLOCK_UNAVAILABLE", "GITHUB_AUTH_UNAVAILABLE", "GITHUB_PERMISSION_DENIED",
    "GITHUB_RATE_LIMITED", "GITHUB_REDIRECT_REFUSED", "GITHUB_READ_FAILED",
    "GITHUB_SOURCE_MOVED", "GITHUB_CENSUS_INCOMPLETE", "SERVICE_UNAVAILABLE"})


class WriterGateServiceRefused(RuntimeError):
    """Closed error: never include provider bodies or credential-bearing errors."""
    def __init__(self, code: str):
        self.code = code if code in _CODES else "SERVICE_UNAVAILABLE"
        super().__init__(self.code)


@dataclasses.dataclass(frozen=True)
class WriterGateTarget:
    operation_key: str
    repository: str
    branch: str
    expected_head_sha: str
    accepted_integration_id: int | None
    authority_generation: str
    expires_at: int


class WriterGateAuthorityResolver(Protocol):
    async def resolve_writer_gate_target(
        self, operation_key: str, principal_digest: str,
    ) -> WriterGateTarget | None: ...


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError("duplicate field")
        result[key] = value
    return result


def _constant(_value):
    raise ValueError("non-finite number")


class GithubWriterGatePort:
    """Optional read companion; the existing three-tool patch catalog is unchanged."""
    def __init__(self, *, principals: PrincipalProvider, authority: WriterGateAuthorityResolver,
                 token_provider: GithubTokenProvider, clock: Callable[[], int],
                 read_transport: Callable[..., HttpResponse] = UrllibHttpTransport._request_sync,
                 production_armed: bool = False):
        if type(production_armed) is not bool or not callable(clock) or not callable(read_transport):
            raise ValueError("invalid writer-gate service configuration")
        self._principals = principals
        self._authority = authority
        self._tokens = token_provider
        self._clock = clock
        self._read_transport = read_transport
        self._armed = production_armed

    def _now(self) -> int:
        now = self._clock()
        if type(now) is not int or not 0 <= now <= 253402300799:
            raise WriterGateServiceRefused("CLOCK_UNAVAILABLE")
        return now

    @staticmethod
    def _request(target: WriterGateTarget, now: int) -> WriterGateRequest:
        return WriterGateRequest(target.operation_key, target.repository, target.branch,
            target.accepted_integration_id,
            datetime.fromtimestamp(now, timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"))

    async def _current(self, operation_key: str, not_before: int):
        principal = await self._principals.current_principal()
        if (type(principal) is not AuthenticatedPrincipal
                or type(principal.principal_digest) is not str
                or _PRINCIPAL.fullmatch(principal.principal_digest) is None):
            raise WriterGateServiceRefused("AUTHENTICATION_REFUSED")
        if type(principal.scopes) is not tuple or WRITER_GATE_SCOPE not in principal.scopes:
            raise WriterGateServiceRefused("SCOPE_REFUSED")
        target = await self._authority.resolve_writer_gate_target(operation_key, principal.principal_digest)
        now = self._now()
        if now < not_before:
            raise WriterGateServiceRefused("CLOCK_UNAVAILABLE")
        if (type(target) is not WriterGateTarget or target.operation_key != operation_key
                or type(target.expected_head_sha) is not str or not _SHA.fullmatch(target.expected_head_sha)
                or type(target.authority_generation) is not str or not target.authority_generation
                or len(target.authority_generation) > 128 or type(target.expires_at) is not int):
            raise WriterGateServiceRefused("TARGET_UNRESOLVED")
        if now >= target.expires_at:
            raise WriterGateServiceRefused("AUTHORITY_EXPIRED")
        if not writer_gate_request_is_valid(self._request(target, now)):
            raise WriterGateServiceRefused("TARGET_UNRESOLVED")
        if any(part in {".", ".."} for part in target.repository.split("/")):
            raise WriterGateServiceRefused("TARGET_UNRESOLVED")
        return principal, target, now

    async def observe_writer_gate(self, operation_key: str) -> dict[str, object]:
        if not self._armed:
            raise WriterGateServiceRefused("PRODUCTION_DISARMED")
        if type(operation_key) is not str or _OPERATION.fullmatch(operation_key) is None:
            raise WriterGateServiceRefused("INPUT_REFUSED")
        try:
            principal, target, checked_at = await self._current(operation_key, self._now())
            # This existing owner contract supplies a SERVICE installation token.
            # Its real provider must be separately provisioned and production-proven.
            token = await self._tokens.installation_token()
            if type(token) is not str or not token or "\r" in token or "\n" in token:
                raise WriterGateServiceRefused("GITHUB_AUTH_UNAVAILABLE")
            current_principal, current_target, checked_at = await self._current(operation_key, checked_at)
            if (current_principal, current_target) != (principal, target):
                raise WriterGateServiceRefused("AUTHORITY_CHANGED")
            result = await asyncio.to_thread(self._observe, target, token)
            current_principal, current_target, _ = await self._current(operation_key, checked_at)
            if (current_principal, current_target) != (principal, target):
                raise WriterGateServiceRefused("AUTHORITY_CHANGED")
            return result.to_dict()
        except WriterGateServiceRefused:
            raise
        except Exception:
            raise WriterGateServiceRefused("SERVICE_UNAVAILABLE") from None

    def _observe(self, target: WriterGateTarget, token: str):
        last_checked = self._now()
        request = self._request(target, last_checked)
        def get(url: str, *, token: str, timeout: float):
            nonlocal last_checked
            now = self._now()
            if now < last_checked:
                raise WriterGateServiceRefused("CLOCK_UNAVAILABLE")
            last_checked = now
            if now >= target.expires_at:
                raise WriterGateServiceRefused("AUTHORITY_EXPIRED")
            return self._get(target, url, token, min(timeout, target.expires_at - now))
        bounded_get = source._BoundedHTTPGet(get)
        try:
            # Reuse the canonical collector and its complete repeated-read fence.
            # No app-specific parser or alternate interpretation of GitHub rules.
            first = source._probe_writer_gate_facts(bounded_get, token, request)
            if isinstance(first, SourceContinuityRefusal):
                return first
            second = source._probe_writer_gate_facts(bounded_get, token, request)
            if isinstance(second, SourceContinuityRefusal):
                return second
            if second != first or first.branch_head_sha != target.expected_head_sha:
                raise WriterGateServiceRefused("GITHUB_SOURCE_MOVED")
            bounded_get.check()
            return verify_technical_writer_gate(self._request(target, self._now()), first)
        except WriterGateServiceRefused:
            raise
        except source._ReadBudgetExceeded:
            raise WriterGateServiceRefused("GITHUB_CENSUS_INCOMPLETE") from None
        except Exception:
            raise WriterGateServiceRefused("GITHUB_READ_FAILED") from None

    def _get(self, target: WriterGateTarget, url: str, token: str, timeout: float):
        fixed = {REST_ROOT + "/" + builder(target.repository, target.branch) for builder in (
            source._branch_endpoint, source._branch_protection_endpoint)}
        rule_pages = {REST_ROOT + "/" + source._branch_rules_endpoint(
            target.repository, target.branch, page): page
            for page in range(1, source._MAX_PAGES + 1)}
        fixed.update(rule_pages)
        repo_ruleset = REST_ROOT + "/repos/" + target.repository + "/rulesets/"
        org_ruleset = REST_ROOT + "/orgs/" + target.repository.split("/", 1)[0] + "/rulesets/"
        allowed_ruleset = False
        for prefix in (repo_ruleset, org_ruleset):
            if url.startswith(prefix):
                suffix = url[len(prefix):]
                allowed_ruleset = (suffix.isascii() and suffix.isdecimal()
                    and not suffix.startswith("0") and len(suffix) <= 10
                    and 0 < int(suffix) <= 2147483647)
                if allowed_ruleset:
                    break
        if url not in fixed and not allowed_ruleset:
            raise WriterGateServiceRefused("GITHUB_READ_FAILED")
        response = self._read_transport("GET", url, {
            "Authorization": "Bearer " + token, "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": API_VERSION, "User-Agent": "Mastermind-Writer-Gate/1"}, None, timeout)
        if (type(response) is not HttpResponse or type(response.status) is not int
                or type(response.body) is not bytes or len(response.body) > source._MAX_HTTP_BODY_BYTES):
            raise WriterGateServiceRefused("GITHUB_READ_FAILED")
        code = {401: "GITHUB_AUTH_UNAVAILABLE", 403: "GITHUB_PERMISSION_DENIED", 429: "GITHUB_RATE_LIMITED"}.get(response.status)
        if code:
            raise WriterGateServiceRefused(code)
        if 300 <= response.status < 400:
            raise WriterGateServiceRefused("GITHUB_REDIRECT_REFUSED")
        if response.status == 404:
            raise source._RemoteResourceMissing()
        if response.status != 200:
            raise WriterGateServiceRefused("GITHUB_READ_FAILED")
        if any(type(key) is not str or type(value) is not str
               for key, value in response.headers.items()):
            raise WriterGateServiceRefused("GITHUB_READ_FAILED")
        try:
            value = json.loads(response.body.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=_constant)
        except (UnicodeError, ValueError):
            raise WriterGateServiceRefused("GITHUB_READ_FAILED") from None
        links = [value for key, value in response.headers.items() if key.lower() == "link" and value.strip()]
        if url in rule_pages:
            if type(value) is not list or len(value) > source._PAGE_SIZE:
                raise WriterGateServiceRefused("GITHUB_CENSUS_INCOMPLETE")
            self._validate_rule_links(url, rule_pages[url], len(value), links)
        elif links:
            raise WriterGateServiceRefused("GITHUB_CENSUS_INCOMPLETE")
        return value

    @staticmethod
    def _validate_rule_links(url: str, page: int, count: int, links: list[str]) -> None:
        # Links are checked, NEVER followed. Canonical Source Continuity alone
        # generates page requests and decides completion under its read budgets.
        if not links:
            return
        if len(links) != 1 or len(links[0]) > 8192:
            raise WriterGateServiceRefused("GITHUB_CENSUS_INCOMPLETE")
        expected = urlsplit(url)
        seen = set()
        parts = links[0].split(",")
        if len(parts) > 4:
            raise WriterGateServiceRefused("GITHUB_CENSUS_INCOMPLETE")
        for part in parts:
            match = re.fullmatch(r'\s*<([^<>\s]+)>\s*;\s*rel="(next|prev|first|last)"\s*', part)
            if match is None or match[2] in seen:
                raise WriterGateServiceRefused("GITHUB_CENSUS_INCOMPLETE")
            seen.add(match[2])
            parsed = urlsplit(match[1])
            query = parse_qsl(parsed.query, keep_blank_values=True)
            values = dict(query)
            number = values.get("page", "")
            if ((parsed.scheme, parsed.netloc, parsed.path) != (expected.scheme, expected.netloc, expected.path)
                    or parsed.fragment or len(query) != 2 or set(values) != {"page", "per_page"}
                    or values["per_page"] != str(source._PAGE_SIZE)
                    or not number.isascii() or not number.isdecimal() or number.startswith("0")
                    or len(number) > 3 or not 1 <= int(number) <= source._MAX_PAGES):
                raise WriterGateServiceRefused("GITHUB_CENSUS_INCOMPLETE")
            linked = int(number)
            # Count-based collection probes after an exactly full final page.
            # Its empty response may truthfully name that preceding page last.
            terminal_probe_last = count == 0 and linked == page - 1
            if ((match[2] == "next" and (linked != page + 1 or count != source._PAGE_SIZE))
                    or (match[2] == "prev" and linked != page - 1)
                    or (match[2] == "first" and linked != 1)
                    or (match[2] == "last" and ((linked < page and not terminal_probe_last)
                        or (linked > page and count != source._PAGE_SIZE)))):
                raise WriterGateServiceRefused("GITHUB_CENSUS_INCOMPLETE")

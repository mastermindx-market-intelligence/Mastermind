"""GBL-4 Paperclip client — the ``GblAskStore`` protocol over issues+comments.

Lane GBL-4 of ``integrations/mmos/gbl/BUILD_PLAN.md``.  This module is ONLY
the persistence mapping documented in ``integrations/mmos/gbl/GBL2_NOTES.md``
("The Paperclip client interface"): one Paperclip issue per ask, opened and
assigned to the "Grok Bridge" bridge service agent; ask events as issue
comments; ``count_asks`` as a scan of that principal's issue rows.  ALL ask
law — admission, mints, duplicate classification, state chain, expiry,
budgets — stays in GBL-1/GBL-2; nothing is restated here.

Boundary law (ADDENDUM §1/§3, BUILD_PLAN GBL-4):

* the base URL is REQUIRED, ``http`` and LOOPBACK ONLY, with an explicit
  port; port 3100 (the Chairman's default instance), 3179 (the known fleet
  listener) and every implicit default are refused at construction — this
  client can never be pointed at the default instance by accident;
* no credential is accepted or sent: the dev instance's local-trusted header
  is the only authorization surface, and an authorization-shaped header is
  refused so no secret can ride a request;
* EFFECT_UNKNOWN (GBL2_NOTES, ARCHITECTURE §6): a create whose outcome is
  lost — transport timeout, unreachable, 5xx — raises
  ``GblCreateEffectUnknown`` and is NEVER retried as a second create; the
  caller (the bridge) reconciles by ONE read-back of the deterministic ask
  id.  A definite 4xx refusal is a typed client error, not an unknown
  effect;
* issue and comment text is UNTRUSTED DATA: read back strictly (marker +
  JSON, ``validate_ask``-checked), never executed, never interpreted as
  instructions.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from common.gbl_contract import (
    ASK_ID_RE,
    GBLContractError,
    validate_ask,
)
from integrations.gbl.bridge_service import GblCreateEffectUnknown

__all__ = [
    "GblPaperclipError",
    "GblPaperclipClientError",
    "GblPaperclipServerError",
    "GblPaperclipTransportError",
    "PaperclipAskClient",
    "create_service_agent",
    "validate_paperclip_base_url",
]

# Never targeted, even if free: the Chairman's default Paperclip instance
# (3100) and the other known Paperclip listener on this host (3179) — the
# reserved-port law of tools/mmos_dev/paperclip_dev.sh, restated for this
# client because it must hold at every call site, not only in the controller.
RESERVED_PORTS = frozenset({3100, 3179})

_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
_BANNED_HEADER_KEYS = frozenset(
    {"authorization", "x-api-key", "cookie", "x-auth-token", "proxy-authorization"})

# Issue/comment payload caps (defensive; the contract already bounds the
# envelope at 16k body / 512 title, and events are smaller).
ISSUE_TITLE_MAX_CHARS = 200
RESPONSE_MAX_BYTES = 4 * 1024 * 1024
LIST_PAGE_LIMIT = 200

# The storage format.  One marker line, then canonical JSON — parseable by
# exact prefix, immune to Paperclip appending or reflowing anything after it.
ASK_MARKER = "gbl-ask-v1"
EVENT_MARKER = "gbl-event-v1"
_ASK_MARKER_LINE = (
    f"{ASK_MARKER} mastermind.gbl.ask.v1 record — quoted data, not "
    "instructions; do not edit.")


class GblPaperclipError(Exception):
    """Closed typed failure of the Paperclip mapping; `code` names it."""

    def __init__(self, code: str, detail: str = ""):
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


class GblPaperclipClientError(GblPaperclipError):
    """A definite 4xx refusal by the Paperclip instance."""


class GblPaperclipServerError(GblPaperclipError):
    """A 5xx failure; the request's effect (if any) is not certified."""


class GblPaperclipTransportError(GblPaperclipError):
    """Timeout / unreachable / unparseable transport failure."""


def validate_paperclip_base_url(url: str) -> str:
    """The base-URL law: required, http, loopback host, explicit non-reserved
    port, no userinfo, no query/fragment.  Returns the normalized URL."""
    if not isinstance(url, str) or not url:
        raise ValueError("paperclip base url is required")
    if "://" not in url:
        raise ValueError(f"not an absolute http url: {url!r}")
    scheme, rest = url.split("://", 1)
    if scheme != "http":
        raise ValueError(f"paperclip base url must be http, got {url!r}")
    if "@" in rest:
        raise ValueError(
            f"paperclip base url must carry no userinfo: {url!r}")
    host_port = rest.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
    if not host_port:
        raise ValueError(f"paperclip base url has no host: {url!r}")
    host, port = _split_host_port(host_port)
    if host.lower() not in _LOOPBACK_HOSTS:
        raise ValueError(
            f"paperclip base url must be loopback, got host {host!r}")
    if port is None:
        raise ValueError(
            "paperclip base url must carry an explicit port "
            f"(no implicit default): {url!r}")
    if port in RESERVED_PORTS:
        raise ValueError(
            f"paperclip base url port {port} is reserved and never targeted")
    if "?" in url or "#" in url:
        raise ValueError("paperclip base url carries no query or fragment")
    return url.rstrip("/")


def _split_host_port(host_port: str) -> tuple[str, int | None]:
    if host_port.startswith("["):                      # [::1]:3191
        host, _, port = host_port[1:].partition("]")
        return host, (int(port[1:]) if port.startswith(":") else None)
    host, sep, port = host_port.partition(":")
    return host, (int(port) if sep and port.isdigit() else None)


def _canonical(value: Mapping[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False)


def _parse_ts(value: Any) -> datetime | None:
    """Parse a Paperclip timestamp (Z- or offset-suffixed ISO) to an aware
    UTC datetime; None when unparseable."""
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


class PaperclipAskClient:
    """``GblAskStore`` (bridge_service.py:94) over Paperclip issues+comments.

    Constructed with the resolved dev-instance facts (base URL, company id,
    service-agent id) — ``from_spec`` reads them from a GBL-4 roster spec
    file.  One urllib request per call; no retries anywhere (the EFFECT_UNKNOWN
    law: an unproven create is reported, never repeated).
    """

    def __init__(self, base_url: str, company_id: str,
                 service_agent_id: str, *,
                 headers: Mapping[str, str] | None = None,
                 timeout_seconds: float = 15.0):
        self._base = validate_paperclip_base_url(base_url)
        for name, value in (("company_id", company_id),
                            ("service_agent_id", service_agent_id)):
            if not isinstance(value, str) or not value:
                raise ValueError(f"{name} is required")
        self._company_id = company_id
        self._agent_id = service_agent_id
        supplied = dict(headers or {"x-instance-role": "local_trusted"})
        for key in supplied:
            if key.lower() in _BANNED_HEADER_KEYS:
                raise ValueError(
                    f"credential-shaped header {key!r} refused — no secret "
                    "rides a Paperclip request")
        self._headers = supplied
        if not 0.1 <= float(timeout_seconds) <= 120:
            raise ValueError("timeout_seconds out of range")
        self._timeout = float(timeout_seconds)
        self._issue_ids: dict[str, str] = {}     # ask_id -> issue_id cache

    # -- construction from a roster spec --------------------------------------

    @classmethod
    def from_spec(cls, path: str | Path) -> "PaperclipAskClient":
        """Build the client from a GBL-4 dev roster spec JSON file (the
        ``paperclip`` block: base_url, company_id, agent_id)."""
        try:
            spec = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ValueError(f"cannot read spec {path}: {exc}") from None
        block = spec.get("paperclip") if isinstance(spec, dict) else None
        if not isinstance(block, dict):
            raise ValueError(f"spec {path} has no paperclip block")
        for field in ("base_url", "company_id", "agent_id"):
            if not block.get(field):
                raise ValueError(f"spec {path} paperclip.{field} is required")
        return cls(block["base_url"], block["company_id"], block["agent_id"])

    # -- the GblAskStore interface --------------------------------------------

    def create_ask(self, ask: Mapping[str, Any]) -> None:
        """Persist the validated ask envelope as ONE issue, assigned to the
        bridge service agent (ADDENDUM §3: the issue IS the record).  A lost
        outcome raises ``GblCreateEffectUnknown`` — never retried here."""
        envelope = validate_ask(ask)      # re-validated; deep copy
        payload = {
            "title": _issue_title(envelope),
            "description": f"{_ASK_MARKER_LINE}\n{_canonical(envelope)}",
            "assigneeAgentId": self._agent_id,
            "status": "todo",
        }
        try:
            row = self._request("POST",
                                f"/api/companies/{self._company_id}/issues",
                                payload)
        except (GblPaperclipTransportError, GblPaperclipServerError) as exc:
            # The create began but its outcome is not certified: unknown
            # effect.  The bridge reconciles by ONE read-back of the
            # deterministic ask id; there is never a second create.
            raise GblCreateEffectUnknown(
                f"issue create outcome unknown ({exc.code})") from None
        issue_id = row.get("id") if isinstance(row, dict) else None
        if not issue_id:
            raise GblCreateEffectUnknown(
                "issue create reply carried no issue id")
        self._issue_ids[envelope["ask_id"]] = str(issue_id)

    def read_ask(self, ask_id: str) -> dict[str, Any] | None:
        """The stored record for the ask id, or None.  Found by the
        deterministic id even when the create reply was lost (the only create
        reconciliation path): direct issue read when known, else a scan of
        the company's issue rows for the ask-id marker."""
        issue = self._issue_for(ask_id)
        if issue is None:
            return None
        envelope = _parse_ask_envelope(issue.get("description"))
        if envelope is None or envelope.get("ask_id") != ask_id:
            return None
        try:
            record = dict(validate_ask(envelope))
        except GBLContractError as exc:
            raise GblPaperclipError(
                "RECORD_INVALID",
                f"issue {issue.get('id')} failed contract validation: "
                f"{exc.code}") from None
        record["events"] = self._events(issue.get("id"))
        return record

    def append_ask_event(self, ask_id: str,
                         event: Mapping[str, Any]) -> None:
        """Append ONE comment carrying the event; idempotent by content (a
        redelivered identical event does not duplicate the comment)."""
        issue = self._issue_for(ask_id)
        if issue is None:
            raise GblPaperclipError("ASK_ISSUE_NOT_FOUND", ask_id)
        body = f"{EVENT_MARKER} {_canonical(dict(event))}"
        for row in self._comment_rows(issue["id"]):
            if str(row.get("body") or "") == body:
                return                      # already appended; no duplicate
        self._request("POST", f"/api/issues/{issue['id']}/comments",
                      {"clientRequestId": str(uuid.uuid4()), "body": body})

    def count_asks(self, principal: str, since_iso: str) -> int:
        """That principal's asks created at or after ``since_iso`` (UTC ISO),
        for the hourly ceilings.  A row whose timestamp cannot be parsed is
        counted: failing open would under-count toward a rate ceiling."""
        since = _parse_ts(since_iso)
        if since is None:
            raise GblPaperclipError("INVALID_SINCE", since_iso)
        total = 0
        for issue in self._list_issues():
            envelope = _parse_ask_envelope(issue.get("description"))
            if envelope is None or envelope.get("principal") != principal:
                continue
            created = _parse_ts(issue.get("createdAt"))
            if created is None or created >= since:
                total += 1
        return total

    # -- issue resolution ------------------------------------------------------

    def _issue_for(self, ask_id: str) -> dict[str, Any] | None:
        """The live issue row for an ask id: cached id when it still reads,
        else one scan of the company's issues for the marker."""
        if not ASK_ID_RE.fullmatch(ask_id or ""):
            return None
        issue_id = self._issue_ids.get(ask_id)
        if issue_id is not None:
            try:
                return self._request("GET", f"/api/issues/{issue_id}")
            except GblPaperclipClientError as exc:
                if exc.code != "HTTP_404":
                    raise
        for issue in self._list_issues():
            if ask_id in str(issue.get("title") or ""):
                self._issue_ids[ask_id] = str(issue.get("id"))
                return issue
        return None

    def _list_issues(self) -> list[dict[str, Any]]:
        rows = self._request(
            "GET", f"/api/companies/{self._company_id}"
                   f"/issues?limit={LIST_PAGE_LIMIT}")
        if isinstance(rows, dict):
            rows = (rows.get("issues") or rows.get("rows") or [])
        if not isinstance(rows, list):
            raise GblPaperclipTransportError("UNPARSEABLE_ISSUE_LIST")
        return [row for row in rows if isinstance(row, dict)]

    def _comment_rows(self, issue_id: str) -> list[dict[str, Any]]:
        rows = self._request("GET", f"/api/issues/{issue_id}/comments")
        if isinstance(rows, dict):
            rows = rows.get("comments") or rows.get("rows") or []
        if not isinstance(rows, list):
            raise GblPaperclipTransportError("UNPARSEABLE_COMMENTS")

        def stamp(row: dict[str, Any]) -> tuple[int, str]:
            parsed = _parse_ts(row.get("createdAt"))
            return (parsed.isoformat() if parsed else "", str(row.get("id")))

        # The API lists newest first; events replay oldest first.
        return sorted((row for row in rows if isinstance(row, dict)),
                      key=stamp)

    def _events(self, issue_id: str) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        for row in self._comment_rows(issue_id):
            event = _parse_event_body(str(row.get("body") or ""))
            if event is not None:
                events.append(event)
        return events

    # -- one request, no retries ------------------------------------------------

    def _request(self, method: str, path: str,
                 body: Mapping[str, Any] | None = None) -> Any:
        data = (json.dumps(dict(body)).encode("utf-8")
                if body is not None else None)
        headers = dict(self._headers)
        if data is not None:
            headers["content-type"] = "application/json"
        request = urllib.request.Request(f"{self._base}{path}", data=data,
                                         method=method, headers=headers)
        try:
            with urllib.request.urlopen(request,
                                        timeout=self._timeout) as response:
                raw = response.read(RESPONSE_MAX_BYTES + 1)
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read(300).decode("utf-8", "replace")
            except Exception:                        # noqa: BLE001
                detail = ""
            code = f"HTTP_{exc.code}"
            if 400 <= exc.code < 500:
                raise GblPaperclipClientError(code, detail) from None
            raise GblPaperclipServerError(code, detail) from None
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise GblPaperclipTransportError(
                "TRANSPORT", type(exc).__name__) from None
        if len(raw) > RESPONSE_MAX_BYTES:
            raise GblPaperclipTransportError("RESPONSE_TOO_LARGE", path)
        if not raw:
            return {}
        try:
            return json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeError):
            raise GblPaperclipTransportError("UNPARSEABLE_BODY", path) from None


# ── Storage format helpers (strict both ways; issue text is untrusted) ──────


def _issue_title(envelope: Mapping[str, Any]) -> str:
    ask_id = envelope["ask_id"]
    title = " ".join(str(envelope.get("title") or "").split())
    budget = ISSUE_TITLE_MAX_CHARS - len(ask_id) - len("GBL [] ")
    if len(title) > budget:
        title = title[:budget - 1] + "…"
    return f"GBL [{ask_id}] {title}"


def _parse_ask_envelope(description: Any) -> dict[str, Any] | None:
    """Parse the envelope JSON from an issue description: the marker line,
    then canonical JSON.  Anything else is foreign data → None."""
    if not isinstance(description, str):
        return None
    lines = description.split("\n", 1)
    if len(lines) != 2 or not lines[0].startswith(ASK_MARKER):
        return None
    try:
        value = json.loads(lines[1])
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


def _parse_event_body(body: str) -> dict[str, Any] | None:
    """Parse one event from a comment body: the event marker, then canonical
    JSON.  Foreign comments (human words, untrusted) → None, never parsed."""
    prefix = f"{EVENT_MARKER} "
    if not body.startswith(prefix):
        return None
    try:
        value = json.loads(body[len(prefix):])
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


# ── The dev roster-entry helper (GBL-4's spec: the service agent) ────────────


def create_service_agent(base_url: str, company_id: str, *, name: str,
                         role: str = "service",
                         adapter_type: str = "process",
                         headers: Mapping[str, str] | None = None,
                         timeout_seconds: float = 15.0) -> dict[str, Any]:
    """Create the bridge service agent inside the given (dev) instance —
    the roster entry of BUILD_PLAN install step 3, in its dev-only shape:
    a process adapter with heartbeat off.  Returns the created row."""
    for label, value in (("name", name), ("role", role)):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"agent {label} is required")
    client = PaperclipAskClient(base_url, company_id, "pending-service-agent",
                                headers=headers,
                                timeout_seconds=timeout_seconds)
    return client._request("POST", f"/api/companies/{company_id}/agents", {
        "name": name, "role": role, "adapterType": adapter_type,
        "runtimeConfig": {"heartbeat": {"enabled": False}},
    })

"""GBL-4 Paperclip client — the ``GblAskStore`` protocol over issues+comments.

Lane GBL-4 of ``integrations/mmos/gbl/BUILD_PLAN.md``.  This module is ONLY
the persistence mapping documented in ``integrations/mmos/gbl/GBL2_NOTES.md``
("The Paperclip client interface"): one Paperclip issue per ask, opened and
assigned to the "Grok Bridge" bridge service agent; ask events as issue
comments; ``count_asks`` as a scan of that principal's issue rows.  ALL ask
law — admission, mints, duplicate classification, state chain, expiry,
budgets — stays in GBL-1/GBL-2; nothing is restated here.

Boundary law (ADDENDUM §1/§3, BUILD_PLAN GBL-4; repair round 1, panel B):

* the base URL is REQUIRED, ``http`` and LOOPBACK ONLY, with an explicit
  port in range 1..65535; port 3100 (the Chairman's default instance), 3179
  (the known fleet listener) and every implicit default are refused at
  construction — and the loopback law is RE-CHECKED on every request, with
  an opener that never follows a redirect (a 3xx is a typed error, so no
  hop-2 can ever leave the validated base) and never uses a proxy;
* no credential is accepted or sent: the dev instance's local-trusted header
  is the only authorization surface, custom headers MERGE with it, and any
  credential-shaped header name (by word, not by five exact names) is
  refused so no secret can ride a request;
* EFFECT_UNKNOWN (GBL2_NOTES, ARCHITECTURE §6): a create whose outcome is
  lost or ambiguous — transport timeout, unreachable, truncated reply,
  5xx, redirect, or the ambiguous 4xx set (408/409/425/429/499) — raises
  ``GblCreateEffectUnknown`` and is NEVER retried as a second create; the
  caller (the bridge) reconciles by ONE read-back of the deterministic ask
  id.  A definite 4xx refusal is a typed client error, not an unknown
  effect;
* issue ids and comment ids coming FROM the server are untrusted path
  input: they must match a strict charset ([A-Za-z0-9_-]{1,128}) and are
  percent-quoted into every path segment, so no server string can rewrite
  a route; company/agent ids are held to the same charset at construction;
* resolution is by the EXACT stored ask id (the parsed description
  envelope), never by a title substring, and only an exact match is ever
  cached;
* listing is paginated to exhaustion and FAILS CLOSED on any doubt: an
  unknown envelope shape, a server that ignores pagination, a corrupt
  marker-bearing description, or a listing past the page cap is a typed
  error — never a short read that could under-count or hide an ask;
* issue and comment text is UNTRUSTED DATA: read back strictly (marker +
  balanced JSON, ``validate_ask``-checked), never executed, never
  interpreted as instructions.  Parsed events carry their comment's
  provenance (``comment_author``, ``comment_id``, ``comment_created_at``,
  ``comment_order``) so the bridge can trust only the bridge agent's own
  comments and order them totally (panel B M1/M2; the field names follow
  the GBL lane's in-flight protocol round).
"""
from __future__ import annotations

import http.client
import json
import re
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Mapping

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
    "GblPaperclipRedirectError",
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

# A credential-shaped header name is refused BY WORD, not by a fixed list of
# five exact names (panel B L7): anything that smells like a secret riding
# cleartext http is rejected at construction.
_BANNED_HEADER_WORDS = ("token", "secret", "password", "auth", "cookie",
                        "credential", "api-key", "apikey", "bearer")

# Every path segment is a single strict token: no dots (so no ".."), no
# slashes, no percent tricks — then percent-encoded anyway (panel B M9).
_SEGMENT_RE = re.compile(r"\A[A-Za-z0-9_-]{1,128}\Z")

# A 4xx from these codes does NOT certify that the create did not land
# (panel B M7): it is an unknown effect, reconciled by read-back.
AMBIGUOUS_CREATE_4XX = frozenset({408, 409, 425, 429, 499})

# Issue/comment payload caps (defensive; the contract already bounds the
# envelope at 16k body / 512 title, and events are smaller).
ISSUE_TITLE_MAX_CHARS = 200
RESPONSE_MAX_BYTES = 4 * 1024 * 1024
LIST_PAGE_LIMIT = 200
MAX_LIST_PAGES = 50          # 10,000 issues; past this, fail closed

# The storage format.  One marker, then canonical JSON — found anywhere in
# the text (appended or reflowed prose is tolerated; panel B H4).
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
        self.status: int | None = None       # HTTP status, when there was one


class GblPaperclipClientError(GblPaperclipError):
    """A definite 4xx refusal by the Paperclip instance."""


class GblPaperclipServerError(GblPaperclipError):
    """A 5xx (or redirect) failure; the request's effect is not certified."""


class GblPaperclipRedirectError(GblPaperclipServerError):
    """A 3xx the client refused to follow (M6); the effect is not certified."""


class GblPaperclipTransportError(GblPaperclipError):
    """Timeout / unreachable / unparseable transport failure."""


def validate_paperclip_base_url(url: str) -> str:
    """The base-URL law: required, http, loopback host, explicit port in
    range 1..65535 and not reserved, no userinfo, no query/fragment.
    Returns the normalized URL."""
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
    if not 1 <= port <= 65535:
        raise ValueError(
            f"paperclip base url port {port} is out of range 1..65535")
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


def _quote_segment(value: Any, *, what: str, typed: bool) -> str:
    """One path segment: strict charset first, then percent-encoding.  A
    construction-time id raises ValueError; a server-supplied id raises the
    typed ``INVALID_ISSUE_ID`` (fail closed — it is never spliced raw)."""
    if not isinstance(value, str) or not _SEGMENT_RE.fullmatch(value):
        if typed:
            raise GblPaperclipError("INVALID_ISSUE_ID",
                                    f"{what} {str(value)[:60]!r} refused")
        raise ValueError(f"{what} must match [A-Za-z0-9_-]{{1,128}}")
    return urllib.parse.quote(value, safe="")


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """A 3xx is never followed (panel B M6): urllib turns it into an
    ``HTTPError`` our caller maps to the typed redirect error."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_OPENER = urllib.request.build_opener(
    _NoRedirectHandler, urllib.request.ProxyHandler({}))


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
        self._company_seg = _quote_segment(company_id, what="company_id",
                                           typed=False)
        self._agent_id = _quote_segment(service_agent_id,
                                        what="service_agent_id", typed=False)
        supplied = dict(headers or {})
        merged = {"x-instance-role": "local_trusted"}
        for key in supplied:
            if any(word in key.lower() for word in _BANNED_HEADER_WORDS):
                raise ValueError(
                    f"credential-shaped header {key!r} refused — no secret "
                    "rides a Paperclip request")
            merged[key] = supplied[key]
        self._headers = merged
        if not 0.1 <= float(timeout_seconds) <= 120:
            raise ValueError("timeout_seconds out of range")
        self._timeout = float(timeout_seconds)
        split = urllib.parse.urlsplit(self._base)
        self._host = split.hostname or ""
        self._port = split.port
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
        or ambiguous outcome raises ``GblCreateEffectUnknown`` — never
        retried here."""
        envelope = validate_ask(ask)      # re-validated; deep copy
        payload = {
            "title": _issue_title(envelope),
            "description": f"{_ASK_MARKER_LINE}\n{_canonical(envelope)}",
            "assigneeAgentId": self._agent_id,
            "status": "todo",
        }
        try:
            row = self._request("POST",
                                f"/api/companies/{self._company_seg}/issues",
                                payload)
        except GblPaperclipClientError as exc:
            if exc.status in AMBIGUOUS_CREATE_4XX:
                # 408/409/425/429/499 do not certify "not created" (M7):
                # the outcome is unknown and reconciled by read-back.
                raise GblCreateEffectUnknown(
                    f"issue create outcome ambiguous ({exc.code})") from None
            raise                                  # a definite refusal
        except (GblPaperclipTransportError, GblPaperclipServerError) as exc:
            # The create began but its outcome is not certified (transport,
            # 5xx, redirect, truncated reply): unknown effect.  The bridge
            # reconciles by ONE read-back of the deterministic ask id; there
            # is never a second create.
            raise GblCreateEffectUnknown(
                f"issue create outcome unknown ({exc.code})") from None
        issue_id = row.get("id") if isinstance(row, dict) else None
        try:
            self._issue_ids[envelope["ask_id"]] = self._issue_seg(issue_id)
        except GblPaperclipError:
            # The create may have landed; the reply's id is unusable (M9).
            raise GblCreateEffectUnknown(
                "issue create reply carried no usable issue id") from None

    def read_ask(self, ask_id: str) -> dict[str, Any] | None:
        """The stored record for the ask id, or None.  Found by the
        deterministic id even when the create reply was lost (the only create
        reconciliation path): a direct issue read when known, else a
        paginated scan for the record whose STORED envelope carries exactly
        that id."""
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
        record["events"] = self._events(self._issue_seg(issue.get("id")))
        return record

    def append_ask_event(self, ask_id: str,
                         event: Mapping[str, Any]) -> None:
        """Append ONE comment carrying the event; idempotent by content (a
        redelivered identical event does not duplicate the comment)."""
        issue = self._issue_for(ask_id)
        if issue is None:
            raise GblPaperclipError("ASK_ISSUE_NOT_FOUND", ask_id)
        seg = self._issue_seg(issue.get("id"))
        body = f"{EVENT_MARKER} {_canonical(dict(event))}"
        for row in self._comment_rows(seg):
            if str(row.get("body") or "") == body:
                return                      # already appended; no duplicate
        self._request("POST", f"/api/issues/{seg}/comments",
                      {"clientRequestId": str(uuid.uuid4()), "body": body})

    def count_asks(self, principal: str, since_iso: str) -> int:
        """That principal's asks created at or after ``since_iso`` (UTC ISO),
        for the hourly ceilings.  FAILS CLOSED on any doubt (panel B H2/M5):
        an unknown envelope shape, an unsupported pagination, a corrupt
        marker-bearing record or a listing past the cap raises — it is never
        read as a short count.  A row whose timestamp cannot be parsed is
        counted: failing open there would under-count toward a ceiling."""
        since = _parse_ts(since_iso)
        if since is None:
            raise GblPaperclipError("INVALID_SINCE", since_iso)
        total = 0
        for issue in self._iter_issues():
            envelope = _parse_ask_envelope(issue.get("description"))
            if envelope is None or envelope.get("principal") != principal:
                continue
            created = _parse_ts(issue.get("createdAt"))
            if created is None or created >= since:
                total += 1
        return total

    # -- issue resolution (exact key only; panel B M3) -------------------------

    def _issue_seg(self, value: Any) -> str:
        return _quote_segment(value, what="issue_id", typed=True)

    def _issue_for(self, ask_id: str) -> dict[str, Any] | None:
        """The issue whose STORED envelope carries exactly this ask id.
        The parsed description envelope is the only exact key (stronger than
        an exact title token); a title substring never resolves anything,
        and only an exact match is ever cached."""
        if not ASK_ID_RE.fullmatch(ask_id or ""):
            return None
        issue_id = self._issue_ids.get(ask_id)
        if issue_id is not None:
            try:
                row = self._request("GET", f"/api/issues/{issue_id}")
            except GblPaperclipClientError as exc:
                if exc.code != "HTTP_404":
                    raise
            else:
                if self._envelope_is(row, ask_id):
                    return row
            self._issue_ids.pop(ask_id, None)   # stale; resolve again
        for row in self._iter_issues():
            if self._envelope_is(row, ask_id):
                self._issue_ids[ask_id] = str(row["id"])
                return row
        return None

    def _envelope_is(self, row: Mapping[str, Any], ask_id: str) -> bool:
        envelope = _parse_ask_envelope(row.get("description"))
        return envelope is not None and envelope.get("ask_id") == ask_id

    def _iter_issues(self) -> Iterator[dict[str, Any]]:
        """Every company issue row, paginated to exhaustion (panel B H2).
        Fail closed: an unknown envelope shape, junk rows, an unusable id,
        a server that ignores pagination (the same page head twice), or a
        listing past the page cap is a typed error — never a short read."""
        seen: set[str] = set()
        offset = 0
        for _page in range(MAX_LIST_PAGES):
            query = urllib.parse.urlencode(
                {"limit": LIST_PAGE_LIMIT, "offset": offset})
            rows = self._request(
                "GET", f"/api/companies/{self._company_seg}/issues?{query}")
            if isinstance(rows, dict):
                if isinstance(rows.get("issues"), list):
                    rows = rows["issues"]
                elif isinstance(rows.get("rows"), list):
                    rows = rows["rows"]
                else:
                    raise GblPaperclipTransportError("UNPARSEABLE_ISSUE_LIST")
            if not isinstance(rows, list):
                raise GblPaperclipTransportError("UNPARSEABLE_ISSUE_LIST")
            page: list[dict[str, Any]] = []
            for row in rows:
                if not isinstance(row, dict):
                    raise GblPaperclipTransportError("UNPARSEABLE_ISSUE_LIST")
                page.append(row)          # ids validated as used, below
            if page:
                head = str(page[0].get("id"))
                if head in seen:
                    # offset returned the same page head: the server does
                    # not paginate; a partial scan would silently hide asks.
                    raise GblPaperclipError("PAGINATION_UNSUPPORTED",
                                            f"offset {offset} replayed the "
                                            f"page head {head}")
                for row in page:
                    issue_id = str(row.get("id"))
                    if issue_id not in seen:
                        self._issue_seg(issue_id)   # charset gate (M9)
                        seen.add(issue_id)
                        yield row
            if len(page) < LIST_PAGE_LIMIT:
                return
            offset += len(page)
        raise GblPaperclipError(
            "LIST_TOO_LARGE",
            f"exceeded {MAX_LIST_PAGES} pages of {LIST_PAGE_LIMIT}")

    def _comment_rows(self, issue_seg: str) -> list[dict[str, Any]]:
        """The issue's comment rows in stable server order (oldest first).
        Fail closed: an unknown envelope shape or junk row is a typed
        error, never an empty list (panel B M4)."""
        rows = self._request("GET", f"/api/issues/{issue_seg}/comments")
        if isinstance(rows, dict):
            if isinstance(rows.get("comments"), list):
                rows = rows["comments"]
            elif isinstance(rows.get("rows"), list):
                rows = rows["rows"]
            else:
                raise GblPaperclipTransportError("UNPARSEABLE_COMMENTS")
        if not isinstance(rows, list):
            raise GblPaperclipTransportError("UNPARSEABLE_COMMENTS")
        for row in rows:
            if not isinstance(row, dict):
                raise GblPaperclipTransportError("UNPARSEABLE_COMMENTS")

        def order(row: Mapping[str, Any]) -> tuple[str, str]:
            stamp = _parse_ts(row.get("createdAt"))
            return (stamp.isoformat() if stamp else "",
                    str(row.get("id") or ""))

        # The API lists newest first; events replay oldest first, in the
        # total server order (createdAt, then id) the bridge also sees.
        return sorted(rows, key=order)

    def _events(self, issue_seg: str) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        for row in self._comment_rows(issue_seg):
            event = _parse_event_body(str(row.get("body") or ""))
            if event is not None:
                _add_comment_provenance(event, row)
                events.append(event)
        return events

    # -- one request, no retries, no redirects, the URL law every time ---------

    def _checked_url(self, path: str) -> str:
        """The request URL, with the loopback law re-verified (panel B M6):
        scheme, host and port must still be the validated base's; the path
        is a single rooted, pre-quoted string that cannot escape."""
        if not path.startswith("/") or "//" in path:
            raise GblPaperclipTransportError("PATH_INVALID", path[:120])
        url = f"{self._base}{path}"
        split = urllib.parse.urlsplit(url)
        if (split.scheme != "http" or split.username or split.password
                or split.fragment or not split.hostname
                or split.hostname.lower() not in _LOOPBACK_HOSTS
                or split.port != self._port):
            raise GblPaperclipTransportError("URL_LAW_VIOLATION",
                                             url[:200])
        return url

    def _request(self, method: str, path: str,
                 body: Mapping[str, Any] | None = None) -> Any:
        data = (json.dumps(dict(body)).encode("utf-8")
                if body is not None else None)
        headers = dict(self._headers)
        if data is not None:
            headers["content-type"] = "application/json"
        request = urllib.request.Request(self._checked_url(path), data=data,
                                         method=method, headers=headers)
        try:
            with _OPENER.open(request, timeout=self._timeout) as response:
                raw = response.read(RESPONSE_MAX_BYTES + 1)
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read(300).decode("utf-8", "replace")
            except Exception:                        # noqa: BLE001
                detail = ""
            error: GblPaperclipError
            if 300 <= exc.code < 400:
                location = ""
                try:
                    location = (exc.headers.get("Location") or "")[:200]
                except Exception:                    # noqa: BLE001
                    location = ""
                error = GblPaperclipRedirectError(
                    f"HTTP_{exc.code}", f"redirect refused: {location}")
            elif 400 <= exc.code < 500:
                error = GblPaperclipClientError(f"HTTP_{exc.code}", detail)
            else:
                error = GblPaperclipServerError(f"HTTP_{exc.code}", detail)
            error.status = exc.code
            raise error from None
        except (urllib.error.URLError, TimeoutError, OSError,
                http.client.HTTPException) as exc:
            # http.client.HTTPException (IncompleteRead, BadStatusLine, …)
            # is NOT an OSError — it must land here, not escape raw (M8).
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
    """The ask envelope embedded ANYWHERE in an issue description: the
    ``gbl-ask-v1`` marker, then the first balanced JSON object after it —
    appended or reflowed text around it is tolerated (panel B H4).  No
    marker → None (a foreign issue).  A marker whose payload cannot be
    parsed is NOT read as absence: that raises ``RECORD_INVALID``, because
    "absent" would mint a duplicate create."""
    if not isinstance(description, str):
        return None
    at = description.find(ASK_MARKER)
    if at < 0:
        return None
    brace = description.find("{", at + len(ASK_MARKER))
    if brace < 0:
        raise GblPaperclipError("RECORD_INVALID",
                                "marker without a JSON payload")
    end = _json_object_end(description, brace)
    if end < 0:
        raise GblPaperclipError("RECORD_INVALID", "unterminated JSON payload")
    try:
        value = json.loads(description[brace:end + 1])
    except ValueError:
        raise GblPaperclipError("RECORD_INVALID",
                                "payload is not JSON") from None
    if not isinstance(value, dict):
        raise GblPaperclipError("RECORD_INVALID", "payload is not an object")
    return value


def _json_object_end(text: str, start: int) -> int:
    """Index of the ``}`` closing the object opened at ``start`` (string- and
    escape-aware brace matching); -1 when unterminated."""
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return index
    return -1


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


# ── Comment provenance (panel B M1/M2 client side; GBL lane consumes) ───────


_AUTHOR_KEYS = ("authorAgentId", "agentId", "authorId", "createdBy", "author")


def _add_comment_provenance(event: dict[str, Any],
                            row: Mapping[str, Any]) -> None:
    """Attach the comment's author and a stable total order key to the
    parsed event, so the bridge can trust only the bridge service agent's
    own comments and order events totally even on same-millisecond ties.
    The names follow the GBL lane's in-flight protocol round."""
    author = None
    for key in _AUTHOR_KEYS:
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            author = value
            break
    created = _parse_ts(row.get("createdAt"))
    event["comment_id"] = str(row.get("id") or "")
    event["comment_author"] = author
    event["comment_created_at"] = created.isoformat() if created else None
    event["comment_order"] = f"{event['comment_created_at'] or ''}|" \
                             f"{event['comment_id']}"


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
    return client._request(
        "POST", f"/api/companies/{client._company_seg}/agents", {
            "name": name, "role": role, "adapterType": adapter_type,
            "runtimeConfig": {"heartbeat": {"enabled": False}},
        })

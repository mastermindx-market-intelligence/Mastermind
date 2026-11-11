"""``paperclip_task`` result-return transport (MMOS lane T4b, build item 2).

The Executive seam (:mod:`control_plane.execution_return_wiring`) projects one
``mastermind.execution_return/v1`` record per sealed attempt and routes it
through a :class:`control_plane.result_delivery.ResultDeliveryRegistry`.  This
module is the transport registered for ``PAPERCLIP_ORIGIN_KIND``: it writes the
verified result back onto the Paperclip task the coding job came from — one
comment a person reads in the task thread, and one issue document carrying the
full payload.

Laws:

* **Dev-loopback only.**  Construction refuses any base URL whose host is not
  loopback (``127.0.0.1``, ``localhost``, ``::1``).  The dev instance's
  local-trusted surface is the only writer this transport is allowed to hold;
  a production credential is a Paperclip-side decision, not a default here.
* **Stdlib only.**  ``urllib`` / ``json`` / ``http`` — a ``control_plane``
  module never imports the integrations package or a third-party client.
* **Honest receipts, never a guess.**  Every failure path returns a REFUSED
  receipt with the exact reason; a network failure mid-flight is never
  reported as DELIVERED.  No exception escapes ``deliver``.
* **Exactly-once posting, two guards.**  (a) Before posting, the issue's
  comments are read and a body already carrying the dedupe marker
  ``paperclip-return-attempt: <attempt_id>`` short-circuits the post; (b) a
  durable sidecar mark (jsonl in ``state_dir``, keyed by attempt id) is
  appended after each 2xx, so a retry after a partial delivery resumes at the
  step that did not land instead of duplicating the one that did.
* **No secrets in bodies.**  Auth headers are held in memory and sent only as
  headers; nothing in this module logs, echoes or embeds them in a comment or
  document body.
* **Delivery is not acceptance.**  The transport writes the record's own
  ``acceptance`` (``not_accepted`` in v1) and changes no issue status.
"""
from __future__ import annotations

import http.client
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Mapping

#: Origin kind this transport claims (the envelope's ``carrier_kind``).
PAPERCLIP_ORIGIN_KIND = "paperclip_task"

#: Machine-checkable dedupe marker line embedded in every posted comment.
PAPERCLIP_RETURN_MARKER_PREFIX = "paperclip-return-attempt:"

#: Receipt schema (the projection's delivery-receipt vocabulary).
_DELIVERY_SCHEMA = "mastermind.execution_return_delivery/v1"

#: The only hosts this transport may write to (dev-loopback law).
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})

#: Sidecar mark file name inside ``state_dir``.
_MARKS_FILE = "paperclip_result_delivery_marks.jsonl"

#: Bounded reason text in a refused receipt.
_REASON_MAX = 300


class _TransportError(Exception):
    """One failed HTTP step; ``reason`` is safe to put in a receipt."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _loopback_base(base_url: Any) -> str:
    """Validate and normalize the base URL; non-loopback is a ValueError."""
    if type(base_url) is not str or not base_url.strip():
        raise ValueError("base_url must be a non-empty string")
    parts = urllib.parse.urlsplit(base_url.strip())
    if parts.scheme not in ("http", "https"):
        raise ValueError("base_url must be an http(s) URL")
    host = parts.hostname or ""
    if host not in _LOOPBACK_HOSTS:
        raise ValueError(
            f"refusing non-loopback Paperclip base {base_url!r}: this transport "
            "is a dev-loopback writer (127.0.0.1, localhost, ::1)")
    return base_url.strip().rstrip("/")


def _issue_id(ids: Mapping[str, str]) -> str | None:
    """The Paperclip issue this origin names.

    ``issue`` is the canonical key.  ``issue_id`` is accepted as the same
    reference, and the frozen envelope's documented requester convention
    (``conversation_id = "paperclip-issue:<issueId>"``) is read as a last
    resort — the wiring builds ``OriginRef.ids`` from the requester block, so
    that is the shape it actually hands over.  Nothing is guessed: an origin
    naming no issue refuses.
    """
    for key in ("issue", "issue_id"):
        value = ids.get(key)
        if type(value) is str and value.strip():
            return value.strip()
    conversation = ids.get("conversation_id")
    if type(conversation) is str and conversation.startswith("paperclip-issue:"):
        value = conversation.split(":", 1)[1].strip()
        if value:
            return value
    return None


def _attempt_id(payload: Mapping[str, Any]) -> str | None:
    attempt = payload.get("attempt")
    if not isinstance(attempt, Mapping):
        return None
    value = attempt.get("attempt_id")
    if type(value) is str and value.strip():
        return value.strip()
    return None


def _comment_rows(value: Any) -> list[Any]:
    """Rows from the comments endpoint, tolerating this build's shapes."""
    if isinstance(value, Mapping):
        for key in ("comments", "rows", "items", "data"):
            candidate = value.get(key)
            if isinstance(candidate, list):
                value = candidate
                break
        else:
            return []
    if not isinstance(value, list):
        return []
    return list(value)


def _comment_row_is_own_delivery(
    row: Any, marker: str, request_id: str,
) -> bool:
    """T4c repair round 1, R2 (panel MED, 2026-11-11): a comment row counts
    as THIS transport's own earlier delivery only when the row itself says
    so — never a bare marker substring, which any comment author could
    forge (the attempt id is public: the worker prompt names it).

    The transport posts its delivery comment through the instance-role
    channel, which the dev instance stamps as the board actor —
    ``authorType "user"``, ``authorAgentId`` unset (observed live
    2026-11-11: ``authorUserId "local-board"``) — and carries the
    deterministic ``clientRequestId`` this module computes (uuid5 keyed on
    the attempt, so a retried delivery re-uses the same request id).  A row
    matches only when BOTH hold: agent-channel posts always carry
    ``authorAgentId`` (the H2 attribution shape) and a board user without
    the exact request id matches neither.  Anything else — even with the
    marker in its body — is another author's word and suppresses nothing.
    """
    if not isinstance(row, Mapping):
        return False
    body = row.get("body")
    if type(body) is not str or marker not in body:
        return False
    if row.get("authorType") != "user" or row.get("authorAgentId"):
        return False  # agent-authored (or unknown-shape) — not our row
    return str(row.get("clientRequestId") or "") == request_id


def _document_key(attempt_id: str) -> str:
    safe = "".join(
        char if (char.isalnum() or char in "-_") else "-" for char in attempt_id)
    return f"coding-job-return-{safe}"[:120]


def _quoted_worker_text(text: str) -> str:
    """F4 (R4b review): worker output rides inside a code fence longer than
    any backtick run in it, so worker words can never pose as the board's
    prose (the whole comment also opens with the ``[coding-job]`` line)."""
    longest = 0
    run = 0
    for char in text:
        run = run + 1 if char == "`" else 0
        if run > longest:
            longest = run
    fence = "`" * max(3, longest + 1)
    return f"{fence}\n{text}\n{fence}"


def build_return_comment(payload: Mapping[str, Any], attempt_id: str) -> str:
    """The comment body: deterministic, built only from fields that exist.

    Job identity (attempt, root, idempotency key, T3 thread/run), the result
    line, artifact refs and the GitHub evidence the record actually carries.
    An unobserved GitHub fact is written as ``unknown`` — never invented.

    F4 (R4b review): the first line is the ``[coding-job]`` marker — every
    comment this transport writes opens with it, so the carrier never takes
    it as a board note — and the worker's text is fenced as quoted output.
    """
    attempt = payload.get("attempt")
    attempt = attempt if isinstance(attempt, Mapping) else {}
    result = payload.get("result")
    result = result if isinstance(result, Mapping) else {}
    github = payload.get("github")
    github = github if isinstance(github, Mapping) else {}

    stage = payload.get("stage")
    stage = stage if type(stage) is str and stage else "unknown"
    lines: list[str] = [
        f"[coding-job] Coding job result — {stage}",
        "",
        f"{PAPERCLIP_RETURN_MARKER_PREFIX} {attempt_id}",
        "",
        "**Job identity**",
    ]
    for label, key in (
        ("attempt", "attempt_id"),
        ("root", "root_id"),
        ("idempotency key", "idempotency_key"),
        ("t3 thread", "t3_thread_id"),
        ("t3 run", "t3_run_id"),
    ):
        value = attempt.get(key)
        if type(value) is str and value:
            lines.append(f"- {label}: `{value}`")
    for label, key in (("return", "return_id"), ("digest", "digest")):
        value = payload.get(key)
        if type(value) is str and value:
            lines.append(f"- {label}: `{value}`")
    acceptance = payload.get("acceptance")
    acceptance = acceptance if type(acceptance) is str and acceptance else "not_accepted"
    lines.append(f"- acceptance: {acceptance} (delivery is not acceptance)")

    lines.extend(["", "**Result** (the worker's output, quoted verbatim)",
                  ""])
    text = result.get("text")
    lines.append(_quoted_worker_text(text)
                 if type(text) is str and text else
                 "(no result text recorded)")
    refs = result.get("artifact_refs")
    if isinstance(refs, list) and refs:
        lines.extend(["", "**Artifacts**"])
        for ref in refs:
            if type(ref) is str and ref:
                lines.append(f"- `{ref}`")

    lines.extend(["", "**GitHub evidence**"])
    evidence: list[str] = []
    branch = github.get("branch")
    if type(branch) is str and branch:
        evidence.append(f"- branch: `{branch}`")
    pr_number = github.get("pr_number")
    pr_url = github.get("pr_url")
    if type(pr_number) is int:
        evidence.append(f"- pr: #{pr_number}")
    if type(pr_url) is str and pr_url:
        evidence.append(f"- pr url: {pr_url}")
    checks_state = github.get("checks_state")
    if type(checks_state) is str and checks_state:
        evidence.append(f"- checks: {checks_state}")
    merge_state = github.get("merge_state")
    if type(merge_state) is str and merge_state:
        evidence.append(f"- merge: {merge_state}")
    installation = github.get("installation")
    if type(installation) is str and installation:
        evidence.append(f"- installation: {installation}")
    if evidence:
        lines.extend(evidence)
    else:
        lines.append("- no GitHub evidence observed (branch/pr/checks unknown)")
    return "\n".join(lines) + "\n"


def build_return_document(payload: Mapping[str, Any], attempt_id: str) -> str:
    """The issue document: the full result payload, canonical and readable."""
    body = json.dumps(
        payload, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False)
    return (
        f"# Coding job return — {attempt_id}\n\n"
        f"{PAPERCLIP_RETURN_MARKER_PREFIX} {attempt_id}\n\n"
        "The full `mastermind.execution_return/v1` record delivered to this "
        "task.\n\n"
        f"```json\n{body}\n```\n"
    )


class PaperclipResultDeliveryTransport:
    """Write one verified result onto the Paperclip task that asked for it.

    ``base_url`` must be loopback (ValueError otherwise).  ``headers`` are the
    per-request auth headers (the dev instance's ``x-instance-role:
    local_trusted`` convention); they are sent as headers only and never
    appear in a body, a receipt or a log.  ``documents`` toggles the issue
    document write.  ``state_dir`` holds the durable dedupe sidecar.
    """

    def __init__(
        self,
        *,
        base_url: str,
        headers: Mapping[str, str] | None = None,
        documents: bool = True,
        state_dir: str | os.PathLike[str],
        timeout: float = 30.0,
    ) -> None:
        self._base_url = _loopback_base(base_url)
        if headers is None:
            headers = {}
        if not isinstance(headers, Mapping):
            raise ValueError("headers must be a mapping of header name to value")
        clean: dict[str, str] = {}
        for name, value in headers.items():
            if type(name) is not str or not name.strip():
                raise ValueError("header names must be non-empty strings")
            if type(value) is not str:
                raise ValueError(f"header {name!r} value must be a string")
            clean[name] = value
        self._headers = clean
        self._documents = bool(documents)
        if state_dir is None or not str(state_dir).strip():
            raise ValueError("state_dir must name a directory")
        self._state_dir = Path(state_dir)
        self._timeout = float(timeout)

    # --- HTTP ------------------------------------------------------------

    def _request(
        self,
        method: str,
        path: str,
        body: Any = None,
        *,
        allow: tuple[int, ...] = (),
    ) -> tuple[int, Any]:
        """One request, no retries.  Raises ``_TransportError`` on failure."""
        url = f"{self._base_url}{path}"
        data = None
        headers = dict(self._headers)
        if body is not None:
            data = json.dumps(body, sort_keys=True).encode("utf-8")
            headers["content-type"] = "application/json"
        request = urllib.request.Request(
            url, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                status = int(response.status)
                raw = response.read()
        except urllib.error.HTTPError as exc:
            if exc.code in allow:
                return int(exc.code), {}
            raise _TransportError(f"{method} {path} -> HTTP {exc.code}") from None
        except (urllib.error.URLError, OSError, http.client.HTTPException) as exc:
            reason = getattr(exc, "reason", None) or type(exc).__name__
            raise _TransportError(
                f"{method} {path} unreachable: {reason}") from None
        if not 200 <= status < 300:
            raise _TransportError(f"{method} {path} -> HTTP {status}")
        if not raw:
            return status, {}
        try:
            return status, json.loads(raw)
        except ValueError:
            return status, {}

    # --- durable dedupe sidecar -----------------------------------------

    @property
    def _marks_path(self) -> Path:
        return self._state_dir / _MARKS_FILE

    def _marks(self, attempt_id: str) -> set[str]:
        steps: set[str] = set()
        try:
            with open(self._marks_path, "r", encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                    except ValueError:
                        continue
                    if (isinstance(row, dict)
                            and row.get("attempt_id") == attempt_id
                            and type(row.get("step")) is str):
                        steps.add(row["step"])
        except FileNotFoundError:
            pass
        return steps

    def _mark(self, attempt_id: str, issue: str, step: str) -> None:
        self._state_dir.mkdir(parents=True, exist_ok=True)
        row = {
            "attempt_id": attempt_id,
            "issue": issue,
            "step": step,
            "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        line = json.dumps(row, sort_keys=True) + "\n"
        descriptor = os.open(
            self._marks_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            os.write(descriptor, line.encode("utf-8"))
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    # --- receipts --------------------------------------------------------

    @staticmethod
    def _receipt(
        payload: Mapping[str, Any],
        *,
        state: str,
        transport_ref: str | None = None,
        refusal_code: str | None = None,
        reason: str | None = None,
        note: str | None = None,
    ) -> dict[str, Any]:
        receipt: dict[str, Any] = {
            "schema": _DELIVERY_SCHEMA,
            "state": state,
            "transport_ref": transport_ref,
            "return_id": payload.get("return_id") if type(
                payload.get("return_id")) is str else "",
            "return_digest": payload.get("digest") if type(
                payload.get("digest")) is str else "",
        }
        if refusal_code is not None:
            receipt["refusal_code"] = refusal_code
        if reason is not None:
            receipt["reason"] = reason[:_REASON_MAX]
        if note is not None:
            receipt["note"] = note
        return receipt

    def _refused(
        self,
        payload: Mapping[str, Any],
        code: str,
        reason: str,
    ) -> dict[str, Any]:
        return self._receipt(
            payload, state="refused", refusal_code=code, reason=reason)

    # --- the protocol ----------------------------------------------------

    async def deliver(
        self, origin: Any, payload: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        """Deliver one verified result; never raises, never guesses."""
        try:
            return self._deliver(origin, payload)
        except Exception as exc:  # last-resort fence: an honest refusal
            safe = payload if isinstance(payload, Mapping) else {}
            return self._refused(
                safe, "TRANSPORT_FAILED",
                f"{type(exc).__name__}: {exc}"[:_REASON_MAX])

    def _deliver(
        self, origin: Any, payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        if not isinstance(payload, Mapping):
            return self._refused({}, "PAYLOAD_INVALID", "payload is not a mapping")
        kind = getattr(origin, "kind", None)
        if kind != PAPERCLIP_ORIGIN_KIND:
            return self._refused(
                payload, "ORIGIN_KIND_MISMATCH",
                f"transport claims {PAPERCLIP_ORIGIN_KIND!r}, got {kind!r}")
        ids = getattr(origin, "ids", None)
        if not isinstance(ids, Mapping):
            return self._refused(
                payload, "ORIGIN_ISSUE_MISSING", "origin carries no ids mapping")
        issue = _issue_id(ids)
        if issue is None:
            return self._refused(
                payload, "ORIGIN_ISSUE_MISSING",
                "origin ids name no Paperclip issue (key 'issue')")
        attempt_id = _attempt_id(payload)
        if attempt_id is None:
            return self._refused(
                payload, "ATTEMPT_ID_MISSING",
                "payload carries no attempt.attempt_id to key the return on")

        marker = f"{PAPERCLIP_RETURN_MARKER_PREFIX} {attempt_id}"
        quoted_issue = urllib.parse.quote(issue, safe="")
        marks = self._marks(attempt_id)
        # R2: the request id this transport posts its delivery comment
        # with — deterministic per attempt, so the dedupe scan below can
        # demand it echoed on a board-authored row (see
        # ``_comment_row_is_own_delivery``).
        request_id = str(uuid.uuid5(
            uuid.NAMESPACE_URL, f"paperclip-return:{attempt_id}"))

        # Guard (a): the issue's own comments are the authority on what was
        # already posted; the sidecar is the fast path.
        comment_posted = "comment" in marks
        already_delivered = comment_posted
        if not comment_posted:
            try:
                _, listing = self._request(
                    "GET", f"/api/issues/{quoted_issue}/comments")
            except _TransportError as exc:
                return self._refused(
                    payload, "COMMENTS_READ_FAILED", exc.reason)
            if any(_comment_row_is_own_delivery(row, marker, request_id)
                   for row in _comment_rows(listing)):
                comment_posted = True
                already_delivered = True
                self._mark(attempt_id, issue, "comment")

        comment_id: str | None = None
        if not comment_posted:
            body = build_return_comment(payload, attempt_id)
            try:
                _, created = self._request(
                    "POST", f"/api/issues/{quoted_issue}/comments",
                    # the API requires a UUID here (invalid_format otherwise);
                    # uuid5 keyed on the attempt keeps it deterministic so a
                    # retried delivery posts the same request id
                    {"clientRequestId": request_id,
                     "body": body})
            except _TransportError as exc:
                return self._refused(
                    payload, "COMMENT_POST_FAILED", exc.reason)
            self._mark(attempt_id, issue, "comment")
            if isinstance(created, Mapping) and type(created.get("id")) is str:
                comment_id = created["id"]

        # The document: same dedupe discipline, one step behind the comment.
        document_key = _document_key(attempt_id)
        document_written = "document" in marks
        if self._documents and not document_written:
            document_body = build_return_document(payload, attempt_id)
            quoted_key = urllib.parse.quote(document_key, safe="")
            try:
                status, existing = self._request(
                    "GET",
                    f"/api/issues/{quoted_issue}/documents/{quoted_key}",
                    allow=(404,))
            except _TransportError as exc:
                return self._refused(
                    payload, "DOCUMENT_READ_FAILED",
                    f"{exc.reason} (comment already posted)")
            if status == 200 and isinstance(existing, Mapping) \
                    and existing.get("body") == document_body:
                self._mark(attempt_id, issue, "document")
                document_written = True
            else:
                try:
                    self._request(
                        "PUT",
                        f"/api/issues/{quoted_issue}/documents/{quoted_key}",
                        {"format": "markdown",
                         "title": f"Coding job return — {attempt_id}",
                         "body": document_body,
                         "changeSummary": "coding job result return"})
                except _TransportError as exc:
                    return self._refused(
                        payload, "DOCUMENT_WRITE_FAILED",
                        f"{exc.reason} (comment already posted)")
                self._mark(attempt_id, issue, "document")
                document_written = True

        transport_ref = f"paperclip:issue:{issue}:comment:{comment_id or 'existing'}"
        if self._documents and document_written:
            transport_ref += f":document:{document_key}"
        note = "already-delivered" if already_delivered else None
        return self._receipt(
            payload, state="delivered", transport_ref=transport_ref, note=note)


__all__ = [
    "PAPERCLIP_ORIGIN_KIND",
    "PAPERCLIP_RETURN_MARKER_PREFIX",
    "PaperclipResultDeliveryTransport",
    "build_return_comment",
    "build_return_document",
]

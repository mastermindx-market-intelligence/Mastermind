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
* **The writer is a dedicated service agent, never the board** (REV-CODE
  F1).  Each delivery that must write reads the agent's bearer from a 0600
  regular non-symlink token file (``service_agent_token_path``, read fresh at
  every delivery), invokes ONE heartbeat run for that agent
  (``POST /api/agents/{id}/heartbeat/invoke``), then posts the comment and
  writes the document with ``Authorization: Bearer`` + ``X-Paperclip-Run-Id``.
  The run is never cancelled by the transport (the agent key cannot cancel it
  anyway — board only).  Comment GETs (the dedupe scan) may ride the board
  ``headers`` — reads only.
* **Exactly-once posting, two guards.**  (a) Before posting, the issue's
  comments are read and a row already carrying the dedupe marker LINE
  ``paperclip-return-attempt: <attempt_id> request: <uuid5 request id>`` as a
  WHOLE line, authored by THIS service agent, short-circuits the post; (b) a
  durable sidecar mark (jsonl in ``state_dir``, keyed by attempt id) is
  appended after each 2xx, so a retry after a partial delivery resumes at the
  step that did not land instead of duplicating the one that did.

  Deviation from "authorAgentId + clientRequestId" (probe fact, dev board
  3196, build 2026.1106.0): on agent rows the server DROPS clientRequestId
  (stores null), so a scan keyed on the row's clientRequestId can never match
  an agent row on this build.  The request id therefore rides IN the marker
  line itself, and a row is ours only when ``authorAgentId`` equals the
  service agent exactly AND the body contains that exact marker line as a
  whole line.  Only the service agent's key can produce that authorAgentId,
  so another author cannot forge it; a board row with the marker is never
  ours.  clientRequestId is still sent on the POST (harmless).
* **No secrets in bodies.**  Auth headers and the bearer token are held in
  memory and sent only as headers; nothing in this module logs, echoes or
  embeds them in a comment or document body, a receipt, an error text or a
  log.  The token file's contents are scrubbed from every reason this
  transport produces.
* **Delivery is not acceptance.**  The transport writes the record's own
  ``acceptance`` (``not_accepted`` in v1) and changes no issue status.
"""
from __future__ import annotations

import http.client
import json
import os
import stat
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
    """One failed HTTP step; ``reason`` is safe to put in a receipt.

    ``code`` optionally names the typed refusal this failure maps to (e.g.
    the token-file and heartbeat-invoke refusals); ``None`` lets the caller
    apply its own step-specific code.
    """

    def __init__(self, reason: str, *, code: str | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.code = code


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
    row: Any, marker_line: str, service_agent_id: str,
) -> bool:
    """T4c repair round 1, R2 (panel MED, 2026-11-11): a comment row counts
    as THIS transport's own earlier delivery only when the row itself says
    so — never a bare marker substring, which any comment author could
    forge (the attempt id is public: the worker prompt names it).

    PF-3 item 1 + REV-CODE F1: the delivery writer is a DEDICATED SERVICE
    AGENT, never the board.  A row is ours only when BOTH hold:

    * ``authorAgentId`` equals this transport's ``service_agent_id``
      exactly — a board-user row (``authorType "user"``, no
      ``authorAgentId``) is NEVER ours whatever its body, and another
      agent's row is never ours;
    * its body is a string containing the exact marker LINE
      ``paperclip-return-attempt: <attempt_id> request: <uuid5 request id>``
      as a WHOLE line (equal to one of ``body.splitlines()``), never a
      substring of a longer line.

    Deviation from the earlier "authorAgentId + clientRequestId" rule, with
    the probe fact (dev board 3196, build 2026.1106.0): on agent rows the
    server DROPS clientRequestId (stores null), so matching the row's
    clientRequestId field can never succeed for an agent row on this build.
    The deterministic uuid5 request id therefore rides IN the marker line.
    Only the service agent's key can produce ``authorAgentId == svc``, so
    another author cannot forge our row; a board row carrying the marker is
    never ours.  Anything else suppresses nothing.
    """
    if not isinstance(row, Mapping):
        return False
    if row.get("authorAgentId") != service_agent_id:
        return False  # board-user (no agent id) or another agent — not ours
    body = row.get("body")
    if type(body) is not str:
        return False
    return marker_line in body.splitlines()


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


def build_return_comment(
    payload: Mapping[str, Any], attempt_id: str, request_id: str,
) -> str:
    """The comment body: deterministic, built only from fields that exist.

    Job identity (attempt, root, idempotency key, T3 thread/run), the result
    line, artifact refs and the GitHub evidence the record actually carries.
    An unobserved GitHub fact is written as ``unknown`` — never invented.

    F4 (R4b review): the first line is the ``[coding-job]`` marker — every
    comment this transport writes opens with it, so the carrier never takes
    it as a board note — and the worker's text is fenced as quoted output.

    REV-CODE F1: the dedupe marker is a WHOLE line carrying both the attempt
    id and the deterministic uuid5 ``request_id`` (the server drops
    clientRequestId on agent rows, so the request id rides here instead).
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
        return_marker_line(attempt_id, request_id),
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


def return_marker_line(attempt_id: str, request_id: str) -> str:
    """The exact whole-line dedupe marker (REV-CODE F1).

    Carries the attempt id AND the deterministic uuid5 request id, because
    the server drops ``clientRequestId`` on agent rows (probe fact, dev board
    3196, build 2026.1106.0) — the request id must ride in the body to be
    recoverable by the exactly-once scan.
    """
    return f"{PAPERCLIP_RETURN_MARKER_PREFIX} {attempt_id} request: {request_id}"


def build_return_document(
    payload: Mapping[str, Any], attempt_id: str, request_id: str,
) -> str:
    """The issue document: the full result payload, canonical and readable."""
    body = json.dumps(
        payload, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False)
    return (
        f"# Coding job return — {attempt_id}\n\n"
        f"{return_marker_line(attempt_id, request_id)}\n\n"
        "The full `mastermind.execution_return/v1` record delivered to this "
        "task.\n\n"
        f"```json\n{body}\n```\n"
    )


class PaperclipResultDeliveryTransport:
    """Write one verified result onto the Paperclip task that asked for it.

    ``base_url`` must be loopback (ValueError otherwise).  ``headers`` are
    the board read headers (the dedupe comment GETs ride them); they are sent
    as headers only and no value from them ever appears in a body, a receipt,
    an error text or a log — every reason this transport produces is scrubbed
    of the configured header values.
    ``service_agent_id`` (PF-3 item 1) is the REQUIRED dedicated service
    agent the delivery is attributed to — never the board; the exactly-once
    scan counts only rows authored by this agent.  REV-CODE F5: an id with
    surrounding whitespace is refused (never silently stripped).
    ``service_agent_token_path`` (REV-CODE F1) is the REQUIRED path to that
    agent's bearer token: a 0600 regular non-symlink file, read fresh at each
    delivery that must write.  The token is sent only as an authorization
    header and is scrubbed from every reason; a missing, non-regular,
    symlinked or wrong-mode file is a typed refusal, never a guess.
    ``documents`` toggles the issue document write.  ``state_dir`` holds the
    durable dedupe sidecar.
    """

    def __init__(
        self,
        *,
        base_url: str,
        service_agent_id: str,
        service_agent_token_path: str | os.PathLike[str],
        headers: Mapping[str, str] | None = None,
        documents: bool = True,
        state_dir: str | os.PathLike[str],
        timeout: float = 30.0,
    ) -> None:
        self._base_url = _loopback_base(base_url)
        # F5: refuse surrounding whitespace rather than store a stripped id —
        # a padded id would never equal the server's authorAgentId and would
        # silently break the exactly-once scan.
        if (type(service_agent_id) is not str or not service_agent_id
                or service_agent_id.strip() != service_agent_id):
            raise ValueError(
                "service_agent_id must be a non-empty string without "
                "surrounding whitespace")
        self._service_agent_id = service_agent_id
        if (service_agent_token_path is None
                or not str(service_agent_token_path).strip()):
            raise ValueError(
                "service_agent_token_path must name the service agent's "
                "0600 bearer token file")
        self._service_agent_token_path = Path(
            str(service_agent_token_path)).expanduser()
        # Transient per-delivery secrets (the bearer token read from the
        # file) and the cached heartbeat run context; both cleared after each
        # delivery so no token is retained.  ``_scrub`` redacts the secrets.
        self._delivery_secrets: tuple[str, ...] = ()
        self._run_context: tuple[str, str] | None = None
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
        # PF-3 item 1: every reason/error text is scrubbed of these values
        # (longest first, so an overlapping shorter value cannot leave a
        # fragment of a longer one behind).
        self._header_values = tuple(sorted(
            {value for value in clean.values() if value},
            key=len, reverse=True))
        self._documents = bool(documents)
        if state_dir is None or not str(state_dir).strip():
            raise ValueError("state_dir must name a directory")
        self._state_dir = Path(state_dir)
        self._timeout = float(timeout)

    def _scrub(self, text: str) -> str:
        """Remove every configured header value AND the transient bearer
        token from a reason/error text (raw and %r forms)."""
        for value in self._header_values + self._delivery_secrets:
            text = text.replace(value, "[redacted-header]")
            # exception texts often carry the %r form (a newline becomes
            # a literal \n), which the raw replace above cannot match
            escaped = repr(value)[1:-1]
            if escaped != value:
                text = text.replace(escaped, "[redacted-header]")
        return text

    # --- the service-agent writer (REV-CODE F1) ---------------------------

    def _read_service_token(self) -> str:
        """Read the agent bearer fresh from its 0600 regular non-symlink
        file.  A missing, symlinked, non-regular, wrong-mode, unreadable or
        empty file is a typed ``SERVICE_TOKEN_UNAVAILABLE`` refusal.  The
        reason texts are static — the token value never appears in them.
        """
        path = self._service_agent_token_path
        code = "SERVICE_TOKEN_UNAVAILABLE"
        try:
            st = os.lstat(path)  # lstat: never follow a symlink
        except OSError:
            raise _TransportError(
                "service agent token file is missing", code=code) from None
        if stat.S_ISLNK(st.st_mode):
            raise _TransportError(
                "service agent token file is a symlink", code=code)
        if not stat.S_ISREG(st.st_mode):
            raise _TransportError(
                "service agent token file is not a regular file", code=code)
        if stat.S_IMODE(st.st_mode) != 0o600:
            raise _TransportError(
                "service agent token file mode is not 0600", code=code)
        try:
            with open(path, "r", encoding="utf-8") as handle:
                token = handle.read().strip()
        except OSError:
            raise _TransportError(
                "service agent token file is unreadable", code=code) from None
        if not token:
            raise _TransportError(
                "service agent token file is empty", code=code)
        return token

    def _invoke_heartbeat(self, token: str) -> str:
        """Invoke ONE heartbeat run for the service agent with its bearer;
        return the run id.  Never cancels the run.  Any failure is a typed
        ``HEARTBEAT_INVOKE_FAILED`` refusal (no comment POST is attempted).
        """
        code = "HEARTBEAT_INVOKE_FAILED"
        agent = urllib.parse.quote(self._service_agent_id, safe="")
        try:
            _, body = self._request(
                "POST", f"/api/agents/{agent}/heartbeat/invoke", {},
                auth={"authorization": f"Bearer {token}"})
        except _TransportError as exc:
            raise _TransportError(exc.reason, code=code) from None
        if not isinstance(body, Mapping) or type(body.get("id")) is not str \
                or not body["id"]:
            raise _TransportError(
                "heartbeat invoke returned no run id", code=code)
        return body["id"]

    def _agent_write_headers(self) -> dict[str, str]:
        """The bearer + run-id headers for an agent write.  Reads the token
        and invokes one heartbeat run on first use, cached for the rest of
        this delivery (one run per delivery).  Raises ``_TransportError``
        with a typed ``code`` on token/heartbeat failure.
        """
        if self._run_context is None:
            token = self._read_service_token()
            self._delivery_secrets = (token,)
            run_id = self._invoke_heartbeat(token)
            self._run_context = (token, run_id)
        token, run_id = self._run_context
        return {"authorization": f"Bearer {token}",
                "X-Paperclip-Run-Id": run_id}

    # --- HTTP ------------------------------------------------------------

    def _request(
        self,
        method: str,
        path: str,
        body: Any = None,
        *,
        allow: tuple[int, ...] = (),
        auth: Mapping[str, str] | None = None,
    ) -> tuple[int, Any]:
        """One request, no retries.  Raises ``_TransportError`` on failure.

        ``auth`` (agent writes) REPLACES the board read headers — an agent
        write rides only its bearer + run id, never the board channel.
        ``None`` (reads) uses the configured board headers.
        """
        url = f"{self._base_url}{path}"
        data = None
        headers = dict(auth) if auth is not None else dict(self._headers)
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
            raise _TransportError(self._scrub(
                f"{method} {path} unreachable: {reason}")) from None
        except Exception as exc:
            # PF-3 item 1: an unexpected exception (e.g. http.client's
            # ValueError quoting an invalid header VALUE) must never carry
            # its text into a receipt — type name only.
            raise _TransportError(
                f"{method} {path} -> {type(exc).__name__}") from None
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
        # PF-3 item 1: no configured header value ever reaches a receipt —
        # including the last-resort fence's str(exc) in ``deliver``.
        return self._receipt(
            payload, state="refused", refusal_code=code,
            reason=self._scrub(reason))

    # --- the protocol ----------------------------------------------------

    async def deliver(
        self, origin: Any, payload: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        """Deliver one verified result; never raises, never guesses."""
        try:
            return self._deliver(origin, payload)
        except Exception as exc:  # last-resort fence: an honest refusal
            safe = payload if isinstance(payload, Mapping) else {}
            # F4: scrub THEN truncate — pass the full text to _refused (which
            # scrubs the whole string) and let _receipt apply the length cap,
            # so a secret straddling the cap can never leave a fragment.
            return self._refused(
                safe, "TRANSPORT_FAILED", f"{type(exc).__name__}: {exc}")
        finally:
            # never retain the bearer token or run context past a delivery
            self._delivery_secrets = ()
            self._run_context = None

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

        quoted_issue = urllib.parse.quote(issue, safe="")
        marks = self._marks(attempt_id)
        # R2: the request id this transport posts its delivery comment
        # with — deterministic per attempt, so a retried delivery re-uses it.
        # REV-CODE F1: it rides IN the marker line (the server drops
        # clientRequestId on agent rows), and the scan demands that whole
        # line on a row authored by THIS service agent.
        request_id = str(uuid.uuid5(
            uuid.NAMESPACE_URL, f"paperclip-return:{attempt_id}"))
        marker_line = return_marker_line(attempt_id, request_id)

        # Guard (a): the issue's own comments are the authority on what was
        # already posted; the sidecar is the fast path.  The scan is a READ
        # and rides the board headers.
        comment_posted = "comment" in marks
        already_delivered = comment_posted
        if not comment_posted:
            try:
                _, listing = self._request(
                    "GET", f"/api/issues/{quoted_issue}/comments")
            except _TransportError as exc:
                return self._refused(
                    payload, "COMMENTS_READ_FAILED", exc.reason)
            if any(_comment_row_is_own_delivery(
                    row, marker_line, self._service_agent_id)
                   for row in _comment_rows(listing)):
                comment_posted = True
                already_delivered = True
                self._mark(attempt_id, issue, "comment")

        comment_id: str | None = None
        if not comment_posted:
            body = build_return_comment(payload, attempt_id, request_id)
            try:
                # REV-CODE F1: the writer is the service agent — read its
                # token, invoke ONE heartbeat run, post with bearer+run id.
                # A token/heartbeat failure refuses typed BEFORE any comment
                # POST is attempted (exc.code names which step failed).
                auth = self._agent_write_headers()
                _, created = self._request(
                    "POST", f"/api/issues/{quoted_issue}/comments",
                    # clientRequestId is still sent (harmless): the API
                    # requires a UUID here, but the server DROPS it on agent
                    # rows — the request id rides in the marker line instead.
                    {"clientRequestId": request_id, "body": body},
                    auth=auth)
            except _TransportError as exc:
                return self._refused(
                    payload, exc.code or "COMMENT_POST_FAILED", exc.reason)
            self._mark(attempt_id, issue, "comment")
            if isinstance(created, Mapping) and type(created.get("id")) is str:
                comment_id = created["id"]

        # The document: same dedupe discipline, one step behind the comment.
        document_key = _document_key(attempt_id)
        document_written = "document" in marks
        if self._documents and not document_written:
            document_body = build_return_document(
                payload, attempt_id, request_id)
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
                    # the document write rides the SAME bearer + run id as
                    # the comment (one heartbeat run per delivery, reused).
                    auth = self._agent_write_headers()
                    self._request(
                        "PUT",
                        f"/api/issues/{quoted_issue}/documents/{quoted_key}",
                        {"format": "markdown",
                         "title": f"Coding job return — {attempt_id}",
                         "body": document_body,
                         "changeSummary": "coding job result return"},
                        auth=auth)
                except _TransportError as exc:
                    return self._refused(
                        payload, exc.code or "DOCUMENT_WRITE_FAILED",
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
    "return_marker_line",
]

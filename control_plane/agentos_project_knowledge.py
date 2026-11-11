"""Bounded read-only capture of workspace project knowledge from Macro's Git store.

Three public functions, all pure readers over the existing sealed owner:

* ``read_project_knowledge_catalogue``    - ``mastermind.workspace_project_knowledge.v1``
* ``read_project_knowledge_source``      - ``mastermind.workspace_project_source.v1``
* ``read_project_communication_preference`` - ``mastermind.workspace_project_preference.v1``

Canonical identity this capture enforces:

* ``work_ref`` is the colon citation ``WS:<KEY>``; the canonical record file is
  ``agentos/workstreams/WS-<KEY>.md``.
* The communication preference is the dynamic fixed-key decision
  ``DEC-PROJECT-COMMUNICATION-PREFERENCE-<KEY>.md`` carrying the canonical
  ``project_preference`` payload; it is EMPTY only when that record is
  genuinely absent, and any valid record anchored to another work is a
  CONFLICT, never an EMPTY.
* Every ``revision`` is the actual Git blob SHA-1 of the exact bytes; only
  ``source.commit`` carries the Macro commit.  Source identities hash
  repository + commit + work_ref + path + blob.
* ``committed_at`` is the actual Git authored-commit clock normalized to UTC;
  authored dates are record source facts (``decided_at`` / ``verified_at``);
  handoff and workstream rows carry no authored date and stay null.

Every call runs a fixed, bounded, immutable Git capture of the one absolute
Macro root pinned by ``expected_macro_sha`` (supplied only by the existing
sealed owner, never by an HTTP caller): HEAD is verified before the first and
after the last Git read, Git replace refs are disabled, lazy fetch is
disabled, no optional locks are taken, nothing is fetched, and the capture
reuses the captured ``scripts/agentos.py`` parser and checkers (module
identity isolated and restored) instead of inferring repositories from file
existence.  Budgets are UTF-8 byte budgets: 4 MiB cumulative within 15
seconds, scripts 1 MiB, workstream 128 KiB, one file or record body 32 KiB,
and every response at most 131072 bytes.

These functions are INTERNAL source capture, not caller authorization.  They
never write, upload, fetch, or infer a principal relation; the parent
collector brackets each call with its own grant/revocation seal.  Only
``common`` (this repository's lower core) is imported; no facade reuse, no
integration imports.
"""

from __future__ import annotations

import contextlib
import datetime
import hashlib
import json
import os
import posixpath
import re
import sys
import time
import types
from pathlib import Path

from common.workspace_project_knowledge_contract import (
    CATALOGUE_SCHEMA,
    MAX_DISPLAY_NAME,
    MAX_FILE_METADATA,
    MAX_MATCHED_RECORDS,
    MAX_SCANNED_RECORDS,
    MAX_SOURCE_BODY,
    PREFERENCE_SCHEMA,
    REASON_CODES,
    REPOSITORY,
    REPOSITORY_KEYS,
    SOURCE_REF_PREFIXES,
    SOURCE_SCHEMA,
    VIEWER_RELATION,
    ContractInvalid,
    empty_memory,
    unavailable_catalogue,
    unavailable_memory,
    unavailable_source,
    validate_catalogue,
    validate_memory,
    validate_preference_payload,
    validate_selection,
    validate_source,
)

__all__ = [
    "read_project_knowledge_catalogue",
    "read_project_knowledge_source",
    "read_project_communication_preference",
]

PREFERENCE_KEY_PREFIX = "PROJECT-COMMUNICATION-PREFERENCE-"

_RESPONSE_LIMIT = 131072
_TOTAL_BUDGET = 4 * 1048576
_PARSER_LIMIT = 1048576
_WS_LIMIT = 131072
# One file or record body: 32768 UTF-8 bytes, read with one spare byte so an
# oversize candidate is detected and counted instead of silently truncated.
_RECORD_LIMIT = MAX_SOURCE_BODY + 1
_HISTORY_LIMIT = 1048576
_DEFAULT_LIMIT = 262144
_TIMEOUT_MAX = 15.0
_MAX_FILES = MAX_FILE_METADATA
_SHA40 = re.compile(r"[0-9a-f]{40}")
_SHA64 = re.compile(r"[0-9a-f]{64}")
_KEY_SHAPE = re.compile(r"[A-Z0-9]+(?:-[A-Z0-9]+)*")
_STAMP = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]+)?(?:Z|[+-][0-9]{2}:[0-9]{2})"
)
_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
# Permitted controls are exactly LF, CR and TAB; every other C0, the C1
# range and DEL are refused anywhere a response can echo them.
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\x80-\x9f]")
_MEMBER = r"100644 blob [0-9a-f]{40}\t"
_RECORD_PATH = re.compile(
    r"agentos/(?:workstreams|decisions|discoveries|handoffs)/"
    r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\.md"
)
_MACRO_DIR_PATH = re.compile(
    r"(?:agentos|research|docs)/[A-Za-z0-9][A-Za-z0-9._/-]{0,510}"
)
# Regular 100644 blob members only; the sentinel marks symlinks, gitlinks,
# executable or otherwise irregular tree entries, which are never read.
_IRREGULAR = object()
_IMMUTABLE_CAPTURE = object()

_PARSE_FAULTS = (ValueError, TypeError, KeyError, AttributeError, RecursionError, SyntaxError)


class _CaptureFailure(Exception):
    """The bounded capture refused; ``reason`` is a closed reason code."""

    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


def _default_runner():
    # control_plane.ceo_boot_packet owns the bounded subprocess runner used by
    # the installed collector; tests inject an equivalent runner instead.
    from control_plane.ceo_boot_packet import bounded_subprocess_runner

    return bounded_subprocess_runner


def _reason(failure):
    return failure.reason if failure.reason in REASON_CODES else "SOURCE_UNAVAILABLE"


def _ulen(value: str) -> int:
    """UTF-8 byte length: every capture budget is a byte budget."""
    return len(value.encode("utf-8"))


def _clean_text(value):
    """A bounded, control-free scalar safe to echo as a display name, or None."""
    if type(value) is not str or value == "" or _ulen(value) > MAX_DISPLAY_NAME:
        return None
    if _CONTROL.search(value) or "/" in value or "\\" in value or value.startswith("."):
        return None
    return value


def _clean_title(value):
    """A bounded, control-free prose title, or None.  Prose may carry ``/``."""
    if type(value) is not str or value == "" or _ulen(value) > 512:
        return None
    if _CONTROL.search(value) or value.strip() == "":
        return None
    return value


def _safe_macro_path(path):
    """Accept only plain, safe Macro paths under agentos/, research/ or docs/."""
    if _MACRO_DIR_PATH.fullmatch(path) is None:
        return False
    if ".." in path or "//" in path or path.endswith("/"):
        return False
    segments = path.split("/")
    if len(segments) > 16 or any(segment.startswith(".") for segment in segments[1:]):
        return False
    return True


def _identity(*parts):
    return hashlib.sha256("\x00".join(parts).encode("utf-8")).hexdigest()


def _utc_clock(raw):
    """Normalize the actual aware Git instant to UTC; never synthesize a clock."""
    text = (raw or "").strip()
    if _STAMP.fullmatch(text) is None:
        return None
    try:
        moment = datetime.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if moment.tzinfo is None:
        return None
    return moment.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _authored_date(value):
    """Authored date as a plain YYYY-MM-DD source fact; absent stays null.

    YAML resolvers hand back ``datetime.date``/``datetime.datetime`` objects
    for ISO dates; both are the record's own authored clock, not a Git clock.
    """
    if type(value) is str and _DATE.fullmatch(value) is not None:
        return value
    if isinstance(value, datetime.datetime):
        value = value.date()
    if isinstance(value, datetime.date):
        return value.isoformat()
    return None


class _CapturedRecord:
    """Path stand-in feeding captured bytes to Macro's own parser."""

    def __init__(self, text):
        self._text = text

    def read_text(self, *, encoding):
        if encoding != "utf-8":
            raise ValueError("record encoding refused")
        return self._text


class _Session:
    """One bounded Git read against a sealed root or issued canonical DATA view.

    DATA and executable code refs stay explicit; the view re-observes the fixed
    canonical default and grants instead of claiming a different filesystem HEAD.
    """

    def __init__(self, macro_root, expected_macro_sha, work_ref, runner, timeout, canonical_data_view=None, code_root=None, code_commit=None, immutable_capture=None):
        validate_selection(work_ref)
        if (
            not isinstance(macro_root, (str, Path))
            or isinstance(macro_root, bytes)
            or not Path(macro_root).is_absolute()
            or type(expected_macro_sha) is not str
            or _SHA40.fullmatch(expected_macro_sha) is None
            or type(timeout) not in (int, float)
            or isinstance(timeout, bool)
            or not 0 < timeout <= _TIMEOUT_MAX
        ):
            raise _CaptureFailure("SOURCE_UNAVAILABLE")
        self.root = Path(macro_root)
        self.commit = expected_macro_sha
        self._data_view = canonical_data_view
        if immutable_capture is not None and immutable_capture is not _IMMUTABLE_CAPTURE:
            raise _CaptureFailure("SOURCE_UNAVAILABLE")
        self._immutable_capture = immutable_capture
        self.code_commit, self.code_root = self.commit, self.root
        if code_root is not None or code_commit is not None:
            if (canonical_data_view is not None or not isinstance(code_root, (str, Path))
                    or not Path(code_root).is_absolute() or type(code_commit) is not str
                    or _SHA40.fullmatch(code_commit) is None):
                raise _CaptureFailure("SOURCE_UNAVAILABLE")
            # Trusted fixed child capture parameters are DATA, never a grant.
            # The installed parent owns code/source seals and principal fences.
            self.code_root, self.code_commit = Path(code_root), code_commit
        if canonical_data_view is not None:
            from control_plane.project_canonical_data import CanonicalProjectDataView
            if (type(canonical_data_view) is not CanonicalProjectDataView
                    or canonical_data_view._root != self.root
                    or canonical_data_view.data_commit != self.commit):
                raise _CaptureFailure("SOURCE_UNAVAILABLE")
            canonical_data_view.check()
            self.code_commit, self.code_root = canonical_data_view.code_commit, canonical_data_view._code_root
        self.work_ref = work_ref
        self.key = work_ref[3:]
        self.ws_path = "agentos/workstreams/WS-" + self.key + ".md"
        self.preference_key = PREFERENCE_KEY_PREFIX + self.key
        self.preference_path = "agentos/decisions/DEC-" + self.preference_key + ".md"
        self.deadline = time.monotonic() + timeout
        self.consumed = 0
        self._runner = runner
        self.commands = []

    def git(self, *args, limit=_DEFAULT_LIMIT, soft=False, _code=False, input_bytes=None):
        """One bounded immutable Git read; ``soft`` turns an output-limit trip
        into a None the caller counts, instead of failing the whole capture."""
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise _CaptureFailure("SOURCE_UNAVAILABLE")
        if self._runner is None:
            self._runner = _default_runner()
        self.commands.append(list(args))
        from control_plane.project_canonical_data import local_git_environment
        try:
            result = self._runner(
                [
                    "git",
                    "--no-optional-locks",
                    "--no-replace-objects",
                    "-C",
                    str(self.code_root if _code else self.root),
                    *args,
                ],
                cwd=self.code_root if _code else self.root,
                timeout=remaining,
                max_bytes=limit,
                env=local_git_environment(),
                **({} if input_bytes is None else {'input_bytes':input_bytes}),
            )
        except (OSError, ValueError, TypeError) as exc:
            raise _CaptureFailure("SOURCE_UNAVAILABLE") from exc
        if (
            not isinstance(result, dict)
            or result.get("code") != 0
            or type(result.get("stdout")) is not str
            or result.get("timed_out") is True
            or result.get("invalid_utf8") is True
        ):
            raise _CaptureFailure("SOURCE_UNAVAILABLE")
        value = result["stdout"]
        self.consumed += _ulen(value)
        if self.consumed > _TOTAL_BUDGET:
            raise _CaptureFailure("CONTENT_OVER_BUDGET")
        if result.get("limit_exceeded") is True:
            if soft:
                return None
            raise _CaptureFailure("SOURCE_UNAVAILABLE")
        return value

    def head(self):
        if self._immutable_capture is _IMMUTABLE_CAPTURE:
            # Internal comparison of immutable objects, bracketed by the
            # canonical owner. It supplies no default observation or grant.
            if self.git("rev-parse", "HEAD", limit=128, _code=True).strip() != self.code_commit:
                raise _CaptureFailure("SOURCE_CHANGED")
            return self.commit
        if (self.code_root != self.root or self.code_commit != self.commit) and self.git("rev-parse", "HEAD", limit=128, _code=True).strip() != self.code_commit:
            raise _CaptureFailure("SOURCE_CHANGED")
        if self._data_view is not None:
            self._data_view.check()
            return self._data_view.data_commit
        return self.git("rev-parse", "HEAD", limit=128).strip()

    def captured(self, path, limit=_DEFAULT_LIMIT, soft=False):
        commit = self.code_commit if path == "scripts/agentos.py" else self.commit
        return self.git("show", commit + ":" + path, limit=limit, soft=soft, _code=path == "scripts/agentos.py")

    def member(self, path):
        """Tree-entry check: None when absent, _IRREGULAR when not a plain blob."""
        raw = self.git("ls-tree", "-z", self.commit, "--", path, limit=16384)
        if not raw:
            return None
        if re.fullmatch(_MEMBER + re.escape(path) + "\x00", raw) is None:
            return _IRREGULAR
        return raw.split("\t", 1)[0].split(" ")[2]

    def committed_at(self, path):
        return _utc_clock(
            self.git("log", "-1", "--format=%cI", self.commit, "--", path, limit=8192)
        )

    def parse(self, module, path, text):
        record, body = module.parse_record(_CapturedRecord(text))
        record["_body"] = body
        if path == self.ws_path:
            problems = module.check_workstream(record, self.root / path, None)
        elif path.startswith("agentos/decisions/"):
            problems = module.check_decision(record, self.root / path)
        elif path.startswith("agentos/discoveries/"):
            problems = module.check_discovery(record, self.root / path)
        else:
            problems = module.check_handoff(record, self.root / path)
        if any(problem.hard for problem in problems):
            raise ValueError("record invalid")
        return record


@contextlib.contextmanager
def _parser_session(session, parser_text):
    """Run the captured Macro parser under an isolated, restored module id."""
    module = types.ModuleType("agentos_bound_project_knowledge_owner")
    module.__file__ = str(session.code_root / "scripts" / "agentos.py")
    name = module.__name__
    prior = sys.modules.get(name)
    original_path = list(sys.path)
    sys.modules[name] = module
    try:
        exec(compile(parser_text, module.__file__, "exec"), module.__dict__)
        yield module
    finally:
        sys.path[:] = original_path
        if prior is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = prior


def _display_name(basename, entry):
    safe = _clean_text(basename)
    if safe is not None:
        return safe
    # Invalid references stay opaque: the unsafe path is never revealed.
    return "sha256:" + hashlib.sha256(str(entry).encode("utf-8")).hexdigest()[:16]


def _row_origin(upload):
    if upload is None:
        return {"kind": "DECLARED_ARTIFACT", "actor_ref": None, "request_sha256": None}
    return {
        "kind": "PRINCIPAL_UPLOAD",
        "actor_ref": upload["origin"]["actor_ref"],
        "request_sha256": upload["origin"]["request_sha256"],
    }


def _valid_upload_entry(entry, key, artifacts):
    """Owner-frozen ``WS.project_files`` recipe; anything else never grants it."""
    if type(entry) is not dict or set(entry) != {
        "artifact_ref",
        "content_sha256",
        "display_name",
        "file_id",
        "media_type",
        "origin",
    }:
        return False
    file_id = entry["file_id"]
    if type(file_id) is not str or _SHA64.fullmatch(file_id) is None:
        return False
    media = entry["media_type"]
    if media == "text/markdown":
        suffix = ".md"
    elif media == "text/plain":
        suffix = ".txt"
    else:
        return False
    artifact_ref = entry["artifact_ref"]
    if type(artifact_ref) is not str:
        return False
    # The namespace is frozen to this workstream: another project's namespace
    # is refused even when a pointer to it exists.
    if artifact_ref != "agentos/project-files/WS-" + key + "/" + file_id + suffix:
        return False
    if artifact_ref not in artifacts:
        return False
    display = entry["display_name"]
    if (
        type(display) is not str
        or not 1 <= _ulen(display) <= MAX_DISPLAY_NAME
        or _CONTROL.search(display)
        or "/" in display
        or "\\" in display
        or display.startswith(".")
    ):
        return False
    if type(entry["content_sha256"]) is not str or _SHA64.fullmatch(entry["content_sha256"]) is None:
        return False
    origin = entry["origin"]
    if type(origin) is not dict or set(origin) != {"actor_ref", "kind", "request_sha256"}:
        return False
    if origin["kind"] != "PRINCIPAL_UPLOAD":
        return False
    actor = origin["actor_ref"]
    if type(actor) is not str or re.fullmatch(r"workspace:[0-9a-f]{64}", actor) is None:
        return False
    if type(origin["request_sha256"]) is not str or _SHA64.fullmatch(origin["request_sha256"]) is None:
        return False
    return True


def _upload_metadata(workstream, key):
    """Strict owner-frozen upload metadata; duplicates and conflicts refuse."""
    entries = workstream.get("project_files")
    if entries is None:
        return {}
    if type(entries) is not list or len(entries) > _MAX_FILES:
        raise _CaptureFailure("SOURCE_INVALID")
    artifacts = workstream.get("artifacts")
    artifacts = artifacts if type(artifacts) is list else []
    uploads = {}
    seen_ids = set()
    seen_paths = set()
    for entry in entries:
        if not _valid_upload_entry(entry, key, artifacts):
            raise _CaptureFailure("SOURCE_INVALID")
        if entry["file_id"] in seen_ids or entry["artifact_ref"] in seen_paths:
            raise _CaptureFailure("CONFLICT")
        seen_ids.add(entry["file_id"])
        seen_paths.add(entry["artifact_ref"])
        uploads[entry["artifact_ref"]] = entry
    return uploads


def _blob_size(session, blob):
    raw = session.git("cat-file", "-s", blob, limit=64).strip()
    if not raw.isdigit():
        return None
    return int(raw)


def _unsupported_row(session, entry, repository_key, path, state, upload):
    literal = entry if type(entry) is str else ""
    return {
        "source_ref": "project-file.v1."
        + _identity(repository_key or "", session.commit, session.work_ref, path or "", "", literal),
        "repository": repository_key,
        "path": path,
        "revision": None,
        "display_name": _display_name(posixpath.basename(path) if path else None, entry),
        "media_type": None,
        "content_sha256": upload["content_sha256"] if upload else None,
        "state": state,
        "origin": _row_origin(upload),
        "viewer_relation": VIEWER_RELATION,
    }


def _shape_row(session, path, blob, state, display, media, upload):
    return {
        "source_ref": "project-file.v1."
        + _identity("macro", session.commit, session.work_ref, path, blob or ""),
        "repository": "macro",
        "path": path,
        "revision": blob if blob else None,
        "display_name": display,
        "media_type": media,
        "content_sha256": upload["content_sha256"] if upload else None,
        "state": state,
        "origin": _row_origin(upload),
        "viewer_relation": VIEWER_RELATION,
    }


def _file_row_for(session, module, workstream, entry, upload):
    if type(entry) is not str or entry == "":
        return _unsupported_row(session, "", None, None, "SOURCE_INVALID", upload)
    try:
        resolved = module._resolve_path(entry, workstream)
    except _PARSE_FAULTS:
        resolved = None
    if resolved is None:
        # URLs and PREFIX:KEY citations are not repo paths: honest unsupported
        # metadata, never a guessed URL or a cross-repo read.
        return _unsupported_row(session, entry, None, None, "UNSUPPORTED_SOURCE", upload)
    repository_key, repo_relative = resolved
    if (
        type(repository_key) is not str
        or repository_key not in REPOSITORY_KEYS
        or type(repo_relative) is not str
    ):
        return _unsupported_row(session, entry, None, None, "UNSUPPORTED_SOURCE", upload)
    if repository_key != "macro":
        return _unsupported_row(session, entry, repository_key, repo_relative, "UNSUPPORTED_SOURCE", upload)
    if not _safe_macro_path(repo_relative):
        return _unsupported_row(session, entry, None, None, "SOURCE_INVALID", upload)
    if not repo_relative.endswith((".md", ".txt")):
        # Accepted directory, but outside the accepted document types.
        return _unsupported_row(session, entry, "macro", repo_relative, "UNSUPPORTED_SOURCE", upload)
    # Upload metadata carries the actual display_name; legacy rows use the
    # exact basename.
    display = upload["display_name"] if upload else _display_name(posixpath.basename(repo_relative), entry)
    media = "text/markdown" if repo_relative.endswith(".md") else "text/plain"
    blob = session.member(repo_relative)
    if blob is None:
        return _shape_row(session, repo_relative, None, "SOURCE_MISSING", display, media, upload)
    if blob is _IRREGULAR:
        return _shape_row(session, repo_relative, None, "SOURCE_INVALID", display, media, upload)
    size = _blob_size(session, blob)
    if size is None:
        return _shape_row(session, repo_relative, None, "SOURCE_INVALID", display, media, upload)
    if size > MAX_SOURCE_BODY:
        return _shape_row(session, repo_relative, blob, "CONTENT_OVER_BUDGET", display, media, upload)
    return _shape_row(session, repo_relative, blob, "READABLE", display, media, upload)


def _file_rows(session, module, workstream, key, uploads):
    """Canonical ``WS.artifacts`` literals in owner order, at most 32 rows.

    Listing never reads a body: ls-tree and cat-file size only.  The declared
    content SHA of an upload is carried as metadata and verified against the
    real bytes on open, never assumed here.
    """
    artifacts = workstream.get("artifacts")
    if artifacts is None:
        artifacts = []
    if type(artifacts) is not list:
        raise _CaptureFailure("SOURCE_INVALID")
    declared = len(artifacts)
    rows = []
    seen = set()
    for entry in artifacts[:_MAX_FILES]:
        upload = uploads.get(entry) if type(entry) is str else None
        row = _file_row_for(session, module, workstream, entry, upload)
        if row["source_ref"] in seen:
            continue
        seen.add(row["source_ref"])
        rows.append(row)
    listed = len(rows)
    omitted = max(0, declared - listed)
    coverage = {
        "state": "COMPLETE" if omitted == 0 else "PARTIAL",
        "declared": declared,
        "listed": listed,
        "omitted": omitted,
    }
    return rows, coverage


_TITLE_KEYS = {"DECISION": "question", "DISCOVERY": "claim", "HANDOFF": "mission"}
_AUTHORED_KEYS = {"DECISION": "decided_at", "DISCOVERY": "verified_at", "HANDOFF": None}


def _names_work(value, key, bare):
    """Parsed association: WS:<KEY> citations, or the bare key where the
    schema allows it (discovery scope).  Never a filename or title."""
    values = value if type(value) is list else ([value] if type(value) is str else [])
    for entry in values:
        if type(entry) is not str:
            continue
        if entry == "WS:" + key or (bare and entry == key):
            return True
    return False


def _record_row_for(session, path, blob, kind, title, authored, committed, preference):
    return {
        "source_ref": "project-record.v1."
        + _identity(REPOSITORY, session.commit, session.work_ref, path, blob),
        "path": path,
        "revision": blob,
        "kind": "PROJECT_PREFERENCE" if preference else kind,
        "title": title,
        "authored_at": authored,
        "committed_at": committed,
    }


def _record_rows(session, module, workstream, key, ws_row):
    """Bounded sample: the WS row plus explicit WS refs plus the last 128 record
    commits touching the canonical record directories.

    Association comes from parsed source fields (``affects``/``scope``/
    ``workstream``), never from a filename.  Authored dates are record source
    facts; ``committed_at`` is the actual Git clock normalized to UTC.
    Omission and invalid counts are exact; nothing is silently truncated, and
    valid candidates of other projects are neither matched, omitted nor
    invalid.
    """
    explicit = []
    for field, prefix, folder in (
        ("decisions", "DEC", "decisions/DEC-"),
        ("discoveries", "DSC", "discoveries/DSC-"),
    ):
        references = workstream.get(field)
        if references is None:
            continue
        if type(references) is not list:
            raise _CaptureFailure("SOURCE_INVALID")
        for reference in references:
            if type(reference) is str and reference.startswith(prefix + ":"):
                target = reference[len(prefix) + 1:]
                if _KEY_SHAPE.fullmatch(target):
                    explicit.append("agentos/" + folder + target + ".md")
    history = session.git(
        "log",
        "--max-count=128",
        "--format=",
        "--name-only",
        session.commit,
        "--",
        "agentos/decisions/",
        "agentos/discoveries/",
        "agentos/handoffs/",
        limit=_HISTORY_LIMIT,
    )
    candidates = list(
        dict.fromkeys(
            [session.ws_path] + explicit + [p for p in history.splitlines() if _RECORD_PATH.fullmatch(p)]
        )
    )
    selected = candidates[:MAX_SCANNED_RECORDS]
    rows = []
    invalid = 0
    pref_hits = 0
    for path in selected:
        if path == session.ws_path:
            rows.append(ws_row)
            continue
        blob = session.member(path)
        if blob is None:
            continue
        if blob is _IRREGULAR:
            invalid += 1
            continue
        text = session.captured(path, limit=_RECORD_LIMIT, soft=True)
        if text is None or _ulen(text) > MAX_SOURCE_BODY:
            invalid += 1
            continue
        try:
            record = session.parse(module, path, text)
        except _PARSE_FAULTS:
            invalid += 1
            continue
        kind = (
            "DECISION"
            if "/decisions/" in path
            else "DISCOVERY"
            if "/discoveries/" in path
            else "HANDOFF"
        )
        record_key = record.get("key")
        if kind == "DECISION" and record_key == session.preference_key:
            pref_hits += 1
        if kind == "DECISION":
            associated = _names_work(record.get("affects"), key, bare=False)
        elif kind == "DISCOVERY":
            associated = _names_work(record.get("scope"), key, bare=False)
        else:
            associated = _names_work(record.get("workstream"), key, bare=False)
        if not associated:
            continue
        preference_row = kind == "DECISION" and record_key == session.preference_key
        title = _clean_title(record.get(_TITLE_KEYS[kind]))
        if title is None:
            # Fallback: the record's own known key only, never generated prose.
            fallback = record_key if kind != "HANDOFF" else posixpath.basename(path)[:-3]
            title = _clean_title(fallback)
        if title is None:
            invalid += 1
            continue
        authored_field = _AUTHORED_KEYS[kind]
        authored = _authored_date(record.get(authored_field)) if authored_field else None
        rows.append(
            _record_row_for(
                session, path, blob, kind, title, authored,
                session.committed_at(path), preference_row,
            )
        )
    omitted = max(0, len(candidates) - len(selected))
    if len(rows) > MAX_MATCHED_RECORDS:
        omitted += len(rows) - MAX_MATCHED_RECORDS
        rows = rows[:MAX_MATCHED_RECORDS]
    coverage = {
        "state": "BOUNDED_SAMPLE",
        "scanned": len(selected),
        "matched": len(rows),
        "omitted": omitted,
        "invalid": invalid,
    }
    return rows, coverage, pref_hits


def _preference_unavailable(reason):
    return {"state": "UNAVAILABLE", "reason": reason, "source_ref": None, "revision": None}


def _preference(session, module, workstream, key, pref_hits):
    """Canonical communication preference; EMPTY only when genuinely absent.

    A valid record anchored to another work, a superseded record, a duplicate
    of the fixed key, or a missing WS pointer is a CONFLICT, never an EMPTY.
    """
    blob = session.member(session.preference_path)
    if blob is None:
        return {"state": "EMPTY", "source_ref": None, "revision": None}
    if blob is _IRREGULAR:
        return _preference_unavailable("SOURCE_INVALID")
    text = session.captured(session.preference_path, limit=_RECORD_LIMIT, soft=True)
    if text is None or _ulen(text) > MAX_SOURCE_BODY:
        return _preference_unavailable("CONTENT_OVER_BUDGET")
    try:
        record = session.parse(module, session.preference_path, text)
    except _PARSE_FAULTS:
        return _preference_unavailable("SOURCE_INVALID")
    if pref_hits > 1:
        return _preference_unavailable("CONFLICT")
    if record.get("superseded_by") or record.get("superseded") is True:
        return _preference_unavailable("CONFLICT")
    if record.get("key") != session.preference_key:
        return _preference_unavailable("SOURCE_INVALID")
    affects = record.get("affects")
    if type(affects) is not list or affects != ["WS:" + key]:
        # Anchored to exactly one other workstream is a valid record for other
        # work: conflict/mismatch here, never an invented EMPTY.
        return _preference_unavailable("CONFLICT")
    decisions = workstream.get("decisions")
    if type(decisions) is not list or "DEC:" + session.preference_key not in decisions:
        return _preference_unavailable("CONFLICT")
    payload = record.get("project_preference")
    answer = record.get("answer")
    if type(payload) is not dict or type(answer) is not str:
        return _preference_unavailable("SOURCE_INVALID")
    try:
        checked = validate_preference_payload(payload)
    except ContractInvalid:
        return _preference_unavailable("SOURCE_INVALID")
    if checked["work_ref"] != session.work_ref or checked["kind"] != "COMMUNICATION":
        return _preference_unavailable("CONFLICT")
    if checked["value"] != answer:
        return _preference_unavailable("CONFLICT")
    return {
        "state": "AVAILABLE",
        "source_ref": "project-record.v1."
        + _identity(REPOSITORY, session.commit, session.work_ref, session.preference_path, blob),
        "revision": blob,
        "value": checked["value"],
        "origin": checked["origin"],
        "last_edit": checked["last_edit"],
        "source": {
            "repository": REPOSITORY,
            "commit": session.commit,
            "path": session.preference_path,
            "revision": blob,
            "content_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "committed_at": session.committed_at(session.preference_path),
        },
    }


def _capture_index(macro_root, expected_macro_sha, work_ref, runner, timeout, canonical_data_view=None, code_root=None, code_commit=None, immutable_capture=None):
    """Regenerate the exact current catalogue metadata and member index.

    No file or record body is read here beyond the records the bounded sample
    must parse for association: the file list is ls-tree, cat-file size and
    blob SHA-1 only.  HEAD is verified before the first and after the last Git
    read, so a source change mid-capture fails closed with no private payload.
    """
    session = _Session(macro_root, expected_macro_sha, work_ref, runner, timeout, canonical_data_view, code_root, code_commit, immutable_capture)
    if session.head() != session.commit:
        raise _CaptureFailure("SOURCE_CHANGED")
    parser_text = session.captured("scripts/agentos.py", limit=_PARSER_LIMIT, soft=True)
    if parser_text is None or _ulen(parser_text) > _PARSER_LIMIT:
        raise _CaptureFailure("CONTENT_OVER_BUDGET")
    if session.head() != session.commit:
        raise _CaptureFailure("SOURCE_CHANGED")
    ws_blob = session.member(session.ws_path)
    if ws_blob is None:
        raise _CaptureFailure("RECORD_NOT_FOUND")
    if ws_blob is _IRREGULAR:
        raise _CaptureFailure("SOURCE_INVALID")
    ws_size = _blob_size(session, ws_blob)
    if ws_size is None:
        raise _CaptureFailure("SOURCE_INVALID")
    if ws_size > _WS_LIMIT:
        raise _CaptureFailure("CONTENT_OVER_BUDGET")
    ws_text = session.captured(session.ws_path, limit=_WS_LIMIT + 1, soft=True)
    if ws_text is None or _ulen(ws_text) > _WS_LIMIT:
        raise _CaptureFailure("CONTENT_OVER_BUDGET")
    with _parser_session(session, parser_text) as module:
        workstream = session.parse(module, session.ws_path, ws_text)
        title = workstream.get("title")
        if _clean_title(title) is None:
            raise _CaptureFailure("SOURCE_INVALID")
        repos = workstream.get("repos")
        if type(repos) is not list or "macro" not in repos:
            # This source is the Macro store; a workstream that does not
            # declare it is not a canonical subject for this reader.
            raise _CaptureFailure("SOURCE_INVALID")
        uploads = _upload_metadata(workstream, session.key)
        files, file_coverage = _file_rows(session, module, workstream, session.key, uploads)
        ws_row = {
            "source_ref": "project-record.v1."
            + _identity(REPOSITORY, session.commit, session.work_ref, session.ws_path, ws_blob),
            "path": session.ws_path,
            "revision": ws_blob,
            "kind": "WORKSTREAM",
            "title": title,
            "authored_at": None,
            "committed_at": session.committed_at(session.ws_path),
        }
        records, record_coverage, pref_hits = _record_rows(
            session, module, workstream, session.key, ws_row
        )
        preference = _preference(session, module, workstream, session.key, pref_hits)
    if session.head() != session.commit:
        raise _CaptureFailure("SOURCE_CHANGED")
    rows_by_ref = {}
    for row in files:
        rows_by_ref[row["source_ref"]] = {
            "path": row["path"],
            "state": row["state"],
            "revision": row["revision"],
            "content_sha256": row["content_sha256"],
            "media_type": row["media_type"],
            "title": row["display_name"],
            "committed_at": None,
        }
    for row in records:
        rows_by_ref[row["source_ref"]] = {
            "path": row["path"],
            "state": "READABLE",
            "revision": row["revision"],
            "content_sha256": None,
            "media_type": "text/markdown",
            "title": row["title"],
            "committed_at": row["committed_at"],
        }
    return {
        "session": session,
        "work_ref": session.work_ref,
        "title": title,
        "ws_text": ws_text,
        "files": files,
        "records": records,
        "file_coverage": file_coverage,
        "record_coverage": record_coverage,
        "preference": preference,
        "rows_by_ref": rows_by_ref,
    }


def capture_selected_project_data_closure(*, macro_root, code_root, code_commit,
                                        data_commit, work_ref, deadline):
    """Compare the actual finite reader inputs at C/N, never a path-prefix guess.

    Both index discovery passes use the configured parser and existing bounds.
    The plan reader records its own selected adoption/proposal/content captures.
    Missing members and literal tree entries preserve additions, deletions,
    renames and modes; generated commit-bound source references are excluded.
    The caller owns live permission/default/code fences. This returns DATA only.
    """
    stop=min(deadline,time.monotonic()+10.0)
    consumed=0
    manifests=[]
    for commit in (code_commit,data_commit):
        remaining=stop-time.monotonic()
        if remaining<=0:
            raise _CaptureFailure("SOURCE_UNAVAILABLE")
        index=_capture_index(macro_root,commit,work_ref,None,remaining,
            code_root=code_root,code_commit=code_commit,immutable_capture=_IMMUTABLE_CAPTURE)
        if (index['file_coverage']['omitted'] or index['record_coverage']['omitted']
                or index['record_coverage']['invalid']
                or any(row['state'] not in ('READABLE','SOURCE_MISSING') for row in index['files'])):
            raise _CaptureFailure("CONTENT_OVER_BUDGET")
        session=index['session']
        # All passes, including plan continuity, share this one original bound.
        session.deadline=stop
        paths={session.ws_path,session.preference_path}
        paths.update(row['path'] for row in index['files'] if row['repository']=='macro' and row['path'] is not None)
        paths.update(row['path'] for row in index['records'])
        members=[]
        for path in sorted(paths):
            if not _safe_macro_path(path):
                raise _CaptureFailure("SOURCE_INVALID")
            members.append([path,session.git('--literal-pathspecs','ls-tree','-z',commit,'--',path,limit=16384)])
        audit={}
        with _parser_session(session,session.captured('scripts/agentos.py',limit=_PARSER_LIMIT)) as owner:
            from control_plane.agentos_plan_continuity_capture import capture_plan_continuity
            capture_plan_continuity(owner=owner,git=lambda *args,**kw:session.git(*args,**kw),
                work_ref=work_ref,macro_sha=commit,
                workstream_source={'repository':REPOSITORY,'commit':commit,'path':session.ws_path,
                    'content_sha256':hashlib.sha256(index['ws_text'].encode()).hexdigest()},
                workstream_bytes=index['ws_text'].encode(),executable_macro_sha=code_commit,
                _data_closure=audit)
        if audit.get('state') not in ('CAPTURED','FIXED_READER_UNAVAILABLE'):
            raise _CaptureFailure("SOURCE_UNAVAILABLE")
        def without_issued_refs(value):
            if type(value) is list:return [without_issued_refs(v) for v in value]
            if type(value) is dict:
                return {k:without_issued_refs(v) for k,v in value.items() if k not in ('source_ref','source')}
            return value
        material=dict(members=members,workstream_sha256=hashlib.sha256(index['ws_text'].encode()).hexdigest(),
            files=without_issued_refs(index['files']),records=without_issued_refs(index['records']),
            file_coverage=index['file_coverage'],record_coverage=index['record_coverage'],
            preference=without_issued_refs(index['preference']),plan=audit)
        consumed+=session.consumed
        if consumed>_TOTAL_BUDGET or session.head()!=commit or time.monotonic()>=stop:
            raise _CaptureFailure("CONTENT_OVER_BUDGET")
        manifests.append(json.dumps(material,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode())
    if manifests[0]!=manifests[1]:
        raise _CaptureFailure("SOURCE_CHANGED")
    return hashlib.sha256(manifests[0]).hexdigest()


def _capture(macro_root, expected_macro_sha, work_ref, runner, timeout, unavailable, canonical_data_view=None, code_root=None, code_commit=None):
    """Shared wrapper: closed-reason mapping, never a partial success."""
    try:
        return _capture_index(macro_root, expected_macro_sha, work_ref, runner, timeout, canonical_data_view, code_root, code_commit), None
    except _CaptureFailure as failure:
        return None, unavailable(work_ref, _reason(failure))
    except (ImportError, SystemExit):
        return None, unavailable(work_ref, "SOURCE_UNAVAILABLE")
    except (
        OSError,
        ValueError,
        TypeError,
        KeyError,
        AttributeError,
        SyntaxError,
        RecursionError,
        OverflowError,
    ):
        return None, unavailable(work_ref, "SOURCE_INVALID")


def _emit(value, validate, unavailable):
    """Validate, then budget: at most 131072 UTF-8 bytes plus a newline."""
    try:
        checked = validate(value)
    except ContractInvalid:
        return unavailable("SOURCE_INVALID")
    encoded = json.dumps(checked, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    if len(encoded.encode("utf-8")) > _RESPONSE_LIMIT:
        return unavailable("RESPONSE_OVER_BUDGET")
    return checked


def read_project_knowledge_catalogue(
    *,
    macro_root: Path,
    expected_macro_sha: str,
    work_ref: str,
    runner=None,
    timeout: float = 10,
    _canonical_data_view=None,
    code_root=None,
    code_commit=None,
) -> dict:
    """Read the bounded project-knowledge catalogue for one workstream."""
    index, failed = _capture(
        macro_root, expected_macro_sha, work_ref, runner, timeout, unavailable_catalogue, _canonical_data_view, code_root, code_commit
    )
    if index is None:
        return failed
    session = index["session"]
    preference = index["preference"]
    value = {
        "schema": CATALOGUE_SCHEMA,
        "selection": {"work_ref": session.work_ref},
        "availability": "AVAILABLE",
        "reason_codes": [],
        "source": {
            "repository": REPOSITORY,
            "commit": session.commit,
            "workstream_sha256": hashlib.sha256(index["ws_text"].encode("utf-8")).hexdigest(),
        },
        "project": {
            "title": index["title"],
            "files": index["files"],
            "records": index["records"],
            "memory": {
                "state": preference["state"],
                "source_ref": preference["source_ref"],
                "revision": preference["revision"],
            },
            "coverage": {
                "files": index["file_coverage"],
                "records": index["record_coverage"],
            },
        },
    }
    return _emit(value, validate_catalogue, lambda reason: unavailable_catalogue(session.work_ref, reason))


def read_project_knowledge_source(
    *,
    macro_root: Path,
    expected_macro_sha: str,
    work_ref: str,
    source_ref: str,
    expected_revision: str,
    runner=None,
    timeout: float = 10,
    _canonical_data_view=None,
    code_root=None,
    code_commit=None,
) -> dict:
    """Open exactly one catalogue member by source_ref and pinned blob revision.

    The reference and revision select only a member of the freshly
    regenerated catalogue, never an arbitrary path, and both are checked
    before any body read.  A malformed reference or revision raises
    ``ContractInvalid``: no DTO can echo it honestly.
    """
    if type(source_ref) is not str or not any(
        source_ref.startswith(prefix) and _SHA64.fullmatch(source_ref[len(prefix):]) is not None
        for prefix in SOURCE_REF_PREFIXES
    ):
        raise ContractInvalid("source_ref must be project-file.v1. or project-record.v1. + 64 hex")
    if type(expected_revision) is not str or _SHA40.fullmatch(expected_revision) is None:
        raise ContractInvalid("expected_revision must be a 40-hex blob revision")
    index, failed = _capture(
        macro_root, expected_macro_sha, work_ref, runner, timeout,
        lambda selection_ref, *reason_codes: unavailable_source(selection_ref, source_ref, *reason_codes), _canonical_data_view, code_root, code_commit,
    )
    if index is None:
        return failed
    session = index["session"]
    member = index["rows_by_ref"].get(source_ref)
    if member is None:
        return unavailable_source(session.work_ref, source_ref, "RECORD_NOT_FOUND")
    state = member["state"]
    if state != "READABLE":
        # Unsupported, invalid, missing and over-budget members never open;
        # only READABLE rows carry a revision pin at all.
        reason = {
            "SOURCE_MISSING": "SOURCE_UNAVAILABLE",
            "SOURCE_INVALID": "SOURCE_INVALID",
            "CONTENT_OVER_BUDGET": "CONTENT_OVER_BUDGET",
            "UNSUPPORTED_SOURCE": "UNSUPPORTED_SOURCE",
        }.get(state, "SOURCE_UNAVAILABLE")
        return unavailable_source(session.work_ref, source_ref, reason)
    if member["revision"] != expected_revision:
        return unavailable_source(session.work_ref, source_ref, "SOURCE_CHANGED")
    text = session.captured(member["path"], limit=_RECORD_LIMIT, soft=True)
    if text is None or _ulen(text) > MAX_SOURCE_BODY:
        return unavailable_source(session.work_ref, source_ref, "CONTENT_OVER_BUDGET")
    if _CONTROL.search(text):
        # Only LF, CR and TAB may travel; every other C0, C1 and DEL refuse.
        return unavailable_source(session.work_ref, source_ref, "SOURCE_INVALID")
    content_sha256 = hashlib.sha256(text.encode("utf-8")).hexdigest()
    if session.head() != session.commit:
        return unavailable_source(session.work_ref, source_ref, "SOURCE_CHANGED")
    blob = session.member(member["path"])
    if blob is None or blob is _IRREGULAR or blob != member["revision"]:
        return unavailable_source(session.work_ref, source_ref, "SOURCE_CHANGED")
    size = _blob_size(session, blob)
    if size is None or size != _ulen(text):
        return unavailable_source(session.work_ref, source_ref, "SOURCE_CHANGED")
    if member["content_sha256"] is not None and member["content_sha256"] != content_sha256:
        return unavailable_source(session.work_ref, source_ref, "SOURCE_MISMATCH")
    committed_at = (
        member["committed_at"]
        if member.get("committed_at") is not None
        else session.committed_at(member["path"])
    )
    value = {
        "schema": SOURCE_SCHEMA,
        "selection": {"work_ref": session.work_ref, "source_ref": source_ref},
        "availability": "AVAILABLE",
        "reason_codes": [],
        "source": {
            "repository": REPOSITORY,
            "commit": session.commit,
            "path": member["path"],
            "revision": blob,
            "content_sha256": content_sha256,
            "committed_at": committed_at,
        },
        "document": {
            "title": member["title"],
            "media_type": member["media_type"],
            "content_utf8": text,
            "content_sha256": content_sha256,
        },
    }
    return _emit(value, validate_source, lambda reason: unavailable_source(session.work_ref, source_ref, reason))


def read_project_discovery_source(*, macro_root, expected_macro_sha, work_ref,
        discovery_ref, expected_source_commit, runner=None, timeout=10,
        _canonical_data_view=None, code_root=None, code_commit=None):
    """Open one current associated DSC without a catalogue-sample dependency."""
    from common.workspace_project_knowledge_read_contract import selection
    from common.workspace_project_knowledge_contract import (
        DISCOVERY_SOURCE_SCHEMA, validate_discovery_source, unavailable_discovery_source)
    selected = selection({"work_ref": work_ref, "discovery_ref": discovery_ref,
        "expected_source_commit": expected_source_commit}, operation="project_discovery_source")
    def unavailable(reason):
        return unavailable_discovery_source(work_ref, discovery_ref, reason)
    try:
        session = _Session(macro_root, expected_macro_sha, work_ref, runner, timeout,
            _canonical_data_view, code_root, code_commit)
        if session.commit != expected_source_commit or session.head() != session.commit:
            raise _CaptureFailure("SOURCE_CHANGED")
        path = "agentos/discoveries/DSC-" + discovery_ref[4:] + ".md"
        parser = session.captured("scripts/agentos.py", limit=_PARSER_LIMIT, soft=True)
        if parser is None or _ulen(parser) > _PARSER_LIMIT:
            raise _CaptureFailure("CONTENT_OVER_BUDGET")
        captured = {}
        for name, limit in ((session.ws_path, _WS_LIMIT), (path, MAX_SOURCE_BODY)):
            blob = session.member(name)
            if blob is None:
                raise _CaptureFailure("RECORD_NOT_FOUND")
            if blob is _IRREGULAR:
                raise _CaptureFailure("SOURCE_INVALID")
            size = _blob_size(session, blob)
            if size is None or size > limit:
                raise _CaptureFailure("CONTENT_OVER_BUDGET")
            text = session.captured(name, limit=limit + 1, soft=True)
            if text is None or _ulen(text) > limit:
                raise _CaptureFailure("CONTENT_OVER_BUDGET")
            if _CONTROL.search(text) or _ulen(text) != size:
                raise _CaptureFailure("SOURCE_INVALID")
            raw = text.encode("utf-8")
            if hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest() != blob:
                raise _CaptureFailure("SOURCE_MISMATCH")
            captured[name] = (text, blob)
        ws_text, ws_blob = captured[session.ws_path]
        text, blob = captured[path]
        with _parser_session(session, parser) as module:
            # The pinned canonical parser owns duplicate/alias and record laws.
            # No complete-reference qualification is implied by this read.
            parse = getattr(module, "parse_project_discovery_reference_text", None)
            if not callable(parse):
                raise _CaptureFailure("SOURCE_INVALID")
            try:
                ws, record = parse(ws_text), parse(text)
            except (*_PARSE_FAULTS, module.yaml.YAMLError):
                raise _CaptureFailure("SOURCE_INVALID") from None
            if (ws.get("key") != session.key or record.get("key") != discovery_ref[4:]
                    or type(ws.get("repos")) is not list or "macro" not in ws["repos"]
                    or not _names_work(record.get("scope"), session.key, bare=False)
                    or any(problem.hard for problem in module.check_workstream(ws, session.root / session.ws_path, None))
                    or any(problem.hard for problem in module.check_discovery(record, session.root / path))):
                raise _CaptureFailure("SOURCE_INVALID")
            title = _clean_title(record.get("claim")) or _clean_title(record["key"])
            if title is None:
                raise _CaptureFailure("SOURCE_INVALID")
        committed_at = session.committed_at(path)
        if (session.head() != session.commit or session.member(path) != blob
                or session.member(session.ws_path) != ws_blob or session.head() != session.commit):
            raise _CaptureFailure("SOURCE_CHANGED")
        content_sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
        value = {"schema": DISCOVERY_SOURCE_SCHEMA,
            "selection": {"work_ref": work_ref, "discovery_ref": discovery_ref},
            "availability": "AVAILABLE", "reason_codes": [],
            "source": {"repository": REPOSITORY, "commit": session.commit, "path": path,
                "revision": blob, "content_sha256": content_sha, "committed_at": committed_at,
                "workstream_sha256": hashlib.sha256(ws_text.encode("utf-8")).hexdigest()},
            "document": {"title": title, "media_type": "text/markdown", "content_utf8": text,
                "content_sha256": content_sha}}
        return _emit(value, validate_discovery_source, unavailable)
    except _CaptureFailure as failure:
        return unavailable(_reason(failure))
    except _PARSE_FAULTS:
        return unavailable("SOURCE_INVALID")


def read_project_communication_preference(
    *,
    macro_root: Path,
    expected_macro_sha: str,
    work_ref: str,
    runner=None,
    timeout: float = 10,
    _canonical_data_view=None,
    code_root=None,
    code_commit=None,
) -> dict:
    """Read the project communication preference; EMPTY only when genuinely absent."""
    index, failed = _capture(
        macro_root, expected_macro_sha, work_ref, runner, timeout, unavailable_memory, _canonical_data_view, code_root, code_commit
    )
    if index is None:
        return failed
    preference = index["preference"]
    if preference["state"] == "EMPTY":
        return empty_memory(index["work_ref"])
    if preference["state"] == "UNAVAILABLE":
        return unavailable_memory(index["work_ref"], preference.get("reason", "SOURCE_UNAVAILABLE"))
    value = {
        "schema": PREFERENCE_SCHEMA,
        "selection": {"work_ref": index["work_ref"]},
        "availability": "AVAILABLE",
        "reason_codes": [],
        "source": preference["source"],
        "memory": {
            "value": preference["value"],
            "origin": preference["origin"],
            "last_edit": preference["last_edit"],
        },
    }
    return _emit(value, validate_memory, lambda reason: unavailable_memory(index["work_ref"], reason))

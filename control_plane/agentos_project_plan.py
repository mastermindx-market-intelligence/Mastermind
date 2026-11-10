"""Canonical Agent OS project-plan acquisition through its installed source owner.

This module creates no plan store, adoption authority, parser, or Runtime work.
Public selectors never choose a repository, path, interpreter, or source revision.
"""
from __future__ import annotations

import hashlib
import re
import sys
import time
import types
from pathlib import Path

from control_plane.ceo_boot_packet import bounded_subprocess_runner

_SOURCE_ROOT = Path(__file__).resolve().parents[1]
_RECORD_BYTES = 262144
_OWNER_BYTES = 1048576
_HISTORY_LOG_BYTES = 8192
_HISTORY_BATCH_BYTES = 8 * _RECORD_BYTES + _HISTORY_LOG_BYTES


class ProjectPlanSourceUnavailable(ValueError):
    pass


def _parse_history_log(log):
    """Validated (commit, committed_at) selectors from one bounded log capture.

    Order is the log order, newest first; repeated exact refs are collapsed to
    their first occurrence so one batch request carries each selector once.
    Conflicting dates for one immutable commit are unavailable source evidence.
    """
    from datetime import datetime
    selectors = []
    lines = log.splitlines()
    if len(lines) > 8:
        raise ProjectPlanSourceUnavailable("SOURCE_UNAVAILABLE")
    observed_dates = {}
    for line in lines:
        fields = line.split("\x00")
        if len(fields) != 3 or fields[2] != "" or re.fullmatch(r"[0-9a-f]{40}", fields[0]) is None:
            raise ProjectPlanSourceUnavailable("SOURCE_UNAVAILABLE")
        try:
            stamp = datetime.fromisoformat(fields[1].replace("Z", "+00:00"))
        except (ValueError, OverflowError):
            raise ProjectPlanSourceUnavailable("SOURCE_UNAVAILABLE") from None
        if stamp.utcoffset() is None:
            raise ProjectPlanSourceUnavailable("SOURCE_UNAVAILABLE")
        if fields[0] in observed_dates:
            if observed_dates[fields[0]] != fields[1]:
                raise ProjectPlanSourceUnavailable("SOURCE_UNAVAILABLE")
            continue
        observed_dates[fields[0]] = fields[1]
        selectors.append((fields[0], fields[1]))
    return selectors


def _history_request(selectors, path):
    """One fixed batch request line per selector, <commit>:<path>, in order."""
    if (len(selectors) > 8 or re.fullmatch(
            r"agentos/workstreams/WS-[A-Z0-9]+(?:-[A-Z0-9]+)*\.md", path) is None):
        raise ProjectPlanSourceUnavailable("SOURCE_UNAVAILABLE")
    return "".join(commit + ":" + path + "\n" for commit, _ in selectors).encode("utf-8")


def _parse_history_batch(selectors, stream):
    """Strictly decode one request-local git cat-file --batch response.

    The stream must be exactly one blob per selector, in request order: a
    40-hex object header, the "blob" type, a decimal byte size within the
    per-record bound, the object bytes, one newline, and nothing else. The
    echoed object id must be the actual SHA-1 identity of the delivered bytes.
    Any other shape -- missing, wrong type, truncated, oversized, extra
    output, non-UTF-8 -- raises, so history never becomes partial.
    """
    try:
        buffer = stream.encode("utf-8")
    except UnicodeEncodeError:
        raise ProjectPlanSourceUnavailable("SOURCE_UNAVAILABLE") from None
    if len(selectors) > 8:
        raise ProjectPlanSourceUnavailable("SOURCE_UNAVAILABLE")
    revisions = []
    offset = 0
    for commit, committed_at in selectors:
        newline = buffer.find(b"\n", offset)
        if newline < 0:
            raise ProjectPlanSourceUnavailable("SOURCE_UNAVAILABLE")
        header = buffer[offset:newline]
        offset = newline + 1
        match = re.fullmatch(rb"([0-9a-f]{40}) blob (0|[1-9][0-9]*)", header)
        if match is None:
            raise ProjectPlanSourceUnavailable("SOURCE_UNAVAILABLE")
        size = int(match.group(2))
        if size > _RECORD_BYTES or offset + size >= len(buffer) or buffer[offset + size] != 0x0A:
            raise ProjectPlanSourceUnavailable("SOURCE_UNAVAILABLE")
        raw = buffer[offset:offset + size]
        offset += size + 1
        if hashlib.sha1(b"blob " + match.group(2) + b"\0" + raw).hexdigest() != match.group(1).decode("ascii"):
            raise ProjectPlanSourceUnavailable("SOURCE_UNAVAILABLE")
        revisions.append({"commit": commit, "committed_at": committed_at,
            "content_sha256": hashlib.sha256(raw).hexdigest()})
    if offset != len(buffer):
        raise ProjectPlanSourceUnavailable("SOURCE_UNAVAILABLE")
    return revisions


class AgentOsProjectPlanReader:
    """A core facade issued only by the existing sealed packet collector."""

    def __init__(self, *, macro_root: Path):
        self._macro_root = Path(macro_root)
        if not self._macro_root.is_absolute():
            raise ValueError("project plan source must be absolute")
        self._installed_context_owner = None
        self._installed_context_binding = None
        self._installed_reader_binding = None

    @staticmethod
    def _context_binding(owner):
        return tuple(getattr(owner, name) for name in (
            "_source_root", "_macro_root", "_code_root", "_python",
            "_expected_source_sha", "_allow_synthetic_fixture",
        ))

    def read(self, *, work_ref: str, deadline=None):
        from control_plane.installed_project_read_binding import (
            InstalledProjectReadUnavailable, read_installed_project_binding,
        )
        try:
            return read_installed_project_binding(self, kind="project_plan", work_ref=work_ref,
                **({"deadline": deadline} if deadline is not None else {}))
        except InstalledProjectReadUnavailable:
            raise ProjectPlanSourceUnavailable("SOURCE_UNAVAILABLE") from None


def read_from_macro_owner(*, macro_root: Path, expected_macro_sha: str,
                          work_ref: str, timeout: float = 10.0, runner=None,
                          include_continuity: bool = False, _canonical_data_view=None,
                          code_root: Path | None = None, code_commit: str | None = None,
                          _discovery_observed_at_ms: int | None = None):
    """Fixed child entry used inside the collector's pre/post seal bracket.

    Macro's actual parser and validator consume bounded captured bytes. No
    frontend parser interprets YAML, and no caller-selected file is opened.
    """
    from common.workspace_project_plan_contract import validate_selection, validate_source, unavailable
    from control_plane.workspace_project_plan import project_workstream_plan
    import re
    selected = validate_selection({"work_ref": work_ref})
    if (_discovery_observed_at_ms is not None
            and (type(_discovery_observed_at_ms) is not int or not 0 < _discovery_observed_at_ms <= 9007199254740991
                 or code_root is None or include_continuity)):
        raise ProjectPlanSourceUnavailable("SOURCE_UNAVAILABLE")
    if (not Path(macro_root).is_absolute()
            or type(expected_macro_sha) is not str
            or type(include_continuity) is not bool
            or re.fullmatch(r"[0-9a-f]{40}", expected_macro_sha) is None
            or type(timeout) not in (int, float) or not 0 < timeout <= 15):
        raise ProjectPlanSourceUnavailable("SOURCE_UNAVAILABLE")
    root = Path(macro_root)
    if (code_root is None) != (code_commit is None):
        raise ProjectPlanSourceUnavailable("SOURCE_UNAVAILABLE")
    code_sha, executable_root = expected_macro_sha, root
    if code_root is not None:
        if not Path(code_root).is_absolute() or type(code_commit) is not str or re.fullmatch(r"[0-9a-f]{40}", code_commit) is None:
            raise ProjectPlanSourceUnavailable("SOURCE_UNAVAILABLE")
        code_sha, executable_root = code_commit, Path(code_root)
    if _canonical_data_view is not None:
        from control_plane.project_canonical_data import CanonicalProjectDataView
        if (type(_canonical_data_view) is not CanonicalProjectDataView
                or _canonical_data_view._root != root
                or _canonical_data_view.data_commit != expected_macro_sha):
            raise ProjectPlanSourceUnavailable("SOURCE_UNAVAILABLE")
        _canonical_data_view.check()
        if code_root is not None and (Path(code_root) != _canonical_data_view._code_root
                                      or code_commit != _canonical_data_view.code_commit):
            raise ProjectPlanSourceUnavailable("SOURCE_UNAVAILABLE")
        code_sha, executable_root = _canonical_data_view.code_commit, _canonical_data_view._code_root

    def current():
        if ((executable_root != root or code_sha != expected_macro_sha)
                and code_git("rev-parse", "HEAD").strip() != code_sha):
            return False
        if _canonical_data_view is not None:
            _canonical_data_view.check()
            return True
        return git("rev-parse", "HEAD").strip() == expected_macro_sha
    path = "agentos/workstreams/WS-" + work_ref[3:] + ".md"
    deadline = time.monotonic() + timeout
    run = runner or bounded_subprocess_runner

    def git_at(repository, *args, limit=_RECORD_BYTES, input_bytes=None):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ProjectPlanSourceUnavailable("SOURCE_UNAVAILABLE")
        options = {} if input_bytes is None else {"input_bytes": input_bytes}
        from control_plane.project_canonical_data import local_git_environment
        value = run(["git", "--no-optional-locks", "--no-replace-objects", "-C", str(repository), *args],
                    cwd=repository, timeout=remaining, max_bytes=limit, env=local_git_environment(), **options)
        if (not isinstance(value, dict) or value.get("code") != 0
                or type(value.get("stdout")) is not str
                or any(value.get(flag) is True for flag in ("timed_out", "limit_exceeded", "invalid_utf8"))):
            raise ProjectPlanSourceUnavailable("SOURCE_UNAVAILABLE")
        return value["stdout"]

    def git(*args, **options):
        return git_at(root, *args, **options)

    def code_git(*args, **options):
        return git_at(executable_root, *args, **options)

    def captured(relative, limit, *, executable=False):
        # Parent collector established the immutable source root. This fixed
        # Git-object read avoids following mutable filesystem names in a parser.
        commit = code_sha if executable else expected_macro_sha
        if executable:
            return code_git("show", commit + ":" + relative, limit=limit)
        return git("show", commit + ":" + relative, limit=limit)

    try:
        if not current():
            return unavailable(work_ref, "SOURCE_CHANGED")
        membership = git("ls-tree", "-z", expected_macro_sha, "--", path)
        if not membership:
            return unavailable(work_ref, "RECORD_NOT_FOUND")
        if re.fullmatch(r"100644 blob [0-9a-f]{40}\t" + re.escape(path) + "\x00", membership) is None:
            return unavailable(work_ref, "RECORD_INVALID")
        text = captured(path, _RECORD_BYTES)
        parser_text = captured("scripts/agentos.py", _OWNER_BYTES, executable=True)
        owner = types.ModuleType("agentos_bound_plan_source")
        owner.__file__ = str(executable_root / "scripts/agentos.py")
        prior = sys.modules.get(owner.__name__)
        sys.modules[owner.__name__] = owner
        original_path = list(sys.path)
        try:
            exec(compile(parser_text, owner.__file__, "exec"), owner.__dict__)

            class CapturedRecord:
                def read_text(self, *, encoding):
                    if encoding != "utf-8":
                        raise ValueError("record encoding refused")
                    return text

            record, _body = owner.parse_record(CapturedRecord())
            problems = owner.check_workstream(record, root / path, None)
            if any(problem.hard for problem in problems):
                return unavailable(work_ref, "RECORD_INVALID")
            if _discovery_observed_at_ms is not None:
                # A selected metadata projection uses the very same captured
                # canonical parser/state builder. It is a separate fixed child
                # response, never an extra field on the public Plan contract.
                from control_plane.agentos_project_discovery import compile_captured_record
                source = validate_source({"repository": "mastermindx-market-intelligence/macro",
                    "commit": expected_macro_sha, "path": path,
                    "content_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()}, work_ref)
                code_source = {"repository": source["repository"], "commit": code_sha,
                    "path": "scripts/agentos.py", "content_sha256": hashlib.sha256(parser_text.encode("utf-8")).hexdigest()}
                result = compile_captured_record(owner=owner, record=record, source=source,
                    code_source=code_source, data_root=root,
                    observed_at_ms=_discovery_observed_at_ms, git=git)
                if not current():
                    raise ProjectPlanSourceUnavailable("SOURCE_CHANGED")
                return result
        finally:
            sys.path[:] = original_path
            if prior is None:
                sys.modules.pop(owner.__name__, None)
            else:
                sys.modules[owner.__name__] = prior
        source = validate_source({"repository": "mastermindx-market-intelligence/macro",
            "commit": expected_macro_sha, "path": path,
            "content_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()}, work_ref)
        value = project_workstream_plan(record, work_ref=work_ref, source=source)
        if value.get("availability") == "AVAILABLE":
            try:
                selectors = _parse_history_log(git("log", "--max-count=8",
                    "--format=%H%x00%cI%x00", expected_macro_sha, "--", path,
                    limit=_HISTORY_LOG_BYTES))
                if selectors:
                    # One request-local batch read replaces the per-revision
                    # historical capture, inside the same cumulative deadline.
                    stream = git("cat-file", "--batch",
                        input_bytes=_history_request(selectors, path),
                        limit=_HISTORY_BATCH_BYTES)
                    value["plan"]["version_history"] = {"state": "AVAILABLE",
                        "kind": "GIT_RECORD_REVISIONS",
                        "revisions": _parse_history_batch(selectors, stream)}
            except (ProjectPlanSourceUnavailable, ValueError, OverflowError):
                # Missing history never fabricates adoption or makes available
                # current authored plan content disappear.
                value["plan"]["version_history"] = {"state": "UNAVAILABLE", "reason": "SOURCE_UNAVAILABLE"}
        if not current():
            return unavailable(work_ref, "SOURCE_CHANGED")
        if include_continuity and value.get("availability") == "AVAILABLE":
            from control_plane.agentos_plan_continuity_capture import capture_plan_continuity
            from common.project_plan_continuity_contract import compose_body_v2
            continuity = capture_plan_continuity(owner=owner, git=git, work_ref=work_ref,
                macro_sha=expected_macro_sha, workstream_source=source, workstream_bytes=text.encode("utf-8"),
                executable_macro_sha=code_sha, code_git=code_git)
            value = compose_body_v2(value, continuity, authored_bytes=text.encode("utf-8"))
            if not current():
                return unavailable(work_ref, "SOURCE_CHANGED")
        from common.executive_workspace_contract import bounded_canonical
        from common.workspace_project_plan_contract import MAX_RESPONSE_BYTES
        try:
            bounded_canonical({"ok": True, "result": value}, limit=MAX_RESPONSE_BYTES - 1)
        except ValueError:
            return unavailable(work_ref, "CONTENT_OVER_BUDGET")
        from common.workspace_project_plan_contract import validate_body
        return validate_body(value)
    except ProjectPlanSourceUnavailable:
        return unavailable(work_ref, "SOURCE_UNAVAILABLE")
    except (ImportError, SystemExit):
        return unavailable(work_ref, "SOURCE_UNAVAILABLE")
    except (OSError, ValueError, TypeError, KeyError, AttributeError, SyntaxError,
            RecursionError, OverflowError):
        return unavailable(work_ref, "RECORD_INVALID")

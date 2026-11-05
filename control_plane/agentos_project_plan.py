"""Canonical Agent OS project-plan acquisition through its installed source owner.

This module creates no plan store, adoption authority, parser, or Runtime work.
Public selectors never choose a repository, path, interpreter, or source revision.
"""
from __future__ import annotations

import hashlib
import sys
import time
import types
from pathlib import Path

from control_plane.ceo_boot_packet import bounded_subprocess_runner

_SOURCE_ROOT = Path(__file__).resolve().parents[1]
_RECORD_BYTES = 262144
_OWNER_BYTES = 1048576


class ProjectPlanSourceUnavailable(ValueError):
    pass


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

    def read(self, *, work_ref: str):
        from control_plane.installed_project_read_binding import (
            InstalledProjectReadUnavailable, read_installed_project_binding,
        )
        try:
            return read_installed_project_binding(self, kind="project_plan", work_ref=work_ref)
        except InstalledProjectReadUnavailable:
            raise ProjectPlanSourceUnavailable("SOURCE_UNAVAILABLE") from None


def read_from_macro_owner(*, macro_root: Path, expected_macro_sha: str,
                          work_ref: str, timeout: float = 10.0, runner=None,
                          include_continuity: bool = False):
    """Fixed child entry used inside the collector's pre/post seal bracket.

    Macro's actual parser and validator consume bounded captured bytes. No
    frontend parser interprets YAML, and no caller-selected file is opened.
    """
    from common.workspace_project_plan_contract import validate_selection, validate_source, unavailable
    from control_plane.workspace_project_plan import project_workstream_plan
    import re
    selected = validate_selection({"work_ref": work_ref})
    if (not Path(macro_root).is_absolute()
            or type(expected_macro_sha) is not str
            or type(include_continuity) is not bool
            or re.fullmatch(r"[0-9a-f]{40}", expected_macro_sha) is None
            or type(timeout) not in (int, float) or not 0 < timeout <= 15):
        raise ProjectPlanSourceUnavailable("SOURCE_UNAVAILABLE")
    root = Path(macro_root)
    path = "agentos/workstreams/WS-" + work_ref[3:] + ".md"
    deadline = time.monotonic() + timeout
    run = runner or bounded_subprocess_runner

    def git(*args, limit=_RECORD_BYTES, input_bytes=None):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ProjectPlanSourceUnavailable("SOURCE_UNAVAILABLE")
        options = {} if input_bytes is None else {"input_bytes": input_bytes}
        value = run(["git", "--no-optional-locks", "--no-replace-objects", "-C", str(root), *args],
                    cwd=root, timeout=remaining, max_bytes=limit, **options)
        if (not isinstance(value, dict) or value.get("code") != 0
                or type(value.get("stdout")) is not str
                or any(value.get(flag) is True for flag in ("timed_out", "limit_exceeded", "invalid_utf8"))):
            raise ProjectPlanSourceUnavailable("SOURCE_UNAVAILABLE")
        return value["stdout"]

    def captured(relative, limit):
        # Parent collector established the immutable source root. This fixed
        # Git-object read avoids following mutable filesystem names in a parser.
        return git("show", expected_macro_sha + ":" + relative, limit=limit)

    try:
        if git("rev-parse", "HEAD").strip() != expected_macro_sha:
            return unavailable(work_ref, "SOURCE_CHANGED")
        membership = git("ls-tree", "-z", expected_macro_sha, "--", path)
        if not membership:
            return unavailable(work_ref, "RECORD_NOT_FOUND")
        if re.fullmatch(r"100644 blob [0-9a-f]{40}\t" + re.escape(path) + "\x00", membership) is None:
            return unavailable(work_ref, "RECORD_INVALID")
        text = captured(path, _RECORD_BYTES)
        parser_text = captured("scripts/agentos.py", _OWNER_BYTES)
        owner = types.ModuleType("agentos_bound_plan_source")
        owner.__file__ = str(root / "scripts/agentos.py")
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
            from datetime import datetime
            try:
                log = git("log", "--max-count=8", "--format=%H%x00%cI%x00",
                          expected_macro_sha, "--", path, limit=8192)
                revisions = []
                for line in log.splitlines():
                    fields = line.split("\x00")
                    if (len(fields) != 3 or fields[2] != ""
                            or re.fullmatch(r"[0-9a-f]{40}", fields[0]) is None
                            or datetime.fromisoformat(fields[1].replace("Z", "+00:00")).utcoffset() is None):
                        raise ProjectPlanSourceUnavailable("SOURCE_UNAVAILABLE")
                    raw = git("show", fields[0] + ":" + path)
                    revisions.append({"commit": fields[0], "committed_at": fields[1],
                        "content_sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest()})
                if revisions:
                    value["plan"]["version_history"] = {"state": "AVAILABLE",
                        "kind": "GIT_RECORD_REVISIONS", "revisions": revisions}
            except (ProjectPlanSourceUnavailable, ValueError, OverflowError):
                # Missing history never fabricates adoption or makes available
                # current authored plan content disappear.
                value["plan"]["version_history"] = {"state": "UNAVAILABLE", "reason": "SOURCE_UNAVAILABLE"}
        if git("rev-parse", "HEAD").strip() != expected_macro_sha:
            return unavailable(work_ref, "SOURCE_CHANGED")
        if include_continuity and value.get("availability") == "AVAILABLE":
            from control_plane.agentos_plan_continuity_capture import capture_plan_continuity
            from common.project_plan_continuity_contract import compose_body_v2
            continuity = capture_plan_continuity(owner=owner, git=git, work_ref=work_ref,
                macro_sha=expected_macro_sha, workstream_source=source, workstream_bytes=text.encode("utf-8"))
            value = compose_body_v2(value, continuity, authored_bytes=text.encode("utf-8"))
            if git("rev-parse", "HEAD").strip() != expected_macro_sha:
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

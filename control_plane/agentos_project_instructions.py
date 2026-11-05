"""Canonical standing-instruction content through the incumbent sealed reader.

No instruction state, scheduling, permission or admission authority is projected.
The fixed child consumes only exact Git-owned parser/projector/record bytes.
"""
from __future__ import annotations

import hashlib
import math
from pathlib import Path
import re
import sys
import time
import types

from control_plane.ceo_boot_packet import bounded_subprocess_runner

_SOURCE_ROOT = Path(__file__).resolve().parents[1]


class ProjectInstructionsSourceUnavailable(ValueError):
    pass


class AgentOsProjectInstructionsReader:
    def __init__(self, *, macro_root: Path):
        self._macro_root = Path(macro_root)
        if not self._macro_root.is_absolute():
            raise ValueError("instruction source must be absolute")
        self._installed_context_owner = None
        self._installed_context_binding = None
        self._installed_reader_binding = None

    @staticmethod
    def _context_binding(owner):
        return tuple(getattr(owner, name) for name in (
            "_source_root", "_macro_root", "_code_root", "_python", "_expected_source_sha", "_allow_synthetic_fixture"))

    def read(self, *, work_ref: str):
        from control_plane.installed_project_read_binding import InstalledProjectReadUnavailable, read_installed_project_binding
        try:
            return read_installed_project_binding(self, kind="project_instructions", work_ref=work_ref)
        except InstalledProjectReadUnavailable:
            raise ProjectInstructionsSourceUnavailable("SOURCE_UNAVAILABLE") from None


def read_from_macro_owner(*, macro_root: Path, expected_macro_sha: str,
                          work_ref: str, timeout: float = 10.0, runner=None):
    from common.workspace_project_instructions_contract import from_canonical_projection, unavailable
    from common.workspace_project_plan_contract import validate_selection, validate_source
    selected = validate_selection({"work_ref": work_ref})
    if (not Path(macro_root).is_absolute() or type(expected_macro_sha) is not str
            or re.fullmatch(r"[0-9a-f]{40}", expected_macro_sha) is None
            or type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0 < timeout <= 15):
        raise ProjectInstructionsSourceUnavailable("SOURCE_UNAVAILABLE")
    root = Path(macro_root)
    deadline = time.monotonic() + timeout
    run = runner or bounded_subprocess_runner
    consumed = 0

    def git(*args, limit=262144):
        nonlocal consumed
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ProjectInstructionsSourceUnavailable("SOURCE_UNAVAILABLE")
        result = run(["git", "--no-optional-locks", "--no-replace-objects", "-C", str(root), *args],
            cwd=root, timeout=remaining, max_bytes=limit)
        if (type(result) is not dict or result.get("code") != 0 or type(result.get("stdout")) is not str
                or any(result.get(flag) is True for flag in ("timed_out", "limit_exceeded", "invalid_utf8"))):
            raise ProjectInstructionsSourceUnavailable("SOURCE_UNAVAILABLE")
        value = result["stdout"]
        consumed += len(value.encode("utf-8"))
        if consumed > 2 * 1048576:
            raise ProjectInstructionsSourceUnavailable("CONTENT_OVER_BUDGET")
        return value

    def capture(relative, limit):
        membership = git("ls-tree", "-z", expected_macro_sha, "--", relative, limit=4096)
        if re.fullmatch(r"100644 blob [0-9a-f]{40}\t" + re.escape(relative) + "\x00", membership) is None:
            raise ProjectInstructionsSourceUnavailable("SOURCE_UNAVAILABLE")
        return git("show", expected_macro_sha + ":" + relative, limit=limit)

    modules = []
    original_path = list(sys.path)
    try:
        if git("rev-parse", "HEAD").strip() != expected_macro_sha:
            return unavailable(work_ref, "SOURCE_CHANGED")
        path = "agentos/workstreams/WS-" + work_ref[3:] + ".md"
        membership = git("ls-tree", "-z", expected_macro_sha, "--", path, limit=4096)
        if not membership:
            return unavailable(work_ref, "RECORD_NOT_FOUND")
        if re.fullmatch(r"100644 blob [0-9a-f]{40}\t" + re.escape(path) + "\x00", membership) is None:
            return unavailable(work_ref, "RECORD_INVALID")
        text = capture(path, 262144)
        owner_modules = []
        for name, relative in (("agentos_bound_instruction_parser", "scripts/agentos.py"),
                               ("agentos_bound_instruction_projector", "scripts/agentos_standing_instructions.py")):
            code = capture(relative, 1048576)
            module = types.ModuleType(name)
            module.__file__ = str(root / relative)
            modules.append((name, sys.modules.get(name)))
            sys.modules[name] = module
            exec(compile(code, module.__file__, "exec"), module.__dict__)
            owner_modules.append(module)
        parser, projector = owner_modules

        class CapturedRecord:
            def read_text(self, *, encoding):
                if encoding != "utf-8":
                    raise ValueError("record encoding refused")
                return text

        record, _ = parser.parse_record(CapturedRecord())
        problems = parser.check_workstream(record, root / path, None)
        if any(problem.hard for problem in problems):
            return unavailable(work_ref, "RECORD_INVALID")
        source = validate_source({"repository": "mastermindx-market-intelligence/macro", "commit": expected_macro_sha,
            "path": path, "content_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()}, work_ref)
        body = from_canonical_projection(projector.project_standing_instructions(record, source), selected)
        if git("rev-parse", "HEAD").strip() != expected_macro_sha:
            return unavailable(work_ref, "SOURCE_CHANGED")
        return body
    except (ValueError, TypeError, KeyError, AttributeError, ImportError, SystemExit, UnicodeError, RecursionError, SyntaxError):
        return unavailable(work_ref, "SOURCE_UNAVAILABLE")
    finally:
        sys.path[:] = original_path
        for name, previous in reversed(modules):
            if previous is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous

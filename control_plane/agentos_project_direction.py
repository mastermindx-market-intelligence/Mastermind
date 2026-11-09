"""Fixed bounded Git capture of actual Agent OS accepted Direction and history.

Only explicit WS/DEC owner declarations are read. No search by title, Git date,
generic decision citation, authored objective or plan-adoption record elects one.
"""
from __future__ import annotations

import hashlib
import math
import re
import sys
import time
import types
from contextlib import redirect_stdout, redirect_stderr
import io
from pathlib import Path

from common import workspace_project_direction_contract as wire
from control_plane.ceo_boot_packet import bounded_subprocess_runner

_SOURCE_ROOT = Path(__file__).resolve().parents[1]
_MAX_RECORD_BYTES = 262144
_MAX_OWNER_BYTES = 1048576


class DirectionSourceUnavailable(ValueError):
    pass


class AgentOsProjectDirectionReader:
    """Facade issued by the existing installed sealed collector only."""
    def __init__(self, *, macro_root):
        self._macro_root = Path(macro_root)
        if not self._macro_root.is_absolute():
            raise ValueError("SOURCE_UNAVAILABLE")
        self._installed_context_owner = None
        self._installed_context_binding = None
        self._installed_reader_binding = None

    @staticmethod
    def _context_binding(owner):
        return tuple(getattr(owner, name) for name in ("_source_root", "_macro_root", "_code_root", "_python",
                    "_expected_source_sha", "_allow_synthetic_fixture"))

    def read(self, *, work_ref):
        from control_plane.installed_project_read_binding import (
            InstalledProjectReadUnavailable, read_installed_project_binding,
        )
        try:
            return read_installed_project_binding(self, kind="project_direction", work_ref=work_ref)
        except InstalledProjectReadUnavailable:
            raise DirectionSourceUnavailable("SOURCE_UNAVAILABLE") from None


def read_from_macro_owner(*, macro_root, expected_macro_sha, work_ref, timeout=10.0, runner=None):
    """Child of the existing collector pre/post permission/source-seal bracket."""
    selected = wire.selection({"work_ref": work_ref})
    root = Path(macro_root)
    if (not root.is_absolute() or type(expected_macro_sha) is not str
            or re.fullmatch(r"[0-9a-f]{40}", expected_macro_sha) is None
            or type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0 < timeout <= 15):
        raise DirectionSourceUnavailable("SOURCE_UNAVAILABLE")
    run = runner or bounded_subprocess_runner
    deadline = time.monotonic() + timeout

    def git(*args, limit=_MAX_RECORD_BYTES):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise DirectionSourceUnavailable("SOURCE_UNAVAILABLE")
        result = run(["git", "--no-optional-locks", "--no-replace-objects", "-C", str(root), *args],
                     cwd=root, timeout=remaining, max_bytes=limit)
        if (type(result) is not dict or result.get("code") != 0 or type(result.get("stdout")) is not str
                or any(result.get(flag) is True for flag in ("timed_out", "limit_exceeded", "invalid_utf8"))):
            raise DirectionSourceUnavailable("SOURCE_UNAVAILABLE")
        return result["stdout"]

    def captured(path, limit):
        member = git("ls-tree", "-z", expected_macro_sha, "--", path, limit=2048)
        if not member:
            raise DirectionSourceUnavailable("RECORD_NOT_FOUND")
        if re.fullmatch(r"100644 blob [0-9a-f]{40}\t" + re.escape(path) + "\x00", member) is None:
            raise DirectionSourceUnavailable("RECORD_INVALID")
        return git("show", expected_macro_sha + ":" + path, limit=limit)

    modules = []
    saved_path = list(sys.path)
    try:
        if git("rev-parse", "HEAD").strip() != expected_macro_sha:
            return wire.unavailable(work_ref, "SOURCE_CHANGED")
        owner_text = captured("scripts/agentos.py", _MAX_OWNER_BYTES)
        direction_text = captured("scripts/agentos_direction.py", _MAX_OWNER_BYTES)
        plan_text = captured("scripts/agentos_project_plan_contract.py", _MAX_OWNER_BYTES)
        # Names are private, fixed and restored. The actual captured producer
        # parser and Direction validator consume captured immutable bytes.
        def module(name, text, path):
            obj = types.ModuleType(name)
            obj.__file__ = str(root / path)
            modules.append((name, sys.modules.get(name)))
            sys.modules[name] = obj
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                exec(compile(text, obj.__file__, "exec"), obj.__dict__)
            return obj
        direction_owner = module("agentos_bound_direction", direction_text, "scripts/agentos_direction.py")
        plan_owner = module("agentos_bound_direction_plan_contract", plan_text, "scripts/agentos_project_plan_contract.py")
        owner = module("agentos_bound_direction_parser", owner_text, "scripts/agentos.py")
        # The native owner validators use these fixed helpers. Bind their
        # captured modules; do not let an import reopen a mutable worktree.
        owner._project_plan_contract = lambda: plan_owner
        owner._direction_contract = lambda: direction_owner

        def record(path, checker):
            raw = captured(path, _MAX_RECORD_BYTES)
            class Captured:
                def read_text(self, *, encoding):
                    if encoding != "utf-8":
                        raise ValueError("RECORD_INVALID")
                    return raw
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                value, _body = owner.parse_record(Captured())
                problems = checker(value, root / path)
            if any(problem.hard for problem in problems):
                raise DirectionSourceUnavailable("RECORD_INVALID")
            source = {"repository": "mastermindx-market-intelligence/macro", "commit": expected_macro_sha,
                      "path": path, "content_sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest()}
            return value, source

        ws_path = "agentos/workstreams/WS-" + work_ref[3:] + ".md"
        ws, ws_source = record(ws_path, lambda r, p: owner.check_workstream(r, p, None))
        head = ws.get("accepted_direction")
        if head is None:
            value = wire.unavailable(work_ref, "NOT_DECLARED")
        else:
            decisions = {}
            selected_ref = head
            for _index in range(8):
                if (type(selected_ref) is not str or re.fullmatch(r"DEC:[A-Z0-9]+(?:-[A-Z0-9]+)*", selected_ref) is None
                        or not 2 <= len(selected_ref[4:]) <= 128 or selected_ref in decisions):
                    raise DirectionSourceUnavailable("LINEAGE_CONFLICT")
                path = "agentos/decisions/DEC-" + selected_ref[4:] + ".md"
                dec, source = record(path, owner.check_decision)
                decisions[selected_ref] = {"record": dec, "source": source}
                declaration = direction_owner.validate_declaration(dec.get("direction"), work_ref=work_ref, decision_ref=selected_ref)
                selected_ref = declaration["predecessor"]
                if selected_ref is None:
                    break
            projected = direction_owner.project_direction(work_ref=work_ref, workstream=ws,
                workstream_source=ws_source, decisions=decisions, max_revisions=8)
            value = {"schema": wire.BODY_SCHEMA, "selection": selected, "availability": "AVAILABLE",
                     "source": ws_source, "direction": projected, "reason_codes": []}
        if git("rev-parse", "HEAD").strip() != expected_macro_sha:
            return wire.unavailable(work_ref, "SOURCE_CHANGED")
        return wire.validate_body(value)
    except DirectionSourceUnavailable as exc:
        reason = str(exc)
        return wire.unavailable(work_ref, reason if reason in wire.REASON_CODES else "SOURCE_UNAVAILABLE")
    except Exception as exc:
        code = getattr(exc, "code", None)
        mapped = {"NOT_DECLARED": "NOT_DECLARED", "LINEAGE_CONFLICT": "LINEAGE_CONFLICT",
                  "LINEAGE_INCOMPLETE": "LINEAGE_INCOMPLETE", "CONTENT_OVER_BUDGET": "CONTENT_OVER_BUDGET"}
        return wire.unavailable(work_ref, mapped.get(code, "RECORD_INVALID"))
    except SystemExit:
        return wire.unavailable(work_ref, "SOURCE_UNAVAILABLE")
    finally:
        sys.path[:] = saved_path
        for name, prior in reversed(modules):
            if prior is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = prior

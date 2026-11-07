"""Fixed immutable Agent OS source for the observational project association.

Production invocation belongs inside the existing InstalledBootPacketCollector
sealed child bracket. No source write, arbitrary path or conversation is created.
"""
from __future__ import annotations
import hashlib
import json
import re
import sys
import time
import types
from pathlib import Path

from common import workspace_project_session_contract as wire
from control_plane.ceo_boot_packet import bounded_subprocess_runner

_SOURCE_ROOT = Path(__file__).resolve().parents[1]

_MARKER = re.compile(r"^<!--\nagentos-project-proposal provenance \(DRAFT_ONLY\):\n"
    r"request_id: ([A-Za-z0-9][A-Za-z0-9_.:-]{0,127})\n"
    r"request_sha256: ([0-9a-f]{64})\nexpected_commit: ([0-9a-f]{40})\n-->\n?", re.MULTILINE)


class AgentOsProjectCreationReader:
    """Facade issued by the incumbent sealed source owner, never by a browser."""
    def __init__(self, *, macro_root):
        self._macro_root = Path(macro_root)
        if not self._macro_root.is_absolute():
            raise ValueError("source_unavailable")
        self._installed_context_owner = None
        self._installed_context_binding = None
        self._installed_reader_binding = None

    @staticmethod
    def _context_binding(owner):
        return tuple(getattr(owner, name) for name in (
            "_source_root", "_macro_root", "_code_root", "_python", "_expected_source_sha", "_allow_synthetic_fixture"))

    def read(self, *, work_ref, record_commit, expected_current_macro_sha=None):
        from control_plane.installed_project_read_binding import (
            InstalledProjectReadUnavailable, read_installed_project_creation_binding)
        try:
            return read_installed_project_creation_binding(self, work_ref=work_ref, record_commit=record_commit,
                expected_current_macro_sha=expected_current_macro_sha)
        except InstalledProjectReadUnavailable:
            raise ValueError("source_unavailable") from None



def read_from_macro_owner(*, macro_root, expected_macro_sha, work_ref, record_commit=None, timeout=10.0, runner=None, _canonical_data_view=None):
    """Return source metadata only after the captured canonical parser/checker.

    The origin marker is checked against the exact parsed record rather than
    assuming that an unchanged marker still describes modified goal/owner data.
    The outer installed collector and Workspace reader retain source/audience
    qualification; file existence or this inert dict is never a write grant.
    """
    from common.workspace_project_journal_contract import validate_selection
    validate_selection({"work_ref": work_ref})
    root = Path(macro_root)
    code_sha, code_root = expected_macro_sha, root
    if _canonical_data_view is not None:
        from control_plane.project_canonical_data import CanonicalProjectDataView
        if (type(_canonical_data_view) is not CanonicalProjectDataView
                or _canonical_data_view._root != root
                or _canonical_data_view.data_commit != expected_macro_sha):
            raise ValueError("source_unavailable")
        _canonical_data_view.check()
        code_sha, code_root = _canonical_data_view.code_commit, _canonical_data_view._code_root
    record_commit = expected_macro_sha if record_commit is None else record_commit
    if (not root.is_absolute() or not wire._hex(expected_macro_sha, 40)
            or not wire._hex(record_commit, 40)
            or type(timeout) not in (int, float) or not 0 < timeout <= 15):
        raise ValueError("source_unavailable")
    path = "agentos/workstreams/WS-" + work_ref[3:] + ".md"
    deadline = time.monotonic() + timeout
    run = runner or bounded_subprocess_runner
    consumed = 0

    def git(*args, limit=262144):
        nonlocal consumed
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ValueError("source_unavailable")
        result = run(["git", "--no-optional-locks", "--no-replace-objects", "-C", str(root), *args],
            cwd=root, timeout=remaining, max_bytes=limit)
        if (type(result) is not dict or result.get("code") != 0 or type(result.get("stdout")) is not str
                or any(result.get(flag) is True for flag in ("timed_out", "limit_exceeded", "invalid_utf8"))):
            raise ValueError("source_unavailable")
        consumed += len(result["stdout"].encode("utf-8"))
        if consumed > 2 * 1048576:
            raise ValueError("source_unavailable")
        return result["stdout"]

    def captured(name, limit=262144):
        commit = code_sha if name in ("scripts/agentos.py", "config/mastermind_programs.yml") else record_commit
        return git("show", commit + ":" + name, limit=limit)

    def current():
        if _canonical_data_view is not None:
            _canonical_data_view.check()
            return True
        return git("rev-parse", "HEAD").strip() == expected_macro_sha

    if not current():
        raise ValueError("source_changed")
    # A recognized Runtime root may retain its original grounding after later
    # unrelated Macro commits. Read that immutable ancestor, never substitute
    # today's goal or mark its historical creation as a current instruction.
    git("merge-base", "--is-ancestor", record_commit, expected_macro_sha, limit=1024)
    member = git("ls-tree", "-z", record_commit, "--", path)
    if re.fullmatch(r"100644 blob [0-9a-f]{40}\t" + re.escape(path) + "\x00", member) is None:
        raise ValueError("source_mismatch")
    content = captured(path, 32768)
    module = types.ModuleType("agentos_bound_project_creation_source")
    module.__file__ = str(code_root / "scripts/agentos.py")
    previous = sys.modules.get(module.__name__)
    original_path = list(sys.path)
    try:
        sys.modules[module.__name__] = module
        exec(compile(captured("scripts/agentos.py", 1048576), module.__file__, "exec"), module.__dict__)

        class CapturedText:
            def __init__(self, text): self.text = text
            def exists(self): return True
            def read_text(self, *, encoding):
                if encoding != "utf-8": raise ValueError("source_mismatch")
                return self.text

        module._PROGRAMS = CapturedText(captured("config/mastermind_programs.yml", 524288))
        programs = module._load_programs()
        if type(programs) is not set or not programs:
            raise ValueError("source_unavailable")
        record, body = module.parse_record(CapturedText(content))
        if (record.get("key") != work_ref[3:]
                or any(problem.hard for problem in module.check_workstream(record, root / path, programs))):
            raise ValueError("source_mismatch")
        markers = list(_MARKER.finditer(body))
        if len(markers) != 1:
            raise ValueError("source_mismatch")
        request_id, request_sha, expected_base = markers[0].groups()
        authored = dict(record)
        request = {"schema": "agentos.project_proposal_request.v1", "request_id": request_id,
                   "expected_commit": expected_base, "record": authored}
        raw = json.dumps(request, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
        if len(raw) > 16384 or hashlib.sha256(raw).hexdigest() != request_sha:
            raise ValueError("source_mismatch")
        git("merge-base", "--is-ancestor", expected_base, record_commit, limit=1024)
        if not current():
            raise ValueError("source_changed")
        return {"repository": "macro", "commit": record_commit, "path": path,
                "content_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(), "request_sha256": request_sha}
    except (ImportError, SystemExit):
        raise ValueError("source_unavailable") from None
    finally:
        sys.path[:] = original_path
        if previous is None: sys.modules.pop(module.__name__, None)
        else: sys.modules[module.__name__] = previous

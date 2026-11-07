"""Bounded canonical Agent OS record reads, through the incumbent sealed owner.

This is a projection of existing authored records, not an event writer, history
store, inferred Runtime diary, or source of execution/acceptance authority.
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
_MAX_CANDIDATES = 128
_PATH = re.compile(r"agentos/(decisions/DEC-[A-Z0-9]+(?:-[A-Z0-9]+)*|discoveries/DSC-[A-Z0-9]+(?:-[A-Z0-9]+)*|handoffs/[A-Za-z0-9_-]+)\.md")


class ProjectJournalSourceUnavailable(ValueError):
    pass


class AgentOsProjectJournalReader:
    """Facade issued only by InstalledBootPacketCollector, never by a caller."""

    def __init__(self, *, macro_root: Path):
        self._macro_root = Path(macro_root)
        if not self._macro_root.is_absolute():
            raise ValueError("journal source must be absolute")
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
            return read_installed_project_binding(self, kind="project_journal", work_ref=work_ref)
        except InstalledProjectReadUnavailable:
            raise ProjectJournalSourceUnavailable("SOURCE_UNAVAILABLE") from None


def read_from_macro_owner(*, macro_root: Path, expected_macro_sha: str,
                          work_ref: str, timeout: float = 10.0, runner=None):
    """Read immutable Git objects using Macro's own parser and validators.

    The bounded sample comprises records touched by the last 128 commits to
    the canonical record folders, plus explicit workstream DEC/DSC references.
    Association is established from parsed source fields, never a filename.
    Authored dates and Git commit dates remain distinct in the returned DTO.
    The parent collector supplies its existing pre/post source seal bracket.
    """
    from common.workspace_project_journal_contract import (
        validate_selection, validate_body, unavailable,
    )
    from control_plane.workspace_project_journal import project_journal

    validate_selection({"work_ref": work_ref})
    if (not Path(macro_root).is_absolute()
            or type(expected_macro_sha) is not str
            or re.fullmatch(r"[0-9a-f]{40}", expected_macro_sha) is None
            or type(timeout) not in (int, float) or not 0 < timeout <= 15):
        raise ProjectJournalSourceUnavailable("SOURCE_UNAVAILABLE")
    root = Path(macro_root)
    run = runner or bounded_subprocess_runner
    deadline = time.monotonic() + timeout
    consumed = 0

    def git(*args, limit=262144):
        nonlocal consumed
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ProjectJournalSourceUnavailable("SOURCE_UNAVAILABLE")
        result = run(["git", "--no-optional-locks", "--no-replace-objects", "-C", str(root), *args],
                     cwd=root, timeout=remaining, max_bytes=limit)
        if (not isinstance(result, dict) or result.get("code") != 0
                or type(result.get("stdout")) is not str
                or any(result.get(flag) is True for flag in ("timed_out", "limit_exceeded", "invalid_utf8"))):
            raise ProjectJournalSourceUnavailable("SOURCE_UNAVAILABLE")
        value = result["stdout"]
        consumed += len(value.encode("utf-8"))
        if consumed > 4 * 1048576:
            raise ProjectJournalSourceUnavailable("CONTENT_OVER_BUDGET")
        return value

    def captured(path, limit=262144):
        return git("show", expected_macro_sha + ":" + path, limit=limit)

    module = types.ModuleType("agentos_bound_journal_source")
    module.__file__ = str(root / "scripts/agentos.py")
    prior = sys.modules.get(module.__name__)
    original_path = list(sys.path)
    try:
        if git("rev-parse", "HEAD").strip() != expected_macro_sha:
            return unavailable(work_ref, "SOURCE_CHANGED")
        ws_path = "agentos/workstreams/WS-" + work_ref[3:] + ".md"
        ws_member = git("ls-tree", "-z", expected_macro_sha, "--", ws_path)
        if not ws_member:
            return unavailable(work_ref, "RECORD_NOT_FOUND")
        if re.fullmatch(r"100644 blob [0-9a-f]{40}\t" + re.escape(ws_path) + "\x00", ws_member) is None:
            return unavailable(work_ref, "RECORD_INVALID")
        sys.modules[module.__name__] = module
        exec(compile(captured("scripts/agentos.py", 1048576), module.__file__, "exec"), module.__dict__)

        def parse(path, text):
            class CapturedRecord:
                def read_text(self, *, encoding):
                    if encoding != "utf-8":
                        raise ValueError("record encoding refused")
                    return text
            record, _body = module.parse_record(CapturedRecord())
            checker = (module.check_workstream if path == ws_path else
                       module.check_decision if path.startswith("agentos/decisions/") else
                       module.check_discovery if path.startswith("agentos/discoveries/") else
                       module.check_handoff)
            problems = (checker(record, root / path, None) if path == ws_path else checker(record, root / path))
            if any(problem.hard for problem in problems):
                raise ValueError("record invalid")
            return record

        workstream = parse(ws_path, captured(ws_path))
        explicit = []
        for field, prefix, folder in (("decisions", "DEC:", "decisions/DEC-"),
                                     ("discoveries", "DSC:", "discoveries/DSC-")):
            for reference in workstream.get(field, []) or []:
                if type(reference) is str and reference.startswith(prefix):
                    explicit.append("agentos/" + folder + reference[len(prefix):] + ".md")
        history = git("log", "--max-count=128", "--format=", "--name-only", expected_macro_sha,
                      "--", "agentos/decisions/", "agentos/discoveries/", "agentos/handoffs/", limit=1048576)
        candidates = list(dict.fromkeys(explicit + [p for p in history.splitlines() if _PATH.fullmatch(p)]))
        selected = candidates[:_MAX_CANDIDATES]
        rows, invalid = [], 0
        for path in selected:
            if not _PATH.fullmatch(path):
                invalid += 1
                continue
            # Deleted, symlinked, submodule or nonregular records are not read.
            member = git("ls-tree", "-z", expected_macro_sha, "--", path)
            if not member:
                continue
            if re.fullmatch(r"100644 blob [0-9a-f]{40}\t" + re.escape(path) + "\x00", member) is None:
                invalid += 1
                continue
            text = captured(path)
            try:
                record = parse(path, text)
            except (ValueError, TypeError, KeyError, AttributeError):
                invalid += 1
                continue
            kind = ("DECISION" if "/decisions/" in path else
                    "DISCOVERY" if "/discoveries/" in path else "HANDOFF")
            association = (record.get("affects") if kind == "DECISION" else
                           record.get("scope") if kind == "DISCOVERY" else None)
            if not (record.get("workstream") == work_ref if kind == "HANDOFF" else
                    ((type(association) is str and association == work_ref) or
                     (type(association) is list and work_ref in association))):
                continue
            committed_at = git("log", "-1", "--format=%cI", expected_macro_sha, "--", path, limit=8192).strip() or None
            rows.append({"kind": kind, "record": record, "path": path,
                         "content_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                         "committed_at": committed_at})
        value = project_journal(rows, work_ref=work_ref,
            source={"repository": "mastermindx-market-intelligence/macro", "commit": expected_macro_sha},
            scanned=len(selected), omitted=max(0, len(candidates) - len(selected)), invalid=invalid)
        if git("rev-parse", "HEAD").strip() != expected_macro_sha:
            return unavailable(work_ref, "SOURCE_CHANGED")
        return validate_body(value)
    except ProjectJournalSourceUnavailable as exc:
        return unavailable(work_ref, "CONTENT_OVER_BUDGET" if str(exc) == "CONTENT_OVER_BUDGET" else "SOURCE_UNAVAILABLE")
    except (ImportError, SystemExit):
        return unavailable(work_ref, "SOURCE_UNAVAILABLE")
    except (OSError, ValueError, TypeError, KeyError, AttributeError, SyntaxError,
            RecursionError, OverflowError):
        return unavailable(work_ref, "RECORD_INVALID")
    finally:
        sys.path[:] = original_path
        if prior is None:
            sys.modules.pop(module.__name__, None)
        else:
            sys.modules[module.__name__] = prior

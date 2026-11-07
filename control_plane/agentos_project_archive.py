"""Existing sealed capture's fixed archive helper, bounded by catalogue membership."""
from __future__ import annotations

import math
import re
import sys
import time
import types
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

from common import workspace_project_archive_contract as wire
from control_plane.ceo_boot_packet import bounded_subprocess_runner

_SOURCE_ROOT = Path(__file__).resolve().parents[1]


class ArchiveSourceUnavailable(ValueError):
    pass


class AgentOsProjectArchiveReader:
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

    def read(self, *, work_refs, expected_current_macro_sha):
        from control_plane.installed_project_read_binding import read_installed_project_archive_binding
        return read_installed_project_archive_binding(self, work_refs=work_refs,
            expected_current_macro_sha=expected_current_macro_sha)


def read_from_macro_owner(*, macro_root, expected_macro_sha, work_refs, timeout=10.0, runner=None):
    """Acquire the actual frozen native helper and its selected canonical records.

    The installed collector owns the immutable materialization and source seal.
    Every helper-consumed file also matches its regular Git blob here, so a
    mutable checkout cannot impersonate that capture when this function is tested.
    """
    refs = wire.validate_refs(work_refs)
    root = Path(macro_root)
    if (not root.is_absolute() or root.is_symlink() or not wire._hex(expected_macro_sha, 40)
            or type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0 < timeout <= 15):
        raise ArchiveSourceUnavailable("SOURCE_UNAVAILABLE")
    run = runner or bounded_subprocess_runner
    deadline = time.monotonic() + timeout

    def git(*args, limit=1048576):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ArchiveSourceUnavailable("SOURCE_UNAVAILABLE")
        value = run(["git", "--no-optional-locks", "--no-replace-objects", "-C", str(root), *args],
                    cwd=root, timeout=remaining, max_bytes=limit)
        if (type(value) is not dict or value.get("code") != 0 or type(value.get("stdout")) is not str
                or any(value.get(flag) is True for flag in ("timed_out", "limit_exceeded", "invalid_utf8"))):
            raise ArchiveSourceUnavailable("SOURCE_UNAVAILABLE")
        return value["stdout"]

    def capture(path, limit):
        member = git("ls-tree", "-z", expected_macro_sha, "--", path, limit=2048)
        if re.fullmatch(r"100644 blob [0-9a-f]{40}\t" + re.escape(path) + "\x00", member) is None:
            raise ArchiveSourceUnavailable("SOURCE_UNAVAILABLE")
        text = git("show", expected_macro_sha + ":" + path, limit=limit)
        target = root / path
        if any(p.is_symlink() for p in (target, *target.parents)) or target.read_bytes() != text.encode("utf-8"):
            raise ArchiveSourceUnavailable("SOURCE_CHANGED")
        return text

    saved = []
    def module(name, text, path):
        obj = types.ModuleType(name)
        obj.__file__ = str(root / path)
        saved.append((name, sys.modules.get(name)))
        sys.modules[name] = obj
        # Actual captured native code is trusted source; diagnostics never enter
        # the public JSON body or an unbounded in-memory diagnostic buffer.
        with open("/dev/null", "w") as discard, redirect_stdout(discard), redirect_stderr(discard):
            exec(compile(text, obj.__file__, "exec"), obj.__dict__)
        return obj

    try:
        if git("rev-parse", "HEAD").strip() != expected_macro_sha:
            raise ArchiveSourceUnavailable("SOURCE_CHANGED")
        owner_text = capture("scripts/agentos.py", 1048576)
        helper_text = capture("scripts/agentos_project_archive.py", 1048576)
        plan_text = capture("scripts/agentos_project_plan_contract.py", 1048576)
        capture("config/mastermind_programs.yml", 262144)
        originals = {"agentos/workstreams/WS-" + ref[3:] + ".md": None for ref in refs}
        for path in originals:
            originals[path] = capture(path, 131072)
        plan = module("agentos_bound_archive_plan", plan_text, "scripts/agentos_project_plan_contract.py")
        owner = module("agentos_bound_archive_parser", owner_text, "scripts/agentos.py")
        helper = module("agentos_bound_archive_helper", helper_text, "scripts/agentos_project_archive.py")
        owner._project_plan_contract = lambda: plan
        with open("/dev/null", "w") as discard, redirect_stdout(discard), redirect_stderr(discard):
            programs = owner._load_programs()
            if type(programs) is not set or not programs:
                raise ArchiveSourceUnavailable("SOURCE_UNAVAILABLE")
            sample = helper.read_archive_sample(root, captured_commit=expected_macro_sha,
                qualified_work_refs=refs, owner=owner, programs=programs)
        for path, text in originals.items():
            if (root / path).read_bytes() != text.encode("utf-8"):
                raise ArchiveSourceUnavailable("SOURCE_CHANGED")
        if git("rev-parse", "HEAD").strip() != expected_macro_sha:
            raise ArchiveSourceUnavailable("SOURCE_CHANGED")
        return wire.validate_sample(sample, refs, expected_macro_sha)
    except (OSError, ValueError, TypeError, KeyError, UnicodeError, SyntaxError, RecursionError):
        raise ArchiveSourceUnavailable("SOURCE_UNAVAILABLE") from None
    finally:
        for name, prior in reversed(saved):
            if prior is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = prior

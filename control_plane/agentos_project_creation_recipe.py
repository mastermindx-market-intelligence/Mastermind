"""Read one fixed immutable Macro compiler inside the installed child bracket.

No source write or publication occurs. The canonical compiler and programme
catalogue are captured at one actual Git commit; working-file imports cannot
substitute their bytes. Outer installed source seals remain mandatory.
"""
from __future__ import annotations
import hashlib
import json
import re
import sys
import time
import types
from pathlib import Path
from control_plane.ceo_boot_packet import bounded_subprocess_runner

_CODE = {"compiler": "scripts/agentos_project_proposal.py", "owner": "scripts/agentos.py",
         "programs": "config/mastermind_programs.yml"}


def capture_creation_recipe(*, macro_root, expected_macro_sha, code_commit, request=None,
                            timeout=10.0, runner=None):
    root = Path(macro_root)
    if (not root.is_absolute() or any(type(x) is not str or re.fullmatch(r"[0-9a-f]{40}", x) is None
        for x in (expected_macro_sha, code_commit)) or type(timeout) not in (int, float)
        or not 0 < timeout <= 15 or (request is not None and type(request) is not dict)):
        raise ValueError("project_creation_recipe_unavailable")
    deadline, run = time.monotonic() + timeout, runner or bounded_subprocess_runner
    def git(*args, cap=1048576):
        remaining = deadline - time.monotonic()
        if remaining <= 0: raise ValueError("project_creation_recipe_unavailable")
        result = run(["git", "--no-optional-locks", "--no-replace-objects", "-C", str(root), *args],
                     cwd=root, timeout=remaining, max_bytes=cap)
        if (type(result) is not dict or result.get("code") != 0 or type(result.get("stdout")) is not str
            or any(result.get(k) is True for k in ("timed_out", "limit_exceeded", "invalid_utf8"))):
            raise ValueError("project_creation_recipe_unavailable")
        return result["stdout"]
    if git("rev-parse", "HEAD", cap=1024).strip() != expected_macro_sha:
        raise ValueError("project_creation_recipe_source_changed")
    git("merge-base", "--is-ancestor", code_commit, expected_macro_sha, cap=1024)
    texts, refs = {}, {}
    for role, path in _CODE.items():
        entry = git("ls-tree", "-z", code_commit, "--", path, cap=2048)
        if re.fullmatch(r"100644 blob [0-9a-f]{40}\t" + re.escape(path) + "\x00", entry) is None:
            raise ValueError("project_creation_recipe_unavailable")
        raw = git("show", code_commit + ":" + path)
        texts[role] = raw
        refs[role] = {"repository": "mastermindx-market-intelligence/macro", "commit": code_commit,
                      "path": path, "content_sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest()}
    package = types.ModuleType("scripts"); package.__path__ = []
    owner = types.ModuleType("scripts.agentos"); owner.__file__ = str(root / _CODE["owner"])
    compiler = types.ModuleType("scripts.agentos_project_proposal"); compiler.__file__ = str(root / _CODE["compiler"])
    names = {"scripts": package, "scripts.agentos": owner, "scripts.agentos_project_proposal": compiler}
    previous, old_path = {k: sys.modules.get(k) for k in names}, list(sys.path)
    try:
        sys.modules.update(names); package.agentos = owner
        exec(compile(texts["owner"], owner.__file__, "exec"), owner.__dict__)
        class CapturedPrograms:
            def exists(self): return True
            def read_text(self, *, encoding):
                if encoding != "utf-8": raise ValueError("project_creation_recipe_unavailable")
                return texts["programs"]
        owner._PROGRAMS = CapturedPrograms()
        programs = owner._load_programs()
        if type(programs) is not set or not programs or any(type(x) is not str for x in programs):
            raise ValueError("project_creation_recipe_unavailable")
        exec(compile(texts["compiler"], compiler.__file__, "exec"), compiler.__dict__)
        recipe = None if request is None else compiler.compile_proposal(request, programs=programs)
        if request is not None and (request.get("expected_commit") != code_commit
                or type(recipe) is not dict or recipe.get("expected_commit") != code_commit
                or recipe.get("schema") != "agentos.project_proposal.v1"
                or recipe.get("state") != "DRAFT_ONLY"):
            raise ValueError("project_creation_recipe_unavailable")
    finally:
        sys.path[:] = old_path
        for key, value in previous.items():
            if value is None: sys.modules.pop(key, None)
            else: sys.modules[key] = value
    if git("rev-parse", "HEAD", cap=1024).strip() != expected_macro_sha:
        raise ValueError("project_creation_recipe_source_changed")
    result = {"schema": "mastermind.project_creation_recipe_capture.v1", "recipe": recipe,
              "programs": sorted(programs), "source_binding": refs}
    raw = json.dumps(result, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
    if len(raw) + 1 > 65536: raise ValueError("project_creation_recipe_unavailable")
    return result

"""Fixed isolated adopted-WS compiler child; emit the owner's exact bytes once.

The installed collector owns source/runtime qualification and process settlement.
The fixed import policy keeps materialized record/artifact files out of ordinary
module resolution even when the actual Macro script prepends its root.
"""
from __future__ import annotations

import argparse
from contextlib import redirect_stderr, redirect_stdout
import importlib.machinery
import importlib.util
import io
from pathlib import Path
import runpy
import sys

_STARTUP_PATHS = tuple(sys.path)
_CODE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_CODE_ROOT))
from control_plane.agentos_context_bundle import MAX_BUNDLE_BYTES, TOKEN_BUDGET, validate_selection


class _ClosedParser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError("SOURCE_UNAVAILABLE")


class _BoundedOutput(io.TextIOBase):
    def __init__(self):
        self.data = bytearray()

    def write(self, text):
        if type(text) is not str or len(text) > MAX_BUNDLE_BYTES:
            raise ValueError("SOURCE_UNAVAILABLE")
        raw = text.encode("utf-8", "strict")
        if len(self.data) + len(raw) > MAX_BUNDLE_BYTES:
            raise ValueError("SOURCE_UNAVAILABLE")
        self.data.extend(raw)
        return len(text)

    def flush(self):
        pass


class _DiscardDiagnostics(io.TextIOBase):
    def write(self, text):
        return len(text)

    def flush(self):
        pass


def _qualify_import_paths(dependencies: Path):
    if (sys.flags.isolated != 1 or sys.flags.no_site != 1 or not sys.dont_write_bytecode
            or not dependencies.is_absolute() or dependencies.is_symlink() or not dependencies.is_dir()):
        raise ValueError("SOURCE_UNAVAILABLE")
    admitted = tuple(dict.fromkeys((str(dependencies), *_STARTUP_PATHS)))
    if any(not Path(path).is_absolute() for path in admitted):
        raise ValueError("SOURCE_UNAVAILABLE")
    machinery = importlib.machinery
    if sys.meta_path != [machinery.BuiltinImporter, machinery.FrozenImporter, machinery.PathFinder]:
        raise ValueError("SOURCE_UNAVAILABLE")
    roots = tuple(Path(path).resolve() for path in admitted)
    refused = False

    def contained(path):
        candidate = Path(path).resolve()
        return any(candidate == root or root in candidate.parents for root in roots)

    class QualifiedPaths:
        @classmethod
        def find_spec(cls, fullname, path=None, target=None):
            nonlocal refused
            selected = admitted if path is None else tuple(entry for entry in path if contained(entry))
            spec = machinery.PathFinder.find_spec(fullname, selected, target)
            if spec is not None:
                if spec.origin not in (None, "built-in", "frozen") and not contained(spec.origin):
                    refused = True
                    raise ImportError("SOURCE_UNAVAILABLE")
                if spec.submodule_search_locations is not None and any(
                        not contained(entry) for entry in spec.submodule_search_locations):
                    refused = True
                    raise ImportError("SOURCE_UNAVAILABLE")
            else:
                # A genuinely absent optional dependency (for example a stdlib
                # platform probe) is not a provenance violation. A module that
                # exists only on the widened path is. Locate, never execute it,
                # and retain refusal even if the compiler catches ImportError.
                outside = machinery.PathFinder.find_spec(fullname, path, target)
                if outside is not None:
                    refused = True
                    raise ImportError("SOURCE_UNAVAILABLE")
            return spec

    # Replace the ordinary PathFinder completely. A missing module cannot fall
    # through to a second finder using the compiler-widened sys.path.
    sys.meta_path[:] = [machinery.BuiltinImporter, machinery.FrozenImporter, QualifiedPaths]
    sys.path[:] = list(admitted)
    import yaml
    import _yaml
    if any(dependencies.resolve() not in Path(module.__file__).resolve().parents for module in (yaml, _yaml)):
        raise ValueError("SOURCE_UNAVAILABLE")

    def require_clean_imports():
        if refused:
            raise ValueError("SOURCE_UNAVAILABLE")
    return require_clean_imports


def _require_source_helper(root: Path):
    # -B prevents cache writes, not reads. The reviewed owner's explicit sibling
    # loader bypasses meta_path and could otherwise consume a materialized pyc.
    # Do not delete or hide an input that the source owner chose to materialize.
    if sys.pycache_prefix is not None or sys.flags.optimize != 0:
        raise ValueError("SOURCE_UNAVAILABLE")
    candidate = Path(importlib.util.cache_from_source(str(root / "scripts/agentos_project_plan_contract.py")))
    try:
        candidate.lstat()
    except FileNotFoundError:
        return
    raise ValueError("SOURCE_UNAVAILABLE")


def main(argv=None):
    parser = _ClosedParser(add_help=False)
    parser.add_argument("--macro-root", required=True)
    parser.add_argument("--work-ref", required=True)
    parser.add_argument("--site-packages", required=True)
    output = _BoundedOutput()
    try:
        args = parser.parse_args(argv)
        validate_selection({"work_ref": args.work_ref})
        root, dependencies = Path(args.macro_root), Path(args.site_packages)
        if not root.is_absolute() or root.is_symlink() or not root.is_dir():
            raise ValueError("SOURCE_UNAVAILABLE")
        require_clean_imports = _qualify_import_paths(dependencies)
        _require_source_helper(root)
        script = root / "scripts/agentos.py"
        sys.argv[:] = [str(script), "compile-context", "--workstream", args.work_ref, "--json", "--budget", str(TOKEN_BUDGET)]
        with redirect_stdout(output), redirect_stderr(_DiscardDiagnostics()):
            try:
                runpy.run_path(str(script), run_name="__main__")
            except SystemExit as exc:
                if type(exc.code) is not int or exc.code != 0:
                    raise ValueError("SOURCE_UNAVAILABLE") from None
        require_clean_imports()
        if not output.data:
            raise ValueError("SOURCE_UNAVAILABLE")
    except Exception:
        return 1  # No raw diagnostic or partially compiled context is emitted.
    sys.stdout.buffer.write(output.data)
    sys.stdout.buffer.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

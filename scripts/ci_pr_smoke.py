"""Bounded source-proximate tests for trusted PR/merge-group smoke scope.

The trusted-base CI scope selects this non-privileged path. This selector
never edits branch protection, suppresses a required check, or publishes a
review verdict. No remote access, shell interpolation, credentials or workers.
"""
from __future__ import annotations

import argparse
import ast
import pathlib
import subprocess
import sys
from collections.abc import Sequence

_MAX_DIFF_BYTES = 256_000
_MAX_SELECTED_MODULES = 3
_MAX_MODULE_BYTES = 160_000

# Run one deterministic always-present policy smoke even when source path
# naming does not map to an exact test. It is not claimed as complete coverage.
_BASELINE = "tests/test_ci_pytest_policy.py"

# The bridge's reviewed generation is owned by runtime_stage, not by a
# same-stem bridge test. Keep this dependency inside the existing module cap.
_PAPER_STAGE_SOURCES = frozenset({
    "integrations/paper_desktop/bridge.py",
    "integrations/paper_desktop/runtime_stage.py",
})
_PAPER_STAGE_TEST = "tests/test_paper_runtime_stage.py"

# Identity-reviewed sources are pinned by exact sha256/site literals, not by
# any same-stem test. The pin registries read for selection come from the
# trusted base commit (never the candidate checkout), so a candidate cannot
# edit its own reviewed-file set; the test modules themselves still run from
# the checkout and verify the checkout's pins against its sources. #2365
# (merge group 42592403849) certified a scoped group without these modules
# while master's full pytest failed the frozen identity pins. Every frozen
# registry module is wired with the test modules that enforce its pins:
# the fabric release review chain and the dormant incident-source review
# (enforced through reviewed_literal_spans in tests/executive_identity_review.py).
_IDENTITY_PIN_REGISTRIES = (
    ("tests/executive_fabric_release_identity_review.py", (
        "tests/test_executive_reviewed_site_identity_tokens.py",
        "tests/test_executive_fabric_release_identity_review.py",
        "tests/test_hermes_fabric_native_identity_review.py",
    )),
    ("tests/executive_incident_identity_review.py", (
        "tests/test_incident_identity_review.py",
    )),
)
_MAX_REGISTRY_BYTES = 256_000

# Top-level statements that either are control flow or mutate in place; a
# registry module must not contain them at all. ``match`` executes at import
# like the rest, so it is included wherever the running Python defines it.
_CONTROL_FLOW_STATEMENTS = tuple(
    node for node in (
        ast.For, ast.While, ast.If, ast.Try, ast.With,
        getattr(ast, "Match", None),
        ast.AugAssign, ast.AnnAssign, ast.Delete,
        ast.Raise, ast.Assert, ast.Global, ast.Nonlocal,
    ) if node is not None
)


class SmokeUnqualified(ValueError):
    pass


def _diff_paths(repo: pathlib.Path, base: str, head: str) -> tuple[str, ...]:
    try:
        ancestor = subprocess.run(
            ["git", "-C", str(repo), "merge-base", base, head],
            check=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            timeout=12,
        ).stdout.decode("ascii").strip()
        result = subprocess.run(
            ["git", "-C", str(repo), "diff", "--name-only", "-z", "--no-renames",
             ancestor, head],
            check=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            timeout=12,
        ).stdout
    except (subprocess.SubprocessError, OSError, UnicodeError):
        raise SmokeUnqualified("SMOKE_SOURCE_DIFF_UNAVAILABLE") from None
    if len(result) > _MAX_DIFF_BYTES or not result.endswith(b"\x00"):
        raise SmokeUnqualified("SMOKE_DIFF_INCOMPLETE")
    try:
        paths = tuple(part.decode("utf-8") for part in result[:-1].split(b"\x00"))
    except UnicodeError:
        raise SmokeUnqualified("SMOKE_DIFF_PATH_INVALID") from None
    return paths


def _registry_dict_keys(node: ast.expr) -> set[str] | None:
    """Constant string keys of a dict-literal expression, else None."""
    if not isinstance(node, ast.Dict):
        return None
    keys = {
        key.value for key in node.keys
        if isinstance(key, ast.Constant) and type(key.value) is str
    }
    return keys if len(keys) == len(node.keys) else None


def _registry_subscript_key(target: ast.expr) -> str | None:
    """Constant string subscript target like REVIEWED_FILES['path']."""
    if (isinstance(target, ast.Subscript)
            and isinstance(target.value, ast.Name)
            and target.value.id == "REVIEWED_FILES"
            and isinstance(target.slice, ast.Constant)
            and type(target.slice.value) is str):
        return target.slice.value
    return None


def _mentions_name(node: ast.AST, name: str) -> bool:
    """True when the name is referenced, including as an exact string key.

    ``globals()['REVIEWED_FILES']`` reaches the registry through a string
    constant rather than a Name node, so both spellings count as a mention.
    """
    for sub in ast.walk(node):
        if isinstance(sub, ast.Name) and sub.id == name:
            return True
        if isinstance(sub, ast.Constant) and type(sub.value) is str and sub.value == name:
            return True
    return False


def _mentions_any(node: ast.AST, names) -> bool:
    """True when any already-bound helper name is referenced."""
    if not names:
        return False
    wanted = set(names)
    return any(isinstance(sub, ast.Name) and sub.id in wanted
               for sub in ast.walk(node))


def _contains_call(node: ast.AST) -> bool:
    """True when any call executes while the statement itself runs."""
    return any(isinstance(sub, ast.Call) for sub in ast.walk(node))


def _registry_blob(repo: pathlib.Path, base: str, path: str) -> bytes | None:
    """Bounded registry blob read; None only when absent at the base."""
    try:
        done = subprocess.run(
            ["git", "-C", str(repo), "cat-file", "blob", f"{base}:{path}"],
            check=False, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=12,
        )
    except (subprocess.SubprocessError, OSError):
        raise SmokeUnqualified("SMOKE_REVIEWED_REGISTRY_UNAVAILABLE") from None
    if done.returncode != 0:
        # A nonzero exit conflates absence with an unreadable object store.
        # Only a listing that proves the path absent at the base keeps the
        # legacy empty mapping; every unclear case fails closed.
        try:
            probe = subprocess.run(
                ["git", "-C", str(repo), "ls-tree", base, "--", path],
                check=False, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=12,
            )
        except (subprocess.SubprocessError, OSError):
            raise SmokeUnqualified("SMOKE_REVIEWED_REGISTRY_UNAVAILABLE") from None
        if probe.returncode != 0 or probe.stdout.strip():
            raise SmokeUnqualified("SMOKE_REVIEWED_REGISTRY_UNREADABLE")
        return None
    if len(done.stdout) > _MAX_REGISTRY_BYTES:
        raise SmokeUnqualified("SMOKE_REVIEWED_REGISTRY_OVER_BOUND")
    return done.stdout


def _registry_keys(repo: pathlib.Path, base: str, path: str, text: bytes,
                   seen: frozenset[str]) -> set[str]:
    """Extract the reviewed-file keys from one trusted-base registry module.

    Only top-level statements are interpreted, so test functions in a
    registry module cannot affect the extracted set, and no base tree code
    is executed. The recognized vocabulary is the frozen-literal shape:
    an initial ``REVIEWED_FILES = {...}``, constant subscript assignments,
    pure dict-literal helper names, ``REVIEWED_FILES.update(...)`` of those
    or of an imported alias registry, and ``from X import REVIEWED_FILES as
    ALIAS`` merges. Everything else that executes or could mutate at import
    fails closed: control flow including ``match``, any call other than the
    update gate (bare-name, attribute, exec/eval, calls inside assigned or
    merged expressions), class definitions (whose bodies execute), def-time
    decorators/defaults/annotations that mention the registry or call a name
    defined in the same module, decorators (with or without call parens)
    rooted at a same-module name, alias or multi-target assignment, dynamic
    subscript keys, exact string-constant lookups, relative or shadowing
    ``REVIEWED_FILES`` imports, and any reuse or rebinding of a tracked
    helper or alias name after its binding.
    Registry files sit on CRITICAL review paths, and imports are parsed,
    not executed; mutation hiding in an imported module's own import side
    effects is the one residual outside this parser's reach.
    """
    if path in seen:
        raise SmokeUnqualified("SMOKE_REVIEWED_REGISTRY_MALFORMED")
    if not text:
        raise SmokeUnqualified("SMOKE_REVIEWED_REGISTRY_MALFORMED")
    try:
        tree = ast.parse(text.decode("utf-8"), filename=path)
    except (UnicodeError, SyntaxError):
        raise SmokeUnqualified("SMOKE_REVIEWED_REGISTRY_MALFORMED") from None
    keys: set[str] | None = None
    literals: dict[str, set[str]] = {}
    imports: dict[str, str] = {}
    module_defs: set[str] = set()

    def merge(argument: ast.expr, chain: frozenset[str]) -> None:
        nonlocal keys
        if keys is None:
            raise SmokeUnqualified("SMOKE_REVIEWED_REGISTRY_MALFORMED")
        if isinstance(argument, ast.Name) and argument.id in literals:
            keys |= literals[argument.id]
            return
        if isinstance(argument, ast.Name) and argument.id in imports:
            blob = _registry_blob(repo, base, imports[argument.id])
            if blob is None:
                raise SmokeUnqualified("SMOKE_REVIEWED_REGISTRY_MALFORMED")
            keys |= _registry_keys(repo, base, imports[argument.id], blob, chain)
            return
        added = _registry_dict_keys(argument)
        if added is None:
            raise SmokeUnqualified("SMOKE_REVIEWED_REGISTRY_MALFORMED")
        keys |= added

    for node in tree.body:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            continue  # module docstring or stray literal: cannot mutate
        if isinstance(node, ast.ClassDef):
            # Class bodies execute at import, so the whole statement counts
            # as module-level code: any registry mention or any call inside
            # (including bases, decorators and the body) is refused.
            if _mentions_name(node, "REVIEWED_FILES") or _contains_call(node):
                raise SmokeUnqualified("SMOKE_REVIEWED_REGISTRY_MALFORMED")
            module_defs.add(node.name)
            continue
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # Function bodies run only when called and nothing at module
            # level may call them (see the call gate below), so only the
            # def-time expressions are checked. A def-time call rooted at a
            # name defined in this module executes an unchecked body; calls
            # rooted at imported names stay under the documented import
            # residual.
            edges: list[ast.expr] = [*node.decorator_list]
            args = node.args
            edges.extend(args.defaults)
            edges.extend(d for d in args.kw_defaults if d is not None)
            annotated = (*args.posonlyargs, *args.args, *args.kwonlyargs,
                         *(a for a in (args.vararg, args.kwarg) if a))
            edges.extend(a.annotation for a in annotated
                         if a.annotation is not None)
            for bound in getattr(node, "type_params", ()):
                edge = getattr(bound, "bound", None)
                if edge is not None:
                    edges.append(edge)
            if node.returns is not None:
                edges.append(node.returns)
            for edge in edges:
                if _mentions_name(edge, "REVIEWED_FILES"):
                    raise SmokeUnqualified("SMOKE_REVIEWED_REGISTRY_MALFORMED")
                for call in (sub for sub in ast.walk(edge)
                             if isinstance(sub, ast.Call)):
                    root = call.func
                    while isinstance(root, ast.Attribute):
                        root = root.value
                    if isinstance(root, ast.Name) and root.id in module_defs:
                        raise SmokeUnqualified("SMOKE_REVIEWED_REGISTRY_MALFORMED")
            for decorator in node.decorator_list:
                # A decorator expression is applied (called) at import even
                # without call parens: @dec is g = dec(g). Refuse it when its
                # leftmost base is defined in this module; imported bases
                # (pytest.fixture, pytest.mark.parametrize) stay allowed.
                root = decorator
                while isinstance(root, (ast.Attribute, ast.Subscript)):
                    root = root.value
                if isinstance(root, ast.Name) and root.id in module_defs:
                    raise SmokeUnqualified("SMOKE_REVIEWED_REGISTRY_MALFORMED")
            module_defs.add(node.name)
            continue
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == "REVIEWED_FILES":
                    if (node.module is None or alias.asname is None or node.level
                            or alias.asname in literals or alias.asname in imports):
                        # Relative imports resolve differently, and an alias
                        # that shadows an earlier helper or registry binding
                        # makes the tracked mapping stale.
                        raise SmokeUnqualified("SMOKE_REVIEWED_REGISTRY_MALFORMED")
                    imports[alias.asname] = node.module.replace(".", "/") + ".py"
                elif alias.asname is not None and (
                        alias.asname in literals or alias.asname in imports):
                    # Rebinding a tracked helper or alias name invalidates
                    # its mapping.
                    raise SmokeUnqualified("SMOKE_REVIEWED_REGISTRY_MALFORMED")
            continue
        if isinstance(node, ast.Import):
            if any(alias.asname is not None
                   and (alias.asname in literals or alias.asname in imports)
                   for alias in node.names):
                raise SmokeUnqualified("SMOKE_REVIEWED_REGISTRY_MALFORMED")
            continue
        if isinstance(node, ast.Assign):
            # No statement may execute a call while assigning: the call's
            # side effects are invisible to static extraction.
            if _contains_call(node):
                raise SmokeUnqualified("SMOKE_REVIEWED_REGISTRY_MALFORMED")
            if len(node.targets) == 1:
                target = node.targets[0]
                if isinstance(target, ast.Name) and target.id == "REVIEWED_FILES":
                    if keys is not None:
                        raise SmokeUnqualified("SMOKE_REVIEWED_REGISTRY_MALFORMED")
                    keys = _registry_dict_keys(node.value)
                    if keys is None:
                        raise SmokeUnqualified("SMOKE_REVIEWED_REGISTRY_MALFORMED")
                    continue
                literal = _registry_subscript_key(target)
                if literal is not None:
                    if keys is None:
                        raise SmokeUnqualified("SMOKE_REVIEWED_REGISTRY_MALFORMED")
                    keys.add(literal)
                    continue
                if (isinstance(target, ast.Subscript)
                        and isinstance(target.value, ast.Name)
                        and target.value.id == "REVIEWED_FILES"):
                    raise SmokeUnqualified("SMOKE_REVIEWED_REGISTRY_MALFORMED")
                if isinstance(target, ast.Name):
                    named = _registry_dict_keys(node.value)
                    if named is not None:
                        # A helper dict that references an earlier helper or
                        # an imported alias aliases the same runtime object;
                        # refuse the alias, and never rebind an alias.
                        if (_mentions_any(node.value, {*literals, *imports})
                                or target.id in imports):
                            raise SmokeUnqualified("SMOKE_REVIEWED_REGISTRY_MALFORMED")
                        literals[target.id] = named
                    elif (_mentions_name(node, "REVIEWED_FILES")
                            or target.id in imports
                            or _mentions_any(node, {*literals, *imports})):
                        raise SmokeUnqualified("SMOKE_REVIEWED_REGISTRY_MALFORMED")
                    continue
                raise SmokeUnqualified("SMOKE_REVIEWED_REGISTRY_MALFORMED")
            if (_mentions_name(node, "REVIEWED_FILES")
                    or _mentions_any(node, {*literals, *imports})):
                raise SmokeUnqualified("SMOKE_REVIEWED_REGISTRY_MALFORMED")
            continue
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            call = node.value
            if (isinstance(call.func, ast.Attribute) and call.func.attr == "update"
                    and isinstance(call.func.value, ast.Name)
                    and call.func.value.id == "REVIEWED_FILES"):
                if keys is None or len(call.args) != 1 or call.keywords:
                    raise SmokeUnqualified("SMOKE_REVIEWED_REGISTRY_MALFORMED")
                if _contains_call(call.args[0]):
                    raise SmokeUnqualified("SMOKE_REVIEWED_REGISTRY_MALFORMED")
                merge(call.args[0], seen | {path})
                continue
            # Every other module-level call executes unreviewed code whose
            # effects (including registry mutation through helpers, exec or
            # an imported module) static extraction cannot see.
            raise SmokeUnqualified("SMOKE_REVIEWED_REGISTRY_MALFORMED")
        if isinstance(node, _CONTROL_FLOW_STATEMENTS):
            raise SmokeUnqualified("SMOKE_REVIEWED_REGISTRY_MALFORMED")
        if (_mentions_name(node, "REVIEWED_FILES")
                or _mentions_any(node, {*literals, *imports})):
            raise SmokeUnqualified("SMOKE_REVIEWED_REGISTRY_MALFORMED")
    if keys is None:
        raise SmokeUnqualified("SMOKE_REVIEWED_REGISTRY_MALFORMED")
    return keys


def _reviewed_registries(
    repo: pathlib.Path, base: str,
) -> tuple[tuple[frozenset[str], tuple[str, ...]], ...]:
    """Read every wired identity pin registry from the trusted base commit.

    Each registry is parsed with ``ast`` only; no base tree code is executed.
    A base object predating a registry keeps that registry's legacy empty
    source set (nothing was identity reviewed there, so no ownership mapping
    can be lost); an unreadable or present-but-unrecognized registry fails
    closed instead of silently dropping identity-reviewed sources from
    smoke coverage.
    """
    out: list[tuple[frozenset[str], tuple[str, ...]]] = []
    for path, tests in _IDENTITY_PIN_REGISTRIES:
        blob = _registry_blob(repo, base, path)
        sources = (frozenset() if blob is None else
                   frozenset(_registry_keys(repo, base, path, blob, frozenset())))
        out.append((sources, tests))
    return tuple(out)


def select_modules(
    repo: pathlib.Path, changed: Sequence[str], *,
    identity_registries: Sequence[tuple[frozenset[str], tuple[str, ...]]],
) -> tuple[str, ...]:
    """Pick fixed ownership dependencies, then capped source-proximate tests.

    Fixed dependencies — the paper stage pin and the owning test modules of
    every identity registry whose reviewed sources intersect the diff — are
    exempt from the module cap, so a selection legitimately exceeds
    _MAX_SELECTED_MODULES when several ownership groups fire together and
    the cap never truncates a required owner.
    """
    root = repo.resolve(strict=True)
    selected: set[str] = set()
    for path in changed:
        if not path or path.startswith("/") or ".." in pathlib.PurePosixPath(path).parts:
            raise SmokeUnqualified("SMOKE_PATH_UNSAFE")
        file = root / path
        if path.endswith(".py") and file.exists() and file.is_file():
            if not file.resolve().is_relative_to(root):
                raise SmokeUnqualified("SMOKE_PATH_ESCAPED")
            if path.startswith("tests/") and file.name.startswith("test_"):
                selected.add(path)
            else:
                candidate = root / "tests" / ("test_" + file.stem + ".py")
                if candidate.exists() and candidate.is_file():
                    selected.add(candidate.relative_to(root).as_posix())
    required: tuple[str, ...] = ()
    if _PAPER_STAGE_SOURCES.intersection(changed):
        required += (_PAPER_STAGE_TEST,)
    # Identity-reviewed ownership keeps the same fixed-dependency rule as the
    # paper stage pin: each registry contributes exactly its own owning
    # modules, they cannot be lost to alphabetic ties or the module cap, and
    # an unavailable module fails the check.
    for sources, tests in identity_registries:
        if sources.intersection(changed):
            required += tests
    for path in required:
        file = root / path
        try:
            available = (not file.is_symlink() and file.is_file()
                         and file.resolve().is_relative_to(root)
                         and file.stat().st_size <= _MAX_MODULE_BYTES)
        except OSError:
            available = False
        if not available:
            raise SmokeUnqualified("SMOKE_REQUIRED_TEST_UNAVAILABLE")
    # Fixed dependencies cannot be lost to alphabetic ties or the module cap.
    # Other source-proximate tests retain their deterministic
    # alphabetic ties and fixed cap. Never let a PR path select a workflow,
    # executable, shell expression, URL, or arbitrary filesystem target.
    ordered = sorted(selected)
    bounded = tuple(p for p in ordered
                    if (root / p).stat().st_size <= _MAX_MODULE_BYTES)
    remaining = tuple(p for p in bounded if p not in required)
    # Fixed dependencies are exempt from the cap; the cap bounds only the
    # source-proximate picks and never goes negative when several required
    # ownership groups fire together.
    return tuple(dict.fromkeys((
        _BASELINE, *required,
        *remaining[:max(0, _MAX_SELECTED_MODULES - len(required))],
    )))


def check_changed_python(repo: pathlib.Path, changed: Sequence[str]) -> None:
    """Syntax-only on changed Python; no source execution on this step."""
    for relative in changed:
        if not relative.endswith(".py"):
            continue
        file = repo / relative
        if not file.is_file() or not file.resolve().is_relative_to(repo.resolve()):
            raise SmokeUnqualified("SMOKE_PYTHON_SOURCE_UNAVAILABLE")
        try:
            compile(file.read_bytes(), relative, "exec")
        except (OSError, UnicodeError, SyntaxError):
            raise SmokeUnqualified("SMOKE_PYTHON_SYNTAX_FAILED") from None


def main() -> int:
    p = argparse.ArgumentParser(description="Fast PR smoke checks")
    p.add_argument("--repo", type=pathlib.Path, required=True)
    p.add_argument("--base", required=True)
    p.add_argument("--head", required=True)
    args = p.parse_args()
    root = args.repo.resolve(strict=True)
    if not (root / ".git").exists():
        raise SmokeUnqualified("SMOKE_REPO_UNAVAILABLE")
    paths = _diff_paths(root, args.base, args.head)
    check_changed_python(root, paths)
    # args.base is the trusted-base classifier's verified base SHA; the
    # reviewed-source registries are read from that commit, not the checkout.
    selected = select_modules(
        root, paths, identity_registries=_reviewed_registries(root, args.base),
    )
    print(f"CI_PR_SMOKE selected_tests={len(selected)} changed_paths={len(paths)}",
          flush=True)
    try:
        # The GitHub job enforces its own overall timeout; subprocess is
        # additionally bounded to prevent a single slow test from stalling
        # PRs. The bound also covers the fixed identity-review ownership
        # modules (~61s warm locally on an M2; shared runners run slower),
        # while staying inside the pr_fast job's own minutes budget.
        done = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "--tb=short", *selected],
            cwd=root, check=False, timeout=330,
        )
    except subprocess.TimeoutExpired:
        print("CI_PR_SMOKE_TEST_BUDGET_EXHAUSTED", file=sys.stderr)
        return 1
    return done.returncode


if __name__ == "__main__":
    sys.exit(main())

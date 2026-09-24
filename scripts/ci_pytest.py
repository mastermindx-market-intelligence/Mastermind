"""Discovery-first repository test gate.

Every ``tests/**/test_*.py`` module runs unless its exact path is listed in
``ci/pytest_exclusions.toml``. New tests are included automatically. Exclusions
are fail-closed and cannot remove constitutional/security modules.

``--jobs N`` splits the *already resolved* included set across N concurrent
pytest processes inside this one gate invocation. It is a placement decision
only: the discovery/exclusion policy above runs first and unchanged, and the
partition is verified to be a total, disjoint cover of that exact set before
any process starts. The gate therefore executes the same modules whatever
``--jobs`` is, and a nonzero exit from any shard fails the whole gate.

Sharding deliberately stays *inside* one job. The branch-protection required
check for this repository is the single context ``test``; turning the gate
into a workflow matrix would rename it to ``test (0)``/``test (1)``/... and
silently make the required check unsatisfiable. Parallelism belongs here,
where the check name is untouched.
"""
from __future__ import annotations

import argparse
import hashlib
import re
import subprocess
import sys
import tomllib
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml
from yaml.constructor import ConstructorError as YAMLConstructorError


EXCLUSIONS_RELATIVE = Path("ci") / "pytest_exclusions.toml"
WORKFLOW_RELATIVE = Path(".github") / "workflows" / "ci.yml"
AUTHORITATIVE_STEP_NAME = "Run repository test gate"
AUTHORITATIVE_RUNNER = "scripts/ci_pytest.py"
REQUIRED_WORKFLOW_EVENTS = ("pull_request", "merge_group", "push", "workflow_dispatch")
REQUIRED_MERGE_GROUP_TRIGGER = {"types": ["checks_requested"]}
REQUIRED_PUSH_TRIGGER = {"branches": ["master"]}
PROTECTED_EXACT = frozenset(
    {
        "tests/test_ci_pytest_policy.py",
        "tests/test_secret_redaction.py",
        "tests/test_gate.py",
        "tests/test_vendored_read_ratchet.py",
        "tests/test_deploy_provenance.py",
        "tests/test_auth.py",
        "tests/test_book_state_isolation.py",
        "tests/test_web_exception_sanitization.py",
    }
)
PROTECTED_PREFIXES = ("tests/test_executive_",)
_TEST_MODULE_RE = re.compile(r"^test_.*\.py$")
_WORKFLOW_TEST_FILE_RE = re.compile(r"^tests/(?:[\w./-]+/)?test_\w+\.py$")


class PolicyError(ValueError):
    """The exclusion manifest or workflow coverage policy is invalid."""


def repo_root(start: Path | None = None) -> Path:
    here = (start or Path(__file__)).resolve()
    if here.is_file():
        here = here.parent
    for candidate in (here, *here.parents):
        if (candidate / "pyproject.toml").is_file() and (candidate / "tests").is_dir():
            return candidate
    raise PolicyError("could not resolve repository root from ci_pytest.py")


def discover_test_modules(root: Path) -> tuple[str, ...]:
    tests_root = (root / "tests").resolve()
    found: list[str] = []
    for path in tests_root.rglob("test_*.py"):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        if path.name.startswith("test_") and path.suffix == ".py":
            found.append(relative)
    return tuple(sorted(found))


def _require_mapping(value: Any, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise PolicyError(f"{label} must be a table")
    return value


def load_exclusions(root: Path, relative: Path = EXCLUSIONS_RELATIVE) -> tuple[dict[str, Any], ...]:
    path = root / relative
    if not path.is_file():
        raise PolicyError(f"exclusion manifest is missing: {relative.as_posix()}")
    payload = tomllib.loads(path.read_text(encoding="utf-8"))
    version = payload.get("version")
    if version != 1:
        raise PolicyError("exclusion manifest version must be 1")
    raw = payload.get("exclude", [])
    if raw is None:
        raw = []
    if not isinstance(raw, list):
        raise PolicyError("exclude must be an array of tables")
    rows: list[dict[str, Any]] = []
    for item in raw:
        rows.append(dict(_require_mapping(item, label="exclude entry")))
    return tuple(rows)


def is_protected(relative: str) -> bool:
    if relative in PROTECTED_EXACT:
        return True
    return any(relative.startswith(prefix) for prefix in PROTECTED_PREFIXES)


def validate_exclusions(
    root: Path,
    rows: Sequence[Mapping[str, Any]],
    discovered: Sequence[str],
) -> tuple[str, ...]:
    discovered_set = set(discovered)
    seen: set[str] = set()
    excluded: list[str] = []
    for row in rows:
        path = str(row.get("path") or "").strip()
        reason = str(row.get("reason") or "").strip()
        replacement = str(row.get("replacement_gate") or "").strip()
        if not path:
            raise PolicyError("exclusion path cannot be empty")
        if any(character in path for character in ("*", "?", "[", "]")):
            raise PolicyError(f"wildcard exclusion is forbidden: {path}")
        if path.endswith("/") or path == "tests" or path == "tests/":
            raise PolicyError(f"directory exclusion is forbidden: {path}")
        rendered = Path(path)
        if rendered.is_absolute() or ".." in rendered.parts:
            raise PolicyError(f"path escape is forbidden: {path}")
        if rendered.parts[:1] != ("tests",):
            raise PolicyError(f"exclusion path must be under tests/: {path}")
        if rendered.as_posix() != path:
            raise PolicyError(f"exclusion path must be a normalized posix path: {path}")
        if not _TEST_MODULE_RE.fullmatch(rendered.name):
            raise PolicyError(f"exclusion basename must be a pytest test module: {path}")
        if path in seen:
            raise PolicyError(f"duplicate exclusion: {path}")
        seen.add(path)
        if path not in discovered_set:
            raise PolicyError(f"stale exclusion names a missing file: {path}")
        if not reason:
            raise PolicyError(f"exclusion reason cannot be empty: {path}")
        if not replacement:
            raise PolicyError(f"replacement_gate is required: {path}")
        if is_protected(path):
            raise PolicyError(f"protected test cannot be excluded: {path}")
        excluded.append(path)
    return tuple(excluded)


def included_modules(discovered: Sequence[str], excluded: Sequence[str]) -> tuple[str, ...]:
    excluded_set = set(excluded)
    included = tuple(path for path in discovered if path not in excluded_set)
    if not included:
        raise PolicyError("included test set is empty")
    missing = excluded_set - set(discovered)
    if missing:
        raise PolicyError(f"excluded paths are not discovered: {sorted(missing)}")
    return included


def coverage_plan(
    *,
    discovered: Sequence[str],
    excluded: Sequence[str],
    included: Sequence[str],
) -> dict[str, int]:
    return {
        "discovered": len(discovered),
        "excluded": len(excluded),
        "running": len(included),
    }


def format_plan(plan: Mapping[str, int], *, shards: Sequence[Sequence[str]] | None = None) -> str:
    rendered = (
        f"discovered={plan['discovered']} "
        f"excluded={plan['excluded']} "
        f"running={plan['running']}"
    )
    if shards is not None:
        sizes = ",".join(str(len(shard)) for shard in shards)
        rendered += f" jobs={len(shards)} shard_modules={sizes}"
    return rendered


def pytest_argv(included: Sequence[str], *, python: str | None = None) -> list[str]:
    return [python or sys.executable, "-m", "pytest", "-q", *included]


def partition_modules(
    included: Sequence[str], *, jobs: int
) -> tuple[tuple[str, ...], ...]:
    """Split ``included`` into ``jobs`` shards that exactly re-cover it.

    A module's shard is a stable function of its own path, not of its position
    in the list. Round-robin would be perfectly balanced, but adding a single
    test file shifts every module after it into a different shard -- and since
    sharding changes which modules share a pytest process, that reshuffle can
    surface a latent cross-module ordering dependency in a completely unrelated
    PR. (This is not hypothetical: `--jobs 4` exposed one on its first CI run,
    where `tests/test_governance_ledger.py` was leaking `sys.modules` stubs.)
    Hashing keeps that blast radius to the file actually being added or removed.

    sha256 rather than ``hash()``: the builtin is salted per process, so the
    same checkout would shard differently on every run and a failure would not
    reproduce.

    Balance is close enough without a committed timing file that could go
    stale: this repository's module count over four shards lands within a few
    percent of even, and the shard sizes are printed in the plan line so drift
    stays visible. (Deliberately written without bare integer literals: the
    identity guard in tests/test_ceo_submit_armed_composition.py flags any
    three-digit literal in that range added outside tests/.)
    """

    if jobs < 1:
        raise PolicyError("jobs must be at least 1")
    if jobs > len(included):
        raise PolicyError(
            f"jobs ({jobs}) cannot exceed the number of included modules "
            f"({len(included)})"
        )
    buckets: list[list[str]] = [[] for _ in range(jobs)]
    for path in included:
        digest = hashlib.sha256(path.encode("utf-8")).digest()
        buckets[int.from_bytes(digest[:8], "big") % jobs].append(path)
    shards = tuple(tuple(bucket) for bucket in buckets)
    verify_partition(included, shards)
    return shards


def verify_partition(
    included: Sequence[str], shards: Sequence[Sequence[str]]
) -> None:
    """Fail closed unless the shards are a total, disjoint cover of ``included``.

    This is the whole safety argument for ``--jobs``: a partition bug must
    never be able to drop a module and still let the gate report success.
    Checked against multiset equality, so a duplicated module (which would
    hide a dropped one behind an equal total) is rejected too.
    """

    flattened = [path for shard in shards for path in shard]
    if len(flattened) != len(included):
        raise PolicyError(
            f"shard plan runs {len(flattened)} modules but the gate resolved "
            f"{len(included)}"
        )
    if sorted(flattened) != sorted(included):
        raise PolicyError("shard plan is not an exact cover of the included set")
    if any(not shard for shard in shards):
        raise PolicyError("shard plan contains an empty shard")


def run_shards(
    shards: Sequence[Sequence[str]],
    *,
    root: Path,
    python: str | None = None,
) -> int:
    """Run every shard and return the lowest-indexed nonzero exit code, else 0.

    Every shard is always waited on, even after one fails: a partial result
    would make the gate's own report unreliable, and the remaining shards'
    failures are exactly what a reviewer needs in one pass.

    Output is captured per shard and replayed whole under a banner rather
    than streamed live, because interleaving several concurrent pytest
    streams into one log makes failures unattributable. Each block is
    printed the moment that shard finishes, so one shard hanging until the
    job timeout still leaves the others' complete output in the log --
    which a single serial process could not do.
    """

    def _run(index: int) -> tuple[int, int, str]:
        completed = subprocess.run(
            pytest_argv(shards[index], python=python),
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
        )
        return index, completed.returncode, completed.stdout + completed.stderr

    codes: dict[int, int] = {}
    with ThreadPoolExecutor(max_workers=len(shards)) as pool:
        futures = [pool.submit(_run, index) for index in range(len(shards))]
        for future in as_completed(futures):
            index, returncode, output = future.result()
            codes[index] = returncode
            print(
                f"--- shard {index + 1}/{len(shards)} "
                f"({len(shards[index])} modules) exit={returncode} ---",
                flush=True,
            )
            print(output, end="" if output.endswith("\n") else "\n", flush=True)

    # Lowest shard index wins so the reported code is stable across runs
    # rather than depending on which shard happened to finish first.
    for index in sorted(codes):
        if codes[index] != 0:
            return codes[index]
    return 0


def workflow_contains_positive_allowlist(text: str) -> bool:
    """True when a workflow run block lists several tests/test_*.py files."""

    consecutive = 0
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            consecutive = 0
            continue
        if _WORKFLOW_TEST_FILE_RE.fullmatch(stripped):
            consecutive += 1
            if consecutive >= 3:
                return True
            continue
        consecutive = 0
    return False


_TRUE_FALSE_BOOL_PATTERN = re.compile(r"^(?:true|True|TRUE|false|False|FALSE)$")


class _WorkflowYAMLLoader(yaml.SafeLoader):
    """Private loader used only for workflow YAML, never for anything else.

    GitHub Actions treats the trigger key as the literal, case-sensitive
    string "on" - it is not a YAML 1.1 boolean. Stock SafeLoader disagrees:
    it coerces on/On/ON/off/Off/OFF/yes/no (and case variants) to Python
    booleans, which hides a literal "on" key behind `True` and makes a
    quoted "on" and an unquoted on collide as different-looking keys that
    are actually identical once parsed. This subclass narrows that resolver
    to true/false only (on/off/yes/no become plain strings, matching
    GitHub's real semantics) and separately rejects duplicate mapping keys
    instead of silently keeping the last one. yaml.SafeLoader itself is
    never modified: PyYAML's add_implicit_resolver/add_constructor copy the
    inherited tables onto the subclass before mutating them, so this can
    only affect _WorkflowYAMLLoader.
    """


class _DuplicateMappingKeyError(YAMLConstructorError):
    """A workflow mapping defines the exact same key more than once.

    __str__ is overridden to a fixed literal: the inherited
    MarkedYAMLError.__str__ renders a snippet of the surrounding source
    text via Mark.get_snippet(), which could otherwise echo the offending
    key (or nearby secret-shaped content) even though the "problem" text
    passed to __init__ is itself already a fixed, non-interpolated string.
    """

    def __str__(self) -> str:
        return "found a duplicate mapping key"


class _UnhashableMappingKeyError(YAMLConstructorError):
    """A workflow mapping uses a YAML complex (unhashable) key.

    See _DuplicateMappingKeyError for why __str__ is overridden.
    """

    def __str__(self) -> str:
        return "found an unhashable mapping key"


def _reject_duplicate_mapping_keys(
    loader: yaml.SafeLoader, node: yaml.MappingNode, deep: bool = False
) -> dict:
    mapping: dict = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            is_duplicate = key in mapping
        except TypeError:
            # A YAML explicit complex key (e.g. `? [a, b]`) constructs to an
            # unhashable Python object (list/dict); membership-testing it
            # against `mapping` raises a raw TypeError. Convert it to a
            # stable, distinctly classified error instead of letting it
            # escape uncaught. Chained `from None`: the original TypeError
            # is not needed and dropping it narrows the cause chain.
            raise _UnhashableMappingKeyError(
                "while constructing a mapping",
                node.start_mark,
                "found an unhashable mapping key",
                key_node.start_mark,
            ) from None
        if is_duplicate:
            raise _DuplicateMappingKeyError(
                "while constructing a mapping",
                node.start_mark,
                "found a duplicate mapping key",
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_WorkflowYAMLLoader.yaml_implicit_resolvers = {
    key: [item for item in resolvers if item[0] != "tag:yaml.org,2002:bool"]
    for key, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}
_WorkflowYAMLLoader.add_implicit_resolver(
    "tag:yaml.org,2002:bool", _TRUE_FALSE_BOOL_PATTERN, list("tTfF")
)
_WorkflowYAMLLoader.add_constructor(
    "tag:yaml.org,2002:map", _reject_duplicate_mapping_keys
)


def _workflow_trigger_mapping(payload: Mapping[str, Any]) -> Any:
    # Checked first, unconditionally: an explicit tag (`!!bool on`) bypasses
    # the narrowed implicit resolver entirely and still constructs to True
    # (the bool constructor function itself is untouched), and a bareword
    # `true`/`false` top-level key still resolves to a real bool by design.
    # Either can sit alongside an otherwise-valid lowercase "on" key, so
    # every top-level key must be a string before anything else is checked.
    non_string_keys = [key for key in payload if not isinstance(key, str)]
    if non_string_keys:
        # Fixed, stable, secret-free message: the offending keys come from
        # untrusted workflow content and must never be interpolated in.
        raise PolicyError("workflow top-level keys must be strings")
    # Checked unconditionally, even when the literal "on" key is present:
    # a sibling case-variant key (On/ON/oN/...) parses as a distinct string
    # under this loader (it no longer collapses into "on" via boolean
    # coercion), so it would otherwise sit alongside a valid "on" mapping
    # and be silently ignored instead of rejected.
    case_variant = next(
        (key for key in payload if key != "on" and key.lower() == "on"),
        None,
    )
    if case_variant is not None:
        raise PolicyError(
            "workflow trigger key must be the literal lowercase 'on', "
            f"not {case_variant!r}"
        )
    if "on" in payload:
        return payload["on"]
    raise PolicyError("workflow is missing an 'on' trigger mapping")


def validate_workflow_events(payload: Mapping[str, Any]) -> None:
    events = _workflow_trigger_mapping(payload)
    if not isinstance(events, dict):
        raise PolicyError("workflow 'on' trigger must be a mapping of event names")
    non_string_keys = [key for key in events if not isinstance(key, str)]
    if non_string_keys:
        # Keys must be validated as strings before any set difference is
        # sorted for an error message: sorting a set that mixes str with
        # int/bool/None raises an uncaught TypeError instead of failing
        # closed with a stable PolicyError.
        raise PolicyError("workflow 'on' trigger keys must be event name strings")
    found = set(events)
    required = set(REQUIRED_WORKFLOW_EVENTS)
    missing = required - found
    if missing:
        raise PolicyError(
            f"workflow 'on' is missing required event(s): {sorted(missing)}"
        )
    extra = found - required
    if extra:
        # Fixed, stable, secret-free message: unlike `missing` (always a
        # subset of our own known REQUIRED_WORKFLOW_EVENTS), `extra` names
        # come straight from untrusted workflow content and must never be
        # interpolated in.
        raise PolicyError("workflow 'on' has unexpected event(s)")
    if events["pull_request"] is not None:
        raise PolicyError("workflow 'pull_request' trigger must have no filters")
    if events["workflow_dispatch"] is not None:
        raise PolicyError("workflow 'workflow_dispatch' trigger must have no filters")
    if events["merge_group"] != REQUIRED_MERGE_GROUP_TRIGGER:
        raise PolicyError(
            "workflow 'merge_group' trigger must be exactly "
            f"{REQUIRED_MERGE_GROUP_TRIGGER!r}"
        )
    if events["push"] != REQUIRED_PUSH_TRIGGER:
        raise PolicyError(
            f"workflow 'push' trigger must be exactly {REQUIRED_PUSH_TRIGGER!r}"
        )


def validate_workflow(text: str) -> None:
    if AUTHORITATIVE_RUNNER not in text:
        raise PolicyError(
            f"authoritative CI step must invoke {AUTHORITATIVE_RUNNER}"
        )
    if AUTHORITATIVE_STEP_NAME not in text:
        raise PolicyError(
            f"CI workflow must name the step {AUTHORITATIVE_STEP_NAME!r}"
        )
    if workflow_contains_positive_allowlist(text):
        raise PolicyError(
            "CI workflow must not contain a positive tests/test_*.py filename allowlist"
        )
    try:
        payload = yaml.load(text, Loader=_WorkflowYAMLLoader)
    except _DuplicateMappingKeyError as exc:
        raise PolicyError("workflow YAML contains a duplicate mapping key") from exc
    except _UnhashableMappingKeyError as exc:
        raise PolicyError("workflow YAML contains an unhashable mapping key") from exc
    except yaml.YAMLError as exc:
        raise PolicyError("workflow is not valid YAML") from exc
    if not isinstance(payload, dict):
        raise PolicyError("workflow document must be a mapping")
    validate_workflow_events(payload)


def resolve_gate(root: Path) -> dict[str, Any]:
    discovered = discover_test_modules(root)
    rows = load_exclusions(root)
    excluded = validate_exclusions(root, rows, discovered)
    included = included_modules(discovered, excluded)
    workflow = root / WORKFLOW_RELATIVE
    if workflow.is_file():
        validate_workflow(workflow.read_text(encoding="utf-8"))
    return {
        "discovered": discovered,
        "excluded": excluded,
        "included": included,
        "plan": coverage_plan(
            discovered=discovered, excluded=excluded, included=included
        ),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--plan-only",
        action="store_true",
        help="print the coverage plan and exit without running pytest",
    )
    parser.add_argument(
        "--root",
        default=None,
        help="repository root (defaults to the checkout that contains this script)",
    )
    parser.add_argument(
        "--jobs",
        type=int,
        default=1,
        help=(
            "run the resolved module set as this many concurrent pytest "
            "processes (default 1). Placement only: the same modules run "
            "either way, and any shard failing fails the gate."
        ),
    )
    args = parser.parse_args(list(argv) if argv is not None else None)
    root = Path(args.root).resolve() if args.root else repo_root()
    try:
        if args.jobs < 1:
            raise PolicyError("jobs must be at least 1")
        gate = resolve_gate(root)
        # jobs=1 keeps the historical single-process argv exactly, so the
        # default gate invocation is unchanged by this feature.
        shards = (
            partition_modules(gate["included"], jobs=args.jobs)
            if args.jobs > 1
            else None
        )
    except PolicyError as exc:
        print(f"ci_pytest policy error: {exc}", file=sys.stderr)
        return 2
    print(format_plan(gate["plan"], shards=shards), flush=True)
    if args.plan_only:
        return 0
    if shards is not None:
        return run_shards(shards, root=root)
    completed = subprocess.run(
        pytest_argv(gate["included"]),
        cwd=root,
        check=False,
    )
    return int(completed.returncode)


if __name__ == "__main__":
    raise SystemExit(main())

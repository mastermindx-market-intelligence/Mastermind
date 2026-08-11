"""control_plane.strategic_state — validated read of config/strategic_state.yml.

That file states what the company is currently trying to accomplish (phase, north
star, P0 objectives, resource policy, standing constraints).  This module is the
only supported way to read it: it parses, validates, and caches it, and raises
:class:`StrategicStateError` on anything malformed.

Design laws
-----------
* **Fail loud.**  This is the deliberate opposite of :mod:`control_plane.contracts`,
  which degrades to ``{}`` so a missing artifact contract can never abort a build.
  The trade-off inverts here.  A strategic state that silently reads as empty means
  a session running with *no* company objectives — precisely the condition under
  which a worker invents its own roadmap.  Malformed state must stop the reader.
* **No runtime coupling.**  Nothing here schedules, dispatches, leases, or executes.
  This module does not import :mod:`control_plane.worker_runtime` and must not:
  the strategic state is orientation, not a control plane.  Wiring an execution
  path off it would violate ``constraints.duplicate_control_planes``.
* **Import-time stdlib only.**  PyYAML is imported lazily inside ``_load()``, the
  same way :mod:`control_plane.contracts` does it, so importing this module pulls
  in no third-party code.
* **Cached.**  Parsed once per process; ``_reset()`` is test-only.

Usage
-----
    from control_plane.strategic_state import load_strategic_state
    state = load_strategic_state()
    state["company_phase"]                       # 'PRE_REVENUE_MVP_CONVERGENCE'
    [o["id"] for o in state["p0"]]               # active objective ids
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parent.parent
_STATE_FILE = _ROOT / "config" / "strategic_state.yml"

#: Schema version this reader understands.  A bump means a migration, not a warning.
SCHEMA = "mastermind.strategic_state.v1"

#: Constraint keys that must always be declared.  Dropping one from the YAML would
#: silently un-prohibit it, so absence is an error rather than a default.
REQUIRED_CONSTRAINTS = (
    "new_feature_expansion",
    "autonomous_production_deploy",
    "autonomous_live_capital_execution",
    "duplicate_control_planes",
    "marketing_org_expansion_before_distribution_proof",
)

_REQUIRED_KEYS = (
    "schema", "meta", "departments", "statuses", "constraint_levels",
    "company_phase", "north_star", "p0", "resource_policy",
    "constraints", "review_triggers",
)
_P0_FIELDS = ("id", "department", "objective", "status")
_VOCABULARIES = ("departments", "statuses", "constraint_levels")
_STR_LISTS = ("north_star", "review_triggers")

#: Resource weights are hand-maintained shares; allow float dust, not real drift.
RESOURCE_SUM_TOLERANCE = 0.01

_ID_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")

# Module-level cache for the default path; None = not yet loaded.
_cache: dict[str, Any] | None = None


class StrategicStateError(RuntimeError):
    """Raised when config/strategic_state.yml is missing, unreadable, or malformed."""


def _fail(where: Path, msg: str) -> None:
    raise StrategicStateError(f"{where}: {msg}")


def _str_list(doc: dict, key: str, where: Path) -> list[str]:
    val = doc.get(key)
    if not isinstance(val, list) or not val:
        _fail(where, f"'{key}' must be a non-empty list")
    for entry in val:
        if not isinstance(entry, str) or not entry.strip():
            _fail(where, f"'{key}' entries must be non-empty strings, got {entry!r}")
    return val


def _validate(doc: Any, where: Path) -> dict[str, Any]:
    """Return `doc` if it is a well-formed strategic state, else raise."""
    if not isinstance(doc, dict) or not doc:
        _fail(where, "top level must be a non-empty mapping")

    missing = [k for k in _REQUIRED_KEYS if k not in doc]
    if missing:
        _fail(where, f"missing required key(s): {', '.join(missing)}")

    if doc["schema"] != SCHEMA:
        _fail(where, f"unsupported schema {doc['schema']!r}; this reader expects {SCHEMA!r}")

    if not isinstance(doc["meta"], dict) or not doc["meta"]:
        _fail(where, "'meta' must be a non-empty mapping")

    for key in _VOCABULARIES:
        _str_list(doc, key, where)
    for key in _STR_LISTS:
        _str_list(doc, key, where)

    if not isinstance(doc["company_phase"], str) or not doc["company_phase"].strip():
        _fail(where, "'company_phase' must be a non-empty string")

    _validate_p0(doc, where)
    _validate_resource_policy(doc, where)
    _validate_constraints(doc, where)
    return doc


def _validate_p0(doc: dict, where: Path) -> None:
    departments, statuses = set(doc["departments"]), set(doc["statuses"])
    p0 = doc["p0"]
    if not isinstance(p0, list) or not p0:
        _fail(where, "'p0' must be a non-empty list of objectives")

    seen: set[str] = set()
    for idx, obj in enumerate(p0):
        at = f"p0[{idx}]"
        if not isinstance(obj, dict):
            _fail(where, f"{at} must be a mapping")
        for field in _P0_FIELDS:
            value = obj.get(field)
            if not isinstance(value, str) or not value.strip():
                _fail(where, f"{at} field '{field}' must be a non-empty string")

        oid = obj["id"]
        if not _ID_RE.match(oid):
            _fail(where, f"{at} id {oid!r} must be UPPER_SNAKE_CASE")
        if oid in seen:
            _fail(where, f"duplicate p0 objective id {oid!r}")
        seen.add(oid)

        if obj["department"] not in departments:
            _fail(where, f"{at} ({oid}) department {obj['department']!r} "
                         f"is not in the declared 'departments' vocabulary")
        if obj["status"] not in statuses:
            _fail(where, f"{at} ({oid}) status {obj['status']!r} "
                         f"is not in the declared 'statuses' vocabulary")


def _validate_resource_policy(doc: dict, where: Path) -> None:
    policy = doc["resource_policy"]
    if not isinstance(policy, dict) or not policy:
        _fail(where, "'resource_policy' must be a non-empty mapping")

    total = 0.0
    for bucket, weight in policy.items():
        # bool is an int subclass — reject it explicitly rather than scoring True as 1.
        if isinstance(weight, bool) or not isinstance(weight, (int, float)):
            _fail(where, f"resource_policy[{bucket!r}] must be a number, got {weight!r}")
        if weight < 0:
            _fail(where, f"resource_policy[{bucket!r}] must not be negative, got {weight!r}")
        total += float(weight)

    if abs(total - 1.0) > RESOURCE_SUM_TOLERANCE:
        _fail(where, f"resource_policy weights must sum to ~1.0 "
                     f"(tolerance {RESOURCE_SUM_TOLERANCE}), got {total:.4f}")


def _validate_constraints(doc: dict, where: Path) -> None:
    levels = set(doc["constraint_levels"])
    constraints = doc["constraints"]
    if not isinstance(constraints, dict) or not constraints:
        _fail(where, "'constraints' must be a non-empty mapping")

    absent = [c for c in REQUIRED_CONSTRAINTS if c not in constraints]
    if absent:
        _fail(where, f"missing required constraint(s): {', '.join(absent)}")

    for name, level in constraints.items():
        if level not in levels:
            _fail(where, f"constraints[{name!r}] level {level!r} "
                         f"is not in the declared 'constraint_levels' vocabulary")


def _parse(path: Path) -> dict[str, Any]:
    try:
        import yaml  # lazy: keeps module import stdlib-only (see Design laws)
    except ImportError as exc:  # pragma: no cover - PyYAML is a declared dependency
        raise StrategicStateError(
            f"{path}: PyYAML is required to read the strategic state"
        ) from exc

    if not path.is_file():
        raise StrategicStateError(f"{path}: strategic state file not found")
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise StrategicStateError(f"{path}: unreadable ({exc})") from exc
    try:
        doc = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise StrategicStateError(f"{path}: not valid YAML ({exc})") from exc

    return _validate(doc, path)


def load_strategic_state(path: str | Path | None = None) -> dict[str, Any]:
    """Return the validated strategic state.

    Raises :class:`StrategicStateError` if the file is missing, unparseable, or
    fails validation — never returns a partial or empty state.

    `path` is for tests and tooling; the default read is cached per process.
    """
    global _cache
    if path is not None:
        return _parse(Path(path))
    if _cache is None:
        _cache = _parse(_STATE_FILE)
    return _cache


def _reset() -> None:
    """Test-only: drop the cache so the next default load re-reads from disk."""
    global _cache
    _cache = None


def company_phase() -> str:
    """The company's current phase, e.g. 'PRE_REVENUE_MVP_CONVERGENCE'."""
    return load_strategic_state()["company_phase"]


def p0_objectives(*, status: str | None = "active") -> list[dict[str, Any]]:
    """P0 objectives, filtered by `status` (pass ``status=None`` for all)."""
    p0 = load_strategic_state()["p0"]
    return [o for o in p0 if status is None or o["status"] == status]


def resource_policy() -> dict[str, float]:
    """Intended share of company effort per investment bucket."""
    return {k: float(v) for k, v in load_strategic_state()["resource_policy"].items()}


def constraint(name: str) -> str | None:
    """The declared level for `name` ('permitted'/'constrained'/'prohibited'), or None."""
    return load_strategic_state()["constraints"].get(name)


def is_prohibited(name: str) -> bool:
    """True when `name` is declared 'prohibited'.

    An *undeclared* constraint returns False: this answers "did the company forbid
    this", not "is this allowed".  Absence of a rule is not permission — that
    judgment belongs to the charter and the authority map, not to this reader.
    """
    return constraint(name) == "prohibited"

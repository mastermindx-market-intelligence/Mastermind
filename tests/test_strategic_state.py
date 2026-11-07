"""Executive OS strategic-state tests (config/strategic_state.yml + its reader).

Covers:
  1. The checked-in strategic state parses through the validated reader
  2. P0 objective ids are unique and UPPER_SNAKE_CASE
  3. P0 department/status values come from the declared vocabularies
  4. Resource-policy weights sum to ~1.0
  5. Required constraint fields exist, and the standing prohibitions are prohibited
  6. The reader FAILS LOUD on every malformation class (its stated design law) —
     each case mutates a copy of the real document so the assertions cannot pass
     for the wrong reason
  7. The reader stays decoupled from the Phase 1B worker runtime (AST import check)
  8. The worker-facing executive contract exists in AGENTS.md / CLAUDE.md and
     points at the strategic state

Deliberately NOT asserted: the number of P0 objectives, the specific phase string,
or any date. Those change as company strategy changes; pinning them would turn a
normal strategy edit into a red build.
"""
from __future__ import annotations

import ast
import copy
from pathlib import Path

import pytest
import yaml

from control_plane import strategic_state as ss
from control_plane.strategic_state import (
    REQUIRED_CONSTRAINTS,
    SCHEMA,
    StrategicStateError,
    load_strategic_state,
)

_ROOT = Path(__file__).resolve().parent.parent
_STATE_FILE = _ROOT / "config" / "strategic_state.yml"
_AGENTS_MD = _ROOT / "AGENTS.md"
_CLAUDE_MD = _ROOT / "CLAUDE.md"

_CONTRACT_HEADING = "## Executive contract"

#: Prohibitions that hold for the whole PRE_REVENUE_MVP_CONVERGENCE phase. Relaxing
#: one is a Chairman/CEO decision, and should have to edit this list to land.
_STANDING_PROHIBITIONS = (
    "autonomous_production_deploy",
    "autonomous_live_capital_execution",
    "duplicate_control_planes",
    "marketing_org_expansion_before_distribution_proof",
)


@pytest.fixture(autouse=True)
def _clear_cache():
    """The reader caches per process; don't leak state across tests."""
    ss._reset()
    yield
    ss._reset()


@pytest.fixture
def state() -> dict:
    return load_strategic_state()


def _write(tmp_path: Path, doc) -> Path:
    path = tmp_path / "strategic_state.yml"
    path.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
    return path


def _mutated(tmp_path: Path, mutate) -> Path:
    """Copy the real document, apply `mutate`, write it to a temp file."""
    doc = copy.deepcopy(yaml.safe_load(_STATE_FILE.read_text(encoding="utf-8")))
    mutate(doc)
    return _write(tmp_path, doc)


# ---------------------------------------------------------------------------
# 1-5. the checked-in strategic state is well-formed
# ---------------------------------------------------------------------------

def test_strategic_state_parses(state):
    assert state["schema"] == SCHEMA
    assert state["company_phase"].strip()
    assert state["north_star"], "north_star must not be empty"
    assert state["meta"]["authority"] == "advisory_and_orientation_only", (
        "the strategic state must keep declaring itself advisory — a runtime "
        "authority here would be the duplicate control plane it prohibits"
    )


def test_p0_ids_are_unique(state):
    ids = [o["id"] for o in state["p0"]]
    assert ids, "p0 must declare at least one objective"
    duplicates = {i for i in ids if ids.count(i) > 1}
    assert not duplicates, f"duplicate p0 objective ids: {sorted(duplicates)}"


def test_p0_ids_are_upper_snake_case(state):
    for objective in state["p0"]:
        oid = objective["id"]
        assert ss._ID_RE.match(oid), f"{oid!r} is not UPPER_SNAKE_CASE"


def test_p0_departments_and_statuses_are_declared(state):
    departments, statuses = set(state["departments"]), set(state["statuses"])
    for objective in state["p0"]:
        assert objective["department"] in departments, (
            f"{objective['id']}: undeclared department {objective['department']!r}"
        )
        assert objective["status"] in statuses, (
            f"{objective['id']}: undeclared status {objective['status']!r}"
        )


def test_p0_objectives_have_prose(state):
    for objective in state["p0"]:
        assert len(objective["objective"].split()) >= 5, (
            f"{objective['id']}: objective text is too thin to act on"
        )


def test_resource_weights_sum_to_one(state):
    total = sum(float(v) for v in state["resource_policy"].values())
    assert total == pytest.approx(1.0, abs=ss.RESOURCE_SUM_TOLERANCE), (
        f"resource_policy weights sum to {total:.4f}, expected ~1.0"
    )


def test_required_constraints_exist(state):
    missing = [c for c in REQUIRED_CONSTRAINTS if c not in state["constraints"]]
    assert not missing, f"missing required constraint(s): {missing}"


def test_constraint_levels_are_declared(state):
    levels = set(state["constraint_levels"])
    for name, level in state["constraints"].items():
        assert level in levels, f"constraints[{name!r}] has undeclared level {level!r}"


def test_standing_prohibitions_are_prohibited(state):
    for name in _STANDING_PROHIBITIONS:
        assert ss.is_prohibited(name), (
            f"{name} must stay 'prohibited' at this company phase, "
            f"got {state['constraints'].get(name)!r}"
        )


def test_review_triggers_declared(state):
    assert state["review_triggers"], "review_triggers must not be empty"


def test_accessors_agree_with_the_document(state):
    assert ss.company_phase() == state["company_phase"]
    assert ss.resource_policy() == {
        k: float(v) for k, v in state["resource_policy"].items()
    }
    assert [o["id"] for o in ss.p0_objectives(status=None)] == [
        o["id"] for o in state["p0"]
    ]
    assert all(o["status"] == "active" for o in ss.p0_objectives())
    assert ss.constraint("does_not_exist") is None
    assert ss.is_prohibited("does_not_exist") is False


# ---------------------------------------------------------------------------
# 6. the reader fails loud (its stated design law)
# ---------------------------------------------------------------------------

def test_missing_file_raises(tmp_path):
    with pytest.raises(StrategicStateError, match="not found"):
        load_strategic_state(tmp_path / "absent.yml")


def test_invalid_yaml_raises(tmp_path):
    path = tmp_path / "strategic_state.yml"
    path.write_text("company_phase: [unclosed\n", encoding="utf-8")
    with pytest.raises(StrategicStateError, match="not valid YAML"):
        load_strategic_state(path)


@pytest.mark.parametrize("payload", ["", "just a string", "[1, 2, 3]"])
def test_non_mapping_document_raises(tmp_path, payload):
    path = tmp_path / "strategic_state.yml"
    path.write_text(payload, encoding="utf-8")
    with pytest.raises(StrategicStateError, match="non-empty mapping"):
        load_strategic_state(path)


def test_empty_mapping_does_not_read_as_empty_state(tmp_path):
    """The core reason this reader exists: {} must not become a silent no-objectives state."""
    path = _write(tmp_path, {})
    with pytest.raises(StrategicStateError):
        load_strategic_state(path)


@pytest.mark.parametrize("key", ["company_phase", "p0", "resource_policy", "constraints"])
def test_missing_required_key_raises(tmp_path, key):
    path = _mutated(tmp_path, lambda d: d.pop(key))
    with pytest.raises(StrategicStateError, match="missing required key"):
        load_strategic_state(path)


def test_unsupported_schema_raises(tmp_path):
    path = _mutated(tmp_path, lambda d: d.update(schema="mastermind.strategic_state.v99"))
    with pytest.raises(StrategicStateError, match="unsupported schema"):
        load_strategic_state(path)


def test_duplicate_p0_id_raises(tmp_path):
    path = _mutated(tmp_path, lambda d: d["p0"].append(copy.deepcopy(d["p0"][0])))
    with pytest.raises(StrategicStateError, match="duplicate p0 objective id"):
        load_strategic_state(path)


def test_undeclared_department_raises(tmp_path):
    path = _mutated(tmp_path, lambda d: d["p0"][0].update(department="skunkworks"))
    with pytest.raises(StrategicStateError, match="not in the declared 'departments'"):
        load_strategic_state(path)


def test_undeclared_status_raises(tmp_path):
    path = _mutated(tmp_path, lambda d: d["p0"][0].update(status="kinda-doing-it"))
    with pytest.raises(StrategicStateError, match="not in the declared 'statuses'"):
        load_strategic_state(path)


def test_lowercase_p0_id_raises(tmp_path):
    path = _mutated(tmp_path, lambda d: d["p0"][0].update(id="quietly_renamed"))
    with pytest.raises(StrategicStateError, match="UPPER_SNAKE_CASE"):
        load_strategic_state(path)


def test_blank_p0_field_raises(tmp_path):
    path = _mutated(tmp_path, lambda d: d["p0"][0].update(objective="   "))
    with pytest.raises(StrategicStateError, match="must be a non-empty string"):
        load_strategic_state(path)


def test_resource_weights_not_summing_to_one_raises(tmp_path):
    path = _mutated(tmp_path, lambda d: d["resource_policy"].update(prophet_quality=0.9))
    with pytest.raises(StrategicStateError, match="must sum to ~1.0"):
        load_strategic_state(path)


def test_non_numeric_resource_weight_raises(tmp_path):
    path = _mutated(tmp_path, lambda d: d["resource_policy"].update(prophet_quality="lots"))
    with pytest.raises(StrategicStateError, match="must be a number"):
        load_strategic_state(path)


def test_boolean_resource_weight_raises(tmp_path):
    """bool is an int subclass — True must not silently score as a weight of 1.0."""
    path = _mutated(tmp_path, lambda d: d["resource_policy"].update(prophet_quality=True))
    with pytest.raises(StrategicStateError, match="must be a number"):
        load_strategic_state(path)


def test_negative_resource_weight_raises(tmp_path):
    def mutate(doc):
        doc["resource_policy"].update(prophet_quality=-0.3, exploratory_rd=0.65)
    path = _mutated(tmp_path, mutate)
    with pytest.raises(StrategicStateError, match="must not be negative"):
        load_strategic_state(path)


@pytest.mark.parametrize("constraint_name", REQUIRED_CONSTRAINTS)
def test_dropping_a_required_constraint_raises(tmp_path, constraint_name):
    path = _mutated(tmp_path, lambda d: d["constraints"].pop(constraint_name))
    with pytest.raises(StrategicStateError, match="missing required constraint"):
        load_strategic_state(path)


def test_undeclared_constraint_level_raises(tmp_path):
    path = _mutated(
        tmp_path, lambda d: d["constraints"].update(duplicate_control_planes="fine_actually")
    )
    with pytest.raises(StrategicStateError, match="not in the declared 'constraint_levels'"):
        load_strategic_state(path)


def test_reset_clears_the_cache(state):
    assert load_strategic_state() is state          # cached
    ss._reset()
    assert load_strategic_state() is not state      # re-read


# ---------------------------------------------------------------------------
# 7. no coupling to the Phase 1B worker runtime
# ---------------------------------------------------------------------------

def test_reader_does_not_import_the_worker_runtime():
    """Strategic state is orientation, not a control plane.

    Checked over the AST rather than the raw text, so the module docstring may
    keep *naming* worker_runtime while a real import fails the test.
    """
    tree = ast.parse(Path(ss.__file__).read_text(encoding="utf-8"))
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            imported.append(module)
            imported += [f"{module}.{a.name}" for a in node.names]

    offenders = [m for m in imported if "worker_runtime" in m or "sqlite" in m.lower()]
    assert not offenders, (
        f"control_plane.strategic_state must stay decoupled from the Phase 1B "
        f"runtime, but imports: {offenders}"
    )


# ---------------------------------------------------------------------------
# 8. the worker-facing executive contract exists and points at the state
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("doc_path", [_AGENTS_MD, _CLAUDE_MD])
def test_executive_contract_section_exists(doc_path):
    assert doc_path.is_file(), f"{doc_path.name} is missing"
    text = doc_path.read_text(encoding="utf-8")
    assert _CONTRACT_HEADING in text, (
        f"{doc_path.name} must carry a '{_CONTRACT_HEADING}' section so a worker "
        f"session that reads only this file still learns the hierarchy"
    )
    assert "config/strategic_state.yml" in text, (
        f"{doc_path.name} must point workers at the strategic state"
    )


def test_executive_contract_declares_the_source_of_truth_order():
    text = _AGENTS_MD.read_text(encoding="utf-8")
    for layer in (
        "research/MASTERMIND_CHARTER_V2.md",
        "config/strategic_state.yml",
        "config/authority_map.yml",
    ):
        assert layer in text, f"AGENTS.md source-of-truth order must cite {layer}"

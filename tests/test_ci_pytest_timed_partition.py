"""Measured-duration six-job placement: exact cover, determinism, fail-closed fallback."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import ci_pytest as cip

ROOT = Path(__file__).resolve().parents[1]
TABLE = ROOT / cip.TIMINGS_RELATIVE


def table() -> dict:
    return json.loads(TABLE.read_text(encoding="utf-8"))


def included() -> tuple[str, ...]:
    return cip.resolve_gate(ROOT)["included"]


def positions(shards):
    return {path: index for index, shard in enumerate(shards) for path in shard}


def projected(shards, timings) -> list[float]:
    weights, default = timings["modules"], timings["default_module_seconds"]
    overhead = timings["module_overhead_seconds"]
    return [
        timings["shard_base_seconds"][index]
        + sum(weights.get(path, default) + overhead for path in shard)
        for index, shard in enumerate(shards)
    ]


def frozen_partition(monkeypatch, modules):
    monkeypatch.setattr(cip, "load_module_timings", lambda path=None: None)
    return cip.partition_modules(modules, jobs=6)


def test_checked_in_table_is_valid_and_has_provenance():
    payload = cip.load_module_timings()
    assert payload is not None, "ci/pytest_timings.json must validate"
    provenance = payload["provenance"]
    assert provenance["event"] == "merge_group"
    assert len(provenance["source_runs"]) >= 5
    assert all(len(row["head"]) == 40 and isinstance(row["run"], int) for row in provenance["source_runs"])
    # Every measured module is a real repository test path (stale rows are
    # inert, but the table should be refreshed rather than accumulate them).
    current = set(included())
    stale = set(payload["modules"]) - current
    assert len(stale) <= len(payload["modules"]) // 20


def test_canonical_six_job_plan_is_exact_disjoint_cover_and_nonempty():
    modules = included()
    shards = cip.partition_modules(modules, jobs=6)
    cip.verify_partition(modules, shards)
    assert len(shards) == 6 and all(shards)
    placed = positions(shards)
    assert sorted(placed) == sorted(modules)
    flat = [path for shard in shards for path in shard]
    assert len(flat) == len(set(flat))


def test_placement_is_deterministic_and_order_independent():
    modules = included()
    first = cip.partition_modules(modules, jobs=6)
    assert first == cip.partition_modules(modules, jobs=6)
    reordered = cip.partition_modules(tuple(reversed(modules)), jobs=6)
    assert positions(first) == positions(reordered)


def test_new_unmeasured_module_never_moves_a_measured_module():
    modules = included()
    measured = set(table()["modules"])
    before = positions(cip.partition_modules(modules, jobs=6))
    extended = tuple(sorted((*modules, "tests/test_future_timed_fixture.py")))
    after = positions(cip.partition_modules(extended, jobs=6))
    assert "tests/test_future_timed_fixture.py" in after
    assert all(after[path] == before[path] for path in modules if path in measured)


def test_removed_module_never_moves_another_measured_module():
    modules = included()
    measured = set(table()["modules"])
    gone = max(measured & set(modules), key=lambda path: table()["modules"][path])
    before = positions(cip.partition_modules(modules, jobs=6))
    after = positions(cip.partition_modules(tuple(p for p in modules if p != gone), jobs=6))
    assert gone not in after
    assert all(after[path] == before[path] for path in after if path in measured)


@pytest.mark.parametrize(
    "content",
    [
        None,  # missing file
        "not json",
        json.dumps([]),
        json.dumps({"schema": "other"}),
    ],
)
def test_missing_or_unparseable_table_is_rejected(tmp_path, content):
    path = tmp_path / "pytest_timings.json"
    if content is not None:
        path.write_text(content, encoding="utf-8")
    assert cip.load_module_timings(path) is None


@pytest.mark.parametrize(
    "mutate",
    [
        lambda t: t.update(jobs=4),
        lambda t: t.update(default_module_seconds=-1),
        lambda t: t.update(default_module_seconds=True),
        lambda t: t.update(default_module_seconds=float("nan")),
        lambda t: t.pop("module_overhead_seconds"),
        lambda t: t.update(shard_base_seconds=t["shard_base_seconds"][:5]),
        lambda t: t["shard_base_seconds"].__setitem__(0, "1"),
        lambda t: t.update(modules={}),
        lambda t: t["modules"].update({"tests/test_x.py": -0.5}),
        lambda t: t["modules"].update({"scripts/not_a_test.py": 1.0}),
        lambda t: t["modules"].update({"tests/test_inf.py": float("inf")}),
    ],
)
def test_invalid_table_values_are_rejected(tmp_path, mutate):
    payload = table()
    mutate(payload)
    path = tmp_path / "pytest_timings.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert cip.load_module_timings(path) is None


def test_invalid_table_falls_back_to_frozen_placement_without_dropping_tests(monkeypatch):
    modules = included()
    with monkeypatch.context() as patch:
        expected = frozen_partition(patch, modules)
    # Exercise the real loader against a missing table path.
    original = cip.load_module_timings
    monkeypatch.setattr(cip, "load_module_timings",
                        lambda path=None: original(ROOT / "ci" / "does_not_exist.json"))
    shards = cip.partition_modules(modules, jobs=6)
    assert shards == expected
    cip.verify_partition(modules, shards)


def test_timed_placement_that_would_empty_a_shard_falls_back(monkeypatch):
    # Synthetic unmeasured modules all land on the lightest-base shards, which
    # would leave the heavy-base shards empty; the frozen hash placement wins.
    modules = tuple(f"tests/test_synthetic_{index}.py" for index in range(12))
    shards = cip.partition_modules(modules, jobs=6)
    assert shards == frozen_partition(monkeypatch, modules)
    cip.verify_partition(modules, shards)


def test_other_job_counts_ignore_the_timing_table(monkeypatch):
    modules = included()
    for jobs in (1, 2, 3, 4, 5, 8):
        live = cip.partition_modules(modules, jobs=jobs)
        with monkeypatch.context() as patch:
            patch.setattr(cip, "load_module_timings", lambda path=None: None)
            assert live == cip.partition_modules(modules, jobs=jobs)


def test_projected_slowest_shard_improves_on_frozen_placement(monkeypatch):
    modules = included()
    timings = table()
    timed = projected(cip.partition_modules(modules, jobs=6), timings)
    frozen = projected(frozen_partition(monkeypatch, modules), timings)
    mean = sum(timed) / len(timed)
    # Measured on the checked-in table: frozen max ~39.2 min vs timed ~36.1.
    assert max(timed) < max(frozen) - 120
    # LPT bound: the slowest shard sits within one large module of the mean.
    assert max(timed) - mean <= 60

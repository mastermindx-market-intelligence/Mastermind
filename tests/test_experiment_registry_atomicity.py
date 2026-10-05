from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date
import os
from pathlib import Path
import time

import pytest

from brain import experiment_registry as registry


def record(eid: str, *, note: str = "") -> dict:
    return {
        "id": eid,
        "what": f"experiment {eid}",
        "gate": "TEST_ONLY gate",
        "comeback_date": None,
        "maturity_condition": "TEST_ONLY condition",
        "status": "open",
        "owner": "opus-session",
        "artifact_paths": [f"research/{eid}.json"],
        "notes": note,
    }


@pytest.fixture
def isolated_registry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "registry.json"
    monkeypatch.setattr(registry, "_REGISTRY_PATH", path)
    if hasattr(registry, "_REGISTRY_LOCK_PATH"):
        monkeypatch.setattr(registry, "_REGISTRY_LOCK_PATH", path.with_name(path.name + ".lock"))
    return path


def slow_save(monkeypatch: pytest.MonkeyPatch) -> None:
    original = registry._save

    def delayed(experiments):
        time.sleep(0.05)
        return original(experiments)

    monkeypatch.setattr(registry, "_save", delayed)


def test_concurrent_distinct_adds_both_survive(isolated_registry: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    slow_save(monkeypatch)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(registry.add, [record("alpha"), record("beta")]))
    assert results == [True, True]
    assert {item["id"] for item in registry.load()} == {"alpha", "beta"}


def test_concurrent_same_id_has_one_winner(isolated_registry: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    slow_save(monkeypatch)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(registry.add, [record("same"), record("same")]))
    assert sorted(results) == [False, True]
    assert [item["id"] for item in registry.load()] == ["same"]


def test_concurrent_update_and_add_preserve_both_effects(isolated_registry: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert registry.add(record("existing")) is True
    slow_save(monkeypatch)

    def do_update() -> bool:
        return registry.update("existing", notes="updated")

    with ThreadPoolExecutor(max_workers=2) as pool:
        a = pool.submit(do_update)
        b = pool.submit(registry.add, record("new"))
        assert a.result() is True
        assert b.result() is True

    got = {item["id"]: item for item in registry.load()}
    assert set(got) == {"existing", "new"}
    assert got["existing"]["notes"] == "updated"


def test_corrupt_preimage_refuses_mutation_and_preserves_bytes(isolated_registry: Path) -> None:
    original = b'{"experiments": [BROKEN'
    isolated_registry.write_bytes(original)
    assert registry.load() == []  # tolerant display/read path remains fail-soft
    assert registry.add(record("new")) is False
    assert isolated_registry.read_bytes() == original


def test_duplicate_id_preimage_refuses_mutation(isolated_registry: Path) -> None:
    isolated_registry.write_text('[{"id":"dup"},{"id":"dup"}]')
    before = isolated_registry.read_bytes()
    assert registry.add(record("new")) is False
    assert isolated_registry.read_bytes() == before


def test_replace_failure_never_leaves_partial_registry(
    isolated_registry: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert registry.add(record("existing")) is True
    before = isolated_registry.read_bytes()

    def fail_replace(src, dst):
        raise OSError("TEST_ONLY replace failure")

    monkeypatch.setattr(os, "replace", fail_replace)
    assert registry.add(record("new")) is False
    assert isolated_registry.read_bytes() == before
    assert {item["id"] for item in registry.load()} == {"existing"}




def test_concurrent_maturity_and_add_preserve_both_effects(
    isolated_registry: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    due = record("due")
    due["comeback_date"] = "2000-01-01"
    assert registry.add(due) is True
    slow_save(monkeypatch)

    with ThreadPoolExecutor(max_workers=2) as pool:
        maturity = pool.submit(registry.matured, date(2026, 1, 1))
        addition = pool.submit(registry.add, record("new"))
        assert any(item["id"] == "due" for item in maturity.result())
        assert addition.result() is True

    got = {item["id"]: item for item in registry.load()}
    assert set(got) == {"due", "new"}
    assert got["due"]["status"] == "matured"


def test_out_of_band_preimage_change_refuses_overwrite(
    isolated_registry: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert registry.add(record("existing")) is True
    original_serializer = registry._serialize_registry

    def race(experiments):
        payload = original_serializer(experiments)
        isolated_registry.write_text(
            '[{"id":"external","what":"external writer","status":"open"}]'
        )
        return payload

    monkeypatch.setattr(registry, "_serialize_registry", race)
    assert registry.add(record("new")) is False
    loaded = registry.load()
    assert [item["id"] for item in loaded] == ["external"]

def test_normal_add_readback_preserves_immutable_artifact_refs(isolated_registry: Path) -> None:
    item = record("i3-prereg")
    item["artifact_paths"] = [
        "research/issuer_inflection/2026-10-03/w0/PREREGISTRATION_CANDIDATE.md"
    ]
    item["notes"] = "method_sha256=abc123 cohort_sha256=def456"
    assert registry.add(item) is True
    got = registry.get("i3-prereg")
    assert got is not None
    assert got["artifact_paths"] == item["artifact_paths"]
    assert got["notes"] == item["notes"]

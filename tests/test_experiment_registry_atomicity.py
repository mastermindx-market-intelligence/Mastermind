from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date
import errno
import json
import multiprocessing
import os
from pathlib import Path
import stat
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


def test_malformed_object_envelope_refuses_mutation(isolated_registry: Path) -> None:
    for raw in (
        b'{"not_experiments":[]}',
        b'{"experiments":{}}',
        b'42',
    ):
        isolated_registry.write_bytes(raw)
        assert registry.load() == []
        assert registry.add(record("new")) is False
        assert isolated_registry.read_bytes() == raw


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


@pytest.mark.parametrize("existing", [False, True])
def test_post_replace_external_publication_is_preserved(
    isolated_registry: Path, monkeypatch: pytest.MonkeyPatch, existing: bool
) -> None:
    if existing:
        assert registry.add(record("existing")) is True
    external = b'[ {"id": "external", "status": "open", "notes": "new writer"} ]\n'
    replace = os.replace
    replacements = []

    def publish_external_after_replace(src, dst):
        replace(src, dst)
        replacements.append((src, dst))
        if len(replacements) == 1:
            isolated_registry.write_bytes(external)

    monkeypatch.setattr(os, "replace", publish_external_after_replace)
    assert registry.add(record("new")) is False
    assert isolated_registry.read_bytes() == external
    assert len(replacements) == 1
    assert not list(isolated_registry.parent.glob(".registry.json.*.tmp"))


@pytest.mark.parametrize("existing", [False, True])
def test_post_replace_readback_error_preserves_the_published_payload(
    isolated_registry: Path, monkeypatch: pytest.MonkeyPatch, existing: bool
) -> None:
    if existing:
        assert registry.add(record("existing")) is True
    replace, read_bytes = os.replace, Path.read_bytes
    published = []

    def observe_replace(src, dst):
        replace(src, dst)
        published.append(read_bytes(isolated_registry))

    def fail_readback(path):
        if path == isolated_registry and published:
            raise OSError(errno.EIO, "TEST_ONLY readback failure")
        return read_bytes(path)

    monkeypatch.setattr(os, "replace", observe_replace)
    monkeypatch.setattr(Path, "read_bytes", fail_readback)
    assert registry.add(record("new")) is False
    assert len(published) == 1
    assert read_bytes(isolated_registry) == published[0]
    expected = {"existing", "new"} if existing else {"new"}
    assert {item["id"] for item in json.loads(published[0])} == expected


@pytest.mark.parametrize("phase, error", [
    ("open", errno.EACCES), ("open", errno.EIO),
    ("fsync", errno.EIO), ("fsync", errno.EINVAL),
])
def test_directory_durability_failure_never_reports_success_or_rolls_back(
    isolated_registry: Path, monkeypatch: pytest.MonkeyPatch, phase: str, error: int
) -> None:
    assert registry.add(record("existing")) is True
    real_open, real_fsync, real_replace = os.open, os.fsync, os.replace
    replacements = []

    def open_directory(path, flags, *args, **kwargs):
        if phase == "open" and Path(path) == isolated_registry.parent:
            raise OSError(error, "TEST_ONLY directory open failure")
        return real_open(path, flags, *args, **kwargs)

    def sync_directory(fd):
        if phase == "fsync" and stat.S_ISDIR(os.fstat(fd).st_mode):
            raise OSError(error, "TEST_ONLY directory sync failure")
        return real_fsync(fd)

    def observe_replace(src, dst):
        real_replace(src, dst)
        replacements.append((src, dst))

    monkeypatch.setattr(os, "open", open_directory)
    monkeypatch.setattr(os, "fsync", sync_directory)
    monkeypatch.setattr(os, "replace", observe_replace)
    assert registry.add(record("new")) is False
    assert {item["id"] for item in registry.load()} == {"existing", "new"}
    assert len(replacements) == 1
    assert not list(isolated_registry.parent.glob(".registry.json.*.tmp"))


def test_unconfirmed_maturity_save_returns_no_promoted_results(
    isolated_registry: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    due = record("due")
    due["comeback_date"] = "2000-01-01"
    assert registry.add(due) is True
    before = isolated_registry.read_bytes()
    monkeypatch.setattr(registry, "_save", lambda items: False)
    assert registry.matured(date(2026, 1, 1)) == []
    assert isolated_registry.read_bytes() == before
    assert registry.get("due")["status"] == "open"


def test_already_matured_records_need_no_new_save(
    isolated_registry: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    item = record("already-matured")
    item["status"] = "matured"
    assert registry.add(item) is True
    before = isolated_registry.read_bytes()

    def unexpected_save(items):
        raise AssertionError("no promotion needs saving")

    monkeypatch.setattr(registry, "_save", unexpected_save)
    assert [row["id"] for row in registry.matured(date(2026, 1, 1))] == ["already-matured"]
    assert isolated_registry.read_bytes() == before


def test_existing_json_serialization_contract_is_preserved(isolated_registry: Path) -> None:
    item = record("serialized")
    item["comeback_date"] = date(2026, 1, 1)
    item["artifact_paths"] = (Path("research/serialized.json"),)
    assert registry.add(item) is True
    stored = registry.get("serialized")
    assert stored["comeback_date"] == "2026-01-01"
    assert stored["artifact_paths"] == ["research/serialized.json"]


def _process_add(path, eid, start, result):
    registry._REGISTRY_PATH = Path(path)
    save = registry._save

    def delayed_save(items):
        time.sleep(0.05)
        return save(items)

    registry._save = delayed_save
    try:
        if not start.wait(10):
            raise AssertionError("fixture start was not signaled")
        result.send(registry.add(record(eid)))
    finally:
        result.close()


@pytest.mark.parametrize("same_id", [False, True])
def test_separate_processes_share_the_original_file_lock(
    isolated_registry: Path, same_id: bool
) -> None:
    context = multiprocessing.get_context("fork")
    start = context.Event()
    identifiers = ("first", "first" if same_id else "second")
    pipes = [context.Pipe(duplex=False) for _ in identifiers]
    children = [context.Process(target=_process_add,
        args=(str(isolated_registry), eid, start, pipe[1]))
        for eid, pipe in zip(identifiers, pipes)]
    try:
        for child in children:
            child.start()
        for receiver, sender in pipes:
            sender.close()
        start.set()
        results = []
        for receiver, _ in pipes:
            assert receiver.poll(10), "fixture child did not return"
            results.append(receiver.recv())
        for child in children:
            child.join(10)
            assert child.exitcode == 0
        assert sorted(results) == ([False, True] if same_id else [True, True])
        assert {item["id"] for item in registry.load()} == set(identifiers)
    finally:
        for child in children:
            if child.pid is not None and child.is_alive():
                child.terminate()
                child.join(5)
                if child.is_alive():
                    child.kill()
                    child.join(5)
        for receiver, sender in pipes:
            receiver.close()
            sender.close()

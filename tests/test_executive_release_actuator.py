from __future__ import annotations

import concurrent.futures
import errno
import hashlib
import json
import multiprocessing
import os
from pathlib import Path
import re

import pytest

from control_plane import executive_release_actuator as actuator
from control_plane import executive_release_contract as contract


BOOT_ID = "12345678-1234-4123-8123-123456789abc"
OPERATION_KEY = "test-operation"
POSTCONDITION = "f" * 64


def _hex64(value: int) -> str:
    return format(value, "064x")


def _canonical_hash(value) -> str:
    return hashlib.sha256(contract.canonical_release_bytes(value)).hexdigest()


def _inputs(operation_key: str = OPERATION_KEY):
    target_ref = _hex64(14)
    preconditions = {
        "schema": "mastermind.executive_release_preconditions/v1",
        "owner_installation_id": BOOT_ID,
        "target_ref": target_ref,
        "boot_id": BOOT_ID,
        "from_installed_manifest_digest": _hex64(6),
        "installed_configuration_digest": _hex64(16),
        "python_runtime_provenance_digest": _hex64(1),
        "provider_binary_attestation_digest": _hex64(2),
        "authority_policy_hash": _hex64(3),
        "grant_digest": _hex64(4),
        "approval_evidence_digest": _hex64(15),
        "staged_artifact_digest": _hex64(7),
        "staged_content_metadata_digest": _hex64(8),
        "compatibility_proof_digest": _hex64(9),
        "preservation_plan_digest": _hex64(10),
        "issuer_binding_digest": _hex64(11),
        "admission_contract_digest": _hex64(12),
        "production_arming_digest": _hex64(13),
    }
    admission = {
        "schema": "mastermind.executive_release_admission/v1",
        "operation_key": operation_key,
        "approved_transition_ref": contract.approval_ref_for(operation_key),
        "target_ref": target_ref,
        "owner_installation_id": BOOT_ID,
        "boot_id": BOOT_ID,
        "request_fingerprint": _hex64(17),
        "effective_grant_digest": preconditions["grant_digest"],
        "maintenance_sequence": 1,
        "admission_event_command_id": (
            "p4-admit:" + contract.approval_ref_for(operation_key).removeprefix("p4-approval:")
        ),
        "target_observation_digest": _hex64(18),
        "admission_contract_digest": preconditions["admission_contract_digest"],
    }
    identity = {
        "operation_key": operation_key,
        "request_fingerprint": admission["request_fingerprint"],
        "approval_evidence_digest": preconditions["approval_evidence_digest"],
        "normalized_requested_effect_digest": _hex64(19),
        "expected_source_and_precondition_digest": _canonical_hash(preconditions),
        "action_target_digest": _hex64(21),
        "owner_installation_id": BOOT_ID,
        "target_ref": target_ref,
        "before_release_commit": "1" * 40,
        "before_release_tree": "2" * 40,
        "before_installed_manifest_digest": preconditions[
            "from_installed_manifest_digest"
        ],
        "before_configuration_digest": preconditions[
            "installed_configuration_digest"
        ],
        "target_release_commit": "3" * 40,
        "target_release_tree": "4" * 40,
        "boot_id": BOOT_ID,
    }
    return identity, preconditions, admission


def _journal(root: Path, **kwargs):
    return actuator.ExecutiveReleaseActuatorJournal._for_tests(root, **kwargs)


def _start(journal, operation_key: str = OPERATION_KEY, **changes):
    identity, preconditions, admission = _inputs(operation_key)
    identity.update(changes.pop("identity", {}))
    preconditions.update(changes.pop("preconditions", {}))
    admission.update(changes.pop("admission", {}))
    return journal.create(
        actuator_generation=changes.pop("actuator_generation", 7),
        identity=identity,
        preconditions=preconditions,
        admission=admission,
        started_at_ms=changes.pop("started_at_ms", 1_000),
        **changes,
    )


def _before(record):
    return {
        "release_commit": record["before_release_commit"],
        "release_tree": record["before_release_tree"],
        "installed_manifest_digest": record["before_installed_manifest_digest"],
        "configuration_digest": record["before_configuration_digest"],
    }


def _target(record):
    return {
        "release_commit": record["target_release_commit"],
        "release_tree": record["target_release_tree"],
        "installed_manifest_digest": _hex64(30),
        "configuration_digest": _hex64(31),
    }


def _to_recovering(journal, record):
    for state in ("PUBLISHED", "BROKER_RESTART_PENDING", "RECOVERING"):
        record = journal.advance(
            record["operation_key"],
            expected_generation=record["journal_generation"],
            state=state,
        )
    return record


def _terminal(journal, record, state):
    if state == "SUCCEEDED":
        after = _target(record)
        rollback = {"attempted": False}
    elif state == "FAILED_NOT_APPLIED":
        after = _before(record)
        rollback = {"attempted": False}
    else:
        after = _before(record)
        rollback = {
            "attempted": True,
            "restored_preimage_digest": _canonical_hash(after),
        }
    return journal.advance(
        record["operation_key"],
        expected_generation=record["journal_generation"],
        state=state,
        completed_at_ms=2_000,
        postcondition_digest=POSTCONDITION,
        after=after,
        rollback=rollback,
    )


def _record_path(root: Path, operation_key: str = OPERATION_KEY) -> Path:
    return root / (hashlib.sha256(operation_key.encode("ascii")).hexdigest() + ".json")


def _process_start(root: str, queue) -> None:
    try:
        queue.put(("ok", _start(_journal(Path(root))).to_dict()))
    except actuator.ExecutiveReleaseActuatorJournalError as exc:
        queue.put(("error", exc.code))


def _process_advance(root: str, queue) -> None:
    try:
        value = _journal(Path(root)).advance(
            OPERATION_KEY, expected_generation=1, state="PUBLISHED"
        )
        queue.put(("ok", value.to_dict()))
    except actuator.ExecutiveReleaseActuatorJournalError as exc:
        queue.put(("error", exc.code))


def test_all_states_restart_and_embedded_records_are_exact(tmp_path):
    root = tmp_path / "journal"
    journal = _journal(root)
    record = _start(journal)
    observed = [record["state"]]
    _, preconditions, admission = _inputs()
    assert record["preconditions"] == contract.validate_precondition_manifest(preconditions)
    assert record["admission"] == contract.validate_admission(admission)
    for state in ("PUBLISHED", "BROKER_RESTART_PENDING", "RECOVERING"):
        record = journal.advance(
            OPERATION_KEY,
            expected_generation=record["journal_generation"],
            state=state,
        )
        observed.append(state)
        assert _journal(root).read(OPERATION_KEY) == record
        assert record["preconditions"] == contract.validate_precondition_manifest(
            preconditions
        )
        assert record["admission"] == contract.validate_admission(admission)
    record = _terminal(journal, record, "SUCCEEDED")
    observed.append(record["state"])
    assert observed == list(actuator._STATES[:5])
    assert _journal(root).read(OPERATION_KEY) == record


def test_exact_start_replay_preserves_bytes_and_generations(tmp_path):
    root = tmp_path / "journal"
    journal = _journal(root)
    first = _start(journal)
    path = _record_path(root)
    raw = path.read_bytes()
    metadata = path.stat().st_mtime_ns
    replay = _start(_journal(root))
    assert replay == first
    assert path.read_bytes() == raw
    assert path.stat().st_mtime_ns == metadata
    assert replay["journal_generation"] == 1


@pytest.mark.parametrize(
    ("category", "field", "replacement"),
    [
        ("identity", "request_fingerprint", _hex64(40)),
        ("identity", "approval_evidence_digest", _hex64(41)),
        ("identity", "normalized_requested_effect_digest", _hex64(42)),
        ("identity", "action_target_digest", _hex64(43)),
        ("identity", "before_release_commit", "5" * 40),
        ("identity", "target_release_tree", "6" * 40),
        ("preconditions", "production_arming_digest", _hex64(44)),
        ("admission", "maintenance_sequence", 2),
    ],
)
def test_same_operation_immutable_mismatch_is_conflict(
    tmp_path, category, field, replacement
):
    root = tmp_path / "journal"
    _start(_journal(root))
    changes = {category: {field: replacement}}
    if category == "preconditions":
        identity, preconditions, _ = _inputs()
        preconditions.update(changes[category])
        changes["identity"] = {
            "expected_source_and_precondition_digest": _canonical_hash(preconditions)
        }
    elif category == "identity" and field == "request_fingerprint":
        changes["admission"] = {"request_fingerprint": replacement}
    elif category == "identity" and field == "approval_evidence_digest":
        identity, preconditions, _ = _inputs()
        preconditions["approval_evidence_digest"] = replacement
        changes["preconditions"] = {
            "approval_evidence_digest": replacement,
        }
        changes["identity"] = {
            field: replacement,
            "expected_source_and_precondition_digest": _canonical_hash(preconditions),
        }
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError) as caught:
        _start(_journal(root), **changes)
    assert caught.value.code == "CONFLICT"


@pytest.mark.parametrize(
    "changes",
    [
        {"actuator_generation": 8},
        {"started_at_ms": 1_001},
    ],
)
def test_start_generation_and_time_are_immutable(tmp_path, changes):
    root = tmp_path / "journal"
    _start(_journal(root))
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError) as caught:
        _start(_journal(root), **changes)
    assert caught.value.code == "CONFLICT"


@pytest.mark.parametrize(
    "changes",
    [
        {"identity": {"expected_source_and_precondition_digest": _hex64(55)}},
        {"admission": {"effective_grant_digest": _hex64(56)}},
        {"admission": {"request_fingerprint": _hex64(57)}},
        {"preconditions": {"boot_id": "22345678-1234-4123-8123-123456789abc"}},
    ],
)
def test_start_refuses_broken_embedded_joins_before_filesystem_mutation(
    tmp_path, changes
):
    root = tmp_path / "journal"
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError):
        _start(_journal(root), **changes)
    assert not root.exists()


def test_state_and_generation_fencing(tmp_path):
    journal = _journal(tmp_path / "journal")
    record = _start(journal)
    for state in (
        "STARTED",
        "BROKER_RESTART_PENDING",
        "RECOVERING",
    ):
        with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError) as caught:
            journal.advance(
                OPERATION_KEY, expected_generation=1, state=state
            )
        assert caught.value.code == "INVALID_TRANSITION"
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError) as caught:
        journal.advance(OPERATION_KEY, expected_generation=2, state="PUBLISHED")
    assert caught.value.code == "GENERATION_MISMATCH"
    record = journal.advance(
        OPERATION_KEY, expected_generation=1, state="PUBLISHED"
    )
    assert record["journal_generation"] == 2
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError) as caught:
        journal.advance(OPERATION_KEY, expected_generation=2, state="PUBLISHED")
    assert caught.value.code == "INVALID_TRANSITION"
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError) as caught:
        journal.advance(
            OPERATION_KEY,
            expected_generation=2,
            state="BROKER_RESTART_PENDING",
            completed_at_ms=2_000,
        )
    assert caught.value.code == "TERMINAL_ARGUMENTS"


@pytest.mark.parametrize("state", ["SUCCEEDED", "ROLLED_BACK", "FAILED_NOT_APPLIED"])
def test_each_terminal_truth_and_terminal_immutability(tmp_path, state):
    journal = _journal(tmp_path / state)
    record = _to_recovering(journal, _start(journal))
    terminal = _terminal(journal, record, state)
    assert terminal["state"] == state
    assert terminal["journal_generation"] == 5
    assert _journal(tmp_path / state).read(OPERATION_KEY) == terminal
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError) as caught:
        journal.advance(
            OPERATION_KEY,
            expected_generation=5,
            state="SUCCEEDED",
            completed_at_ms=2_001,
            postcondition_digest=POSTCONDITION,
            after=_target(terminal),
            rollback={"attempted": False},
        )
    assert caught.value.code == "TERMINAL_IMMUTABLE"


@pytest.mark.parametrize(
    ("state", "after_kind", "rollback"),
    [
        ("SUCCEEDED", "before", {"attempted": False}),
        ("SUCCEEDED", "target", {"attempted": True, "restored_preimage_digest": "a" * 64}),
        ("FAILED_NOT_APPLIED", "target", {"attempted": False}),
        ("FAILED_NOT_APPLIED", "before", {"attempted": True, "restored_preimage_digest": "a" * 64}),
        ("ROLLED_BACK", "before", {"attempted": False}),
        ("ROLLED_BACK", "before", {"attempted": True, "restored_preimage_digest": "a" * 64}),
    ],
)
def test_terminal_truth_refusals(tmp_path, state, after_kind, rollback):
    journal = _journal(tmp_path / (state + after_kind + str(rollback["attempted"])))
    record = _to_recovering(journal, _start(journal))
    after = _before(record) if after_kind == "before" else _target(record)
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError) as caught:
        journal.advance(
            OPERATION_KEY,
            expected_generation=record["journal_generation"],
            state=state,
            completed_at_ms=2_000,
            postcondition_digest=POSTCONDITION,
            after=after,
            rollback=rollback,
        )
    assert caught.value.code == "INVALID_TERMINAL_TRUTH"


def test_terminal_time_and_closed_rollback_union(tmp_path):
    journal = _journal(tmp_path / "journal")
    record = _to_recovering(journal, _start(journal))
    for completed, rollback in (
        (999, {"attempted": False}),
        (2_000, {"attempted": False, "restored_preimage_digest": "a" * 64}),
        (2_000, {"attempted": True}),
        (2_000, {"attempted": 1}),
    ):
        with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError):
            journal.advance(
                OPERATION_KEY,
                expected_generation=record["journal_generation"],
                state="FAILED_NOT_APPLIED",
                completed_at_ms=completed,
                postcondition_digest=POSTCONDITION,
                after=_before(record),
                rollback=rollback,
            )


@pytest.mark.parametrize(
    "malformed",
    [
        b"{}",
        b'{"schema":"x","schema":"y"}',
        b'{"value":null}',
        b'{"value":' + b"[" * 10 + b"0" + b"]" * 10 + b"}",
        b"x" * (16 * 1024 + 1),
    ],
)
def test_malformed_duplicate_null_depth_and_oversize_storage_fail_closed(
    tmp_path, malformed
):
    root = tmp_path / "journal"
    _start(_journal(root))
    _record_path(root).write_bytes(malformed)
    os.chmod(_record_path(root), 0o600)
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError) as caught:
        _journal(root).read(OPERATION_KEY)
    assert caught.value.code in {"RECORD_BYTES", "RECORD_SIZE"}


def test_noncanonical_bytes_fail_closed(tmp_path):
    root = tmp_path / "journal"
    record = _start(_journal(root))
    noncanonical = json.dumps(record.to_dict(), sort_keys=True, indent=2).encode("ascii")
    _record_path(root).write_bytes(noncanonical)
    os.chmod(_record_path(root), 0o600)
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError) as caught:
        _journal(root).read(OPERATION_KEY)
    assert caught.value.code == "RECORD_BYTES"


def test_record_symlink_hardlink_and_mode_refuse(tmp_path):
    root = tmp_path / "journal"
    _start(_journal(root))
    path = _record_path(root)
    raw = path.read_bytes()
    path.unlink()
    path.symlink_to("/etc/passwd")
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError):
        _journal(root).read(OPERATION_KEY)
    path.unlink()
    path.write_bytes(raw)
    os.chmod(path, 0o644)
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError) as caught:
        _journal(root).read(OPERATION_KEY)
    assert caught.value.code == "RECORD_METADATA"
    os.chmod(path, 0o600)
    alias = root / "alias"
    os.link(path, alias)
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError) as caught:
        _journal(root).read(OPERATION_KEY)
    assert caught.value.code == "RECORD_METADATA"


def test_root_symlink_mode_owner_and_acl_refuse(tmp_path, monkeypatch):
    root = tmp_path / "journal"
    _start(_journal(root))
    os.chmod(root, 0o755)
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError) as caught:
        _journal(root).read(OPERATION_KEY)
    assert caught.value.code == "ROOT_METADATA"


def test_root_path_replacement_during_read_refuses(tmp_path, monkeypatch):
    root = tmp_path / "journal"
    journal = _journal(root)
    _start(journal)
    original_read = journal._read_file
    moved = tmp_path / "moved-journal"

    def replace_after_read(*args, **kwargs):
        result = original_read(*args, **kwargs)
        root.rename(moved)
        root.mkdir(mode=0o700)
        return result

    monkeypatch.setattr(journal, "_read_file", replace_after_read)
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError) as caught:
        journal.read(OPERATION_KEY)
    assert caught.value.code == "ROOT_REPLACED"
    os.chmod(root, 0o700)
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError) as caught:
        _journal(root, expected_uid=os.geteuid() + 1).read(OPERATION_KEY)
    assert caught.value.code == "ROOT_METADATA"
    monkeypatch.setattr(actuator, "has_macos_acl", lambda *args, **kwargs: True)
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError) as caught:
        _journal(root).read(OPERATION_KEY)
    assert caught.value.code == "ROOT_METADATA"


def test_atomic_replace_failure_preserves_prior_record_and_cleans_temp(
    tmp_path, monkeypatch
):
    root = tmp_path / "journal"
    journal = _journal(root)
    original = _start(journal)

    def refuse_replace(*args, **kwargs):
        raise OSError(errno.EIO, "refused")

    monkeypatch.setattr(actuator.os, "replace", refuse_replace)
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError) as caught:
        journal.advance(OPERATION_KEY, expected_generation=1, state="PUBLISHED")
    assert caught.value.code == "RECORD_REPLACE"
    assert journal.read(OPERATION_KEY) == original
    assert not list(root.glob("*.tmp"))


def test_stale_temporary_file_refuses_without_changing_record(tmp_path):
    root = tmp_path / "journal"
    journal = _journal(root)
    original = _start(journal)
    temporary = root / (_record_path(root).stem + ".tmp")
    temporary.write_bytes(b"stale")
    os.chmod(temporary, 0o600)
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError) as caught:
        journal.advance(OPERATION_KEY, expected_generation=1, state="PUBLISHED")
    assert caught.value.code == "RECORD_EXISTS"
    assert journal.read(OPERATION_KEY) == original


def test_thread_concurrency_serializes_start_and_generation_cas(tmp_path):
    root = tmp_path / "journal"
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        starts = list(pool.map(lambda _: _start(_journal(root)), range(16)))
    assert all(value == starts[0] for value in starts)

    def advance(_):
        try:
            return _journal(root).advance(
                OPERATION_KEY, expected_generation=1, state="PUBLISHED"
            )
        except actuator.ExecutiveReleaseActuatorJournalError as exc:
            return exc.code

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(advance, range(16)))
    accepted = [value for value in results if isinstance(value, contract.ReleaseRecord)]
    refused = [value for value in results if isinstance(value, str)]
    assert len(accepted) == 1
    assert refused == ["GENERATION_MISMATCH"] * 15


@pytest.mark.skipif(not hasattr(os, "fork"), reason="requires process flock semantics")
def test_process_concurrency_serializes_start_and_generation_cas(tmp_path):
    root = tmp_path / "journal"
    context = multiprocessing.get_context("fork")
    queue = context.Queue()
    starters = [context.Process(target=_process_start, args=(str(root), queue)) for _ in range(6)]
    for process in starters:
        process.start()
    for process in starters:
        process.join(10)
        assert process.exitcode == 0
    start_results = [queue.get(timeout=2) for _ in starters]
    assert all(kind == "ok" for kind, _ in start_results)
    assert all(value == start_results[0][1] for _, value in start_results)

    workers = [context.Process(target=_process_advance, args=(str(root), queue)) for _ in range(6)]
    for process in workers:
        process.start()
    for process in workers:
        process.join(10)
        assert process.exitcode == 0
    results = [queue.get(timeout=2) for _ in workers]
    assert [kind for kind, _ in results].count("ok") == 1
    assert [value for kind, value in results if kind == "error"] == [
        "GENERATION_MISMATCH"
    ] * 5


def test_multiple_operation_families_share_one_root(tmp_path):
    root = tmp_path / "journal"
    first = _start(_journal(root), "first-operation")
    second = _start(_journal(root), "second-operation")
    assert _journal(root).read("first-operation") == first
    assert _journal(root).read("second-operation") == second
    assert len(list(root.glob("*.json"))) == 2
    assert len(list(root.glob("*.lock"))) == 2


def test_missing_root_or_record_is_not_found_without_replay(tmp_path):
    root = tmp_path / "journal"
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError) as caught:
        _journal(root).read(OPERATION_KEY)
    assert caught.value.code == "NOT_FOUND"
    assert not root.exists()
    _start(_journal(root), "another-operation")
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError) as caught:
        _journal(root).read(OPERATION_KEY)
    assert caught.value.code == "NOT_FOUND"


def test_fixed_production_root_bounded_public_surface_and_no_effect_imports():
    source = Path(actuator.__file__).read_text()
    production = actuator.ExecutiveReleaseActuatorJournal()
    assert production._root == Path(
        "/var/db/mastermind-executive/release-actuator/journal"
    )
    assert production._expected_uid == 0
    assert production._lock_timeout == 5.0
    assert [
        name
        for name in dir(actuator.ExecutiveReleaseActuatorJournal)
        if not name.startswith("_")
    ] == ["advance", "create", "read"]
    assert set(actuator.__all__) == {
        "ExecutiveReleaseActuatorJournal",
        "ExecutiveReleaseActuatorJournalError",
        "JOURNAL_PRODUCTION_ROOT",
    }
    for forbidden in (
        "subprocess",
        "socket",
        "requests",
        "urllib",
        "os.system",
        "popen",
        "getenv",
        "/var/lib",
        "sys.modules",
        "types.moduletype",
        "os.umask",
    ):
        assert forbidden not in source.lower()
    assert re.search(r"fcntl\.flock\(.+LOCK_NB", source)
    assert "os.unlink(lock_name" not in source

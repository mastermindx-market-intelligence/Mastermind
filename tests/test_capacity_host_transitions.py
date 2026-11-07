"""Capacity host transitions cases; shared helpers retain their original owner."""
from __future__ import annotations

from tests.test_capacity_host_artifacts import (
    Path,
    _assert_only_kernel_atime_may_advance,
    _repair_arguments,
    _repair_host_fixture,
    _scoped_content_observation,
    _scoped_metadata_observation,
    _scoped_tree_snapshot,
    _verify_arguments,
    artifacts,
    hashlib,
    os,
    pytest,
)


def test_source_repair_transition_table_is_exhaustive_and_terminal_states_are_distinct() -> None:
    table = artifacts.SOURCE_REPAIR_TRANSITIONS
    for mode in artifacts.SourceRepairMode:
        assert {
            phase
            for table_mode, phase, _failure_layout in table
            if table_mode is mode
        } == set(artifacts.SourceRepairPhase)
    assert {transition.action for transition in table.values()} == set(
        artifacts.SourceRepairAction
    )
    assert all(
        isinstance(transition.permitted_next_states, frozenset)
        for transition in table.values()
    )
    for mode in artifacts.SourceRepairMode:
        for phase in (
            artifacts.SourceRepairPhase.ROLLBACK_STARTED,
            artifacts.SourceRepairPhase.ROLLBACK_GENERATION_RESTORED,
            artifacts.SourceRepairPhase.ROLLED_BACK,
        ):
            for layout in (
                artifacts.SourceRepairFailureLayout.EMPTY,
                artifacts.SourceRepairFailureLayout.INSTALLED_SOURCE,
                artifacts.SourceRepairFailureLayout.STAGED_SOURCE,
            ):
                assert (mode, phase, layout) in table
    assert table[
        (
            artifacts.SourceRepairMode.REPAIR,
            artifacts.SourceRepairPhase.ROLLED_BACK,
            artifacts.SourceRepairFailureLayout.INSTALLED_SOURCE,
        )
    ].action is artifacts.SourceRepairAction.REFUSE_ROLLED_BACK
    assert table[
        (
            artifacts.SourceRepairMode.VERIFY_ONLY,
            artifacts.SourceRepairPhase.COMMITTED,
            artifacts.SourceRepairFailureLayout.NONE,
        )
    ].action is artifacts.SourceRepairAction.VERIFY_COMMITTED


@pytest.mark.parametrize("authority_change", ("removed", "refused"))
def test_repair_transition_table_is_the_executable_authority_before_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    authority_change: str,
) -> None:
    system_root, transport, commit, _manifest = _repair_host_fixture(
        tmp_path, monkeypatch
    )
    arguments = _repair_arguments(system_root, transport, commit)
    with pytest.raises(artifacts.SourceRepairIncomplete):
        artifacts.run_source_repair_host(**arguments, crash_at="after_intent_fsync")
    before = _scoped_tree_snapshot(system_root)
    key = (
        artifacts.SourceRepairMode.REPAIR,
        artifacts.SourceRepairPhase.INTENT_DURABLE,
        artifacts.SourceRepairFailureLayout.NONE,
    )
    transitions = dict(artifacts.SOURCE_REPAIR_TRANSITIONS)
    if authority_change == "removed":
        transitions.pop(key)
    else:
        transitions[key] = artifacts.SourceRepairTransition(
            artifacts.SourceRepairAction.REFUSE_UNKNOWN, frozenset()
        )
    monkeypatch.setattr(artifacts, "SOURCE_REPAIR_TRANSITIONS", transitions)

    with pytest.raises(
        artifacts.CapacityHostArtifactError,
        match="SOURCE_REPAIR_TRANSITION_(UNKNOWN|REFUSED)",
    ):
        artifacts.run_source_repair_host(**arguments)
    assert _scoped_tree_snapshot(system_root) == before


def test_transition_permitted_next_states_refuse_forward_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    system_root, transport, commit, _manifest = _repair_host_fixture(
        tmp_path, monkeypatch
    )
    arguments = _repair_arguments(system_root, transport, commit)
    with pytest.raises(artifacts.SourceRepairIncomplete):
        artifacts.run_source_repair_host(**arguments, crash_at="after_intent_fsync")
    before = _scoped_tree_snapshot(system_root)
    key = (
        artifacts.SourceRepairMode.REPAIR,
        artifacts.SourceRepairPhase.INTENT_DURABLE,
        artifacts.SourceRepairFailureLayout.NONE,
    )
    transitions = dict(artifacts.SOURCE_REPAIR_TRANSITIONS)
    transitions[key] = artifacts.SourceRepairTransition(
        artifacts.SourceRepairAction.ADVANCE_SOURCE, frozenset()
    )
    monkeypatch.setattr(artifacts, "SOURCE_REPAIR_TRANSITIONS", transitions)

    with pytest.raises(
        artifacts.SourceRepairTransitionError,
        match="SOURCE_REPAIR_NEXT_STATE_REFUSED",
    ):
        artifacts.run_source_repair_host(**arguments)
    assert _scoped_tree_snapshot(system_root) == before


def test_transition_permitted_next_states_refuse_rollback_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    system_root, transport, commit, _manifest = _repair_host_fixture(
        tmp_path, monkeypatch
    )
    arguments = _repair_arguments(system_root, transport, commit)

    def refuse_receipt(*args: object, **kwargs: object) -> str:
        raise artifacts.CapacityHostArtifactError("INJECTED_RECEIPT_REFUSAL")

    with monkeypatch.context() as failure:
        failure.setattr(artifacts, "publish_source_repair_receipt", refuse_receipt)
        with pytest.raises(artifacts.SourceRepairIncomplete):
            artifacts.run_source_repair_host(
                **arguments, crash_at="after_failure_namespace_parent_fsync"
            )
    archive = next((system_root / "capacity-archive").iterdir())
    position = artifacts.reconcile_source_repair(
        archive, expected_uid=os.getuid(), expected_gid=os.getgid()
    )
    before = _scoped_tree_snapshot(system_root)
    key = (
        artifacts.SourceRepairMode.REPAIR,
        position.phase,
        position.failure_layout,
    )
    transitions = dict(artifacts.SOURCE_REPAIR_TRANSITIONS)
    transitions[key] = artifacts.SourceRepairTransition(
        artifacts.SourceRepairAction.RECOVER_PRECOMMIT, frozenset()
    )
    monkeypatch.setattr(artifacts, "SOURCE_REPAIR_TRANSITIONS", transitions)

    with pytest.raises(
        artifacts.SourceRepairTransitionError,
        match="SOURCE_REPAIR_NEXT_STATE_REFUSED",
    ):
        artifacts.run_source_repair_host(**arguments)
    assert _scoped_tree_snapshot(system_root) == before


@pytest.mark.parametrize(
    ("crash_at", "phase"),
    (
        (
            "after_intent_fsync",
            artifacts.SourceRepairPhase.INTENT_DURABLE,
        ),
        (
            "after_old_source_move",
            artifacts.SourceRepairPhase.SOURCE_ARCHIVED,
        ),
        (
            "after_candidate_install",
            artifacts.SourceRepairPhase.SOURCE_INSTALLED,
        ),
        (
            "after_old_generation_move",
            artifacts.SourceRepairPhase.GENERATION_ARCHIVED,
        ),
        (
            "after_repair_receipt_fsync",
            artifacts.SourceRepairPhase.RECEIPT_DURABLE,
        ),
        (
            "before_final_rename",
            artifacts.SourceRepairPhase.GENERATION_PREFIX,
        ),
        (
            None,
            artifacts.SourceRepairPhase.COMMITTED,
        ),
    ),
)
def test_repair_transition_table_refusal_controls_each_forward_position(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    crash_at: str | None,
    phase: artifacts.SourceRepairPhase,
) -> None:
    system_root, transport, commit, _manifest = _repair_host_fixture(
        tmp_path, monkeypatch
    )
    arguments = _repair_arguments(system_root, transport, commit)
    if crash_at is None:
        assert artifacts.run_source_repair_host(**arguments) == (
            "H0_SOURCE_CLOSURE_REPAIR_PASS_NOT_P0_ACCEPTED"
        )
    else:
        with pytest.raises(artifacts.SourceRepairIncomplete):
            artifacts.run_source_repair_host(**arguments, crash_at=crash_at)
    before = _scoped_tree_snapshot(system_root)
    key = (
        artifacts.SourceRepairMode.REPAIR,
        phase,
        artifacts.SourceRepairFailureLayout.NONE,
    )
    transitions = dict(artifacts.SOURCE_REPAIR_TRANSITIONS)
    transitions[key] = artifacts.SourceRepairTransition(
        artifacts.SourceRepairAction.REFUSE_UNKNOWN, frozenset()
    )
    monkeypatch.setattr(artifacts, "SOURCE_REPAIR_TRANSITIONS", transitions)

    expected_error = (
        artifacts.SourceRepairIncomplete
        if phase is artifacts.SourceRepairPhase.COMMITTED
        else artifacts.SourceRepairTransitionError
    )
    with pytest.raises(expected_error):
        artifacts.run_source_repair_host(**arguments)
    assert _scoped_tree_snapshot(system_root) == before


def test_source_repair_host_commits_generation_last_and_verify_is_zero_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    system_root, transport, commit, _manifest = _repair_host_fixture(
        tmp_path, monkeypatch
    )
    lock_events: list[str] = []
    original_lock = artifacts._source_repair_lock

    def observed_lock(*args: object, **kwargs: object) -> int:
        descriptor = original_lock(*args, **kwargs)
        lock_events.append("locked")
        return descriptor

    def resolve_after_lock(operator_user: str) -> int:
        assert operator_user == "operator"
        assert lock_events == ["locked"]
        return os.getuid()

    monkeypatch.setattr(artifacts, "_source_repair_lock", observed_lock)
    monkeypatch.setattr(
        artifacts, "_resolve_source_repair_operator_uid", resolve_after_lock
    )
    result = artifacts.run_source_repair_host(
        mode="repair",
        system_root=system_root,
        lock_file=system_root / "locks" / "cf2-h0.lock",
        expected_repair_commit="d" * 40,
        expected_source_commit=commit,
        operator_user="operator",
        transport=transport,
        transport_sha256=hashlib.sha256(transport.read_bytes()).hexdigest(),
        test_adapter=True,
    )
    assert result == "H0_SOURCE_CLOSURE_REPAIR_PASS_NOT_P0_ACCEPTED"
    archives = list((system_root / "capacity-archive").iterdir())
    assert len(archives) == 1
    assert (archives[0] / "archived-source" / "promisor-source").read_bytes().startswith(
        b"old incomplete"
    )
    assert (archives[0] / "archived-generation").is_dir()
    assert (archives[0] / "source-repair-receipt.json").is_file()
    visible = [path for path in (system_root / "capacity-generations").iterdir()]
    assert len(visible) == 1
    assert not visible[0].name.startswith(".")
    assert sorted(path.name for path in visible[0].iterdir()) == [
        "broker-topology.json",
        "components.json",
        "host-preparation-receipt.json",
        "rollback-contract.json",
        "rollback-drill-receipt.json",
        "source-config.json",
    ]

    content_before = _scoped_content_observation(system_root)
    metadata_before = _scoped_metadata_observation(system_root)
    for _ in range(2):
        assert artifacts.run_source_repair_host(
            mode="verify-only",
            system_root=system_root,
            lock_file=system_root / "locks" / "cf2-h0.lock",
            expected_repair_commit="d" * 40,
            expected_source_commit=commit,
            transport=None,
            transport_sha256=None,
            test_adapter=True,
        ) == "H0_INSTALLED_HOST_PASS_NOT_P0_ACCEPTED"
    metadata_after = _scoped_metadata_observation(system_root)
    content_after = _scoped_content_observation(system_root)
    _assert_only_kernel_atime_may_advance(metadata_before, metadata_after)
    assert content_after == content_before


def test_verify_only_native_read_atime_advance_is_observed_separately(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    system_root, transport, commit, _manifest = _repair_host_fixture(
        tmp_path, monkeypatch
    )
    arguments = _repair_arguments(system_root, transport, commit)
    assert artifacts.run_source_repair_host(**arguments) == (
        "H0_SOURCE_CLOSURE_REPAIR_PASS_NOT_P0_ACCEPTED"
    )
    installed_index = (
        system_root / "capacity-sources" / "macro" / commit / ".git" / "index"
    )
    expected_index_digest = hashlib.sha256(installed_index.read_bytes()).hexdigest()
    observed = installed_index.stat()
    os.utime(
        installed_index,
        ns=(observed.st_mtime_ns - 1_000_000_000, observed.st_mtime_ns),
    )
    metadata_before = _scoped_metadata_observation(system_root)

    assert artifacts.run_source_repair_host(
        **_verify_arguments(system_root, commit)
    ) == "H0_INSTALLED_HOST_PASS_NOT_P0_ACCEPTED"
    metadata_after = _scoped_metadata_observation(system_root)
    _assert_only_kernel_atime_may_advance(metadata_before, metadata_after)
    relative_index = installed_index.relative_to(system_root).as_posix()
    assert metadata_after[1][relative_index] > metadata_before[1][relative_index]
    assert hashlib.sha256(installed_index.read_bytes()).hexdigest() == expected_index_digest


def test_verify_only_has_no_reachable_program_mutation_api(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    system_root, transport, commit, _manifest = _repair_host_fixture(
        tmp_path, monkeypatch
    )
    arguments = _repair_arguments(system_root, transport, commit)
    assert artifacts.run_source_repair_host(**arguments) == (
        "H0_SOURCE_CLOSURE_REPAIR_PASS_NOT_P0_ACCEPTED"
    )
    content_before = _scoped_content_observation(system_root)
    metadata_before = _scoped_metadata_observation(system_root)
    original_open = os.open

    def read_only_open(path: object, flags: int, *args: object, **kwargs: object) -> int:
        forbidden_flags = (
            os.O_WRONLY
            | os.O_RDWR
            | os.O_CREAT
            | os.O_TRUNC
            | os.O_APPEND
            | getattr(os, "O_EXCL", 0)
        )
        assert flags & forbidden_flags == 0, (path, flags)
        return original_open(path, flags, *args, **kwargs)

    def forbidden_mutation(*args: object, **kwargs: object) -> None:
        raise AssertionError((args, kwargs))

    with monkeypatch.context() as mutation_guard:
        mutation_guard.setattr(os, "open", read_only_open)
        for name in (
            "chmod",
            "fchmod",
            "chown",
            "fchown",
            "mkdir",
            "makedirs",
            "rename",
            "replace",
            "unlink",
            "remove",
            "rmdir",
            "link",
            "symlink",
            "utime",
            "truncate",
            "ftruncate",
            "fsync",
            "chflags",
            "fchflags",
            "setxattr",
            "removexattr",
        ):
            if hasattr(os, name):
                mutation_guard.setattr(os, name, forbidden_mutation)
        for name in (
            "_rename_exclusive",
            "publish_source_repair_intent",
            "publish_source_repair_receipt",
            "_build_repaired_generation_candidate",
            "_restore_digest_bound_precommit_state",
            "_durable_source_repair_rename",
            "_write_generation_payload",
            "copy_closed_input",
            "materialize_source_transport_v3",
        ):
            mutation_guard.setattr(artifacts, name, forbidden_mutation)
        assert artifacts.run_source_repair_host(
            **_verify_arguments(system_root, commit)
        ) == "H0_INSTALLED_HOST_PASS_NOT_P0_ACCEPTED"

    metadata_after = _scoped_metadata_observation(system_root)
    content_after = _scoped_content_observation(system_root)
    _assert_only_kernel_atime_may_advance(metadata_before, metadata_after)
    assert content_after == content_before


def test_source_repair_replays_forward_after_visible_final_rename_without_rollback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    system_root, transport, commit, _manifest = _repair_host_fixture(
        tmp_path, monkeypatch
    )
    with pytest.raises(artifacts.SourceRepairIncomplete):
        artifacts.run_source_repair_host(
            mode="repair",
            system_root=system_root,
            lock_file=system_root / "locks" / "cf2-h0.lock",
            expected_repair_commit="d" * 40,
            expected_source_commit=commit,
            operator_uid=os.getuid(),
            transport=transport,
            transport_sha256=hashlib.sha256(transport.read_bytes()).hexdigest(),
            test_adapter=True,
            crash_at="after_final_rename_before_parent_fsync",
        )
    archive = next((system_root / "capacity-archive").iterdir())
    assert (archive / "archived-source").is_dir()
    assert not (system_root / "capacity-generations" / artifacts.PRIOR_GENERATION_DIGEST).exists()
    assert artifacts.run_source_repair_host(
        mode="repair",
        system_root=system_root,
        lock_file=system_root / "locks" / "cf2-h0.lock",
        expected_repair_commit="d" * 40,
        expected_source_commit=commit,
        operator_uid=os.getuid(),
        transport=transport,
        transport_sha256=hashlib.sha256(transport.read_bytes()).hexdigest(),
        test_adapter=True,
    ) == "H0_SOURCE_CLOSURE_REPAIR_PASS_NOT_P0_ACCEPTED"
    assert (archive / "archived-source").is_dir()


def test_source_repair_replay_after_success_stdout_is_exactly_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    system_root, transport, commit, _manifest = _repair_host_fixture(
        tmp_path, monkeypatch
    )
    arguments = {
        "mode": "repair",
        "system_root": system_root,
        "lock_file": system_root / "locks" / "cf2-h0.lock",
        "expected_repair_commit": "d" * 40,
        "expected_source_commit": commit,
        "operator_uid": os.getuid(),
        "transport": transport,
        "transport_sha256": hashlib.sha256(transport.read_bytes()).hexdigest(),
        "test_adapter": True,
    }
    assert artifacts.run_source_repair_host(**arguments) == (
        "H0_SOURCE_CLOSURE_REPAIR_PASS_NOT_P0_ACCEPTED"
    )
    committed = _scoped_tree_snapshot(system_root)
    assert artifacts.run_source_repair_host(**arguments) == (
        "H0_SOURCE_CLOSURE_REPAIR_PASS_NOT_P0_ACCEPTED"
    )
    assert _scoped_tree_snapshot(system_root) == committed

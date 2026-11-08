"""Capacity host recovery cases; shared helpers retain their original owner."""
from __future__ import annotations

from tests.test_capacity_host_artifacts import (
    Path,
    _repair_arguments,
    _repair_host_fixture,
    _rollback_started_empty_fixture,
    artifacts,
    errno,
    os,
    pytest,
)


@pytest.mark.parametrize(
    "observation_name",
    (
        "_observe_source_repair_source",
        "_observe_source_repair_archived_generation",
        "_expected_source_repair_receipt",
        "_generation_values",
    ),
)
def test_committed_replay_early_observation_failure_never_rolls_back(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    observation_name: str,
) -> None:
    system_root, transport, commit, _manifest = _repair_host_fixture(
        tmp_path, monkeypatch
    )
    arguments = _repair_arguments(system_root, transport, commit)
    assert artifacts.run_source_repair_host(**arguments) == (
        "H0_SOURCE_CLOSURE_REPAIR_PASS_NOT_P0_ACCEPTED"
    )
    archive = next((system_root / "capacity-archive").iterdir())

    def fail_committed_observation(*args: object, **kwargs: object) -> object:
        raise artifacts.CapacityHostArtifactError("INJECTED_COMMITTED_OBSERVATION")

    monkeypatch.setattr(artifacts, observation_name, fail_committed_observation)
    with pytest.raises(
        artifacts.SourceRepairIncomplete,
        match="POST_COMMIT_RECONCILIATION_REQUIRED",
    ):
        artifacts.run_source_repair_host(**arguments)

    visible_generations = [
        child
        for child in (system_root / "capacity-generations").iterdir()
        if not child.name.startswith(".")
    ]
    assert len(visible_generations) == 1
    assert not any(child.name.startswith("failure-") for child in archive.iterdir())
    assert (archive / "archived-source").is_dir()
    assert (archive / "archived-generation").is_dir()


@pytest.mark.parametrize(
    "fault_site",
    (
        "transition_reconcile",
        "initial_classification",
        "classification_entry_observation",
        "generation_parent_inventory",
    ),
)
def test_committed_replay_structural_fault_before_recovery_authorization_is_effect_unknown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fault_site: str,
) -> None:
    system_root, transport, commit, _manifest = _repair_host_fixture(
        tmp_path, monkeypatch
    )
    arguments = _repair_arguments(system_root, transport, commit)
    assert artifacts.run_source_repair_host(**arguments) == (
        "H0_SOURCE_CLOSURE_REPAIR_PASS_NOT_P0_ACCEPTED"
    )
    archive = next((system_root / "capacity-archive").iterdir())
    injected = artifacts.CapacityHostArtifactError(
        f"INJECTED_STRUCTURAL_FAULT_{fault_site.upper()}"
    )
    original_restore = artifacts._restore_digest_bound_precommit_state
    restore_calls = 0
    fault_triggered = False

    def observed_restore(*args: object, **kwargs: object) -> None:
        nonlocal restore_calls
        restore_calls += 1
        original_restore(*args, **kwargs)

    with monkeypatch.context() as replay_fault:
        replay_fault.setattr(
            artifacts, "_restore_digest_bound_precommit_state", observed_restore
        )
        if fault_site == "transition_reconcile":
            original_reconcile = artifacts.reconcile_source_repair
            reconcile_calls = 0

            def fault_transition_reconcile(*args: object, **kwargs: object) -> object:
                nonlocal fault_triggered, reconcile_calls
                reconcile_calls += 1
                if reconcile_calls == 2:
                    fault_triggered = True
                    raise injected
                return original_reconcile(*args, **kwargs)

            replay_fault.setattr(
                artifacts, "reconcile_source_repair", fault_transition_reconcile
            )
        elif fault_site == "initial_classification":
            original_classify = artifacts._classify_source_repair_position

            def fault_initial_classification(
                *args: object, **kwargs: object
            ) -> object:
                nonlocal fault_triggered
                if not fault_triggered:
                    fault_triggered = True
                    raise injected
                return original_classify(*args, **kwargs)

            replay_fault.setattr(
                artifacts,
                "_classify_source_repair_position",
                fault_initial_classification,
            )
        elif fault_site == "classification_entry_observation":
            original_entry_info = artifacts._descriptor_entry_info

            def fault_classification_entry_observation(
                *args: object, **kwargs: object
            ) -> object:
                nonlocal fault_triggered
                if not fault_triggered:
                    fault_triggered = True
                    raise injected
                return original_entry_info(*args, **kwargs)

            replay_fault.setattr(
                artifacts,
                "_descriptor_entry_info",
                fault_classification_entry_observation,
            )
        elif fault_site == "generation_parent_inventory":
            original_directory_names = artifacts._descriptor_directory_names
            generation_info = (system_root / "capacity-generations").stat()
            generation_identity = (generation_info.st_dev, generation_info.st_ino)

            def fault_generation_parent_inventory(descriptor: int) -> list[str]:
                nonlocal fault_triggered
                descriptor_info = os.fstat(descriptor)
                if (
                    not fault_triggered
                    and (descriptor_info.st_dev, descriptor_info.st_ino)
                    == generation_identity
                ):
                    fault_triggered = True
                    raise injected
                return original_directory_names(descriptor)

            replay_fault.setattr(
                artifacts,
                "_descriptor_directory_names",
                fault_generation_parent_inventory,
            )
        else:
            raise AssertionError(fault_site)

        with pytest.raises(
            artifacts.SourceRepairIncomplete,
            match="POST_COMMIT_RECONCILIATION_REQUIRED",
        ) as raised:
            artifacts.run_source_repair_host(**arguments)

    assert fault_triggered
    assert raised.value.__cause__ is injected
    assert restore_calls == 0
    assert not any(child.name.startswith("failure-") for child in archive.iterdir())
    assert (archive / "archived-source").is_dir()
    assert (archive / "archived-generation").is_dir()
    visible_generations = [
        child
        for child in (system_root / "capacity-generations").iterdir()
        if not child.name.startswith(".")
    ]
    assert len(visible_generations) == 1
    assert not (
        system_root
        / "capacity-generations"
        / artifacts.PRIOR_GENERATION_DIGEST
    ).exists()
    assert artifacts.run_source_repair_host(**arguments) == (
        "H0_SOURCE_CLOSURE_REPAIR_PASS_NOT_P0_ACCEPTED"
    )


def test_exact_precommit_classification_pre_authorizes_table_recovery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    system_root, transport, commit, _manifest = _repair_host_fixture(
        tmp_path, monkeypatch
    )
    arguments = _repair_arguments(system_root, transport, commit)
    original_classify = artifacts._classify_source_repair_position
    original_transition_for = artifacts._source_repair_transition_for
    original_restore = artifacts._restore_digest_bound_precommit_state
    events: list[tuple[object, ...]] = []
    injected = artifacts.CapacityHostArtifactError("INJECTED_RECEIPT_REFUSAL")

    def observed_classify(*args: object, **kwargs: object) -> object:
        phase = original_classify(*args, **kwargs)
        events.append(("classified", phase))
        return phase

    def observed_transition_for(
        mode: artifacts.SourceRepairMode,
        phase: artifacts.SourceRepairPhase,
        failure_layout: artifacts.SourceRepairFailureLayout,
    ) -> artifacts.SourceRepairTransition:
        transition = original_transition_for(mode, phase, failure_layout)
        events.append(("transition", mode, phase, failure_layout, transition))
        return transition

    def refuse_receipt(*args: object, **kwargs: object) -> str:
        events.append(("fault", injected))
        raise injected

    def observed_restore(*args: object, **kwargs: object) -> None:
        events.append(("restore", kwargs["transition"]))
        original_restore(*args, **kwargs)

    monkeypatch.setattr(
        artifacts, "_classify_source_repair_position", observed_classify
    )
    monkeypatch.setattr(
        artifacts, "_source_repair_transition_for", observed_transition_for
    )
    monkeypatch.setattr(artifacts, "publish_source_repair_receipt", refuse_receipt)
    monkeypatch.setattr(
        artifacts, "_restore_digest_bound_precommit_state", observed_restore
    )

    with pytest.raises(
        artifacts.CapacityHostArtifactError, match="INJECTED_RECEIPT_REFUSAL"
    ) as raised:
        artifacts.run_source_repair_host(**arguments)
    assert raised.value is injected

    classified_index = next(
        index
        for index, event in enumerate(events)
        if event == ("classified", artifacts.SourceRepairPhase.GENERATION_ARCHIVED)
    )
    recovery_index = next(
        index
        for index, event in enumerate(events)
        if event[:4]
        == (
            "transition",
            artifacts.SourceRepairMode.RECOVERY,
            artifacts.SourceRepairPhase.GENERATION_ARCHIVED,
            artifacts.SourceRepairFailureLayout.NONE,
        )
    )
    fault_index = next(
        index for index, event in enumerate(events) if event[0] == "fault"
    )
    restore_index = next(
        index for index, event in enumerate(events) if event[0] == "restore"
    )
    assert classified_index < recovery_index < fault_index < restore_index
    assert not any(
        event[0] == "classified" for event in events[fault_index + 1 : restore_index]
    )
    recovery_transition = events[recovery_index][4]
    assert isinstance(recovery_transition, artifacts.SourceRepairTransition)
    assert recovery_transition.action is artifacts.SourceRepairAction.RECOVER_PRECOMMIT
    assert events[restore_index][1] is recovery_transition
    assert sum(event[0] == "restore" for event in events) == 1
    restored_source = system_root / "capacity-sources" / "macro" / commit
    assert restored_source.is_dir()
    assert (
        system_root
        / "capacity-generations"
        / artifacts.PRIOR_GENERATION_DIGEST
    ).is_dir()


def test_direct_recovery_consumes_grant_before_single_restore_attempt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    system_root, arguments, archive = _rollback_started_empty_fixture(
        tmp_path, monkeypatch
    )
    original_restore = artifacts._restore_digest_bound_precommit_state
    restore_transitions: list[artifacts.SourceRepairTransition] = []

    def observed_restore(*args: object, **kwargs: object) -> None:
        transition = kwargs["transition"]
        assert isinstance(transition, artifacts.SourceRepairTransition)
        restore_transitions.append(transition)
        original_restore(*args, **kwargs)

    monkeypatch.setattr(
        artifacts, "_restore_digest_bound_precommit_state", observed_restore
    )
    with pytest.raises(
        artifacts.CapacityHostArtifactError,
        match="SOURCE_REPAIR_PRECOMMIT_RESTORED",
    ):
        artifacts.run_source_repair_host(**arguments)

    assert len(restore_transitions) == 1
    direct_transition = artifacts.SOURCE_REPAIR_TRANSITIONS[
        (
            artifacts.SourceRepairMode.REPAIR,
            artifacts.SourceRepairPhase.ROLLBACK_STARTED,
            artifacts.SourceRepairFailureLayout.EMPTY,
        )
    ]
    assert restore_transitions[0] is direct_transition
    position = artifacts.reconcile_source_repair(
        archive, expected_uid=os.getuid(), expected_gid=os.getgid()
    )
    assert position.phase is artifacts.SourceRepairPhase.ROLLED_BACK
    assert (
        position.failure_layout
        is artifacts.SourceRepairFailureLayout.INSTALLED_SOURCE
    )
    assert (
        system_root
        / "capacity-generations"
        / artifacts.PRIOR_GENERATION_DIGEST
    ).is_dir()


def test_direct_recovery_typed_incomplete_is_single_attempt_and_replays(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    system_root, arguments, archive = _rollback_started_empty_fixture(
        tmp_path, monkeypatch
    )
    restore_calls = 0
    injected_cause = OSError(errno.EIO, "injected recovery interruption")
    injected = artifacts.SourceRepairIncomplete(
        "INJECTED_RECOVERY_INCOMPLETE"
    )

    def interrupt_restore(*args: object, **kwargs: object) -> None:
        nonlocal restore_calls
        restore_calls += 1
        raise injected from injected_cause

    with monkeypatch.context() as interrupted:
        interrupted.setattr(
            artifacts, "_restore_digest_bound_precommit_state", interrupt_restore
        )
        with pytest.raises(
            artifacts.SourceRepairIncomplete,
            match="INJECTED_RECOVERY_INCOMPLETE",
        ) as raised:
            artifacts.run_source_repair_host(**arguments)

    assert raised.value is injected
    assert raised.value.__cause__ is injected_cause
    assert restore_calls == 1
    interrupted_position = artifacts.reconcile_source_repair(
        archive, expected_uid=os.getuid(), expected_gid=os.getgid()
    )
    assert interrupted_position.phase is artifacts.SourceRepairPhase.ROLLBACK_STARTED
    assert (
        interrupted_position.failure_layout
        is artifacts.SourceRepairFailureLayout.EMPTY
    )

    with pytest.raises(
        artifacts.CapacityHostArtifactError,
        match="SOURCE_REPAIR_PRECOMMIT_RESTORED",
    ):
        artifacts.run_source_repair_host(**arguments)
    replayed_position = artifacts.reconcile_source_repair(
        archive, expected_uid=os.getuid(), expected_gid=os.getgid()
    )
    assert replayed_position.phase is artifacts.SourceRepairPhase.ROLLED_BACK
    assert (
        replayed_position.failure_layout
        is artifacts.SourceRepairFailureLayout.INSTALLED_SOURCE
    )
    assert (
        system_root
        / "capacity-generations"
        / artifacts.PRIOR_GENERATION_DIGEST
    ).is_dir()


def test_direct_recovery_durability_uncertain_is_single_attempt_and_replays(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    system_root, arguments, archive = _rollback_started_empty_fixture(
        tmp_path, monkeypatch
    )
    restore_calls = 0
    injected_cause = OSError(errno.EIO, "injected recovery durability")
    injected = artifacts.SourceRepairRenameDurabilityUncertain(
        "INJECTED_RECOVERY_DURABILITY_UNCERTAIN"
    )

    def interrupt_restore(*args: object, **kwargs: object) -> None:
        nonlocal restore_calls
        restore_calls += 1
        raise injected from injected_cause

    with monkeypatch.context() as interrupted:
        interrupted.setattr(
            artifacts, "_restore_digest_bound_precommit_state", interrupt_restore
        )
        with pytest.raises(
            artifacts.SourceRepairRenameDurabilityUncertain,
            match="INJECTED_RECOVERY_DURABILITY_UNCERTAIN",
        ) as raised:
            artifacts.run_source_repair_host(**arguments)

    assert raised.value is injected
    assert raised.value.__cause__ is injected_cause
    assert restore_calls == 1
    interrupted_position = artifacts.reconcile_source_repair(
        archive, expected_uid=os.getuid(), expected_gid=os.getgid()
    )
    assert interrupted_position.phase is artifacts.SourceRepairPhase.ROLLBACK_STARTED
    assert (
        interrupted_position.failure_layout
        is artifacts.SourceRepairFailureLayout.EMPTY
    )

    with pytest.raises(
        artifacts.CapacityHostArtifactError,
        match="SOURCE_REPAIR_PRECOMMIT_RESTORED",
    ):
        artifacts.run_source_repair_host(**arguments)
    replayed_position = artifacts.reconcile_source_repair(
        archive, expected_uid=os.getuid(), expected_gid=os.getgid()
    )
    assert replayed_position.phase is artifacts.SourceRepairPhase.ROLLED_BACK
    assert (
        replayed_position.failure_layout
        is artifacts.SourceRepairFailureLayout.INSTALLED_SOURCE
    )
    assert (
        system_root
        / "capacity-generations"
        / artifacts.PRIOR_GENERATION_DIGEST
    ).is_dir()

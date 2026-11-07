"""Capacity host failure evidence cases; shared helpers retain their original owner."""
from __future__ import annotations

from tests.test_capacity_host_artifacts import (
    Path,
    _repair_arguments,
    _repair_host_fixture,
    _terminal_failure_evidence_fixture,
    artifacts,
    os,
    pytest,
    stat,
)


@pytest.mark.parametrize("layout", ("installed-source", "staged-source"))
@pytest.mark.parametrize(
    "mutation",
    (
        "type",
        "symlink",
        "mode",
        "ownership",
        "device_identity",
        "hard_link",
        "unexpected_descendant",
        "content_digest",
    ),
)
def test_failure_evidence_layouts_refuse_every_semantic_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    layout: str,
    mutation: str,
) -> None:
    _system_root, archive, evidence = _terminal_failure_evidence_fixture(
        tmp_path, monkeypatch, layout
    )
    expected_uid = os.getuid()
    expected_gid = os.getgid()
    if mutation in {"type", "symlink"}:
        preserved = tmp_path / f"preserved-{layout}"
        evidence.rename(preserved)
        if mutation == "type":
            evidence.write_bytes(b"not a repository\n")
        else:
            evidence.symlink_to(preserved, target_is_directory=True)
    elif mutation == "mode":
        evidence.chmod(0o755)
    elif mutation == "ownership":
        alternate_gid = next(gid for gid in os.getgroups() if gid != expected_gid)
        os.chown(evidence, -1, alternate_gid)
    elif mutation == "device_identity":
        original_fstat = os.fstat
        evidence_info = evidence.stat()

        def wrong_device(descriptor: int) -> os.stat_result:
            info = original_fstat(descriptor)
            if info.st_dev == evidence_info.st_dev and info.st_ino == evidence_info.st_ino:
                values = list(info)
                values[2] = info.st_dev + 1
                return os.stat_result(values)
            return info

        monkeypatch.setattr(os, "fstat", wrong_device)
    elif mutation == "hard_link":
        linked = next(path for path in evidence.rglob("*") if path.is_file())
        os.link(linked, tmp_path / f"external-hard-link-{layout}")
    elif mutation == "unexpected_descendant":
        (evidence / "unexpected-evidence").write_bytes(b"unexpected\n")
    elif mutation == "content_digest":
        changed = next(
            path
            for path in evidence.rglob("*")
            if path.is_file() and ".git" not in path.relative_to(evidence).parts
        )
        original_mode = stat.S_IMODE(changed.stat().st_mode)
        changed.chmod(0o600)
        changed.write_bytes(changed.read_bytes() + b"tampered\n")
        changed.chmod(original_mode)
    else:
        raise AssertionError(mutation)

    with pytest.raises(
        artifacts.CapacityHostArtifactError,
        match="SOURCE_REPAIR_FAILURE_(EVIDENCE|NAMESPACE)_INVALID",
    ):
        artifacts.reconcile_source_repair(
            archive, expected_uid=expected_uid, expected_gid=expected_gid
        )


def test_failure_evidence_binds_exact_intent_source_tree_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _system_root, archive, _evidence_path = _terminal_failure_evidence_fixture(
        tmp_path, monkeypatch, "installed-source"
    )
    original_verify = artifacts._verify_installed_repair_source

    def unequal_tree_with_same_inventory(
        *args: object, **kwargs: object
    ) -> tuple[dict[str, object], artifacts.SourceClosureEvidence]:
        manifest, evidence = original_verify(*args, **kwargs)
        return manifest, artifacts.SourceClosureEvidence(
            object_count=evidence.object_count,
            object_inventory_sha256=evidence.object_inventory_sha256,
            source_tree_sha256="0" * 64,
        )

    monkeypatch.setattr(
        artifacts, "_verify_installed_repair_source", unequal_tree_with_same_inventory
    )
    with pytest.raises(
        artifacts.CapacityHostArtifactError,
        match="SOURCE_REPAIR_FAILURE_EVIDENCE_INVALID",
    ):
        artifacts.reconcile_source_repair(
            archive, expected_uid=os.getuid(), expected_gid=os.getgid()
        )


def test_empty_failure_namespace_is_an_explicit_recovery_child_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    system_root, transport, commit, _manifest = _repair_host_fixture(
        tmp_path, monkeypatch
    )
    arguments = _repair_arguments(system_root, transport, commit)
    def refuse_receipt(*args: object, **kwargs: object) -> str:
        raise artifacts.CapacityHostArtifactError("INJECTED_RECEIPT_REFUSAL")

    monkeypatch.setattr(artifacts, "publish_source_repair_receipt", refuse_receipt)
    with pytest.raises(artifacts.SourceRepairIncomplete):
        artifacts.run_source_repair_host(
            **arguments, crash_at="after_failure_namespace_parent_fsync"
        )
    archive = next((system_root / "capacity-archive").iterdir())
    position = artifacts.reconcile_source_repair(
        archive, expected_uid=os.getuid(), expected_gid=os.getgid()
    )
    assert position.failure_layout is artifacts.SourceRepairFailureLayout.EMPTY


def test_terminal_recovery_revalidates_preserved_failure_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    system_root, transport, commit, _manifest = _repair_host_fixture(
        tmp_path, monkeypatch
    )
    arguments = _repair_arguments(system_root, transport, commit)
    original_rename = artifacts._durable_source_repair_rename

    def mutate_after_source_restore(*args: object, **kwargs: object) -> object:
        result = original_rename(*args, **kwargs)
        if kwargs.get("move_name") == "rollback_source":
            archive = next((system_root / "capacity-archive").iterdir())
            failure_namespace = archive / (
                f"failure-{archive.name.removeprefix('source-closure-repair-')}"
            )
            evidence = failure_namespace / "installed-source"
            changed = next(
                path
                for path in evidence.rglob("*")
                if path.is_file() and ".git" not in path.relative_to(evidence).parts
            )
            original_mode = stat.S_IMODE(changed.stat().st_mode)
            changed.chmod(0o600)
            changed.write_bytes(changed.read_bytes() + b"late-tamper\n")
            changed.chmod(original_mode)
        return result

    def refuse_receipt(*args: object, **kwargs: object) -> str:
        raise artifacts.CapacityHostArtifactError("INJECTED_RECEIPT_REFUSAL")

    monkeypatch.setattr(
        artifacts, "_durable_source_repair_rename", mutate_after_source_restore
    )
    monkeypatch.setattr(artifacts, "publish_source_repair_receipt", refuse_receipt)
    with pytest.raises(
        artifacts.CapacityHostArtifactError,
        match="SOURCE_REPAIR_FAILURE_EVIDENCE_INVALID",
    ):
        artifacts.run_source_repair_host(**arguments)

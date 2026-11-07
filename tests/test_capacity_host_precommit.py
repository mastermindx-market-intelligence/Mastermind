"""Capacity host precommit cases; shared helpers retain their original owner."""
from __future__ import annotations

from tests.test_capacity_host_artifacts import (
    Path,
    _FakePreservedView,
    _PRESERVED_LABELS,
    _git,
    _repair_arguments,
    _repair_carrier_git_fixture,
    _repair_host_fixture,
    _verify_arguments,
    artifacts,
    contract,
    hashlib,
    json,
    os,
    pytest,
    subprocess,
)


@pytest.mark.parametrize(
    "timeout_target,expected_reason",
    (
        ("print-disabled", "SOURCE_REPAIR_SERVICE_STATE_INVALID"),
        *((label, "SOURCE_REPAIR_SERVICE_STATE_INVALID") for label in _PRESERVED_LABELS),
        ("dscl", "SOURCE_REPAIR_PRINCIPAL_INVALID"),
        ("dsmemberutil", "SOURCE_REPAIR_PRINCIPAL_INVALID"),
        ("dseditgroup", "SOURCE_REPAIR_PRINCIPAL_INVALID"),
        ("id", "SOURCE_REPAIR_PRINCIPAL_INVALID"),
    ),
)
def test_preserved_native_command_timeout_is_typed_at_each_semantic_stage(
    monkeypatch: pytest.MonkeyPatch,
    timeout_target: str,
    expected_reason: str,
) -> None:
    disabled = (
        "disabled services = {\n"
        + "".join(f'    "{label}" => true\n' for label in _PRESERVED_LABELS)
        + "}\n"
    ).encode("utf-8")

    def completed(
        arguments: list[str], *args: object, **kwargs: object
    ) -> subprocess.CompletedProcess[bytes]:
        executable = Path(arguments[0]).name
        target = (
            arguments[-1].removeprefix("system/")
            if arguments[:2] == ["/bin/launchctl", "print"]
            else arguments[1] if arguments[:2] == ["/bin/launchctl", "print-disabled"]
            else executable
        )
        if target == timeout_target:
            raise subprocess.TimeoutExpired(
                arguments,
                5,
                output=b"/private/secret-output",
                stderr=b"secret-error",
            )
        if arguments[:2] == ["/bin/launchctl", "print-disabled"]:
            return subprocess.CompletedProcess(arguments, 0, disabled, b"")
        if arguments[:2] == ["/bin/launchctl", "print"]:
            return subprocess.CompletedProcess(arguments, 113, b"", b"")
        if executable == "dscl":
            field = arguments[-1]
            record = Path(arguments[-2]).name
            expected = {
                "_mastermind_exec": 450,
                "_mastermind_codex_01": 454,
                "_mastermind_codex_02": 455,
                "_mastermind_codex_03": 456,
            }[record]
            return subprocess.CompletedProcess(
                arguments, 0, f"{field}: {expected}\n".encode("ascii"), b""
            )
        if executable == "dsmemberutil":
            return subprocess.CompletedProcess(
                arguments, 0, b"user is a member of the group\n", b""
            )
        if executable == "dseditgroup":
            group = arguments[-1]
            return subprocess.CompletedProcess(
                arguments,
                67,
                f"no _mastermind_exec is NOT a member of {group}\n".encode("ascii"),
                b"",
            )
        if executable == "id":
            return subprocess.CompletedProcess(arguments, 0, b"12 61 100 450\n", b"")
        raise AssertionError(arguments)

    monkeypatch.setattr(artifacts.subprocess, "run", completed)
    with pytest.raises(artifacts.CapacityHostArtifactError) as caught:
        artifacts._verify_preserved_service_principal_state(_PRESERVED_LABELS)
    assert str(caught.value) == expected_reason
    assert "/private" not in str(caught.value)
    assert "secret" not in str(caught.value)


def test_source_repair_cli_normalizes_subprocess_timeout_without_argv_leak(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def timed_out(**kwargs: object) -> str:
        raise subprocess.TimeoutExpired(
            ["/bin/launchctl", "print", "system/private-secret-label"],
            5,
            output=b"private output",
            stderr=b"private error",
        )

    monkeypatch.setattr(artifacts, "run_source_repair_host", timed_out)
    code = artifacts.main(
        [
            "source-repair-host",
            "--mode",
            "verify-only",
            "--system-root",
            str(tmp_path),
            "--lock-file",
            str(tmp_path / "locks" / "cf2-h0.lock"),
            "--expected-repair-commit",
            "d" * 40,
            "--expected-source-commit",
            artifacts.PRODUCER_COMMIT,
        ]
    )
    captured = capsys.readouterr()
    assert code == 65
    assert captured.out == ""
    assert captured.err == (
        "capacity host artifact refused: "
        "SOURCE_REPAIR_PRESERVED_EVIDENCE_INVALID\n"
    )


def test_precommit_subprocess_timeout_uses_authorized_recovery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    system_root, transport, commit, _manifest = _repair_host_fixture(
        tmp_path, monkeypatch
    )
    arguments = _repair_arguments(system_root, transport, commit)
    calls = 0

    def timeout_at_final_precommit_check(*args: object, **kwargs: object) -> None:
        nonlocal calls
        calls += 1
        if calls > 1:
            raise subprocess.TimeoutExpired(
                ["/bin/launchctl", "print-disabled", "system"], 5
            )

    monkeypatch.setattr(
        artifacts, "_verify_preserved_h0_invariants", timeout_at_final_precommit_check
    )
    with pytest.raises(artifacts.CapacityHostArtifactError) as caught:
        artifacts.run_source_repair_host(**arguments)
    assert str(caught.value) == "SOURCE_REPAIR_PRESERVED_EVIDENCE_INVALID"
    archive = next((system_root / "capacity-archive").iterdir())
    position = artifacts.reconcile_source_repair(
        archive, expected_uid=os.getuid(), expected_gid=os.getgid()
    )
    assert position.phase is artifacts.SourceRepairPhase.ROLLED_BACK


@pytest.mark.parametrize(
    ("observer_name", "error_kind"),
    (
        pytest.param(
            "_observe_source_repair_source", "timeout", id="source-timeout"
        ),
        pytest.param(
            "_observe_source_repair_source", "generic", id="source-generic"
        ),
        pytest.param(
            "_observe_source_repair_archived_generation",
            "timeout",
            id="archived-generation-timeout",
        ),
        pytest.param(
            "_observe_source_repair_archived_generation",
            "generic",
            id="archived-generation-generic",
        ),
    ),
)
def test_receipt_durable_precommit_observer_subprocess_failure_restores_exact_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    observer_name: str,
    error_kind: str,
) -> None:
    system_root, transport, commit, _manifest = _repair_host_fixture(
        tmp_path, monkeypatch
    )
    arguments = _repair_arguments(system_root, transport, commit)
    source_root = system_root / "capacity-sources" / "macro" / commit
    generation_root = system_root / "capacity-generations"
    old_generation = generation_root / artifacts.PRIOR_GENERATION_DIGEST
    expected_uid = os.getuid()
    expected_gid = os.getgid()
    source_digest_before = artifacts.closed_tree_digest(
        source_root, expected_uid=expected_uid, expected_gid=expected_gid
    )
    generation_digest_before = artifacts.closed_tree_digest(
        old_generation, expected_uid=expected_uid, expected_gid=expected_gid
    )

    with pytest.raises(
        artifacts.SourceRepairIncomplete, match="after_repair_receipt_fsync"
    ):
        artifacts.run_source_repair_host(
            **arguments, crash_at="after_repair_receipt_fsync"
        )

    archive = next((system_root / "capacity-archive").iterdir())
    position = artifacts.reconcile_source_repair(
        archive, expected_uid=expected_uid, expected_gid=expected_gid
    )
    assert position.phase is artifacts.SourceRepairPhase.RECEIPT_DURABLE
    assert position.failure_layout is artifacts.SourceRepairFailureLayout.NONE
    parents = artifacts._open_source_repair_parents(
        system_root, expected_uid=expected_uid, expected_gid=expected_gid
    )
    try:
        artifacts._attach_source_repair_archive_parent(
            parents,
            archive,
            expected_uid=expected_uid,
            expected_gid=expected_gid,
        )
        structural_phase = artifacts._classify_source_repair_position(
            archive_position=position,
            parents=parents,
            source_name=commit,
            staged_source_name=f"source-candidate-{'d' * 40}",
        )
        assert structural_phase is artifacts.SourceRepairPhase.RECEIPT_DURABLE
        assert not any(
            not name.startswith(".")
            for name in artifacts._descriptor_directory_names(parents.generation)
        )
    finally:
        parents.close()

    private_marker = "/private/receipt-durable-observer-secret"
    if error_kind == "timeout":
        injected: subprocess.SubprocessError = subprocess.TimeoutExpired(
            ["/bin/observer", private_marker],
            5,
            output=b"private output",
            stderr=b"private error",
        )
    else:
        injected = subprocess.SubprocessError(private_marker)
    fault_calls = 0
    restore_transitions: list[artifacts.SourceRepairTransition] = []
    original_restore = artifacts._restore_digest_bound_precommit_state

    def fail_observer(*args: object, **kwargs: object) -> object:
        nonlocal fault_calls
        fault_calls += 1
        raise injected

    def observed_restore(*args: object, **kwargs: object) -> None:
        transition = kwargs["transition"]
        assert isinstance(transition, artifacts.SourceRepairTransition)
        restore_transitions.append(transition)
        original_restore(*args, **kwargs)

    monkeypatch.setattr(artifacts, observer_name, fail_observer)
    monkeypatch.setattr(
        artifacts, "_restore_digest_bound_precommit_state", observed_restore
    )
    with pytest.raises(artifacts.CapacityHostArtifactError) as caught:
        artifacts.run_source_repair_host(**arguments)
    assert type(caught.value) is artifacts.CapacityHostArtifactError
    assert str(caught.value) == "SOURCE_REPAIR_PRESERVED_EVIDENCE_INVALID"
    assert private_marker not in str(caught.value)
    assert caught.value.__cause__ is injected
    assert fault_calls == 1
    assert restore_transitions == [
        artifacts.SOURCE_REPAIR_TRANSITIONS[
            (
                artifacts.SourceRepairMode.RECOVERY,
                artifacts.SourceRepairPhase.RECEIPT_DURABLE,
                artifacts.SourceRepairFailureLayout.NONE,
            )
        ]
    ]

    restored_position = artifacts.reconcile_source_repair(
        archive, expected_uid=expected_uid, expected_gid=expected_gid
    )
    assert restored_position.phase is artifacts.SourceRepairPhase.ROLLED_BACK
    assert (
        restored_position.failure_layout
        is artifacts.SourceRepairFailureLayout.INSTALLED_SOURCE
    )
    assert artifacts.closed_tree_digest(
        source_root, expected_uid=expected_uid, expected_gid=expected_gid
    ) == source_digest_before
    assert artifacts.closed_tree_digest(
        old_generation, expected_uid=expected_uid, expected_gid=expected_gid
    ) == generation_digest_before
    assert not (archive / "archived-source").exists()
    assert not (archive / "archived-generation").exists()


def test_before_final_rename_crash_preserves_candidate_and_replays_forward(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    system_root, transport, commit, _manifest = _repair_host_fixture(
        tmp_path, monkeypatch
    )
    arguments = _repair_arguments(system_root, transport, commit)
    generation_root = system_root / "capacity-generations"
    original_restore = artifacts._restore_digest_bound_precommit_state
    restore_calls = 0

    def observed_restore(*args: object, **kwargs: object) -> None:
        nonlocal restore_calls
        restore_calls += 1
        original_restore(*args, **kwargs)

    monkeypatch.setattr(
        artifacts, "_restore_digest_bound_precommit_state", observed_restore
    )
    with pytest.raises(
        artifacts.SourceRepairIncomplete, match="before_final_rename"
    ):
        artifacts.run_source_repair_host(
            **arguments, crash_at="before_final_rename"
        )

    archive = next((system_root / "capacity-archive").iterdir())
    assert restore_calls == 0
    assert not any(child.name.startswith("failure-") for child in archive.iterdir())
    assert (archive / "archived-source").is_dir()
    assert (archive / "archived-generation").is_dir()
    assert not (
        system_root / "capacity-sources" / "macro" / commit / "promisor-source"
    ).exists()
    assert not (generation_root / artifacts.PRIOR_GENERATION_DIGEST).exists()
    hidden_generations = list(generation_root.iterdir())
    assert len(hidden_generations) == 1
    assert hidden_generations[0].name.startswith(".candidate-")

    assert artifacts.run_source_repair_host(**arguments) == (
        "H0_SOURCE_CLOSURE_REPAIR_PASS_NOT_P0_ACCEPTED"
    )
    generations = list(generation_root.iterdir())
    assert len(generations) == 1
    assert not generations[0].name.startswith(".")
    assert artifacts.run_source_repair_host(
        **_verify_arguments(system_root, commit)
    ) == "H0_INSTALLED_HOST_PASS_NOT_P0_ACCEPTED"


@pytest.mark.parametrize(
    "add_visible_drift",
    (
        pytest.param(False, id="hidden-candidate"),
        pytest.param(True, id="hidden-candidate-plus-visible-child"),
    ),
)
def test_final_observer_failure_revokes_generation_parent_rollback_grant(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    add_visible_drift: bool,
) -> None:
    system_root, transport, commit, _manifest = _repair_host_fixture(
        tmp_path, monkeypatch
    )
    arguments = _repair_arguments(system_root, transport, commit)
    generation_root = system_root / "capacity-generations"
    with pytest.raises(
        artifacts.SourceRepairIncomplete, match="after_repair_receipt_fsync"
    ):
        artifacts.run_source_repair_host(
            **arguments, crash_at="after_repair_receipt_fsync"
        )

    archive = next((system_root / "capacity-archive").iterdir())
    injected = artifacts.CapacityHostArtifactError("INJECTED_FINAL_OBSERVER_FAILURE")
    visible_drift = generation_root / "non-prefix-visible-drift"
    restore_calls = 0
    original_restore = artifacts._restore_digest_bound_precommit_state
    original_observer = artifacts._observe_source_repair_source
    observer_calls = 0

    def fail_after_candidate(*args: object, **kwargs: object) -> object:
        nonlocal observer_calls
        observer_calls += 1
        if observer_calls == 1:
            return original_observer(*args, **kwargs)
        hidden_generations = [
            child
            for child in generation_root.iterdir()
            if child.name.startswith(".candidate-")
        ]
        assert len(hidden_generations) == 1
        if add_visible_drift:
            visible_drift.mkdir(mode=0o700)
        raise injected

    def observed_restore(*args: object, **kwargs: object) -> None:
        nonlocal restore_calls
        restore_calls += 1
        original_restore(*args, **kwargs)

    monkeypatch.setattr(
        artifacts, "_observe_source_repair_source", fail_after_candidate
    )
    monkeypatch.setattr(
        artifacts, "_restore_digest_bound_precommit_state", observed_restore
    )
    with pytest.raises(Exception) as raised:
        artifacts.run_source_repair_host(**arguments)

    assert observer_calls == 2
    assert restore_calls == 0
    assert not any(child.name.startswith("failure-") for child in archive.iterdir())
    assert (archive / "archived-source").is_dir()
    assert (archive / "archived-generation").is_dir()
    assert not (
        system_root / "capacity-sources" / "macro" / commit / "promisor-source"
    ).exists()
    assert visible_drift.is_dir() is add_visible_drift
    assert not (generation_root / artifacts.PRIOR_GENERATION_DIGEST).exists()
    hidden_generations = [
        child
        for child in generation_root.iterdir()
        if child.name.startswith(".candidate-")
    ]
    assert len(hidden_generations) == 1
    assert type(raised.value) is artifacts.SourceRepairIncomplete
    assert str(raised.value) == "POST_COMMIT_RECONCILIATION_REQUIRED"
    assert raised.value.__cause__ is injected


def test_postcommit_subprocess_timeout_requires_same_carrier_reconciliation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    system_root, transport, commit, _manifest = _repair_host_fixture(
        tmp_path, monkeypatch
    )
    arguments = _repair_arguments(system_root, transport, commit)
    assert artifacts.run_source_repair_host(**arguments) == (
        "H0_SOURCE_CLOSURE_REPAIR_PASS_NOT_P0_ACCEPTED"
    )

    def timed_out(*args: object, **kwargs: object) -> None:
        raise subprocess.TimeoutExpired(
            ["/bin/launchctl", "print-disabled", "system"], 5
        )

    monkeypatch.setattr(artifacts, "_verify_preserved_h0_invariants", timed_out)
    with pytest.raises(artifacts.SourceRepairIncomplete) as caught:
        artifacts.run_source_repair_host(**arguments)
    assert str(caught.value) == "POST_COMMIT_RECONCILIATION_REQUIRED"


def test_preserved_verifier_body_uses_only_supplied_retained_semantic_views(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    system_root = tmp_path / "system"
    generation = system_root / "capacity-generations" / ("a" * 64)
    archive = system_root / "capacity-archive" / "rollback-drill-fixture"
    labels = (
        "com.mastermind.executive.control",
        "com.mastermind.executive.worker.codex",
        "com.mastermind.executive.worker.codex-pro-01",
        "com.mastermind.executive.worker.codex-pro-02",
        "com.mastermind.executive.worker.codex-pro-03",
    )
    topology_payloads: dict[Path, bytes] = {}
    brokers: list[dict[str, object]] = []
    artifacts_rows: list[dict[str, str]] = []
    rollback_payloads: dict[str, bytes] = {}
    for index in range(9):
        path = tmp_path / f"topology-{index}.json"
        payload = f"topology-{index}\n".encode("ascii")
        topology_payloads[path] = payload
    for broker_index in range(3):
        offset = broker_index * 3
        brokers.append(
            {
                "config_path": str(tuple(topology_payloads)[offset]),
                "config_sha256": hashlib.sha256(
                    topology_payloads[tuple(topology_payloads)[offset]]
                ).hexdigest(),
                "attestation_path": str(tuple(topology_payloads)[offset + 1]),
                "attestation_sha256": hashlib.sha256(
                    topology_payloads[tuple(topology_payloads)[offset + 1]]
                ).hexdigest(),
                "plist_path": str(tuple(topology_payloads)[offset + 2]),
                "plist_sha256": hashlib.sha256(
                    topology_payloads[tuple(topology_payloads)[offset + 2]]
                ).hexdigest(),
            }
        )
    for index in range(9):
        name = f"artifact-{index}.json"
        payload = f"rollback-{index}\n".encode("ascii")
        rollback_payloads[name] = payload
        artifacts_rows.append(
            {"name": name, "sha256": hashlib.sha256(payload).hexdigest()}
        )
    legacy_paths = (
        system_root / "config" / "control.json",
        system_root / "config" / "worker-codex.json",
        Path("/Library/LaunchDaemons/com.mastermind.executive.control.plist"),
        Path("/Library/LaunchDaemons/com.mastermind.executive.worker.codex.plist"),
    )
    legacy_lines = [f"{path}=absent\n" for path in legacy_paths]
    legacy_lines.extend(
        f"{label}:disabled=true:loaded=false\n" for label in labels[:2]
    )
    topology = {
        "brokers": brokers,
        "legacy_phase1c_state_digest": hashlib.sha256(
            "".join(legacy_lines).encode("utf-8")
        ).hexdigest(),
    }
    drill = {
        "outcome": "SHRINK_ONLY_ROLLBACK_PASS",
        "moved_artifact_count": 9,
        "artifacts": artifacts_rows,
        "archive_root": str(archive),
    }
    drill_bytes = json.dumps(drill).encode("utf-8")
    rollback_payloads["rollback-receipt.json"] = drill_bytes
    generation_view = _FakePreservedView(
        {
            "broker-topology.json": json.dumps(topology).encode("utf-8"),
            "rollback-drill-receipt.json": drill_bytes,
        }
    )
    topology_views = {
        path: _FakePreservedView({".": payload})
        for path, payload in topology_payloads.items()
    }
    views = artifacts._PreservedH0Views(
        runtime=_FakePreservedView(),
        generation=generation_view,
        telemetry=_FakePreservedView(),
        release=_FakePreservedView(),
        rollback_archive=_FakePreservedView(rollback_payloads),
        topology=topology_views,
        legacy={path: None for path in legacy_paths},
        socket_parent=_FakePreservedView(absent=frozenset({"mastermind-executive"})),
        socket_directory=None,
    )
    observed_helpers: list[str] = []
    monkeypatch.setattr(
        artifacts,
        "_verify_runtime_view",
        lambda view: observed_helpers.append("runtime"),
        raising=False,
    )
    monkeypatch.setattr(
        artifacts,
        "_verify_telemetry_view",
        lambda view: observed_helpers.append("telemetry"),
        raising=False,
    )
    monkeypatch.setattr(
        artifacts,
        "_verify_preserved_service_principal_state",
        lambda received_labels: observed_helpers.append("services"),
        raising=False,
    )
    monkeypatch.setattr(
        artifacts,
        "_verify_inert_release_manifest",
        lambda *args, **kwargs: observed_helpers.append("release") or {},
    )

    def forbidden_path_reopen(*args: object, **kwargs: object) -> object:
        raise AssertionError((args, kwargs))

    monkeypatch.setattr(Path, "read_bytes", forbidden_path_reopen)
    monkeypatch.setattr(Path, "rglob", forbidden_path_reopen)
    monkeypatch.setattr(Path, "lstat", forbidden_path_reopen)
    monkeypatch.setattr(artifacts, "sha256_file", forbidden_path_reopen)
    monkeypatch.setattr(artifacts, "_path_lexists", forbidden_path_reopen)
    artifacts._verify_preserved_h0_invariants_body(
        system_root,
        generation,
        test_adapter=False,
        retained_views=views,
    )
    assert observed_helpers == ["runtime", "telemetry", "release", "services"]


def test_inert_release_manifest_verifier_never_executes_installed_payload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    release = tmp_path / contract.PRESERVED_TOPOLOGY_RELEASE_COMMIT
    script = release / "ops" / "executive_os" / "release_manifest.py"
    script.parent.mkdir(parents=True)
    script.write_bytes(b"# reviewed release verifier placeholder\n")
    script.chmod(0o444)
    for directory in (release, release / "ops", script.parent):
        directory.chmod(0o755)
    original = script.read_bytes()
    entries = [
        {
            "path": "ops",
            "mode": 0o755,
            "uid": os.getuid(),
            "gid": os.getgid(),
            "type": "directory",
        },
        {
            "path": "ops/executive_os",
            "mode": 0o755,
            "uid": os.getuid(),
            "gid": os.getgid(),
            "type": "directory",
        },
        {
            "path": "ops/executive_os/release_manifest.py",
            "mode": 0o444,
            "uid": os.getuid(),
            "gid": os.getgid(),
            "type": "file",
            "size": len(original),
            "sha256": hashlib.sha256(original).hexdigest(),
        },
    ]
    manifest = release / ".executive-release-manifest.json"
    manifest_bytes = (
        json.dumps(
            {
                "schema_version": "mastermind.executive_release_manifest/v1",
                "commit_sha": contract.PRESERVED_TOPOLOGY_RELEASE_COMMIT,
                "tree_sha": "f" * 40,
                "entries": entries,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        + b"\n"
    )
    manifest.write_bytes(manifest_bytes)
    manifest.chmod(0o444)
    monkeypatch.setattr(artifacts, "_TRUSTED_E4_RELEASE_TREE", "f" * 40)
    monkeypatch.setattr(
        artifacts,
        "_TRUSTED_E4_MANIFEST_SHA256",
        hashlib.sha256(manifest_bytes).hexdigest(),
    )
    monkeypatch.setattr(artifacts, "_TRUSTED_E4_MANIFEST_SIZE", len(manifest_bytes))
    monkeypatch.setattr(artifacts, "_TRUSTED_E4_MANIFEST_ENTRY_COUNT", len(entries))
    sentinel = tmp_path / "installed-code-executed"
    script.chmod(0o600)
    script.write_text(
        f"from pathlib import Path\nPath({str(sentinel)!r}).write_text('ran')\n",
        encoding="utf-8",
    )
    script.chmod(0o444)

    def subprocess_is_forbidden(*args: object, **kwargs: object) -> object:
        raise AssertionError("installed release code must never be launched")

    monkeypatch.setattr(artifacts.subprocess, "run", subprocess_is_forbidden)
    with pytest.raises(artifacts.CapacityHostArtifactError, match="RELEASE_INVALID"):
        artifacts._verify_inert_release_manifest(
            release,
            expected_commit=contract.PRESERVED_TOPOLOGY_RELEASE_COMMIT,
            expected_uid=os.getuid(),
            expected_gid=os.getgid(),
        )
    assert not sentinel.exists()


def test_privileged_git_environment_is_closed_to_ambient_execution_and_network() -> None:
    environment = artifacts._git_environment()
    assert environment == {
        "HOME": "/var/empty",
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        "LANG": "C",
        "LC_ALL": "C",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_LOCAL": "/dev/null",
        "GIT_ATTR_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_ASKPASS": "/usr/bin/false",
        "SSH_ASKPASS": "/usr/bin/false",
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_NO_LAZY_FETCH": "1",
        "GIT_NO_REPLACE_OBJECTS": "1",
        "GIT_EXTERNAL_DIFF": "/usr/bin/false",
        "GIT_ALLOW_PROTOCOL": "file",
        "GIT_CONFIG_COUNT": "6",
        "GIT_CONFIG_KEY_0": "core.hooksPath",
        "GIT_CONFIG_VALUE_0": "/dev/null",
        "GIT_CONFIG_KEY_1": "core.fsmonitor",
        "GIT_CONFIG_VALUE_1": "false",
        "GIT_CONFIG_KEY_2": "core.attributesFile",
        "GIT_CONFIG_VALUE_2": "/dev/null",
        "GIT_CONFIG_KEY_3": "protocol.allow",
        "GIT_CONFIG_VALUE_3": "never",
        "GIT_CONFIG_KEY_4": "protocol.file.allow",
        "GIT_CONFIG_VALUE_4": "always",
        "GIT_CONFIG_KEY_5": "diff.external",
        "GIT_CONFIG_VALUE_5": "/usr/bin/false",
    }


def test_hardened_git_does_not_execute_local_include_fsmonitor_diff_or_textconv(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    _git(repository, "init", "-q")
    _git(repository, "config", "user.name", "Fixture")
    _git(repository, "config", "user.email", "fixture@example.invalid")
    payload = repository / "payload.txt"
    payload.write_text("one\n", encoding="utf-8")
    (repository / ".gitattributes").write_text(
        "payload.txt diff=hostile\n", encoding="utf-8"
    )
    _git(repository, "add", ".")
    _git(repository, "commit", "-qm", "fixture")
    payload.write_text("two\n", encoding="utf-8")

    sentinel = tmp_path / "external-code-ran"
    hostile = tmp_path / "hostile.sh"
    hostile.write_text(
        f"#!/bin/sh\n/usr/bin/touch {str(sentinel)!r}\nexit 1\n",
        encoding="utf-8",
    )
    hostile.chmod(0o700)
    included = tmp_path / "included.config"
    included.write_text(
        f"[diff \"hostile\"]\n\texternal = {hostile}\n\ttextconv = {hostile}\n",
        encoding="utf-8",
    )
    _git(repository, "config", "core.fsmonitor", str(hostile))
    _git(repository, "config", "include.path", str(included))
    _git(repository, "config", "diff.hostile.external", str(hostile))
    _git(repository, "config", "diff.hostile.textconv", str(hostile))

    artifacts._run_git(repository, "status", "--porcelain=v1")
    artifacts._run_git(
        repository, "diff", "--no-ext-diff", "--no-textconv", "--", "payload.txt"
    )
    assert not sentinel.exists()


def test_root_created_carrier_is_immune_to_preopened_operator_write_descriptor(
    tmp_path: Path,
) -> None:
    repository, carrier, commit, payloads = _repair_carrier_git_fixture(tmp_path)
    operator_source = tmp_path / "operator-source"
    operator_source.write_bytes(payloads["ops/executive_os/repair-capacity-source-closure.sh"])
    writable_descriptor = os.open(operator_source, os.O_RDWR)
    try:
        os.lseek(writable_descriptor, 0, os.SEEK_SET)
        os.write(writable_descriptor, b"attacker mutation\n")
        os.ftruncate(writable_descriptor, len(b"attacker mutation\n"))
        assert artifacts.verify_repair_carrier(
            carrier,
            repository_root=repository / ".git",
            expected_commit=commit,
            expected_uid=os.getuid(),
            expected_gid=os.getgid(),
        )["commit_sha"] == commit
        assert (carrier / "ops/executive_os/repair-capacity-source-closure.sh").read_bytes() == (
            payloads["ops/executive_os/repair-capacity-source-closure.sh"]
        )
    finally:
        os.close(writable_descriptor)

    linked = tmp_path / "carrier-hardlink"
    os.link(carrier / "ops/executive_os/capacity_host_artifacts.py", linked)
    with pytest.raises(artifacts.CapacityHostArtifactError, match="REPAIR_CARRIER_INVALID"):
        artifacts.verify_repair_carrier(
            carrier,
            repository_root=repository / ".git",
            expected_commit=commit,
            expected_uid=os.getuid(),
            expected_gid=os.getgid(),
        )


def test_repair_carrier_refuses_one_byte_substitution_against_real_git_commit(
    tmp_path: Path,
) -> None:
    repository, carrier, commit, _payloads = _repair_carrier_git_fixture(tmp_path)
    victim = carrier / "ops/executive_os/capacity_source_contract.py"
    victim.chmod(0o600)
    payload = bytearray(victim.read_bytes())
    payload[-2] ^= 1
    victim.write_bytes(payload)
    victim.chmod(0o400)

    with pytest.raises(artifacts.CapacityHostArtifactError, match="REPAIR_CARRIER_INVALID"):
        artifacts.verify_repair_carrier(
            carrier,
            repository_root=repository / ".git",
            expected_commit=commit,
            expected_uid=os.getuid(),
            expected_gid=os.getgid(),
        )


def test_repair_carrier_uses_retained_repository_after_basename_swap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository, carrier, commit, _payloads = _repair_carrier_git_fixture(tmp_path)
    repository_root = repository / ".git"
    retained_repository = repository / ".git-retained"
    original_run = subprocess.run
    swapped = False

    def swap_before_first_git(*args: object, **kwargs: object) -> subprocess.CompletedProcess:
        nonlocal swapped
        command = args[0]
        if (
            not swapped
            and isinstance(command, list)
            and command
            and command[0] == "/usr/bin/git"
        ):
            repository_root.rename(retained_repository)
            repository_root.mkdir(mode=0o700)
            swapped = True
        return original_run(*args, **kwargs)

    monkeypatch.setattr(artifacts.subprocess, "run", swap_before_first_git)

    assert artifacts.verify_repair_carrier(
        carrier,
        repository_root=repository_root,
        expected_commit=commit,
        expected_uid=os.getuid(),
        expected_gid=os.getgid(),
    )["commit_sha"] == commit
    assert swapped is True

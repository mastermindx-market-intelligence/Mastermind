"""Capacity host source admission cases; shared helpers retain their original owner."""
from __future__ import annotations

from tests.test_capacity_host_artifacts import (
    Path,
    _StatOverlay,
    _ancestor_overlay_changes,
    _overlay_stable_ancestor_flags,
    _repair_arguments,
    _repair_host_fixture,
    _source_repair_intent_fields,
    artifacts,
    contract,
    hashlib,
    os,
    pwd,
    pytest,
    stat,
    subprocess,
    sys,
)


def test_source_repair_intent_builder_owns_fixed_fields_and_identity() -> None:
    intent = artifacts.build_source_repair_intent(**_source_repair_intent_fields())
    assert contract.validate_source_repair_intent(intent) == intent
    identity = dict(intent)
    intent_id = identity.pop("intent_id")
    assert intent_id == hashlib.sha256(artifacts.canonical_json(identity)).hexdigest()


def test_source_repair_intent_publication_is_canonical_lf_and_idempotent(
    tmp_path: Path,
) -> None:
    intent = artifacts.build_source_repair_intent(
        **_source_repair_intent_fields(filesystem_device=tmp_path.stat().st_dev)
    )
    archive = tmp_path / f"source-closure-repair-{intent['intent_id']}"
    archive.mkdir(mode=0o700)
    observed = artifacts.publish_source_repair_intent(
        archive,
        intent,
        expected_uid=os.getuid(),
        expected_gid=os.getgid(),
    )
    payload = artifacts.canonical_json(intent) + b"\n"
    assert observed == hashlib.sha256(payload).hexdigest()
    assert (archive / "source-repair-intent.json").read_bytes() == payload
    assert artifacts.publish_source_repair_intent(
        archive,
        intent,
        expected_uid=os.getuid(),
        expected_gid=os.getgid(),
    ) == observed


def test_source_repair_intent_publication_refuses_prefix_or_changed_same_id(
    tmp_path: Path,
) -> None:
    intent = artifacts.build_source_repair_intent(
        **_source_repair_intent_fields(filesystem_device=tmp_path.stat().st_dev)
    )
    archive = tmp_path / f"source-closure-repair-{intent['intent_id']}"
    archive.mkdir(mode=0o700)
    candidate = archive / ".source-repair-intent.json.candidate"
    candidate.write_bytes(b"attacker-prefix")
    candidate.chmod(0o400)
    with pytest.raises(artifacts.CapacityHostArtifactError):
        artifacts.publish_source_repair_intent(
            archive,
            intent,
            expected_uid=os.getuid(),
            expected_gid=os.getgid(),
        )

    candidate.unlink()
    artifacts.publish_source_repair_intent(
        archive,
        intent,
        expected_uid=os.getuid(),
        expected_gid=os.getgid(),
    )
    changed = dict(intent)
    changed["candidate_transport_sha256"] = "6" * 64
    with pytest.raises(artifacts.CapacityHostArtifactError):
        artifacts.publish_source_repair_intent(
            archive,
            changed,
            expected_uid=os.getuid(),
            expected_gid=os.getgid(),
        )


def test_source_repair_publication_refuses_device_mismatch(tmp_path: Path) -> None:
    intent = artifacts.build_source_repair_intent(
        **_source_repair_intent_fields(
            filesystem_device=tmp_path.stat().st_dev + 1
        )
    )
    archive = tmp_path / f"source-closure-repair-{intent['intent_id']}"
    archive.mkdir(mode=0o700)

    with pytest.raises(
        artifacts.CapacityHostArtifactError,
        match="SOURCE_REPAIR_DEVICE_MISMATCH",
    ):
        artifacts.publish_source_repair_intent(
            archive,
            intent,
            expected_uid=os.getuid(),
            expected_gid=os.getgid(),
        )
    assert list(archive.iterdir()) == []


def test_source_repair_move_refuses_existing_destination_without_fallback(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    source.mkdir()
    destination.mkdir()
    (source / "source-evidence").write_bytes(b"source\n")
    (destination / "destination-evidence").write_bytes(b"destination\n")

    with pytest.raises(
        artifacts.CapacityHostArtifactError,
        match="SOURCE_REPAIR_DESTINATION_EXISTS",
    ):
        artifacts._move_source_repair_tree(source, destination)
    assert (source / "source-evidence").read_bytes() == b"source\n"
    assert (destination / "destination-evidence").read_bytes() == b"destination\n"


@pytest.mark.parametrize(
    "reason",
    ("SOURCE_REPAIR_DEVICE_MISMATCH", "NO_REPLACE_RENAME_UNAVAILABLE"),
)
def test_source_repair_move_has_no_exdev_or_unavailable_rename_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, reason: str
) -> None:
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    source.mkdir()
    (source / "evidence").write_bytes(b"preserved\n")

    def refuse_rename(*_arguments: object) -> None:
        raise artifacts.CapacityHostArtifactError(reason)

    monkeypatch.setattr(artifacts, "_rename_exclusive", refuse_rename)
    with pytest.raises(artifacts.CapacityHostArtifactError, match=reason):
        artifacts._move_source_repair_tree(source, destination)
    assert (source / "evidence").read_bytes() == b"preserved\n"
    assert not destination.exists()


def test_source_repair_reconcile_refuses_wrong_gid_extra_member_and_two_intents(
    tmp_path: Path,
) -> None:
    intent = artifacts.build_source_repair_intent(
        **_source_repair_intent_fields(filesystem_device=tmp_path.stat().st_dev)
    )
    archive = tmp_path / f"source-closure-repair-{intent['intent_id']}"
    archive.mkdir(mode=0o700)
    artifacts.publish_source_repair_intent(
        archive,
        intent,
        expected_uid=os.getuid(),
        expected_gid=os.getgid(),
    )
    position = artifacts.reconcile_source_repair(
        archive,
        expected_uid=os.getuid(),
        expected_gid=os.getgid(),
    )
    assert position.intent_id == intent["intent_id"]
    assert position.archived_source is False
    assert position.archived_generation is False
    assert position.receipt_digest is None

    with pytest.raises(artifacts.CapacityHostArtifactError):
        artifacts.reconcile_source_repair(
            archive,
            expected_uid=os.getuid(),
            expected_gid=os.getgid() + 1,
        )
    (archive / "extra").write_bytes(b"unexpected")
    with pytest.raises(artifacts.CapacityHostArtifactError):
        artifacts.reconcile_source_repair(
            archive,
            expected_uid=os.getuid(),
            expected_gid=os.getgid(),
        )
    (archive / "extra").unlink()
    (archive / "second-source-repair-intent.json").write_bytes(
        (archive / "source-repair-intent.json").read_bytes()
    )
    with pytest.raises(artifacts.CapacityHostArtifactError):
        artifacts.reconcile_source_repair(
            archive,
            expected_uid=os.getuid(),
            expected_gid=os.getgid(),
        )


def test_source_repair_threads_exact_v3_capacity_bound_to_closed_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    system_root, transport, commit, _manifest = _repair_host_fixture(
        tmp_path, monkeypatch
    )

    class Observed(Exception):
        pass

    def observe_copy(
        source: Path,
        destination: Path,
        *,
        operator_uid: int,
        expected_sha256: str,
        maximum_bytes: int,
        minimum_free_multiplier: int,
        minimum_free_reserve_bytes: int,
    ) -> dict[str, object]:
        assert source == transport
        assert destination.parent == system_root / "capacity-staging"
        assert operator_uid == os.getuid()
        assert expected_sha256 == hashlib.sha256(transport.read_bytes()).hexdigest()
        assert maximum_bytes == artifacts._V3_TRANSPORT_MAX_BYTES
        assert minimum_free_multiplier == artifacts._V3_REPAIR_SPACE_MULTIPLIER
        assert (
            minimum_free_reserve_bytes
            == artifacts._V3_REPAIR_SPACE_RESERVE_BYTES
        )
        raise Observed

    monkeypatch.setattr(artifacts, "copy_closed_input", observe_copy)
    with pytest.raises(Observed):
        artifacts.run_source_repair_host(
            **_repair_arguments(system_root, transport, commit)
        )


@pytest.mark.parametrize(
    "drift",
    (
        "intermediate-symlink",
        "parent-mode",
        "parent-xattr",
        "parent-acl",
        "parent-flags",
    ),
)
def test_source_repair_parent_graph_refuses_untrusted_intermediate_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    drift: str,
) -> None:
    system_root, _transport, _commit, _manifest = _repair_host_fixture(
        tmp_path, monkeypatch
    )
    capacity_sources = system_root / "capacity-sources"
    cleanup_xattr: tuple[Path, bytes] | None = None
    cleanup_acl = False
    cleanup_flags = False
    if drift == "intermediate-symlink":
        moved = system_root / "real-capacity-sources"
        capacity_sources.rename(moved)
        capacity_sources.symlink_to(moved, target_is_directory=True)
    elif drift == "parent-mode":
        capacity_sources.chmod(0o755)
    elif drift == "parent-xattr":
        name = b"com.mastermind.test" if sys.platform == "darwin" else b"user.mastermind-test"
        try:
            if sys.platform == "darwin":
                subprocess.run(
                    ["/usr/bin/xattr", "-w", name.decode(), "unsafe", capacity_sources],
                    check=True,
                    capture_output=True,
                )
            else:
                os.setxattr(capacity_sources, name, b"unsafe", follow_symlinks=False)
        except (AttributeError, OSError, subprocess.CalledProcessError):
            pytest.skip("extended attribute fixture is unavailable")
        cleanup_xattr = (capacity_sources, name)
    elif drift == "parent-acl":
        if sys.platform != "darwin":
            pytest.skip("macOS ACL fixture is unavailable")
        subprocess.run(
            [
                "/bin/chmod",
                "+a",
                f"{pwd.getpwuid(os.getuid()).pw_name} allow read",
                capacity_sources,
            ],
            check=True,
            capture_output=True,
        )
        cleanup_acl = True
    else:
        if sys.platform != "darwin" or not hasattr(os, "chflags"):
            pytest.skip("macOS BSD flags fixture is unavailable")
        os.chflags(capacity_sources, stat.UF_NODUMP)
        cleanup_flags = True
    try:
        with pytest.raises(
            (artifacts.CapacityHostArtifactError, OSError),
            match="SOURCE_REPAIR_(PARENT|ROOT)|Too many levels|Not a directory",
        ):
            artifacts._open_source_repair_parents(
                system_root, expected_uid=os.getuid(), expected_gid=os.getgid()
            )
    finally:
        if cleanup_xattr is not None:
            if sys.platform == "darwin":
                subprocess.run(
                    [
                        "/usr/bin/xattr",
                        "-d",
                        cleanup_xattr[1].decode(),
                        cleanup_xattr[0],
                    ],
                    check=True,
                    capture_output=True,
                )
            else:
                os.removexattr(*cleanup_xattr, follow_symlinks=False)
        if cleanup_acl:
            subprocess.run(["/bin/chmod", "-N", capacity_sources], check=True)
        if cleanup_flags:
            os.chflags(capacity_sources, 0)


def test_source_repair_parent_graph_detects_synchronized_system_root_swap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    system_root, _transport, _commit, _manifest = _repair_host_fixture(
        tmp_path, monkeypatch
    )
    parents = artifacts._open_source_repair_parents(
        system_root, expected_uid=os.getuid(), expected_gid=os.getgid()
    )
    retained = system_root.with_name("retained-host")
    try:
        system_root.rename(retained)
        system_root.mkdir(mode=0o755)
        with pytest.raises(artifacts.CapacityHostArtifactError, match="PARENT_DRIFT"):
            parents.revalidate()
    finally:
        parents.close()


@pytest.mark.skipif(
    not hasattr(stat, "UF_NODUMP"), reason="BSD user flag constant is unavailable"
)
def test_source_repair_traversal_ancestor_refuses_stable_user_flag_at_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    system_root, _transport, _commit, _manifest = _repair_host_fixture(
        tmp_path, monkeypatch
    )
    _overlay_stable_ancestor_flags(monkeypatch, tmp_path, stat.UF_NODUMP)
    parents: artifacts.SourceRepairParents | None = None
    try:
        with pytest.raises(
            artifacts.CapacityHostArtifactError,
            match="SOURCE_REPAIR_PARENT_INVALID",
        ):
            parents = artifacts._open_source_repair_parents(
                system_root,
                expected_uid=os.getuid(),
                expected_gid=os.getgid(),
            )
    finally:
        if parents is not None:
            parents.close()


@pytest.mark.skipif(
    sys.platform != "darwin", reason="observed platform flags are macOS-specific"
)
@pytest.mark.parametrize(
    "platform_flags",
    (
        pytest.param(
            getattr(stat, "SF_NOUNLINK", 0x00100000),
            id="root-var-folders-library",
        ),
        pytest.param(
            getattr(stat, "SF_RESTRICTED", 0x00080000)
            | getattr(stat, "UF_HIDDEN", 0x00008000),
            id="var",
        ),
        pytest.param(
            getattr(stat, "SF_NOUNLINK", 0x00100000)
            | getattr(stat, "UF_HIDDEN", 0x00008000),
            id="private",
        ),
    ),
)
def test_source_repair_traversal_ancestor_accepts_observed_platform_flags(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    platform_flags: int,
) -> None:
    system_root, _transport, _commit, _manifest = _repair_host_fixture(
        tmp_path, monkeypatch
    )
    _overlay_stable_ancestor_flags(monkeypatch, tmp_path, platform_flags)
    parents = artifacts._open_source_repair_parents(
        system_root, expected_uid=os.getuid(), expected_gid=os.getgid()
    )
    try:
        parents.revalidate()
    finally:
        parents.close()


@pytest.mark.parametrize(
    ("phase", "drift"),
    (
        *(("open", drift) for drift in ("uid", "gid", "mode", "device", "link-count", "acl", "xattr")),
        *(("revalidation", drift) for drift in ("flags", "uid", "gid", "mode", "device", "link-count", "acl", "xattr")),
    ),
)
def test_source_repair_true_traversal_ancestor_obeys_complete_security_law(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    phase: str,
    drift: str,
) -> None:
    system_root, _transport, _commit, _manifest = _repair_host_fixture(
        tmp_path, monkeypatch
    )
    ancestor_info = tmp_path.stat()
    ancestor_identity = (ancestor_info.st_dev, ancestor_info.st_ino)
    parents: artifacts.SourceRepairParents | None = None
    if phase == "revalidation":
        parents = artifacts._open_source_repair_parents(
            system_root, expected_uid=os.getuid(), expected_gid=os.getgid()
        )
    original_fstat = os.fstat
    original_stat = os.stat
    original_xattrs = artifacts._descriptor_extended_attribute_names
    original_acl = artifacts._descriptor_has_extended_acl

    def is_ancestor(info: os.stat_result) -> bool:
        return (info.st_dev, info.st_ino) == ancestor_identity

    def overlay(info: os.stat_result) -> os.stat_result | _StatOverlay:
        changes = _ancestor_overlay_changes(drift, info)
        return _StatOverlay(info, **changes) if changes and is_ancestor(info) else info

    def stable_fstat(descriptor: int) -> os.stat_result | _StatOverlay:
        return overlay(original_fstat(descriptor))

    def stable_stat(*args: object, **kwargs: object) -> os.stat_result | _StatOverlay:
        return overlay(original_stat(*args, **kwargs))

    def ancestor_xattrs(descriptor: int) -> frozenset[bytes]:
        observed = original_xattrs(descriptor)
        if drift == "xattr" and is_ancestor(original_fstat(descriptor)):
            return observed | frozenset({b"com.mastermind.test"})
        return observed

    def ancestor_acl(descriptor: int) -> bool:
        if drift == "acl" and is_ancestor(original_fstat(descriptor)):
            return True
        return original_acl(descriptor)

    monkeypatch.setattr(os, "fstat", stable_fstat)
    monkeypatch.setattr(os, "stat", stable_stat)
    monkeypatch.setattr(
        artifacts, "_descriptor_extended_attribute_names", ancestor_xattrs
    )
    monkeypatch.setattr(artifacts, "_descriptor_has_extended_acl", ancestor_acl)
    try:
        with pytest.raises(
            artifacts.CapacityHostArtifactError,
            match="SOURCE_REPAIR_PARENT_(INVALID|DRIFT)",
        ):
            if phase == "open":
                parents = artifacts._open_source_repair_parents(
                    system_root,
                    expected_uid=os.getuid(),
                    expected_gid=os.getgid(),
                )
            else:
                assert parents is not None
                parents.revalidate()
    finally:
        if parents is not None:
            parents.close()


def test_source_repair_traversal_ancestor_tolerates_positive_link_count_churn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    system_root, _transport, _commit, _manifest = _repair_host_fixture(
        tmp_path, monkeypatch
    )
    ancestor_info = tmp_path.stat()
    ancestor_identity = (ancestor_info.st_dev, ancestor_info.st_ino)
    parents = artifacts._open_source_repair_parents(
        system_root, expected_uid=os.getuid(), expected_gid=os.getgid()
    )
    original_fstat = os.fstat
    original_stat = os.stat

    def overlay(info: os.stat_result) -> os.stat_result | _StatOverlay:
        if (info.st_dev, info.st_ino) == ancestor_identity:
            return _StatOverlay(info, st_nlink=info.st_nlink + 1)
        return info

    monkeypatch.setattr(os, "fstat", lambda descriptor: overlay(original_fstat(descriptor)))
    monkeypatch.setattr(
        os, "stat", lambda *args, **kwargs: overlay(original_stat(*args, **kwargs))
    )
    try:
        parents.revalidate()
    finally:
        parents.close()


def test_source_repair_fixed_system_root_freezes_exact_link_count(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    system_root, _transport, _commit, _manifest = _repair_host_fixture(
        tmp_path, monkeypatch
    )
    root_info = system_root.stat()
    root_identity = (root_info.st_dev, root_info.st_ino)
    parents = artifacts._open_source_repair_parents(
        system_root, expected_uid=os.getuid(), expected_gid=os.getgid()
    )
    original_fstat = os.fstat
    original_stat = os.stat

    def overlay(info: os.stat_result) -> os.stat_result | _StatOverlay:
        if (info.st_dev, info.st_ino) == root_identity:
            return _StatOverlay(info, st_nlink=info.st_nlink + 1)
        return info

    monkeypatch.setattr(os, "fstat", lambda descriptor: overlay(original_fstat(descriptor)))
    monkeypatch.setattr(
        os, "stat", lambda *args, **kwargs: overlay(original_stat(*args, **kwargs))
    )
    try:
        with pytest.raises(
            artifacts.CapacityHostArtifactError, match="SOURCE_REPAIR_PARENT_DRIFT"
        ):
            parents.revalidate()
    finally:
        parents.close()


def test_source_repair_fixed_parent_freezes_exact_approved_xattr_name_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    system_root, _transport, _commit, _manifest = _repair_host_fixture(
        tmp_path, monkeypatch
    )
    parents = artifacts._open_source_repair_parents(
        system_root, expected_uid=os.getuid(), expected_gid=os.getgid()
    )
    target = parents.generation
    initial = dict(parents.security_xattr_states)[target]
    changed = (
        frozenset()
        if initial
        else frozenset({b"com.apple.provenance"})
    )
    original = artifacts._descriptor_extended_attribute_names

    def observed(descriptor: int) -> frozenset[bytes]:
        return changed if descriptor == target else original(descriptor)

    monkeypatch.setattr(artifacts, "_descriptor_extended_attribute_names", observed)
    try:
        with pytest.raises(
            artifacts.CapacityHostArtifactError, match="SOURCE_REPAIR_PARENT_DRIFT"
        ):
            parents.revalidate()
    finally:
        parents.close()

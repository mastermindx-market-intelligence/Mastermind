"""Capacity host retained views cases; shared helpers retain their original owner."""
from __future__ import annotations

from tests.test_capacity_host_artifacts import (
    Path,
    _StatOverlay,
    _canonical_e4_manifest_from_git_objects,
    _open_fd_inventory,
    _overlay_fixture_identity_as_root,
    _overlay_fixture_metadata,
    _producer_topology_rows,
    _repair_arguments,
    _repair_host_fixture,
    _repository_role_directory_policy,
    _write_inert_release_fixture,
    _write_metadata_fixture,
    artifacts,
    errno,
    hashlib,
    json,
    os,
    pytest,
    resource,
    stat,
    subprocess,
    sys,
    tempfile,
    yaml,
)


def test_primary_ci_checkout_retains_full_history_for_trusted_release_identity() -> None:
    workflow = yaml.safe_load(
        (Path(__file__).resolve().parents[1] / ".github/workflows/ci.yml").read_text(
            encoding="utf-8"
        )
    )
    # Trusted history is consumed by the actual pytest workers; the fan-in
    # `test` status job validates the matrix result and canonical coverage.
    steps = workflow["jobs"]["pytest_shards"]["steps"]
    primary = next(
        step
        for step in steps
        if isinstance(step, dict)
        and step.get("name") == "Checkout event source"
        and step.get("uses") == "actions/checkout@v4"
        and "repository" not in step.get("with", {})
    )
    assert steps.index(primary) == 1
    assert primary.get("with", {}).get("fetch-depth") == 0


def test_trusted_e4_release_manifest_identity_is_derived_from_git_objects() -> None:
    tree, manifest_bytes, entry_count = _canonical_e4_manifest_from_git_objects()
    assert tree == artifacts._TRUSTED_E4_RELEASE_TREE
    assert len(manifest_bytes) == artifacts._TRUSTED_E4_MANIFEST_SIZE
    assert entry_count == artifacts._TRUSTED_E4_MANIFEST_ENTRY_COUNT
    assert (
        hashlib.sha256(manifest_bytes).hexdigest()
        == artifacts._TRUSTED_E4_MANIFEST_SHA256
    )


def test_inert_release_refuses_self_authored_payload_and_matching_manifest_under_e4_basename(
    tmp_path: Path,
) -> None:
    release = tmp_path / artifacts.PRESERVED_TOPOLOGY_RELEASE_COMMIT
    _write_inert_release_fixture(
        release,
        tree_sha="ee1b95af3341a49151890cec1a6a31997f632aec",
    )
    with pytest.raises(artifacts.CapacityHostArtifactError, match="RELEASE_INVALID"):
        artifacts._verify_inert_release_manifest(
            release,
            expected_commit=artifacts.PRESERVED_TOPOLOGY_RELEASE_COMMIT,
            expected_uid=os.getuid(),
            expected_gid=os.getgid(),
        )


def test_inert_release_refuses_valid_manifest_shape_with_wrong_trusted_e4_tree(
    tmp_path: Path,
) -> None:
    release = tmp_path / artifacts.PRESERVED_TOPOLOGY_RELEASE_COMMIT
    _write_inert_release_fixture(release, tree_sha="f" * 40)
    with pytest.raises(artifacts.CapacityHostArtifactError, match="RELEASE_INVALID"):
        artifacts._verify_inert_release_manifest(
            release,
            expected_commit=artifacts.PRESERVED_TOPOLOGY_RELEASE_COMMIT,
            expected_uid=os.getuid(),
            expected_gid=os.getgid(),
        )


def test_inert_release_revalidates_basename_relation_after_root_is_retained(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    release = tmp_path / artifacts.PRESERVED_TOPOLOGY_RELEASE_COMMIT
    manifest_bytes = _write_inert_release_fixture(release, tree_sha="a" * 40)
    monkeypatch.setattr(artifacts, "_TRUSTED_E4_RELEASE_TREE", "a" * 40, raising=False)
    monkeypatch.setattr(
        artifacts,
        "_TRUSTED_E4_MANIFEST_SHA256",
        hashlib.sha256(manifest_bytes).hexdigest(),
        raising=False,
    )
    monkeypatch.setattr(
        artifacts, "_TRUSTED_E4_MANIFEST_SIZE", len(manifest_bytes), raising=False
    )
    monkeypatch.setattr(
        artifacts, "_TRUSTED_E4_MANIFEST_ENTRY_COUNT", 1, raising=False
    )
    replacement = tmp_path / "replacement"
    replacement.mkdir(mode=0o755)
    replacement.chmod(0o755)
    displaced = tmp_path / "displaced-release"
    manifest_inode = (release / ".executive-release-manifest.json").stat().st_ino
    root_before = release.stat()
    root_inode = root_before.st_ino
    original_read = artifacts._read_descriptor
    original_fstat = os.fstat
    swapped = False

    def swap_release_basename(descriptor: int, maximum_bytes: int) -> bytes:
        nonlocal swapped
        if not swapped and os.fstat(descriptor).st_ino == manifest_inode:
            release.rename(displaced)
            replacement.rename(release)
            swapped = True
        return original_read(descriptor, maximum_bytes)

    monkeypatch.setattr(artifacts, "_read_descriptor", swap_release_basename)
    monkeypatch.setattr(
        os,
        "fstat",
        lambda descriptor: (
            _StatOverlay(
                original_fstat(descriptor),
                st_ctime_ns=root_before.st_ctime_ns,
            )
            if swapped and original_fstat(descriptor).st_ino == root_inode
            else original_fstat(descriptor)
        ),
    )
    with pytest.raises(artifacts.CapacityHostArtifactError, match="RELEASE_INVALID"):
        artifacts._verify_inert_release_manifest(
            release,
            expected_commit=artifacts.PRESERVED_TOPOLOGY_RELEASE_COMMIT,
            expected_uid=os.getuid(),
            expected_gid=os.getgid(),
        )
    assert swapped


def test_inert_release_refuses_unrelated_retained_view_injection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    expected_parent = tmp_path / "expected-parent"
    injected_parent = tmp_path / "injected-parent"
    expected_parent.mkdir(mode=0o755)
    injected_parent.mkdir(mode=0o755)
    expected_release = expected_parent / artifacts.PRESERVED_TOPOLOGY_RELEASE_COMMIT
    injected_release = injected_parent / artifacts.PRESERVED_TOPOLOGY_RELEASE_COMMIT
    manifest_bytes = _write_inert_release_fixture(expected_release, tree_sha="a" * 40)
    _write_inert_release_fixture(injected_release, tree_sha="a" * 40)
    monkeypatch.setattr(artifacts, "_TRUSTED_E4_RELEASE_TREE", "a" * 40)
    monkeypatch.setattr(
        artifacts,
        "_TRUSTED_E4_MANIFEST_SHA256",
        hashlib.sha256(manifest_bytes).hexdigest(),
    )
    monkeypatch.setattr(artifacts, "_TRUSTED_E4_MANIFEST_SIZE", len(manifest_bytes))
    monkeypatch.setattr(artifacts, "_TRUSTED_E4_MANIFEST_ENTRY_COUNT", 1)
    expected_parent_descriptor = os.open(
        expected_parent,
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
    )
    injected_view = artifacts._RepositoryView(
        injected_release,
        allow_symlinks=True,
    )
    try:
        with pytest.raises(artifacts.CapacityHostArtifactError, match="RELEASE_INVALID"):
            artifacts._verify_inert_release_manifest(
                expected_release,
                expected_commit=artifacts.PRESERVED_TOPOLOGY_RELEASE_COMMIT,
                expected_uid=os.getuid(),
                expected_gid=os.getgid(),
                parent_descriptor=expected_parent_descriptor,
                retained_view=injected_view,
            )
    finally:
        injected_view.close()
        os.close(expected_parent_descriptor)


def test_retained_semantic_read_refuses_approved_xattr_name_set_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "xattr-state"
    root.mkdir(mode=0o755)
    evidence = root / "evidence.json"
    evidence.write_bytes(b"{}\n")
    evidence.chmod(0o444)
    view = artifacts._RepositoryView(root)
    target = view.descriptors["evidence.json"]
    initial_names = view.xattr_states["evidence.json"]
    drifted_names = (
        frozenset()
        if initial_names
        else frozenset({b"com.apple.provenance"})
    )
    original_names = artifacts._descriptor_extended_attribute_names
    original_read = artifacts._read_descriptor
    drifted = False

    def observed_names(descriptor: int) -> frozenset[bytes]:
        if drifted and descriptor == target:
            return drifted_names
        return original_names(descriptor)

    def drift_after_read(descriptor: int, maximum_bytes: int) -> bytes:
        nonlocal drifted
        payload = original_read(descriptor, maximum_bytes)
        if descriptor == target:
            drifted = True
        return payload

    monkeypatch.setattr(artifacts, "_descriptor_extended_attribute_names", observed_names)
    monkeypatch.setattr(artifacts, "_read_descriptor", drift_after_read)
    try:
        with pytest.raises(artifacts.CapacityHostArtifactError, match="SOURCE_VIEW_DRIFT"):
            view.read_bytes("evidence.json", maximum_bytes=1024)
    finally:
        view.close()


def test_retained_parent_proves_optional_absence_without_path_reopen(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    parent = tmp_path / "optional-parent"
    parent.mkdir(mode=0o755)
    view = artifacts._RepositoryView(parent, recursive=False)

    def forbid_lexists(*args: object, **kwargs: object) -> bool:
        raise AssertionError((args, kwargs))

    monkeypatch.setattr(artifacts, "_path_lexists", forbid_lexists)
    try:
        assert view.is_absent("optional-evidence.json")
        view.revalidate()
    finally:
        view.close()


def test_absolute_view_refuses_forbidden_stable_ancestor_flags(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    evidence = tmp_path / "ancestor-policy.json"
    evidence.write_bytes(b"evidence\n")
    evidence.chmod(0o444)
    ancestor = tmp_path.parent.stat()
    ancestor_identity = (ancestor.st_dev, ancestor.st_ino)
    original_fstat = os.fstat
    original_stat = os.stat

    def overlay(info: os.stat_result) -> os.stat_result | _StatOverlay:
        if (info.st_dev, info.st_ino) == ancestor_identity:
            return _StatOverlay(info, st_flags=1)
        return info

    monkeypatch.setattr(os, "fstat", lambda descriptor: overlay(original_fstat(descriptor)))
    monkeypatch.setattr(
        os,
        "stat",
        lambda *args, **kwargs: overlay(original_stat(*args, **kwargs)),
    )
    with pytest.raises(artifacts.CapacityHostArtifactError, match="SOURCE_METADATA_INVALID"):
        artifacts._RepositoryView(evidence)


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS fixed root aliases")
@pytest.mark.parametrize("alias", (Path("/var"), Path("/tmp")))
def test_absolute_view_authenticates_fixed_macos_root_alias_component(
    alias: Path,
) -> None:
    if alias == Path("/tmp"):
        with tempfile.TemporaryDirectory(prefix="mmx-retained-", dir="/tmp") as root:
            os.chown(root, os.getuid(), os.getgid())
            evidence = Path(root) / "evidence.json"
            evidence.write_bytes(b"evidence\n")
            evidence.chmod(0o444)
            view = artifacts._RepositoryView(evidence)
            try:
                assert view.read_bytes(".", maximum_bytes=1024) == b"evidence\n"
            finally:
                view.close()
    else:
        view = artifacts._RepositoryView(alias, recursive=False)
        try:
            assert stat.S_ISDIR(os.fstat(view.root_descriptor).st_mode)
            view.revalidate()
        finally:
            view.close()


@pytest.mark.parametrize(
    "violation",
    (
        "type",
        "owner",
        "group",
        "mode",
        "device",
        "link",
        "acl",
        "xattr",
        "flags",
    ),
)
def test_linux_tmp_traversal_root_requires_exact_security_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    violation: str,
) -> None:
    descriptor = os.open(
        tmp_path,
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
    )
    original = os.fstat(descriptor)
    changes = {
        "st_mode": stat.S_IFDIR | 0o1777,
        "st_uid": 0,
        "st_gid": 0,
        "st_dev": original.st_dev,
        "st_nlink": max(original.st_nlink, 1),
        "st_flags": 0,
    }
    if violation == "type":
        changes["st_mode"] = stat.S_IFREG | 0o1777
    elif violation == "owner":
        changes["st_uid"] = 10000
    elif violation == "group":
        changes["st_gid"] = 10000
    elif violation == "mode":
        changes["st_mode"] = stat.S_IFDIR | 0o0777
    elif violation == "device":
        changes["st_dev"] = original.st_dev + 1
    elif violation == "link":
        changes["st_nlink"] = 0
    elif violation == "flags":
        changes["st_flags"] = 1
    monkeypatch.setattr(
        artifacts,
        "_descriptor_extended_attribute_names",
        lambda _descriptor: (
            frozenset({b"user.mastermind-test"})
            if violation == "xattr"
            else frozenset()
        ),
    )
    monkeypatch.setattr(
        artifacts,
        "_descriptor_has_extended_acl",
        lambda _descriptor: violation == "acl",
    )
    try:
        with pytest.raises(
            artifacts.CapacityHostArtifactError,
            match="SOURCE_METADATA_INVALID",
        ):
            artifacts._require_linux_tmp_traversal_root(
                descriptor,
                _StatOverlay(original, **changes),
                expected_device=original.st_dev,
                reason="SOURCE_METADATA_INVALID",
            )
    finally:
        os.close(descriptor)


def test_linux_tmp_traversal_root_accepts_only_empty_security_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    descriptor = os.open(
        tmp_path,
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
    )
    original = os.fstat(descriptor)
    trusted = _StatOverlay(
        original,
        st_mode=stat.S_IFDIR | 0o1777,
        st_uid=0,
        st_gid=0,
        st_dev=original.st_dev,
        st_nlink=max(original.st_nlink, 1),
        st_flags=0,
    )
    monkeypatch.setattr(
        artifacts,
        "_descriptor_extended_attribute_names",
        lambda _descriptor: frozenset(),
    )
    monkeypatch.setattr(
        artifacts,
        "_descriptor_has_extended_acl",
        lambda _descriptor: False,
    )
    try:
        assert artifacts._require_linux_tmp_traversal_root(
            descriptor,
            trusted,
            expected_device=original.st_dev,
            reason="SOURCE_METADATA_INVALID",
        ) == frozenset()
    finally:
        os.close(descriptor)


@pytest.mark.skipif(sys.platform != "linux", reason="real Linux /tmp traversal root")
@pytest.mark.parametrize("phase", ("open", "revalidation"))
@pytest.mark.parametrize(
    "violation",
    (
        "owner",
        "group",
        "mode",
        "device",
        "link",
        "acl",
        "xattr",
        "flags",
        "relation",
    ),
)
def test_absolute_view_refuses_each_linux_tmp_traversal_root_violation(
    monkeypatch: pytest.MonkeyPatch,
    phase: str,
    violation: str,
) -> None:
    tmp_info = Path("/tmp").stat()
    tmp_identity = (tmp_info.st_dev, tmp_info.st_ino)
    original_fstat = os.fstat
    original_stat = os.stat
    original_xattrs = artifacts._descriptor_extended_attribute_names
    original_acl = artifacts._descriptor_has_extended_acl

    with tempfile.TemporaryDirectory(prefix="mmx-linux-tmp-", dir="/tmp") as root:
        evidence = Path(root) / "evidence.json"
        evidence.write_bytes(b"evidence\n")
        evidence.chmod(0o444)
        view = (
            artifacts._RepositoryView(evidence)
            if phase == "revalidation"
            else None
        )

        def is_tmp(info: os.stat_result) -> bool:
            return (info.st_dev, info.st_ino) == tmp_identity

        def overlay(
            info: os.stat_result, *, relation: bool = False
        ) -> os.stat_result | _StatOverlay:
            if not is_tmp(info):
                return info
            changes: dict[str, int] = {}
            if violation == "owner":
                changes["st_uid"] = 10000
            elif violation == "group":
                changes["st_gid"] = 10000
            elif violation == "mode":
                changes["st_mode"] = stat.S_IFDIR | 0o0777
            elif violation == "device":
                changes["st_dev"] = info.st_dev + 1
            elif violation == "link":
                changes["st_nlink"] = 0
            elif violation == "flags":
                changes["st_flags"] = 1
            elif violation == "relation" and relation:
                changes["st_ino"] = info.st_ino + 1
            return _StatOverlay(info, **changes) if changes else info

        monkeypatch.setattr(
            os,
            "fstat",
            lambda descriptor: overlay(original_fstat(descriptor)),
        )
        monkeypatch.setattr(
            os,
            "stat",
            lambda *args, **kwargs: overlay(
                original_stat(*args, **kwargs), relation=True
            ),
        )

        def observed_xattrs(descriptor: int) -> frozenset[bytes]:
            observed = original_xattrs(descriptor)
            if violation == "xattr" and is_tmp(original_fstat(descriptor)):
                return observed | frozenset({b"user.mastermind-test"})
            return observed

        def observed_acl(descriptor: int) -> bool:
            if violation == "acl" and is_tmp(original_fstat(descriptor)):
                return True
            return original_acl(descriptor)

        monkeypatch.setattr(
            artifacts,
            "_descriptor_extended_attribute_names",
            observed_xattrs,
        )
        monkeypatch.setattr(
            artifacts,
            "_descriptor_has_extended_acl",
            observed_acl,
        )
        try:
            with pytest.raises(
                artifacts.CapacityHostArtifactError,
                match=(
                    "SOURCE_VIEW_DRIFT"
                    if phase == "revalidation"
                    else "SOURCE_METADATA_INVALID"
                ),
            ):
                if phase == "revalidation":
                    assert view is not None
                    view.revalidate()
                else:
                    artifacts._RepositoryView(evidence)
        finally:
            if view is not None:
                view.close()


@pytest.mark.skipif(sys.platform != "linux", reason="real Linux /tmp traversal root")
def test_absolute_view_accepts_exact_real_linux_tmp_traversal_root() -> None:
    with tempfile.TemporaryDirectory(prefix="mmx-linux-tmp-", dir="/tmp") as root:
        evidence = Path(root) / "evidence.json"
        evidence.write_bytes(b"evidence\n")
        evidence.chmod(0o444)
        view = artifacts._RepositoryView(evidence)
        try:
            assert view.read_bytes(".", maximum_bytes=1024) == b"evidence\n"
            assert view.guard_linux_tmp.count(True) == 1
            view.revalidate()
        finally:
            view.close()


@pytest.mark.parametrize(
    "semantic_role",
    ("runtime", "generation", "topology", "rollback", "legacy"),
)
def test_preserved_semantic_reads_use_retained_descriptors_during_restored_path_swap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    semantic_role: str,
) -> None:
    root = tmp_path / semantic_role
    root.mkdir(mode=0o755)
    trusted = root / "evidence.json"
    trusted.write_bytes(b'{"trusted":true}\n')
    trusted.chmod(0o444)
    replacement = tmp_path / f"{semantic_role}-replacement"
    replacement.mkdir(mode=0o755)
    attacker = replacement / "evidence.json"
    attacker.write_bytes(b'{"trusted":false}\n')
    attacker.chmod(0o444)
    displaced = tmp_path / f"{semantic_role}-displaced"
    view = artifacts._RepositoryView(root)
    original_read = artifacts._read_descriptor
    target_descriptor = view.descriptors["evidence.json"]
    root_before = root.stat()
    root_inode = root_before.st_ino
    swapped = False
    original_fstat = os.fstat
    original_stat = os.stat

    def restored_swap(descriptor: int, maximum_bytes: int) -> bytes:
        nonlocal swapped
        if descriptor == target_descriptor and not swapped:
            root.rename(displaced)
            replacement.rename(root)
            try:
                payload = original_read(descriptor, maximum_bytes)
            finally:
                root.rename(replacement)
                displaced.rename(root)
            swapped = True
            return payload
        return original_read(descriptor, maximum_bytes)

    def forbid_pathname_read(*args: object, **kwargs: object) -> bytes:
        raise AssertionError((args, kwargs))

    monkeypatch.setattr(artifacts, "_read_descriptor", restored_swap)
    monkeypatch.setattr(Path, "read_bytes", forbid_pathname_read)
    monkeypatch.setattr(
        os,
        "fstat",
        lambda descriptor: (
            _StatOverlay(
                original_fstat(descriptor),
                st_ctime_ns=root_before.st_ctime_ns,
            )
            if (original_fstat(descriptor).st_dev, original_fstat(descriptor).st_ino)
            == (root_before.st_dev, root_inode)
            else original_fstat(descriptor)
        ),
    )
    monkeypatch.setattr(
        os,
        "stat",
        lambda *args, **kwargs: (
            _StatOverlay(
                original_stat(*args, **kwargs),
                st_ctime_ns=root_before.st_ctime_ns,
            )
            if (
                original_stat(*args, **kwargs).st_dev,
                original_stat(*args, **kwargs).st_ino,
            )
            == (root_before.st_dev, root_inode)
            else original_stat(*args, **kwargs)
        ),
    )
    try:
        assert view.read_bytes("evidence.json", maximum_bytes=1024) == (
            b'{"trusted":true}\n'
        )
        assert swapped
        view.revalidate()
    finally:
        view.close()


def test_absolute_evidence_view_opens_every_component_from_retained_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    evidence = tmp_path / "absolute-evidence.json"
    evidence.write_bytes(b"evidence\n")
    evidence.chmod(0o444)
    original_open = os.open
    absolute_opens: list[str] = []

    def observe_open(path: object, flags: int, *args: object, **kwargs: object) -> int:
        encoded = os.fspath(path)
        if "dir_fd" not in kwargs and os.path.isabs(encoded):
            absolute_opens.append(encoded)
        return original_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", observe_open)
    view = artifacts._RepositoryView(evidence)
    try:
        assert view.read_bytes(".", maximum_bytes=1024) == b"evidence\n"
    finally:
        view.close()
    assert absolute_opens == ["/"]


def test_repository_view_full_revalidation_walks_retained_parent_capability_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "linear-revalidation"
    for branch_index in range(3):
        nested = root / f"branch-{branch_index}" / "middle" / "leaf"
        nested.mkdir(parents=True)
        for file_index in range(3):
            evidence = nested / f"evidence-{file_index}.json"
            evidence.write_bytes(f"{branch_index}:{file_index}\n".encode("ascii"))
            evidence.chmod(0o444)
    view = artifacts._RepositoryView(root)
    parent_checks = 0
    object_xattr_checks = {descriptor: 0 for descriptor in view.descriptors.values()}
    original_parent = artifacts._RepositoryView._revalidate_parent_capability
    original_xattrs = artifacts._descriptor_extended_attribute_names

    def observed_parent_capability(received: artifacts._RepositoryView) -> None:
        nonlocal parent_checks
        parent_checks += 1
        original_parent(received)

    def observed_xattrs(descriptor: int) -> frozenset[bytes]:
        if descriptor in object_xattr_checks:
            object_xattr_checks[descriptor] += 1
        return original_xattrs(descriptor)

    monkeypatch.setattr(
        artifacts._RepositoryView,
        "_revalidate_parent_capability",
        observed_parent_capability,
    )
    monkeypatch.setattr(
        artifacts,
        "_descriptor_extended_attribute_names",
        observed_xattrs,
    )
    try:
        view.revalidate()
        assert parent_checks == 2
        assert set(object_xattr_checks.values()) == {1}
    finally:
        view.close()


def test_repository_view_closes_guard_descriptor_when_initial_guard_audit_refuses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    evidence = tmp_path / "evidence.json"
    evidence.write_bytes(b"evidence\n")
    evidence.chmod(0o444)
    opened_root: list[int] = []
    closed_root: list[int] = []
    original_open = os.open
    original_close = os.close

    def observed_open(path: object, flags: int, *args: object, **kwargs: object) -> int:
        descriptor = original_open(path, flags, *args, **kwargs)
        if os.fspath(path) == "/" and "dir_fd" not in kwargs:
            opened_root.append(descriptor)
        return descriptor

    def observed_close(descriptor: int) -> None:
        if descriptor in opened_root:
            closed_root.append(descriptor)
        original_close(descriptor)

    def refuse_guard(*args: object, **kwargs: object) -> None:
        raise artifacts.CapacityHostArtifactError("SOURCE_METADATA_INVALID")

    monkeypatch.setattr(os, "open", observed_open)
    monkeypatch.setattr(os, "close", observed_close)
    monkeypatch.setattr(artifacts, "_require_source_repair_ancestor", refuse_guard)
    with pytest.raises(artifacts.CapacityHostArtifactError, match="SOURCE_METADATA_INVALID"):
        artifacts._RepositoryView(evidence)
    assert opened_root
    assert closed_root == opened_root


@pytest.mark.parametrize(
    "failure_stage",
    (
        "first-fstat",
        "ancestor-validation",
        "xattr-audit",
        "acl-audit",
        "relation-observation",
        "later-guard-open",
    ),
)
def test_repository_view_owns_every_guard_before_each_admission_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_stage: str,
) -> None:
    evidence = tmp_path / "guard-admission" / "evidence.json"
    evidence.parent.mkdir()
    evidence.write_bytes(b"evidence\n")
    evidence.chmod(0o444)
    before = _open_fd_inventory()
    opened_guards: list[int] = []
    closed_guards: list[int] = []
    original_open = os.open
    original_close = os.close
    original_fstat = os.fstat
    original_stat = os.stat
    original_acl = artifacts._descriptor_has_extended_acl

    def observed_open(
        path: object, flags: int, *args: object, **kwargs: object
    ) -> int:
        is_guard = bool(flags & getattr(os, "O_DIRECTORY", 0))
        if (
            failure_stage == "later-guard-open"
            and is_guard
            and "dir_fd" in kwargs
            and kwargs["dir_fd"] in opened_guards
        ):
            raise OSError(errno.EIO, "injected later guard open failure")
        descriptor = original_open(path, flags, *args, **kwargs)
        if is_guard and (
            os.fspath(path) == "/"
            or (
                "dir_fd" in kwargs
                and kwargs["dir_fd"] in opened_guards
            )
        ):
            opened_guards.append(descriptor)
        return descriptor

    def observed_close(descriptor: int) -> None:
        if descriptor in opened_guards:
            closed_guards.append(descriptor)
        original_close(descriptor)

    def observed_fstat(descriptor: int) -> os.stat_result:
        if failure_stage == "first-fstat" and descriptor in opened_guards:
            raise OSError(errno.EIO, "injected first guard fstat failure")
        return original_fstat(descriptor)

    def observed_stat(*args: object, **kwargs: object) -> os.stat_result | _StatOverlay:
        info = original_stat(*args, **kwargs)
        if (
            failure_stage == "relation-observation"
            and kwargs.get("dir_fd") in opened_guards
            and kwargs.get("follow_symlinks") is False
        ):
            return _StatOverlay(info, st_ino=info.st_ino + 1)
        return info

    def refuse_ancestor(*args: object, **kwargs: object) -> None:
        raise artifacts.CapacityHostArtifactError("SOURCE_METADATA_INVALID")

    def refuse_xattrs(*args: object, **kwargs: object) -> frozenset[bytes]:
        raise artifacts.CapacityHostArtifactError("SOURCE_METADATA_INVALID")

    def observed_acl(descriptor: int) -> bool:
        if failure_stage == "acl-audit" and descriptor in opened_guards:
            return True
        return original_acl(descriptor)

    monkeypatch.setattr(os, "open", observed_open)
    monkeypatch.setattr(os, "close", observed_close)
    monkeypatch.setattr(os, "fstat", observed_fstat)
    monkeypatch.setattr(os, "stat", observed_stat)
    monkeypatch.setattr(artifacts, "_descriptor_has_extended_acl", observed_acl)
    if failure_stage == "ancestor-validation":
        monkeypatch.setattr(
            artifacts, "_require_source_repair_ancestor", refuse_ancestor
        )
    if failure_stage == "xattr-audit":
        monkeypatch.setattr(
            artifacts, "_source_repair_ancestor_xattrs", refuse_xattrs
        )

    with pytest.raises((artifacts.CapacityHostArtifactError, OSError)):
        artifacts._RepositoryView(evidence)
    assert opened_guards
    assert closed_guards == list(reversed(opened_guards))
    assert len(closed_guards) == len(set(closed_guards))
    assert _open_fd_inventory() == before


def test_repository_view_attempts_all_guard_closes_after_one_close_refuses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    evidence = tmp_path / "guard-close" / "evidence.json"
    evidence.parent.mkdir()
    evidence.write_bytes(b"evidence\n")
    evidence.chmod(0o444)
    before = _open_fd_inventory()
    opened_guards: list[int] = []
    close_attempts: list[int] = []
    original_open = os.open
    original_close = os.close
    original_stat = os.stat
    injected_close_failure = False

    def observed_open(
        path: object, flags: int, *args: object, **kwargs: object
    ) -> int:
        descriptor = original_open(path, flags, *args, **kwargs)
        if flags & getattr(os, "O_DIRECTORY", 0) and (
            os.fspath(path) == "/"
            or (
                "dir_fd" in kwargs
                and kwargs["dir_fd"] in opened_guards
            )
        ):
            opened_guards.append(descriptor)
        return descriptor

    def observed_close(descriptor: int) -> None:
        nonlocal injected_close_failure
        if descriptor in opened_guards:
            close_attempts.append(descriptor)
            original_close(descriptor)
            if not injected_close_failure:
                injected_close_failure = True
                raise OSError(errno.EIO, "injected guard close failure")
            return
        original_close(descriptor)

    def mismatched_relation(
        *args: object, **kwargs: object
    ) -> os.stat_result | _StatOverlay:
        info = original_stat(*args, **kwargs)
        if (
            kwargs.get("dir_fd") in opened_guards
            and kwargs.get("follow_symlinks") is False
        ):
            return _StatOverlay(info, st_ino=info.st_ino + 1)
        return info

    monkeypatch.setattr(os, "open", observed_open)
    monkeypatch.setattr(os, "close", observed_close)
    monkeypatch.setattr(os, "stat", mismatched_relation)
    with pytest.raises(
        artifacts.CapacityHostArtifactError, match="SOURCE_METADATA_INVALID"
    ):
        artifacts._RepositoryView(evidence)
    assert len(opened_guards) >= 2
    assert close_attempts == list(reversed(opened_guards))
    assert len(close_attempts) == len(set(close_attempts))
    assert _open_fd_inventory() == before


def test_repository_role_directory_refuses_stable_zero_link_count(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "zero-link-role"
    root.mkdir(mode=0o755)
    root.chmod(0o755)
    policy = _repository_role_directory_policy(root)
    identity = (root.stat().st_dev, root.stat().st_ino)
    original_fstat = os.fstat
    original_stat = os.stat

    def overlay(info: os.stat_result) -> os.stat_result | _StatOverlay:
        if (info.st_dev, info.st_ino) == identity:
            return _StatOverlay(info, st_nlink=0)
        return info

    monkeypatch.setattr(os, "fstat", lambda descriptor: overlay(original_fstat(descriptor)))
    monkeypatch.setattr(
        os, "stat", lambda *args, **kwargs: overlay(original_stat(*args, **kwargs))
    )
    with pytest.raises(
        artifacts.CapacityHostArtifactError, match="SOURCE_METADATA_INVALID"
    ):
        artifacts._RepositoryView(root, security_policy=policy)


def test_repository_role_directory_freezes_each_admitted_positive_link_count(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "positive-link-role"
    root.mkdir(mode=0o755)
    root.chmod(0o755)
    policy = _repository_role_directory_policy(root)
    identity = (root.stat().st_dev, root.stat().st_ino)
    original_fstat = os.fstat
    original_stat = os.stat
    observed_nlink = 7

    def overlay(info: os.stat_result) -> os.stat_result | _StatOverlay:
        if (info.st_dev, info.st_ino) == identity:
            return _StatOverlay(info, st_nlink=observed_nlink)
        return info

    monkeypatch.setattr(os, "fstat", lambda descriptor: overlay(original_fstat(descriptor)))
    monkeypatch.setattr(
        os, "stat", lambda *args, **kwargs: overlay(original_stat(*args, **kwargs))
    )
    view = artifacts._RepositoryView(root, security_policy=policy)
    try:
        observed_nlink = 8
        with pytest.raises(
            artifacts.CapacityHostArtifactError, match="SOURCE_VIEW_DRIFT"
        ):
            view.revalidate()
    finally:
        view.close()


def test_preserved_fd_budget_uplifts_soft_limit_in_subprocess() -> None:
    script = """
import json, resource, tempfile
from pathlib import Path
from ops.executive_os import capacity_host_artifacts as a
soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
if hard < a._PRESERVED_H0_REQUIRED_NOFILE:
    raise SystemExit(77)
resource.setrlimit(resource.RLIMIT_NOFILE, (256, hard))
observed = a._ensure_preserved_h0_fd_budget()
with tempfile.TemporaryDirectory() as temporary:
    root = Path(temporary) / 'exact-scale'
    root.mkdir(mode=0o755)
    for index in range(a._TRUSTED_E4_MANIFEST_ENTRY_COUNT):
        child = root / f'evidence-{index:04d}'
        child.write_bytes(b'evidence\\n')
        child.chmod(0o444)
    view = a._RepositoryView(root)
    try:
        count = len(view.descriptors)
        peak = len([name for name in __import__('os').listdir('/dev/fd') if name.isdecimal()])
        view.revalidate()
    finally:
        view.close()
print(json.dumps({'observed': observed, 'actual': resource.getrlimit(resource.RLIMIT_NOFILE)[0], 'count': count, 'peak': peak}))
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).parents[1],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        text=True,
    )
    if completed.returncode == 77:
        pytest.skip("host hard RLIMIT_NOFILE is below the reviewed H0 bound")
    assert completed.returncode == 0, completed.stderr
    observed = json.loads(completed.stdout)
    assert observed["observed"] >= artifacts._PRESERVED_H0_REQUIRED_NOFILE
    assert observed["actual"] >= artifacts._PRESERVED_H0_REQUIRED_NOFILE
    assert observed["count"] == artifacts._TRUSTED_E4_MANIFEST_ENTRY_COUNT + 1
    assert observed["peak"] >= observed["count"]


def test_preserved_fd_budget_refuses_low_hard_limit_before_graph_in_subprocess() -> None:
    script = """
import resource
from ops.executive_os import capacity_host_artifacts as a
soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
limit = min(1024, hard)
resource.setrlimit(resource.RLIMIT_NOFILE, (limit, limit))
try:
    a._ensure_preserved_h0_fd_budget()
except a.CapacityHostArtifactError as exc:
    print(str(exc))
    raise SystemExit(0)
raise SystemExit(1)
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).parents[1],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert "SOURCE_REPAIR_FD_LIMIT_INVALID" in completed.stdout


def test_preserved_fd_budget_refuses_setrlimit_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        resource,
        "getrlimit",
        lambda limit: (256, artifacts._PRESERVED_H0_REQUIRED_NOFILE * 2),
    )

    def refused(*args: object, **kwargs: object) -> None:
        raise OSError(errno.EPERM, "injected")

    monkeypatch.setattr(resource, "setrlimit", refused)
    with pytest.raises(
        artifacts.CapacityHostArtifactError,
        match="SOURCE_REPAIR_FD_LIMIT_INVALID",
    ):
        artifacts._ensure_preserved_h0_fd_budget()


@pytest.mark.parametrize(
    "component",
    ("", ".", "..", "slash/name", "nul\x00name"),
)
def test_absolute_component_validation_refuses_before_open(
    monkeypatch: pytest.MonkeyPatch, component: str
) -> None:
    opened = False

    def forbidden_open(*args: object, **kwargs: object) -> int:
        nonlocal opened
        opened = True
        raise AssertionError((args, kwargs))

    monkeypatch.setattr(os, "open", forbidden_open)
    with pytest.raises(artifacts.CapacityHostArtifactError, match="SOURCE_METADATA_INVALID"):
        artifacts._validate_absolute_components(("private", component, "evidence"))
    assert not opened


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS fixed root alias")
@pytest.mark.parametrize("failure_stage", ("fstat", "xattrs", "readlink", "acl"))
def test_native_alias_descriptor_is_owned_before_every_audit_refusal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_stage: str,
) -> None:
    before_fds = _open_fd_inventory()
    evidence = tmp_path / "evidence"
    evidence.write_bytes(b"evidence\n")
    evidence.chmod(0o444)
    alias_fd: int | None = None
    closed: list[int] = []
    original_open_alias = artifacts._open_release_symlink
    original_fstat = os.fstat
    original_xattrs = artifacts._descriptor_extended_attribute_names
    original_readlink = os.readlink
    original_acl = artifacts._descriptor_has_extended_acl
    original_close = os.close

    def opened_alias(parent: int, name: str) -> int:
        nonlocal alias_fd
        alias_fd = original_open_alias(parent, name)
        return alias_fd

    def refuse_fstat(fd: int) -> os.stat_result:
        if failure_stage == "fstat" and fd == alias_fd:
            raise OSError(errno.EIO, "injected")
        return original_fstat(fd)

    def refuse_xattrs(fd: int) -> frozenset[bytes]:
        if failure_stage == "xattrs" and fd == alias_fd:
            raise OSError(errno.EIO, "injected")
        return original_xattrs(fd)

    def refuse_readlink(*args: object, **kwargs: object) -> str:
        if failure_stage == "readlink":
            raise OSError(errno.EIO, "injected")
        return original_readlink(*args, **kwargs)

    def refuse_acl(fd: int) -> bool:
        if failure_stage == "acl" and fd == alias_fd:
            raise OSError(errno.EIO, "injected")
        return original_acl(fd)

    def observe_close(fd: int) -> None:
        if fd == alias_fd:
            closed.append(fd)
        original_close(fd)

    monkeypatch.setattr(artifacts, "_open_release_symlink", opened_alias)
    monkeypatch.setattr(os, "fstat", refuse_fstat)
    monkeypatch.setattr(artifacts, "_descriptor_extended_attribute_names", refuse_xattrs)
    monkeypatch.setattr(os, "readlink", refuse_readlink)
    monkeypatch.setattr(artifacts, "_descriptor_has_extended_acl", refuse_acl)
    monkeypatch.setattr(os, "close", observe_close)
    with pytest.raises((artifacts.CapacityHostArtifactError, OSError)):
        artifacts._RepositoryView(Path("/var"), recursive=False)
    assert alias_fd is not None
    assert closed == [alias_fd]
    assert _open_fd_inventory() == before_fds


@pytest.mark.parametrize("mode,links", ((0o666, 1), (0o444, 2)))
def test_repository_view_rejects_stably_unsafe_regular_file_before_snapshot(
    tmp_path: Path,
    mode: int,
    links: int,
) -> None:
    root = tmp_path / "unsafe"
    root.mkdir(mode=0o755)
    evidence = root / "evidence"
    evidence.write_bytes(b"evidence\n")
    evidence.chmod(mode)
    if links == 2:
        os.link(evidence, root / "second-link")
    with pytest.raises(artifacts.CapacityHostArtifactError, match="SOURCE_METADATA_INVALID"):
        artifacts._RepositoryView(root)


def test_generation_parent_capability_is_bound_to_exact_lifecycle_position(
    tmp_path: Path,
) -> None:
    generation_parent = tmp_path / "capacity-generations"
    archive = tmp_path / "archive"
    generation_parent.mkdir()
    archive.mkdir()
    visible = generation_parent / artifacts.PRIOR_GENERATION_DIGEST
    archived = archive / artifacts._ARCHIVED_GENERATION_NAME
    generation_fd = os.open(generation_parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    archive_fd = os.open(archive, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    parents = artifacts.SourceRepairParents(
        source_path=tmp_path,
        source=os.dup(generation_fd),
        generation_path=generation_parent,
        generation=generation_fd,
        staging_path=tmp_path,
        staging=os.dup(generation_fd),
        archive_path=tmp_path,
        archive=os.dup(generation_fd),
        device=tmp_path.stat().st_dev,
        intent_archive_path=archive,
        intent_archive=archive_fd,
    )
    try:
        assert artifacts._retained_generation_parent(parents, visible) == generation_fd
        assert artifacts._retained_generation_parent(parents, archived) == archive_fd
        with pytest.raises(artifacts.CapacityHostArtifactError, match="PARENT_INVALID"):
            artifacts._retained_generation_parent(parents, archive / artifacts.PRIOR_GENERATION_DIGEST)
        parents.intent_archive = None
        assert artifacts._retained_generation_parent(parents, visible) == generation_fd
        with pytest.raises(artifacts.CapacityHostArtifactError, match="PARENT_INVALID"):
            artifacts._retained_generation_parent(parents, archived)
    finally:
        if parents.intent_archive is None:
            parents.intent_archive = archive_fd
        parents.close()


def test_retained_prior_generation_authenticates_fixed_inventory_and_hashes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / artifacts.PRIOR_GENERATION_DIGEST
    root.mkdir(mode=0o755)
    payloads = {name: f"{name}\n".encode() for name in artifacts.PRIOR_GENERATION_ARTIFACT_SHA256}
    for name, payload in payloads.items():
        path = root / name
        path.write_bytes(payload)
        path.chmod(0o444)
    root.chmod(0o555)
    monkeypatch.setattr(
        artifacts,
        "PRIOR_GENERATION_ARTIFACT_SHA256",
        {name: hashlib.sha256(payload).hexdigest() for name, payload in payloads.items()},
    )
    view = artifacts._RepositoryView(root)
    try:
        artifacts._verify_retained_prior_generation(
            view,
            expected_uid=os.getuid(),
            expected_gid=os.getgid(),
            expected_device=root.stat().st_dev,
        )
    finally:
        view.close()
    root.chmod(0o755)
    extra = root / "extra"
    extra.write_bytes(b"extra")
    extra.chmod(0o444)
    root.chmod(0o555)
    invalid_view = artifacts._RepositoryView(root)
    try:
        with pytest.raises(
            artifacts.CapacityHostArtifactError, match="PRIOR_GENERATION_INVALID"
        ):
            artifacts._verify_retained_prior_generation(
                invalid_view,
                expected_uid=os.getuid(),
                expected_gid=os.getgid(),
                expected_device=root.stat().st_dev,
            )
    finally:
        invalid_view.close()


def test_retained_prior_generation_swap_refuses_before_external_topology_open(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    system_root, _transport, _commit, _manifest = _repair_host_fixture(
        tmp_path, monkeypatch
    )
    generation = (
        system_root / "capacity-generations" / artifacts.PRIOR_GENERATION_DIGEST
    )
    artifacts._validate_prior_generation(
        generation,
        expected_uid=os.getuid(),
        expected_gid=os.getgid(),
    )
    topology = generation / "broker-topology.json"
    topology.chmod(0o600)
    topology.write_bytes(
        b'{"brokers":[{"config_path":"/tmp/untrusted-topology-open"}]}'
    )
    topology.chmod(0o444)
    generation.chmod(0o555)
    runtime_parent = system_root / "capacity-runtimes"
    runtime = runtime_parent / "cf1-pyyaml-6.0.3-cp312-arm64"
    runtime.mkdir(parents=True, mode=0o755)
    runtime.chmod(0o555)
    runtime_parent.chmod(0o755)
    parents = artifacts._open_source_repair_parents(
        system_root, expected_uid=os.getuid(), expected_gid=os.getgid()
    )
    opened_external = False
    original_init = artifacts._RepositoryView.__init__

    def observed_init(
        received: artifacts._RepositoryView,
        source_root: Path,
        *args: object,
        **kwargs: object,
    ) -> None:
        nonlocal opened_external
        if source_root == Path("/tmp/untrusted-topology-open"):
            opened_external = True
        original_init(received, source_root, *args, **kwargs)

    monkeypatch.setattr(artifacts._RepositoryView, "__init__", observed_init)
    _overlay_fixture_identity_as_root(monkeypatch, device=parents.device)
    try:
        with pytest.raises(
            artifacts.CapacityHostArtifactError, match="PRIOR_GENERATION_INVALID"
        ):
            artifacts._verify_preserved_h0_invariants(
                system_root,
                generation,
                test_adapter=False,
                parents=parents,
            )
        assert not opened_external
    finally:
        parents.close()


@pytest.mark.parametrize("field", ("st_uid", "st_gid", "st_dev"))
def test_role_policy_rejects_wrong_identity_before_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
) -> None:
    root = tmp_path / "role-policy"
    root.mkdir(mode=0o755)
    evidence = root / "evidence"
    evidence.write_bytes(b"evidence\n")
    evidence.chmod(0o444)
    target = evidence.stat()
    identity = (target.st_dev, target.st_ino)
    original_fstat = os.fstat

    def overlaid_fstat(descriptor: int) -> os.stat_result | _StatOverlay:
        info = original_fstat(descriptor)
        if (info.st_dev, info.st_ino) == identity:
            return _StatOverlay(info, **{field: getattr(info, field) + 1})
        return info

    monkeypatch.setattr(os, "fstat", overlaid_fstat)
    policy = artifacts._RepositorySecurityPolicy(
        role="test-evidence",
        expected_uid=os.getuid(),
        expected_gid=os.getgid(),
        expected_device=root.stat().st_dev,
        directory_modes=frozenset({0o755}),
        file_modes=frozenset({0o444}),
    )
    with pytest.raises(artifacts.CapacityHostArtifactError, match="SOURCE_METADATA_INVALID"):
        artifacts._RepositoryView(root, security_policy=policy)


def test_bad_release_manifest_refuses_before_any_payload_child_open(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release = tmp_path / artifacts.PRESERVED_TOPOLOGY_RELEASE_COMMIT
    _write_inert_release_fixture(release, tree_sha="a" * 40)
    giant = release / "giant-untrusted-child"
    giant.write_bytes(b"x" * 1024)
    giant.chmod(0o444)
    opened: list[str] = []
    original_open = os.open

    def observed_open(path: object, flags: int, *args: object, **kwargs: object) -> int:
        opened.append(os.fspath(path))
        return original_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", observed_open)
    with pytest.raises(artifacts.CapacityHostArtifactError, match="RELEASE_INVALID"):
        artifacts._verify_inert_release_manifest(
            release,
            expected_commit=artifacts.PRESERVED_TOPOLOGY_RELEASE_COMMIT,
            expected_uid=os.getuid(),
            expected_gid=os.getgid(),
        )
    assert "giant-untrusted-child" not in opened
    assert "ops" not in opened


def test_authenticated_release_inventory_refuses_unexpected_child_without_opening_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release = tmp_path / artifacts.PRESERVED_TOPOLOGY_RELEASE_COMMIT
    manifest_bytes = _write_inert_release_fixture(release, tree_sha="a" * 40)
    unexpected = release / "unexpected-giant"
    unexpected.write_bytes(b"x" * 1024)
    unexpected.chmod(0o444)
    monkeypatch.setattr(artifacts, "_TRUSTED_E4_RELEASE_TREE", "a" * 40)
    monkeypatch.setattr(
        artifacts,
        "_TRUSTED_E4_MANIFEST_SHA256",
        hashlib.sha256(manifest_bytes).hexdigest(),
    )
    monkeypatch.setattr(artifacts, "_TRUSTED_E4_MANIFEST_SIZE", len(manifest_bytes))
    monkeypatch.setattr(artifacts, "_TRUSTED_E4_MANIFEST_ENTRY_COUNT", 1)
    opened: list[str] = []
    original_open = os.open

    def observed_open(path: object, flags: int, *args: object, **kwargs: object) -> int:
        opened.append(os.fspath(path))
        return original_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", observed_open)
    with pytest.raises(artifacts.CapacityHostArtifactError, match="RELEASE_INVALID"):
        artifacts._verify_inert_release_manifest(
            release,
            expected_commit=artifacts.PRESERVED_TOPOLOGY_RELEASE_COMMIT,
            expected_uid=os.getuid(),
            expected_gid=os.getgid(),
        )
    assert "unexpected-giant" not in opened
    assert "payload.txt" not in opened


def test_release_metadata_mismatch_refuses_before_payload_hash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release = tmp_path / artifacts.PRESERVED_TOPOLOGY_RELEASE_COMMIT
    manifest_bytes = _write_inert_release_fixture(release, tree_sha="a" * 40)
    (release / "payload.txt").chmod(0o400)
    monkeypatch.setattr(artifacts, "_TRUSTED_E4_RELEASE_TREE", "a" * 40)
    monkeypatch.setattr(
        artifacts,
        "_TRUSTED_E4_MANIFEST_SHA256",
        hashlib.sha256(manifest_bytes).hexdigest(),
    )
    monkeypatch.setattr(artifacts, "_TRUSTED_E4_MANIFEST_SIZE", len(manifest_bytes))
    monkeypatch.setattr(artifacts, "_TRUSTED_E4_MANIFEST_ENTRY_COUNT", 1)

    def forbidden_hash(*args: object, **kwargs: object) -> str:
        raise AssertionError((args, kwargs))

    monkeypatch.setattr(artifacts, "_descriptor_sha256", forbidden_hash)
    with pytest.raises(artifacts.CapacityHostArtifactError, match="RELEASE_INVALID"):
        artifacts._verify_inert_release_manifest(
            release,
            expected_commit=artifacts.PRESERVED_TOPOLOGY_RELEASE_COMMIT,
            expected_uid=os.getuid(),
            expected_gid=os.getgid(),
        )


def test_real_mode_visible_prior_generation_receives_retained_generation_parent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    system_root, transport, commit, _manifest = _repair_host_fixture(
        tmp_path, monkeypatch
    )
    _overlay_fixture_identity_as_root(monkeypatch, device=system_root.stat().st_dev)

    class Observed(Exception):
        pass

    def observed(
        received_root: Path,
        generation: Path,
        *,
        test_adapter: bool,
        parents: artifacts.SourceRepairParents | None = None,
    ) -> None:
        assert received_root == system_root
        assert not test_adapter
        assert parents is not None
        assert parents.intent_archive is None
        assert generation == parents.generation_path / artifacts.PRIOR_GENERATION_DIGEST
        assert artifacts._retained_generation_parent(parents, generation) == parents.generation
        raise Observed

    monkeypatch.setattr(artifacts, "_verify_preserved_h0_invariants", observed)
    arguments = _repair_arguments(system_root, transport, commit)
    arguments["test_adapter"] = False
    with pytest.raises(Observed):
        artifacts.run_source_repair_host(**arguments)


@pytest.mark.parametrize("mode", ("repair", "verify-only"))
def test_real_mode_archived_and_verify_only_receive_same_retained_archive_parent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
) -> None:
    system_root, transport, commit, _manifest = _repair_host_fixture(
        tmp_path, monkeypatch
    )
    arguments = _repair_arguments(system_root, transport, commit)
    assert artifacts.run_source_repair_host(**arguments) == (
        "H0_SOURCE_CLOSURE_REPAIR_PASS_NOT_P0_ACCEPTED"
    )
    archive = next((system_root / "capacity-archive").iterdir())
    intent = json.loads((archive / artifacts._SOURCE_REPAIR_INTENT_NAME).read_bytes())
    receipt = json.loads((archive / artifacts._SOURCE_REPAIR_RECEIPT_NAME).read_bytes())
    installed_manifest, installed_evidence = artifacts._verify_installed_repair_source(
        system_root / "capacity-sources" / "macro" / commit,
        commit,
    )
    _overlay_fixture_identity_as_root(monkeypatch, device=system_root.stat().st_dev)

    def preserved_tree_digest(path: Path, **kwargs: object) -> str:
        if path.name == artifacts._ARCHIVED_SOURCE_NAME:
            return intent["observed_old_source_tree_sha256"]
        if path.name == artifacts._ARCHIVED_GENERATION_NAME:
            return receipt["archived_generation_tree_sha256"]
        return "0" * 64

    monkeypatch.setattr(artifacts, "closed_tree_digest", preserved_tree_digest)
    monkeypatch.setattr(
        artifacts,
        "_validate_prior_generation",
        lambda *args, **kwargs: receipt["archived_generation_tree_sha256"],
    )
    monkeypatch.setattr(
        artifacts,
        "_verify_installed_repair_source",
        lambda *args, **kwargs: (installed_manifest, installed_evidence),
    )

    class Observed(Exception):
        pass

    def observed(
        received_root: Path,
        generation: Path,
        *,
        test_adapter: bool,
        parents: artifacts.SourceRepairParents | None = None,
    ) -> None:
        assert received_root == system_root
        assert not test_adapter
        assert parents is not None
        assert parents.intent_archive is not None
        assert generation == parents.intent_archive_path / artifacts._ARCHIVED_GENERATION_NAME
        assert (
            artifacts._retained_generation_parent(parents, generation)
            == parents.intent_archive
        )
        raise Observed

    monkeypatch.setattr(artifacts, "_verify_preserved_h0_invariants", observed)
    with pytest.raises((Observed, artifacts.SourceRepairIncomplete)) as caught:
        artifacts.run_source_repair_host(
            mode=mode,
            system_root=system_root,
            lock_file=system_root / "locks" / "cf2-h0.lock",
            expected_repair_commit="d" * 40,
            expected_source_commit=commit,
            transport=transport if mode == "repair" else None,
            transport_sha256=(
                hashlib.sha256(transport.read_bytes()).hexdigest()
                if mode == "repair"
                else None
            ),
            operator_uid=os.getuid() if mode == "repair" else None,
            test_adapter=False,
        )
    if isinstance(caught.value, artifacts.SourceRepairIncomplete):
        assert isinstance(caught.value.__cause__, Observed)


def test_retained_topology_accepts_exact_per_row_producer_metadata_and_rejects_gid_swap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rows, metadata = _producer_topology_rows(tmp_path / "topology")
    _overlay_fixture_metadata(monkeypatch, metadata)
    views: list[artifacts._RepositoryView] = []
    try:
        for row in rows:
            for path_key in ("config_path", "attestation_path", "plist_path"):
                path = Path(str(row[path_key]))
                views.append(
                    artifacts._RepositoryView(
                        path,
                        security_policy=artifacts._topology_object_security_policy(
                            row,
                            path_key=path_key,
                            expected_device=path.stat().st_dev,
                        ),
                    )
                )
        for view in views:
            view.revalidate()
    finally:
        for view in reversed(views):
            view.close()

    first = Path(str(rows[0]["config_path"]))
    wrong = {**metadata, first: (0, int(rows[1]["worker_gid"]), 0o440)}
    with monkeypatch.context() as swapped:
        _overlay_fixture_metadata(swapped, wrong)
        with pytest.raises(artifacts.CapacityHostArtifactError, match="SOURCE_METADATA_INVALID"):
            artifacts._RepositoryView(
                first,
                security_policy=artifacts._topology_object_security_policy(
                    rows[0],
                    path_key="config_path",
                    expected_device=first.stat().st_dev,
                ),
            )


def test_exact_topology_policy_refuses_directory_substitution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    substituted = tmp_path / "worker-codex-pro-01.json"
    substituted.mkdir(mode=0o755)
    identity = (substituted.stat().st_dev, substituted.stat().st_ino)
    expected_device = substituted.stat().st_dev
    original_fstat = os.fstat
    original_stat = os.stat

    def overlay(info: os.stat_result) -> os.stat_result | _StatOverlay:
        if (info.st_dev, info.st_ino) == identity:
            return _StatOverlay(
                info,
                st_mode=stat.S_IFDIR | 0o440,
                st_uid=0,
                st_gid=454,
            )
        return info

    monkeypatch.setattr(os, "fstat", lambda descriptor: overlay(original_fstat(descriptor)))
    monkeypatch.setattr(
        os, "stat", lambda *args, **kwargs: overlay(original_stat(*args, **kwargs))
    )
    policy = artifacts._topology_object_security_policy(
        {
            "worker_gid": 454,
            "config_path": str(substituted),
        },
        path_key="config_path",
        expected_device=expected_device,
    )
    with pytest.raises(
        artifacts.CapacityHostArtifactError, match="SOURCE_METADATA_INVALID"
    ):
        artifacts._RepositoryView(substituted, security_policy=policy)


def test_retained_rollback_accepts_exact_moved_artifact_metadata_and_rejects_substitution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rows, topology_metadata = _producer_topology_rows(tmp_path / "topology")
    archive = tmp_path / "rollback-drill-fixture"
    archive.mkdir(mode=0o700)
    metadata: dict[Path, tuple[int, int, int]] = {archive: (0, 0, 0o700)}
    artifacts_rows: list[dict[str, str]] = []
    ordered_paths = [
        Path(str(row[path_key]))
        for row in rows
        for path_key in ("config_path", "attestation_path", "plist_path")
    ]
    for index, original in enumerate(ordered_paths, start=1):
        child = archive / f"{index}-{original.name}"
        expected = topology_metadata[original]
        _write_metadata_fixture(child, original.read_bytes(), expected[2])
        metadata[child] = expected
        artifacts_rows.append(
            {"name": child.name, "sha256": hashlib.sha256(child.read_bytes()).hexdigest()}
        )
    receipt = archive / "rollback-receipt.json"
    _write_metadata_fixture(receipt, b'{"outcome":"SHRINK_ONLY_ROLLBACK_PASS"}\n', 0o400)
    metadata[receipt] = (0, 0, 0o400)
    drill = {"artifacts": artifacts_rows}
    _overlay_fixture_metadata(monkeypatch, metadata)
    policy = artifacts._rollback_object_security_policy(
        rows,
        drill,
        expected_device=archive.stat().st_dev,
    )
    view = artifacts._RepositoryView(archive, security_policy=policy)
    try:
        view.revalidate()
    finally:
        view.close()

    first = archive / artifacts_rows[0]["name"]
    wrong = {**metadata, first: (0, 455, 0o440)}
    with monkeypatch.context() as substituted:
        _overlay_fixture_metadata(substituted, wrong)
        with pytest.raises(artifacts.CapacityHostArtifactError, match="SOURCE_METADATA_INVALID"):
            artifacts._RepositoryView(archive, security_policy=policy)


def test_retained_legacy_accepts_each_canonical_producer_metadata_and_rejects_union(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixtures = (
        ("control-config", tmp_path / "config" / "control.json", 0, 450, 0o440),
        ("worker-config", tmp_path / "config" / "worker-codex.json", 0, 451, 0o440),
        (
            "control-plist",
            tmp_path / "LaunchDaemons" / "com.mastermind.executive.control.plist",
            0,
            0,
            0o644,
        ),
        (
            "worker-plist",
            tmp_path / "LaunchDaemons" / "com.mastermind.executive.worker.codex.plist",
            0,
            0,
            0o644,
        ),
    )
    metadata = {path: (uid, gid, mode) for _role, path, uid, gid, mode in fixtures}
    for _role, path, _uid, _gid, mode in fixtures:
        _write_metadata_fixture(path, f"{path.name}\n".encode("ascii"), mode)
    _overlay_fixture_metadata(monkeypatch, metadata)
    views: list[artifacts._RepositoryView] = []
    try:
        for role, path, _uid, _gid, _mode in fixtures:
            views.append(
                artifacts._RepositoryView(
                    path,
                    security_policy=artifacts._legacy_object_security_policy(
                        role, expected_device=path.stat().st_dev
                    ),
                )
            )
        for view in views:
            view.revalidate()
    finally:
        for view in reversed(views):
            view.close()

    worker = fixtures[1][1]
    wrong = {**metadata, worker: (0, 450, 0o440)}
    with monkeypatch.context() as substituted:
        _overlay_fixture_metadata(substituted, wrong)
        with pytest.raises(artifacts.CapacityHostArtifactError, match="SOURCE_METADATA_INVALID"):
            artifacts._RepositoryView(
                worker,
                security_policy=artifacts._legacy_object_security_policy(
                    "worker-config", expected_device=worker.stat().st_dev
                ),
            )

"""Capacity host transport cases; shared helpers retain their original owner."""
from __future__ import annotations

from tests.test_capacity_host_artifacts import (
    Path,
    _StatOverlay,
    _complete_repository,
    _git,
    _inventory_bytes,
    _write_noncanonical_v2_zip,
    _write_v2_archive,
    artifacts,
    canonical_native_tmp_leaf,
    contract,
    hashlib,
    json,
    os,
    pytest,
    re,
    stat,
    struct,
    subprocess,
    zipfile,
)


@pytest.mark.parametrize("transport_version", ("v2", "v3"))
def test_complete_materializer_preserves_manifest_nonexecutable_script_mode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    transport_version: str,
) -> None:
    source, _commit, _nonmaterial_oid = _complete_repository(tmp_path, monkeypatch)
    script_relative = next(
        relative
        for relative in contract.PRODUCER_MATERIAL_PATHS
        if relative.startswith("scripts/")
    )
    script = source / script_relative
    script.chmod(0o644)
    _git(source, "add", script_relative)
    _git(source, "commit", "-qm", "fixture nonexecutable script")
    commit = _git(source, "rev-parse", "HEAD")
    monkeypatch.setattr(artifacts, "PRODUCER_COMMIT", commit, raising=False)
    archive = tmp_path / f"complete-transport-{transport_version}.zip"
    checkout = tmp_path / f"complete-checkout-{transport_version}"
    builder = getattr(artifacts, f"build_source_transport_{transport_version}")
    materializer = getattr(
        artifacts, f"materialize_source_transport_{transport_version}"
    )

    manifest = builder(source, archive, commit=commit)
    assert next(
        row["mode"] for row in manifest["material"] if row["path"] == script_relative
    ) == "100644"

    materializer(archive, checkout, expected_commit=commit)

    assert stat.S_IMODE((checkout / script_relative).stat().st_mode) == 0o444
    assert _git(checkout, "status", "--porcelain=v1", "--untracked-files=all") == ""


@pytest.mark.parametrize("transport_version", ("v2", "v3"))
def test_complete_materializer_verifies_through_retained_destination_parent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    transport_version: str,
) -> None:
    source, commit, _nonmaterial_oid = _complete_repository(tmp_path, monkeypatch)
    archive = tmp_path / f"retained-parent-{transport_version}.zip"
    checkout = tmp_path / f"retained-parent-{transport_version}"
    builder = getattr(artifacts, f"build_source_transport_{transport_version}")
    materializer = getattr(
        artifacts, f"materialize_source_transport_{transport_version}"
    )
    manifest = builder(source, archive, commit=commit)
    original_view = artifacts._RepositoryView
    observed: list[tuple[int | None, str | None]] = []

    def observe_view(
        root: Path, *args: object, **kwargs: object
    ) -> artifacts._RepositoryView:
        observed.append(
            (
                kwargs.get("parent_descriptor"),
                kwargs.get("root_name"),
            )
        )
        return original_view(root, *args, **kwargs)

    monkeypatch.setattr(artifacts, "_RepositoryView", observe_view)

    assert materializer(archive, checkout, expected_commit=commit) == manifest
    assert len(observed) == 1
    assert isinstance(observed[0][0], int)
    assert observed[0][1] == checkout.name


def test_complete_transport_v2_binds_nonmaterial_closure_and_exact_archive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, commit, nonmaterial_oid = _complete_repository(tmp_path, monkeypatch)
    archive_path = tmp_path / "complete-v2.zip"

    manifest = artifacts.build_source_transport_v2(
        source, archive_path, commit=commit
    )
    rows = artifacts.enumerate_reachable_objects(source, commit)
    inventory_bytes = _inventory_bytes(rows)
    assert nonmaterial_oid in {row.oid for row in rows}
    assert manifest == {
        "schema_version": "mastermind.capacity_source_transport/v2",
        "repository": "mastermindx-market-intelligence/macro",
        "commit": commit,
        "object_format": "sha1",
        "closure_kind": "complete_reachable_commit_graph",
        "payload_sha256": manifest["payload_sha256"],
        "object_count": len(rows),
        "object_inventory_sha256": hashlib.sha256(inventory_bytes).hexdigest(),
        "material": manifest["material"],
    }
    assert [row["path"] for row in manifest["material"]] == list(
        contract.PRODUCER_MATERIAL_PATHS
    )

    with zipfile.ZipFile(archive_path) as archive:
        infos = archive.infolist()
        assert [info.filename for info in infos] == ["manifest.json", "payload.pack"]
        assert archive.comment == b""
        for info in infos:
            assert info.date_time == (1980, 1, 1, 0, 0, 0)
            assert info.create_system == 3
            assert info.compress_type == zipfile.ZIP_STORED
            assert info.flag_bits & 0x1 == 0
            assert info.extra == b""
            assert info.comment == b""
            assert stat.S_IMODE(info.external_attr >> 16) == 0o400

    extracted = tmp_path / "complete-extracted"
    assert artifacts.extract_source_transport_v2(
        archive_path, extracted, expected_commit=commit
    ) == manifest
    checkout = tmp_path / "complete-installed"
    assert artifacts.materialize_source_transport_v2(
        archive_path, checkout, expected_commit=commit
    ) == manifest
    evidence = artifacts.verify_complete_repository(checkout, manifest)
    assert evidence.object_count == manifest["object_count"]
    assert evidence.object_inventory_sha256 == manifest["object_inventory_sha256"]
    assert re.fullmatch(r"[0-9a-f]{64}", evidence.source_tree_sha256)
    assert not list((checkout / ".git" / "objects" / "pack").glob("*.promisor"))
    assert "partialclone" not in _git(checkout, "config", "--local", "--list").lower()


def test_complete_transport_v2_semantic_inventory_survives_different_pack_layouts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, commit, _nonmaterial_oid = _complete_repository(tmp_path, monkeypatch)
    first_path = tmp_path / "first.zip"
    first = artifacts.build_source_transport_v2(source, first_path, commit=commit)
    rows = artifacts.enumerate_reachable_objects(source, commit)
    object_input = b"".join(f"{row.oid}\n".encode("ascii") for row in rows)
    alternate_payload = subprocess.run(
        [
            "/usr/bin/git",
            "--no-replace-objects",
            "-C",
            str(source),
            "pack-objects",
            "--stdout",
            "--window=0",
            "--depth=0",
        ],
        input=object_input,
        check=True,
        capture_output=True,
        env=artifacts._git_environment(),
    ).stdout
    with zipfile.ZipFile(first_path) as archive:
        first_payload = archive.read("payload.pack")
    assert alternate_payload != first_payload

    second = dict(first)
    second["payload_sha256"] = hashlib.sha256(alternate_payload).hexdigest()
    second_path = tmp_path / "second.zip"
    _write_v2_archive(second_path, second, alternate_payload)
    first_checkout = tmp_path / "first-checkout"
    second_checkout = tmp_path / "second-checkout"
    artifacts.materialize_source_transport_v2(first_path, first_checkout, expected_commit=commit)
    artifacts.materialize_source_transport_v2(second_path, second_checkout, expected_commit=commit)
    first_evidence = artifacts.verify_complete_repository(first_checkout, first)
    second_evidence = artifacts.verify_complete_repository(second_checkout, second)
    assert first_evidence.object_count == second_evidence.object_count
    assert (
        first_evidence.object_inventory_sha256
        == second_evidence.object_inventory_sha256
    )
    assert first["payload_sha256"] != second["payload_sha256"]
    assert hashlib.sha256(first_path.read_bytes()).hexdigest() != hashlib.sha256(
        second_path.read_bytes()
    ).hexdigest()


@pytest.mark.parametrize(
    "field,value",
    (
        ("object_count", 1),
        ("object_inventory_sha256", "f" * 64),
    ),
)
def test_complete_materializer_refuses_manifest_object_inventory_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    value: object,
) -> None:
    source, commit, _nonmaterial_oid = _complete_repository(tmp_path, monkeypatch)
    valid_path = tmp_path / "valid.zip"
    manifest = artifacts.build_source_transport_v2(source, valid_path, commit=commit)
    with zipfile.ZipFile(valid_path) as archive:
        payload = archive.read("payload.pack")
    drifted = dict(manifest)
    drifted[field] = value
    drifted_path = tmp_path / f"drifted-{field}.zip"
    _write_v2_archive(drifted_path, drifted, payload)
    with pytest.raises(artifacts.CapacityHostArtifactError, match="OBJECT_INVENTORY"):
        artifacts.materialize_source_transport_v2(
            drifted_path,
            tmp_path / f"drifted-{field}",
            expected_commit=commit,
        )


@pytest.mark.parametrize("mutation", ("type", "size"))
def test_complete_materializer_refuses_semantic_object_type_or_size_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
) -> None:
    source, commit, _nonmaterial_oid = _complete_repository(tmp_path, monkeypatch)
    valid_path = tmp_path / "semantic-valid.zip"
    manifest = artifacts.build_source_transport_v2(source, valid_path, commit=commit)
    rows = artifacts.enumerate_reachable_objects(source, commit)
    with zipfile.ZipFile(valid_path) as archive:
        payload = archive.read("payload.pack")
    drifted_rows: list[bytes] = []
    for index, row in enumerate(rows):
        object_type = row.object_type
        size = row.size
        if index == 0 and mutation == "type":
            object_type = "blob" if object_type != "blob" else "tree"
        if index == 0 and mutation == "size":
            size += 1
        drifted_rows.append(f"{row.oid} {object_type} {size}\n".encode("ascii"))
    drifted = dict(manifest)
    drifted["object_inventory_sha256"] = hashlib.sha256(
        b"".join(drifted_rows)
    ).hexdigest()
    drifted_path = tmp_path / f"semantic-{mutation}.zip"
    _write_v2_archive(drifted_path, drifted, payload)
    with pytest.raises(artifacts.CapacityHostArtifactError, match="OBJECT_INVENTORY"):
        artifacts.materialize_source_transport_v2(
            drifted_path,
            tmp_path / f"semantic-{mutation}",
            expected_commit=commit,
        )


def test_complete_transport_v2_streams_pack_and_refuses_pack_trailer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, commit, _nonmaterial_oid = _complete_repository(tmp_path, monkeypatch)
    valid_path = tmp_path / "valid.zip"
    manifest = artifacts.build_source_transport_v2(source, valid_path, commit=commit)
    with zipfile.ZipFile(valid_path) as archive:
        payload = archive.read("payload.pack") + b"trailer"
    invalid = dict(manifest)
    invalid["payload_sha256"] = hashlib.sha256(payload).hexdigest()
    invalid_path = tmp_path / "trailer.zip"
    _write_v2_archive(invalid_path, invalid, payload)
    with pytest.raises(artifacts.CapacityHostArtifactError, match="PACK"):
        artifacts.extract_source_transport_v2(
            invalid_path, tmp_path / "trailer-extract", expected_commit=commit
        )


def test_complete_transport_v2_does_not_full_buffer_pack_or_archive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, commit, _nonmaterial_oid = _complete_repository(tmp_path, monkeypatch)
    archive_path = tmp_path / "streamed.zip"
    manifest = artifacts.build_source_transport_v2(source, archive_path, commit=commit)
    original_read_bytes = Path.read_bytes
    original_zip_read = zipfile.ZipFile.read

    def reject_full_buffer(path: Path) -> bytes:
        if path.suffix in {".zip", ".pack"}:
            raise AssertionError("v2 transport pack/archive must be streamed")
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", reject_full_buffer)

    def reject_archive_read(
        archive: zipfile.ZipFile,
        name: object,
        password: bytes | None = None,
    ) -> bytes:
        if name == "payload.pack" or getattr(name, "filename", None) == "payload.pack":
            raise AssertionError("v2 payload must use bounded ZipExtFile reads")
        return original_zip_read(archive, name, password)

    monkeypatch.setattr(zipfile.ZipFile, "read", reject_archive_read)
    artifacts.extract_source_transport_v2(
        archive_path, tmp_path / "streamed-extract", expected_commit=commit
    )
    checkout = tmp_path / "streamed-checkout"
    artifacts.materialize_source_transport_v2(
        archive_path, checkout, expected_commit=commit
    )
    assert artifacts.verify_complete_repository(checkout, manifest).object_count == manifest[
        "object_count"
    ]


def test_complete_materializer_refuses_removed_nonmaterial_blob_without_promisor_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, commit, nonmaterial_oid = _complete_repository(tmp_path, monkeypatch)
    valid_path = tmp_path / "complete-valid.zip"
    manifest = artifacts.build_source_transport_v2(source, valid_path, commit=commit)
    rows = tuple(
        row
        for row in artifacts.enumerate_reachable_objects(source, commit)
        if row.oid != nonmaterial_oid
    )
    payload = subprocess.run(
        [
            "/usr/bin/git",
            "--no-replace-objects",
            "-C",
            str(source),
            "pack-objects",
            "--stdout",
        ],
        input=b"".join(f"{row.oid}\n".encode("ascii") for row in rows),
        check=True,
        capture_output=True,
        env=artifacts._git_environment(),
    ).stdout
    incomplete = dict(manifest)
    incomplete["payload_sha256"] = hashlib.sha256(payload).hexdigest()
    incomplete["object_count"] = len(rows)
    incomplete["object_inventory_sha256"] = hashlib.sha256(
        _inventory_bytes(rows)
    ).hexdigest()
    incomplete_path = tmp_path / "incomplete-nonmaterial.zip"
    _write_v2_archive(incomplete_path, incomplete, payload)

    with pytest.raises(artifacts.CapacityHostArtifactError):
        artifacts.materialize_source_transport_v2(
            incomplete_path,
            tmp_path / "incomplete-nonmaterial",
            expected_commit=commit,
        )


@pytest.mark.parametrize(
    "mutation",
    (
        "local_version",
        "local_flag",
        "local_crc",
        "local_size",
        "central_version",
        "central_extract_version",
        "central_flag",
        "central_crc",
        "central_disk",
        "central_internal_attributes",
        "eocd_disk",
        "eocd_start_disk",
        "eocd_count",
        "name",
        "prefix",
        "suffix",
        "archive_comment",
        "member_comment",
        "extra",
        "encryption",
        "compression",
        "data_descriptor",
        "zip64",
    ),
)
def test_complete_transport_v2_refuses_every_noncanonical_zip_record_field(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
) -> None:
    source, commit, _nonmaterial_oid = _complete_repository(tmp_path, monkeypatch)
    valid = tmp_path / "canonical.zip"
    artifacts.build_source_transport_v2(source, valid, commit=commit)
    invalid = tmp_path / f"noncanonical-{mutation}.zip"
    _write_noncanonical_v2_zip(valid, invalid, mutation)
    with pytest.raises(
        (artifacts.CapacityHostArtifactError, zipfile.BadZipFile, RuntimeError)
    ):
        artifacts.extract_source_transport_v2(
            invalid,
            tmp_path / f"extract-{mutation}",
            expected_commit=commit,
        )


def test_v2_zip32_effective_boundary_refuses_before_python_writes_zip64(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Keep the artificial limit above the complete small archive framing so this
    # isolates Python's 1.05 member-size preflight rather than its EOCD offset.
    monkeypatch.setattr(zipfile, "ZIP64_LIMIT", 10_000)
    safe_payload = tmp_path / "safe.pack"
    safe_payload.write_bytes(b"s" * 9_523)
    safe_output = tmp_path / "safe.zip"
    artifacts._write_transport_v2_archive(safe_output, {}, safe_payload)
    with zipfile.ZipFile(safe_output) as archive:
        assert all(info.extra == b"" for info in archive.infolist())

    unsafe_payload = tmp_path / "unsafe.pack"
    unsafe_payload.write_bytes(b"u" * 9_524)
    unsafe_output = tmp_path / "unsafe.zip"
    with pytest.raises(
        artifacts.CapacityHostArtifactError,
        match="TRANSPORT_V2_ZIP32_LIMIT_EXCEEDED",
    ):
        artifacts._write_transport_v2_archive(unsafe_output, {}, unsafe_payload)
    assert not unsafe_output.exists()


def test_complete_transport_v3_is_canonical_zip64_and_materializes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, commit, _nonmaterial_oid = _complete_repository(tmp_path, monkeypatch)
    archive_path = tmp_path / "complete-v3.zip"
    manifest = artifacts.build_source_transport_v3(
        source, archive_path, commit=commit
    )
    assert manifest["schema_version"] == artifacts.TRANSPORT_SCHEMA_V3

    with zipfile.ZipFile(archive_path) as archive:
        infos = archive.infolist()
        assert [info.filename for info in infos] == ["manifest.json", "payload.pack"]
        assert archive.comment == b""
        assert infos[0].extract_version == 20
        assert infos[0].create_version == 20
        assert infos[0].extra == b""
        assert infos[1].extract_version == 45
        assert infos[1].create_version == 45
        assert infos[1].extra == struct.pack(
            "<HHQQ", 0x0001, 16, infos[1].file_size, infos[1].file_size
        )
        assert all(info.flag_bits == 0 for info in infos)
        assert all(info.compress_type == zipfile.ZIP_STORED for info in infos)

    raw = archive_path.read_bytes()
    assert raw.count(b"PK\x06\x06") == 1
    assert raw.count(b"PK\x06\x07") == 1
    assert raw.count(b"PK\x05\x06") == 1
    assert raw.endswith(b"\x00\x00")
    legacy_eocd = raw.rindex(b"PK\x05\x06")
    assert struct.unpack_from("<I", raw, legacy_eocd + 16)[0] == 0xFFFFFFFF

    extracted = tmp_path / "v3-extracted"
    assert artifacts.extract_source_transport_v3(
        archive_path, extracted, expected_commit=commit
    ) == manifest
    checkout = tmp_path / "v3-checkout"
    assert artifacts.materialize_source_transport_v3(
        archive_path, checkout, expected_commit=commit
    ) == manifest
    evidence = artifacts.verify_complete_repository(checkout, manifest)
    assert evidence.object_count == manifest["object_count"]
    assert evidence.object_inventory_sha256 == manifest["object_inventory_sha256"]


def test_v3_writer_crosses_zip32_boundary_without_buffering_or_schema_reinterpretation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(zipfile, "ZIP64_LIMIT", 10_000)
    payload = tmp_path / "large-for-artificial-zip32.pack"
    payload.write_bytes(b"p" * 9_524)
    output = tmp_path / "canonical-v3.zip"
    manifest = {
        "schema_version": artifacts.TRANSPORT_SCHEMA_V3,
        "payload_sha256": hashlib.sha256(payload.read_bytes()).hexdigest(),
    }
    original_read_bytes = Path.read_bytes

    def reject_pack_buffer(path: Path) -> bytes:
        if path.suffix == ".pack":
            raise AssertionError("v3 payload must be streamed")
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", reject_pack_buffer)
    artifacts._write_transport_v3_archive(output, manifest, payload)
    with zipfile.ZipFile(output) as archive:
        info = archive.getinfo("payload.pack")
        assert info.file_size == 9_524
        assert info.extra == struct.pack("<HHQQ", 0x0001, 16, 9_524, 9_524)
        with archive.open(info) as source:
            assert hashlib.sha256(source.read()).hexdigest() == manifest["payload_sha256"]


def test_v2_and_v3_complete_transports_refuse_cross_schema_interpretation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, commit, _nonmaterial_oid = _complete_repository(tmp_path, monkeypatch)
    v2 = tmp_path / "v2.zip"
    v3 = tmp_path / "v3.zip"
    artifacts.build_source_transport_v2(source, v2, commit=commit)
    artifacts.build_source_transport_v3(source, v3, commit=commit)
    with pytest.raises(artifacts.CapacityHostArtifactError):
        artifacts.extract_source_transport_v3(
            v2, tmp_path / "v2-as-v3", expected_commit=commit
        )
    with pytest.raises(artifacts.CapacityHostArtifactError):
        artifacts.extract_source_transport_v2(
            v3, tmp_path / "v3-as-v2", expected_commit=commit
        )


@pytest.mark.parametrize("record", ("zip64_eocd", "zip64_locator", "legacy_eocd"))
def test_complete_transport_v3_refuses_noncanonical_end_records(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, record: str
) -> None:
    source, commit, _nonmaterial_oid = _complete_repository(tmp_path, monkeypatch)
    valid = tmp_path / "valid-v3.zip"
    artifacts.build_source_transport_v3(source, valid, commit=commit)
    raw = bytearray(valid.read_bytes())
    offsets = {
        "zip64_eocd": raw.rindex(b"PK\x06\x06"),
        "zip64_locator": raw.rindex(b"PK\x06\x07"),
        "legacy_eocd": raw.rindex(b"PK\x05\x06"),
    }
    raw[offsets[record] + 4] ^= 0x01
    invalid = tmp_path / f"invalid-{record}.zip"
    invalid.write_bytes(raw)
    with pytest.raises(
        (artifacts.CapacityHostArtifactError, zipfile.BadZipFile, RuntimeError)
    ):
        artifacts.extract_source_transport_v3(
            invalid, tmp_path / f"extract-{record}", expected_commit=commit
        )


@pytest.mark.parametrize(
    "mutation",
    (
        "manifest_local_version",
        "manifest_local_flag",
        "manifest_local_crc",
        "manifest_local_size",
        "payload_local_version",
        "payload_local_flag",
        "payload_local_crc",
        "payload_local_size",
        "payload_local_extra_length",
        "payload_local_extra_tag",
        "manifest_central_version",
        "manifest_central_extract_version",
        "manifest_central_flag",
        "manifest_central_crc",
        "manifest_central_attributes",
        "manifest_central_offset",
        "payload_central_version",
        "payload_central_extract_version",
        "payload_central_flag",
        "payload_central_crc",
        "payload_central_size",
        "payload_central_extra_length",
        "payload_central_attributes",
        "payload_central_offset",
        "payload_central_extra_tag",
        "zip64_record_size",
        "zip64_version",
        "zip64_disk",
        "zip64_count",
        "zip64_central_size",
        "zip64_central_offset",
        "locator_disk",
        "locator_offset",
        "locator_total_disks",
        "legacy_count",
        "legacy_central_size",
        "legacy_central_offset",
        "prefix",
        "suffix",
    ),
)
def test_complete_transport_v3_refuses_every_noncanonical_record_field(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutation: str
) -> None:
    source, commit, _nonmaterial_oid = _complete_repository(tmp_path, monkeypatch)
    valid = tmp_path / "canonical-v3.zip"
    artifacts.build_source_transport_v3(source, valid, commit=commit)
    with zipfile.ZipFile(valid) as archive:
        manifest_local = archive.getinfo("manifest.json").header_offset
        payload_local = archive.getinfo("payload.pack").header_offset
    raw = bytearray(valid.read_bytes())
    legacy = raw.rindex(b"PK\x05\x06")
    locator = legacy - 20
    zip64 = struct.unpack_from("<Q", raw, locator + 8)[0]
    central = struct.unpack_from("<Q", raw, zip64 + 48)[0]
    manifest_central = central
    payload_central = manifest_central + 46 + len("manifest.json")
    offsets = {
        "manifest_local_version": manifest_local + 4,
        "manifest_local_flag": manifest_local + 6,
        "manifest_local_crc": manifest_local + 14,
        "manifest_local_size": manifest_local + 18,
        "payload_local_version": payload_local + 4,
        "payload_local_flag": payload_local + 6,
        "payload_local_crc": payload_local + 14,
        "payload_local_size": payload_local + 18,
        "payload_local_extra_length": payload_local + 28,
        "payload_local_extra_tag": payload_local + 30 + len("payload.pack"),
        "manifest_central_version": manifest_central + 4,
        "manifest_central_extract_version": manifest_central + 6,
        "manifest_central_flag": manifest_central + 8,
        "manifest_central_crc": manifest_central + 16,
        "manifest_central_attributes": manifest_central + 38,
        "manifest_central_offset": manifest_central + 42,
        "payload_central_version": payload_central + 4,
        "payload_central_extract_version": payload_central + 6,
        "payload_central_flag": payload_central + 8,
        "payload_central_crc": payload_central + 16,
        "payload_central_size": payload_central + 20,
        "payload_central_extra_length": payload_central + 30,
        "payload_central_attributes": payload_central + 38,
        "payload_central_offset": payload_central + 42,
        "payload_central_extra_tag": payload_central + 46 + len("payload.pack"),
        "zip64_record_size": zip64 + 4,
        "zip64_version": zip64 + 12,
        "zip64_disk": zip64 + 16,
        "zip64_count": zip64 + 24,
        "zip64_central_size": zip64 + 40,
        "zip64_central_offset": zip64 + 48,
        "locator_disk": locator + 4,
        "locator_offset": locator + 8,
        "locator_total_disks": locator + 16,
        "legacy_count": legacy + 8,
        "legacy_central_size": legacy + 12,
        "legacy_central_offset": legacy + 16,
    }
    if mutation == "prefix":
        raw = bytearray(b"x") + raw
    elif mutation == "suffix":
        raw.extend(b"x")
    else:
        raw[offsets[mutation]] ^= 0x01
    invalid = tmp_path / f"noncanonical-v3-{mutation}.zip"
    invalid.write_bytes(raw)
    with pytest.raises(
        (artifacts.CapacityHostArtifactError, zipfile.BadZipFile, RuntimeError)
    ):
        artifacts.extract_source_transport_v3(
            invalid, tmp_path / f"extract-{mutation}", expected_commit=commit
        )


def test_v3_transport_cap_is_finite_and_inclusive() -> None:
    artifacts._require_v3_transport_size(artifacts._V3_TRANSPORT_MAX_BYTES)
    with pytest.raises(
        artifacts.CapacityHostArtifactError,
        match="TRANSPORT_V3_SIZE_LIMIT_EXCEEDED",
    ):
        artifacts._require_v3_transport_size(artifacts._V3_TRANSPORT_MAX_BYTES + 1)


def test_complete_manifest_dispatch_refuses_unknown_schema() -> None:
    with pytest.raises(
        artifacts.CapacityHostArtifactError,
        match="TRANSPORT_COMPLETE_MANIFEST_SCHEMA_INVALID",
    ):
        artifacts.validate_complete_transport_manifest(
            {"schema_version": "mastermind.capacity_source_transport/v999"},
            expected_commit="a" * 40,
        )


@pytest.mark.parametrize("kind", ("file", "directory"))
def test_canonical_native_tmp_and_alias_retain_the_same_source(
    canonical_native_tmp_leaf, kind: str,
) -> None:
    root, leaf = canonical_native_tmp_leaf
    alias = leaf if kind == "file" else root
    canonical = alias.resolve()
    assert canonical.parts[:3] == ("/", "private", "tmp")
    identity = alias.stat()
    assert (identity.st_dev, identity.st_ino) == (
        canonical.stat().st_dev, canonical.stat().st_ino
    )
    snapshots = []
    for target in (alias, canonical):
        view = artifacts._RepositoryView(target)
        try:
            retained = os.fstat(view.root_descriptor)
            snapshots.append((retained.st_dev, retained.st_ino))
            assert view.read_bytes("." if kind == "file" else leaf.name,
                                   maximum_bytes=1024) == b"same retained source bytes\n"
            view.revalidate()
        finally:
            view.close()
    assert snapshots == [(identity.st_dev, identity.st_ino)] * 2


def test_canonical_native_tmp_preserves_complete_materialized_repository(
    canonical_native_tmp_leaf, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _leaf = canonical_native_tmp_leaf
    # Exercise the established real Git/pack/archive/materialization contract,
    # then read the very same closed repository through its canonical name.
    test_complete_transport_v2_binds_nonmaterial_closure_and_exact_archive(root, monkeypatch)
    with zipfile.ZipFile(root / "complete-v2.zip") as archive:
        manifest = json.loads(archive.read("manifest.json"))
    checkout = root / "complete-installed"
    assert checkout.stat().st_ino == checkout.resolve().stat().st_ino
    alias = artifacts.verify_complete_repository(checkout, manifest)
    canonical = artifacts.verify_complete_repository(checkout.resolve(), manifest)
    assert canonical == alias


def test_canonical_native_tmp_does_not_trust_nested_tmp_names(
    canonical_native_tmp_leaf,
) -> None:
    root, _leaf = canonical_native_tmp_leaf
    misleading = root / "private" / "tmp"
    misleading.mkdir(parents=True)
    misleading.chmod(0o1777)
    leaf = misleading / "evidence.json"
    leaf.write_bytes(b"not a native traversal root\n")
    leaf.chmod(0o444)
    with pytest.raises(artifacts.CapacityHostArtifactError,
                       match="SOURCE_METADATA_INVALID"):
        view = artifacts._RepositoryView(leaf.resolve())
        view.close()


@pytest.mark.parametrize("phase", ("open", "revalidate"))
@pytest.mark.parametrize("violation", (
    "type", "owner", "group", "mode", "device", "link", "flags", "acl", "xattr",
))
def test_canonical_native_tmp_keeps_exact_security_checks(
    canonical_native_tmp_leaf, monkeypatch: pytest.MonkeyPatch,
    phase: str, violation: str,
) -> None:
    _root, leaf = canonical_native_tmp_leaf
    target = leaf.resolve()
    native = Path("/private/tmp").stat()
    native_identity = (native.st_dev, native.st_ino)
    original_fstat, original_stat = os.fstat, os.stat
    original_acl = artifacts._descriptor_has_extended_acl
    original_xattrs = artifacts._descriptor_extended_attribute_names
    changes = {
        "type": {"st_mode": stat.S_IFREG | 0o1777},
        "owner": {"st_uid": 10000},
        "group": {"st_gid": 10000},
        "mode": {"st_mode": stat.S_IFDIR | 0o0777},
        "device": {"st_dev": native.st_dev + 1},
        "link": {"st_nlink": 0},
        "flags": {"st_flags": 1},
    }.get(violation, {})

    def matches(info):
        return (info.st_dev, info.st_ino) == native_identity

    def overlay(info):
        return _StatOverlay(info, **changes) if matches(info) else info

    # A successful baseline prevents an earlier unrelated refusal from
    # masquerading as coverage of the selected security predicate.
    view = artifacts._RepositoryView(target)
    try:
        assert view.read_bytes(".", maximum_bytes=1024) == b"same retained source bytes\n"
        if phase == "open":
            view.close()
            view = None
        monkeypatch.setattr(os, "fstat", lambda fd: overlay(original_fstat(fd)))
        monkeypatch.setattr(os, "stat", lambda *a, **k: overlay(original_stat(*a, **k)))
        monkeypatch.setattr(artifacts, "_descriptor_has_extended_acl",
            lambda fd: (True if violation == "acl" and matches(original_fstat(fd))
                        else original_acl(fd)))
        monkeypatch.setattr(artifacts, "_descriptor_extended_attribute_names",
            lambda fd: (original_xattrs(fd) | frozenset({b"user.mmx-forbidden"})
                        if violation == "xattr" and matches(original_fstat(fd))
                        else original_xattrs(fd)))
        code = "SOURCE_METADATA_INVALID" if phase == "open" else "SOURCE_VIEW_DRIFT"
        with pytest.raises(artifacts.CapacityHostArtifactError, match=code):
            if phase == "open":
                view = artifacts._RepositoryView(target)
            else:
                view.revalidate()
    finally:
        if view is not None:
            view.close()

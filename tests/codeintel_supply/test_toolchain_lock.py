from __future__ import annotations

import copy
import hashlib
import io
import json
import os
import tarfile
from pathlib import Path

import pytest

from experiments.codeintel_supply import toolchain_lock as locks

ROOT = Path(__file__).resolve().parents[2]
LOCK_PATH = (
    ROOT
    / "research/code_intelligence_fabric/codeintel-experiment-toolchain-lock.v1.json"
)
SCHEMA_PATH = (
    ROOT
    / "research/code_intelligence_fabric/codeintel-experiment-toolchain-lock.schema.json"
)


def _payload() -> dict[str, object]:
    return json.loads(LOCK_PATH.read_text(encoding="utf-8"))


def _tar_bytes(
    entries: list[tuple[str, bytes, int, str]], *, gzip: bool = True
) -> bytes:
    stream = io.BytesIO()
    mode = "w:gz" if gzip else "w"
    with tarfile.open(fileobj=stream, mode=mode) as archive:
        for name, body, file_mode, kind in entries:
            info = tarfile.TarInfo(name)
            info.mode = file_mode
            if kind == "file":
                info.size = len(body)
                archive.addfile(info, io.BytesIO(body))
            elif kind == "directory":
                info.type = tarfile.DIRTYPE
                archive.addfile(info)
            elif kind == "symlink":
                info.type = tarfile.SYMTYPE
                info.linkname = body.decode("utf-8")
                archive.addfile(info)
            elif kind == "fifo":
                info.type = tarfile.FIFOTYPE
                archive.addfile(info)
            else:  # pragma: no cover - test helper misuse
                raise AssertionError(kind)
    return stream.getvalue()


def test_committed_lock_is_closed_and_schema_bound() -> None:
    lock = locks.load_toolchain_lock(LOCK_PATH, schema_path=SCHEMA_PATH)

    assert lock.schema_version == "mastermind.codeintel_experiment_toolchain_lock.v1"
    assert lock.mode == "Z0"
    assert lock.sha256 == hashlib.sha256(LOCK_PATH.read_bytes()).hexdigest()
    assert lock.payload["$schema"] == SCHEMA_PATH.name
    assert lock.payload["build"]["recipe_sha256"] == lock.build_recipe_sha256
    assert lock.payload["acquisition"]["network_enforcement"] == (
        "fresh_user_mount_netns_loopback_relay_parent_unix_gate_landlock_seccomp"
    )
    assert lock.payload["acquisition"]["network_namespace"] == (
        "fresh_user_mount_network_namespace_with_loopback_only"
    )
    assert lock.payload["acquisition"]["gate_mount"] == ("private_read_only_bind_mount")
    assert lock.payload["acquisition"]["relay_endpoint"] == "127.0.0.1:47853"
    assert lock.payload["acquisition"]["parent_gate_transport"] == (
        "pathname_unix_stream"
    )
    assert lock.payload["acquisition"]["client_socket_policy"] == (
        "af_inet_tcp_only_no_fastopen_no_io_uring_no_socket_inheritance"
    )
    assert lock.payload["acquisition"]["minimum_landlock_abi"] == 4
    assert lock.payload["acquisition"]["boundary_receipt"] == (
        "CODEINTEL_PHASE_P_BOUNDARY_V1"
    )
    assert lock.payload["acquisition"]["allowed_host_suffixes"] == (
        "blob.core.windows.net",
    )
    assert lock.payload["universal_ctags"] == {
        "enabled": False,
        "reason": "disabled_until_separately_content_addressed_and_admitted",
    }

    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["additionalProperties"] is False
    assert schema["properties"]["mode"]["const"] == "Z0"


@pytest.mark.parametrize(
    ("target", "needle", "replacement", "expected_code", "expected_detail"),
    [
        (
            "lock",
            '  "mode": "Z0",',
            '  "mode": "Z0",\n  "mode": "Z0",',
            "LOCK_INVALID",
            "duplicate object key",
        ),
        (
            "lock",
            '  "mode": "Z0",',
            '  "mode": NaN,',
            "LOCK_INVALID",
            "non-finite number",
        ),
        (
            "schema",
            '  "type": "object",',
            '  "type": "object",\n  "type": "object",',
            "SCHEMA_INVALID",
            "duplicate object key",
        ),
        (
            "schema",
            '  "type": "object",',
            '  "type": "object",\n  "hostile": Infinity,',
            "SCHEMA_INVALID",
            "non-finite number",
        ),
    ],
)
def test_lock_and_schema_use_the_same_strict_json_decoder(
    tmp_path: Path,
    target: str,
    needle: str,
    replacement: str,
    expected_code: str,
    expected_detail: str,
) -> None:
    hostile = tmp_path / f"hostile-{target}.json"
    source = LOCK_PATH if target == "lock" else SCHEMA_PATH
    body = source.read_text(encoding="utf-8")
    assert body.count(needle) == 1
    hostile.write_text(body.replace(needle, replacement), encoding="utf-8")

    lock_path = hostile if target == "lock" else LOCK_PATH
    schema_path = hostile if target == "schema" else SCHEMA_PATH
    with pytest.raises(locks.ToolchainLockError) as raised:
        locks.load_toolchain_lock(lock_path, schema_path=schema_path)

    assert raised.value.code == expected_code
    assert expected_detail in raised.value.detail


@pytest.mark.parametrize("target", ["lock", "schema"])
def test_lock_and_schema_decoder_is_size_bounded(tmp_path: Path, target: str) -> None:
    oversized = tmp_path / f"oversized-{target}.json"
    oversized.write_bytes(b" " * (locks.STRICT_JSON_MAX_BYTES + 1))

    lock_path = oversized if target == "lock" else LOCK_PATH
    schema_path = oversized if target == "schema" else SCHEMA_PATH
    with pytest.raises(locks.ToolchainLockError) as raised:
        locks.load_toolchain_lock(lock_path, schema_path=schema_path)

    assert raised.value.code == (
        "LOCK_INVALID" if target == "lock" else "SCHEMA_INVALID"
    )
    assert "size ceiling" in raised.value.detail


def test_validated_lock_payload_is_recursively_immutable() -> None:
    lock = locks.load_toolchain_lock(LOCK_PATH, schema_path=SCHEMA_PATH)
    expected = locks.canonical_json_bytes(_payload())

    with pytest.raises(TypeError):
        lock.payload["zoekt"]["go_mod"]["git_blob_sha1"] = "0" * 40  # type: ignore[index]
    with pytest.raises(TypeError):
        lock.payload["acquisition"]["allowed_hosts"][0] = "hostile.invalid"  # type: ignore[index]

    assert lock.payload["zoekt"]["go_mod"]["git_blob_sha1"] == (
        "db33117af57ea746dff8064e70ce56e3721e44ba"
    )
    assert locks.canonical_json_bytes(lock.payload) == expected


def test_authorized_zoekt_and_go_pins_match_primary_objects() -> None:
    lock = locks.load_toolchain_lock(LOCK_PATH, schema_path=SCHEMA_PATH)
    zoekt = lock.payload["zoekt"]
    go = lock.payload["go"]

    assert zoekt["commit"] == "5f833dde1bc4b1a8f99007617b4b721e44506c4f"
    assert zoekt["tree"] == "8135ec1d7329e7f8de43714ac5c7a2bad14bd7b5"
    assert zoekt["module_path"] == "github.com/sourcegraph/zoekt"
    assert zoekt["go_mod"]["git_blob_sha1"] == (
        "db33117af57ea746dff8064e70ce56e3721e44ba"
    )
    assert zoekt["go_sum"]["git_blob_sha1"] == (
        "6f54532eef8a9628275d1aa870c1b26f89987dd0"
    )
    assert zoekt["license"]["git_blob_sha1"] == (
        "261eeb9e9f8b2b4b0d119366dda99c6fd7d35c64"
    )
    assert go["version"] == "1.26.5"
    assert go["archive"]["filename"] == "go1.26.5.linux-amd64.tar.gz"
    assert go["archive"]["sha256"] == (
        "5c2c3b16caefa1d968a94c1daca04a7ca301a496d9b086e17ad77bb81393f053"
    )
    assert go["source"]["commit"] == "c19862e5f8415b4f24b189d065ed739517c548ba"
    assert go["source"]["tree"] == "0bb2fb1cc06c334c36a2a92d2f0b07fea7236d74"


@pytest.mark.parametrize(
    ("path", "replacement"),
    [
        (("zoekt", "commit"), "0" * 40),
        (("zoekt", "tree"), "1" * 40),
        (("zoekt", "module_path"), "sourcegraph/zoekt"),
        # Regression for the stale packet digest superseded by the Sol ruling.
        (("zoekt", "go_mod", "git_blob_sha1"), "a3917455" + "0" * 32),
        (("zoekt", "go_sum", "git_blob_sha1"), "2" * 40),
        (("zoekt", "license", "git_blob_sha1"), "3" * 40),
        (("go", "archive", "sha256"), "4" * 64),
        (("go", "source", "commit"), "5" * 40),
        (("go", "source", "tree"), "6" * 40),
        (("go", "source", "license_blob_sha1"), "7" * 40),
    ],
)
def test_every_alternate_upstream_identity_is_rejected(
    path: tuple[str, ...], replacement: str
) -> None:
    payload = copy.deepcopy(_payload())
    target: dict[str, object] = payload
    for component in path[:-1]:
        target = target[component]  # type: ignore[assignment,index]
    target[path[-1]] = replacement

    with pytest.raises(locks.ToolchainLockError, match="PIN_MISMATCH"):
        locks.validate_lock_payload(payload)


def test_lock_rejects_floating_or_widened_acquisition() -> None:
    for mutation in (
        lambda value: value["zoekt"].__setitem__("commit", "main"),
        lambda value: value["zoekt"].__setitem__(
            "source_url", "https://mirror.invalid/zoekt.git"
        ),
        lambda value: value["go"]["archive"].__setitem__(
            "url", "https://go.dev/dl/go1.26.6.linux-amd64.tar.gz"
        ),
        lambda value: value["acquisition"].__setitem__(
            "allowed_hosts", ["github.com", "example.invalid"]
        ),
        lambda value: value["acquisition"].__setitem__(
            "allowed_host_suffixes", ["example.invalid"]
        ),
        lambda value: value["acquisition"].__setitem__(
            "network_enforcement", "descriptive_only"
        ),
        lambda value: value["acquisition"].__setitem__(
            "network_namespace", "host_network"
        ),
        lambda value: value["acquisition"].__setitem__("gate_mount", "mutable"),
        lambda value: value["acquisition"].__setitem__(
            "relay_endpoint", "127.0.0.2:47853"
        ),
        lambda value: value["acquisition"].__setitem__("parent_gate_transport", "tcp"),
        lambda value: value["acquisition"].__setitem__(
            "client_socket_policy", "ambient"
        ),
        lambda value: value["acquisition"].__setitem__("minimum_landlock_abi", 3),
        lambda value: value["acquisition"].__setitem__(
            "boundary_receipt", "UNVERIFIED"
        ),
        lambda value: value.__setitem__("serena", {"version": "latest"}),
        lambda value: value.__setitem__("mode", "C0"),
    ):
        payload = copy.deepcopy(_payload())
        mutation(payload)
        with pytest.raises(locks.ToolchainLockError):
            locks.validate_lock_payload(payload)


def test_actions_are_full_immutable_commits() -> None:
    lock = locks.load_toolchain_lock(LOCK_PATH, schema_path=SCHEMA_PATH)
    assert lock.payload["actions"] == {
        "checkout": {
            "repository": "actions/checkout",
            "commit": "11bd71901bbe5b1630ceea73d27597364c9af683",
        },
        "download_artifact": {
            "repository": "actions/download-artifact",
            "commit": "d3f86a106a0bac45b974a628896c90dbdf5c8093",
        },
        "upload_artifact": {
            "repository": "actions/upload-artifact",
            "commit": "ea165f8d65b6e75b540449e92b4886f43607fa02",
        },
    }

    payload = copy.deepcopy(_payload())
    payload["actions"]["checkout"]["commit"] = "v4"  # type: ignore[index]
    with pytest.raises(locks.ToolchainLockError, match="PIN_MISMATCH"):
        locks.validate_lock_payload(payload)


def test_git_blob_identity_is_computed_over_git_header_and_bytes() -> None:
    body = b"go 1.25.9\n\ntoolchain go1.26.5\n"
    expected = hashlib.sha1(
        b"blob " + str(len(body)).encode() + b"\0" + body
    ).hexdigest()
    assert locks.git_blob_sha1(body) == expected


def test_archive_validator_accepts_only_bounded_regular_go_tree(tmp_path: Path) -> None:
    archive = tmp_path / "go.tar.gz"
    archive.write_bytes(
        _tar_bytes(
            [
                ("go", b"", 0o755, "directory"),
                ("go/bin", b"", 0o755, "directory"),
                ("go/bin/go", b"go", 0o755, "file"),
                ("go/LICENSE", b"license", 0o644, "file"),
            ]
        )
    )
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()

    members = locks.validate_tar_archive(
        archive,
        expected_sha256=digest,
        expected_top_level="go",
        max_archive_bytes=1024 * 1024,
        max_member_bytes=1024,
        max_total_bytes=4096,
    )

    assert [member.name for member in members] == [
        "go",
        "go/LICENSE",
        "go/bin",
        "go/bin/go",
    ]


@pytest.mark.parametrize(
    "entry",
    [
        ("../escape", b"x", 0o644, "file"),
        ("/absolute", b"x", 0o644, "file"),
        ("go/link", b"../../etc/passwd", 0o777, "symlink"),
        ("go/fifo", b"", 0o644, "fifo"),
        ("go/world", b"x", 0o666, "file"),
        ("other/file", b"x", 0o644, "file"),
    ],
)
def test_archive_validator_rejects_traversal_links_special_and_unsafe_modes(
    tmp_path: Path, entry: tuple[str, bytes, int, str]
) -> None:
    archive = tmp_path / "hostile.tar.gz"
    archive.write_bytes(_tar_bytes([entry]))

    with pytest.raises(locks.ToolchainLockError, match="ARCHIVE_UNSAFE"):
        locks.validate_tar_archive(
            archive,
            expected_top_level="go",
            max_archive_bytes=1024 * 1024,
            max_member_bytes=1024,
            max_total_bytes=4096,
        )


def test_safe_extract_never_follows_preexisting_destination_symlink(
    tmp_path: Path,
) -> None:
    archive = tmp_path / "go.tar.gz"
    archive.write_bytes(
        _tar_bytes(
            [
                ("go", b"", 0o755, "directory"),
                ("go/bin", b"", 0o755, "directory"),
                ("go/bin/go", b"safe", 0o755, "file"),
            ]
        )
    )
    destination = tmp_path / "extract"
    outside = tmp_path / "outside"
    outside.mkdir()
    destination.mkdir()
    os.symlink(outside, destination / "go")

    with pytest.raises(locks.ToolchainLockError, match="DESTINATION_UNSAFE"):
        locks.safe_extract_tar(
            archive,
            destination,
            expected_top_level="go",
            max_archive_bytes=1024 * 1024,
            max_member_bytes=1024,
            max_total_bytes=4096,
        )
    assert list(outside.iterdir()) == []

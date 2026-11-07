"""Isolated retained v5-to-v7 schema-upgrade evidence tests.

Every database, receipt, backup, release root, and config file in these tests
is fixture-owned and disposable.  The synthetic ownership proof mocks the
production module's private Root gate, Control principal lookup, physical host
top, config path, config reader, and release observers to the current fixture
UID; no live Root, cross-UID, network, credential, or process effect is used,
and the existing ``executive_backup`` verifiers keep observing the real test
EUID on the fixture copies.

Disclosed synthetic limitations: this host cannot chown to Root, so the
Root0:ControlGID 0440 configuration gate is demonstrated through the scoped
private seams (``_read_qualified_control_config``/``_control_config_profile``)
plus static source assertions on the production gate, never through a real
cross-UID proof, and the Darwin Root gate itself is neutralised per fixture.
The fixtures use the actual owner layout: ``<top>/control/db/data/
control_plane/executive.sqlite3`` with receipts, lock, barrier and marker in
that same authoritative database directory, ``<top>/control/backups`` beside
it, and a distinct Root-configuration stand-in.

Test isolation: nothing in this module mutates ``os.environ``, global sockets,
processes, or credentials at import.  The network refusal is a scoped autouse
fixture, and a collection-audit test proves the import-time sentinels stayed
unchanged.
"""

from __future__ import annotations

import ast
import hashlib
import inspect
import json
import os
import socket
import sqlite3
import stat
from pathlib import Path

import pytest

# Guard every potential network entry point only for the duration of each
# test, never at import and never for unrelated tests or modules.
def _refuse_network(*args, **kwargs):  # pragma: no cover - guard
    raise AssertionError("fixture tests must not open network connections")


from control_plane import executive_backup as backup  # noqa: E402
from control_plane import executive_runtime as rt  # noqa: E402
from control_plane.executive_runtime import RuntimeProofError  # noqa: E402
from ops.executive_os import autonomy_control  # noqa: E402
from ops.executive_os import schema_upgrade_evidence as evidence  # noqa: E402
from tests.test_executive_backup import (  # noqa: E402
    _exact_v4,
    _populate_v4_evidence,
    _upgrade_test_release_and_census,
)

# Import-time sentinels for the collection-audit proof below.
_COLLECTION_ENVIRONMENT = dict(os.environ)
_COLLECTION_CREATE_CONNECTION = socket.create_connection
_TEST_MODULE_SOURCE = Path(__file__).read_text(encoding="utf-8")

_RECEIPT_NAMES = {
    "P56": backup._UPGRADE_V5_TO_V6_PREFLIGHT_NAME,
    "C56": backup._UPGRADE_V5_TO_V6_COMPLETION_NAME,
    "P67": backup._UPGRADE_V6_TO_V7_PREFLIGHT_NAME,
    "C67": backup._UPGRADE_V6_TO_V7_COMPLETION_NAME,
}


@pytest.fixture(autouse=True)
def _refuse_network_fixture(request, monkeypatch):
    """Scoped process-local network guard; the audit test runs unguarded."""
    if "collection_is_inert" in request.node.name:
        yield
        return
    monkeypatch.setattr(socket, "create_connection", _refuse_network)
    yield


def _write_private(path: Path, raw: bytes) -> None:
    descriptor = os.open(
        path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_CLOEXEC", 0), 0o600
    )
    try:
        os.write(descriptor, raw)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    path.chmod(0o600)


def _exact_v5(path: Path) -> Path:
    _exact_v4(path)
    _populate_v4_evidence(path)
    with sqlite3.connect(path) as connection:
        version, name, statements = rt._MIGRATIONS[4]
        for statement in statements:
            connection.execute(statement)
        connection.execute(
            "INSERT INTO schema_migrations VALUES(?,?,?,?)",
            (version, name, rt._migration_checksum(statements), -105),
        )
    path.chmod(0o600)
    return path


def _state_directory(runtime: Path) -> Path:
    return runtime / "data" / "control_plane"


def _receipt_path(runtime: Path, role: str) -> Path:
    return _state_directory(runtime) / _RECEIPT_NAMES[role]


_REFUSAL = RuntimeProofError


def _rewrite_receipt(path: Path, mutate) -> None:
    value = json.loads(path.read_text())
    mutate(value)
    _write_private(
        path,
        (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode(
            "utf-8"
        ),
    )


def _write_config(path: Path, value) -> None:
    """Rewrite an existing 0440 fixture configuration and restore its gate."""
    path.chmod(0o600)
    _write_private(
        path,
        (
            json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        ).encode("utf-8"),
    )
    path.chmod(0o440)


def _backup_database(runtime: Path, role: str, field: str) -> Path:
    return Path(json.loads(_receipt_path(runtime, role).read_text())[field]["database_path"])


def _snapshot(paths) -> dict:
    return {
        str(path): (
            path.lstat().st_dev,
            path.lstat().st_ino,
            stat.S_IMODE(path.lstat().st_mode),
            path.lstat().st_uid,
            hashlib.sha256(path.read_bytes()).hexdigest(),
        )
        for path in paths
    }


def _chain_paths(runtime: Path, backups: Path) -> list:
    paths = [_receipt_path(runtime, role) for role in _RECEIPT_NAMES]
    for role, field in (
        ("P56", "v5_backup"),
        ("C56", "v6_backup"),
        ("P67", "v6_backup"),
        ("C67", "v7_backup"),
    ):
        database = _backup_database(runtime, role, field)
        paths.append(database)
        paths.append(database.with_suffix(".manifest.json"))
    return paths


def _temp_roots() -> set:
    return set(Path("/tmp").glob("mastermind-executive-upgrade-evidence-*"))


def _descriptor_count() -> int:
    try:
        return len(os.listdir("/dev/fd"))
    except OSError:  # pragma: no cover - non-procfs platform
        return -1


def _fixture_control_config(path: Path, *, control_gid: int):
    """Fixture stand-in for the Root 0440 config gate at the current EUID.

    Identical closed gate to ``_read_qualified_control_config`` (exact 0440,
    single link, no symlink, no ACL, exact uid/gid) except that the required
    uid is the fixture principal because this host cannot chown to Root.
    """
    return autonomy_control._root_json(
        path,
        modes=frozenset({0o440}),
        uid=os.geteuid(),
        gid=control_gid,
    )


def _mock_root(monkeypatch, tmp_path: Path, runtime: Path, backups: Path, config: Path):
    uid, gid = os.geteuid(), os.getgid()
    monkeypatch.setattr(evidence, "_root_darwin_gate", lambda: None)
    monkeypatch.setattr(evidence, "_control_identity", lambda: (uid, gid))
    monkeypatch.setattr(evidence, "_physical_host_top", lambda: tmp_path)
    monkeypatch.setattr(evidence, "_control_config_path", lambda: config)
    monkeypatch.setattr(evidence, "_read_qualified_control_config", _fixture_control_config)
    monkeypatch.setattr(evidence, "_config_namespace_profile", lambda: evidence._CustodyProfile(
        uid=uid, gid=gid, mode=0o700))
    monkeypatch.setattr(
        evidence,
        "_control_config_profile",
        lambda control_uid, control_gid: evidence._CustodyProfile(
            uid=os.geteuid(), gid=control_gid, mode=0o440
        ),
    )
    monkeypatch.setattr(
        evidence,
        "_prove_current_release",
        lambda sha: {
            "release_root": str(tmp_path / sha),
            "release_sha": sha,
            "release_tree_sha": "b" * 40,
            "release_manifest_sha256": "c" * 64,
        },
    )
    monkeypatch.setattr(
        evidence,
        "_verify_pinned_release",
        lambda root, sha, tree: {"commit_sha": sha, "tree_sha": tree, "manifest_sha256": "c" * 64},
    )
    return uid, gid


_BUILD_STATE = {"count": 0}


def _build_chain(tmp_path: Path, monkeypatch):
    _BUILD_STATE["count"] += 1
    top = tmp_path / f"chain-{_BUILD_STATE['count']:02d}"
    top.mkdir(mode=0o700)
    release = _upgrade_test_release_and_census(monkeypatch, top)
    runtime = top / "control" / "db"
    runtime.mkdir(parents=True, mode=0o700)
    data_directory = runtime / "data"
    data_directory.mkdir(mode=0o700)
    state = data_directory / "control_plane"
    state.mkdir(mode=0o700)
    _write_private(state / backup.DEFAULT_SERVICE_LOCK_NAME, b"")
    database = _exact_v5(state / "executive.sqlite3")
    backups = top / "control" / "backups"
    backup.upgrade_v5_to_v6(database, backups, release_sha=release)
    backup.upgrade_v6_to_v7(database, backups, release_sha=release)
    config_directory = top / "control-config"
    config_directory.mkdir(mode=0o700)
    config = config_directory / "control.json"
    _write_private(
        config,
        (
            json.dumps(
                {"runtime_root": str(runtime), "backup_root": str(backups)},
                indent=2,
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8"),
    )
    config.chmod(0o440)
    _mock_root(monkeypatch, top, runtime, backups, config)
    return runtime, backups, config, release


def _open_initial(runtime: Path, release: str):
    return evidence.open_v5_to_v7_evidence(runtime, release)


def _receipt_identity(runtime: Path, role: str) -> dict:
    payload = json.loads(_receipt_path(runtime, role).read_text())
    if role == "C67":
        record = payload["authoritative_v7_database"]
        return {
            "path": record["path"],
            "device": record["device"],
            "inode": record["inode"],
            "size": record["size"],
            "sha256": record["sha256"],
        }
    raise AssertionError(role)


def test_collection_is_inert_for_environment_sockets_and_processes():
    """Collection mutated no socket and carries no environment mutation.

    The process environment is not compared byte-for-byte: the repository's
    own ``tests/conftest.py`` legitimately scrubs credential variables for
    every test, so env inertness for *this module* is proved statically —
    the AST below shows this file never reads, writes, or deletes
    ``os.environ`` and never carries a credential-bearing literal — while the
    socket sentinel is asserted directly because nothing external patches it.
    """
    assert socket.create_connection is _COLLECTION_CREATE_CONNECTION
    tree = ast.parse(_TEST_MODULE_SOURCE)
    audit = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "test_collection_is_inert_for_environment_sockets_and_processes"
    )
    audit_span = (audit.lineno, audit.end_lineno)
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr == "environ":
            assert isinstance(node.ctx, ast.Load), "os.environ is only ever read"
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Attribute)
            and node.func.value.attr == "environ"
            and node.func.attr in {"pop", "clear", "setdefault", "update", "delitem"}
        ):
            raise AssertionError("fixture tests must not mutate os.environ")
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Attribute) and target.attr in {
                    "create_connection",
                    "socket",
                }:
                    raise AssertionError(
                        "fixture tests must not patch sockets at import"
                    )
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if audit_span[0] <= node.lineno <= audit_span[1]:
                continue  # the audit's own banned-tag literals are exempt
            assert not any(
                tag in node.value.upper()
                for tag in ("TOKEN", "API_KEY", "SECRET", "PASSWORD")
            ), "fixture tests must not name credential material at all"


def test_production_config_gate_is_root_owned_0440(tmp_path, monkeypatch):
    """The 0440 Root config gate is static in production and enforced here."""
    reader = inspect.getsource(evidence._read_qualified_control_config)
    assert "0o440" in reader and "uid=0" in reader and "control_gid" in reader
    profile = inspect.getsource(evidence._control_config_profile)
    assert "0o440" in profile and "uid=0" in profile
    fixture_reader = inspect.getsource(_fixture_control_config)
    assert "frozenset({0o440})" in fixture_reader

    runtime, backups, config, release = _build_chain(tmp_path, monkeypatch)
    with _open_initial(runtime, release) as material:
        assert material.control_config_bytes == config.read_bytes()
        assert material.control_config_identity["path"] == str(config)
        assert material.control_config_identity["mode"] == 0o440

    # A Control-original 0600 configuration is refused: the generic owner-only
    # qualifier never stands in for the distinct Root 0440 config gate.
    runtime2, backups2, config2, release2 = _build_chain(tmp_path, monkeypatch)
    config2.chmod(0o600)
    with pytest.raises(evidence.EvidenceCustodyError, match="control config"):
        with _open_initial(runtime2, release2):
            pass

    runtime3, backups3, config3, release3 = _build_chain(tmp_path, monkeypatch)
    config3.chmod(0o644)
    with pytest.raises(evidence.EvidenceCustodyError, match="control config"):
        with _open_initial(runtime3, release3):
            pass


def test_positive_chain_yields_closed_material_and_cleans_temps(tmp_path, monkeypatch):
    runtime, backups, config, release = _build_chain(tmp_path, monkeypatch)
    before = _snapshot(_chain_paths(runtime, backups))
    temp_roots_before = _temp_roots()
    with _open_initial(runtime, release) as material:
        assert material.phase == "INITIAL"
        assert material.material["phase"] == "INITIAL"
        records = material.material["origin_records"]
        assert len(records) == 12
        assert sorted(item["role"] for item in records) == sorted(
            evidence._EXPECTED_ROLES
        )
        assert set(material.material) == {
            "schema_version",
            "phase",
            "host",
            "origin_records",
            "chain",
        }
        assert material.material["schema_version"] == evidence.MATERIAL_SCHEMA_VERSION
        assert material.material["host"] == {
            "runtime_root": str(runtime),
            "backup_root": str(backups),
            "control_uid": os.geteuid(),
            "control_gid": os.getgid(),
        }
        for record in records:
            assert set(record) == (
                set(evidence._ORIGIN_KEYS)
                if record["kind"] != "receipt"
                else set(evidence._RECEIPT_ORIGIN_KEYS)
            )
            assert {"mtime_ns", "ctime_ns"} <= set(record)
        chain = material.material["chain"]
        assert material.source_v5_content_digest == chain[
            "original_full_v5_content_digest"
        ]
        assert chain["preserved_full_v5_content_digest"] == chain[
            "original_full_v5_content_digest"
        ]
        assert chain["initial_v7_full_v6_content_digest"] == chain[
            "intermediate_full_v6_content_digest"
        ]
        # the two retained v6 pairs are distinct UUID files with equal semantics
        c56 = _backup_database(runtime, "C56", "v6_backup")
        p67 = _backup_database(runtime, "P67", "v6_backup")
        assert c56 != p67 and c56.name != p67.name
        assert material.source_v5_database.is_file()
        assert material.target_v7_database.is_file()
        assert material.target_v7_database.name == "executive.sqlite3"
        assert material.target_v7_database_identity != {
            "path": str(material.target_v7_database),
            "device": material.target_v7_database.stat().st_dev,
            "inode": material.target_v7_database.stat().st_ino,
            "size": material.target_v7_database.stat().st_size,
            "sha256": hashlib.sha256(
                material.target_v7_database.read_bytes()
            ).hexdigest(),
        }
        assert set(material.inventory_additions) == {
            str(path) for path in backups.iterdir()
        }
        assert len(material.inventory_additions) == 8
        assert all(
            set(item) == {"uid", "gid", "mode", "nlink", "sha256"}
            for item in material.inventory_additions.values()
        )
        report = material.check()
        assert report["held_files"] >= 13 and report["held_directories"] >= 2
        assert {item["role"] for item in records} <= {
            item["role"] for item in report["origin_records"]
        }
        assert {item["role"] for item in report["origin_records"]} >= {
            "control.config",
            "executive-service.lock",
            "authoritative.v7.database",
        }
    assert not material.source_v5_database.exists()
    assert not material.target_v7_database.exists()
    assert _temp_roots() == temp_roots_before
    assert _snapshot(_chain_paths(runtime, backups)) == before


def test_historical_reopens_only_with_exact_pinned_material(tmp_path, monkeypatch):
    runtime, backups, config, release = _build_chain(tmp_path, monkeypatch)
    with _open_initial(runtime, release) as material:
        pinned = json.loads(json.dumps(material.material))
    database = runtime / "data" / "control_plane" / "executive.sqlite3"
    inode_before = database.stat().st_ino
    moved = tmp_path / "moved-executive.sqlite3"
    raw = bytearray(database.read_bytes())
    raw[120:124] = b"\x01\x02\x03\x04"
    _write_private(moved, bytes(raw))
    os.replace(moved, database)
    assert database.stat().st_ino != inode_before
    with evidence.open_retained_v5_to_v7_evidence(
        runtime, release, pinned
    ) as historical:
        assert historical.phase == "HISTORICAL"
        # the stable material keeps the pinned provenance phase untouched
        assert historical.material == pinned
        assert historical.material["phase"] == "INITIAL"
        assert historical.material["host"] == pinned["host"]
        assert historical.material["chain"] == pinned["chain"]
        assert historical.target_v7_database_identity == _receipt_identity(
            runtime, "C67"
        )
    incomplete = json.loads(json.dumps(pinned))
    incomplete["origin_records"] = incomplete["origin_records"][:11]
    with pytest.raises(evidence.RetainedChainInvalid, match="twelve origin records"):
        with evidence.open_retained_v5_to_v7_evidence(runtime, release, incomplete):
            pass
    tampered = json.loads(json.dumps(pinned))
    tampered["origin_records"][0]["sha256"] = "0" * 64
    with pytest.raises(evidence.RetainedChainInvalid, match="pinned material"):
        with evidence.open_retained_v5_to_v7_evidence(runtime, release, tampered):
            pass


def test_initial_refuses_current_database_mismatch(tmp_path, monkeypatch):
    runtime, backups, config, release = _build_chain(tmp_path, monkeypatch)
    database = runtime / "data" / "control_plane" / "executive.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute("UPDATE jobs SET updated_at_ms=updated_at_ms+1")
        connection.commit()
    with pytest.raises(evidence.RetainedChainInvalid, match="INITIAL"):
        with _open_initial(runtime, release):
            pass


@pytest.mark.parametrize(
    "role,field",
    [("C56", "v6_backup"), ("C67", "v7_backup"), ("P56", "v5_backup")],
)
def test_retained_backup_cell_timestamp_and_schema_tamper_refused(
    tmp_path, monkeypatch, role, field
):
    runtime, backups, config, release = _build_chain(tmp_path, monkeypatch)
    target = _backup_database(runtime, role, field)
    with sqlite3.connect(target) as connection:
        connection.execute("UPDATE jobs SET updated_at_ms=updated_at_ms+1")
        connection.commit()
    target.chmod(0o600)
    with pytest.raises(_REFUSAL):
        with _open_initial(runtime, release):
            pass

    runtime2, backups2, config2, release2 = _build_chain(tmp_path, monkeypatch)
    stamp = _backup_database(runtime2, role, field)
    stamp_version = 5 if field == "v5_backup" else 6
    with sqlite3.connect(stamp) as connection:
        connection.execute(
            "UPDATE schema_migrations SET applied_at_ms=applied_at_ms+1 WHERE version=?",
            (stamp_version,),
        )
        connection.commit()
    stamp.chmod(0o600)
    with pytest.raises(_REFUSAL):
        with _open_initial(runtime2, release2):
            pass

    runtime3, backups3, config3, release3 = _build_chain(tmp_path, monkeypatch)
    schema = _backup_database(runtime3, role, field)
    with sqlite3.connect(schema) as connection:
        connection.execute("CREATE TABLE fixture_extra(cell TEXT)")
        connection.commit()
    schema.chmod(0o600)
    with pytest.raises(_REFUSAL):
        with _open_initial(runtime3, release3):
            pass


def test_receipt_release_operation_and_preflight_digest_refusals(
    tmp_path, monkeypatch
):
    runtime, backups, config, release = _build_chain(tmp_path, monkeypatch)
    preflight_path = _receipt_path(runtime, "P56")
    _rewrite_receipt(
        preflight_path,
        lambda value: value.update(release_sha="a" * 40),
    )
    drifted = backup._upgrade_digest(json.loads(preflight_path.read_text()))
    _rewrite_receipt(
        _receipt_path(runtime, "C56"),
        lambda value: value.update(preflight_receipt_digest=drifted),
    )
    with pytest.raises(evidence.RetainedChainInvalid, match="tool release"):
        with _open_initial(runtime, release):
            pass

    runtime2, backups2, config2, release2 = _build_chain(tmp_path, monkeypatch)
    other = json.loads(_receipt_path(runtime2, "P67").read_text())["operation_id"]
    _rewrite_receipt(
        _receipt_path(runtime2, "C56"),
        lambda value: value.update(operation_id=other),
    )
    with pytest.raises(evidence.RetainedChainInvalid, match="operation"):
        with _open_initial(runtime2, release2):
            pass

    runtime3, backups3, config3, release3 = _build_chain(tmp_path, monkeypatch)
    _rewrite_receipt(
        _receipt_path(runtime3, "C56"),
        lambda value: value.update(preflight_receipt_digest="0" * 64),
    )
    with pytest.raises(evidence.RetainedChainInvalid, match="preflight digest"):
        with _open_initial(runtime3, release3):
            pass

    runtime4, backups4, config4, release4 = _build_chain(tmp_path, monkeypatch)
    _rewrite_receipt(
        _receipt_path(runtime4, "C56"),
        lambda value: value.update(migration_vector=[]),
    )
    with pytest.raises(evidence.RetainedChainInvalid, match="migration vector"):
        with _open_initial(runtime4, release4):
            pass


def test_missing_extra_and_conflicting_receipts_refused(tmp_path, monkeypatch):
    runtime, backups, config, release = _build_chain(tmp_path, monkeypatch)
    _receipt_path(runtime, "C67").unlink()
    with pytest.raises(evidence.EvidenceCustodyError, match="unavailable"):
        with _open_initial(runtime, release):
            pass

    runtime2, backups2, config2, release2 = _build_chain(tmp_path, monkeypatch)
    _rewrite_receipt(
        _receipt_path(runtime2, "P67"),
        lambda value: value.update(fixture_extra_key="nope"),
    )
    with pytest.raises(evidence.RetainedChainInvalid, match="closed evidence shape"):
        with _open_initial(runtime2, release2):
            pass

    runtime3, backups3, config3, release3 = _build_chain(tmp_path, monkeypatch)
    _rewrite_receipt(
        _receipt_path(runtime3, "C67"),
        lambda value: value.update(physical_history_digest="0" * 64),
    )
    with pytest.raises(evidence.RetainedChainInvalid, match="physical history"):
        with _open_initial(runtime3, release3):
            pass


def test_noncanonical_receipt_bytes_refused(tmp_path, monkeypatch):
    runtime, backups, config, release = _build_chain(tmp_path, monkeypatch)
    path = _receipt_path(runtime, "P56")
    value = json.loads(path.read_text())
    raw = json.dumps(value, indent=4, sort_keys=True) + "\n"
    path.write_bytes(raw.encode("utf-8"))
    path.chmod(0o600)
    with pytest.raises(evidence.RetainedChainInvalid, match="canonical producer bytes"):
        with _open_initial(runtime, release):
            pass


def test_ownership_mode_acl_and_uid_refusals(tmp_path, monkeypatch):
    runtime, backups, config, release = _build_chain(tmp_path, monkeypatch)
    _backup_database(runtime, "C67", "v7_backup").chmod(0o640)
    with pytest.raises(evidence.EvidenceCustodyError, match="owner-only"):
        with _open_initial(runtime, release):
            pass

    runtime2, backups2, config2, release2 = _build_chain(tmp_path, monkeypatch)
    # synthetic foreign-owner proof: the qualified principal is not the owner
    monkeypatch.setattr(
        evidence, "_control_identity", lambda: (os.geteuid() + 4242, os.getgid())
    )
    with pytest.raises(evidence.EvidenceCustodyError, match="foreign.*owner"):
        with _open_initial(runtime2, release2):
            pass

    runtime3, backups3, config3, release3 = _build_chain(tmp_path, monkeypatch)
    monkeypatch.setattr(evidence, "_path_has_acl", lambda path, info: True)
    with pytest.raises(evidence.EvidenceCustodyError, match="ACL"):
        with _open_initial(runtime3, release3):
            pass


def test_symlink_hardlink_and_namespace_refusals(tmp_path, monkeypatch):
    runtime, backups, config, release = _build_chain(tmp_path, monkeypatch)
    manifest = _backup_database(runtime, "C67", "v7_backup").with_suffix(
        ".manifest.json"
    )
    manifest.unlink()
    manifest.symlink_to(tmp_path / "missing-manifest-target")
    with pytest.raises(evidence.EvidenceCustodyError, match="escapes"):
        with _open_initial(runtime, release):
            pass

    runtime2, backups2, config2, release2 = _build_chain(tmp_path, monkeypatch)
    database = _backup_database(runtime2, "C67", "v7_backup")
    os.link(database, tmp_path / "fixture-hardlink.sqlite3")
    with pytest.raises(evidence.EvidenceCustodyError, match="single-link"):
        with _open_initial(runtime2, release2):
            pass

    runtime3, backups3, config3, release3 = _build_chain(tmp_path, monkeypatch)
    alias = tmp_path / "fixture-backup-alias"
    alias.symlink_to(backups3)
    _write_config(
        config3, {"runtime_root": str(runtime3), "backup_root": str(alias)}
    )
    with pytest.raises(evidence.EvidenceCustodyError, match="alias"):
        with _open_initial(runtime3, release3):
            pass

    runtime4, backups4, config4, release4 = _build_chain(tmp_path, monkeypatch)
    caller_link = tmp_path / "caller-runtime-link"
    caller_link.symlink_to(runtime4)
    with pytest.raises(evidence.EvidenceCustodyError, match="canonical host mapping"):
        with _open_initial(caller_link, release4):
            pass


def test_replacement_sidecar_and_outside_root_refusals(tmp_path, monkeypatch):
    runtime, backups, config, release = _build_chain(tmp_path, monkeypatch)
    target = _backup_database(runtime, "C67", "v7_backup")
    # The mid-custody rewrite is caught by the held file-time identity before
    # the re-read hash comparison even runs.
    with pytest.raises(evidence.EvidenceCustodyError, match="identity changed"):
        with _open_initial(runtime, release) as material:
            raw = bytearray(target.read_bytes())
            raw[64:68] = b"\x09\x09\x09\x09"
            _write_private(target, bytes(raw))
            material.check()

    runtime2, backups2, config2, release2 = _build_chain(tmp_path, monkeypatch)
    (
        runtime2 / "data" / "control_plane" / "executive.sqlite3-wal"
    ).write_bytes(b"fixture sidecar")
    with pytest.raises(evidence.EvidenceCustodyError, match="sidecar"):
        with _open_initial(runtime2, release2):
            pass

    runtime3, backups3, config3, release3 = _build_chain(tmp_path, monkeypatch)
    database = _backup_database(runtime3, "C67", "v7_backup")
    sidecar = database.with_name(database.name + "-journal")
    sidecar.write_bytes(b"retained sidecar")
    sidecar.chmod(0o600)
    with pytest.raises(evidence.EvidenceCustodyError, match="sidecar"):
        with _open_initial(runtime3, release3):
            pass

    runtime4, backups4, config4, release4 = _build_chain(tmp_path, monkeypatch)
    outside = tmp_path / "outside.sqlite3"
    _write_private(outside, b"fixture outside root")
    manifest = outside.with_suffix(".manifest.json")
    _write_private(manifest, b"{}\n")

    def move_out(value):
        value["v5_backup"]["database_path"] = str(outside)
        value["v5_backup"]["manifest_path"] = str(manifest)

    _rewrite_receipt(_receipt_path(runtime4, "P56"), move_out)
    with pytest.raises(evidence.EvidenceCustodyError, match="outside"):
        with _open_initial(runtime4, release4):
            pass


def test_copy_tamper_is_refused_before_verification(tmp_path, monkeypatch):
    runtime, backups, config, release = _build_chain(tmp_path, monkeypatch)
    original = evidence._copy_descriptor_to_temp
    state = {"corrupted": False}

    def corrupt(descriptor, destination, *, expected_sha256):
        if not state["corrupted"]:
            state["corrupted"] = True
            result = original(descriptor, destination, expected_sha256=expected_sha256)
            raw = bytearray(result.read_bytes())
            raw[0] ^= 0xFF
            _write_private(result, bytes(raw))
            return result
        return original(descriptor, destination, expected_sha256=expected_sha256)

    monkeypatch.setattr(evidence, "_copy_descriptor_to_temp", corrupt)
    with pytest.raises(_REFUSAL, match="not a database"):
        with _open_initial(runtime, release):
            pass
    assert state["corrupted"]


def test_inventory_boundary_keeps_exactly_eight_qualified_additions(
    tmp_path, monkeypatch
):
    """Old backups are never adopted; the frozen eight additions hold."""
    runtime, backups, config, release = _build_chain(tmp_path, monkeypatch)
    preexisting = backups / "executive-v3-historical.sqlite3"
    _write_private(preexisting, b"qualified old backup outside this evidence set")
    preexisting_manifest = preexisting.with_suffix(".manifest.json")
    _write_private(preexisting_manifest, b"{}\n")
    with _open_initial(runtime, release) as material:
        expected = {
            str(path)
            for path in backups.iterdir()
            if path.name not in {preexisting.name, preexisting_manifest.name}
        }
        assert set(material.inventory_additions) == expected
        assert len(material.inventory_additions) == 8
        frozen = json.loads(json.dumps(material.inventory_additions))
        late_extra = backups / "executive-v7-late-extra.sqlite3"
        _write_private(late_extra, b"late unqualified addition")
        report = material.check()
        assert report["inventory_additions"] == frozen
        assert material.inventory_additions == frozen
    assert preexisting.read_bytes() == b"qualified old backup outside this evidence set"

    runtime2, backups2, config2, release2 = _build_chain(tmp_path, monkeypatch)
    replaced = _backup_database(runtime2, "C67", "v7_backup")
    replacement = tmp_path / "replacement.sqlite3"
    _write_private(replacement, b"replaced bytes that match no receipt")
    os.replace(replacement, replaced)
    with pytest.raises(_REFUSAL, match="not a database"):
        with _open_initial(runtime2, release2):
            pass

    # A byte-identical replacement keeps every digest but moves the inode, so
    # the initial open still succeeds afterwards while the pinned historical
    # material (which froze the original inode identity) refuses the move.
    runtime3, backups3, config3, release3 = _build_chain(tmp_path, monkeypatch)
    with _open_initial(runtime3, release3) as material:
        pinned_before_replacement = json.loads(json.dumps(material.material))
    same = _backup_database(runtime3, "C67", "v7_backup")
    twin = tmp_path / "twin.sqlite3"
    _write_private(twin, same.read_bytes())
    os.replace(twin, same)
    with pytest.raises(evidence.RetainedChainInvalid, match="pinned material"):
        with evidence.open_retained_v5_to_v7_evidence(
            runtime3, release3, pinned_before_replacement
        ):
            pass


def test_verify_v7_acceptance_backup_accepts_actual_pair_and_refuses_rest(
    tmp_path, monkeypatch
):
    runtime, backups, config, release = _build_chain(tmp_path, monkeypatch)
    receipt = json.loads(_receipt_path(runtime, "C67").read_text())
    database_path = Path(receipt["v7_backup"]["database_path"])
    name = database_path.name
    material_before = None
    frozen_inventory = None
    with _open_initial(runtime, release) as material:
        material_before = json.loads(json.dumps(material.material))
        frozen_inventory = json.loads(json.dumps(material.inventory_additions))
        accepted = material.verify_v7_acceptance_backup(
            name,
            receipt["v7_backup"]["database_sha256"],
            receipt["v7_backup"]["manifest_sha256"],
        )
        assert accepted.verification["database_sha256"] == receipt["v7_backup"][
            "database_sha256"
        ]
        assert accepted.verification["normalized_schema_digest"] == receipt[
            "authoritative_v7_schema_digest"
        ]
        assert accepted.restore_drill["runtime_schema_version"] == 7
        assert isinstance(accepted.restore_drill["migration_versions"], list)
        assert set(accepted.origin_identities) == {"database", "manifest"}
        for record in accepted.origin_identities.values():
            assert set(record) == set(evidence._IDENTITY_RECORD_KEYS)
            assert not {"kind", "role", "payload_digest"} & set(record)
        assert accepted.origin_identities["database"]["path"] == str(database_path)
        assert accepted.origin_identities["manifest"]["path"] == str(
            database_path.with_suffix(".manifest.json")
        )
        assert accepted.database.is_file()
        assert accepted.database.name == name
        assert material.material == material_before
        assert material.inventory_additions == frozen_inventory
        assert material.check()["phase"] == "INITIAL"
        assert material.inventory_additions == frozen_inventory
        for wrong_name, args in (
            ("../escape.sqlite3", (receipt["v7_backup"]["database_sha256"],) * 2),
            ("manifest.json", (receipt["v7_backup"]["database_sha256"],) * 2),
            ("x" * 129 + ".sqlite3", (receipt["v7_backup"]["database_sha256"],) * 2),
            ("short.sqlite3", ("0" * 64, receipt["v7_backup"]["manifest_sha256"])),
            (
                "short.sqlite3",
                (receipt["v7_backup"]["database_sha256"], "0" * 64),
            ),
        ):
            if wrong_name == "short.sqlite3":
                continue
            with pytest.raises(evidence.SchemaUpgradeEvidenceError):
                material.verify_v7_acceptance_backup(wrong_name, *args)
        with pytest.raises(evidence.RetainedChainInvalid, match="database hash"):
            material.verify_v7_acceptance_backup(
                name, "0" * 64, receipt["v7_backup"]["manifest_sha256"]
            )
        with pytest.raises(evidence.RetainedChainInvalid, match="manifest hash"):
            material.verify_v7_acceptance_backup(
                name, receipt["v7_backup"]["database_sha256"], "0" * 64
            )
        with pytest.raises(evidence.EvidenceCustodyError, match="strict simple"):
            material.verify_v7_acceptance_backup(
                "fixture/../../traversal.sqlite3",
                receipt["v7_backup"]["database_sha256"],
                receipt["v7_backup"]["manifest_sha256"],
            )
    assert not accepted.database.exists()
    assert material.material == material_before
    assert material.inventory_additions == frozen_inventory


def test_long_name_and_non_sqlite_suffix_refused(tmp_path, monkeypatch):
    runtime, backups, config, release = _build_chain(tmp_path, monkeypatch)
    receipt = json.loads(_receipt_path(runtime, "C67").read_text())
    name = Path(receipt["v7_backup"]["database_path"]).name
    with _open_initial(runtime, release) as material:
        with pytest.raises(evidence.EvidenceCustodyError, match="strict simple"):
            material.verify_v7_acceptance_backup(
                name[:-9] + ".sqlite3.bak",
                receipt["v7_backup"]["database_sha256"],
                receipt["v7_backup"]["manifest_sha256"],
            )
        with pytest.raises(evidence.EvidenceCustodyError, match="strict simple"):
            material.verify_v7_acceptance_backup(
                "x" * 200 + ".sqlite3",
                receipt["v7_backup"]["database_sha256"],
                receipt["v7_backup"]["manifest_sha256"],
            )


def test_initial_opening_never_mutates_or_relaxes_originals(tmp_path, monkeypatch):
    runtime, backups, config, release = _build_chain(tmp_path, monkeypatch)
    before = _snapshot(_chain_paths(runtime, backups))
    uid = os.geteuid()
    with _open_initial(runtime, release):
        pass
    after = _snapshot(_chain_paths(runtime, backups))
    assert before == after
    assert all(value[3] == uid for value in after.values())
    assert all(
        stat.S_IMODE(path.lstat().st_mode) == 0o600
        for path in _chain_paths(runtime, backups)
    )
    assert stat.S_IMODE(config.lstat().st_mode) == 0o440


def test_failure_paths_close_descriptors_and_remove_private_temps(
    tmp_path, monkeypatch
):
    temp_roots_before = _temp_roots()
    runtime, backups, config, release = _build_chain(tmp_path, monkeypatch)
    _receipt_path(runtime, "C67").unlink()
    before = _descriptor_count()
    with pytest.raises(evidence.EvidenceCustodyError, match="unavailable"):
        with _open_initial(runtime, release):
            pass
    assert _descriptor_count() <= before + 2
    assert _temp_roots() == temp_roots_before

    runtime2, backups2, config2, release2 = _build_chain(tmp_path, monkeypatch)

    def explode(descriptor, destination, *, expected_sha256):
        raise OSError("fixture mid-copy failure")

    monkeypatch.setattr(evidence, "_copy_descriptor_to_temp", explode)
    before2 = _descriptor_count()
    with pytest.raises(OSError, match="mid-copy"):
        with _open_initial(runtime2, release2):
            pass
    assert _descriptor_count() <= before2 + 2
    assert _temp_roots() == temp_roots_before


# Native principal integration regressions, after the retained raw Fabric
# counterexamples. Every call uses the public context entrypoint on disposable
# actual-owner-layout fixtures, with the existing original custody seams above.
def _relink_preflight(runtime, role):
    pre = json.loads(_receipt_path(runtime, role).read_text())
    completion = {"P56": "C56", "P67": "C67"}[role]
    _rewrite_receipt(_receipt_path(runtime, completion), lambda value: value.update(
        preflight_receipt_digest=backup._upgrade_digest(pre),
        quiesce_writer_census_digest=pre["quiesce_writer_census_digest"]))


@pytest.mark.parametrize("role,field", [("P56", "v5_backup"), ("C56", "v6_backup"),
                                        ("P67", "v6_backup"), ("C67", "v7_backup")])
def test_embedded_drill_is_cross_bound_at_public_entry(tmp_path, monkeypatch, role, field):
    runtime, backups, config, release = _build_chain(tmp_path, monkeypatch)
    _rewrite_receipt(_receipt_path(runtime, role), lambda value:
                     value[field]["restore_drill_receipt"].update(integrity_check="NOT_OK"))
    if role.startswith("P"):
        _relink_preflight(runtime, role)
    with pytest.raises(evidence.RetainedChainInvalid, match="retained restore drill"):
        with _open_initial(runtime, release):
            pass


@pytest.mark.parametrize("change", ["processes", "control_uid", "lock_pid", "lock_path", "sensor", "extra"])
def test_closed_original_census_at_public_entry(tmp_path, monkeypatch, change):
    runtime, backups, config, release = _build_chain(tmp_path, monkeypatch)
    def mutate(value):
        census = value["quiesce_writer_census"]
        if change == "processes":
            census["processes"] = [{"pid": 99999, "uids": [os.geteuid()], "command_sha256": "a" * 64}]
        elif change == "control_uid":
            census["control_uids"] = [os.geteuid() + 1]
        elif change == "lock_pid":
            census["open_files"][0]["pid"] += 1
        elif change == "lock_path":
            census["open_files"][0]["path"] += ".foreign"
        elif change == "sensor":
            census["process_sensor"]["upgrader_observed"] = False
        else:
            census["extra"] = True
        value["quiesce_writer_census_digest"] = backup._upgrade_digest(census)
    _rewrite_receipt(_receipt_path(runtime, "P56"), mutate)
    _relink_preflight(runtime, "P56")
    with pytest.raises(evidence.RetainedChainInvalid, match="census"):
        with _open_initial(runtime, release):
            pass


def test_distinct_original_upgrader_pids_and_lock_fds_are_valid(tmp_path, monkeypatch):
    runtime, backups, config, release = _build_chain(tmp_path, monkeypatch)
    for role, pid, fd in (("P56", 10001, "71"), ("P67", 10002, "82")):
        def mutate(value, pid=pid, fd=fd):
            census = value["quiesce_writer_census"]
            census["upgrader_pid"] = pid
            census["open_files"][0].update(pid=pid, fd=fd)
            value["quiesce_writer_census_digest"] = backup._upgrade_digest(census)
        _rewrite_receipt(_receipt_path(runtime, role), mutate)
        _relink_preflight(runtime, role)
    with _open_initial(runtime, release) as value:
        pinned = json.loads(json.dumps(value.material))
    with evidence.open_retained_v5_to_v7_evidence(runtime, release, pinned) as value:
        assert value.material == pinned


@pytest.mark.parametrize("field", ["path", "sha256", "payload_digest"])
def test_original_barrier_binding_is_not_just_closed_shape(tmp_path, monkeypatch, field):
    runtime, backups, config, release = _build_chain(tmp_path, monkeypatch)
    _rewrite_receipt(_receipt_path(runtime, "P56"), lambda value:
                     value["barrier_identity"].update({field: "/foreign" if field == "path" else "0" * 64}))
    _relink_preflight(runtime, "P56")
    with pytest.raises(evidence.RetainedChainInvalid, match="barrier binding"):
        with _open_initial(runtime, release):
            pass


def test_historical_tool_sha_and_manifest_are_actual_original_bindings(tmp_path, monkeypatch):
    runtime, backups, config, release = _build_chain(tmp_path, monkeypatch)
    with _open_initial(runtime, release) as value:
        pinned = json.loads(json.dumps(value.material))
    with pytest.raises(evidence.RetainedChainInvalid, match="expected SHA"):
        with evidence.open_retained_v5_to_v7_evidence(runtime, "f" * 40, pinned):
            pass
    monkeypatch.setattr(evidence, "_verify_pinned_release", lambda root, sha, tree:
                        {"commit_sha": sha, "tree_sha": tree, "manifest_sha256": "0" * 64})
    with pytest.raises(evidence.RetainedChainInvalid, match="retained manifest"):
        with evidence.open_retained_v5_to_v7_evidence(runtime, release, pinned):
            pass


def test_historical_running_service_and_new_config_preserve_exact_material(tmp_path, monkeypatch):
    runtime, backups, config, release = _build_chain(tmp_path, monkeypatch)
    with _open_initial(runtime, release) as value:
        pinned = json.loads(json.dumps(value.material))
        old_config = value.control_config_bytes
    database = runtime / rt._DB_RELATIVE_PATH
    _write_private(database.parent / backup.DEFAULT_SERVICE_MARKER_NAME, b"running fixture")
    _write_private(database.with_name(database.name + "-wal"), b"live fixture sidecar")
    _write_config(config, {"runtime_root": str(runtime), "backup_root": str(backups), "proof_base": "e" * 40})
    with evidence.open_retained_v5_to_v7_evidence(runtime, release, pinned) as value:
        assert value.material == pinned
        assert value.control_config_bytes != old_config


def test_real_old_backup_and_distinct_acceptance_pair_remain_separate(tmp_path, monkeypatch):
    runtime, backups, config, release = _build_chain(tmp_path, monkeypatch)
    old = backup.create_offline_backup(_backup_database(runtime, "P56", "v5_backup"), backups,
                                      expected_schema_version=5)
    pair = backup.create_offline_backup(runtime / rt._DB_RELATIVE_PATH, backups,
                                       expected_schema_version=7)
    old_paths = [Path(old.database_path), Path(old.manifest_path)]
    before = _snapshot(old_paths)
    with _open_initial(runtime, release) as value:
        material = json.loads(json.dumps(value.material))
        additions = json.loads(json.dumps(value.inventory_additions))
        assert len(additions) == 8
        assert not set(map(str, old_paths)) & set(additions)
        verified = value.verify_v7_acceptance_backup(Path(pair.database_path).name,
                          pair.database_sha256, pair.manifest_sha256)
        assert set(verified.origin_identities) == {"database", "manifest"}
        expected = {"path", "device", "inode", "uid", "gid", "mode", "nlink", "size",
                    "mtime_ns", "ctime_ns", "sha256"}
        assert all(set(record) == expected for record in verified.origin_identities.values())
        assert verified.origin_identities["database"]["path"] == pair.database_path
        assert value.material == material
        assert value.inventory_additions == additions
        value.check()
    assert _snapshot(old_paths) == before


def test_original_config_parent_alias_and_namespace_acl_refuse(tmp_path, monkeypatch):
    runtime, backups, config, release = _build_chain(tmp_path, monkeypatch)
    parent = config.parent
    moved = parent.with_name("original-config")
    parent.rename(moved)
    parent.symlink_to(moved, target_is_directory=True)
    with pytest.raises(evidence.EvidenceCustodyError, match="alias"):
        with _open_initial(runtime, release):
            pass
    runtime, backups, config, release = _build_chain(tmp_path, monkeypatch)
    original = evidence._path_has_acl
    monkeypatch.setattr(evidence, "_path_has_acl", lambda path, info:
                        path == config.parent or original(path, info))
    with pytest.raises(evidence.EvidenceCustodyError, match="namespace carries an ACL"):
        with _open_initial(runtime, release):
            pass


def test_fixed_control_identity_cannot_collapse_to_root_or_foreign_group(monkeypatch):
    from types import SimpleNamespace
    for uid, primary_gid, name, group_name in ((0, 450, autonomy_control.CONTROL_USER, autonomy_control.CONTROL_GROUP),
                   (450, 451, autonomy_control.CONTROL_USER, autonomy_control.CONTROL_GROUP),
                   (450, 450, autonomy_control.CONTROL_USER, "foreign")):
        monkeypatch.setattr(evidence.pwd, "getpwnam", lambda label, uid=uid, primary_gid=primary_gid, name=name:
                            SimpleNamespace(pw_uid=uid, pw_gid=primary_gid, pw_name=name))
        monkeypatch.setattr(evidence.grp, "getgrnam", lambda label, group_name=group_name:
                            SimpleNamespace(gr_gid=450, gr_name=group_name))
        with pytest.raises(evidence.EvidenceCustodyError):
            evidence._control_identity()



def test_writable_original_control_ancestor_is_refused(tmp_path, monkeypatch):
    runtime, backups, config, release = _build_chain(tmp_path, monkeypatch)
    parent = runtime.parent
    parent.chmod(0o777)
    try:
        with pytest.raises(evidence.EvidenceCustodyError, match="writable owner"):
            with _open_initial(runtime, release):
                pass
    finally:
        parent.chmod(0o700)


def test_pinned_release_checker_reads_actual_root_manifest_gate(tmp_path, monkeypatch):
    sha, tree = "d" * 40, "e" * 40
    root = tmp_path / "releases" / sha
    root.mkdir(parents=True)
    raw = b"inert retained manifest fixture bytes" * 40000
    assert len(raw) > 1024 * 1024
    calls = []
    monkeypatch.setattr(autonomy_control, "SYSTEM_ROOT", tmp_path)
    monkeypatch.setattr(evidence.release_manifest, "verify", lambda path, commit, tree_sha:
                        {"commit_sha": commit, "tree_sha": tree_sha})
    def read(commit):
        calls.append(commit)
        return raw
    # This source depends on the protected 1812 owner; cold-archive checks use
    # that real reader.  This unit isolates only the exact-SHA dispatch seam.
    monkeypatch.setattr(autonomy_control, "_release_manifest_bytes", read, raising=False)
    value = evidence._verify_pinned_release(root, sha, tree)
    assert value["manifest_sha256"] == hashlib.sha256(raw).hexdigest()
    assert calls == [sha]
    with pytest.raises(evidence.RetainedChainInvalid, match="fixed sealed release"):
        evidence._verify_pinned_release(tmp_path / sha, sha, tree)



def test_historical_material_cannot_relabel_initial_provenance(tmp_path, monkeypatch):
    runtime, backups, config, release = _build_chain(tmp_path, monkeypatch)
    with _open_initial(runtime, release) as value:
        pinned = json.loads(json.dumps(value.material))
    pinned["phase"] = "HISTORICAL"
    with pytest.raises(evidence.RetainedChainInvalid, match="original INITIAL"):
        with evidence.open_retained_v5_to_v7_evidence(runtime, release, pinned):
            pass



@pytest.mark.parametrize("target", ["backup", "config"])
def test_special_original_is_refused_before_blocking_read(tmp_path, monkeypatch, target):
    # A missing nonblocking flag fails before creating the disposable FIFO,
    # so this regression can never hang when run against an older preimage.
    assert "O_NONBLOCK" in inspect.getsource(evidence._qualify_control_file)
    runtime, backups, config, release = _build_chain(tmp_path, monkeypatch)
    path = config if target == "config" else _backup_database(runtime, "C67", "v7_backup")
    path.unlink()
    os.mkfifo(path, 0o440 if target == "config" else 0o600)
    with pytest.raises(evidence.EvidenceCustodyError):
        with _open_initial(runtime, release):
            pass


def test_pre_yield_custody_is_revalidated(tmp_path, monkeypatch):
    runtime, backups, config, release = _build_chain(tmp_path, monkeypatch)
    original = backup.verify_backup
    changed = []
    entered = []
    def verify(*args, **kwargs):
        result = original(*args, **kwargs)
        if kwargs.get('expected_schema_version') == 7 and not changed:
            changed.append(True)
            twin = config.with_name('replacement-control.json')
            twin.write_bytes(config.read_bytes())
            twin.chmod(0o440)
            os.replace(twin, config)
        return result
    monkeypatch.setattr(backup, 'verify_backup', verify)
    with pytest.raises(evidence.EvidenceCustodyError):
        with evidence.open_v5_to_v7_evidence(runtime, release):
            entered.append(True)
    assert changed and not entered, 'stale retained DATA reached the with-body'


@pytest.mark.parametrize('kind', ['migration', 'acceptance'])
def test_retained_sidecar_absence_is_revalidated(tmp_path, monkeypatch, kind):
    runtime, backups, config, release = _build_chain(tmp_path, monkeypatch)
    if kind == 'acceptance':
        pair = backup.create_offline_backup(runtime / rt._DB_RELATIVE_PATH, backups, expected_schema_version=7)
        database = Path(pair.database_path)
    else:
        database = _backup_database(runtime, 'C67', 'v7_backup')
    with evidence.open_v5_to_v7_evidence(runtime, release) as value:
        if kind == 'acceptance':
            value.verify_v7_acceptance_backup(database.name, pair.database_sha256, pair.manifest_sha256)
        sidecar = database.with_name(database.name + '-journal')
        sidecar.write_bytes(b'inert disposable sidecar')
        sidecar.chmod(0o600)
        try:
            with pytest.raises(evidence.EvidenceCustodyError, match='sidecar'):
                value.check()
        finally:
            sidecar.unlink()


def test_fixed_system_spellings_are_bidirectional_and_closed():
    for suffix in ("db", "backups"):
        logical = Path("/var/db/mastermind-executive/control") / suffix
        physical = Path("/private/var/db/mastermind-executive/control") / suffix
        assert set(evidence._fixed_lexical_variants(logical)) == {logical, physical}
        assert set(evidence._fixed_lexical_variants(physical)) == {logical, physical}
    foreign = Path("/tmp/foreign/control/db")
    assert evidence._fixed_lexical_variants(foreign) == (foreign,)


def test_public_entry_fixed_logical_config_and_argument(tmp_path, monkeypatch):
    runtime, backups, config, release = _build_chain(tmp_path, monkeypatch)
    physical_top = runtime.parent.parent
    logical_top = tmp_path / "logical-system-spelling"
    logical_top.symlink_to(physical_top, target_is_directory=True)
    # Only the fixed system mapping is substituted to a disposable analogue;
    # realpath, original namespace FDs, and all original file checks remain real.
    monkeypatch.setattr(evidence, "_FIXED_SYSTEM_MAPPINGS", ((logical_top, physical_top),))
    logical_runtime = logical_top / runtime.relative_to(physical_top)
    logical_backups = logical_top / backups.relative_to(physical_top)
    config.chmod(0o600)
    _write_private(config, (json.dumps({"runtime_root": str(logical_runtime),
                                     "backup_root": str(logical_backups)}) + "\n").encode())
    config.chmod(0o440)
    with evidence.open_v5_to_v7_evidence(logical_runtime, release) as value:
        assert value.material["host"]["runtime_root"] == str(runtime)
        assert value.material["host"]["backup_root"] == str(backups)
    foreign = tmp_path / "foreign-alias"
    foreign.symlink_to(physical_top, target_is_directory=True)
    with pytest.raises(evidence.EvidenceCustodyError, match="qualified physical"):
        with evidence.open_v5_to_v7_evidence(foreign / runtime.relative_to(physical_top), release):
            pytest.fail("foreign alias reached qualified body")


def test_historical_backup_sidecar_is_refused_at_context_exit(tmp_path, monkeypatch):
    runtime, backups, config, release = _build_chain(tmp_path, monkeypatch)
    with _open_initial(runtime, release) as value:
        pinned = json.loads(json.dumps(value.material))
    database = runtime / rt._DB_RELATIVE_PATH
    # Current live sidecars are intentionally irrelevant to historical proof;
    # a retained migration backup sidecar is always consequential.
    database.with_name(database.name + '-wal').write_bytes(b'inert current live sidecar')
    retained = _backup_database(runtime, 'C67', 'v7_backup')
    sidecar = retained.with_name(retained.name + '-shm')
    try:
        with pytest.raises(evidence.EvidenceCustodyError, match='sidecar'):
            with evidence.open_retained_v5_to_v7_evidence(runtime, release, pinned):
                sidecar.write_bytes(b'inert immutable backup sidecar')
    finally:
        sidecar.unlink(missing_ok=True)


def test_acceptance_pair_rechecks_existing_custody_before_return(tmp_path, monkeypatch):
    runtime, backups, config, release = _build_chain(tmp_path, monkeypatch)
    pair = backup.create_offline_backup(runtime / rt._DB_RELATIVE_PATH, backups,
                                      expected_schema_version=7)
    original = backup.verify_backup
    returned = []
    changed = []
    def verify(*args, **kwargs):
        result = original(*args, **kwargs)
        if not changed:
            twin = config.with_name('replacement-control.json')
            twin.write_bytes(config.read_bytes())
            twin.chmod(0o440)
            os.replace(twin, config)
            changed.append(True)
        return result
    with pytest.raises(evidence.EvidenceCustodyError):
        with _open_initial(runtime, release) as value:
            monkeypatch.setattr(backup, 'verify_backup', verify)
            value.verify_v7_acceptance_backup(Path(pair.database_path).name,
                                             pair.database_sha256, pair.manifest_sha256)
            returned.append(True)
    assert changed and not returned

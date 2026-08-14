"""Hermetic tests for the install-time Codex attestation receipt.

Phase 1C acceptance failed at worker-broker startup on the real host: the
worker daemon (throttled ``ProcessType=Background`` + ``LowPriorityIO=true``,
under host load) called ``attest_codex_binary`` -- which shells out to a
version probe and (on Darwin) two ``codesign`` invocations -- on every single
startup, and that cold path blew past a 60-second bound. These tests cover
the fix: install time records a root-owned, immutable receipt
(``control_plane.codex_worker.load_codex_attestation_receipt``), and worker
startup (``scripts.executive_os_phase1c_worker._build_broker`` and
``check-config``) builds a ``BinaryAttestation`` from that receipt instead of
re-attesting -- with a cheap ``fstat``-based identity pin catching a binary
swapped or modified after install.

That "zero subprocess calls" property is NOT provable by running any test in
this file against base commit 9603b408d0b8d3c806a76764f6a5e12454d140a1: the
module fails to even COLLECT there (``AttributeError:
CODEX_ATTESTATION_RECEIPT_SCHEMA_VERSION`` does not exist yet), so nothing
in this file ever runs against it. The property was instead verified with a
standalone, base-compatible reproduction script run directly against
9603b40's ``scripts/executive_os_phase1c_worker.py`` +
``control_plane/codex_worker.py`` (and independently, by the reviewing
session, with ``sys.addaudithook``): 3 subprocess calls recorded there
(``--version``, ``codesign --verify --strict``, ``codesign -dv
--verbose=4``) building a broker from an otherwise-valid config, versus zero
on the fixed tree. ``test_broker_construction_from_valid_receipt_spawns_no_subprocess``
below re-exercises that same zero-calls property against the CURRENT
(fixed) code, using real fixtures; it is a regression guard, not itself the
9603b40 comparison.

No test here spawns a subprocess against a real Codex binary, requires
root, or touches a real 220 MB binary; every fixture is a small tmp file
with fabricated attestation fields. A handful of checks are fundamentally
about real OS-level file ownership (root-owned receipts and binaries) that
this unprivileged test process cannot produce by literally chowning to
root; those are noted and handled either by exercising the natural,
correctly-non-root-owned fixture as the REFUSAL case, or -- for tests that
need to get PAST that gate to exercise something else -- by patching
exactly the observed ``fstat`` result for the fixture's own inode (see
``_patch_owner_as_root``), never by relaxing what the code under test
actually requires.
"""
from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from control_plane import codex_worker as cw


ROOT = Path(__file__).resolve().parents[1]
INSTALL_SH = ROOT / "ops" / "executive_os" / "install.sh"
_MACHO_MAGIC_PREFIX = b"\xcf\xfa\xed\xfe"


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _write_fake_binary(path: Path, *, payload: bytes = b"fixture-codex-binary-bytes") -> None:
    """Write a small fixture file that reads as a native Mach-O binary.

    The magic prefix is unconditional (not just a default) because two
    different things depend on it: the pre-fix regression proof (base
    commit 9603b40's attest_codex_binary rejects non-Mach-O input before
    ever reaching its subprocess calls, so a non-Mach-O fixture would
    short-circuit before exercising the branch under test) and this
    commit's own Mach-O magic check in _verify_codex_binary_identity. Mode
    0o500 (owner read+execute only) also means every fixture binary is
    naturally non-group/other-writable, satisfying that invariant without
    any extra setup.
    """
    path.write_bytes(_MACHO_MAGIC_PREFIX + payload)
    path.chmod(0o500)


def _identity_of(path: Path) -> dict[str, int]:
    info = path.stat()
    return {
        "device": info.st_dev,
        "inode": info.st_ino,
        "size": info.st_size,
        "mode": stat.S_IMODE(info.st_mode),
        "uid": info.st_uid,
        "gid": info.st_gid,
        "mtime_ns": info.st_mtime_ns,
        "ctime_ns": info.st_ctime_ns,
    }


def _root_owned_identity_of(path: Path) -> dict[str, int]:
    """The real identity of ``path``, with the owner claimed as root.

    Pair with ``_patch_owner_as_root(monkeypatch, path)`` so the OBSERVED
    side (a fresh fstat at load time) agrees with what is RECORDED here --
    otherwise this just manufactures a different, equally-wrong mismatch.
    """
    identity = _identity_of(path)
    identity["uid"] = 0
    return identity


class _UidZeroStat:
    """Proxies a real os.stat_result, reporting st_uid as 0."""

    __slots__ = ("_real",)

    def __init__(self, real: os.stat_result) -> None:
        self._real = real

    def __getattr__(self, name: str):
        if name == "st_uid":
            return 0
        return getattr(self._real, name)


def _patch_owner_as_root(monkeypatch: pytest.MonkeyPatch, *paths: Path) -> None:
    """Make ``os.fstat`` report ``st_uid == 0`` for exactly the given paths.

    Real root ownership of the installed Codex binary and its attestation
    receipt is a hard, correct invariant that this unprivileged test
    process cannot honestly produce (chowning to root requires root). The
    refusal itself is proven elsewhere using the real, naturally
    non-root-owned fixture (see test_identity_non_root_binary_owner_is_refused,
    test_receipt_not_root_owned_is_refused): those tests need NO patch, since
    the real environment already exercises the refusal.

    This patch exists only for tests that need to get PAST that gate to
    exercise something else. It patches the OBSERVED side only (a fresh
    fstat of the real file at load time) -- it never changes what the code
    under test requires or accepts, and it is scoped to exactly the named
    paths' (device, inode) pairs, so it never masks an unrelated file's
    real ownership (in particular, a receipt path NOT passed here still
    shows its real, non-root uid).
    """
    targets = {(os.stat(p).st_dev, os.stat(p).st_ino) for p in paths}
    real_fstat = cw.os.fstat

    def fake_fstat(fd, *args, **kwargs):
        result = real_fstat(fd, *args, **kwargs)
        if (result.st_dev, result.st_ino) in targets:
            return _UidZeroStat(result)
        return result

    monkeypatch.setattr(cw.os, "fstat", fake_fstat)


def _write_receipt(
    receipt_path: Path,
    *,
    binary_path: Path,
    identity: dict[str, int] | None = None,
    schema_version: str = cw.CODEX_ATTESTATION_RECEIPT_SCHEMA_VERSION,
    version: str = "0.147.0",
    team_identifier: str | None = "2DC432GLL2",
    sha256: str = "a" * 64,
    recorded_at: str = "2026-08-14T00:00:00+00:00",
    path_field: str | None = None,
    extra_fields: dict | None = None,
    omit_fields: tuple[str, ...] = (),
    mode: int = 0o440,
) -> None:
    document: dict = {
        "schema_version": schema_version,
        "path": path_field if path_field is not None else str(binary_path),
        "version": version,
        "team_identifier": team_identifier,
        "sha256": sha256,
        "recorded_at": recorded_at,
        "identity": identity if identity is not None else _identity_of(binary_path),
    }
    for field in omit_fields:
        document.pop(field, None)
    if extra_fields:
        document.update(extra_fields)
    receipt_path.write_text(json.dumps(document, sort_keys=True), encoding="utf-8")
    receipt_path.chmod(mode)


def _fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    """A binary + a receipt describing it exactly, ready for the happy path.

    The binary is patched to appear root-owned (see _patch_owner_as_root)
    and its recorded identity claims uid=0 to match -- a fully-valid,
    unweakened fixture, not a relaxed one. The receipt FILE's own ownership
    is handled separately: callers use _load()'s default
    expected_owner_uid=os.geteuid() override for that (a receipt this
    unprivileged test process created can only ever really be owned by
    it), which is orthogonal to the binary's recorded/observed identity.
    """
    binary = tmp_path / "codex-0.147.0"
    _write_fake_binary(binary)
    _patch_owner_as_root(monkeypatch, binary)
    receipt = tmp_path / "codex-attestation.json"
    _write_receipt(receipt, binary_path=binary, identity=_root_owned_identity_of(binary))
    return binary, receipt


def _load(binary: Path, receipt: Path, **overrides):
    kwargs = dict(
        expected_binary_path=binary,
        expected_owner_gid=os.getegid(),
        expected_owner_uid=os.geteuid(),
    )
    kwargs.update(overrides)
    return cw.load_codex_attestation_receipt(receipt, **kwargs)


def _write_worker_config(
    path: Path, *, codex_binary: Path, codex_attestation_receipt: Path
) -> None:
    root = path.parent
    value = {
        "schema_version": "mastermind.executive_worker_broker_config/v3",
        "control_uid": os.geteuid() + 1000,
        "worker_uid": os.geteuid(),
        "worker_gid": os.getegid(),
        # _load_config (unlike BrokerPolicy) requires this set to be one of
        # the two reviewed ambient GID sets, not merely well-formed.
        "allowed_supplementary_gids": [12, 61, 100],
        "worker_user": "fixture-worker",
        "worker_id": "codex-01",
        "workspace_root": str(root / "workspaces"),
        "run_root": str(root / "runs"),
        "provider_home": str(root / "provider-home"),
        "codex_binary": str(codex_binary),
        "codex_attestation_receipt": str(codex_attestation_receipt),
        "allowed_codex_versions": ["0.147.0"],
        "required_team_identifier": "2DC432GLL2",
        "launchd_socket_name": "WorkerBroker",
        "uid_sweep_receipt": str(root / "uid-sweep.json"),
        "require_secret_canary": True,
    }
    path.write_text(json.dumps(value), encoding="utf-8")
    path.chmod(0o640)


_IDENTITY_FIELDS = ("device", "inode", "size", "mode", "uid", "gid", "mtime_ns", "ctime_ns")


# ---------------------------------------------------------------------------
# 1. Headline proof -- no subprocess at broker construction time, and the
#    call site is not allowed to weaken the owner it expects (Blocker 2)
# ---------------------------------------------------------------------------


def test_broker_construction_from_valid_receipt_spawns_no_subprocess(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With a valid receipt, building the worker broker never shells out,
    and _build_broker never weakens the receipt's required owner uid.

    See the module docstring for how the "zero subprocess calls" property
    was actually verified against 9603b40 (a standalone script, not this
    test, which cannot even be collected on that commit).
    """

    from scripts import executive_os_phase1c_worker as worker_entry
    from scripts.executive_os_phase1c_worker import _build_broker

    binary, receipt = _fixture(tmp_path, monkeypatch)
    workspace_root = tmp_path / "workspaces"
    run_root = tmp_path / "runs"
    provider_home = tmp_path / "provider-home"
    for path in (workspace_root, run_root, provider_home):
        path.mkdir(mode=0o700)

    subprocess_calls: list[tuple] = []

    def spy_run(*args, **kwargs):
        subprocess_calls.append((args, kwargs))
        return subprocess.CompletedProcess(args[0] if args else [], 0, "codex-cli 0.147.0\n", "")

    monkeypatch.setattr(cw.subprocess, "run", spy_run)

    # A SPY, not a stub that silently redirects: it records the exact
    # kwargs _build_broker calls it with (asserted below, unmodified), and
    # only THEN builds its own copy to delegate with -- so a call site
    # weakened to pass expected_owner_uid=policy.worker_uid (accepting a
    # receipt owned by the worker principal itself -- the forged-receipt
    # attack) shows up in `recorded_calls` and fails the assertion, instead
    # of being silently swallowed by **kwargs like an unconditional
    # override would be.
    recorded_calls: list[dict] = []

    def spy_loader(receipt_path, **kwargs):
        recorded_calls.append(dict(kwargs))
        delegate_kwargs = dict(kwargs)
        delegate_kwargs["expected_owner_uid"] = os.geteuid()
        return cw.load_codex_attestation_receipt(receipt_path, **delegate_kwargs)

    monkeypatch.setattr(
        worker_entry, "load_codex_attestation_receipt", spy_loader, raising=False
    )

    config = {
        "schema_version": "mastermind.executive_worker_broker_config/v3",
        "control_uid": os.geteuid() + 1000,
        "worker_uid": os.geteuid(),
        "worker_gid": os.getegid(),
        "allowed_supplementary_gids": [],
        "worker_user": "fixture-worker",
        "worker_id": "codex-01",
        "workspace_root": str(workspace_root),
        "run_root": str(run_root),
        "provider_home": str(provider_home),
        "codex_binary": str(binary),
        "codex_attestation_receipt": str(receipt),
        "allowed_codex_versions": ["0.147.0"],
        "required_team_identifier": "2DC432GLL2",
        "launchd_socket_name": "WorkerBroker",
        "uid_sweep_receipt": str(tmp_path / "uid-sweep.json"),
        "require_secret_canary": True,
    }

    broker = _build_broker(config)

    assert broker.adapter.binary.version == "0.147.0"
    assert subprocess_calls == []
    assert len(recorded_calls) == 1
    assert "expected_owner_uid" not in recorded_calls[0] or recorded_calls[0]["expected_owner_uid"] == 0


def test_build_broker_refuses_on_missing_receipt_without_subprocess_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A missing receipt must refuse to start -- never silently re-attest.

    Mutation target: if _build_broker ever caught the load failure and
    fell back to building CodexWorkerAdapter with no binary_attestation,
    that would reintroduce the exact slow codesign/--version cold path
    this whole mechanism exists to remove.
    """

    from scripts.executive_os_phase1c_worker import _build_broker

    binary = tmp_path / "codex-0.147.0"
    _write_fake_binary(binary)
    missing_receipt = tmp_path / "codex-attestation.json"  # never written
    workspace_root = tmp_path / "workspaces"
    run_root = tmp_path / "runs"
    provider_home = tmp_path / "provider-home"
    for path in (workspace_root, run_root, provider_home):
        path.mkdir(mode=0o700)

    calls: list[tuple] = []

    def spy_run(*args, **kwargs):
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(args[0] if args else [], 0, "codex-cli 0.147.0\n", "")

    monkeypatch.setattr(cw.subprocess, "run", spy_run)

    config = {
        "schema_version": "mastermind.executive_worker_broker_config/v3",
        "control_uid": os.geteuid() + 1000,
        "worker_uid": os.geteuid(),
        "worker_gid": os.getegid(),
        "allowed_supplementary_gids": [],
        "worker_user": "fixture-worker",
        "worker_id": "codex-01",
        "workspace_root": str(workspace_root),
        "run_root": str(run_root),
        "provider_home": str(provider_home),
        "codex_binary": str(binary),
        "codex_attestation_receipt": str(missing_receipt),
        "allowed_codex_versions": ["0.147.0"],
        "required_team_identifier": "2DC432GLL2",
        "launchd_socket_name": "WorkerBroker",
        "uid_sweep_receipt": str(tmp_path / "uid-sweep.json"),
        "require_secret_canary": True,
    }

    with pytest.raises(cw.CodexAttestationReceiptError, match="missing or unreadable"):
        _build_broker(config)

    assert calls == []


# ---------------------------------------------------------------------------
# 2. Fail-closed matrix -- the receipt file itself
# ---------------------------------------------------------------------------


def test_receipt_missing_is_refused(tmp_path: Path) -> None:
    binary = tmp_path / "codex"
    _write_fake_binary(binary)
    missing = tmp_path / "codex-attestation.json"
    with pytest.raises(cw.CodexAttestationReceiptError, match="missing or unreadable"):
        _load(binary, missing)


def test_receipt_relative_path_is_refused(tmp_path: Path) -> None:
    binary = tmp_path / "codex"
    _write_fake_binary(binary)
    with pytest.raises(cw.CodexAttestationReceiptError, match="absolute"):
        cw.load_codex_attestation_receipt(
            "relative/codex-attestation.json",
            expected_binary_path=binary,
            expected_owner_gid=os.getegid(),
            expected_owner_uid=os.geteuid(),
        )


def test_receipt_directory_is_refused(tmp_path: Path) -> None:
    binary = tmp_path / "codex"
    _write_fake_binary(binary)
    receipt_dir = tmp_path / "codex-attestation.json"
    receipt_dir.mkdir()
    with pytest.raises(cw.CodexAttestationReceiptError, match="regular file"):
        _load(binary, receipt_dir)


def test_receipt_not_root_owned_is_refused(tmp_path: Path) -> None:
    binary = tmp_path / "codex"
    _write_fake_binary(binary)
    receipt = tmp_path / "codex-attestation.json"
    _write_receipt(receipt, binary_path=binary)
    # expected_owner_uid defaults to 0 (root); this fixture's actual owner
    # is this unprivileged test process, so leaving the default triggers
    # the "not root-owned" branch honestly, without any chown.
    with pytest.raises(cw.CodexAttestationReceiptError, match="not root-owned"):
        _load(binary, receipt, expected_owner_uid=0)


def test_receipt_wrong_group_owner_is_refused(tmp_path: Path) -> None:
    binary = tmp_path / "codex"
    _write_fake_binary(binary)
    receipt = tmp_path / "codex-attestation.json"
    _write_receipt(receipt, binary_path=binary)
    with pytest.raises(cw.CodexAttestationReceiptError, match="unexpected group owner"):
        _load(binary, receipt, expected_owner_gid=os.getegid() + 1)


def test_receipt_wrong_mode_is_refused(tmp_path: Path) -> None:
    binary = tmp_path / "codex"
    _write_fake_binary(binary)
    receipt = tmp_path / "codex-attestation.json"
    _write_receipt(receipt, binary_path=binary, mode=0o640)
    with pytest.raises(cw.CodexAttestationReceiptError, match="unsafe mode"):
        _load(binary, receipt)


def test_receipt_extra_hard_link_is_refused(tmp_path: Path) -> None:
    binary = tmp_path / "codex"
    _write_fake_binary(binary)
    receipt = tmp_path / "codex-attestation.json"
    _write_receipt(receipt, binary_path=binary)
    os.link(receipt, tmp_path / "codex-attestation.json.alias")
    with pytest.raises(cw.CodexAttestationReceiptError, match="one hard link"):
        _load(binary, receipt)


def test_receipt_symlink_is_refused(tmp_path: Path) -> None:
    binary = tmp_path / "codex"
    _write_fake_binary(binary)
    real = tmp_path / "codex-attestation.real.json"
    _write_receipt(real, binary_path=binary)
    link = tmp_path / "codex-attestation.json"
    link.symlink_to(real)
    with pytest.raises(cw.CodexAttestationReceiptError, match="missing or unreadable"):
        _load(binary, link)


def test_receipt_oversized_is_refused(tmp_path: Path) -> None:
    binary = tmp_path / "codex"
    _write_fake_binary(binary)
    receipt = tmp_path / "codex-attestation.json"
    receipt.write_bytes(b"{" + b" " * (cw._MAX_CODEX_RECEIPT_BYTES + 10) + b"}")
    receipt.chmod(0o440)
    with pytest.raises(cw.CodexAttestationReceiptError, match="size limit"):
        _load(binary, receipt)


def test_receipt_malformed_json_is_refused(tmp_path: Path) -> None:
    binary = tmp_path / "codex"
    _write_fake_binary(binary)
    receipt = tmp_path / "codex-attestation.json"
    receipt.write_text("{not-json", encoding="utf-8")
    receipt.chmod(0o440)
    with pytest.raises(cw.CodexAttestationReceiptError, match="not valid UTF-8 JSON"):
        _load(binary, receipt)


def test_receipt_extra_top_level_field_is_refused(tmp_path: Path) -> None:
    binary = tmp_path / "codex"
    _write_fake_binary(binary)
    receipt = tmp_path / "codex-attestation.json"
    _write_receipt(receipt, binary_path=binary, extra_fields={"unexpected": "value"})
    with pytest.raises(cw.CodexAttestationReceiptError, match="fields do not match the schema"):
        _load(binary, receipt)


@pytest.mark.parametrize(
    "field",
    ["schema_version", "path", "version", "team_identifier", "sha256", "recorded_at", "identity"],
)
def test_receipt_missing_top_level_field_is_refused(tmp_path: Path, field: str) -> None:
    binary = tmp_path / "codex"
    _write_fake_binary(binary)
    receipt = tmp_path / "codex-attestation.json"
    _write_receipt(receipt, binary_path=binary, omit_fields=(field,))
    with pytest.raises(cw.CodexAttestationReceiptError, match="fields do not match the schema"):
        _load(binary, receipt)


@pytest.mark.parametrize("field", ["path", "version", "sha256", "recorded_at"])
def test_receipt_empty_string_field_is_refused(tmp_path: Path, field: str) -> None:
    binary = tmp_path / "codex"
    _write_fake_binary(binary)
    receipt = tmp_path / "codex-attestation.json"
    _write_receipt(receipt, binary_path=binary, extra_fields={field: ""})
    with pytest.raises(cw.CodexAttestationReceiptError, match=f"field {field!r} is invalid"):
        _load(binary, receipt)


def test_receipt_malformed_sha256_is_refused(tmp_path: Path) -> None:
    binary = tmp_path / "codex"
    _write_fake_binary(binary)
    receipt = tmp_path / "codex-attestation.json"
    _write_receipt(receipt, binary_path=binary, sha256="not-a-valid-hash")
    with pytest.raises(cw.CodexAttestationReceiptError, match="sha256 is malformed"):
        _load(binary, receipt)


def test_receipt_team_identifier_wrong_type_is_refused(tmp_path: Path) -> None:
    binary = tmp_path / "codex"
    _write_fake_binary(binary)
    receipt = tmp_path / "codex-attestation.json"
    _write_receipt(receipt, binary_path=binary, extra_fields={"team_identifier": 12345})
    with pytest.raises(cw.CodexAttestationReceiptError, match="team_identifier is invalid"):
        _load(binary, receipt)


def test_receipt_schema_version_mismatch_is_refused(tmp_path: Path) -> None:
    binary = tmp_path / "codex"
    _write_fake_binary(binary)
    receipt = tmp_path / "codex-attestation.json"
    _write_receipt(
        receipt, binary_path=binary, schema_version="mastermind.executive_codex_attestation/v0"
    )
    with pytest.raises(cw.CodexAttestationReceiptError, match="schema version"):
        _load(binary, receipt)


def test_receipt_binary_path_mismatch_is_refused(tmp_path: Path) -> None:
    binary = tmp_path / "codex"
    _write_fake_binary(binary)
    other = tmp_path / "codex-other"
    _write_fake_binary(other)
    receipt = tmp_path / "codex-attestation.json"
    _write_receipt(receipt, binary_path=binary, path_field=str(other))
    with pytest.raises(cw.CodexAttestationReceiptError, match="does not match the configured"):
        _load(binary, receipt)


# ---------------------------------------------------------------------------
# 2b. Fail-closed matrix -- the recorded identity sub-object
# ---------------------------------------------------------------------------


def test_identity_extra_field_is_refused(tmp_path: Path) -> None:
    binary = tmp_path / "codex"
    _write_fake_binary(binary)
    identity = _identity_of(binary)
    identity["extra"] = 1
    receipt = tmp_path / "codex-attestation.json"
    _write_receipt(receipt, binary_path=binary, identity=identity)
    with pytest.raises(cw.CodexAttestationReceiptError, match="identity fields do not match"):
        _load(binary, receipt)


@pytest.mark.parametrize("field", _IDENTITY_FIELDS)
def test_identity_missing_field_is_refused(tmp_path: Path, field: str) -> None:
    binary = tmp_path / "codex"
    _write_fake_binary(binary)
    identity = _identity_of(binary)
    del identity[field]
    receipt = tmp_path / "codex-attestation.json"
    _write_receipt(receipt, binary_path=binary, identity=identity)
    with pytest.raises(cw.CodexAttestationReceiptError, match="identity fields do not match"):
        _load(binary, receipt)


@pytest.mark.parametrize("field", _IDENTITY_FIELDS)
def test_identity_field_wrong_type_is_refused(tmp_path: Path, field: str) -> None:
    binary = tmp_path / "codex"
    _write_fake_binary(binary)
    identity = _identity_of(binary)
    identity[field] = str(identity[field])
    receipt = tmp_path / "codex-attestation.json"
    _write_receipt(receipt, binary_path=binary, identity=identity)
    with pytest.raises(
        cw.CodexAttestationReceiptError, match=f"identity field {field!r} is not an integer"
    ):
        _load(binary, receipt)


def test_identity_bool_value_is_not_silently_accepted_as_int(tmp_path: Path) -> None:
    # bool is technically an int subclass in Python; `type(x) is not int`
    # (rather than `isinstance`) is what keeps a bool from sneaking through.
    binary = tmp_path / "codex"
    _write_fake_binary(binary)
    identity = _identity_of(binary)
    identity["size"] = True
    receipt = tmp_path / "codex-attestation.json"
    _write_receipt(receipt, binary_path=binary, identity=identity)
    with pytest.raises(
        cw.CodexAttestationReceiptError, match="identity field 'size' is not an integer"
    ):
        _load(binary, receipt)


@pytest.mark.parametrize("field", _IDENTITY_FIELDS)
def test_identity_mismatch_on_each_pinned_field_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, field: str
) -> None:
    binary = tmp_path / "codex"
    _write_fake_binary(binary)
    _patch_owner_as_root(monkeypatch, binary)
    identity = _root_owned_identity_of(binary)
    identity[field] = identity[field] + 1
    receipt = tmp_path / "codex-attestation.json"
    _write_receipt(receipt, binary_path=binary, identity=identity)
    with pytest.raises(cw.CodexAttestationReceiptError, match=field):
        _load(binary, receipt)


def test_identity_non_root_binary_owner_is_refused(tmp_path: Path) -> None:
    """The binary's recorded owner must be root.

    No patching needed: this fixture's binary is (correctly, since real
    root isn't available in this test process) owned by the unprivileged
    test process, so the real, unmodified identity already exercises the
    refusal -- the static uid==0 invariant, not a receipt/reality mismatch
    (recorded and observed agree here; both say "not root").
    """
    binary = tmp_path / "codex"
    _write_fake_binary(binary)
    assert os.geteuid() != 0, "this refusal is meaningful only when not already root"
    receipt = tmp_path / "codex-attestation.json"
    _write_receipt(receipt, binary_path=binary)  # real (non-root) identity, untampered
    with pytest.raises(cw.CodexAttestationReceiptError, match="non-root-owned binary"):
        _load(binary, receipt)


def test_identity_group_writable_binary_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    binary = tmp_path / "codex"
    _write_fake_binary(binary)
    binary.chmod(0o775)  # deliberately group/other-writable; still self-consistent
    _patch_owner_as_root(monkeypatch, binary)  # isolate: only the mode invariant is under test
    identity = _root_owned_identity_of(binary)
    receipt = tmp_path / "codex-attestation.json"
    _write_receipt(receipt, binary_path=binary, identity=identity)
    with pytest.raises(cw.CodexAttestationReceiptError, match="group/other-writable binary"):
        _load(binary, receipt)


def test_binary_is_not_mach_o_is_refused(tmp_path: Path) -> None:
    binary = tmp_path / "codex"
    binary.write_bytes(b"#!/bin/sh\necho not a real binary\n")
    binary.chmod(0o500)
    receipt = tmp_path / "codex-attestation.json"
    _write_receipt(receipt, binary_path=binary)
    with pytest.raises(cw.CodexAttestationReceiptError, match="native Mach-O binary"):
        _load(binary, receipt)


def test_binary_missing_is_refused(tmp_path: Path) -> None:
    binary = tmp_path / "codex"
    _write_fake_binary(binary)
    receipt = tmp_path / "codex-attestation.json"
    _write_receipt(receipt, binary_path=binary)
    binary.unlink()
    with pytest.raises(cw.CodexAttestationReceiptError, match="missing or unreadable"):
        _load(binary, receipt)


def test_binary_directory_is_refused(tmp_path: Path) -> None:
    binary_dir = tmp_path / "codex"
    binary_dir.mkdir()
    receipt = tmp_path / "codex-attestation.json"
    identity = {field: 0 for field in _IDENTITY_FIELDS}
    real = _identity_of(binary_dir)
    identity.update(real)  # a directory has a real, self-consistent identity too
    _write_receipt(receipt, binary_path=binary_dir, identity=identity)
    with pytest.raises(cw.CodexAttestationReceiptError, match="not a regular file"):
        _load(binary_dir, receipt)


# ---------------------------------------------------------------------------
# 3. Strengthening proof: a binary physically replaced after install
# ---------------------------------------------------------------------------


def test_binary_replaced_after_install_is_refused_at_startup(tmp_path: Path) -> None:
    """A same-size, same-content, different-inode swap must be refused.

    This is exactly what the earlier, weaker "Option 2" (compare only what
    the receipt already carried, or trust an unpinned config) would have
    missed: nothing about the file's *content* changed here. No root-owned
    patching needed -- the inode/ctime mismatch this proves is caught by
    the dynamic comparison, which runs before the static uid==0 check ever
    gets a chance to fire on this (still real, non-root) fixture.
    """

    binary = tmp_path / "codex"
    _write_fake_binary(binary, payload=b"same-bytes-both-times")
    receipt = tmp_path / "codex-attestation.json"
    _write_receipt(receipt, binary_path=binary)

    original_identity = _identity_of(binary)

    # Replace with a fresh inode carrying byte-identical content and size.
    replacement = tmp_path / "codex.replacement"
    _write_fake_binary(replacement, payload=b"same-bytes-both-times")
    os.replace(replacement, binary)

    new_identity = _identity_of(binary)
    assert new_identity["inode"] != original_identity["inode"]
    assert new_identity["size"] == original_identity["size"]

    with pytest.raises(cw.CodexAttestationReceiptError, match="inode"):
        _load(binary, receipt)


def test_valid_receipt_round_trips_into_a_binary_attestation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    binary, receipt = _fixture(tmp_path, monkeypatch)
    attestation = _load(binary, receipt)
    assert isinstance(attestation, cw.BinaryAttestation)
    assert attestation.version == "0.147.0"
    assert attestation.team_identifier == "2DC432GLL2"
    assert attestation.sha256 == "a" * 64
    assert attestation.real_path == str(binary.resolve(strict=True))


# ---------------------------------------------------------------------------
# 4. check-config exercises the receipt load end to end (Must Fix 6)
# ---------------------------------------------------------------------------


def test_check_config_fails_when_receipt_is_broken(tmp_path: Path) -> None:
    """check-config must not report success while the receipt is unusable.

    Before this fix, check-config validated only the config JSON's shape;
    install would "succeed" with a receipt that could never actually load,
    and the failure would only surface later and silently, when launchd
    first started the daemon.
    """

    from scripts.executive_os_phase1c_worker import main

    binary = tmp_path / "codex"
    _write_fake_binary(binary)
    missing_receipt = tmp_path / "codex-attestation.json"  # never written
    config_path = tmp_path / "worker.json"
    _write_worker_config(
        config_path, codex_binary=binary, codex_attestation_receipt=missing_receipt
    )

    exit_code = main(
        ["check-config", "--config", str(config_path), "--allow-non-root-owner-for-test"]
    )
    assert exit_code == 2


def test_check_config_succeeds_when_receipt_loads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    from scripts.executive_os_phase1c_worker import main

    binary = tmp_path / "codex"
    _write_fake_binary(binary)
    receipt = tmp_path / "codex-attestation.json"
    _write_receipt(receipt, binary_path=binary, identity=_root_owned_identity_of(binary))
    # check-config's real call hardcodes expected_owner_uid=0 for BOTH the
    # receipt file and (via the identity it carries) the binary -- there is
    # no test-only override on that path, by design (Blocker 2). Patch the
    # observed side for both (now that both files exist) so this
    # unprivileged fixture can exercise the real, unweakened check end to
    # end.
    _patch_owner_as_root(monkeypatch, binary, receipt)
    config_path = tmp_path / "worker.json"
    _write_worker_config(config_path, codex_binary=binary, codex_attestation_receipt=receipt)

    exit_code = main(
        ["check-config", "--config", str(config_path), "--allow-non-root-owner-for-test"]
    )
    assert exit_code == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["valid"] is True


# ---------------------------------------------------------------------------
# 5. Install-side: the embedded receipt-writer heredoc
# ---------------------------------------------------------------------------


def _extract_receipt_writer_source() -> str:
    install_text = INSTALL_SH.read_text(encoding="utf-8")
    begin = "# --- BEGIN codex attestation receipt writer ---"
    end = "# --- END codex attestation receipt writer ---"
    assert begin in install_text and end in install_text
    block = install_text.split(begin, 1)[1].split(end, 1)[0]
    assert block.count("<<'PY'") == 1
    heredoc_start = block.index("<<'PY'") + len("<<'PY'")
    body = block[heredoc_start:]
    # The heredoc body runs up to the first line that is exactly "PY".
    lines = body.splitlines()
    end_index = next(i for i, line in enumerate(lines) if line == "PY")
    return "\n".join(lines[1:end_index]) + "\n"


def _run_receipt_writer(
    tmp_path: Path, *, destination: Path, binary: Path, worker_gid: int | str = "20",
    version: str = "0.147.0", team: str = "2DC432GLL2", sha256: str = "f" * 64,
) -> subprocess.CompletedProcess:
    source = _extract_receipt_writer_source()
    script = tmp_path / "receipt_writer.py"
    script.write_text(source, encoding="utf-8")
    return subprocess.run(
        [sys.executable, "-I", "-S", "-B", str(script), str(destination), str(binary),
         version, team, sha256, str(worker_gid)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )


def test_install_sh_receipt_writer_source_is_present_and_ordered() -> None:
    install_text = INSTALL_SH.read_text(encoding="utf-8")
    assert 'CODEX_ATTESTATION_RECEIPT="$SYSTEM_ROOT/codex-attestation-$CODEX_VERSION.json"' in install_text
    assert "mastermind.executive_codex_attestation/v1" in install_text
    assert '"0:$WORKER_GID:440:1"' in install_text
    assert "Codex binary attestation receipt validation failed" in install_text
    assert "failed to record the Codex binary attestation receipt" in install_text
    # Blocker 1: the writer is unconditional now -- no existence guard that
    # could skip rewriting (and thus never recover from a replaced binary).
    writer_block = install_text.split(
        "# --- BEGIN codex attestation receipt writer ---", 1
    )[1].split("# --- END codex attestation receipt writer ---", 1)[0]
    assert 'if [ ! -f "$CODEX_ATTESTATION_RECEIPT" ]' not in writer_block
    assert "os.chown(temporary, -1, int(worker_gid))" in writer_block
    # Ownership and mode land on the temp file BEFORE the rename, in that
    # order relative to os.replace -- no post-rename window.
    chown_index = writer_block.index("os.chown(temporary")
    chmod_index = writer_block.index("os.chmod(temporary")
    replace_index = writer_block.index("os.replace(temporary")
    assert chown_index < replace_index and chmod_index < replace_index
    # The ancestor uid/mode invariant (Must Fix 4) lives in this same block.
    assert "receipt_ancestor" in writer_block
    assert "root-owned and non-group/other-writable" in writer_block
    # The receipt is written+validated only after the existing codesign /
    # version / hash / mode checks on the installed Codex binary succeed.
    codesign_check = install_text.index('/usr/bin/codesign --verify --strict "$INSTALLED_CODEX"')
    receipt_write = install_text.index("# --- BEGIN codex attestation receipt writer ---")
    worker_config_write = install_text.index('"schema_version": "mastermind.executive_worker_broker_config/v3"')
    assert codesign_check < receipt_write < worker_config_write
    # codesign/--version are not invoked again anywhere in the worker's own
    # startup entrypoint or its adapter's fast path.
    worker_entry = (ROOT / "scripts" / "executive_os_phase1c_worker.py").read_text(
        encoding="utf-8"
    )
    assert "codesign" not in worker_entry
    assert "load_codex_attestation_receipt" in worker_entry
    # check-config now exercises the receipt load too (Must Fix 6).
    check_config_branch = worker_entry.split('if args.command == "check-config":', 1)[1]
    assert "load_codex_attestation_receipt(" in check_config_branch.split("return 0", 1)[0]


def test_install_sh_receipt_writer_heredoc_produces_a_valid_receipt(tmp_path: Path) -> None:
    """Execute the exact embedded writer to prove its behavior, not just its text.

    This covers the pure-Python fstat/json logic install.sh runs as root.
    It does NOT cover the surrounding shell (the ancestor uid/mode/ACL
    gate, or the later shell-level 0:$WORKER_GID:440:1 + no-ACL
    re-validation) -- those need root and the real host and are
    review-only; see the source-text test above for what the shell wiring
    asserts around this block.
    """

    binary = tmp_path / "codex-0.147.0"
    _write_fake_binary(binary)
    destination = tmp_path / "codex-attestation.json"

    completed = _run_receipt_writer(
        tmp_path, destination=destination, binary=binary, worker_gid=os.getegid()
    )
    assert completed.returncode == 0, completed.stderr

    assert stat.S_IMODE(destination.stat().st_mode) == 0o440
    assert destination.stat().st_gid == os.getegid()
    document = json.loads(destination.read_text(encoding="utf-8"))
    assert document["schema_version"] == cw.CODEX_ATTESTATION_RECEIPT_SCHEMA_VERSION
    assert document["path"] == str(binary)
    assert document["version"] == "0.147.0"
    assert document["team_identifier"] == "2DC432GLL2"
    assert document["sha256"] == "f" * 64
    assert document["identity"] == _identity_of(binary)

    # The output round-trips through the real loader too. This unprivileged
    # writer subprocess can only ever record a non-root-owned binary (real
    # root ownership needs real root, which install.sh has and this test
    # does not), so the one check that cannot pass here is that specific,
    # environment-only gap -- not a structural defect in the writer's
    # output. Every OTHER check (schema, fields, hard link, mode, size,
    # identity shape, and the identity match against a fresh fstat of the
    # real binary) already passed by the time this fires.
    with pytest.raises(cw.CodexAttestationReceiptError, match="non-root-owned binary"):
        cw.load_codex_attestation_receipt(
            destination,
            expected_binary_path=binary,
            expected_owner_gid=os.getegid(),
            expected_owner_uid=os.geteuid(),
        )


def test_install_sh_receipt_writer_refuses_a_missing_binary(tmp_path: Path) -> None:
    destination = tmp_path / "codex-attestation.json"
    missing_binary = tmp_path / "does-not-exist"

    completed = _run_receipt_writer(
        tmp_path, destination=destination, binary=missing_binary, worker_gid=os.getegid()
    )
    assert completed.returncode != 0
    assert not destination.exists()


def test_install_sh_receipt_writer_rewrites_after_binary_replacement(tmp_path: Path) -> None:
    """Blocker 1, reproduction 1: re-running install after the binary is
    replaced (even byte-identically, at a fresh inode) must SUCCEED and
    produce a receipt matching the NEW binary -- not wedge forever.

    Because the writer is now unconditional (no existence guard), calling
    it twice in a row with a changed binary IS the reproduction: there is
    no separate idempotency-guard code path left to interfere.
    """

    binary = tmp_path / "codex-0.147.0"
    _write_fake_binary(binary, payload=b"original-bytes")
    destination = tmp_path / "codex-attestation.json"

    first = _run_receipt_writer(
        tmp_path, destination=destination, binary=binary, worker_gid=os.getegid()
    )
    assert first.returncode == 0, first.stderr
    first_identity = json.loads(destination.read_text(encoding="utf-8"))["identity"]

    replacement = tmp_path / "codex.replacement"
    _write_fake_binary(replacement, payload=b"original-bytes")  # byte-identical, fresh inode
    os.replace(replacement, binary)
    assert _identity_of(binary)["inode"] != first_identity["inode"]

    second = _run_receipt_writer(
        tmp_path, destination=destination, binary=binary, worker_gid=os.getegid()
    )
    assert second.returncode == 0, second.stderr
    second_identity = json.loads(destination.read_text(encoding="utf-8"))["identity"]
    assert second_identity["inode"] == _identity_of(binary)["inode"]
    assert second_identity["inode"] != first_identity["inode"]

    # And the rewritten receipt is immediately usable by the real loader --
    # it reaches (and only fails on) the environment-only real-root gap
    # this unprivileged writer subprocess cannot honestly satisfy, exactly
    # as in test_install_sh_receipt_writer_heredoc_produces_a_valid_receipt.
    # Reaching that specific, later check -- rather than an earlier
    # structural one -- confirms the REWRITTEN receipt is well-formed and
    # matches the NEW binary's identity.
    with pytest.raises(cw.CodexAttestationReceiptError, match="non-root-owned binary"):
        cw.load_codex_attestation_receipt(
            destination,
            expected_binary_path=binary,
            expected_owner_gid=os.getegid(),
            expected_owner_uid=os.geteuid(),
        )


def test_install_sh_receipt_writer_self_heals_a_corrupted_prior_receipt(tmp_path: Path) -> None:
    """Blocker 1, reproduction 2: whatever garbage or wrong-permission state
    sits at the destination path (modeling an interrupted prior run that
    left the receipt short of its final root:$WORKER_GROUP 0440 shape),
    an unconditional rewrite atomically replaces it with a fresh, correct
    receipt -- it does not skip rewriting because "a file is already
    there", and it does not require the prior state to be valid.
    """

    binary = tmp_path / "codex-0.147.0"
    _write_fake_binary(binary)
    destination = tmp_path / "codex-attestation.json"
    destination.write_text("not even json, and world-writable", encoding="utf-8")
    destination.chmod(0o666)  # simulates a prior run that never reached chmod 0o440

    completed = _run_receipt_writer(
        tmp_path, destination=destination, binary=binary, worker_gid=os.getegid()
    )
    assert completed.returncode == 0, completed.stderr

    assert stat.S_IMODE(destination.stat().st_mode) == 0o440
    document = json.loads(destination.read_text(encoding="utf-8"))
    assert document["identity"] == _identity_of(binary)

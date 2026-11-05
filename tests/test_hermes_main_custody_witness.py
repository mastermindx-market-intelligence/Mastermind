"""Focused checks for the private main-process custody witness.

Four existing owners are exercised here and nowhere else in this change:

* ``common/hermes_role_status_contract.py`` -- the one closed status
  validation owner, now able to read and write the v2 custody document;
* ``integrations/hermes_runtime/role_status_publisher.py`` -- the supervisor's
  own STATUS publisher, with its private in-process ``custody_observer``
  dependency;
* ``integrations/hermes_runtime/cli.py`` -- the private dependency plumbing
  from ``main`` to the existing supervisor construction;
* ``ops/native_fabric/quota_continuity/candidate/linux_process_identity.py``
  -- the existing Linux process identity owner, with its strict live option.

Every test here is hermetic and credentialless.  No PID1, no systemd unit, no
provider, no credential, no network and no real ``/proc`` read happens: the
process-identity seams are replaced with synthetic fixtures and a guard fails
the test if the module under test attempts any real host I/O or any executed
image open.
"""
from __future__ import annotations

import dataclasses
import inspect
import os
from pathlib import Path
import socket
import tempfile
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from common import hermes_role_status_contract as wire
from common import workspace_byok_read_contract as workspace
from integrations.hermes_harness.stack import compose_profile
from integrations.hermes_runtime import cli
from integrations.hermes_runtime import role_status_publisher as publisher
from integrations.hermes_runtime.constants import CONFIG_EXIT
from integrations.hermes_runtime.errors import RuntimeRefusal
from ops.native_fabric.quota_continuity.candidate import linux_process_identity as lpi

SHA = "a" * 40
BOOT = "12345678-1234-1234-1234-123456789abc"
INVOCATION = "1" * 32
ROLE = "mmmeta"

# The exact v1 text the BASE contract produced for the fixture below.  It is
# frozen here so a later change to the v1 bytes, key set or ordering fails
# this check instead of silently redefining the legacy document.
FROZEN_V1_TEXT = (
    "MM_HERMES_ROLE_V1:"
    '{"host_boot_id":"12345678-1234-1234-1234-123456789abc",'
    '"implementation_sha":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",'
    '"invocation_id":"11111111111111111111111111111111",'
    '"metadata":{"proof":{"credential_enrollment":"UNVERIFIED","credentials_read":false,'
    '"provider_called":false,"served_model_verified":false,"service_observed":false},'
    '"reason":"INSTALL_MANIFEST_ABSENT","role":"mmmeta",'
    '"schema":"mastermind.hermes.role_metadata.v1","source_binding":"NOT_ATTESTED",'
    '"state":"ABSENT"},"observed_at_ms":1800000000000,"observed_monotonic_ms":1800000000,'
    '"role":"mmmeta","schema":"mastermind.hermes.role_status.v1"}'
)


def _profile(tmp_path, role=ROLE):
    return compose_profile(role, state_dir=tmp_path / (role + "-state"),
                           hermes_home=tmp_path / (role + "-home"),
                           secrets_file=tmp_path / (role + ".env"))


def _metadata(role=ROLE, state="ABSENT"):
    return {"schema": wire.METADATA_SCHEMA, "role": role, "state": state,
            "reason": "INSTALL_MANIFEST_ABSENT" if state == "ABSENT" else "METADATA_READ_FAILED",
            "source_binding": "NOT_ATTESTED", "proof": workspace.proof()}


def _witness(pid=None, **overrides):
    value = {"pid": os.getpid() if pid is None else pid, "start_ticks": "123456789",
             "uid": 1000, "gid": 1000, "manifest_sha256": "c" * 64, "image_sha256": "e" * 64}
    value.update(overrides)
    return value


def _v1_document(metadata=None):
    return {"schema": wire.STATUS_SCHEMA, "role": ROLE, "host_boot_id": BOOT,
            "invocation_id": INVOCATION, "implementation_sha": SHA,
            "observed_at_ms": 1_800_000_000_000, "observed_monotonic_ms": 1_800_000_000,
            "metadata": _metadata() if metadata is None else metadata}


def _v2_document(custody=None, metadata=None):
    document = _v1_document(metadata)
    document["schema"] = wire.STATUS_SCHEMA_V2
    document["custody"] = _witness() if custody is None else custody
    return document


# ---------------------------------------------------------------------------
# Contract: the one closed validation owner
# ---------------------------------------------------------------------------


def test_v1_encoding_is_byte_identical_to_the_base_contract():
    assert wire.encode_status_text(_v1_document()) == FROZEN_V1_TEXT
    assert len(FROZEN_V1_TEXT.encode("ascii")) == 624


def test_v1_document_shape_is_unchanged_and_carries_no_custody():
    document = wire.validate_status(_v1_document())
    assert set(document) == {"schema", "role", "host_boot_id", "invocation_id",
                             "implementation_sha", "observed_at_ms",
                             "observed_monotonic_ms", "metadata"}
    assert "custody" not in document
    assert document["schema"] == wire.STATUS_SCHEMA
    # The v1 read still round-trips exactly.
    assert wire.decode_status_text(FROZEN_V1_TEXT, expected_role=ROLE) == document


def test_v1_decode_never_accepts_a_v2_text():
    text = wire.encode_status_v2_text(_v2_document())
    assert text.startswith(wire.STATUS_PREFIX_V2)
    with pytest.raises(wire.RoleStatusError):
        wire.decode_status_text(text, expected_role=ROLE)


def test_v1_validator_never_accepts_a_v2_document():
    with pytest.raises(wire.RoleStatusError):
        wire.validate_status(_v2_document())


def test_valid_v2_document_is_read_as_the_closed_custody_object():
    document = wire.validate_status_v2(_v2_document())
    assert document["schema"] == wire.STATUS_SCHEMA_V2
    assert set(document) == set(_v1_document()) | {"custody"}
    assert set(document["custody"]) == {"pid", "start_ticks", "uid", "gid",
                                        "manifest_sha256", "image_sha256"}
    assert wire.decode_status_v2_text(wire.encode_status_v2_text(_v2_document()),
                                      expected_role=ROLE) == document


def test_v1_document_never_satisfies_a_v2_or_custody_required_read():
    with pytest.raises(wire.RoleStatusError):
        wire.validate_status_v2(_v1_document())
    with pytest.raises(wire.RoleStatusError):
        wire.decode_status_v2_text(FROZEN_V1_TEXT, expected_role=ROLE)
    with pytest.raises(wire.RoleStatusError):
        wire.decode_status_text_any(FROZEN_V1_TEXT, expected_role=ROLE, require_custody=True)


def test_status_text_any_reads_either_revision_but_never_degrades_a_custody_read():
    assert wire.decode_status_text_any(FROZEN_V1_TEXT, expected_role=ROLE)["schema"] == wire.STATUS_SCHEMA
    text = wire.encode_status_v2_text(_v2_document())
    assert wire.decode_status_text_any(text, expected_role=ROLE)["schema"] == wire.STATUS_SCHEMA_V2
    assert wire.decode_status_text_any(text, expected_role=ROLE,
                                        require_custody=True)["custody"]["pid"] == os.getpid()
    with pytest.raises(wire.RoleStatusError):
        wire.decode_status_text_any("MM_HERMES_ROLE_V1:not-json", expected_role=ROLE)


@pytest.mark.parametrize("bad", [
    {"pid": 0},
    {"pid": -1},
    {"pid": 2_147_483_648},
    {"pid": True},
    {"pid": "1000"},
    {"start_ticks": "0"},
    {"start_ticks": "0123"},
    {"start_ticks": "-1"},
    {"start_ticks": 123456789},
    {"start_ticks": "9223372036854775808"},
    {"uid": True},
    {"uid": 0},
    {"uid": -1},
    {"uid": 2_147_483_648},
    {"gid": True},
    {"gid": 0},
    {"gid": 2_147_483_648},
    {"manifest_sha256": "C" * 64},
    {"manifest_sha256": "c" * 63},
    {"manifest_sha256": "c" * 65},
    {"image_sha256": "e" * 63},
    {"image_sha256": "not-hex" + "e" * 56},
    {"verified": True},
])
def test_invalid_custody_fields_are_refused(bad):
    with pytest.raises(wire.RoleStatusError):
        wire.validate_custody(_witness(**bad))


def test_custody_object_is_closed_and_rejects_unknown_or_missing_fields():
    # The exact closed key set, asserted here and not read back from the
    # implementation's own constant.
    assert set(wire.validate_custody(_witness())) == {
        "pid", "start_ticks", "uid", "gid", "manifest_sha256", "image_sha256"}
    for extra in ("extra", "verified", "schema", "image_path", "provider"):
        witness = _witness()
        witness[extra] = "x"
        with pytest.raises(wire.RoleStatusError):
            wire.validate_custody(witness)
    missing = _witness()
    del missing["image_sha256"]
    with pytest.raises(wire.RoleStatusError):
        wire.validate_custody(missing)
    with pytest.raises(wire.RoleStatusError):
        wire.validate_custody([_witness()])


def test_custody_start_ticks_accepts_the_exact_kernel_tick_bound():
    assert wire.validate_custody(_witness(start_ticks="1"))["start_ticks"] == "1"
    assert wire.validate_custody(_witness(start_ticks=str((1 << 63) - 1)))["start_ticks"] == str((1 << 63) - 1)


def test_unknown_top_level_field_is_refused_in_a_v2_document():
    document = _v2_document()
    document["provider"] = "synthetic"
    with pytest.raises(wire.RoleStatusError):
        wire.validate_status_v2(document)


def test_encoded_status_ceiling_is_preserved_for_both_revisions():
    assert wire.MAX_STATUS_BYTES == 2048
    for text in (FROZEN_V1_TEXT, wire.encode_status_v2_text(_v2_document())):
        assert len(text.encode("ascii")) <= wire.MAX_STATUS_BYTES


def test_maximum_permitted_v2_document_stays_inside_the_ceiling():
    """The measured bound, not a claim: the largest permitted document."""
    requested = {"provider_id": "p" * 128, "native_provider": "n" * 128,
                 "requested_model": "m" * 128}
    provenance = {"upstream_sha": "b" * 40, "release": "20261105",
                  "manifest_sha256": "c" * 64, "profile_sha256": "d" * 64,
                  "hermes_config_sha256": "e" * 64, "upstream_attested": False}
    metadata = {"schema": wire.METADATA_SCHEMA, "role": ROLE,
                "state": "CONFIGURATION_OBSERVED", "reason": "CONFIGURATION_CONSISTENT",
                "source_binding": "NOT_ATTESTED", "proof": workspace.proof(),
                "requested": requested, "provenance": provenance}
    custody = {"pid": 2_147_483_647, "start_ticks": str((1 << 63) - 1),
               "uid": 2_147_483_647, "gid": 2_147_483_647,
               "manifest_sha256": "c" * 64, "image_sha256": "e" * 64}
    text = wire.encode_status_v2_text(_v2_document(custody=custody, metadata=metadata))
    assert len(text.encode("ascii")) <= wire.MAX_STATUS_BYTES


def test_encoded_ceiling_is_enforced_on_both_revisions(monkeypatch):
    """The byte ceiling binds, not merely the per-field bounds.

    Every permitted field is individually bounded, so the largest valid
    document cannot reach the 2048-byte ceiling on its own.  Lowering the
    ceiling proves that the shared owner actually enforces it for both
    revisions instead of only bounding the fields.
    """
    encoded = wire.encode_status_v2_text(_v2_document())
    monkeypatch.setattr(wire, "MAX_STATUS_BYTES", 100)
    with pytest.raises(wire.RoleStatusError):
        wire.encode_status_v2_text(_v2_document())
    with pytest.raises(wire.RoleStatusError):
        wire.encode_status_text(_v1_document())
    with pytest.raises(wire.RoleStatusError):
        wire.decode_status_v2_text(encoded, expected_role=ROLE)


def test_oversized_metadata_field_is_refused():
    document = _v2_document(metadata=_metadata(state="UNAVAILABLE"))
    document["metadata"]["reason"] = "X" * 3000
    with pytest.raises(wire.RoleStatusError):
        wire.encode_status_v2_text(document)
    with pytest.raises(wire.RoleStatusError):
        wire.encode_status_text(dict(document, schema=wire.STATUS_SCHEMA))


# ---------------------------------------------------------------------------
# Publisher: the private in-process custody dependency
# ---------------------------------------------------------------------------


def _context(profile, address, custody_observer=None):
    return publisher.RoleStatusPublisher(profile.role, profile.state_dir, SHA, BOOT,
                                         INVOCATION, os.getpid(), address,
                                         custody_observer=custody_observer)


def _receiver(directory):
    address = str(Path(directory) / "notify")
    channel = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    channel.bind(address)
    channel.settimeout(0.5)
    return channel, address


def test_publisher_without_a_callback_publishes_only_the_v1_document(tmp_path, monkeypatch):
    profile = _profile(tmp_path)
    monkeypatch.setattr(publisher, "role_metadata", Mock(return_value=_metadata()))
    with tempfile.TemporaryDirectory(prefix="mm-custody-v1-", dir="/tmp") as directory:
        receiver, address = _receiver(directory)
        try:
            context = _context(profile, address)
            assert context.publish() is True
            data = receiver.recv(4096)
        finally:
            receiver.close()
    assert data.startswith(b"STATUS=" + wire.STATUS_PREFIX.encode("ascii"))
    assert wire.STATUS_PREFIX_V2.encode("ascii") not in data
    document = wire.decode_status_text(data[7:].decode(), expected_role=ROLE)
    assert document["schema"] == wire.STATUS_SCHEMA
    assert "custody" not in document


def test_publisher_with_a_callback_publishes_the_v2_custody_document(tmp_path, monkeypatch):
    profile = _profile(tmp_path)
    monkeypatch.setattr(publisher, "role_metadata", Mock(return_value=_metadata()))
    with tempfile.TemporaryDirectory(prefix="mm-custody-v2-", dir="/tmp") as directory:
        receiver, address = _receiver(directory)
        try:
            context = _context(profile, address, custody_observer=lambda: _witness())
            assert context.publish() is True
            data = receiver.recv(4096)
        finally:
            receiver.close()
    assert data.startswith(b"STATUS=" + wire.STATUS_PREFIX_V2.encode("ascii"))
    document = wire.decode_status_v2_text(data[7:].decode(), expected_role=ROLE)
    assert document["custody"] == _witness()
    assert document["metadata"]["state"] == "ABSENT"


def test_callback_is_called_around_the_metadata_acquisition(tmp_path, monkeypatch):
    profile = _profile(tmp_path)
    order = []

    def observer():
        order.append("custody")
        return _witness()

    def reader(state_dir, role):
        order.append("metadata")
        return _metadata()

    monkeypatch.setattr(publisher, "role_metadata", reader)
    with tempfile.TemporaryDirectory(prefix="mm-custody-order-", dir="/tmp") as directory:
        receiver, address = _receiver(directory)
        try:
            assert _context(profile, address, custody_observer=observer).publish() is True
            receiver.recv(4096)
        finally:
            receiver.close()
    assert order == ["custody", "metadata", "custody"]


def test_drifting_witness_sends_nothing(tmp_path, monkeypatch):
    profile = _profile(tmp_path)
    monkeypatch.setattr(publisher, "role_metadata", Mock(return_value=_metadata()))
    witnesses = iter([_witness(), _witness(start_ticks="999")])
    with tempfile.TemporaryDirectory(prefix="mm-custody-drift-", dir="/tmp") as directory:
        receiver, address = _receiver(directory)
        try:
            context = _context(profile, address,
                               custody_observer=lambda: next(witnesses))
            assert context.publish() is False
            with pytest.raises(socket.timeout):
                receiver.recv(4096)
        finally:
            receiver.close()


def test_failing_callback_sends_nothing(tmp_path, monkeypatch):
    profile = _profile(tmp_path)
    monkeypatch.setattr(publisher, "role_metadata", Mock(return_value=_metadata()))
    with tempfile.TemporaryDirectory(prefix="mm-custody-fail-", dir="/tmp") as directory:
        receiver, address = _receiver(directory)
        try:
            context = _context(profile, address,
                               custody_observer=Mock(side_effect=RuntimeError("synthetic")))
            assert context.publish() is False
            with pytest.raises(socket.timeout):
                receiver.recv(4096)
        finally:
            receiver.close()


def test_missing_or_invalid_witness_sends_nothing(tmp_path, monkeypatch):
    profile = _profile(tmp_path)
    monkeypatch.setattr(publisher, "role_metadata", Mock(return_value=_metadata()))
    cases = [
        lambda: None,
        lambda: {},
        lambda: _witness(pid=os.getpid() + 1),
        lambda: _witness(uid=True),
        lambda: _witness(start_ticks="0"),
        lambda: dict(_witness(), extra="x"),
    ]
    with tempfile.TemporaryDirectory(prefix="mm-custody-invalid-", dir="/tmp") as directory:
        receiver, address = _receiver(directory)
        try:
            for case in cases:
                context = _context(profile, address, custody_observer=case)
                assert context.publish() is False
            with pytest.raises(socket.timeout):
                receiver.recv(4096)
        finally:
            receiver.close()


def test_forked_publisher_sends_nothing_and_never_measures(tmp_path, monkeypatch):
    profile = _profile(tmp_path)
    monkeypatch.setattr(publisher, "role_metadata", Mock(return_value=_metadata()))
    observer = Mock(side_effect=AssertionError("a forked publisher must not measure"))
    with tempfile.TemporaryDirectory(prefix="mm-custody-fork-", dir="/tmp") as directory:
        receiver, address = _receiver(directory)
        try:
            context = dataclasses.replace(_context(profile, address,
                                                   custody_observer=observer),
                                          process_pid=os.getpid() + 1)
            assert context.publish() is False
            with pytest.raises(socket.timeout):
                receiver.recv(4096)
        finally:
            receiver.close()
    observer.assert_not_called()


def test_publisher_refuses_a_non_callable_custody_dependency(tmp_path):
    profile = _profile(tmp_path)
    with pytest.raises(RuntimeRefusal, match="ROLE_STATUS_CONTEXT_INVALID"):
        _context(profile, "/tmp/fixture-notify", custody_observer="not-callable")


def test_publication_failure_keeps_the_incident_failure_containment(tmp_path, monkeypatch):
    """A failed custody read never reaches the socket and never raises."""
    profile = _profile(tmp_path)
    reader = Mock(side_effect=RuntimeError("synthetic-private-error"))
    monkeypatch.setattr(publisher, "role_metadata", reader)
    socket_factory = Mock(side_effect=AssertionError("no socket after a refused witness"))
    monkeypatch.setattr(publisher, "socket", SimpleNamespace(AF_UNIX=1, SOCK_DGRAM=2,
                                                             socket=socket_factory))
    context = _context(profile, "/tmp/fixture-notify", custody_observer=lambda: _witness())
    assert context.publish() is False
    socket_factory.assert_not_called()


def test_an_invalid_witness_is_refused_before_any_metadata_read(tmp_path, monkeypatch):
    profile = _profile(tmp_path)
    reader = Mock(side_effect=AssertionError("metadata read after a refused witness"))
    monkeypatch.setattr(publisher, "role_metadata", reader)
    socket_factory = Mock(side_effect=AssertionError("no socket after a refused witness"))
    monkeypatch.setattr(publisher, "socket", SimpleNamespace(AF_UNIX=1, SOCK_DGRAM=2,
                                                             socket=socket_factory))
    context = _context(profile, "/tmp/fixture-notify", custody_observer=lambda: None)
    assert context.publish() is False
    reader.assert_not_called()
    socket_factory.assert_not_called()


# ---------------------------------------------------------------------------
# CLI: the private dependency plumbing
# ---------------------------------------------------------------------------


def test_main_forwards_the_private_custody_observer_to_the_supervisor(monkeypatch):
    seen = {}

    def fake_supervise(args, *, custody_observer=None):
        seen["observer"] = custody_observer
        return 0

    monkeypatch.setattr(cli, "_supervise", fake_supervise)
    observer = lambda: {}
    assert cli.main(["supervise", "--profile", "/tmp/fixture.yaml",
                      "--hermes-bin", "/tmp/fixture-hermes"],
                     custody_observer=observer) == 0
    assert seen["observer"] is observer


def test_supervise_hands_the_observer_to_the_publisher(tmp_path, monkeypatch):
    profile = _profile(tmp_path)
    monkeypatch.setattr(cli, "load_profile", lambda *_a, **_k: profile)
    from integrations.hermes_runtime import role_isolation, system_service, tcp_sandbox
    monkeypatch.setattr(system_service, "assert_root_service_cgroup", lambda _role: None)
    monkeypatch.setattr(system_service, "assert_role_network_profile", lambda _profile: None)
    monkeypatch.setattr(role_isolation, "assert_role_credential_isolation", lambda _profile: None)
    monkeypatch.setattr(tcp_sandbox, "enforce_role_tcp_ports", lambda _profile: None)
    captured = {}

    def fake_from_process(profile, custody_observer=None):
        captured["observer"] = custody_observer
        raise RuntimeRefusal("ROLE_STATUS_CONTEXT_INVALID")

    monkeypatch.setattr(publisher, "publisher_from_process", fake_from_process)
    read_secrets = Mock(side_effect=AssertionError("credential read before context validation"))
    monkeypatch.setattr(cli, "load_secrets", read_secrets)
    observer = lambda: {}
    args = SimpleNamespace(profile=tmp_path / "profile.yaml", state=None,
                            secrets_file=None, hermes_bin=Path("/fixture/hermes"))
    assert cli._supervise(args, custody_observer=observer) == CONFIG_EXIT
    assert captured["observer"] is observer
    read_secrets.assert_not_called()


def test_publisher_from_process_without_a_callback_stays_v1(tmp_path, monkeypatch):
    profile = _profile(tmp_path)
    monkeypatch.setattr(publisher.sys, "platform", "linux")
    monkeypatch.setenv(publisher.IMPLEMENTATION_ENV, SHA)
    monkeypatch.setenv("INVOCATION_ID", INVOCATION)
    monkeypatch.setenv("NOTIFY_SOCKET", "/run/systemd/notify")
    monkeypatch.setenv("SYSTEMD_EXEC_PID", str(os.getpid()))
    monkeypatch.setattr(publisher, "_read_boot_id", lambda: BOOT)
    context = publisher.publisher_from_process(profile)
    assert context.custody_observer is None
    assert publisher.publisher_from_process(profile, custody_observer=lambda: _witness()
                                            ).custody_observer is not None


# ---------------------------------------------------------------------------
# Linux process identity: the strict live option
# ---------------------------------------------------------------------------

_PROC_ROOT_FD = 7301
_PID_DIR_FD = 7402


def _synthetic_stat(pid=4242, state=b"S", start_ticks=123456789):
    rest = [state, 1, pid, pid, 3489, 3489, 4202624, 1000, 0, 0, 0, 40, 3, 0, 0, 20,
            0, 4, 0, start_ticks, 219136, 512]
    rest_bytes = b" ".join(field if isinstance(field, bytes) else str(field).encode("ascii")
                            for field in rest)
    return str(pid).encode("ascii") + b" (mm-broker) " + rest_bytes


def _synthetic_status(pid=4242, ppid=1):
    return (b"Name:\tmm-broker\nUmask:\t0022\nState:\tS (sleeping)\nTgid:\t%d\nNgid:\t0\n"
            b"Pid:\t%d\nPPid:\t%d\nTracerPid:\t0\nUid:\t1000\t1000\t1000\t1000\n"
            b"Gid:\t1000\t1000\t1000\t1000\nFDSize:\t64\nVmRSS:\t1024 kB\nThreads:\t4\n"
            b"voluntary_ctxt_switches:\t12\n") % (pid, pid, ppid)


@pytest.fixture
def inert_proc(monkeypatch):
    """Replace every OS seam; forbid real host I/O and any image open."""
    forbidden = Mock(side_effect=AssertionError("module attempted real host I/O"))
    for name in ("open", "read", "sysconf"):
        monkeypatch.setattr(lpi.os, name, forbidden)
    monkeypatch.setattr(lpi, "_open_proc_root", lambda: _PROC_ROOT_FD)
    monkeypatch.setattr(lpi, "_open_proc_pid_dir", lambda fd, pid: _PID_DIR_FD)
    monkeypatch.setattr(lpi, "_close_fd", lambda fd: None)
    opened = Mock(side_effect=AssertionError("the live non-image path opened the image"))
    monkeypatch.setattr(lpi, "_open_proc_exe_image", opened)
    return opened


def _serve(monkeypatch, stats, statuses):
    queue = {"stat": list(stats), "status": list(statuses)}

    def fake_read_proc_file(dir_fd, name, limit, label):
        assert dir_fd == _PID_DIR_FD
        assert name not in ("environ", "cmdline")
        pending = queue.get(name)
        if not pending:
            raise AssertionError(f"unexpected {name!r} read")
        return pending.pop(0)

    monkeypatch.setattr(lpi, "_read_proc_file", fake_read_proc_file)


def test_live_non_image_identity_is_returned_without_opening_the_image(inert_proc, monkeypatch):
    _serve(monkeypatch, [_synthetic_stat(), _synthetic_stat()],
           [_synthetic_status(), _synthetic_status()])
    identity = lpi.inspect_linux_process(4242, require_live=True)
    assert identity["start_identity"] == "123456789"
    assert identity["effective_uid"] == 1000 and identity["real_uid"] == 1000
    assert identity["effective_gid"] == 1000 and identity["real_gid"] == 1000
    assert identity["parent_pid"] == 1
    inert_proc.assert_not_called()


def test_live_non_image_identity_refuses_a_zombie(inert_proc, monkeypatch):
    _serve(monkeypatch, [_synthetic_stat(state=b"Z")], [])
    with pytest.raises(lpi.LinuxProcessIdentityError, match="zombie"):
        lpi.inspect_linux_process(4242, require_live=True)
    inert_proc.assert_not_called()


def test_default_identity_still_reports_a_zombie_process(inert_proc, monkeypatch):
    """The default API keeps its historical behaviour exactly."""
    _serve(monkeypatch, [_synthetic_stat(state=b"Z"), _synthetic_stat(state=b"Z")],
           [_synthetic_status(), _synthetic_status()])
    identity = lpi.inspect_linux_process(4242)
    assert identity["start_identity"] == "123456789"
    inert_proc.assert_not_called()


def test_live_option_is_keyword_only_and_preserves_the_existing_signature():
    signature = inspect.signature(lpi.inspect_linux_process)
    assert list(signature.parameters) == ["pid", "require_live"]
    assert signature.parameters["require_live"].kind is inspect.Parameter.KEYWORD_ONLY
    assert signature.parameters["require_live"].default is False



def test_custody_validation_detaches_the_six_scalar_measurements():
    original = _witness()
    captured = wire.validate_custody(original)
    original["start_ticks"] = "999"
    assert captured["start_ticks"] == "123456789"


def test_mutating_and_returning_the_same_witness_sends_nothing(tmp_path, monkeypatch):
    profile = _profile(tmp_path)
    monkeypatch.setattr(publisher, "role_metadata", Mock(return_value=_metadata()))
    shared = _witness()
    calls = []
    def observer():
        calls.append(1)
        if len(calls) == 2:
            shared["start_ticks"] = "999"
        return shared
    with tempfile.TemporaryDirectory(prefix="mm-custody-alias-", dir="/tmp") as directory:
        receiver, address = _receiver(directory)
        try:
            assert _context(profile, address, custody_observer=observer).publish() is False
            assert len(calls) == 2
            with pytest.raises(socket.timeout):
                receiver.recv(4096)
        finally:
            receiver.close()


@pytest.mark.parametrize("closing_state", [b"Z", b"X", b"x"])
def test_live_non_image_identity_refuses_death_during_the_bracket(inert_proc, monkeypatch, closing_state):
    _serve(monkeypatch, [_synthetic_stat(), _synthetic_stat(state=closing_state)],
           [_synthetic_status(), _synthetic_status()])
    with pytest.raises(lpi.LinuxProcessIdentityError, match="zombie"):
        lpi.inspect_linux_process(4242, require_live=True)
    inert_proc.assert_not_called()


def test_both_live_packaging_surfaces_keep_one_process_identity_implementation():
    root = Path(__file__).resolve().parents[1]
    assert (root / "control_plane/linux_process_identity.py").read_bytes() == (
        root / "ops/native_fabric/quota_continuity/candidate/linux_process_identity.py").read_bytes()

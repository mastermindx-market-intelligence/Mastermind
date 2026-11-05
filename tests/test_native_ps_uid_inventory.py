"""Native signed UID rendering, without live process or service effects."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from control_plane import executive_recovery_host_observation as host
from control_plane import executive_recovery_observation_normalization as norm


# Reduced from the fixed macOS ps command on 2026-10-15. Apple ps uses the
# signed UIDFMT "d" even though uid_t is uint32_t; nobody appears as -2.
NATIVE = b"    1     0\n  771    -2\n 1000     0\n 1001     0\n"


def test_native_nobody_row_preserves_all_root_processes():
    assert norm.normalize_root_inventory(0, NATIVE, b"") == (1, 1000, 1001)


def test_host_inventory_removes_only_its_settled_command_child(monkeypatch):
    monkeypatch.setattr(host, "os", SimpleNamespace(getpid=lambda: 1000))
    command = Mock(return_value=(0, NATIVE, b"", 1001))
    monkeypatch.setattr(host.release, "_command", command)
    budget = SimpleNamespace(call=lambda fn, *a, **kw: fn(*a, **kw))
    assert host._root_pids(budget) == (1, 1000)
    command.assert_called_once_with(
        host.release._ROOT_PID_UID_ARGV, budget, include_owned_inventory_pid=True
    )


@pytest.mark.parametrize("uid", [-2147483648, -2, -1, 0, 501, 2147483647, 4294967295])
def test_signed_and_unsigned_uid_boundaries_never_alias_root(uid):
    raw = b"1 0\n" + f"23 {uid}\n".encode("ascii")
    assert norm.normalize_root_inventory(0, raw, b"") == (
        (1, 23) if uid == 0 else (1,)
    )


@pytest.mark.parametrize("uid", [
    "-2147483649", "-4294967296", "4294967296", "-0", "-00", "-01",
    "+0", "+1", "00", "01", "0x0", "1.0", "root", "-", "0 extra",
])
def test_noncanonical_or_out_of_range_uid_refuses_entire_inventory(uid):
    with pytest.raises(norm.ObservationRejected):
        norm.normalize_root_inventory(0, b"1 0\n" + f"23 {uid}\n".encode(), b"")


@pytest.mark.parametrize("raw", [
    b"1 -2\n23 0\n",                         # PID1 must still be root.
    NATIVE + b"771 4294967294\n",             # Duplicate nonroot PID.
    NATIVE + b"1000 -2\n",                   # Duplicate crossing UID classes.
    NATIVE + b"0 -2\n", NATIVE + b"-1 0\n", # Invalid PIDs remain invalid.
    NATIVE + b"2147483648 0\n",               # PID overflow.
    NATIVE[:-1], NATIVE + b"\n",              # Missing terminator / empty row.
    NATIVE + b"24 \xff\n",                   # Non-ASCII input.
])
def test_native_uid_does_not_relax_other_inventory_invariants(raw):
    with pytest.raises(norm.ObservationRejected):
        norm.normalize_root_inventory(0, raw, b"")


@pytest.mark.parametrize("rc,err", [(1, b""), (True, b""), (0, b"warning\n")])
def test_native_uid_cannot_override_failed_command(rc, err):
    with pytest.raises(norm.ObservationRejected):
        norm.normalize_root_inventory(rc, NATIVE, err)


@pytest.mark.parametrize("child", [771, 1000, 9999])
def test_native_nonroot_row_cannot_supply_owned_root_child(monkeypatch, child):
    monkeypatch.setattr(host, "os", SimpleNamespace(getpid=lambda: 1000))
    monkeypatch.setattr(host.release, "_command", Mock(return_value=(0, NATIVE, b"", child)))
    budget = SimpleNamespace(call=lambda fn, *a, **kw: fn(*a, **kw))
    with pytest.raises(host.HostObservationError, match="RECOVERY_INVENTORY_CHILD_UNSETTLED"):
        host._root_pids(budget)
